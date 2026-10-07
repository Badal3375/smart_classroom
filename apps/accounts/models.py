from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ADMIN, TEACHER, STUDENT = "ADMIN", "TEACHER", "STUDENT"
    ROLES = [(ADMIN, "Admin"), (TEACHER, "Teacher"), (STUDENT, "Student")]
    role = models.CharField(max_length=10, choices=ROLES, default=STUDENT, db_index=True)
    phone = models.CharField(max_length=20, blank=True)

    @property
    def is_admin_role(self):
        return self.role == self.ADMIN or self.is_superuser

    @property
    def is_teacher_role(self):
        return self.role == self.TEACHER

    @property
    def is_student_role(self):
        return self.role == self.STUDENT

    def __str__(self):
        return self.get_full_name() or self.username
