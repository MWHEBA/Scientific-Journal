class PaymentNotAllowedError(Exception):
    """الدفع غير مسموح في الحالة الحالية للتقديم."""
    pass


class DuplicatePaymentError(Exception):
    """محاولة دفع مكررة — الدفع مكتمل مسبقاً."""
    pass
