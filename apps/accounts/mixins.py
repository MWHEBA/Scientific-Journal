from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from apps.accounts.models import User


class RoleRequiredMixin(LoginRequiredMixin):
    """يتحقق من دور المستخدم — يرفع PermissionDenied إذا كان الدور غير مطابق."""
    required_role = None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if self.required_role and request.user.role != self.required_role:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class AuthorRequiredMixin(RoleRequiredMixin):
    required_role = User.ROLE_AUTHOR


class ReviewerRequiredMixin(RoleRequiredMixin):
    required_role = User.ROLE_REVIEWER


class AdminRequiredMixin(RoleRequiredMixin):
    required_role = User.ROLE_ADMIN
