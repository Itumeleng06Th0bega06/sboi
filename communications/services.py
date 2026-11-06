"""Query and mutation helpers for the admin communications portal.

Keeping these rules in one module makes it harder for a view to accidentally
skip a membership check: every read uses ``conversations_for_user`` and every
group change goes through a helper that verifies the participant's role.
"""

from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import (
    Count,
    IntegerField,
    Max,
    OuterRef,
    Q,
    Subquery,
    Value,
)
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import (
    Conversation,
    ConversationParticipant,
    Message,
    MessageAttachment,
    MessageRead,
)

User = get_user_model()

PORTAL_PERMISSION = 'communications.manage_communications'


def name_initials(name):
    parts = [part for part in (name or '').split() if part]
    if not parts:
        return 'S'
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def can_use_portal(user):
    """Only active staff explicitly granted the portal permission may enter.

    Being ``is_staff`` is not enough on its own, so creating a staff account
    never silently exposes internal conversations.
    """
    return bool(
        user
        and user.is_authenticated
        and user.is_active
        and user.is_staff
        and user.has_perm(PORTAL_PERMISSION)
    )


def portal_users(exclude=None):
    """Active staff accounts that may be picked as group members/recipients."""
    permission = Permission.objects.filter(
        content_type__app_label='communications',
        codename='manage_communications',
    ).first()
    queryset = User.objects.filter(is_active=True, is_staff=True)
    if permission is not None:
        queryset = queryset.filter(
            Q(is_superuser=True)
            | Q(user_permissions=permission)
            | Q(groups__permissions=permission)
        ).distinct()
    else:
        queryset = queryset.none()
    if exclude is not None:
        queryset = queryset.exclude(pk=exclude.pk)
    return queryset.order_by('first_name', 'last_name', 'username')


def _unread_subquery(user):
    """Correlated count of messages newer than this user's read cursor."""
    # This subquery is nested inside the message subquery below, so the
    # OuterRef must point at the message's conversation rather than the
    # conversation's own primary key. Using ``pk`` here silently compared
    # participant.conversation_id to message.id, which happened to work only
    # when those sequences matched.
    cursor = ConversationParticipant.objects.filter(
        conversation=OuterRef('conversation_id'), user=user,
    ).values('last_read_at')[:1]
    return (
        Message.objects.filter(conversation=OuterRef('pk'))
        .exclude(sender=user)
        .filter(created_at__gt=Subquery(cursor))
        .order_by()
        .values('conversation')
        .annotate(total=Count('pk'))
        .values('total')
    )


def conversations_for_user(user):
    """Every group/direct conversation the user is an active participant in."""
    return (
        Conversation.objects.filter(
            participants__user=user,
            is_archived=False,
        )
        .annotate(
            unread_count=Coalesce(
                Subquery(_unread_subquery(user), output_field=IntegerField()),
                Value(0),
            ),
            last_message_id=Subquery(
                Message.objects.filter(conversation=OuterRef('pk'))
                .order_by('-created_at', '-pk')
                .values('pk')[:1]
            ),
        )
        .select_related('created_by')
        .prefetch_related('participants__user')
        .distinct()
    )


def conversation_for_user(user, conversation_id):
    """Resolve a conversation only when the user is a participant."""
    return conversations_for_user(user).filter(pk=conversation_id).first()


def participant_for(conversation, user):
    return ConversationParticipant.objects.filter(
        conversation=conversation, user=user,
    ).first()


def conversation_summaries(user, query=''):
    """Conversation list rows with unread counts, previews and timestamps."""
    queryset = conversations_for_user(user)
    query = (query or '').strip()
    if query:
        queryset = queryset.filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(participants__user__first_name__icontains=query)
            | Q(participants__user__last_name__icontains=query)
            | Q(participants__user__username__icontains=query)
            | Q(messages__body__icontains=query)
        ).distinct()

    conversations = list(queryset)
    if not conversations:
        return []

    # Prefetch the latest message for every row in two small queries instead of
    # one query per conversation.
    ids = [conversation.pk for conversation in conversations]
    latest_by_conversation = {}
    latest_ids = (
        Message.objects.filter(conversation_id__in=ids)
        .values('conversation_id')
        .annotate(latest_id=Max('pk'))
        .values_list('latest_id', flat=True)
    )
    for message in (
        Message.objects.filter(pk__in=list(latest_ids))
        .select_related('sender')
        .prefetch_related('attachments')
    ):
        latest_by_conversation[message.conversation_id] = message

    rows = []
    for conversation in conversations:
        latest = latest_by_conversation.get(conversation.pk)
        if latest is None:
            preview = 'No messages yet'
        elif latest.body.strip():
            preview = latest.body.strip().replace('\n', ' ')
        elif latest.attachments.exists():
            preview = f'Attachment: {latest.attachments.first().original_name}'
        else:
            preview = 'No messages yet'

        participants = list(conversation.participants.all())
        other = None
        if conversation.is_direct:
            other = next(
                (item for item in participants if item.user_id != user.pk),
                None,
            )
            display_name = (
                other.display_name if other is not None else 'Direct message'
            )
        else:
            display_name = conversation.name or 'Untitled group'

        rows.append({
            'conversation': conversation,
            'display_name': display_name,
            'initials': name_initials(display_name),
            'other': other,
            'preview': preview[:90],
            'last_message': latest,
            'last_activity': (
                latest.created_at if latest is not None
                else conversation.updated_at
            ),
            'unread_count': getattr(conversation, 'unread_count', 0),
            'participant_count': len(participants),
        })
    return rows


def unread_total(user):
    if not can_use_portal(user):
        return 0
    return sum(row['unread_count'] for row in conversation_summaries(user))


# ---------------------------------------------------------------------------
# Admin community: church-office threads and member-to-member moderation
# ---------------------------------------------------------------------------

def avatar_url_for(user):
    """Return a member avatar URL without assuming a profile row exists."""
    profile = getattr(user, 'member_profile', None)
    if profile is not None and profile.avatar:
        try:
            return profile.avatar.url
        except ValueError:
            return ''
    return ''


def office_conversation_rows(query='', limit=80):
    """One row per member who has written to the church office.

    Only threads tied to a member account belong here: anonymous contact-form
    submissions stay in the existing contact admin. ``unread`` counts the
    member's messages an administrator has not read yet, matching
    ``ContactMessage.is_read``.
    """
    from contact.models import ContactMessage

    queryset = (
        ContactMessage.objects
        .filter(user__isnull=False)
        .select_related('user', 'sender')
    )
    query = (query or '').strip()
    if query:
        queryset = queryset.filter(
            Q(user__username__icontains=query)
            | Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
            | Q(user__email__icontains=query)
            | Q(subject__icontains=query)
            | Q(message__icontains=query)
        )

    groups = {}
    for message in queryset.order_by('created_at', 'pk'):
        row = groups.get(message.user_id)
        if row is None:
            row = {
                'user': message.user,
                'latest': message,
                'unread': 0,
                'total': 0,
            }
            groups[message.user_id] = row
        row['latest'] = message
        row['total'] += 1
        if not message.is_from_admin and not message.is_read:
            row['unread'] += 1

    rows = sorted(
        groups.values(),
        key=lambda item: item['latest'].created_at,
        reverse=True,
    )[:limit]
    for row in rows:
        display_name = (
            row['user'].get_full_name() or row['user'].get_username()
        )
        row['display_name'] = display_name
        row['initials'] = name_initials(display_name)
        row['avatar_url'] = avatar_url_for(row['user'])
        row['membership'] = getattr(row['user'], 'church_membership', None)
    return rows


def office_thread_for(member, query=''):
    """Chronological church-office messages for one member."""
    from contact.models import ContactMessage

    queryset = (
        ContactMessage.objects
        .filter(user=member)
        .select_related('sender')
        .order_by('created_at', 'pk')
    )
    query = (query or '').strip()
    if query:
        queryset = queryset.filter(
            Q(message__icontains=query)
            | Q(subject__icontains=query)
        )
    return queryset


def mark_office_thread_read(member):
    """Mark the member's messages as read, firing notification cleanup."""
    from contact.models import ContactMessage

    unread = list(
        ContactMessage.objects.filter(
            user=member,
            is_from_admin=False,
            is_read=False,
        )
    )
    for message in unread:
        message.is_read = True
        # Saving each row lets the shared notification receiver close the
        # matching staff-bell entry, exactly like the contact admin does.
        message.save(update_fields=['is_read'])
    return len(unread)


def office_unread_total():
    from contact.models import ContactMessage

    return ContactMessage.objects.filter(
        user__isnull=False,
        is_from_admin=False,
        is_read=False,
    ).count()


def dm_moderation_rows(query='', limit=80):
    """Member-to-member direct threads, newest first.

    These rows are only ever built for superusers. Staff-to-staff and
    staff-to-member threads are deliberately excluded: the first belongs in
    staff chat, the second is a member inbox conversation.
    """
    from members.models_comms import CommsDirectMessage, CommsDirectThread

    queryset = (
        CommsDirectThread.objects
        .filter(user_a__is_staff=False, user_b__is_staff=False)
        .select_related('user_a', 'user_b')
        .annotate(message_count=Count('messages'))
        .order_by('-last_message_at', '-updated_at', '-pk')
    )
    query = (query or '').strip()
    if query:
        queryset = queryset.filter(
            Q(user_a__username__icontains=query)
            | Q(user_a__first_name__icontains=query)
            | Q(user_a__last_name__icontains=query)
            | Q(user_b__username__icontains=query)
            | Q(user_b__first_name__icontains=query)
            | Q(user_b__last_name__icontains=query)
            | Q(messages__body__icontains=query)
        ).distinct()

    threads = list(queryset[:limit])
    if not threads:
        return []

    thread_ids = [thread.pk for thread in threads]
    latest_ids = (
        CommsDirectMessage.objects
        .filter(thread_id__in=thread_ids)
        .values('thread_id')
        .annotate(latest_id=Max('pk'))
        .values_list('latest_id', flat=True)
    )
    latest_by_thread = {
        message.thread_id: message
        for message in (
            CommsDirectMessage.objects
            .filter(pk__in=list(latest_ids))
            .select_related('sender')
        )
    }

    rows = []
    for thread in threads:
        latest = latest_by_thread.get(thread.pk)
        name_a = (
            thread.user_a.get_full_name() or thread.user_a.get_username()
        )
        name_b = (
            thread.user_b.get_full_name() or thread.user_b.get_username()
        )
        display_name = f'{name_a} & {name_b}'
        rows.append({
            'thread': thread,
            'display_name': display_name,
            'initials': (
                name_initials(name_a)[:1] + name_initials(name_b)[:1]
            ),
            'user_a': thread.user_a,
            'user_b': thread.user_b,
            'latest': latest,
            'preview': (
                latest.body.strip().replace('\n', ' ')
                if latest is not None else 'No messages yet'
            ),
            'last_activity': (
                latest.created_at if latest is not None
                else thread.updated_at
            ),
            'message_count': thread.message_count,
        })
    return rows


def unread_summary(user):
    """Return ``(total, latest_unread_conversation_id)`` for the admin bell."""
    if not can_use_portal(user):
        return 0, None
    rows = conversation_summaries(user)
    total = sum(row['unread_count'] for row in rows)
    latest = next(
        (row['conversation'].pk for row in rows if row['unread_count']),
        None,
    )
    return total, latest


def message_queryset(conversation, query=''):
    """Chronological messages with receipts and attachments prefetched."""
    queryset = (
        conversation.messages
        .select_related('sender', 'reply_to', 'reply_to__sender')
        .prefetch_related('attachments')
        .annotate(read_count=Count('receipts', distinct=True))
    )
    query = (query or '').strip()
    if query:
        queryset = queryset.filter(
            Q(body__icontains=query)
            | Q(attachments__original_name__icontains=query)
        ).distinct()
    return queryset.order_by('created_at', 'pk')


def mark_conversation_read(conversation, user):
    """Advance the read cursor and create per-message receipts."""
    participant = participant_for(conversation, user)
    if participant is None:
        return
    now = timezone.now()
    unread_messages = list(
        Message.objects.filter(
            conversation=conversation,
            created_at__gt=participant.last_read_at,
        )
        .exclude(sender=user)
        .values_list('pk', flat=True)
    )
    if unread_messages:
        MessageRead.objects.bulk_create(
            [
                MessageRead(message_id=message_id, user=user)
                for message_id in unread_messages
            ],
            ignore_conflicts=True,
        )
    ConversationParticipant.objects.filter(pk=participant.pk).update(
        last_read_at=now,
    )
    # Opening a thread also clears the matching staff-bell rows. This is
    # deliberately best-effort: the portal must still work if the optional
    # notifications app is unavailable on an older deployment.
    try:
        from notifications.services import resolve_admin_message_notifications

        resolve_admin_message_notifications(user, conversation=conversation)
    except Exception:
        pass


@transaction.atomic
def create_message(conversation, sender, body, reply_to=None, attachment=None,
                   content_type=''):
    """Create a message and its optional attachment in one transaction."""
    message = Message.objects.create(
        conversation=conversation,
        sender=sender,
        body=body,
        reply_to=reply_to,
    )
    if attachment is not None:
        MessageAttachment.objects.create(
            message=message,
            file=attachment,
            original_name=Path(attachment.name).name[:255],
            content_type=(content_type or '')[:120],
            size=getattr(attachment, 'size', 0) or 0,
        )
    now = message.created_at or timezone.now()
    Conversation.objects.filter(pk=conversation.pk).update(
        last_message_at=now,
        updated_at=now,
    )
    ConversationParticipant.objects.filter(
        conversation=conversation, user=sender,
    ).update(last_read_at=now)

    try:
        from notifications.services import sync_admin_message

        recipients = (
            conversation.participants
            .select_related('user')
            .exclude(user=sender)
        )
        for participant in recipients:
            sync_admin_message(message, participant.user)
    except Exception:
        # Notifications are a convenience; a missing table must not lose the
        # message itself.
        pass
    return message


@transaction.atomic
def create_group(creator, name, description, members=(), **settings):
    """Create a group and make the creator its owner."""
    conversation = Conversation.objects.create(
        kind=Conversation.KIND_GROUP,
        name=name.strip(),
        description=(description or '').strip(),
        created_by=creator,
        members_can_add_members=bool(settings.get('members_can_add_members')),
        members_can_edit_group=bool(settings.get('members_can_edit_group')),
    )
    now = timezone.now()
    participants = [
        ConversationParticipant(
            conversation=conversation,
            user=creator,
            role=ConversationParticipant.ROLE_OWNER,
            last_read_at=now,
        )
    ]
    seen = {creator.pk}
    for member in members:
        if member.pk in seen or not can_use_portal(member):
            continue
        seen.add(member.pk)
        participants.append(
            ConversationParticipant(
                conversation=conversation,
                user=member,
                role=ConversationParticipant.ROLE_MEMBER,
                last_read_at=now,
            )
        )
    ConversationParticipant.objects.bulk_create(participants)
    return conversation


@transaction.atomic
def get_or_create_direct(user, other):
    """Return the single direct thread shared by two authorised staff users."""
    if user.pk == other.pk:
        raise ValidationError('You cannot start a direct conversation with yourself.')
    if not can_use_portal(other):
        raise ValidationError('That account is not authorised for staff messages.')

    low, high = sorted((user.pk, other.pk))
    key = f'direct:{low}:{high}'
    conversation, created = Conversation.objects.get_or_create(
        direct_key=key,
        defaults={
            'kind': Conversation.KIND_DIRECT,
            'name': 'Direct message',
            'created_by': user,
        },
    )
    if created:
        now = timezone.now()
        ConversationParticipant.objects.bulk_create([
            ConversationParticipant(
                conversation=conversation,
                user=user,
                role=ConversationParticipant.ROLE_MEMBER,
                last_read_at=now,
            ),
            ConversationParticipant(
                conversation=conversation,
                user=other,
                role=ConversationParticipant.ROLE_MEMBER,
                last_read_at=now,
            ),
        ])
    else:
        # Direct threads have no membership management UI, but restoring both
        # participants here keeps an old thread usable if a record was edited
        # directly in the database.
        for participant_user in (user, other):
            ConversationParticipant.objects.get_or_create(
                conversation=conversation,
                user=participant_user,
                defaults={'role': ConversationParticipant.ROLE_MEMBER},
            )
    return conversation, created


def can_manage_group(user, conversation):
    participant = participant_for(conversation, user)
    return bool(
        conversation.is_group
        and participant is not None
        and participant.is_manager
    )


def can_add_members(user, conversation):
    participant = participant_for(conversation, user)
    if not conversation.is_group or participant is None:
        return False
    return participant.is_manager or conversation.members_can_add_members


def can_edit_group(user, conversation):
    participant = participant_for(conversation, user)
    if not conversation.is_group or participant is None:
        return False
    return participant.is_manager or conversation.members_can_edit_group


@transaction.atomic
def add_members(conversation, users):
    if not conversation.is_group:
        raise ValidationError('Members can only be added to group conversations.')
    existing = set(
        conversation.participants.values_list('user_id', flat=True)
    )
    now = timezone.now()
    additions = []
    for user in users:
        if user.pk in existing or not can_use_portal(user):
            continue
        existing.add(user.pk)
        additions.append(
            ConversationParticipant(
                conversation=conversation,
                user=user,
                role=ConversationParticipant.ROLE_MEMBER,
                last_read_at=now,
            )
        )
    ConversationParticipant.objects.bulk_create(additions)
    if additions:
        Conversation.objects.filter(pk=conversation.pk).update(updated_at=now)
    return len(additions)


@transaction.atomic
def remove_member(conversation, participant):
    if not conversation.is_group:
        raise ValidationError('Direct message participants cannot be removed.')
    if participant.role == ConversationParticipant.ROLE_OWNER:
        owners = conversation.participants.filter(
            role=ConversationParticipant.ROLE_OWNER,
        ).count()
        if owners <= 1:
            raise ValidationError('A group must keep at least one owner.')
    participant.delete()
    Conversation.objects.filter(pk=conversation.pk).update(
        updated_at=timezone.now(),
    )


@transaction.atomic
def leave_group(conversation, user):
    if not conversation.is_group:
        raise ValidationError('Direct messages cannot be left; they are private to both participants.')
    participant = participant_for(conversation, user)
    if participant is None:
        raise ValidationError('You are not a member of this group.')
    remaining = conversation.participants.exclude(pk=participant.pk)
    if not remaining.exists():
        conversation.delete()
        return
    if participant.role == ConversationParticipant.ROLE_OWNER:
        replacement = remaining.filter(role=ConversationParticipant.ROLE_OWNER).first()
        if replacement is None:
            replacement = remaining.select_related('user').first()
            replacement.role = ConversationParticipant.ROLE_OWNER
            replacement.save(update_fields=['role'])
    participant.delete()
    Conversation.objects.filter(pk=conversation.pk).update(
        updated_at=timezone.now(),
    )
