import pytest
from django.urls import reverse
from apps.submissions.statuses import SubmissionStatus
from apps.accounts.models import User

@pytest.mark.django_db
def test_author_archive_flow(client_as, author, make_submission, make_user):
    client = client_as(author)

    # 5.1 أرشفة تقديم مرفوض
    sub_rejected = make_submission(status=SubmissionStatus.REJECTED, author=author)
    url_archive = reverse('submissions:archive', kwargs={'pk': sub_rejected.pk})
    response = client.post(url_archive)
    assert response.status_code == 302
    sub_rejected.refresh_from_db()
    assert sub_rejected.is_archived is True

    # 5.2 أرشفة تقديم مسحوب
    sub_withdrawn = make_submission(status=SubmissionStatus.WITHDRAWN, author=author)
    url_archive_withdrawn = reverse('submissions:archive', kwargs={'pk': sub_withdrawn.pk})
    response = client.post(url_archive_withdrawn)
    assert response.status_code == 302
    sub_withdrawn.refresh_from_db()
    assert sub_withdrawn.is_archived is True

    # 5.3 محاولة أرشفة تقديم نشط
    sub_active = make_submission(status=SubmissionStatus.UNDER_REVIEW, author=author)
    url_archive_active = reverse('submissions:archive', kwargs={'pk': sub_active.pk})
    response = client.post(url_archive_active)
    assert response.status_code == 302
    sub_active.refresh_from_db()
    assert sub_active.is_archived is False

    # 5.4 إلغاء الأرشفة
    url_unarchive = reverse('submissions:unarchive', kwargs={'pk': sub_rejected.pk})
    response = client.post(url_unarchive)
    assert response.status_code == 302
    sub_rejected.refresh_from_db()
    assert sub_rejected.is_archived is False

    # 5.5 أرشفة تقديم شخص آخر
    other_author = make_user(role=User.ROLE_AUTHOR)
    other_client = client_as(other_author)
    response = other_client.post(url_archive_withdrawn)
    assert response.status_code == 403
