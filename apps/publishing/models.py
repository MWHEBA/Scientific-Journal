from django.db import models


class Volume(models.Model):
    number     = models.PositiveSmallIntegerField(unique=True)
    year       = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-number']

    def __str__(self):
        return f"Volume {self.number} ({self.year})"


class Issue(models.Model):
    QUARTER_CHOICES = [
        (1, 'Jan–Mar'),
        (2, 'Apr–Jun'),
        (3, 'Jul–Sep'),
        (4, 'Oct–Dec'),
    ]

    volume       = models.ForeignKey(Volume, on_delete=models.CASCADE, related_name='issues')
    number       = models.PositiveSmallIntegerField()
    quarter      = models.PositiveSmallIntegerField(choices=QUARTER_CHOICES)
    is_current   = models.BooleanField(default=False)
    published_at = models.DateField(null=True, blank=True)

    class Meta:
        unique_together = ('volume', 'number')
        ordering = ['-volume__number', '-number']

    def __str__(self):
        return f"Vol.{self.volume.number} Issue {self.number} ({self.get_quarter_display()})"


class PublishedArticle(models.Model):
    """
    pdf_file هو reference لنفس ملف ManuscriptFile.file الحالي وقت النشر.
    لا يُنسخ الملف — يُشار إليه مباشرة لتوفير المساحة.
    """
    submission      = models.OneToOneField(
        'submissions.ArticleSubmission',
        on_delete=models.CASCADE,
        related_name='published',
    )
    manuscript_file = models.ForeignKey(
        'submissions.ManuscriptFile',
        on_delete=models.PROTECT,
        related_name='+',
    )
    issue       = models.ForeignKey(
        Issue, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='articles',
    )
    title       = models.CharField(max_length=500)
    abstract    = models.TextField()
    keywords    = models.CharField(max_length=500)
    section     = models.ForeignKey(
        'submissions.JournalSection', on_delete=models.PROTECT
    )
    published_at = models.DateTimeField(auto_now_add=True)
    views_count  = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-published_at']

    @property
    def pdf_file(self):
        """الملف مأخوذ مباشرة من ManuscriptFile — لا نسخ."""
        return self.manuscript_file.file

    def __str__(self):
        return f"{self.title} ({self.published_at.date() if self.published_at else '—'})"
