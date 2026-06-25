import pytest
from django.urls import reverse
from apps.payments.models import Payment
from apps.submissions.statuses import SubmissionStatus

@pytest.mark.django_db
def test_admin_payments_flow(client_as, admin_user, make_submission, payment_service, author, site_settings):
    client = client_as(admin_user)
    
    # Create payments
    sub1 = make_submission(status=SubmissionStatus.ACCEPTED, author=author)
    payment_service.initiate_payment(sub1, actor=author)
    
    sub2 = make_submission(status=SubmissionStatus.ACCEPTED, author=author)
    payment_service.initiate_payment(sub2, actor=author)
    # mock success payment
    import json
    import hmac
    import hashlib
    from apps.payments.adapters import MockPaymentGatewayAdapter
    order_id = sub2.payment.gateway_order_id
    payload = json.dumps({'order_id': order_id, 'status': 'paid'}).encode()
    signature = hmac.HMAC(
        MockPaymentGatewayAdapter.SECRET_KEY.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    payment_service.handle_webhook(payload, signature)

    # 12.1 Admin يرى كل الدفعات
    url = reverse('dashboard:admin_payments')
    response = client.get(url)
    assert response.status_code == 200
    content = response.content.decode()
    assert sub1.title in content
    assert sub2.title in content

    # 12.2 فلترة الدفعات بالحالة
    response_completed = client.get(url + '?status=' + Payment.STATUS_COMPLETED)
    assert response_completed.status_code == 200
    content_completed = response_completed.content.decode()
    assert sub2.title in content_completed
    assert sub1.title not in content_completed

    # 12.3 إحصاءات الدفعات صحيحة
    # check that completed and processing count exist in context
    ctx = response.context
    assert ctx['stats']['completed'] == 1
    assert ctx['stats']['processing'] == 1

    # 12.4 إجمالي الإيرادات
    assert ctx['stats']['total_revenue'] == 100  # Default apc_amount in site_settings in conftest is 100
