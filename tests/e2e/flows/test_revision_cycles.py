import pytest
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.submissions.statuses import SubmissionStatus
from apps.submissions.models import ArticleSubmission, ManuscriptFile, AuditLog
from apps.reviews.models import Review
from apps.notifications.models import Notification
from apps.accounts.models import User
from django.utils import timezone
from datetime import timedelta
from apps.pages.models import SiteSettings

@pytest.mark.django_db
def test_revision_cycles_full_e2e(client_as, author, admin_user, reviewer, make_submission, make_review, make_user):
    client_author = client_as(author)
    client_admin = client_as(admin_user)
    client_reviewer = client_as(reviewer)
    
    # Setup submission
    sub = make_submission(status=SubmissionStatus.UNDER_REVIEW, author=author)
    sub.original_reviewer = reviewer
    sub.assigned_reviewer = reviewer
    sub.save()

    review1 = make_review(submission=sub, reviewer=reviewer, revision_round=1)
    
    # 21.1 الدورة الأولى: طلب تعديلات (Revision Required)
    url_review1 = reverse('reviews:submit', kwargs={'pk': review1.pk})
    response_rev1 = client_reviewer.post(url_review1, {
        'score_originality': '3',
        'score_relevance': '3',
        'score_clarity': '3',
        'score_language': '3',
        'decision': Review.DECISION_REVISION,
        'comments': 'Please fix the intro and section 2.',
    })
    assert response_rev1.status_code == 302
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.REVISION_REQUIRED
    
    # Assert notifications
    assert Notification.objects.filter(user=author, type='review_decision', message__contains='Please fix').exists()
    assert Notification.objects.filter(user=admin_user, type='review_completed').exists()

    # 21.2 المؤلف يرفع التعديل الأول (Revision 1)
    url_revise = reverse('submissions:revise', kwargs={'pk': sub.pk})
    pdf1 = SimpleUploadedFile('manuscript_v2.pdf', b'%PDF-1.4 revision 1', content_type='application/pdf')
    response_upload1 = client_author.post(url_revise, {'manuscript': pdf1})
    assert response_upload1.status_code == 302
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.UNDER_REVIEW
    assert sub.revision_count == 1
    # Check manuscript versioning
    all_files = sub.manuscript_files.order_by('version')
    assert all_files.count() == 2
    assert all_files.first().is_current is False
    assert all_files.last().is_current is True
    assert all_files.last().version == 2

    # 21.3 الدورة الثانية: طلب تعديلات إضافية
    # Create reviewer 2 to test assigned_reviewer handover
    reviewer2 = make_user(role=User.ROLE_REVIEWER)
    # Admin assigns reviewer 2
    client_admin.post(reverse('dashboard:assign_reviewer', kwargs={'pk': sub.pk}), {'reviewer_id': reviewer2.pk})
    sub.refresh_from_db()
    assert sub.assigned_reviewer == reviewer2
    
    review2 = Review.objects.get(submission=sub, reviewer=reviewer2, revision_round=2)
    client_reviewer2 = client_as(reviewer2)
    url_review2 = reverse('reviews:submit', kwargs={'pk': review2.pk})
    
    response_rev2 = client_reviewer2.post(url_review2, {
        'score_originality': '3',
        'score_relevance': '4',
        'score_clarity': '4',
        'score_language': '3',
        'decision': Review.DECISION_REVISION,
        'comments': 'Intro is better, but section 2 is still weak.',
    })
    assert response_rev2.status_code == 302
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.REVISION_REQUIRED

    # 21.4 المؤلف يرفع التعديل الثاني (Revision 2)
    pdf2 = SimpleUploadedFile('manuscript_v3.pdf', b'%PDF-1.4 revision 2', content_type='application/pdf')
    response_upload2 = client_author.post(url_revise, {'manuscript': pdf2})
    assert response_upload2.status_code == 302
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.UNDER_REVIEW
    assert sub.revision_count == 2
    # Verify version 3 is active
    assert sub.manuscript_files.filter(is_current=True).first().version == 3
    # Check that assigned_reviewer was reset back to original_reviewer (reviewer 1)
    assert sub.assigned_reviewer == reviewer

    # 21.5 منع طلب تعديل ثالث (الدورة الثالثة)
    review3 = Review.objects.get(submission=sub, reviewer=reviewer, revision_round=3)
    url_review3 = reverse('reviews:submit', kwargs={'pk': review3.pk})
    response_rev3 = client_reviewer.post(url_review3, {
        'score_originality': '3',
        'score_relevance': '3',
        'score_clarity': '3',
        'score_language': '3',
        'decision': Review.DECISION_REVISION,
        'comments': 'Try one more time.',
    })
    assert response_rev3.status_code == 302  # redirects with error message
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.UNDER_REVIEW  # stays under review because limit exceeded

    # 21.6 قرار نهائي بالقبول بعد دورتين
    before_deadline = timezone.now()
    response_accept = client_reviewer.post(url_review3, {
        'score_originality': '5',
        'score_relevance': '5',
        'score_clarity': '4',
        'score_language': '4',
        'decision': Review.DECISION_ACCEPT,
        'comments': 'Looks good now. Accept.',
    })
    assert response_accept.status_code == 302
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.ACCEPTED
    
    # Assert deadline calculated correctly
    deadline_days = SiteSettings.get().payment_deadline_days
    assert before_deadline + timedelta(days=deadline_days) <= sub.payment_deadline <= timezone.now() + timedelta(days=deadline_days)
    
    # Assert notification generated
    assert Notification.objects.filter(user=author, type='payment_required').exists()

    # 21.7 تتبع السجل التاريخي الكامل للمراجعات
    all_reviews = Review.objects.filter(submission=sub).order_by('revision_round')
    assert all_reviews.count() == 4
    # Round 1: reviewer 1 (round 1)
    assert all_reviews[0].reviewer == reviewer
    assert all_reviews[0].revision_round == 1
    assert all_reviews[0].decision == Review.DECISION_REVISION
    
    # Round 2: reviewer 1 (round 2 - generated auto, not submitted)
    assert all_reviews[1].reviewer == reviewer
    assert all_reviews[1].revision_round == 2
    assert all_reviews[1].is_submitted is False
    
    # Round 3: reviewer 2 (round 2 - assigned by admin, submitted)
    assert all_reviews[2].reviewer == reviewer2
    assert all_reviews[2].revision_round == 2
    assert all_reviews[2].decision == Review.DECISION_REVISION
    
    # Round 4: reviewer 1 (round 3 - auto reassigned, accepted)
    assert all_reviews[3].reviewer == reviewer
    assert all_reviews[3].revision_round == 3
    assert all_reviews[3].decision == Review.DECISION_ACCEPT
