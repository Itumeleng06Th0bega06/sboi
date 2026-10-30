"""Custom AdminSite for the Shekinah Blaze admin console.

Two rules drive this module:

* every registered section/model is visible in the dashboard, even when the
  signed-in staff member cannot open it; and
* visibility never grants access. Access is enforced by each ModelAdmin's
  ``AreaPermissionMixin``, so an unassigned section simply returns 403.

The stock Django admin hides models the user has no permission for. We keep
that enforcement, but override the app-dictionary builder so the navigation can
still show every section with a locked state.
"""

from functools import wraps

from django.apps import apps
from django.contrib.admin import AdminSite
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.template.response import TemplateResponse
from django.urls import NoReverseMatch, reverse
from django.utils.text import capfirst


class SBOIAdminSite(AdminSite):
    """Admin site that exposes all sections but protects them individually."""

    def _build_app_dict(self, request, label=None):
        """Build the full app list, including sections the user cannot open.

        This mirrors Django's implementation but intentionally does not skip
        models when ``has_module_permission()`` is false. Each entry records a
        ``has_permission`` flag so templates can render a lock instead of
        hiding the section.
        """
        app_dict = {}

        if label:
            models = {
                model: model_admin
                for model, model_admin in self._registry.items()
                if model._meta.app_label == label
            }
        else:
            models = self._registry

        for model, model_admin in models.items():
            app_label = model._meta.app_label
            perms = model_admin.get_model_perms(request)
            has_permission = True in perms.values()

            info = (app_label, model._meta.model_name)
            model_dict = {
                'model': model,
                'name': capfirst(model._meta.verbose_name_plural),
                'object_name': model._meta.object_name,
                'perms': perms,
                'has_permission': has_permission,
                'admin_url': None,
                'add_url': None,
            }

            # Build URLs even for locked entries: clicking a locked item must
            # reach the real admin view, where the permission mixin returns a
            # clean 403. Hiding the URL would turn it into a dead end.
            try:
                model_dict['admin_url'] = reverse(
                    'admin:%s_%s_changelist' % info,
                    current_app=self.name,
                )
            except NoReverseMatch:
                pass
            try:
                model_dict['add_url'] = reverse(
                    'admin:%s_%s_add' % info,
                    current_app=self.name,
                )
            except NoReverseMatch:
                pass

            if app_label in app_dict:
                app_dict[app_label]['models'].append(model_dict)
            else:
                app_dict[app_label] = {
                    'name': apps.get_app_config(app_label).verbose_name,
                    'app_label': app_label,
                    'app_url': reverse(
                        'admin:app_list',
                        kwargs={'app_label': app_label},
                        current_app=self.name,
                    ),
                    'has_module_perms': False,
                    'has_permission': False,
                    'models': [model_dict],
                }

        for app in app_dict.values():
            app['has_permission'] = any(
                model['has_permission'] for model in app['models']
            )
            app['has_module_perms'] = app['has_permission']

        return app_dict

    def app_index(self, request, app_label, extra_context=None):
        """Block direct access to an app section the user is not assigned to."""
        app_list = self.get_app_list(request, app_label)
        if not app_list:
            raise Http404('The requested admin page does not exist.')
        if not app_list[0].get('has_permission'):
            raise PermissionDenied
        return super().app_index(request, app_label, extra_context)

    def admin_view(self, view, cacheable=False):
        """Render a branded 403 page when an admin view denies access."""
        protected = super().admin_view(view, cacheable=cacheable)

        @wraps(protected)
        def handler(request, *args, **kwargs):
            try:
                return protected(request, *args, **kwargs)
            except PermissionDenied as exc:
                # Leave CSRF failures to Django's normal CSRF handling.
                if 'CSRF' in str(exc):
                    raise
                request.current_app = self.name
                context = self.each_context(request)
                context.update({'title': 'Access denied'})
                return TemplateResponse(
                    request,
                    'admin/permission_denied.html',
                    context,
                    status=403,
                )

        return handler
