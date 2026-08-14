from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User


class MemberLoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({
            'class': 'input',
            'placeholder': 'Username or email',
            'autocomplete': 'username',
            'autofocus': True,
        })
        self.fields['password'].widget.attrs.update({
            'class': 'input',
            'placeholder': 'Password',
            'autocomplete': 'current-password',
        })

    def clean(self):
        username = self.cleaned_data.get('username')
        if username and '@' in username:
            try:
                user = User.objects.get(email__iexact=username)
                self.cleaned_data['username'] = user.get_username()
            except User.DoesNotExist:
                pass
        return super().clean()


class MemberRegistrationForm(UserCreationForm):
    first_name = forms.CharField(max_length=120, required=True, widget=forms.TextInput(attrs={'class': 'input', 'placeholder': 'First name'}))
    last_name = forms.CharField(max_length=120, required=True, widget=forms.TextInput(attrs={'class': 'input', 'placeholder': 'Last name'}))
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={'class': 'input', 'placeholder': 'Email address'}))

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'username', 'password1', 'password2']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Username'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget = forms.PasswordInput(attrs={'class': 'input', 'placeholder': 'Password'})
        self.fields['password2'].widget = forms.PasswordInput(attrs={'class': 'input', 'placeholder': 'Confirm password'})
