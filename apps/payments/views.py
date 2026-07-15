import json
from django.views.generic import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.urls import reverse

from apps.payments.models import Payment
from apps.payments.services import PaymentService
from apps.payments.adapters import MockPaymentGatewayAdapter
from apps.payments.exceptions import PaymentNotAllowedError, DuplicatePaymentError
from apps.submissions.models import ArticleSubmission
from apps.pages.models import SiteSettings

# Adapter افتراضي للتطوير — يُستبدل بالمزوّد الحقيقي لاحقاً
_default_gateway = MockPaymentGatewayAdapter()
_payment_service = PaymentService(gateway=_default_gateway)

def _t(ar_text, en_text):
    from django.utils import translation
    return en_text if translation.get_language() == 'en' else ar_text


class PaymentInitiateView(LoginRequiredMixin, View):
    """بدء عملية الدفع — object-level permission (submission.author == request.user)."""

    def get(self, request, pk):
        submission = get_object_or_404(ArticleSubmission, pk=pk)
        if submission.author != request.user:
            raise PermissionDenied

        settings = SiteSettings.get()
        try:
            payment = submission.payment
        except Payment.DoesNotExist:
            payment = None

        return render(request, 'payments/initiate.html', {
            'submission': submission,
            'payment':    payment,
            'apc_amount': settings.apc_amount,
        })

    def post(self, request, pk):
        submission = get_object_or_404(ArticleSubmission, pk=pk)
        if submission.author != request.user:
            raise PermissionDenied

        try:
            payment_url = _payment_service.initiate_payment(
                submission=submission,
                actor=request.user,
            )
            return redirect(payment_url)
        except PaymentNotAllowedError as e:
            messages.error(request, _t(f'لا يمكن بدء الدفع: {e}', f'Cannot initiate payment: {e}'))
        except DuplicatePaymentError:
            messages.error(request, _t('تم إتمام الدفع مسبقاً لهذا المقالة.', 'Payment has already been completed for this article.'))

        return redirect(reverse('dashboard:author'))


@method_decorator(csrf_exempt, name='dispatch')
class PaymentWebhookView(View):
    """استقبال callback من بوابة الدفع — لا يتطلب تسجيل دخول."""

    def post(self, request):
        signature = request.headers.get('X-Signature', '')
        raw_body  = request.body  # bytes — قبل أي parsing

        try:
            _payment_service.handle_webhook(raw_body, signature)
            return JsonResponse({'status': 'ok'})
        except PermissionError:
            return JsonResponse({'error': 'invalid signature'}, status=400)
        except Payment.DoesNotExist:
            return JsonResponse({'error': 'unknown order'}, status=404)
        except Exception:
            return JsonResponse({'error': 'internal server error'}, status=500)


class MockPayView(View):
    """صفحة دفع وهمية للتطوير — تُحاكي بوابة الدفع."""

    def get(self, request, order_id):
        return render(request, 'payments/mock_pay.html', {'order_id': order_id})

    def post(self, request, order_id):
        """يُرسل webhook وهمي لمحاكاة نجاح/فشل الدفع."""
        import hmac
        import hashlib
        action = request.POST.get('action', 'success')
        payload = json.dumps({
            'order_id': order_id,
            'status':   'paid' if action == 'success' else 'failed',
        }).encode()
        signature = hmac.HMAC(
            MockPaymentGatewayAdapter.SECRET_KEY.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()

        # استدعاء الـ webhook handler مباشرة
        try:
            _payment_service.handle_webhook(payload, signature)
            messages.success(request, _t('تمت عملية الدفع بنجاح!', 'Payment completed successfully!') if action == 'success'
                             else _t('فشلت عملية الدفع.', 'Payment failed.'))
        except Exception as e:
            messages.error(request, _t(f'خطأ: {e}', f'Error: {e}'))

        return redirect(reverse('dashboard:author'))
