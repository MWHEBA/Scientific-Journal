import pytest
import json
import hmac
import hashlib
from django.urls import reverse
from apps.submissions.statuses import SubmissionStatus
from apps.submissions.models import ArticleSubmission, ManuscriptFile, AuditLog
from apps.publishing.models import PublishedArticle, PublishedArticleSlugHistory
from apps.reviews.models import Review
from apps.reviews.services import ReviewService
from apps.submissions.services import SubmissionService
from apps.payments.adapters import MockPaymentGatewayAdapter
from apps.payments.models import Payment
from apps.accounts.models import User
from django.core.files.uploadedfile import SimpleUploadedFile

@pytest.mark.django_db
def test_happy_path_full_flow(client_as, author, admin_user, reviewer, journal_section, site_settings, payment_service):
    # 19.1 المسار الكامل بدون تعديل
    client_author = client_as(author)
    client_admin = client_as(admin_user)
    client_reviewer = client_as(reviewer)

    # 1. Author creates draft
    url_create = reverse('submissions:create')
    pdf = SimpleUploadedFile('manuscript.pdf', b'%PDF-1.4 E2E Content', content_type='application/pdf')
    data = {
        'title': 'E2E Happy Path Article',
        'abstract': 'E2E Abstract',
        'corresponding_author_email': author.email,
        'keywords': 'e2e, testing',
        'section': journal_section.pk,
        'action': 'save',
        'manuscript': pdf,
        'coauthor_set-TOTAL_FORMS': '0',
        'coauthor_set-INITIAL_FORMS': '0',
        'coauthor_set-MIN_NUM_FORMS': '0',
        'coauthor_set-MAX_NUM_FORMS': '1000',
    }
    client_author.post(url_create, data)
    sub = ArticleSubmission.objects.get(title='E2E Happy Path Article')
    assert sub.status == SubmissionStatus.DRAFT

    # 2. Author submits
    client_author.post(reverse('submissions:submit', kwargs={'pk': sub.pk}))
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.INITIAL_CHECK

    # 3. Admin passes initial check
    url_check = reverse('dashboard:submission_detail', kwargs={'pk': sub.pk})
    client_admin.post(url_check, {'action': 'pass'})
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.UNDER_REVIEW

    # 4. Admin assigns reviewer
    url_assign = reverse('dashboard:assign_reviewer', kwargs={'pk': sub.pk})
    client_admin.post(url_assign, {'reviewer_id': reviewer.pk})
    sub.refresh_from_db()
    assert sub.assigned_reviewer == reviewer

    # 5. Reviewer accepts
    review = Review.objects.get(submission=sub, reviewer=reviewer)
    url_rev_submit = reverse('reviews:submit', kwargs={'pk': review.pk})
    client_reviewer.post(url_rev_submit, {
        'score_originality': '5',
        'score_relevance': '5',
        'score_clarity': '5',
        'score_language': '5',
        'decision': Review.DECISION_ACCEPT,
        'comments': 'Excellent research.',
    })
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.ACCEPTED

    # 6. Author initiates payment
    url_pay = reverse('payments:initiate', kwargs={'pk': sub.pk})
    client_author.post(url_pay)
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.PAYMENT_PROCESSING
    order_id = sub.payment.gateway_order_id

    # 7. Webhook payment success
    payload = json.dumps({'order_id': order_id, 'status': 'paid'}).encode()
    sig = hmac.HMAC(MockPaymentGatewayAdapter.SECRET_KEY.encode(), payload, hashlib.sha256).hexdigest()
    client_author.post(reverse('payments:webhook'), payload, content_type='application/json', HTTP_X_SIGNATURE=sig)
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.PUBLISHED
    assert PublishedArticle.objects.filter(submission=sub).exists()

    # 19.6 AuditLog يُسجّل كل الخطوات
    assert AuditLog.objects.filter(entity_id=sub.pk).count() >= 5

    # 19.4 PublishedArticle slug فريد
    # Create another article with same title and publish it
    sub2 = ArticleSubmission.objects.create(
        title='E2E Happy Path Article',
        abstract='Abstract',
        author=author,
        section=journal_section,
        corresponding_author_email=author.email,
        status=SubmissionStatus.PAID
    )
    ManuscriptFile.objects.create(submission=sub2, file=pdf, version=1, is_current=True)
    from apps.publishing.services import PublishingService
    pub1 = PublishedArticle.objects.get(submission=sub)
    pub2 = PublishingService.publish(sub2, actor=admin_user)
    assert pub1.slug != pub2.slug
    assert pub2.slug.endswith('-2')

    # 19.5 SlugHistory عند تغيير العنوان
    old_slug = pub2.slug
    pub2.slug = ''  # generate new slug based on new title
    pub2.title = 'Different Title'
    pub2.save()
    assert PublishedArticleSlugHistory.objects.filter(article=pub2, slug=old_slug).exists()
