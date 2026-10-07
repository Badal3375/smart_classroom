from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.academics.models import Classroom, Student, Subject, Teacher, Timetable


class AttendanceSession(models.Model):
    ACTIVE, ENDED = "ACTIVE", "ENDED"
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="sessions")
    teacher = models.ForeignKey(Teacher, on_delete=models.PROTECT, related_name="sessions")
    classroom = models.ForeignKey(Classroom, on_delete=models.PROTECT, related_name="sessions")
    timetable = models.ForeignKey(Timetable, null=True, blank=True, on_delete=models.SET_NULL)
    date = models.DateField(default=timezone.localdate, db_index=True)
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, default=ACTIVE, db_index=True)
    late_after_minutes = models.PositiveIntegerField(default=15)
    mode = models.CharField(max_length=10, default="camera")  # camera | demo

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"#{self.pk} {self.subject.code} {self.date}"


class Attendance(models.Model):
    PRESENT, ABSENT, LATE, EXCUSED = "P", "A", "L", "E"
    STATUSES = [(PRESENT, "Present"), (ABSENT, "Absent"), (LATE, "Late"), (EXCUSED, "Excused")]
    session = models.ForeignKey(AttendanceSession, on_delete=models.CASCADE, related_name="records")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="attendance")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="attendance")
    classroom = models.ForeignKey(Classroom, on_delete=models.PROTECT)
    date = models.DateField(db_index=True)
    time = models.TimeField(null=True, blank=True)
    status = models.CharField(max_length=1, choices=STATUSES, db_index=True)
    confidence = models.FloatField(default=0.0)
    face_score = models.FloatField(null=True, blank=True)
    iris_score = models.FloatField(null=True, blank=True)
    method = models.CharField(max_length=12, default="")  # face | face+iris | manual | auto
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-time"]
        constraints = [models.UniqueConstraint(fields=["session", "student"], name="uniq_student_per_session")]

    def __str__(self):
        return f"{self.student.roll_no} {self.get_status_display()} {self.date}"


class AttendanceCorrection(models.Model):
    PENDING, APPROVED, REJECTED = "PENDING", "APPROVED", "REJECTED"
    attendance = models.ForeignKey(Attendance, on_delete=models.CASCADE, related_name="corrections")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="corrections_requested")
    old_status = models.CharField(max_length=1)
    new_status = models.CharField(max_length=1, choices=Attendance.STATUSES)
    reason = models.TextField()
    status = models.CharField(max_length=10, default=PENDING, db_index=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="corrections_reviewed")
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
