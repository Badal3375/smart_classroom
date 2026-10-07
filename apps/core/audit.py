from .models import AuditLog


def log_action(user, action, target="", details="", request=None):
    ip = request.META.get("REMOTE_ADDR") if request is not None else None
    AuditLog.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        action=action, target=str(target)[:200], details=str(details)[:2000], ip_address=ip,
    )
