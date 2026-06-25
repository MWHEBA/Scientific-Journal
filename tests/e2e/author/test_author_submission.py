import pytest
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.submissions.models import ArticleSubmission, ManuscriptFile
from apps.submissions.statuses import SubmissionStatus
from apps.notifications.models import Notification

@pytest.mark.django_db
def test_submission_creation_and_modification_flow(client_as, author, journal_section, admin_user):
    client = client_as(author)
    
    # 1.1 إنشاء مسودة بدون ملف PDF
    url = reverse('submissions:create')
    data = {
        'title': 'E2E Test Draft 1',
        'abstract': 'Abstract draft',
        'corresponding_author_email': author.email,
        'keywords': 'test, draft',
        'section': journal_section.pk,
        'action': 'save',
        'coauthor_set-TOTAL_FORMS': '0',
        'coauthor_set-INITIAL_FORMS': '0',
        'coauthor_set-MIN_NUM_FORMS': '0',
        'coauthor_set-MAX_NUM_FORMS': '1000',
    }
    response = client.post(url, data)
    assert response.status_code == 302
    sub = ArticleSubmission.objects.get(title='E2E Test Draft 1')
    assert sub.status == SubmissionStatus.DRAFT
    assert sub.manuscript_files.count() == 0

    # 1.2 إنشاء مسودة مع رفع PDF
    pdf_content = b'%PDF-1.4 E2E PDF Content'
    pdf = SimpleUploadedFile('manuscript.pdf', pdf_content, content_type='application/pdf')
    data['title'] = 'E2E Test Draft 2'
    data['manuscript'] = pdf
    response = client.post(url, data)
    assert response.status_code == 302
    sub2 = ArticleSubmission.objects.get(title='E2E Test Draft 2')
    assert sub2.status == SubmissionStatus.DRAFT
    assert sub2.manuscript_files.filter(is_current=True).count() == 1

    # 1.3 رفع ملف غير PDF عند الإنشاء
    docx = SimpleUploadedFile('manuscript.docx', b'Word Content', content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    data['title'] = 'E2E Test Draft 3'
    data['manuscript'] = docx
    response = client.post(url, data)
    assert response.status_code == 200  # returns template with form_invalid
    assert not ArticleSubmission.objects.filter(title='E2E Test Draft 3').exists()

    # 1.4 تقديم مسودة بدون manuscript
    sub3 = ArticleSubmission.objects.create(
        title='Draft No PDF',
        abstract='Abstract',
        author=author,
        corresponding_author_email=author.email,
        status=SubmissionStatus.DRAFT
    )
    submit_url = reverse('submissions:submit', kwargs={'pk': sub3.pk})
    response = client.post(submit_url)
    assert response.status_code == 302
    sub3.refresh_from_db()
    assert sub3.status == SubmissionStatus.DRAFT  # stays draft

    # 1.5 تقديم مسودة مع manuscript
    ManuscriptFile.objects.create(
        submission=sub3,
        file=SimpleUploadedFile('manuscript.pdf', pdf_content, content_type='application/pdf'),
        version=1,
        is_current=True
    )
    response = client.post(submit_url)
    assert response.status_code == 302
    sub3.refresh_from_db()
    assert sub3.status == SubmissionStatus.INITIAL_CHECK
    assert Notification.objects.filter(type='new_submission').exists()

    # 1.6 تعديل مسودة (بيانات)
    sub_draft = ArticleSubmission.objects.create(
        title='Draft Title',
        abstract='Abstract',
        author=author,
        corresponding_author_email=author.email,
        status=SubmissionStatus.DRAFT
    )
    edit_url = reverse('submissions:edit', kwargs={'pk': sub_draft.pk})
    edit_data = {
        'title': 'Updated Draft Title',
        'abstract': 'Updated Abstract',
        'corresponding_author_email': author.email,
        'keywords': 'updated',
        'section': journal_section.pk,
        'action': 'save',
        'coauthor_set-TOTAL_FORMS': '0',
        'coauthor_set-INITIAL_FORMS': '0',
        'coauthor_set-MIN_NUM_FORMS': '0',
        'coauthor_set-MAX_NUM_FORMS': '1000',
    }
    response = client.post(edit_url, edit_data)
    assert response.status_code == 302
    sub_draft.refresh_from_db()
    assert sub_draft.title == 'Updated Draft Title'
    assert sub_draft.status == SubmissionStatus.DRAFT

    # 1.7 تعديل مسودة (ملف PDF جديد)
    pdf2 = SimpleUploadedFile('manuscript2.pdf', pdf_content, content_type='application/pdf')
    edit_data['manuscript'] = pdf2
    response = client.post(edit_url, edit_data)
    assert response.status_code == 302
    sub_draft.refresh_from_db()
    assert sub_draft.manuscript_files.count() == 1  # version 1
    assert sub_draft.manuscript_files.filter(is_current=True).first().version == 1

    # 1.8 محاولة تعديل تقديم غير مسودة
    sub_initial = ArticleSubmission.objects.create(
        title='Initial Check Sub',
        abstract='Abstract',
        author=author,
        corresponding_author_email=author.email,
        status=SubmissionStatus.INITIAL_CHECK
    )
    edit_initial_url = reverse('submissions:edit', kwargs={'pk': sub_initial.pk})
    response = client.post(edit_initial_url, edit_data)
    assert response.status_code == 403  # PermissionDenied

    # 1.9 محاولة تعديل مسودة مؤلف آخر
    from apps.accounts.models import User
    other_author = User.objects.create_user(username='other_author', email='other@test.com', password='pass', role=User.ROLE_AUTHOR)
    sub_other = ArticleSubmission.objects.create(
        title='Other Author Draft',
        abstract='Abstract',
        author=other_author,
        corresponding_author_email=other_author.email,
        status=SubmissionStatus.DRAFT
    )
    edit_other_url = reverse('submissions:edit', kwargs={'pk': sub_other.pk})
    response = client.post(edit_other_url, edit_data)
    assert response.status_code == 403

    # 1.10 تقديم submission سبق تقديمه
    response = client.post(reverse('submissions:submit', kwargs={'pk': sub_initial.pk}))
    assert response.status_code == 302
    sub_initial.refresh_from_db()
    assert sub_initial.status == SubmissionStatus.INITIAL_CHECK
