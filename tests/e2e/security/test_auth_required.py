import pytest
from django.urls import reverse
from apps.submissions.statuses import SubmissionStatus

@pytest.mark.django_db
def test_authentication_required_for_dashboards(client):
    # 25.1 GET /dashboard/author/ -> Redirect
    response = client.get(reverse('dashboard:author'))
    assert response.status_code == 302
    assert 'login' in response.url

    # 25.2 GET /dashboard/reviewer/ -> Redirect
    response = client.get(reverse('dashboard:reviewer'))
    assert response.status_code == 302
    assert 'login' in response.url

    # 25.3 GET /dashboard/admin/ -> Redirect
    response = client.get(reverse('dashboard:admin'))
    assert response.status_code == 302
    assert 'login' in response.url


@pytest.mark.django_db
def test_authentication_required_for_submissions(client, make_submission):
    sub = make_submission(status=SubmissionStatus.DRAFT)
    
    # 25.4 GET /submissions/new/ -> Redirect
    response = client.get(reverse('submissions:create'))
    assert response.status_code == 302
    
    # 25.5 GET /submissions/<pk>/edit/ -> Redirect
    response = client.get(reverse('submissions:edit', kwargs={'pk': sub.pk}))
    assert response.status_code == 302
    
    # 25.6 POST /submissions/<pk>/submit/ -> Redirect
    response = client.post(reverse('submissions:submit', kwargs={'pk': sub.pk}))
    assert response.status_code == 302
    
    # 25.7 GET/POST /submissions/<pk>/revise/ -> Redirect
    response = client.get(reverse('submissions:revise', kwargs={'pk': sub.pk}))
    assert response.status_code == 302
    response = client.post(reverse('submissions:revise', kwargs={'pk': sub.pk}))
    assert response.status_code == 302
    
    # 25.8 POST /submissions/<pk>/withdraw/ -> Redirect
    response = client.post(reverse('submissions:withdraw', kwargs={'pk': sub.pk}))
    assert response.status_code == 302


@pytest.mark.django_db
def test_authentication_required_for_reviews(client, make_submission, make_review):
    sub = make_submission(status=SubmissionStatus.UNDER_REVIEW)
    review = make_review(submission=sub, revision_round=1)
    
    # 25.9 GET /reviews/<pk>/ -> Redirect
    response = client.get(reverse('reviews:detail', kwargs={'pk': review.pk}))
    assert response.status_code == 302
    
    # 25.10 POST /reviews/<pk>/submit/ -> Redirect
    response = client.post(reverse('reviews:submit', kwargs={'pk': review.pk}))
    assert response.status_code == 302


@pytest.mark.django_db
def test_authentication_required_for_payments(client, make_submission):
    sub = make_submission(status=SubmissionStatus.ACCEPTED)
    
    # 25.11 GET/POST /payments/<pk>/initiate/ -> Redirect
    response = client.get(reverse('payments:initiate', kwargs={'pk': sub.pk}))
    assert response.status_code == 302
    response = client.post(reverse('payments:initiate', kwargs={'pk': sub.pk}))
    assert response.status_code == 302


@pytest.mark.django_db
def test_webhook_does_not_require_authentication(client):
    # 25.12 /payments/webhook/ does not require login, but signature is validated
    # (should return 400 invalid signature instead of redirecting to login)
    response = client.post(reverse('payments:webhook'), data={}, content_type='application/json')
    assert response.status_code == 400
