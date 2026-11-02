"""Keep notification activity rows in step with their source records.

The receivers are intentionally small wrappers around ``notifications.services``.
Bulk database updates do not fire signals, so the services also reconcile on
read (and the ``sync_notifications`` command repairs existing data).
"""

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from blackboard.models import Announcement, Event, EventRsvp, MemberProfile
from contact.models import ContactMessage
from home.models import Subscriber, Testimony
from members.models import ChurchMembership

from . import services


# ---------------------------------------------------------------------------
# Contact messages
# ---------------------------------------------------------------------------

@receiver(post_save, sender=ContactMessage, dispatch_uid='notify_contact_saved')
def contact_saved(sender, instance, **kwargs):
    services.sync_contact_message(instance)


@receiver(post_delete, sender=ContactMessage, dispatch_uid='notify_contact_deleted')
def contact_deleted(sender, instance, **kwargs):
    services._close(f'contact:{instance.pk}')


# ---------------------------------------------------------------------------
# Testimonies
# ---------------------------------------------------------------------------

@receiver(post_save, sender=Testimony, dispatch_uid='notify_testimony_saved')
def testimony_saved(sender, instance, **kwargs):
    services.sync_testimony(instance)


@receiver(post_delete, sender=Testimony, dispatch_uid='notify_testimony_deleted')
def testimony_deleted(sender, instance, **kwargs):
    services._close(f'testimony:{instance.pk}')


# ---------------------------------------------------------------------------
# Member access / new members
# ---------------------------------------------------------------------------

@receiver(post_save, sender=MemberProfile, dispatch_uid='notify_member_saved')
def member_profile_saved(sender, instance, **kwargs):
    services.sync_member_profile(instance)


@receiver(post_delete, sender=MemberProfile, dispatch_uid='notify_member_deleted')
def member_profile_deleted(sender, instance, **kwargs):
    services._close(f'member_access:{instance.pk}')
    services._close(f'new_member:{instance.pk}')


# ---------------------------------------------------------------------------
# Newsletter subscribers
# ---------------------------------------------------------------------------

@receiver(post_save, sender=Subscriber, dispatch_uid='notify_subscriber_saved')
def subscriber_saved(sender, instance, **kwargs):
    services.sync_subscriber(instance)


@receiver(post_delete, sender=Subscriber, dispatch_uid='notify_subscriber_deleted')
def subscriber_deleted(sender, instance, **kwargs):
    services._close(f'subscriber:{instance.pk}')


# ---------------------------------------------------------------------------
# Event RSVPs
# ---------------------------------------------------------------------------

@receiver(post_save, sender=EventRsvp, dispatch_uid='notify_rsvp_saved')
def rsvp_saved(sender, instance, **kwargs):
    services.sync_event_rsvp(instance)


@receiver(post_delete, sender=EventRsvp, dispatch_uid='notify_rsvp_deleted')
def rsvp_deleted(sender, instance, **kwargs):
    services._close(f'event_rsvp:{instance.pk}')


# ---------------------------------------------------------------------------
# Church memberships
# ---------------------------------------------------------------------------

@receiver(pre_save, sender=ChurchMembership, dispatch_uid='notify_membership_pre_save')
def membership_pre_save(sender, instance, **kwargs):
    """Remember the old status so only real transitions notify the member."""
    if instance.pk:
        instance._previous_notification_status = (
            ChurchMembership.objects.filter(pk=instance.pk)
            .values_list('status', flat=True)
            .first()
        )
    else:
        instance._previous_notification_status = None


@receiver(post_save, sender=ChurchMembership, dispatch_uid='notify_membership_saved')
def membership_saved(sender, instance, **kwargs):
    previous = getattr(instance, '_previous_notification_status', None)
    services.sync_membership(
        instance, notify_member=previous != instance.status,
    )


@receiver(post_delete, sender=ChurchMembership, dispatch_uid='notify_membership_deleted')
def membership_deleted(sender, instance, **kwargs):
    services._close(f'membership_pending:{instance.pk}')
    services._close(f'membership_new:{instance.pk}')
    services.Notification.objects.filter(
        source_type='membership_member',
        source_id=instance.pk,
        status__in=services.Notification.OPEN_STATUSES,
    ).update(
        status=services.Notification.STATUS_RESOLVED,
        resolved_at=services.timezone.now(),
        updated_at=services.timezone.now(),
    )


# ---------------------------------------------------------------------------
# Public content
# ---------------------------------------------------------------------------

@receiver(post_save, sender=Announcement, dispatch_uid='notify_announcement_saved')
def announcement_saved(sender, instance, **kwargs):
    services.sync_announcement(instance)


@receiver(post_delete, sender=Announcement, dispatch_uid='notify_announcement_deleted')
def announcement_deleted(sender, instance, **kwargs):
    services._close(f'announcement:{instance.pk}')


@receiver(post_save, sender=Event, dispatch_uid='notify_event_saved')
def event_saved(sender, instance, **kwargs):
    services.sync_event(instance)


@receiver(post_delete, sender=Event, dispatch_uid='notify_event_deleted')
def event_deleted(sender, instance, **kwargs):
    services._close(f'event:{instance.pk}', status=services.Notification.STATUS_COMPLETED)
