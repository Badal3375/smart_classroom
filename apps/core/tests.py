import numpy as np
from django.core.management import call_command
from django.test import TestCase, Client

from apps.academics.models import Student
from apps.attendance import services
from apps.attendance.models import Attendance, AttendanceSession
from apps.biometrics.services import iris_service as I, face_service as F, liveness as L, synthetic as S, recognition


class BiometricTests(TestCase):
    def test_iris_genuine_vs_impostor(self):
        a, b, c = (I.generate_template(S.synth_eye(1, v)) for v in (0, 1, 2))
        other = I.generate_template(S.synth_eye(2, 1))
        g = I.hamming_distance(a["code"], a["mask"], b["code"], b["mask"])
        i = I.hamming_distance(a["code"], a["mask"], other["code"], other["mask"])
        self.assertLess(g, 0.16)
        self.assertGreater(i, g)

    def test_face_embedding_similarity(self):
        e = lambda s, v: F.extract_embedding(F.align_face(S.synth_face(s, v), (0, 0, 160, 160))[0])
        self.assertGreater(float(e(1, 0) @ e(1, 1)), 0.92)
        self.assertLess(float(e(1, 0) @ e(2, 0)), 0.92)

    def test_liveness_rejects_replay(self):
        self.assertTrue(L.check_liveness(S.synth_face(1, 3))["is_live"])
        self.assertFalse(L.check_liveness(S.make_spoof(S.synth_face(1, 3)))["is_live"])


class WorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", "--no-history", verbosity=0)

    def test_roles_and_rbac(self):
        c = Client()
        self.assertEqual(c.get("/dashboard/").status_code, 302)
        c.login(username="student1", password="Student@12345")
        self.assertEqual(c.get("/manage/students/").status_code, 403)
        self.assertEqual(c.get("/dashboard/student/").status_code, 200)

    def test_attendance_flow_and_duplicates(self):
        from apps.academics.models import Teacher, Classroom
        t = Teacher.objects.get(user__username="teacher1")
        s = services.start_session(t.subjects.first(), t, Classroom.objects.first(), "demo")
        st = services.eligible_students(s).first()
        r1, created1 = services.mark_attendance(s, st, 0.9, 0.9, None, "face")
        r2, created2 = services.mark_attendance(s, st, 0.9, 0.9, None, "face")
        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(Attendance.objects.filter(session=s, student=st).count(), 1)
        absent = services.end_session(s)
        self.assertEqual(absent, services.eligible_students(s).count() - 1)

    def test_demo_recognition_pipeline(self):
        st = Student.objects.get(roll_no="CSE26001")
        frame, eyes = recognition.demo_probe("student", st)
        res = recognition.recognize(frame, [st.pk], eye_images=eyes, allow_fallback=True)
        self.assertEqual(res[0]["status"], "matched")
        frame, eyes = recognition.demo_probe("unknown")
        self.assertEqual(recognition.recognize(frame, [st.pk], eye_images=eyes, allow_fallback=True)[0]["status"], "unknown")
