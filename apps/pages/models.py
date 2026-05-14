from django.db import models


class SiteSettings(models.Model):
    """Singleton — سجل واحد فقط في قاعدة البيانات."""
    journal_name          = models.CharField(max_length=255, default='Scientific Journal')
    journal_desc          = models.TextField(blank=True)
    apc_amount            = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_deadline_days = models.PositiveSmallIntegerField(default=30)
    contact_email         = models.EmailField(blank=True)
    contact_address       = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Site Settings'
        verbose_name_plural = 'Site Settings'

    def save(self, *args, **kwargs):
        self.pk = 1  # يضمن وجود سجل واحد فقط
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return self.journal_name


class EditorialBoardMember(models.Model):
    """عضو في هيئة التحرير — يُدار من لوحة الإدارة."""

    ROLE_EDITOR_IN_CHIEF  = 'editor_in_chief'
    ROLE_DEPUTY_EDITOR    = 'deputy_editor'
    ROLE_REGIONAL_EDITOR  = 'regional_editor'
    ROLE_SUPERVISORY      = 'supervisory'
    ROLE_EDITORIAL        = 'editorial'

    ROLE_CHOICES = [
        (ROLE_EDITOR_IN_CHIEF, 'رئيس التحرير'),
        (ROLE_DEPUTY_EDITOR,   'نائب رئيس التحرير'),
        (ROLE_REGIONAL_EDITOR, 'رئيس تحرير إقليمي'),
        (ROLE_SUPERVISORY,     'عضو اللجنة الإشرافية'),
        (ROLE_EDITORIAL,       'عضو هيئة التحرير'),
    ]

    name        = models.CharField(max_length=255, verbose_name='الاسم')
    role        = models.CharField(max_length=30, choices=ROLE_CHOICES,
                                   default=ROLE_EDITORIAL, verbose_name='الدور')
    institution = models.CharField(max_length=255, blank=True, verbose_name='المؤسسة')
    country     = models.CharField(max_length=100, blank=True, verbose_name='الدولة')
    email       = models.EmailField(blank=True, verbose_name='البريد الإلكتروني')
    order       = models.PositiveSmallIntegerField(default=0, verbose_name='الترتيب')
    is_active   = models.BooleanField(default=True, verbose_name='نشط')

    class Meta:
        ordering = ['order', 'name']
        verbose_name = 'عضو هيئة التحرير'
        verbose_name_plural = 'هيئة التحرير'

    def __str__(self):
        return f"{self.name} ({self.get_role_display()})"
