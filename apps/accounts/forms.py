from django import forms
from django.contrib.auth.forms import UserCreationForm
from apps.accounts.models import User, AuthorProfile, ReviewerProfile


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


class AuthorProfileForm(forms.ModelForm):
    """فورم تعديل بيانات المؤلف."""
    class Meta:
        model = AuthorProfile
        fields = ['institution', 'orcid', 'bio']
        widgets = {
            'institution': forms.TextInput(attrs={
                'class': 'submit-field__input',
                'placeholder': 'اسم المؤسسة الأكاديمية'
            }),
            'orcid': forms.TextInput(attrs={
                'class': 'submit-field__input',
                'placeholder': 'مثال: 0000-0000-0000-0000',
                'dir': 'ltr'
            }),
            'bio': forms.Textarea(attrs={
                'class': 'submit-field__input submit-field__textarea',
                'rows': 4,
                'placeholder': 'اكتب نبذة عن نفسك'
            }),
        }
        labels = {
            'institution': 'المؤسسة',
            'orcid': 'ORCID',
            'bio': 'السيرة الذاتية',
        }


class ReviewerProfileForm(forms.ModelForm):
    """فورم تعديل بيانات المراجع."""
    class Meta:
        model = ReviewerProfile
        fields = ['institution', 'is_available']
        widgets = {
            'institution': forms.TextInput(attrs={
                'class': 'submit-field__input',
                'placeholder': 'اسم المؤسسة الأكاديمية'
            }),
            'is_available': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }
        labels = {
            'institution': 'المؤسسة',
            'is_available': 'متاح للمراجعة',
        }


class UserProfileForm(forms.ModelForm):
    """فورم تعديل بيانات المستخدم الشخصية."""
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'submit-field__input',
                'placeholder': 'الاسم الأول'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'submit-field__input',
                'placeholder': 'اسم العائلة'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'submit-field__input',
                'placeholder': 'البريد الإلكتروني'
            }),
        }
        labels = {
            'first_name': 'الاسم الأول',
            'last_name': 'اسم العائلة',
            'email': 'البريد الإلكتروني',
        }

    def clean_email(self):
        email = self.cleaned_data.get('email')
        # السماح بالبريد الحالي للمستخدم
        if User.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('هذا البريد الإلكتروني مستخدم مسبقاً.')
        return email
