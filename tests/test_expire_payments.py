"""
اختبارات expire_payments command و SiteSettings — P5, P6
"""
import pytest
from datetime import timedelta
from django.utils import timezone
from django.core.management import call_command
from hypothesis import given, settings as h_settings, HealthCheck
from hypothesis import strategies as st

from apps.submissions.statuses import SubmissionStatus
from apps.submissions.models import ArticleSubmission
from apps.pages.models import SiteSettings
from apps.notifications.models import Notification


# ─── expire_payments command ─────────────────────────────────────────────────

@pytest.mark.django_db
def test_expire_payments_transitions_expired_submissions(make_submission):
    """expire_payments ينقل التقديمات المنتهية المهلة إلى expired."""
    sub = make_submission(status=SubmissionStatus.ACCEPTED)
    sub.payment_deadline = timezone.now() - timedelta(days=1)  # منتهية
    sub.save()

    call_command('expire_payments')

    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.EXPIRED


@pytest.mark.django_db
def test_expire_payments_notifies_author(make_submission):
    """expire_payments يُشعر المؤلف عند انتهاء المهلة."""
    sub = make_submission(status=SubmissionStatus.ACCEPTED)
    sub.payment_deadline = timezone.now() - timedelta(days=1)
    sub.save()

    call_command('expire_payments')

    assert Notification.objects.filter(
        user=sub.author, type='payment_required'
    ).exists()


@pytest.mark.django_db
def test_expire_payments_skips_non_expired(make_submission):
    """expire_payments لا يُغيّر التقديمات التي لم تنته مهلتها."""
    sub = make_submission(status=SubmissionStatus.ACCEPTED)
    sub.payment_deadline = timezone.now() + timedelta(days=10)  # لم تنته
    sub.save()

    call_command('expire_payments')

    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.ACCEPTED


@pytest.mark.django_db
def test_expire_payments_race_condition_guard(make_submission):
    """race condition guard: تقديم تغيّرت حالته بين الاستعلام والـ lock يُتجاهل."""
    sub = make_submission(status=SubmissionStatus.ACCEPTED)
    sub.payment_deadline = timezone.now() - timedelta(days=1)
    sub.save()

    # نغيّر الحالة قبل تشغيل الأمر (محاكاة race condition)
    sub.status = SubmissionStatus.PAYMENT_PROCESSING
    sub.save(update_fields=['status'])

    call_command('expire_payments')

    sub.refresh_from_db()
    # يجب أن تبقى payment_processing — لم تُعالَج
    assert sub.status == SubmissionStatus.PAYMENT_PROCESSING


# ─── Property-Based Test P5 ──────────────────────────────────────────────────

@pytest.mark.django_db(transaction=True)
@given(deadline_days=st.integers(min_value=1, max_value=90))
@h_settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
def test_p5_payment_deadline_calculated_from_settings(
    make_submission, make_review, make_user, deadline_days
):
    """P5: ∀ accepted submission: payment_deadline ≈ accepted_at + payment_deadline_days"""
    from apps.accounts.models import User
    from apps.reviews.services import ReviewService
    from apps.reviews.models import Review

    settings = SiteSettings.get()
    settings.payment_deadline_days = deadline_days
    settings.save()

    reviewer = make_user(role=User.ROLE_REVIEWER)
    sub = make_submission(status=SubmissionStatus.UNDER_REVIEW)
    review = make_review(
        submission=sub,
        reviewer=reviewer,
        revision_round=1,
    )

    before = timezone.now()
    ReviewService.submit_review(review, 'accept', {
        'originality': 4, 'relevance': 4, 'clarity': 4, 'language': 4
    }, '', actor=reviewer)
    after = timezone.now()

    sub.refresh_from_db()
    expected_min = before + timedelta(days=deadline_days)
    expected_max = after  + timedelta(days=deadline_days)
    assert expected_min <= sub.payment_deadline <= expected_max


# ─── Property-Based Test P6 — SiteSettings Singleton ────────────────────────

@pytest.mark.django_db(transaction=True)
@given(calls=st.integers(min_value=1, max_value=20))
@h_settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
def test_p6_site_settings_singleton(calls):
    """P6: SiteSettings.objects.count() == 1 دائماً بعد أي عدد من استدعاءات SiteSettings.get()"""
    for _ in range(calls):
        SiteSettings.get()

    assert SiteSettings.objects.count() == 1


@pytest.mark.django_db
def test_site_settings_save_enforces_singleton():
    """SiteSettings.save() يضمن وجود سجل واحد فقط."""
    s1 = SiteSettings.get()
    s1.journal_name = 'Journal A'
    s1.save()

    s2 = SiteSettings.get()
    s2.journal_name = 'Journal B'
    s2.save()

    assert SiteSettings.objects.count() == 1
    assert SiteSettings.objects.first().journal_name == 'Journal B'
