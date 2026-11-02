"""Single notification model shared by the public site and the admin console.

A ``Notification`` is the *activity* (a new contact message, a membership
application, an active announcement, ...).  Read/dismiss/archive state is kept
per user in ``NotificationState`` so one administrator reading a shared
notification never silently resolves it for every other administrator.

The record is never deleted just because it was read, dismissed or completed:
the open dropdown filters it out while the history page still has the audit
trail.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class Notification(models.Model):
    # ---- Audience --------------------------------------------------------
    AUDIENCE_PUBLIC = 'public'
    AUDIENCE_MEMBER = 'member'
    AUDIENCE_STAFF = 'staff'
    AUDIENCE_CHOICES = [
        (AUDIENCE_PUBLIC, 'Public / signed-in members'),
        (AUDIENCE_MEMBER, 'One member'),
        (AUDIENCE_STAFF, 'Staff'),
    ]

    # ---- Activity status -------------------------------------------------
    STATUS_ACTIVE = 'active'
    STATUS_PENDING = 'pending'
    STATUS_RESOLVED = 'resolved'
    STATUS_COMPLETED = 'completed'
    STATUS_DISMISSED = 'dismissed'
    STATUS_ARCHIVED = 'archived'
    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_PENDING, 'Pending'),
        (STATUS_RESOLVED, 'Resolved'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_DISMISSED, 'Dismissed'),
        (STATUS_ARCHIVED, 'Archived'),
    ]
    OPEN_STATUSES = (STATUS_ACTIVE, STATUS_PENDING)

    # ---- Presentation ----------------------------------------------------
    TONE_INFO = 'info'
    TONE_ATTENTION = 'attention'
    TONE_WARNING = 'warning'
    TONE_CHOICES = [
        (TONE_INFO, 'Information'),
        (TONE_ATTENTION, 'Attention'),
        (TONE_WARNING, 'Warning'),
    ]

    # ``recipient`` is null for shared/public notifications.  A member
    # notification and a direct staff notification always name one user.
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications',
    )
    audience = models.CharField(
        max_length=10, choices=AUDIENCE_CHOICES, default=AUDIENCE_STAFF,
        db_index=True,
    )
    category = models.CharField(max_length=40, db_index=True)
    # Stable identity of the underlying activity.  It makes the synchroniser
    # idempotent and keeps history across repeated saves.
    source_type = models.CharField(max_length=40, db_index=True)
    source_id = models.PositiveBigIntegerField(null=True, blank=True, db_index=True)
    source_key = models.CharField(max_length=180, unique=True)

    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    url = models.CharField(max_length=500, blank=True)
    icon = models.CharField(max_length=40, default='bell', blank=True)
    tone = models.CharField(
        max_length=12, choices=TONE_CHOICES, default=TONE_INFO,
    )
    # Staff notifications may be restricted to holders of one area permission.
    permission = models.CharField(max_length=120, blank=True, db_index=True)

    status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default=STATUS_ACTIVE,
        db_index=True,
    )
    # Read status and activity status are deliberately separate.  A read
    # notification still appears while it requires attention.
    requires_action = models.BooleanField(default=False)

    # Delivery audit for the optional WhatsApp notice. The in-app notification
    # is always the primary channel; WhatsApp is best-effort and generic.
    WHATSAPP_STATUS_CHOICES = [
        ('not_attempted', 'Not attempted'),
        ('not_configured', 'Not configured'),
        ('skipped', 'Skipped (no consent or phone)'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
    ]
    whatsapp_status = models.CharField(
        max_length=20, choices=WHATSAPP_STATUS_CHOICES,
        default='not_attempted',
    )
    whatsapp_error = models.TextField(blank=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        indexes = [
            models.Index(fields=['audience', 'status', 'expires_at']),
            models.Index(fields=['recipient', 'status']),
            models.Index(fields=['permission', 'status']),
            models.Index(fields=['source_type', 'source_id']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['status', 'requires_action']),
        ]

    def __str__(self):
        return self.title

    @property
    def is_open(self):
        return (
            self.status in self.OPEN_STATUSES
            and (self.expires_at is None or self.expires_at > timezone.now())
        )

    @property
    def is_expired(self):
        return self.expires_at is not None and self.expires_at <= timezone.now()

    def mark_resolved(self, status=None):
        """Close an activity without deleting its historical record."""
        self.status = status or self.STATUS_RESOLVED
        self.resolved_at = timezone.now()
        if self.status == self.STATUS_COMPLETED:
            self.completed_at = self.resolved_at
        self.save(update_fields=['status', 'resolved_at', 'completed_at', 'updated_at'])


class NotificationState(models.Model):
    """Per-user state for one notification.

    Shared admin notifications are a single row; this table is what makes
    "read", "dismissed" and "archived" personal to each administrator.
    """

    notification = models.ForeignKey(
        Notification,
        on_delete=models.CASCADE,
        related_name='states',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notification_states',
    )
    read_at = models.DateTimeField(null=True, blank=True)
    dismissed_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        constraints = [
            models.UniqueConstraint(
                fields=['notification', 'user'],
                name='unique_notification_state',
            ),
        ]
        indexes = [
            models.Index(fields=['user', 'dismissed_at']),
            models.Index(fields=['user', 'archived_at']),
            models.Index(fields=['user', 'read_at']),
        ]

    def __str__(self):
        return f'Notification #{self.notification_id} for {self.user}'
