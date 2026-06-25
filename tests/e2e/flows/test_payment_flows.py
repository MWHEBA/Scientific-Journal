import pytest
import json
import hmac
import hashlib
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from unittest.mock import patch
from apps.submissions.statuses import SubmissionStatus
from apps.submissions.models import ArticleSubmission, ManuscriptFile, AuditLog
from apps.publishing.models import PublishedArticle
from apps.payments.models import Payment
from apps.payments.adapters import MockPaymentGatewayAdapter
from apps.payments.views import _payment_service
from apps.notifications.models import Notification

@pytest.mark.django_db
def test_payment_success_publishes_article(client_as, author, journal_section, site_settings):
    # 22.1 نجاح الدفع → نشر فوري
    client_author = client_as(author)
    
    sub = ArticleSubmission.objects.create(
        title='E2E Payment Success Article',
        abstract='Abstract content',
        author=author,
        section=journal_section,
        corresponding_author_email=author.email,
        status=SubmissionStatus.ACCEPTED
    )
    pdf = SimpleUploadedFile('manuscript.pdf', b'%PDF-1.4 E2E Content', content_type='application/pdf')
    ManuscriptFile.objects.create(submission=sub, file=pdf, version=1, is_current=True)
    
    # Initiate payment via view
    response = client_author.post(reverse('payments:initiate', kwargs={'pk': sub.pk}))
    assert response.status_code == 302
    
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.PAYMENT_PROCESSING
    
    # Construct successful webhook
    payment = sub.payment
    payload = json.dumps({'order_id': payment.gateway_order_id, 'status': 'paid'}).encode()
    sig = hmac.HMAC(MockPaymentGatewayAdapter.SECRET_KEY.encode(), payload, hashlib.sha256).hexdigest()
    
    # Send webhook
    response_webhook = client_author.post(
        reverse('payments:webhook'),
        payload,
        content_type='application/json',
        HTTP_X_SIGNATURE=sig
    )
    assert response_webhook.status_code == 200
    
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.PUBLISHED
    assert PublishedArticle.objects.filter(submission=sub).exists()
    
    payment.refresh_from_db()
    assert payment.status == Payment.STATUS_COMPLETED
    
    # Verify AuditLogs
    assert AuditLog.objects.filter(entity_type='ArticleSubmission', entity_id=sub.pk, new_value='published').exists()
    assert AuditLog.objects.filter(entity_type='Payment', entity_id=payment.pk, event='payment_confirmed').exists()


@pytest.mark.django_db
def test_payment_failure_rolls_back_to_accepted(client_as, author, journal_section, site_settings):
    # 22.2 فشل الدفع → العودة لـ accepted
    client_author = client_as(author)
    
    sub = ArticleSubmission.objects.create(
        title='E2E Payment Failure Article',
        abstract='Abstract content',
        author=author,
        section=journal_section,
        corresponding_author_email=author.email,
        status=SubmissionStatus.ACCEPTED
    )
    pdf = SimpleUploadedFile('manuscript.pdf', b'%PDF-1.4 E2E Content', content_type='application/pdf')
    ManuscriptFile.objects.create(submission=sub, file=pdf, version=1, is_current=True)
    
    # Initiate payment
    client_author.post(reverse('payments:initiate', kwargs={'pk': sub.pk}))
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.PAYMENT_PROCESSING
    
    # Construct failed webhook
    payment = sub.payment
    payload = json.dumps({'order_id': payment.gateway_order_id, 'status': 'failed'}).encode()
    sig = hmac.HMAC(MockPaymentGatewayAdapter.SECRET_KEY.encode(), payload, hashlib.sha256).hexdigest()
    
    # Send webhook
    response_webhook = client_author.post(
        reverse('payments:webhook'),
        payload,
        content_type='application/json',
        HTTP_X_SIGNATURE=sig
    )
    assert response_webhook.status_code == 200
    
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.ACCEPTED
    
    payment.refresh_from_db()
    assert payment.status == Payment.STATUS_FAILED
    
    # Check failure notification to author
    assert Notification.objects.filter(user=author, type='payment_required').exists()


@pytest.mark.django_db
def test_payment_retry_after_failure(client_as, author, journal_section, site_settings):
    # 22.3 إعادة المحاولة بعد فشل
    client_author = client_as(author)
    
    sub = ArticleSubmission.objects.create(
        title='E2E Payment Retry Article',
        abstract='Abstract content',
        author=author,
        section=journal_section,
        corresponding_author_email=author.email,
        status=SubmissionStatus.ACCEPTED
    )
    pdf = SimpleUploadedFile('manuscript.pdf', b'%PDF-1.4 E2E Content', content_type='application/pdf')
    ManuscriptFile.objects.create(submission=sub, file=pdf, version=1, is_current=True)
    
    # First attempt (Failure)
    client_author.post(reverse('payments:initiate', kwargs={'pk': sub.pk}))
    sub.refresh_from_db()
    payment1 = sub.payment
    
    payload_fail = json.dumps({'order_id': payment1.gateway_order_id, 'status': 'failed'}).encode()
    sig_fail = hmac.HMAC(MockPaymentGatewayAdapter.SECRET_KEY.encode(), payload_fail, hashlib.sha256).hexdigest()
    client_author.post(reverse('payments:webhook'), payload_fail, content_type='application/json', HTTP_X_SIGNATURE=sig_fail)
    
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.ACCEPTED
    
    # Second attempt (Initiate again)
    response_retry = client_author.post(reverse('payments:initiate', kwargs={'pk': sub.pk}))
    assert response_retry.status_code == 302
    
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.PAYMENT_PROCESSING
    
    # Get the new or updated payment status
    payment2 = sub.payment
    assert payment2.status == Payment.STATUS_PROCESSING


@pytest.mark.django_db
def test_payment_webhook_idempotency(client_as, author, journal_section, site_settings):
    # 22.4 webhook يصل مرتين (idempotent)
    client_author = client_as(author)
    
    sub = ArticleSubmission.objects.create(
        title='E2E Payment Idempotent Article',
        abstract='Abstract content',
        author=author,
        section=journal_section,
        corresponding_author_email=author.email,
        status=SubmissionStatus.ACCEPTED
    )
    pdf = SimpleUploadedFile('manuscript.pdf', b'%PDF-1.4 E2E Content', content_type='application/pdf')
    ManuscriptFile.objects.create(submission=sub, file=pdf, version=1, is_current=True)
    
    client_author.post(reverse('payments:initiate', kwargs={'pk': sub.pk}))
    sub.refresh_from_db()
    payment = sub.payment
    
    payload = json.dumps({'order_id': payment.gateway_order_id, 'status': 'paid'}).encode()
    sig = hmac.HMAC(MockPaymentGatewayAdapter.SECRET_KEY.encode(), payload, hashlib.sha256).hexdigest()
    
    # Send webhook first time
    res1 = client_author.post(reverse('payments:webhook'), payload, content_type='application/json', HTTP_X_SIGNATURE=sig)
    assert res1.status_code == 200
    
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.PUBLISHED
    assert PublishedArticle.objects.filter(submission=sub).count() == 1
    
    # Send webhook second time
    res2 = client_author.post(reverse('payments:webhook'), payload, content_type='application/json', HTTP_X_SIGNATURE=sig)
    assert res2.status_code == 200
    
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.PUBLISHED
    assert PublishedArticle.objects.filter(submission=sub).count() == 1  # Still exactly 1


@pytest.mark.django_db
def test_payment_gateway_failure_rolls_back(client_as, author, journal_section, site_settings):
    # 22.5 gateway يفشل في create_order
    client_author = client_as(author)
    
    sub = ArticleSubmission.objects.create(
        title='E2E Payment Gateway Failure Article',
        abstract='Abstract content',
        author=author,
        section=journal_section,
        corresponding_author_email=author.email,
        status=SubmissionStatus.ACCEPTED
    )
    pdf = SimpleUploadedFile('manuscript.pdf', b'%PDF-1.4 E2E Content', content_type='application/pdf')
    ManuscriptFile.objects.create(submission=sub, file=pdf, version=1, is_current=True)
    
    # Mock gateway create_order to raise an exception
    with patch.object(MockPaymentGatewayAdapter, 'create_order', side_effect=RuntimeError("gateway down")):
        with pytest.raises(RuntimeError):
            client_author.post(reverse('payments:initiate', kwargs={'pk': sub.pk}))
        
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.ACCEPTED
    
    payment = sub.payment
    assert payment.status == Payment.STATUS_FAILED


@pytest.mark.django_db
def test_payment_webhook_missing_section_fails(client_as, author, journal_section, site_settings):
    # 22.6 webhook بدون section في المقالة
    client_author = client_as(author)
    
    sub = ArticleSubmission.objects.create(
        title='E2E Payment Missing Section Article',
        abstract='Abstract content',
        author=author,
        section=journal_section,
        corresponding_author_email=author.email,
        status=SubmissionStatus.ACCEPTED
    )
    pdf = SimpleUploadedFile('manuscript.pdf', b'%PDF-1.4 E2E Content', content_type='application/pdf')
    ManuscriptFile.objects.create(submission=sub, file=pdf, version=1, is_current=True)
    
    client_author.post(reverse('payments:initiate', kwargs={'pk': sub.pk}))
    sub.refresh_from_db()
    payment = sub.payment
    
    # Remove section programmatically to simulate a weird edge case
    sub.section = None
    sub.save()
    
    payload = json.dumps({'order_id': payment.gateway_order_id, 'status': 'paid'}).encode()
    sig = hmac.HMAC(MockPaymentGatewayAdapter.SECRET_KEY.encode(), payload, hashlib.sha256).hexdigest()
    
    response_webhook = client_author.post(
        reverse('payments:webhook'),
        payload,
        content_type='application/json',
        HTTP_X_SIGNATURE=sig
    )
    # The view handles handle_webhook. The exception is caught internally and handled gracefully, returning 200.
    assert response_webhook.status_code == 200
    
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.ACCEPTED
    
    payment.refresh_from_db()
    assert payment.status == Payment.STATUS_FAILED
    
    # Check AuditLog
    assert AuditLog.objects.filter(
        entity_type='Payment',
        entity_id=payment.id,
        event='payment_failed',
        notes__contains='Publishing blocked'
    ).exists()
