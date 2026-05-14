from django.views.generic import ListView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator

from apps.notifications.models import Notification


class NotificationListView(LoginRequiredMixin, ListView):
    """قائمة إشعارات المستخدم الحالي."""
    model               = Notification
    template_name       = 'notifications/list.html'
    context_object_name = 'notifications'
    paginate_by         = 20

    def get_queryset(self):
        return Notification.objects.filter(
            user=self.request.user
        ).order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['unread_count'] = Notification.objects.filter(
            user=self.request.user, is_read=False
        ).count()
        return ctx


class MarkNotificationReadView(LoginRequiredMixin, View):
    """تحديث حالة إشعار واحد إلى مقروء."""

    def post(self, request, pk):
        notification = get_object_or_404(
            Notification, pk=pk, user=request.user
        )
        notification.is_read = True
        notification.save(update_fields=['is_read'])
        return JsonResponse({'status': 'ok'})


class MarkAllReadView(LoginRequiredMixin, View):
    """تحديث جميع إشعارات المستخدم إلى مقروءة."""

    def post(self, request):
        Notification.objects.filter(
            user=request.user, is_read=False
        ).update(is_read=True)
        return JsonResponse({'status': 'ok', 'message': 'تم تحديد جميع الإشعارات كمقروءة.'})
