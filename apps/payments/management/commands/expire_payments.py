"""
Management command: expire_payments
------------------------------------
يُشغَّل دورياً (Cron / Task Scheduler) لمعالجة:
  1. تحويل التقديمات المقبولة التي تجاوزت مهلة الدفع → Expired
  2. إرسال تذكير للتقديمات التي تبقّى لها 7 أيام أو أقل

الاستخدام:
    python manage.py expire_payments
    python manage.py expire_payments --dry-run   (معاينة بدون تغيير)
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from django.urls import reverse

from apps.submissions.models import ArticleSubmission
from apps.submissions.statuses import SubmissionStatus
from apps.submissions.state_machine import SubmissionStateMachine
from apps.notifications.services import NotificationService


class Command(BaseCommand):
    help = 'تحويل التقديمات المنتهية مهلة دفعها إلى Expired وإرسال تذكيرات الدفع'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            dest='dry_run',
            action='store_true',
            help='معاينة التقديمات المتأثرة بدون تنفيذ أي تغييرات',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        now = timezone.now()

        if dry_run:
            self.stdout.write(self.style.WARNING('--- وضع المعاينة (dry-run) --- لن يتم تغيير أي بيانات'))

        self._expire_overdue(now, dry_run)
        self._send_reminders(now, dry_run)

    # ─── expire overdue ───────────────────────────────────────────────────────

    def _expire_overdue(self, now, dry_run: bool) -> None:
        """
        يُحوّل التقديمات المقبولة التي تجاوزت payment_deadline إلى Expired.
        الحالات المؤهلة: accepted_awaiting_payment أو payment_processing
        (في حالة payment_processing يعني المستخدم بدأ الدفع لكن لم يكمله).
        """
        overdue = ArticleSubmission.objects.filter(
            status__in=[
                SubmissionStatus.ACCEPTED,
                SubmissionStatus.PAYMENT_PROCESSING,
            ],
            payment_deadline__lt=now,
        ).select_related('author')

        count = overdue.count()
        self.stdout.write(f'تقديمات منتهية المهلة: {count}')

        if dry_run:
            for sub in overdue:
                self.stdout.write(
                    f'  [dry-run] سيتم تحويل #{sub.pk} "{sub.title[:50]}" → Expired'
                )
            return

        expired_count = 0
        for sub in overdue:
            try:
                with transaction.atomic():
                    locked = ArticleSubmission.objects.select_for_update().get(pk=sub.pk)

                    # تحقق مزدوج داخل الـ transaction
                    if locked.status not in [
                        SubmissionStatus.ACCEPTED,
                        SubmissionStatus.PAYMENT_PROCESSING,
                    ]:
                        continue
                    if locked.payment_deadline and locked.payment_deadline >= now:
                        continue

                    SubmissionStateMachine.transition(
                        locked,
                        SubmissionStatus.EXPIRED,
                        notes='Payment deadline exceeded — auto-expired',
                    )

                    # إشعار المؤلف
                    NotificationService.notify(
                        user=locked.author,
                        type='payment_required',
                        title='انتهت مهلة الدفع',
                        message=(
                            f'انتهت مهلة الدفع لمقالتك "{locked.title}". '
                            f'تم تحويل حالة المقالة إلى "منتهي الصلاحية". '
                            f'يرجى التواصل مع إدارة المجلة إذا كنت ترغب في إعادة النظر.'
                        ),
                        target_url=reverse('dashboard:author'),
                    )
                    expired_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f'  ✓ #{sub.pk} "{sub.title[:50]}" → Expired')
                    )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'  ✗ خطأ في #{sub.pk}: {e}')
                )

        self.stdout.write(self.style.SUCCESS(f'تم تحويل {expired_count} تقديم إلى Expired'))

    # ─── send reminders ───────────────────────────────────────────────────────

    def _send_reminders(self, now, dry_run: bool) -> None:
        """
        يُرسل تذكيراً للتقديمات المقبولة التي تبقّى لها 7 أيام أو أقل.
        يتجنب إرسال تذكير مكرر بالتحقق من الإشعارات الموجودة.
        """
        from datetime import timedelta
        from apps.notifications.models import Notification

        reminder_window = now + timedelta(days=7)

        pending = ArticleSubmission.objects.filter(
            status=SubmissionStatus.ACCEPTED,
            payment_deadline__gt=now,
            payment_deadline__lte=reminder_window,
        ).select_related('author')

        count = pending.count()
        self.stdout.write(f'تقديمات تحتاج تذكير (≤7 أيام): {count}')

        if dry_run:
            for sub in pending:
                days_left = (sub.payment_deadline - now).days
                self.stdout.write(
                    f'  [dry-run] سيتم إرسال تذكير لـ #{sub.pk} "{sub.title[:50]}" '
                    f'(متبقي {days_left} يوم)'
                )
            return

        reminded_count = 0
        for sub in pending:
            # تجنب التذكير المكرر في نفس اليوم
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            already_reminded = Notification.objects.filter(
                user=sub.author,
                type='payment_reminder',
                created_at__gte=today_start,
                message__contains=sub.title[:30],
            ).exists()

            if already_reminded:
                continue

            try:
                NotificationService.send_payment_reminder(sub)
                reminded_count += 1
                days_left = (sub.payment_deadline - now).days
                self.stdout.write(
                    self.style.SUCCESS(
                        f'  ✓ تذكير أُرسل لـ #{sub.pk} "{sub.title[:50]}" '
                        f'(متبقي {days_left} يوم)'
                    )
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'  ✗ خطأ في إرسال تذكير #{sub.pk}: {e}')
                )

        self.stdout.write(self.style.SUCCESS(f'تم إرسال {reminded_count} تذكير'))
