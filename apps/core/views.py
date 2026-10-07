from django.contrib import messages
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import admin_required, role_required, student_required
from apps.academics.models import Student, Teacher, Timetable, Course, Subject, Classroom
from apps.attendance import services
from apps.attendance.models import Attendance, AttendanceSession, AttendanceCorrection
from . import analytics, conf
from .audit import log_action
from .models import AuditLog, Notification, SystemSetting


def home(request):
    return redirect("dashboard" if request.user.is_authenticated else "login")


@role_required("ADMIN", "TEACHER", "STUDENT")
def dashboard(request):
    u = request.user
    if u.is_superuser or u.role == "ADMIN":
        return redirect("admin_dashboard")
    if u.role == "TEACHER":
        return redirect("teacher_dashboard")
    return redirect("student_dashboard")


def _analytics_ctx(qs=None):
    ov = analytics.overview(qs)
    t = ov["today"]
    cards = [("Total students", ov["total_students"], "bi-people", "primary"), ("Present today", t["P"], "bi-check-circle", "success"),
             ("Late today", t["L"], "bi-clock", "warning"), ("Absent today", t["A"], "bi-x-circle", "danger"),
             ("Overall attendance", f'{ov["overall_pct"]}%', "bi-percent", "info")]
    return {"stat_cards": cards, "ov": ov, "subject_trend": analytics.subject_trends(qs), "monthly": analytics.monthly_trends(qs),
            "weekday": analytics.weekday_absenteeism(qs), "low": analytics.low_attendance_students(),
            "risk": analytics.at_risk_predictions(),
            "min_pct": conf.get("min_attendance_percent", float) or 75}


@role_required("ADMIN", "TEACHER")
def analytics_dashboard(request):
    qs = None
    if not (request.user.is_superuser or request.user.role == "ADMIN"):
        qs = Attendance.objects.filter(session__teacher__user=request.user)
    return render(request, "core/analytics.html", _analytics_ctx(qs))


@role_required("ADMIN")
def admin_dashboard(request):
    ctx = _analytics_ctx()
    ctx.update(counts={"students": Student.objects.count(), "teachers": Teacher.objects.count(), "courses": Course.objects.count(),
                       "subjects": Subject.objects.count(), "classrooms": Classroom.objects.count(),
                       "face": Student.objects.filter(face_embeddings__isnull=False).distinct().count(),
                       "iris": Student.objects.filter(iris_templates__isnull=False).distinct().count()},
               active_sessions=AttendanceSession.objects.filter(status="ACTIVE").select_related("subject", "classroom"),
               pending=AttendanceCorrection.objects.filter(status="PENDING").count(),
               audit=AuditLog.objects.select_related("user")[:8])
    return render(request, "admin_panel/dashboard.html", ctx)


@student_required
def student_dashboard(request):
    st = get_object_or_404(Student.objects.select_related("user", "course"), user=request.user)
    rows = services.subject_breakdown(st)
    slots = Timetable.objects.filter(subject__course=st.course, subject__semester=st.semester).select_related("subject", "teacher__user", "classroom")
    hist = Attendance.objects.filter(student=st).select_related("subject", "classroom").order_by("-date", "-time")
    page = Paginator(hist, 10).get_page(request.GET.get("page"))
    preds = [dict(subject=r["subject"], **p) for r in rows if (p := analytics.predict_shortage(st, r["subject"]))]
    return render(request, "student/dashboard.html", {
        "st": st, "rows": rows, "overall": services.student_percentage(st), "slots": slots, "page": page, "preds": preds,
        "min_pct": conf.get("min_attendance_percent", float) or 75,
        "face_n": st.face_embeddings.filter(is_active=True).count(), "iris_n": st.iris_templates.count(),
        "notes": request.user.notifications.all()[:6],
        "days": Timetable.DAYS})


# ---------------------------------------------------------------- notifications
@role_required("ADMIN", "TEACHER", "STUDENT")
def notifications(request):
    qs = request.user.notifications.all()
    page = Paginator(qs, 15).get_page(request.GET.get("page"))
    return render(request, "core/notifications.html", {"page": page})


@role_required("ADMIN", "TEACHER", "STUDENT")
@require_POST
def notifications_read(request):
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return redirect("notifications")


@role_required("ADMIN")
@require_POST
def send_low_attendance_alerts(request):
    n = 0
    for st in Student.objects.select_related("user", "course"):
        for sub in Subject.objects.filter(course=st.course, semester=st.semester):
            n += services.check_low_attendance(st, sub)
    log_action(request.user, "LOW_ATTENDANCE_ALERTS", "", f"{n} alerts", request)
    messages.success(request, f"{n} low-attendance alert(s) sent.")
    return redirect("admin_dashboard")


# ---------------------------------------------------------------- settings & audit
@admin_required
def system_settings(request):
    conf.ensure_defaults()
    if request.method == "POST":
        for s in SystemSetting.objects.all():
            if s.key in request.POST:
                val = request.POST[s.key].strip()
                if val != "" and not _valid(val):
                    messages.error(request, f"Invalid value for {s.key}.")
                    return redirect("system_settings")
                s.value = val
                s.save()
        conf.clear_cache()
        from apps.biometrics.services import recognition
        recognition.invalidate_gallery()
        log_action(request.user, "SETTINGS_UPDATE", "", "", request)
        messages.success(request, "Settings saved.")
        return redirect("system_settings")
    return render(request, "admin_panel/settings.html", {"items": SystemSetting.objects.all()})


def _valid(v):
    try:
        float(v)
        return True
    except ValueError:
        return False


@admin_required
def audit_log(request):
    qs = AuditLog.objects.select_related("user")
    q = request.GET.get("q", "").strip()
    if q:
        from django.db.models import Q
        qs = qs.filter(Q(action__icontains=q) | Q(target__icontains=q) | Q(user__username__icontains=q) | Q(details__icontains=q))
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    return render(request, "admin_panel/audit.html", {"page": page, "q": q})
