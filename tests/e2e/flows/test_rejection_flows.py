import pytest
from django.urls import reverse
from apps.submissions.statuses import SubmissionStatus
from apps.submissions.models import ArticleSubmission
from apps.reviews.models import Review
from apps.reviews.services import ReviewService
from apps.submissions.services import SubmissionService
from apps.submissions.exceptions import InvalidStateTransitionError, RevisionLimitExceededError
from django.core.files.uploadedfile import SimpleUploadedFile

@pytest.mark.django_db
def test_rejection_flows_e2e(client_as, author, admin_user, reviewer, make_submission, make_review):
    client_admin = client_as(admin_user)
    client_reviewer = client_as(reviewer)

    # 20.1 رفض في الفحص الأولي
    sub1 = make_submission(status=SubmissionStatus.INITIAL_CHECK)
    url1 = reverse('dashboard:submission_detail', kwargs={'pk': sub1.pk})
    client_admin.post(url1, {'action': 'reject', 'reason': 'Out of scope'})
    sub1.refresh_from_db()
    assert sub1.status == SubmissionStatus.REJECTED

    # 20.5 المقالة المرفوضة terminal state
    # Try transitioning rejected to UNDER_REVIEW
    with pytest.raises(InvalidStateTransitionError):
        from apps.submissions.state_machine import SubmissionStateMachine
        SubmissionStateMachine.transition(sub1, SubmissionStatus.UNDER_REVIEW)

    # 20.2 رفض من المراجع
    sub2 = make_submission(status=SubmissionStatus.UNDER_REVIEW)
    review2 = make_review(submission=sub2, reviewer=reviewer)
    url2 = reverse('reviews:submit', kwargs={'pk': review2.pk})
    client_reviewer.post(url2, {
        'score_originality': '2',
        'score_relevance': '2',
        'score_clarity': '2',
        'score_language': '2',
        'decision': Review.DECISION_REJECT,
        'comments': 'Plagiarism detected',
    })
    sub2.refresh_from_db()
    assert sub2.status == SubmissionStatus.REJECTED

    # 20.3 رفض بعد revision أولى
    sub3 = make_submission(status=SubmissionStatus.UNDER_REVIEW)
    review3 = make_review(submission=sub3, reviewer=reviewer)
    ReviewService.submit_review(
        review3, Review.DECISION_REVISION,
        {'originality': 3, 'relevance': 3, 'clarity': 3, 'language': 3},
        'Needs minor edits', actor=reviewer
    )
    sub3.refresh_from_db()
    assert sub3.status == SubmissionStatus.REVISION_REQUIRED

    # Author uploads revision
    pdf = SimpleUploadedFile('rev.pdf', b'%PDF-1.4 rev', content_type='application/pdf')
    SubmissionService.upload_revision(sub3, pdf, actor=sub3.author)
    sub3.refresh_from_db()
    assert sub3.status == SubmissionStatus.UNDER_REVIEW

    # Reviewer rejects round 2
    review3_r2 = make_review(submission=sub3, reviewer=reviewer, revision_round=2)
    url3_r2 = reverse('reviews:submit', kwargs={'pk': review3_r2.pk})
    client_reviewer.post(url3_r2, {
        'score_originality': '2',
        'score_relevance': '2',
        'score_clarity': '2',
        'score_language': '2',
        'decision': Review.DECISION_REJECT,
        'comments': 'Not fixed',
    })
    sub3.refresh_from_db()
    assert sub3.status == SubmissionStatus.REJECTED

    # 20.4 رفض بعد revision ثانية (حد أقصى)
    sub4 = make_submission(status=SubmissionStatus.UNDER_REVIEW)
    review4 = make_review(submission=sub4, reviewer=reviewer)
    ReviewService.submit_review(
        review4, Review.DECISION_REVISION,
        {'originality': 3, 'relevance': 3, 'clarity': 3, 'language': 3},
        'Edits round 1', actor=reviewer
    )
    sub4.refresh_from_db()
    
    # Upload revision 1
    SubmissionService.upload_revision(sub4, pdf, actor=sub4.author)
    sub4.refresh_from_db()

    # Round 2 review
    review4_r2 = make_review(submission=sub4, reviewer=reviewer, revision_round=2)
    ReviewService.submit_review(
        review4_r2, Review.DECISION_REVISION,
        {'originality': 3, 'relevance': 3, 'clarity': 3, 'language': 3},
        'Edits round 2', actor=reviewer
    )
    sub4.refresh_from_db()

    # Upload revision 2
    SubmissionService.upload_revision(sub4, pdf, actor=sub4.author)
    sub4.refresh_from_db()
    assert sub4.revision_count == 2

    # Round 3 review
    review4_r3 = make_review(submission=sub4, reviewer=reviewer, revision_round=3)
    # Trying to request revision round 3 fails
    with pytest.raises(RevisionLimitExceededError):
        ReviewService.submit_review(
            review4_r3, Review.DECISION_REVISION,
            {'originality': 3, 'relevance': 3, 'clarity': 3, 'language': 3},
            'Edits round 3', actor=reviewer
        )
    # Reviewer must accept or reject. Rejecting should work:
    ReviewService.submit_review(
        review4_r3, Review.DECISION_REJECT,
        {'originality': 2, 'relevance': 2, 'clarity': 2, 'language': 2},
        'Final reject', actor=reviewer
    )
    sub4.refresh_from_db()
    assert sub4.status == SubmissionStatus.REJECTED
