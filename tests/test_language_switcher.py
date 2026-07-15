import pytest
from django.urls import reverse
from django.test import Client, override_settings
from django.conf import settings
from Journal.loaders import _current_language

@pytest.mark.django_db
class TestLanguageSwitcher:
    
    def test_dynamic_template_loader_resolution(self):
        """Test that _current_language context variable correctly resolves template path order."""
        from Journal.loaders import LanguageTemplateLoader
        from django.template import Engine
        
        # Instantiate loader
        engine = Engine.get_default()
        loader = LanguageTemplateLoader(engine)
        
        # Set language to 'en'
        token = _current_language.set('en')
        try:
            dirs = loader.get_dirs()
            # The first directory should be templates/en
            assert any('templates\\en' in str(d) or 'templates/en' in str(d) for d in dirs)
            assert str(dirs[0]).endswith('templates/en') or str(dirs[0]).endswith('templates\\en')
        finally:
            _current_language.reset(token)

        # Set language to 'ar'
        token = _current_language.set('ar')
        try:
            dirs = loader.get_dirs()
            # The first directory should be templates/ar
            assert any('templates\\ar' in str(d) or 'templates/ar' in str(d) for d in dirs)
            assert str(dirs[0]).endswith('templates/ar') or str(dirs[0]).endswith('templates\\ar')
        finally:
            _current_language.reset(token)

    @override_settings(DEBUG=True)
    def test_toggle_language_view_under_debug(self):
        """Test that the toggle-language view switches session/cookie and redirects."""
        client = Client()
        
        # Initial call to toggle from default (ar) to en
        response = client.get('/toggle-language/?next=/')
        assert response.status_code == 302
        assert response.url == '/'
        assert client.session.get('site_language') == 'en'
        assert response.cookies.get('site_language').value == 'en'

        # Call again to toggle from en back to ar
        response = client.get('/toggle-language/?next=/dashboard/')
        assert response.status_code == 302
        assert response.url == '/dashboard/'
        assert client.session.get('site_language') == 'ar'
        assert response.cookies.get('site_language').value == 'ar'

    @override_settings(DEBUG=False)
    def test_toggle_language_view_under_production(self):
        """Test that toggle-language view is forbidden/404 when DEBUG is False."""
        client = Client()
        response = client.get('/toggle-language/?next=/')
        # Since the URL pattern is not added when DEBUG is False, it should return 404
        assert response.status_code == 404

    @override_settings(DEBUG=True)
    def test_floating_button_injection_in_html_under_debug(self):
        """Test that the floating switcher button is injected into HTML responses in debug mode."""
        client = Client()
        # Fetch the homepage
        response = client.get('/')
        assert response.status_code == 200
        # The floating button should be injected
        assert b'dev-lang-switcher' in response.content
        assert b'toggle-language/' in response.content

    @override_settings(DEBUG=False)
    def test_no_floating_button_injection_under_production(self):
        """Test that the floating button is NOT injected when DEBUG is False."""
        client = Client()
        response = client.get('/')
        assert response.status_code == 200
        # The floating button should NOT be injected
        assert b'dev-lang-switcher' not in response.content
