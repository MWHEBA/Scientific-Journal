import pytest
from apps.accounts.models import User

@pytest.fixture
def client_as():
    """Helper: يُعيد client مسجّل دخوله بدور محدد."""
    from django.test import Client
    def _login(user):
        c = Client()
        c.force_login(user)
        return c
    return _login

@pytest.fixture
def superuser(make_user):
    """SuperUser لاختبارات الـ Impersonation."""
    user = make_user(role=User.ROLE_ADMIN)
    user.is_superuser = True
    user.save()
    return user

@pytest.fixture
def second_author(make_user):
    """مؤلف ثانٍ لاختبارات الـ isolation."""
    return make_user(role=User.ROLE_AUTHOR)

@pytest.fixture
def second_reviewer(make_user):
    """مراجع ثانٍ لاختبارات تعارض التعيين."""
    return make_user(role=User.ROLE_REVIEWER)
