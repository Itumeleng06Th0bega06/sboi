"""Sunday service now runs 09:00–12:00 instead of two sittings.

Only the untouched seed value is replaced, so an admin's own wording is
never overwritten.
"""
from django.db import migrations

OLD = (
    'Sundays: 09:00 & 11:00\n'
    'Wednesdays: 17:00 — Bible Study\n'
    'Fridays: 17:00 — Intercession'
)
NEW = (
    'Sundays: 09:00 – 12:00\n'
    'Wednesdays: 17:00 — Bible Study\n'
    'Fridays: 17:00 — Intercession'
)


def forwards(apps, schema_editor):
    ContactInfo = apps.get_model('contact', 'ContactInfo')
    ContactInfo.objects.filter(service_times=OLD).update(service_times=NEW)


def backwards(apps, schema_editor):
    ContactInfo = apps.get_model('contact', 'ContactInfo')
    ContactInfo.objects.filter(service_times=NEW).update(service_times=OLD)


class Migration(migrations.Migration):

    dependencies = [
        ('contact', '0002_alter_contactinfo_options_and_more'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
