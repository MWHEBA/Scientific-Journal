from django import forms
from django.contrib.auth.forms import UserCreationForm
from apps.accounts.models import User


class RegisterForm(UserCreationForm):
    first_name = forms.CharField(max_length=150, required=True, label='الاسم الأول')
    last_name  = forms.CharField(max_length=150, required=True, label='اسم العائلة')
    email      = forms.EmailField(required=True, label='البريد الإلكتروني')
    institution = forms.CharField(max_length=255, required=False, label='المؤسسة الأكاديمية')

    class Meta:
        model  = User
        fields = ('username', 'first_name', 'last_name', 'email',
                  'password1', 'password2')

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('هذا البريد الإلكتروني مستخدم مسبقاً.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email      = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name  = self.cleaned_data['last_name']
        user.role       = User.ROLE_AUTHOR
        if commit:
            user.save()
            from apps.accounts.models import AuthorProfile
            AuthorProfile.objects.create(
                user=user,
                institution=self.cleaned_data.get('institution', ''),
            )
        return user


class AdminCreateUserForm(UserCreationForm):
    """فورم إنشاء مستخدم جديد من لوحة تحكم المشرف — يدعم كل الأدوار."""
    first_name  = forms.CharField(max_length=150, required=True,  label='الاسم الأول')
    last_name   = forms.CharField(max_length=150, required=True,  label='اسم العائلة')
    email       = forms.EmailField(required=True, label='البريد الإلكتروني')
    role        = forms.ChoiceField(choices=User.ROLE_CHOICES,    label='الدور')
    institution = forms.CharField(max_length=255, required=False, label='المؤسسة')

    class Meta:
        model  = User
        fields = ('username', 'first_name', 'last_name', 'email',
                  'role', 'password1', 'password2')

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('هذا البريد الإلكتروني مستخدم مسبقاً.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email      = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name  = self.cleaned_data['last_name']
        user.role       = self.cleaned_data['role']
        if commit:
            user.save()
            # إنشاء الـ profile المناسب تلقائياً
            if user.role == User.ROLE_AUTHOR:
                from apps.accounts.models import AuthorProfile
                AuthorProfile.objects.get_or_create(
                    user=user,
                    defaults={'institution': self.cleaned_data.get('institution', '')},
                )
            elif user.role == User.ROLE_REVIEWER:
                from apps.accounts.models import ReviewerProfile
                ReviewerProfile.objects.get_or_create(user=user)
        return user
