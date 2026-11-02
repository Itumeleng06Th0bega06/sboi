from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'notifications'
    verbose_name = 'Notifications'

    def ready(self):
        # Register the lightweight receivers that keep the bell in step with
        # the underlying activities (contact messages, memberships, content).
        from . import signals  # noqa: F401
