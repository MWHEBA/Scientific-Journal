import pytest
from django.urls import reverse
from apps.accounts.models import User

@pytest.mark.django_db
def test_admin_impersonation_flow(client_as, superuser, admin_user, author):
    # 13.1 SuperUser يدخل كمؤلف
    client = client_as(superuser)
    url_start = reverse('dashboard:impersonate_start', kwargs={'pk': author.pk})
    response = client.post(url_start)
    assert response.status_code == 302
    assert client.session['impersonator_user_id'] == superuser.pk
    # check we are logged in as author now (request.user should be author)
    # in django client test, client.session contains the session data,
    # and the user logged in can be verified by requesting a view and checking context or user_id
    response_home = client.get(reverse('dashboard:home'))
    assert response_home.status_code == 302 # redirect based on user role (author redirects to author dashboard)

    # 13.2 العودة للـ SuperUser
    url_stop = reverse('dashboard:impersonate_stop')
    response_stop = client.post(url_stop)
    assert response_stop.status_code == 302
    assert 'impersonator_user_id' not in client.session

    # 13.3 Admin عادي لا يملك Impersonation
    client_admin = client_as(admin_user)
    response_admin = client_admin.post(url_start)
    assert response_admin.status_code == 403  # SuperUserRequiredMixin raises 403

    # 13.4 Impersonation لنفس الحساب
    url_self = reverse('dashboard:impersonate_start', kwargs={'pk': superuser.pk})
    client_super = client_as(superuser)
    response_self = client_super.post(url_self)
    assert response_self.status_code == 302
    assert 'impersonator_user_id' not in client_super.session  # Impersonation failed

    # 13.5 إيقاف Impersonation بدون جلسة
    client_no_session = client_as(superuser)
    response_no = client_no_session.post(url_stop)
    assert response_no.status_code == 302  # redirects with error message
