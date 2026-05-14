class SubmissionStatus:
    DRAFT              = 'draft'
    INITIAL_CHECK      = 'under_initial_check'
    UNDER_REVIEW       = 'under_review'
    REVISION_REQUIRED  = 'revision_required'
    ACCEPTED           = 'accepted_awaiting_payment'
    PAYMENT_PROCESSING = 'payment_processing'
    PAID               = 'paid'
    PUBLISHED          = 'published'
    REJECTED           = 'rejected'
    EXPIRED            = 'expired'

    CHOICES = [
        (DRAFT,              'مسودة'),
        (INITIAL_CHECK,      'قيد الفحص الأولي'),
        (UNDER_REVIEW,       'قيد المراجعة'),
        (REVISION_REQUIRED,  'يتطلب تعديلات'),
        (ACCEPTED,           'مقبول – في انتظار الدفع'),
        (PAYMENT_PROCESSING, 'جاري معالجة الدفع'),
        (PAID,               'تم الدفع'),
        (PUBLISHED,          'منشور'),
        (REJECTED,           'مرفوض'),
        (EXPIRED,            'منتهي الصلاحية'),
    ]
