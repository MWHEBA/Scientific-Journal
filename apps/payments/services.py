import json
from django.db import transaction
from django.utils import timezone

from apps.payments.models import Payment
from apps.payments.adapters import PaymentGatewayAdapter, NormalizedPaymentData
from apps.payments.exceptions import PaymentNotAllowedError, DuplicatePaymentError
from apps.submissions.models import ArticleSubmission, AuditLog
from apps.submissions.statuses import SubmissionStatus
from apps.submissions.state_machine import SubmissionStateMachine
from apps.pages.models import SiteSettings
from apps.notifications.services import NotificationService


class PaymentService:

    def __init__(self, gateway: PaymentGatewayAdapter):
        self.gateway = gateway

    # ─── initiate_payment ────────────────────────────────────────────────────

    def initiate_payment(self, submission: ArticleSubmission, actor) -> str:
        """
        يُنشئ معاملة دفع ويُعيد رابط الدفع.
        يرفع PaymentNotAllowedError إذا لم تكن الحالة accepted.
        يرفع DuplicatePaymentError إذا كان الدفع مكتملاً مسبقاً.
        """
        with transaction.atomic():
            sub = ArticleSubmission.objects.select_for_update().get(pk=submission.pk)
            if sub.status != SubmissionStatus.ACCEPTED:
                raise PaymentNotAllowedError(
                    f"Payment not allowed when status is '{sub.status}'"
                )

            settings_obj = SiteSettings.get()
            payment, created = Payment.objects.get_or_create(
                submission=sub,
                defaults={
                    'amount':   settings_obj.apc_amount,
                    'currency': 'USD',
                },
            )

            if not created and payment.status == Payment.STATUS_COMPLETED:
                raise DuplicatePaymentError(
                    "Payment already completed for this submission"
                )

            payment.gateway_name = self.gateway.__class__.__name__
            payment.status = Payment.STATUS_PROCESSING
            payment.save()

            SubmissionStateMachine.transition(
                sub, SubmissionStatus.PAYMENT_PROCESSING,
                actor=actor, notes='Payment initiated',
            )
            AuditLog.objects.create(
                entity_type='Payment',
                entity_id=payment.id,
                event='payment_initiated',
                actor=actor,
            )

        try:
            result = self.gateway.create_order(
                amount=payment.amount,
                currency=payment.currency,
                metadata={'submission_id': sub.id},
            )
        except Exception:
            with transaction.atomic():
                locked_sub = ArticleSubmission.objects.select_for_update().get(pk=sub.id)
                locked_payment = Payment.objects.select_for_update().get(pk=payment.id)
                if locked_sub.status == SubmissionStatus.PAYMENT_PROCESSING:
                    SubmissionStateMachine.transition(
                        locked_sub, SubmissionStatus.ACCEPTED,
                        actor=actor, notes='Payment order creation failed',
                    )
                locked_payment.status = Payment.STATUS_FAILED
                locked_payment.save(update_fields=['status'])
            raise

        Payment.objects.filter(pk=payment.id).update(
            gateway_order_id=result['order_id'],
            status=Payment.STATUS_PROCESSING,
        )
        return result['payment_url']

    # ─── handle_webhook ──────────────────────────────────────────────────────

    def handle_webhook(self, raw_payload: bytes, signature: str) -> None:
        """
        يعالج callback من بوابة الدفع.
        Idempotent: يتجاهل الـ webhook لو الدفع مكتمل مسبقاً.
        يرفع PermissionError إذا فشل التحقق من التوقيع.
        """
        # التحقق من التوقيع أولاً
        if not self.gateway.verify_signature(raw_payload, signature):
            raise PermissionError("Invalid webhook signature")

        payload = json.loads(raw_payload)
        data    = self.gateway.normalize_webhook(payload)

        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(
                gateway_order_id=data.external_order_id
            )

            # Idempotency — تجاهل إذا مكتمل مسبقاً
            if payment.status == Payment.STATUS_COMPLETED:
                return

            payment.gateway_response = data.raw_payload

            if data.payment_status == 'success':
                self._handle_payment_success(payment, data)
            elif data.payment_status == 'failed':
                self._handle_payment_failure(payment)

    def _handle_payment_success(self, payment: Payment,
                                 data: NormalizedPaymentData) -> None:
        """معالجة نجاح الدفع — يُستدعى داخل transaction موجودة."""
        payment.status  = Payment.STATUS_COMPLETED
        payment.paid_at = data.paid_at or timezone.now()
        payment.save()

        sub = ArticleSubmission.objects.select_for_update().get(
            pk=payment.submission_id
        )
        SubmissionStateMachine.transition(
            sub, SubmissionStatus.PAID,
            notes='Payment confirmed via webhook',
        )
        AuditLog.objects.create(
            entity_type='Payment',
            entity_id=payment.id,
            event='payment_confirmed',
            old_value='processing',
            new_value='completed',
        )

        # استدعاء النشر صراحةً — لا signals
        from apps.publishing.services import PublishingService
        from apps.publishing.exceptions import MissingSectionError, MissingManuscriptError
        try:
            PublishingService.publish(sub)
        except (MissingSectionError, MissingManuscriptError) as e:
            # لا نترك الدفع مكتملًا مع فشل النشر بسبب بيانات ناقصة.
            payment.status = Payment.STATUS_FAILED
            payment.save(update_fields=['status'])
            SubmissionStateMachine.transition(
                sub, SubmissionStatus.ACCEPTED,
                notes=f'Payment confirmed but publishing blocked: {e}',
            )
            AuditLog.objects.create(
                entity_type='Payment',
                entity_id=payment.id,
                event='payment_failed',
                notes=f'Publishing blocked بسبب: {e}',
            )
            NotificationService.notify_author_payment_failed(sub)

    def _handle_payment_failure(self, payment: Payment) -> None:
        """معالجة فشل الدفع — يُعيد الحالة لـ accepted للسماح بإعادة المحاولة."""
        payment.status = Payment.STATUS_FAILED
        payment.save()

        sub = ArticleSubmission.objects.select_for_update().get(
            pk=payment.submission_id
        )
        SubmissionStateMachine.transition(
            sub, SubmissionStatus.ACCEPTED,
            notes='Payment failed — retry allowed',
        )
        AuditLog.objects.create(
            entity_type='Payment',
            entity_id=payment.id,
            event='payment_failed',
        )
        NotificationService.notify_author_payment_failed(sub)
