"""Chat retention helpers.

The project does not ship a task queue, so the 90-day retention rule is
enforced in two places: the ``cleanup_old_chats`` management command for a
host cron job, and a throttled lazy purge when a chat page is opened. The lazy
purge means chat history still expires on a small single-process deployment
where nobody remembered to add the cron job.
"""

from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from communications.models import Message
from contact.models import ContactMessage
from members.models_comms import CommsComment

RETENTION_DAYS = 90
LAZY_PURGE_CACHE_KEY = 'members:chat-retention:last-run'


def purge_expired_chats(days=RETENTION_DAYS):
    """Delete private chat rows and feed comments older than ``days``.

    Public contact-form enquiries also live in ``ContactMessage`` but have no
    member account, so they are deliberately excluded and kept for the office.
    """
    cutoff = timezone.now() - timedelta(days=max(1, days))
    member_chat, _ = ContactMessage.objects.filter(
        user__isnull=False,
        created_at__lt=cutoff,
    ).delete()
    staff_chat, _ = Message.objects.filter(
        created_at__lt=cutoff,
    ).delete()
    feed_comments, _ = CommsComment.objects.filter(
        created_at__lt=cutoff,
    ).delete()
    return {
        'member_chat': member_chat,
        'staff_chat': staff_chat,
        'feed_comments': feed_comments,
        'days': days,
    }


def purge_expired_chats_once_per_hour():
    """Run retention at most once an hour per process/cache backend."""
    if cache.get(LAZY_PURGE_CACHE_KEY):
        return None
    counts = purge_expired_chats()
    cache.set(LAZY_PURGE_CACHE_KEY, True, 3600)
    return counts
