from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect
from django.http import Http404

def toggle_language_view(request):
    if not settings.DEBUG:
        raise Http404("Not allowed in production")
    current_lang = request.session.get('site_language') or settings.SITE_LANGUAGE
    new_lang = 'en' if current_lang == 'ar' else 'ar'
    request.session['site_language'] = new_lang
    
    response = redirect(request.GET.get('next', '/'))
    response.set_cookie('site_language', new_lang)
    return response

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("submissions/", include("apps.submissions.urls")),
    path("reviews/", include("apps.reviews.urls")),
    path("payments/", include("apps.payments.urls")),
    path("dashboard/", include("apps.dashboard.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("toggle-language/", toggle_language_view, name="toggle_language"),
    path("", include("apps.pages.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

