from django.db import models

from sboi.fields import OptimizedImageField


class HomeStat(models.Model):
    value = models.CharField(max_length=50, blank=True)
    label = models.CharField(max_length=120, blank=True)
    order = models.PositiveIntegerField(blank=True, default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f'{self.value or ""} {self.label or ""}'.strip() or '(Untitled stat)'


class FeaturedSection(models.Model):
    title = models.CharField(max_length=200, blank=True)
    subtitle = models.CharField(max_length=200, blank=True)
    body = models.TextField(blank=True)
    image = OptimizedImageField(upload_to='home/sections/', blank=True)
    button_text = models.CharField(max_length=60, blank=True)
    button_url = models.CharField(max_length=200, blank=True)
    order = models.PositiveIntegerField(blank=True, default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.title or '(Untitled section)'


class Testimony(models.Model):
    name = models.CharField(max_length=120)
    message = models.TextField()
    submitted_at = models.DateTimeField(auto_now_add=True)
    is_approved = models.BooleanField(default=False)

    class Meta:
        ordering = ['-submitted_at']

    def __str__(self):
        return self.name


class Subscriber(models.Model):
    email = models.EmailField(unique=True)
    subscribed_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Newsletter Subscriber'
        verbose_name_plural = 'Newsletter Subscribers'
        ordering = ['-subscribed_at']

    def __str__(self):
        return self.email
