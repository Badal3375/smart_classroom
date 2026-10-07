from .models import Notification


def notify(user, title, message, level="info", kind=""):
    return Notification.objects.create(user=user, title=title, message=message, level=level, kind=kind)
