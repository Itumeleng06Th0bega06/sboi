from django import forms
from django.contrib import admin
from django.db import models
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe


class OptionalDateAdminMixin:
    """Admin date fields are optional; a blank date saves as today."""

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        for field in form.base_fields.values():
            if isinstance(field, forms.DateField):
                field.required = False
        return form

    def save_model(self, request, obj, form, change):
        for field in obj._meta.fields:
            if isinstance(field, models.DateField) and getattr(obj, field.name) is None:
                setattr(obj, field.name, timezone.localdate())
        super().save_model(request, obj, form, change)


def image_thumb(obj, field='image'):
    """Render a thumbnail of an ImageField with the storage path shown beneath."""
    file_field = getattr(obj, field, None)
    if not file_field or not file_field.name:
        return mark_safe('<span class="admin-thumb admin-thumb-empty" aria-hidden="true">&mdash;</span>')
    return format_html(
        '<img class="admin-thumb" src="{url}" alt="{name}" title="{name}" loading="lazy">'
        '<span class="admin-thumb-path">{name}</span>',
        url=file_field.url,
        name=file_field.name,
    )


class ImageThumbMixin:
    """Adds a ``thumb`` column to an admin list view."""

    thumb_field = 'image'

    @admin.display(description='Image')
    def thumb(self, obj):
        return image_thumb(obj, self.thumb_field)