from django.db import models

from sboi.fields import OptimizedImageField


class SliderImage(models.Model):
    PLACEMENT_CHOICES = [
        ('home', 'Home'),
        ('gallery', 'Gallery'),
        ('both', 'Both'),
    ]

    title = models.CharField(max_length=200, blank=True)
    caption = models.CharField(max_length=300, blank=True)
    image = OptimizedImageField(upload_to='slider/', blank=True, help_text='Recommended size: 1920x1080 (16:9).')
    placement = models.CharField(max_length=10, choices=PLACEMENT_CHOICES, blank=True, default='home')
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(blank=True, default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.title or f'Slide #{self.pk}'
