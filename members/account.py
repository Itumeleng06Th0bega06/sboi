"""Member account portal views.

All views are login-protected and every object is resolved through
``request.user``; no view accepts an owner id from the request. Profile edits
are whitelisted by :class:`members.forms.AccountProfileForm`, and membership
approval is never reachable from this module — only administrators can change
an approval status (see ``members.admin`` and ``members.services``).
"""

from django.contrib import messages
from django.contrib.auth import get_user_model, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from blackboard.models import Announcement, Event, EventRsvp, MemberProfile
from contact.forms import MemberMessageForm
from contact.models import ContactMessage
from notifications.models import Notification

from . import services
from .forms import (
    AccountProfileForm,
    ChildNameForm,
    MembershipDetailsForm,
    NotificationPreferenceForm,
)
from .models import ChurchMembership, MembershipChangeRequest
from .models_comms import (
    CommsBlock,
    CommsDirectMessage,
    CommsDirectThread,
    CommsReaction,
)
from .views_comms import (
    FEED_PAGE_SIZE,
    feed_page,
    feed_page_for,
    feed_posts_for,
    serialize_posts,
)


ACCOUNT_SECTIONS = {
    'account': ('Community', 'Community'),
    'posts': ('My posts', 'My posts'),
    'saved': ('Saved posts', 'Saved posts'),
    'profile': ('My profile', 'My profile'),
    'children': ('Children', 'Children'),
    'activities': ('My activity', 'My activity'),
    'messages': ('Inbox', 'Inbox'),
    'notifications': ('Notifications', 'Notifications'),
    'settings': ('Settings', 'Settings'),
}


def _is_ajax(request):
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


def _redirect_back(request, fallback):
    """Return to the referring page only when it belongs to this site."""
    target = request.META.get('HTTP_REFERER') or ''
    if target and url_has_allowed_host_and_scheme(
        target,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(target)
    return redirect(fallback)


def _account_base(request):
    if _is_ajax(request):
        return 'members/account/_fragment_base.html'
    return 'members/account/base_account.html'


def _render_account(request, template, context):
    """Render a normal page or only the replaceable account section."""
    context['account_base'] = _account_base(request)
    return render(request, template, context)


def _section_fragment(request, template, context):
    context['account_base'] = 'members/account/_fragment_base.html'
    return render_to_string(template, context, request=request)


def _profile(user):
    profile, _ = MemberProfile.objects.get_or_create(user=user)
    return profile


def _membership(user):
    return (
        ChurchMembership.objects
        .select_related('user')
        .filter(user=user)
        .first()
    )


def _membership_is_active(membership):
    """The registry form unlocks only after an administrator approves."""
    return membership is not None and membership.status == 'active'


MEMBERSHIP_LOCKED_MESSAGE = (
    'The membership registry form opens after the church office approves '
    'your membership request.'
)


def _membership_snapshot(membership):
    if membership is None:
        return {
            'interests': [], 'current_ministries': [],
            'volunteer_ministries': [], 'wants_to_join': [],
            'member_since': None,
        }
    return {
        'interests': list(membership.interests.all()),
        'current_ministries': list(
            membership.ministries.filter(status='current')
        ),
        'volunteer_ministries': list(
            membership.ministries.filter(status='volunteer')
        ),
        'wants_to_join': list(membership.ministries.filter(status='join')),
        'member_since': membership.date_joined_church or membership.created_at.date(),
    }


def _account_context(request, section):
    user = request.user
    membership = _membership(user)
    profile = _profile(user)
    section_label, page_title = ACCOUNT_SECTIONS.get(
        section, ('My account', 'My account'),
    )
    return {
        'account_section': section,
        'account_section_label': section_label,
        'account_page_title': page_title,
        'member_avatar_url': _avatar_url(user),
        'member_initials': _avatar_initials(user),
        'member_display_name': user.get_full_name() or user.get_username(),
        'membership': membership,
        'membership_editable': _membership_is_active(membership),
        'member_profile': profile,
        'membership_snapshot': _membership_snapshot(membership),
        'pending_change': services.pending_change_for(membership),
        'latest_decision': services.latest_decision_for(membership),
        'unread_notifications': services.unread_notification_count(request),
        'unread_messages': services.unread_message_count(user),
        'notification_preview': services.notification_preview(user),
    }


def _account_counts(request):
    return {
        'ok': True,
        'unread_messages': services.unread_message_count(request.user),
        'unread_notifications': services.unread_notification_count(request),
    }


def _form_fragment(request, template, context):
    return render_to_string(template, context, request=request)


def _avatar_url(user):
    profile = getattr(user, 'member_profile', None)
    if profile is not None and profile.avatar:
        try:
            return profile.avatar.url
        except ValueError:
            return ''
    return ''


def _avatar_initials(user):
    display_name = user.get_full_name() or user.get_username()
    parts = [part for part in display_name.split() if part]
    if not parts:
        return 'S'
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _community_aside_context():
    """Real church information only; the templates hide the aside when empty."""
    today = timezone.localdate()
    events = list(
        Event.objects
        .filter(is_published=True, date__gte=today)
        .order_by('date', 'id')[:4]
    )
    announcements = list(
        Announcement.objects
        .filter(is_published=True)
        .order_by('-date', '-id')[:3]
    )
    return {
        'aside_events': events,
        'aside_announcements': announcements,
        'has_community_aside': bool(events or announcements),
    }


def _serialise_page(queryset, user, before=None, limit=FEED_PAGE_SIZE):
    return feed_page_for(queryset, user, before=before, limit=limit)


def _feed_context(request, section, posts, has_more=False, next_before=''):
    context = _account_context(request, section)
    membership = context['membership']
    profile_form = AccountProfileForm(
        user=request.user,
        membership=membership,
        profile=context['member_profile'],
    )
    membership_form = (
        MembershipDetailsForm(instance=membership)
        if _membership_is_active(membership)
        else None
    )
    thread = list(services.member_thread(request.user))
    context.update({
        'profile_form': profile_form,
        'posts': posts,
        'post_reaction_choices': CommsReaction.REACTION_CHOICES,
        'feed_latest_id': posts[0].pk if posts else '',
        'feed_has_more': has_more,
        'feed_next_before': next_before,
        'membership_form': membership_form,
        'message_form': MemberMessageForm(),
        'recent_messages': thread[-3:],
        'thread_count': len(thread),
        'children': services.child_names(membership),
        'account_type': 'Church Member' if membership else 'Regular User',
        'feed_surface': 'community',
    })
    context.update(_community_aside_context())
    return context


# ---------------------------------------------------------------------------
# Community feed / dashboard
# ---------------------------------------------------------------------------

@login_required
def account_home(request):
    posts, has_more, next_before = feed_page(request.user)
    context = _feed_context(
        request, 'account', posts, has_more, next_before,
    )
    # Home is the post feed only; chats live on the Inbox page.
    context['timeline_items'] = None
    context['timeline_filter'] = 'posts'
    return _render_account(request, 'members/account/dashboard.html', context)


@login_required
def account_posts(request):
    queryset = feed_posts_for(request.user).filter(author=request.user)
    before = request.GET.get('before', '')
    posts, has_more, next_before = _serialise_page(
        queryset, request.user, int(before) if before.isdigit() else None,
    )
    context = _feed_context(request, 'posts', posts, has_more, next_before)
    return _render_account(request, 'members/account/posts.html', context)


@login_required
def account_saved(request):
    from .models_comms import CommsPostSave

    queryset = feed_posts_for(request.user).filter(saves__user=request.user)
    before = request.GET.get('before', '')
    posts, has_more, next_before = _serialise_page(
        queryset, request.user, int(before) if before.isdigit() else None,
    )
    context = _feed_context(request, 'saved', posts, has_more, next_before)
    context['saved_count'] = CommsPostSave.objects.filter(
        user=request.user,
    ).count()
    return _render_account(request, 'members/account/saved.html', context)


@login_required
def account_profile(request):
    context = _account_context(request, 'profile')
    membership = context['membership']
    context.update({
        'profile_form': AccountProfileForm(
            user=request.user,
            membership=membership,
            profile=context['member_profile'],
        ),
        'membership_form': (
            MembershipDetailsForm(instance=membership)
            if _membership_is_active(membership)
            else None
        ),
        'children': services.child_names(membership),
        'account_type': 'Church Member' if membership else 'Regular User',
    })
    return _render_account(request, 'members/account/profile.html', context)


@login_required
def account_member_profile(request, username):
    """Public (signed-in only) member profile; never exposes private records."""
    member = get_object_or_404(
        get_user_model().objects.filter(is_active=True),
        username=username,
    )
    membership = _membership(member)
    visible_membership = (
        membership if membership is not None and membership.status == 'active'
        else None
    )
    queryset = (
        feed_posts_for(request.user)
        .filter(author=member)
        .order_by('-created_at', '-pk')
    )
    before = request.GET.get('before', '')
    posts, has_more, next_before = _serialise_page(
        queryset, request.user, int(before) if before.isdigit() else None,
    )
    context = _account_context(request, 'account')
    context.update({
        'profile_member': member,
        'profile_avatar_url': _avatar_url(member),
        'profile_initials': _avatar_initials(member),
        'profile_display_name': (
            member.get_full_name() or member.get_username()
        ),
        'profile_membership': visible_membership,
        'posts': posts,
        'post_reaction_choices': CommsReaction.REACTION_CHOICES,
        'feed_has_more': has_more,
        'feed_next_before': next_before,
        'feed_surface': 'community',
        'is_own_profile': member.pk == request.user.pk,
        'profile_online': services.is_user_online(member),
        'profile_blocked': services.interaction_blocked(
            request.user, member,
        ),
        'profile_blocked_by_me': CommsBlock.objects.filter(
            blocker=request.user, blocked=member,
        ).exists(),
    })
    context.update(_community_aside_context())
    return _render_account(
        request, 'members/account/member_profile.html', context,
    )


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

@login_required
@require_POST
def account_profile_edit(request):
    membership = _membership(request.user)
    profile = _profile(request.user)
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
            context = _account_context(request, 'account')
            html = _form_fragment(
                request, 'members/account/_profile_card.html', context,
            )
            membership_html = _form_fragment(
                request, 'members/account/_membership_card.html', context,
            )
            form_html = _form_fragment(
                request,
                'members/account/_profile_form.html',
                {
                    'profile_form': AccountProfileForm(
                        user=request.user,
                        membership=membership,
                        profile=profile,
                    ),
                    'membership': membership,
                    'member_avatar_url': _avatar_url(request.user),
                    'member_initials': _avatar_initials(request.user),
                },
            )
            return JsonResponse({
                'ok': True,
                'message': 'Your profile has been updated.',
                'html': html,
                'membership_html': membership_html,
                'form_html': form_html,
                'display_name': (
                    request.user.get_full_name() or request.user.get_username()
                ),
                'greeting_name': (
                    request.user.first_name or request.user.get_username()
                ),
                'email': request.user.email,
            })
        messages.success(request, 'Your profile has been updated.')
        return redirect('members:account')

    if _is_ajax(request):
        html = _form_fragment(
            request,
            'members/account/_profile_form.html',
            {
                'profile_form': form,
                'membership': membership,
                'member_avatar_url': _avatar_url(request.user),
                'member_initials': _avatar_initials(request.user),
            },
        )
        return JsonResponse({'ok': False, 'html': html}, status=400)
    messages.error(request, 'Please correct the errors below and try again.')
    return redirect('members:account')


# ---------------------------------------------------------------------------
# Membership
# ---------------------------------------------------------------------------

@login_required
@require_POST
def account_membership_request(request):
    """Ask the church office for a membership record.

    A visitor only asks to join here; the full registry form stays locked
    until an administrator approves the request. An earlier declined request
    can be submitted again. The pending ``MembershipChangeRequest`` is what
    the admin review screen and the member's notification feed already use.
    """
    membership = _membership(request.user)
    message = ''
    ok = False
    status = 400

    if membership is None:
        membership = ChurchMembership.objects.create(
            user=request.user, status='pending',
        )
        message = (
            'Your church membership request has been sent to the church '
            'office. You will be notified when it is approved.'
        )
        ok = True
        status = 200
    elif membership.status == 'rejected':
        membership.status = 'pending'
        membership.save(update_fields=['status', 'updated_at'])
        message = (
            'Your new church membership request has been sent to the church '
            'office for review.'
        )
        ok = True
        status = 200
    elif membership.status == 'pending':
        message = 'Your membership request is already with the church office.'
        ok = True
        status = 200
    elif membership.status == 'active':
        message = 'You are already an active church member.'
    else:
        message = (
            'Your membership is currently inactive. Please message the church '
            'office so they can help you.'
        )

    if ok:
        services.record_membership_change(
            membership,
            request.user,
            MembershipChangeRequest.KIND_APPLICATION,
            'Church membership requested from the account menu.',
        )

    if _is_ajax(request):
        return JsonResponse({'ok': ok, 'message': message}, status=status)
    if ok:
        messages.success(request, message)
    else:
        messages.error(request, message)
    return redirect(reverse('members:account_profile') + '#membership')


@login_required
@require_POST
def account_membership_edit(request):
    membership = _membership(request.user)
    if not _membership_is_active(membership):
        if _is_ajax(request):
            return JsonResponse({
                'ok': False,
                'message': MEMBERSHIP_LOCKED_MESSAGE,
            }, status=403)
        messages.error(request, MEMBERSHIP_LOCKED_MESSAGE)
        return redirect(reverse('members:account_profile') + '#membership')

    previous_status = membership.status if membership else 'pending'
    previous_exists = membership is not None
    form = MembershipDetailsForm(request.POST, instance=membership)

    if form.is_valid():
        membership, _created = form.save(request.user)
        kind = (
            MembershipChangeRequest.KIND_APPLICATION
            if not previous_exists or previous_status in ('pending', 'rejected')
            else MembershipChangeRequest.KIND_UPDATE
        )
        services.record_membership_change(
            membership, request.user, kind, form.summary(),
        )
        if _is_ajax(request):
            context = _account_context(request, 'account')
            card_html = _form_fragment(
                request, 'members/account/_membership_card.html', context,
            )
            form_html = _form_fragment(
                request,
                'members/account/_membership_form.html',
                {'membership_form': MembershipDetailsForm(instance=membership)},
            )
            return JsonResponse({
                'ok': True,
                'message': (
                    'Your membership details were submitted for review. '
                    'Your current status is unchanged until an administrator '
                    'reviews the update.'
                ),
                'html': card_html,
                'form_html': form_html,
            })
        messages.success(
            request,
            'Your membership details were submitted for review.',
        )
        return redirect(reverse('members:account_profile') + '#membership')

    if _is_ajax(request):
        html = _form_fragment(
            request,
            'members/account/_membership_form.html',
            {'membership_form': form},
        )
        return JsonResponse({'ok': False, 'html': html}, status=400)
    messages.error(request, 'Please correct the errors below and try again.')
    return redirect(reverse('members:account_profile') + '#membership')


# ---------------------------------------------------------------------------
# Children
# ---------------------------------------------------------------------------

def _children_context(request, child_form=None):
    context = _account_context(request, 'children')
    membership = context['membership']
    context.update({
        'children': services.child_names(membership),
        'child_form': child_form or ChildNameForm(),
        'membership_form': (
            MembershipDetailsForm(instance=membership)
            if _membership_is_active(membership)
            else None
        ),
    })
    return context


def _children_ajax(request, message, ok=True, status=200, child_form=None):
    context = _children_context(request, child_form=child_form)
    return JsonResponse({
        'ok': ok,
        'message': message,
        'html': _section_fragment(
            request, 'members/account/_children_card.html', context,
        ),
    }, status=status)


@login_required
def account_children(request):
    return _render_account(
        request, 'members/account/children.html', _children_context(request),
    )


def _require_membership(user):
    membership = _membership(user)
    if not _membership_is_active(membership):
        raise Http404(MEMBERSHIP_LOCKED_MESSAGE)
    return membership


@login_required
@require_POST
def account_child_add(request):
    membership = _require_membership(request.user)
    form = ChildNameForm(request.POST)
    if form.is_valid():
        names = services.child_names(membership)
        candidate = form.cleaned_data['name']
        if candidate.casefold() in {name.casefold() for name in names}:
            message = 'That child is already on your list.'
            if _is_ajax(request):
                return _children_ajax(
                    request, message, ok=False, status=400, child_form=form,
                )
            messages.error(request, message)
        else:
            names.append(candidate)
            services.save_child_names(membership, names)
            message = 'Child added.'
            if _is_ajax(request):
                return _children_ajax(request, message)
            messages.success(request, message)
    else:
        message = 'Enter the child’s name.'
        if _is_ajax(request):
            return _children_ajax(
                request, message, ok=False, status=400, child_form=form,
            )
        messages.error(request, message)
    return redirect('members:account_children')


@login_required
@require_POST
def account_child_edit(request, index):
    membership = _require_membership(request.user)
    names = services.child_names(membership)
    if index < 0 or index >= len(names):
        raise Http404('Child not found.')
    form = ChildNameForm(request.POST)
    if form.is_valid():
        candidate = form.cleaned_data['name']
        if candidate.casefold() in {
            name.casefold() for i, name in enumerate(names) if i != index
        }:
            message = 'That child is already on your list.'
            if _is_ajax(request):
                return _children_ajax(request, message, ok=False, status=400)
            messages.error(request, message)
        else:
            names[index] = candidate
            services.save_child_names(membership, names)
            message = 'Child updated.'
            if _is_ajax(request):
                return _children_ajax(request, message)
            messages.success(request, message)
    else:
        message = 'Enter the child’s name.'
        if _is_ajax(request):
            return _children_ajax(request, message, ok=False, status=400)
        messages.error(request, message)
    return redirect('members:account_children')


@login_required
@require_POST
def account_child_remove(request, index):
    membership = _require_membership(request.user)
    names = services.child_names(membership)
    if index < 0 or index >= len(names):
        raise Http404('Child not found.')
    removed = names.pop(index)
    services.save_child_names(membership, names)
    message = f'{removed} was removed from your children list.'
    if _is_ajax(request):
        return _children_ajax(request, message)
    messages.success(request, message)
    return redirect('members:account_children')


# ---------------------------------------------------------------------------
# Activities
# ---------------------------------------------------------------------------

@login_required
def account_activities(request):
    context = _account_context(request, 'activities')
    membership = context['membership']
    snapshot = context['membership_snapshot']
    email = (request.user.email or '').strip()
    rsvps = []
    if email:
        rsvps = (
            EventRsvp.objects
            .filter(email__iexact=email)
            .select_related('event')
            .order_by('-event__date', '-created_at')[:20]
        )
    context.update({
        'rsvps': rsvps,
        'confirmed': snapshot['current_ministries'] + snapshot['volunteer_ministries'],
        'requests': snapshot['wants_to_join'],
        'interests': snapshot['interests'],
    })
    return _render_account(request, 'members/account/activities.html', context)


# ---------------------------------------------------------------------------
# Private messages (one unified member ↔ administration inbox)
# ---------------------------------------------------------------------------

def _purge_chat_retention():
    from .retention import purge_expired_chats_once_per_hour

    purge_expired_chats_once_per_hour()


@login_required
def account_messages(request):
    _purge_chat_retention()
    services.mark_member_messages_read(request.user)

    active_thread = None
    active_other = None
    direct_messages = []
    thread_id = (request.GET.get('thread') or '').strip()
    if thread_id.isdigit():
        active_thread = get_object_or_404(
            services.direct_threads_for(request.user),
            pk=int(thread_id),
        )
        active_other = active_thread.other_user(request.user)
        if (
            active_other is None
            or services.interaction_blocked(request.user, active_other)
        ):
            raise Http404('Conversation not found.')
        active_thread.mark_read(request.user)
        direct_messages = list(
            active_thread.messages
            .select_related('sender')
            .order_by('created_at', 'pk')[:300]
        )

    # Build the list after the selected thread has been marked read so its
    # unread badge and the header count drop on the page load that opened it.
    thread_rows = _direct_thread_rows(request.user)
    thread_by_member = {
        row['other'].pk: row['thread'] for row in thread_rows
    }
    online_rows = _online_rows(request.user, thread_by_member)

    context = _account_context(request, 'messages')
    context.update({
        'thread': list(services.member_thread(request.user)),
        'message_form': MemberMessageForm(),
        'unread_messages': services.unread_message_count(request.user),
        'direct_threads': thread_rows,
        'inbox_unread_count': sum(1 for row in thread_rows if row['unread']),
        'online_rows': online_rows,
        'blocked_members': services.blocked_members(request.user),
        'dm_thread': active_thread,
        'dm_other': active_other,
        'dm_other_online': (
            services.is_user_online(active_other)
            if active_other is not None else False
        ),
        'dm_messages': direct_messages,
        'dm_avatar_url': _avatar_url(active_other) if active_other else '',
        'dm_initials': _avatar_initials(active_other) if active_other else 'S',
    })
    return _render_account(request, 'members/account/messages.html', context)


def _direct_thread_rows(user):
    """Recent member-to-member conversations, newest first."""
    rows = []
    for thread in services.direct_threads_for(user)[:40]:
        other = thread.other_user(user)
        if other is None:
            continue
        last = (
            thread.messages
            .select_related('sender')
            .order_by('-created_at', '-pk')
            .first()
        )
        rows.append({
            'thread': thread,
            'other': other,
            'display_name': other.get_full_name() or other.get_username(),
            'avatar_url': _avatar_url(other),
            'initials': _avatar_initials(other),
            'online': services.is_user_online(other),
            'last_body': last.body if last else '',
            'last_at': last.created_at if last else None,
            'unread': thread.unread_count(user),
        })
    return rows


def _online_rows(user, thread_by_member):
    """People who are online now, with a shortcut to any existing thread."""
    rows = []
    for person in services.online_members(user, limit=12):
        thread = thread_by_member.get(person.pk)
        rows.append({
            'member': person,
            'display_name': person.get_full_name() or person.get_username(),
            'avatar_url': _avatar_url(person),
            'initials': _avatar_initials(person),
            'thread': thread,
        })
    return rows


@login_required
@require_POST
def account_direct_start(request):
    """Open (or create) a private conversation with another member."""
    username = (request.POST.get('username') or '').strip()
    member = get_object_or_404(
        get_user_model().objects.filter(is_active=True),
        username=username,
    )
    if member.pk == request.user.pk:
        return redirect('members:account_messages')
    if services.interaction_blocked(request.user, member):
        messages.error(
            request,
            'You cannot start a conversation with this member.',
        )
        return redirect('members:account_messages')

    thread = CommsDirectThread.for_users(request.user, member)
    return redirect(
        reverse('members:account_messages') + f'?thread={thread.pk}'
    )


@login_required
@require_POST
def account_direct_send(request, pk):
    """Send one private message inside a member-to-member thread."""
    thread = get_object_or_404(
        CommsDirectThread.objects.select_related('user_a', 'user_b'),
        pk=pk,
    )
    other = thread.other_user(request.user)
    if other is None:
        raise Http404('Conversation not found.')
    if services.interaction_blocked(request.user, other):
        if _is_ajax(request):
            return JsonResponse({
                'ok': False,
                'message': 'This conversation is no longer available.',
            }, status=403)
        messages.error(request, 'This conversation is no longer available.')
        return redirect('members:account_messages')

    body = (request.POST.get('body') or '').replace('\x00', '').strip()[:2000]
    if not body:
        if _is_ajax(request):
            return JsonResponse({
                'ok': False,
                'message': 'Write a message before sending.',
            }, status=400)
        messages.error(request, 'Write a message before sending.')
        return redirect(
            reverse('members:account_messages') + f'?thread={thread.pk}'
        )

    message = CommsDirectMessage.objects.create(
        thread=thread,
        sender=request.user,
        body=body,
    )
    thread.last_message_at = message.created_at
    thread.save(update_fields=['last_message_at', 'updated_at'])
    thread.mark_read(request.user)
    services.notify_direct_message(message)

    if _is_ajax(request):
        return JsonResponse({
            'ok': True,
            'id': message.pk,
            'message': 'Message sent.',
            'html': _form_fragment(
                request,
                'members/account/_direct_message_bubble.html',
                {'message': message, 'is_own': True},
            ),
        })
    return redirect(
        reverse('members:account_messages') + f'?thread={thread.pk}'
    )


@login_required
def account_direct_poll(request, pk):
    """Poll one direct thread for new messages without a page reload."""
    thread = get_object_or_404(
        services.direct_threads_for(request.user),
        pk=pk,
    )
    other = thread.other_user(request.user)
    if other is None or services.interaction_blocked(request.user, other):
        raise Http404('Conversation not found.')

    after = (request.GET.get('after') or '').strip()
    messages_qs = (
        thread.messages
        .select_related('sender')
        .order_by('created_at', 'pk')
    )
    if after.isdigit():
        messages_qs = messages_qs.filter(pk__gt=int(after))
    if request.GET.get('read') == '1':
        thread.mark_read(request.user)

    payload = [
        {
            'id': message.pk,
            'html': _form_fragment(
                request,
                'members/account/_direct_message_bubble.html',
                {
                    'message': message,
                    'is_own': message.sender_id == request.user.pk,
                },
            ),
        }
        for message in messages_qs
    ]
    return JsonResponse({
        'ok': True,
        'messages': payload,
        'unread': services.unread_message_count(request.user),
    })


@login_required
@require_POST
def account_block_member(request, username):
    """Hide a member's posts and block messages in both directions."""
    member = get_object_or_404(
        get_user_model().objects.filter(is_active=True),
        username=username,
    )
    if member.pk == request.user.pk:
        raise Http404('You cannot block yourself.')
    CommsBlock.objects.get_or_create(blocker=request.user, blocked=member)
    if _is_ajax(request):
        return JsonResponse({'ok': True, 'blocked': True})
    messages.success(
        request,
        'You will no longer see this member\'s posts or messages.',
    )
    return _redirect_back(request, reverse('members:account'))


@login_required
@require_POST
def account_unblock_member(request, username):
    member = get_object_or_404(
        get_user_model().objects.filter(is_active=True),
        username=username,
    )
    CommsBlock.objects.filter(
        blocker=request.user, blocked=member,
    ).delete()
    if _is_ajax(request):
        return JsonResponse({'ok': True, 'blocked': False})
    messages.success(request, 'This member has been unblocked.')
    return _redirect_back(request, reverse('members:account_messages'))



def _duplicate_message(user, body):
    return services.duplicate_message_exists(user, body)


@login_required
@require_POST
def account_message_send(request):
    form = MemberMessageForm(request.POST, request.FILES)
    if not form.is_valid():
        if _is_ajax(request):
            return JsonResponse({
                'ok': False,
                'errors': form.errors.get_json_data(),
            }, status=400)
        messages.error(request, 'Please check your message and try again.')
        return redirect('members:account_messages')

    body = form.cleaned_data['message']
    if _duplicate_message(request.user, body):
        if _is_ajax(request):
            return JsonResponse({
                'ok': False,
                'message': 'You just sent that message. Please wait a moment.',
            }, status=400)
        messages.error(request, 'You just sent that message.')
        return redirect('members:account_messages')

    membership = _membership(request.user)
    member_message = ContactMessage.objects.create(
        user=request.user,
        sender=request.user,
        name=request.user.get_full_name() or request.user.get_username(),
        email=request.user.email or '',
        phone=(membership.phone if membership else '') or '',
        message=body,
        attachment=form.cleaned_data.get('attachment') or None,
        is_read=False,
        read_by_member=True,
    )
    services.clear_admin_notification_cache()

    if _is_ajax(request):
        html = _form_fragment(
            request,
            'members/account/_message_bubble.html',
            {'message': member_message, 'is_own': True},
        )
        return JsonResponse({
            'ok': True,
            'message': (
                'Your message has been sent privately to the church '
                'administration.'
            ),
            'html': html,
            'id': member_message.pk,
        })

    messages.success(
        request,
        'Your message has been sent privately to the church administration.',
    )
    return redirect(reverse('members:account_messages') + f'#message-{member_message.pk}')


@login_required
def account_message_poll(request):
    _purge_chat_retention()
    after = (request.GET.get('after') or '').strip()
    queryset = services.member_thread(request.user)
    if after.isdigit():
        queryset = queryset.filter(pk__gt=int(after))
    if request.GET.get('read') == '1':
        services.mark_member_messages_read(request.user)
    payload = [
        {
            'id': message.pk,
            'html': _form_fragment(
                request,
                'members/account/_message_bubble.html',
                {
                    'message': message,
                    'is_own': message.sender_id == request.user.pk
                    and not message.is_from_admin,
                },
            ),
        }
        for message in queryset
    ]
    return JsonResponse({
        'ok': True,
        'messages': payload,
        'unread': services.unread_message_count(request.user),
    })


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

@login_required
def account_notifications(request):
    context = _account_context(request, 'notifications')
    history = services.notification_history(request.user)
    context.update({
        'notifications': services.serialized_notifications(
            list(history[:100]), request,
        ),
        'unread_notifications': services.unread_notification_count(request),
    })
    return _render_account(request, 'members/account/notifications.html', context)


@login_required
@require_POST
def account_notification_read(request):
    services.mark_all_notifications_read(request)
    if _is_ajax(request):
        context = _account_context(request, 'notifications')
        context['notifications'] = services.serialized_notifications(
            list(services.notification_history(request.user)[:100]), request,
        )
        context['unread_notifications'] = 0
        return JsonResponse({
            **_account_counts(request),
            'message': 'All notifications are marked as read.',
            'html': _section_fragment(
                request, 'members/account/notifications.html', context,
            ),
        })
    return redirect('members:account_notifications')


@login_required
def account_notification_open(request, pk):
    notification = get_object_or_404(Notification, pk=pk)
    from notifications import services as notification_services

    if not notification_services.notification_is_visible(notification, request):
        raise Http404('Notification not found.')
    services.mark_notification_read(notification, request)
    target = (notification.url or '').strip()
    # Only follow paths produced by reverse(); never an off-site redirect.
    if not target.startswith('/') or target.startswith('//'):
        target = reverse('members:account_notifications')
    if _is_ajax(request):
        return JsonResponse({
            **_account_counts(request),
            'ok': True,
            'url': target,
        })
    return redirect(target)


@login_required
def account_counts(request):
    """Small JSON endpoint used to keep account badges in sync without reloading."""
    return JsonResponse(_account_counts(request))


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@login_required
def account_settings(request):
    profile = _profile(request.user)
    password_form = PasswordChangeForm(request.user)
    preference_form = NotificationPreferenceForm(profile=profile)
    message = ''
    ok = True
    status = 200

    if request.method == 'POST':
        if 'change_password' in request.POST:
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                update_session_auth_hash(request, password_form.save())
                password_form = PasswordChangeForm(request.user)
                message = 'Your password has been changed.'
            else:
                ok = False
                status = 400
                message = 'Please correct the password errors below.'
        elif 'save_preferences' in request.POST:
            preference_form = NotificationPreferenceForm(
                request.POST, profile=profile,
            )
            if preference_form.is_valid():
                preference_form.save()
                preference_form = NotificationPreferenceForm(profile=profile)
                message = 'Your preferences have been saved.'
            else:
                ok = False
                status = 400
                message = 'Could not save your preferences.'

        if _is_ajax(request):
            context = _account_context(request, 'settings')
            context.update({
                'password_form': password_form,
                'preference_form': preference_form,
                'blocked_members': services.blocked_members(request.user),
            })
            return JsonResponse({
                'ok': ok,
                'message': message,
                'html': _section_fragment(
                    request, 'members/account/settings.html', context,
                ),
            }, status=status)
        if ok:
            messages.success(request, message)
        else:
            messages.error(request, message)
        return redirect('members:account_settings')

    context = _account_context(request, 'settings')
    context.update({
        'password_form': password_form,
        'preference_form': preference_form,
        'blocked_members': services.blocked_members(request.user),
    })
    return _render_account(request, 'members/account/settings.html', context)


@login_required
@require_POST
def account_delete(request):
    """Permanently delete the signed-in user and everything linked to them.

    Requires an explicit confirmation checkbox. The account is signed out
    first so the session cannot keep pointing at a deleted user.
    """
    if request.POST.get('confirm_delete') != 'yes':
        messages.error(
            request,
            'Tick the confirmation box before deleting your account.',
        )
        return redirect('members:account_settings')

    user = request.user
    logout(request)
    user.delete()
    messages.success(
        request,
        'Your account and all linked church records have been deleted.',
    )
    return redirect('home:home')
