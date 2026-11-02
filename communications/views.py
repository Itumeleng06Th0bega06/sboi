"""Views for the private admin communications portal."""

import mimetypes
from functools import wraps
from pathlib import Path

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

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
    get_or_create_direct,
    leave_group,
    mark_conversation_read,
    message_queryset,
    name_initials,
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


def _inbox_context(request, group_form=None, direct_form=None, open_dialog=''):
    user = request.user
    query = (request.GET.get('q') or '').strip()
    message_query = (request.GET.get('mq') or '').strip()

    selected = None
    selected_id = request.GET.get('conversation')
    if selected_id:
        try:
            selected_id = int(selected_id)
        except (TypeError, ValueError):
            selected_id = None
    if selected_id:
        selected = conversation_for_user(user, selected_id)

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

    # Build the list after the selected thread has been marked read so its
    # unread badge does not survive the page load that opened it.
    rows = conversation_summaries(user, query)
    users = portal_users(exclude=user)
    context = admin.site.each_context(request)
    context.update({
        'title': 'Admin Communications',
        'section_label': 'communications',
        'conversation_rows': rows,
        'conversation_query': query,
        'selected_id': selected.pk if selected else None,
        'group_form': group_form or GroupForm(portal_queryset=users),
        'direct_form': direct_form or StartDirectForm(portal_queryset=users),
        'portal_users': users,
        'open_dialog': open_dialog,
        'total_unread': unread_total(user),
        'inbox_url': reverse('communications:inbox'),
        **selected_context,
    })
    return context


@portal_view
@require_GET
def inbox(request):
    return render(
        request,
        'admin/communications/portal.html',
        _inbox_context(request),
    )


@portal_view
@require_GET
def conversation_workspace(request, pk):
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
            f"{reverse('communications:inbox')}?conversation={conversation.pk}"
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
        f"{reverse('communications:inbox')}?conversation={conversation.pk}"
    )


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
            f"{reverse('communications:inbox')}?conversation={conversation.pk}"
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
            f"{reverse('communications:inbox')}?conversation={conversation.pk}"
        )

    context = _inbox_context(
        request,
        direct_form=form,
        open_dialog='direct',
    )
    return render(request, 'admin/communications/portal.html', context, status=400)


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
        f"{reverse('communications:inbox')}?conversation={conversation.pk}"
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
        f"{reverse('communications:inbox')}?conversation={conversation.pk}"
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
            f"{reverse('communications:inbox')}?conversation={conversation.pk}"
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
        f"{reverse('communications:inbox')}?conversation={conversation.pk}"
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
