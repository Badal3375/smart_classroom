from django.urls import path
from . import views

urlpatterns = [
    path("<str:key>/", views.crud_list, name="crud_list"),
    path("<str:key>/new/", views.crud_edit, name="crud_new"),
    path("<str:key>/<int:pk>/edit/", views.crud_edit, name="crud_edit"),
    path("<str:key>/<int:pk>/delete/", views.crud_delete, name="crud_delete"),
]
