"""Data helpers for the Church Membership admin dashboard.

The dashboard template (``admin/members/churchmembership/dashboard.html``)
is a Django template fragment supplied as a UI kit; this module turns the
project's real ``ChurchMembership`` records into the context it expects.

Everything here reads from the database. No member is ever hard-coded.
"""

from django.core.paginator import Paginator
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from .models import (
    MEMBERSHIP_CATEGORY_CHOICES,
    MEMBERSHIP_STATUS_CHOICES,
    MINISTRY_CHOICES,
    ChurchMembership,
    MembershipMinistry,
)

# Rows per page in the member directory.
PAGE_SIZE = 10

DASHBOARD_URL_NAME = 'admin:members_churchmembership_dashboard'
CHANGELIST_URL_NAME = 'admin:members_churchmembership_changelist'
ADD_URL_NAME = 'admin:members_churchmembership_add'
CHANGE_URL_NAME = 'admin:members_churchmembership_change'


def initials(name):
    """Two-letter avatar initials, with a safe fallback for blank names."""
    parts = [p for p in (name or '').split() if p]
    if not parts:
        return 'M'
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def full_address(membership):
    parts = [membership.address, membership.city, membership.province]
    return ', '.join(p for p in parts if p)


def group_names(membership):
    labels = {membership_item.name: membership_item.get_name_display()
              for membership_item in membership.ministries.all()}
    return sorted(labels.values(), key=str.lower)


def _membership_type(membership):
    if not membership.membership_category:
        return ''
    return membership.get_membership_category_display()


def member_summary(membership):
    """The compact record used by the directory table."""
    name = membership.full_name
    return {
        'id': membership.pk,
        'full_name': name,
        'initials': initials(name),
        'member_id': membership.membership_id or '',
        'email': membership.user.email,
        'phone': membership.phone,
        'membership_type': _membership_type(membership),
        'group_names': group_names(membership),
        'status': membership.get_status_display(),
        'profile_url': '{}?member={}'.format(
            reverse(DASHBOARD_URL_NAME), membership.pk,
        ),
        'edit_url': reverse(CHANGE_URL_NAME, args=[membership.pk]),
    }


def member_detail(membership):
    """The full record used by the profile panel."""
    detail = member_summary(membership)
    detail.update({
        'date_joined': membership.date_joined_church or membership.created_at,
        'date_of_birth': membership.date_of_birth,
        'gender': membership.get_gender_display() if membership.gender else '',
        'address': full_address(membership),
        'baptism_status': (
            membership.get_baptism_status_display()
            if membership.baptism_status else ''
        ),
        'baptism_date': membership.baptism_date,
        'previous_church': membership.previous_church,
        'interests': [
            interest.get_name_display() for interest in membership.interests.all()
        ],
        'activities': [
            ministry.get_name_display()
            for ministry in membership.ministries.all()
            if ministry.status == 'current'
        ],
        'skills': membership.skills or membership.talents or '',
        'availability': membership.preferred_times or membership.service_areas or '',
        'notes': membership.notes,
    })
    return detail


def _option(value, label):
    return {'value': value, 'label': label}


def membership_type_options():
    return [_option(value, label) for value, label in MEMBERSHIP_CATEGORY_CHOICES]


def status_options():
    return [_option(value, label) for value, label in MEMBERSHIP_STATUS_CHOICES]


def group_options():
    """Ministries that actually appear on at least one member record."""
    labels = dict(MINISTRY_CHOICES)
    used = (
        MembershipMinistry.objects.values_list('name', flat=True).distinct()
    )
    options = [_option(name, labels.get(name, name)) for name in used]
    return sorted(options, key=lambda option: option['label'].lower())


def membership_stats():
    """Live counts shown in the four stat cards."""
    today = timezone.localdate()
    return {
        'total_members': ChurchMembership.objects.count(),
        'baptized_members': ChurchMembership.objects.filter(
            baptism_status='baptized',
        ).count(),
        'active_groups': (
            MembershipMinistry.objects.values('name').distinct().count()
        ),
        'new_this_month': ChurchMembership.objects.filter(
            created_at__year=today.year, created_at__month=today.month,
        ).count(),
    }


def filtered_members(request):
    """The directory queryset for the current search/filter state."""
    queryset = ChurchMembership.objects.select_related('user').prefetch_related(
        'interests', 'ministries',
    )

    query = (request.GET.get('q') or '').strip()
    if query:
        queryset = queryset.filter(
            Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
            | Q(user__username__icontains=query)
            | Q(user__email__icontains=query)
            | Q(phone__icontains=query)
            | Q(alt_phone__icontains=query)
            | Q(membership_id__icontains=query)
        )

    membership_type = request.GET.get('type') or ''
    if membership_type:
        queryset = queryset.filter(membership_category=membership_type)

    group = request.GET.get('group') or ''
    if group:
        queryset = queryset.filter(ministries__name=group).distinct()

    status = request.GET.get('status') or ''
    if status:
        queryset = queryset.filter(status=status)

    return queryset.order_by('-created_at')


def selected_member(request):
    """Resolve ``?member=<pk>`` to a profile dict, or ``None`` when absent."""
    raw = request.GET.get('member')
    if not raw:
        return None
    try:
        pk = int(raw)
    except (TypeError, ValueError):
        return None
    membership = (
        ChurchMembership.objects.select_related('user')
        .prefetch_related('interests', 'ministries')
        .filter(pk=pk)
        .first()
    )
    if membership is None:
        return None
    return member_detail(membership)


def build_dashboard_context(request):
    """The complete context for the church membership dashboard template."""
    page_obj = Paginator(filtered_members(request), PAGE_SIZE).get_page(
        request.GET.get('page'),
    )
    return {
        'membership_list_url': reverse(DASHBOARD_URL_NAME),
        'add_member_url': reverse(ADD_URL_NAME),
        'directory_url': reverse(CHANGELIST_URL_NAME),
        'stats': membership_stats(),
        'members': [member_summary(m) for m in page_obj.object_list],
        'selected_member': selected_member(request),
        'search_query': request.GET.get('q', ''),
        'selected_type': request.GET.get('type', ''),
        'selected_group': request.GET.get('group', ''),
        'selected_status': request.GET.get('status', ''),
        'membership_type_options': membership_type_options(),
        'group_options': group_options(),
        'status_options': status_options(),
        'page_obj': page_obj,
    }
