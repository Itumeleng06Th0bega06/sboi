from django import forms
from django.contrib.auth.forms import UserChangeForm

from .page_permissions import PAGE_BY_KEY, PAGES, granted_page_keys


class PageAccessWidget(forms.CheckboxSelectMultiple):
    """Renders page access as grouped cards with per-page descriptions."""

    template_name = 'admin/widgets/page_access.html'

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        selected = set(value or [])
        disabled = bool(getattr(self, 'is_superuser', False))
        groups = []
        for page in PAGES:
            group_label = page['group']
            group = next((g for g in groups if g['label'] == group_label), None)
            if group is None:
                group = {'label': group_label, 'pages': []}
                groups.append(group)
            group['pages'].append({
                'key': page['key'],
                'label': page['label'],
                'description': page['description'],
                'checked': page['key'] in selected or disabled,
                'disabled': disabled,
            })
        context['widget']['groups_render'] = groups
        context['widget']['is_superuser'] = disabled
        return context


class PageAccessUserChangeForm(UserChangeForm):
    """``UserChangeForm`` plus a grouped "page access" editor.

    ``page_access`` is a declared (non-model) field, so it never touches
    ``User`` itself; the UserAdmin applies it in ``save_related``.
    """

    page_access = forms.MultipleChoiceField(
        choices=[(page['key'], page['label']) for page in PAGES],
        required=False,
        widget=PageAccessWidget,
        label='Page access',
        help_text=(
            'Tick the pages this person may manage. Each page unlocks its '
            'sections on the dashboard, the section menus, quick add and search.'
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        target = self.instance
        is_super = bool(target and target.pk and target.is_superuser)
        # Deep-copied per form instance, so stashing a flag on it is safe.
        self.fields['page_access'].widget.is_superuser = is_super
        if target and target.pk:
            self.initial['page_access'] = sorted(granted_page_keys(target))
            if is_super:
                # A superuser already reaches every page; make that explicit
                # and read-only rather than implying the ticks do something.
                self.fields['page_access'].disabled = True

    def clean_page_access(self):
        # Guard against a forged POST granting a page that no longer exists.
        return [key for key in self.cleaned_data['page_access'] if key in PAGE_BY_KEY]
