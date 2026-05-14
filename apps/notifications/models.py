from django.db import models
from django.conf import settings


class Notification(models.Model):
    TYPE_CHOICES = [
        ('submission_confirmed', 'تم استلام التقديم'),
        ('initial_check_result', 'نتيجة الفحص الأولي'),
        ('review_decision',      'قرار المراجعة'),
        ('payment_required',     'مطلوب إتمام الدفع'),
        ('payment_reminder',     'تذكير بالدفع'),
        ('article_published',    'تم نشر المقال'),
        ('reviewer_assigned',    'تم تعيينك مراجعاً'),
        ('new_submission',       'تقديم جديد'),
        ('review_completed',     'اكتملت المراجعة'),
    ]

    user       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                   related_name='notifications')
    type       = models.CharField(max_length=50, choices=TYPE_CHOICES)
    title      = models.CharField(max_length=255)
    message    = models.TextField()
    target_url = models.CharField(max_length=500, blank=True)
    is_read    = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.type} → {self.user.username}"
