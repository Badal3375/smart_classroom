from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/admin/", views.admin_dashboard, name="admin_dashboard"),
    path("dashboard/student/", views.student_dashboard, name="student_dashboard"),
    path("analytics/", views.analytics_dashboard, name="analytics"),
    path("notifications/", views.notifications, name="notifications"),
    path("notifications/read/", views.notifications_read, name="notifications_read"),
    path("alerts/low-attendance/", views.send_low_attendance_alerts, name="send_alerts"),
    path("settings/", views.system_settings, name="system_settings"),
    path("audit/", views.audit_log, name="audit_log"),
]
