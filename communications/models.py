"""Private staff communication models.

This app is intentionally separate from the public member-to-admin inbox
(``contact.ContactMessage``) and from the members blackboard. Only signed-in
staff holding the ``communications.manage_communications`` permission can use
the portal, and every read/write is additionally scoped to the requesting
user's conversation membership.
"""

from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone

from sboi.storage import PrivateMediaStorage

# Attachments are deliberately limited to document/image types that a church
# office legitimately shares. Executables, scripts and archives are rejected.
ALLOWED_ATTACHMENT_EXTENSIONS = (
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
    'txt', 'csv', 'rtf', 'odt', 'ods',
    'jpg', 'jpeg', 'png', 'gif', 'webp',
)

MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024  # 10 MB

private_storage = PrivateMediaStorage()


def attachment_upload_path(instance, filename):
    """Store each upload under its conversation, with a collision-proof name."""
    suffix = Path(filename).suffix.lower()
    return (
        f'communications/{instance.message.conversation_id}/'
        f'{timezone.now():%Y/%m}/{uuid4().hex}{suffix}'
    )


class Conversation(models.Model):
    KIND_GROUP = 'group'
    KIND_DIRECT = 'direct'
    KIND_CHOICES = [
        (KIND_GROUP, 'Group conversation'),
        (KIND_DIRECT, 'Direct message'),
    ]

    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=KIND_GROUP)
    name = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True)
    # A stable key such as ``direct:4:9`` prevents duplicate direct threads.
    direct_key = models.CharField(max_length=64, unique=True, null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_admin_conversations',
    )
    members_can_add_members = models.BooleanField(default=False)
    members_can_edit_group = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False)
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-last_message_at', '-updated_at', '-pk']
        permissions = [
            (
                'manage_communications',
                'Admin communications: use the staff communication portal',
            ),
        ]

    def __str__(self):
        if self.kind == self.KIND_DIRECT:
            return self.direct_key or 'Direct message'
        return self.name or f'Group #{self.pk}'

    @property
    def is_group(self):
        return self.kind == self.KIND_GROUP

    @property
    def is_direct(self):
        return self.kind == self.KIND_DIRECT

    def display_name_for(self, user):
        """A conversation title scoped to the signed-in user."""
        if self.is_group:
            return self.name or 'Untitled group'
        other = (
            self.participants.exclude(user=user)
            .select_related('user')
            .first()
        )
        if other is None:
            return 'Direct message'
        return other.user.get_full_name() or other.user.get_username()

    def other_participant(self, user):
        if self.is_group:
            return None
        return (
            self.participants.exclude(user=user)
            .select_related('user')
            .first()
        )


class ConversationParticipant(models.Model):
    ROLE_OWNER = 'owner'
    ROLE_ADMIN = 'admin'
    ROLE_MEMBER = 'member'
    ROLE_CHOICES = [
        (ROLE_OWNER, 'Owner'),
        (ROLE_ADMIN, 'Group admin'),
        (ROLE_MEMBER, 'Member'),
    ]

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='participants',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='admin_conversation_participations',
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=ROLE_MEMBER)
    # New participants start with a clean unread slate. Existing group history
    # remains readable, but only messages after joining count as unread.
    last_read_at = models.DateTimeField(default=timezone.now)
    is_muted = models.BooleanField(default=False)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['role', 'joined_at', 'user__first_name', 'user__username']
        constraints = [
            models.UniqueConstraint(
                fields=['conversation', 'user'],
                name='unique_conversation_participant',
            ),
        ]
        indexes = [
            models.Index(fields=['user', 'conversation']),
        ]

    def __str__(self):
        return f'{self.user} in {self.conversation}'

    @property
    def is_manager(self):
        return self.role in (self.ROLE_OWNER, self.ROLE_ADMIN)

    @property
    def display_name(self):
        return self.user.get_full_name() or self.user.get_username()

    @property
    def initials(self):
        name = self.display_name
        parts = [part for part in name.split() if part]
        if not parts:
            return 'S'
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()


class Message(models.Model):
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='messages',
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_admin_messages',
    )
    body = models.TextField(blank=True)
    reply_to = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='replies',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at', 'pk']
        indexes = [
            models.Index(fields=['conversation', 'created_at']),
        ]

    def __str__(self):
        preview = (self.body or '').strip()[:60]
        return preview or f'Message #{self.pk}'

    @property
    def sender_name(self):
        if self.sender is None:
            return 'Removed user'
        return self.sender.get_full_name() or self.sender.get_username()

    @property
    def initials(self):
        name = self.sender_name
        parts = [part for part in name.split() if part]
        if not parts:
            return 'S'
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()

    @property
    def has_attachments(self):
        return bool(self.attachments.all())


class MessageAttachment(models.Model):
    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name='attachments',
    )
    file = models.FileField(
        upload_to=attachment_upload_path,
        storage=private_storage,
        validators=[FileExtensionValidator(ALLOWED_ATTACHMENT_EXTENSIONS)],
    )
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120, blank=True)
    size = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['pk']

    def __str__(self):
        return self.original_name or Path(self.file.name).name

    @property
    def extension(self):
        return Path(self.original_name or self.file.name).suffix.lower().lstrip('.')

    @property
    def is_image(self):
        return self.extension in {'jpg', 'jpeg', 'png', 'gif', 'webp'}


class MessageRead(models.Model):
    """One receipt per participant per message.

    Read receipts make direct-message "Seen" states and group "Read by N"
    indicators accurate without relying on a single mutable cursor.
    """

    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name='receipts',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='admin_message_reads',
    )
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-read_at']
        constraints = [
            models.UniqueConstraint(
                fields=['message', 'user'],
                name='unique_message_read',
            ),
        ]

    def __str__(self):
        return f'{self.user} read message #{self.message_id}'
