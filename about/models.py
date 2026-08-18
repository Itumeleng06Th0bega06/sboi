from django.db import models

from sboi.fields import OptimizedImageField


class ChurchProfile(models.Model):
    church_name = models.CharField(max_length=200, default='Shekinah Blaze Outreach International')
    tagline = models.CharField(max_length=200, blank=True)
    location = models.CharField(max_length=300, blank=True)

    founder_name = models.CharField(max_length=200, blank=True)
    founder_role = models.CharField(max_length=200, blank=True)
    founder_byline = models.TextField(blank=True)
    founder_scripture = models.CharField(max_length=300, blank=True)
    founder_message = models.TextField(blank=True)
    founder_signature = models.TextField(blank=True)
    founder_tagline = models.CharField(max_length=300, blank=True)

    story = models.TextField(blank=True)
    story_subtitle = models.TextField(blank=True)
    story_image = OptimizedImageField(upload_to='about/', blank=True)

    vision_title = models.CharField(max_length=200, default='Our Vision')
    vision = models.TextField(blank=True)
    vision_intro = models.TextField(blank=True)
    vision_components_intro = models.TextField(blank=True)
    vision_scripture = models.CharField(max_length=300, blank=True)
    vision_practice = models.TextField(blank=True)
    vision_future = models.TextField(blank=True)
    vision_declaration = models.TextField(blank=True)
    vision_key_scripture = models.CharField(max_length=500, blank=True)

    mission_title = models.CharField(max_length=200, default='Our Mission')
    mission = models.TextField(blank=True)
    mission_intro = models.TextField(blank=True)
    mission_components_intro = models.TextField(blank=True)
    mission_scripture = models.CharField(max_length=300, blank=True)
    mission_multiplication = models.TextField(blank=True)
    mission_commitment = models.TextField(blank=True)
    mission_declaration = models.TextField(blank=True)
    mission_key_scripture = models.CharField(max_length=500, blank=True)

    pathway_intro = models.TextField(blank=True)
    pathway_closing = models.TextField(blank=True)
    mission_in_action_intro = models.TextField(blank=True)
    mission_in_action_closing = models.TextField(blank=True)

    values_intro = models.TextField(blank=True)

    culture_statement = models.TextField(blank=True)
    values_declaration = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Church Profile'
        verbose_name_plural = 'Church Profile'

    def __str__(self):
        return self.church_name


class VisionPillar(models.Model):
    title = models.CharField(max_length=200, blank=True)
    subtitle = models.CharField(max_length=200, blank=True)
    body = models.TextField(blank=True)
    order = models.PositiveIntegerField(blank=True, default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.title or '(Untitled pillar)'


class MissionComponent(models.Model):
    title = models.CharField(max_length=200, blank=True)
    subtitle = models.CharField(max_length=200, blank=True)
    body = models.TextField(blank=True)
    order = models.PositiveIntegerField(blank=True, default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.title or '(Untitled component)'


class PathwayStep(models.Model):
    step = models.PositiveIntegerField(blank=True, default=1)
    title = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(blank=True, default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f'{self.step}. {self.title or "Untitled"}'


class MissionAction(models.Model):
    title = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(blank=True, default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.title or '(Untitled action)'


class CoreValue(models.Model):
    title = models.CharField(max_length=120, blank=True)
    scripture = models.CharField(max_length=300, blank=True)
    what_we_believe = models.TextField(blank=True)
    what_this_means = models.TextField(blank=True)
    our_commitment = models.TextField(blank=True)
    order = models.PositiveIntegerField(blank=True, default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.title or '(Untitled value)'


class Leader(models.Model):
    name = models.CharField(max_length=200, blank=True)
    role = models.CharField(max_length=200, blank=True)
    photo = OptimizedImageField(upload_to='about/', blank=True)
    bio = models.TextField(blank=True)
    order = models.PositiveIntegerField(blank=True, default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.name or '(Untitled leader)'
