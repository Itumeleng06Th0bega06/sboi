"""Members-only social feed models for the admin communications workspace.

The feed is visible only to signed-in accounts. Nothing here is ever shown on
the public website. Posts may carry one attachment (image, video or document),
comments, and emoji reactions. A small moderation helper in ``views_comms``
keeps disrespectful content out without needing a third-party service.
"""

from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone

from sboi.storage import PrivateMediaStorage

# Feed attachments accept the same office documents plus video, because the
# church shares short clips and photos as well as PDFs.
FEED_ATTACHMENT_EXTENSIONS = (
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
    'txt', 'csv', 'rtf', 'odt', 'ods',
    'jpg', 'jpeg', 'png', 'gif', 'webp',
    'mp4', 'webm', 'mov', 'm4v',
)

FEED_MAX_ATTACHMENT_SIZE = 25 * 1024 * 1024  # 25 MB

feed_storage = PrivateMediaStorage()


def feed_upload_path(instance, filename):
    suffix = Path(filename).suffix.lower()
    return (
        f'feed/{timezone.now():%Y/%m}/'
        f'{uuid4().hex}{suffix}'
    )


class CommsPost(models.Model):
    AUDIENCE_ALL = 'all'
    AUDIENCE_STAFF = 'staff'
    AUDIENCE_CHOICES = [
        (AUDIENCE_ALL, 'All members'),
        (AUDIENCE_STAFF, 'Staff only'),
    ]

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='comms_posts',
    )
    audience = models.CharField(
        max_length=10, choices=AUDIENCE_CHOICES, default=AUDIENCE_ALL,
    )
    title = models.CharField(max_length=200, blank=True)
    body = models.TextField(blank=True)
    is_published = models.BooleanField(default=True)
    # Member-authored posts stay visible immediately unless the lightweight
    # moderation filter flags them; staff can still hide any post.
    is_hidden = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    edited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at', '-pk']

    def __str__(self):
        return self.title or (self.body or '')[:60] or f'Post #{self.pk}'

    @property
    def author_name(self):
        if self.author is None:
            return 'Removed account'
        return self.author.get_full_name() or self.author.get_username()

    @property
    def author_initials(self):
        parts = [part for part in self.author_name.split() if part]
        if not parts:
            return 'S'
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()

    @property
    def is_staff_post(self):
        return bool(self.author and self.author.is_staff)


class CommsAttachment(models.Model):
    KIND_IMAGE = 'image'
    KIND_VIDEO = 'video'
    KIND_DOCUMENT = 'document'
    KIND_CHOICES = [
        (KIND_IMAGE, 'Image'),
        (KIND_VIDEO, 'Video'),
        (KIND_DOCUMENT, 'Document'),
    ]

    post = models.ForeignKey(
        CommsPost,
        on_delete=models.CASCADE,
        related_name='attachments',
    )
    file = models.FileField(
        upload_to=feed_upload_path,
        storage=feed_storage,
        validators=[FileExtensionValidator(FEED_ATTACHMENT_EXTENSIONS)],
    )
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120, blank=True)
    size = models.PositiveIntegerField(default=0)
    kind = models.CharField(max_length=12, choices=KIND_CHOICES, default=KIND_DOCUMENT)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['pk']

    def __str__(self):
        return self.original_name or Path(self.file.name).name

    @property
    def extension(self):
        return Path(self.original_name or self.file.name).suffix.lower().lstrip('.')


class CommsComment(models.Model):
    post = models.ForeignKey(
        CommsPost,
        on_delete=models.CASCADE,
        related_name='comments',
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='comms_comments',
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='replies',
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at', 'pk']
        indexes = [
            models.Index(fields=['post', 'created_at']),
        ]

    def __str__(self):
        return (self.body or '')[:60] or f'Comment #{self.pk}'

    @property
    def author_name(self):
        return self.author.get_full_name() or self.author.get_username()

    @property
    def author_initials(self):
        parts = [part for part in self.author_name.split() if part]
        if not parts:
            return 'S'
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()

    @property
    def is_reply(self):
        return self.parent_id is not None


class CommsReaction(models.Model):
    THUMB = 'thumb'
    HEART = 'heart'
    PRAY = 'pray'
    REACTION_CHOICES = [
        (THUMB, '👍'),
        (HEART, '❤️'),
        (PRAY, '🙏'),
        ('laugh', '😂'),
        ('wow', '😮'),
        ('sad', '😢'),
    ]

    post = models.ForeignKey(
        CommsPost,
        on_delete=models.CASCADE,
        related_name='reactions',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='comms_reactions',
    )
    reaction = models.CharField(
        max_length=10, choices=REACTION_CHOICES, default=THUMB,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['post', 'user', 'reaction'],
                name='unique_feed_reaction',
            ),
        ]

    def __str__(self):
        return f'{self.user} reacted {self.reaction} to #{self.post_id}'


class CommsPostSave(models.Model):
    """A private bookmark. Saving a post never notifies anybody."""

    post = models.ForeignKey(
        CommsPost,
        on_delete=models.CASCADE,
        related_name='saves',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='saved_comms_posts',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['post', 'user'],
                name='unique_feed_save',
            ),
        ]

    def __str__(self):
        return f'{self.user} saved #{self.post_id}'


class CommsReport(models.Model):
    """A moderation report raised by a signed-in member."""

    REASON_SPAM = 'spam'
    REASON_ABUSE = 'abuse'
    REASON_HARASSMENT = 'harassment'
    REASON_MISINFORMATION = 'misinformation'
    REASON_OTHER = 'other'
    REASON_CHOICES = [
        (REASON_SPAM, 'Spam or advertising'),
        (REASON_ABUSE, 'Abusive or disrespectful content'),
        (REASON_HARASSMENT, 'Harassment or bullying'),
        (REASON_MISINFORMATION, 'False or misleading information'),
        (REASON_OTHER, 'Something else'),
    ]

    STATUS_PENDING = 'pending'
    STATUS_REVIEWED = 'reviewed'
    STATUS_DISMISSED = 'dismissed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Awaiting review'),
        (STATUS_REVIEWED, 'Reviewed'),
        (STATUS_DISMISSED, 'Dismissed'),
    ]

    post = models.ForeignKey(
        CommsPost,
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='reports',
    )
    comment = models.ForeignKey(
        CommsComment,
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='reports',
    )
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='comms_reports',
    )
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    note = models.TextField(blank=True)
    status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default=STATUS_PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='reviewed_comms_reports',
    )

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['post', 'reporter'],
                condition=models.Q(comment__isnull=True),
                name='unique_post_report',
            ),
            models.UniqueConstraint(
                fields=['comment', 'reporter'],
                condition=models.Q(post__isnull=True),
                name='unique_comment_report',
            ),
        ]

    def __str__(self):
        target = f'post #{self.post_id}' if self.post_id else f'comment #{self.comment_id}'
        return f'{self.get_reason_display()} report on {target}'


# ---------------------------------------------------------------------------
# Presence, blocking and direct messages
# ---------------------------------------------------------------------------

class CommunityPresence(models.Model):
    """The last time a signed-in member touched the community.

    A single row per account keeps the "online now" list cheap. The account
    middleware refreshes it at most once a minute while the feed and inbox
    polling keep an active session warm.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='community_presence',
    )
    last_seen_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ['-last_seen_at']

    def __str__(self):
        return f'{self.user} seen {self.last_seen_at:%Y-%m-%d %H:%M}'


class CommsBlock(models.Model):
    """A private block between two community accounts.

    Blocking is mutual for content and interaction: neither account sees the
    other's posts or comments, and neither can send the other a direct message.
    Only the blocker can remove the block from the member's profile.
    """

    blocker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='community_blocks',
    )
    blocked = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='community_blocked_by',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['blocker', 'blocked'],
                name='unique_community_block',
            ),
        ]
        indexes = [
            models.Index(fields=['blocker', 'blocked']),
            models.Index(fields=['blocked', 'blocker']),
        ]

    def __str__(self):
        return f'{self.blocker} blocked {self.blocked}'


class CommsDirectThread(models.Model):
    """One private member-to-member conversation.

    The two participants are normalised by primary key (``user_a`` is always
    the lower id) so a pair can never end up with two duplicate threads. The
    read cursor lets the inbox show an accurate unread count without creating
    a receipt row for every message.
    """

    user_a = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='direct_threads_started',
    )
    user_b = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='direct_threads_received',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)
    user_a_read_at = models.DateTimeField(default=timezone.now)
    user_b_read_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-last_message_at', '-updated_at', '-pk']
        constraints = [
            models.UniqueConstraint(
                fields=['user_a', 'user_b'],
                name='unique_direct_thread_pair',
            ),
        ]
        indexes = [
            models.Index(fields=['user_a', 'last_message_at']),
            models.Index(fields=['user_b', 'last_message_at']),
        ]

    def __str__(self):
        return f'{self.user_a} ↔ {self.user_b}'

    @classmethod
    def for_users(cls, one, two):
        if one.pk == two.pk:
            raise ValueError('A direct thread needs two different accounts.')
        a, b = (one, two) if one.pk < two.pk else (two, one)
        thread, _ = cls.objects.get_or_create(user_a=a, user_b=b)
        return thread

    def other_user(self, user):
        if user.pk == self.user_a_id:
            return self.user_b
        if user.pk == self.user_b_id:
            return self.user_a
        return None

    def read_cursor(self, user):
        if user.pk == self.user_a_id:
            return self.user_a_read_at
        if user.pk == self.user_b_id:
            return self.user_b_read_at
        return None

    def mark_read(self, user):
        field = None
        if user.pk == self.user_a_id:
            field = 'user_a_read_at'
        elif user.pk == self.user_b_id:
            field = 'user_b_read_at'
        if not field:
            return
        setattr(self, field, timezone.now())
        self.save(update_fields=[field, 'updated_at'])
        self.mark_notifications_read(user)

    def unread_count(self, user):
        cursor = self.read_cursor(user)
        if cursor is None:
            return 0
        return (
            self.messages
            .exclude(sender=user)
            .filter(created_at__gt=cursor)
            .count()
        )

    def mark_notifications_read(self, user):
        from notifications.models import Notification, NotificationState

        notification_ids = Notification.objects.filter(
            recipient=user,
            source_type='direct_message',
            status__in=Notification.OPEN_STATUSES,
        ).filter(
            source_id__in=self.messages.values('pk'),
        ).values_list('pk', flat=True)
        now = timezone.now()
        for notification in Notification.objects.filter(pk__in=list(notification_ids)):
            state, _ = NotificationState.objects.get_or_create(
                notification=notification,
                user=user,
            )
            if state.read_at is None:
                state.read_at = now
                state.save(update_fields=['read_at', 'updated_at'])


class CommsDirectMessage(models.Model):
    """A short private message between two community members."""

    thread = models.ForeignKey(
        CommsDirectThread,
        on_delete=models.CASCADE,
        related_name='messages',
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_direct_messages',
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['created_at', 'pk']
        indexes = [
            models.Index(fields=['thread', 'created_at']),
        ]

    def __str__(self):
        return (self.body or '')[:60] or f'Direct message #{self.pk}'

    @property
    def sender_name(self):
        return self.sender.get_full_name() or self.sender.get_username()

    @property
    def sender_initials(self):
        parts = [part for part in self.sender_name.split() if part]
        if not parts:
            return 'S'
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()
