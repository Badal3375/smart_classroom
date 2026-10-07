"""python manage.py seed_demo  -> admin/teacher/students, course data, timetable, demo biometrics and 3 weeks of history."""
import random
from datetime import time, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.academics.models import Classroom, Course, Student, Subject, Teacher, Timetable
from apps.attendance.models import Attendance, AttendanceSession
from apps.biometrics.services import recognition
from apps.core import conf

NAMES = ["Aarav Sharma", "Vivaan Patel", "Aditya Verma", "Diya Singh", "Ananya Gupta", "Ishaan Mishra", "Kavya Joshi", "Rohan Yadav",
         "Saanvi Tiwari", "Arjun Pandey", "Meera Dubey", "Karan Chauhan", "Neha Rajput", "Riya Soni", "Yash Thakur", "Pooja Kushwaha"]


class Command(BaseCommand):
    help = "Load demo data (idempotent)."

    def add_arguments(self, p):
        p.add_argument("--no-history", action="store_true")
        p.add_argument("--students", type=int, default=12)

    @transaction.atomic
    def handle(self, *a, **o):
        conf.ensure_defaults()
        admin, c = User.objects.get_or_create(username="admin", defaults=dict(role="ADMIN", is_staff=True, is_superuser=True,
                                                                               first_name="System", last_name="Admin", email="admin@example.com"))
        if c:
            admin.set_password("Admin@12345")
            admin.save()
        course, _ = Course.objects.get_or_create(code="BTCSE", defaults=dict(name="B.Tech Computer Science & Engineering", semesters=8))
        subs = []
        for code, name in [("CS701", "Machine Learning"), ("CS702", "Computer Vision"), ("CS703", "Cloud Computing"), ("CS704", "Information Security")]:
            subs.append(Subject.objects.get_or_create(code=code, defaults=dict(name=name, course=course, semester=7, credits=4))[0])
        rooms = [Classroom.objects.get_or_create(name=n, defaults=dict(building="Main Block", capacity=60, camera_source="demo"))[0]
                 for n in ("Room 101", "Room 202")]
        teachers = []
        for i, (u, fn, ln) in enumerate([("teacher1", "Priya", "Nair"), ("teacher2", "Rahul", "Kapoor")]):
            user, c = User.objects.get_or_create(username=u, defaults=dict(role="TEACHER", first_name=fn, last_name=ln, email=f"{u}@example.com"))
            if c:
                user.set_password("Teacher@12345")
                user.save()
            t, _ = Teacher.objects.get_or_create(user=user, defaults=dict(employee_id=f"EMP{100 + i}", department="CSE"))
            t.subjects.set(subs[i * 2: i * 2 + 2])
            teachers.append(t)
        for d, (sub, t, room, st) in enumerate([(subs[0], teachers[0], rooms[0], 9), (subs[1], teachers[0], rooms[1], 11),
                                                (subs[2], teachers[1], rooms[0], 13), (subs[3], teachers[1], rooms[1], 15)]):
            for wd in (d % 5, (d + 2) % 5):
                Timetable.objects.get_or_create(subject=sub, teacher=t, classroom=room, weekday=wd,
                                                defaults=dict(start_time=time(st, 0), end_time=time(st + 1, 0)))
        students = []
        for i in range(min(o["students"], len(NAMES))):
            fn, ln = NAMES[i].split()
            user, c = User.objects.get_or_create(username=f"student{i + 1}", defaults=dict(role="STUDENT", first_name=fn, last_name=ln, email=f"student{i + 1}@example.com"))
            if c:
                user.set_password("Student@12345")
                user.save()
            s, c = Student.objects.get_or_create(user=user, defaults=dict(roll_no=f"CSE26{i + 1:03d}", course=course, semester=7,
                                                                           guardian_email=f"parent{i + 1}@example.com"))
            if c or not s.face_enrolled:
                s.demo_seed = 100 + i
                s.save(update_fields=["demo_seed"])
                recognition.enroll_demo(s)
            students.append(s)
        if not o["no_history"] and not Attendance.objects.exists():
            self._history(students, subs, teachers, rooms)
        self.stdout.write(self.style.SUCCESS("Demo data ready.\n  Admin:   admin / Admin@12345\n  Teacher: teacher1 / Teacher@12345\n  Student: student1 / Student@12345"))

    def _history(self, students, subs, teachers, rooms):
        rnd = random.Random(7)
        today = timezone.localdate()
        habit = {s.pk: rnd.choice([0.97, 0.92, 0.88, 0.8, 0.7, 0.62]) for s in students}
        for back in range(21, 0, -1):
            day = today - timedelta(days=back)
            if day.weekday() > 4:
                continue
            for i, sub in enumerate(subs):
                if (day.weekday() + i) % 3 == 0:
                    continue
                t, room = teachers[i // 2], rooms[i % 2]
                start = timezone.make_aware(timezone.datetime.combine(day, time(9 + 2 * i, 0)))
                sess = AttendanceSession.objects.create(subject=sub, teacher=t, classroom=room, date=day, started_at=start,
                                                        ended_at=start + timedelta(hours=1), status="ENDED", mode="demo")
                for s in students:
                    r = rnd.random()
                    if r < habit[s.pk] - 0.05:
                        late = rnd.random() < 0.1
                        Attendance.objects.create(session=sess, student=s, subject=sub, classroom=room, date=day,
                                                  time=(start + timedelta(minutes=rnd.randint(16, 30) if late else rnd.randint(0, 8))).time(),
                                                  status="L" if late else "P", confidence=round(rnd.uniform(0.8, 0.99), 3),
                                                  face_score=round(rnd.uniform(0.8, 0.99), 3), method="face")
                    else:
                        Attendance.objects.create(session=sess, student=s, subject=sub, classroom=room, date=day,
                                                  status="E" if rnd.random() < 0.08 else "A", method="auto")
