from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from about.models import ChurchProfile
from contact.models import ContactInfo


def build_admin_notifications():
    """Every site notification shown in the admin bell and dashboard.

    Each item: {label, count, url, icon, tone}.
    tone: 'attention' = needs action, 'warning' = needs review,
          'info' = recent activity.
    """
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

    return [
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


def site_info(request):
    return {
        'site_profile': ChurchProfile.objects.first(),
        'site_contact': ContactInfo.objects.first(),
    }


def admin_notifications(request):
    try:
        admin_path = reverse('admin:index')
    except Exception:
        admin_path = '/admin/'
    if not request.path.startswith(admin_path):
        return {}

    from blackboard.models import Announcement, Devotion, Event, Sermon
    from contact.models import ContactMessage
    from gallery.models import SliderImage

    from .models import Testimony

    notifications = build_admin_notifications()

    def quick_action(label, icon, add_view_name):
        return {'label': label, 'icon': icon, 'url': reverse(add_view_name)}

    def change_url(admin_name, pk):
        return reverse(f'admin:{admin_name}_change', args=[pk])

    def image_item(img, admin_name):
        return {
            'title': img.title,
            'image': img.image,
            'url': change_url(admin_name, img.pk),
        }

    dashboard = {
        'quick_actions': [
            quick_action('Add devotion', 'fa-solid fa-book-bible', 'admin:blackboard_devotion_add'),
            quick_action('Add event', 'fa-solid fa-calendar-plus', 'admin:blackboard_event_add'),
            quick_action('Add sermon', 'fa-solid fa-microphone-lines', 'admin:blackboard_sermon_add'),
            quick_action('Add announcement', 'fa-solid fa-bullhorn', 'admin:blackboard_announcement_add'),
            quick_action('Add slider image', 'fa-solid fa-photo-film', 'admin:gallery_sliderimage_add'),
        ],
        'slider_latest': [image_item(img, 'gallery_sliderimage') for img in SliderImage.objects.all()[:6]],
        'messages_latest': [
            {
                'name': m.name,
                'subject': m.subject,
                'is_read': m.is_read,
                'created_at': m.created_at,
                'url': change_url('contact_contactmessage', m.pk),
            }
            for m in ContactMessage.objects.all()[:5]
        ],
        'testimonies_pending': [
            {
                'name': t.name,
                'submitted_at': t.submitted_at,
                'url': change_url('home_testimony', t.pk),
            }
            for t in Testimony.objects.filter(is_approved=False)[:5]
        ],
        'devotions_latest': [
            {
                'title': d.title,
                'date': d.date,
                'url': change_url('blackboard_devotion', d.pk),
            }
            for d in Devotion.objects.all()[:5]
        ],
        'events_latest': [
            {
                'title': e.title,
                'date': e.date,
                'url': change_url('blackboard_event', e.pk),
            }
            for e in Event.objects.all()[:5]
        ],
        'sermons_latest': [
            {
                'title': s.title,
                'speaker': s.speaker,
                'date': s.date,
                'url': change_url('blackboard_sermon', s.pk),
            }
            for s in Sermon.objects.all()[:5]
        ],
        'announcements_latest': [
            {
                'title': a.title,
                'date': a.date,
                'url': change_url('blackboard_announcement', a.pk),
            }
            for a in Announcement.objects.all()[:5]
        ],
    }
    return {'admin_notifications': notifications, 'admin_dashboard': dashboard}
