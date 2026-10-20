"""
Production settings for the Shekinah Blaze site on shared cPanel hosting.

  * Database .... MariaDB / MySQL (via the pure-Python PyMySQL driver)
  * Static ........ collected into ``staticfiles/`` and served by WhiteNoise
  * Uploaded media  served by Apache from ``public_html/media``
  * WSGI .......... run by Phusion Passenger through ``passenger_wsgi.py``

Every command runs with this settings module, e.g.::

    python manage.py migrate --settings=sboi.settings_prod
    python manage.py collectstatic --settings=sboi.settings_prod

Configuration comes from a ``.env`` file in the project root (copy
``.env.example`` and fill it in). See DEPLOYMENT.md for the full walkthrough.
"""
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

from sboi.settings import *  # noqa: F401,F403

# Load the environment variables created from .env.example.
load_dotenv(BASE_DIR / '.env')

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

DEBUG = False

SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    raise ImproperlyConfigured(
        'SECRET_KEY is not set. Copy .env.example to .env and set SECRET_KEY '
        'to a long random string. Generate one with:\n'
        '  python -c "from django.core.management.utils import '
        'get_random_secret_key; print(get_random_secret_key())"'
    )

ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get(
        'ALLOWED_HOSTS',
        'shekinahblaze.org,www.shekinahblaze.org,mail.shekinahblaze.org,.shekinahblaze.org',
    ).split(',')
    if h.strip()
]

CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        'CSRF_TRUSTED_ORIGINS',
        'https://shekinahblaze.org,https://www.shekinahblaze.org',
    ).split(',')
    if o.strip()
]

# Renamed admin URL (unguessable secret path in production).
ADMIN_URL = os.environ.get('ADMIN_URL', 'admin/').strip('/') + '/'

# ---------------------------------------------------------------------------
# Security hardening
# ---------------------------------------------------------------------------

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
# Set SECURE_SSL_REDIRECT=false in .env if cPanel's AutoSSL/redirect setup
# causes a redirect loop (Django -> HTTPS -> Django).
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
# Static files (collected into the project, served by WhiteNoise)
# ---------------------------------------------------------------------------
#
# Static files are collected into ``staticfiles/`` next to manage.py and served
# by WhiteNoise through Passenger. They deliberately do NOT go into
# public_html, which is left for uploads only.
#
# Run once after every deploy that changes static files:
#   python manage.py collectstatic --noinput --settings=sboi.settings_prod

PUBLIC_HTML = Path(os.environ.get('PUBLIC_HTML') or (Path.home() / 'public_html'))

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# ---------------------------------------------------------------------------
# Uploaded media (served directly by Apache from public_html/media)
# ---------------------------------------------------------------------------
#
# Uploads are the only thing kept in the web root: Apache returns them directly
# without waking Django. Override PUBLIC_HTML in .env if the layout differs.

MEDIA_URL = '/media/'
MEDIA_ROOT = PUBLIC_HTML / 'media'

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    # See sboi/storage.py: non-strict manifest storage tolerates templates
    # that request bare directory paths which can never exist in the manifest;
    # strict mode would 500 the page that references them.
    'staticfiles': {
        'BACKEND': 'sboi.storage.NonStrictManifestStaticFilesStorage',
    },
}

# WhiteNoise serves the collected static files. They live in the project rather
# than public_html, so Apache never sees them and Passenger must serve them.
# It belongs directly after SecurityMiddleware (Django's recommended order).
MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')

WHITENOISE_MAX_AGE = 31536000

# ---------------------------------------------------------------------------
# Database (MariaDB / MySQL)
# ---------------------------------------------------------------------------

DB_NAME = os.environ.get('DB_NAME', '')
if not DB_NAME:
    raise ImproperlyConfigured(
        'DB_NAME is not set. Create a database and user in cPanel -> MySQL '
        'Databases, then put DB_NAME, DB_USER and DB_PASSWORD in .env.'
    )

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': DB_NAME,
        'USER': os.environ.get('DB_USER', ''),
        'PASSWORD': os.environ.get('DB_PASSWORD', ''),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '3306'),
        'OPTIONS': {
            'charset': 'utf8mb4',
            # Django expects strict mode; this mirrors the recommendation in
            # the Django MySQL notes.
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
        },
        # Persistent connections are off by default: shared cPanel MariaDB
        # instances cap connections per user. Raise DB_CONN_MAX_AGE in .env if
        # the host allows it.
        'CONN_MAX_AGE': int(os.environ.get('DB_CONN_MAX_AGE', '0')),
        'CONN_HEALTH_CHECKS': True,
    },
}

# ---------------------------------------------------------------------------
# Email (optional — the site stores contact messages in the DB)
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

# Admin/site email address. Receives Django error reports (when DEBUG=False)
# and is used as the "from" address for outgoing mail. Override via
# ADMIN_EMAIL in .env.
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@shekinahblaze.org')
ADMINS = [('Shekinah Blaze Admin', ADMIN_EMAIL)]
MANAGERS = ADMINS
SERVER_EMAIL = ADMIN_EMAIL
DEFAULT_FROM_EMAIL = os.environ.get(
    'DEFAULT_FROM_EMAIL', f'Shekinah Blaze <{ADMIN_EMAIL}>'
)

# ---------------------------------------------------------------------------
# Logging (Passenger captures stderr into the app's error log)
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
