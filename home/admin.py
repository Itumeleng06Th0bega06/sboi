from django.contrib import admin

from sboi.admin_permissions import AreaPermissionMixin
from sboi.admin_utils import ImageThumbMixin

from .models import FeaturedSection, HomeStat, Subscriber, Testimony

admin.site.site_header = 'Shekinah Blaze Outreach International'
admin.site.site_title = 'Shekinah Blaze Admin'
admin.site.index_title = 'Church Website Administration'


@admin.register(HomeStat)
class HomeStatAdmin(AreaPermissionMixin, admin.ModelAdmin):
    area_permission = 'home.manage_home_content'
    list_display = ['value', 'label']


@admin.register(FeaturedSection)
class FeaturedSectionAdmin(
    AreaPermissionMixin, ImageThumbMixin, admin.ModelAdmin,
):
    area_permission = 'home.manage_home_content'
    thumb_field = 'image'
    list_display = ['thumb', 'title']
    list_display_links = ['title']


@admin.register(Testimony)
class TestimonyAdmin(AreaPermissionMixin, admin.ModelAdmin):
    area_permission = 'home.manage_testimonies'
    list_display = ['name', 'is_approved', 'submitted_at']
    list_filter = ['is_approved']
    actions = ['approve_testimonies']

    @admin.action(description='Approve selected testimonies')
    def approve_testimonies(self, request, queryset):
        queryset.update(is_approved=True)


@admin.register(Subscriber)
class SubscriberAdmin(AreaPermissionMixin, admin.ModelAdmin):
    area_permission = 'home.manage_subscribers'
    list_display = ['email', 'is_active', 'subscribed_at']
    list_filter = ['is_active']
    search_fields = ['email']
    actions = ['export_csv']

    @admin.action(description='Export selected subscribers (CSV)')
    def export_csv(self, request, queryset):
        import csv

        from django.http import HttpResponse

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="subscribers.csv"'
        writer = csv.writer(response)
        writer.writerow(['email', 'subscribed_at', 'is_active'])
        for sub in queryset:
            writer.writerow([sub.email, sub.subscribed_at, sub.is_active])
        return response
