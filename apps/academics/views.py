"""Admin management screens (generic CRUD with search, filter and pagination)."""
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.decorators import admin_required
from apps.accounts.models import User
from apps.core.audit import log_action
from . import forms
from .models import Classroom, Course, Student, Subject, Teacher, Timetable

CONFIG = {
    "students": dict(model=Student, form=forms.StudentForm, title="Students", sr=["user", "course"],
                     cols=[("Roll No", "roll_no"), ("Name", "name"), ("Course", "course"), ("Sem", "semester"),
                           ("Face", "face_enrolled"), ("Iris", "iris_enrolled")],
                     search=["roll_no", "user__first_name", "user__last_name", "user__username"], filter="course", bio=True),
    "teachers": dict(model=Teacher, form=forms.TeacherForm, title="Teachers", sr=["user"],
                     cols=[("Employee ID", "employee_id"), ("Name", "name"), ("Department", "department")],
                     search=["employee_id", "user__first_name", "user__last_name", "department"]),
    "courses": dict(model=Course, form=forms.CourseForm, title="Courses", sr=[],
                    cols=[("Code", "code"), ("Name", "name"), ("Semesters", "semesters")], search=["code", "name"]),
    "subjects": dict(model=Subject, form=forms.SubjectForm, title="Subjects", sr=["course"],
                     cols=[("Code", "code"), ("Name", "name"), ("Course", "course"), ("Sem", "semester"), ("Credits", "credits")],
                     search=["code", "name"], filter="course"),
    "classrooms": dict(model=Classroom, form=forms.ClassroomForm, title="Classrooms", sr=[],
                       cols=[("Name", "name"), ("Building", "building"), ("Capacity", "capacity"), ("Camera", "camera_source")],
                       search=["name", "building"]),
    "timetables": dict(model=Timetable, form=forms.TimetableForm, title="Timetable", sr=["subject", "teacher__user", "classroom"],
                       cols=[("Day", "get_weekday_display"), ("Start", "start_time"), ("End", "end_time"),
                             ("Subject", "subject"), ("Teacher", "teacher"), ("Room", "classroom")],
                       search=["subject__name", "subject__code", "classroom__name"], filter="subject"),
    "users": dict(model=User, form=forms.UserForm, title="Users", sr=[],
                  cols=[("Username", "username"), ("Name", "get_full_name"), ("Role", "role"), ("Active", "is_active")],
                  search=["username", "first_name", "last_name", "email"], filter=None),
}


def _cfg(key):
    if key not in CONFIG:
        from django.http import Http404
        raise Http404
    return CONFIG[key]


@admin_required
def crud_list(request, key):
    c = _cfg(key)
    qs = c["model"].objects.all()
    if c["sr"]:
        qs = qs.select_related(*c["sr"])
    q = request.GET.get("q", "").strip()
    if q:
        cond = Q()
        for f in c["search"]:
            cond |= Q(**{f"{f}__icontains": q})
        qs = qs.filter(cond)
    flt, flt_opts, flt_val = c.get("filter"), None, request.GET.get("f", "")
    if flt:
        rel = c["model"]._meta.get_field(flt).related_model
        flt_opts = rel.objects.all()
        if flt_val.isdigit():
            qs = qs.filter(**{flt: flt_val})
    page = Paginator(qs, 12).get_page(request.GET.get("page"))
    return render(request, "crud/list.html", {"cfg": c, "key": key, "page": page, "q": q,
                                              "flt": flt, "flt_opts": flt_opts, "flt_val": flt_val})


@admin_required
def crud_edit(request, key, pk=None):
    c = _cfg(key)
    obj = get_object_or_404(c["model"], pk=pk) if pk else None
    form = c["form"](request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        log_action(request.user, "UPDATE" if pk else "CREATE", f"{key}:{saved.pk}", str(saved), request)
        messages.success(request, f"{c['title']} saved.")
        if key == "students" and not pk:
            return redirect("enroll", student_id=saved.pk)
        return redirect("crud_list", key=key)
    return render(request, "crud/form.html", {"cfg": c, "key": key, "form": form, "obj": obj})


@admin_required
def crud_delete(request, key, pk):
    c = _cfg(key)
    obj = get_object_or_404(c["model"], pk=pk)
    if request.method == "POST":
        label = str(obj)
        try:
            user = getattr(obj, "user", None)
            obj.delete()
            if user is not None and key in ("students", "teachers"):
                user.delete()
            log_action(request.user, "DELETE", f"{key}:{pk}", label, request)
            messages.success(request, "Deleted.")
        except Exception as exc:  # protected FK etc.
            messages.error(request, f"Cannot delete: {exc}")
        return redirect("crud_list", key=key)
    return render(request, "crud/confirm_delete.html", {"obj": obj, "key": key, "cfg": c})
