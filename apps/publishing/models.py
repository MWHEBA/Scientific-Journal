from django.db import models
from django.urls import reverse
from django.utils.text import slugify


class Volume(models.Model):
    number = models.PositiveSmallIntegerField(unique=True)
    year = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-number']

    def __str__(self):
        return f"Volume {self.number} ({self.year})"


class Issue(models.Model):
    QUARTER_CHOICES = [
        (1, 'يناير'),
        (2, 'مارس'),
        (3, 'مايو'),
        (4, 'يوليو'),
        (5, 'سبتمبر'),
        (6, 'نوفمبر'),
    ]

    volume = models.ForeignKey(Volume, on_delete=models.CASCADE, related_name='issues')
    number = models.PositiveSmallIntegerField()
    quarter = models.PositiveSmallIntegerField(choices=QUARTER_CHOICES)
    is_current = models.BooleanField(default=False)
    published_at = models.DateField(null=True, blank=True)

    class Meta:
        unique_together = ('volume', 'number')
        ordering = ['-volume__number', '-number']

    def __str__(self):
        return f"مجلد {self.volume.number} - عدد {self.number} ({self.volume.year}، {self.get_quarter_display()})"


class PublishedArticle(models.Model):
    submission = models.OneToOneField(
        'submissions.ArticleSubmission',
        on_delete=models.CASCADE,
        related_name='published',
    )
    manuscript_file = models.ForeignKey(
        'submissions.ManuscriptFile',
        on_delete=models.PROTECT,
        related_name='+',
    )
    issue = models.ForeignKey(
        Issue, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='articles',
    )
    title = models.CharField(max_length=500)
    abstract = models.TextField()
    keywords = models.CharField(max_length=500)
    section = models.ForeignKey('submissions.JournalSection', on_delete=models.PROTECT)
    slug = models.SlugField(max_length=220, unique=True, db_index=True, blank=True)
    published_at = models.DateTimeField(auto_now_add=True)
    views_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-published_at']

    @property
    def pdf_file(self):
        return self.manuscript_file.file

    @staticmethod
    def _reserved_slugs():
        return {
            'about', 'aims-scope', 'editorial-board', 'review-process', 'ethics',
            'author-guidelines', 'apc', 'contact', 'topics', 'blog', 'conferences',
            'archive', 'search', 'section', 'current-issue', 'articles',
            'accounts', 'dashboard', 'payments', 'notifications', 'admin',
            'login', 'logout', 'register', 'password', 'favicon.ico', 'robots.txt', 'sitemap.xml',
        }

    @classmethod
    def generate_unique_slug(cls, source_text: str, exclude_pk=None) -> str:
        base = slugify((source_text or '').strip())[:200] or 'article'
        if base in cls._reserved_slugs():
            base = f'article-{base}'
        candidate = base
        i = 2
        while True:
            qs = cls.objects.filter(slug=candidate)
            if exclude_pk:
                qs = qs.exclude(pk=exclude_pk)
            if not qs.exists():
                return candidate
            suffix = f'-{i}'
            candidate = f'{base[:max(1, 220 - len(suffix))]}{suffix}'
            i += 1

    def save(self, *args, **kwargs):
        old_slug = None
        if self.pk:
            old_slug = PublishedArticle.objects.filter(pk=self.pk).values_list('slug', flat=True).first()

        source = self.slug or self.title
        self.slug = self.generate_unique_slug(source, exclude_pk=self.pk)

        super().save(*args, **kwargs)

        if old_slug and old_slug != self.slug:
            PublishedArticleSlugHistory.objects.get_or_create(article=self, slug=old_slug)

    def get_absolute_url(self):
        return reverse('pages:article_detail', kwargs={'slug': self.slug})

    def __str__(self):
        return f"{self.title} ({self.published_at.date() if self.published_at else '-'})"


class PublishedArticleSlugHistory(models.Model):
    article = models.ForeignKey(PublishedArticle, on_delete=models.CASCADE, related_name='slug_history')
    slug = models.SlugField(max_length=220, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.slug} -> {self.article_id}'
