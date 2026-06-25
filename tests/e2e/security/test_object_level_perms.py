import pytest
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.submissions.statuses import SubmissionStatus

@pytest.mark.django_db
def test_author_object_level_permissions(client_as, author, make_submission, make_user):
    client_author2 = client_as(make_user(role=User.ROLE_AUTHOR))
    
    # Create submission for author 1
    sub = make_submission(status=SubmissionStatus.DRAFT, author=author)
    
    # 27.1 مؤلف يعدّل تقديم مؤلف آخر -> 403
    response = client_author2.post(reverse('submissions:edit', kwargs={'pk': sub.pk}), {'title': 'Hacked Title'})
    assert response.status_code == 403

    # Change sub to INITIAL_CHECK to test withdraw
    sub.status = SubmissionStatus.INITIAL_CHECK
    sub.save()

    # 27.2 مؤلف يسحب تقديم مؤلف آخر -> 403
    response = client_author2.post(reverse('submissions:withdraw', kwargs={'pk': sub.pk}))
    assert response.status_code == 403

    # Change sub to ACCEPTED to test payment
    sub.status = SubmissionStatus.ACCEPTED
    sub.save()

    # 27.3 مؤلف يبدأ دفع تقديم آخر -> 403
    response = client_author2.post(reverse('payments:initiate', kwargs={'pk': sub.pk}))
    assert response.status_code == 403

    # 27.6 مؤلف يرى تفاصيل تقديم مؤلف آخر -> 404
    response = client_author2.get(reverse('dashboard:author_submission_detail', kwargs={'pk': sub.pk}))
    assert response.status_code == 404

    # Change sub to REVISION_REQUIRED to test revise
    sub.status = SubmissionStatus.REVISION_REQUIRED
    sub.save()

    # 27.7 مؤلف يصل revision تقديم آخر -> 403
    response = client_author2.get(reverse('submissions:revise', kwargs={'pk': sub.pk}))
    assert response.status_code == 403
    response = client_author2.post(reverse('submissions:revise', kwargs={'pk': sub.pk}))
    assert response.status_code == 403


@pytest.mark.django_db
def test_reviewer_object_level_permissions(client_as, reviewer, make_submission, make_review, make_user):
    reviewer2 = make_user(role=User.ROLE_REVIEWER)
    client_rev2 = client_as(reviewer2)

    sub = make_submission(status=SubmissionStatus.UNDER_REVIEW)
    review1 = make_review(submission=sub, reviewer=reviewer, revision_round=1)

    # 27.4 مراجع يرى تفاصيل review مراجع آخر -> 403
    response = client_rev2.get(reverse('reviews:detail', kwargs={'pk': review1.pk}))
    assert response.status_code == 403

    # 27.5 مراجع يرسل قرار review مراجع آخر -> 403
    response = client_rev2.post(reverse('reviews:submit', kwargs={'pk': review1.pk}), {
        'score_originality': '5',
        'score_relevance': '5',
        'score_clarity': '5',
        'score_language': '5',
        'decision': 'accept',
        'comments': 'Hack accept',
    })
    assert response.status_code == 403
from apps.accounts.models import User
