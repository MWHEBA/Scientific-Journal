from django.db import models
from django.conf import settings


class Review(models.Model):
    DECISION_ACCEPT   = 'accept'
    DECISION_REJECT   = 'reject'
    DECISION_REVISION = 'revision'
    DECISION_CHOICES  = [
        (DECISION_ACCEPT,   'قبول'),
        (DECISION_REJECT,   'رفض'),
        (DECISION_REVISION, 'يتطلب تعديلات'),
    ]

    SCORE_CHOICES = [(i, str(i)) for i in range(1, 6)]  # 1–5

    submission    = models.ForeignKey(
        'submissions.ArticleSubmission',
        on_delete=models.CASCADE,
        related_name='reviews',
    )
    reviewer      = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reviews',
    )
    decision      = models.CharField(max_length=20, choices=DECISION_CHOICES, blank=True)
    comments      = models.TextField(blank=True)

    # معايير التقييم (1–5)
    score_originality = models.PositiveSmallIntegerField(
        null=True, blank=True, choices=SCORE_CHOICES
    )
    score_relevance   = models.PositiveSmallIntegerField(
        null=True, blank=True, choices=SCORE_CHOICES
    )
    score_clarity     = models.PositiveSmallIntegerField(
        null=True, blank=True, choices=SCORE_CHOICES
    )
    score_language    = models.PositiveSmallIntegerField(
        null=True, blank=True, choices=SCORE_CHOICES
    )

    is_submitted   = models.BooleanField(default=False)
    revision_round = models.PositiveSmallIntegerField(default=1)
    created_at     = models.DateTimeField(auto_now_add=True)
    submitted_at   = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Review #{self.pk} — {self.submission.title} [{self.decision or 'pending'}]"
