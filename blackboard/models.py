from django.conf import settings
from django.db import models
from django.utils import timezone

from sboi.fields import OptimizedImageField


class Devotion(models.Model):
    title = models.CharField(max_length=200, blank=True)
    date = models.DateField(default=timezone.localdate)
    scripture = models.CharField(max_length=300, blank=True)
    author = models.CharField(max_length=120, blank=True)
    image = OptimizedImageField(upload_to='devotions/', blank=True)
    message = models.TextField(blank=True)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return self.title or f'Devotion ({self.date})'


class Announcement(models.Model):
    title = models.CharField(max_length=200, blank=True)
    date = models.DateField(default=timezone.localdate)
    body = models.TextField(blank=True)
    image = OptimizedImageField(upload_to='announcements/', blank=True)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return self.title or f'Announcement ({self.date})'


class Event(models.Model):
    title = models.CharField(max_length=200, blank=True)
    date = models.DateField(default=timezone.localdate)
    description = models.TextField(blank=True)
    poster = OptimizedImageField(upload_to='events/', blank=True)
    link = models.URLField(blank=True)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ['-date', '-id']

    def __str__(self):
        return self.title or f'Event ({self.date})'

    @property
    def is_upcoming(self):
        return self.date >= timezone.localdate()


class EventRsvp(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='rsvps')
    name = models.CharField(max_length=120)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=60, blank=True)
    guests = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} - {self.event.title}'


class Sermon(models.Model):
    title = models.CharField(max_length=200, blank=True)
    speaker = models.CharField(max_length=120, blank=True)
    date = models.DateField(blank=True, null=True)
    scripture = models.CharField(max_length=300, blank=True)
    series = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    video_url = models.URLField(blank=True)
    pdf = models.FileField(upload_to='sermons/', blank=True)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ['-date', '-id']

    @property
    def video_id(self):
        url = (self.video_url or '').strip()
        if not url:
            return ''
        if 'youtu.be/' in url:
            return url.split('youtu.be/')[-1].split('?')[0].split('&')[0]
        if 'youtube.com/watch' in url or 'youtube.com/shorts' in url:
            from urllib.parse import parse_qs, urlparse

            qs = parse_qs(urlparse(url).query)
            vid = qs.get('v', [''])[0]
            if vid:
                return vid
            parts = [p for p in url.split('/') if p]
            for part in parts:
                if len(part) == 11 and part != 'watch':
                    return part
        return ''

    @property
    def thumbnail_url(self):
        vid = self.video_id
        if not vid:
            return ''
        return f'https://img.youtube.com/vi/{vid}/hqdefault.jpg'

    def __str__(self):
        return self.title or f'Sermon ({self.date or "no date"})'


class PdfMaterial(models.Model):
    title = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to='materials/', blank=True)
    is_published = models.BooleanField(default=True)
    order = models.PositiveIntegerField(blank=True, default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.title or f'PDF Material #{self.pk}'


class MemberProfile(models.Model):
    STATUS_ACTIVE = 'active'
    STATUS_SUSPENDED = 'suspended'
    STATUS_BLOCKED = 'blocked'
    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_SUSPENDED, 'Suspended'),
        (STATUS_BLOCKED, 'Blocked'),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='member_profile')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    suspended_until = models.DateField(blank=True, null=True)
    blocked_reason = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.username

    def access_block(self):
        """Return an explanation message if this member may not use the Blackboard, else None."""
        if self.status == self.STATUS_BLOCKED:
            return 'Your account has been blocked. Please contact the church office for assistance.'
        if self.status == self.STATUS_SUSPENDED:
            until = self.suspended_until
            if until and until >= timezone.localdate():
                return (
                    f'Your account has been temporarily suspended until {until.strftime("%-d %B %Y")}. '
                    'Please contact the church office if you believe this is a mistake.'
                )
        return None
