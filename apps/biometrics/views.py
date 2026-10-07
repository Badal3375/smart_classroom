import json
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.contrib import messages

from apps.accounts.decorators import admin_required
from apps.academics.models import Student
from apps.core.audit import log_action
from .services import recognition
from .utils import decode_b64, decode_file, limit_size


def _images(request, key):
    imgs = []
    if request.content_type and request.content_type.startswith("application/json"):
        body = json.loads(request.body or "{}")
        imgs = [decode_b64(x) for x in body.get(key, [])]
    else:
        imgs = [decode_file(f) for f in request.FILES.getlist(key)]
    return [limit_size(i) for i in imgs if i is not None][:12]


@admin_required
def enroll(request, student_id):
    st = get_object_or_404(Student.objects.select_related("user", "course"), pk=student_id)
    return render(request, "biometrics/enroll.html", {
        "student": st, "face_count": st.face_embeddings.filter(is_active=True).count(),
        "iris_count": st.iris_templates.count(), "backend": recognition.backend()})


@admin_required
@require_POST
def enroll_face_api(request, student_id):
    st = get_object_or_404(Student, pk=student_id)
    imgs = _images(request, "images")
    if not imgs:
        return JsonResponse({"ok": False, "error": "No valid images received."}, status=400)
    saved, rejected = recognition.enroll_face(st, imgs, allow_fallback=settings.DEMO_MODE and request.POST.get("fallback") == "1")
    log_action(request.user, "BIOMETRIC_ENROLL_FACE", st.roll_no, f"saved={saved} rejected={len(rejected)}", request)
    return JsonResponse({"ok": saved > 0, "saved": saved, "rejected": rejected,
                         "total": st.face_embeddings.filter(is_active=True).count()})


@admin_required
@require_POST
def enroll_iris_api(request, student_id):
    st = get_object_or_404(Student, pk=student_id)
    imgs = _images(request, "images")
    if not imgs:
        return JsonResponse({"ok": False, "error": "No valid images received."}, status=400)
    saved, rejected = recognition.enroll_iris(st, imgs, eye=request.POST.get("eye", "U")[:1] or "U")
    log_action(request.user, "BIOMETRIC_ENROLL_IRIS", st.roll_no, f"saved={saved} rejected={len(rejected)}", request)
    return JsonResponse({"ok": saved > 0, "saved": saved, "rejected": rejected, "total": st.iris_templates.count()})


@admin_required
@require_POST
def enroll_demo_api(request, student_id):
    st = get_object_or_404(Student, pk=student_id)
    f, i, rej = recognition.enroll_demo(st)
    log_action(request.user, "BIOMETRIC_ENROLL_DEMO", st.roll_no, f"face={f} iris={i}", request)
    messages.success(request, f"Demo biometrics generated: {f} face and {i} iris templates.")
    return redirect("enroll", student_id=st.pk)


@admin_required
@require_POST
def clear_biometrics(request, student_id):
    st = get_object_or_404(Student, pk=student_id)
    st.face_embeddings.all().delete()
    st.iris_templates.all().delete()
    recognition.invalidate_gallery()
    log_action(request.user, "BIOMETRIC_DELETE", st.roll_no, "all templates removed", request)
    messages.success(request, "All biometric templates deleted.")
    return redirect("enroll", student_id=st.pk)
