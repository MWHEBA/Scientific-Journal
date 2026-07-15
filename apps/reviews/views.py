from django.views.generic import DetailView, View
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.urls import reverse

from apps.accounts.mixins import ReviewerRequiredMixin
from apps.reviews.models import Review
from apps.reviews.forms import ReviewForm
from apps.reviews.services import ReviewService
from apps.submissions.exceptions import (
    InvalidStateTransitionError,
    RevisionLimitExceededError,
)

def _t(ar_text, en_text):
    from django.utils import translation
    return en_text if translation.get_language() == 'en' else ar_text


class ReviewDetailView(ReviewerRequiredMixin, DetailView):
    """عرض تفاصيل المخطوطة للمراجع — object-level permission."""
    model         = Review
    template_name = 'reviews/detail.html'

    def get_object(self, queryset=None):
        obj = get_object_or_404(Review, pk=self.kwargs['pk'])
        if obj.reviewer != self.request.user:
            raise PermissionDenied
        return obj

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['manuscript'] = self.object.submission.manuscript_files.filter(
            is_current=True
        ).first()
        ctx['form'] = ReviewForm() if not self.object.is_submitted else None
        return ctx


class ReviewSubmitView(ReviewerRequiredMixin, View):
    """إرسال قرار المراجعة — يستدعي ReviewService.submit_review()."""

    def post(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        if review.reviewer != request.user:
            raise PermissionDenied

        if review.is_submitted:
            messages.error(request, _t('تم إرسال هذه المراجعة مسبقاً.', 'This review has already been submitted.'))
            return redirect(reverse('reviews:detail', kwargs={'pk': pk}))

        form = ReviewForm(request.POST)
        if not form.is_valid():
            return render(request, 'reviews/detail.html', {
                'object': review,
                'review': review,
                'form': form,
                'manuscript': review.submission.manuscript_files.filter(
                    is_current=True
                ).first(),
            })

        try:
            ReviewService.submit_review(
                review=review,
                decision=form.cleaned_data['decision'],
                scores=form.get_scores(),
                comments=form.cleaned_data.get('comments', ''),
                actor=request.user,
            )
            messages.success(request, _t('تم إرسال قرار المراجعة بنجاح.', 'Review decision submitted successfully.'))
        except InvalidStateTransitionError as e:
            messages.error(request, _t(f'خطأ: {e}', f'Error: {e}'))
        except RevisionLimitExceededError:
            messages.error(
                request,
                _t('وصل المقالة للحد الأقصى من دورات التعديل. يجب اختيار قبول أو رفض.', 'The article has reached the maximum number of revision rounds. You must choose accept or reject.')
            )

        return redirect(reverse('dashboard:reviewer'))
