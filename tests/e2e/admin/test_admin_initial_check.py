import pytest
from django.urls import reverse
from apps.submissions.statuses import SubmissionStatus
from apps.submissions.models import ArticleSubmission, JournalSection
from apps.notifications.models import Notification

@pytest.mark.django_db
def test_admin_initial_check_flow(client_as, admin_user, make_submission, journal_section, make_user):
    client = client_as(admin_user)
    
    # Create submission in INITIAL_CHECK without section
    sub = make_submission(status=SubmissionStatus.INITIAL_CHECK, section=None)
    url = reverse('dashboard:submission_detail', kwargs={'pk': sub.pk})

    # 7.2 قبول بدون قسم محدد
    response = client.post(url, {'action': 'pass'})
    assert response.status_code == 302
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.INITIAL_CHECK  # stays initial_check

    # 7.3 تحديد قسم للتقديم
    response = client.post(url, {'action': 'set_section', 'section_id': journal_section.pk})
    assert response.status_code == 302
    sub.refresh_from_db()
    assert sub.section == journal_section

    # 7.1 قبول تقديم للمراجعة (pass)
    response = client.post(url, {'action': 'pass'})
    assert response.status_code == 302
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.UNDER_REVIEW
    assert Notification.objects.filter(user=sub.author, type='initial_check_result').exists()

    # 7.6 محاولة pass لـ under_review
    response = client.post(url, {'action': 'pass'})
    assert response.status_code == 302
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.UNDER_REVIEW

    # Reject flow
    sub_to_reject = make_submission(status=SubmissionStatus.INITIAL_CHECK)
    url_reject = reverse('dashboard:submission_detail', kwargs={'pk': sub_to_reject.pk})

    # 7.5 رفض بدون سبب
    response = client.post(url_reject, {'action': 'reject', 'reason': ''})
    assert response.status_code == 302
    sub_to_reject.refresh_from_db()
    assert sub_to_reject.status == SubmissionStatus.INITIAL_CHECK

    # 7.4 رفض تقديم مع سبب
    response = client.post(url_reject, {'action': 'reject', 'reason': 'Poor quality'})
    assert response.status_code == 302
    sub_to_reject.refresh_from_db()
    assert sub_to_reject.status == SubmissionStatus.REJECTED
    assert sub_to_reject.admin_notes == 'Poor quality'

    # 7.7 Admin يرى كل التقديمات
    author1 = make_user(username='author1')
    author2 = make_user(username='author2')
    sub_a1 = make_submission(author=author1, title='First Sub title', status=SubmissionStatus.INITIAL_CHECK)
    sub_a2 = make_submission(author=author2, title='Second Sub title', status=SubmissionStatus.UNDER_REVIEW)

    list_url = reverse('dashboard:admin_submissions')
    response = client.get(list_url)
    assert response.status_code == 200
    content = response.content.decode()
    assert 'First Sub title' in content
    assert 'Second Sub title' in content

    # 7.8 فلترة التقديمات بالحالة
    response_filter = client.get(list_url + '?status=' + SubmissionStatus.UNDER_REVIEW)
    assert response_filter.status_code == 200
    content_filter = response_filter.content.decode()
    assert 'Second Sub title' in content_filter
    assert 'First Sub title' not in content_filter

    # 7.9 فلترة التقديمات بالقسم
    sec2 = JournalSection.objects.create(name='Physics', slug='physics')
    sub_a1.section = sec2
    sub_a1.save()
    response_sec = client.get(list_url + '?section=' + str(sec2.pk))
    assert response_sec.status_code == 200
    content_sec = response_sec.content.decode()
    assert 'First Sub title' in content_sec
    assert 'Second Sub title' not in content_sec

    # 7.10 البحث بالعنوان
    response_search = client.get(list_url + '?q=First')
    assert response_search.status_code == 200
    content_search = response_search.content.decode()
    assert 'First Sub title' in content_search
    assert 'Second Sub title' not in content_search
