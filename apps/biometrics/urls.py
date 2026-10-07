from django.urls import path
from . import views

urlpatterns = [
    path("enroll/<int:student_id>/", views.enroll, name="enroll"),
    path("enroll/<int:student_id>/face/", views.enroll_face_api, name="enroll_face"),
    path("enroll/<int:student_id>/iris/", views.enroll_iris_api, name="enroll_iris"),
    path("enroll/<int:student_id>/demo/", views.enroll_demo_api, name="enroll_demo"),
    path("enroll/<int:student_id>/clear/", views.clear_biometrics, name="clear_biometrics"),
]
