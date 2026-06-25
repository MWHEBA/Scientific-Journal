import pytest
from django.urls import reverse
from apps.pages.models import SiteSettings
from apps.accounts.models import User
from apps.submissions.statuses import SubmissionStatus
from apps.reviews.services import ReviewService
from django.utils import timezone
from datetime import timedelta

@pytest.mark.django_db
def test_admin_settings_flow(client_as, admin_user, make_submission, make_review, reviewer):
    client = client_as(admin_user)
    
    # 11.1 حفظ إعدادات APC
    url = reverse('dashboard:settings')
    data = {
        'journal_name': 'My Scientific Journal',
        'journal_desc': 'Description here',
        'apc_amount': '250.00',
        'payment_deadline_days': '14',
        'contact_email': 'contact@journal.com',
        'contact_address': 'Address 123',
    }
    response = client.post(url, data)
    assert response.status_code == 302
    settings_obj = SiteSettings.get()
    assert settings_obj.apc_amount == 250
    assert settings_obj.payment_deadline_days == 14

    # 11.2 SiteSettings Singleton
    assert SiteSettings.objects.count() == 1

    # 11.3 payment_deadline_days يؤثر على قبول
    sub = make_submission(status=SubmissionStatus.UNDER_REVIEW)
    review = make_review(submission=sub, reviewer=reviewer)
    before = timezone.now()
    ReviewService.submit_review(review, 'accept', {
        'originality': 4, 'relevance': 4, 'clarity': 4, 'language': 4
    }, '', actor=reviewer)
    after = timezone.now()
    sub.refresh_from_db()
    assert before + timedelta(days=14) <= sub.payment_deadline <= after + timedelta(days=14)

    # 11.4 محاولة وصول Reviewer للإعدادات
    reviewer_user = reviewer
    reviewer_client = client_as(reviewer_user)
    response_rev = reviewer_client.get(url)
    assert response_rev.status_code == 403
