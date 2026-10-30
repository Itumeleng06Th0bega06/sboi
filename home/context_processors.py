from datetime import timedelta

from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from about.models import ChurchProfile
from contact.models import ContactInfo

# Cache window for the admin notification bell counts.
NOTIFICATIONS_CACHE_KEY = 'admin_notifications'
NOTIFICATIONS_CACHE_TTL = 45


def build_admin_notifications():
    """Admin notification items used by the bell's JSON API.

    Returns six fixed rows (labels always present) whose counts are cached
    briefly (45s) so admin page loads and the bell's periodic polling cost
    near-zero DB work; badges may lag by up to a minute, which is fine for
    this purpose.
    """
    cached = cache.get(NOTIFICATIONS_CACHE_KEY)
    if cached is not None:
        return cached

    from blackboard.models import EventRsvp, MemberProfile
    from contact.models import ContactMessage

    from .models import Subscriber, Testimony

    week = timezone.now() - timedelta(days=7)

    def item(label, queryset, view_name, icon, tone, permission):
        return {
            'label': label,
            'count': queryset.count(),
            'url': reverse(view_name),
            'icon': icon,
            'tone': tone,
            'permission': permission,
        }

    notifications = [
        item(
            'Unread contact messages',
            ContactMessage.objects.filter(is_read=False),
            'admin:contact_contactmessage_changelist',
            'mail',
            'attention',
            'contact.manage_contact_messages',
        ),
        item(
            'Pending testimonies',
            Testimony.objects.filter(is_approved=False),
            'admin:home_testimony_changelist',
            'message',
            'attention',
            'home.manage_testimonies',
        ),
        item(
            'Blocked / suspended members',
            MemberProfile.objects.exclude(status='active'),
            'admin:blackboard_memberprofile_changelist',
            'user-slash',
            'warning',
            'blackboard.manage_member_access',
        ),
        item(
            'New newsletter subscribers (7 days)',
            Subscriber.objects.filter(subscribed_at__gte=week),
            'admin:home_subscriber_changelist',
            'mail-open',
            'info',
            'home.manage_subscribers',
        ),
        item(
            'New event RSVPs (7 days)',
            EventRsvp.objects.filter(created_at__gte=week),
            'admin:blackboard_eventrsvp_changelist',
            'clipboard',
            'info',
            'blackboard.manage_rsvps',
        ),
        item(
            'New members (7 days)',
            MemberProfile.objects.filter(created_at__gte=week),
            'admin:blackboard_memberprofile_changelist',
            'id-card',
            'info',
            'blackboard.manage_member_access',
        ),
    ]
    cache.set(NOTIFICATIONS_CACHE_KEY, notifications, NOTIFICATIONS_CACHE_TTL)
    return notifications


def notifications_for_user(user):
    """Hide counts/links for areas the staff member cannot open."""
    return [
        item for item in build_admin_notifications()
        if user.has_perm(item['permission'])
    ]


def site_info(request):
    return {
        'site_profile': ChurchProfile.objects.first(),
        'site_contact': ContactInfo.objects.first(),
    }


def admin_notifications(request):
    """Navbar shortcuts and notification counts for signed-in staff.

    The dashboard itself is generated from the full section list; this context
    only supplies the quick-add menu and bell. Both are filtered by the same
    area permissions so an unassigned staff member never sees a working
    shortcut or a count for an area they cannot open.
    """
    try:
        admin_path = reverse('admin:index')
    except Exception:
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
    ]
    quick_actions = [
        action for action in quick_actions
        if request.user.has_perm(action['permission'])
    ]
    notifications = notifications_for_user(request.user)
    return {
        'admin_dashboard': {
            'quick_actions': quick_actions,
            'notifications': notifications,
            'notification_badge': sum(
                item['count'] for item in notifications
                if item['tone'] in ('attention', 'warning')
            ),
        },
    }
