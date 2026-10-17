import csv
import re

from django import forms
from django.contrib import admin, messages
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import path

from . import dashboard
from .models import (
    MINISTRY_CHOICES,
    ChurchMembership,
    MembershipInterest,
    MembershipMinistry,
)


class MembershipInterestInline(admin.TabularInline):
    model = MembershipInterest
    extra = 0


class MembershipMinistryInline(admin.TabularInline):
    model = MembershipMinistry
    extra = 0


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


class ChurchMembershipAdminForm(forms.ModelForm):
    """Admin form for :class:`ChurchMembership`.

    Instead of asking an administrator to pick a ``User`` from a search box,
    the linked account is managed inline: first/last name and email live in
    the Personal details tab, and username + password live in the Account tab
    (passwords are only requested when creating a member).
    """

    first_name = forms.CharField(
        required=False, max_length=150, label='First name',
        widget=forms.TextInput(attrs={'placeholder': 'e.g. Grace'}),
    )
    last_name = forms.CharField(
        required=False, max_length=150, label='Last name',
        widget=forms.TextInput(attrs={'placeholder': 'e.g. Mokoena'}),
    )
    email = forms.EmailField(
        required=False, label='Email address',
        widget=forms.EmailInput(attrs={'placeholder': 'you@example.com'}),
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
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'baptism_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'date_joined_church': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The raw account picker has nothing to select on a fresh install, and
        # gender is only offered on the public registration forms.
        self.fields.pop('user', None)
        self.fields.pop('gender', None)

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
        obj = super().save(commit=False)
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
        obj.user = user

        if commit:
            obj.save()
            self.save_m2m()
        else:
            self.save_m2m = lambda: None
        return obj


@admin.register(ChurchMembership)
class ChurchMembershipAdmin(admin.ModelAdmin):
    list_display = [
        'membership_id', 'full_name', 'email', 'phone',
        'membership_category', 'status', 'baptism_status', 'created_at',
    ]
    list_filter = [
        'membership_category', 'status', 'baptism_status',
        MinistryFilter, 'created_at',
    ]
    search_fields = [
        'membership_id', 'user__username', 'user__first_name',
        'user__last_name', 'user__email', 'phone', 'alt_phone',
    ]
    date_hierarchy = 'created_at'
    list_per_page = 25
    inlines = [MembershipInterestInline, MembershipMinistryInline]
    form = ChurchMembershipAdminForm
    readonly_fields = ['membership_id', 'created_at', 'updated_at']
    actions = ['export_csv']
    fieldsets = [
        ('Account', {'fields': ['username', 'password1', 'password2']}),
        ('Personal details', {'fields': [
            'first_name', 'last_name', 'email', 'phone', 'alt_phone',
            'date_of_birth', 'address', 'city', 'province',
            'emergency_contact_name', 'emergency_contact_phone',
        ]}),
        ('Church membership', {'fields': [
            'membership_category', 'status', 'date_joined_church',
            'baptism_status', 'baptism_date', 'previous_church',
            'transferring_from_church', 'preferred_language',
            'campus_branch',
        ]}),
        ('Interests and spiritual growth', {'fields': [
            'interests_other', 'spiritual_growth_goals',
            'wants_bible_study', 'wants_contact',
        ]}),
        ('Current church activities', {'fields': [
            'currently_involved', 'current_activities', 'small_group_name',
            'volunteers_currently', 'volunteer_details', 'wants_to_volunteer',
        ]}),
        ('Skills and availability', {'fields': [
            'skills', 'talents', 'service_areas', 'preferred_times',
            'additional_info',
        ]}),
        ('Additional information', {'fields': ['notes']}),
        ('Record', {'fields': ['membership_id', 'created_at', 'updated_at']}),
    ]

    def get_fieldsets(self, request, obj=None):
        # Passwords are only requested when creating a member; on the change
        # view the Account tab shows just the username.
        if obj is None:
            return self.fieldsets
        fieldsets = []
        for title, opts in self.fieldsets:
            if title == 'Account':
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

    def has_export_permission(self, request):
        return request.user.has_perm('members.export_churchmembership')

    @admin.action(description='Export selected members to CSV')
    def export_csv(self, request, queryset):
        if not (request.user.is_superuser or self.has_export_permission(request)):
            self.message_user(
                request, 'You do not have permission to export membership data.',
                level=30,
            )
            return None
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="church_members.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'Membership ID', 'First name', 'Last name', 'Email', 'Phone',
            'Category', 'Status', 'Baptism status', 'Joined church', 'Registered',
        ])
        for m in self.get_queryset(request).filter(pk__in=queryset.values('pk')):
            writer.writerow([
                obj_value(obj.membership_id), obj.user.first_name,
                obj.user.last_name, obj.user.email, obj.phone,
                obj.get_membership_category_display(),
                obj.get_status_display(),
                obj.get_baptism_status_display(),
                obj.date_joined_church or '', obj.created_at.date(),
            ])
        return response


def obj_value(value):
    return value or ''
