from django import forms

from .models import EventRsvp


class EventRsvpForm(forms.ModelForm):
    class Meta:
        model = EventRsvp
        fields = ['event', 'name', 'email', 'phone', 'guests']
        widgets = {
            'event': forms.HiddenInput(),
            'name': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Your full name'}),
            'email': forms.EmailInput(attrs={'class': 'input', 'placeholder': 'Email (optional)'}),
            'phone': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Phone (optional)'}),
            'guests': forms.NumberInput(attrs={'class': 'input', 'min': 1}),
        }
