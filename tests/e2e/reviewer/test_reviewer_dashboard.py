import pytest
from django.urls import reverse
from apps.submissions.statuses import SubmissionStatus
from apps.accounts.models import User

@pytest.mark.django_db
def test_reviewer_dashboard_flow(client_as, reviewer, make_submission, make_review, make_user):
    client = client_as(reviewer)
    
    # 14.5 مراجع بدون تعيين
    response = client.get(reverse('dashboard:reviewer'))
    assert response.status_code == 200
    assert len(response.context['reviews']) == 0

    # Create submission and assign reviewer
    sub1 = make_submission(status=SubmissionStatus.UNDER_REVIEW)
    review1 = make_review(submission=sub1, reviewer=reviewer, is_submitted=False)

    # 14.1 مراجع يرى مراجعاته الحالية فقط
    sub_other = make_submission(status=SubmissionStatus.UNDER_REVIEW)
    other_reviewer = make_user(role=User.ROLE_REVIEWER)
    make_review(submission=sub_other, reviewer=other_reviewer)

    response = client.get(reverse('dashboard:reviewer'))
    assert response.status_code == 200
    assert len(response.context['reviews']) == 1
    assert response.context['reviews'].first().submission == sub1

    # 14.2 تصنيف المراجعات (جديدة/مكتملة)
    assert len(response.context['new_reviews']) == 1
    assert len(response.context['completed_reviews']) == 0

    # Make review completed
    review1.is_submitted = True
    review1.save()
    response2 = client.get(reverse('dashboard:reviewer'))
    assert len(response2.context['new_reviews']) == 0
    assert len(response2.context['completed_reviews']) == 1

    # 14.4 Reviewer يرى التقديمات المعيّنة له
    # 14.6 Reviewer يرى تقديمات under_review بدون مراجع
    sub_unassigned = make_submission(status=SubmissionStatus.UNDER_REVIEW, title='Unassigned Sub')
    response_subs = client.get(reverse('dashboard:reviewer_submissions'))
    assert response_subs.status_code == 200
    content = response_subs.content.decode()
    assert 'Unassigned Sub' in content
    # sub1 is assigned to reviewer but is now status=UNDER_REVIEW and has a completed review, wait!
    # Let's see if sub1 has assigned_reviewer. Yes, sub1 has assigned_reviewer=reviewer.
    assert sub1.title in content

    # 14.3 Reviewer لا يرى لوحة Admin
    response_admin = client.get(reverse('dashboard:admin'))
    assert response_admin.status_code == 403
