from django.contrib import admin

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
class ChurchProfileAdmin(admin.ModelAdmin):
    list_display = ['church_name', 'tagline', 'location']
    fieldsets = (
        (None, {'fields': ['church_name', 'tagline', 'location']}),
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
class VisionPillarAdmin(admin.ModelAdmin):
    list_display = ['title', 'subtitle', 'order']
    list_editable = ['order']
    fields = ['title', 'subtitle', 'body', 'order']


@admin.register(MissionComponent)
class MissionComponentAdmin(admin.ModelAdmin):
    list_display = ['title', 'subtitle', 'order']
    list_editable = ['order']
    fields = ['title', 'subtitle', 'body', 'order']


@admin.register(PathwayStep)
class PathwayStepAdmin(admin.ModelAdmin):
    list_display = ['step', 'title', 'order']
    list_editable = ['order']
    list_display_links = ['step', 'title']


@admin.register(MissionAction)
class MissionActionAdmin(admin.ModelAdmin):
    list_display = ['title', 'order']
    list_editable = ['order']


@admin.register(CoreValue)
class CoreValueAdmin(admin.ModelAdmin):
    list_display = ['title', 'scripture', 'order']
    list_editable = ['order']
    fields = ['title', 'scripture', 'what_we_believe', 'what_this_means', 'our_commitment', 'order']


@admin.register(Leader)
class LeaderAdmin(admin.ModelAdmin):
    list_display = ['name', 'role', 'order']
    list_editable = ['order']