"""Query, filtering and lifecycle helpers for the notification bell.

Everything that decides whether a notification is visible lives here so the
public bell, the member portal and the admin bell can never drift apart.

Visibility rules
----------------
* Only ``active``/``pending`` activities are eligible.
* Expired, resolved, completed, dismissed and archived activities are hidden.
* Unread activities are always shown.  A *read* activity stays visible only
  when it still ``requires_action``.
* Read/dismiss/archive state is per user (``NotificationState``) or, for an
  anonymous visitor, per session.
"""

from datetime import datetime, time, timedelta

from django.db.models import DateTimeField, F, OuterRef, Q, Subquery
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from .models import Notification, NotificationState

# Session keys used for visitors who are not signed in.
SESSION_READ = 'sboi_notifications_read'
SESSION_DISMISSED = 'sboi_notifications_dismissed'
SESSION_ARCHIVED = 'sboi_notifications_archived'

PUBLIC_SCOPE = 'public'
STAFF_SCOPE = 'staff'


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def _state_subquery(user, field):
    return NotificationState.objects.filter(
        notification=OuterRef('pk'),
        user=user,
    ).values(field)[:1]


def open_notifications(scope=None):
    """All activity records that could still be relevant, before per-user data."""
    now = timezone.now()
    queryset = Notification.objects.filter(
        status__in=Notification.OPEN_STATUSES,
    ).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=now),
    )
    if scope == STAFF_SCOPE:
        queryset = queryset.filter(audience=Notification.AUDIENCE_STAFF)
    elif scope == PUBLIC_SCOPE:
        queryset = queryset.filter(
            audience__in=(
                Notification.AUDIENCE_PUBLIC,
                Notification.AUDIENCE_MEMBER,
            ),
        )
    return queryset


def _audience_q(user):
    """Notifications the signed-in user is allowed to see."""
    conditions = Q(audience=Notification.AUDIENCE_PUBLIC)
    conditions |= Q(
        audience=Notification.AUDIENCE_MEMBER,
        recipient_id=user.pk,
    )
    conditions |= Q(
        audience=Notification.AUDIENCE_STAFF,
        recipient_id=user.pk,
    )
    if user.is_superuser:
        conditions |= Q(
            audience=Notification.AUDIENCE_STAFF,
            recipient__isnull=True,
        )
    elif user.is_staff:
        permissions = set(user.get_all_permissions())
        conditions |= (
            Q(
                audience=Notification.AUDIENCE_STAFF,
                recipient__isnull=True,
            )
            & (
                Q(permission='')
                | Q(permission__in=permissions)
            )
        )
    return conditions


def visible_notifications(user, scope=None):
    """Eligible notifications for one user, with their personal state attached."""
    queryset = open_notifications(scope)
    if not user or not user.is_authenticated:
        # Anonymous visitors only ever receive public notifications.
        return queryset.filter(audience=Notification.AUDIENCE_PUBLIC).order_by(
            '-created_at', '-pk',
        )

    queryset = queryset.filter(_audience_q(user)).annotate(
        user_read_at=Subquery(
            _state_subquery(user, 'read_at'),
            output_field=DateTimeField(),
        ),
        user_dismissed_at=Subquery(
            _state_subquery(user, 'dismissed_at'),
            output_field=DateTimeField(),
        ),
        user_archived_at=Subquery(
            _state_subquery(user, 'archived_at'),
            output_field=DateTimeField(),
        ),
    ).filter(
        Q(user_dismissed_at__isnull=True) & Q(user_archived_at__isnull=True)
    ).filter(
        Q(user_read_at__isnull=True) | Q(requires_action=True)
    )
    return queryset.distinct().order_by('-created_at', '-pk')


def notification_is_visible(notification, request):
    """Return True when this notification belongs to the requesting user."""
    user = getattr(request, 'user', None)
    scope = STAFF_SCOPE if getattr(request, 'notification_scope', None) == STAFF_SCOPE else None
    if not user or not user.is_authenticated:
        return notification.audience == Notification.AUDIENCE_PUBLIC

    if notification.audience == Notification.AUDIENCE_PUBLIC:
        return True
    if notification.recipient_id == user.pk:
        return True
    if notification.audience == Notification.AUDIENCE_STAFF:
        if user.is_superuser:
            return True
        if notification.permission:
            return user.has_perm(notification.permission)
        return user.is_staff
    return False


def _session_ids(request, key):
    if request is None or not hasattr(request, 'session'):
        return set()
    return {str(value) for value in request.session.get(key, [])}


def _add_session_id(request, key, pk):
    values = list(request.session.get(key, []))
    if str(pk) not in values:
        values.append(str(pk))
        request.session[key] = values[-200:]


def _is_anonymous(request):
    user = getattr(request, 'user', None)
    return not user or not user.is_authenticated


def _annotated_read(notification, request):
    if _is_anonymous(request):
        return str(notification.pk) in _session_ids(request, SESSION_READ)
    return getattr(notification, 'user_read_at', None) is not None


def _blocked_by_session(notification, request):
    if not _is_anonymous(request):
        return False
    pk = str(notification.pk)
    return (
        pk in _session_ids(request, SESSION_DISMISSED)
        or pk in _session_ids(request, SESSION_ARCHIVED)
    )


def notification_items(request, scope=None):
    """Serialised bell rows for the current request."""
    items = []
    for notification in visible_notifications(request.user, scope).select_related(
        'recipient',
    ):
        if _blocked_by_session(notification, request):
            continue
        items.append(serialize(notification, request))
    return items


def unread_count(request, scope=None):
    """Unread badge count for the current user (read but actionable excluded)."""
    count = 0
    for notification in visible_notifications(request.user, scope).select_related(
        'recipient',
    ):
        if _blocked_by_session(notification, request):
            continue
        if not _annotated_read(notification, request):
            count += 1
    return count


def get_visible_notification(pk, request):
    """Resolve a notification only when the current user may act on it."""
    notification = Notification.objects.select_related('recipient').filter(pk=pk).first()
    if notification is None:
        return None
    if not notification_is_visible(notification, request):
        return None
    return notification


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

def _safe_reverse(name, **kwargs):
    try:
        return reverse(name, **kwargs)
    except NoReverseMatch:
        return ''


def serialize(notification, request=None):
    is_anonymous = _is_anonymous(request) if request is not None else True
    if is_anonymous:
        is_read = (
            str(notification.pk) in _session_ids(request, SESSION_READ)
            if request is not None else False
        )
    else:
        is_read = getattr(notification, 'user_read_at', None) is not None

    return {
        'id': notification.pk,
        'title': notification.title,
        'label': notification.title,  # backwards-compatible with old admin JS
        'body': notification.body,
        'description': notification.body,
        'url': notification.url,
        'icon': notification.icon or 'bell',
        'tone': notification.tone,
        'status': notification.status,
        'requires_action': notification.requires_action,
        'is_read': is_read,
        'unread': not is_read,
        'created_at': notification.created_at.isoformat() if notification.created_at else '',
        'date': (
            timezone.localtime(notification.created_at).strftime('%d %b %Y')
            if notification.created_at else ''
        ),
        'mark_read_url': _safe_reverse('notifications:read', args=[notification.pk]),
        'open_url': _safe_reverse('notifications:open', args=[notification.pk]),
        'dismiss_url': _safe_reverse('notifications:dismiss', args=[notification.pk]),
        'archive_url': _safe_reverse('notifications:archive', args=[notification.pk]),
        # The legacy admin bell displayed one count per category row.
        'count': 1,
    }


# ---------------------------------------------------------------------------
# Per-user actions
# ---------------------------------------------------------------------------

def _state_for(notification, user):
    state, _ = NotificationState.objects.get_or_create(
        notification=notification,
        user=user,
    )
    return state


def mark_read(notification, request):
    if _is_anonymous(request):
        _add_session_id(request, SESSION_READ, notification.pk)
        return
    state = _state_for(notification, request.user)
    if state.read_at is None:
        state.read_at = timezone.now()
        state.save(update_fields=['read_at', 'updated_at'])


def dismiss(notification, request):
    if _is_anonymous(request):
        _add_session_id(request, SESSION_DISMISSED, notification.pk)
        return
    state = _state_for(notification, request.user)
    if state.dismissed_at is None:
        state.dismissed_at = timezone.now()
        state.save(update_fields=['dismissed_at', 'updated_at'])


def archive(notification, request):
    if _is_anonymous(request):
        _add_session_id(request, SESSION_ARCHIVED, notification.pk)
        return
    state = _state_for(notification, request.user)
    if state.archived_at is None:
        state.archived_at = timezone.now()
        state.save(update_fields=['archived_at', 'updated_at'])


def mark_all_read(request, scope=None):
    """Mark every notification currently visible to this user as read.

    Only rows the user can actually see are touched, so a staff member using
    the admin bell never marks a public/member row they cannot see.
    """
    notifications = list(visible_notifications(request.user, scope))
    if _is_anonymous(request):
        for notification in notifications:
            _add_session_id(request, SESSION_READ, notification.pk)
        return len(notifications)

    now = timezone.now()
    marked = 0
    for notification in notifications:
        state = _state_for(notification, request.user)
        if state.read_at is None:
            state.read_at = now
            state.save(update_fields=['read_at', 'updated_at'])
            marked += 1
    return marked


def dismiss_many(request, pks, scope=None):
    """Dismiss (remove from the bell) the user's own visible notifications.

    ``pks`` may contain arbitrary ids; anything outside the user's visible set
    is silently ignored.  The notification records themselves are kept for the
    history page, matching the single-row dismiss behaviour.
    """
    try:
        pks = [int(pk) for pk in pks]
    except (TypeError, ValueError):
        return 0
    if not pks:
        return 0

    notifications = list(
        visible_notifications(request.user, scope).filter(pk__in=pks)
    )
    for notification in notifications:
        dismiss(notification, request)
    return len(notifications)


# ---------------------------------------------------------------------------
# History (separate page; never mixed into the active dropdown)
# ---------------------------------------------------------------------------

def history_notifications(user, scope=None):
    queryset = Notification.objects.all()
    if scope == STAFF_SCOPE:
        queryset = queryset.filter(audience=Notification.AUDIENCE_STAFF)
    elif scope == PUBLIC_SCOPE:
        queryset = queryset.filter(
            audience__in=(Notification.AUDIENCE_PUBLIC, Notification.AUDIENCE_MEMBER),
        )

    if not user or not user.is_authenticated:
        return queryset.filter(audience=Notification.AUDIENCE_PUBLIC)

    return queryset.filter(_audience_q(user)).annotate(
        user_read_at=Subquery(
            _state_subquery(user, 'read_at'),
            output_field=DateTimeField(),
        ),
        user_dismissed_at=Subquery(
            _state_subquery(user, 'dismissed_at'),
            output_field=DateTimeField(),
        ),
        user_archived_at=Subquery(
            _state_subquery(user, 'archived_at'),
            output_field=DateTimeField(),
        ),
    ).distinct().order_by('-created_at', '-pk')


# ---------------------------------------------------------------------------
# Sync helpers: keep activity rows in step with the underlying records
# ---------------------------------------------------------------------------

def _start_of_day(value):
    return timezone.make_aware(datetime.combine(value, time.min))


def _end_of_day(value):
    return timezone.make_aware(datetime.combine(value, time.max))


def _upsert(source_key, **defaults):
    notification, _ = Notification.objects.update_or_create(
        source_key=source_key,
        defaults=defaults,
    )
    return notification


def _close(source_key, status=Notification.STATUS_RESOLVED):
    now = timezone.now()
    fields = {
        'status': status,
        'resolved_at': now,
        'updated_at': now,
    }
    if status == Notification.STATUS_COMPLETED:
        fields['completed_at'] = now
    return Notification.objects.filter(
        source_key=source_key,
        status__in=Notification.OPEN_STATUSES,
    ).update(**fields)


def _close_missing(source_type, open_source_ids, status=Notification.STATUS_RESOLVED):
    """Close rows whose activity no longer exists or is no longer open."""
    now = timezone.now()
    fields = {
        'status': status,
        'resolved_at': now,
        'updated_at': now,
    }
    if status == Notification.STATUS_COMPLETED:
        fields['completed_at'] = now
    queryset = Notification.objects.filter(
        source_type=source_type,
        status__in=Notification.OPEN_STATUSES,
    )
    if open_source_ids:
        queryset = queryset.exclude(source_id__in=list(open_source_ids))
    return queryset.update(**fields)


def _notify_admin_contact(message):
    """Best-effort email + WhatsApp notice to admin for a new contact message."""
    import urllib.request
    from django.conf import settings as _settings
    from django.core.mail import send_mail

    admin_email = getattr(_settings, 'ADMIN_EMAIL', 'admin@shekinahblaze.org')
    # Email
    try:
        send_mail(
            subject=f'New contact message from {message.sender_name}',
            message=(
                f'You have a new message from {message.sender_name}'
                + (f' ({message.email})' if message.email else '')
                + (f': {message.subject}' if message.subject else '')
                + '\n\nSign in to the admin console to read and reply.'
            ),
            from_email=getattr(_settings, 'DEFAULT_FROM_EMAIL', admin_email),
            recipient_list=[admin_email],
            fail_silently=True,
        )
    except Exception:
        pass

    # WhatsApp doorbell
    admin_wa = getattr(_settings, 'ADMIN_WHATSAPP_NUMBER', '').strip()
    api_url = getattr(_settings, 'WHATSAPP_API_URL', '').strip()
    api_token = getattr(_settings, 'WHATSAPP_API_TOKEN', '').strip()
    if admin_wa and api_url and api_token:
        digits = ''.join(ch for ch in admin_wa if ch.isdigit())
        if len(digits) >= 7:
            try:
                payload = {
                    'to': digits,
                    'type': 'text',
                    'text': {
                        'body': (
                            'New contact message from '
                            f'{message.sender_name}. Sign in to the admin '
                            'console to read and reply.'
                        ),
                    },
                }
                sender = getattr(_settings, 'WHATSAPP_SENDER_ID', '').strip()
                if sender:
                    payload['from'] = sender
                request = urllib.request.Request(
                    api_url,
                    data=__import__('json').dumps(payload).encode('utf-8'),
                    headers={
                        'Authorization': f'Bearer {api_token}',
                        'Content-Type': 'application/json',
                    },
                    method='POST',
                )
                with urllib.request.urlopen(request, timeout=10):
                    pass
            except Exception:
                pass


def sync_contact_message(message):
    source_key = f'contact:{message.pk}'
    # Administrator replies are a member-facing activity, not an admin task.
    # The member notification is created by members.services.notify_member_reply.
    if message.is_from_admin or message.is_read:
        _close(source_key)
        return
    _upsert(
        source_key,
        recipient=None,
        audience=Notification.AUDIENCE_STAFF,
        category='contact',
        source_type='contact',
        source_id=message.pk,
        title=(
            'Unread member messages'
            if message.user_id else 'Unread contact messages'
        ),
        body=(
            f'New message from {message.sender_name}'
            + (f': {message.subject}' if message.subject else '')
        )[:220],
        url=_safe_reverse('admin:contact_contactmessage_change', args=[message.pk]),
        icon='mail',
        tone=Notification.TONE_ATTENTION,
        permission='contact.manage_contact_messages',
        status=Notification.STATUS_PENDING,
        requires_action=True,
        created_at=message.created_at or timezone.now(),
        expires_at=None,
        resolved_at=None,
        completed_at=None,
    )
    # Notify admin via email + WhatsApp (best-effort, generic, no message text)
    _notify_admin_contact(message)


def sync_testimony(testimony):
    source_key = f'testimony:{testimony.pk}'
    if testimony.is_approved:
        _close(source_key)
        return
    _upsert(
        source_key,
        recipient=None,
        audience=Notification.AUDIENCE_STAFF,
        category='testimony',
        source_type='testimony',
        source_id=testimony.pk,
        title='Pending testimonies',
        body=f'Testimony from {testimony.name} needs review: {testimony.message[:120]}',
        url=_safe_reverse('admin:home_testimony_change', args=[testimony.pk]),
        icon='message',
        tone=Notification.TONE_ATTENTION,
        permission='home.manage_testimonies',
        status=Notification.STATUS_PENDING,
        requires_action=True,
        created_at=testimony.submitted_at or timezone.now(),
        expires_at=None,
        resolved_at=None,
        completed_at=None,
    )


def sync_member_profile(profile):
    source_key = f'member_access:{profile.pk}'
    if profile.status == profile.STATUS_ACTIVE:
        _close(source_key)
    else:
        _upsert(
            source_key,
            recipient=None,
            audience=Notification.AUDIENCE_STAFF,
            category='member_access',
            source_type='member_access',
            source_id=profile.pk,
            title='Blocked / suspended members',
            body=f'{profile.user.get_username()} is now {profile.get_status_display().lower()}.',
            url=_safe_reverse(
                'admin:blackboard_memberprofile_change', args=[profile.pk],
            ),
            icon='user-slash',
            tone=Notification.TONE_WARNING,
            permission='blackboard.manage_member_access',
            status=Notification.STATUS_PENDING,
            requires_action=True,
            created_at=profile.created_at or timezone.now(),
            expires_at=None,
            resolved_at=None,
            completed_at=None,
        )

    # A short-lived "new member" information row.  It disappears once read or
    # after seven days, matching the old dashboard's seven-day counter.
    new_key = f'new_member:{profile.pk}'
    cutoff = timezone.now() - timedelta(days=7)
    if profile.created_at and profile.created_at >= cutoff:
        _upsert(
            new_key,
            recipient=None,
            audience=Notification.AUDIENCE_STAFF,
            category='new_member',
            source_type='new_member',
            source_id=profile.pk,
            title='New members',
            body=f'{profile.user.get_username()} created a member profile.',
            url=_safe_reverse(
                'admin:blackboard_memberprofile_change', args=[profile.pk],
            ),
            icon='id-card',
            tone=Notification.TONE_INFO,
            permission='blackboard.manage_member_access',
            status=Notification.STATUS_ACTIVE,
            requires_action=False,
            created_at=profile.created_at,
            expires_at=profile.created_at + timedelta(days=7),
            resolved_at=None,
            completed_at=None,
        )
    else:
        _close(new_key)


def sync_subscriber(subscriber):
    source_key = f'subscriber:{subscriber.pk}'
    cutoff = timezone.now() - timedelta(days=7)
    if not subscriber.is_active or subscriber.subscribed_at < cutoff:
        _close(source_key)
        return
    _upsert(
        source_key,
        recipient=None,
        audience=Notification.AUDIENCE_STAFF,
        category='subscriber',
        source_type='subscriber',
        source_id=subscriber.pk,
        title='New newsletter subscribers (7 days)',
        body=f'{subscriber.email} subscribed to the newsletter.',
        url=_safe_reverse('admin:home_subscriber_changelist'),
        icon='mail-open',
        tone=Notification.TONE_INFO,
        permission='home.manage_subscribers',
        status=Notification.STATUS_ACTIVE,
        requires_action=False,
        created_at=subscriber.subscribed_at,
        expires_at=subscriber.subscribed_at + timedelta(days=7),
        resolved_at=None,
        completed_at=None,
    )


def sync_event_rsvp(rsvp):
    source_key = f'event_rsvp:{rsvp.pk}'
    cutoff = timezone.now() - timedelta(days=7)
    if rsvp.created_at < cutoff:
        _close(source_key)
        return
    _upsert(
        source_key,
        recipient=None,
        audience=Notification.AUDIENCE_STAFF,
        category='event_rsvp',
        source_type='event_rsvp',
        source_id=rsvp.pk,
        title='New event RSVPs (7 days)',
        body=f'{rsvp.name} RSVPed for {rsvp.event.title or "an event"}.',
        url=_safe_reverse('admin:blackboard_eventrsvp_change', args=[rsvp.pk]),
        icon='clipboard',
        tone=Notification.TONE_INFO,
        permission='blackboard.manage_rsvps',
        status=Notification.STATUS_ACTIVE,
        requires_action=False,
        created_at=rsvp.created_at,
        expires_at=rsvp.created_at + timedelta(days=7),
        resolved_at=None,
        completed_at=None,
    )


def sync_membership(membership, notify_member=False):
    pending_key = f'membership_pending:{membership.pk}'
    if membership.status == 'pending':
        _upsert(
            pending_key,
            recipient=None,
            audience=Notification.AUDIENCE_STAFF,
            category='membership',
            source_type='membership_pending',
            source_id=membership.pk,
            title='Membership applications awaiting approval',
            body=f'{membership.full_name} submitted church membership details.',
            url=_safe_reverse(
                'admin:members_churchmembership_profile',
                args=[membership.pk],
            ),
            icon='id-card',
            tone=Notification.TONE_ATTENTION,
            permission='members.manage_membership',
            status=Notification.STATUS_PENDING,
            requires_action=True,
            created_at=membership.created_at or timezone.now(),
            expires_at=None,
            resolved_at=None,
            completed_at=None,
        )
    else:
        _close(pending_key)

    new_key = f'membership_new:{membership.pk}'
    cutoff = timezone.now() - timedelta(days=7)
    if membership.created_at and membership.created_at >= cutoff:
        _upsert(
            new_key,
            recipient=None,
            audience=Notification.AUDIENCE_STAFF,
            category='membership',
            source_type='membership_new',
            source_id=membership.pk,
            title='New church memberships',
            body=f'{membership.full_name} joined the church membership records.',
            url=_safe_reverse(
                'admin:members_churchmembership_profile',
                args=[membership.pk],
            ),
            icon='id-card',
            tone=Notification.TONE_INFO,
            permission='members.manage_membership',
            status=Notification.STATUS_ACTIVE,
            requires_action=False,
            created_at=membership.created_at,
            expires_at=membership.created_at + timedelta(days=7),
            resolved_at=None,
            completed_at=None,
        )
    else:
        _close(new_key)

    # Member-facing update.  Only a real status transition creates a new row;
    # a routine save (or the global repair command) must not replay old events.
    if notify_member:
        member_key = f'membership_member:{membership.pk}:{membership.status}'
        labels = {
            'pending': 'Membership application received',
            'active': 'Membership approved',
            'inactive': 'Membership status updated',
            'rejected': 'Membership application not approved',
        }
        _upsert(
            member_key,
            recipient=membership.user,
            audience=Notification.AUDIENCE_MEMBER,
            category='membership',
            source_type='membership_member',
            source_id=membership.pk,
            title=labels.get(
                membership.status, 'Membership status updated',
            ),
            body=(
                'Your church membership record is now '
                f'{membership.get_status_display().lower()}.'
            ),
            url=_safe_reverse('members:account_profile') + '#membership',
            icon='id-card',
            tone=(
                Notification.TONE_ATTENTION
                if membership.status in ('pending', 'rejected')
                else Notification.TONE_INFO
            ),
            permission='',
            status=Notification.STATUS_ACTIVE,
            requires_action=False,
            created_at=membership.updated_at or membership.created_at or timezone.now(),
            expires_at=None,
            resolved_at=None,
            completed_at=None,
        )
        Notification.objects.filter(
            source_type='membership_member',
            source_id=membership.pk,
            status__in=Notification.OPEN_STATUSES,
        ).exclude(source_key=member_key).update(
            status=Notification.STATUS_RESOLVED,
            resolved_at=timezone.now(),
            updated_at=timezone.now(),
        )


def sync_announcement(announcement):
    source_key = f'announcement:{announcement.pk}'
    today = timezone.localdate()
    cutoff = today - timedelta(days=30)
    if not announcement.is_published or announcement.date < cutoff:
        _close(source_key)
        return
    _upsert(
        source_key,
        recipient=None,
        audience=Notification.AUDIENCE_PUBLIC,
        category='announcement',
        source_type='announcement',
        source_id=announcement.pk,
        title='Church announcement',
        body=(announcement.title or announcement.body or 'New announcement')[:220],
        url=_safe_reverse('home:home') + '#announcements',
        icon='bullhorn',
        tone=Notification.TONE_INFO,
        permission='',
        status=Notification.STATUS_ACTIVE,
        requires_action=False,
        created_at=_start_of_day(announcement.date),
        expires_at=_end_of_day(announcement.date + timedelta(days=30)),
        resolved_at=None,
        completed_at=None,
    )


def sync_event(event):
    source_key = f'event:{event.pk}'
    today = timezone.localdate()
    if not event.is_published or event.date < today:
        _close(source_key, status=Notification.STATUS_COMPLETED)
        return
    _upsert(
        source_key,
        recipient=None,
        audience=Notification.AUDIENCE_PUBLIC,
        category='event',
        source_type='event',
        source_id=event.pk,
        title='Upcoming event',
        body=f'{event.title or "Church event"} on {event.date:%d %b %Y}.',
        url=event.link or (_safe_reverse('home:home') + '#events'),
        icon='calendar',
        tone=Notification.TONE_INFO,
        permission='',
        status=Notification.STATUS_ACTIVE,
        requires_action=False,
        created_at=min(_start_of_day(event.date), timezone.now()),
        expires_at=_end_of_day(event.date),
        resolved_at=None,
        completed_at=None,
    )


def sync_admin_message(message, user):
    """Create one staff notification per recipient of an internal message."""
    if not user or not user.is_authenticated:
        return
    try:
        from communications.services import can_use_portal

        if not can_use_portal(user):
            return
    except Exception:
        return
    source_key = f'admin_message:{message.pk}:{user.pk}'
    sender = message.sender_name if message.sender_id else 'Staff'
    preview = (message.body or 'New attachment').strip().replace('\n', ' ')
    inbox_url = _safe_reverse('communications:inbox')
    if inbox_url:
        inbox_url = f'{inbox_url}?conversation={message.conversation_id}'
    _upsert(
        source_key,
        recipient=user,
        audience=Notification.AUDIENCE_STAFF,
        category='admin_message',
        source_type='admin_message',
        source_id=message.pk,
        title='New internal admin message',
        body=f'{sender}: {preview[:140]}',
        url=inbox_url or _safe_reverse('admin:index'),
        icon='message',
        tone=Notification.TONE_ATTENTION,
        permission='communications.manage_communications',
        status=Notification.STATUS_ACTIVE,
        requires_action=True,
        created_at=message.created_at or timezone.now(),
        expires_at=None,
        resolved_at=None,
        completed_at=None,
    )


def resolve_admin_message_notifications(user, message_ids=None, conversation=None):
    if not user or not user.is_authenticated:
        return
    queryset = Notification.objects.filter(
        recipient=user,
        source_type='admin_message',
        status__in=Notification.OPEN_STATUSES,
    )
    if message_ids is not None:
        queryset = queryset.filter(source_id__in=list(message_ids))
    elif conversation is not None:
        queryset = queryset.filter(
            source_id__in=conversation.messages.values('pk'),
        )
    queryset.update(
        status=Notification.STATUS_RESOLVED,
        resolved_at=timezone.now(),
        updated_at=timezone.now(),
    )


def sync_admin_messages_for_user(user):
    """Back-fill unread internal staff messages for one administrator."""
    if not user or not user.is_authenticated:
        return
    try:
        from communications.models import ConversationParticipant, Message
        from communications.services import can_use_portal
    except Exception:
        return

    if not can_use_portal(user):
        # Access may have been revoked after a notification was created. Clear
        # any internal-message previews so the bell cannot expose them.
        Notification.objects.filter(
            recipient=user,
            source_type='admin_message',
            status__in=Notification.OPEN_STATUSES,
        ).update(
            status=Notification.STATUS_RESOLVED,
            resolved_at=timezone.now(),
            updated_at=timezone.now(),
        )
        return

    try:
        cursor = ConversationParticipant.objects.filter(
            conversation=OuterRef('conversation'),
            user=user,
        ).values('last_read_at')[:1]
        queryset = (
            Message.objects.filter(
                conversation__participants__user=user,
                conversation__is_archived=False,
            )
            .exclude(sender=user)
            .annotate(read_cursor=Subquery(cursor))
            .filter(created_at__gt=F('read_cursor'))
            .select_related('sender', 'conversation')
            .order_by('-created_at', '-pk')
        )
        message_ids = list(queryset.values_list('pk', flat=True))
        for message in queryset[:50]:
            sync_admin_message(message, user)
        # Anything already read, or any conversation the user has since left,
        # must leave the open dropdown. This also runs when there are no unread
        # messages left, because an old preview would otherwise survive after
        # a member was removed from a private group.
        Notification.objects.filter(
            recipient=user,
            source_type='admin_message',
            status__in=Notification.OPEN_STATUSES,
        ).exclude(source_id__in=message_ids).update(
            status=Notification.STATUS_RESOLVED,
            resolved_at=timezone.now(),
            updated_at=timezone.now(),
        )
    except Exception:
        # The portal is optional on a fresh install; a missing table must never
        # break the rest of the admin console.
        return


def sync_notifications():
    """Back-fill/repair notifications from the current source records.

    Safe to run repeatedly; it is used by the management command and is also
    useful after importing legacy data.
    """
    from blackboard.models import Announcement, Event, EventRsvp, MemberProfile
    from contact.models import ContactMessage
    from home.models import Subscriber, Testimony
    from members.models import ChurchMembership

    unread_contact_ids = list(
        ContactMessage.objects.filter(
            is_read=False, is_from_admin=False,
        ).values_list('pk', flat=True)
    )
    for message in ContactMessage.objects.filter(
        is_read=False, is_from_admin=False,
    ):
        sync_contact_message(message)
    _close_missing('contact', unread_contact_ids)

    pending_testimony_ids = list(
        Testimony.objects.filter(is_approved=False).values_list('pk', flat=True)
    )
    for testimony in Testimony.objects.filter(is_approved=False):
        sync_testimony(testimony)
    _close_missing('testimony', pending_testimony_ids)

    blocked_ids = list(
        MemberProfile.objects.exclude(status=MemberProfile.STATUS_ACTIVE)
        .values_list('pk', flat=True)
    )
    for profile in MemberProfile.objects.select_related('user'):
        sync_member_profile(profile)
    _close_missing('member_access', blocked_ids)

    for membership in ChurchMembership.objects.select_related('user'):
        sync_membership(membership)

    for subscriber in Subscriber.objects.filter(
        subscribed_at__gte=timezone.now() - timedelta(days=7),
    ):
        sync_subscriber(subscriber)

    for rsvp in EventRsvp.objects.filter(
        created_at__gte=timezone.now() - timedelta(days=7),
    ).select_related('event'):
        sync_event_rsvp(rsvp)

    for announcement in Announcement.objects.all():
        sync_announcement(announcement)
    for event in Event.objects.all():
        sync_event(event)

    # Expired information rows are closed so history reflects the lifecycle.
    now = timezone.now()
    Notification.objects.filter(
        status__in=Notification.OPEN_STATUSES,
        expires_at__lte=now,
    ).update(
        status=Notification.STATUS_RESOLVED,
        resolved_at=now,
        updated_at=now,
    )
    return Notification.objects.count()
