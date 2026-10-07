from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def role_required(*roles):
    """Role-based access control. Superusers are treated as ADMIN."""
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapper(request, *args, **kwargs):
            u = request.user
            effective = "ADMIN" if u.is_superuser else u.role
            if effective not in roles:
                raise PermissionDenied("You do not have permission to access this page.")
            return view(request, *args, **kwargs)
        return wrapper
    return decorator


admin_required = role_required("ADMIN")
teacher_required = role_required("TEACHER", "ADMIN")
student_required = role_required("STUDENT")
