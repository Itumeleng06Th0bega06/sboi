"""Tests for the private admin communications portal.

The cases mirror the acceptance criteria: access control, direct-message
privacy, groups and membership, replies, unread/read state, attachments, CSRF,
search and isolation from the member-to-admin contact inbox.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from contact.models import ContactMessage
from notifications.models import Notification

from .models import (
    ALLOWED_ATTACHMENT_EXTENSIONS,
    MAX_ATTACHMENT_SIZE,
    Conversation,
    ConversationParticipant,
    Message,
    MessageAttachment,
    MessageRead,
)
from .services import (
    add_members,
    can_use_portal,
    conversation_summaries,
    create_group,
    create_message,
    get_or_create_direct,
    leave_group,
    mark_conversation_read,
    message_queryset,
    portal_users,
    remove_member,
    unread_summary,
    unread_total,
)

User = get_user_model()


class CommunicationsBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.permission = Permission.objects.get(
            content_type__app_label='communications',
            codename='manage_communications',
        )

    def make_user(self, username, *, staff=True, allowed=True, superuser=False):
        user = User.objects.create_user(
            username=username,
            password='test-pass-12345',
            first_name=username.title(),
            email=f'{username}@example.com',
            is_staff=staff,
            is_superuser=superuser,
        )
        if allowed:
            user.user_permissions.add(self.permission)
        return user

    def setUp(self):
        self.owner = self.make_user('owner')
        self.member = self.make_user('member')
        self.outsider = self.make_user('outsider')
        self.staff_without_permission = self.make_user(
            'unpermitted', allowed=False,
        )
        self.ordinary_member = self.make_user(
            'ordinary', staff=False, allowed=False,
        )
        self.client.force_login(self.owner)

    def tearDown(self):
        # Attachments use real private storage; remove them after each test.
        for attachment in MessageAttachment.objects.all():
            if attachment.file:
                attachment.file.storage.delete(attachment.file.name)

    def login(self, user):
        client = Client()
        client.force_login(user)
        return client

    def make_group(self, creator=None, members=(), name='Leadership'):
        return create_group(
            creator or self.owner,
            name,
            'Private staff group',
            list(members),
        )

    def send(self, conversation, sender, body, **kwargs):
        return create_message(conversation, sender, body, **kwargs)


class PortalAccessTests(CommunicationsBase):
    def test_anonymous_visitor_is_sent_to_admin_login(self):
        self.client.logout()
        response = self.client.get(reverse('communications:inbox'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('admin:login'), response['Location'])

    def test_ordinary_member_cannot_enter_even_with_permission(self):
        self.ordinary_member.user_permissions.add(self.permission)
        self.assertFalse(can_use_portal(self.ordinary_member))
        client = self.login(self.ordinary_member)
        response = client.get(reverse('communications:inbox'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('admin:login'), response['Location'])

    def test_staff_without_explicit_permission_is_denied(self):
        self.assertFalse(can_use_portal(self.staff_without_permission))
        client = self.login(self.staff_without_permission)
        response = client.get(reverse('communications:inbox'))
        self.assertEqual(response.status_code, 403)

    def test_authorised_staff_can_render_the_three_column_portal(self):
        response = self.client.get(reverse('communications:inbox'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Admin Communications')
        self.assertContains(response, 'comms-shell')
        self.assertContains(response, 'comms-sidebar')
        self.assertContains(response, 'data-comms-root')
        self.assertContains(response, 'communications.css')
        self.assertContains(response, 'communications.js')
        # The portal renders inside the admin shell, so Django's shared admin
        # context (account menu, notification bell, logout) must be present.
        self.assertTrue(response.context['has_permission'])
        self.assertIn('admin_dashboard', response.context)

    def test_superuser_passes_without_explicit_permission_row(self):
        superuser = self.make_user('root', allowed=False, superuser=True)
        client = self.login(superuser)
        self.assertEqual(
            client.get(reverse('communications:inbox')).status_code, 200,
        )

    def test_admin_header_and_dashboard_link_to_the_portal(self):
        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['admin_dashboard']['communications']['allowed'])
        self.assertContains(response, 'Admin Communications')
        self.assertContains(response, reverse('communications:inbox'))

    def test_member_picker_only_lists_authorised_staff(self):
        users = list(portal_users())
        self.assertIn(self.owner, users)
        self.assertNotIn(self.staff_without_permission, users)
        self.assertNotIn(self.ordinary_member, users)


class CsrfAndSendingTests(CommunicationsBase):
    def setUp(self):
        super().setUp()
        self.group = self.make_group(members=[self.member])

    def test_post_without_csrf_token_is_rejected(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        response = client.post(
            reverse('communications:send_message', args=[self.group.pk]),
            {'body': 'This must not be stored'},
        )
        self.assertNotEqual(response.status_code, 200)
        self.assertFalse(
            Message.objects.filter(body='This must not be stored').exists()
        )

    def test_sending_creates_message_and_recipient_notification(self):
        response = self.client.post(
            reverse('communications:send_message', args=[self.group.pk]),
            {'body': 'The meeting starts at 18:00.'},
        )
        self.assertEqual(response.status_code, 302)
        message = Message.objects.get(body='The meeting starts at 18:00.')
        self.assertEqual(message.sender, self.owner)
        notification = Notification.objects.get(
            recipient=self.member,
            source_type='admin_message',
            source_id=message.pk,
        )
        self.assertEqual(notification.audience, Notification.AUDIENCE_STAFF)
        self.assertIn(
            f'?conversation={self.group.pk}', notification.url,
        )
        self.assertEqual(notification.status, Notification.STATUS_ACTIVE)

    def test_ajax_send_returns_rendered_message_fragment(self):
        response = self.client.post(
            reverse('communications:send_message', args=[self.group.pk]),
            {'body': 'Ajax message'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 201)
        self.assertContains(response, 'Ajax message', status_code=201)
        self.assertContains(response, 'comms-message', status_code=201)

    def test_reply_to_message_in_the_same_conversation(self):
        original = self.send(self.group, self.member, 'Original question')
        response = self.client.post(
            reverse('communications:send_message', args=[self.group.pk]),
            {'body': 'Answer', 'reply_to': str(original.pk)},
        )
        self.assertEqual(response.status_code, 302)
        reply = Message.objects.get(body='Answer')
        self.assertEqual(reply.reply_to, original)

    def test_reply_id_from_another_conversation_is_ignored(self):
        other_group = self.make_group(name='Other group')
        foreign = self.send(other_group, self.owner, 'Foreign message')
        self.client.post(
            reverse('communications:send_message', args=[self.group.pk]),
            {'body': 'Safe reply', 'reply_to': str(foreign.pk)},
        )
        reply = Message.objects.get(body='Safe reply')
        self.assertIsNone(reply.reply_to)

    def test_empty_message_and_attachment_is_rejected(self):
        response = self.client.post(
            reverse('communications:send_message', args=[self.group.pk]),
            {'body': '   '},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Message.objects.exists())


class UnreadAndReadStateTests(CommunicationsBase):
    def setUp(self):
        super().setUp()
        self.group = self.make_group(members=[self.member, self.outsider])

    def test_unread_counts_and_latest_conversation_summary(self):
        self.send(self.group, self.owner, 'Unread for everyone else')
        rows = conversation_summaries(self.member)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['unread_count'], 1)
        self.assertEqual(unread_total(self.member), 1)
        total, latest = unread_summary(self.member)
        self.assertEqual(total, 1)
        self.assertEqual(latest, self.group.pk)
        self.assertEqual(unread_total(self.owner), 0)

    def test_unread_count_does_not_rely_on_matching_ids(self):
        # Shift the conversation id sequence so a group's pk and its
        # messages' pks cannot coincide. The old correlated subquery compared
        # participant.conversation_id with message.id and undercounted.
        self.make_group(name='ID shifter', members=[self.member])
        self.send(self.group, self.owner, 'First unread')
        self.send(self.group, self.owner, 'Second unread')
        rows = conversation_summaries(self.member)
        row = next(
            item for item in rows
            if item['conversation'].pk == self.group.pk
        )
        self.assertEqual(row['unread_count'], 2)
        self.assertEqual(unread_total(self.member), 2)

    def test_opening_conversation_marks_read_and_resolves_notification(self):
        message = self.send(self.group, self.owner, 'Please read me')
        mark_conversation_read(self.group, self.member)
        self.assertTrue(
            MessageRead.objects.filter(message=message, user=self.member).exists()
        )
        participant = ConversationParticipant.objects.get(
            conversation=self.group, user=self.member,
        )
        self.assertGreaterEqual(participant.last_read_at, message.created_at)
        notification = Notification.objects.get(
            recipient=self.member,
            source_type='admin_message',
            source_id=message.pk,
        )
        self.assertEqual(notification.status, Notification.STATUS_RESOLVED)
        self.assertEqual(unread_total(self.member), 0)
        self.assertEqual(
            message_queryset(self.group).get(pk=message.pk).read_count, 1,
        )

    def test_reading_one_conversation_leaves_other_unread(self):
        other_group = self.make_group(name='Finance', members=[self.member])
        self.send(self.group, self.owner, 'Operations update')
        self.send(other_group, self.owner, 'Finance update')
        mark_conversation_read(self.group, self.member)
        self.assertEqual(unread_total(self.member), 1)
        total, latest = unread_summary(self.member)
        self.assertEqual(total, 1)
        self.assertEqual(latest, other_group.pk)

    def test_workspace_endpoint_marks_messages_read(self):
        message = self.send(self.group, self.member, 'Visible in workspace')
        response = self.client.get(
            reverse('communications:conversation_workspace', args=[self.group.pk])
            + f'?conversation={self.group.pk}',
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Visible in workspace')
        self.assertTrue(
            MessageRead.objects.filter(message=message, user=self.owner).exists()
        )

    def test_chat_messages_do_not_shadow_admin_flash_messages(self):
        self.send(self.group, self.member, 'Chat-only body')
        response = self.client.get(
            reverse('communications:inbox')
            + f'?conversation={self.group.pk}',
        )
        self.assertEqual(response.status_code, 200)
        # The admin base template renders ``messages`` for flash notices; the
        # chat list must use its own context name so chat bodies never appear
        # as admin notices.
        self.assertEqual(list(response.context['messages']), [])
        self.assertNotContains(response, '<ul class="messagelist">')

    def test_opening_inbox_clears_the_selected_row_unread_badge(self):
        self.send(self.group, self.member, 'Unread on arrival')
        response = self.client.get(
            reverse('communications:inbox')
            + f'?conversation={self.group.pk}',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['conversation_rows'][0]['unread_count'], 0)
        self.assertEqual(response.context['total_unread'], 0)

    def test_revoked_permission_clears_internal_message_notifications(self):
        message = self.send(self.group, self.owner, 'Permission-sensitive')
        self.member.user_permissions.remove(self.permission)
        response = self.login(self.member).get(reverse('admin:index'))
        self.assertEqual(response.status_code, 200)
        notification = Notification.objects.get(
            recipient=self.member,
            source_type='admin_message',
            source_id=message.pk,
        )
        self.assertEqual(notification.status, Notification.STATUS_RESOLVED)

    def test_removed_group_member_notification_is_cleared(self):
        message = self.send(self.group, self.owner, 'Group-only secret')
        remove_member(
            self.group,
            self.group.participants.get(user=self.member),
        )
        response = self.login(self.member).get(reverse('admin:index'))
        self.assertEqual(response.status_code, 200)
        notification = Notification.objects.get(
            recipient=self.member,
            source_type='admin_message',
            source_id=message.pk,
        )
        self.assertEqual(notification.status, Notification.STATUS_RESOLVED)


class DirectMessagePrivacyTests(CommunicationsBase):
    def setUp(self):
        super().setUp()
        self.direct, _created = get_or_create_direct(self.owner, self.member)

    def test_direct_thread_is_reused_not_duplicated(self):
        again, created = get_or_create_direct(self.member, self.owner)
        self.assertFalse(created)
        self.assertEqual(again.pk, self.direct.pk)
        self.assertEqual(self.direct.participants.count(), 2)

    def test_direct_display_name_is_the_other_participant(self):
        self.assertEqual(self.direct.display_name_for(self.owner), 'Member')
        self.assertEqual(self.direct.display_name_for(self.member), 'Owner')

    def test_outsider_cannot_read_or_post_to_a_direct_thread(self):
        message = self.send(self.direct, self.owner, 'Confidential')
        client = self.login(self.outsider)
        read_urls = [
            reverse('communications:conversation_workspace', args=[self.direct.pk]),
            reverse('communications:conversation_messages', args=[self.direct.pk]),
        ]
        for url in read_urls:
            response = client.get(url)
            self.assertEqual(response.status_code, 404, url)
        send_url = reverse('communications:send_message', args=[self.direct.pk])
        # GET is rejected before any conversation lookup, so an outsider
        # cannot use the method response to discover the thread.
        self.assertEqual(client.get(send_url).status_code, 405)
        response = client.post(send_url, {'body': 'Injected'})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Message.objects.filter(body='Injected').exists())
        self.assertNotIn(
            self.direct,
            [row['conversation'] for row in conversation_summaries(self.outsider)],
        )
        self.assertTrue(
            Message.objects.filter(pk=message.pk).exists()
        )

    def test_direct_thread_cannot_be_left_or_have_members_removed(self):
        with self.assertRaises(ValidationError):
            leave_group(self.direct, self.owner)
        participant = self.direct.participants.get(user=self.member)
        with self.assertRaises(ValidationError):
            remove_member(self.direct, participant)

    def test_direct_thread_cannot_be_edited_through_group_view(self):
        response = self.client.post(
            reverse('communications:update_group', args=[self.direct.pk]),
            {'name': 'Renamed', 'description': ''},
        )
        self.assertEqual(response.status_code, 403)
        self.direct.refresh_from_db()
        self.assertNotEqual(self.direct.name, 'Renamed')


class GroupManagementTests(CommunicationsBase):
    def setUp(self):
        super().setUp()
        self.group = self.make_group(members=[self.member])
        self.other = self.make_user('other')

    def test_create_group_through_view(self):
        response = self.client.post(
            reverse('communications:create_group'),
            {
                'name': 'Finance Team',
                'description': 'Budget and reporting',
                'members': [str(self.member.pk)],
                'members_can_add_members': 'on',
            },
        )
        self.assertEqual(response.status_code, 302)
        group = Conversation.objects.get(name='Finance Team')
        self.assertEqual(group.created_by, self.owner)
        self.assertTrue(group.members_can_add_members)
        self.assertEqual(group.participants.count(), 2)
        self.assertTrue(
            group.participants.filter(
                user=self.owner, role=ConversationParticipant.ROLE_OWNER,
            ).exists()
        )

    def test_owner_can_add_and_remove_members(self):
        response = self.client.post(
            reverse('communications:add_members', args=[self.group.pk]),
            {'members': [str(self.other.pk)]},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            self.group.participants.filter(user=self.other).exists()
        )
        participant = self.group.participants.get(user=self.other)
        response = self.client.post(
            reverse('communications:remove_member', args=[self.group.pk]),
            {'participant': str(participant.pk)},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            self.group.participants.filter(user=self.other).exists()
        )

    def test_plain_member_cannot_manage_members(self):
        self.group.members_can_add_members = False
        self.group.save(update_fields=['members_can_add_members'])
        client = self.login(self.member)
        response = client.post(
            reverse('communications:add_members', args=[self.group.pk]),
            {'members': [str(self.other.pk)]},
        )
        self.assertEqual(response.status_code, 403)
        participant = self.group.participants.get(user=self.owner)
        response = client.post(
            reverse('communications:remove_member', args=[self.group.pk]),
            {'participant': str(participant.pk)},
        )
        self.assertEqual(response.status_code, 403)

    def test_member_permissions_can_be_enabled_by_owner(self):
        response = self.client.post(
            reverse('communications:update_group', args=[self.group.pk]),
            {
                'name': 'Leadership Team',
                'description': 'Updated description',
                'members_can_add_members': 'on',
                'members_can_edit_group': 'on',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.group.refresh_from_db()
        self.assertEqual(self.group.name, 'Leadership Team')
        self.assertTrue(self.group.members_can_add_members)
        self.assertTrue(self.group.members_can_edit_group)

        client = self.login(self.member)
        response = client.post(
            reverse('communications:update_group', args=[self.group.pk]),
            {
                'name': 'Member Edited Name',
                'description': 'Member edit',
                # A plain member must not be able to escalate permissions.
                'members_can_add_members': 'on',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.group.refresh_from_db()
        self.assertEqual(self.group.name, 'Member Edited Name')
        self.assertTrue(self.group.members_can_add_members)

    def test_last_owner_is_not_removed(self):
        participant = self.group.participants.get(user=self.owner)
        with self.assertRaises(ValidationError):
            remove_member(self.group, participant)

    def test_owner_leaving_transfers_ownership(self):
        allow_additions = add_members(self.group, [self.other])
        self.assertEqual(allow_additions, 1)
        leave_group(self.group, self.owner)
        self.assertFalse(
            self.group.participants.filter(user=self.owner).exists()
        )
        replacement = self.group.participants.get(user=self.member)
        self.assertEqual(
            replacement.role, ConversationParticipant.ROLE_OWNER,
        )

    def test_leaving_an_empty_group_deletes_it(self):
        solo = self.make_group(name='Solo group')
        leave_group(solo, self.owner)
        self.assertFalse(Conversation.objects.filter(pk=solo.pk).exists())


class AttachmentTests(CommunicationsBase):
    def setUp(self):
        super().setUp()
        self.group = self.make_group(members=[self.member])

    def test_disallowed_extension_is_rejected(self):
        response = self.client.post(
            reverse('communications:send_message', args=[self.group.pk]),
            {
                'body': 'Please run this',
                'attachment': SimpleUploadedFile(
                    'payload.exe', b'MZ-not-allowed', content_type='application/x-msdownload',
                ),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Message.objects.filter(body='Please run this').exists())
        self.assertFalse(MessageAttachment.objects.exists())

    def test_empty_attachment_is_rejected(self):
        response = self.client.post(
            reverse('communications:send_message', args=[self.group.pk]),
            {
                'body': 'Empty file',
                'attachment': SimpleUploadedFile('empty.txt', b''),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Message.objects.filter(body='Empty file').exists())

    def test_oversized_attachment_is_rejected(self):
        # Keep the request tiny while exercising the size branch: the form
        # compares against this module constant, so lower it for the test.
        with mock.patch('communications.forms.MAX_ATTACHMENT_SIZE', 5):
            oversized = SimpleUploadedFile('large.txt', b'more than five')
            response = self.client.post(
                reverse('communications:send_message', args=[self.group.pk]),
                {'body': 'Too large', 'attachment': oversized},
            )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Message.objects.filter(body='Too large').exists())

    def test_allowed_attachment_uses_private_storage(self):
        response = self.client.post(
            reverse('communications:send_message', args=[self.group.pk]),
            {
                'body': 'Minutes attached',
                'attachment': SimpleUploadedFile(
                    'minutes.txt', b'Approved minutes', content_type='text/plain',
                ),
            },
        )
        self.assertEqual(response.status_code, 302)
        attachment = MessageAttachment.objects.get()
        self.assertEqual(attachment.original_name, 'minutes.txt')
        self.assertIn('txt', ALLOWED_ATTACHMENT_EXTENSIONS)
        self.assertTrue(attachment.file.name.startswith('communications/'))
        self.assertIn('private_media', attachment.file.path.replace('\\', '/'))
        self.assertNotIn('\\media\\', attachment.file.path)

    def test_attachment_download_is_limited_to_participants(self):
        self.client.post(
            reverse('communications:send_message', args=[self.group.pk]),
            {
                'body': 'Private file',
                'attachment': SimpleUploadedFile(
                    'private.txt', b'secret bytes', content_type='text/plain',
                ),
            },
        )
        attachment = MessageAttachment.objects.get()
        url = reverse('communications:download_attachment', args=[attachment.pk])

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertEqual(b''.join(response.streaming_content), b'secret bytes')

        outsider_client = self.login(self.outsider)
        self.assertEqual(outsider_client.get(url).status_code, 404)

        anonymous = Client()
        self.assertEqual(anonymous.get(url).status_code, 302)


class SearchAndIsolationTests(CommunicationsBase):
    def setUp(self):
        super().setUp()
        self.operations = self.make_group(name='Operations')
        self.finance = self.make_group(name='Finance')
        self.send(self.operations, self.owner, 'Sunday rota is ready')
        self.send(self.finance, self.owner, 'Budget review on Friday')

    def test_conversation_search_matches_name_and_message_body(self):
        by_name = conversation_summaries(self.owner, 'finance')
        self.assertEqual([row['display_name'] for row in by_name], ['Finance'])
        by_body = conversation_summaries(self.owner, 'rota')
        self.assertEqual([row['display_name'] for row in by_body], ['Operations'])

    def test_message_search_is_scoped_to_the_conversation(self):
        matches = message_queryset(self.operations, 'rota')
        self.assertEqual(matches.count(), 1)
        self.assertEqual(matches.get().body, 'Sunday rota is ready')
        self.assertEqual(message_queryset(self.finance, 'rota').count(), 0)

    def test_portal_search_fragment_only_returns_matches(self):
        response = self.client.get(
            reverse('communications:conversation_list') + '?q=finance',
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Finance')
        self.assertNotContains(response, 'Operations')

    def test_selected_conversation_message_search(self):
        response = self.client.get(
            reverse('communications:conversation_workspace', args=[self.finance.pk])
            + '?mq=budget',
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Budget review on Friday')
        self.assertNotContains(response, 'Sunday rota is ready')

    def test_contact_inbox_is_kept_separate_from_internal_messages(self):
        contact = ContactMessage.objects.create(
            name='Visitor',
            email='visitor@example.com',
            subject='Prayer request',
            message='Please pray for our family.',
        )
        self.group = self.make_group(name='Internal only')
        self.send(self.group, self.owner, 'Internal staff note')

        response = self.client.get(reverse('communications:inbox'))
        self.assertNotContains(response, 'Please pray for our family.')
        self.assertNotContains(response, 'Prayer request')
        self.assertEqual(ContactMessage.objects.count(), 1)
        self.assertTrue(ContactMessage.objects.filter(pk=contact.pk).exists())
        self.assertEqual(
            Notification.objects.filter(
                source_type='admin_message',
                category='contact',
            ).count(),
            0,
        )
