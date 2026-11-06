from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from contact.models import ContactMessage
from members import services as member_services

from . import services
from .models import Notification, NotificationState

User = get_user_model()


class NotificationFilteringTests(TestCase):
    def setUp(self):
        self.member = User.objects.create_user(
            'member', 'member@example.com', 'pw',
        )
        self.other_member = User.objects.create_user(
            'other', 'other@example.com', 'pw',
        )
        self.staff = User.objects.create_superuser(
            'staff', 'staff@example.com', 'pw',
        )
        self.other_staff = User.objects.create_superuser(
            'staff2', 'staff2@example.com', 'pw',
        )

    def make(self, **overrides):
        values = {
            'audience': Notification.AUDIENCE_PUBLIC,
            'category': 'test',
            'source_type': 'test',
            'source_key': f'test:{Notification.objects.count() + 1}',
            'title': 'Test notification',
            'status': Notification.STATUS_ACTIVE,
            'requires_action': False,
        }
        values.update(overrides)
        return Notification.objects.create(**values)

    def feed(self, user=None):
        if user is not None:
            self.client.force_login(user)
        else:
            self.client.logout()
        response = self.client.get(reverse('notifications:feed'))
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_read_informational_notification_is_hidden_from_bell(self):
        notification = self.make(title='Already read')
        NotificationState.objects.create(
            notification=notification,
            user=self.member,
            read_at=timezone.now(),
        )

        data = self.feed(self.member)

        self.assertNotIn('Already read', [item['title'] for item in data['items']])
        self.assertEqual(data['badge'], 0)

    def test_read_actionable_notification_stays_visible(self):
        notification = self.make(
            title='Please review',
            status=Notification.STATUS_PENDING,
            requires_action=True,
        )
        NotificationState.objects.create(
            notification=notification,
            user=self.member,
            read_at=timezone.now(),
        )

        data = self.feed(self.member)

        titles = [item['title'] for item in data['items']]
        self.assertIn('Please review', titles)
        self.assertEqual(data['badge'], 0)

    def test_resolved_expired_and_dismissed_are_hidden(self):
        now = timezone.now()
        self.make(title='Resolved', status=Notification.STATUS_RESOLVED)
        self.make(
            title='Expired',
            status=Notification.STATUS_ACTIVE,
            expires_at=now - timedelta(minutes=1),
        )
        dismissed = self.make(title='Dismissed')
        NotificationState.objects.create(
            notification=dismissed,
            user=self.member,
            dismissed_at=now,
        )
        self.make(title='Still open')

        data = self.feed(self.member)
        titles = [item['title'] for item in data['items']]

        self.assertEqual(titles, ['Still open'])

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    )
    def test_history_keeps_read_and_dismissed_rows(self):
        read = self.make(title='Read history')
        dismissed = self.make(title='Dismissed history')
        NotificationState.objects.create(
            notification=read, user=self.member, read_at=timezone.now(),
        )
        NotificationState.objects.create(
            notification=dismissed,
            user=self.member,
            dismissed_at=timezone.now(),
        )

        self.client.force_login(self.member)
        response = self.client.get(reverse('notifications:history'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Read history')
        self.assertContains(response, 'Dismissed history')

    def test_visitor_only_sees_public_notifications(self):
        self.make(title='Public notice', audience=Notification.AUDIENCE_PUBLIC)
        self.make(
            title='Member only',
            audience=Notification.AUDIENCE_MEMBER,
            recipient=self.member,
        )
        self.make(title='Staff only', audience=Notification.AUDIENCE_STAFF)

        data = self.feed()

        self.assertEqual([item['title'] for item in data['items']], ['Public notice'])

    def test_member_sees_own_member_notification_not_another_members(self):
        self.make(
            title='For this member',
            audience=Notification.AUDIENCE_MEMBER,
            recipient=self.member,
        )
        self.make(
            title='For another member',
            audience=Notification.AUDIENCE_MEMBER,
            recipient=self.other_member,
        )
        self.make(title='For staff', audience=Notification.AUDIENCE_STAFF)

        data = self.feed(self.member)

        self.assertEqual(
            [item['title'] for item in data['items']],
            ['For this member'],
        )

    def test_admin_bell_is_staff_only_and_read_state_is_per_admin(self):
        shared = self.make(
            title='Shared admin task',
            audience=Notification.AUDIENCE_STAFF,
            status=Notification.STATUS_PENDING,
            requires_action=False,
        )
        self.make(title='Public notice', audience=Notification.AUDIENCE_PUBLIC)

        self.client.force_login(self.staff)
        self.client.post(reverse('notifications:read', args=[shared.pk]))
        first = self.client.get(reverse('admin_notifications')).json()
        self.assertNotIn(
            'Shared admin task', [item['title'] for item in first['items']],
        )
        self.assertNotIn(
            'Public notice', [item['title'] for item in first['items']],
        )

        self.client.force_login(self.other_staff)
        second = self.client.get(reverse('admin_notifications')).json()
        self.assertIn(
            'Shared admin task', [item['title'] for item in second['items']],
        )

        shared.refresh_from_db()
        self.assertEqual(shared.status, Notification.STATUS_PENDING)

    def test_dismiss_hides_from_bell_without_deleting_history(self):
        notification = self.make(title='Dismiss me')

        self.client.force_login(self.member)
        response = self.client.post(
            reverse('notifications:dismiss', args=[notification.pk]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)

        feed = self.client.get(reverse('notifications:feed')).json()
        self.assertNotIn('Dismiss me', [item['title'] for item in feed['items']])
        self.assertTrue(Notification.objects.filter(pk=notification.pk).exists())

        history = self.client.get(reverse('notifications:history'))
        self.assertContains(history, 'Dismiss me')

    def test_admin_cannot_see_public_items_in_history(self):
        self.make(title='Public history', audience=Notification.AUDIENCE_PUBLIC)
        self.make(title='Staff history', audience=Notification.AUDIENCE_STAFF)

        self.client.force_login(self.staff)
        response = self.client.get(reverse('admin_notifications_history'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Staff history')
        self.assertNotContains(response, 'Public history')


    def test_opening_a_notification_marks_it_read_and_follows_its_link(self):
        notification = self.make(
            title='Read on open',
            audience=Notification.AUDIENCE_MEMBER,
            recipient=self.member,
            url=reverse('members:account_messages'),
        )
        self.client.force_login(self.member)
        response = self.client.get(
            reverse('notifications:open', args=[notification.pk]),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('members:account_messages'))
        state = NotificationState.objects.get(
            notification=notification, user=self.member,
        )
        self.assertIsNotNone(state.read_at)

        feed = self.client.get(reverse('notifications:feed')).json()
        self.assertNotIn('Read on open', [item['title'] for item in feed['items']])
        self.assertEqual(feed['badge'], 0)

    def test_member_cannot_open_another_members_notification(self):
        notification = self.make(
            audience=Notification.AUDIENCE_MEMBER,
            recipient=self.other_member,
        )
        self.client.force_login(self.member)
        response = self.client.get(
            reverse('notifications:open', args=[notification.pk]),
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(
            NotificationState.objects.filter(
                notification=notification, user=self.member,
            ).exists()
        )

    def test_open_never_redirects_to_an_external_site(self):
        notification = self.make(
            audience=Notification.AUDIENCE_MEMBER,
            recipient=self.member,
            url='https://example.com/phishing',
        )
        self.client.force_login(self.member)
        response = self.client.get(
            reverse('notifications:open', args=[notification.pk]),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('members:account_notifications'))

        public = self.make(title='Public external', url='https://example.com')
        self.client.logout()
        response = self.client.get(
            reverse('notifications:open', args=[public.pk]),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('notifications:history'))

    def test_bell_payload_includes_the_safe_open_link(self):
        notification = self.make(
            audience=Notification.AUDIENCE_MEMBER,
            recipient=self.member,
            url=reverse('members:account_messages'),
        )
        data = self.feed(self.member)
        item = next(
            row for row in data['items'] if row['title'] == notification.title
        )
        self.assertEqual(
            item['open_url'],
            reverse('notifications:open', args=[notification.pk]),
        )


class NotificationSourceSyncTests(TestCase):
    def setUp(self):
        self.member = User.objects.create_user(
            'member', 'member@example.com', 'pw',
        )
        self.staff = User.objects.create_superuser(
            'staff', 'staff@example.com', 'pw',
        )

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    )
    def test_member_message_creates_admin_task_but_admin_reply_does_not(self):
        member_message = ContactMessage.objects.create(
            name='Member',
            email='member@example.com',
            message='Please help',
            user=self.member,
            sender=self.member,
        )
        task = Notification.objects.get(source_key=f'contact:{member_message.pk}')
        self.assertEqual(task.audience, Notification.AUDIENCE_STAFF)
        self.assertEqual(task.title, 'Unread member messages')

        admin_reply = ContactMessage.objects.create(
            name='Church office',
            email='office@example.com',
            message='We can help',
            user=self.member,
            sender=self.staff,
            is_from_admin=True,
            read_by_member=False,
        )
        self.assertFalse(
            Notification.objects.filter(
                source_key=f'contact:{admin_reply.pk}',
                status__in=Notification.OPEN_STATUSES,
            ).exists()
        )

        notification, created = member_services.notify_member_reply(admin_reply)
        self.assertTrue(created)
        self.assertEqual(notification.audience, Notification.AUDIENCE_MEMBER)
        self.assertEqual(notification.recipient, self.member)
        # One email from sync_contact_message (member message) + one from
        # notify_member_reply (admin reply).
        self.assertEqual(len(mail.outbox), 2)

    def test_membership_decision_creates_one_member_notice(self):
        from members.models import ChurchMembership, MembershipChangeRequest

        membership = ChurchMembership.objects.create(
            user=self.member,
            status='pending',
        )
        change = MembershipChangeRequest.objects.create(
            membership=membership,
            submitted_by=self.member,
            kind=MembershipChangeRequest.KIND_APPLICATION,
        )

        change, notification, created = member_services.apply_membership_decision(
            change.pk, self.staff, approve=True,
        )

        self.assertTrue(created)
        membership.refresh_from_db()
        self.assertEqual(membership.status, 'active')
        self.assertEqual(notification.recipient, self.member)
        self.assertEqual(notification.title, 'Membership approved')
        self.assertEqual(
            Notification.objects.filter(
                recipient=self.member,
                source_type='membership_member',
                status__in=Notification.OPEN_STATUSES,
            ).count(),
            1,
        )
