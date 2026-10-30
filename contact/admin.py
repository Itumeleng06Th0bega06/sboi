from django.contrib import admin

from sboi.admin_permissions import AreaPermissionMixin

from .models import ContactInfo, ContactMessage


@admin.register(ContactInfo)
class ContactInfoAdmin(AreaPermissionMixin, admin.ModelAdmin):
    area_permission = 'contact.manage_contact_details'
    list_display = ['church_name', 'email', 'phone']


@admin.register(ContactMessage)
class ContactMessageAdmin(AreaPermissionMixin, admin.ModelAdmin):
    area_permission = 'contact.manage_contact_messages'
    list_display = ['name', 'subject', 'email', 'created_at', 'is_read']
    list_filter = ['is_read']
    list_editable = ['is_read']
    search_fields = ['name', 'email', 'subject', 'message']
    readonly_fields = ['name', 'email', 'phone', 'subject', 'message', 'created_at']
    date_hierarchy = 'created_at'
    actions = ['mark_read', 'mark_unread']

    @admin.action(description='Mark selected messages as read')
    def mark_read(self, request, queryset):
        queryset.update(is_read=True)

    @admin.action(description='Mark selected messages as unread')
    def mark_unread(self, request, queryset):
        queryset.update(is_read=False)
