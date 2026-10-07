from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.core.cache import cache
from django.shortcuts import redirect

from apps.core.audit import log_action


def _client_ip(request):
    return request.META.get("REMOTE_ADDR", "")


class SecureLoginView(auth_views.LoginView):
    """Login with brute-force throttling (5 failures / 15 min per username+IP) and audit logging."""
    template_name = "registration/login.html"
    redirect_authenticated_user = True
    MAX_FAILS, WINDOW = 5, 15 * 60

    def _key(self, request):
        return f"loginfail:{request.POST.get('username', '').lower()}:{_client_ip(request)}"

    def post(self, request, *args, **kwargs):
        if cache.get(self._key(request), 0) >= self.MAX_FAILS:
            messages.error(request, "Too many failed attempts. Try again in 15 minutes.")
            log_action(None, "LOGIN_BLOCKED", request.POST.get("username", ""), request=request)
            return redirect("login")
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        cache.delete(self._key(self.request))
        resp = super().form_valid(form)
        log_action(self.request.user, "LOGIN", str(self.request.user), request=self.request)
        return resp

    def form_invalid(self, form):
        k = self._key(self.request)
        cache.set(k, cache.get(k, 0) + 1, self.WINDOW)
        log_action(None, "LOGIN_FAILED", self.request.POST.get("username", ""), request=self.request)
        return super().form_invalid(form)


class SecureLogoutView(auth_views.LogoutView):
    def post(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            log_action(request.user, "LOGOUT", str(request.user), request=request)
        return super().post(request, *args, **kwargs)
