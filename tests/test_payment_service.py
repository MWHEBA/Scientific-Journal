"""
اختبارات PaymentService — P8 (Idempotency)
"""
import json
import hmac
import hashlib
import pytest
from datetime import timedelta
from django.utils import timezone
from django.urls import reverse
from hypothesis import given, settings as h_settings, HealthCheck
from hypothesis import strategies as st

from apps.payments.services import PaymentService
from apps.payments.models import Payment
from apps.payments.adapters import MockPaymentGatewayAdapter
from apps.payments.exceptions import PaymentNotAllowedError, DuplicatePaymentError
from apps.submissions.statuses import SubmissionStatus
from apps.publishing.models import PublishedArticle
from apps.notifications.models import Notification


def _make_webhook(order_id: str, status: str = 'paid') -> tuple[bytes, str]:
    """يُنشئ webhook payload + signature صحيح."""
    payload = json.dumps({'order_id': order_id, 'status': status}).encode()
    signature = hmac.HMAC(
        MockPaymentGatewayAdapter.SECRET_KEY.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return payload, signature


# ─── initiate_payment() ──────────────────────────────────────────────────────

@pytest.mark.django_db
def test_initiate_payment_wrong_status_raises(make_submission, author, payment_service):
    """initiate_payment() يرفع PaymentNotAllowedError إذا لم تكن الحالة accepted."""
    sub = make_submission(status=SubmissionStatus.UNDER_REVIEW, author=author)
    with pytest.raises(PaymentNotAllowedError):
        payment_service.initiate_payment(sub, actor=author)


@pytest.mark.django_db
def test_initiate_payment_duplicate_raises(make_submission, author, payment_service, site_settings):
    """initiate_payment() يرفع DuplicatePaymentError إذا كان الدفع مكتملاً."""
    sub = make_submission(status=SubmissionStatus.ACCEPTED, author=author)
    sub.payment_deadline = timezone.now() + timedelta(days=30)
    sub.save()

    # أول مرة — تنجح
    payment_service.initiate_payment(sub, actor=author)
    sub.refresh_from_db()

    # نجعل الدفع مكتملاً
    payment = sub.payment
    payment.status = Payment.STATUS_COMPLETED
    payment.save()

    # إعادة الحالة لـ accepted للاختبار
    sub.status = SubmissionStatus.ACCEPTED
    sub.save()

    with pytest.raises(DuplicatePaymentError):
        payment_service.initiate_payment(sub, actor=author)


@pytest.mark.django_db
def test_initiate_payment_transitions_to_processing(make_submission, author, payment_service, site_settings):
    """initiate_payment() ينقل الحالة إلى payment_processing."""
    sub = make_submission(status=SubmissionStatus.ACCEPTED, author=author)
    sub.payment_deadline = timezone.now() + timedelta(days=30)
    sub.save()

    payment_service.initiate_payment(sub, actor=author)
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.PAYMENT_PROCESSING


@pytest.mark.django_db
def test_initiate_payment_order_failure_rolls_back_submission_status(
    make_submission, author, site_settings
):
    class FailingGateway(MockPaymentGatewayAdapter):
        def create_order(self, amount, currency, metadata):
            raise RuntimeError("gateway down")

    service = PaymentService(gateway=FailingGateway())
    sub = make_submission(status=SubmissionStatus.ACCEPTED, author=author)
    sub.payment_deadline = timezone.now() + timedelta(days=30)
    sub.save()

    with pytest.raises(RuntimeError):
        service.initiate_payment(sub, actor=author)

    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.ACCEPTED
    assert sub.payment.status == Payment.STATUS_FAILED


# ─── handle_webhook() ────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_webhook_invalid_signature_raises(make_submission, author, payment_service, site_settings):
    """handle_webhook() يرفع PermissionError عند توقيع خاطئ."""
    sub = make_submission(status=SubmissionStatus.ACCEPTED, author=author)
    sub.payment_deadline = timezone.now() + timedelta(days=30)
    sub.save()

    payment_service.initiate_payment(sub, actor=author)
    sub.refresh_from_db()
    order_id = sub.payment.gateway_order_id

    payload = json.dumps({'order_id': order_id, 'status': 'paid'}).encode()
    with pytest.raises(PermissionError):
        payment_service.handle_webhook(payload, 'invalid-signature')


@pytest.mark.django_db
def test_webhook_success_publishes_article(make_submission, author, payment_service, site_settings):
    """handle_webhook() نجاح: Payment completed + submission paid + PublishedArticle يُنشأ."""
    sub = make_submission(status=SubmissionStatus.ACCEPTED, author=author)
    sub.payment_deadline = timezone.now() + timedelta(days=30)
    sub.save()

    payment_service.initiate_payment(sub, actor=author)
    sub.refresh_from_db()
    order_id = sub.payment.gateway_order_id

    payload, signature = _make_webhook(order_id, 'paid')
    payment_service.handle_webhook(payload, signature)

    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.PUBLISHED
    assert sub.payment.status == Payment.STATUS_COMPLETED
    assert PublishedArticle.objects.filter(submission=sub).exists()


@pytest.mark.django_db
def test_webhook_failure_returns_to_accepted(make_submission, author, payment_service, site_settings):
    """handle_webhook() فشل: Payment failed + submission يرجع لـ accepted_awaiting_payment."""
    sub = make_submission(status=SubmissionStatus.ACCEPTED, author=author)
    sub.payment_deadline = timezone.now() + timedelta(days=30)
    sub.save()

    payment_service.initiate_payment(sub, actor=author)
    sub.refresh_from_db()
    order_id = sub.payment.gateway_order_id

    payload, signature = _make_webhook(order_id, 'failed')
    payment_service.handle_webhook(payload, signature)

    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.ACCEPTED
    assert sub.payment.status == Payment.STATUS_FAILED

    # إشعار المؤلف بالفشل
    assert Notification.objects.filter(user=author, type='payment_required').exists()


@pytest.mark.django_db
def test_webhook_success_without_section_rolls_back_to_accepted(
    make_submission, author, payment_service, site_settings
):
    sub = make_submission(status=SubmissionStatus.ACCEPTED, author=author)
    sub.section = None
    sub.payment_deadline = timezone.now() + timedelta(days=30)
    sub.save(update_fields=['section', 'payment_deadline'])

    payment_service.initiate_payment(sub, actor=author)
    sub.refresh_from_db()
    order_id = sub.payment.gateway_order_id

    payload, signature = _make_webhook(order_id, 'paid')
    payment_service.handle_webhook(payload, signature)

    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.ACCEPTED
    assert sub.payment.status == Payment.STATUS_FAILED
    assert not PublishedArticle.objects.filter(submission=sub).exists()


# ─── Property-Based Test P8 — Idempotency ────────────────────────────────────

@pytest.mark.django_db
def test_p8_webhook_idempotency(make_submission, author, payment_service, site_settings):
    """P8: نفس webhook مرتين → لا تغيير في البيانات بعد المرة الأولى."""
    sub = make_submission(status=SubmissionStatus.ACCEPTED, author=author)
    sub.payment_deadline = timezone.now() + timedelta(days=30)
    sub.save()

    payment_service.initiate_payment(sub, actor=author)
    sub.refresh_from_db()
    order_id = sub.payment.gateway_order_id

    payload, signature = _make_webhook(order_id, 'paid')

    # المرة الأولى
    payment_service.handle_webhook(payload, signature)
    sub.refresh_from_db()
    first_status = sub.status
    first_paid_at = sub.payment.paid_at
    article_count_1 = PublishedArticle.objects.filter(submission=sub).count()

    # المرة الثانية — يجب أن تُتجاهل
    payment_service.handle_webhook(payload, signature)
    sub.refresh_from_db()

    assert sub.status == first_status
    assert sub.payment.paid_at == first_paid_at
    assert PublishedArticle.objects.filter(submission=sub).count() == article_count_1


@pytest.mark.django_db
def test_webhook_view_does_not_leak_internal_error(client, monkeypatch):
    from apps.payments import views as payment_views

    def _raise(_payload, _signature):
        raise RuntimeError("db connection secret details")

    monkeypatch.setattr(payment_views, "_payment_service", type(
        "Svc", (), {"handle_webhook": staticmethod(_raise)}
    )())

    response = client.post(
        reverse("payments:webhook"),
        data=b'{}',
        content_type="application/json",
        HTTP_X_SIGNATURE="x",
    )
    assert response.status_code == 500
    body = response.json()
    assert body["error"] == "internal server error"
