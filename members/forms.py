from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.db import transaction

from sboi.auth_utils import username_for_login

from .models import (
    BAPTISM_STATUS_CHOICES,
    GENDER_CHOICES,
    INTEREST_CHOICES,
    MARITAL_STATUS_CHOICES,
    MEMBERSHIP_CATEGORY_CHOICES,
    MINISTRY_CHOICES,
    ChurchMembership,
    MembershipInterest,
    MembershipMinistry,
    MembershipPastoralNote,
)


class MemberLoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = 'Email or username'
        self.fields['username'].widget.attrs.update({
            'class': 'input',
            'placeholder': 'Email or username',
            'autocomplete': 'username',
            'autofocus': True,
        })
        self.fields['password'].widget.attrs.update({
            'class': 'input',
            'placeholder': 'Password',
            'autocomplete': 'current-password',
        })

    def clean(self):
        identifier = self.cleaned_data.get('username')
        if identifier:
            self.cleaned_data['username'] = username_for_login(identifier)
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


# ---------------------------------------------------------------------------
# Church membership forms
# ---------------------------------------------------------------------------

_DATE_FORMATS = ['%Y-%m-%d', '%d/%m/%Y', '%d %B %Y', '%d %b %Y']

# Short single-choice questions render as neat checkbox-style controls
# (radios), and the long "pick as many as you like" lists render as true
# multi-checkbox groups, so members can always tick more than one option.


def _phone_validator(value):
    """Loose international phone check: digits plus + ( ) - and spaces."""
    if not value:
        return value
    allowed = set('0123456789+() -')
    digits = ''.join(c for c in value if c.isdigit())
    if set(value) - allowed or len(digits) < 7 or len(digits) > 15:
        raise forms.ValidationError('Enter a valid phone number.')
    return value


class ChurchMembershipFieldsMixin(forms.Form):
    """All church-membership fields, shared by the register and join forms.

    Every field here is optional. Nothing forces a member to share personal
    information: only the account credentials (username, email, password) are
    technically required, and those live on the account form, not here.
    This subclasses ``forms.Form`` so Django's metaclass actually collects the
    declared fields when it is mixed into a ModelForm.
    """

    phone = forms.CharField(
        label='Phone number', max_length=30, required=False,
        validators=[_phone_validator],
        widget=forms.TextInput(attrs={'class': 'input', 'placeholder': 'Phone number'}),
    )
    alt_phone = forms.CharField(
        label='Alternative phone number', max_length=30, required=False,
        validators=[_phone_validator],
        widget=forms.TextInput(attrs={'class': 'input', 'placeholder': 'Alternative phone number'}),
    )
    date_of_birth = forms.DateField(
        label='Date of birth', required=False, input_formats=_DATE_FORMATS,
        widget=forms.DateInput(
            attrs={'class': 'input', 'placeholder': 'Date of birth', 'data-date': ''},
            format='%Y-%m-%d',
        ),
    )
    gender = forms.ChoiceField(
        label='Gender', required=False, choices=GENDER_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'choice-list'}),
    )
    marital_status = forms.ChoiceField(
        label='Marital status', required=False, choices=MARITAL_STATUS_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'choice-list'}),
    )
    address = forms.CharField(
        label='Residential address', max_length=255, required=False,
        widget=forms.TextInput(attrs={'class': 'input', 'placeholder': 'Residential address'}),
    )
    city = forms.CharField(
        label='Suburb or town', max_length=120, required=False,
        widget=forms.TextInput(attrs={'class': 'input', 'placeholder': 'Suburb or town'}),
    )
    province = forms.CharField(
        label='Province', max_length=120, required=False,
        widget=forms.TextInput(attrs={'class': 'input', 'placeholder': 'Province'}),
    )
    emergency_contact_name = forms.CharField(
        label='Emergency contact name', max_length=120, required=False,
        widget=forms.TextInput(attrs={'class': 'input', 'placeholder': 'Emergency contact name'}),
    )
    emergency_contact_phone = forms.CharField(
        label='Emergency contact phone number', max_length=30, required=False,
        validators=[_phone_validator],
        widget=forms.TextInput(attrs={'class': 'input', 'placeholder': 'Emergency contact phone number'}),
    )

    # --- Family -----------------------------------------------------------
    spouse_name = forms.CharField(
        label='Spouse full name', max_length=200, required=False,
        widget=forms.TextInput(attrs={
            'class': 'input', 'placeholder': 'Spouse full name',
            'data-family': 'spouse',
        }),
    )
    children_names = forms.CharField(
        label='Children', required=False,
        help_text=(
            'One child per line. Children aged 16 and over can create their '
            'own membership form.'
        ),
        widget=forms.Textarea(attrs={
            'class': 'input', 'rows': 3,
            'placeholder': 'One child per line, e.g. Thabo Mokoena',
            'data-family': 'children',
        }),
    )

    # Section B
    membership_category = forms.ChoiceField(
        label='Membership category', required=False, choices=MEMBERSHIP_CATEGORY_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'choice-list'}),
    )
    date_joined_church = forms.DateField(
        label='Date joined the church', required=False, input_formats=_DATE_FORMATS,
        widget=forms.DateInput(
            attrs={'class': 'input', 'placeholder': 'Date joined the church', 'data-date': ''},
            format='%Y-%m-%d',
        ),
    )
    baptism_status = forms.ChoiceField(
        label='Baptism status', required=False, choices=BAPTISM_STATUS_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'choice-list'}),
    )
    baptism_date = forms.DateField(
        label='Baptism date', required=False, input_formats=_DATE_FORMATS,
        widget=forms.DateInput(
            attrs={'class': 'input', 'placeholder': 'Baptism date', 'data-date': ''},
            format='%Y-%m-%d',
        ),
    )
    previous_church = forms.CharField(
        label='Previous church affiliation', max_length=200, required=False,
        widget=forms.TextInput(attrs={'class': 'input', 'placeholder': 'Previous church affiliation'}),
    )
    transferring_from_church = forms.BooleanField(
        label='Transferring from another church', required=False,
    )
    preferred_language = forms.CharField(
        label='Preferred language', max_length=60, required=False,
        widget=forms.TextInput(attrs={'class': 'input', 'placeholder': 'Preferred language'}),
    )
    campus_branch = forms.CharField(
        label='Church campus or branch', max_length=120, required=False,
        widget=forms.TextInput(attrs={'class': 'input', 'placeholder': 'Church campus or branch'}),
    )

    # --- Section C: interests and spiritual growth ------------------------
    interests = forms.MultipleChoiceField(
        label='What areas of church life interest you? (tick all that apply)', required=False,
        choices=INTEREST_CHOICES,
        widget=forms.CheckboxSelectMultiple,
    )
    interests_other = forms.CharField(
        label='Other interest', max_length=200, required=False,
        widget=forms.TextInput(attrs={'class': 'input', 'placeholder': 'Other interest'}),
    )
    spiritual_growth_goals = forms.CharField(
        label='What would you like to learn or grow in spiritually?', required=False,
        widget=forms.Textarea(attrs={'class': 'input', 'rows': 3, 'placeholder': 'What would you like to learn or grow in spiritually?'}),
    )
    wants_bible_study = forms.BooleanField(
        label='I would like to attend Bible study or discipleship sessions', required=False,
    )
    wants_contact = forms.BooleanField(
        label='I would like someone from the church to contact me', required=False,
    )
    guidance_support = forms.CharField(
        label='Any areas where you would appreciate guidance or support?', required=False,
        widget=forms.Textarea(attrs={'class': 'input', 'rows': 3, 'placeholder': 'Any areas where you would appreciate guidance or support?'}),
    )

    # --- Section D: current church activities -----------------------------
    currently_involved = forms.BooleanField(
        label='I am currently participating in church activities', required=False,
    )
    current_ministries = forms.MultipleChoiceField(
        label='Which ministries or departments are you involved in? (tick all that apply)', required=False,
        choices=MINISTRY_CHOICES,
        widget=forms.CheckboxSelectMultiple,
    )
    current_activities = forms.CharField(
        label='Other ministries, departments or activities', required=False,
        widget=forms.Textarea(attrs={'class': 'input', 'rows': 2, 'placeholder': 'Other ministries, departments or activities'}),
    )
    small_group_name = forms.CharField(
        label='Small group / cell group / Bible study group', max_length=200, required=False,
        widget=forms.TextInput(attrs={'class': 'input', 'placeholder': 'Small group / cell group / Bible study group'}),
    )
    volunteers_currently = forms.BooleanField(
        label='I currently volunteer in the church', required=False,
    )
    volunteer_ministries = forms.MultipleChoiceField(
        label='If you volunteer, which activities do you assist with? (tick all that apply)', required=False,
        choices=MINISTRY_CHOICES,
        widget=forms.CheckboxSelectMultiple,
    )
    volunteer_details = forms.CharField(
        label='Anything else about your volunteering?', required=False,
        widget=forms.Textarea(attrs={'class': 'input', 'rows': 2, 'placeholder': 'Anything else about your volunteering?'}),
    )
    wants_to_join = forms.MultipleChoiceField(
        label='Which ministries or activities would you like to join? (tick all that apply)', required=False,
        choices=MINISTRY_CHOICES,
        widget=forms.CheckboxSelectMultiple,
    )
    wants_to_volunteer = forms.BooleanField(
        label='I would like to volunteer in the future', required=False,
    )

    # --- Section E: skills, talents and availability ----------------------
    skills = forms.CharField(
        label='Skills or professional experience', required=False,
        widget=forms.Textarea(attrs={'class': 'input', 'rows': 2, 'placeholder': 'Skills or professional experience'}),
    )
    talents = forms.CharField(
        label='Talents or abilities you would like to contribute', required=False,
        widget=forms.Textarea(attrs={'class': 'input', 'rows': 2, 'placeholder': 'Talents or abilities you would like to contribute'}),
    )
    service_areas = forms.CharField(
        label='Areas where you would be willing to serve', required=False,
        widget=forms.Textarea(attrs={'class': 'input', 'rows': 2, 'placeholder': 'Areas where you would be willing to serve'}),
    )
    preferred_times = forms.CharField(
        label='Preferred days or times for church activities', max_length=200, required=False,
        widget=forms.TextInput(attrs={'class': 'input', 'placeholder': 'Preferred days or times for church activities'}),
    )
    additional_info = forms.CharField(
        label='Any additional information you would like the church to know', required=False,
        widget=forms.Textarea(attrs={'class': 'input', 'rows': 3, 'placeholder': 'Any additional information you would like the church to know'}),
    )

    # --- Section F: additional information --------------------------------
    notes = forms.CharField(
        label='Additional notes', required=False,
        widget=forms.Textarea(attrs={'class': 'input', 'rows': 3, 'placeholder': 'Additional notes'}),
    )
    prayer_request = forms.CharField(
        label='Prayer request', required=False,
        widget=forms.Textarea(attrs={'class': 'input', 'rows': 3, 'placeholder': 'Prayer request'}),
    )
    pastoral_support_requested = forms.BooleanField(
        label='I would like pastoral support', required=False,
    )

    PERSONAL_FIELDS = [
        'phone', 'alt_phone', 'date_of_birth', 'gender', 'marital_status',
        'address', 'city', 'province', 'emergency_contact_name',
        'emergency_contact_phone',
    ]
    FAMILY_FIELDS = ['spouse_name', 'children_names']
    CHURCH_FIELDS = [
        'membership_category', 'date_joined_church', 'baptism_status',
        'baptism_date', 'previous_church', 'transferring_from_church',
        'preferred_language', 'campus_branch',
    ]
    INTEREST_FIELDS = ['interests', 'interests_other', 'spiritual_growth_goals', 'wants_bible_study', 'wants_contact', 'guidance_support']
    ACTIVITY_FIELDS = ['currently_involved', 'current_ministries', 'current_activities', 'small_group_name', 'volunteers_currently', 'volunteer_ministries', 'volunteer_details', 'wants_to_join', 'wants_to_volunteer']
    SKILL_FIELDS = ['skills', 'talents', 'service_areas', 'preferred_times', 'additional_info']
    EXTRA_FIELDS = ['notes', 'prayer_request', 'pastoral_support_requested']

    def _bound(self, names):
        return [self[name] for name in names if name in self.fields]

    def sections(self):
        """Group bound fields into named sections for the template."""
        return [
            {'id': 'church-family', 'title': 'Family details',
             'blurb': (
                 'Add your spouse and children so the church can care for your '
                 'whole family.'
             ),
             'fields': self._bound(self.FAMILY_FIELDS)},
            {'id': 'church-b', 'title': 'Church membership information',
             'fields': self._bound(self.CHURCH_FIELDS)},
            {'id': 'church-c', 'title': 'Interests and spiritual growth',
             'fields': self._bound(self.INTEREST_FIELDS)},
            {'id': 'church-d', 'title': 'Current church activities',
             'fields': self._bound(self.ACTIVITY_FIELDS)},
            {'id': 'church-e', 'title': 'Skills, talents and availability',
             'fields': self._bound(self.SKILL_FIELDS)},
            {'id': 'church-f', 'title': 'Additional information',
             'fields': self._bound(self.EXTRA_FIELDS)},
        ]

    def personal_sections(self):
        """Account (if any) + personal-detail sections for the template."""
        sections = []
        if 'username' in self.fields:
            sections.append({
                'id': 'account',
                'title': 'Account details',
                'fields': self._bound(['username', 'email', 'password1', 'password2']),
            })
        personal = ['first_name', 'last_name'] + self.PERSONAL_FIELDS
        sections.append({
            'id': 'church-a',
            'title': 'Personal details',
            'fields': self._bound(personal),
        })
        return sections

    # -- persistence helpers ------------------------------------------------

    MODEL_FIELD_NAMES = [
        'phone', 'alt_phone', 'date_of_birth', 'gender', 'marital_status',
        'spouse_name', 'children_names', 'address', 'city',
        'province', 'emergency_contact_name', 'emergency_contact_phone',
        'membership_category', 'date_joined_church', 'baptism_status',
        'baptism_date', 'previous_church', 'transferring_from_church',
        'preferred_language', 'campus_branch', 'interests_other',
        'spiritual_growth_goals', 'wants_bible_study', 'wants_contact',
        'currently_involved', 'current_activities', 'small_group_name',
        'volunteers_currently', 'volunteer_details', 'wants_to_volunteer',
        'skills', 'talents', 'service_areas', 'preferred_times',
        'additional_info', 'notes',
    ]

    def _populate(self, membership):
        for name in self.MODEL_FIELD_NAMES:
            if name in self.cleaned_data:
                setattr(membership, name, self.cleaned_data[name])

        # A spouse only belongs to a married member: switching the status
        # clears any previously captured spouse name.
        membership.spouse_name = (membership.spouse_name or '').strip()
        if membership.marital_status != 'married':
            membership.spouse_name = ''
        membership.children_names = (membership.children_names or '').strip()
        membership.save()

        # Rebuild multi-select rows (idempotent, so re-submits never duplicate).
        membership.interests.all().delete()
        for name in self.cleaned_data.get('interests') or []:
            MembershipInterest.objects.get_or_create(membership=membership, name=name)

        membership.ministries.all().delete()
        rows = []
        rows += [('current', n) for n in self.cleaned_data.get('current_ministries') or []]
        rows += [('volunteer', n) for n in self.cleaned_data.get('volunteer_ministries') or []]
        rows += [('join', n) for n in self.cleaned_data.get('wants_to_join') or []]
        for status, name in rows:
            MembershipMinistry.objects.get_or_create(
                membership=membership, name=name, status=status,
            )

        guidance = self.cleaned_data.get('guidance_support')
        prayer = self.cleaned_data.get('prayer_request')
        pastoral = self.cleaned_data.get('pastoral_support_requested')
        if guidance or prayer or pastoral:
            note, _ = MembershipPastoralNote.objects.get_or_create(membership=membership)
            note.guidance_support = guidance or ''
            note.prayer_request = prayer or ''
            note.pastoral_support_requested = bool(pastoral)
            note.save()
        return membership


class ChurchMembershipRegistrationForm(ChurchMembershipFieldsMixin, UserCreationForm):
    """Create a new user account *and* a linked church membership.

    Only the account credentials are required (username, email, password).
    Every personal and church question is optional and may be left blank.
    """

    first_name = forms.CharField(
        max_length=120, required=False,
        widget=forms.TextInput(attrs={'class': 'input', 'placeholder': 'First name'}),
    )
    last_name = forms.CharField(
        max_length=120, required=False,
        widget=forms.TextInput(attrs={'class': 'input', 'placeholder': 'Last name'}),
    )
    email = forms.EmailField(
        required=True,
        help_text='Required. Used to sign in and to contact you about your account.',
        widget=forms.EmailInput(attrs={'class': 'input', 'placeholder': 'Email address *'}),
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'username', 'password1', 'password2']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Username *'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].help_text = (
            'Required. Used to sign in (or you can sign in with your email).'
        )
        self.fields['password1'].widget = forms.PasswordInput(attrs={'class': 'input', 'placeholder': 'Password *'})
        self.fields['password2'].widget = forms.PasswordInput(attrs={'class': 'input', 'placeholder': 'Confirm password *'})

    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                'An account with this email already exists. Please sign in and '
                'choose "Join the church membership" instead.'
            )
        return email

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=True)
        membership = ChurchMembership(user=user)
        self._populate(membership)
        return user


class ChurchMembershipJoinForm(ChurchMembershipFieldsMixin, forms.ModelForm):
    """Attach church membership details to an existing logged-in account."""

    class Meta:
        model = ChurchMembership
        fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # ``Meta.fields`` is empty because the visible fields are declared on
        # the mixin, so populate their initial values from the instance by
        # hand. Without this the "update my details" form always starts blank.
        instance = self.instance
        if instance is not None and instance.pk:
            for name in self.MODEL_FIELD_NAMES:
                if name in self.fields and name not in self.initial:
                    self.initial[name] = getattr(instance, name)

    @transaction.atomic
    def save(self, user, commit=True):
        membership, _ = ChurchMembership.objects.get_or_create(user=user)
        self._populate(membership)
        return membership
