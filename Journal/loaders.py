import contextvars
from django.conf import settings
from django.template.loaders.filesystem import Loader as FilesystemLoader

# Thread-safe context variable to store the current language preference
_current_language = contextvars.ContextVar('current_language', default=None)

class LanguageTemplateLoader(FilesystemLoader):
    """
    A custom template loader that dynamically changes the search directory
    based on the current thread/request language preference.
    """
    def get_dirs(self):
        lang = _current_language.get() or settings.SITE_LANGUAGE
        base_dir = settings.BASE_DIR
        return [
            base_dir / f"templates/{lang}",
            base_dir / "templates/common",
            base_dir / "templates",
        ]
