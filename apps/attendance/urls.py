from django.urls import path
from . import views, reports

urlpatterns = [
    path("", views.teacher_dashboard, name="teacher_dashboard"),
    path("session/start/", views.session_start, name="session_start"),
    path("sessions/", views.session_list, name="session_list"),
    path("session/<int:pk>/", views.session_detail, name="session_detail"),
    path("session/<int:pk>/live/", views.session_live, name="session_live"),
    path("session/<int:pk>/end/", views.session_end, name="session_end"),
    path("session/<int:pk>/feed/", views.session_feed, name="session_feed"),
    path("session/<int:pk>/frame/", views.session_frame, name="session_frame"),
    path("session/<int:pk>/demo/", views.session_demo, name="session_demo"),
    path("session/<int:session_id>/correct/<int:student_id>/", views.correction_request, name="correction_request"),
    path("corrections/", views.corrections_admin, name="corrections_admin"),
    path("register/", reports.register, name="register"),
    path("export/<str:fmt>/", reports.export, name="export"),
]
