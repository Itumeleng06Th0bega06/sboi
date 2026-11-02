"""Acceptance tests for the private member ↔ administration inbox."""
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from members.models import ChurchMembership
from notifications.models import Notification

from .models import ALLOWED_MESSAGE_ATTACHMENT_EXTENSIONS, ContactMessage

User = get_user_model()
STRONG = 'ComplexPassw0rd!'


class MemberInboxTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.member_user = User.objects.create_user(
            'member1', 'member1@example.com', STRONG,
            first_name='Ada', last_name='Okoye',
        )
        cls.member = ChurchMembership.objects.create(
            user=cls.member_user,
            phone='+27123456789',
            whatsapp_consent=True,
        )
        cls.other_user = User.objects.create_user(
            'other', 'other@example.com', STRONG,
            first_name='Ben', last_name='Mokoena',
        )
        ChurchMembership.objects.create(user=cls.other_user)
        cls.admin = User.objects.create_superuser(
            'admin', 'admin@example.com', STRONG,
        )

    def setUp(self):
        self.client = Client()
        Notification.objects.all().delete()
        ContactMessage.objects.all().delete()

    def test_anonymous_member_cannot_access_inbox(self):
        response = self.client.get(reverse('members:account_messages'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.url)

    def test_anonymous_member_cannot_post_message(self):
        response = self.client.post(
            reverse('members:account_message_send'),
            {'message': 'Hello'},
        )
        self.assertEqual(response.status_code, 302)

    def test_member_can_start_conversation_and_see_history(self):
        self.client.force_login(self.member_user)
        response = self.client.post(
            reverse('members:account_message_send'),
            {'message': 'Please pray for my family.'},
        )
        self.assertIn(response.status_code, (200, 302))
        thread = list(ContactMessage.objects.filter(user=self.member_user))
        self.assertEqual(len(thread), 1)
        self.assertEqual(thread[0].message, 'Please pray for my family.')
        self.assertFalse(thread[0].is_from_admin)

        inbox = self.client.get(reverse('members:account_messages'))
        self.assertEqual(inbox.status_code, 200)
        self.assertContains(inbox, 'Please pray for my family')

    def test_public_contact_form_still_works(self):
        response = self.client.post(
            reverse('contact:contact'),
            {
                'name': 'Visitor',
                'email': 'visitor@example.com',
                'phone': '',
                'subject': 'General',
                'message': 'Just saying hello',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            ContactMessage.objects.filter(
                email='visitor@example.com', user__isnull=True,
            ).exists()
        )

    def test_member_message_creates_staff_notification(self):
        self.client.force_login(self.member_user)
        self.client.post(
            reverse('members:account_message_send'),
            {'message': 'I need assistance with transport.'},
        )
        msg = ContactMessage.objects.get(user=self.member_user)
        staff_note = Notification.objects.filter(
            source_type='contact', source_id=msg.pk,
        )
        self.assertTrue(staff_note.exists())

    def test_admin_bulk_mark_read_closes_staff_notification(self):
        self.client.force_login(self.member_user)
        self.client.post(
            reverse('members:account_message_send'),
            {'message': 'Please mark this thread read.'},
        )
        msg = ContactMessage.objects.get(user=self.member_user)
        notification = Notification.objects.get(
            source_type='contact', source_id=msg.pk,
        )
        self.assertEqual(notification.status, Notification.STATUS_PENDING)

        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('admin:contact_contactmessage_changelist'),
            {
                'action': 'mark_read',
                '_selected_action': [str(msg.pk)],
                'index': '0',
            },
        )
        self.assertIn(response.status_code, (200, 302))
        notification.refresh_from_db()
        self.assertEqual(notification.status, Notification.STATUS_RESOLVED)

    def test_admin_can_start_conversation_with_member_with_no_prior_contact(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('admin:contact_contactmessage_compose'))
        self.assertEqual(response.status_code, 200)
        choices = response.context['form'].fields['membership'].queryset
        self.assertIn(self.member, choices)

        response = self.client.post(
            reverse('admin:contact_contactmessage_compose'),
            {
                'membership': self.member.pk,
                'subject': 'Welcome',
                'message': 'Welcome to the private inbox. Feel free to reply.',
            },
        )
        self.assertEqual(response.status_code, 302)
        msg = ContactMessage.objects.get(user=self.member_user, is_from_admin=True)
        self.assertEqual(msg.message, 'Welcome to the private inbox. Feel free to reply.')
        note = Notification.objects.filter(
            recipient=self.member_user, source_type='contact_reply', source_id=msg.pk,
        )
        self.assertTrue(note.exists())
        self.assertEqual(note.first().title, 'New message from church administration')

    def test_admin_reply_creates_notification_and_marks_unread_for_member(self):
        self.client.force_login(self.admin)
        member_msg = ContactMessage.objects.create(
            user=self.member_user,
            name='Ada Okoye',
            email='member1@example.com',
            subject='Prayer',
            message='Please pray for healing.',
            is_from_admin=False,
            is_read=False,
        )
        response = self.client.post(
            reverse('admin:contact_contactmessage_conversation', args=[member_msg.pk]),
            {'message': 'We are praying with you.'},
        )
        self.assertEqual(response.status_code, 302)
        reply = ContactMessage.objects.get(
            user=self.member_user, is_from_admin=True, parent=member_msg,
        )
        self.assertEqual(reply.read_by_member, False)
        note = Notification.objects.filter(
            recipient=self.member_user, source_type='contact_reply', source_id=reply.pk,
        )
        self.assertTrue(note.exists())
        self.assertEqual(note.first().title, 'New reply from church administration')

    def test_admin_reply_retry_does_not_duplicate(self):
        self.client.force_login(self.admin)
        member_msg = ContactMessage.objects.create(
            user=self.member_user,
            name='Ada Okoye',
            email='member1@example.com',
            subject='Prayer',
            message='Please pray.',
            is_from_admin=False,
            is_read=False,
        )
        url = reverse(
            'admin:contact_contactmessage_conversation', args=[member_msg.pk],
        )
        first = self.client.post(url, {'message': 'Praying with you.'})
        second = self.client.post(url, {'message': 'Praying with you.'})
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        replies = ContactMessage.objects.filter(
            user=self.member_user, is_from_admin=True,
            message='Praying with you.',
        )
        self.assertEqual(replies.count(), 1)
        self.assertEqual(
            Notification.objects.filter(
                source_type='contact_reply', source_id=replies.first().pk,
            ).count(),
            1,
        )

    def test_member_replies_notify_admin(self):
        self.client.force_login(self.admin)
        member_msg = ContactMessage.objects.create(
            user=self.member_user,
            name='Ada Okoye',
            email='member1@example.com',
            subject='Question',
            message='What time is Bible study?',
            is_from_admin=False,
            is_read=True,
        )
        self.client.force_login(self.member_user)
        Notification.objects.filter(source_type='contact', source_id=member_msg.pk).delete()
        response = self.client.post(
            reverse('members:account_message_send'),
            {'message': 'Is it still at 18:00?'},
        )
        self.assertIn(response.status_code, (200, 302))
        reply = ContactMessage.objects.get(
            user=self.member_user, is_from_admin=False, message__contains='18:00',
        )
        staff_note = Notification.objects.filter(
            source_type='contact', source_id=reply.pk,
        )
        self.assertTrue(staff_note.exists())

    def test_opening_messages_marks_read_and_resolves_notifications(self):
        self.client.force_login(self.admin)
        reply = ContactMessage.objects.create(
            user=self.member_user,
            name='Admin',
            email='admin@example.com',
            subject='Prayer',
            message='We prayed for you.',
            is_from_admin=True,
            is_read=True,
            read_by_member=False,
        )
        Notification.objects.create(
            recipient=self.member_user,
            audience='member',
            category='contact',
            source_type='contact_reply',
            source_id=reply.pk,
            source_key=f'contact_reply:{reply.pk}',
            title='New reply from church administration',
            body='We prayed for you.',
            url=reverse('members:account_messages'),
            status='active',
        )
        self.client.force_login(self.member_user)
        response = self.client.get(reverse('members:account_messages'))
        self.assertEqual(response.status_code, 200)
        reply.refresh_from_db()
        self.assertTrue(reply.read_by_member)
        note = Notification.objects.get(
            recipient=self.member_user, source_type='contact_reply', source_id=reply.pk,
        )
        self.assertTrue(
            note.states.filter(
                user=self.member_user, read_at__isnull=False,
            ).exists()
        )

    def test_notification_dedup_on_retry(self):
        self.client.force_login(self.admin)
        msg = ContactMessage.objects.create(
            user=self.member_user,
            name='Admin',
            email='admin@example.com',
            subject='Hello',
            message='Hello member',
            is_from_admin=True,
            is_read=True,
            read_by_member=False,
        )
        from members import services
        n1, c1 = services.notify_member_reply(msg)
        n2, c2 = services.notify_member_reply(msg)
        self.assertTrue(c1)
        self.assertFalse(c2)
        self.assertEqual(n1.pk, n2.pk)
        self.assertEqual(
            Notification.objects.filter(
                recipient=self.member_user, source_type='contact_reply', source_id=msg.pk,
            ).count(),
            1,
        )

    def test_admin_views_require_contact_permission(self):
        staff = User.objects.create_user(
            'staff', 'staff@example.com', STRONG, is_staff=True,
        )
        self.client.force_login(staff)
        for name in (
            'admin:contact_contactmessage_inbox',
            'admin:contact_contactmessage_compose',
        ):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 403, name)

    def test_admin_inbox_shows_awaiting_reply_and_counts(self):
        self.client.force_login(self.admin)
        ContactMessage.objects.create(
            user=self.member_user,
            name='Ada Okoye',
            email='member1@example.com',
            subject='Help',
            message='I need help.',
            is_from_admin=False,
            is_read=False,
        )
        response = self.client.get(reverse('admin:contact_contactmessage_inbox'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'member1@example.com')
        self.assertContains(response, 'Awaiting reply')
        self.assertEqual(response.context['total_awaiting'], 1)

    def test_admin_can_see_member_read_status_and_reply(self):
        self.client.force_login(self.admin)
        reply = ContactMessage.objects.create(
            user=self.member_user,
            name='Admin',
            email='admin@example.com',
            subject='Hello',
            message='Hi there',
            is_from_admin=True,
            is_read=True,
            read_by_member=False,
        )
        member_msg = ContactMessage.objects.create(
            user=self.member_user,
            name='Ada Okoye',
            email='member1@example.com',
            subject='Hello',
            message='Thanks',
            parent=reply,
            is_from_admin=False,
            is_read=True,
        )
        response = self.client.get(
            reverse('admin:contact_contactmessage_conversation', args=[member_msg.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Unread by member')
        self.assertContains(response, 'Awaiting your reply')

    def test_member_cannot_see_other_members_conversation(self):
        self.client.force_login(self.member_user)
        ContactMessage.objects.create(
            user=self.other_user,
            name='Ben Mokoena',
            email='other@example.com',
            subject='Private',
            message='Secret',
            is_from_admin=False,
        )
        response = self.client.get(reverse('members:account_messages'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Secret')

    def test_attachment_privacy_for_member(self):
        self.client.force_login(self.member_user)
        msg = ContactMessage.objects.create(
            user=self.member_user,
            name='Ada Okoye',
            email='member1@example.com',
            subject='Doc',
            message='See attached',
            attachment=SimpleUploadedFile('note.txt', b'hello'),
        )
        response = self.client.get(reverse('contact:attachment', args=[msg.pk]))
        self.assertEqual(response.status_code, 200)

        self.client.force_login(self.other_user)
        response = self.client.get(reverse('contact:attachment', args=[msg.pk]))
        self.assertEqual(response.status_code, 404)

    def test_duplicate_message_within_twenty_seconds_blocked(self):
        self.client.force_login(self.member_user)
        r1 = self.client.post(
            reverse('members:account_message_send'),
            {'message': 'Same message again'},
        )
        self.assertIn(r1.status_code, (200, 302))
        r2 = self.client.post(
            reverse('members:account_message_send'),
            {'message': 'Same message again'},
        )
        self.assertIn(r2.status_code, (200, 302))
        self.assertEqual(
            ContactMessage.objects.filter(
                user=self.member_user, message='Same message again',
            ).count(),
            1,
        )

    @override_settings(
        WHATSAPP_API_URL='https://example.com/send',
        WHATSAPP_API_TOKEN='tok',
        WHATSAPP_SENDER_ID='123',
    )
    def test_whatsapp_generic_no_confidential_content(self):
        self.client.force_login(self.admin)
        msg = ContactMessage.objects.create(
            user=self.member_user,
            name='Ada Okoye',
            email='member1@example.com',
            subject='Top secret subject',
            message='This is confidential details',
            is_from_admin=True,
            is_read=True,
            read_by_member=False,
        )
        with mock.patch('urllib.request.urlopen') as m:
            m.return_value.status = 200
            m.return_value.__enter__ = mock.Mock(return_value=m.return_value)
            m.return_value.__exit__ = mock.Mock(return_value=False)
            from members import services
            services.notify_member_reply(msg)
            self.assertTrue(m.called)
            body = m.call_args[0][0].data.decode()
            self.assertNotIn('confidential', body)
            self.assertNotIn('Top secret', body)
            self.assertIn('Sign in to your account', body)
            self.assertIn('private message', body)
