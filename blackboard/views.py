from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse

from .forms import EventRsvpForm
from .models import Announcement, Event, PdfMaterial, Sermon


@login_required
def _member_access_denied(request):
    profile = getattr(request.user, 'member_profile', None)
    if profile is None:
        return None
    return profile.access_block()


@login_required
def blackboard(request):
    denied = _member_access_denied(request)
    if denied:
        logout(request)
        messages.error(request, denied)
        return redirect('home:home')
    context = {
        'announcements': Announcement.objects.filter(is_published=True),
        'events': Event.objects.filter(is_published=True),
        'sermons': Sermon.objects.filter(is_published=True),
        'materials': PdfMaterial.objects.filter(is_published=True),
        'rsvp_form': EventRsvpForm(),
        'share_url': reverse('blackboard:blackboard'),
    }
    return render(request, 'blackboard.html', context)


@login_required
def event_rsvp(request):
    denied = _member_access_denied(request)
    if denied:
        logout(request)
        messages.error(request, denied)
        return redirect('home:home')
    if request.method == 'POST':
        form = EventRsvpForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Thank you — your RSVP has been received. See you there!')
        else:
            messages.error(request, 'Please provide at least your name for the RSVP.')
    return redirect('blackboard:blackboard')