"""
اختبارات SubmissionService
"""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from hypothesis import given, settings as h_settings, HealthCheck
from hypothesis import strategies as st

from apps.submissions.services import SubmissionService
from apps.submissions.statuses import SubmissionStatus
from apps.submissions.models import ArticleSubmission, ManuscriptFile, AuditLog
from apps.submissions.exceptions import (
    InvalidStateTransitionError,
    RevisionLimitExceededError,
    InvalidManuscriptFileError,
)
from apps.notifications.models import Notification


# ─── submit() ────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_submit_transitions_draft_to_initial_check(make_submission, author):
    """submit() ينقل من Draft → Under Initial Check."""
    sub = make_submission(status=SubmissionStatus.DRAFT, author=author)
    SubmissionService.submit(sub, actor=author)
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.INITIAL_CHECK


@pytest.mark.django_db
def test_submit_creates_audit_log(make_submission, author):
    """submit() يُسجّل في AuditLog."""
    sub = make_submission(status=SubmissionStatus.DRAFT, author=author)
    SubmissionService.submit(sub, actor=author)
    log = AuditLog.objects.filter(
        entity_type='ArticleSubmission', entity_id=sub.id, event='status_change'
    ).latest('created_at')
    assert log.old_value == SubmissionStatus.DRAFT
    assert log.new_value == SubmissionStatus.INITIAL_CHECK


@pytest.mark.django_db
def test_submit_notifies_admin(make_submission, author, admin_user):
    """submit() يُرسل إشعاراً للمشرف."""
    sub = make_submission(status=SubmissionStatus.DRAFT, author=author)
    SubmissionService.submit(sub, actor=author)
    assert Notification.objects.filter(
        user=admin_user, type='new_submission'
    ).exists()


# ─── admin_pass_initial_check() ──────────────────────────────────────────────

@pytest.mark.django_db
def test_admin_pass_transitions_to_under_review(make_submission, admin_user):
    """admin_pass_initial_check() ينقل إلى Under Review."""
    sub = make_submission(status=SubmissionStatus.INITIAL_CHECK)
    SubmissionService.admin_pass_initial_check(sub, actor=admin_user)
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.UNDER_REVIEW


@pytest.mark.django_db
def test_admin_pass_notifies_author(make_submission, admin_user):
    """admin_pass_initial_check() يُشعر المؤلف."""
    sub = make_submission(status=SubmissionStatus.INITIAL_CHECK)
    SubmissionService.admin_pass_initial_check(sub, actor=admin_user)
    assert Notification.objects.filter(
        user=sub.author, type='initial_check_result'
    ).exists()


# ─── admin_reject_initial_check() ────────────────────────────────────────────

@pytest.mark.django_db
def test_admin_reject_transitions_to_rejected(make_submission, admin_user):
    """admin_reject_initial_check() ينقل إلى Rejected."""
    sub = make_submission(status=SubmissionStatus.INITIAL_CHECK)
    SubmissionService.admin_reject_initial_check(sub, actor=admin_user, reason='Out of scope')
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.REJECTED
    assert sub.admin_notes == 'Out of scope'


@pytest.mark.django_db
def test_admin_reject_notifies_author(make_submission, admin_user):
    """admin_reject_initial_check() يُشعر المؤلف بسبب الرفض."""
    sub = make_submission(status=SubmissionStatus.INITIAL_CHECK)
    SubmissionService.admin_reject_initial_check(sub, actor=admin_user, reason='Poor quality')
    notif = Notification.objects.filter(user=sub.author, type='initial_check_result').first()
    assert notif is not None
    assert 'Poor quality' in notif.message


# ─── upload_revision() ───────────────────────────────────────────────────────

@pytest.mark.django_db
def test_upload_revision_wrong_status_raises(make_submission, author):
    """upload_revision() يرفع InvalidStateTransitionError إذا لم تكن الحالة revision_required."""
    sub = make_submission(status=SubmissionStatus.UNDER_REVIEW, author=author)
    pdf = SimpleUploadedFile('rev.pdf', b'%PDF content', content_type='application/pdf')
    with pytest.raises(InvalidStateTransitionError):
        SubmissionService.upload_revision(sub, file=pdf, actor=author)


@pytest.mark.django_db
def test_upload_revision_limit_exceeded_raises(make_submission, author):
    """upload_revision() يرفع RevisionLimitExceededError عند revision_count >= 2."""
    sub = make_submission(
        status=SubmissionStatus.REVISION_REQUIRED,
        author=author,
        revision_count=2,
    )
    pdf = SimpleUploadedFile('rev.pdf', b'%PDF content', content_type='application/pdf')
    with pytest.raises(RevisionLimitExceededError):
        SubmissionService.upload_revision(sub, file=pdf, actor=author)


@pytest.mark.django_db
def test_upload_revision_non_pdf_raises(make_submission, author):
    """upload_revision() يرفع InvalidManuscriptFileError إذا لم يكن PDF."""
    sub = make_submission(status=SubmissionStatus.REVISION_REQUIRED, author=author)
    docx = SimpleUploadedFile('rev.docx', b'Word content', content_type='application/msword')
    with pytest.raises(InvalidManuscriptFileError):
        SubmissionService.upload_revision(sub, file=docx, actor=author)


@pytest.mark.django_db
def test_upload_revision_success(make_submission, author):
    """upload_revision() ينجح: نسخة جديدة + is_current صحيح + حالة Under Review."""
    sub = make_submission(
        status=SubmissionStatus.REVISION_REQUIRED,
        author=author,
        revision_count=0,
    )
    pdf = SimpleUploadedFile('rev.pdf', b'%PDF revised content', content_type='application/pdf')
    SubmissionService.upload_revision(sub, file=pdf, actor=author)

    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.UNDER_REVIEW
    assert sub.revision_count == 1

    # نسخة واحدة فقط is_current=True
    current_files = ManuscriptFile.objects.filter(submission=sub, is_current=True)
    assert current_files.count() == 1


# ─── Property-Based Test P7 ──────────────────────────────────────────────────

@pytest.mark.django_db(transaction=True)
@given(revision_count=st.integers(min_value=0, max_value=1))
@h_settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
def test_p7_only_one_current_manuscript(make_submission, author, revision_count):
    """P7: ∀ submission: manuscript_files.filter(is_current=True).count() == 1"""
    sub = make_submission(
        status=SubmissionStatus.REVISION_REQUIRED,
        author=author,
        revision_count=revision_count,
    )
    pdf = SimpleUploadedFile('rev.pdf', b'%PDF content', content_type='application/pdf')
    SubmissionService.upload_revision(sub, file=pdf, actor=author)

    current_count = ManuscriptFile.objects.filter(submission=sub, is_current=True).count()
    assert current_count == 1
