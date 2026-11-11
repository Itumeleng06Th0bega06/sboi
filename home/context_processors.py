from django.db import DatabaseError, transaction
from django.urls import NoReverseMatch, reverse

from about.models import ChurchProfile
from contact.models import ContactInfo

# Kept for the membership service's cache invalidation hook. The new bell uses
# per-user notification rows and no longer serves stale cached counts, but the
# constant remains part of the existing public API.
NOTIFICATIONS_CACHE_KEY = 'admin_notifications'
NOTIFICATIONS_CACHE_TTL = 45


def build_admin_notifications():
    """Category summaries for callers that still want the old shape.

    The live bell uses the shared notification service instead; this helper
    exists only for backwards-compatible imports.
    """
    from notifications.models import Notification
    from notifications.services import open_notifications

    rows = []
    seen = set()
    for notification in open_notifications('staff').filter(
        recipient__isnull=True,
    ).order_by('category', '-created_at'):
        if notification.category in seen:
            continue
        seen.add(notification.category)
        rows.append({
            'label': notification.title,
            'count': open_notifications('staff').filter(
                recipient__isnull=True,
                category=notification.category,
            ).count(),
            'url': notification.url,
            'icon': notification.icon,
            'tone': notification.tone,
            'permission': notification.permission,
        })
    return rows


def notifications_for_user(user):
    """Serialised open staff notifications for one user (no request state)."""
    from notifications import services

    return [
        services.serialize(notification)
        for notification in services.visible_notifications(
            user, services.STAFF_SCOPE,
        ).select_related('recipient')
    ]


def site_info(request):
    return {
        'site_profile': ChurchProfile.objects.first(),
        'site_contact': ContactInfo.objects.first(),
    }


def admin_notifications(request):
    """Navbar shortcuts and notification counts for signed-in staff."""
    try:
        admin_path = reverse('admin:index')
    except NoReverseMatch:
        admin_path = '/admin/'
    if not request.path.startswith(admin_path) or not request.user.is_authenticated:
        return {}

    def quick_action(label, icon, add_view_name, permission):
        return {
            'label': label,
            'icon': icon,
            'url': reverse(add_view_name),
            'permission': permission,
        }

    quick_actions = [
        quick_action(
            'Add devotion', 'book', 'admin:blackboard_devotion_add',
            'blackboard.manage_blackboard',
        ),
        quick_action(
            'Add event', 'calendar', 'admin:blackboard_event_add',
            'blackboard.manage_blackboard',
        ),
        quick_action(
            'Add sermon', 'video', 'admin:blackboard_sermon_add',
            'blackboard.manage_blackboard',
        ),
        quick_action(
            'Add announcement', 'bullhorn', 'admin:blackboard_announcement_add',
            'blackboard.manage_blackboard',
        ),
        quick_action(
            'Add slider image', 'image', 'admin:gallery_sliderimage_add',
            'gallery.manage_gallery',
        ),
        quick_action(
            'Message a member', 'mail',
            'admin:contact_contactmessage_compose',
            'contact.manage_contact_messages',
        ),
    ]
    quick_actions = [
        action for action in quick_actions
        if request.user.has_perm(action['permission'])
    ]

    from notifications import services

    services.sync_admin_messages_for_user(request.user)
    items = services.notification_items(request, services.STAFF_SCOPE)
    badge = services.unread_count(request, services.STAFF_SCOPE)
    communications = {'allowed': False, 'url': '', 'unread': 0}
    try:
        with transaction.atomic():
            from communications.services import can_use_portal, unread_summary

            if can_use_portal(request.user):
                total, latest_conversation = unread_summary(request.user)
                inbox_url = reverse('communications:inbox')
                communications = {
                    'allowed': True,
                    'url': (
                        f'{inbox_url}?conversation={latest_conversation}'
                        if latest_conversation else inbox_url
                    ),
                    'unread': total,
                }
    except DatabaseError:
        # The portal is optional on a fresh install; the rest of the admin
        # console must still render if its tables have not been migrated yet.
        pass
    return {
        'admin_dashboard': {
            'quick_actions': quick_actions,
            'notifications': items,
            'notification_badge': badge,
            'notification_history_url': reverse('admin_notifications_history'),
            'communications': communications,
        },
    }
