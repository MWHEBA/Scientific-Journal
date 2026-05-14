from django import forms
from apps.pages.models import SiteSettings


class SiteSettingsForm(forms.ModelForm):
    class Meta:
        model  = SiteSettings
        fields = [
            'journal_name', 'journal_desc',
            'apc_amount', 'payment_deadline_days',
            'contact_email', 'contact_address',
        ]
        widgets = {
            'journal_name':          forms.TextInput(attrs={'class': 'form-control'}),
            'journal_desc':          forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'apc_amount':            forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'payment_deadline_days': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'contact_email':         forms.EmailInput(attrs={'class': 'form-control'}),
            'contact_address':       forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        labels = {
            'journal_name':          'اسم المجلة',
            'journal_desc':          'وصف المجلة',
            'apc_amount':            'رسوم النشر (APC) بالدولار',
            'payment_deadline_days': 'مهلة الدفع (بالأيام)',
            'contact_email':         'البريد الإلكتروني للتواصل',
            'contact_address':       'العنوان البريدي',
        }


class ContactForm(forms.Form):
    """نموذج الاتصال — يرسل رسالة للإدارة."""
    name = forms.CharField(
        max_length=100,
        label='الاسم الكامل',
        widget=forms.TextInput(attrs={
            'class': 'contact-form__input',
            'placeholder': 'أدخل اسمك الكامل'
        })
    )
    email = forms.EmailField(
        label='البريد الإلكتروني',
        widget=forms.EmailInput(attrs={
            'class': 'contact-form__input',
            'placeholder': 'example@email.com'
        })
    )
    subject = forms.CharField(
        max_length=200,
        label='الموضوع',
        widget=forms.TextInput(attrs={
            'class': 'contact-form__input',
            'placeholder': 'موضوع الرسالة'
        })
    )
    message = forms.CharField(
        label='الرسالة',
        widget=forms.Textarea(attrs={
            'class': 'contact-form__textarea',
            'rows': 6,
            'placeholder': 'اكتب رسالتك هنا...'
        })
    )
