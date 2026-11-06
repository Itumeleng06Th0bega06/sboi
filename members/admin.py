import csv
import re

from django import forms
from django.contrib import admin, messages
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils.html import format_html

from sboi.admin_permissions import AreaPermissionMixin

from . import dashboard, services
from .forms import ChurchMembershipFieldsMixin
from .models import (
    MEMBERSHIP_STATUS_CHOICES,
    MINISTRY_CHOICES,
    ChurchMembership,
    MembershipChangeRequest,
)
from .models_comms import CommsComment, CommsPost, CommsPostSave, CommsReport


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
            'whatsapp_consent',
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

    def save_related(self, request, form, formsets, change):
        """Notify the member when an administrator edits their record.

        A status transition already produces its own member notice from the
        shared membership signal. For every other real change we add one
        consolidated "details updated" row, after the model and its ministry
        rows have been saved, so the member portal and their bell agree.
        """
        super().save_related(request, form, formsets, change)
        if not change:
            return
        changed = set(form.changed_data) - {'status'}
        if not changed:
            return
        services.notify_member_admin_update(form.instance, changed)

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
            path(
                '<int:pk>/profile/',
                self.admin_site.admin_view(self.profile_view),
                name='members_churchmembership_profile',
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
        """The custom Church Membership dashboard (stats and directory)."""
        if not self.has_view_permission(request):
            raise PermissionDenied

        # Old links (bookmarks, earlier bell rows) used ?member=<pk> to open the
        # profile panel that this page no longer embeds. Forward them to the
        # dedicated profile page so those links keep working.
        member_id = request.GET.get('member')
        if member_id:
            try:
                member_id = int(member_id)
            except (TypeError, ValueError):
                member_id = None
            if member_id is not None:
                exists = ChurchMembership.objects.filter(pk=member_id).exists()
                if exists:
                    return redirect(
                        'admin:members_churchmembership_profile',
                        pk=member_id,
                    )

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

    def profile_view(self, request, pk):
        """A dedicated page for one member: details, status and messages.

        The dashboard no longer embeds a sliding profile panel. Opening a
        member takes the administrator here, where the profile is read top to
        bottom and the two actions live side by side: change/approve the
        membership status, or send a private comment to the member.
        """
        if not self.has_view_permission(request):
            raise PermissionDenied

        membership = get_object_or_404(
            ChurchMembership.objects
            .select_related('user')
            .prefetch_related('interests', 'ministries'),
            pk=pk,
        )
        can_change = self.has_change_permission(request, membership)
        pending_change = services.pending_change_for(membership)
        review_form = MembershipReviewForm()
        status_form = MembershipProfileStatusForm(
            initial={'status': membership.status},
        )
        message_form = MembershipProfileMessageForm()

        if request.method == 'POST':
            action = request.POST.get('action')
            if action in ('approve', 'reject'):
                if not can_change:
                    raise PermissionDenied
                review_form = MembershipReviewForm(request.POST)
                if review_form.is_valid():
                    note = review_form.cleaned_data.get('admin_note', '')
                    if pending_change is not None:
                        services.apply_membership_decision(
                            pending_change.pk,
                            request.user,
                            approve=action == 'approve',
                            note=note,
                        )
                    else:
                        services.set_membership_status(
                            membership,
                            request.user,
                            'active' if action == 'approve' else 'rejected',
                            note=note,
                        )
                    what = 'approved' if action == 'approve' else 'rejected'
                    self.message_user(
                        request,
                        f'{membership.full_name}\'s membership was {what}. '
                        'The member has been notified.',
                        messages.SUCCESS,
                    )
                    return redirect(
                        'admin:members_churchmembership_profile',
                        pk=membership.pk,
                    )
            elif action == 'status':
                if not can_change:
                    raise PermissionDenied
                status_form = MembershipProfileStatusForm(request.POST)
                if status_form.is_valid():
                    new_status = status_form.cleaned_data['status']
                    if new_status == membership.status:
                        self.message_user(
                            request,
                            'That is already the current status.',
                            messages.INFO,
                        )
                    else:
                        services.set_membership_status(
                            membership, request.user, new_status,
                        )
                        self.message_user(
                            request,
                            'Membership status updated and the member '
                            'notified.',
                            messages.SUCCESS,
                        )
                    return redirect(
                        'admin:members_churchmembership_profile',
                        pk=membership.pk,
                    )
            elif action == 'message':
                if not can_change:
                    raise PermissionDenied
                message_form = MembershipProfileMessageForm(request.POST)
                if message_form.is_valid():
                    _message, created = services.send_admin_message(
                        membership,
                        request.user,
                        message_form.cleaned_data['message'],
                    )
                    if created:
                        self.message_user(
                            request,
                            'Message sent to the member\'s private inbox.',
                            messages.SUCCESS,
                        )
                    else:
                        self.message_user(
                            request,
                            'That message was already sent a moment ago.',
                            messages.INFO,
                        )
                    return redirect(
                        'admin:members_churchmembership_profile',
                        pk=membership.pk,
                    )

        thread = list(services.member_thread(membership.user))[-6:]
        profile = dashboard.member_detail(membership)
        profile['date_joined'] = (
            membership.date_joined_church or membership.created_at
        )
        context = {
            **self.admin_site.each_context(request),
            'title': f'Membership profile — {membership.full_name}',
            'opts': self.model._meta,
            'app_label': self.model._meta.app_label,
            'membership': membership,
            'profile': profile,
            'pending_change': pending_change,
            'summary_lines': [
                line for line in (pending_change.summary or '').splitlines()
                if line
            ] if pending_change else [],
            'review_form': review_form,
            'status_form': status_form,
            'status_options': dashboard.status_options(),
            'message_form': message_form,
            'thread': thread,
            'can_change': can_change,
            'dashboard_url': reverse(
                'admin:members_churchmembership_dashboard',
            ),
        }
        return render(
            request,
            'admin/members/churchmembership/profile.html',
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


class MembershipReviewForm(forms.Form):
    admin_note = forms.CharField(
        label='Note (optional)',
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 2,
            'placeholder': 'Optional note',
        }),
    )


class MembershipProfileStatusForm(forms.Form):
    status = forms.ChoiceField(
        label='Membership status',
        choices=MEMBERSHIP_STATUS_CHOICES,
    )


class MembershipProfileMessageForm(forms.Form):
    message = forms.CharField(
        label='Comment',
        max_length=5000,
        widget=forms.Textarea(attrs={
            'class': 'cm-comment-input',
            'rows': 1,
            'placeholder': 'Write a comment…',
            'aria-label': 'Comment',
        }),
    )

    def clean_message(self):
        message = (self.cleaned_data.get('message') or '').strip()
        if not message:
            raise forms.ValidationError(
                'Please type a message before sending.',
            )
        return message


@admin.register(MembershipChangeRequest)
class MembershipChangeRequestAdmin(AreaPermissionMixin, admin.ModelAdmin):
    """The administrator-only review queue for membership changes.

    The actions call :func:`members.services.apply_membership_decision`, which
    is also used by the review page. That function is the *only* place that
    changes an approval status, and it always records the reviewer.
    """

    area_permission = 'members.manage_membership'
    list_display = [
        'membership', 'kind', 'status', 'submitted_by', 'created_at',
        'reviewed_by', 'whatsapp_status', 'review_link',
    ]
    list_filter = ['status', 'kind', 'whatsapp_status', 'created_at']
    search_fields = [
        'membership__membership_id', 'membership__user__first_name',
        'membership__user__last_name', 'membership__user__email',
        'submitted_by__username', 'summary',
    ]
    date_hierarchy = 'created_at'
    readonly_fields = [
        'membership', 'submitted_by', 'kind', 'status', 'summary',
        'reviewed_by', 'reviewed_at', 'created_at', 'updated_at',
        'whatsapp_status', 'whatsapp_error',
    ]
    fields = readonly_fields + ['admin_note']
    actions = ['approve_selected', 'reject_selected']

    def get_urls(self):
        custom = [
            path(
                '<int:pk>/review/',
                self.admin_site.admin_view(self.review_view),
                name='members_membershipchangerequest_review',
            ),
        ]
        return custom + super().get_urls()

    def has_add_permission(self, request):
        # The queue is produced by member submissions, never hand-created.
        return False

    def has_delete_permission(self, request, obj=None):
        # Keep the review history as an audit trail.
        return False

    @admin.display(description='Review')
    def review_link(self, obj):
        if obj.status != MembershipChangeRequest.STATUS_PENDING:
            return 'Reviewed'
        url = reverse(
            'admin:members_membershipchangerequest_review', args=[obj.pk],
        )
        return format_html('<a class="button" href="{}">Review</a>', url)

    def review_view(self, request, pk):
        if not self.has_change_permission(request):
            raise PermissionDenied
        change = get_object_or_404(
            MembershipChangeRequest.objects.select_related(
                'membership', 'membership__user', 'submitted_by',
                'reviewed_by',
            ),
            pk=pk,
        )
        form = MembershipReviewForm()
        if request.method == 'POST':
            form = MembershipReviewForm(request.POST)
            if form.is_valid():
                decision = request.POST.get('decision')
                if decision not in ('approve', 'reject'):
                    messages.error(request, 'Choose approve or reject.')
                else:
                    change, notification, _created = (
                        services.apply_membership_decision(
                            change.pk,
                            request.user,
                            approve=decision == 'approve',
                            note=form.cleaned_data.get('admin_note', ''),
                        )
                    )
                    if notification is not None:
                        what = 'approved' if decision == 'approve' else 'rejected'
                        self.message_user(
                            request,
                            f'{change.membership.full_name}\'s request was '
                            f'{what}. The member has been notified in-app.',
                            messages.SUCCESS,
                        )
                    else:
                        self.message_user(
                            request,
                            'That request was already reviewed.',
                            messages.WARNING,
                        )
                    return redirect(
                        'admin:members_membershipchangerequest_changelist',
                    )

        context = {
            **self.admin_site.each_context(request),
            'title': 'Review membership request',
            'opts': self.model._meta,
            'original': change,
            'change': change,
            'membership': change.membership,
            'summary_lines': [
                line for line in (change.summary or '').splitlines() if line
            ],
            'form': form,
        }
        return render(
            request,
            'admin/members/membershipchangerequest/review.html',
            context,
        )

    @admin.action(description='Approve selected membership requests')
    def approve_selected(self, request, queryset):
        count = 0
        for change in queryset.filter(
            status=MembershipChangeRequest.STATUS_PENDING,
        ).select_related('membership__user'):
            services.apply_membership_decision(
                change.pk, request.user, approve=True,
            )
            count += 1
        self.message_user(
            request, f'{count} request(s) approved and members notified.',
            messages.SUCCESS,
        )

    @admin.action(description='Reject selected membership requests')
    def reject_selected(self, request, queryset):
        count = 0
        for change in queryset.filter(
            status=MembershipChangeRequest.STATUS_PENDING,
        ).select_related('membership__user'):
            services.apply_membership_decision(
                change.pk, request.user, approve=False,
            )
            count += 1
        self.message_user(
            request, f'{count} request(s) rejected and members notified.',
            messages.SUCCESS,
        )


@admin.register(CommsReport)
class CommsReportAdmin(AreaPermissionMixin, admin.ModelAdmin):
    """Member moderation reports, reviewable without the extra chat workspace."""

    area_permission = 'communications.manage_communications'
    list_display = [
        'id', 'reason', 'post', 'comment', 'reporter', 'status',
        'created_at', 'reviewed_by',
    ]
    list_filter = ['status', 'reason', 'created_at']
    search_fields = [
        'reporter__username', 'note', 'post__body', 'comment__body',
    ]
    date_hierarchy = 'created_at'
    raw_id_fields = ['post', 'comment', 'reporter', 'reviewed_by']
    readonly_fields = ['created_at']


@admin.register(CommsPostSave)
class CommsPostSaveAdmin(AreaPermissionMixin, admin.ModelAdmin):
    """Read-only bookmarks. They are private and never notify anybody."""

    area_permission = 'communications.manage_communications'
    list_display = ['id', 'post', 'user', 'created_at']
    list_filter = ['created_at']
    search_fields = ['user__username']
    raw_id_fields = ['post', 'user']
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
