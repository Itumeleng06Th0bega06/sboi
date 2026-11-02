from datetime import timedelta

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from members import services as member_services
from notifications import services as notification_services
from sboi.admin_permissions import AreaPermissionMixin

from .forms import AdminComposeForm, AdminReplyForm
from .models import ContactInfo, ContactMessage


@admin.register(ContactInfo)
class ContactInfoAdmin(AreaPermissionMixin, admin.ModelAdmin):
    area_permission = 'contact.manage_contact_details'
    list_display = ['church_name', 'email', 'phone']


@admin.register(ContactMessage)
class ContactMessageAdmin(AreaPermissionMixin, admin.ModelAdmin):
    area_permission = 'contact.manage_contact_messages'
    list_display = [
        'name', 'subject', 'email', 'created_at', 'is_read',
        'conversation_link',
    ]
    list_filter = ['is_read', 'is_from_admin']
    list_editable = ['is_read']
    search_fields = ['name', 'email', 'subject', 'message', 'user__email']
    readonly_fields = [
        'name', 'email', 'phone', 'subject', 'message', 'created_at',
        'user', 'sender', 'is_from_admin', 'read_by_member', 'attachment_link',
    ]
    exclude = ['attachment']
    date_hierarchy = 'created_at'
    actions = ['mark_read', 'mark_unread']
    change_list_template = 'admin/contact/contactmessage/change_list.html'

    def get_urls(self):
        custom = [
            path(
                'inbox/',
                self.admin_site.admin_view(self.inbox_view),
                name='contact_contactmessage_inbox',
            ),
            path(
                'compose/',
                self.admin_site.admin_view(self.compose_view),
                name='contact_contactmessage_compose',
            ),
            path(
                '<int:pk>/conversation/',
                self.admin_site.admin_view(self.conversation_view),
                name='contact_contactmessage_conversation',
            ),
        ]
        return custom + super().get_urls()

    def _recent_duplicate_admin_message(self, request, user_id, body):
        """Return a just-sent identical reply, so a retried POST is a no-op.

        The notification service is idempotent per message, but a browser
        retry can otherwise create a second message and therefore a second
        notification. A short window keeps accidental double-clicks and
        network retries from duplicating the conversation.
        """
        return (
            ContactMessage.objects
            .filter(
                user_id=user_id,
                sender=request.user,
                is_from_admin=True,
                message=body,
                created_at__gte=timezone.now() - timedelta(seconds=30),
            )
            .order_by('-created_at')
            .first()
        )

    # -- Conversation inbox ------------------------------------------------

    def inbox_view(self, request):
        """One row per member, with unread and awaiting-reply state."""
        if not self.has_view_permission(request):
            raise PermissionDenied

        query = (request.GET.get('q') or '').strip()
        messages_qs = ContactMessage.objects.filter(
            user__isnull=False,
        ).select_related('user', 'sender')
        if query:
            matching_users = messages_qs.filter(
                Q(user__username__icontains=query)
                | Q(user__first_name__icontains=query)
                | Q(user__last_name__icontains=query)
                | Q(user__email__icontains=query)
                | Q(subject__icontains=query)
                | Q(message__icontains=query)
            ).values_list('user_id', flat=True)
            messages_qs = messages_qs.filter(user_id__in=matching_users)

        groups = {}
        for message in messages_qs.order_by('created_at', 'pk'):
            row = groups.get(message.user_id)
            if row is None:
                row = {
                    'user': message.user,
                    'latest': message,
                    'unread_admin': 0,
                    'unread_member': 0,
                }
                groups[message.user_id] = row
            row['latest'] = message
            if message.is_from_admin:
                if not message.read_by_member:
                    row['unread_member'] += 1
            elif not message.is_read:
                row['unread_admin'] += 1

        rows = sorted(
            groups.values(),
            key=lambda row: row['latest'].created_at,
            reverse=True,
        )
        for row in rows:
            row['awaiting_reply'] = not row['latest'].is_from_admin
            row['conversation_url'] = reverse(
                'admin:contact_contactmessage_conversation',
                args=[row['latest'].pk],
            )
            membership = getattr(row['user'], 'church_membership', None)
            row['membership'] = membership
            row['compose_url'] = reverse(
                'admin:contact_contactmessage_compose',
            ) + (f'?member={membership.pk}' if membership else '')

        context = {
            **self.admin_site.each_context(request),
            'title': 'Member messages',
            'opts': self.model._meta,
            'rows': rows,
            'query': query,
            'total_conversations': len(rows),
            'total_unread_admin': sum(
                row['unread_admin'] for row in rows
            ),
            'total_unread_member': sum(
                row['unread_member'] for row in rows
            ),
            'total_awaiting': sum(
                1 for row in rows if row['awaiting_reply']
            ),
            'compose_url': reverse(
                'admin:contact_contactmessage_compose',
            ),
            'changelist_url': reverse(
                'admin:contact_contactmessage_changelist',
            ),
        }
        return render(
            request,
            'admin/contact/contactmessage/inbox.html',
            context,
        )

    def compose_view(self, request):
        """Start a conversation with any member, even with no prior contact."""
        if not self.has_change_permission(request):
            raise PermissionDenied

        initial = {}
        member_id = (request.GET.get('member') or '').strip()
        if member_id.isdigit():
            initial['membership'] = member_id

        form = AdminComposeForm(
            request.POST or None,
            request.FILES or None,
            initial=initial,
        )
        if request.method == 'POST' and form.is_valid():
            membership = form.cleaned_data['membership']
            user = membership.user
            body = form.cleaned_data['message']
            duplicate = self._recent_duplicate_admin_message(
                request, user.pk, body,
            )
            if duplicate is not None:
                self.message_user(
                    request,
                    'That message was already sent. Open the existing '
                    'conversation below.',
                    messages.INFO,
                )
                return HttpResponseRedirect(
                    reverse(
                        'admin:contact_contactmessage_conversation',
                        args=[duplicate.pk],
                    )
                )
            message = ContactMessage.objects.create(
                user=user,
                sender=request.user,
                name=membership.full_name or user.get_username(),
                email=user.email or '',
                phone=membership.phone or '',
                subject=(form.cleaned_data.get('subject') or '').strip(),
                message=body,
                attachment=form.cleaned_data.get('attachment') or None,
                is_from_admin=True,
                is_read=True,
                read_by_member=False,
            )
            member_services.notify_member_reply(
                message,
                title='New message from church administration',
            )
            self.message_user(
                request,
                'Message sent. The member will see it in their private '
                'inbox and in-app notifications.',
                messages.SUCCESS,
            )
            return HttpResponseRedirect(
                reverse(
                    'admin:contact_contactmessage_conversation',
                    args=[message.pk],
                )
            )

        context = {
            **self.admin_site.each_context(request),
            'title': 'New member message',
            'opts': self.model._meta,
            'form': form,
            'changelist_url': reverse(
                'admin:contact_contactmessage_changelist',
            ),
            'inbox_url': reverse(
                'admin:contact_contactmessage_inbox',
            ),
        }
        return render(
            request,
            'admin/contact/contactmessage/compose.html',
            context,
        )

    @admin.display(description='Conversation')
    def conversation_link(self, obj):
        if obj.user_id is None:
            return '—'
        url = reverse(
            'admin:contact_contactmessage_conversation', args=[obj.pk],
        )
        label = 'Open thread'
        return format_html('<a class="button" href="{}">{}</a>', url, label)

    @admin.display(description='Attachment')
    def attachment_link(self, obj):
        if not obj.attachment:
            return '—'
        return format_html(
            '<a href="{}" target="_blank" rel="noopener">{}</a>',
            reverse('contact:attachment', args=[obj.pk]),
            obj.attachment_name,
        )

    def conversation_view(self, request, pk):
        """One permission-checked page for the whole member conversation."""
        if not self.has_change_permission(request):
            raise PermissionDenied
        message = get_object_or_404(
            ContactMessage.objects.select_related('user', 'sender'), pk=pk,
        )
        if message.user_id is None:
            messages.error(
                request,
                'This is a public contact message. It has no member inbox to '
                'reply to; use the normal change form to mark it read.',
            )
            return HttpResponseRedirect(
                reverse('admin:contact_contactmessage_change', args=[pk]),
            )

        thread = list(
            ContactMessage.objects
            .filter(user_id=message.user_id)
            .select_related('sender')
            .order_by('created_at', 'pk')
        )
        # Opening the thread is the administrator reading the member's side.
        # Saving each row fires the shared notification receiver, which closes
        # the corresponding staff bell item.
        for item in thread:
            if not item.is_from_admin and not item.is_read:
                item.is_read = True
                item.save(update_fields=['is_read'])

        member_name = (
            message.user.get_full_name()
            or message.user.get_username()
            or message.name
        )
        membership = getattr(message.user, 'church_membership', None)

        form = AdminReplyForm()
        if request.method == 'POST':
            form = AdminReplyForm(request.POST, request.FILES)
            if form.is_valid():
                body = form.cleaned_data['message']
                duplicate = self._recent_duplicate_admin_message(
                    request, message.user_id, body,
                )
                if duplicate is not None:
                    self.message_user(
                        request,
                        'That reply was already sent.',
                        messages.INFO,
                    )
                    return HttpResponseRedirect(
                        reverse(
                            'admin:contact_contactmessage_conversation',
                            args=[duplicate.pk],
                        )
                    )
                reply = ContactMessage.objects.create(
                    user_id=message.user_id,
                    sender=request.user,
                    name=(
                        request.user.get_full_name()
                        or request.user.get_username()
                    ),
                    email=message.email or request.user.email or '',
                    phone=message.phone or '',
                    subject=(
                        message.subject or 'Reply from church administration'
                    ),
                    message=body,
                    attachment=form.cleaned_data.get('attachment') or None,
                    parent=thread[-1] if thread else None,
                    is_from_admin=True,
                    is_read=True,
                    read_by_member=False,
                )
                member_services.notify_member_reply(reply)
                self.message_user(
                    request,
                    'Reply sent. The member will see it in their private '
                    'inbox and in-app notifications.',
                    messages.SUCCESS,
                )
                return HttpResponseRedirect(
                    reverse(
                        'admin:contact_contactmessage_conversation',
                        args=[reply.pk],
                    )
                )

        context = {
            **self.admin_site.each_context(request),
            'title': f'Conversation with {member_name}',
            'member_name': member_name,
            'opts': self.model._meta,
            'original': message,
            'thread': thread,
            'form': form,
            'awaiting_reply': bool(thread) and not thread[-1].is_from_admin,
            'member_unread': sum(
                1 for item in thread
                if item.is_from_admin and not item.read_by_member
            ),
            'change_url': reverse(
                'admin:contact_contactmessage_change', args=[message.pk],
            ),
            'inbox_url': reverse(
                'admin:contact_contactmessage_inbox',
            ),
            'compose_url': reverse(
                'admin:contact_contactmessage_compose',
            ) + (f'?member={membership.pk}' if membership else ''),
        }
        return render(
            request,
            'admin/contact/contactmessage/conversation.html',
            context,
        )

    @admin.action(description='Mark selected messages as read')
    def mark_read(self, request, queryset):
        queryset.update(is_read=True)
        for message in queryset.select_related('user'):
            notification_services.sync_contact_message(message)

    @admin.action(description='Mark selected messages as unread')
    def mark_unread(self, request, queryset):
        queryset.update(is_read=False)
        for message in queryset.select_related('user'):
            notification_services.sync_contact_message(message)
