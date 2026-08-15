from django.contrib import admin

from sboi.admin_utils import ImageThumbMixin

from .models import FeaturedSection, HomeStat, Subscriber, Testimony

admin.site.site_header = 'Shekinah Blaze Outreach International'
admin.site.site_title = 'Shekinah Blaze Admin'
admin.site.index_title = 'Church Website Administration'


@admin.register(HomeStat)
class HomeStatAdmin(admin.ModelAdmin):
    list_display = ['value', 'label', 'order']
    list_editable = ['order']


@admin.register(FeaturedSection)
class FeaturedSectionAdmin(ImageThumbMixin, admin.ModelAdmin):
    thumb_field = 'image'
    list_display = ['thumb', 'title', 'subtitle', 'order']
    list_display_links = ['title']
    list_editable = ['order']


@admin.register(Testimony)
class TestimonyAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_approved', 'submitted_at']
    list_filter = ['is_approved']
    actions = ['approve_testimonies']

    @admin.action(description='Approve selected testimonies')
    def approve_testimonies(self, request, queryset):
        queryset.update(is_approved=True)


@admin.register(Subscriber)
class SubscriberAdmin(admin.ModelAdmin):
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
