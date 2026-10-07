from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction

from .models import Classroom, Course, Student, Subject, Teacher, Timetable

User = get_user_model()


class BootstrapMixin:
    def _style(self):
        for f in self.fields.values():
            w = f.widget
            if isinstance(w, forms.CheckboxInput):
                w.attrs["class"] = "form-check-input"
            elif isinstance(w, (forms.Select, forms.SelectMultiple)):
                w.attrs["class"] = "form-select"
            else:
                w.attrs["class"] = "form-control"


class BaseForm(BootstrapMixin, forms.ModelForm):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._style()


class CourseForm(BaseForm):
    class Meta:
        model = Course
        fields = ["code", "name", "semesters"]


class SubjectForm(BaseForm):
    class Meta:
        model = Subject
        fields = ["code", "name", "course", "semester", "credits"]


class ClassroomForm(BaseForm):
    class Meta:
        model = Classroom
        fields = ["name", "building", "capacity", "camera_source"]


class TimetableForm(BaseForm):
    class Meta:
        model = Timetable
        fields = ["subject", "teacher", "classroom", "weekday", "start_time", "end_time"]
        widgets = {"start_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
                   "end_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M")}


class _UserBackedForm(BaseForm):
    """Creates / updates the linked User in the same transaction as the profile."""
    ROLE = None
    username = forms.CharField(max_length=150)
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField(required=False)
    password = forms.CharField(widget=forms.PasswordInput(render_value=False), required=False,
                               help_text="Required for new accounts; leave blank to keep the current password.")

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        if self.instance.pk:
            u = self.instance.user
            for f in ("username", "first_name", "last_name", "email"):
                self.fields[f].initial = getattr(u, f)
        self.order_fields(["username", "first_name", "last_name", "email", "password"])

    def clean_username(self):
        name = self.cleaned_data["username"]
        qs = User.objects.filter(username__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.user_id)
        if qs.exists():
            raise forms.ValidationError("This username is already taken.")
        return name

    def clean_password(self):
        pw = self.cleaned_data.get("password")
        if not self.instance.pk and not pw:
            raise forms.ValidationError("Password is required for new accounts.")
        if pw:
            validate_password(pw)
        return pw

    @transaction.atomic
    def save(self, commit=True):
        d = self.cleaned_data
        u = self.instance.user if self.instance.pk else User(role=self.ROLE)
        u.username, u.first_name, u.last_name, u.email = d["username"], d["first_name"], d.get("last_name", ""), d.get("email", "")
        u.role = self.ROLE
        if d.get("password"):
            u.set_password(d["password"])
        u.save()
        obj = super().save(commit=False)
        obj.user = u
        obj.save()
        self.save_m2m()
        return obj


class StudentForm(_UserBackedForm):
    ROLE = "STUDENT"

    class Meta:
        model = Student
        fields = ["roll_no", "course", "semester", "guardian_email"]


class TeacherForm(_UserBackedForm):
    ROLE = "TEACHER"

    class Meta:
        model = Teacher
        fields = ["employee_id", "department", "subjects"]


class UserForm(BootstrapMixin, forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(render_value=False), required=False,
                               help_text="Leave blank to keep the current password.")

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "role", "is_active"]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._style()

    def clean_password(self):
        pw = self.cleaned_data.get("password")
        if not self.instance.pk and not pw:
            raise forms.ValidationError("Password is required for new users.")
        if pw:
            validate_password(pw)
        return pw

    def save(self, commit=True):
        u = super().save(commit=False)
        if self.cleaned_data.get("password"):
            u.set_password(self.cleaned_data["password"])
        u.save()
        return u
