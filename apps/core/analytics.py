"""Analytics + simple AI attendance-shortage prediction."""
from collections import defaultdict
from datetime import timedelta

import numpy as np
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.academics.models import Student, Subject
from apps.attendance.models import Attendance
from apps.attendance import services
from . import conf

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _pct(p, l, a):
    held = p + l + a
    late_ok = conf.get("late_counts_as_present", bool)
    return round(100.0 * (p + (l if late_ok else 0)) / held, 1) if held else 0.0


def overview(qs=None):
    qs = Attendance.objects.all() if qs is None else qs
    today = timezone.localdate()
    t = qs.filter(date=today)
    agg = lambda q: q.aggregate(P=Count("id", filter=Q(status="P")), L=Count("id", filter=Q(status="L")),
                                A=Count("id", filter=Q(status="A")), E=Count("id", filter=Q(status="E")))
    a_all, a_today = agg(qs), agg(t)
    return {"total_students": Student.objects.count(), "today": a_today, "overall": a_all,
            "overall_pct": _pct(a_all["P"], a_all["L"], a_all["A"])}


def subject_trends(qs=None):
    qs = Attendance.objects.all() if qs is None else qs
    rows = qs.values("subject__code").annotate(P=Count("id", filter=Q(status="P")), L=Count("id", filter=Q(status="L")),
                                                A=Count("id", filter=Q(status="A"))).order_by("subject__code")
    return [{"label": r["subject__code"], "pct": _pct(r["P"], r["L"], r["A"])} for r in rows]


def monthly_trends(qs=None):
    qs = Attendance.objects.all() if qs is None else qs
    rows = qs.annotate(m=TruncMonth("date")).values("m").annotate(
        P=Count("id", filter=Q(status="P")), L=Count("id", filter=Q(status="L")), A=Count("id", filter=Q(status="A"))).order_by("m")
    return [{"label": r["m"].strftime("%b %Y"), "pct": _pct(r["P"], r["L"], r["A"]), "absent": r["A"]} for r in rows if r["m"]]


def weekday_absenteeism(qs=None):
    qs = Attendance.objects.filter(status="A") if qs is None else qs.filter(status="A")
    counts = [0] * 7
    for d in qs.values_list("date", flat=True):
        counts[d.weekday()] += 1
    return [{"label": WEEKDAYS[i], "absent": c} for i, c in enumerate(counts)]


def low_attendance_students(limit=10):
    minimum = conf.get("min_attendance_percent", float) or 75.0
    rows = Attendance.objects.values("student_id").annotate(
        P=Count("id", filter=Q(status="P")), L=Count("id", filter=Q(status="L")), A=Count("id", filter=Q(status="A")))
    out = []
    names = {s.pk: s for s in Student.objects.select_related("user")}
    for r in rows:
        if r["P"] + r["L"] + r["A"] < 3:
            continue
        pct = _pct(r["P"], r["L"], r["A"])
        if pct < minimum:
            s = names[r["student_id"]]
            out.append({"student": s, "pct": pct, "absent": r["A"]})
    return sorted(out, key=lambda x: x["pct"])[:limit]


def predict_shortage(student, subject):
    """Forecast final attendance: exponentially-weighted recent attendance rate projected over the
    remaining planned classes. Flags risk when projected % < required minimum.
    (Pure-numpy; swap for sklearn LogisticRegression/ARIMA for a stronger model.)"""
    recs = list(Attendance.objects.filter(student=student, subject=subject).exclude(status="E").order_by("date", "id")
                .values_list("status", flat=True))
    if len(recs) < 3:
        return None
    late_ok = conf.get("late_counts_as_present", bool)
    y = np.array([1.0 if (s == "P" or (s == "L" and late_ok)) else 0.0 for s in recs])
    w = np.exp(np.linspace(-2, 0, len(y)))
    recent_rate = float((y * w).sum() / w.sum())
    total_planned = conf.get("semester_total_classes", int) or 40
    held, attended = len(y), float(y.sum())
    remaining = max(0, total_planned - held)
    projected = 100.0 * (attended + recent_rate * remaining) / max(total_planned, held)
    minimum = conf.get("min_attendance_percent", float) or 75.0
    need = max(0, int(np.ceil(minimum / 100 * max(total_planned, held) - attended)))
    return {"projected": round(projected, 1), "recent_rate": round(recent_rate * 100, 1), "remaining": remaining,
            "must_attend": need, "feasible": need <= remaining, "at_risk": projected < minimum}


def at_risk_predictions(limit=8):
    out = []
    for st in Student.objects.select_related("user", "course"):
        for sub in Subject.objects.filter(course=st.course, semester=st.semester):
            p = predict_shortage(st, sub)
            if p and p["at_risk"]:
                out.append({"student": st, "subject": sub, **p})
    return sorted(out, key=lambda x: x["projected"])[:limit]
