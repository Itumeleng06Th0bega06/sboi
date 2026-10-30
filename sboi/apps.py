from django.contrib.admin.apps import AdminConfig


class SBOIAdminConfig(AdminConfig):
    """Use the project's custom AdminSite without changing app registration."""

    default_site = 'sboi.admin_site.SBOIAdminSite'
