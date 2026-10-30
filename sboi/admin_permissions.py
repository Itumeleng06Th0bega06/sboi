"""Shared area-permission helpers for the custom admin site.

The public site is divided into a small number of editor areas (home page,
about page, blackboard, membership, and so on). Each area has exactly one
custom permission named ``<app>.<area>``. A staff member who holds that
permission can view, add, change and delete everything in that area; there are
no separate per-action permissions to assign.

Django's automatically-created add/change/delete/view permissions are kept in
the database (they are still used internally by Django), but they are never
offered in the Group or User permission pickers. Only the permissions listed in
``AREA_PERMISSIONS`` are shown.
"""

from functools import reduce
from operator import or_

from django.contrib.auth.models import Permission
from django.core.exceptions import ImproperlyConfigured
from django.db.models import Q


# One permission per editable area/function. The codename always starts with
# ``manage_`` so the picker filter and the setup command stay in sync.
AREA_PERMISSIONS = (
    'home.manage_home_content',
    'home.manage_testimonies',
    'home.manage_subscribers',
    'about.manage_about',
    'about.manage_values',
    'blackboard.manage_blackboard',
    'blackboard.manage_rsvps',
    'blackboard.manage_member_access',
    'contact.manage_contact_details',
    'contact.manage_contact_messages',
    'gallery.manage_gallery',
    'members.manage_membership',
    'auth.manage_staff_accounts',
)


# Role groups created by ``python manage.py setup_roles``. The command only
# adds these permissions; it never removes permissions added manually later.
ROLE_GROUPS = {
    'Home Page Editor': ('home.manage_home_content',),
    'Home Testimonies Moderator': ('home.manage_testimonies',),
    'Newsletter Manager': ('home.manage_subscribers',),
    'About Page Editor': ('about.manage_about',),
    'Values Page Editor': ('about.manage_values',),
    'Blackboard Manager': ('blackboard.manage_blackboard',),
    'Blackboard RSVP Manager': ('blackboard.manage_rsvps',),
    'Member Access Manager': ('blackboard.manage_member_access',),
    'Contact Page Editor': ('contact.manage_contact_details',),
    'Contact Messages Manager': ('contact.manage_contact_messages',),
    'Gallery Manager': ('gallery.manage_gallery',),
    'Membership Manager': ('members.manage_membership',),
    'Staff Accounts Manager': ('auth.manage_staff_accounts',),
}


def _permission_q():
    """Return a Q object matching every configured area permission."""
    conditions = []
    for dotted_name in AREA_PERMISSIONS:
        app_label, codename = dotted_name.split('.', 1)
        conditions.append(
            Q(content_type__app_label=app_label, codename=codename)
        )
    return reduce(or_, conditions, Q(pk__in=[]))


def area_permission_queryset():
    """Only the custom manage permissions, for the admin permission pickers."""
    return (
        Permission.objects.filter(_permission_q())
        .select_related('content_type')
        .order_by('content_type__app_label', 'content_type__model', 'codename')
    )


class AreaPermissionMixin:
    """Map all ModelAdmin permission hooks to one area permission.

    Set ``area_permission`` to the dotted permission name on every ModelAdmin
    and inline that belongs to the area. Django still consults the normal
    ``has_*_permission`` methods, but all of them answer with the same check,
    so holding the area permission grants full control of the area.
    """

    area_permission = None

    def _has_area_permission(self, request, obj=None):
        permission = self.area_permission
        if not permission:
            raise ImproperlyConfigured(
                f'{self.__class__.__name__} must define area_permission.'
            )
        return request.user.has_perm(permission)

    def has_module_permission(self, request):
        return self._has_area_permission(request)

    def has_view_permission(self, request, obj=None):
        return self._has_area_permission(request, obj)

    def has_view_or_change_permission(self, request, obj=None):
        return self._has_area_permission(request, obj)

    def has_add_permission(self, request, obj=None):
        return self._has_area_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        return self._has_area_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return self._has_area_permission(request, obj)

    def formfield_for_manytomany(self, db_field, request=None, **kwargs):
        """Show only the clean manage permissions in Group/User forms."""
        if db_field.name in ('permissions', 'user_permissions'):
            remote_model = getattr(db_field.remote_field, 'model', None)
            if remote_model is Permission:
                kwargs['queryset'] = area_permission_queryset()
        return super().formfield_for_manytomany(
            db_field, request=request, **kwargs
        )
