from pathlib import Path

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator

from .models import ALLOWED_ATTACHMENT_EXTENSIONS, MAX_ATTACHMENT_SIZE

User = get_user_model()


def _portal_queryset(queryset):
    """Return a usable queryset; an empty queryset is falsy but still valid."""
    if queryset is None:
        return User.objects.none()
    return queryset


def attachment_accept_attribute():
    return ','.join(f'.{extension}' for extension in ALLOWED_ATTACHMENT_EXTENSIONS)


class MessageForm(forms.Form):
    body = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 2,
            'placeholder': 'Write a message…',
            'class': 'comms-composer__textarea',
            'aria-label': 'Message',
            'maxlength': 4000,
        }),
    )
    reply_to = forms.IntegerField(
        required=False,
        widget=forms.HiddenInput(),
    )
    attachment = forms.FileField(
        required=False,
        widget=forms.ClearableFileInput(attrs={
            'class': 'comms-composer__file',
            'accept': attachment_accept_attribute(),
        }),
    )

    def clean_body(self):
        body = (self.cleaned_data.get('body') or '').strip()
        if len(body) > 4000:
            raise ValidationError('Messages cannot be longer than 4,000 characters.')
        return body

    def clean_attachment(self):
        attachment = self.cleaned_data.get('attachment')
        if not attachment:
            return attachment
        if attachment.size == 0:
            raise ValidationError('The selected file is empty.')
        if attachment.size > MAX_ATTACHMENT_SIZE:
            raise ValidationError('Attachments must be 10 MB or smaller.')
        extension = Path(attachment.name).suffix.lower().lstrip('.')
        if extension not in ALLOWED_ATTACHMENT_EXTENSIONS:
            raise ValidationError(
                'This file type is not allowed. Upload a document or image.'
            )
        # FileExtensionValidator is also declared on the model, so files added
        # through any other route are checked at save time too.
        FileExtensionValidator(ALLOWED_ATTACHMENT_EXTENSIONS)(attachment)
        return attachment

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('body') and not cleaned.get('attachment'):
            raise ValidationError('Write a message or attach a file.')
        return cleaned


class GroupForm(forms.Form):
    name = forms.CharField(
        max_length=120,
        widget=forms.TextInput(attrs={
            'placeholder': 'e.g. Finance Team',
            'autocomplete': 'off',
        }),
    )
    description = forms.CharField(
        required=False,
        max_length=2000,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'What is this group for?',
        }),
    )
    members = forms.ModelMultipleChoiceField(
        queryset=None,
        required=False,
        widget=forms.CheckboxSelectMultiple(),
    )
    members_can_add_members = forms.BooleanField(required=False)
    members_can_edit_group = forms.BooleanField(required=False)

    def __init__(self, *args, portal_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['members'].queryset = _portal_queryset(portal_queryset)

    def clean_name(self):
        name = (self.cleaned_data.get('name') or '').strip()
        if not name:
            raise ValidationError('Give the group a name.')
        return name


class GroupSettingsForm(forms.Form):
    name = forms.CharField(max_length=120)
    description = forms.CharField(
        required=False,
        max_length=2000,
        widget=forms.Textarea(attrs={'rows': 3}),
    )
    members_can_add_members = forms.BooleanField(required=False)
    members_can_edit_group = forms.BooleanField(required=False)

    def clean_name(self):
        name = (self.cleaned_data.get('name') or '').strip()
        if not name:
            raise ValidationError('Give the group a name.')
        return name


class AddMembersForm(forms.Form):
    members = forms.ModelMultipleChoiceField(
        queryset=None,
        required=True,
        widget=forms.CheckboxSelectMultiple(),
        error_messages={
            'required': 'Choose at least one staff member to add.',
        },
    )

    def __init__(self, *args, portal_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['members'].queryset = _portal_queryset(portal_queryset)


class StartDirectForm(forms.Form):
    recipient = forms.ModelChoiceField(
        queryset=None,
        error_messages={'required': 'Choose a staff member.'},
    )

    def __init__(self, *args, portal_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['recipient'].queryset = _portal_queryset(portal_queryset)
