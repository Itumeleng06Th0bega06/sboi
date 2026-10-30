from io import StringIO
from urllib.parse import urlsplit

from django.contrib.auth.models import User
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from about.models import ChurchProfile
from blackboard.models import Event, EventRsvp, MemberProfile
from contact.models import ContactInfo, ContactMessage

from .models import Subscriber, Testimony


class SiteSmokeTests(TestCase):
    def setUp(self):
        ChurchProfile.objects.create(church_name='Shekinah Blaze Outreach International')
        ContactInfo.objects.create(church_name='Shekinah Blaze Outreach International')

    def test_public_pages_render(self):
        for url in ['home:home', 'about:about', 'gallery:gallery', 'contact:contact']:
            response = self.client.get(reverse(url))
            self.assertEqual(response.status_code, 200, url)

    def test_auth_pages_render(self):
        for url in ['members:login', 'members:register']:
            response = self.client.get(reverse(url))
            self.assertEqual(response.status_code, 200, url)

    def test_blackboard_requires_login(self):
        response = self.client.get(reverse('blackboard:blackboard'))
        self.assertEqual(response.status_code, 302)

    def test_subscribe_saves_and_dedupes(self):
        url = reverse('home:subscribe')
        self.client.post(url, {'email': 'a@example.com'})
        self.client.post(url, {'email': 'a@example.com'})
        self.assertEqual(Subscriber.objects.filter(email='a@example.com').count(), 1)

    def test_admin_notifications_present_for_staff(self):
        user = User.objects.create_superuser('admin', 'admin@example.com', 'pw')
        ContactMessage.objects.create(name='N', email='n@example.com', message='Hi')
        Testimony.objects.create(name='T', message='Testimony')
        Event.objects.create(title='E')
        EventRsvp.objects.create(event=Event.objects.first(), name='R')
        MemberProfile.objects.create(user=user)
        self.client.force_login(user)
        response = self.client.get(reverse('admin_notifications'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Unread contact messages')

    def test_dashboard_lists_modules_for_staff(self):
        user = User.objects.create_superuser('admin', 'admin@example.com', 'pw')
        self.client.force_login(user)
        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.status_code, 200)
        # Menu-driven dashboard: one card per admin section.
        self.assertContains(response, 'sboi-app__title')
        self.assertContains(response, reverse('admin_section', args=['home']))

    def test_dashboard_shows_locked_sections_without_permission(self):
        user = User.objects.create_user('staff', 'staff@example.com', 'pw', is_staff=True)
        self.client.force_login(user)
        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.status_code, 200)
        # Every section is visible; unassigned ones are greyed out with a lock.
        self.assertContains(response, 'sboi-app__title')
        self.assertContains(response, 'sboi-app--locked')
        self.assertContains(response, reverse('admin_section', args=['home']))
        self.assertEqual(
            self.client.get(reverse('admin_section', args=['home'])).status_code,
            403,
        )

    def test_section_page_lists_submenus(self):
        user = User.objects.create_superuser('admin', 'admin@example.com', 'pw')
        self.client.force_login(user)
        response = self.client.get(reverse('admin_section', args=['home']))
        self.assertEqual(response.status_code, 200)
        # Sub-menus are the section's models, linking to their real admin pages.
        self.assertContains(response, 'sboi-tile')
        self.assertContains(response, reverse('admin:home_homestat_changelist'))
        # A back tab returns to the dashboard.
        self.assertContains(response, reverse('admin:index'))

    def test_section_page_denied_without_permission(self):
        user = User.objects.create_user('staff', 'staff@example.com', 'pw', is_staff=True)
        self.client.force_login(user)
        response = self.client.get(reverse('admin_section', args=['home']))
        self.assertEqual(response.status_code, 403)
        self.assertContains(
            response,
            "You don't have permission to open this section",
            status_code=403,
        )


class AdminPasswordResetTests(TestCase):
    """The admin "forgot password" flow and the offline recovery command."""

    def setUp(self):
        mail.outbox.clear()
        self.user = User.objects.create_user(
            'resetme', 'resetme@example.com', 'old-pass-123', is_staff=True,
        )

    def _request_reset(self):
        response = self.client.post(
            reverse('admin_password_reset'), {'email': 'resetme@example.com'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        for token in mail.outbox[0].body.split():
            if '/reset/' in token and token.startswith('http'):
                return token
        self.fail('No reset link found in the reset email.')

    def test_login_page_links_to_reset(self):
        response = self.client.get(reverse('admin:login'))
        self.assertContains(response, reverse('admin_password_reset'))

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    )
    def test_reset_email_sets_a_new_password(self):
        link = self._request_reset()
        path = urlsplit(link).path
        # The first GET hands the token over to the set-password step.
        final = self.client.get(path, follow=True).redirect_chain[-1][0]
        response = self.client.post(final, {
            'new_password1': 'brand-new-pass-987',
            'new_password2': 'brand-new-pass-987',
        })
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('brand-new-pass-987'))

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    )
    def test_reset_link_is_single_use(self):
        link = self._request_reset()
        path = urlsplit(link).path
        final = self.client.get(path, follow=True).redirect_chain[-1][0]
        self.client.post(final, {
            'new_password1': 'brand-new-pass-987',
            'new_password2': 'brand-new-pass-987',
        })
        response = self.client.get(path, follow=True)
        self.assertContains(response, 'Link expired')

    def test_recovery_command_prints_a_working_link(self):
        out = StringIO()
        call_command('reset_admin_password', 'resetme', stdout=out)
        self.assertIn('resetme', out.getvalue())
        link = next(t for t in out.getvalue().split() if t.startswith('http'))
        response = self.client.get(urlsplit(link).path, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Set a new password')
