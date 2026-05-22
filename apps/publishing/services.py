from django.db import transaction
from django.urls import reverse

from apps.publishing.models import PublishedArticle
from apps.publishing.exceptions import (
    AlreadyPublishedError,
    MissingManuscriptError,
    MissingSectionError,
    PublishNotAllowedError,
)
from apps.submissions.models import ArticleSubmission, AuditLog
from apps.submissions.statuses import SubmissionStatus
from apps.submissions.state_machine import SubmissionStateMachine
from apps.notifications.services import NotificationService


class PublishingService:

    @staticmethod
    def publish(submission: ArticleSubmission, actor=None) -> PublishedArticle:
        """
        ينشر المقال بعد تأكيد الدفع.
        يُستدعى صراحةً من PaymentService — لا signals.
        كل الجلب والتحقق داخل transaction واحدة مع select_for_update.
        """
        with transaction.atomic():
            # جلب submission بـ lock داخل الـ transaction
            sub = ArticleSubmission.objects.select_for_update().get(pk=submission.pk)

            # Guard 1: الحالة لازم تكون paid
            if sub.status != SubmissionStatus.PAID:
                raise PublishNotAllowedError(
                    f"Cannot publish submission with status '{sub.status}'"
                )

            # Guard 2: منع duplicate publish
            if PublishedArticle.objects.filter(submission=sub).exists():
                raise AlreadyPublishedError(
                    f"Submission {sub.id} is already published"
                )

            # Guard 3: لازم يوجد manuscript حالي — يُجلب داخل الـ transaction
            manuscript = sub.manuscript_files.select_for_update().filter(
                is_current=True
            ).first()
            if not manuscript:
                raise MissingManuscriptError(
                    f"No current manuscript file for submission {sub.id}"
                )
            if not sub.section_id:
                raise MissingSectionError(
                    f"No section assigned for submission {sub.id}"
                )

            # إنشاء PublishedArticle بـ reference للـ ManuscriptFile — لا نسخ
            keywords_str = ', '.join(sub.keywords.values_list('name', flat=True))
            article = PublishedArticle.objects.create(
                submission      = sub,
                manuscript_file = manuscript,
                title           = sub.title,
                abstract        = sub.abstract,
                keywords        = keywords_str,
                section         = sub.section,
            )

            # انتقال الحالة إلى published
            SubmissionStateMachine.transition(
                sub, SubmissionStatus.PUBLISHED,
                actor=actor,
                notes='Auto-published after payment confirmation',
            )

            # تسجيل في AuditLog
            AuditLog.objects.create(
                entity_type='PublishedArticle',
                entity_id=article.id,
                event='article_published',
                actor=actor,
            )

            # إشعار المؤلف
            NotificationService.notify(
                user=sub.author,
                type='article_published',
                title='تم نشر مقالك',
                message=f'تهانينا! تم نشر مقالك "{sub.title}" بنجاح وأصبح متاحاً للعموم.',
                target_url=reverse('dashboard:author'),
            )

        return article
