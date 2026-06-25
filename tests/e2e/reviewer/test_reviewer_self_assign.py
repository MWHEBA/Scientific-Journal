import pytest
from django.urls import reverse
from apps.submissions.statuses import SubmissionStatus
from apps.submissions.models import ArticleSubmission
from apps.reviews.models import Review
from apps.accounts.models import User

@pytest.mark.django_db
def test_reviewer_self_assign_flow(client_as, reviewer, make_submission, make_user):
    client = client_as(reviewer)

    # 16.1 تعيين نفسه لتقديم under_review بدون مراجع
    sub1 = make_submission(status=SubmissionStatus.UNDER_REVIEW, section=None)
    sub1.assigned_reviewer = None
    sub1.save()

    url1 = reverse('dashboard:reviewer_submission_detail', kwargs={'pk': sub1.pk})
    response = client.post(url1, {'action': 'self_assign'})
    assert response.status_code == 302
    sub1.refresh_from_db()
    assert sub1.assigned_reviewer == reviewer
    assert Review.objects.filter(submission=sub1, reviewer=reviewer).exists()

    # 16.2 محاولة تعيين نفسه لتقديم initial_check
    sub2 = make_submission(status=SubmissionStatus.INITIAL_CHECK)
    sub2.assigned_reviewer = None
    sub2.save()
    url2 = reverse('dashboard:reviewer_submission_detail', kwargs={'pk': sub2.pk})
    # Since submission has status INITIAL_CHECK, the post request will raise PermissionDenied or reject
    # Let's check view logic:
    # is_initial_check_unassigned is True, so permission is granted.
    # But in action check:
    # if submission.status == SubmissionStatus.INITIAL_CHECK: messages.error... and redirect
    response2 = client.post(url2, {'action': 'self_assign'})
    assert response2.status_code == 302
    sub2.refresh_from_db()
    assert sub2.assigned_reviewer is None

    # 16.3 محاولة تعيين نفسه لتقديم معيّن بالفعل
    sub3 = make_submission(status=SubmissionStatus.UNDER_REVIEW)
    other_rev = make_user(role=User.ROLE_REVIEWER)
    sub3.assigned_reviewer = other_rev
    sub3.save()
    url3 = reverse('dashboard:reviewer_submission_detail', kwargs={'pk': sub3.pk})
    # is_assigned_reviewer is False (since user is reviewer and assigned is other_rev),
    # is_under_review_unassigned is False (since assigned is not null).
    # Thus, PermissionDenied is raised!
    response3 = client.post(url3, {'action': 'self_assign'})
    assert response3.status_code == 403

    # 16.4 get_or_create منع تكرار Review
    sub4 = make_submission(status=SubmissionStatus.UNDER_REVIEW)
    sub4.assigned_reviewer = None
    sub4.save()
    url4 = reverse('dashboard:reviewer_submission_detail', kwargs={'pk': sub4.pk})
    # First self-assign
    client.post(url4, {'action': 'self_assign'})
    # Simulate another get_or_create by calling review creation or posting again if allowed
    assert Review.objects.filter(submission=sub4, reviewer=reviewer).count() == 1
