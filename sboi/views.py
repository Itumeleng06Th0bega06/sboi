from django.apps import apps
from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse


def csrf_failure(request, reason=""):
    messages.error(request, 'Your session expired. Please try again.')
    referer = request.META.get('HTTP_REFERER', '')
    if referer and referer.startswith(('http://', 'https://')):
        return redirect(referer)
    return redirect('home:home')


# (app_label, model name, display label, searchable fields)
ADMIN_SEARCH_MODELS = [
    ('blackboard', 'Devotion', 'Devotions', ['title', 'scripture', 'author', 'message']),
    ('blackboard', 'Sermon', 'Sermons', ['title', 'speaker', 'scripture', 'series', 'description']),
    ('blackboard', 'Event', 'Events', ['title', 'description']),
    ('blackboard', 'Announcement', 'Announcements', ['title', 'body']),
    ('blackboard', 'PdfMaterial', 'PDF Materials', ['title']),
    ('blackboard', 'EventRsvp', 'Event RSVPs', ['name', 'email', 'phone']),
    ('blackboard', 'MemberProfile', 'Members', ['user__username', 'user__email', 'user__first_name', 'user__last_name']),
    ('auth', 'User', 'Users', ['username', 'email', 'first_name', 'last_name']),
    ('home', 'FeaturedSection', 'Featured Sections', ['title', 'subtitle', 'body']),
    ('home', 'HomeStat', 'Home Stats', ['value', 'label']),
    ('home', 'Testimony', 'Testimonies', ['name', 'message']),
    ('home', 'Subscriber', 'Subscribers', ['email']),
    ('about', 'ChurchProfile', 'Church Profile', ['church_name', 'tagline', 'location']),
    ('about', 'Leader', 'Leaders', ['name', 'role', 'bio']),
    ('about', 'CoreValue', 'Core Values', ['title', 'scripture']),
    ('about', 'VisionPillar', 'Vision Pillars', ['title', 'subtitle', 'body']),
    ('about', 'MissionComponent', 'Mission Components', ['title', 'subtitle', 'body']),
    ('about', 'PathwayStep', 'Pathway Steps', ['step', 'title']),
    ('about', 'MissionAction', 'Mission in Action', ['title']),
    ('contact', 'ContactInfo', 'Contact Info', ['church_name', 'email', 'phone', 'address']),
    ('contact', 'ContactMessage', 'Contact Messages', ['name', 'subject', 'email', 'phone', 'message']),
    ('gallery', 'SliderImage', 'Slider Images', ['title', 'caption']),
]


def admin_search(request):
    """One search box that searches across every model in the admin."""
    q = (request.GET.get('q') or '').strip()
    results = []
    total = 0
    if q:
        for app_label, model_name, label, fields in ADMIN_SEARCH_MODELS:
            model = apps.get_model(app_label, model_name)
            if model is None:
                continue
            query = Q()
            for field in fields:
                query |= Q(**{f'{field}__icontains': q})
            items = []
            for obj in model.objects.filter(query).order_by('-pk')[:15]:
                items.append({
                    'name': str(obj),
                    'url': reverse(
                        f'admin:{app_label}_{model._meta.model_name}_change',
                        args=[obj.pk],
                    ),
                })
            if items:
                results.append({'label': label, 'items': items})
                total += len(items)
    return render(request, 'admin/search.html', {
        'q': q,
        'results': results,
        'total': total,
    })


def admin_notifications_api(request):
    """JSON feed for the admin nav notification bell."""
    from home.context_processors import build_admin_notifications

    items = build_admin_notifications()
    return JsonResponse({
        'badge': sum(i['count'] for i in items if i['tone'] in ('attention', 'warning')),
        'total': sum(i['count'] for i in items),
        'items': items,
    })


def handler404(request, exception):
    return render(request, '404.html', status=404)


def handler500(request):
    return render(request, '500.html', status=500)


def handler403(request, exception):
    return render(request, '403.html', status=403)


def handler400(request, exception):
    return render(request, '400.html', status=400)
