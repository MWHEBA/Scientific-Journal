import pytest
from django.urls import reverse
from apps.accounts.models import User, ReviewerProfile

@pytest.mark.django_db
def test_admin_users_flow(client_as, admin_user, superuser, make_user):
    client = client_as(admin_user)
    url = reverse('dashboard:users')

    # 9.1 إنشاء مستخدم جديد (Admin)
    response = client.post(url, {
        'action': 'create_user',
        'username': 'new_admin_user',
        'email': 'new_admin_user@test.com',
        'first_name': 'New',
        'last_name': 'Admin',
        'role': User.ROLE_ADMIN,
        'password1': 'testpass123',
        'password2': 'testpass123',
    })
    assert response.status_code == 302
    created_user = User.objects.get(username='new_admin_user')
    assert created_user.role == User.ROLE_ADMIN

    # 9.2 إنشاء مستخدم (Reviewer)
    response = client.post(url, {
        'action': 'create_user',
        'username': 'new_rev',
        'email': 'new_rev@test.com',
        'first_name': 'New',
        'last_name': 'Rev',
        'role': User.ROLE_REVIEWER,
        'password1': 'testpass123',
        'password2': 'testpass123',
    })
    assert response.status_code == 302
    created_rev = User.objects.get(username='new_rev')
    assert created_rev.role == User.ROLE_REVIEWER
    assert ReviewerProfile.objects.filter(user=created_rev).exists()

    # 9.3 تغيير دور مشرف إلى مراجع
    response = client.post(url, {
        'action': 'set_role',
        'user_id': created_user.pk,
        'role': User.ROLE_REVIEWER,
    })
    assert response.status_code == 302
    created_user.refresh_from_db()
    assert created_user.role == User.ROLE_REVIEWER
    assert ReviewerProfile.objects.filter(user=created_user).exists()

    # 9.4 تفعيل/تعطيل مستخدم
    response = client.post(url, {
        'action': 'toggle_active',
        'user_id': created_user.pk,
    })
    assert response.status_code == 302
    created_user.refresh_from_db()
    assert created_user.is_active is False

    # 9.5 محاولة تعديل superuser
    response = client.post(url, {
        'action': 'set_role',
        'user_id': superuser.pk,
        'role': User.ROLE_AUTHOR,
    })
    assert response.status_code == 302
    superuser.refresh_from_db()
    assert superuser.role == User.ROLE_ADMIN

    # 9.6 محاولة تعطيل superuser
    response = client.post(url, {
        'action': 'toggle_active',
        'user_id': superuser.pk,
    })
    assert response.status_code == 302
    superuser.refresh_from_db()
    assert superuser.is_active is True

    # 9.7 Admin يحاول تعديل نفسه
    response = client.post(url, {
        'action': 'toggle_active',
        'user_id': admin_user.pk,
    })
    assert response.status_code == 302
    admin_user.refresh_from_db()
    assert admin_user.is_active is True

    # 9.8 بحث المستخدمين بالاسم
    response = client.get(url + '?q=new_admin')
    assert response.status_code == 200
    assert 'new_admin' in response.content.decode()

    # 9.9 فلترة بالدور
    # بما أن الصفحة تعرض الإداريين فقط، نتحقق من أن المراجع غير معروض
    response = client.get(url)
    assert response.status_code == 200
    assert 'new_rev@test.com' not in response.content.decode()
