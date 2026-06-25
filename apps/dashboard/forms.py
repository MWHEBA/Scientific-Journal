from django import forms
from apps.submissions.models import JournalSection
from taggit.models import Tag


class JournalSectionForm(forms.ModelForm):
    class Meta:
        model = JournalSection
        fields = ['name', 'slug', 'order']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'مثال: العلوم الإدارية'}),
            'slug': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'مثال: management-sciences'}),
            'order': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'مثال: 1'}),
        }
        labels = {
            'name': 'اسم التصنيف / القسم',
            'slug': 'الرابط البديل (Slug)',
            'order': 'المسلسل (الترتيب)',
        }
        help_texts = {
            'slug': 'يستخدم في روابط الويب (أحرف إنجليزية وأرقام وشرطات فقط).',
            'order': 'الرقم المسلسل لتحديد ترتيب ظهور هذا التصنيف.',
        }

    def clean_slug(self):
        slug = self.cleaned_data.get('slug', '').strip().lower()
        if not slug:
            return slug
        import re
        if not re.match(r'^[-a-zA-Z0-9_]+$', slug):
            raise forms.ValidationError('الرابط البديل يجب أن يحتوي على أحرف إنجليزية، أرقام، أو شرطات فقط.')
        return slug


class TagForm(forms.ModelForm):
    class Meta:
        model = Tag
        fields = ['name', 'slug']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'مثال: الذكاء الاصطناعي'}),
            'slug': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'مثال: artificial-intelligence'}),
        }
        labels = {
            'name': 'اسم الوسم',
            'slug': 'الرابط البديل (Slug)',
        }
        help_texts = {
            'slug': 'يستخدم في روابط الويب (أحرف إنجليزية وأرقام وشرطات فقط). سيتم توليده تلقائياً إذا تُرِك فارغاً.',
        }

    def clean_slug(self):
        slug = self.cleaned_data.get('slug', '').strip().lower()
        if not slug:
            return slug
        import re
        if not re.match(r'^[-a-zA-Z0-9_]+$', slug):
            raise forms.ValidationError('الرابط البديل يجب أن يحتوي على أحرف إنجليزية، أرقام، أو شرطات فقط.')
        return slug
