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
        fields = ['name', 'email', 'phone', 'subject', 'message']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Your full name'}),
            'email': forms.EmailInput(attrs={'class': 'input', 'placeholder': 'Your email'}),
            'phone': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Phone (optional)'}),
            'subject': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Subject'}),
            'message': forms.Textarea(attrs={'class': 'input', 'placeholder': 'How can we help you?', 'rows': 6}),
        }


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
