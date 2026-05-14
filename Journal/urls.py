from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("submissions/", include("apps.submissions.urls")),
    path("reviews/", include("apps.reviews.urls")),
    path("payments/", include("apps.payments.urls")),
    path("dashboard/", include("apps.dashboard.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("", include("apps.pages.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
