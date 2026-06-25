import pytest
from django.urls import reverse
from apps.submissions.statuses import SubmissionStatus
from apps.accounts.models import User

@pytest.mark.django_db
def test_reviewer_access_control(client_as, reviewer, make_submission, make_user):
    client = client_as(reviewer)

    # 17.1 Reviewer لا يصل للوحة Admin
    url_admin = reverse('dashboard:admin')
    response = client.get(url_admin)
    assert response.status_code == 403

    # 17.2 Reviewer لا يقدر يعمل pass/reject للفحص الأولي
    sub = make_submission(status=SubmissionStatus.INITIAL_CHECK)
    url_detail = reverse('dashboard:submission_detail', kwargs={'pk': sub.pk}) # admin detail URL
    # Admin detail URL uses AdminRequiredMixin, so it should return 403
    response_pass = client.post(url_detail, {'action': 'pass'})
    assert response_pass.status_code == 403

    # 17.3 Reviewer لا يقدر يصل تقديم غير معيّن له
    other_reviewer = make_user(role=User.ROLE_REVIEWER)
    sub_other = make_submission(status=SubmissionStatus.UNDER_REVIEW)
    sub_other.assigned_reviewer = other_reviewer
    sub_other.save()
    url_rev_detail = reverse('dashboard:reviewer_submission_detail', kwargs={'pk': sub_other.pk})
    response_detail = client.get(url_rev_detail)
    assert response_detail.status_code == 403

    # 17.4 Reviewer لا يقدر يبدأ دفع
    sub_accepted = make_submission(status=SubmissionStatus.ACCEPTED)
    url_pay = reverse('payments:initiate', kwargs={'pk': sub_accepted.pk})
    response_pay = client.post(url_pay)
    assert response_pay.status_code == 403
