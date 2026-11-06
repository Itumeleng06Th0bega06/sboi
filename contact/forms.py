from django import forms
from django.core.validators import FileExtensionValidator

from members.models import ChurchMembership

from .models import (
    ALLOWED_MESSAGE_ATTACHMENT_EXTENSIONS,
    ContactMessage,
    validate_message_attachment_size,
)


class ContactMessageForm(forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ['name', 'email', 'phone', 'preferred_contact', 'subject', 'message']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Your full name'}),
            'email': forms.EmailInput(attrs={'class': 'input', 'placeholder': 'Your email'}),
            'phone': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Contact number / WhatsApp'}),
            'subject': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Subject'}),
            'message': forms.Textarea(attrs={'class': 'input', 'placeholder': 'How can we help you?', 'rows': 6}),
            'preferred_contact': forms.Select(attrs={'class': 'input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Older clients and API posts may omit the preference; fall back to
        # the model default (email) instead of rejecting the message.
        self.fields['preferred_contact'].required = False
        self.fields['preferred_contact'].initial = ContactMessage.CONTACT_EMAIL

    def clean_preferred_contact(self):
        return (
            self.cleaned_data.get('preferred_contact')
            or ContactMessage.CONTACT_EMAIL
        )

    def clean(self):
        cleaned = super().clean()
        preferred = (
            cleaned.get('preferred_contact') or ContactMessage.CONTACT_EMAIL
        )
        phone = (cleaned.get('phone') or '').strip()
        if (
            preferred in {
                ContactMessage.CONTACT_WHATSAPP,
                ContactMessage.CONTACT_PHONE,
            }
            and not phone
        ):
            self.add_error(
                'phone',
                'Add a phone or WhatsApp number so we can reach you this way.',
            )
        return cleaned


class MemberMessageForm(forms.Form):
    """The single composer used for every private member → admin message.

    No category is required: a testimony, prayer request, question or concern
    is simply ordinary text in the same box.
    """

    message = forms.CharField(
        label='Message',
        max_length=5000,
        widget=forms.Textarea(attrs={
            'class': 'input account-message-input',
            'placeholder': 'Message…',
            'rows': 1,
            'style': 'min-height:36px; max-height:60px; resize:none; padding-top:0.35rem; padding-bottom:0.35rem;',
            'required': True,
        }),
    )
    attachment = forms.FileField(
        label='Attach a file (optional)',
        required=False,
        validators=[
            FileExtensionValidator(ALLOWED_MESSAGE_ATTACHMENT_EXTENSIONS),
            validate_message_attachment_size,
        ],
    )

    def clean_message(self):
        message = (self.cleaned_data.get('message') or '').strip()
        if not message:
            raise forms.ValidationError('Please type a message before sending.')
        return message


class AdminReplyForm(MemberMessageForm):
    """Administrator reply. Same validation, different label."""
    CHANNEL_EMAIL = 'email'
    CHANNEL_WHATSAPP = 'whatsapp'
    CHANNEL_BOTH = 'both'
    CHANNEL_CHOICES = [
        (CHANNEL_EMAIL, 'Email'),
        (CHANNEL_WHATSAPP, 'WhatsApp'),
        (CHANNEL_BOTH, 'Both'),
    ]

    channel = forms.ChoiceField(
        choices=CHANNEL_CHOICES,
        initial=CHANNEL_EMAIL,
        required=False,
        widget=forms.Select(attrs={'class': 'select'}),
    )

    def clean_channel(self):
        return self.cleaned_data.get('channel') or self.CHANNEL_EMAIL


class AdminComposeForm(forms.Form):
    membership = forms.ModelChoiceField(
        label='Member',
        queryset=ChurchMembership.objects.select_related('user').order_by(
            'user__last_name', 'user__first_name',
        ),
        widget=forms.Select(attrs={'class': 'select'}),
    )
    subject = forms.CharField(
        label='Subject',
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'input',
            'placeholder': 'Optional subject',
        }),
    )
    message = forms.CharField(
        label='Message',
        max_length=5000,
        widget=forms.Textarea(attrs={
            'class': 'input',
            'placeholder': 'Write a private message to this member…',
            'rows': 6,
        }),
    )
    attachment = forms.FileField(
        label='Attach a file (optional)',
        required=False,
        validators=[
            FileExtensionValidator(ALLOWED_MESSAGE_ATTACHMENT_EXTENSIONS),
            validate_message_attachment_size,
        ],
    )

    def clean_message(self):
        message = (self.cleaned_data.get('message') or '').strip()
        if not message:
            raise forms.ValidationError('Please type a message before sending.')
        return message
