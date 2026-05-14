class InvalidStateTransitionError(Exception):
    """انتقال حالة غير مسموح به في State Machine."""
    pass


class RevisionLimitExceededError(Exception):
    """تجاوز الحد الأقصى لدورات التعديل (2 دورات)."""
    pass


class InvalidManuscriptFileError(Exception):
    """ملف المخطوطة غير صالح (يجب أن يكون PDF)."""
    pass
