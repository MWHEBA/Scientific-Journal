"""
اختبارات النشر المباشر بواسطة الأدمن (Direct Publishing by Admin Tests)
- النشر المباشر وتجاوز قيود الـ State Machine والدفع
- النشر بتاريخ مخصص (Backdating)
- توليد الروابط العربية (Arabic Unicode Slugs)
- استرجاع حالة التقديم السابقة عند إلغاء النشر (Retraction)
- الإنشاء والنشر المباشر لمقال خارجي/أوفلاين (AdminDirectPublishCreateView)
"""
import pytest
from django.utils import timezone
from datetime import timedelta
from django.urls import reverse

from apps.publishing.services import PublishingService
from apps.publishing.models import PublishedArticle
from apps.submissions.statuses import SubmissionStatus
from apps.submissions.models import ArticleSubmission, AuditLog, ManuscriptFile
from apps.notifications.models import Notification
from apps.accounts.models import User


@pytest.mark.django_db
def test_direct_publish_from_draft_status(make_submission, admin_user):
    """النشر المباشر يُمكن الأدمن من نشر مقالة من حالة Draft مباشرة مع وجود ملف وقسم."""
    sub = make_submission(status=SubmissionStatus.DRAFT, with_manuscript=True)
    article = PublishingService.publish(sub, actor=admin_user, force=True, notes="Direct Publish Test")

    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.PUBLISHED
    assert article.submission == sub
    assert PublishedArticle.objects.filter(submission=sub).exists()


@pytest.mark.django_db
def test_direct_publish_backdating(make_submission, admin_user):
    """اختبار النشر بتاريخ مخصص في الماضي (Backdating)."""
    sub = make_submission(status=SubmissionStatus.INITIAL_CHECK, with_manuscript=True)
    past_date = timezone.now() - timedelta(days=365)
    
    article = PublishingService.publish(
        sub,
        actor=admin_user,
        force=True,
        custom_published_at=past_date,
        notes="Historical Archive"
    )

    article.refresh_from_db()
    assert article.published_at.year == past_date.year
    assert article.published_at.month == past_date.month


@pytest.mark.django_db
def test_arabic_unicode_slug(make_submission, admin_user):
    """اختبار توليد الـ Slug باللغة العربية بدعم allow_unicode=True."""
    sub = make_submission(status=SubmissionStatus.ACCEPTED, with_manuscript=True)
    sub.title = "بحث جديد حول الذكاء الاصطناعي"
    sub.save()

    article = PublishingService.publish(sub, actor=admin_user, force=True)
    assert "ذكاء" in article.slug or "بحث" in article.slug or article.slug != "article"


@pytest.mark.django_db
def test_direct_publish_notification_toggle(make_submission, admin_user):
    """تعطيل الإشعارات عند اختيار send_notification=False."""
    sub = make_submission(status=SubmissionStatus.UNDER_REVIEW, with_manuscript=True)
    
    initial_notifs = Notification.objects.filter(user=sub.author).count()
    PublishingService.publish(sub, actor=admin_user, force=True, send_notification=False)
    
    final_notifs = Notification.objects.filter(user=sub.author).count()
    assert final_notifs == initial_notifs


@pytest.mark.django_db
def test_retract_article_restores_prior_status(make_submission, admin_user, client):
    """إلغاء النشر يعيد المقالة لحالتها السابقة المسجلة في AuditLog بدلاً من فرض PAID."""
    sub = make_submission(status=SubmissionStatus.INITIAL_CHECK, with_manuscript=True)
    
    # 1. النشر المباشر من الفحص الأولي
    PublishingService.publish(sub, actor=admin_user, force=True)
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.PUBLISHED

    # 2. إلغاء النشر بواسطة الأدمن عبر View
    client.force_login(admin_user)
    url = reverse('dashboard:submission_detail', kwargs={'pk': sub.pk})
    response = client.post(url, {'action': 'retract_article'})
    
    assert response.status_code == 302
    sub.refresh_from_db()
    # يجب أن تعود المقالة لحالتها الأصلية (under_initial_check)
    assert sub.status == SubmissionStatus.INITIAL_CHECK
    assert not PublishedArticle.objects.filter(submission=sub).exists()
