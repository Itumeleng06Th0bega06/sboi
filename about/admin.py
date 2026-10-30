from django.contrib import admin

from sboi.admin_permissions import AreaPermissionMixin
from sboi.admin_utils import ImageThumbMixin

from .models import (
    ChurchProfile,
    CoreValue,
    Leader,
    MissionAction,
    MissionComponent,
    PathwayStep,
    VisionPillar,
)


@admin.register(ChurchProfile)
class ChurchProfileAdmin(AreaPermissionMixin, ImageThumbMixin, admin.ModelAdmin):
    area_permission = 'about.manage_about'
    thumb_field = 'story_image'
    list_display = ['thumb', 'church_name', 'tagline', 'location']
    list_display_links = ['church_name']
    fieldsets = (
        (None, {'fields': ['church_name', 'tagline', 'location', 'founded_year']}),
        ('Founder', {'fields': ['founder_name', 'founder_role', 'founder_byline', 'founder_scripture', 'founder_message', 'founder_signature', 'founder_tagline']}),
        ('Our Story', {'fields': ['story', 'story_subtitle', 'story_image']}),
        (
            'Vision',
            {
                'fields': [
                    'vision_title',
                    'vision',
                    'vision_intro',
                    'vision_components_intro',
                    'vision_scripture',
                    'vision_practice',
                    'vision_future',
                    'vision_declaration',
                    'vision_key_scripture',
                ]
            },
        ),
        (
            'Mission',
            {
                'fields': [
                    'mission_title',
                    'mission',
                    'mission_intro',
                    'mission_components_intro',
                    'mission_scripture',
                    'mission_multiplication',
                    'mission_commitment',
                    'mission_declaration',
                    'mission_key_scripture',
                ]
            },
        ),
        (
            'Pathway & Mission in Action',
            {
                'fields': [
                    'pathway_intro',
                    'pathway_closing',
                    'mission_in_action_intro',
                    'mission_in_action_closing',
                ]
            },
        ),
        (
            'Culture & Values',
            {
                'fields': ['culture_statement', 'values_intro', 'values_declaration']
            },
        ),
    )


@admin.register(VisionPillar)
class VisionPillarAdmin(AreaPermissionMixin, admin.ModelAdmin):
    area_permission = 'about.manage_about'
    list_display = ['title']
    fields = ['title', 'subtitle', 'body']


@admin.register(MissionComponent)
class MissionComponentAdmin(AreaPermissionMixin, admin.ModelAdmin):
    area_permission = 'about.manage_about'
    list_display = ['title']
    fields = ['title', 'subtitle', 'body']


@admin.register(PathwayStep)
class PathwayStepAdmin(AreaPermissionMixin, admin.ModelAdmin):
    area_permission = 'about.manage_about'
    list_display = ['step', 'title']
    list_display_links = ['step', 'title']


@admin.register(MissionAction)
class MissionActionAdmin(AreaPermissionMixin, admin.ModelAdmin):
    area_permission = 'about.manage_about'
    list_display = ['title']


@admin.register(CoreValue)
class CoreValueAdmin(AreaPermissionMixin, admin.ModelAdmin):
    area_permission = 'about.manage_values'
    list_display = ['title', 'scripture']
    fields = ['title', 'scripture', 'what_we_believe', 'what_this_means', 'our_commitment']


@admin.register(Leader)
class LeaderAdmin(AreaPermissionMixin, ImageThumbMixin, admin.ModelAdmin):
    area_permission = 'about.manage_about'
    thumb_field = 'photo'
    list_display = ['thumb', 'name', 'role']
    list_display_links = ['name']
