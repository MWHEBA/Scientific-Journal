from django import forms
from django.forms import inlineformset_factory
from apps.submissions.models import ArticleSubmission, CoAuthor, JournalSection


class SubmissionForm(forms.ModelForm):
    keywords = forms.CharField(
        required=False,
        label='الكلمات المفتاحية',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'كلمة١، كلمة٢، كلمة٣',
            'id': 'id_keywords_input'
        }),
        help_text='أدخل الكلمات مفصولة بفاصلة (اختياري)'
    )

    class Meta:
        model  = ArticleSubmission
        fields = ['title', 'abstract', 'section', 'corresponding_author_email']
        widgets = {
            'title':                       forms.TextInput(attrs={'class': 'form-control'}),
            'abstract':                    forms.Textarea(attrs={'class': 'form-control', 'rows': 6}),
            'section':                     forms.Select(attrs={'class': 'form-control'}),
            'corresponding_author_email':  forms.EmailInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'title':                       'عنوان المقالة',
            'abstract':                    'الملخص',
            'section':                     'القسم العلمي',
            'corresponding_author_email':  'البريد الإلكتروني للمؤلف المسؤول',
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        # جعل القسم اختياري
        self.fields['section'].required = False
        self.fields['section'].widget.attrs['class'] = 'form-control submit-field__select'
        
        # جعل الإيميل إجباري
        self.fields['corresponding_author_email'].required = True
        self.fields['corresponding_author_email'].widget.attrs['class'] = 'form-control submit-field__input'
        
        # ملء البيانات الافتراضية من المستخدم (عند إنشاء submission جديد)
        if user and not self.instance.pk:
            self.fields['corresponding_author_email'].initial = user.email
        
        # إضافة الكلمات المفتاحية من المثيل إن وجدت
        if self.instance and self.instance.pk:
            self.fields['keywords'].initial = ', '.join(
                self.instance.keywords.values_list('name', flat=True)
            )

    def save(self, commit=True):
        instance = super().save(commit=commit)
        if commit:
            # حفظ الكلمات المفتاحية
            keywords_str = self.cleaned_data.get('keywords', '')
            if keywords_str:
                keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
                instance.keywords.set(keywords)
            else:
                instance.keywords.clear()
        return instance


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
        fields = ['full_name', 'institution', 'order']
        widgets = {
            'full_name':   forms.TextInput(attrs={'class': 'form-control'}),
            'institution': forms.TextInput(attrs={'class': 'form-control'}),
            'order':       forms.HiddenInput(),
        }
        labels = {
            'full_name':   'الاسم الكامل',
            'institution': 'المؤسسة',
        }


CoAuthorFormSet = inlineformset_factory(
    ArticleSubmission,
    CoAuthor,
    form=CoAuthorForm,
    extra=0,
    can_delete=True,
    max_num=10,
)
