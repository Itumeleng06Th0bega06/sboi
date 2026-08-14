from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from about.models import ChurchProfile
from contact.models import ContactInfo


def site_info(request):
    return {
        'site_profile': ChurchProfile.objects.first(),
        'site_contact': ContactInfo.objects.first(),
    }


def admin_notifications(request):
    if not request.path.startswith('/admin/'):
        return {}

    from blackboard.models import EventRsvp, MemberProfile
    from contact.models import ContactMessage

    from .models import Subscriber, Testimony

    week = timezone.now() - timedelta(days=7)

    def count_with_url(label, queryset, view_name):
        return {
            'label': label,
            'count': queryset.count(),
            'url': reverse(view_name),
        }

    notifications = [
        count_with_url(
            'Unread contact messages',
            ContactMessage.objects.filter(is_read=False),
            'admin:contact_contactmessage_changelist',
        ),
        count_with_url(
            'Pending testimonies',
            Testimony.objects.filter(is_approved=False),
            'admin:home_testimony_changelist',
        ),
        count_with_url(
            'New newsletter subscribers (7 days)',
            Subscriber.objects.filter(subscribed_at__gte=week),
            'admin:home_subscriber_changelist',
        ),
        count_with_url(
            'New event RSVPs (7 days)',
            EventRsvp.objects.filter(created_at__gte=week),
            'admin:blackboard_eventrsvp_changelist',
        ),
        count_with_url(
            'New members (7 days)',
            MemberProfile.objects.filter(created_at__gte=week),
            'admin:blackboard_memberprofile_changelist',
        ),
        count_with_url(
            'Blocked / suspended members',
            MemberProfile.objects.exclude(status='active'),
            'admin:blackboard_memberprofile_changelist',
        ),
    ]
    return {'admin_notifications': notifications}

