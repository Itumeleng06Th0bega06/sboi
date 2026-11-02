from django.core.management.base import BaseCommand

from notifications import services


class Command(BaseCommand):
    help = 'Back-fill and reconcile notifications from existing records.'

    def handle(self, *args, **options):
        count = services.sync_notifications()
        self.stdout.write(
            self.style.SUCCESS(f'Notifications reconciled ({count} total records).')
        )
