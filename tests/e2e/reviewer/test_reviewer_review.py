import pytest
from django.urls import reverse
from apps.submissions.statuses import SubmissionStatus
from apps.reviews.models import Review
from apps.accounts.models import User
from django.utils import timezone
from datetime import timedelta
from apps.pages.models import SiteSettings

@pytest.mark.django_db
def test_reviewer_review_submission_flow(client_as, reviewer, make_submission, make_review, make_user):
    client = client_as(reviewer)
    
    # 15.1 قبول مقالة + 15.9 payment_deadline يُحسب صحيحاً عند القبول + 15.10 Scores تُحفظ صحيحاً
    sub1 = make_submission(status=SubmissionStatus.UNDER_REVIEW)
    review1 = make_review(submission=sub1, reviewer=reviewer)
    url1 = reverse('reviews:submit', kwargs={'pk': review1.pk})
    data = {
        'score_originality': '4',
        'score_relevance': '5',
        'score_clarity': '3',
        'score_language': '4',
        'decision': Review.DECISION_ACCEPT,
        'comments': 'Great paper',
    }
    before = timezone.now()
    response = client.post(url1, data)
    assert response.status_code == 302
    sub1.refresh_from_db()
    review1.refresh_from_db()
    assert sub1.status == SubmissionStatus.ACCEPTED
    assert review1.is_submitted is True
    assert review1.decision == Review.DECISION_ACCEPT
    assert review1.score_originality == 4
    # payment deadline check
    deadline_days = SiteSettings.get().payment_deadline_days
    assert before + timedelta(days=deadline_days) <= sub1.payment_deadline <= timezone.now() + timedelta(days=deadline_days)

    # 15.6 إرسال مراجعة مكررة
    response_dup = client.post(url1, data)
    assert response_dup.status_code == 302 # redirects showing error message

    # 15.2 رفض مقالة
    sub2 = make_submission(status=SubmissionStatus.UNDER_REVIEW)
    review2 = make_review(submission=sub2, reviewer=reviewer)
    url2 = reverse('reviews:submit', kwargs={'pk': review2.pk})
    data['decision'] = Review.DECISION_REJECT
    response2 = client.post(url2, data)
    assert response2.status_code == 302
    sub2.refresh_from_db()
    assert sub2.status == SubmissionStatus.REJECTED

    # 15.3 طلب تعديل (أولى)
    sub3 = make_submission(status=SubmissionStatus.UNDER_REVIEW)
    review3 = make_review(submission=sub3, reviewer=reviewer)
    url3 = reverse('reviews:submit', kwargs={'pk': review3.pk})
    data['decision'] = Review.DECISION_REVISION
    response3 = client.post(url3, data)
    assert response3.status_code == 302
    sub3.refresh_from_db()
    assert sub3.status == SubmissionStatus.REVISION_REQUIRED
    assert sub3.revision_count == 0

    # 15.4 طلب تعديل (ثانية)
    # mock author uploading revision
    sub3.revision_count = 1
    sub3.status = SubmissionStatus.UNDER_REVIEW
    sub3.save()
    review3_round2 = make_review(submission=sub3, reviewer=reviewer, revision_round=2)
    url3_r2 = reverse('reviews:submit', kwargs={'pk': review3_round2.pk})
    response_r2 = client.post(url3_r2, data)
    assert response_r2.status_code == 302
    sub3.refresh_from_db()
    assert sub3.status == SubmissionStatus.REVISION_REQUIRED

    # 15.5 محاولة طلب تعديل بعد 2 دورات
    sub3.revision_count = 2
    sub3.status = SubmissionStatus.UNDER_REVIEW
    sub3.save()
    review3_round3 = make_review(submission=sub3, reviewer=reviewer, revision_round=3)
    url3_r3 = reverse('reviews:submit', kwargs={'pk': review3_round3.pk})
    response_r3 = client.post(url3_r3, data)
    assert response_r3.status_code == 302 # redirects with error message
    sub3.refresh_from_db()
    assert sub3.status == SubmissionStatus.UNDER_REVIEW # stays under review

    # 15.7 مراجع غير المعيّن يرسل مراجعة
    other_reviewer = make_user(role=User.ROLE_REVIEWER)
    other_client = client_as(other_reviewer)
    # sub3 has assigned_reviewer=reviewer, let's create a review for other_reviewer
    review_other = Review.objects.create(submission=sub3, reviewer=other_reviewer, revision_round=3)
    url_other = reverse('reviews:submit', kwargs={'pk': review_other.pk})
    response_other = other_client.post(url_other, data)
    assert response_other.status_code == 302  # redirects with error message (since sub3.assigned_reviewer is reviewer)
    review_other.refresh_from_db()
    assert not review_other.is_submitted

    # 15.8 قرار غير صالح
    sub4 = make_submission(status=SubmissionStatus.UNDER_REVIEW)
    review4 = make_review(submission=sub4, reviewer=reviewer)
    url4 = reverse('reviews:submit', kwargs={'pk': review4.pk})
    invalid_data = data.copy()
    invalid_data['decision'] = 'invalid_decision'
    response_invalid = client.post(url4, invalid_data)
    assert response_invalid.status_code == 200 # returns form with error

    # 15.11 Reviewer يحاول عرض review لمراجع آخر
    detail_url = reverse('reviews:detail', kwargs={'pk': review_other.pk})
    response_detail = client.get(detail_url)
    assert response_detail.status_code == 403
