from django.db import transaction
from apps.submissions.models import ArticleSubmission, ManuscriptFile
from apps.submissions.statuses import SubmissionStatus
from apps.submissions.state_machine import SubmissionStateMachine
from apps.submissions.exceptions import (
    InvalidStateTransitionError,
    RevisionLimitExceededError,
    InvalidManuscriptFileError,
)
from apps.notifications.services import NotificationService


class SubmissionService:

    @staticmethod
    def submit(submission: ArticleSubmission, actor) -> None:
        """Draft → Under Initial Check مباشرة، بدون حالة Submitted وسيطة."""
        with transaction.atomic():
            sub = ArticleSubmission.objects.select_for_update().get(pk=submission.pk)
            SubmissionStateMachine.transition(
                sub,
                SubmissionStatus.INITIAL_CHECK,
                actor=actor,
                notes='Author submitted',
            )
            NotificationService.notify_admin_new_submission(sub)

    @staticmethod
    def admin_pass_initial_check(submission: ArticleSubmission, actor) -> None:
        """Under Initial Check → Under Review."""
        with transaction.atomic():
            sub = ArticleSubmission.objects.select_for_update().get(pk=submission.pk)
            SubmissionStateMachine.transition(
                sub,
                SubmissionStatus.UNDER_REVIEW,
                actor=actor,
                notes='Admin passed initial check',
            )
            NotificationService.notify_author(
                sub,
                'initial_check_result',
                f'تم قبول مقالتك "{sub.title}" للمراجعة الأكاديمية.',
            )

    @staticmethod
    def admin_reject_initial_check(submission: ArticleSubmission,
                                   actor, reason: str) -> None:
        """Under Initial Check → Rejected."""
        with transaction.atomic():
            sub = ArticleSubmission.objects.select_for_update().get(pk=submission.pk)
            sub.admin_notes = reason
            sub.save(update_fields=['admin_notes'])
            SubmissionStateMachine.transition(
                sub,
                SubmissionStatus.REJECTED,
                actor=actor,
                notes=reason,
            )
            NotificationService.notify_author(
                sub,
                'initial_check_result',
                f'نأسف لإبلاغك برفض مقالتك "{sub.title}" في الفحص الأولي. السبب: {reason}',
            )

    @staticmethod
    def upload_revision(submission: ArticleSubmission, file, actor) -> None:
        """Revision Required → Under Review (بحد أقصى دورتين)."""
        # التحقق من الحالة قبل الـ transaction
        if submission.status != SubmissionStatus.REVISION_REQUIRED:
            raise InvalidStateTransitionError(
                f"Cannot upload revision when status is '{submission.status}'"
            )
        # التحقق من الحد
        if submission.revision_count >= 2:
            raise RevisionLimitExceededError("Maximum 2 revision cycles allowed")
        # التحقق من نوع الملف
        if not file.name.lower().endswith('.pdf'):
            raise InvalidManuscriptFileError("Manuscript must be a PDF file")

        with transaction.atomic():
            sub = ArticleSubmission.objects.select_for_update().get(pk=submission.pk)

            # إلغاء تفعيل النسخة الحالية
            ManuscriptFile.objects.filter(
                submission=sub, is_current=True
            ).update(is_current=False)

            # إنشاء نسخة جديدة — version = revision_count + 2 لتجنب التعارض
            next_version = sub.revision_count + 2
            ManuscriptFile.objects.create(
                submission=sub,
                file=file,
                version=next_version,
                is_current=True,
            )

            sub.revision_count += 1
            sub.save(update_fields=['revision_count', 'updated_at'])

            # إعادة تعيين original_reviewer تلقائياً عند رفع revision
            if sub.original_reviewer and sub.assigned_reviewer != sub.original_reviewer:
                sub.assigned_reviewer = sub.original_reviewer
                sub.save(update_fields=['assigned_reviewer', 'updated_at'])

            if sub.assigned_reviewer:
                from apps.reviews.models import Review
                Review.objects.get_or_create(
                    submission=sub,
                    reviewer=sub.assigned_reviewer,
                    revision_round=sub.revision_count + 1,
                )

            SubmissionStateMachine.transition(
                sub,
                SubmissionStatus.UNDER_REVIEW,
                actor=actor,
                notes=f'Revision #{sub.revision_count} uploaded',
            )

    @staticmethod
    def withdraw(submission: ArticleSubmission, actor) -> None:
        """المؤلف يسحب المقالة — Under Initial Check → Withdrawn."""
        with transaction.atomic():
            sub = ArticleSubmission.objects.select_for_update().get(pk=submission.pk)
            SubmissionStateMachine.transition(
                sub,
                SubmissionStatus.WITHDRAWN,
                actor=actor,
                notes='Author withdrew submission',
            )
            NotificationService.notify_author(
                sub,
                'withdrawal_confirmation',
                f'تم سحب مقالتك "{sub.title}" بنجاح.',
            )
