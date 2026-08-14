from django.contrib import admin

from .models import GalleryImage, SliderImage


@admin.register(SliderImage)
class SliderImageAdmin(admin.ModelAdmin):
    list_display = ['title', 'placement', 'is_active', 'order']
    list_editable = ['placement', 'is_active', 'order']
    list_filter = ['placement', 'is_active']


@admin.register(GalleryImage)
class GalleryImageAdmin(admin.ModelAdmin):
    list_display = ['title', 'is_active', 'order']
    list_editable = ['is_active', 'order']
