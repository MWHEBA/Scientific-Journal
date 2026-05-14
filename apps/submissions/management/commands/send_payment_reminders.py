from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.submissions.models import ArticleSubmission
from apps.submissions.statuses import SubmissionStatus
from apps.notifications.services import NotificationService


class Command(BaseCommand):
    help = 'إرسال تذكيرات الدفع للمؤلفين الذين تبقّى 7 أيام أو أقل على انتهاء مهلتهم'

    def handle(self, *args, **kwargs):
        now      = timezone.now()
        in_7days = now + timedelta(days=7)

        # التقديمات المقبولة التي تنتهي مهلتها خلال 7 أيام
        submissions = ArticleSubmission.objects.filter(
            status=SubmissionStatus.ACCEPTED,
            payment_deadline__gt=now,
            payment_deadline__lte=in_7days,
        ).select_related('author')

        sent_count = 0
        for sub in submissions:
            try:
                NotificationService.send_payment_reminder(sub)
                sent_count += 1
            except Exception as e:
                self.stderr.write(
                    self.style.ERROR(f'خطأ في إرسال تذكير للتقديم #{sub.pk}: {e}')
                )

        self.stdout.write(
            self.style.SUCCESS(f'تم إرسال {sent_count} تذكير دفع.')
        )
