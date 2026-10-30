"""Add the one custom permission used by the staff-accounts admin area.

The built-in ``auth.User`` and ``auth.Group`` models cannot declare
``Meta.permissions``, so this permission is created explicitly. It is still a
normal Django permission and is assigned through the Staff Accounts Manager
group like every other area permission.
"""

from django.db import migrations


PERMISSION_NAME = 'Staff accounts: manage'
PERMISSION_CODENAME = 'manage_staff_accounts'


def create_permission(apps, schema_editor):
    ContentType = apps.get_model('contenttypes', 'ContentType')
    Permission = apps.get_model('auth', 'Permission')
    content_type, _ = ContentType.objects.get_or_create(
        app_label='auth',
        model='user',
    )
    Permission.objects.get_or_create(
        content_type=content_type,
        codename=PERMISSION_CODENAME,
        defaults={'name': PERMISSION_NAME},
    )


def remove_permission(apps, schema_editor):
    Permission = apps.get_model('auth', 'Permission')
    Permission.objects.filter(
        content_type__app_label='auth',
        content_type__model='user',
        codename=PERMISSION_CODENAME,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('home', '0005_alter_featuredsection_options_and_more'),
        ('contenttypes', '0002_remove_content_type_name'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(create_permission, remove_permission),
    ]
