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

    @property
    def localized_title(self):
        from django.utils import translation
        if translation.get_language() == 'en':
            return self._translate_title()
        return self.title

    @property
    def localized_message(self):
        from django.utils import translation
        if translation.get_language() == 'en':
            return self._translate_message()
        return self.message

    def _translate_title(self):
        title = self.title
        mapping = {
            'تقديم مقالة جديدة': 'New article submission',
            'تقديم جديد': 'New submission',
            'تم استلام التقديم': 'Submission received',
            'تم استلام تقديمك': 'Submission received',
            'نتيجة الفحص الأولي': 'Initial check result',
            'قرار المراجعة': 'Review decision',
            'مطلوب إتمام الدفع': 'Payment required',
            'تذكير بالدفع': 'Payment reminder',
            'تم نشر المقال': 'Article published',
            'تم نشر مقالك': 'Your article has been published',
            'تم تعيينك كمراجع': 'You have been assigned as a reviewer',
            'تم تعيينك لمراجعة مقالة': 'You have been assigned to review an article',
            'تم تعيينك مراجعاً': 'You have been assigned as a reviewer',
            'اكتملت المراجعة': 'Review completed',
            'اكتملت مراجعة مقالة': 'Article review completed',
            'تم قبول مقالتك': 'Your article has been accepted',
            'رفض مقالتك': 'Your article was rejected',
            'مطلوب تعديل': 'Revision required',
            'مراجع سجل نفسه لمراجعة مقالة': 'Reviewer self-assigned to review an article',
            'فشل الدفع': 'Payment failed',
            'انتهت مهلة الدفع': 'Payment deadline expired',
        }
        if title in mapping:
            return mapping[title]
        
        import re
        m = re.match(r'^تذكير:\s*(\d+)\s*أيام لإتمام الدفع$', title)
        if m:
            return f"Reminder: {m.group(1)} days left to complete payment"
            
        return title

    def _translate_message(self):
        message = self.message
        import re
        
        m = re.match(r'^تم تقديم مقالة جديدة بعنوان:\s*"(.*)"\s*من\s*(.*)\.$', message)
        if m:
            return f'A new article was submitted: "{m.group(1)}" by {m.group(2)}.'
            
        m = re.match(r'^تم قبول مقالتك\s*"(.*)"\s*للمراجعة الأكاديمية\.$', message)
        if m:
            return f'Your article "{m.group(1)}" has been accepted for academic review.'
            
        m = re.match(r'^نأسف لإبلاغك برفض مقالتك\s*"(.*)"\s*في الفحص الأولي\.\s*السبب:\s*(.*)$', message)
        if m:
            return f'We regret to inform you that your article "{m.group(1)}" was rejected in the initial check. Reason: {m.group(2)}'
            
        m = re.match(r'^تم سحب مقالتك\s*"(.*)"\s*بنجاح\.$', message)
        if m:
            return f'Your article "{m.group(1)}" has been successfully withdrawn.'
            
        m = re.match(r'^تهانينا!\s*تم قبول مقالتك\s*"(.*)"\.\s*يرجى إتمام الدفع لإتمام النشر\.$', message)
        if m:
            return f'Congratulations! Your article "{m.group(1)}" has been accepted. Please complete the payment to proceed with publishing.'
            
        m = re.match(r'^فشلت عملية الدفع لمقالتك\s*"(.*)"\.\s*يرجى المحاولة مرة أخرى\.$', message)
        if m:
            return f'Payment failed for your article "{m.group(1)}". Please try again.'
            
        m = re.match(r'^انتهت مهلة الدفع لمقالتك\s*"(.*)"\.\s*تم تحويل حالة المقالة إلى "منتهي الصلاحية"\.\s*يرجى التواصل مع إدارة المجلة إذا كنت ترغب في إعادة النظر\.$', message)
        if m:
            return f'Payment deadline expired for your article "{m.group(1)}". The status has been changed to "Expired". Please contact the journal administration if you wish to appeal.'
            
        m = re.match(r'^نأسف لإبلاغك برفض مقالتك\s*"(.*)"\.\s*التعليقات:\s*(.*)$', message)
        if m:
            return f'We regret to inform you that your article "{m.group(1)}" was rejected. Comments: {m.group(2)}'
            
        m = re.match(r'^طلب المراجع تعديلات على مقالتك\s*"(.*)"\.\s*التعليقات:\s*(.*)$', message)
        if m:
            return f'The reviewer requested revisions on your article "{m.group(1)}". Comments: {m.group(2)}'
            
        m = re.match(r'^اكتملت مراجعة المقالة\s*"(.*)"\.$', message)
        if m:
            return f'Review completed for the article "{m.group(1)}".'
            
        m = re.match(r'^تم تعيينك لمراجعة المقالة\s*"(.*)"\.\s*يرجى الاطلاع عليه وتقديم تقييمك\.$', message)
        if m:
            return f'You have been assigned to review the article "{m.group(1)}". Please examine it and provide your review.'
            
        m = re.match(r'^(.*)\s+سجل نفسه لمراجعة المقالة\s*"(.*)"\.$', message)
        if m:
            return f'{m.group(1)} has self-assigned to review the article "{m.group(2)}".'
            
        m = re.match(r'^تبقّى\s*(.*)\s*أيام لإتمام دفع رسوم نشر مقالتك\s*"(.*)"\.$', message)
        if m:
            return f'There are {m.group(1)} days left to complete the payment for publishing your article "{m.group(2)}".'
            
        m = re.match(r'^تهانينا!\s*تم نشر مقالك\s*"(.*)"\s*بنجاح وأصبح متاحاً للعموم\.$', message)
        if m:
            return f'Congratulations! Your article "{m.group(1)}" has been successfully published and is now publicly available.'

        return message
