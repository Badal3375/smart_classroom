import json
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import admin_required, teacher_required
from apps.academics.models import Classroom, Student, Subject, Teacher
from apps.biometrics.services import recognition
from apps.biometrics.utils import decode_b64, decode_file, limit_size
from apps.core import conf
from apps.core.audit import log_action
from . import services
from .models import Attendance, AttendanceCorrection, AttendanceSession


def _teacher_for(request):
    if request.user.is_superuser or request.user.role == "ADMIN":
        return Teacher.objects.first()
    return get_object_or_404(Teacher, user=request.user)


def _own_session(request, pk):
    s = get_object_or_404(AttendanceSession.objects.select_related("subject", "classroom", "teacher__user"), pk=pk)
    if not (request.user.is_superuser or request.user.role == "ADMIN") and s.teacher.user_id != request.user.id:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    return s


# ------------------------------------------------------------------ sessions
@teacher_required
def teacher_dashboard(request):
    t = _teacher_for(request)
    today = timezone.localdate()
    slots = t.slots.filter(weekday=today.weekday()).select_related("subject", "classroom") if t else []
    active = AttendanceSession.objects.filter(teacher=t, status="ACTIVE").select_related("subject", "classroom") if t else []
    recent = AttendanceSession.objects.filter(teacher=t).select_related("subject", "classroom")[:8] if t else []
    return render(request, "teacher/dashboard.html", {
        "teacher": t, "slots": slots, "active": active, "recent": recent,
        "subjects": t.subjects.all() if t else [], "classrooms": Classroom.objects.all(), "demo": settings.DEMO_MODE})


@teacher_required
@require_POST
def session_start(request):
    t = _teacher_for(request)
    subject = get_object_or_404(Subject, pk=request.POST.get("subject"))
    room = get_object_or_404(Classroom, pk=request.POST.get("classroom"))
    if not request.user.is_superuser and not t.subjects.filter(pk=subject.pk).exists():
        messages.error(request, "You are not assigned to that subject.")
        return redirect("teacher_dashboard")
    if AttendanceSession.objects.filter(subject=subject, date=timezone.localdate(), status="ACTIVE").exists():
        messages.warning(request, "A session for this subject is already running.")
        return redirect("session_live", pk=AttendanceSession.objects.filter(subject=subject, status="ACTIVE").first().pk)
    mode = "demo" if request.POST.get("mode") == "demo" and settings.DEMO_MODE else "camera"
    s = services.start_session(subject, t, room, mode)
    log_action(request.user, "SESSION_START", f"session:{s.pk}", f"{subject.code} {room.name} {mode}", request)
    return redirect("session_live", pk=s.pk)


@teacher_required
def session_live(request, pk):
    s = _own_session(request, pk)
    return render(request, "teacher/live.html", {
        "s": s, "total": services.eligible_students(s).count(), "demo": settings.DEMO_MODE, "is_demo": s.mode == "demo"})


@teacher_required
@require_POST
def session_end(request, pk):
    s = _own_session(request, pk)
    n = services.end_session(s)
    log_action(request.user, "SESSION_END", f"session:{s.pk}", f"{n} marked absent", request)
    messages.success(request, f"Session ended. {n} student(s) marked absent.")
    return redirect("session_detail", pk=s.pk)


def _feed(session):
    recs = session.records.exclude(method="auto").select_related("student__user").order_by("-created_at")
    total = services.eligible_students(session).count()
    from django.db.models import Count
    c = {r["status"]: r["n"] for r in session.records.values("status").annotate(n=Count("id"))}
    return {
        "present": c.get("P", 0), "late": c.get("L", 0), "absent": c.get("A", 0), "excused": c.get("E", 0),
        "marked": recs.count(), "total": total, "status": session.status,
        "recent": [{"id": r.pk, "roll": r.student.roll_no, "name": r.student.name, "status": r.get_status_display(),
                    "code": r.status, "time": r.time.strftime("%H:%M:%S") if r.time else "", "confidence": round(r.confidence * 100, 1),
                    "method": r.method} for r in recs[:30]],
    }


@teacher_required
def session_feed(request, pk):
    return JsonResponse(_feed(_own_session(request, pk)))


def _process(session, frame, eyes=None, allow_fallback=False):
    cand = list(services.eligible_students(session).values_list("pk", flat=True))
    results = recognition.recognize(frame, cand, eye_images=eyes, allow_fallback=allow_fallback)
    out = []
    for r in results:
        item = {"box": list(r["box"]), "status": r["status"], "face_score": r["face_score"], "iris_score": r["iris_score"],
                "confidence": r["confidence"], "method": r["method"], "message": r["message"], "liveness": r["liveness"]}
        if r["status"] == "matched":
            st = Student.objects.select_related("user").get(pk=r["student_id"])
            rec, created = services.mark_attendance(session, st, r["confidence"], r["face_score"], r["iris_score"], r["method"])
            item.update(student=st.name, roll=st.roll_no, new=created, attendance=rec.get_status_display(),
                        message="Attendance marked" if created else "Already marked - duplicate ignored")
            if rec.status == "A" and not created:  # previously auto-absent (shouldn't happen mid-session) -> leave
                pass
        elif r["status"] == "needs_iris" and r["student_id"]:
            st = Student.objects.select_related("user").get(pk=r["student_id"])
            item.update(student=st.name, roll=st.roll_no)
        out.append(item)
    return out


@teacher_required
@require_POST
def session_frame(request, pk):
    """Receives a camera frame (base64 JSON) or an uploaded image/video-frame file."""
    s = _own_session(request, pk)
    if s.status != "ACTIVE":
        return JsonResponse({"ok": False, "error": "Session is not active."}, status=400)
    frame, eyes = None, None
    if request.content_type.startswith("application/json"):
        body = json.loads(request.body or "{}")
        frame = limit_size(decode_b64(body.get("image")))
        if body.get("eye"):
            eyes = [limit_size(decode_b64(body["eye"]))]
    else:
        frame = limit_size(decode_file(request.FILES["image"])) if "image" in request.FILES else None
        if "eye" in request.FILES:
            eyes = [limit_size(decode_file(request.FILES["eye"]))]
    if frame is None:
        return JsonResponse({"ok": False, "error": "Invalid image."}, status=400)
    results = _process(s, frame, eyes, allow_fallback=settings.DEMO_MODE and s.mode == "demo")
    return JsonResponse({"ok": True, "results": results, "feed": _feed(s)})


@teacher_required
@require_POST
def session_demo(request, pk):
    """Demo mode: synthesise a camera frame and push it through the REAL recognition pipeline."""
    s = _own_session(request, pk)
    if not settings.DEMO_MODE or s.status != "ACTIVE":
        return JsonResponse({"ok": False, "error": "Demo mode unavailable."}, status=400)
    kind = request.POST.get("kind", "student")
    student = None
    if kind in ("student", "degraded", "spoof"):
        pending = services.eligible_students(s).filter(demo_seed__isnull=False).exclude(attendance__session=s)
        pool = pending if kind != "spoof" else services.eligible_students(s).filter(demo_seed__isnull=False)
        student = pool.order_by("?").first()
        if student is None:
            return JsonResponse({"ok": False, "error": "No demo-enrolled students left. Run `python manage.py seed_demo`."}, status=400)
    frame, eyes = recognition.demo_probe(kind, student)
    results = _process(s, frame, eyes, allow_fallback=True)
    for r in results:
        r["expected"] = {"student": "Genuine student", "degraded": "Degraded face (iris fallback)",
                         "unknown": "Unknown person", "spoof": "Spoof attempt"}[kind]
    return JsonResponse({"ok": True, "results": results, "feed": _feed(s)})


# ------------------------------------------------------------------ history & detail
@teacher_required
def session_list(request):
    qs = AttendanceSession.objects.select_related("subject", "classroom", "teacher__user")
    if not (request.user.is_superuser or request.user.role == "ADMIN"):
        qs = qs.filter(teacher__user=request.user)
    page = Paginator(qs, 15).get_page(request.GET.get("page"))
    return render(request, "teacher/sessions.html", {"page": page})


@teacher_required
def session_detail(request, pk):
    s = _own_session(request, pk)
    records = {r.student_id: r for r in s.records.select_related("student__user")}
    rows = [{"student": st, "rec": records.get(st.pk)} for st in services.eligible_students(s)]
    q = request.GET.get("q", "").lower()
    if q:
        rows = [r for r in rows if q in r["student"].name.lower() or q in r["student"].roll_no.lower()]
    return render(request, "teacher/session_detail.html", {"s": s, "rows": rows, "statuses": Attendance.STATUSES, "q": q,
                                                          "corrections": AttendanceCorrection.objects.filter(attendance__session=s)[:20]})


# ------------------------------------------------------------------ corrections (re-authentication + reason + audit)
@teacher_required
@require_POST
def correction_request(request, session_id, student_id):
    s = _own_session(request, session_id)
    st = get_object_or_404(Student, pk=student_id)
    new, reason, pw = request.POST.get("status"), request.POST.get("reason", "").strip(), request.POST.get("password", "")
    if new not in dict(Attendance.STATUSES) or len(reason) < 5:
        messages.error(request, "Choose a status and give a reason (min 5 characters).")
        return redirect("session_detail", pk=s.pk)
    if authenticate(request, username=request.user.username, password=pw) is None:
        log_action(request.user, "CORRECTION_AUTH_FAILED", f"session:{s.pk}", st.roll_no, request)
        messages.error(request, "Password re-authentication failed. Correction not applied.")
        return redirect("session_detail", pk=s.pk)
    rec, _ = Attendance.objects.get_or_create(
        session=s, student=st, defaults=dict(subject=s.subject, classroom=s.classroom, date=s.date, status="A", method="auto"))
    window = conf.get("correction_window_days", int) or 7
    within = (timezone.localdate() - s.date) <= timedelta(days=window)
    is_admin = request.user.is_superuser or request.user.role == "ADMIN"
    corr = AttendanceCorrection.objects.create(attendance=rec, requested_by=request.user, old_status=rec.status,
                                               new_status=new, reason=reason)
    if within or is_admin:
        _apply(corr, request.user)
        messages.success(request, "Correction applied and logged.")
    else:
        messages.info(request, f"Session is older than {window} days - sent to Admin for approval.")
    log_action(request.user, "CORRECTION_REQUEST", f"attendance:{rec.pk}", f"{corr.old_status}->{new}: {reason}", request)
    return redirect("session_detail", pk=s.pk)


def _apply(corr, reviewer):
    a = corr.attendance
    a.status, a.method = corr.new_status, "manual"
    if not a.time:
        a.time = timezone.localtime().time().replace(microsecond=0)
    a.save()
    corr.status, corr.reviewed_by, corr.reviewed_at = "APPROVED", reviewer, timezone.now()
    corr.save()
    services.check_low_attendance(a.student, a.subject)


@admin_required
def corrections_admin(request):
    if request.method == "POST":
        corr = get_object_or_404(AttendanceCorrection, pk=request.POST.get("id"), status="PENDING")
        if request.POST.get("action") == "approve":
            _apply(corr, request.user)
        else:
            corr.status, corr.reviewed_by, corr.reviewed_at = "REJECTED", request.user, timezone.now()
            corr.save()
        log_action(request.user, f"CORRECTION_{request.POST.get('action', '').upper()}", f"correction:{corr.pk}", "", request)
        return redirect("corrections_admin")
    qs = AttendanceCorrection.objects.select_related("attendance__student__user", "attendance__subject", "requested_by")
    page = Paginator(qs, 15).get_page(request.GET.get("page"))
    return render(request, "admin_panel/corrections.html", {"page": page})
