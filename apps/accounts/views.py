from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.views import LoginView as DjangoLoginView
from django.contrib.auth.views import LogoutView as DjangoLogoutView
from django.views.generic import CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.shortcuts import redirect
from django.contrib import messages
from apps.accounts.forms import RegisterForm, AuthorProfileForm, ReviewerProfileForm, UserProfileForm
from apps.accounts.models import User, AuthorProfile, ReviewerProfile


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

def _t(ar_text, en_text):
    from django.utils import translation
    return en_text if translation.get_language() == 'en' else ar_text


class ProfileView(LoginRequiredMixin, UpdateView):
    """صفحة حساب المستخدم — تعديل البيانات الشخصية."""
    model = User
    form_class = UserProfileForm
    template_name = 'accounts/profile.html'
    success_url = reverse_lazy('accounts:profile')

    def get_object(self):
        return self.request.user

    def post(self, request, *args, **kwargs):
        """معالجة POST لتحديث بيانات المستخدم والـ profile معاً."""
        self.object = self.get_object()
        user = self.object
        
        # تحديد أي form اللي اتحفظ بناءً على البيانات المرسلة
        submitted_form = None
        
        # إذا كانت البيانات تحتوي على first_name أو last_name أو email، فهي user form
        if 'first_name' in request.POST or 'last_name' in request.POST or 'email' in request.POST:
            submitted_form = 'user'
        # إذا كانت البيانات تحتوي على institution أو orcid أو bio، فهي author profile form
        elif 'institution' in request.POST or 'orcid' in request.POST or 'bio' in request.POST:
            submitted_form = 'author'
        # إذا كانت البيانات تحتوي على is_available، فهي reviewer profile form
        elif 'is_available' in request.POST:
            submitted_form = 'reviewer'
        
        # معالجة user form
        if submitted_form == 'user':
            user_form = self.get_form()
            if user_form.is_valid():
                user_form.save()
                messages.success(request, _t('تم تحديث بيانات حسابك بنجاح.', 'Account details updated successfully.'))
                return self.get(request, *args, **kwargs)
            return self.form_invalid(user_form)
        
        # معالجة author profile form
        elif submitted_form == 'author':
            author_profile = AuthorProfile.objects.get_or_create(user=user)[0]
            author_profile_form = AuthorProfileForm(request.POST, instance=author_profile)
            if author_profile_form.is_valid():
                author_profile_form.save()
                messages.success(request, _t('تم تحديث بيانات المؤلف بنجاح.', 'Author details updated successfully.'))
                return self.get(request, *args, **kwargs)
            return self.form_invalid(author_profile_form)
        
        # معالجة reviewer profile form
        elif submitted_form == 'reviewer':
            reviewer_profile = ReviewerProfile.objects.get_or_create(user=user)[0]
            reviewer_profile_form = ReviewerProfileForm(request.POST, instance=reviewer_profile)
            if reviewer_profile_form.is_valid():
                reviewer_profile_form.save()
                messages.success(request, _t('تم تحديث بيانات المراجع بنجاح.', 'Reviewer details updated successfully.'))
                return self.get(request, *args, **kwargs)
            return self.form_invalid(reviewer_profile_form)
        
        # إذا لم نتمكن من تحديد الـ form، أعد عرض الصفحة
        return self.get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        
        # أضف بيانات الملف الشخصي حسب الدور
        if user.role == User.ROLE_AUTHOR:
            author_profile = AuthorProfile.objects.get_or_create(user=user)[0]
            ctx['author_profile'] = author_profile
            ctx['author_profile_form'] = AuthorProfileForm(instance=author_profile)
        elif user.role == User.ROLE_REVIEWER:
            reviewer_profile = ReviewerProfile.objects.get_or_create(user=user)[0]
            ctx['reviewer_profile'] = reviewer_profile
            ctx['reviewer_profile_form'] = ReviewerProfileForm(instance=reviewer_profile)
        
        return ctx


def _dashboard_url(user):
    """يُعيد رابط لوحة التحكم المناسبة لدور المستخدم."""
    if user.role == User.ROLE_ADMIN:
        return '/dashboard/admin/'
    elif user.role == User.ROLE_REVIEWER:
        return '/dashboard/reviewer/'
    return '/dashboard/author/'
