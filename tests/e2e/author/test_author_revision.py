import pytest
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.submissions.models import ArticleSubmission, ManuscriptFile
from apps.submissions.statuses import SubmissionStatus
from apps.submissions.exceptions import RevisionLimitExceededError, InvalidManuscriptFileError
from apps.accounts.models import User

@pytest.mark.django_db
def test_author_revision_flow(client_as, author, make_submission, reviewer, make_user):
    client = client_as(author)
    sub = make_submission(status=SubmissionStatus.REVISION_REQUIRED, author=author)
    sub.original_reviewer = reviewer
    sub.assigned_reviewer = make_user(role=User.ROLE_REVIEWER)  # temporary different reviewer
    sub.save()

    # 2.4 رفع Revision بملف غير PDF
    url = reverse('submissions:revise', kwargs={'pk': sub.pk})
    docx = SimpleUploadedFile('rev.docx', b'Word revision', content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    response = client.post(url, {'manuscript': docx})
    assert response.status_code == 200  # Form invalid
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.REVISION_REQUIRED

    # 2.1 رفع Revision أولى
    pdf = SimpleUploadedFile('rev1.pdf', b'%PDF-1.4 rev 1', content_type='application/pdf')
    response = client.post(url, {'manuscript': pdf})
    assert response.status_code == 302
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.UNDER_REVIEW
    assert sub.revision_count == 1
    # 2.6 التحقق من إعادة تعيين original_reviewer
    assert sub.assigned_reviewer == reviewer
    # 2.7 نسخة الملف عند الـ Revision
    assert sub.manuscript_files.count() == 2
    assert sub.manuscript_files.filter(is_current=True).first().version == 2

    # 2.5 رفع Revision من حالة خاطئة
    pdf.seek(0)
    response = client.post(url, {'manuscript': pdf})
    assert response.status_code == 302  # redirects and shows error message because sub is under_review
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.UNDER_REVIEW  # stays under review

    # 2.2 رفع Revision ثانية
    sub.status = SubmissionStatus.REVISION_REQUIRED
    sub.save()
    pdf2 = SimpleUploadedFile('rev2.pdf', b'%PDF-1.4 rev 2', content_type='application/pdf')
    response = client.post(url, {'manuscript': pdf2})
    assert response.status_code == 302
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.UNDER_REVIEW
    assert sub.revision_count == 2
    assert sub.manuscript_files.filter(is_current=True).first().version == 3

    # 2.3 محاولة رفع Revision ثالثة
    sub.status = SubmissionStatus.REVISION_REQUIRED
    sub.save()
    pdf3 = SimpleUploadedFile('rev3.pdf', b'%PDF-1.4 rev 3', content_type='application/pdf')
    response = client.post(url, {'manuscript': pdf3})
    assert response.status_code == 302  # redirects and shows error message because revision_count = 2
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.REVISION_REQUIRED  # stays revision_required

    # 2.8 رفع Revision من مؤلف آخر
    other_author = make_user(role=User.ROLE_AUTHOR)
    other_client = client_as(other_author)
    response = other_client.post(url, {'manuscript': pdf3})
    assert response.status_code == 403
