from django.apps import apps
from django.contrib import admin
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.template.response import TemplateResponse
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
    ('members', 'ChurchMembership', 'Church Members', ['membership_id', 'user__username', 'user__first_name', 'user__last_name', 'user__email', 'phone']),
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
            model_admin = admin.site._registry.get(model)
            if model_admin is None or not model_admin.has_view_permission(request):
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
    context = admin.site.each_context(request)
    context.update({
        'title': 'Search',
        'q': q,
        'results': results,
        'total': total,
    })
    return render(request, 'admin/search.html', context)


def admin_section(request, app_label):
    """Drill-down page: the sub-menus of one dashboard section, as cards."""
    section = next(
        (a for a in admin.site.get_app_list(request) if a['app_label'] == app_label),
        None,
    )
    if section is None:
        raise Http404('Unknown admin section')
    if not section.get('has_permission'):
        raise PermissionDenied
    context = admin.site.each_context(request)
    context.update({
        'title': section['name'],
        'section': section,
        'section_label': app_label,
        'section_name': section['name'],
        'dashboard_url': reverse('admin:index'),
    })

    if app_label == 'members':
        context.update(_members_section_context(request))
    return TemplateResponse(request, 'admin/section_index.html', context)


def _members_section_context(request):
    """Inline the church membership dashboard on the Members section page.

    The section used to show two tiles ("Church memberships" and "Membership
    change requests") that only linked to other pages. Administrators work in
    the directory itself, so the section page now renders it directly and the
    two tiles are dropped from the template. Pending applications and updates
    are surfaced by the notification bell instead of a separate tile.
    """
    from members import dashboard as membership_dashboard
    from members.models import ChurchMembership

    model_admin = admin.site._registry.get(ChurchMembership)
    if model_admin is None or not model_admin.has_view_permission(request):
        # No access to the membership records: keep the normal tile listing,
        # which shows the locked section rather than leaking the directory.
        return {}

    context = membership_dashboard.build_dashboard_context(
        request,
        list_url=reverse('admin_section', args=['members']),
    )
    context.update({
        'can_add': model_admin.has_add_permission(request),
        'can_change': model_admin.has_change_permission(request),
        'members_dashboard': True,
    })
    return context


def admin_notifications_api(request):
    """JSON feed for the admin nav notification bell.

    The same service that powers the public/member bell applies the open,
    unread and per-user read/dismiss rules here.  Only staff-audience rows are
    included.
    """
    from notifications import services

    services.sync_admin_messages_for_user(request.user)
    items = services.notification_items(request, services.STAFF_SCOPE)
    return JsonResponse({
        'badge': services.unread_count(request, services.STAFF_SCOPE),
        'unread_count': services.unread_count(request, services.STAFF_SCOPE),
        'total': len(items),
        'items': items,
    })


def admin_notifications_history(request):
    """Staff notification history, rendered inside the admin console shell."""
    from notifications import services

    items = [
        services.serialize(notification, request)
        for notification in services.history_notifications(
            request.user, services.STAFF_SCOPE,
        )
    ]
    context = admin.site.each_context(request)
    context.update({
        'title': 'Notification history',
        'notifications': items,
        'history_url': reverse('notifications:history_staff'),
    })
    return render(request, 'notifications/admin_history.html', context)


def handler404(request, exception):
    return render(request, '404.html', status=404)


def handler500(request):
    return render(request, '500.html', status=500)


def handler403(request, exception):
    return render(request, '403.html', status=403)


def handler400(request, exception):
    return render(request, '400.html', status=400)
