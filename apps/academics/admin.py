from django.contrib import admin
from .models import Course, Subject, Classroom, Student, Teacher, Timetable
for m in (Course, Subject, Classroom, Student, Teacher, Timetable):
    admin.site.register(m)
