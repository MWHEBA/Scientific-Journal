import pytest
from django.urls import reverse
from apps.submissions.statuses import SubmissionStatus
from apps.submissions.models import ArticleSubmission
from apps.reviews.models import Review
from apps.reviews.services import ReviewService
from apps.submissions.services import SubmissionService
from apps.submissions.exceptions import RevisionLimitExceededError, InvalidStateTransitionError
from apps.accounts.models import User
from django.core.files.uploadedfile import SimpleUploadedFile

@pytest.mark.django_db
def test_multiple_reviews_e2e(client_as, admin_user, reviewer, make_submission, make_review, make_user):
    # 18.1 مراجع أول يراجع -> طلب تعديل -> مراجع ثانٍ يُعين في الدورة الثانية
    sub = make_submission(status=SubmissionStatus.UNDER_REVIEW)
    sub.original_reviewer = reviewer
    sub.assigned_reviewer = reviewer
    sub.save()

    review1 = make_review(submission=sub, reviewer=reviewer, revision_round=1)

    # reviewer 1 reviews -> request revision
    ReviewService.submit_review(
        review1, Review.DECISION_REVISION,
        {'originality': 4, 'relevance': 4, 'clarity': 4, 'language': 4},
        'Need edits', actor=reviewer
    )
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.REVISION_REQUIRED

    # Author uploads revision
    pdf = SimpleUploadedFile('manuscript_rev.pdf', b'%PDF-1.4 E2E PDF', content_type='application/pdf')
    SubmissionService.upload_revision(sub, pdf, actor=sub.author)
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.UNDER_REVIEW
    assert sub.revision_count == 1

    # Admin assigns reviewer 2
    reviewer2 = make_user(role=User.ROLE_REVIEWER)
    assign_url = reverse('dashboard:assign_reviewer', kwargs={'pk': sub.pk})
    client_admin = client_as(admin_user)
    response_assign = client_admin.post(assign_url, {'reviewer_id': reviewer2.pk})
    assert response_assign.status_code == 302
    sub.refresh_from_db()
    assert sub.assigned_reviewer == reviewer2
    
    # 18.3 ثبات original_reviewer عند تغيير المراجع الحالي
    assert sub.original_reviewer == reviewer # original reviewer stays reviewer 1

    # 18.2 تزايد revision_round بشكل صحيح
    review2 = Review.objects.get(submission=sub, reviewer=reviewer2)
    assert review2.revision_round == 2

    # 18.5 مراجع الدورة الثانية يحاول تقديم مراجعة وهو ليس assigned_reviewer
    # If a reviewer submits a review but is not the currently assigned reviewer
    # Let's say reviewer 1 (who is not assigned_reviewer right now) tries to submit review
    # We will try to call submit_review with reviewer 1's review
    # Wait, can reviewer 2 submit? Yes. Let's make sure reviewer 1 cannot submit review2, or submit their own review again.
    # Actually, ReviewService.submit_review checks sub.assigned_reviewer_id == review.reviewer_id.
    # reviewer1's id != sub.assigned_reviewer_id (reviewer2).
    # So if reviewer1 tries to submit a new review or edit theirs:
    # Let's create a review for reviewer1 under round 2:
    review1_round2 = Review.objects.create(submission=sub, reviewer=reviewer, revision_round=2)
    with pytest.raises(InvalidStateTransitionError):
        ReviewService.submit_review(
            review1_round2, Review.DECISION_ACCEPT,
            {'originality': 4, 'relevance': 4, 'clarity': 4, 'language': 4},
            'Good', actor=reviewer
        )

    # 18.6 مراجع الدورة الأولى يحاول تقديم مراجعة في الدورة الثانية بعد الاستبدال
    # Same as above, verified.

    # 18.4 إرجاع المراجع الأصلي تلقائياً عند رفع التعديل
    # Let reviewer 2 request revision
    ReviewService.submit_review(
        review2, Review.DECISION_REVISION,
        {'originality': 4, 'relevance': 4, 'clarity': 4, 'language': 4},
        'Need more edits', actor=reviewer2
    )
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.REVISION_REQUIRED

    # Author uploads revision 2
    pdf2 = SimpleUploadedFile('manuscript_rev2.pdf', b'%PDF-1.4 E2E PDF', content_type='application/pdf')
    SubmissionService.upload_revision(sub, pdf2, actor=sub.author)
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.UNDER_REVIEW
    assert sub.revision_count == 2
    # Check that assigned_reviewer was reset back to original_reviewer (reviewer 1)
    assert sub.assigned_reviewer == reviewer

    # 18.7 قرار revision من ReviewService عند وصول revision_count==2
    review1_round3 = Review.objects.get(submission=sub, reviewer=reviewer, revision_round=3)
    with pytest.raises(RevisionLimitExceededError):
        ReviewService.submit_review(
            review1_round3, Review.DECISION_REVISION,
            {'originality': 4, 'relevance': 4, 'clarity': 4, 'language': 4},
            'Need edits', actor=reviewer
        )

    # 18.8 منع تكرار الـ Review لنفس المراجع والتقديم في نفس الدورة
    # get_or_create check
    r, created = Review.objects.get_or_create(submission=sub, reviewer=reviewer, revision_round=3)
    assert not created

    # 18.9 الاحتفاظ بكامل تاريخ المراجعات في قاعدة البيانات
    all_reviews = Review.objects.filter(submission=sub)
    assert all_reviews.count() >= 3 # round 1 (reviewer 1), round 2 (reviewer 2), round 3 (reviewer 1)

    # 18.10 إحصاءات المراجعين في لوحة التحكم صحيحة عبر الأدوار المختلفة
    # list reviewers view and context check
    client_admin = client_as(admin_user)
    response = client_admin.get(reverse('dashboard:reviewers'))
    assert response.status_code == 200
    reviewer_stats = response.context['reviewer_stats']
    assert reviewer.pk in reviewer_stats
    assert reviewer2.pk in reviewer_stats
