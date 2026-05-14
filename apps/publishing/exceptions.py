class AlreadyPublishedError(Exception):
    """المقال منشور مسبقاً — لا يمكن النشر مرتين."""
    pass


class MissingManuscriptError(Exception):
    """لا يوجد ملف مخطوطة حالي للتقديم."""
    pass


class PublishNotAllowedError(Exception):
    """حالة التقديم لا تسمح بالنشر — يجب أن تكون paid."""
    pass
