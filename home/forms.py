from django import forms

from .models import Subscriber, Testimony


class TestimonyForm(forms.ModelForm):
    class Meta:
        model = Testimony
        fields = ['name', 'email', 'phone', 'preferred_contact', 'message']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Your name'}),
            'message': forms.Textarea(attrs={'class': 'input', 'placeholder': 'Share what God has done...', 'rows': 4}),
            'email': forms.EmailInput(attrs={'class': 'input', 'placeholder': 'Your email'}),
            'phone': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Contact number / WhatsApp'}),
            'preferred_contact': forms.Select(attrs={'class': 'input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Email stays optional (as before), and a missing preference falls
        # back to the model default rather than rejecting the testimony.
        self.fields['preferred_contact'].required = False
        self.fields['preferred_contact'].initial = Testimony.CONTACT_EMAIL

    def clean_preferred_contact(self):
        return (
            self.cleaned_data.get('preferred_contact')
            or Testimony.CONTACT_EMAIL
        )

    def clean(self):
        cleaned = super().clean()
        preferred = (
            cleaned.get('preferred_contact') or Testimony.CONTACT_EMAIL
        )
        phone = (cleaned.get('phone') or '').strip()
        if (
            preferred in {
                Testimony.CONTACT_WHATSAPP,
                Testimony.CONTACT_PHONE,
            }
            and not phone
        ):
            self.add_error(
                'phone',
                'Add a phone or WhatsApp number so we can reach you this way.',
            )
        return cleaned


class SubscriberForm(forms.ModelForm):
    class Meta:
        model = Subscriber
        fields = ['email']
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'input', 'placeholder': 'Your email address'}),
        }
