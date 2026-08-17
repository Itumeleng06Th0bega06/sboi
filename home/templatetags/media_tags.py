import os

import cloudinary.utils
from django import template
from django.conf import settings

register = template.Library()


@register.simple_tag
def opt_img(image, width=1000, height=None):
    """Render an optimized Cloudinary URL for the given ImageFieldFile.

    Serves a scaled, auto-compressed version instead of the full original,
    keeping pages fast on slow connections. Falls back to plain image.url
    when media is not on Cloudinary (local development).
    """
    if not image or not image.name:
        return ''
    name = image.name.replace('\\', '/')
    if settings.STORAGES['default']['BACKEND'] != 'sboi.cloudinary_storage.CloudinaryMediaStorage':
        return image.url
    transforms = []
    if width:
        transforms.append({'width': width, 'crop': 'scale'})
    if height:
        transforms.append({'height': height, 'crop': 'scale'})
    if os.path.splitext(name)[1].lower() != '.png':
        transforms.append({'quality': 'auto', 'fetch_format': 'auto'})
    else:
        transforms.append({'quality': 'auto'})
    url, _ = cloudinary.utils.cloudinary_url(name, secure=True, transformation=transforms)
    return url