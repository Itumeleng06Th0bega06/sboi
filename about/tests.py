from django.test import TestCase
from django.urls import reverse

from .models import ChurchProfile, Leader


class AboutSubPageTests(TestCase):
    def setUp(self):
        self.profile = ChurchProfile.objects.create(
            church_name='Shekinah Blaze Outreach International',
            tagline='Governed by Heaven, Established on Earth',
            founder_message='Founder body text.',
            story=(
                'A Vision Born from God’s Calling\n\n'
                'First story paragraph.\n\n'
                'Looking Toward the Future\n\n'
                'Final story paragraph.'
            ),
            story_subtitle='The journey so far',
            vision='Vision statement text.',
            mission='Mission statement text.',
        )
        Leader.objects.create(name='Pastor Example', role='Lead Pastor')

    def test_each_about_page_renders_its_own_template(self):
        pages = {
            'about': 'about/overview.html',
            'leadership': 'about/leadership.html',
            'founder': 'about/founder.html',
            'story': 'about/story.html',
            'vision': 'about/vision.html',
            'mission': 'about/mission.html',
        }
        for name, template in pages.items():
            with self.subTest(page=name):
                response = self.client.get(reverse(f'about:{name}'))
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, template)

    def test_overview_links_to_each_sub_page(self):
        response = self.client.get(reverse('about:about'))
        for name in ('leadership', 'founder', 'story', 'vision', 'mission'):
            with self.subTest(page=name):
                self.assertContains(response, reverse(f'about:{name}'))
                self.assertContains(response, f'id="ch-{name}"')

    def test_navigation_uses_sub_page_urls(self):
        response = self.client.get(reverse('about:about'))
        for name in ('leadership', 'founder', 'story', 'vision', 'mission'):
            with self.subTest(page=name):
                self.assertContains(response, reverse(f'about:{name}'))
        self.assertNotContains(response, f"{reverse('about:about')}#ch-")

    def test_content_lives_on_its_own_page(self):
        founder = self.client.get(reverse('about:founder'))
        self.assertContains(founder, 'Founder body text.')

        story = self.client.get(reverse('about:story'))
        self.assertContains(story, 'First story paragraph.')
        self.assertContains(story, 'Final story paragraph.')

        vision = self.client.get(reverse('about:vision'))
        self.assertContains(vision, 'Vision statement text.')

        mission = self.client.get(reverse('about:mission'))
        self.assertContains(mission, 'Mission statement text.')

        leadership = self.client.get(reverse('about:leadership'))
        self.assertContains(leadership, 'Pastor Example')

        overview = self.client.get(reverse('about:about'))
        self.assertNotContains(overview, 'Founder body text.')
        self.assertNotContains(overview, 'First story paragraph.')
        self.assertNotContains(overview, 'Vision statement text.')
        self.assertNotContains(overview, 'Mission statement text.')

    def test_empty_sections_are_not_linked(self):
        ChurchProfile.objects.all().delete()
        Leader.objects.all().delete()
        response = self.client.get(reverse('about:about'))
        for name in ('leadership', 'founder', 'story', 'vision', 'mission'):
            with self.subTest(page=name):
                self.assertNotContains(response, reverse(f'about:{name}'))
