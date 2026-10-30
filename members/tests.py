from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse

from blackboard.models import MemberProfile

from .models import (
    ChurchMembership,
    MembershipInterest,
    MembershipMinistry,
    MembershipPastoralNote,
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
        self.assertRedirects(response, reverse('blackboard:blackboard'))
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
        self.assertRedirects(response, reverse('blackboard:blackboard'))
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
        self.assertRedirects(response, reverse('blackboard:blackboard'))
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
        self.assertRedirects(response, reverse('blackboard:blackboard'))
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
        self.assertRedirects(response, reverse('blackboard:blackboard'))
        membership = ChurchMembership.objects.get(user__username='gracemember')
        self.assertEqual(membership.membership_category, '')
        self.assertEqual(membership.baptism_status, '')

    def test_phone_is_optional(self):
        response = self.client.post(reverse(self.url), self._minimal(phone=''))
        self.assertRedirects(response, reverse('blackboard:blackboard'))
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
        # Cards are generated from the same permission-filtered source as
        # the sidebar; the card opens the section, which then links onward.
        self.assertContains(response, 'sboi-app__title')
        self.assertContains(response, reverse('admin_section', args=['members']))
        section = self.client.get(reverse('admin_section', args=['members']))
        self.assertEqual(section.status_code, 200)
        self.assertContains(section, reverse('admin:members_churchmembership_dashboard'))

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
        self.assertNotIn('user', form.fields)
        self.assertNotIn('gender', form.fields)

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

    def test_requires_view_permission(self):
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
        self.assertContains(response, 'findme')
        self.assertNotContains(response, 'hideme')

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
        self.assertContains(response, 'choirguy')
        self.assertNotContains(response, 'loner')

    def test_pagination_splits_the_directory(self):
        self._superuser()
        for i in range(15):
            self._member(f'paged{i:02d}')
        first = self.client.get(reverse(self.dashboard))
        self.assertEqual(len(first.context['members']), 10)
        second = self.client.get(reverse(self.dashboard), {'page': 2})
        self.assertEqual(len(second.context['members']), 5)

    def test_selected_member_profile_uses_real_data(self):
        self._superuser()
        member = self._member(
            'profiled', phone='0821234567', membership_category='regular',
            gender='female', address='1 Main Road',
        )
        response = self.client.get(reverse(self.dashboard), {'member': member.pk})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'profiled')
        self.assertContains(response, '0821234567')
        self.assertContains(response, '1 Main Road')
        self.assertEqual(response.context['selected_member']['id'], member.pk)
        self.assertEqual(response.context['selected_member']['gender'], 'Female')

    def test_profile_shows_family_details(self):
        self._superuser()
        member = self._member(
            'familyprofile', marital_status='married',
            spouse_name='Naledi Mokoena',
            children_names='Lerato Mokoena\nKagiso Mokoena',
        )
        response = self.client.get(reverse(self.dashboard), {'member': member.pk})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Married')
        self.assertContains(response, 'Naledi Mokoena')
        self.assertContains(response, 'Lerato Mokoena, Kagiso Mokoena')

    def test_blank_profile_renders_without_errors(self):
        self._superuser()
        member = self._member('blankdash')
        response = self.client.get(reverse(self.dashboard), {'member': member.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['selected_member']['gender'], '')
        self.assertContains(response, 'blankdash')

    def test_add_button_only_with_add_permission(self):
        self._superuser()
        self._member('someone')
        response = self.client.get(reverse(self.dashboard))
        self.assertContains(response, 'Add New Member')

    def test_view_only_staff_has_no_add_or_edit_links(self):
        user = User.objects.create_user(
            'viewer', 'viewer@example.com', STRONG, is_staff=True,
        )
        user.user_permissions.add(
            Permission.objects.get(codename='view_churchmembership'),
        )
        self.client.force_login(user)
        member = self._member('lookedat')
        response = self.client.get(reverse(self.dashboard), {'member': member.pk})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['can_add'])
        self.assertFalse(response.context['can_change'])
        self.assertNotContains(response, 'Add New Member')
        self.assertNotContains(response, '>Edit Member<')
