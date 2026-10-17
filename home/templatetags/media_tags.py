from django import template

register = template.Library()


@register.simple_tag
def opt_img(image, width=1000, height=None):
    """Return the URL for an uploaded image.

    Uploads are stored on the local disk: ``media/`` in development and
    ``public_html/media`` in production, where Apache serves them from
    ``/media/``. ``width``/``height`` are accepted for template compatibility.
    """
    if not image or not image.name:
        return ''
    return image.url
