from django import forms
from apps.reviews.models import Review

SCORE_CHOICES = [('', '-- اختر --')] + [(i, str(i)) for i in range(1, 6)]


class ReviewForm(forms.Form):
    """نموذج تقييم المراجع — scores 1-5 + decision + comments."""

    score_originality = forms.ChoiceField(
        choices=SCORE_CHOICES,
        label='الأصالة والابتكار',
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    score_relevance = forms.ChoiceField(
        choices=SCORE_CHOICES,
        label='الصلة بالموضوع',
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    score_clarity = forms.ChoiceField(
        choices=SCORE_CHOICES,
        label='الوضوح والتنظيم',
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    score_language = forms.ChoiceField(
        choices=SCORE_CHOICES,
        label='اللغة والعرض',
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    decision = forms.ChoiceField(
        choices=[('', '-- اختر القرار --')] + list(Review.DECISION_CHOICES),
        label='القرار النهائي',
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    comments = forms.CharField(
        label='التعليقات والملاحظات',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 6}),
        required=False,
    )

    def clean_decision(self):
        decision = self.cleaned_data.get('decision')
        if not decision:
            raise forms.ValidationError('يجب اختيار قرار.')
        return decision

    def clean_score_originality(self):
        return self._clean_score('score_originality')

    def clean_score_relevance(self):
        return self._clean_score('score_relevance')

    def clean_score_clarity(self):
        return self._clean_score('score_clarity')

    def clean_score_language(self):
        return self._clean_score('score_language')

    def _clean_score(self, field_name):
        value = self.cleaned_data.get(field_name)
        if not value:
            raise forms.ValidationError('هذا الحقل مطلوب.')
        return int(value)

    def get_scores(self) -> dict:
        """يُعيد dict الـ scores للاستخدام في ReviewService."""
        return {
            'originality': self.cleaned_data.get('score_originality'),
            'relevance':   self.cleaned_data.get('score_relevance'),
            'clarity':     self.cleaned_data.get('score_clarity'),
            'language':    self.cleaned_data.get('score_language'),
        }
