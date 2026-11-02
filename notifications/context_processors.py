from django.urls import reverse

from . import services


def notification_bell(request):
    """Context for the public/member bell (skipped inside the admin console)."""
    try:
        admin_path = reverse('admin:index')
    except Exception:
        admin_path = '/admin/'
    if request.path.startswith(admin_path):
        return {}

    try:
        items = services.notification_items(request, services.PUBLIC_SCOPE)
        badge = services.unread_count(request, services.PUBLIC_SCOPE)
    except Exception:
        items, badge = [], 0

    return {
        'notification_items': items,
        'notification_badge': badge,
        'notification_feed_url': reverse('notifications:feed'),
        'notification_history_url': (
            reverse('members:account_notifications')
            if request.user.is_authenticated
            else reverse('notifications:history')
        ),
    }
