import pytest
from django.urls import reverse
from apps.publishing.models import Volume, Issue, PublishedArticle
from apps.submissions.models import ArticleSubmission
from apps.submissions.statuses import SubmissionStatus

@pytest.mark.django_db
def test_admin_volumes_issues_flow(client_as, admin_user, make_submission):
    client = client_as(admin_user)
    
    # 10.1 إنشاء مجلد جديد
    url_vol = reverse('dashboard:volumes')
    response = client.post(url_vol, {'number': '1', 'year': '2024'})
    assert response.status_code == 302
    assert Volume.objects.filter(number=1, year=2024).exists()
    vol = Volume.objects.get(number=1)

    # 10.2 إنشاء مجلد مكرر
    response = client.post(url_vol, {'number': '1', 'year': '2025'})
    assert response.status_code == 302
    assert Volume.objects.filter(number=1).count() == 1  # Still 1

    # 10.3 تحديث مجلد
    url_edit_vol = reverse('dashboard:volume_update', kwargs={'pk': vol.pk})
    response = client.post(url_edit_vol, {'number': '2', 'year': '2025'})
    assert response.status_code == 302
    vol.refresh_from_db()
    assert vol.number == 2
    assert vol.year == 2025

    # 10.4 إنشاء عدد داخل مجلد
    url_issue = reverse('dashboard:issue_create')
    response = client.post(url_issue, {'volume_id': vol.pk, 'number': '1', 'quarter': '1'})
    assert response.status_code == 302
    assert Issue.objects.filter(volume=vol, number=1, quarter=1).exists()
    issue = Issue.objects.get(volume=vol, number=1)

    # 10.8 is_current يُعاد حسابه تلقائياً
    assert issue.is_current is True  # The only issue is current

    # 10.5 إنشاء عدد بـ quarter غير صالح
    response = client.post(url_issue, {'volume_id': vol.pk, 'number': '2', 'quarter': '7'})
    assert response.status_code == 302
    assert not Issue.objects.filter(volume=vol, number=2).exists()

    # 10.6 تعيين مقال لعدد
    sub = make_submission(status=SubmissionStatus.PUBLISHED)
    pub_article = PublishedArticle.objects.create(
        submission=sub,
        title=sub.title,
        abstract=sub.abstract,
        section=sub.section,
        manuscript_file=sub.manuscript_files.first(),
    )
    url_assign = reverse('dashboard:assign_article', kwargs={'pk': pub_article.pk})
    response = client.post(url_assign, {'issue_id': issue.pk})
    assert response.status_code == 302
    pub_article.refresh_from_db()
    assert pub_article.issue == issue

    # 10.7 إلغاء تعيين مقال من عدد
    response = client.post(url_assign, {'issue_id': ''})
    assert response.status_code == 302
    pub_article.refresh_from_db()
    assert pub_article.issue is None
