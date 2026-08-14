from datetime import timedelta

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.utils import timezone

from .models import (
    Announcement,
    Devotion,
    Event,
    EventRsvp,
    MemberProfile,
    PdfMaterial,
    Sermon,
)


class EventRsvpInline(admin.TabularInline):
    model = EventRsvp
    extra = 0
    readonly_fields = ['name', 'email', 'phone', 'guests', 'created_at']


class MemberProfileInline(admin.StackedInline):
    model = MemberProfile
    can_delete = False
    fields = ['status', 'suspended_until', 'blocked_reason', 'created_at']
    readonly_fields = ['created_at']


class MemberUserAdmin(UserAdmin):
    inlines = [MemberProfileInline]
    list_display = ['username', 'email', 'first_name', 'last_name', 'is_staff', 'is_active', 'member_status']
    list_filter = ['is_active', 'is_staff', 'member_profile__status']

    @admin.display(description='Member status')
    def member_status(self, obj):
        profile = getattr(obj, 'member_profile', None)
        return profile.status if profile else '—'


admin.site.unregister(User)
admin.site.register(User, MemberUserAdmin)


@admin.register(MemberProfile)
class MemberProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'status', 'suspended_until', 'recorded_at']
    list_filter = ['status']
    list_editable = ['status']
    search_fields = ['user__username', 'user__email', 'user__first_name', 'user__last_name']
    actions = ['suspend_7_days', 'suspend_30_days', 'block_permanently', 'reactivate']
    fields = ['user', 'status', 'suspended_until', 'blocked_reason', 'created_at']
    readonly_fields = ['user', 'created_at']

    @admin.display(description='Registered')
    def recorded_at(self, obj):
        return obj.created_at.date()

    def _suspend(self, queryset, days):
        queryset.update(
            status=MemberProfile.STATUS_SUSPENDED,
            suspended_until=timezone.localdate() + timedelta(days=days),
        )

    @admin.action(description='Suspend selected members for 7 days')
    def suspend_7_days(self, request, queryset):
        self._suspend(queryset, 7)

    @admin.action(description='Suspend selected members for 30 days')
    def suspend_30_days(self, request, queryset):
        self._suspend(queryset, 30)

    @admin.action(description='Block selected members permanently')
    def block_permanently(self, request, queryset):
        queryset.update(
            status=MemberProfile.STATUS_BLOCKED,
            suspended_until=None,
        )

    @admin.action(description='Reactivate selected members')
    def reactivate(self, request, queryset):
        queryset.update(
            status=MemberProfile.STATUS_ACTIVE,
            suspended_until=None,
            blocked_reason='',
        )


@admin.register(Devotion)
class DevotionAdmin(admin.ModelAdmin):
    list_display = ['title', 'date', 'author', 'is_published']
    list_filter = ['is_published']
    search_fields = ['title', 'message']
    list_editable = ['is_published']
    date_hierarchy = 'date'


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ['title', 'date', 'is_published']
    list_filter = ['is_published']
    search_fields = ['title', 'body']
    list_editable = ['is_published']
    date_hierarchy = 'date'


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ['title', 'date', 'is_published']
    list_filter = ['is_published']
    search_fields = ['title', 'description']
    list_editable = ['is_published']
    date_hierarchy = 'date'
    inlines = [EventRsvpInline]


@admin.register(EventRsvp)
class EventRsvpAdmin(admin.ModelAdmin):
    list_display = ['name', 'event', 'email', 'phone', 'guests', 'created_at']
    list_filter = ['event']
    search_fields = ['name', 'email']
    date_hierarchy = 'created_at'


@admin.register(Sermon)
class SermonAdmin(admin.ModelAdmin):
    list_display = ['title', 'speaker', 'date', 'series', 'has_video', 'is_published']
    list_filter = ['is_published', 'series']
    search_fields = ['title', 'speaker', 'scripture']
    list_editable = ['is_published']
    date_hierarchy = 'date'

    @admin.display(boolean=True, description='Video')
    def has_video(self, obj):
        return bool(obj.video_url)


@admin.register(PdfMaterial)
class PdfMaterialAdmin(admin.ModelAdmin):
    list_display = ['title', 'is_published', 'order']
    list_editable = ['is_published', 'order']