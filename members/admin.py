import csv
import re

from django import forms
from django.contrib import admin
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import path

from sboi.admin_permissions import AreaPermissionMixin

from . import dashboard
from .forms import ChurchMembershipFieldsMixin
from .models import MINISTRY_CHOICES, ChurchMembership


class MinistryFilter(admin.SimpleListFilter):
    title = 'ministry'
    parameter_name = 'ministry'

    def lookups(self, request, model_admin):
        return list(MINISTRY_CHOICES)

    def queryset(self, request, queryset):
        value = self.value()
        if value:
            return queryset.filter(ministries__name=value).distinct()
        return queryset


class ChurchMembershipAdminForm(ChurchMembershipFieldsMixin, forms.ModelForm):
    """Admin form for :class:`ChurchMembership`.

    The church questions come from
    :class:`members.forms.ChurchMembershipFieldsMixin`, the same mixin the
    public register/join forms use, so administrators see exactly the same
    fields, in the same order, with the same widgets. The linked account and
    the internal record status are the only admin-only additions.
    """

    first_name = forms.CharField(
        required=False, max_length=150, label='First name',
        widget=forms.TextInput(attrs={'placeholder': 'First name'}),
    )
    last_name = forms.CharField(
        required=False, max_length=150, label='Last name',
        widget=forms.TextInput(attrs={'placeholder': 'Last name'}),
    )
    email = forms.EmailField(
        required=False, label='Email address',
        widget=forms.EmailInput(attrs={'placeholder': 'Email address'}),
    )
    username = forms.CharField(
        required=False, max_length=150, label='Username',
        widget=forms.TextInput(attrs={'autocomplete': 'username'}),
    )
    password1 = forms.CharField(
        required=False, label='Password',
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )
    password2 = forms.CharField(
        required=False, label='Confirm password',
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )

    class Meta:
        model = ChurchMembership
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The raw account picker has nothing to select on a fresh install.
        self.fields.pop('user', None)

        instance = self.instance
        if instance and instance.pk:
            user = instance.user
            self.fields['first_name'].initial = user.first_name
            self.fields['last_name'].initial = user.last_name
            self.fields['email'].initial = user.email
            self.fields['username'].initial = user.username
            self.fields.pop('password1')
            self.fields.pop('password2')
            self.fields['username'].help_text = 'Linked site account username.'

            # The multi-choice questions and the pastoral note live in
            # related tables, so they need to be loaded by hand.
            self.initial['interests'] = list(
                instance.interests.values_list('name', flat=True)
            )
            for field_name, status in (
                ('current_ministries', 'current'),
                ('volunteer_ministries', 'volunteer'),
                ('wants_to_join', 'join'),
            ):
                self.initial[field_name] = list(
                    instance.ministries.filter(status=status)
                    .values_list('name', flat=True)
                )

            note = getattr(instance, 'pastoral_note', None)
            if note is not None:
                self.initial['guidance_support'] = note.guidance_support
                self.initial['prayer_request'] = note.prayer_request
                self.initial['pastoral_support_requested'] = (
                    note.pastoral_support_requested
                )
        else:
            self.fields['username'].help_text = (
                'Optional — generated from the email address when left blank.'
            )
            self.fields['password1'].help_text = (
                'Optional — leave blank to create the account without a password; '
                'one can be set later from the Users page.'
            )

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip()
        queryset = User.objects.filter(email__iexact=email)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.user_id)
        if email and queryset.exists():
            raise forms.ValidationError(
                'A site account with this email address already exists.'
            )
        return email

    def clean_username(self):
        username = (self.cleaned_data.get('username') or '').strip()
        queryset = User.objects.filter(username=username)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.user_id)
        if username and queryset.exists():
            raise forms.ValidationError('This username is already taken.')
        return username

    def clean(self):
        cleaned = super().clean()
        if 'password1' in self.fields and cleaned.get('password1') != cleaned.get('password2'):
            self.add_error('password2', 'The two password fields did not match.')
        return cleaned

    def _generated_username(self, stem):
        candidate, count = stem, 2
        while User.objects.filter(username=candidate).exists():
            candidate = f'{stem}{count}'
            count += 1
        return candidate

    def save(self, commit=True):
        cleaned = self.cleaned_data

        if self.instance.pk:
            user = self.instance.user
        else:
            email = (cleaned.get('email') or '').strip()
            requested = (cleaned.get('username') or '').strip()
            stem = re.sub(r'\W+', '_', (email.split('@')[0] or 'member').lower()).strip('_')
            stem = re.sub(r'_+', '_', stem).strip('_') or 'member'
            username = requested or self._generated_username(stem[:30])
            user = User(username=username)

        user.first_name = (cleaned.get('first_name') or '').strip()
        user.last_name = (cleaned.get('last_name') or '').strip()
        user.email = (cleaned.get('email') or '').strip()
        if 'password1' in self.fields and cleaned.get('password1'):
            user.set_password(cleaned['password1'])
        user.save()

        obj = super().save(commit=False)
        obj.user = user
        obj.status = cleaned.get('status') or obj.status

        if commit:
            obj.save()
            self._populate(obj)
        return obj

    def _save_m2m(self):
        """Persist the church questions after the admin saves the instance."""
        super()._save_m2m()
        if self.instance.pk:
            self._populate(self.instance)


@admin.register(ChurchMembership)
class ChurchMembershipAdmin(AreaPermissionMixin, admin.ModelAdmin):
    area_permission = 'members.manage_membership'
    list_display = [
        'membership_id', 'full_name', 'email', 'phone',
        'membership_category', 'status', 'baptism_status', 'created_at',
    ]
    list_filter = [
        'membership_category', 'marital_status', 'status', 'baptism_status',
        MinistryFilter, 'created_at',
    ]
    search_fields = [
        'membership_id', 'user__username', 'user__first_name',
        'user__last_name', 'user__email', 'phone', 'alt_phone',
        'spouse_name', 'children_names',
    ]
    date_hierarchy = 'created_at'
    list_per_page = 25
    form = ChurchMembershipAdminForm
    readonly_fields = ['membership_id', 'created_at', 'updated_at']
    actions = ['export_csv']
    # Keep this list in step with the public church form's sections (see
    # ChurchMembershipFieldsMixin.sections). Only the account and record
    # blocks are admin-only.
    fieldsets = [
        ('Account details', {
            'fields': ['username', 'email', 'password1', 'password2'],
        }),
        ('Personal details', {'fields': [
            'first_name', 'last_name', 'phone', 'alt_phone', 'date_of_birth',
            'gender', 'marital_status', 'address', 'city', 'province',
            'emergency_contact_name', 'emergency_contact_phone',
        ]}),
        ('Family details', {
            'fields': ['spouse_name', 'children_names'],
            'description': (
                'Add your spouse and children so the church can care for your '
                'whole family.'
            ),
        }),
        ('Church membership information', {'fields': [
            'membership_category', 'date_joined_church', 'baptism_status',
            'baptism_date', 'previous_church', 'transferring_from_church',
            'preferred_language', 'campus_branch',
        ]}),
        ('Interests and spiritual growth', {'fields': [
            'interests', 'interests_other', 'spiritual_growth_goals',
            'wants_bible_study', 'wants_contact', 'guidance_support',
        ]}),
        ('Current church activities', {'fields': [
            'currently_involved', 'current_ministries', 'current_activities',
            'small_group_name', 'volunteers_currently', 'volunteer_ministries',
            'volunteer_details', 'wants_to_join', 'wants_to_volunteer',
        ]}),
        ('Skills, talents and availability', {'fields': [
            'skills', 'talents', 'service_areas', 'preferred_times',
            'additional_info',
        ]}),
        ('Additional information', {'fields': [
            'notes', 'prayer_request', 'pastoral_support_requested',
        ]}),
        ('Record', {'fields': [
            'membership_id', 'status', 'created_at', 'updated_at',
        ]}),
    ]

    def get_fieldsets(self, request, obj=None):
        # Passwords are only requested when creating a member; on the change
        # view the Account tab shows just the username and email.
        if obj is None:
            return self.fieldsets
        fieldsets = []
        for title, opts in self.fieldsets:
            if title == 'Account details':
                fields = [f for f in opts['fields'] if f not in ('password1', 'password2')]
                fieldsets.append((title, {'fields': fields}))
            else:
                fieldsets.append((title, opts))
        return fieldsets

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')

    @admin.display(description='Member', ordering='user__first_name')
    def full_name(self, obj):
        return obj.full_name

    @admin.display(description='Email', ordering='user__email')
    def email(self, obj):
        return obj.user.email

    # -- Church membership dashboard ---------------------------------------

    def get_urls(self):
        custom = [
            path(
                'dashboard/',
                self.admin_site.admin_view(self.dashboard_view),
                name='members_churchmembership_dashboard',
            ),
        ]
        return custom + super().get_urls()

    def changelist_view(self, request, extra_context=None):
        # Open the full dashboard (rich UI) when browsing the changelist;
        # still allow POST for bulk actions via the default implementation if needed.
        if request.method == 'GET':
            from django.shortcuts import redirect
            from django.urls import reverse

            if not self.has_view_permission(request):
                raise PermissionDenied
            return redirect(reverse('admin:members_churchmembership_dashboard') + '?' + request.GET.urlencode())
        return super().changelist_view(request, extra_context=extra_context)

    def dashboard_view(self, request):
        """The custom Church Membership dashboard (stats, directory, profile)."""
        if not self.has_view_permission(request):
            raise PermissionDenied

        context = dashboard.build_dashboard_context(request)
        context.update(self.admin_site.each_context(request))
        context.update({
            'title': 'Church Membership',
            'opts': self.model._meta,
            'app_label': self.model._meta.app_label,
            'can_add': self.has_add_permission(request),
            'can_change': self.has_change_permission(request),
        })
        return render(
            request,
            'admin/members/churchmembership/dashboard.html',
            context,
        )

    @admin.action(description='Export selected members to CSV')
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="church_members.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'Membership ID', 'First name', 'Last name', 'Email', 'Phone',
            'Marital status', 'Spouse', 'Children', 'Category', 'Status',
            'Baptism status', 'Joined church', 'Registered',
        ])
        for m in self.get_queryset(request).filter(pk__in=queryset.values('pk')):
            writer.writerow([
                obj_value(obj.membership_id), obj.user.first_name,
                obj.user.last_name, obj.user.email, obj.phone,
                obj.get_marital_status_display(),
                obj.spouse_name,
                '; '.join(
                    line.strip() for line in obj.children_names.splitlines()
                    if line.strip()
                ),
                obj.get_membership_category_display(),
                obj.get_status_display(),
                obj.get_baptism_status_display(),
                obj.date_joined_church or '', obj.created_at.date(),
            ])
        return response


def obj_value(value):
    return value or ''
