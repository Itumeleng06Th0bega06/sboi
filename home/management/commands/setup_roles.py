"""Create or refresh the admin role groups.

Run after migrations::

    python manage.py setup_roles

The command is intentionally additive: it creates missing groups, adds the
area permissions each group needs, and leaves anything you have assigned
manually untouched. It is safe to run after every deployment.
"""

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError

from sboi.admin_permissions import (
    AREA_PERMISSIONS,
    ROLE_GROUPS,
    area_permission_queryset,
)


class Command(BaseCommand):
    help = 'Create/refresh the admin role groups and their area permissions.'

    def handle(self, *args, **options):
        permissions = {
            f'{permission.content_type.app_label}.{permission.codename}': permission
            for permission in area_permission_queryset()
        }

        missing = [
            name for name in AREA_PERMISSIONS if name not in permissions
        ]
        if missing:
            raise CommandError(
                'Missing area permissions: %s. Run "python manage.py migrate" '
                'first.' % ', '.join(missing)
            )

        created_count = 0
        for group_name, permission_names in ROLE_GROUPS.items():
            group, created = Group.objects.get_or_create(name=group_name)
            if created:
                created_count += 1
            for permission_name in permission_names:
                group.permissions.add(permissions[permission_name])
            suffix = ' (created)' if created else ''
            self.stdout.write(
                self.style.SUCCESS(f'{group_name}{suffix}')
            )

        self.stdout.write(
            self.style.SUCCESS(
                'Role groups ready: %s group(s) created, %s group(s) checked. '
                'Existing manual permissions were left in place.'
                % (created_count, len(ROLE_GROUPS))
            )
        )
