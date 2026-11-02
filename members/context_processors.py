"""Account-wide template context for the public site navigation.

The member bell/avatar live in the shared header, so the unread counts are
supplied here rather than being duplicated in every account view. Admin pages
are skipped: the admin console already has its own notification bell and the
public member tables are not part of that request.
"""

from django.conf import settings

from . import services


def _admin_prefix():
    raw = (getattr(settings, 'ADMIN_URL', 'admin/') or 'admin/').lstrip('/')
    return '/' + raw


def member_account(request):
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {}
    if request.path.startswith(_admin_prefix()):
        return {}

    profile = getattr(user, 'member_profile', None)
    avatar_url = ''
    if profile is not None and profile.avatar:
        try:
            avatar_url = profile.avatar.url
        except ValueError:
            # Private/unsupported storage has no public URL; fall back to initials.
            avatar_url = ''

    display_name = user.get_full_name() or user.get_username()
    parts = [part for part in display_name.split() if part]
    if not parts:
        initials = 'S'
    elif len(parts) == 1:
        initials = parts[0][:2].upper()
    else:
        initials = (parts[0][0] + parts[-1][0]).upper()

    return {
        'member_unread_notifications': services.unread_notification_count(request),
        'member_unread_messages': services.unread_message_count(user),
        'member_avatar_url': avatar_url,
        'member_initials': initials,
        'member_display_name': display_name,
    }
