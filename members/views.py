from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse

from blackboard.models import MemberProfile

from .forms import (
    ChurchMembershipFieldsMixin,
    ChurchMembershipJoinForm,
    ChurchMembershipRegistrationForm,
    MemberLoginForm,
    MemberRegistrationForm,
)


class MemberLoginView(LoginView):
    """Send first-time sign-ins to the profile; later sign-ins go home."""

    template_name = 'members/login.html'
    redirect_authenticated_user = True
    authentication_form = MemberLoginForm

    def form_valid(self, form):
        first_login = form.get_user().last_login is None
        response = super().form_valid(form)
        # Public sign-in deliberately ignores ?next=: a brand-new account
        # lands on its profile, every later sign-in returns to the home page.
        target = 'members:account_profile' if first_login else 'home:home'
        response['Location'] = reverse(target)
        return response


def register(request):
    """Step 1: choose a normal User account or a Church Member registration."""
    if request.user.is_authenticated:
        return redirect('members:join_church')
    return render(request, 'members/register.html')


def register_user(request):
    """Option 1: the existing customer/visitor account registration."""
    if request.user.is_authenticated:
        return redirect('members:join_church')
    if request.method == 'POST':
        form = MemberRegistrationForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user = form.save()
                MemberProfile.objects.get_or_create(user=user)
            login(request, user)
            messages.success(
                request,
                'Your account has been created. Welcome to the Shekinah Blaze family!',
            )
            return redirect('members:account_profile')
    else:
        form = MemberRegistrationForm()
    return render(request, 'members/register_user.html', {'form': form})


def register_church(request):
    """Option 2: create an account and a linked church membership record."""
    if request.user.is_authenticated:
        return redirect('members:join_church')
    if request.method == 'POST':
        form = ChurchMembershipRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            MemberProfile.objects.get_or_create(user=user)
            login(request, user)
            messages.success(
                request,
                'Thank you! Your church membership registration was received.',
            )
            return redirect('members:account_profile')
    else:
        form = ChurchMembershipRegistrationForm()
    return render(
        request,
        'members/register_church.html',
        {'form': form, 'is_joining': False},
    )


@login_required
def join_church(request):
    """Let an existing account attach church membership details later."""
    membership = getattr(request.user, 'church_membership', None)

    if request.method == 'POST':
        form = ChurchMembershipJoinForm(request.POST, instance=membership)
        if form.is_valid():
            form.save(request.user)
            messages.success(
                request,
                'Your church membership details have been saved. Thank you!',
            )
            return redirect('members:join_church')
    else:
        form = ChurchMembershipJoinForm(instance=membership)
        if membership is not None:
            form.initial.update({
                'interests': list(membership.interests.values_list('name', flat=True)),
                'current_ministries': list(membership.ministries.filter(status='current').values_list('name', flat=True)),
                'volunteer_ministries': list(membership.ministries.filter(status='volunteer').values_list('name', flat=True)),
                'wants_to_join': list(membership.ministries.filter(status='join').values_list('name', flat=True)),
            })
            note = getattr(membership, 'pastoral_note', None)
            if note is not None:
                form.initial.update({
                    'guidance_support': note.guidance_support,
                    'prayer_request': note.prayer_request,
                    'pastoral_support_requested': note.pastoral_support_requested,
                })

    return render(
        request,
        'members/join_church.html',
        {'form': form, 'is_joining': True, 'membership': membership},
    )


@login_required
def members_home(request):
    return redirect('blackboard:blackboard')
