"""Attendance engine: marking, duplicate prevention, finalisation, percentages, warnings."""
from datetime import timedelta
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.academics.models import Student
from apps.core import conf
from apps.core.notifications import notify
from .models import Attendance, AttendanceSession


def eligible_students(session):
    s = session.subject
    return Student.objects.filter(course=s.course, semester=s.semester).select_related("user")


def mark_attendance(session, student, confidence=0.0, face_score=None, iris_score=None, method="face"):
    """Idempotent: returns (record, created). The DB unique constraint is the last line of defence
    against duplicates (race between two cameras / rapid frames)."""
    existing = Attendance.objects.filter(session=session, student=student).first()
    if existing:
        return existing, False
    now = timezone.localtime()
    late = now > session.started_at + timedelta(minutes=session.late_after_minutes)
    try:
        with transaction.atomic():
            rec = Attendance.objects.create(
                session=session, student=student, subject=session.subject, classroom=session.classroom,
                date=session.date, time=now.time().replace(microsecond=0),
                status=Attendance.LATE if late else Attendance.PRESENT,
                confidence=round(confidence, 3), face_score=face_score, iris_score=iris_score, method=method)
        return rec, True
    except IntegrityError:
        return Attendance.objects.get(session=session, student=student), False


def start_session(subject, teacher, classroom, mode="camera", timetable=None):
    return AttendanceSession.objects.create(
        subject=subject, teacher=teacher, classroom=classroom, timetable=timetable, mode=mode,
        late_after_minutes=conf.get("late_after_minutes", int) or 15)


def end_session(session):
    """Close the session, mark everyone not seen as Absent, send notifications."""
    if session.status == AttendanceSession.ENDED:
        return 0
    marked = set(session.records.values_list("student_id", flat=True))
    absent = 0
    for st in eligible_students(session):
        if st.pk in marked:
            continue
        Attendance.objects.get_or_create(
            session=session, student=st,
            defaults=dict(subject=session.subject, classroom=session.classroom, date=session.date,
                          status=Attendance.ABSENT, method="auto"))
        notify(st.user, f"Absent: {session.subject.name}",
               f"You were marked absent for {session.subject.name} on {session.date:%d %b %Y}.",
               level="warning", kind="absence")
        absent += 1
    session.status = AttendanceSession.ENDED
    session.ended_at = timezone.now()
    session.save(update_fields=["status", "ended_at"])
    for st in eligible_students(session):
        check_low_attendance(st, session.subject)
    return absent


# ------------------------------------------------------------------ percentages
def counts_for(qs):
    agg = qs.aggregate(P=Count("id", filter=Q(status="P")), L=Count("id", filter=Q(status="L")),
                       A=Count("id", filter=Q(status="A")), E=Count("id", filter=Q(status="E")))
    return agg


def percentage_from(agg):
    """Excused classes are excluded from the denominator. Late counts as attended by default."""
    late_ok = conf.get("late_counts_as_present", bool)
    attended = agg["P"] + (agg["L"] if late_ok else 0)
    held = agg["P"] + agg["L"] + agg["A"]
    return round(100.0 * attended / held, 1) if held else 100.0


def student_percentage(student, subject=None):
    qs = Attendance.objects.filter(student=student)
    if subject:
        qs = qs.filter(subject=subject)
    return percentage_from(counts_for(qs))


def subject_breakdown(student):
    rows = []
    from apps.academics.models import Subject
    for sub in Subject.objects.filter(course=student.course, semester=student.semester):
        agg = counts_for(Attendance.objects.filter(student=student, subject=sub))
        pct = percentage_from(agg)
        rows.append({"subject": sub, **agg, "total": agg["P"] + agg["L"] + agg["A"] + agg["E"], "percent": pct,
                     "low": pct < (conf.get("min_attendance_percent", float) or 75) and (agg["P"] + agg["L"] + agg["A"]) > 0})
    return rows


def check_low_attendance(student, subject):
    minimum = conf.get("min_attendance_percent", float) or 75.0
    agg = counts_for(Attendance.objects.filter(student=student, subject=subject))
    if agg["P"] + agg["L"] + agg["A"] < 3:
        return False
    pct = percentage_from(agg)
    if pct >= minimum:
        return False
    from apps.core.models import Notification
    today = timezone.localdate()
    if Notification.objects.filter(user=student.user, kind="low_attendance", created_at__date=today,
                                   title__contains=subject.code).exists():
        return False
    notify(student.user, f"Low attendance: {subject.code}",
           f"Your attendance in {subject.name} is {pct}% (minimum required {minimum:g}%). Please attend upcoming classes.",
           level="danger", kind="low_attendance")
    return True
