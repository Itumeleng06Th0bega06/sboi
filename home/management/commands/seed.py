from django.core.management.base import BaseCommand
from django.conf import settings
from pathlib import Path
import re
from datetime import date, timedelta

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from about.manual_texts import MANUAL
from about.models import (
    ChurchProfile,
    CoreValue,
    Leader,
    MissionAction,
    MissionComponent,
    PathwayStep,
    VisionPillar,
)
from blackboard.models import Announcement, Devotion
from contact.models import ContactInfo
from gallery.models import SliderImage
from home.models import FeaturedSection, HomeStat

STATIC = Path(settings.BASE_DIR) / 'static' / 'images'


def _safe_name(name: str) -> str:
    """Cloudinary public IDs cannot contain spaces or unusual characters."""
    return re.sub(r'[^A-Za-z0-9._-]+', '_', name).strip('_')


def copy(src: Path, sub: str) -> str:
    """Upload a static image to the default media storage (Cloudinary in
    production, local disk in development) and return its relative path."""
    if not src.exists():
        return ''
    dst = f'{sub}/{_safe_name(src.name)}'
    if not default_storage.exists(dst):
        default_storage.save(dst, ContentFile(src.read_bytes()))
    return dst


def img(sub: str, name: str) -> str:
    return copy(STATIC / sub / name, sub)


class Command(BaseCommand):
    help = 'Seed the site with content from the Vision & Strategic Framework Manual and provided images.'

    def handle(self, *args, **options):
        self.seed_profile()
        self.seed_pillars()
        self.seed_components()
        self.seed_pathway()
        self.seed_actions()
        self.seed_values()
        self.seed_leaders()
        self.seed_stats()
        self.seed_sections()
        self.seed_sliders()
        self.seed_devotions()
        self.seed_announcement()
        self.seed_contact()
        self.stdout.write(self.style.SUCCESS('Seeding complete.'))

    def seed_profile(self):
        ChurchProfile.objects.update_or_create(
            pk=1,
            defaults={
                'church_name': 'Shekinah Blaze Outreach International',
                'tagline': 'Governed by Heaven, Established on Earth.',
                'location': 'Mapoteng Village, Mothibistad, near Kuruman, Northern Cape, South Africa',
                'founder_name': 'Apostle G.V. Mosokini',
                'founder_role': 'Founder & Senior Pastor · Vision Bearer',
                'founder_byline': MANUAL['founder_byline'],
                'founder_scripture': MANUAL['founder_scripture'],
                'founder_message': MANUAL['founder_message'],
                'founder_signature': MANUAL['founder_signature'],
                'founder_tagline': MANUAL['founder_tagline'],
                'story': MANUAL['story'],
                'story_subtitle': MANUAL['story_subtitle'],
                'story_image': img('about', 'Visionary Leaders_2.png.png'),
                'vision': MANUAL['vision_statement'],
                'vision_intro': MANUAL['vision_intro'],
                'vision_components_intro': MANUAL['vision_components_intro'],
                'vision_scripture': MANUAL['vision_scripture'],
                'vision_practice': MANUAL['vision_practice'],
                'vision_future': MANUAL['vision_future'],
                'vision_declaration': MANUAL['vision_declaration'],
                'vision_key_scripture': MANUAL['vision_key_scripture'],
                'mission': MANUAL['mission_statement'],
                'mission_intro': MANUAL['mission_intro'],
                'mission_components_intro': MANUAL['mission_components_intro'],
                'mission_scripture': MANUAL['mission_scripture'],
                'mission_multiplication': MANUAL['mission_multiplication'],
                'mission_commitment': MANUAL['mission_commitment'],
                'mission_declaration': MANUAL['mission_declaration'],
                'mission_key_scripture': MANUAL['mission_key_scripture'],
                'pathway_intro': MANUAL['pathway_intro'],
                'pathway_closing': MANUAL['pathway_closing'],
                'mission_in_action_intro': MANUAL['mission_in_action_intro'],
                'mission_in_action_closing': MANUAL['mission_in_action_closing'],
                'values_intro': MANUAL['values_intro'],
                'culture_statement': MANUAL['culture'],
                'values_declaration': MANUAL['values_declaration'],
            },
        )
        self.stdout.write('  Church profile seeded.')

    def seed_pillars(self):
        for i, item in enumerate(MANUAL['pillars']):
            VisionPillar.objects.update_or_create(title=item['title'], defaults={'subtitle': item['subtitle'], 'body': item['body'], 'order': i + 1})
        titles = {item['title'] for item in MANUAL['pillars']}
        VisionPillar.objects.exclude(title__in=titles).delete()
        self.stdout.write(f'  {len(MANUAL["pillars"])} vision pillars seeded.')

    def seed_components(self):
        for i, item in enumerate(MANUAL['components']):
            MissionComponent.objects.update_or_create(title=item['title'], defaults={'subtitle': item['subtitle'], 'body': item['body'], 'order': i + 1})
        titles = {item['title'] for item in MANUAL['components']}
        MissionComponent.objects.exclude(title__in=titles).delete()
        self.stdout.write(f'  {len(MANUAL["components"])} mission components seeded.')

    def seed_pathway(self):
        for i, (title, desc) in enumerate(MANUAL['pathway']):
            PathwayStep.objects.update_or_create(step=i + 1, defaults={'title': title, 'description': desc, 'order': i + 1})
        PathwayStep.objects.exclude(step__in=range(1, len(MANUAL['pathway']) + 1)).delete()
        self.stdout.write(f'  {len(MANUAL["pathway"])} pathway steps seeded.')

    def seed_actions(self):
        for i, (title, desc) in enumerate(MANUAL['mission_in_action']):
            MissionAction.objects.update_or_create(title=title, defaults={'description': desc, 'order': i + 1})
        titles = {t for t, _ in MANUAL['mission_in_action']}
        MissionAction.objects.exclude(title__in=titles).delete()
        self.stdout.write(f'  {len(MANUAL["mission_in_action"])} mission actions seeded.')

    def seed_values(self):
        for i, item in enumerate(MANUAL['values']):
            CoreValue.objects.update_or_create(
                title=item['title'],
                defaults={
                    'scripture': item['scripture'],
                    'what_we_believe': item['what_we_believe'],
                    'what_this_means': item['what_this_means'],
                    'our_commitment': item['our_commitment'],
                    'order': i + 1,
                },
            )
        titles = {item['title'] for item in MANUAL['values']}
        CoreValue.objects.exclude(title__in=titles).delete()
        self.stdout.write(f'  {len(MANUAL["values"])} core values seeded.')

    def seed_leaders(self):
        for i, item in enumerate(MANUAL['leaders']):
            photo = img('about', 'Pastor.jpg') if 'GV' in item['name'] else img('about', 'Prophetess.jpg')
            Leader.objects.update_or_create(name=item['name'], defaults={'role': item['role'], 'photo': photo, 'bio': item['bio'], 'order': i + 1})
        names = {item['name'] for item in MANUAL['leaders']}
        Leader.objects.exclude(name__in=names).delete()
        self.stdout.write(f'  {len(MANUAL["leaders"])} leaders seeded.')

    def seed_stats(self):
        stats = [
            ('16', 'Years Established'),
            ('2008', 'Vision Birthed'),
            ('5', 'First Gathering'),
        ]
        for i, (value, label) in enumerate(stats):
            HomeStat.objects.update_or_create(value=value, defaults={'label': label, 'order': i + 1})
        self.stdout.write('  Stats seeded.')

    def seed_sections(self):
        FeaturedSection.objects.update_or_create(
            title='Welcome to Shekinah Blaze',
            defaults={'subtitle': 'A Message From The Vision Bearer', 'body': 'To all our visitors, friends, and family — welcome to the joyful fire of God’s presence. Shekinah Blaze is a family, and we are glad you are here.', 'button_text': 'Read Our Story', 'button_url': '/about/', 'order': 1},
        )
        FeaturedSection.objects.update_or_create(
            title='The Dwelling Place of God',
            defaults={'subtitle': 'The Meaning Behind The Name', 'body': 'The name Shekinah means the manifested dwelling presence and glory of God. The Blaze — the fire of God. Together: “The Dwelling Place of God, Distinguished by Fire.”', 'image': img('home', 'Culture.jpg'), 'button_text': 'More About Us', 'button_url': '/about/', 'order': 2},
        )
        FeaturedSection.objects.update_or_create(
            title='Our Culture',
            defaults={'subtitle': 'The Spiritual DNA of Our House', 'body': 'Go, and teach. Go, and heal. Go, and to be led of the Spirit. A people of prayer, prayer–made worship, and worship–made people.', 'image': img('home', 'Visionary Leaders.png.png'), 'button_text': 'Our Values', 'button_url': '/about/', 'order': 3},
        )
        FeaturedSection.objects.update_or_create(
            title='Touching Our Community',
            defaults={'subtitle': 'Mission In Action', 'body': 'The strongest mouth of our message is our hands — gifts, time, service, and kindness to the community. Everyone is welcome, everyone is reached.', 'image': img('home', '16 years established.jpg'), 'button_text': 'Get Involved', 'button_url': '/contact/', 'order': 4},
        )
        titles = {'Welcome to Shekinah Blaze', 'The Dwelling Place of God', 'Our Culture', 'Touching Our Community'}
        FeaturedSection.objects.exclude(title__in=titles).delete()
        self.stdout.write('  Featured sections seeded.')

    def seed_sliders(self):
        home_slides = [
            ('1.jpg', 'Shekinah Blaze Outreach International', 'Governed by Heaven, Established on Earth.'),
            ('Visionary Leaders.png.png', 'Raising God-Fearing Kingdom Leaders', 'To nurture and develop God-fearing Kingdom leaders through the power of the Bible.'),
            ('Culture.jpg', 'The Dwelling Place of God, Distinguished by Fire', 'We are governed by Heaven before we move on Earth.'),
            ('16 years established.jpg', '16 Years Established', 'We have witnessed the faithfulness of the Lord.'),
            ('God Made.jpeg.jpg', 'Transformed Lives', 'Lives transformed by the power of the Gospel.'),
        ]
        new_home = []
        for i, (name, title, caption) in enumerate(home_slides):
            rel = img('home', name)
            if not rel:
                continue
            new_home.append(rel)
            SliderImage.objects.update_or_create(
                image=rel,
                defaults={'title': title, 'caption': caption, 'placement': 'home', 'is_active': True, 'order': i + 1},
            )
        new_gallery = []
        img_filter = (p for p in (STATIC / 'gallery').iterdir() if p.suffix.lower() in ('.jpg', '.jpeg', '.png'))
        for i, name in enumerate(sorted(img_filter)):
            rel = img('gallery', name.name)
            if not rel:
                continue
            new_gallery.append(rel)
            SliderImage.objects.update_or_create(
                image=rel,
                defaults={'title': 'Shekinah Blaze', 'caption': 'Moments of worship and fellowship.', 'placement': 'gallery', 'is_active': True, 'order': 100 + i},
            )
        SliderImage.objects.filter(placement='home').exclude(image__in=new_home).delete()
        SliderImage.objects.filter(placement='gallery', title='Shekinah Blaze').exclude(image__in=new_gallery).delete()
        self.stdout.write('  Slider images seeded.')

    def seed_devotions(self):
        folder = STATIC / 'devotions'
        files = sorted(p.name for p in folder.iterdir() if p.suffix.lower() in ('.jpg', '.jpeg', '.png'))
        known = {
            'IMG-20260729-WA0000.jpg': date(2026, 7, 29),
            'IMG-20260801-WA0000.jpg': date(2026, 8, 1),
            'IMG-20260802-WA0000.jpg': date(2026, 8, 2),
            'IMG-20260803-WA0002.jpg': date(2026, 8, 3),
        }
        fallback = date(2026, 7, 26)
        for i, f in enumerate(files):
            rel = copy(STATIC / 'devotions' / f, 'devotions')
            d = known.get(f, fallback + timedelta(days=i))
            Devotion.objects.update_or_create(image=rel, defaults={'title': 'Daily Devotion', 'date': d, 'is_published': True})
        self.stdout.write(f'  {len(files)} devotions seeded.')

    def seed_announcement(self):
        Announcement.objects.update_or_create(
            title='16 Years Established',
            defaults={'date': date(2024, 1, 1), 'image': img('home', '16 years established.jpg'), 'body': 'To God be the glory for His faithfulness through the years.', 'is_published': True},
        )
        self.stdout.write('  Announcement seeded.')

    def seed_contact(self):
        ContactInfo.objects.update_or_create(
            pk=1,
            defaults={
                'church_name': 'Shekinah Blaze Outreach International',
                'address': 'Mapoteng Village, Mothibistad, near Kuruman, Northern Cape, South Africa',
                'phone': '+27 53 712 0000',
                'whatsapp': '+27 53 712 0000',
                'email': 'info@shekinahblaze.org',
                'service_times': 'Sundays: 09:00 & 11:00\nWednesdays: 17:00 — Bible Study\nFridays: 17:00 — Intercession',
                'facebook': 'https://facebook.com/ShekinahBlazeOutreachInternational',
                'twitter': '',
                'instagram': 'https://instagram.com/shekinahblazeoutreach',
                'youtube': 'https://youtube.com/@ShekinahBlaze',
            },
        )
        self.stdout.write('  Contact info seeded.')