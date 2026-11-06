from django.apps import AppConfig


class MembersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'members'
    verbose_name = 'Church Membership'

    def ready(self):
        import members.models_comms  # noqa: F401
