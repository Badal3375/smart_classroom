from django.conf import settings


def globals(request):
    ctx = {"DEMO_MODE": settings.DEMO_MODE, "PROJECT_NAME": "SmartAttend AI"}
    u = getattr(request, "user", None)
    if u is not None and u.is_authenticated:
        ctx["unread_count"] = u.notifications.filter(is_read=False).count()
        ctx["eff_role"] = "ADMIN" if u.is_superuser else u.role
    return ctx
