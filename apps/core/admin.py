from django.contrib import admin
from .models import SystemSetting, Notification, AuditLog
for m in (SystemSetting, Notification, AuditLog):
    admin.site.register(m)
