from django.db import models


class SliderImage(models.Model):
    PLACEMENT_CHOICES = [
        ('home', 'Home'),
        ('gallery', 'Gallery'),
        ('both', 'Both'),
    ]

    title = models.CharField(max_length=200, blank=True)
    caption = models.CharField(max_length=300, blank=True)
    image = models.ImageField(upload_to='slider/')
    placement = models.CharField(max_length=10, choices=PLACEMENT_CHOICES, default='home')
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.title or str(self.image)


class GalleryImage(models.Model):
    title = models.CharField(max_length=200, blank=True)
    caption = models.CharField(max_length=300, blank=True)
    image = models.ImageField(upload_to='gallery/')
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.title or str(self.image)
