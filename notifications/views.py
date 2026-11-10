from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from . import services
from .models import Notification


def _bell_context(request, scope=None):
    try:
        scope = scope or getattr(request, 'notification_scope', None)
        items = services.notification_items(request, scope)
        badge = services.unread_count(request, scope)
        return {
            'ok': True,
            'badge': badge,
            'unread_count': badge,
            'total': len(items),
            'items': items,
            'notifications': items,
        }
    except Exception:
        return {
            'ok': True,
            'badge': 0,
            'unread_count': 0,
            'total': 0,
            'items': [],
            'notifications': [],
        }


def bell_api(request):
    """JSON feed for the public/member bell.

    Staff have their own admin endpoint; this endpoint always applies the
    public/member scope so a staff session on the public site cannot leak
    staff-only activities into the public dropdown.
    """
    return JsonResponse(_bell_context(request, services.PUBLIC_SCOPE))


@login_required
def bell_api_staff(request):
    request.notification_scope = services.STAFF_SCOPE
    return JsonResponse(_bell_context(request, services.STAFF_SCOPE))


@require_GET
def open_notification(request, pk):
    """Open a bell item: mark it read, then follow its safe internal link.

    Opening is the only read action in the redesigned bell, so a member never
    has to hunt for a separate "mark read" control.
    """
    notification = services.get_visible_notification(pk, request)
    if notification is None:
        raise Http404('Notification not found.')
    services.mark_read(notification, request)

    target = (notification.url or '').strip()
    if target and url_has_allowed_host_and_scheme(
        target,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(target)
    if request.user.is_authenticated:
        return redirect(reverse('members:account_notifications'))
    return redirect(reverse('notifications:history'))


@require_POST
def read_notification(request, pk):
    notification = services.get_visible_notification(pk, request)
    if notification is None:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False}, status=404)
        return redirect('home:home')
    services.mark_read(notification, request)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'ok': True, 'id': notification.pk})
    return redirect(notification.url or 'home:home')


@require_POST
def dismiss_notification(request, pk):
    notification = services.get_visible_notification(pk, request)
    if notification is None:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False}, status=404)
        return redirect('home:home')
    services.dismiss(notification, request)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'ok': True, 'id': notification.pk})
    return redirect(request.META.get('HTTP_REFERER') or notification.url or 'home:home')


def _action_scope(request):
    """Scope sent by the bell that triggered the bulk action.

    The member bell always targets public/member rows; only staff may ask for
    the staff scope, so a member can never touch a staff-only notification.
    """
    requested = request.POST.get('scope')
    if requested == services.STAFF_SCOPE and request.user.is_staff:
        return services.STAFF_SCOPE
    if requested == services.PUBLIC_SCOPE:
        return services.PUBLIC_SCOPE
    return None


@login_required
@require_POST
def mark_all_read(request):
    """Bulk action for the admin bell: mark every visible row as read."""
    scope = _action_scope(request)
    services.mark_all_read(request, scope)
    return JsonResponse(_bell_context(request, scope))


@login_required
@require_POST
def delete_selected(request):
    """Bulk action for the admin bell: remove the ticked rows from the bell."""
    scope = _action_scope(request)
    removed = services.dismiss_many(request, request.POST.getlist('ids'), scope)
    payload = _bell_context(request, scope)
    payload['removed'] = removed
    return JsonResponse(payload)


@require_POST
def archive_notification(request, pk):
    notification = services.get_visible_notification(pk, request)
    if notification is None:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False}, status=404)
        return redirect('home:home')
    services.archive(notification, request)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'ok': True, 'id': notification.pk})
    return redirect(request.META.get('HTTP_REFERER') or notification.url or 'home:home')


def history(request, scope=None):
    scope = scope or services.PUBLIC_SCOPE
    items = []
    for notification in services.history_notifications(request.user, scope):
        items.append(services.serialize(notification, request))
    context = {
        'notifications': items,
        'scope': scope,
    }
    return render_template(request, context)


def history_public(request):
    return history(request, services.PUBLIC_SCOPE)


@login_required
def history_member(request):
    return history(request, services.PUBLIC_SCOPE)


@login_required
def history_staff(request):
    return history(request, services.STAFF_SCOPE)


def render_template(request, context):
    from django.shortcuts import render

    template = 'notifications/history.html'
    try:
        return render(request, template, context)
    except Exception:
        from django.http import HttpResponse

        rows = ''.join(
            f"<li><a href='{item['url']}'>{item['title']}</a> - {item['date']}</li>"
            for item in context.get('notifications', [])
        )
        return HttpResponse(
            f"<html><body><h1>Notifications</h1><ul>{rows or '<li>None</li>'}</ul></body></html>"
        )
