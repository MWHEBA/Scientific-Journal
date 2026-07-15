import pytest
import os
from django.urls import reverse
from apps.submissions.statuses import SubmissionStatus
from apps.submissions.models import ArticleSubmission, ManuscriptFile, AuditLog
from apps.publishing.models import PublishedArticle

@pytest.mark.django_db
def test_admin_retract_article_flow(client_as, admin_user, make_submission, journal_section):
    client = client_as(admin_user)
    
    # Create a published submission (automatically creates a ManuscriptFile)
    sub = make_submission(status=SubmissionStatus.PUBLISHED, section=journal_section)
    manuscript = sub.manuscript_files.first()
    
    pub_article = PublishedArticle.objects.create(
        submission=sub,
        manuscript_file=manuscript,
        title=sub.title,
        abstract=sub.abstract,
        section=sub.section,
        slug="test-slug-retract"
    )
    
    assert PublishedArticle.objects.filter(pk=pub_article.pk).exists()
    
    url = reverse('dashboard:submission_detail', kwargs={'pk': sub.pk})
    
    # Call retract action
    response = client.post(url, {'action': 'retract_article'})
    assert response.status_code == 302
    
    # Verify that the PublishedArticle is deleted
    assert not PublishedArticle.objects.filter(pk=pub_article.pk).exists()
    
    # Verify submission status returned to PAID
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.PAID
    
    # Verify audit log recorded status change
    assert AuditLog.objects.filter(
        entity_type='ArticleSubmission',
        entity_id=sub.pk,
        event='status_change',
        new_value=SubmissionStatus.PAID
    ).exists()

@pytest.mark.django_db
def test_admin_delete_submission_completely_flow(client_as, admin_user, make_submission, journal_section):
    client = client_as(admin_user)
    
    # Create submission in UNDER_REVIEW
    sub = make_submission(status=SubmissionStatus.UNDER_REVIEW, section=journal_section)
    manuscript = sub.manuscript_files.first()
    filepath = manuscript.file.path
    
    # Make sure the file exists physically
    assert os.path.exists(filepath)
    
    url = reverse('dashboard:submission_detail', kwargs={'pk': sub.pk})
    
    # Call delete completely action
    response = client.post(url, {'action': 'delete_submission_completely'})
    assert response.status_code == 302
    
    # Verify submission is deleted from db
    assert not ArticleSubmission.objects.filter(pk=sub.pk).exists()
    assert not ManuscriptFile.objects.filter(pk=manuscript.pk).exists()
    
    # Verify file is deleted from filesystem
    assert not os.path.exists(filepath)
    
    # Verify audit log exists for the deletion
    assert AuditLog.objects.filter(
        entity_type='ArticleSubmission',
        entity_id=sub.pk,
        event='deleted_permanently'
    ).exists()
