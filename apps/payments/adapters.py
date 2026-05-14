import uuid
import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional


@dataclass
class NormalizedPaymentData:
    """بيانات موحّدة من أي بوابة دفع — مستقلة عن المزوّد."""
    external_order_id: str
    payment_status:    str          # 'success' | 'failed' | 'pending'
    paid_at:           Optional[datetime]
    raw_payload:       dict


class PaymentGatewayAdapter:
    """
    واجهة مجردة — كل مزوّد دفع يُنفّذ هذه الواجهة.
    normalize_webhook() هي الطريقة الوحيدة لقراءة بيانات الـ webhook.
    """

    def create_order(self, amount: Decimal, currency: str, metadata: dict) -> dict:
        """
        يُنشئ طلب دفع لدى البوابة.
        يُعيد: {'order_id': str, 'payment_url': str}
        """
        raise NotImplementedError

    def verify_signature(self, payload: bytes, signature: str) -> bool:
        """يتحقق من صحة توقيع الـ webhook."""
        raise NotImplementedError

    def normalize_webhook(self, payload: dict) -> NormalizedPaymentData:
        """
        يُحوّل payload الخام لبيانات موحّدة.
        كل gateway يُنفّذ هذه الطريقة بشكل مختلف.
        """
        raise NotImplementedError


class MockPaymentGatewayAdapter(PaymentGatewayAdapter):
    """
    Adapter وهمي للتطوير والاختبار.
    يُحاكي بوابة دفع حقيقية دون الحاجة لـ API خارجي.
    """
    SECRET_KEY = 'mock-secret-key-for-testing'

    def create_order(self, amount: Decimal, currency: str, metadata: dict) -> dict:
        order_id = f"MOCK-{uuid.uuid4().hex[:12].upper()}"
        return {
            'order_id':    order_id,
            'payment_url': f'/payments/mock/pay/{order_id}/',
        }

    def verify_signature(self, payload: bytes, signature: str) -> bool:
        expected = hmac.HMAC(
            self.SECRET_KEY.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def normalize_webhook(self, payload: dict) -> NormalizedPaymentData:
        from django.utils import timezone
        status_map = {
            'paid':    'success',
            'success': 'success',
            'failed':  'failed',
            'failure': 'failed',
        }
        raw_status = payload.get('status', 'failed')
        return NormalizedPaymentData(
            external_order_id=payload.get('order_id', ''),
            payment_status=status_map.get(raw_status, 'failed'),
            paid_at=timezone.now() if raw_status in ('paid', 'success') else None,
            raw_payload=payload,
        )
