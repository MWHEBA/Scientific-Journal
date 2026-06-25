import pytest
from django.urls import reverse
from apps.submissions.statuses import SubmissionStatus
from apps.accounts.models import User

@pytest.mark.django_db
def test_author_access_control(client_as, client, author, second_author, make_submission, reviewer, make_review):
    # 6.5 زائر غير مسجّل يصل dashboard
    response = client.get(reverse('dashboard:home'))
    assert response.status_code == 302
    assert 'login' in response.url

    # 6.1 Author يرى فقط تقديماته
    client_a1 = client_as(author)
    client_a2 = client_as(second_author)
    sub1 = make_submission(author=author, title='Sub 1', status=SubmissionStatus.INITIAL_CHECK)
    sub2 = make_submission(author=second_author, title='Sub 2', status=SubmissionStatus.INITIAL_CHECK)

    response_a1 = client_a1.get(reverse('dashboard:author'))
    assert response_a1.status_code == 200
    assert 'Sub 1' in response_a1.content.decode()
    assert 'Sub 2' not in response_a1.content.decode()

    response_a2 = client_a2.get(reverse('dashboard:author'))
    assert response_a2.status_code == 200
    assert 'Sub 2' in response_a2.content.decode()
    assert 'Sub 1' not in response_a2.content.decode()

    # 6.2 Author يحاول الدخول على لوحة Admin
    response = client_a1.get(reverse('dashboard:admin_submissions'))
    assert response.status_code == 403

    # 6.3 Author يحاول الدخول على لوحة Reviewer
    response = client_a1.get(reverse('dashboard:reviewer'))
    assert response.status_code == 403

    # 6.4 Author يحاول عرض review detail
    review = make_review(submission=sub1, reviewer=reviewer)
    review_detail_url = reverse('reviews:detail', kwargs={'pk': review.pk})
    response = client_a1.get(review_detail_url)
    assert response.status_code == 403
