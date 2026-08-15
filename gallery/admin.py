from django.contrib import admin

from sboi.admin_utils import ImageThumbMixin

from .models import SliderImage


@admin.register(SliderImage)
class SliderImageAdmin(ImageThumbMixin, admin.ModelAdmin):
    thumb_field = 'image'
    list_display = ['thumb', 'title', 'placement', 'is_active', 'order']
    list_display_links = ['title']
    list_editable = ['placement', 'is_active', 'order']
    list_filter = ['placement', 'is_active']
