"""Print a one-time admin password-reset link (no email server required).

Use this when the reset email cannot be delivered (no ``SMTP_HOST`` configured)
or when you are locked out and cannot reach the inbox. The link behaves exactly
like the one the site emails out: open it while signed out and choose a new
password. It can only be used once.

On cPanel run it through the manage_prod.py wrapper:

    manage_prod.py reset_admin_password <username>

The link is printed to stdout (cPanel -> Setup Python App -> "Run Python
script", or from a Cron job whose output is emailed to you).
"""
import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


def _default_site_url():
    override = os.environ.get('SITE_URL')
    if override:
        return override.rstrip('/')
    scheme = 'http' if settings.DEBUG else 'https'
    hosts = [h for h in settings.ALLOWED_HOSTS if h and not h.startswith('.')]
    host = hosts[0] if hosts else 'localhost'
    if settings.DEBUG and ':' not in host:
        host = f'{host}:8000'
    return f'{scheme}://{host}'


class Command(BaseCommand):
    help = (
        'Print a one-time admin password-reset URL for a user. Works without '
        'an email server, for when the reset email cannot be sent.'
    )

    def add_arguments(self, parser):
        parser.add_argument('username', help='The admin username to reset.')
        parser.add_argument(
            '--site-url',
            default='',
            help='Base URL to prefix the link with (defaults to SITE_URL, or '
                 'the first non-wildcard ALLOWED_HOSTS entry).',
        )

    def handle(self, *args, **options):
        username = options['username']
        User = get_user_model()
        try:
            user = User.objects.get_by_natural_key(username)
        except User.DoesNotExist:
            raise CommandError(f'No user named "{username}".')
        if not user.is_staff:
            raise CommandError(f'"{username}" is not a staff user.')

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        path = reverse(
            'admin_password_reset_confirm',
            kwargs={'uidb64': uid, 'token': token},
        )
        base = (options['site_url'] or _default_site_url()).rstrip('/')

        self.stdout.write(self.style.SUCCESS('One-time password-reset link:'))
        self.stdout.write(f'{base}{path}')
        self.stdout.write(
            f'For "{user.get_username()}". Open it while signed out, then set '
            'a new password. It can only be used once.'
        )
