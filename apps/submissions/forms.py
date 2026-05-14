from django import forms
from django.forms import inlineformset_factory
from apps.submissions.models import ArticleSubmission, CoAuthor, JournalSection


class SubmissionForm(forms.ModelForm):
    class Meta:
        model  = ArticleSubmission
        fields = ['title', 'abstract', 'keywords', 'section']
        widgets = {
            'title':    forms.TextInput(attrs={'class': 'form-control'}),
            'abstract': forms.Textarea(attrs={'class': 'form-control', 'rows': 6}),
            'keywords': forms.TextInput(attrs={'class': 'form-control',
                                               'placeholder': 'كلمات مفصولة بفاصلة'}),
            'section':  forms.Select(attrs={'class': 'form-control'}),
        }
        labels = {
            'title':    'عنوان المقالة',
            'abstract': 'الملخص',
            'keywords': 'الكلمات المفتاحية',
            'section':  'القسم العلمي',
        }


class ManuscriptUploadForm(forms.Form):
    """نموذج رفع ملف المخطوطة (PDF فقط، حجم أقصى 20MB)."""
    manuscript = forms.FileField(
        label='ملف المخطوطة (PDF)',
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf'}),
    )

    def clean_manuscript(self):
        file = self.cleaned_data.get('manuscript')
        if file:
            if not file.name.lower().endswith('.pdf'):
                raise forms.ValidationError('يجب أن يكون الملف بصيغة PDF.')
            if file.size > 20 * 1024 * 1024:  # 20MB
                raise forms.ValidationError('حجم الملف يتجاوز الحد الأقصى (20 ميغابايت).')
        return file


class CoAuthorForm(forms.ModelForm):
    class Meta:
        model  = CoAuthor
        fields = ['full_name', 'institution', 'email', 'order']
        widgets = {
            'full_name':   forms.TextInput(attrs={'class': 'form-control'}),
            'institution': forms.TextInput(attrs={'class': 'form-control'}),
            'email':       forms.EmailInput(attrs={'class': 'form-control'}),
            'order':       forms.HiddenInput(),
        }
        labels = {
            'full_name':   'الاسم الكامل',
            'institution': 'المؤسسة',
            'email':       'البريد الإلكتروني',
        }


CoAuthorFormSet = inlineformset_factory(
    ArticleSubmission,
    CoAuthor,
    form=CoAuthorForm,
    extra=1,
    can_delete=True,
    max_num=10,
)
