"""
اختبارات ReviewService
"""
import pytest
from datetime import timedelta
from django.utils import timezone
from hypothesis import given, settings as h_settings, HealthCheck
from hypothesis import strategies as st

from apps.reviews.services import ReviewService
from apps.reviews.models import Review
from apps.submissions.statuses import SubmissionStatus
from apps.submissions.exceptions import InvalidStateTransitionError, RevisionLimitExceededError
from apps.notifications.models import Notification
from apps.pages.models import SiteSettings


SCORES = {
    'originality': 4,
    'relevance':   4,
    'clarity':     4,
    'language':    4,
}


# ─── submit_review() — القرارات الثلاثة ──────────────────────────────────────

@pytest.mark.django_db
def test_submit_review_accept(make_submission, make_review, reviewer, site_settings):
    """قرار accept ينقل التقديم إلى accepted_awaiting_payment."""
    sub    = make_submission(status=SubmissionStatus.UNDER_REVIEW)
    review = make_review(sub, reviewer=reviewer)

    ReviewService.submit_review(review, 'accept', SCORES, 'Good paper', actor=reviewer)

    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.ACCEPTED
    assert sub.payment_deadline is not None
    assert review.is_submitted is True
    assert review.decision == 'accept'


@pytest.mark.django_db
def test_submit_review_reject(make_submission, make_review, reviewer):
    """قرار reject ينقل التقديم إلى rejected."""
    sub    = make_submission(status=SubmissionStatus.UNDER_REVIEW)
    review = make_review(sub, reviewer=reviewer)

    ReviewService.submit_review(review, 'reject', SCORES, 'Not suitable', actor=reviewer)

    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.REJECTED


@pytest.mark.django_db
def test_submit_review_revision(make_submission, make_review, reviewer):
    """قرار revision ينقل التقديم إلى revision_required."""
    sub    = make_submission(status=SubmissionStatus.UNDER_REVIEW)
    review = make_review(sub, reviewer=reviewer)

    ReviewService.submit_review(review, 'revision', SCORES, 'Needs work', actor=reviewer)

    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.REVISION_REQUIRED


# ─── منع التكرار ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_submit_review_already_submitted_raises(make_submission, make_review, reviewer):
    """مراجعة مُرسَلة مسبقاً ترفع InvalidStateTransitionError."""
    sub    = make_submission(status=SubmissionStatus.UNDER_REVIEW)
    review = make_review(sub, reviewer=reviewer, is_submitted=True, decision='accept')

    with pytest.raises(InvalidStateTransitionError):
        ReviewService.submit_review(review, 'accept', SCORES, '', actor=reviewer)


@pytest.mark.django_db
def test_submit_review_rejects_old_reviewer_after_reassignment(
    make_submission, make_review, make_user
):
    from apps.accounts.models import User

    reviewer_old = make_user(role=User.ROLE_REVIEWER)
    reviewer_new = make_user(role=User.ROLE_REVIEWER)
    sub = make_submission(status=SubmissionStatus.UNDER_REVIEW)
    sub.assigned_reviewer = reviewer_new
    sub.save(update_fields=['assigned_reviewer'])

    old_review = make_review(sub, reviewer=reviewer_old)
    with pytest.raises(InvalidStateTransitionError):
        ReviewService.submit_review(old_review, 'accept', SCORES, '', actor=reviewer_old)

# ─── حساب payment_deadline ───────────────────────────────────────────────────

@pytest.mark.django_db
def test_payment_deadline_calculated_correctly(make_submission, make_review, reviewer, site_settings):
    """payment_deadline = now + payment_deadline_days."""
    site_settings.payment_deadline_days = 30
    site_settings.save()

    sub    = make_submission(status=SubmissionStatus.UNDER_REVIEW)
    review = make_review(sub, reviewer=reviewer)

    before = timezone.now()
    ReviewService.submit_review(review, 'accept', SCORES, '', actor=reviewer)
    after  = timezone.now()

    sub.refresh_from_db()
    expected_min = before + timedelta(days=30)
    expected_max = after  + timedelta(days=30)
    assert expected_min <= sub.payment_deadline <= expected_max


# ─── إشعارات ─────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_submit_review_notifies_author_and_admin(make_submission, make_review, reviewer, admin_user):
    """submit_review() يُشعر المؤلف والمشرف."""
    sub    = make_submission(status=SubmissionStatus.UNDER_REVIEW)
    review = make_review(sub, reviewer=reviewer)

    ReviewService.submit_review(review, 'reject', SCORES, 'Not suitable', actor=reviewer)

    assert Notification.objects.filter(user=sub.author).exists()
    assert Notification.objects.filter(user=admin_user, type='review_completed').exists()


# ─── Property-Based Test P3 ──────────────────────────────────────────────────

@pytest.mark.django_db(transaction=True)
@given(revision_count=st.integers(min_value=2, max_value=5))
@h_settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
def test_p3_revision_limit_enforced(make_submission, make_review, reviewer, revision_count):
    """P3: revision_count >= 2 مع قرار revision → RevisionLimitExceededError"""
    sub = make_submission(
        status=SubmissionStatus.UNDER_REVIEW,
        revision_count=revision_count,
    )
    review = make_review(sub, reviewer=reviewer)

    with pytest.raises(RevisionLimitExceededError):
        ReviewService.submit_review(review, 'revision', SCORES, '', actor=reviewer)


# ─── Property-Based Test P4 ──────────────────────────────────────────────────

@pytest.mark.django_db
def test_p4_original_reviewer_reassigned_on_revision(make_submission, make_review, make_user):
    """P4: عند رفع revision، assigned_reviewer == original_reviewer."""
    from apps.accounts.models import User
    from apps.submissions.services import SubmissionService
    from django.core.files.uploadedfile import SimpleUploadedFile

    author   = make_user(role=User.ROLE_AUTHOR)
    reviewer_a = make_user(role=User.ROLE_REVIEWER)

    sub = make_submission(status=SubmissionStatus.UNDER_REVIEW, author=author)
    sub.original_reviewer = reviewer_a
    sub.assigned_reviewer = reviewer_a
    sub.save()

    review = make_review(sub, reviewer=reviewer_a)
    ReviewService.submit_review(review, 'revision', SCORES, 'Needs work', actor=reviewer_a)

    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.REVISION_REQUIRED

    # رفع revision
    pdf = SimpleUploadedFile('rev.pdf', b'%PDF revised', content_type='application/pdf')
    SubmissionService.upload_revision(sub, file=pdf, actor=author)

    sub.refresh_from_db()
    assert sub.assigned_reviewer == reviewer_a
    assert sub.assigned_reviewer == sub.original_reviewer
