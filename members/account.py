"""Member account portal views.

All views are login-protected and every object is resolved through
``request.user``; no view accepts an owner id from the request. Profile edits
are whitelisted by :class:`members.forms.AccountProfileForm`, and membership
approval is never reachable from this module — only administrators can change
an approval status (see ``members.admin`` and ``members.services``).
"""

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.http import require_POST

from blackboard.models import EventRsvp, MemberProfile
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


def _is_ajax(request):
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


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
    return {
        'account_section': section,
        'membership': membership,
        'member_profile': profile,
        'membership_snapshot': _membership_snapshot(membership),
        'pending_change': services.pending_change_for(membership),
        'latest_decision': services.latest_decision_for(membership),
        'unread_notifications': services.unread_notification_count(request),
        'unread_messages': services.unread_message_count(user),
        'notification_preview': services.notification_preview(user),
    }


def _form_fragment(request, template, context):
    return render_to_string(template, context, request=request)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@login_required
def account_home(request):
    context = _account_context(request, 'account')
    membership = context['membership']
    profile_form = AccountProfileForm(
        user=request.user,
        membership=membership,
        profile=context['member_profile'],
    )
    membership_form = MembershipDetailsForm(instance=membership)
    thread = list(services.member_thread(request.user))
    context.update({
        'profile_form': profile_form,
        'membership_form': membership_form,
        'message_form': MemberMessageForm(),
        'recent_messages': thread[-3:],
        'thread_count': len(thread),
        'children': services.child_names(membership),
        'account_type': 'Church Member' if membership else 'Regular User',
    })
    return render(request, 'members/account/dashboard.html', context)


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
            html = _form_fragment(
                request,
                'members/account/_profile_card.html',
                {
                    'request': request,
                    'membership': membership,
                    'member_profile': profile,
                    'account_type': 'Church Member' if membership else 'Regular User',
                },
            )
            return JsonResponse({
                'ok': True,
                'message': 'Your profile has been updated.',
                'html': html,
            })
        messages.success(request, 'Your profile has been updated.')
        return redirect('members:account')

    if _is_ajax(request):
        html = _form_fragment(
            request,
            'members/account/_profile_form.html',
            {'profile_form': form, 'membership': membership},
        )
        return JsonResponse({'ok': False, 'html': html}, status=400)
    messages.error(request, 'Please correct the errors below and try again.')
    return redirect('members:account')


# ---------------------------------------------------------------------------
# Membership
# ---------------------------------------------------------------------------

@login_required
@require_POST
def account_membership_edit(request):
    membership = _membership(request.user)
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
            card_html = _form_fragment(
                request,
                'members/account/_membership_card.html',
                {
                    'request': request,
                    'membership': membership,
                    'membership_snapshot': _membership_snapshot(membership),
                    'pending_change': services.pending_change_for(membership),
                    'latest_decision': services.latest_decision_for(membership),
                },
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
        return redirect(reverse('members:account') + '#membership')

    if _is_ajax(request):
        html = _form_fragment(
            request,
            'members/account/_membership_form.html',
            {'membership_form': form},
        )
        return JsonResponse({'ok': False, 'html': html}, status=400)
    messages.error(request, 'Please correct the errors below and try again.')
    return redirect(reverse('members:account') + '#membership')


# ---------------------------------------------------------------------------
# Children
# ---------------------------------------------------------------------------

@login_required
def account_children(request):
    context = _account_context(request, 'children')
    membership = context['membership']
    context.update({
        'children': services.child_names(membership),
        'child_form': ChildNameForm(),
        'membership_form': MembershipDetailsForm(instance=membership),
    })
    return render(request, 'members/account/children.html', context)


def _require_membership(user):
    membership = _membership(user)
    if membership is None:
        raise Http404('Complete your membership details first.')
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
            messages.error(request, 'That child is already on your list.')
        else:
            names.append(candidate)
            services.save_child_names(membership, names)
            messages.success(request, 'Child added.')
    else:
        messages.error(request, 'Enter the child’s name.')
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
            messages.error(request, 'That child is already on your list.')
        else:
            names[index] = candidate
            services.save_child_names(membership, names)
            messages.success(request, 'Child updated.')
    else:
        messages.error(request, 'Enter the child’s name.')
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
    messages.success(request, f'{removed} was removed from your children list.')
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
    return render(request, 'members/account/activities.html', context)


# ---------------------------------------------------------------------------
# Private messages (one unified member ↔ administration inbox)
# ---------------------------------------------------------------------------

@login_required
def account_messages(request):
    services.mark_member_messages_read(request.user)
    context = _account_context(request, 'messages')
    context.update({
        'thread': services.member_thread(request.user),
        'message_form': MemberMessageForm(),
        'unread_messages': 0,
    })
    return render(request, 'members/account/messages.html', context)


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
    return render(request, 'members/account/notifications.html', context)


@login_required
@require_POST
def account_notification_read(request):
    services.mark_all_notifications_read(request)
    if _is_ajax(request):
        return JsonResponse({
            'ok': True,
            'unread': services.unread_notification_count(request),
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
    return redirect(target)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@login_required
def account_settings(request):
    profile = _profile(request.user)
    password_form = PasswordChangeForm(request.user)
    preference_form = NotificationPreferenceForm(profile=profile)

    if request.method == 'POST':
        if 'change_password' in request.POST:
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                update_session_auth_hash(request, password_form.save())
                messages.success(request, 'Your password has been changed.')
                return redirect('members:account_settings')
            messages.error(request, 'Please correct the password errors below.')
        elif 'save_preferences' in request.POST:
            preference_form = NotificationPreferenceForm(
                request.POST, profile=profile,
            )
            if preference_form.is_valid():
                preference_form.save()
                messages.success(request, 'Your preferences have been saved.')
                return redirect('members:account_settings')
            messages.error(request, 'Could not save your preferences.')

    context = _account_context(request, 'settings')
    context.update({
        'password_form': password_form,
        'preference_form': preference_form,
    })
    return render(request, 'members/account/settings.html', context)
