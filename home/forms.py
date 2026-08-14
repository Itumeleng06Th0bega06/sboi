from django import forms

from .models import Subscriber, Testimony


class TestimonyForm(forms.ModelForm):
    class Meta:
        model = Testimony
        fields = ['name', 'message']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Your name'}),
            'message': forms.Textarea(attrs={'class': 'input', 'placeholder': 'Share what God has done...', 'rows': 4}),
        }


class SubscriberForm(forms.ModelForm):
    class Meta:
        model = Subscriber
        fields = ['email']
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'input', 'placeholder': 'Your email address'}),
        }
