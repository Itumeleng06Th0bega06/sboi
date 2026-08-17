import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        'Create a superuser from SUPERUSER_EMAIL and SUPERUSER_PASSWORD '
        'environment variables (idempotent — skips if the user already exists).'
    )

    def handle(self, *args, **options):
        email = os.environ.get('SUPERUSER_EMAIL')
        password = os.environ.get('SUPERUSER_PASSWORD')

        if not email or not password:
            raise CommandError(
                'SUPERUSER_EMAIL and SUPERUSER_PASSWORD must be set in the '
                'environment (Render -> Environment -> Add Environment Variable).'
            )

        User = get_user_model()
        username = os.environ.get('SUPERUSER_USERNAME') or email.split('@')[0]

        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.WARNING(f'Superuser "{username}" already exists — skipping.'))
            return

        User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
        )
        self.stdout.write(self.style.SUCCESS(f'Superuser "{username}" created.'))
