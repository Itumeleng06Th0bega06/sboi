"""
Production settings for the Shekinah Blaze site (Render.com).

Run with:  python manage.py runserver --settings=sboi.settings_prod
Deploy as: DJANGO_SETTINGS_MODULE=sboi.settings_prod gunicorn sboi.wsgi:application
"""
import os
import dj_database_url
from dotenv import load_dotenv
from sboi.settings import *  # noqa: F401,F403

# Load a local .env file if present (e.g. for smoke-testing prod settings locally).
# On Render, environment variables are set in the dashboard and this is a no-op.
load_dotenv(BASE_DIR / '.env')

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

DEBUG = False

SECRET_KEY = os.environ['SECRET_KEY']

ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get(
        'ALLOWED_HOSTS',
        'shekinahblaze.org,www.shekinahblaze.org,sboi.onrender.com,.onrender.com',
    ).split(',')
    if h.strip()
]

CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        'CSRF_TRUSTED_ORIGINS',
        'https://shekinahblaze.org,https://www.shekinahblaze.org,https://*.onrender.com',
    ).split(',')
    if o.strip()
]

# Renamed admin URL (secret path in production).
ADMIN_URL = os.environ.get('ADMIN_URL', 'admin/').strip('/') + '/'

# ---------------------------------------------------------------------------
# Security hardening
# ---------------------------------------------------------------------------

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = os.environ.get('SECURE_SSL_REDIRECT', 'true').lower() == 'true'

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'

SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
X_FRAME_OPTIONS = 'DENY'

# ---------------------------------------------------------------------------
# Static files (WhiteNoise) and media (local disk — testing phase)
# ---------------------------------------------------------------------------
#
# Media note: uploaded files live on Render's ephemeral disk and are lost on
# every deploy/restart, and are not served in production. During the testing
# phase this is fine (no admin uploads). Before going live with real uploads,
# switch the default storage to an S3-compatible bucket (django-storages).

STATIC_ROOT = BASE_DIR / 'staticfiles'

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

MIDDLEWARE = [
    'whitenoise.middleware.WhiteNoiseMiddleware',
    *MIDDLEWARE,
]

WHITENOISE_MAX_AGE = 31536000

# ---------------------------------------------------------------------------
# Database (PostgreSQL via DATABASE_URL; Render includes sslmode in the URL)
# ---------------------------------------------------------------------------

DATABASES = {
    'default': dj_database_url.config(conn_max_age=600),
}

# ---------------------------------------------------------------------------
# Email (optional — the site currently stores messages in the DB)
# ---------------------------------------------------------------------------

EMAIL_BACKEND = (
    'django.core.mail.backends.smtp.EmailBackend'
    if os.environ.get('SMTP_HOST')
    else 'django.core.mail.backends.console.EmailBackend'
)
EMAIL_HOST = os.environ.get('SMTP_HOST', '')
EMAIL_PORT = int(os.environ.get('SMTP_PORT', '587'))
EMAIL_HOST_USER = os.environ.get('SMTP_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
EMAIL_USE_TLS = os.environ.get('SMTP_USE_TLS', 'true').lower() == 'true'
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'Shekinah Blaze <no-reply@shekinahblaze.org>')

# ---------------------------------------------------------------------------
# Logging (Render captures stdout/stderr)
# ---------------------------------------------------------------------------

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}