from django.contrib.auth.models import User
from django.test import TestCase
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
        # Menu-driven dashboard: one card per permitted sidebar section.
        self.assertContains(response, 'sboi-app__title')
        self.assertContains(response, reverse('admin_section', args=['home']))

    def test_dashboard_hides_sections_without_permission(self):
        user = User.objects.create_user('staff', 'staff@example.com', 'pw', is_staff=True)
        self.client.force_login(user)
        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.status_code, 200)
        # Permission-filtered, exactly like the sidebar: no permission, no card.
        self.assertNotContains(response, 'sboi-app__title')

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

    def test_section_page_hidden_without_permission(self):
        user = User.objects.create_user('staff', 'staff@example.com', 'pw', is_staff=True)
        self.client.force_login(user)
        response = self.client.get(reverse('admin_section', args=['home']))
        self.assertEqual(response.status_code, 404)
