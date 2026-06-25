import pytest
from datetime import timedelta
from django.utils import timezone
from django.core.management import call_command
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.submissions.statuses import SubmissionStatus
from apps.submissions.models import ArticleSubmission, ManuscriptFile
from apps.submissions.state_machine import SubmissionStateMachine
from apps.submissions.exceptions import InvalidStateTransitionError
from apps.notifications.models import Notification

@pytest.mark.django_db
def test_expiry_moves_accepted_to_expired(client_as, author, journal_section):
    # 23.1 انتهاء الـ deadline يُنقل لـ expired
    sub = ArticleSubmission.objects.create(
        title='Expired E2E Article',
        abstract='Abstract content',
        author=author,
        section=journal_section,
        corresponding_author_email=author.email,
        status=SubmissionStatus.ACCEPTED
    )
    sub.payment_deadline = timezone.now() - timedelta(days=1)
    sub.save()

    call_command('expire_payments')

    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.EXPIRED
    
    # Assert notification generated
    assert Notification.objects.filter(user=author, type='payment_required').exists()


@pytest.mark.django_db
def test_expired_is_terminal_state(client_as, author, journal_section):
    # 23.2 Expired terminal state
    client_author = client_as(author)
    sub = ArticleSubmission.objects.create(
        title='Expired Terminal E2E Article',
        abstract='Abstract content',
        author=author,
        section=journal_section,
        corresponding_author_email=author.email,
        status=SubmissionStatus.EXPIRED
    )
    
    # Try initiating payment (should fail)
    response_pay = client_author.post(reverse('payments:initiate', kwargs={'pk': sub.pk}))
    # View redirects to dashboard with error message
    assert response_pay.status_code == 302
    
    # Try revising (should raise transition/validation error or fail authorization)
    pdf = SimpleUploadedFile('manuscript.pdf', b'%PDF-1.4 E2E Content', content_type='application/pdf')
    response_revise = client_author.post(reverse('submissions:revise', kwargs={'pk': sub.pk}), {'manuscript': pdf})
    assert response_revise.status_code == 403 or response_revise.status_code == 302
    
    # Try state machine transition directly
    with pytest.raises(InvalidStateTransitionError):
        SubmissionStateMachine.transition(sub, SubmissionStatus.PAYMENT_PROCESSING)


@pytest.mark.django_db
def test_non_expired_remains_accepted(client_as, author, journal_section):
    # 23.3 deadline لم ينته لا يُنقل
    sub = ArticleSubmission.objects.create(
        title='Active Accepted E2E Article',
        abstract='Abstract content',
        author=author,
        section=journal_section,
        corresponding_author_email=author.email,
        status=SubmissionStatus.ACCEPTED
    )
    sub.payment_deadline = timezone.now() + timedelta(days=10)
    sub.save()

    call_command('expire_payments')

    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.ACCEPTED


@pytest.mark.django_db
def test_payment_processing_does_not_expire(client_as, author, journal_section):
    # 23.4 payment_processing لا يُنقل لـ expired
    sub = ArticleSubmission.objects.create(
        title='Payment Processing E2E Article',
        abstract='Abstract content',
        author=author,
        section=journal_section,
        corresponding_author_email=author.email,
        status=SubmissionStatus.PAYMENT_PROCESSING
    )
    sub.payment_deadline = timezone.now() - timedelta(days=1)
    sub.save()

    call_command('expire_payments')

    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.PAYMENT_PROCESSING
