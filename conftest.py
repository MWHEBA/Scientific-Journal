"""
conftest.py — Fixtures مشتركة لجميع الاختبارات.
لا mocks — كل شيء يستخدم الكود الحقيقي.
"""
import io
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import User, AuthorProfile, ReviewerProfile
from apps.submissions.models import ArticleSubmission, JournalSection, ManuscriptFile
from apps.submissions.statuses import SubmissionStatus
from apps.submissions.state_machine import SubmissionStateMachine
from apps.reviews.models import Review
from apps.payments.models import Payment
from apps.payments.adapters import MockPaymentGatewayAdapter
from apps.payments.services import PaymentService
from apps.pages.models import SiteSettings


# ─── Fixtures المستخدمين ─────────────────────────────────────────────────────

@pytest.fixture
def make_user(db):
    """Factory لإنشاء مستخدمين بأدوار مختلفة."""
    counter = [0]

    def _make(role=User.ROLE_AUTHOR, **kwargs):
        counter[0] += 1
        n = counter[0]
        user = User.objects.create_user(
            username=kwargs.get('username', f'user_{role}_{n}'),
            email=kwargs.get('email', f'user_{role}_{n}@test.com'),
            password='testpass123',
            role=role,
            first_name=kwargs.get('first_name', f'User{n}'),
            last_name=kwargs.get('last_name', 'Test'),
        )
        if role == User.ROLE_AUTHOR:
            AuthorProfile.objects.get_or_create(user=user)
        elif role == User.ROLE_REVIEWER:
            ReviewerProfile.objects.get_or_create(user=user)
        return user

    return _make


@pytest.fixture
def author(make_user):
    return make_user(role=User.ROLE_AUTHOR)


@pytest.fixture
def reviewer(make_user):
    return make_user(role=User.ROLE_REVIEWER)


@pytest.fixture
def admin_user(make_user):
    return make_user(role=User.ROLE_ADMIN)


# ─── Fixtures التقديمات ──────────────────────────────────────────────────────

@pytest.fixture
def journal_section(db):
    section, _ = JournalSection.objects.get_or_create(
        slug='computer-science',
        defaults={'name': 'Computer Science'},
    )
    return section


@pytest.fixture
def pdf_file():
    """ملف PDF وهمي للاختبار."""
    content = b'%PDF-1.4 fake pdf content for testing'
    return SimpleUploadedFile('test_manuscript.pdf', content, content_type='application/pdf')


@pytest.fixture
def make_submission(db, make_user, journal_section):
    """Factory لإنشاء تقديمات بحالات مختلفة."""
    counter = [0]

    def _make(status=SubmissionStatus.DRAFT, author=None, with_manuscript=True, **kwargs):
        counter[0] += 1
        n = counter[0]
        if author is None:
            author = make_user(role=User.ROLE_AUTHOR)

        sub = ArticleSubmission.objects.create(
            title=kwargs.get('title', f'Test Submission {n}'),
            abstract=kwargs.get('abstract', 'Test abstract for submission.'),
            keywords=kwargs.get('keywords', 'test, research, science'),
            section=kwargs.get('section', journal_section),
            author=author,
            status=status,
            revision_count=kwargs.get('revision_count', 0),
        )

        if with_manuscript:
            content = b'%PDF-1.4 fake pdf content'
            f = SimpleUploadedFile(f'manuscript_{n}.pdf', content, content_type='application/pdf')
            ManuscriptFile.objects.create(
                submission=sub,
                file=f,
                version=1,
                is_current=True,
            )

        return sub

    return _make


@pytest.fixture
def make_review(db, make_user):
    """Factory لإنشاء مراجعات."""

    def _make(submission, reviewer=None, is_submitted=False, decision='', **kwargs):
        if reviewer is None:
            reviewer = make_user(role=User.ROLE_REVIEWER)
        review = Review.objects.create(
            submission=submission,
            reviewer=reviewer,
            decision=decision,
            is_submitted=is_submitted,
            revision_round=kwargs.get('revision_round', 1),
        )
        return review

    return _make


@pytest.fixture
def site_settings(db):
    """إعدادات المجلة للاختبار."""
    settings = SiteSettings.get()
    settings.apc_amount = 100
    settings.payment_deadline_days = 30
    settings.save()
    return settings


@pytest.fixture
def mock_gateway():
    """MockPaymentGatewayAdapter للاختبار — بدون API خارجي."""
    return MockPaymentGatewayAdapter()


@pytest.fixture
def payment_service(mock_gateway):
    """PaymentService مع MockGateway."""
    return PaymentService(gateway=mock_gateway)


@pytest.fixture
def make_paid_submission(db, make_submission, make_user, site_settings, payment_service):
    """Factory لإنشاء تقديم وصل لمرحلة paid."""

    def _make():
        author   = make_user(role=User.ROLE_AUTHOR)
        reviewer = make_user(role=User.ROLE_REVIEWER)
        sub = make_submission(status=SubmissionStatus.ACCEPTED, author=author)

        # تعيين payment_deadline
        from django.utils import timezone
        from datetime import timedelta
        sub.payment_deadline = timezone.now() + timedelta(days=30)
        sub.save(update_fields=['payment_deadline'])

        # بدء الدفع
        payment_url = payment_service.initiate_payment(sub, actor=author)
        sub.refresh_from_db()

        # محاكاة نجاح الدفع عبر webhook
        import json
        import hmac
        import hashlib
        order_id = sub.payment.gateway_order_id
        payload = json.dumps({'order_id': order_id, 'status': 'paid'}).encode()
        signature = hmac.HMAC(
            MockPaymentGatewayAdapter.SECRET_KEY.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()
        payment_service.handle_webhook(payload, signature)
        sub.refresh_from_db()
        return sub

    return _make
