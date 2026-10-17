"""Custom admin authentication form.

Lets staff sign in with either their username or their email address, matching
the behaviour of the public member login.
"""

from django.contrib.admin.forms import AdminAuthenticationForm

from .auth_utils import username_for_login


class EmailOrUsernameAdminAuthenticationForm(AdminAuthenticationForm):
    """Admin login that accepts a username *or* an email address."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = 'Email or username'

    def clean(self):
        identifier = self.cleaned_data.get('username')
        if identifier:
            self.cleaned_data['username'] = username_for_login(identifier)
        return super().clean()
