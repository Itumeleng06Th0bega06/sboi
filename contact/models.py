from django.db import models


class ContactInfo(models.Model):
    church_name = models.CharField(max_length=200, default='Shekinah Blaze Outreach International')
    phone = models.CharField(max_length=60, blank=True)
    whatsapp = models.CharField(max_length=60, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=300, blank=True)
    service_times = models.TextField(blank=True)
    facebook = models.URLField(blank=True)
    twitter = models.URLField(blank=True)
    instagram = models.URLField(blank=True)
    youtube = models.URLField(blank=True)

    class Meta:
        verbose_name = 'Contact Info'
        verbose_name_plural = 'Contact Info'

    def __str__(self):
        return self.church_name


class ContactMessage(models.Model):
    name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=60, blank=True)
    subject = models.CharField(max_length=200, blank=True)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name}: {self.subject}'
