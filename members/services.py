"""Business rules for the member account portal.

Keeping membership decisions, notifications and the optional WhatsApp delivery
in one module means the member views and the admin actions share exactly the
same permission-safe path. Nothing here trusts a submitted status: only
:func:`apply_membership_decision`, called from an administrator action, may
change a membership's approval state.

Notifications use the project's single ``notifications.Notification`` model so
the member bell, the admin bell and their read state never drift apart. There is
no second member-notification table.
"""

import json
import urllib.error
import urllib.request
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from notifications.models import Notification, NotificationState

from .models import (
    ChurchMembership,
    MembershipChangeRequest,
)

WHATSAPP_TIMEOUT = 10


def _safe_reverse(name, **kwargs):
    try:
        return reverse(name, **kwargs)
    except NoReverseMatch:
        return ''


def _excerpt(text, limit=160):
    text = (text or '').strip().replace('\n', ' ')
    if len(text) > limit:
        return text[:limit - 1].rstrip() + '…'
    return text


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

def notify_member_reply(message, title='New reply from church administration'):
    """Tell the member that an administrator wrote to their inbox.

    The row is keyed by the administrator message, so a retried save or a
    double click cannot create a second notice. The notification is shared with
    the public site's bell, which already understands per-user read state.
    ``title`` lets a brand-new conversation say "New message" instead of
    "New reply".
    """
    if message.user_id is None:
        return None, False
    excerpt = _excerpt(message.message)
    notification, created = Notification.objects.get_or_create(
        source_key=f'contact_reply:{message.pk}',
        defaults={
            'recipient': message.user,
            'audience': Notification.AUDIENCE_MEMBER,
            'category': 'contact',
            'source_type': 'contact_reply',
            'source_id': message.pk,
            'title': title,
            'body': excerpt,
            'url': (
                reverse('members:account_messages')
                + f'#message-{message.pk}'
            ),
            'icon': 'mail',
            'tone': Notification.TONE_ATTENTION,
            'permission': '',
            'status': Notification.STATUS_ACTIVE,
            'requires_action': False,
            'created_at': message.created_at or timezone.now(),
        },
    )
    if created:
        send_member_email(
            message.user,
            title,
            'You have a new private message from the church administration. '
            'Open your account to read and reply: '
            f'{reverse("members:account_messages")}',
        )
        # WhatsApp is a generic doorbell only: never the message content.
        status = send_message_whatsapp(message)
        notification.whatsapp_status = status
        notification.save(update_fields=['whatsapp_status'])
    return notification, created


def _whatsapp_target(membership):
    """Return a normalised phone number only when consent allows a send."""
    if membership is None or not membership.whatsapp_consent:
        return ''
    digits = ''.join(ch for ch in (membership.phone or '') if ch.isdigit())
    return digits if len(digits) >= 7 else ''


def send_message_whatsapp(message):
    """Optional generic WhatsApp notice for a private inbox message.

    The body is deliberately generic: it contains no message text, subject,
    attachment name or other confidential content. The in-app notification is
    always created first, so WhatsApp can never replace or gate the inbox.
    """
    if message.user_id is None:
        return 'skipped'
    membership = (
        ChurchMembership.objects
        .filter(user_id=message.user_id)
        .only('phone', 'whatsapp_consent')
        .first()
    )
    target = _whatsapp_target(membership)
    if not target:
        return 'skipped'
    body = (
        'You have a new private message from the Shekinah Blaze church '
        'administration. Sign in to your account to read and reply.'
    )
    # Reuse the generic poster, injecting the recipient without exposing text.
    return _post_whatsapp_to(target, body)


def _post_whatsapp_to(target, body):
    api_url = (getattr(settings, 'WHATSAPP_API_URL', '') or '').strip()
    api_token = (getattr(settings, 'WHATSAPP_API_TOKEN', '') or '').strip()
    if not api_url or not api_token:
        return 'not_configured'
    payload = {'to': target, 'type': 'text', 'text': {'body': body}}
    sender = (getattr(settings, 'WHATSAPP_SENDER_ID', '') or '').strip()
    if sender:
        payload['from'] = sender
    request = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {api_token}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(
            request, timeout=WHATSAPP_TIMEOUT,
        ) as response:
            return 'sent' if 200 <= response.status < 300 else 'failed'
    except Exception:
        return 'failed'


def mark_message_notifications_read(user):
    """Mark reply notices read after the member opens the unified inbox."""
    if not user or not user.is_authenticated:
        return 0
    queryset = Notification.objects.filter(
        recipient=user,
        audience=Notification.AUDIENCE_MEMBER,
        source_type='contact_reply',
        status__in=Notification.OPEN_STATUSES,
    )
    count = 0
    for notification in queryset:
        state, _ = NotificationState.objects.get_or_create(
            notification=notification, user=user,
        )
        if state.read_at is None:
            state.read_at = timezone.now()
            state.save(update_fields=['read_at', 'updated_at'])
            count += 1
    return count


def _admin_change_url(change):
    return (
        _safe_reverse(
            'admin:members_membershipchangerequest_change',
            args=[change.pk],
        )
        or _safe_reverse('admin:members_churchmembership_dashboard')
    )


def notify_admin_membership_change(change):
    """Queue a details update for staff review.

    New applications already produce a pending-review notification from the
    shared ``sync_membership`` receiver, so this only adds the missing notice
    for an *edit* to an existing membership. That avoids two bell rows for one
    event while still telling administrators that an active member changed
    their details.
    """
    if change.kind != MembershipChangeRequest.KIND_UPDATE:
        return None
    notification, _ = Notification.objects.update_or_create(
        source_key=f'membership_change:{change.pk}',
        defaults={
            'recipient': None,
            'audience': Notification.AUDIENCE_STAFF,
            'category': 'membership',
            'source_type': 'membership_change',
            'source_id': change.pk,
            'title': 'Membership details awaiting review',
            'body': (
                f'{change.membership.full_name} submitted a membership '
                'details update.'
            ),
            'url': _admin_change_url(change),
            'icon': 'id-card',
            'tone': Notification.TONE_ATTENTION,
            'permission': 'members.manage_membership',
            'status': Notification.STATUS_PENDING,
            'requires_action': True,
        },
    )
    return notification


def _resolve_notification(source_key):
    now = timezone.now()
    return Notification.objects.filter(
        source_key=source_key,
        status__in=Notification.OPEN_STATUSES,
    ).update(
        status=Notification.STATUS_RESOLVED,
        resolved_at=now,
        updated_at=now,
    )


def _notify_member_decision(change):
    """One notice per reviewed *details update*.

    The membership signal already emits a new notice when a pending
    application becomes active or rejected. An active member's update keeps
    the same status, so the generic notice would keep its old read state; this
    dedicated row makes the decision visible in the member's bell.
    """
    if change.is_application:
        return None
    approved = change.status == MembershipChangeRequest.STATUS_APPROVED
    title = (
        'Membership details approved'
        if approved
        else 'Membership changes not approved'
    )
    body = (
        'Your updated church membership details have been reviewed and '
        'approved.'
        if approved
        else 'Your membership changes were not approved. Your membership '
             'status is unchanged; you can update your details and submit '
             'again.'
    )
    if change.admin_note:
        body = f'{body}\n\nNote from the church: {change.admin_note}'
    notification, _ = Notification.objects.update_or_create(
        source_key=f'membership_decision:{change.pk}',
        defaults={
            'recipient': change.membership.user,
            'audience': Notification.AUDIENCE_MEMBER,
            'category': 'membership',
            'source_type': 'membership_decision',
            'source_id': change.pk,
            'title': title,
            'body': body,
            'url': reverse('members:account') + '#membership',
            'icon': 'id-card',
            'tone': (
                Notification.TONE_INFO
                if approved else Notification.TONE_ATTENTION
            ),
            'permission': '',
            'status': Notification.STATUS_ACTIVE,
            'requires_action': False,
        },
    )
    return notification


def send_member_email(user, subject, body):
    """Optional plain-text notice.

    Email is best-effort: a missing mail server must never make a message or a
    membership decision fail. The in-app notification is the primary channel.
    """
    profile = getattr(user, 'member_profile', None)
    if profile is not None and not profile.email_notifications:
        return False
    if not user.email:
        return False
    try:
        from django.core.mail import send_mail

        send_mail(
            subject,
            body,
            getattr(settings, 'DEFAULT_FROM_EMAIL', None),
            [user.email],
            fail_silently=True,
        )
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Membership review
# ---------------------------------------------------------------------------

def record_membership_change(membership, user, kind, summary=''):
    """Create or refresh the single open review item for a membership."""
    defaults = {
        'submitted_by': user,
        'kind': kind,
        'summary': summary,
    }
    try:
        with transaction.atomic():
            change = (
                MembershipChangeRequest.objects
                .select_for_update()
                .filter(membership=membership, status='pending')
                .first()
            )
            if change is None:
                change = MembershipChangeRequest.objects.create(
                    membership=membership, **defaults,
                )
            else:
                for name, value in defaults.items():
                    setattr(change, name, value)
                change.save(update_fields=[*defaults, 'updated_at'])
            notify_admin_membership_change(change)
            return change
    except IntegrityError:
        # A concurrent submission won the unique-pending race; reuse its row.
        change = MembershipChangeRequest.objects.filter(
            membership=membership, status='pending',
        ).first()
        if change is not None:
            return change
        raise


@transaction.atomic
def apply_membership_decision(change_id, admin, approve, note=''):
    """Approve or reject a pending membership request.

    Returns ``(change, notification, created)``. Calling this twice is safe:
    an already-reviewed request is left untouched. An existing active member
    is never downgraded by a decision on their details update.
    """
    change = (
        MembershipChangeRequest.objects
        .select_for_update()
        .select_related('membership', 'membership__user')
        .get(pk=change_id)
    )
    if change.status != MembershipChangeRequest.STATUS_PENDING:
        return change, None, False

    membership = change.membership
    change.status = (
        MembershipChangeRequest.STATUS_APPROVED
        if approve else MembershipChangeRequest.STATUS_REJECTED
    )
    change.reviewed_by = admin
    change.reviewed_at = timezone.now()
    change.admin_note = (note or '').strip()
    change.save(update_fields=[
        'status', 'reviewed_by', 'reviewed_at', 'admin_note', 'updated_at',
    ])

    if approve:
        # Only a new/resubmitted application becomes active. An active member
        # who edited their details simply keeps their active status.
        if membership.status in ('pending', 'rejected'):
            membership.status = 'active'
            membership.save(update_fields=['status', 'updated_at'])
        title = (
            'Membership approved'
            if change.is_application
            else 'Membership details approved'
        )
        body = (
            'Your church membership has been approved. Welcome to the '
            'Shekinah Blaze family!'
            if change.is_application
            else 'Your updated church membership details have been reviewed '
                 'and approved.'
        )
    else:
        # Rejecting a details update must not revoke an existing active
        # membership. Only an unresolved application becomes rejected.
        if membership.status == 'pending':
            membership.status = 'rejected'
            membership.save(update_fields=['status', 'updated_at'])
        title = (
            'Membership application not approved'
            if change.is_application
            else 'Membership changes not approved'
        )
        body = (
            'Your church membership application was not approved. You can '
            'update your details and submit again.'
            if change.is_application
            else 'Your membership changes were not approved. Your membership '
                 'status is unchanged; you can update your details and submit '
                 'again.'
        )
    if change.admin_note:
        body = f'{body}\n\nNote from the church: {change.admin_note}'

    # The membership save above fires the shared receiver, which creates the
    # application decision notice. Details updates need their own notice.
    notification = _notify_member_decision(change)
    _resolve_notification(f'membership_change:{change.pk}')

    if notification is None:
        # Application decisions are represented by the status notification.
        notification = Notification.objects.filter(
            recipient=membership.user,
            audience=Notification.AUDIENCE_MEMBER,
            source_type='membership_member',
            source_id=membership.pk,
            status__in=Notification.OPEN_STATUSES,
        ).order_by('-created_at').first()

    send_membership_whatsapp(change, title, body)
    return change, notification, notification is not None


def send_membership_whatsapp(change, title, body):
    """Send the decision through a configured WhatsApp provider, if any.

    No provider is bundled with this project. The function therefore records an
    honest ``not_configured`` / ``skipped`` status on the review request and
    never claims a delivery that did not happen. See ``docs/WHATSAPP.md`` for
    the required settings.
    """
    api_url = (getattr(settings, 'WHATSAPP_API_URL', '') or '').strip()
    api_token = (getattr(settings, 'WHATSAPP_API_TOKEN', '') or '').strip()
    membership = change.membership

    if not api_url or not api_token:
        change.whatsapp_status = 'not_configured'
        change.whatsapp_error = ''
        change.save(update_fields=['whatsapp_status', 'whatsapp_error'])
        return change.whatsapp_status

    if not membership.whatsapp_consent:
        change.whatsapp_status = 'skipped'
        change.whatsapp_error = (
            'The member has not consented to WhatsApp messages.'
        )
        change.save(update_fields=['whatsapp_status', 'whatsapp_error'])
        return change.whatsapp_status

    digits = ''.join(ch for ch in (membership.phone or '') if ch.isdigit())
    if len(digits) < 7:
        change.whatsapp_status = 'skipped'
        change.whatsapp_error = 'No usable phone number on the membership.'
        change.save(update_fields=['whatsapp_status', 'whatsapp_error'])
        return change.whatsapp_status

    # Never put the decision, admin note or member details in a third-party
    # message. The member signs in to read the confidential content.
    payload = {
        'to': digits,
        'type': 'text',
        'text': {
            'body': (
                'Your church membership record has an update. Sign in to '
                'your account to view the details.'
            ),
        },
    }
    sender = (getattr(settings, 'WHATSAPP_SENDER_ID', '') or '').strip()
    if sender:
        payload['from'] = sender

    request = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {api_token}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(
            request, timeout=WHATSAPP_TIMEOUT,
        ) as response:
            if 200 <= response.status < 300:
                change.whatsapp_status = 'sent'
                change.whatsapp_error = ''
            else:
                change.whatsapp_status = 'failed'
                change.whatsapp_error = (
                    f'Provider returned HTTP {response.status}.'
                )
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
            OSError) as exc:
        change.whatsapp_status = 'failed'
        change.whatsapp_error = str(exc)[:500]
    except Exception as exc:  # pragma: no cover - defensive provider boundary
        change.whatsapp_status = 'failed'
        change.whatsapp_error = str(exc)[:500]
    change.save(update_fields=['whatsapp_status', 'whatsapp_error'])
    return change.whatsapp_status


# ---------------------------------------------------------------------------
# Small read helpers shared by views and the context processor
# ---------------------------------------------------------------------------

def member_thread(user):
    from contact.models import ContactMessage

    return (
        ContactMessage.objects
        .filter(user=user)
        .select_related('sender')
        .order_by('created_at', 'pk')
    )


def unread_message_count(user):
    from contact.models import ContactMessage

    if not user or not user.is_authenticated:
        return 0
    return ContactMessage.objects.filter(
        user=user, is_from_admin=True, read_by_member=False,
    ).count()


def mark_member_messages_read(user):
    from contact.models import ContactMessage

    if not user or not user.is_authenticated:
        return 0
    count = ContactMessage.objects.filter(
        user=user, is_from_admin=True, read_by_member=False,
    ).update(read_by_member=True)
    mark_message_notifications_read(user)
    return count


def unread_notification_count(request):
    """Unread items in the shared public/member notification bell."""
    from notifications import services as notification_services

    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return 0
    try:
        return notification_services.unread_count(
            request, notification_services.PUBLIC_SCOPE,
        )
    except Exception:
        return 0


def notification_history(user):
    from notifications import services as notification_services

    if not user or not user.is_authenticated:
        return []
    return notification_services.history_notifications(
        user, notification_services.PUBLIC_SCOPE,
    )


def notification_preview(user, limit=5):
    from notifications import services as notification_services

    if not user or not user.is_authenticated:
        return []
    return list(
        notification_services.visible_notifications(
            user, notification_services.PUBLIC_SCOPE,
        )[:limit]
    )


def serialized_notifications(notifications, request):
    from notifications import services as notification_services

    return [
        notification_services.serialize(notification, request)
        for notification in notifications
    ]


def mark_notification_read(notification, request):
    from notifications import services as notification_services

    notification_services.mark_read(notification, request)


def mark_all_notifications_read(request, limit=100):
    from notifications import services as notification_services

    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return 0
    count = 0
    for notification in notification_preview(user, limit=limit):
        if getattr(notification, 'user_read_at', None) is None:
            notification_services.mark_read(notification, request)
            count += 1
    return count



def pending_change_for(membership):
    if membership is None:
        return None
    return membership.change_requests.filter(status='pending').first()


def latest_decision_for(membership):
    if membership is None:
        return None
    return (
        membership.change_requests
        .exclude(status='pending')
        .select_related('reviewed_by')
        .order_by('-reviewed_at', '-created_at')
        .first()
    )


def child_names(membership):
    """Parse the existing one-name-per-line storage into a clean list."""
    if membership is None:
        return []
    return [
        line.strip()
        for line in (membership.children_names or '').splitlines()
        if line.strip()
    ]


def save_child_names(membership, names):
    membership.children_names = '\n'.join(names)
    membership.save(update_fields=['children_names', 'updated_at'])
    return names


def membership_or_none(user):
    return ChurchMembership.objects.filter(user=user).first()


def duplicate_message_exists(user, body, seconds=20):
    """Block an accidental double-click on Send without a category system."""
    from contact.models import ContactMessage

    cutoff = timezone.now() - timedelta(seconds=seconds)
    return ContactMessage.objects.filter(
        user=user,
        is_from_admin=False,
        message=body,
        created_at__gte=cutoff,
    ).exists()


def clear_admin_notification_cache():
    """Compatibility hook.

    Notifications used to be cached in a module-level key. The unified
    ``notifications`` service reads live rows, so there is nothing to clear;
    the function is kept because older call sites still invoke it.
    """
    return None
