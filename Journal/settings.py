"""
Django settings for Journal project.
"""

from pathlib import Path
import environ

BASE_DIR = Path(__file__).resolve().parent.parent

# Initialize environ
env = environ.Env()
# Read env file if it exists
environ.Env.read_env(BASE_DIR / '.env')

SECRET_KEY = env('SECRET_KEY', default="django-insecure-s)jv^rezs#!*0d427()-u7t$ki$6)^#shf(ck&#!3rw2=kic1t")

DEBUG = env.bool('DEBUG', default=True)

SITE_LANGUAGE = env('SITE_LANGUAGE', default='ar')

ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=[])

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "crispy_forms",
    "crispy_bootstrap5",
    # Local apps
    "apps.accounts",
    "apps.submissions",
    "apps.reviews",
    "apps.payments",
    "apps.publishing",
    "apps.notifications",
    "apps.dashboard",
    "taggit",
    "apps.pages",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "Journal.middleware.LanguageMiddleware",
]

ROOT_URLCONF = "Journal.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": False,
        "OPTIONS": {
            "loaders": [
                "Journal.loaders.LanguageTemplateLoader",
                "django.template.loaders.app_directories.Loader",
            ],
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.notifications.context_processors.unread_notifications_count",
                "apps.pages.context_processors.public_context",
                "apps.dashboard.context_processors.impersonation_context",
            ],
        },
    },
]

WSGI_APPLICATION = "Journal.wsgi.application"

DATABASES = {
    "default": env.db('DATABASE_URL', default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ar" if SITE_LANGUAGE == "ar" else "en-us"
TIME_ZONE = "Africa/Cairo"
USE_I18N = True
USE_TZ = True

# Static & Media
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = env('STATIC_ROOT', default=str(BASE_DIR / "staticfiles"))

MEDIA_URL = "media/"
MEDIA_ROOT = env('MEDIA_ROOT', default=str(BASE_DIR / "media"))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Custom User Model
AUTH_USER_MODEL = "accounts.User"

# Crispy Forms
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

# Email Settings
EMAIL_BACKEND = env('EMAIL_BACKEND', default="django.core.mail.backends.console.EmailBackend")
if EMAIL_BACKEND == "django.core.mail.backends.smtp.EmailBackend":
    EMAIL_HOST = env('EMAIL_HOST')
    EMAIL_PORT = env.int('EMAIL_PORT', default=587)
    EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)
    EMAIL_HOST_USER = env('EMAIL_HOST_USER')
    EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD')
    DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default=EMAIL_HOST_USER)

# Auth redirects
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/dashboard/author/"
LOGOUT_REDIRECT_URL = "/"

# Authentication Backends
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]
