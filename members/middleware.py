"""Lightweight community presence tracking.

Only signed-in accounts are recorded. The write is throttled per session so a
busy page (feed polling, chat polling, notifications) does not hit the database
on every request, while an open session still stays "online" for the inbox.
"""

from django.utils import timezone

from .models_comms import CommunityPresence

PRESENCE_SESSION_KEY = 'community_presence_ping'
PRESENCE_INTERVAL_SECONDS = 60


class CommunityPresenceMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated:
            now = timezone.now()
            last_ping = request.session.get(PRESENCE_SESSION_KEY, 0)
            try:
                last_ping = float(last_ping)
            except (TypeError, ValueError):
                last_ping = 0
            if now.timestamp() - last_ping >= PRESENCE_INTERVAL_SECONDS:
                CommunityPresence.objects.update_or_create(
                    user=user,
                    defaults={'last_seen_at': now},
                )
                request.session[PRESENCE_SESSION_KEY] = now.timestamp()
        return self.get_response(request)
