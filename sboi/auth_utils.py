"""Authentication helpers shared by the public and admin login forms."""

from django.contrib.auth.models import User


def username_for_login(identifier):
    """Resolve a login identifier that may be either a username or an email.

    Django's default user model does not require emails to be unique, so the
    email address is only swapped for a username when it matches exactly one
    account. In every other case the original value is returned and treated as
    a plain username, which keeps the normal authentication flow intact.
    """
    if not identifier or '@' not in identifier:
        return identifier

    usernames = list(
        User.objects.filter(email__iexact=identifier)
        .values_list('username', flat=True)[:2]
    )
    if len(usernames) == 1:
        return usernames[0]
    return identifier
