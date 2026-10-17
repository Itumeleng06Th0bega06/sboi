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

    def item(label, queryset, view_name, icon, tone):
        return {
            'label': label,
            'count': queryset.count(),
            'url': reverse(view_name),
            'icon': icon,
            'tone': tone,
        }

    notifications = [
        item(
            'Unread contact messages',
            ContactMessage.objects.filter(is_read=False),
            'admin:contact_contactmessage_changelist',
            'fa-solid fa-envelope',
            'attention',
        ),
        item(
            'Pending testimonies',
            Testimony.objects.filter(is_approved=False),
            'admin:home_testimony_changelist',
            'fa-solid fa-comment-dots',
            'attention',
        ),
        item(
            'Blocked / suspended members',
            MemberProfile.objects.exclude(status='active'),
            'admin:blackboard_memberprofile_changelist',
            'fa-solid fa-user-slash',
            'warning',
        ),
        item(
            'New newsletter subscribers (7 days)',
            Subscriber.objects.filter(subscribed_at__gte=week),
            'admin:home_subscriber_changelist',
            'fa-solid fa-envelope-open-text',
            'info',
        ),
        item(
            'New event RSVPs (7 days)',
            EventRsvp.objects.filter(created_at__gte=week),
            'admin:blackboard_eventrsvp_changelist',
            'fa-solid fa-clipboard-check',
            'info',
        ),
        item(
            'New members (7 days)',
            MemberProfile.objects.filter(created_at__gte=week),
            'admin:blackboard_memberprofile_changelist',
            'fa-solid fa-id-card',
            'info',
        ),
    ]
    cache.set(NOTIFICATIONS_CACHE_KEY, notifications, NOTIFICATIONS_CACHE_TTL)
    return notifications


def site_info(request):
    return {
        'site_profile': ChurchProfile.objects.first(),
        'site_contact': ContactInfo.objects.first(),
    }


def admin_notifications(request):
    """Quick "add" shortcuts for the admin navbar's quick-actions menu.

    The admin dashboard is now generated from the (permission-filtered)
    sidebar menu, so no dashboard widgets are built here. The notification
    bell fetches its own data from the notifications JSON API.
    """
    try:
        admin_path = reverse('admin:index')
    except Exception:
        admin_path = '/admin/'
    if not request.path.startswith(admin_path):
        return {}

    def quick_action(label, icon, add_view_name):
        return {'label': label, 'icon': icon, 'url': reverse(add_view_name)}

    return {
        'admin_dashboard': {
            'quick_actions': [
                quick_action('Add devotion', 'fa-solid fa-book-bible', 'admin:blackboard_devotion_add'),
                quick_action('Add event', 'fa-solid fa-calendar-plus', 'admin:blackboard_event_add'),
                quick_action('Add sermon', 'fa-solid fa-microphone-lines', 'admin:blackboard_sermon_add'),
                quick_action('Add announcement', 'fa-solid fa-bullhorn', 'admin:blackboard_announcement_add'),
                quick_action('Add slider image', 'fa-solid fa-photo-film', 'admin:gallery_sliderimage_add'),
            ],
        },
    }
