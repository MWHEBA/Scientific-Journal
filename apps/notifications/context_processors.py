def unread_notifications_count(request):
    """يُعيد عدد الإشعارات غير المقروءة للمستخدم الحالي."""
    if request.user.is_authenticated:
        from apps.notifications.models import Notification
        unread_qs = Notification.objects.filter(user=request.user, is_read=False)
        latest_notifications = Notification.objects.filter(user=request.user).order_by('-created_at')[:5]
        return {
            'unread_notifications_count': unread_qs.count(),
            'latest_notifications': latest_notifications,
        }
    return {
        'unread_notifications_count': 0,
        'latest_notifications': [],
    }
