from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy
from . import views

urlpatterns = [
    path("login/", views.SecureLoginView.as_view(), name="login"),
    path("logout/", views.SecureLogoutView.as_view(), name="logout"),
    path("password/", auth_views.PasswordChangeView.as_view(
        template_name="registration/password_change.html", success_url=reverse_lazy("dashboard")), name="password_change"),
]
