from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import get_valid_filename

from sboi.storage import PrivateMediaStorage

# Member-to-administration attachments are limited to the document and image
# types a church office legitimately receives. Everything is stored outside
# MEDIA_ROOT and streamed through a permission-checked view.
ALLOWED_MESSAGE_ATTACHMENT_EXTENSIONS = (
    'pdf', 'doc', 'docx', 'txt', 'rtf', 'odt',
    'jpg', 'jpeg', 'png', 'gif', 'webp',
)

MAX_MESSAGE_ATTACHMENT_SIZE = 10 * 1024 * 1024  # 10 MB

private_message_storage = PrivateMediaStorage()


def validate_message_attachment_size(file):
    if file is not None and getattr(file, 'size', 0) > MAX_MESSAGE_ATTACHMENT_SIZE:
        raise ValidationError('Attachments must be 10 MB or smaller.')


def message_attachment_path(instance, filename):
    """Store private attachments under their owner, never by public URL."""
    suffix = Path(filename).suffix.lower()
    owner = instance.user_id or 'public'
    original = get_valid_filename(Path(filename).name) or f'attachment{suffix}'
    return (
        f'contact_messages/{owner}/{timezone.now():%Y/%m}/'
        f'{uuid4().hex}-{original}'
    )


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
        permissions = [
            ('manage_contact_details', 'Contact page: manage details'),
        ]

    def __str__(self):
        return self.church_name


class ContactMessage(models.Model):
    """A public contact message or a private member ↔ administration message.

    One table serves both flows. Anonymous messages created by the public
    contact form have no ``user``. A signed-in member's messages carry their
    ``user`` and form one continuous private conversation with the church
    administration; administrator replies are rows in the same conversation
    with ``is_from_admin=True``. Reusing this model avoids a second messaging
    system while keeping the public contact form untouched.
    """

    name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=60, blank=True)
    subject = models.CharField(max_length=200, blank=True)
    message = models.TextField()
    # --- Private member conversation -------------------------------------
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='contact_messages',
        help_text='The member whose private conversation this belongs to.',
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='sent_contact_messages',
        help_text='The account that actually wrote this message.',
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='replies',
    )
    is_from_admin = models.BooleanField(default=False)
    # ``is_read`` means "read by an administrator" (the existing contact form
    # meaning). ``read_by_member`` only applies to administrator replies.
    read_by_member = models.BooleanField(default=True)
    attachment = models.FileField(
        upload_to=message_attachment_path,
        storage=private_message_storage,
        blank=True,
        validators=[
            FileExtensionValidator(ALLOWED_MESSAGE_ATTACHMENT_EXTENSIONS),
            validate_message_attachment_size,
        ],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    # WhatsApp presence cache (checked on first admin thread open)
    has_whatsapp = models.BooleanField(default=False)
    whatsapp_checked = models.BooleanField(default=False)
    whatsapp_checked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        permissions = [
            ('manage_contact_messages', 'Contact page: manage messages'),
        ]
        indexes = [
            models.Index(fields=['user', 'created_at']),
        ]

    def __str__(self):
        sender = self.sender_name
        subject = self.subject or (self.message or '')[:40]
        return f'{sender}: {subject}'

    @property
    def sender_name(self):
        if self.is_from_admin and self.sender_id:
            return self.sender.get_full_name() or self.sender.get_username()
        return self.name or (self.user.get_full_name() if self.user_id else 'Member')

    @property
    def is_member_message(self):
        return self.user_id is not None and not self.is_from_admin

    @property
    def attachment_name(self):
        if not self.attachment:
            return ''
        name = Path(self.attachment.name).name
        # New uploads are stored as ``<uuid-hex>-<original name>`` so the
        # download keeps a friendly filename while remaining unique on disk.
        prefix, separator, original = name.partition('-')
        if (
            separator and len(prefix) == 32
            and all(ch in '0123456789abcdef' for ch in prefix)
        ):
            return original
        return name

    @property
    def attachment_url(self):
        if not self.attachment:
            return ''
        return reverse('contact:attachment', args=[self.pk])

    def check_whatsapp(self):
        """Check if the message's phone number has WhatsApp.
        Returns True/False and caches the result."""
        import urllib.request
        from django.conf import settings as _settings
        from django.utils import timezone

        phone = self.phone.strip() if self.phone else ''
        if not phone:
            self.has_whatsapp = False
            self.whatsapp_checked = True
            self.whatsapp_checked_at = timezone.now()
            self.save(update_fields=['has_whatsapp', 'whatsapp_checked', 'whatsapp_checked_at'])
            return False

        api_url = getattr(_settings, 'WHATSAPP_API_URL', '').strip()
        api_token = getattr(_settings, 'WHATSAPP_API_TOKEN', '').strip()
        if not api_url or not api_token:
            self.whatsapp_checked = False
            self.save(update_fields=['whatsapp_checked'])
            return False

        digits = ''.join(ch for ch in phone if ch.isdigit())
        if len(digits) < 7:
            self.has_whatsapp = False
            self.whatsapp_checked = True
            self.whatsapp_checked_at = timezone.now()
            self.save(update_fields=['has_whatsapp', 'whatsapp_checked', 'whatsapp_checked_at'])
            return False

        try:
            # WhatsApp Business API contact check
            url = f'{api_url.rstrip("/")}/contacts'
            payload = {'contacts': [digits]}
            request = urllib.request.Request(
                url,
                data=__import__('json').dumps(payload).encode('utf-8'),
                headers={
                    'Authorization': f'Bearer {api_token}',
                    'Content-Type': 'application/json',
                },
                method='POST',
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                import json
                data = json.loads(response.read().decode('utf-8'))
                contacts = data.get('contacts', [])
                status = 'valid' if contacts and contacts[0].get('status') == 'valid' else 'invalid'
                result = status == 'valid'
        except Exception:
            result = False

        self.has_whatsapp = result
        self.whatsapp_checked = True
        self.whatsapp_checked_at = timezone.now()
        self.save(update_fields=['has_whatsapp', 'whatsapp_checked', 'whatsapp_checked_at'])
        return result
