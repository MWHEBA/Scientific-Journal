from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.views import LoginView as DjangoLoginView
from django.contrib.auth.views import LogoutView as DjangoLogoutView
from django.views.generic import CreateView
from django.urls import reverse_lazy
from django.shortcuts import redirect
from apps.accounts.forms import RegisterForm
from apps.accounts.models import User


class RegisterView(CreateView):
    form_class    = RegisterForm
    template_name = 'accounts/register.html'
    success_url   = reverse_lazy('accounts:login')

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(_dashboard_url(request.user))
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        return response


class LoginView(DjangoLoginView):
    template_name = 'accounts/login.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(_dashboard_url(request.user))
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return _dashboard_url(self.request.user)


class LogoutView(DjangoLogoutView):
    next_page = '/'


def _dashboard_url(user):
    """يُعيد رابط لوحة التحكم المناسبة لدور المستخدم."""
    if user.role == User.ROLE_ADMIN:
        return '/dashboard/admin/'
    elif user.role == User.ROLE_REVIEWER:
        return '/dashboard/reviewer/'
    return '/dashboard/author/'
