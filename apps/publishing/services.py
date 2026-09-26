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
    def publish(submission: ArticleSubmission, actor=None, force: bool = False,
                issue=None, custom_published_at=None, notes: str = '',
                send_notification: bool = True) -> PublishedArticle:
        """
        ينشر المقال بعد تأكيد الدفع أو مباشرة من قِبل المشرف (عندما force=True).
        يُدعم تحديد العدد وتاريخ نشر مخصص (Backdating) وإرسال إشعار اختياري.
        """
        with transaction.atomic():
            # جلب submission بـ lock داخل الـ transaction
            sub = ArticleSubmission.objects.select_for_update().get(pk=submission.pk)

            # Guard 1: الحالة لازم تكون paid إلا إذا تم التجاوز بـ force=True بواسطة المشرف
            if sub.status != SubmissionStatus.PAID and not force:
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
                issue           = issue,
                title           = sub.title,
                abstract        = sub.abstract,
                keywords        = keywords_str,
                section         = sub.section,
            )

            if custom_published_at:
                PublishedArticle.objects.filter(pk=article.pk).update(published_at=custom_published_at)
                article.refresh_from_db()

            # انتقال الحالة إلى published
            transition_notes = notes or ('Directly published by admin' if force else 'Auto-published after payment confirmation')
            SubmissionStateMachine.transition(
                sub, SubmissionStatus.PUBLISHED,
                actor=actor,
                notes=transition_notes,
                force=force,
            )

            # تسجيل في AuditLog
            AuditLog.objects.create(
                entity_type='PublishedArticle',
                entity_id=article.id,
                event='article_published',
                actor=actor,
                notes=notes or ('Admin direct publish' if force else ''),
            )

            # إشعار المؤلف اختياري حسب الخيار المالي
            if send_notification:
                NotificationService.notify(
                    user=sub.author,
                    type='article_published',
                    title='تم نشر مقالك',
                    message=f'تهانينا! تم نشر مقالك "{sub.title}" بنجاح وأصبح متاحاً للعموم.',
                    target_url=reverse('dashboard:author'),
                )

        return article
