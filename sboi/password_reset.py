"""Development helpers for the two password-reset flows.

In development the project emails through Django's console backend (see
``sboi/settings.py``), so a reset link is only printed to the ``runserver``
terminal and is easy to miss. When that backend is active, these views also
stash the freshly generated link in the session and the "check your email"
page shows it as a clickable link. Production (SMTP) behaviour is unchanged.
"""

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.views import PasswordResetDoneView, PasswordResetView
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

DEBUG_LINKS_SESSION_KEY = 'debug_password_reset_links'


def _console_backend_active():
    return settings.DEBUG and 'console' in settings.EMAIL_BACKEND


class DebugLinkPasswordResetView(PasswordResetView):
    """PasswordResetView that exposes reset links on the console backend."""

    # Set per URLconf, e.g. 'members:password_reset_confirm'.
    reset_url_name = None

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.reset_url_name and _console_backend_active():
            links = []
            for user in form.get_users(form.cleaned_data['email']):
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                token = default_token_generator.make_token(user)
                path = reverse(
                    self.reset_url_name,
                    kwargs={'uidb64': uid, 'token': token},
                )
                links.append(self.request.build_absolute_uri(path))
            if links:
                self.request.session[DEBUG_LINKS_SESSION_KEY] = links
        return response


class DebugLinkPasswordResetDoneView(PasswordResetDoneView):
    """PasswordResetDoneView that hands the debug links to the template."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        links = self.request.session.pop(DEBUG_LINKS_SESSION_KEY, [])
        context['debug_reset_links'] = links if _console_backend_active() else []
        return context
