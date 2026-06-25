import pytest
from django.urls import reverse
from apps.submissions.statuses import SubmissionStatus

@pytest.mark.django_db
def test_reviewer_role_restrictions(client_as, reviewer, make_submission):
    client_rev = client_as(reviewer)
    sub = make_submission(status=SubmissionStatus.UNDER_REVIEW)

    # 26.1 Reviewer يصل Admin dashboard -> 403
    response = client_rev.get(reverse('dashboard:admin'))
    assert response.status_code == 403

    # 26.2 Reviewer يُعيّن مراجعاً -> 403
    response = client_rev.post(reverse('dashboard:assign_reviewer', kwargs={'pk': sub.pk}), {'reviewer_id': reviewer.pk})
    assert response.status_code == 403

    # 26.5 Reviewer يُنشئ مجلداً -> 403
    response = client_rev.post(reverse('dashboard:volumes'), {'number': 1, 'year': 2024})
    assert response.status_code == 403

    # 26.7 Reviewer يتحكم في المستخدمين -> 403
    response = client_rev.post(reverse('dashboard:users'))
    assert response.status_code == 403


@pytest.mark.django_db
def test_author_role_restrictions(client_as, author, make_submission):
    client_auth = client_as(author)

    # 26.3 Author يصل Admin dashboard -> 403
    response = client_auth.get(reverse('dashboard:admin'))
    assert response.status_code == 403

    # 26.4 Author يصل Reviewer dashboard -> 403
    response = client_auth.get(reverse('dashboard:reviewer'))
    assert response.status_code == 403

    # 26.6 Author يُعدّل إعدادات المجلة -> 403
    response = client_auth.post(reverse('dashboard:settings'), {'apc_amount': 500})
    assert response.status_code == 403


@pytest.mark.django_db
def test_admin_role_restrictions(client_as, admin_user, make_submission):
    client_admin = client_as(admin_user)
    sub = make_submission(status=SubmissionStatus.REVISION_REQUIRED)

    # 26.8 Admin يحاول رفع revision -> 403
    response = client_admin.post(reverse('submissions:revise', kwargs={'pk': sub.pk}))
    assert response.status_code == 403
