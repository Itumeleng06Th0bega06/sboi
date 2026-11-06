"""Delete private chat history after the three-month retention window.

The church office keeps conversations for 90 days. Feed posts are deliberately
kept because they are announcements; only the comment thread under them (which
behaves like chat) is expired with the conversations.
"""

from django.core.management.base import BaseCommand

from members.retention import RETENTION_DAYS, purge_expired_chats


class Command(BaseCommand):
    help = 'Delete chat messages and feed comments older than 3 months.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=RETENTION_DAYS,
            help=f'Retention window in days (default: {RETENTION_DAYS}).',
        )

    def handle(self, *args, **options):
        counts = purge_expired_chats(options['days'])
        self.stdout.write(self.style.SUCCESS(
            f"Deleted {counts['member_chat']} member/admin message(s), "
            f"{counts['staff_chat']} staff message(s) and "
            f"{counts['feed_comments']} feed comment(s) older than "
            f"{counts['days']} days."
        ))
