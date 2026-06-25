import pytest
import json
import hmac
import hashlib
from django.urls import reverse
from apps.submissions.statuses import SubmissionStatus
from apps.submissions.models import ArticleSubmission, ManuscriptFile
from apps.payments.models import Payment
from apps.payments.adapters import MockPaymentGatewayAdapter
from apps.notifications.models import Notification
from apps.accounts.models import User

@pytest.mark.django_db
def test_author_payment_flows(client_as, author, make_submission, site_settings, make_user):
    client = client_as(author)
    sub = make_submission(status=SubmissionStatus.ACCEPTED, author=author)

    # 3.1 بدء الدفع من حالة accepted
    url = reverse('payments:initiate', kwargs={'pk': sub.pk})
    response = client.post(url)
    assert response.status_code == 302
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.PAYMENT_PROCESSING
    order_id = sub.payment.gateway_order_id
    assert order_id is not None

    # 3.2 محاولة بدء الدفع من حالة خاطئة
    sub_wrong = make_submission(status=SubmissionStatus.UNDER_REVIEW, author=author)
    wrong_url = reverse('payments:initiate', kwargs={'pk': sub_wrong.pk})
    response = client.post(wrong_url)
    assert response.status_code == 302  # redirects with error message
    sub_wrong.refresh_from_db()
    assert sub_wrong.status == SubmissionStatus.UNDER_REVIEW

    # 3.12 محاولة بدء دفع لمقالة شخص آخر
    other_author = make_user(role=User.ROLE_AUTHOR)
    other_client = client_as(other_author)
    response = other_client.post(url)
    assert response.status_code == 403

    # 3.6 webhook بتوقيع خاطئ
    webhook_url = reverse('payments:webhook')
    payload = json.dumps({'order_id': order_id, 'status': 'paid'}).encode()
    response = client.post(webhook_url, payload, content_type='application/json', HTTP_X_SIGNATURE='wrong_sig')
    assert response.status_code == 400

    # 3.7 webhook لـ order_id غير موجود
    unknown_payload = json.dumps({'order_id': 'unknown-order', 'status': 'paid'}).encode()
    unknown_sig = hmac.HMAC(MockPaymentGatewayAdapter.SECRET_KEY.encode(), unknown_payload, hashlib.sha256).hexdigest()
    response = client.post(webhook_url, unknown_payload, content_type='application/json', HTTP_X_SIGNATURE=unknown_sig)
    assert response.status_code == 404

    # 3.4 نجاح الدفع عبر webhook
    sig = hmac.HMAC(MockPaymentGatewayAdapter.SECRET_KEY.encode(), payload, hashlib.sha256).hexdigest()
    response = client.post(webhook_url, payload, content_type='application/json', HTTP_X_SIGNATURE=sig)
    assert response.status_code == 200
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.PUBLISHED
    assert Payment.objects.get(gateway_order_id=order_id).status == Payment.STATUS_COMPLETED

    # 3.8 webhook مكرر (idempotency)
    response = client.post(webhook_url, payload, content_type='application/json', HTTP_X_SIGNATURE=sig)
    assert response.status_code == 200  # returns 200, does not crash or double publish

    # 3.3 بدء الدفع مرتين لنفس المقالة
    sub.status = SubmissionStatus.PUBLISHED
    sub.save()
    response = client.post(url)
    assert response.status_code == 302
    # check that we got the duplicate payment error in message
    
    # 3.5 فشل الدفع عبر webhook
    sub_fail = make_submission(status=SubmissionStatus.ACCEPTED, author=author)
    fail_url = reverse('payments:initiate', kwargs={'pk': sub_fail.pk})
    client.post(fail_url)
    sub_fail.refresh_from_db()
    assert sub_fail.status == SubmissionStatus.PAYMENT_PROCESSING
    fail_order_id = sub_fail.payment.gateway_order_id
    
    fail_payload = json.dumps({'order_id': fail_order_id, 'status': 'failed'}).encode()
    fail_sig = hmac.HMAC(MockPaymentGatewayAdapter.SECRET_KEY.encode(), fail_payload, hashlib.sha256).hexdigest()
    response = client.post(webhook_url, fail_payload, content_type='application/json', HTTP_X_SIGNATURE=fail_sig)
    assert response.status_code == 200
    sub_fail.refresh_from_db()
    assert sub_fail.status == SubmissionStatus.ACCEPTED
    assert Payment.objects.get(gateway_order_id=fail_order_id).status == Payment.STATUS_FAILED
    assert Notification.objects.filter(user=author, type='payment_required').exists()

    # 3.10 النشر يفشل بسبب missing section
    sub_no_section = make_submission(status=SubmissionStatus.ACCEPTED, author=author)
    sub_no_section.section = None
    sub_no_section.save()
    no_sec_url = reverse('payments:initiate', kwargs={'pk': sub_no_section.pk})
    client.post(no_sec_url)
    sub_no_section.refresh_from_db()
    no_sec_order_id = sub_no_section.payment.gateway_order_id
    
    no_sec_payload = json.dumps({'order_id': no_sec_order_id, 'status': 'paid'}).encode()
    no_sec_sig = hmac.HMAC(MockPaymentGatewayAdapter.SECRET_KEY.encode(), no_sec_payload, hashlib.sha256).hexdigest()
    response = client.post(webhook_url, no_sec_payload, content_type='application/json', HTTP_X_SIGNATURE=no_sec_sig)
    assert response.status_code == 200
    sub_no_section.refresh_from_db()
    # should rollback to ACCEPTED because publishing failed due to missing section
    assert sub_no_section.status == SubmissionStatus.ACCEPTED
    assert Payment.objects.get(gateway_order_id=no_sec_order_id).status == Payment.STATUS_FAILED

    # 3.11 النشر يفشل بسبب missing manuscript
    sub_no_pdf = make_submission(status=SubmissionStatus.ACCEPTED, author=author, with_manuscript=False)
    no_pdf_url = reverse('payments:initiate', kwargs={'pk': sub_no_pdf.pk})
    client.post(no_pdf_url)
    sub_no_pdf.refresh_from_db()
    no_pdf_order_id = sub_no_pdf.payment.gateway_order_id
    
    no_pdf_payload = json.dumps({'order_id': no_pdf_order_id, 'status': 'paid'}).encode()
    no_pdf_sig = hmac.HMAC(MockPaymentGatewayAdapter.SECRET_KEY.encode(), no_pdf_payload, hashlib.sha256).hexdigest()
    response = client.post(webhook_url, no_pdf_payload, content_type='application/json', HTTP_X_SIGNATURE=no_pdf_sig)
    assert response.status_code == 200
    sub_no_pdf.refresh_from_db()
    assert sub_no_pdf.status == SubmissionStatus.ACCEPTED
    assert Payment.objects.get(gateway_order_id=no_pdf_order_id).status == Payment.STATUS_FAILED
