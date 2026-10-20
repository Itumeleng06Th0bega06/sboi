"""Page-based admin permissions.

Maps the human "pages" of the site (the dashboard sections / public pages) onto
Django's own model permissions. Checking a page on a user grants the standard
view/add/change/delete permission bundle for every model behind that page.

This leans on the fact that the admin's section list is already permission
filtered through ``admin.site.get_app_list`` — so once a page's bundle is
granted, that page lights up for the user on the dashboard, the section
drill-down, the quick-add menu and the global search with no extra wiring.
"""

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType

# Order matters: it is the order the pages render in the "Page access" editor.
# ``models`` are (app_label, ModelName) pairs; granting a page grants the
# view/add/change/delete bundle for each of them.
PAGES = [
    {
        'key': 'dashboard',
        'label': 'Dashboard',
        'description': 'Read-only overview, charts and activity feed.',
        'group': 'Site pages',
        # The dashboard is a read-only rollup of everything else, so it is
        # backed by the read-only "view" permission on the stats model.
        'models': [('home', 'HomeStat')],
        'view_only': True,
    },
    {
        'key': 'home',
        'label': 'Home page',
        'description': 'Stats, featured sections, testimonies and subscribers.',
        'group': 'Site pages',
        'models': [
            ('home', 'HomeStat'),
            ('home', 'FeaturedSection'),
            ('home', 'Testimony'),
            ('home', 'Subscriber'),
        ],
    },
    {
        'key': 'about',
        'label': 'About page',
        'description': 'Church profile, vision, mission, values and leaders.',
        'group': 'Site pages',
        'models': [
            ('about', 'ChurchProfile'),
            ('about', 'VisionPillar'),
            ('about', 'MissionComponent'),
            ('about', 'PathwayStep'),
            ('about', 'MissionAction'),
            ('about', 'CoreValue'),
            ('about', 'Leader'),
        ],
    },
    {
        'key': 'blackboard',
        'label': 'Blackboard',
        'description': 'Devotions, events, sermons, announcements and PDFs.',
        'group': 'Site pages',
        'models': [
            ('blackboard', 'Devotion'),
            ('blackboard', 'Announcement'),
            ('blackboard', 'Event'),
            ('blackboard', 'EventRsvp'),
            ('blackboard', 'Sermon'),
            ('blackboard', 'PdfMaterial'),
        ],
    },
    {
        'key': 'gallery',
        'label': 'Gallery',
        'description': 'Homepage slider images and captions.',
        'group': 'Site pages',
        'models': [('gallery', 'SliderImage')],
    },
    {
        'key': 'contact',
        'label': 'Contact page',
        'description': 'Public contact details and incoming messages.',
        'group': 'Site pages',
        'models': [
            ('contact', 'ContactInfo'),
            ('contact', 'ContactMessage'),
        ],
    },
    {
        'key': 'members',
        'label': 'Members',
        'description': 'Church membership records, interests and pastoral notes.',
        'group': 'People & access',
        'models': [
            ('members', 'ChurchMembership'),
            ('members', 'MembershipInterest'),
            ('members', 'MembershipMinistry'),
            ('members', 'MembershipPastoralNote'),
            ('blackboard', 'MemberProfile'),
        ],
        'extra_codenames': {
            ('members', 'ChurchMembership'): ['export_churchmembership'],
        },
    },
    {
        'key': 'users',
        'label': 'Users & groups',
        'description': 'Manage staff accounts and their groups.',
        'group': 'People & access',
        'models': [
            ('auth', 'User'),
            ('auth', 'Group'),
        ],
    },
]

PAGE_BY_KEY = {page['key']: page for page in PAGES}

# The standard CRUD bundle. A read-only page only asks for "view".
FULL_ACTIONS = ['view', 'add', 'change', 'delete']
VIEW_ACTIONS = ['view']


def page_permission_keys(page):
    """Permission natural keys ("app_label.codename") owned by one page."""
    actions = VIEW_ACTIONS if page.get('view_only') else FULL_ACTIONS
    extra = page.get('extra_codenames') or {}
    keys = []
    for app_label, model_name in page['models']:
        lower = model_name.lower()
        for action in actions:
            keys.append(f'{app_label}.{action}_{lower}')
        for codename in extra.get((app_label, model_name), ()):
            keys.append(f'{app_label}.{codename}')
    return keys


def page_permission_ids(page):
    """Database ids of the Permission rows owned by one page."""
    actions = VIEW_ACTIONS if page.get('view_only') else FULL_ACTIONS
    extra = page.get('extra_codenames') or {}
    ids = []
    for app_label, model_name in page['models']:
        content_type = ContentType.objects.get(
            app_label=app_label,
            model=model_name.lower(),
        )
        ids.extend(
            Permission.objects.filter(
                content_type=content_type,
                codename__in=[f'{action}_{model_name.lower()}' for action in actions],
            ).values_list('id', flat=True)
        )
        codenames = extra.get((app_label, model_name), ())
        if codenames:
            ids.extend(
                Permission.objects.filter(
                    content_type=content_type,
                    codename__in=list(codenames),
                ).values_list('id', flat=True)
            )
    return ids


def managed_permission_ids():
    """Every permission id that any page owns — the set we are allowed to edit.

    Permissions outside this set (admin log, future custom perms) are left
    untouched when page access is saved, so this editor never clobbers
    permissions it does not understand.
    """
    ids = set()
    for page in PAGES:
        ids.update(page_permission_ids(page))
    return ids


def granted_page_keys(user):
    """Page keys the user currently has (superusers always have everything)."""
    if not user or not user.is_authenticated:
        return set()
    if user.is_superuser:
        return set(PAGE_BY_KEY)
    granted = set()
    for page in PAGES:
        keys = page_permission_keys(page)
        if all(user.has_perm(key) for key in keys):
            granted.add(page['key'])
    return granted


def apply_page_access(user, selected_keys):
    """Sync ``user.user_permissions`` so exactly ``selected_keys`` are granted.

    Only permissions owned by a page are touched; anything else the user holds
    is preserved. Superusers keep their implicit full access regardless.
    """
    selected_keys = set(selected_keys) & set(PAGE_BY_KEY)
    keep = set()
    for key in selected_keys:
        keep.update(page_permission_ids(PAGE_BY_KEY[key]))

    editable = managed_permission_ids()
    existing = set(user.user_permissions.values_list('id', flat=True))
    # Drop page permissions that were unchecked, keep everything else.
    to_remove = (existing & editable) - keep
    if to_remove:
        user.user_permissions.remove(*to_remove)
    to_add = keep - existing
    if to_add:
        user.user_permissions.add(*to_add)

    # Django caches a user's permissions on the instance (_perm_cache plus the
    # per-backend _user_perm_cache / _group_perm_cache). Drop them so any
    # has_perm check later in this same request reflects what we just saved
    # instead of stale results.
    for cache_attr in ('_perm_cache', '_user_perm_cache', '_group_perm_cache'):
        if hasattr(user, cache_attr):
            delattr(user, cache_attr)
