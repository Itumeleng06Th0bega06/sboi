"""Views for the private admin communications portal."""

import mimetypes
from datetime import timedelta
from functools import wraps
from pathlib import Path

from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from contact.forms import AdminReplyForm
from contact.models import ContactMessage
from members.models import ChurchMembership
from members.models_comms import (
    CommsDirectMessage,
    CommsDirectThread,
    CommsPost,
    CommsReaction,
)
from members.services import (
    direct_threads_for,
    interaction_blocked,
    is_user_online,
    notify_direct_message,
    notify_member_reply,
    online_members,
)
from members.views_comms import feed_page_for, feed_posts_for, serialize_posts

from .forms import (
    AddMembersForm,
    GroupForm,
    GroupSettingsForm,
    MessageForm,
    StartDirectForm,
)
from .models import Conversation, ConversationParticipant, MessageAttachment
from .services import (
    add_members,
    can_add_members,
    can_edit_group,
    can_manage_group,
    can_use_portal,
    conversation_for_user,
    conversation_summaries,
    create_group,
    create_message,
    dm_moderation_rows,
    get_or_create_direct,
    leave_group,
    delete_group,
    mark_conversation_read,
    mark_office_thread_read,
    message_queryset,
    name_initials,
    office_conversation_rows,
    office_thread_for,
    office_unread_total,
    participant_for,
    portal_users,
    remove_member,
    unread_total,
)


def portal_view(view):
    """Protect a view with the portal permission and the admin login flow."""

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not can_use_portal(request.user):
            raise PermissionDenied('Admin communications access is restricted.')
        return view(request, *args, **kwargs)

    return admin.site.admin_view(wrapped)


def _is_ajax(request):
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


def _purge_chat_retention():
    """Expire 90-day-old chats without requiring a cron job on small hosts."""
    from members.retention import purge_expired_chats_once_per_hour

    purge_expired_chats_once_per_hour()


COMMUNITY_VIEWS = {'feed', 'chat', 'members', 'profile'}


def _community_view(request):
    view = (request.GET.get('view') or '').strip().lower()
    return view if view in COMMUNITY_VIEWS else 'chat'


def _admin_identity(user):
    display_name = user.get_full_name() or user.get_username()
    return {
        'display_name': display_name,
        'initials': name_initials(display_name),
        'avatar_url': _admin_avatar_url(user),
    }


def _admin_avatar_url(user):
    profile = getattr(user, 'member_profile', None)
    if profile is not None and profile.avatar:
        try:
            return profile.avatar.url
        except ValueError:
            return ''
    return ''


def _member_directory(query='', limit=240):
    """Active accounts for the Members section, with church status."""
    accounts = (
        get_user_model().objects
        .filter(is_active=True)
        .select_related('member_profile', 'church_membership')
        .order_by('-is_staff', 'first_name', 'last_name', 'username')
    )
    query = (query or '').strip()
    if query:
        accounts = accounts.filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
        )

    rows = []
    for account in accounts[:limit]:
        membership = getattr(account, 'church_membership', None)
        display_name = (
            account.get_full_name() or account.get_username()
        )
        rows.append({
            'user': account,
            'display_name': display_name,
            'initials': name_initials(display_name),
            'avatar_url': _admin_avatar_url(account),
            'membership': membership,
            'status': membership.status if membership else '',
            'status_label': (
                membership.get_status_display() if membership else 'Visitor'
            ),
            'is_staff': account.is_staff,
            'is_superuser': account.is_superuser,
        })
    return rows


def _admin_direct_rows(user):
    """Private admin ↔ member conversations, newest first."""
    rows = []
    for thread in direct_threads_for(user)[:40]:
        other = thread.other_user(user)
        if other is None:
            continue
        last = (
            thread.messages
            .select_related('sender')
            .order_by('-created_at', '-pk')
            .first()
        )
        display_name = other.get_full_name() or other.get_username()
        rows.append({
            'thread': thread,
            'other': other,
            'display_name': display_name,
            'avatar_url': _admin_avatar_url(other),
            'initials': name_initials(display_name),
            'online': is_user_online(other),
            'last_body': last.body if last else '',
            'last_at': last.created_at if last else None,
            'unread': thread.unread_count(user),
        })
    return rows


def _admin_online_rows(user, thread_by_member):
    """Active member accounts online right now, with any existing thread."""
    rows = []
    for person in online_members(user, limit=24):
        if person.is_staff:
            continue
        display_name = person.get_full_name() or person.get_username()
        rows.append({
            'member': person,
            'display_name': display_name,
            'avatar_url': _admin_avatar_url(person),
            'initials': name_initials(display_name),
            'thread': thread_by_member.get(person.pk),
        })
    return rows


def _inbox_context(request, group_form=None, direct_form=None, open_dialog=''):
    user = request.user
    community_view = _community_view(request)
    query = (request.GET.get('q') or '').strip()
    message_query = (request.GET.get('mq') or '').strip()
    channel = (request.GET.get('channel') or '').strip().lower()

    selected = None
    selected_id = request.GET.get('conversation')
    if selected_id:
        try:
            selected_id = int(selected_id)
        except (TypeError, ValueError):
            selected_id = None
    if selected_id:
        selected = conversation_for_user(user, selected_id)
        if selected is not None:
            channel = 'staff'

    selected_context = {}
    if selected is not None:
        mark_conversation_read(selected, user)
        selected_participant = participant_for(selected, user)
        existing_ids = selected.participants.values_list('user_id', flat=True)
        available_users = portal_users(exclude=user).exclude(
            pk__in=existing_ids,
        )
        display_name = selected.display_name_for(user)
        selected_context = {
            'selected': selected,
            'display_name': display_name,
            'conversation_initials': name_initials(display_name),
            'other_participant': selected.other_participant(user),
            'selected_participant': selected_participant,
            'thread_messages': message_queryset(selected, message_query),
            'message_query': message_query,
            'participants': selected.participants.select_related('user'),
            'can_manage': can_manage_group(user, selected),
            'can_add_members': can_add_members(user, selected),
            'can_edit_group': can_edit_group(user, selected),
            'available_users': available_users,
            'add_members_form': AddMembersForm(
                portal_queryset=available_users,
            ),
            'group_settings_form': GroupSettingsForm(initial={
                'name': selected.name,
                'description': selected.description,
                'members_can_add_members': selected.members_can_add_members,
                'members_can_edit_group': selected.members_can_edit_group,
            }),
        }

    # Church-office thread: any communications staff member may read and
    # answer the member's existing ContactMessage conversation.
    office_member = None
    office_messages = []
    if community_view == 'chat' and channel == 'office':
        member_id = (request.GET.get('member') or '').strip()
        if member_id.isdigit():
            office_member = get_object_or_404(
                get_user_model().objects.filter(is_active=True),
                pk=int(member_id),
            )
            mark_office_thread_read(office_member)
            office_messages = list(
                office_thread_for(office_member, message_query)[:500]
            )

    # Member-to-member direct messages are a superuser-only moderation view.
    dm_thread = None
    dm_messages = []
    if community_view == 'chat' and channel == 'dm':
        if not user.is_superuser:
            raise PermissionDenied(
                'Only a superuser may read member-to-member conversations.',
            )
        thread_id = (request.GET.get('thread') or '').strip()
        if thread_id.isdigit():
            dm_thread = get_object_or_404(
                CommsDirectThread.objects.select_related('user_a', 'user_b'),
                pk=int(thread_id),
            )
            if dm_thread.user_a.is_staff or dm_thread.user_b.is_staff:
                raise Http404('Conversation not found.')
            dm_messages = list(
                dm_thread.messages
                .select_related('sender')
                .order_by('created_at', 'pk')[:500]
            )

    # The signed-in admin's own private conversations live in the same
    # CommsDirectThread model as member DMs, so a message started here shows
    # up in both the admin inbox and the member's inbox.
    admin_thread = None
    admin_thread_other = None
    admin_thread_messages = []
    if community_view == 'chat' and channel != 'dm':
        thread_key = (request.GET.get('thread') or '').strip()
        if thread_key.isdigit():
            admin_thread = get_object_or_404(
                direct_threads_for(user),
                pk=int(thread_key),
            )
            admin_thread_other = admin_thread.other_user(user)
            if (
                admin_thread_other is None
                or interaction_blocked(user, admin_thread_other)
            ):
                raise Http404('Conversation not found.')
            admin_thread.mark_read(user)
            admin_thread_messages = list(
                admin_thread.messages
                .select_related('sender')
                .order_by('created_at', 'pk')[:300]
            )

    # Build the staff list after the selected thread has been marked read so
    # its unread badge does not survive the page load that opened it.
    rows = conversation_summaries(user, query)
    users = portal_users(exclude=user)
    office_rows = office_conversation_rows(query)
    office_unread = office_unread_total()
    dm_rows = dm_moderation_rows(query) if user.is_superuser else []

    admin_thread_rows = _admin_direct_rows(user) if community_view == 'chat' else []
    admin_thread_by_member = {
        row['other'].pk: row['thread'] for row in admin_thread_rows
    }
    admin_online_rows = (
        _admin_online_rows(user, admin_thread_by_member)
        if community_view == 'chat' else []
    )
    admin_dm_unread = sum(row['unread'] for row in admin_thread_rows)

    timeline_filter = (request.GET.get('filter') or 'all').strip().lower()
    if timeline_filter not in {'all', 'posts', 'chats'}:
        timeline_filter = 'all'

    posts = []
    feed_has_more = False
    feed_next_before = ''
    if community_view in {'feed', 'chat'}:
        posts, feed_has_more, feed_next_before = feed_page_for(
            feed_posts_for(user), user,
        )

    member_directory = []
    if community_view in {'feed', 'chat', 'members'}:
        member_directory = _member_directory(query)

    member_total = get_user_model().objects.filter(
        is_active=True, is_staff=False,
    ).count()

    # Unified iChat timeline: community posts and conversation activity,
    # merged chronologically. Conversation previews only render for people who
    # are allowed to see them (office/staff for comms staff, member DMs for
    # superusers); nobody else ever receives this content.
    timeline_mode = community_view in {'feed', 'chat'} and not (
        selected or office_member or dm_thread
    )
    timeline_items = [] if timeline_mode else None
    if timeline_mode:
        for post in posts:
            timeline_items.append({
                'kind': 'post',
                'sort': post.created_at,
                'post': post,
            })
        if timeline_filter in {'all', 'chats'}:
            timeline_base = reverse('communications:inbox')
            for row in rows:
                conversation = row['conversation']
                timeline_items.append({
                    'kind': 'chat',
                    'sort': row['last_activity'],
                    'kind_label': (
                        'Direct message' if conversation.is_direct else 'Staff group'
                    ),
                    'name': row['display_name'],
                    'initials': row['initials'],
                    'avatar_url': '',
                    'preview': row['preview'],
                    'time': row['last_activity'],
                    'unread': row['unread_count'],
                    'url': f'{timeline_base}?view=chat&conversation={conversation.pk}',
                })
            for row in office_rows:
                latest = row['latest']
                text = (latest.message or '').strip().replace('\n', ' ')
                timeline_items.append({
                    'kind': 'chat',
                    'sort': latest.created_at,
                    'kind_label': 'Church office',
                    'name': row['display_name'],
                    'initials': row['initials'],
                    'avatar_url': row.get('avatar_url', ''),
                    'preview': text or 'Attachment',
                    'time': latest.created_at,
                    'unread': row['unread'],
                    'url': (
                        f'{timeline_base}?view=chat&channel=office&member={row["user"].pk}'
                    ),
                })
            for row in dm_rows:
                latest = row.get('latest')
                text = (
                    latest.body.strip().replace('\n', ' ')
                    if latest is not None else 'No messages yet'
                )
                timeline_items.append({
                    'kind': 'chat',
                    'sort': row['last_activity'],
                    'kind_label': 'Members · Moderation',
                    'name': row['display_name'],
                    'initials': row['initials'],
                    'avatar_url': '',
                    'preview': text,
                    'time': row['last_activity'],
                    'unread': 0,
                    'url': (
                        f'{timeline_base}?view=chat&channel=dm&thread={row["thread"].pk}'
                    ),
                })
        timeline_items.sort(
            key=lambda item: item['sort'] or timezone.now(),
            reverse=True,
        )
        if timeline_filter == 'posts':
            timeline_items = [i for i in timeline_items if i['kind'] == 'post']
        elif timeline_filter == 'chats':
            timeline_items = [i for i in timeline_items if i['kind'] == 'chat']
    staff_total = get_user_model().objects.filter(
        is_active=True, is_staff=True,
    ).count()
    identity = _admin_identity(user)
    admin_membership = (
        ChurchMembership.objects
        .select_related('user')
        .filter(user=user)
        .first()
    )

    context = admin.site.each_context(request)
    inbox_mode = community_view == 'chat' and timeline_filter == 'chats'
    context.update({
        'title': 'Admin Communications',
        'section_label': 'communications',
        'community_view': community_view,
        'community_heading': (
            'Inbox' if inbox_mode else {
                'feed': 'iChat',
                'chat': 'iChat',
                'members': 'Members',
                'profile': 'Profile',
            }.get(community_view, 'iChat')
        ),
        'community_lead': (
            'Church-office messages and private member conversations.'
            if inbox_mode else {
                'feed': 'Community posts and every conversation, in one stream.',
                'chat': 'Community posts and every conversation, in one stream.',
                'members': 'Everyone who belongs to the church community.',
                'profile': 'Your staff account and communication access.',
            }.get(community_view, '')
        ),
        'member_display_name': identity['display_name'],
        'member_initials': identity['initials'],
        'member_avatar_url': identity['avatar_url'],
        'admin_profile': {
            **identity,
            'user': user,
            'membership': admin_membership,
            'status_label': (
                admin_membership.get_status_display()
                if admin_membership else 'Staff account'
            ),
        },
        'conversation_rows': rows,
        'group_rows': [row for row in rows if not row['conversation'].is_direct],
        'conversation_query': query,
        'selected_id': selected.pk if selected else None,
        'group_form': group_form or GroupForm(portal_queryset=users),
        'direct_form': direct_form or StartDirectForm(portal_queryset=users),
        'portal_users': users,
        'open_dialog': open_dialog,
        'total_unread': unread_total(user),
        'office_rows': office_rows,
        'office_unread_total': office_unread,
        'office_member': office_member,
        'office_thread_messages': office_messages,
        'dm_rows': dm_rows,
        'dm_thread': dm_thread,
        'dm_messages': dm_messages,
        'can_moderate_dms': user.is_superuser,
        'chat_unread_total': unread_total(user) + office_unread + admin_dm_unread,
        'inbox_mode': inbox_mode,
        'admin_thread': admin_thread,
        'admin_thread_other': admin_thread_other,
        'admin_thread_messages': admin_thread_messages,
        'admin_thread_online': (
            is_user_online(admin_thread_other)
            if admin_thread_other is not None else False
        ),
        'admin_thread_avatar_url': (
            _admin_avatar_url(admin_thread_other)
            if admin_thread_other is not None else ''
        ),
        'admin_thread_initials': (
            name_initials(
                admin_thread_other.get_full_name()
                or admin_thread_other.get_username()
            )
            if admin_thread_other is not None else ''
        ),
        'admin_thread_rows': admin_thread_rows,
        'admin_online_rows': admin_online_rows,
        'admin_inbox_count': (
            sum(1 for row in office_rows if row['unread'])
            + sum(1 for row in admin_thread_rows if row['unread'])
        ),
        'member_directory': member_directory,
        'member_query': query,
        'member_total': member_total,
        'staff_total': staff_total,
        'inbox_url': reverse('communications:inbox'),
        'timeline_items': timeline_items,
        'timeline_mode': timeline_mode,
        'timeline_filter': timeline_filter,
        'posts': posts,
        'feed_posts': posts,
        'feed_member_accounts': member_directory,
        'feed_view': community_view == 'feed',
        'feed_member_count': member_total,
        'feed_staff_count': staff_total,
        'feed_latest_id': posts[0].pk if posts else '',
        'feed_has_more': feed_has_more,
        'feed_next_before': feed_next_before,
        'feed_surface': 'admin_feed',
        'post_reaction_choices': CommsReaction.REACTION_CHOICES,
        'message_query': message_query,
        **selected_context,
    })
    return context


@portal_view
@require_GET
def inbox(request):
    _purge_chat_retention()
    return render(
        request,
        'admin/communications/portal.html',
        _inbox_context(request),
    )


@portal_view
def admin_profile_edit(request):
    """Edit the signed-in staff member's admin profile (avatar, name, etc.)."""
    from members.forms import AccountProfileForm

    profile = getattr(request.user, 'member_profile', None)
    membership = getattr(request.user, 'church_membership', None)

    if request.method == 'POST':
        form = AccountProfileForm(
            request.POST,
            request.FILES,
            user=request.user,
            membership=membership,
            profile=profile,
        )
        if form.is_valid():
            form.save()
            if _is_ajax(request):
                identity = _admin_identity(request.user)
                return JsonResponse({
                    'ok': True,
                    'message': 'Your profile has been updated.',
                    'avatar_url': identity['avatar_url'],
                    'initials': identity['initials'],
                    'display_name': identity['display_name'],
                })
            messages.success(request, 'Your profile has been updated.')
            return redirect('communications:inbox')

        if _is_ajax(request):
            return JsonResponse({'ok': False, 'errors': form.errors}, status=400)
        messages.error(request, 'Please correct the errors below and try again.')
        return redirect('communications:inbox')

    # GET - return form fragment for modal
    form = AccountProfileForm(user=request.user, membership=membership, profile=profile)
    identity = _admin_identity(request.user)
    html = render_to_string(
        'admin/communications/_admin_profile_form.html',
        {
            'profile_form': form,
            'membership': membership,
            'admin_avatar_url': identity['avatar_url'],
            'admin_initials': identity['initials'],
        },
        request=request,
    )
    if _is_ajax(request):
        return JsonResponse({'ok': True, 'html': html})
    return HttpResponse(html)


@portal_view
@require_GET
def conversation_workspace(request, pk):
    _purge_chat_retention()
    conversation = conversation_for_user(request.user, pk)
    if conversation is None:
        raise Http404('Conversation not found.')
    mark_conversation_read(conversation, request.user)
    message_query = (request.GET.get('mq') or '').strip()
    participant = participant_for(conversation, request.user)
    existing_ids = conversation.participants.values_list('user_id', flat=True)
    available_users = portal_users(exclude=request.user).exclude(
        pk__in=existing_ids,
    )
    display_name = conversation.display_name_for(request.user)
    context = {
        'selected': conversation,
        'display_name': display_name,
        'conversation_initials': name_initials(display_name),
        'other_participant': conversation.other_participant(request.user),
        'selected_participant': participant,
        'thread_messages': message_queryset(conversation, message_query),
        'message_query': message_query,
        'participants': conversation.participants.select_related('user'),
        'can_manage': can_manage_group(request.user, conversation),
        'can_add_members': can_add_members(request.user, conversation),
        'can_edit_group': can_edit_group(request.user, conversation),
        'available_users': available_users,
        'add_members_form': AddMembersForm(portal_queryset=available_users),
        'group_settings_form': GroupSettingsForm(initial={
            'name': conversation.name,
            'description': conversation.description,
            'members_can_add_members': conversation.members_can_add_members,
            'members_can_edit_group': conversation.members_can_edit_group,
        }),
    }
    return render(
        request,
        'admin/communications/_workspace.html',
        context,
    )


@portal_view
@require_GET
def conversation_list(request):
    query = (request.GET.get('q') or '').strip()
    selected_id = request.GET.get('conversation')
    try:
        selected_id = int(selected_id) if selected_id else None
    except (TypeError, ValueError):
        selected_id = None
    return render(
        request,
        'admin/communications/_conversation_list.html',
        {
            'conversation_rows': conversation_summaries(request.user, query),
            'conversation_query': query,
            'selected_id': selected_id,
        },
    )


@portal_view
@require_GET
def conversation_messages(request, pk):
    """Polling endpoint: returns the latest rendered message history."""
    _purge_chat_retention()
    conversation = conversation_for_user(request.user, pk)
    if conversation is None:
        raise Http404('Conversation not found.')
    mark_conversation_read(conversation, request.user)
    query = (request.GET.get('mq') or '').strip()
    return render(
        request,
        'admin/communications/_messages.html',
        {
            'selected': conversation,
            'thread_messages': message_queryset(conversation, query),
            'message_query': query,
        },
    )


@portal_view
@require_POST
def send_message(request, pk):
    conversation = conversation_for_user(request.user, pk)
    if conversation is None:
        raise Http404('Conversation not found.')

    form = MessageForm(request.POST, request.FILES)
    if not form.is_valid():
        error = ' '.join(
            message for errors in form.errors.values() for message in errors
        ) or 'The message could not be sent.'
        if _is_ajax(request):
            return JsonResponse({'error': error}, status=400)
        messages.error(request, error)
        return redirect(
            f"{reverse('communications:inbox')}?view=chat&conversation={conversation.pk}"
        )

    reply_to = None
    reply_id = form.cleaned_data.get('reply_to')
    if reply_id:
        reply_to = conversation.messages.filter(pk=reply_id).first()

    attachment = form.cleaned_data.get('attachment')
    created_message = create_message(
        conversation,
        request.user,
        form.cleaned_data['body'],
        reply_to=reply_to,
        attachment=attachment,
        content_type=getattr(attachment, 'content_type', '') if attachment else '',
    )
    # Re-fetch through the annotated queryset so the receipt count is in the
    # same shape as messages rendered by the normal thread view.
    message = message_queryset(conversation).get(pk=created_message.pk)

    if _is_ajax(request):
        return render(
            request,
            'admin/communications/_message.html',
            {
                'message': message,
                'selected': conversation,
                'user': request.user,
            },
            status=201,
        )
    return redirect(
        f"{reverse('communications:inbox')}?view=chat&conversation={conversation.pk}"
    )


def _office_thread_url(member):
    return (
        f"{reverse('communications:inbox')}?view=chat"
        f"&channel=office&member={member.pk}"
    )


def _dm_thread_url(thread):
    return (
        f"{reverse('communications:inbox')}?view=chat"
        f"&channel=dm&thread={thread.pk}"
    )


def _notify_dm_moderation(message):
    """Tell both members that the church office wrote in their DM thread.

    A superuser message has a sender outside the two thread participants, so
    ``members.services.notify_direct_message`` cannot resolve a recipient.
    Creating the two member-facing rows here keeps the bell consistent without
    changing the member model.
    """
    from notifications.models import Notification

    thread = message.thread
    inbox_url = reverse('members:account_messages') + f'?thread={thread.pk}'
    created_at = message.created_at or timezone.now()
    for recipient in (thread.user_a, thread.user_b):
        Notification.objects.update_or_create(
            source_key=f'direct_message:{message.pk}:{recipient.pk}',
            defaults={
                'recipient': recipient,
                'audience': Notification.AUDIENCE_MEMBER,
                'category': 'direct_message',
                'source_type': 'direct_message',
                'source_id': message.pk,
                'title': 'Message from church administration',
                'body': (message.body or '')[:180],
                'url': inbox_url,
                'icon': 'message',
                'tone': Notification.TONE_INFO,
                'permission': '',
                'status': Notification.STATUS_ACTIVE,
                'requires_action': False,
                'created_at': created_at,
                'expires_at': None,
                'resolved_at': None,
                'completed_at': None,
            },
        )


@portal_view
@require_POST
def office_reply(request, user_id):
    """Reply in the member's existing church-office conversation."""
    member = get_object_or_404(
        get_user_model().objects.filter(is_active=True),
        pk=user_id,
    )
    target = _office_thread_url(member)
    form = AdminReplyForm(request.POST, request.FILES)
    if not form.is_valid():
        error = ' '.join(
            message for errors in form.errors.values() for message in errors
        ) or 'The reply could not be sent.'
        messages.error(request, error)
        return redirect(target)

    body = form.cleaned_data['message']
    duplicate = (
        ContactMessage.objects
        .filter(
            user=member,
            sender=request.user,
            is_from_admin=True,
            message=body,
            created_at__gte=timezone.now() - timedelta(seconds=30),
        )
        .order_by('-created_at')
        .first()
    )
    if duplicate is not None:
        messages.info(request, 'That reply was already sent.')
        return redirect(f'{target}#message-{duplicate.pk}')

    latest = (
        ContactMessage.objects
        .filter(user=member)
        .order_by('-created_at', '-pk')
        .first()
    )
    membership = ChurchMembership.objects.filter(user=member).first()
    reply = ContactMessage.objects.create(
        user=member,
        sender=request.user,
        name=request.user.get_full_name() or request.user.get_username(),
        email=(
            (latest.email if latest else '')
            or member.email
            or request.user.email
            or ''
        ),
        phone=(
            (latest.phone if latest else '')
            or (membership.phone if membership else '')
        ),
        subject=(
            (latest.subject if latest and latest.subject else '')
            or 'Reply from church administration'
        ),
        message=body,
        attachment=form.cleaned_data.get('attachment') or None,
        parent=latest,
        is_from_admin=True,
        is_read=True,
        read_by_member=False,
    )
    channel = (form.cleaned_data.get('channel') or 'email').strip().lower()
    notify_member_reply(reply)
    # Optional WhatsApp doorbell (generic, no message content).
    if channel in {'whatsapp', 'both'}:
        from members.services import _post_whatsapp_to
        membership = ChurchMembership.objects.filter(user=member).first()
        phone = (reply.phone or (membership.phone if membership else '') or '').strip()
        digits = ''.join(ch for ch in phone if ch.isdigit())
        if len(digits) >= 7:
            _post_whatsapp_to(
                digits,
                'You have a new private message from the Shekinah Blaze church '
                'administration. Sign in to your account to read and reply.',
            )
    messages.success(
        request,
        'Reply sent. The member will see it in their church-office inbox.',
    )
    return redirect(f'{target}#message-{reply.pk}')


@portal_view
@require_POST
def dm_reply(request, thread_id):
    """Superuser moderation note inside a member-to-member conversation."""
    if not request.user.is_superuser:
        raise PermissionDenied(
            'Only a superuser may write to member-to-member conversations.',
        )
    thread = get_object_or_404(
        CommsDirectThread.objects.select_related('user_a', 'user_b'),
        pk=thread_id,
    )
    if thread.user_a.is_staff or thread.user_b.is_staff:
        raise Http404('Conversation not found.')

    target = _dm_thread_url(thread)
    body = (request.POST.get('body') or '').replace('\x00', '').strip()[:2000]
    if not body:
        messages.error(request, 'Write a message before sending.')
        return redirect(target)

    message = CommsDirectMessage.objects.create(
        thread=thread,
        sender=request.user,
        body=body,
    )
    thread.last_message_at = message.created_at
    thread.save(update_fields=['last_message_at', 'updated_at'])
    _notify_dm_moderation(message)
    messages.success(
        request,
        'Moderation message sent. Both members can see it in their inbox.',
    )
    return redirect(f'{target}#dm-message-{message.pk}')


@portal_view
@require_POST
def dm_message_delete(request, thread_id, pk):
    """Remove a single message from a member-to-member conversation."""
    if not request.user.is_superuser:
        raise PermissionDenied(
            'Only a superuser may moderate member-to-member conversations.',
        )
    thread = get_object_or_404(
        CommsDirectThread.objects.select_related('user_a', 'user_b'),
        pk=thread_id,
    )
    if thread.user_a.is_staff or thread.user_b.is_staff:
        raise Http404('Conversation not found.')
    message = get_object_or_404(
        CommsDirectMessage,
        pk=pk,
        thread=thread,
    )
    from notifications.models import Notification

    Notification.objects.filter(
        source_type='direct_message',
        source_id=message.pk,
    ).delete()
    message.delete()

    latest = thread.messages.order_by('-created_at', '-pk').first()
    thread.last_message_at = latest.created_at if latest else None
    thread.save(update_fields=['last_message_at', 'updated_at'])
    messages.success(request, 'Message removed from the conversation.')
    return redirect(_dm_thread_url(thread))


@portal_view
@require_POST
def dm_thread_delete(request, thread_id):
    """Remove an entire member-to-member conversation."""
    if not request.user.is_superuser:
        raise PermissionDenied(
            'Only a superuser may moderate member-to-member conversations.',
        )
    thread = get_object_or_404(
        CommsDirectThread.objects.select_related('user_a', 'user_b'),
        pk=thread_id,
    )
    if thread.user_a.is_staff or thread.user_b.is_staff:
        raise Http404('Conversation not found.')

    from notifications.models import Notification

    message_ids = list(thread.messages.values_list('pk', flat=True))
    if message_ids:
        Notification.objects.filter(
            source_type='direct_message',
            source_id__in=message_ids,
        ).delete()
    thread.delete()
    messages.success(request, 'Member conversation removed.')
    return redirect(f"{reverse('communications:inbox')}?view=chat")


@portal_view
@require_POST
def create_group_view(request):
    users = portal_users(exclude=request.user)
    form = GroupForm(request.POST, portal_queryset=users)
    if form.is_valid():
        conversation = create_group(
            request.user,
            form.cleaned_data['name'],
            form.cleaned_data['description'],
            form.cleaned_data['members'],
            members_can_add_members=form.cleaned_data['members_can_add_members'],
            members_can_edit_group=form.cleaned_data['members_can_edit_group'],
        )
        messages.success(request, f'Group “{conversation.name}” created.')
        return redirect(
            f"{reverse('communications:inbox')}?view=chat&conversation={conversation.pk}"
        )

    context = _inbox_context(
        request,
        group_form=form,
        open_dialog='group',
    )
    return render(request, 'admin/communications/portal.html', context, status=400)


@portal_view
@require_POST
def start_direct_view(request):
    form = StartDirectForm(
        request.POST,
        portal_queryset=portal_users(exclude=request.user),
    )
    if form.is_valid():
        try:
            conversation, _created = get_or_create_direct(
                request.user,
                form.cleaned_data['recipient'],
            )
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
            return redirect('communications:inbox')
        return redirect(
            f"{reverse('communications:inbox')}?view=chat&conversation={conversation.pk}"
        )

    context = _inbox_context(
        request,
        direct_form=form,
        open_dialog='direct',
    )
    return render(request, 'admin/communications/portal.html', context, status=400)


def _member_thread_url(thread):
    return (
        f"{reverse('communications:inbox')}?view=chat"
        f"&filter=chats&thread={thread.pk}"
    )


@portal_view
@require_POST
def start_member_direct_view(request):
    """Open (or create) a private conversation between staff and a member.

    The thread uses the member inbox model, so it appears in the member's own
    inbox and in the admin inbox at the same time.
    """
    username = (request.POST.get('username') or '').strip()
    member = get_object_or_404(
        get_user_model().objects.filter(is_active=True),
        username=username,
    )
    inbox_url = f"{reverse('communications:inbox')}?view=chat&filter=chats"
    if member.pk == request.user.pk:
        return redirect(inbox_url)
    if interaction_blocked(request.user, member):
        messages.error(
            request,
            'You cannot start a conversation with this account.',
        )
        return redirect(inbox_url)

    thread = CommsDirectThread.for_users(request.user, member)
    return redirect(_member_thread_url(thread))


@portal_view
@require_POST
def send_member_direct_view(request, pk):
    """Send one message in the admin's private conversation with a member."""
    thread = get_object_or_404(
        direct_threads_for(request.user).select_related('user_a', 'user_b'),
        pk=pk,
    )
    other = thread.other_user(request.user)
    if other is None or interaction_blocked(request.user, other):
        raise Http404('Conversation not found.')

    body = (request.POST.get('body') or '').replace('\x00', '').strip()[:2000]
    if not body:
        if _is_ajax(request):
            return JsonResponse({
                'ok': False,
                'message': 'Write a message before sending.',
            }, status=400)
        messages.error(request, 'Write a message before sending.')
        return redirect(_member_thread_url(thread))

    message = CommsDirectMessage.objects.create(
        thread=thread,
        sender=request.user,
        body=body,
    )
    thread.last_message_at = message.created_at
    thread.save(update_fields=['last_message_at', 'updated_at'])
    thread.mark_read(request.user)
    notify_direct_message(message)

    if _is_ajax(request):
        html = render_to_string(
            'members/account/_direct_message_bubble.html',
            {'message': message, 'is_own': True},
            request=request,
        )
        return JsonResponse({
            'ok': True,
            'id': message.pk,
            'message': 'Message sent.',
            'html': html,
        })
    return redirect(_member_thread_url(thread))


@portal_view
@require_GET
def member_direct_poll(request, pk):
    """Poll the admin's private thread for new member messages."""
    thread = get_object_or_404(
        direct_threads_for(request.user),
        pk=pk,
    )
    other = thread.other_user(request.user)
    if other is None or interaction_blocked(request.user, other):
        raise Http404('Conversation not found.')

    after = (request.GET.get('after') or '').strip()
    queryset = (
        thread.messages
        .select_related('sender')
        .order_by('created_at', 'pk')
    )
    if after.isdigit():
        queryset = queryset.filter(pk__gt=int(after))
    if request.GET.get('read') == '1':
        thread.mark_read(request.user)

    payload = [
        {
            'id': message.pk,
            'html': render_to_string(
                'members/account/_direct_message_bubble.html',
                {
                    'message': message,
                    'is_own': message.sender_id == request.user.pk,
                },
                request=request,
            ),
        }
        for message in queryset
    ]
    return JsonResponse({'ok': True, 'messages': payload})


@portal_view
@require_POST
def update_group_view(request, pk):
    conversation = conversation_for_user(request.user, pk)
    if conversation is None:
        raise Http404('Conversation not found.')
    if not conversation.is_group:
        raise PermissionDenied('Direct conversations cannot be edited this way.')
    if not can_edit_group(request.user, conversation):
        raise PermissionDenied('You cannot edit this group.')

    form = GroupSettingsForm(request.POST)
    if form.is_valid():
        conversation.name = form.cleaned_data['name']
        conversation.description = form.cleaned_data['description']
        if can_manage_group(request.user, conversation):
            conversation.members_can_add_members = form.cleaned_data[
                'members_can_add_members'
            ]
            conversation.members_can_edit_group = form.cleaned_data[
                'members_can_edit_group'
            ]
        conversation.save()
        messages.success(request, 'Group details updated.')
    else:
        messages.error(request, 'Group details could not be updated.')
    return redirect(
        f"{reverse('communications:inbox')}?view=chat&conversation={conversation.pk}"
    )


@portal_view
@require_POST
def add_members_view(request, pk):
    conversation = conversation_for_user(request.user, pk)
    if conversation is None:
        raise Http404('Conversation not found.')
    if not can_add_members(request.user, conversation):
        raise PermissionDenied('You cannot add members to this group.')

    existing_ids = conversation.participants.values_list('user_id', flat=True)
    form = AddMembersForm(
        request.POST,
        portal_queryset=portal_users(exclude=request.user).exclude(
            pk__in=existing_ids,
        ),
    )
    if form.is_valid():
        count = add_members(conversation, form.cleaned_data['members'])
        if count:
            messages.success(request, f'{count} member(s) added to the group.')
        else:
            messages.info(request, 'Those staff members are already in the group.')
    else:
        messages.error(request, 'Choose at least one staff member to add.')
    return redirect(
        f"{reverse('communications:inbox')}?view=chat&conversation={conversation.pk}"
    )


@portal_view
@require_POST
def remove_member_view(request, pk):
    conversation = conversation_for_user(request.user, pk)
    if conversation is None:
        raise Http404('Conversation not found.')
    if not can_manage_group(request.user, conversation):
        raise PermissionDenied('You cannot remove members from this group.')

    participant = get_object_or_404(
        conversation.participants,
        pk=request.POST.get('participant'),
    )
    if participant.user_id == request.user.pk:
        messages.error(request, 'Use “Leave group” to remove yourself.')
        return redirect(
            f"{reverse('communications:inbox')}?view=chat&conversation={conversation.pk}"
        )
    try:
        remove_member(conversation, participant)
        messages.success(
            request,
            f'{participant.display_name} was removed from the group.',
        )
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    return redirect(
        f"{reverse('communications:inbox')}?view=chat&conversation={conversation.pk}"
    )


@portal_view
@require_POST
def leave_group_view(request, pk):
    conversation = conversation_for_user(request.user, pk)
    if conversation is None:
        raise Http404('Conversation not found.')
    try:
        leave_group(conversation, request.user)
        messages.success(request, 'You left the group.')
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    return redirect('communications:inbox')


@portal_view
@require_POST
def delete_group_view(request, pk):
    conversation = conversation_for_user(request.user, pk)
    if conversation is None:
        raise Http404('Conversation not found.')
    if not conversation.is_group:
        raise PermissionDenied('Only group conversations can be deleted.')
    if not can_manage_group(request.user, conversation):
        raise PermissionDenied('Only a group owner or admin can delete it.')
    try:
        delete_group(conversation, request.user)
    except ValidationError as exc:
        messages.error(
            request,
            exc.messages[0],
        )
        return redirect(
            f"{reverse('communications:inbox')}?view=chat&conversation={conversation.pk}"
        )
    messages.success(request, 'The group was deleted.')
    return redirect('communications:inbox')


@portal_view
@require_GET
def download_attachment(request, pk):
    attachment = get_object_or_404(
        MessageAttachment.objects.select_related('message__conversation'),
        pk=pk,
    )
    conversation = attachment.message.conversation
    if not ConversationParticipant.objects.filter(
        conversation=conversation, user=request.user,
    ).exists():
        raise Http404('Attachment not found.')

    try:
        file_handle = attachment.file.open('rb')
    except (FileNotFoundError, OSError):
        raise Http404('The attachment file is no longer available.')

    filename = attachment.original_name or Path(attachment.file.name).name
    # Images may be requested inline for the thumbnail preview. Everything
    # else is always a download, and the browser is told not to sniff it.
    inline_image = (
        request.GET.get('inline') == '1' and attachment.is_image
    )
    guessed_type = mimetypes.guess_type(filename)[0]
    content_type = (
        (guessed_type if inline_image else attachment.content_type)
        or guessed_type
        or 'application/octet-stream'
    )
    response = FileResponse(
        file_handle,
        as_attachment=not inline_image,
        filename=filename,
        content_type=content_type,
    )
    response['X-Content-Type-Options'] = 'nosniff'
    return response
