import pytest
from django.urls import reverse
from apps.submissions.statuses import SubmissionStatus
from apps.accounts.models import User

@pytest.mark.django_db
def test_author_withdraw_flow(client_as, author, make_submission, make_user):
    client = client_as(author)

    # 4.1 سحب مقالة في initial_check
    sub = make_submission(status=SubmissionStatus.INITIAL_CHECK, author=author)
    url = reverse('submissions:withdraw', kwargs={'pk': sub.pk})
    response = client.post(url)
    assert response.status_code == 302
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.WITHDRAWN

    # 4.2 محاولة سحب مقالة تحت المراجعة
    sub2 = make_submission(status=SubmissionStatus.UNDER_REVIEW, author=author)
    url2 = reverse('submissions:withdraw', kwargs={'pk': sub2.pk})
    response = client.post(url2)
    assert response.status_code == 302
    sub2.refresh_from_db()
    assert sub2.status == SubmissionStatus.UNDER_REVIEW  # remains under review

    # 4.3 محاولة سحب مقالة مرفوضة
    sub3 = make_submission(status=SubmissionStatus.REJECTED, author=author)
    url3 = reverse('submissions:withdraw', kwargs={'pk': sub3.pk})
    response = client.post(url3)
    assert response.status_code == 302
    sub3.refresh_from_db()
    assert sub3.status == SubmissionStatus.REJECTED  # remains rejected

    # 4.4 سحب مقالة شخص آخر
    other_author = make_user(role=User.ROLE_AUTHOR)
    other_client = client_as(other_author)
    sub4 = make_submission(status=SubmissionStatus.INITIAL_CHECK, author=author)
    url4 = reverse('submissions:withdraw', kwargs={'pk': sub4.pk})
    response = other_client.post(url4)
    assert response.status_code == 403
