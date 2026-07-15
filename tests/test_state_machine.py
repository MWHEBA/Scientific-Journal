"""
اختبارات State Machine — P1
∀ (from, to) not in ALLOWED_TRANSITIONS → raises InvalidStateTransitionError
"""
import pytest
from hypothesis import given, settings as h_settings, HealthCheck
from hypothesis import strategies as st

from apps.submissions.state_machine import SubmissionStateMachine
from apps.submissions.statuses import SubmissionStatus
from apps.submissions.exceptions import InvalidStateTransitionError
from apps.submissions.models import AuditLog


ALL_STATUSES = [
    SubmissionStatus.DRAFT,
    SubmissionStatus.INITIAL_CHECK,
    SubmissionStatus.UNDER_REVIEW,
    SubmissionStatus.REVISION_REQUIRED,
    SubmissionStatus.ACCEPTED,
    SubmissionStatus.PAYMENT_PROCESSING,
    SubmissionStatus.PAID,
    SubmissionStatus.PUBLISHED,
    SubmissionStatus.REJECTED,
    SubmissionStatus.EXPIRED,
    SubmissionStatus.WITHDRAWN,
]

ALLOWED = SubmissionStateMachine.ALLOWED_TRANSITIONS


# ─── اختبارات الانتقالات المسموحة ────────────────────────────────────────────

@pytest.mark.parametrize("from_status, to_status", [
    (SubmissionStatus.DRAFT,              SubmissionStatus.INITIAL_CHECK),
    (SubmissionStatus.INITIAL_CHECK,      SubmissionStatus.UNDER_REVIEW),
    (SubmissionStatus.INITIAL_CHECK,      SubmissionStatus.REJECTED),
    (SubmissionStatus.UNDER_REVIEW,       SubmissionStatus.ACCEPTED),
    (SubmissionStatus.UNDER_REVIEW,       SubmissionStatus.REJECTED),
    (SubmissionStatus.UNDER_REVIEW,       SubmissionStatus.REVISION_REQUIRED),
    (SubmissionStatus.REVISION_REQUIRED,  SubmissionStatus.UNDER_REVIEW),
    (SubmissionStatus.ACCEPTED,           SubmissionStatus.PAYMENT_PROCESSING),
    (SubmissionStatus.ACCEPTED,           SubmissionStatus.EXPIRED),
    (SubmissionStatus.PAYMENT_PROCESSING, SubmissionStatus.PAID),
    (SubmissionStatus.PAYMENT_PROCESSING, SubmissionStatus.ACCEPTED),
    (SubmissionStatus.PAID,               SubmissionStatus.PUBLISHED),
    (SubmissionStatus.PUBLISHED,          SubmissionStatus.PAID),
])
@pytest.mark.django_db
def test_allowed_transition_changes_status(make_submission, from_status, to_status):
    """الانتقالات المسموحة تُغيّر الحالة وتُسجّل في AuditLog."""
    sub = make_submission(status=from_status)
    initial_audit_count = AuditLog.objects.filter(
        entity_type='ArticleSubmission', entity_id=sub.id
    ).count()

    SubmissionStateMachine.transition(sub, to_status)

    sub.refresh_from_db()
    assert sub.status == to_status

    # التحقق من تسجيل AuditLog
    new_count = AuditLog.objects.filter(
        entity_type='ArticleSubmission', entity_id=sub.id
    ).count()
    assert new_count == initial_audit_count + 1

    log = AuditLog.objects.filter(
        entity_type='ArticleSubmission', entity_id=sub.id
    ).latest('created_at')
    assert log.old_value == from_status
    assert log.new_value == to_status
    assert log.event == 'status_change'


# ─── اختبارات الانتقالات المرفوضة ────────────────────────────────────────────

@pytest.mark.parametrize("from_status, to_status", [
    (SubmissionStatus.DRAFT,     SubmissionStatus.PUBLISHED),
    (SubmissionStatus.DRAFT,     SubmissionStatus.PAID),
    (SubmissionStatus.REJECTED,  SubmissionStatus.UNDER_REVIEW),
    (SubmissionStatus.PUBLISHED, SubmissionStatus.DRAFT),
    (SubmissionStatus.EXPIRED,   SubmissionStatus.ACCEPTED),
    (SubmissionStatus.PAID,      SubmissionStatus.DRAFT),
])
@pytest.mark.django_db
def test_illegal_transition_raises_error(make_submission, from_status, to_status):
    """الانتقالات غير المسموحة ترفع InvalidStateTransitionError."""
    sub = make_submission(status=from_status)
    with pytest.raises(InvalidStateTransitionError):
        SubmissionStateMachine.transition(sub, to_status)

    # التأكد من عدم تغيير الحالة
    sub.refresh_from_db()
    assert sub.status == from_status


@pytest.mark.django_db
def test_terminal_states_have_no_transitions(make_submission):
    """الحالات النهائية لا تقبل أي انتقال."""
    for terminal in [SubmissionStatus.REJECTED, SubmissionStatus.EXPIRED, SubmissionStatus.WITHDRAWN]:
        sub = make_submission(status=terminal)
        for target in ALL_STATUSES:
            if target != terminal:
                with pytest.raises(InvalidStateTransitionError):
                    SubmissionStateMachine.transition(sub, target)


# ─── Property-Based Test P1 ──────────────────────────────────────────────────

@pytest.mark.django_db(transaction=True)
@given(
    from_status=st.sampled_from(ALL_STATUSES),
    to_status=st.sampled_from(ALL_STATUSES),
)
@h_settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
def test_p1_only_allowed_transitions_succeed(make_submission, from_status, to_status):
    """P1: ∀ (from, to) not in ALLOWED_TRANSITIONS → raises InvalidStateTransitionError"""
    sub = make_submission(status=from_status)
    allowed = ALLOWED.get(from_status, [])

    if to_status in allowed:
        # الانتقال مسموح — يجب أن ينجح
        SubmissionStateMachine.transition(sub, to_status)
        sub.refresh_from_db()
        assert sub.status == to_status
    else:
        # الانتقال غير مسموح — يجب أن يرفع
        with pytest.raises(InvalidStateTransitionError):
            SubmissionStateMachine.transition(sub, to_status)
        sub.refresh_from_db()
        assert sub.status == from_status
