from django.db import models


class Payment(models.Model):
    STATUS_PENDING    = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_COMPLETED  = 'completed'
    STATUS_FAILED     = 'failed'
    STATUS_EXPIRED    = 'expired'

    STATUS_CHOICES = [
        (STATUS_PENDING,    'Pending'),
        (STATUS_PROCESSING, 'Processing'),
        (STATUS_COMPLETED,  'Completed'),
        (STATUS_FAILED,     'Failed'),
        (STATUS_EXPIRED,    'Expired'),
    ]

    submission       = models.OneToOneField(
        'submissions.ArticleSubmission',
        on_delete=models.CASCADE,
        related_name='payment',
    )
    amount           = models.DecimalField(max_digits=10, decimal_places=2)
    currency         = models.CharField(max_length=3, default='USD')
    status           = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    gateway_name     = models.CharField(max_length=50, blank=True)
    gateway_order_id = models.CharField(max_length=255, blank=True, db_index=True)
    gateway_response = models.JSONField(default=dict, blank=True)
    paid_at          = models.DateTimeField(null=True, blank=True)
    created_at       = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment #{self.pk} — {self.submission.title} [{self.status}]"
