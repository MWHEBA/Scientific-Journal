from django.urls import path
from apps.notifications.views import (
    NotificationListView,
    MarkNotificationReadView,
    MarkAllReadView,
)

app_name = 'notifications'

urlpatterns = [
    path('',                  NotificationListView.as_view(),    name='list'),
    path('<int:pk>/read/',    MarkNotificationReadView.as_view(), name='mark_read'),
    path('mark-all-read/',    MarkAllReadView.as_view(),          name='mark_all_read'),
]
