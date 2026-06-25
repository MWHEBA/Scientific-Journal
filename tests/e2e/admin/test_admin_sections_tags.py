import pytest
from django.urls import reverse
from apps.submissions.models import JournalSection
from taggit.models import Tag


@pytest.mark.django_db
def test_admin_sections_crud_flow(client_as, admin_user):
    client = client_as(admin_user)

    # 1. Create a section
    url_sections = reverse('dashboard:sections')
    response = client.post(url_sections, {
        'name': 'العلوم الإدارية والتسويق',
        'slug': 'admin-marketing',
        'order': 5
    })
    assert response.status_code == 302
    assert JournalSection.objects.filter(slug='admin-marketing').exists()
    section = JournalSection.objects.get(slug='admin-marketing')
    assert section.name == 'العلوم الإدارية والتسويق'
    assert section.order == 5

    # 2. Try creating a section with duplicate slug
    response = client.post(url_sections, {
        'name': 'العلوم الإدارية فقط',
        'slug': 'admin-marketing',
        'order': 10
    })
    # Since model unique validation fails on form submit, it re-renders form with 200 code
    assert response.status_code == 200
    assert JournalSection.objects.filter(slug='admin-marketing').count() == 1

    # 3. Update a section
    url_update = reverse('dashboard:section_update', kwargs={'pk': section.pk})
    response = client.post(url_update, {
        'name': 'العلوم الإدارية الجديدة',
        'slug': 'admin-marketing-new',
        'order': 15
    })
    assert response.status_code == 302
    section.refresh_from_db()
    assert section.name == 'العلوم الإدارية الجديدة'
    assert section.slug == 'admin-marketing-new'
    assert section.order == 15

    # 4. Delete a section
    url_delete = reverse('dashboard:section_delete', kwargs={'pk': section.pk})
    response = client.post(url_delete)
    assert response.status_code == 302
    assert not JournalSection.objects.filter(pk=section.pk).exists()


@pytest.mark.django_db
def test_admin_tags_crud_flow(client_as, admin_user):
    client = client_as(admin_user)

    # 1. Create a tag
    url_tags = reverse('dashboard:tags')
    response = client.post(url_tags, {
        'name': 'الذكاء الاصطناعي',
        'slug': 'ai-tag'
    })
    assert response.status_code == 302
    assert Tag.objects.filter(slug='ai-tag').exists()
    tag = Tag.objects.get(slug='ai-tag')
    assert tag.name == 'الذكاء الاصطناعي'

    # 2. Update a tag
    url_update = reverse('dashboard:tag_update', kwargs={'pk': tag.pk})
    response = client.post(url_update, {
        'name': 'الذكاء الاصطناعي والتعلم الآلي',
        'slug': 'ai-ml-tag'
    })
    assert response.status_code == 302
    tag.refresh_from_db()
    assert tag.name == 'الذكاء الاصطناعي والتعلم الآلي'
    assert tag.slug == 'ai-ml-tag'

    # 3. Delete a tag
    url_delete = reverse('dashboard:tag_delete', kwargs={'pk': tag.pk})
    response = client.post(url_delete)
    assert response.status_code == 302
    assert not Tag.objects.filter(pk=tag.pk).exists()
