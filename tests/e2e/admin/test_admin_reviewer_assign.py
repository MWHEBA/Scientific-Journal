import pytest
from django.urls import reverse
from apps.submissions.statuses import SubmissionStatus
from apps.submissions.models import ArticleSubmission
from apps.reviews.models import Review
from apps.accounts.models import User

@pytest.mark.django_db
def test_admin_reviewer_assign_flow(client_as, admin_user, make_submission, reviewer, make_user):
    client = client_as(admin_user)
    sub = make_submission(status=SubmissionStatus.UNDER_REVIEW)
    url = reverse('dashboard:assign_reviewer', kwargs={'pk': sub.pk})

    # 8.4 تعيين بدون reviewer_id
    response = client.post(url, {'reviewer_id': ''})
    assert response.status_code == 302
    sub.refresh_from_db()
    assert sub.assigned_reviewer is None

    # 8.5 تعيين مستخدم ليس مراجعاً
    author_user = make_user(role=User.ROLE_AUTHOR)
    response = client.post(url, {'reviewer_id': author_user.pk})
    assert response.status_code == 404

    # 8.1 تعيين مراجع لتقديم
    response = client.post(url, {'reviewer_id': reviewer.pk})
    assert response.status_code == 302
    sub.refresh_from_db()
    assert sub.assigned_reviewer == reviewer
    # 8.2 original_reviewer لأول مرة
    assert sub.original_reviewer == reviewer
    # Review object created
    assert Review.objects.filter(submission=sub, reviewer=reviewer).exists()

    # 8.3 تعيين مراجع آخر (تغيير)
    second_reviewer = make_user(role=User.ROLE_REVIEWER)
    response = client.post(url, {'reviewer_id': second_reviewer.pk})
    assert response.status_code == 302
    sub.refresh_from_db()
    assert sub.assigned_reviewer == second_reviewer
    assert sub.original_reviewer == reviewer  # remains original
    assert Review.objects.filter(submission=sub, reviewer=second_reviewer).exists()

    # 8.6 Review object لا يُنشأ مكرر
    response = client.post(url, {'reviewer_id': second_reviewer.pk})
    assert response.status_code == 302
    assert Review.objects.filter(submission=sub, reviewer=second_reviewer).count() == 1

    # 8.7 إحصاءات المراجعين (active/completed)
    # let's fetch the assign reviewer page and verify list stats
    response = client.get(url)
    assert response.status_code == 200
    content = response.content.decode()
    # stats details for reviewers should be in page context or content
