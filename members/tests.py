from datetime import date, timedelta
from io import StringIO
from urllib.parse import urlsplit

from django.contrib.auth.models import Permission, User
from django.core import mail
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from blackboard.models import MemberProfile
from communications.models import Conversation, Message
from contact.models import ContactMessage
from notifications.models import Notification

from . import services
from .models import (
    ChurchMembership,
    MembershipChangeRequest,
    MembershipInterest,
    MembershipMinistry,
    MembershipPastoralNote,
)
from .models_comms import (
    CommsAttachment,
    CommsBlock,
    CommsComment,
    CommsDirectMessage,
    CommsDirectThread,
    CommsPost,
    CommsPostSave,
    CommsReaction,
    CommsReport,
    CommunityPresence,
)

STRONG = 'Str0ng-Pass-123'


class RegistrationChoiceTests(TestCase):
    def test_chooser_lists_both_options(self):
        response = self.client.get(reverse('members:register'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('members:register_user'))
        self.assertContains(response, reverse('members:register_church'))


class UserRegistrationTests(TestCase):
    def test_normal_user_registration_unchanged(self):
        response = self.client.post(reverse('members:register_user'), {
            'first_name': 'Normal',
            'last_name': 'Customer',
            'email': 'normal@example.com',
            'username': 'normalcustomer',
            'password1': STRONG,
            'password2': STRONG,
        })
        self.assertRedirects(response, reverse('members:account_profile'))
        user = User.objects.get(username='normalcustomer')
        self.assertTrue(MemberProfile.objects.filter(user=user).exists())
        # A plain user account must not gain a church membership.
        self.assertFalse(ChurchMembership.objects.filter(user=user).exists())
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)


class ChurchRegistrationTests(TestCase):
    url = 'members:register_church'

    def _minimal(self, **extra):
        data = {
            'first_name': 'Grace',
            'last_name': 'Member',
            'email': 'grace@example.com',
            'username': 'gracemember',
            'password1': STRONG,
            'password2': STRONG,
            'phone': '0821234567',
        }
        data.update(extra)
        return data

    def test_minimal_registration_succeeds(self):
        response = self.client.post(reverse(self.url), self._minimal())
        self.assertRedirects(response, reverse('members:account_profile'))
        membership = ChurchMembership.objects.get(user__username='gracemember')
        self.assertTrue(membership.membership_id)
        self.assertTrue(membership.membership_id.startswith('SBOI-M-'))
        self.assertFalse(membership.baptism_date)
        # Optional sections stay empty.
        self.assertFalse(membership.interests.exists())
        self.assertFalse(membership.ministries.exists())
        self.assertFalse(MembershipPastoralNote.objects.filter(membership=membership).exists())

    def test_registration_with_only_credentials(self):
        """The barest account: username, email and password, nothing else."""
        response = self.client.post(reverse(self.url), {
            'username': 'barest',
            'email': 'barest@example.com',
            'password1': STRONG,
            'password2': STRONG,
        })
        self.assertRedirects(response, reverse('members:account_profile'))
        user = User.objects.get(username='barest')
        self.assertEqual(user.first_name, '')
        self.assertEqual(user.last_name, '')
        membership = ChurchMembership.objects.get(user=user)
        self.assertEqual(membership.phone, '')
        self.assertFalse(membership.gender)
        self.assertIsNone(membership.date_of_birth)
        self.assertTrue(membership.membership_id)

    def test_names_and_phone_are_optional(self):
        data = self._minimal()
        data.pop('first_name')
        data.pop('last_name')
        data.pop('phone')
        response = self.client.post(reverse(self.url), data)
        self.assertRedirects(response, reverse('members:account_profile'))
        user = User.objects.get(username='gracemember')
        self.assertEqual(user.first_name, '')
        self.assertEqual(user.last_name, '')

    def test_all_church_questions_may_be_blank(self):
        data = self._minimal(
            phone='', membership_category='', baptism_status='',
            date_of_birth='', gender='', address='', city='', province='',
            emergency_contact_name='', emergency_contact_phone='',
        )
        response = self.client.post(reverse(self.url), data)
        self.assertRedirects(response, reverse('members:account_profile'))
        membership = ChurchMembership.objects.get(user__username='gracemember')
        self.assertEqual(membership.membership_category, '')
        self.assertEqual(membership.baptism_status, '')

    def test_phone_is_optional(self):
        response = self.client.post(reverse(self.url), self._minimal(phone=''))
        self.assertRedirects(response, reverse('members:account_profile'))
        self.assertEqual(
            ChurchMembership.objects.get(user__username='gracemember').phone, '',
        )

    def test_not_baptized_does_not_require_baptism_date(self):
        response = self.client.post(reverse(self.url), self._minimal(
            baptism_status='not_baptized', baptism_date='',
        ))
        self.assertEqual(response.status_code, 302)

    def test_email_is_required(self):
        data = self._minimal(email='')
        response = self.client.post(reverse(self.url), data)
        self.assertEqual(response.status_code, 200)

    def test_duplicate_email_is_blocked(self):
        User.objects.create_user('existing', 'grace@example.com', STRONG)
        response = self.client.post(reverse(self.url), self._minimal())
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='gracemember').exists())

    def test_optional_choices_are_saved(self):
        response = self.client.post(reverse(self.url), self._minimal(
            interests=['bible_study', 'youth'],
            current_ministries=['choir'],
            wants_to_join=['ushering'],
            prayer_request='Please pray for my family.',
            pastoral_support_requested='yes',
            membership_category='regular',
        ))
        self.assertEqual(response.status_code, 302)
        membership = ChurchMembership.objects.get(user__username='gracemember')
        self.assertEqual(
            set(membership.interests.values_list('name', flat=True)),
            {'bible_study', 'youth'},
        )
        self.assertTrue(membership.ministries.filter(name='choir', status='current').exists())
        self.assertTrue(membership.ministries.filter(name='ushering', status='join').exists())
        note = MembershipPastoralNote.objects.get(membership=membership)
        self.assertIn('family', note.prayer_request)

    def test_invalid_choices_are_rejected_server_side(self):
        response = self.client.post(reverse(self.url), self._minimal(
            interests=['not_a_real_interest'],
        ))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='gracemember').exists())


class MemberPasswordResetTests(TestCase):
    """Member "forgot password" flow and the public login page."""

    def setUp(self):
        mail.outbox.clear()
        self.user = User.objects.create_user(
            'resetmember', 'resetmember@example.com', STRONG,
        )

    def _request_reset(self):
        response = self.client.post(
            reverse('members:password_reset'),
            {'email': 'resetmember@example.com'},
        )
        self.assertRedirects(response, reverse('members:password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
        for token in mail.outbox[0].body.split():
            if '/members/password-reset/confirm/' in token:
                return token
        self.fail('No reset link found in the reset email.')

    def test_login_page_has_toggle_and_reset_link(self):
        response = self.client.get(reverse('members:login'))
        self.assertContains(response, 'Login to your account')
        self.assertContains(response, 'password-toggle')
        self.assertContains(response, 'password-toggle-icon--show')
        self.assertContains(response, 'password-toggle-icon--hide')
        self.assertContains(response, reverse('members:password_reset'))
        self.assertNotContains(response, 'auth-logo')
        self.assertNotContains(response, 'data-sboi-public-bell')

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    )
    def test_reset_email_sets_a_new_password(self):
        link = self._request_reset()
        response = self.client.get(urlsplit(link).path)
        self.assertEqual(response.status_code, 302)
        final = response.headers['Location']
        response = self.client.post(final, {
            'new_password1': 'Brand-new-2026',
            'new_password2': 'Brand-new-2026',
        })
        self.assertRedirects(
            response, reverse('members:password_reset_complete'),
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Brand-new-2026'))


class GenderFieldTests(TestCase):
    url = 'members:register_church'

    def _post(self, gender, username):
        self.client.logout()  # registration logs the user in; start fresh
        return self.client.post(reverse(self.url), {
            'email': f'{username}@example.com',
            'username': username,
            'password1': STRONG,
            'password2': STRONG,
            'gender': gender,
        })

    def test_only_male_and_female_are_offered(self):
        from .models import GENDER_CHOICES
        self.assertEqual(
            [value for value, _ in GENDER_CHOICES], ['male', 'female'],
        )

    def test_male_and_female_are_accepted(self):
        self._post('male', 'gendermale')
        self._post('female', 'genderfemale')
        self.assertEqual(
            ChurchMembership.objects.get(user__username='gendermale').gender, 'male',
        )
        self.assertEqual(
            ChurchMembership.objects.get(user__username='genderfemale').gender, 'female',
        )

    def test_blank_gender_is_allowed(self):
        response = self._post('', 'genderblank')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            ChurchMembership.objects.get(user__username='genderblank').gender, '',
        )

    def test_other_values_are_rejected(self):
        response = self._post('other', 'genderother')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='genderother').exists())

    def test_gender_is_not_preselected(self):
        response = self.client.get(reverse(self.url))
        html = response.content.decode()
        group = html.split('name="gender"', 1)[1].split('</fieldset>', 1)[0]
        # Both options are offered as checkboxes, neither ticked by default.
        self.assertIn('value="male"', group)
        self.assertIn('value="female"', group)
        self.assertNotIn('checked', group)


class FamilyDetailsTests(TestCase):
    """Marital status, spouse and children on the membership forms."""

    url = 'members:register_church'

    def _post(self, username, **extra):
        data = {
            'email': f'{username}@example.com',
            'username': username,
            'password1': STRONG,
            'password2': STRONG,
        }
        data.update(extra)
        return self.client.post(reverse(self.url), data)

    def test_marital_status_choices(self):
        from .models import MARITAL_STATUS_CHOICES
        self.assertEqual(
            [value for value, _ in MARITAL_STATUS_CHOICES],
            ['', 'single', 'married', 'widowed', 'divorced', 'separated'],
        )

    def test_registration_saves_married_family_details(self):
        response = self._post(
            'marriedmember',
            marital_status='married',
            spouse_name='Thabo Mokoena',
            children_names='Lerato Mokoena\nKagiso Mokoena',
        )
        self.assertEqual(response.status_code, 302)
        membership = ChurchMembership.objects.get(user__username='marriedmember')
        self.assertEqual(membership.marital_status, 'married')
        self.assertEqual(membership.spouse_name, 'Thabo Mokoena')
        self.assertEqual(
            membership.children_names, 'Lerato Mokoena\nKagiso Mokoena',
        )

    def test_single_parent_can_add_children_without_a_spouse(self):
        response = self._post(
            'singleparent',
            marital_status='single',
            spouse_name='Should be ignored',
            children_names='Lerato Mokoena',
        )
        self.assertEqual(response.status_code, 302)
        membership = ChurchMembership.objects.get(user__username='singleparent')
        self.assertEqual(membership.marital_status, 'single')
        self.assertEqual(membership.children_names, 'Lerato Mokoena')
        self.assertEqual(membership.spouse_name, '')

    def test_family_details_are_optional(self):
        response = self._post('nofamily')
        self.assertEqual(response.status_code, 302)
        membership = ChurchMembership.objects.get(user__username='nofamily')
        self.assertEqual(membership.marital_status, '')
        self.assertEqual(membership.spouse_name, '')
        self.assertEqual(membership.children_names, '')

    def test_join_form_saves_and_prefills_family_details(self):
        user = User.objects.create_user('familyjoin', 'familyjoin@example.com', STRONG)
        self.client.force_login(user)
        self.client.post(reverse('members:join_church'), {
            'marital_status': 'married',
            'spouse_name': 'Naledi Mokoena',
            'children_names': 'Lerato Mokoena\nKagiso Mokoena',
        })
        membership = ChurchMembership.objects.get(user=user)
        self.assertEqual(membership.marital_status, 'married')
        self.assertEqual(membership.spouse_name, 'Naledi Mokoena')

        response = self.client.get(reverse('members:join_church'))
        form = response.context['form']
        self.assertEqual(form.initial['marital_status'], 'married')
        self.assertEqual(form.initial['spouse_name'], 'Naledi Mokoena')
        self.assertEqual(
            form.initial['children_names'],
            'Lerato Mokoena\nKagiso Mokoena',
        )


class MembershipIdTests(TestCase):
    def test_ids_are_unique_and_sequential(self):
        ids = set()
        for i in range(5):
            user = User.objects.create_user(f'user{i}', f'u{i}@example.com', STRONG)
            membership = ChurchMembership.objects.create(user=user)
            self.assertTrue(membership.membership_id)
            self.assertNotIn(membership.membership_id, ids)
            ids.add(membership.membership_id)
        self.assertEqual(len(ids), 5)


class JoinChurchTests(TestCase):
    def test_existing_user_can_join_without_new_account(self):
        user = User.objects.create_user('joiner', 'join@example.com', STRONG)
        self.client.force_login(user)
        response = self.client.post(reverse('members:join_church'), {
            'phone': '0821234567',
            'membership_category': 'visitor',
        })
        self.assertRedirects(response, reverse('members:join_church'))
        self.assertEqual(User.objects.count(), 1)
        membership = ChurchMembership.objects.get(user=user)
        self.assertEqual(membership.membership_category, 'visitor')

    def test_resubmitting_does_not_duplicate(self):
        user = User.objects.create_user('again', 'again@example.com', STRONG)
        self.client.force_login(user)
        for _ in range(2):
            self.client.post(reverse('members:join_church'), {'phone': '0821234567'})
        self.assertEqual(ChurchMembership.objects.filter(user=user).count(), 1)

    def test_blank_profile_then_completed_later(self):
        user = User.objects.create_user('later', 'later@example.com', STRONG)
        self.client.force_login(user)
        # Save with nothing filled in at all.
        self.client.post(reverse('members:join_church'), {})
        memberships = ChurchMembership.objects.filter(user=user)
        self.assertEqual(memberships.count(), 1)
        self.assertEqual(memberships.first().phone, '')
        # Come back later and add details — still one record, one account.
        self.client.post(reverse('members:join_church'), {
            'phone': '0821234567', 'membership_category': 'regular',
        })
        memberships = ChurchMembership.objects.filter(user=user)
        self.assertEqual(memberships.count(), 1)
        self.assertEqual(memberships.first().phone, '0821234567')
        self.assertEqual(memberships.first().membership_category, 'regular')
        self.assertEqual(User.objects.count(), 1)


class MembershipIdUniquenessTests(TestCase):
    def test_ids_are_unique(self):
        ids = set()
        for i in range(5):
            user = User.objects.create_user(f'u{i}', f'u{i}@example.com', STRONG)
            membership = ChurchMembership.objects.create(user=user)
            ids.add(membership.membership_id)
        self.assertEqual(len(ids), 5)


class MembershipStatusDefaultTests(TestCase):
    def test_new_membership_defaults_to_pending(self):
        user = User.objects.create_user(
            'newmember', 'newmember@example.com', STRONG,
        )
        membership = ChurchMembership.objects.create(user=user)
        self.assertEqual(membership.status, 'pending')


class AdminAccessTests(TestCase):
    def test_directory_requires_staff(self):
        response = self.client.get(reverse('admin:members_churchmembership_changelist'))
        self.assertEqual(response.status_code, 302)

        user = User.objects.create_user('plain', 'plain@example.com', STRONG)
        self.client.force_login(user)
        response = self.client.get(reverse('admin:members_churchmembership_changelist'))
        self.assertIn(response.status_code, (302, 403))

    def test_dashboard_is_menu_driven(self):
        """The admin index mirrors the sidebar menu as clickable cards."""
        admin_user = User.objects.create_superuser('boss', 'boss@example.com', STRONG)
        ChurchMembership.objects.create(
            user=User.objects.create_user('m0', 'm0@example.com', STRONG),
            status='active',
        )
        self.client.force_login(admin_user)
        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.status_code, 200)
        # Cards are generated from the full section list; the card opens the
        # section, which then links onward.
        self.assertContains(response, 'sboi-app__title')
        self.assertContains(response, reverse('admin_section', args=['members']))
        section = self.client.get(reverse('admin_section', args=['members']))
        self.assertEqual(section.status_code, 200)
        self.assertContains(
            section, reverse('admin:members_churchmembership_changelist'),
        )
        # The separate "Membership dashboard" tile was removed; the model
        # tile itself opens the dashboard via the changelist redirect. Check
        # the section's own model cards, not the whole page, because the
        # global notification bell may legitimately link to a member record.
        model_urls = [
            model['admin_url']
            for model in section.context['section']['models']
        ]
        self.assertNotIn(
            reverse('admin:members_churchmembership_dashboard'),
            model_urls,
        )

    def test_blank_profile_displays_in_admin(self):
        admin_user = User.objects.create_superuser('blankadmin', 'blankadmin@example.com', STRONG)
        user = User.objects.create_user('blankuser', 'blankuser@example.com', STRONG)
        membership = ChurchMembership.objects.create(user=user)  # everything blank
        self.client.force_login(admin_user)
        listing = self.client.get(reverse('admin:members_churchmembership_changelist'))
        self.assertEqual(listing.status_code, 302)
        self.assertRedirects(listing, reverse('admin:members_churchmembership_dashboard'), fetch_redirect_response=False)
        dashboard = self.client.get(reverse('admin:members_churchmembership_dashboard'))
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, 'blankuser')  # name falls back to username
        change = self.client.get(
            reverse('admin:members_churchmembership_change', args=[membership.pk]),
        )
        self.assertEqual(change.status_code, 200)

    def test_pastoral_notes_admin_permanently_removed(self):
        # The "Pastoral notes" admin entry was removed outright, so the model
        # is no longer registered and its admin URL no longer resolves.
        from django.contrib import admin as django_admin
        from django.urls import NoReverseMatch

        self.assertNotIn(MembershipPastoralNote, django_admin.site._registry)
        with self.assertRaises(NoReverseMatch):
            reverse('admin:members_membershippastoralnote_changelist')


class AdminMemberFormTests(TestCase):
    """The member add/change form manages the linked account inline."""

    def test_add_form_exposes_names_email_and_no_user_selector(self):
        admin_user = User.objects.create_superuser('formadmin', 'formadmin@example.com', STRONG)
        self.client.force_login(admin_user)
        response = self.client.get(reverse('admin:members_churchmembership_add'))
        self.assertEqual(response.status_code, 200)
        form = response.context['adminform'].form
        self.assertIn('first_name', form.fields)
        self.assertIn('last_name', form.fields)
        self.assertIn('email', form.fields)
        self.assertIn('username', form.fields)
        self.assertIn('password1', form.fields)
        self.assertIn('marital_status', form.fields)
        self.assertIn('spouse_name', form.fields)
        self.assertIn('children_names', form.fields)
        self.assertIn('gender', form.fields)
        self.assertNotIn('user', form.fields)

    def test_add_form_matches_the_public_church_form(self):
        """The admin form asks exactly the same questions as the public one."""
        from .forms import ChurchMembershipRegistrationForm

        admin_user = User.objects.create_superuser(
            'parityadmin', 'parityadmin@example.com', STRONG,
        )
        self.client.force_login(admin_user)
        response = self.client.get(reverse('admin:members_churchmembership_add'))
        admin_form = response.context['adminform'].form
        public_form = ChurchMembershipRegistrationForm()

        # `status` is an internal record field, so it is the only extra.
        self.assertEqual(
            set(admin_form.fields),
            set(public_form.fields) | {'status'},
        )
        # The public and admin forms render the same section headings.
        from .admin import ChurchMembershipAdmin

        public_titles = [
            section['title']
            for section in public_form.personal_sections()
            if section['id'] != 'account'
        ] + [section['title'] for section in public_form.sections()]
        admin_titles = [
            title for title, _options in ChurchMembershipAdmin.fieldsets
            if title not in ('Account details', 'Record')
        ]
        self.assertEqual(admin_titles, public_titles)

    def test_add_member_creates_linked_account(self):
        admin_user = User.objects.create_superuser('formadmin2', 'formadmin2@example.com', STRONG)
        self.client.force_login(admin_user)
        response = self.client.post(
            reverse('admin:members_churchmembership_add'),
            {
                'username': 'grace_m',
                'password1': STRONG,
                'password2': STRONG,
                'first_name': 'Grace',
                'last_name': 'Mokoena',
                'email': 'grace@example.com',
                'gender': '',
                'marital_status': 'married',
                'spouse_name': 'Thabo Mokoena',
                'children_names': 'Lerato Mokoena',
                'membership_category': 'regular',
                'status': 'active',
                'interests-TOTAL_FORMS': '0',
                'interests-INITIAL_FORMS': '0',
                'interests-MIN_NUM_FORMS': '0',
                'interests-MAX_NUM_FORMS': '1000',
                'ministries-TOTAL_FORMS': '0',
                'ministries-INITIAL_FORMS': '0',
                'ministries-MIN_NUM_FORMS': '0',
                'ministries-MAX_NUM_FORMS': '1000',
                '_save': 'Save',
            },
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username='grace_m')
        self.assertEqual(user.first_name, 'Grace')
        self.assertEqual(user.last_name, 'Mokoena')
        self.assertEqual(user.email, 'grace@example.com')
        self.assertTrue(user.check_password(STRONG))
        membership = ChurchMembership.objects.get(user=user)
        self.assertTrue(membership.membership_id)
        self.assertEqual(membership.marital_status, 'married')
        self.assertEqual(membership.spouse_name, 'Thabo Mokoena')
        self.assertEqual(membership.children_names, 'Lerato Mokoena')

    def test_add_member_saves_the_public_questions(self):
        admin_user = User.objects.create_superuser(
            'fulladmin', 'fulladmin@example.com', STRONG,
        )
        self.client.force_login(admin_user)
        response = self.client.post(
            reverse('admin:members_churchmembership_add'),
            {
                'username': 'full_m',
                'password1': STRONG,
                'password2': STRONG,
                'first_name': 'Full',
                'last_name': 'Member',
                'email': 'full@example.com',
                'gender': 'female',
                'marital_status': 'married',
                'spouse_name': 'Spouse Name',
                'children_names': 'Child One',
                'membership_category': 'regular',
                'baptism_status': 'baptized',
                'interests': ['bible_study', 'youth'],
                'current_ministries': ['choir'],
                'volunteer_ministries': ['ushering'],
                'wants_to_join': ['media_sound'],
                'guidance_support': 'Some guidance',
                'prayer_request': 'Please pray',
                'pastoral_support_requested': 'on',
                'status': 'active',
                '_save': 'Save',
            },
        )
        self.assertEqual(response.status_code, 302)
        membership = ChurchMembership.objects.get(user__username='full_m')
        self.assertEqual(membership.gender, 'female')
        self.assertEqual(
            set(membership.interests.values_list('name', flat=True)),
            {'bible_study', 'youth'},
        )
        self.assertTrue(
            membership.ministries.filter(name='choir', status='current').exists()
        )
        self.assertTrue(
            membership.ministries.filter(name='ushering', status='volunteer').exists()
        )
        self.assertTrue(
            membership.ministries.filter(name='media_sound', status='join').exists()
        )
        note = MembershipPastoralNote.objects.get(membership=membership)
        self.assertEqual(note.guidance_support, 'Some guidance')
        self.assertEqual(note.prayer_request, 'Please pray')
        self.assertTrue(note.pastoral_support_requested)

    def test_change_form_prefills_the_public_questions(self):
        user = User.objects.create_user(
            'prefilled', 'prefilled@example.com', STRONG,
        )
        membership = ChurchMembership.objects.create(
            user=user, gender='male', marital_status='married',
            spouse_name='Spouse Name',
        )
        MembershipInterest.objects.create(membership=membership, name='youth')
        MembershipMinistry.objects.create(
            membership=membership, name='choir', status='current',
        )
        MembershipPastoralNote.objects.create(
            membership=membership, prayer_request='Please pray',
        )
        admin_user = User.objects.create_superuser(
            'prefilladmin', 'prefilladmin@example.com', STRONG,
        )
        self.client.force_login(admin_user)
        response = self.client.get(
            reverse('admin:members_churchmembership_change', args=[membership.pk]),
        )
        form = response.context['adminform'].form
        self.assertEqual(form['gender'].value(), 'male')
        self.assertEqual(form.initial['interests'], ['youth'])
        self.assertEqual(form.initial['current_ministries'], ['choir'])
        self.assertEqual(form.initial['prayer_request'], 'Please pray')

    def test_change_form_saves_the_public_questions(self):
        user = User.objects.create_user(
            'changesave', 'changesave@example.com', STRONG,
        )
        membership = ChurchMembership.objects.create(user=user)
        admin_user = User.objects.create_superuser(
            'changeadmin', 'changeadmin@example.com', STRONG,
        )
        self.client.force_login(admin_user)
        response = self.client.post(
            reverse('admin:members_churchmembership_change', args=[membership.pk]),
            {
                'username': 'changesave',
                'email': 'changesave@example.com',
                'first_name': 'Changed',
                'last_name': 'Member',
                'gender': 'female',
                'marital_status': 'single',
                'interests': ['bible_study', 'youth'],
                'current_ministries': ['choir'],
                'status': 'active',
                '_save': 'Save',
            },
        )
        self.assertEqual(response.status_code, 302)
        membership.refresh_from_db()
        self.assertEqual(membership.gender, 'female')
        self.assertEqual(membership.marital_status, 'single')
        self.assertEqual(
            set(membership.interests.values_list('name', flat=True)),
            {'bible_study', 'youth'},
        )
        self.assertTrue(
            membership.ministries.filter(name='choir', status='current').exists()
        )

    def test_add_member_generates_username_from_email(self):
        admin_user = User.objects.create_superuser('formadmin3', 'formadmin3@example.com', STRONG)
        self.client.force_login(admin_user)
        response = self.client.post(
            reverse('admin:members_churchmembership_add'),
            {
                'username': '',
                'first_name': 'Jane',
                'email': 'jane@example.com',
                'status': 'active',
                'interests-TOTAL_FORMS': '0',
                'interests-INITIAL_FORMS': '0',
                'interests-MIN_NUM_FORMS': '0',
                'interests-MAX_NUM_FORMS': '1000',
                'ministries-TOTAL_FORMS': '0',
                'ministries-INITIAL_FORMS': '0',
                'ministries-MIN_NUM_FORMS': '0',
                'ministries-MAX_NUM_FORMS': '1000',
                '_save': 'Save',
            },
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(email='jane@example.com')
        self.assertEqual(user.username, 'jane')
        membership = ChurchMembership.objects.get(user=user)
        self.assertTrue(membership.membership_id)

    def test_change_form_omit_passwords_and_prefill_names(self):
        user = User.objects.create_user(
            'formuser', 'formuser@example.com', STRONG,
            first_name='Form', last_name='User',
        )
        membership = ChurchMembership.objects.create(user=user)
        admin_user = User.objects.create_superuser('formadmin4', 'formadmin4@example.com', STRONG)
        self.client.force_login(admin_user)
        response = self.client.get(
            reverse('admin:members_churchmembership_change', args=[membership.pk]),
        )
        self.assertEqual(response.status_code, 200)
        form = response.context['adminform'].form
        self.assertNotIn('password1', form.fields)
        self.assertNotIn('password2', form.fields)
        self.assertIn('username', form.fields)
        self.assertIn('first_name', form.fields)
        self.assertEqual(form['username'].value(), 'formuser')
        self.assertEqual(form['first_name'].value(), 'Form')
        self.assertEqual(form['email'].value(), 'formuser@example.com')


class MembershipDashboardTests(TestCase):
    """The integrated Church Membership dashboard admin page."""

    dashboard = 'admin:members_churchmembership_dashboard'

    def _superuser(self):
        user = User.objects.create_superuser('dashboss', 'dashboss@example.com', STRONG)
        self.client.force_login(user)
        return user

    def _member(self, username, **kwargs):
        user = User.objects.create_user(username, f'{username}@example.com', STRONG)
        return ChurchMembership.objects.create(user=user, **kwargs)

    def test_requires_staff(self):
        response = self.client.get(reverse(self.dashboard))
        self.assertEqual(response.status_code, 302)

        plain = User.objects.create_user('plain2', 'plain2@example.com', STRONG)
        self.client.force_login(plain)
        response = self.client.get(reverse(self.dashboard))
        self.assertIn(response.status_code, (302, 403))

    def test_requires_manage_permission(self):
        # Staff, but with no church-membership permission at all.
        staff = User.objects.create_user('staff2', 'staff2@example.com', STRONG, is_staff=True)
        self.client.force_login(staff)
        response = self.client.get(reverse(self.dashboard))
        self.assertEqual(response.status_code, 403)

    def test_dashboard_lists_real_members_and_stats(self):
        self._superuser()
        for i in range(3):
            member = self._member(f'person{i}')
            if i == 0:
                member.baptism_status = 'baptized'
                member.save()
                MembershipMinistry.objects.create(
                    membership=member, name='choir', status='current',
                )
        response = self.client.get(reverse(self.dashboard))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'person0')
        self.assertContains(response, 'person2')
        self.assertEqual(response.context['stats']['total_members'], 3)
        self.assertEqual(response.context['stats']['baptized_members'], 1)
        self.assertEqual(response.context['stats']['active_groups'], 1)

    def test_empty_directory_renders(self):
        self._superuser()
        response = self.client.get(reverse(self.dashboard))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No members found')

    def test_search_filters_by_name(self):
        self._superuser()
        self._member('findme')
        self._member('hideme')
        response = self.client.get(reverse(self.dashboard), {'q': 'findme'})
        self.assertEqual(response.status_code, 200)
        listed = [member['full_name'] for member in response.context['members']]
        self.assertIn('findme', listed)
        self.assertNotIn('hideme', listed)

    def test_type_and_status_filters(self):
        self._superuser()
        self._member('regularguy', membership_category='regular')
        self._member('visitorgal', membership_category='visitor', status='inactive')
        typed = self.client.get(reverse(self.dashboard), {'type': 'regular'})
        self.assertContains(typed, 'regularguy@example.com')
        self.assertNotContains(typed, 'visitorgal@example.com')
        status = self.client.get(reverse(self.dashboard), {'status': 'inactive'})
        self.assertContains(status, 'visitorgal@example.com')
        self.assertNotContains(status, 'regularguy@example.com')

    def test_group_filter(self):
        self._superuser()
        choir = self._member('choirguy')
        MembershipMinistry.objects.create(
            membership=choir, name='choir', status='current',
        )
        self._member('loner')
        response = self.client.get(reverse(self.dashboard), {'group': 'choir'})
        listed = [member['full_name'] for member in response.context['members']]
        self.assertIn('choirguy', listed)
        self.assertNotIn('loner', listed)

    def test_pagination_splits_the_directory(self):
        self._superuser()
        for i in range(15):
            self._member(f'paged{i:02d}')
        first = self.client.get(reverse(self.dashboard))
        self.assertEqual(len(first.context['members']), 10)
        second = self.client.get(reverse(self.dashboard), {'page': 2})
        self.assertEqual(len(second.context['members']), 5)

    def test_profile_page_uses_real_data(self):
        self._superuser()
        member = self._member(
            'profiled', phone='0821234567', membership_category='regular',
            gender='female', address='1 Main Road',
        )
        response = self.client.get(
            reverse('admin:members_churchmembership_profile', args=[member.pk]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'profiled')
        self.assertContains(response, '0821234567')
        self.assertContains(response, '1 Main Road')
        self.assertEqual(response.context['profile']['id'], member.pk)
        self.assertEqual(response.context['profile']['gender'], 'Female')

    def test_profile_shows_family_details(self):
        self._superuser()
        member = self._member(
            'familyprofile', marital_status='married',
            spouse_name='Naledi Mokoena',
            children_names='Lerato Mokoena\nKagiso Mokoena',
        )
        response = self.client.get(
            reverse('admin:members_churchmembership_profile', args=[member.pk]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Married')
        self.assertContains(response, 'Naledi Mokoena')
        self.assertContains(response, 'Lerato Mokoena, Kagiso Mokoena')

    def test_blank_profile_renders_without_errors(self):
        self._superuser()
        member = self._member('blankdash')
        response = self.client.get(
            reverse('admin:members_churchmembership_profile', args=[member.pk]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['profile']['gender'], '')
        self.assertContains(response, 'blankdash')

    def test_approve_pending_profile_activates_membership(self):
        self._superuser()
        member = self._member('pendingprofile', status='pending')
        response = self.client.post(
            reverse('admin:members_churchmembership_profile', args=[member.pk]),
            {'action': 'approve', 'admin_note': 'Welcome aboard.'},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        member.refresh_from_db()
        self.assertEqual(member.status, 'active')
        self.assertContains(response, 'approved')
        self.assertTrue(
            Notification.objects.filter(
                recipient=member.user,
                source_type='membership_member',
                source_id=member.pk,
            ).exists()
        )

    def test_approve_pending_change_request_records_the_decision(self):
        admin = self._superuser()
        member = self._member('changeauthor', status='pending')
        change = services.record_membership_change(
            member, member.user,
            MembershipChangeRequest.KIND_APPLICATION,
            summary='Submitted from the member portal.',
        )
        response = self.client.post(
            reverse('admin:members_churchmembership_profile', args=[member.pk]),
            {'action': 'approve', 'admin_note': 'Details verified.'},
        )
        self.assertEqual(response.status_code, 302)
        change.refresh_from_db()
        member.refresh_from_db()
        self.assertEqual(change.status, MembershipChangeRequest.STATUS_APPROVED)
        self.assertEqual(change.reviewed_by, admin)
        self.assertEqual(change.admin_note, 'Details verified.')
        self.assertEqual(member.status, 'active')

    def test_direct_status_change_updates_the_member(self):
        self._superuser()
        member = self._member('statusguy')
        response = self.client.post(
            reverse('admin:members_churchmembership_profile', args=[member.pk]),
            {'action': 'status', 'status': 'inactive'},
        )
        self.assertEqual(response.status_code, 302)
        member.refresh_from_db()
        self.assertEqual(member.status, 'inactive')
        self.assertTrue(
            Notification.objects.filter(
                recipient=member.user,
                source_type='membership_member',
                source_id=member.pk,
                title='Membership status updated',
            ).exists()
        )

    def test_profile_sends_a_private_message_to_the_member(self):
        self._superuser()
        member = self._member('messaged')
        response = self.client.post(
            reverse('admin:members_churchmembership_profile', args=[member.pk]),
            {'action': 'message', 'message': 'Please confirm your address.'},
        )
        self.assertEqual(response.status_code, 302)
        message = ContactMessage.objects.get(
            user=member.user, is_from_admin=True,
        )
        self.assertEqual(message.message, 'Please confirm your address.')
        self.assertTrue(
            Notification.objects.filter(
                recipient=member.user,
                source_type='contact_reply',
                source_id=message.pk,
            ).exists()
        )

    def test_old_member_query_redirects_to_profile(self):
        self._superuser()
        member = self._member('oldlink')
        response = self.client.get(
            reverse(self.dashboard), {'member': member.pk},
        )
        self.assertRedirects(
            response,
            reverse('admin:members_churchmembership_profile', args=[member.pk]),
        )

    def test_section_page_inlines_the_directory(self):
        self._superuser()
        self._member('sectionmember')
        response = self.client.get(reverse('admin_section', args=['members']))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['members_dashboard'])
        self.assertContains(response, 'sectionmember')
        self.assertNotContains(response, 'Membership change requests')

    def test_section_page_requires_membership_permission(self):
        user = User.objects.create_user(
            'noaccess', 'noaccess@example.com', STRONG, is_staff=True,
        )
        self.client.force_login(user)
        self._member('privatesectionmember')
        response = self.client.get(reverse('admin_section', args=['members']))
        self.assertEqual(response.status_code, 403)
        self.assertNotContains(
            response, 'privatesectionmember', status_code=403,
        )

    def test_add_button_with_manage_permission(self):
        self._superuser()
        self._member('someone')
        response = self.client.get(reverse(self.dashboard))
        self.assertContains(response, 'Add New Member')

    def test_manage_permission_has_full_control(self):
        user = User.objects.create_user(
            'manager', 'manager@example.com', STRONG, is_staff=True,
        )
        user.user_permissions.add(
            Permission.objects.get(codename='manage_membership'),
        )
        self.client.force_login(user)
        member = self._member('managed')
        response = self.client.get(reverse(self.dashboard))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['can_add'])
        self.assertTrue(response.context['can_change'])
        self.assertContains(response, 'Add New Member')
        profile = self.client.get(
            reverse('admin:members_churchmembership_profile', args=[member.pk]),
        )
        self.assertEqual(profile.status_code, 200)
        self.assertContains(profile, 'Edit member')


class AccountPortalTests(TestCase):
    """The member portal is owner-scoped and cannot approve memberships."""

    def setUp(self):
        self.member = User.objects.create_user(
            'accountmember', 'account@example.com', STRONG,
            first_name='Account', last_name='Member',
        )
        self.membership = ChurchMembership.objects.create(
            user=self.member,
            status='active',
            phone='0821234567',
            membership_category='regular',
            children_names='Lerato\nKagiso',
        )
        self.client.force_login(self.member)

    def test_account_requires_authentication(self):
        self.client.logout()
        response = self.client.get(reverse('members:account'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('members:login'), response['Location'])

    def test_login_redirects_to_home_after_the_first_login(self):
        self.client.logout()
        response = self.client.post(
            reverse('members:login'),
            {'username': self.member.username, 'password': STRONG},
        )
        self.assertRedirects(response, reverse('home:home'))

    def test_first_ever_login_redirects_to_the_profile(self):
        User.objects.create_user('firstlogin', 'first@example.com', STRONG)
        self.client.logout()
        response = self.client.post(
            reverse('members:login'),
            {'username': 'firstlogin', 'password': STRONG},
        )
        self.assertRedirects(response, reverse('members:account_profile'))

    def test_account_page_has_no_sidebar_and_sign_out_uses_post(self):
        response = self.client.get(reverse('members:account'))
        self.assertNotContains(response, 'account-sidebar')
        self.assertContains(response, 'class="nav-account-logout"')
        self.assertNotContains(
            response, f'<a href="{reverse("members:logout")}"',
        )
        response = self.client.post(reverse('members:logout'))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_merged_header_controls_and_anonymous_bell(self):
        self.client.logout()
        public = self.client.get(reverse('home:home'))
        self.assertNotContains(public, 'data-sboi-public-bell')

        self.client.force_login(self.member)
        public = self.client.get(reverse('home:home'))
        self.assertContains(public, 'nav-auth-combo')
        self.assertContains(public, 'data-sboi-public-bell')
        self.assertNotContains(public, 'Admin console')

        member_home = self.client.get(reverse('members:account'))
        self.assertContains(member_home, 'cf-topbar-combo')
        self.assertContains(member_home, 'data-sboi-public-bell')

    def test_home_shows_only_the_post_feed(self):
        response = self.client.get(reverse('members:account'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="comms-feed"')
        for marker in (
            'cf-page-head',
            'cf-membership-strip',
            'sboi-ichat__filters',
            'placeholder="Share something',
            'placeholder="Share an update',
        ):
            self.assertNotContains(response, marker)
        self.assertNotContains(
            response,
            f'href="{reverse("members:account_profile")}" class="cf-tab',
        )

    def test_profile_avatar_opens_the_edit_modal(self):
        response = self.client.get(reverse('members:account_profile'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'cf-avatar-edit')
        self.assertContains(response, 'data-account-open="profileModal"')
        self.assertNotContains(
            response,
            f'href="{reverse("members:account_profile_edit")}" class="cf-avatar-link"',
        )

    def test_profile_form_offers_avatar_cropping(self):
        response = self.client.get(reverse('members:account_profile'))
        self.assertEqual(response.status_code, 200)
        for marker in (
            'data-avatar-cropper',
            'data-avatar-input',
            'data-avatar-preview',
            'data-avatar-stage',
            'data-avatar-zoom',
            'data-avatar-apply',
            'Crop &amp; use',
            'Drag to frame your photo',
        ):
            self.assertContains(response, marker)
        self.assertEqual(response.content.decode().count('name="avatar"'), 1)

    def test_staff_account_menu_exposes_the_admin_console(self):
        self.member.is_staff = True
        self.member.save(update_fields=['is_staff'])
        response = self.client.get(reverse('home:home'))
        self.assertContains(response, 'Admin console')

    def test_profile_shows_status_and_no_self_approval(self):
        response = self.client.get(reverse('members:account_profile'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Active')
        self.assertContains(response, 'Church membership')
        self.assertNotContains(
            response,
            reverse(
                'admin:members_membershipchangerequest_review',
                args=[1],
            ),
        )

    def test_profile_edit_cannot_change_membership_or_approval(self):
        other = User.objects.create_user('othermember', 'other@example.com', STRONG)
        response = self.client.post(
            reverse('members:account_profile_edit'),
            {
                'first_name': 'Changed',
                'last_name': 'Name',
                'email': 'changed@example.com',
                'phone': '0837654321',
                'address': '2 New Road',
                'city': 'Pretoria',
                'province': 'Gauteng',
                'marital_status': 'single',
                'spouse_name': 'Should be cleared',
                'status': 'rejected',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        self.member.refresh_from_db()
        self.membership.refresh_from_db()
        self.assertEqual(self.member.first_name, 'Changed')
        self.assertEqual(self.member.email, 'changed@example.com')
        self.assertEqual(self.membership.status, 'active')
        self.assertEqual(self.membership.address, '2 New Road')
        self.assertEqual(self.membership.spouse_name, '')
        other.refresh_from_db()
        self.assertEqual(other.email, 'other@example.com')
        self.assertFalse(ChurchMembership.objects.filter(user=other).exists())

    def test_membership_edit_stays_active_and_creates_a_pending_review(self):
        response = self.client.post(
            reverse('members:account_membership_edit'),
            {
                'membership_category': 'regular',
                'baptism_status': 'baptized',
                'current_ministries': ['choir'],
                'wants_to_join': ['media_sound'],
                'whatsapp_consent': 'on',
                'status': 'rejected',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.status, 'active')
        self.assertTrue(self.membership.whatsapp_consent)
        change = MembershipChangeRequest.objects.get(
            membership=self.membership, status='pending',
        )
        self.assertEqual(change.kind, MembershipChangeRequest.KIND_UPDATE)
        self.assertEqual(change.submitted_by, self.member)
        self.assertTrue(
            Notification.objects.filter(
                source_type='membership_change', source_id=change.pk,
                permission='members.manage_membership',
            ).exists()
        )

    def test_membership_edit_preserves_private_contact_details(self):
        """The focused form must not clear fields it never renders."""
        self.membership.address = '12 Church Street'
        self.membership.date_of_birth = date(1990, 1, 2)
        self.membership.gender = 'female'
        self.membership.marital_status = 'married'
        self.membership.save()

        response = self.client.post(
            reverse('members:account_membership_edit'),
            {
                'membership_category': 'regular',
                'baptism_status': 'baptized',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.phone, '0821234567')
        self.assertEqual(self.membership.address, '12 Church Street')
        self.assertEqual(self.membership.date_of_birth, date(1990, 1, 2))
        self.assertEqual(self.membership.gender, 'female')
        self.assertEqual(self.membership.marital_status, 'married')

    def test_new_application_is_pending_and_not_active(self):
        new_member = User.objects.create_user(
            'applicant', 'applicant@example.com', STRONG,
        )
        self.client.force_login(new_member)
        response = self.client.post(
            reverse('members:account_membership_request'),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        membership = ChurchMembership.objects.get(user=new_member)
        self.assertEqual(membership.status, 'pending')
        change = MembershipChangeRequest.objects.get(membership=membership)
        self.assertEqual(change.kind, MembershipChangeRequest.KIND_APPLICATION)
        self.assertEqual(change.status, 'pending')

    def test_membership_edit_locked_until_approved(self):
        new_member = User.objects.create_user(
            'lockedapplicant', 'locked@example.com', STRONG,
        )
        self.client.force_login(new_member)
        # Requesting membership creates a pending record; editing is locked.
        self.client.post(reverse('members:account_membership_request'))
        membership = ChurchMembership.objects.get(user=new_member)
        self.assertEqual(membership.status, 'pending')
        response = self.client.post(
            reverse('members:account_membership_edit'),
            {'membership_category': 'regular', 'baptism_status': 'not_baptized'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()['ok'])

    def test_member_cannot_open_admin_review_page(self):
        change = MembershipChangeRequest.objects.create(
            membership=self.membership,
            submitted_by=self.member,
            kind=MembershipChangeRequest.KIND_UPDATE,
            summary='Test',
        )
        response = self.client.get(
            reverse(
                'admin:members_membershipchangerequest_review',
                args=[change.pk],
            )
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/', response['Location'])

    def test_children_are_owner_scoped(self):
        response = self.client.post(
            reverse('members:account_child_add'), {'name': 'Neo'},
        )
        self.assertEqual(response.status_code, 302)
        self.membership.refresh_from_db()
        self.assertIn('Neo', self.membership.children_names)
        self.client.post(
            reverse('members:account_child_edit', args=[0]),
            {'name': 'Lerato Updated'},
        )
        self.membership.refresh_from_db()
        self.assertIn('Lerato Updated', self.membership.children_names)
        self.client.post(reverse('members:account_child_remove', args=[0]))
        self.membership.refresh_from_db()
        self.assertNotIn('Lerato Updated', self.membership.children_names)

    def test_private_message_is_one_thread_and_owner_scoped(self):
        response = self.client.post(
            reverse('members:account_message_send'),
            {'message': 'Please pray for my family.'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        message = ContactMessage.objects.get(user=self.member, is_from_admin=False)
        self.assertEqual(message.sender, self.member)
        self.assertTrue(message.read_by_member)
        self.assertTrue(
            Notification.objects.filter(
                source_type='contact', source_id=message.pk,
            ).exists()
        )

        other = User.objects.create_user('nosy', 'nosy@example.com', STRONG)
        self.client.force_login(other)
        response = self.client.get(reverse('members:account_messages'))
        self.assertNotContains(response, 'Please pray for my family.')
        response = self.client.get(reverse('contact:attachment', args=[message.pk]))
        self.assertEqual(response.status_code, 404)

    def test_private_attachment_is_streamed_only_to_owner(self):
        upload = SimpleUploadedFile(
            'prayer-note.txt', b'Private prayer note', content_type='text/plain',
        )
        response = self.client.post(
            reverse('members:account_message_send'),
            {'message': 'See the attached note.', 'attachment': upload},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        message = ContactMessage.objects.get(
            user=self.member, is_from_admin=False,
            attachment__isnull=False,
        )
        self.addCleanup(message.attachment.delete, save=False)
        self.assertEqual(message.attachment_name, 'prayer-note.txt')
        download = self.client.get(
            reverse('contact:attachment', args=[message.pk]),
        )
        self.assertEqual(download.status_code, 200)
        self.assertEqual(b''.join(download.streaming_content), b'Private prayer note')

        other = User.objects.create_user('nosy2', 'nosy2@example.com', STRONG)
        self.client.force_login(other)
        denied = self.client.get(
            reverse('contact:attachment', args=[message.pk]),
        )
        self.assertEqual(denied.status_code, 404)

    def test_admin_decision_keeps_active_member_and_notifies_them(self):
        change = MembershipChangeRequest.objects.create(
            membership=self.membership,
            submitted_by=self.member,
            kind=MembershipChangeRequest.KIND_UPDATE,
            summary='Address: 2 New Road',
        )
        admin = User.objects.create_superuser(
            'reviewadmin', 'review@example.com', STRONG,
        )
        change, notification, created = services.apply_membership_decision(
            change.pk, admin, approve=False, note='Please use a street number.',
        )
        self.membership.refresh_from_db()
        self.assertEqual(change.status, MembershipChangeRequest.STATUS_REJECTED)
        self.assertEqual(self.membership.status, 'active')
        self.assertTrue(created)
        self.assertIsNotNone(notification)
        self.assertIn('not approved', notification.title.lower())
        # A second decision is a no-op.
        _, again, created_again = services.apply_membership_decision(
            change.pk, admin, approve=True,
        )
        self.assertIsNone(again)
        self.assertFalse(created_again)

    def test_approving_application_makes_member_active(self):
        applicant = User.objects.create_user(
            'pendingapplicant', 'pending@example.com', STRONG,
        )
        membership = ChurchMembership.objects.create(
            user=applicant, status='pending',
        )
        change = MembershipChangeRequest.objects.create(
            membership=membership,
            submitted_by=applicant,
            kind=MembershipChangeRequest.KIND_APPLICATION,
            summary='Membership category: Regular',
        )
        admin = User.objects.create_superuser(
            'approveadmin', 'approve@example.com', STRONG,
        )
        change, notification, created = services.apply_membership_decision(
            change.pk, admin, approve=True,
        )
        membership.refresh_from_db()
        self.assertEqual(change.status, MembershipChangeRequest.STATUS_APPROVED)
        self.assertEqual(membership.status, 'active')
        self.assertTrue(created)
        self.assertIsNotNone(notification)
        self.assertTrue(
            Notification.objects.filter(
                recipient=applicant, source_type='membership_member',
            ).exists()
        )

    def test_notifications_page_only_shows_the_signed_in_member(self):
        other = User.objects.create_user('othernotified', 'other2@example.com', STRONG)
        Notification.objects.create(
            recipient=other,
            audience=Notification.AUDIENCE_MEMBER,
            category='membership',
            source_key='other-only',
            title='Private notice for someone else',
            body='You should not see this.',
        )
        response = self.client.get(reverse('members:account_notifications'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Private notice for someone else')

    def test_ajax_navigation_returns_only_the_account_section(self):
        response = self.client.get(
            reverse('members:account_children'),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-account-section')
        self.assertContains(response, 'data-account-title="Children"')
        self.assertContains(response, 'Lerato')
        self.assertNotContains(response, '<html')
        self.assertNotContains(response, 'account-sidebar')

    def test_counts_endpoint_keeps_badges_and_bell_in_sync(self):
        ContactMessage.objects.create(
            user=self.member,
            sender=User.objects.create_user(
                'replyadmin', 'replyadmin@example.com', STRONG,
            ),
            name='Church Office',
            email='office@example.com',
            message='A private reply.',
            is_from_admin=True,
            is_read=True,
            read_by_member=False,
        )
        Notification.objects.create(
            recipient=self.member,
            audience=Notification.AUDIENCE_MEMBER,
            category='membership',
            source_key='unread-count-test',
            title='Unread notice',
            body='Please review this.',
        )
        response = self.client.get(reverse('members:account_counts'))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['ok'])
        self.assertEqual(payload['unread_messages'], 1)
        self.assertGreaterEqual(payload['unread_notifications'], 1)

    def test_child_ajax_returns_a_replacement_fragment(self):
        response = self.client.post(
            reverse('members:account_child_add'),
            {'name': 'Neo'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['ok'])
        self.assertIn('Neo', payload['html'])
        self.assertIn('account-child-list', payload['html'])
        self.membership.refresh_from_db()
        self.assertIn('Neo', self.membership.children_names)

    def test_settings_ajax_returns_settings_section(self):
        response = self.client.post(
            reverse('members:account_settings'),
            {'save_preferences': '1'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['ok'])
        self.assertIn('data-account-section', payload['html'])
        self.assertIn('Change password', payload['html'])
        self.assertNotIn('<html', payload['html'])

    def test_notification_open_is_owner_scoped_and_returns_target(self):
        notification = Notification.objects.create(
            recipient=self.member,
            audience=Notification.AUDIENCE_MEMBER,
            category='membership',
            source_key='open-scope-test',
            title='Membership details approved',
            body='Your details were approved.',
            url=reverse('members:account_profile') + '#membership',
        )
        response = self.client.get(
            reverse('members:account_notification_open', args=[notification.pk]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        self.assertEqual(
            response.json()['url'], reverse('members:account_profile') + '#membership',
        )

        other = User.objects.create_user('otherreader', 'otherreader@example.com', STRONG)
        self.client.force_login(other)
        denied = self.client.get(
            reverse('members:account_notification_open', args=[notification.pk]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(denied.status_code, 404)

    def test_member_cannot_review_their_own_request(self):
        change = MembershipChangeRequest.objects.create(
            membership=self.membership,
            submitted_by=self.member,
            kind=MembershipChangeRequest.KIND_UPDATE,
            summary='Address changed',
        )
        with self.assertRaises(PermissionDenied):
            services.apply_membership_decision(
                change.pk, self.member, approve=True,
            )
        change.refresh_from_db()
        self.assertEqual(change.status, MembershipChangeRequest.STATUS_PENDING)

    def test_admin_edit_updates_profile_and_notifies_once(self):
        admin = User.objects.create_superuser(
            'recordadmin', 'recordadmin@example.com', STRONG,
        )
        self.client.force_login(admin)
        payload = {
            'username': 'accountmember',
            'email': 'account@example.com',
            'first_name': 'Account',
            'last_name': 'Member',
            'phone': '0837654321',
            'status': 'active',
            'membership_category': 'regular',
            '_save': 'Save',
        }
        url = reverse(
            'admin:members_churchmembership_change',
            args=[self.membership.pk],
        )
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 302)
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.phone, '0837654321')
        notices = Notification.objects.filter(
            recipient=self.member,
            source_type='membership_admin_update',
            source_id=self.membership.pk,
        )
        self.assertEqual(notices.count(), 1)
        self.assertIn('updated', notices.get().title.lower())

        # Re-saving the same values must not spam a second notice.
        self.client.post(url, payload)
        self.assertEqual(notices.count(), 1)

        # Personal contact details now live on the member profile page: the
        # feed landing page deliberately shows no personal records.
        self.client.force_login(self.member)
        response = self.client.get(reverse('members:account'))
        self.assertEqual(response.status_code, 200)
        profile = self.client.get(reverse('members:account_profile'))
        self.assertEqual(profile.status_code, 200)
        self.assertContains(profile, '0837654321')


class AccountDeletionTests(TestCase):
    """Account deletion requires confirmation and cascades safely."""

    def setUp(self):
        self.member = User.objects.create_user(
            'deletable', 'deletable@example.com', STRONG,
            first_name='Deletable', last_name='Member',
        )
        self.membership = ChurchMembership.objects.create(
            user=self.member,
            status='active',
            phone='0821234567',
            membership_category='regular',
        )
        self.client.force_login(self.member)

    def test_delete_requires_confirmation(self):
        response = self.client.post(
            reverse('members:account_delete'),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 302)
        self.member.refresh_from_db()
        self.assertTrue(User.objects.filter(pk=self.member.pk).exists())

    def test_delete_removes_account_and_membership(self):
        response = self.client.post(
            reverse('members:account_delete'),
            {'confirm_delete': 'yes'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.filter(pk=self.member.pk).exists())
        self.assertFalse(
            ChurchMembership.objects.filter(user=self.member).exists()
        )

    def test_delete_signs_user_out(self):
        self.client.post(
            reverse('members:account_delete'),
            {'confirm_delete': 'yes'},
        )
        self.assertNotIn('_auth_user_id', self.client.session)


class CommunityFeedTests(TestCase):
    """The members-only feed must never leak to visitors or other members."""

    def setUp(self):
        self.member = User.objects.create_user(
            'feedmember', 'feed@example.com', STRONG,
            first_name='Feed', last_name='Member',
        )
        self.other = User.objects.create_user(
            'othermember', 'other@example.com', STRONG,
            first_name='Other', last_name='Member',
        )
        self.staff = User.objects.create_superuser(
            'feedstaff', 'staff@example.com', STRONG,
            first_name='Feed', last_name='Admin',
        )
        self.client.force_login(self.member)

    def _publish(self, body='A church update', **extra):
        payload = {'body': body}
        payload.update(extra)
        return self.client.post(reverse('members:feed_post_create'), payload)

    def test_visitor_cannot_see_feed_or_publish(self):
        self.client.logout()
        post = CommsPost.objects.create(author=self.staff, body='Members only')
        response = self.client.get(reverse('members:account'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('members:login'), response.url)
        response = self.client.post(
            reverse('members:feed_post_create'), {'body': 'Nope'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CommsPost.objects.count(), 1)
        public = self.client.get(reverse('home:home'))
        self.assertNotContains(public, 'Members only')
        self.assertNotContains(public, reverse('members:feed_post_create'))
        self.assertTrue(post.pk)

    def test_member_sees_composer_and_can_publish(self):
        response = self.client.get(reverse('members:account'))
        self.assertContains(response, 'data-feed-composer')
        self.assertContains(response, reverse('members:feed_post_create'))

        response = self._publish('Youth night this Friday.')
        self.assertEqual(response.status_code, 302)
        post = CommsPost.objects.get()
        self.assertEqual(post.author, self.member)
        self.assertEqual(post.audience, CommsPost.AUDIENCE_ALL)
        self.assertTrue(post.is_published)
        self.assertFalse(post.is_hidden)

        response = self.client.get(reverse('members:account'))
        self.assertContains(response, 'Youth night this Friday.')

    def test_member_cannot_publish_staff_only_post(self):
        self._publish('For everyone', audience=CommsPost.AUDIENCE_STAFF)
        self.assertEqual(
            CommsPost.objects.get().audience, CommsPost.AUDIENCE_ALL,
        )

    def test_member_can_repost_a_post_to_the_feed(self):
        original = CommsPost.objects.create(
            author=self.other, body='Original testimony',
        )
        url = reverse('members:feed_post_share', args=[original.pk])
        response = self.client.post(
            url, {'surface': 'community'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['created'])
        shared = CommsPost.objects.get(pk=data['post_id'])
        self.assertEqual(shared.author, self.member)
        self.assertEqual(shared.shared_from, original)
        self.assertEqual(shared.audience, CommsPost.AUDIENCE_ALL)
        self.assertIn('Original testimony', data['html'])
        self.assertIn('cf-shared-post', data['html'])
        self.assertIn('shared a post', data['html'])

        # A second click is idempotent and does not duplicate the repost.
        again = self.client.post(
            url, {'surface': 'community'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(again.status_code, 200)
        self.assertFalse(again.json()['created'])
        self.assertEqual(
            CommsPost.objects.filter(shared_from=original).count(), 1,
        )

        feed = self.client.get(reverse('members:account'))
        self.assertContains(feed, 'Original testimony')
        self.assertContains(feed, 'cf-shared-post')
        self.assertContains(feed, 'name="surface" value="community"')

    def test_hidden_and_staff_only_posts_cannot_be_shared_by_members(self):
        hidden = CommsPost.objects.create(
            author=self.staff, body='Hidden note', is_hidden=True,
        )
        response = self.client.post(
            reverse('members:feed_post_share', args=[hidden.pk]),
        )
        self.assertEqual(response.status_code, 404)

        staff_post = CommsPost.objects.create(
            author=self.staff,
            audience=CommsPost.AUDIENCE_STAFF,
            body='Staff retreat notes',
        )
        response = self.client.post(
            reverse('members:feed_post_share', args=[staff_post.pk]),
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(CommsPost.objects.filter(shared_from=hidden).exists())
        self.assertFalse(
            CommsPost.objects.filter(shared_from=staff_post).exists()
        )

    def test_staff_only_post_is_hidden_from_members(self):
        post = CommsPost.objects.create(
            author=self.staff,
            audience=CommsPost.AUDIENCE_STAFF,
            body='Leadership retreat notes',
        )
        response = self.client.get(reverse('members:account'))
        self.assertNotContains(response, 'Leadership retreat notes')

        self.client.force_login(self.staff)
        response = self.client.get(
            reverse('communications:inbox') + '?view=feed',
        )
        self.assertContains(response, 'Leadership retreat notes')
        self.assertTrue(post.pk)

    def test_comment_is_created_and_abuse_is_rejected(self):
        post = CommsPost.objects.create(author=self.staff, body='Welcome')
        response = self.client.post(
            reverse('members:feed_post_comment', args=[post.pk]),
            {'body': 'Amen!'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(post.comments.count(), 1)
        self.assertContains(response, 'Amen!')

        response = self.client.post(
            reverse('members:feed_post_comment', args=[post.pk]),
            {'body': 'You are an idiot'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(post.comments.count(), 1)

    def test_reaction_toggles_and_replaces(self):
        post = CommsPost.objects.create(author=self.staff, body='Prayer')
        url = reverse('members:feed_post_react', args=[post.pk])

        response = self.client.post(
            url, {'reaction': 'heart'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['active'])
        self.assertEqual(CommsReaction.objects.get().reaction, 'heart')

        response = self.client.post(
            url, {'reaction': 'pray'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertTrue(response.json()['active'])
        self.assertEqual(CommsReaction.objects.count(), 1)
        self.assertEqual(CommsReaction.objects.get().reaction, 'pray')

        response = self.client.post(
            url, {'reaction': 'pray'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertFalse(response.json()['active'])
        self.assertEqual(CommsReaction.objects.count(), 0)

    def test_attachment_upload_and_download(self):
        upload = SimpleUploadedFile(
            'notice.pdf', b'%PDF-1.4 test attachment',
            content_type='application/pdf',
        )
        response = self.client.post(
            reverse('members:feed_post_create'),
            {'body': 'See the attached notice', 'attachment': upload},
        )
        self.assertEqual(response.status_code, 302)
        attachment = CommsAttachment.objects.get()
        self.addCleanup(attachment.file.delete, save=False)
        self.assertEqual(attachment.kind, CommsAttachment.KIND_DOCUMENT)
        self.assertEqual(attachment.original_name, 'notice.pdf')

        response = self.client.get(
            reverse('members:feed_attachment_download', args=[attachment.pk]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment', response['Content-Disposition'])
        # Consume the stream instead of response.close(): closing the response
        # sends request_finished, which closes the test database connection and
        # breaks every test that runs after this one.
        self.assertIn(b'%PDF-1.4', b''.join(response.streaming_content))

    def test_member_cannot_download_staff_only_attachment(self):
        post = CommsPost.objects.create(
            author=self.staff,
            audience=CommsPost.AUDIENCE_STAFF,
            body='Staff file',
        )
        attachment = CommsAttachment.objects.create(
            post=post,
            file=SimpleUploadedFile('staff.pdf', b'%PDF-1.4 staff'),
            original_name='staff.pdf',
            kind=CommsAttachment.KIND_DOCUMENT,
        )
        self.addCleanup(attachment.file.delete, save=False)
        response = self.client.get(
            reverse('members:feed_attachment_download', args=[attachment.pk]),
        )
        self.assertEqual(response.status_code, 404)

    def test_member_can_delete_own_post(self):
        post = CommsPost.objects.create(author=self.member, body='My post')
        response = self.client.post(
            reverse('members:feed_post_delete', args=[post.pk]),
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(CommsPost.objects.filter(pk=post.pk).exists())

    def test_member_cannot_delete_another_members_post(self):
        post = CommsPost.objects.create(author=self.other, body='Not mine')
        response = self.client.post(
            reverse('members:feed_post_delete', args=[post.pk]),
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(CommsPost.objects.filter(pk=post.pk).exists())

        self.client.force_login(self.staff)
        response = self.client.post(
            reverse('members:feed_post_delete', args=[post.pk]),
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(CommsPost.objects.filter(pk=post.pk).exists())


class CommunityMemberExperienceTests(TestCase):
    """Member feed actions stay private, incremental and owner-scoped."""

    def setUp(self):
        self.member = User.objects.create_user(
            'memberone', 'memberone@example.com', STRONG,
            first_name='Member', last_name='One',
        )
        self.other = User.objects.create_user(
            'membertwo', 'membertwo@example.com', STRONG,
            first_name='Member', last_name='Two',
        )
        self.staff = User.objects.create_superuser(
            'communitystaff', 'communitystaff@example.com', STRONG,
            first_name='Church', last_name='Admin',
        )
        self.membership = ChurchMembership.objects.create(
            user=self.member,
            status='active',
            phone='0831234567',
            membership_category='regular',
            date_joined_church=timezone.localdate() - timedelta(days=400),
        )
        self.client.force_login(self.member)

    def _post(self, author=None, body='Community post', **extra):
        return CommsPost.objects.create(
            author=author or self.member, body=body, **extra,
        )

    def _comment(self, post, author, body, parent=None):
        return CommsComment.objects.create(
            post=post, author=author, body=body, parent=parent,
        )

    def test_member_can_edit_own_post_only(self):
        post = self._post(body='Before the edit')
        url = reverse('members:feed_post_edit', args=[post.pk])
        response = self.client.post(
            url,
            {'body': 'After the edit', 'surface': 'community'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        post.refresh_from_db()
        self.assertEqual(post.body, 'After the edit')
        self.assertIsNotNone(post.edited_at)
        self.assertIn('After the edit', response.json()['html'])
        self.assertIn('cf-post', response.json()['html'])
        self.assertNotIn('comms-post', response.json()['html'])

        response = self.client.post(
            url, {'body': 'idiot'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 400)
        post.refresh_from_db()
        self.assertEqual(post.body, 'After the edit')

        self.client.force_login(self.other)
        response = self.client.post(
            url, {'body': 'Not mine'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 403)
        post.refresh_from_db()
        self.assertEqual(post.body, 'After the edit')

    def test_save_and_unsave_are_private_bookmarks(self):
        post = self._post(body='A post worth keeping')
        url = reverse('members:feed_post_save', args=[post.pk])
        response = self.client.post(
            url, HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['saved'])
        self.assertTrue(
            CommsPostSave.objects.filter(post=post, user=self.member).exists()
        )

        feed = self.client.get(reverse('members:account'))
        self.assertContains(feed, 'data-cf-saved="true"')
        saved = self.client.get(reverse('members:account_saved'))
        self.assertContains(saved, 'A post worth keeping')
        self.assertContains(saved, '1 saved')

        self.client.force_login(self.other)
        other_saved = self.client.get(reverse('members:account_saved'))
        self.assertNotContains(other_saved, 'A post worth keeping')
        self.assertNotContains(
            other_saved, 'data-cf-saved="true"',
        )

        self.client.force_login(self.member)
        response = self.client.post(
            url, HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertFalse(response.json()['saved'])
        self.assertFalse(
            CommsPostSave.objects.filter(post=post, user=self.member).exists()
        )
        saved = self.client.get(reverse('members:account_saved'))
        self.assertNotContains(saved, 'A post worth keeping')

    def test_report_post_and_comment_deduplicates_for_each_reporter(self):
        post = self._post(author=self.other, body='Reportable post')
        comment = self._comment(post, self.other, 'Reportable comment')
        url = reverse('members:feed_report')

        response = self.client.post(
            url,
            {'post_id': post.pk, 'reason': 'spam', 'note': 'Looks like spam'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        report = CommsReport.objects.get(reporter=self.member, post=post)
        self.assertEqual(report.reason, CommsReport.REASON_SPAM)

        response = self.client.post(
            url,
            {'post_id': post.pk, 'reason': 'abuse', 'note': 'Changed my mind'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            CommsReport.objects.filter(reporter=self.member, post=post).count(), 1,
        )
        report.refresh_from_db()
        self.assertEqual(report.reason, CommsReport.REASON_ABUSE)

        response = self.client.post(
            url,
            {'comment_id': comment.pk, 'reason': 'harassment'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            CommsReport.objects.filter(
                reporter=self.member, comment=comment, post__isnull=True,
            ).exists()
        )

        staff_only = self._post(
            author=self.staff,
            body='Staff only report target',
            audience=CommsPost.AUDIENCE_STAFF,
        )
        response = self.client.post(
            url,
            {'post_id': staff_only.pk, 'reason': 'spam'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 404)

    def test_replies_stay_one_level_deep_and_render_member_markup(self):
        post = self._post(author=self.staff, body='Discussion')
        root = self._comment(post, self.other, 'Root comment')
        first_reply = self._comment(post, self.member, 'First reply', root)
        url = reverse('members:feed_post_comment', args=[post.pk])

        response = self.client.post(
            url,
            {'body': 'Nested reply', 'parent': first_reply.pk, 'surface': 'community'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['parent_id'], root.pk)
        nested = CommsComment.objects.get(body='Nested reply')
        self.assertEqual(nested.parent, root)
        self.assertIn('cf-comment', payload['html'])
        self.assertIn('cf-comment--reply', payload['html'])
        self.assertIn('data-cf-comment-item', payload['html'])
        self.assertNotIn('comms-comment', payload['html'])

        response = self.client.post(
            url,
            {'body': 'A root comment', 'surface': 'community'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('cf-comment', response.json()['html'])
        self.assertNotIn('comms-comment', response.json()['html'])
        self.assertEqual(post.comments.count(), 4)

    def test_load_more_uses_cursor_and_scopes(self):
        for index in range(12):
            self._post(author=self.staff, body=f'Staff post {index}')
        own = self._post(author=self.member, body='My own older post')
        saved_posts = [
            self._post(author=self.staff, body='Saved one'),
            self._post(author=self.staff, body='Saved two'),
        ]
        for saved_post in saved_posts:
            CommsPostSave.objects.create(post=saved_post, user=self.member)

        url = reverse('members:feed_load_more')
        response = self.client.get(
            url, {'scope': 'feed'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        first = response.json()
        self.assertTrue(first['has_more'])
        self.assertEqual(
            first['html'].count('data-cf-post data-post-id'), 10,
        )
        self.assertIn('My own older post', first['html'])

        response = self.client.get(
            url,
            {'scope': 'feed', 'before': first['next_before']},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        second = response.json()
        self.assertFalse(second['has_more'])
        self.assertEqual(second['html'].count('data-cf-post data-post-id'), 5)
        self.assertNotIn('My own older post', second['html'])

        response = self.client.get(
            url, {'scope': 'posts'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        posts_html = response.json()['html']
        self.assertIn('My own older post', posts_html)
        self.assertNotIn('Staff post', posts_html)
        self.assertFalse(response.json()['has_more'])

        response = self.client.get(
            url, {'scope': 'saved'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        saved_html = response.json()['html']
        self.assertIn('Saved one', saved_html)
        self.assertIn('Saved two', saved_html)
        self.assertNotIn('Staff post', saved_html)
        self.assertFalse(response.json()['has_more'])

    def test_load_more_cursor_follows_created_at_order(self):
        posts = [
            self._post(
                author=self.staff,
                body=f'Chronological marker {index:02d}',
            )
            for index in range(14)
        ]
        base = timezone.now()
        for index, post in enumerate(posts):
            CommsPost.objects.filter(pk=post.pk).update(
                created_at=base - timedelta(minutes=index),
            )
        ordered = list(CommsPost.objects.order_by('-created_at', '-pk'))
        self.assertEqual([post.pk for post in ordered], [post.pk for post in posts])

        url = reverse('members:feed_load_more')
        first = self.client.get(
            url, HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        ).json()
        self.assertTrue(first['has_more'])
        self.assertEqual(
            first['html'].count('data-cf-post data-post-id'), 10,
        )
        for post in posts[:10]:
            self.assertIn(post.body, first['html'])
        for post in posts[10:]:
            self.assertNotIn(post.body, first['html'])

        second = self.client.get(
            url,
            {'before': first['next_before']},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        ).json()
        self.assertFalse(second['has_more'])
        self.assertEqual(
            second['html'].count('data-cf-post data-post-id'), 4,
        )
        for post in posts[10:]:
            self.assertIn(post.body, second['html'])
        for post in posts[:10]:
            self.assertNotIn(post.body, second['html'])

    def test_public_profile_never_exposes_private_contact_details(self):
        visible = self._post(body='Visible community post')
        hidden = self._post(
            body='Staff only profile post',
            audience=CommsPost.AUDIENCE_STAFF,
        )
        self.client.force_login(self.other)
        response = self.client.get(
            reverse('members:member_profile', args=[self.member.username]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Member One')
        self.assertContains(response, 'Church member')
        self.assertContains(response, 'Visible community post')
        self.assertNotContains(response, 'Staff only profile post')
        self.assertNotContains(response, 'memberone@example.com')
        self.assertNotContains(response, '0831234567')
        self.assertNotContains(response, 'Membership category')
        self.assertNotContains(response, 'Emergency contact')

        self.client.logout()
        response = self.client.get(
            reverse('members:member_profile', args=[self.member.username]),
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('members:login'), response.url)
        self.assertTrue(visible.pk and hidden.pk)

    def test_new_account_sections_support_ajax_fragments(self):
        self._post(body='My AJAX post')
        for name in ('account_posts', 'account_saved', 'account_profile'):
            response = self.client.get(
                reverse(f'members:{name}'),
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            )
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'data-account-section')
            self.assertNotContains(response, '<html')
            self.assertNotContains(response, 'cf-topbar')


class CommunitySafetyAndInboxTests(TestCase):
    """Presence, blocking and private member-to-member conversations."""

    def setUp(self):
        self.member = User.objects.create_user(
            'safetymember', 'safetymember@example.com', STRONG,
            first_name='Safety', last_name='Member',
        )
        self.other = User.objects.create_user(
            'safetyother', 'safetyother@example.com', STRONG,
            first_name='Safety', last_name='Other',
        )
        self.outsider = User.objects.create_user(
            'safetyoutsider', 'safetyoutsider@example.com', STRONG,
            first_name='Safety', last_name='Outsider',
        )
        self.client.force_login(self.member)

    def _thread(self):
        return CommsDirectThread.for_users(self.member, self.other)

    def _message(self, thread, sender, body='Private hello'):
        message = CommsDirectMessage.objects.create(
            thread=thread, sender=sender, body=body,
        )
        CommsDirectThread.objects.filter(pk=thread.pk).update(
            last_message_at=message.created_at,
        )
        thread.refresh_from_db()
        return message

    def test_inbox_shows_online_members_and_known_conversations(self):
        self.client.force_login(self.other)
        self.client.get(reverse('members:account'))
        self.assertTrue(
            CommunityPresence.objects.filter(user=self.other).exists()
        )

        thread = self._thread()
        self._message(thread, self.other, 'A private hello')

        self.client.force_login(self.member)
        response = self.client.get(reverse('members:account_messages'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Online now')
        self.assertContains(response, 'Safety Other')
        self.assertContains(response, 'A private hello')

    def test_member_can_exchange_a_private_thread_and_recipient_is_notified(self):
        thread = self._thread()
        send_url = reverse('members:account_direct_send', args=[thread.pk])

        response = self.client.post(send_url, {'body': 'Peace be with you'})
        self.assertEqual(response.status_code, 302)
        message = CommsDirectMessage.objects.get()
        self.assertEqual(message.sender, self.member)
        self.assertEqual(message.body, 'Peace be with you')
        self.assertEqual(services.unread_message_count(self.other), 1)
        notification = Notification.objects.get(
            recipient=self.other, source_type='direct_message',
        )
        self.assertIn('Peace be with you', notification.body)

        self.client.force_login(self.other)
        response = self.client.get(
            reverse('members:account_messages') + f'?thread={thread.pk}',
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Peace be with you')
        # The office row stays a real link so it can return from a member
        # conversation, where the office thread panel is not rendered.
        self.assertContains(response, 'data-cf-open-thread')
        self.assertContains(
            response, f'href="{reverse("members:account_messages")}"',
        )
        self.assertEqual(services.unread_message_count(self.other), 0)
        notification.refresh_from_db()
        self.assertTrue(
            Notification.objects.filter(pk=notification.pk).exists()
        )

    def test_outsider_cannot_read_or_write_another_members_thread(self):
        thread = self._thread()
        self._message(thread, self.other, 'Just between us')

        self.client.force_login(self.outsider)
        response = self.client.get(
            reverse('members:account_messages') + f'?thread={thread.pk}',
        )
        self.assertEqual(response.status_code, 404)
        response = self.client.post(
            reverse('members:account_direct_send', args=[thread.pk]),
            {'body': 'Butting in'},
        )
        self.assertEqual(response.status_code, 404)
        response = self.client.get(
            reverse('members:account_direct_poll', args=[thread.pk]),
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(CommsDirectMessage.objects.count(), 1)

    def test_blocking_hides_posts_comments_and_blocks_messages(self):
        member_post = CommsPost.objects.create(
            author=self.member, body='Visible to everyone',
        )
        other_post = CommsPost.objects.create(
            author=self.other, body='Hidden after the block',
        )
        CommsComment.objects.create(
            post=member_post, author=self.other, body='Hidden comment',
        )

        response = self.client.post(
            reverse(
                'members:account_block_member',
                args=[self.other.username],
            ),
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            CommsBlock.objects.filter(
                blocker=self.member, blocked=self.other,
            ).exists()
        )

        feed = self.client.get(reverse('members:account'))
        self.assertContains(feed, 'Visible to everyone')
        self.assertNotContains(feed, 'Hidden after the block')
        self.assertNotContains(feed, 'Hidden comment')

        thread = self._thread()
        response = self.client.post(
            reverse('members:account_direct_send', args=[thread.pk]),
            {'body': 'You should not see this'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(CommsDirectMessage.objects.count(), 0)
        self.assertFalse(
            services.direct_threads_for(self.member).filter(pk=thread.pk).exists()
        )
        self.assertEqual(other_post.author, self.other)

        response = self.client.post(
            reverse(
                'members:account_unblock_member',
                args=[self.other.username],
            ),
        )
        self.assertEqual(response.status_code, 302)
        feed = self.client.get(reverse('members:account'))
        self.assertContains(feed, 'Hidden after the block')

    def test_reciprocal_block_hides_the_other_members_view_too(self):
        CommsPost.objects.create(author=self.member, body='Member post')
        self.client.force_login(self.other)
        self.client.post(
            reverse(
                'members:account_block_member',
                args=[self.member.username],
            ),
        )
        feed = self.client.get(reverse('members:account'))
        self.assertNotContains(feed, 'Member post')

    def test_profile_and_settings_offer_block_and_unblock_controls(self):
        self.client.post(
            reverse(
                'members:account_block_member',
                args=[self.other.username],
            ),
        )
        profile = self.client.get(
            reverse('members:member_profile', args=[self.other.username]),
        )
        self.assertContains(profile, 'Unblock')
        settings = self.client.get(reverse('members:account_settings'))
        self.assertContains(settings, 'Blocked members')
        self.assertContains(settings, 'Safety Other')


class ChatRetentionTests(TestCase):
    """The 90-day cleanup covers every private chat surface."""

    def setUp(self):
        self.staff = User.objects.create_superuser(
            'retentionstaff', 'retention@example.com', STRONG,
        )
        self.member = User.objects.create_user(
            'retentionmember', 'retentionmember@example.com', STRONG,
        )

    def test_cleanup_removes_only_old_messages(self):
        old = timezone.now() - timedelta(days=120)
        conversation = Conversation.objects.create(
            kind=Conversation.KIND_GROUP, name='Office', created_by=self.staff,
        )
        old_staff_message = Message.objects.create(
            conversation=conversation, sender=self.staff, body='Old staff',
        )
        new_staff_message = Message.objects.create(
            conversation=conversation, sender=self.staff, body='New staff',
        )
        old_member_message = ContactMessage.objects.create(
            user=self.member, sender=self.member, name='Member',
            email='retentionmember@example.com', message='Old member',
        )
        new_member_message = ContactMessage.objects.create(
            user=self.member, sender=self.member, name='Member',
            email='retentionmember@example.com', message='New member',
        )
        # A public contact-form enquiry shares the table but is not a chat.
        public_enquiry = ContactMessage.objects.create(
            name='Website visitor', email='visitor@example.com',
            message='Please call me about the youth programme.',
        )
        post = CommsPost.objects.create(author=self.staff, body='Announcement')
        old_comment = CommsComment.objects.create(
            post=post, author=self.member, body='Old comment',
        )
        new_comment = CommsComment.objects.create(
            post=post, author=self.member, body='New comment',
        )
        Message.objects.filter(pk__in=[
            old_staff_message.pk,
        ]).update(created_at=old)
        ContactMessage.objects.filter(pk__in=[
            old_member_message.pk, public_enquiry.pk,
        ]).update(created_at=old)
        CommsComment.objects.filter(pk__in=[
            old_comment.pk,
        ]).update(created_at=old)

        output = StringIO()
        call_command('cleanup_old_chats', stdout=output)

        self.assertFalse(Message.objects.filter(pk=old_staff_message.pk).exists())
        self.assertTrue(Message.objects.filter(pk=new_staff_message.pk).exists())
        self.assertFalse(
            ContactMessage.objects.filter(pk=old_member_message.pk).exists()
        )
        self.assertTrue(
            ContactMessage.objects.filter(pk=new_member_message.pk).exists()
        )
        # Public contact enquiries never expire with the private chats.
        self.assertTrue(
            ContactMessage.objects.filter(pk=public_enquiry.pk).exists()
        )
        self.assertFalse(CommsComment.objects.filter(pk=old_comment.pk).exists())
        self.assertTrue(CommsComment.objects.filter(pk=new_comment.pk).exists())
        # Announcements themselves are retained.
        self.assertTrue(CommsPost.objects.filter(pk=post.pk).exists())
