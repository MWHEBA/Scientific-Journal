import pytest
from django.urls import reverse
from apps.accounts.models import User

@pytest.mark.django_db
def test_admin_authors_dashboard_flow(client_as, admin_user):
    client = client_as(admin_user)
    
    # إنشاء بعض المستخدمين بدور مؤلف
    author1 = User.objects.create_user(
        username='author_test_1',
        email='author1@test.com',
        password='password123',
        role=User.ROLE_AUTHOR,
        first_name='أحمد',
        last_name='علي'
    )
    author2 = User.objects.create_user(
        username='author_test_2',
        email='author2@test.com',
        password='password123',
        role=User.ROLE_AUTHOR,
        first_name='سارة',
        last_name='أحمد'
    )
    
    # 1. الوصول لصفحة إدارة المؤلفين
    url = reverse('dashboard:admin_authors')
    response = client.get(url)
    assert response.status_code == 200
    assert author1.username in response.content.decode('utf-8')
    assert author2.username in response.content.decode('utf-8')
    
    # 2. البحث عن مؤلف
    response_search = client.get(url, {'q': 'سارة'})
    assert response_search.status_code == 200
    assert 'سارة' in response_search.content.decode('utf-8')
    assert 'author_test_2' in response_search.content.decode('utf-8')
    
    # 3. تفعيل / تعطيل الحساب عن طريق الـ POST
    assert author1.is_active is True
    
    # تعطيل الحساب
    response_post = client.post(url, {'user_id': author1.pk})
    assert response_post.status_code == 302
    author1.refresh_from_db()
    assert author1.is_active is False
    
    # تفعيل الحساب مجدداً
    response_post_reactivate = client.post(url, {'user_id': author1.pk})
    assert response_post_reactivate.status_code == 302
    author1.refresh_from_db()
    assert author1.is_active is True
    
    # 4. محاولة مؤلف آخر الوصول لصفحة الإدارة (يجب أن يفشل 403)
    author_client = client_as(author2)
    response_forbidden = author_client.get(url)
    assert response_forbidden.status_code == 403
