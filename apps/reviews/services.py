from datetime import timedelta
from django.db import transaction
from django.utils import timezone

from apps.reviews.models import Review
from apps.submissions.models import ArticleSubmission
from apps.submissions.statuses import SubmissionStatus
from apps.submissions.state_machine import SubmissionStateMachine
from apps.submissions.exceptions import (
    InvalidStateTransitionError,
    RevisionLimitExceededError,
)
from apps.pages.models import SiteSettings
from apps.notifications.services import NotificationService


class ReviewService:

    @staticmethod
    def submit_review(review: Review, decision: str,
                      scores: dict, comments: str, actor) -> None:
        """
        تسجيل قرار المراجع وتحديث حالة التقديم.
        كل شيء في transaction واحدة مع select_for_update.
        """
        # التحقق من عدم الإرسال المسبق
        if review.is_submitted:
            raise InvalidStateTransitionError("Review already submitted")

        # التحقق من صحة القرار
        if decision not in [Review.DECISION_ACCEPT,
                             Review.DECISION_REJECT,
                             Review.DECISION_REVISION]:
            raise ValueError(f"Invalid decision: {decision}")

        # التحقق من حد التعديل
        if (decision == Review.DECISION_REVISION
                and review.submission.revision_count >= 2):
            raise RevisionLimitExceededError(
                "Max revision cycles reached. Must accept or reject."
            )
        with transaction.atomic():
            sub = ArticleSubmission.objects.select_for_update().get(
                pk=review.submission_id
            )
            if sub.assigned_reviewer_id != review.reviewer_id:
                raise InvalidStateTransitionError(
                    "Only the currently assigned reviewer can submit this review"
                )

            # حفظ بيانات المراجعة
            review.decision          = decision
            review.comments          = comments
            review.score_originality = scores.get('originality')
            review.score_relevance   = scores.get('relevance')
            review.score_clarity     = scores.get('clarity')
            review.score_language    = scores.get('language')
            review.is_submitted      = True
            review.submitted_at      = timezone.now()
            review.save()

            # تحديث حالة التقديم بناءً على القرار
            if decision == Review.DECISION_ACCEPT:
                sub.payment_deadline = timezone.now() + timedelta(
                    days=SiteSettings.get().payment_deadline_days
                )
                sub.save(update_fields=['payment_deadline', 'updated_at'])
                SubmissionStateMachine.transition(
                    sub, SubmissionStatus.ACCEPTED,
                    actor=actor, notes='قبل المراجع المقالة',
                )
            elif decision == Review.DECISION_REJECT:
                SubmissionStateMachine.transition(
                    sub, SubmissionStatus.REJECTED,
                    actor=actor, notes='رفض المراجع المقالة',
                )
            else:  # revision
                SubmissionStateMachine.transition(
                    sub, SubmissionStatus.REVISION_REQUIRED,
                    actor=actor, notes='طلب المراجع تعديلات',
                )

            # إشعار المؤلف والمشرف
            NotificationService.notify_author_review_decision(sub, decision, comments)
            NotificationService.notify_admin_review_completed(sub)
