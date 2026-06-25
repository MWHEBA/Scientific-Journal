from django.db import models
from django.conf import settings
from taggit.managers import TaggableManager
from apps.submissions.statuses import SubmissionStatus


class JournalSection(models.Model):
    name  = models.CharField(max_length=100)
    slug  = models.SlugField(unique=True)
    order = models.PositiveIntegerField(default=0, verbose_name="المسلسل")

    class Meta:
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class ArticleSubmission(models.Model):
    STATUS_DRAFT              = SubmissionStatus.DRAFT
    STATUS_INITIAL_CHECK      = SubmissionStatus.INITIAL_CHECK
    STATUS_UNDER_REVIEW       = SubmissionStatus.UNDER_REVIEW
    STATUS_REVISION_REQUIRED  = SubmissionStatus.REVISION_REQUIRED
    STATUS_ACCEPTED           = SubmissionStatus.ACCEPTED
    STATUS_PAYMENT_PROCESSING = SubmissionStatus.PAYMENT_PROCESSING
    STATUS_PAID               = SubmissionStatus.PAID
    STATUS_PUBLISHED          = SubmissionStatus.PUBLISHED
    STATUS_REJECTED           = SubmissionStatus.REJECTED
    STATUS_EXPIRED            = SubmissionStatus.EXPIRED
    STATUS_WITHDRAWN          = SubmissionStatus.WITHDRAWN

    STATUS_CHOICES = SubmissionStatus.CHOICES

    title             = models.CharField(max_length=500)
    abstract          = models.TextField()
    section           = models.ForeignKey(JournalSection, on_delete=models.PROTECT, null=True, blank=True)
    keywords          = TaggableManager(blank=True, verbose_name='الكلمات المفتاحية')
    author            = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                          related_name='submissions')
    status            = models.CharField(max_length=30, choices=STATUS_CHOICES,
                                         default=STATUS_DRAFT)
    revision_count    = models.PositiveSmallIntegerField(default=0)
    original_reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                          on_delete=models.SET_NULL,
                                          related_name='original_reviews')
    assigned_reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                          on_delete=models.SET_NULL,
                                          related_name='assigned_submissions')
    admin_notes                = models.TextField(blank=True)
    is_archived                = models.BooleanField(default=False)
    corresponding_author_email = models.EmailField(blank=True, help_text='البريد الإلكتروني للمؤلف المسؤول عن المراسلات')
    payment_deadline           = models.DateTimeField(null=True, blank=True)
    created_at                 = models.DateTimeField(auto_now_add=True)
    updated_at                 = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} [{self.status}]"


class CoAuthor(models.Model):
    submission  = models.ForeignKey(ArticleSubmission, on_delete=models.CASCADE,
                                    related_name='co_authors')
    full_name   = models.CharField(max_length=255)
    institution = models.CharField(max_length=255, blank=True)
    order       = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.full_name


class ManuscriptFile(models.Model):
    submission  = models.ForeignKey(ArticleSubmission, on_delete=models.CASCADE,
                                    related_name='manuscript_files')
    file        = models.FileField(upload_to='manuscripts/%Y/%m/')
    version     = models.PositiveSmallIntegerField(default=1)
    is_current  = models.BooleanField(default=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('submission', 'version')

    def __str__(self):
        return f"v{self.version} - {self.submission.title}"


class AuditLog(models.Model):
    entity_type = models.CharField(max_length=50)
    entity_id   = models.PositiveIntegerField()
    event       = models.CharField(max_length=100)
    old_value   = models.CharField(max_length=100, blank=True)
    new_value   = models.CharField(max_length=100, blank=True)
    actor       = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.SET_NULL)
    notes       = models.TextField(blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['entity_type', 'entity_id']),
        ]

    def __str__(self):
        return f"{self.entity_type}#{self.entity_id} — {self.event}"
