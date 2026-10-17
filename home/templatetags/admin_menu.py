"""Template helpers for the menu-driven admin dashboard.

The dashboard itself is generated from Django's permission-filtered
``available_apps`` (rendered by Jazzmin's ``get_side_menu`` tag), so its
structure never needs to be maintained by hand. Only the optional short
descriptions live here; a module with no entry simply renders without one.
"""

from django import template

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
    # custom links (keyed by lower-cased name)
    'membership dashboard': 'Overview of church membership statistics',
    # auth
    'auth.group': 'Permission groups for admin users',
    'auth.user': 'Admin and staff user accounts',
}


@register.filter
def module_description(item):
    """Return a short description for a side-menu item, or an empty string."""
    if not item:
        return ''
    try:
        key = item.get('model_str') or item.get('name') or ''
    except AttributeError:
        return ''
    return MODULE_DESCRIPTIONS.get(key.lower(), '')
