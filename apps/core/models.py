from django.conf import settings
from django.db import models


class SystemSetting(models.Model):
    key = models.CharField(max_length=60, unique=True)
    value = models.CharField(max_length=200, blank=True)
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["key"]

    def __str__(self):
        return f"{self.key}={self.value}"


class Notification(models.Model):
    INFO, WARNING, DANGER = "info", "warning", "danger"
    LEVELS = [(INFO, "Info"), (WARNING, "Warning"), (DANGER, "Alert")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=150)
    message = models.TextField()
    level = models.CharField(max_length=10, choices=LEVELS, default=INFO)
    kind = models.CharField(max_length=30, blank=True, db_index=True)  # absence | low_attendance | system
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user}: {self.title}"


class AuditLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_logs")
    action = models.CharField(max_length=60, db_index=True)
    target = models.CharField(max_length=200, blank=True)
    details = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action} {self.target}"
