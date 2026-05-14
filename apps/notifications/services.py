from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from apps.notifications.models import Notification


class NotificationService:

    @staticmethod
    def notify(user, type: str, title: str, message: str, target_url: str = '') -> None:
        """يُنشئ إشعاراً داخلياً ويُرسل بريداً إلكترونياً."""
        Notification.objects.create(
            user=user,
            type=type,
            title=title,
            message=message,
            target_url=target_url,
        )
        try:
            send_mail(
                subject=title,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL if hasattr(settings, 'DEFAULT_FROM_EMAIL') else 'noreply@journal.com',
                recipient_list=[user.email],
                fail_silently=True,
            )
        except Exception:
            pass  # البريد الإلكتروني اختياري — لا يوقف العملية

    @staticmethod
    def notify_admin_new_submission(submission) -> None:
        """إشعار المشرف عند تقديم مقالة جديدة."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        admins = User.objects.filter(role=User.ROLE_ADMIN)
        for admin in admins:
            NotificationService.notify(
                user=admin,
                type='new_submission',
                title='تقديم مقالة جديدة',
                message=f'تم تقديم مقالة جديدة بعنوان: "{submission.title}" من {submission.author.get_full_name() or submission.author.username}.',
                target_url=reverse('dashboard:submission_detail', args=[submission.pk]),
            )

    @staticmethod
    def notify_author(submission, notification_type: str, message: str) -> None:
        """إشعار مؤلف التقديم."""
        NotificationService.notify(
            user=submission.author,
            type=notification_type,
            title=_get_title_for_type(notification_type),
            message=message,
            target_url=_dashboard_url_for_user(submission.author),
        )

    @staticmethod
    def notify_author_review_decision(submission, decision: str, comments: str) -> None:
        """إشعار المؤلف بقرار المراجعة."""
        decision_map = {
            'accept':   ('payment_required',  'تم قبول مقالتك', f'تهانينا! تم قبول مقالتك "{submission.title}". يرجى إتمام الدفع لإتمام النشر.'),
            'reject':   ('review_decision',   'رفض مقالتك',     f'نأسف لإبلاغك برفض مقالتك "{submission.title}". التعليقات: {comments}'),
            'revision': ('review_decision',   'مطلوب تعديل',  f'طلب المراجع تعديلات على مقالتك "{submission.title}". التعليقات: {comments}'),
        }
        notification_type, title, message = decision_map.get(
            decision, ('review_decision', 'قرار المراجعة', comments)
        )
        NotificationService.notify(
            user=submission.author,
            type=notification_type,
            title=title,
            message=message,
            target_url=_dashboard_url_for_user(submission.author),
        )

    @staticmethod
    def notify_admin_review_completed(submission) -> None:
        """إشعار المشرف عند إكمال مراجعة."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        admins = User.objects.filter(role=User.ROLE_ADMIN)
        for admin in admins:
            NotificationService.notify(
                user=admin,
                type='review_completed',
                title='اكتملت مراجعة مقالة',
                message=f'اكتملت مراجعة المقالة "{submission.title}".',
                target_url=reverse('dashboard:submission_detail', args=[submission.pk]),
            )

    @staticmethod
    def notify_reviewer_assigned(submission, reviewer) -> None:
        """إشعار المراجع عند تعيينه."""
        NotificationService.notify(
            user=reviewer,
            type='reviewer_assigned',
            title='تم تعيينك لمراجعة مقالة',
            message=f'تم تعيينك لمراجعة المقالة "{submission.title}". يرجى الاطلاع عليه وتقديم تقييمك.',
            target_url=_dashboard_url_for_user(reviewer),
        )

    @staticmethod
    def notify_author_payment_failed(submission) -> None:
        """إشعار المؤلف عند فشل الدفع."""
        NotificationService.notify(
            user=submission.author,
            type='payment_required',
            title='فشل الدفع',
            message=f'فشلت عملية الدفع لمقالتك "{submission.title}". يرجى المحاولة مرة أخرى.',
            target_url=_dashboard_url_for_user(submission.author),
        )

    @staticmethod
    def send_payment_reminder(submission) -> None:
        """يُرسل تذكيراً قبل 7 أيام من انتهاء مهلة الدفع."""
        from django.utils import timezone
        days_left = (submission.payment_deadline - timezone.now()).days
        NotificationService.notify(
            user=submission.author,
            type='payment_reminder',
            title=f'تذكير: {days_left} أيام لإتمام الدفع',
            message=f'تبقّى {days_left} أيام لإتمام دفع رسوم نشر مقالتك "{submission.title}".',
            target_url=_dashboard_url_for_user(submission.author),
        )


def _dashboard_url_for_user(user) -> str:
    return reverse('dashboard:home')


def _get_title_for_type(notification_type: str) -> str:
    titles = {
        'submission_confirmed': 'تم استلام تقديمك',
        'initial_check_result': 'نتيجة الفحص الأولي',
        'review_decision':      'قرار المراجعة',
        'payment_required':     'مطلوب إتمام الدفع',
        'payment_reminder':     'تذكير بالدفع',
        'article_published':    'تم نشر مقالك',
        'reviewer_assigned':    'تم تعيينك لمراجعة مقالة',
        'new_submission':       'تقديم مقالة جديدة',
        'review_completed':     'اكتملت المراجعة',
    }
    return titles.get(notification_type, 'إشعار')
