"""
اختبارات PublishingService — P2, P9
"""
import pytest
from hypothesis import given, settings as h_settings, HealthCheck
from hypothesis import strategies as st

from apps.publishing.services import PublishingService
from apps.publishing.models import PublishedArticle
from apps.publishing.exceptions import (
    AlreadyPublishedError,
    MissingManuscriptError,
    PublishNotAllowedError,
)
from apps.submissions.statuses import SubmissionStatus
from apps.submissions.models import AuditLog
from apps.notifications.models import Notification
from apps.payments.models import Payment


# ─── Guards ──────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_publish_guard1_wrong_status_raises(make_submission):
    """Guard 1: status != paid → PublishNotAllowedError."""
    for status in [
        SubmissionStatus.DRAFT,
        SubmissionStatus.UNDER_REVIEW,
        SubmissionStatus.ACCEPTED,
        SubmissionStatus.REJECTED,
    ]:
        sub = make_submission(status=status)
        with pytest.raises(PublishNotAllowedError):
            PublishingService.publish(sub)


@pytest.mark.django_db
def test_publish_guard2_already_published_raises(make_paid_submission):
    """Guard 2: PublishedArticle موجود → AlreadyPublishedError."""
    sub = make_paid_submission()
    assert sub.status == SubmissionStatus.PUBLISHED

    # محاولة نشر مرة ثانية
    sub.status = SubmissionStatus.PAID
    sub.save()
    with pytest.raises(AlreadyPublishedError):
        PublishingService.publish(sub)


@pytest.mark.django_db
def test_publish_guard3_no_manuscript_raises(make_submission):
    """Guard 3: لا manuscript حالي → MissingManuscriptError."""
    sub = make_submission(status=SubmissionStatus.PAID, with_manuscript=False)
    with pytest.raises(MissingManuscriptError):
        PublishingService.publish(sub)


# ─── النجاح ──────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_publish_success_creates_article(make_submission):
    """publish() ينجح: PublishedArticle يُنشأ + status = published."""
    sub = make_submission(status=SubmissionStatus.PAID)
    article = PublishingService.publish(sub)

    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.PUBLISHED
    assert article.title == sub.title
    assert article.abstract == sub.abstract
    assert article.submission == sub


@pytest.mark.django_db
def test_publish_success_creates_audit_log(make_submission):
    """publish() يُسجّل في AuditLog."""
    sub = make_submission(status=SubmissionStatus.PAID)
    article = PublishingService.publish(sub)

    log = AuditLog.objects.filter(
        entity_type='PublishedArticle', entity_id=article.id, event='article_published'
    ).first()
    assert log is not None


@pytest.mark.django_db
def test_publish_success_notifies_author(make_submission):
    """publish() يُشعر المؤلف."""
    sub = make_submission(status=SubmissionStatus.PAID)
    PublishingService.publish(sub)

    assert Notification.objects.filter(
        user=sub.author, type='article_published'
    ).exists()


@pytest.mark.django_db
def test_publish_pdf_file_is_reference_not_copy(make_submission):
    """pdf_file هو reference للـ ManuscriptFile — لا نسخ."""
    sub = make_submission(status=SubmissionStatus.PAID)
    article = PublishingService.publish(sub)

    manuscript = sub.manuscript_files.filter(is_current=True).first()
    assert article.manuscript_file == manuscript
    assert article.pdf_file == manuscript.file


# ─── Property-Based Test P2 ──────────────────────────────────────────────────

@pytest.mark.django_db
def test_p2_published_article_has_completed_payment(make_paid_submission):
    """P2: ∀ published_article: payment.status == 'completed'"""
    sub = make_paid_submission()
    assert sub.status == SubmissionStatus.PUBLISHED

    article = PublishedArticle.objects.get(submission=sub)
    assert article.submission.payment.status == Payment.STATUS_COMPLETED


# ─── Property-Based Test P9 ──────────────────────────────────────────────────

@pytest.mark.django_db
def test_p9_no_duplicate_published_article(make_submission):
    """P9: ∀ submission: PublishedArticle.objects.filter(submission=sub).count() <= 1"""
    sub = make_submission(status=SubmissionStatus.PAID)
    PublishingService.publish(sub)

    count = PublishedArticle.objects.filter(submission=sub).count()
    assert count == 1

    # محاولة نشر مرة ثانية
    sub.status = SubmissionStatus.PAID
    sub.save()
    with pytest.raises(AlreadyPublishedError):
        PublishingService.publish(sub)

    # لا يزال 1
    assert PublishedArticle.objects.filter(submission=sub).count() == 1
