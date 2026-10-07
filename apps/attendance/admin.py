from django.contrib import admin
from .models import AttendanceSession, Attendance, AttendanceCorrection
for m in (AttendanceSession, Attendance, AttendanceCorrection):
    admin.site.register(m)
