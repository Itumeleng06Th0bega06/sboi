from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe


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