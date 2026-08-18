from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse

from blackboard.models import Announcement, Devotion, Event, Sermon
from gallery.models import SliderImage

from .forms import SubscriberForm, TestimonyForm
from .models import FeaturedSection, HomeStat, Subscriber, Testimony


def home(request):
    sections = list(FeaturedSection.objects.all())
    context = {
        'slides': SliderImage.objects.filter(is_active=True, placement__in=['home', 'both']),
        'stats': HomeStat.objects.all(),
        'sections_top': [s for s in sections if s.order <= 2],
        'sections_bottom': [s for s in sections if s.order > 2],
        'devotions': Devotion.objects.filter(is_published=True)[:6],
        'sermons': Sermon.objects.filter(is_published=True).exclude(video_url='').order_by('-date', '-id')[:2],
        'events': Event.objects.filter(is_published=True)[:3],
        'announcements': Announcement.objects.filter(is_published=True)[:5],
        'testimonies': Testimony.objects.filter(is_approved=True)[:6],
        'subscribe_form': SubscriberForm(),
        'testimony_form': TestimonyForm(),
        'share_url': reverse('home:home'),
    }
    return render(request, 'home.html', context)


def subscribe(request):
    if request.method == 'POST':
        form = SubscriberForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            Subscriber.objects.get_or_create(email=email, defaults={'is_active': True})
            messages.success(request, 'Thank you for subscribing to our newsletter.')
        else:
            messages.error(request, 'Please enter a valid email address.')
    return redirect('home:home')


def submit_testimony(request):
    if request.method == 'POST':
        form = TestimonyForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Thank you for sharing your testimony. It will appear after review.')
        else:
            messages.error(request, 'Please provide your name and a message.')
    return redirect('home:home')
