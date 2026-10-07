from django.conf import settings
from django.db import models


class Course(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=150)
    semesters = models.PositiveSmallIntegerField(default=8)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class Subject(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=150)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="subjects")
    semester = models.PositiveSmallIntegerField(default=1)
    credits = models.PositiveSmallIntegerField(default=3)

    class Meta:
        ordering = ["course", "semester", "code"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class Classroom(models.Model):
    name = models.CharField(max_length=60, unique=True)
    building = models.CharField(max_length=60, blank=True)
    capacity = models.PositiveIntegerField(default=60)
    camera_source = models.CharField(max_length=200, blank=True, help_text="Browser camera, RTSP URL or 'demo'")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Student(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="student")
    roll_no = models.CharField(max_length=30, unique=True)
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="students")
    semester = models.PositiveSmallIntegerField(default=1)
    guardian_email = models.EmailField(blank=True)
    demo_seed = models.IntegerField(null=True, blank=True, help_text="Set when enrolled with synthetic demo biometrics")

    class Meta:
        ordering = ["roll_no"]

    @property
    def name(self):
        return self.user.get_full_name() or self.user.username

    @property
    def face_enrolled(self):
        return self.face_embeddings.filter(is_active=True).exists()

    @property
    def iris_enrolled(self):
        return self.iris_templates.exists()

    def __str__(self):
        return f"{self.roll_no} - {self.name}"


class Teacher(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="teacher")
    employee_id = models.CharField(max_length=30, unique=True)
    department = models.CharField(max_length=100, blank=True)
    subjects = models.ManyToManyField(Subject, blank=True, related_name="teachers")

    class Meta:
        ordering = ["employee_id"]

    @property
    def name(self):
        return self.user.get_full_name() or self.user.username

    def __str__(self):
        return f"{self.employee_id} - {self.name}"


class Timetable(models.Model):
    DAYS = [(0, "Monday"), (1, "Tuesday"), (2, "Wednesday"), (3, "Thursday"), (4, "Friday"), (5, "Saturday"), (6, "Sunday")]
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="slots")
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name="slots")
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name="slots")
    weekday = models.PositiveSmallIntegerField(choices=DAYS)
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        ordering = ["weekday", "start_time"]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError("End time must be after start time.")

    def __str__(self):
        return f"{self.get_weekday_display()} {self.start_time:%H:%M}-{self.end_time:%H:%M} {self.subject.code}"
