import re
from django.conf import settings
from django.utils import translation
from Journal.loaders import _current_language

class LanguageMiddleware:
    """
    Middleware that manages the dynamic language context in development.
    If DEBUG is True, it allows switching between Arabic and English
    using session or cookie, and injects a floating toggle button into HTML pages.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        lang = None
        
        # Only allow dynamic language switching in development
        if settings.DEBUG:
            lang = request.session.get('site_language') or request.COOKIES.get('site_language')
            # Check for query parameter override
            if 'lang' in request.GET:
                override_lang = request.GET['lang']
                if override_lang in ['ar', 'en']:
                    lang = override_lang
                    request.session['site_language'] = lang
        
        # Fallback to the configured default site language
        if not lang:
            lang = settings.SITE_LANGUAGE
            
        # Set the thread-safe context variable for the template loader
        token = _current_language.set(lang)
        
        # Activate the translation language context in Django
        translation.activate(lang)
        
        try:
            response = self.get_response(request)
            
            # Inject the floating switcher button in development HTML responses
            if (settings.DEBUG and 
                    response.status_code == 200 and 
                    'text/html' in response.headers.get('Content-Type', '')):
                
                # Check for django-admin pages or non-standard HTML to avoid injecting there if necessary,
                # but injecting in dashboard and public pages is correct. Let's exclude admin path to be safe.
                if not request.path.startswith('/admin/'):
                    self.inject_toggle_button(request, response, lang)
                    
            return response
        finally:
            translation.deactivate()
            _current_language.reset(token)

    def inject_toggle_button(self, request, response, current_lang):
        try:
            content = response.content.decode('utf-8')
        except UnicodeDecodeError:
            return  # If decoding fails, skip injection to avoid raising exceptions
            
        # Determine target language and button text
        target_lang = 'en' if current_lang == 'ar' else 'ar'
        label = 'English' if current_lang == 'ar' else 'العربية'
        
        # Create a professional, clean floating button aligned to the bottom-right/left
        # CSS variables from tokens.css are used for all colors, fonts, and shadows.
        # Gradients are avoided, adhering to flat colors only.
        button_html = f"""
        <!-- DEV ONLY: Dynamic Language Switcher -->
        <div id="dev-lang-switcher" style="
            position: fixed;
            bottom: var(--space-6);
            right: var(--space-6);
            z-index: 999999;
            direction: ltr;
            font-family: inherit;
        ">
            <a href="/toggle-language/?next={request.path}" style="
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-4);
                background-color: var(--color-primary);
                color: var(--color-text-inverse);
                border: 1px solid var(--color-primary-dark);
                border-radius: var(--radius-sm);
                font-size: var(--text-sm);
                font-weight: 500;
                text-decoration: none;
                box-shadow: var(--shadow-md);
                cursor: pointer;
                transition: background-color var(--transition);
            " onmouseover="this.style.backgroundColor='var(--color-primary-dark)'" onmouseout="this.style.backgroundColor='var(--color-primary)'">
                <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round" style="display: block;">
                    <circle cx="12" cy="12" r="10"></circle>
                    <line x1="2" y1="12" x2="22" y2="12"></line>
                    <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>
                </svg>
                <span>{label}</span>
                <span style="font-size: 9px; opacity: 0.8; border: 1px solid var(--color-border-light); padding: 1px 4px; border-radius: 2px;">DEV</span>
            </a>
        </div>
        """
        
        # Inject the button right before </body>
        body_close_tag = '</body>'
        pattern = re.compile(re.escape(body_close_tag), re.IGNORECASE)
        parts = pattern.split(content)
        if len(parts) > 1:
            new_content = parts[0] + button_html + body_close_tag + body_close_tag.join(parts[1:])
            response.content = new_content.encode('utf-8')
