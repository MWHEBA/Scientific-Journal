from apps.submissions.statuses import SubmissionStatus
from apps.submissions.exceptions import InvalidStateTransitionError


class SubmissionStateMachine:
    """
    State Machine مركزية — المرجع الوحيد للانتقالات المسموح بها.
    يستخدم SubmissionStatus مباشرة، لا ArticleSubmission.STATUS_*.
    الطريقة الوحيدة لتغيير حالة التقديم هي transition().
    """

    ALLOWED_TRANSITIONS = {
        SubmissionStatus.DRAFT:              [SubmissionStatus.INITIAL_CHECK],
        SubmissionStatus.INITIAL_CHECK:      [SubmissionStatus.UNDER_REVIEW,
                                              SubmissionStatus.REJECTED,
                                              SubmissionStatus.WITHDRAWN],
        SubmissionStatus.UNDER_REVIEW:       [SubmissionStatus.ACCEPTED,
                                              SubmissionStatus.REJECTED,
                                              SubmissionStatus.REVISION_REQUIRED],
        SubmissionStatus.REVISION_REQUIRED:  [SubmissionStatus.UNDER_REVIEW],
        SubmissionStatus.ACCEPTED:           [SubmissionStatus.PAYMENT_PROCESSING,
                                              SubmissionStatus.EXPIRED],
        SubmissionStatus.PAYMENT_PROCESSING: [SubmissionStatus.PAID,
                                              SubmissionStatus.ACCEPTED],
        SubmissionStatus.PAID:               [SubmissionStatus.PUBLISHED,
                                              SubmissionStatus.ACCEPTED],
        # Terminal states — لا انتقالات منها
        SubmissionStatus.PUBLISHED:          [SubmissionStatus.PAID],
        SubmissionStatus.REJECTED:           [],
        SubmissionStatus.EXPIRED:            [],
        SubmissionStatus.WITHDRAWN:          [],
    }

    @classmethod
    def transition(cls, submission, to_status: str,
                   actor=None, notes: str = '', force: bool = False) -> None:
        """
        الطريقة الوحيدة لتغيير حالة التقديم.
        تتحقق من صحة الانتقال وتسجّل في AuditLog.
        إذا كان force=True يُسمح بالنشر المباشر من الأدمن والتجاوز الاستثنائي.
        يجب استدعاؤها داخل transaction.atomic() من الـ service.
        """
        allowed = cls.ALLOWED_TRANSITIONS.get(submission.status, [])
        if to_status not in allowed and not force:
            raise InvalidStateTransitionError(
                f"Cannot transition from '{submission.status}' to '{to_status}'"
            )

        old_status = submission.status
        submission.status = to_status
        submission.save(update_fields=['status', 'updated_at'])

        # تسجيل في AuditLog — import هنا لتجنب circular import
        from apps.submissions.models import AuditLog
        AuditLog.objects.create(
            entity_type='ArticleSubmission',
            entity_id=submission.id,
            event='status_change',
            old_value=old_status,
            new_value=to_status,
            actor=actor,
            notes=notes,
        )
