"""Template helpers for the custom admin console.

The admin shell is built from Django's permission-filtered ``app_list``; this
module supplies the presentation extras (short section descriptions, the
inline icon names used by the SVG sprite in ``templates/admin/includes/icons.html``,
and the realistic 3D icon images in ``static/images/3d/`` used by the
dashboard and section navigation). Nothing here depends on a third-party
admin theme.
"""

from django import template
from django.templatetags.static import static
from django.utils.html import format_html

register = template.Library()

# Keyed by the menu item's ``model_str`` (``app_label.modelname``) for models
# and by the lower-cased ``name`` for custom links. This is additive metadata,
# not a duplicated navigation list: unknown items fall back to no description.
MODULE_DESCRIPTIONS = {
    # home
    'home.homestat': 'Headline numbers shown on the homepage',
    'home.featuredsection': 'Featured blocks on the homepage',
    'home.testimony': 'Testimonies submitted by visitors',
    'home.subscriber': 'Newsletter subscribers',
    # about
    'about.churchprofile': 'Church name, logo and public details',
    'about.corevalue': 'Core values shown on the About page',
    'about.leader': 'Leadership team profiles',
    'about.missionaction': 'Outreach actions and mission work',
    'about.missioncomponent': 'Components of the church mission',
    'about.pathwaystep': 'Steps in the discipleship pathway',
    'about.visionpillar': 'Pillars of the church vision',
    # blackboard
    'blackboard.announcement': 'Notices published to the congregation',
    'blackboard.devotion': 'Daily devotions and reflections',
    'blackboard.event': 'Upcoming events and activities',
    'blackboard.eventrsvp': 'RSVPs received for events',
    'blackboard.memberprofile': 'Member profiles for the blackboard',
    'blackboard.pdfmaterial': 'Downloadable PDF resources',
    'blackboard.sermon': 'Sermon recordings and messages',
    # contact
    'contact.contactinfo': 'Public contact details',
    'contact.contactmessage': 'Messages sent through the contact form',
    # gallery
    'gallery.sliderimage': 'Images in the homepage slider',
    # members
    'members.churchmembership': 'Church member records and directory',
    'membership dashboard': 'Overview of church membership statistics',
    # auth
    'auth.group': 'Permission groups for admin users',
    'auth.user': 'Admin and staff user accounts',
}

# Sprite icon names (see templates/admin/includes/icons.html).
APP_ICONS = {
    'home': 'house',
    'about': 'info',
    'blackboard': 'book',
    'gallery': 'image',
    'contact': 'address-book',
    'members': 'users',
    'auth': 'shield',
}

MODEL_ICONS = {
    'home.homestat': 'chart',
    'home.featuredsection': 'star',
    'home.testimony': 'message',
    'home.subscriber': 'mail',
    'about.churchprofile': 'church',
    'about.corevalue': 'gem',
    'about.leader': 'user',
    'about.missionaction': 'handshake',
    'about.missioncomponent': 'target',
    'about.pathwaystep': 'route',
    'about.visionpillar': 'eye',
    'blackboard.announcement': 'bullhorn',
    'blackboard.devotion': 'book',
    'blackboard.event': 'calendar',
    'blackboard.eventrsvp': 'clipboard',
    'blackboard.memberprofile': 'id-card',
    'blackboard.pdfmaterial': 'file',
    'blackboard.sermon': 'video',
    'contact.contactinfo': 'address-book',
    'contact.contactmessage': 'mail',
    'gallery.sliderimage': 'image',
    'members.churchmembership': 'users',
    'auth.group': 'users',
    'auth.user': 'user',
}

# Realistic 3D icon file stems in ``static/images/3d/`` (Microsoft Fluent
# Emoji 3D renders, MIT licence). Rendered as <img> by ``app_icon`` /
# ``model_icon``; unknown keys fall back to the SVG sprite above.
APP_ICONS_3D = {
    'home': 'house',
    'about': 'church',
    'blackboard': 'book',
    'gallery': 'frame',
    'contact': 'envelope',
    'members': 'users',
    'auth': 'key',
}

MODEL_ICONS_3D = {
    'home.homestat': 'chart',
    'home.featuredsection': 'star',
    'home.testimony': 'speech',
    'home.subscriber': 'inbox',
    'about.churchprofile': 'church',
    'about.corevalue': 'gem',
    'about.leader': 'person',
    'about.missionaction': 'handshake',
    'about.missioncomponent': 'target',
    'about.pathwaystep': 'footprints',
    'about.visionpillar': 'eye',
    'blackboard.announcement': 'megaphone',
    'blackboard.devotion': 'book',
    'blackboard.event': 'calendar',
    'blackboard.eventrsvp': 'clipboard',
    'blackboard.memberprofile': 'idcard',
    'blackboard.pdfmaterial': 'page',
    'blackboard.sermon': 'video',
    'contact.contactinfo': 'telephone',
    'contact.contactmessage': 'envelope',
    'gallery.sliderimage': 'frame',
    'members.churchmembership': 'users',
    'auth.group': 'groups',
    'auth.user': 'person',
    # Custom links keyed like app-list models.
    'members.dashboard': 'growth',
}

# Every 3D icon stem shipped in ``static/images/3d/`` — used to validate
# ``icon_3d`` lookups before falling back to the SVG sprite.
_KNOWN_3D = frozenset({
    'book', 'calendar', 'chart', 'church', 'clipboard', 'envelope', 'eye',
    'footprints', 'frame', 'gem', 'groups', 'growth', 'handshake', 'house',
    'idcard', 'inbox', 'key', 'megaphone', 'page', 'person', 'speech',
    'star', 'target', 'telephone', 'users', 'video',
})


def _item_key(item, app_label=''):
    """Return the description/icon key for an app-list model or menu item."""
    if not item:
        return ''
    try:
        object_name = item.get('object_name')
        if app_label and object_name:
            return f'{app_label}.{object_name}'.lower()
        key = item.get('model_str') or item.get('name') or ''
        return str(key).lower()
    except AttributeError:
        return ''


@register.filter
def module_description(item, app_label=''):
    """Return a short description for an app-list model, or an empty string."""
    return MODULE_DESCRIPTIONS.get(_item_key(item, app_label), '')


@register.simple_tag
def admin_icon(name):
    """Render an inline SVG from the admin icon sprite."""
    return format_html(
        '<svg class="sboi-ico" aria-hidden="true" focusable="false">'
        '<use href="#sboi-i-{}"></use></svg>',
        name,
    )


def _icon_3d(name):
    """Render a realistic 3D icon image from ``static/images/3d/``."""
    return format_html(
        '<img class="sboi-ico3d" src="{}" alt="" loading="lazy" decoding="async">',
        static(f'images/3d/{name}.png'),
    )


@register.simple_tag
def icon_3d(name, fallback='folder'):
    """Render a named 3D icon (app/model-specific lookups and custom links)."""
    if name and name in _KNOWN_3D:
        return _icon_3d(name)
    return admin_icon(fallback)


@register.simple_tag
def app_icon(app_label):
    """Render the icon for an admin app section (3D image when mapped)."""
    name = APP_ICONS_3D.get(app_label)
    if name:
        return _icon_3d(name)
    return admin_icon(APP_ICONS.get(app_label, 'folder'))


@register.simple_tag
def model_icon(app_label, object_name=''):
    """Render the icon for an app-list model, falling back to its app."""
    key = f'{app_label}.{object_name}'.lower() if object_name else ''
    name = MODEL_ICONS_3D.get(key) or APP_ICONS_3D.get(app_label)
    if name:
        return _icon_3d(name)
    return admin_icon(
        MODEL_ICONS.get(key, APP_ICONS.get(app_label, 'folder'))
    )
