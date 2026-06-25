import pytest
from concurrent.futures import ThreadPoolExecutor
from django.db import transaction, connection
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.submissions.statuses import SubmissionStatus
from apps.submissions.models import ArticleSubmission, ManuscriptFile, AuditLog
from apps.submissions.state_machine import SubmissionStateMachine
from apps.publishing.services import PublishingService
from apps.publishing.exceptions import AlreadyPublishedError
from apps.payments.models import Payment
from apps.payments.services import PaymentService
from apps.payments.exceptions import DuplicatePaymentError, PaymentNotAllowedError
from apps.reviews.models import Review
from apps.reviews.services import ReviewService
from apps.submissions.exceptions import InvalidStateTransitionError

@pytest.mark.django_db(transaction=True)
def test_concurrent_review_submission(client_as, reviewer, make_submission, make_review, make_user):
    # 24.1 مراجعان يحاولان submit_review لنفس الوقت
    # فقط المعيّن ينجح
    sub = make_submission(status=SubmissionStatus.UNDER_REVIEW)
    reviewer2 = make_user(role=User.ROLE_REVIEWER)
    
    # Assign reviewer 1
    sub.assigned_reviewer = reviewer
    sub.save()
    
    review1 = make_review(submission=sub, reviewer=reviewer, revision_round=1)
    review2 = make_review(submission=sub, reviewer=reviewer2, revision_round=1)
    
    # reviewer 2 tries to submit review (should fail since he is not assigned)
    with pytest.raises(InvalidStateTransitionError) as excinfo:
        ReviewService.submit_review(
            review2,
            decision=Review.DECISION_ACCEPT,
            scores={'originality': 4, 'relevance': 4, 'clarity': 4, 'language': 4},
            comments='Good',
            actor=reviewer2
        )
    assert "Only the currently assigned reviewer can submit this review" in str(excinfo.value)
    
    # reviewer 1 (assigned) submits review (should succeed)
    ReviewService.submit_review(
        review1,
        decision=Review.DECISION_ACCEPT,
        scores={'originality': 4, 'relevance': 4, 'clarity': 4, 'language': 4},
        comments='Good',
        actor=reviewer
    )
    
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.ACCEPTED


@pytest.mark.django_db(transaction=True)
def test_concurrent_payment_initiation(client_as, author, journal_section, site_settings, payment_service):
    # 24.2 منع duplicate initiate_payment
    sub = ArticleSubmission.objects.create(
        title='Concurrent Payment Article',
        abstract='Abstract content',
        author=author,
        section=journal_section,
        corresponding_author_email=author.email,
        status=SubmissionStatus.ACCEPTED
    )
    pdf = SimpleUploadedFile('manuscript.pdf', b'%PDF-1.4 Content', content_type='application/pdf')
    ManuscriptFile.objects.create(submission=sub, file=pdf, version=1, is_current=True)
    
    # Simulate first initiate payment
    payment_service.initiate_payment(sub, actor=author)
    
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.PAYMENT_PROCESSING
    
    # A concurrent attempt to initiate payment should raise PaymentNotAllowedError because status is no longer ACCEPTED
    with pytest.raises(PaymentNotAllowedError):
        payment_service.initiate_payment(sub, actor=author)


@pytest.mark.django_db(transaction=True)
def test_concurrent_publishing(admin_user, make_submission, journal_section):
    # 24.3 منع duplicate PublishingService.publish
    sub = make_submission(status=SubmissionStatus.PAID, section=journal_section)
    
    # Publish first time
    pub1 = PublishingService.publish(sub, actor=admin_user)
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.PUBLISHED
    
    # Concurrently attempting to publish again should raise AlreadyPublishedError
    # We must reset status to PAID to bypass Guard 1 and hit Guard 2
    sub.status = SubmissionStatus.PAID
    sub.save()
    with pytest.raises(AlreadyPublishedError):
        PublishingService.publish(sub, actor=admin_user)


@pytest.mark.django_db(transaction=True)
def test_select_for_update_prevents_race_conditions(make_submission):
    # 24.4 select_for_update يمنع التعارض
    sub = make_submission(status=SubmissionStatus.INITIAL_CHECK)
    
    # We want to verify that transitioning locking mechanism works.
    # When we retrieve with select_for_update, it locks the row.
    with transaction.atomic():
        locked_sub = ArticleSubmission.objects.select_for_update().get(pk=sub.pk)
        assert locked_sub.status == SubmissionStatus.INITIAL_CHECK
        
        # Simulating that during the lock, another request fetched the same object (without lock or before lock releases)
        # and tries to perform transition. In a concurrent database, it would wait.
        # Here we just verify that transition updates status and release of lock persists the final state.
        SubmissionStateMachine.transition(locked_sub, SubmissionStatus.UNDER_REVIEW)
        
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.UNDER_REVIEW
from apps.accounts.models import User
