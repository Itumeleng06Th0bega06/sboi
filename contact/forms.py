from django import forms

from .models import ContactMessage


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
