"""End-to-end checks for the one-permission-per-area admin model."""

from io import StringIO

from django.contrib import admin
from django.contrib.auth.models import Group, Permission, User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from blackboard.models import Devotion
from contact.models import ContactMessage
from members.models import ChurchMembership
from sboi.admin_permissions import (
    AREA_PERMISSIONS,
    ROLE_GROUPS,
    AreaPermissionMixin,
)

STRONG = 'Str0ng-Pass-123'

SECTION_LABELS = (
    'home',
    'about',
    'blackboard',
    'gallery',
    'contact',
    'members',
    'auth',
)


class RoleTestMixin:
    @classmethod
    def setUpTestData(cls):
        call_command('setup_roles', stdout=StringIO())

    def staff_user(self, username, groups=()):
        user = User.objects.create_user(
            username,
            f'{username}@example.com',
            STRONG,
            is_staff=True,
        )
        for group_name in groups:
            user.groups.add(Group.objects.get(name=group_name))
        return user


class DashboardVisibilityTests(RoleTestMixin, TestCase):
    def test_staff_with_no_groups_see_every_section_but_open_none(self):
        user = self.staff_user('ungrouped')
        self.client.force_login(user)

        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.status_code, 200)
        for label in SECTION_LABELS:
            self.assertContains(
                response,
                reverse('admin_section', args=[label]),
            )
        self.assertContains(response, 'sboi-app--locked')

        for label in SECTION_LABELS:
            denied = self.client.get(reverse('admin_section', args=[label]))
            self.assertEqual(denied.status_code, 403, label)
            self.assertContains(
                denied,
                "You don't have permission to open this section",
                status_code=403,
            )

    def test_one_group_opens_that_section_and_marks_the_rest_locked(self):
        user = self.staff_user('blackboard_editor', ['Blackboard Manager'])
        self.client.force_login(user)

        section = self.client.get(reverse('admin_section', args=['blackboard']))
        self.assertEqual(section.status_code, 200)
        # RSVPs and member access are separate areas, so their tiles are locked.
        self.assertContains(section, 'sboi-tile--locked')
        self.assertContains(section, reverse('admin:blackboard_devotion_changelist'))

        home = self.client.get(reverse('admin_section', args=['home']))
        self.assertEqual(home.status_code, 403)

    def test_blackboard_manager_has_full_control_of_blackboard_content(self):
        user = self.staff_user('blackboard_full', ['Blackboard Manager'])
        self.client.force_login(user)
        devotion = Devotion.objects.create(title='Permission check', message='Body')

        self.assertEqual(
            self.client.get(reverse('admin:blackboard_devotion_changelist')).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse('admin:blackboard_devotion_add')).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                reverse('admin:blackboard_devotion_change', args=[devotion.pk])
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                reverse('admin:blackboard_devotion_delete', args=[devotion.pk])
            ).status_code,
            200,
        )

    def test_unassigned_membership_urls_return_403(self):
        user = self.staff_user('blackboard_only', ['Blackboard Manager'])
        self.client.force_login(user)
        member = ChurchMembership.objects.create(
            user=User.objects.create_user(
                'member_record', 'member_record@example.com', STRONG
            )
        )

        urls = [
            reverse('admin:members_churchmembership_changelist'),
            reverse('admin:members_churchmembership_add'),
            reverse('admin:members_churchmembership_change', args=[member.pk]),
            reverse('admin:members_churchmembership_delete', args=[member.pk]),
            reverse('admin:members_churchmembership_dashboard'),
            reverse('admin:auth_user_changelist'),
        ]
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 403, url)

        # An add page in a different unassigned app is denied too.
        response = self.client.get(reverse('admin:home_homestat_add'))
        self.assertEqual(response.status_code, 403)

    def test_unassigned_blackboard_urls_and_app_index_return_403(self):
        user = self.staff_user('membership_only', ['Membership Manager'])
        self.client.force_login(user)
        devotion = Devotion.objects.create(title='Locked devotion')

        urls = [
            reverse('admin:app_list', args=['blackboard']),
            reverse('admin:blackboard_devotion_changelist'),
            reverse('admin:blackboard_devotion_add'),
            reverse('admin:blackboard_devotion_change', args=[devotion.pk]),
            reverse('admin:blackboard_devotion_delete', args=[devotion.pk]),
        ]
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 403, url)

    def test_two_groups_open_both_areas(self):
        user = self.staff_user(
            'two_roles',
            ['Blackboard Manager', 'Membership Manager'],
        )
        self.client.force_login(user)
        member = ChurchMembership.objects.create(
            user=User.objects.create_user(
                'member_two', 'member_two@example.com', STRONG
            )
        )

        self.assertEqual(
            self.client.get(reverse('admin_section', args=['blackboard'])).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse('admin_section', args=['members'])).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse('admin:members_churchmembership_add')).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                reverse('admin:members_churchmembership_change', args=[member.pk])
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse('admin_section', args=['home'])).status_code,
            403,
        )

    def test_superuser_can_open_every_section(self):
        user = User.objects.create_superuser('owner', 'owner@example.com', STRONG)
        self.client.force_login(user)

        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'sboi-app--locked')

        for label in SECTION_LABELS:
            self.assertEqual(
                self.client.get(reverse('admin_section', args=[label])).status_code,
                200,
                label,
            )

    def test_search_results_are_filtered_by_area_permission(self):
        user = self.staff_user('search_staff', ['Blackboard Manager'])
        self.client.force_login(user)
        Devotion.objects.create(title='Searchable devotion')
        ContactMessage.objects.create(
            name='Searchable contact',
            email='search@example.com',
            message='Body',
        )

        response = self.client.get(reverse('admin_search'), {'q': 'Searchable'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Searchable devotion')
        self.assertNotContains(response, 'Searchable contact')


class PermissionPickerTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            'picker', 'picker@example.com', STRONG
        )
        self.client.force_login(self.superuser)

    def assert_only_manage_permissions(self, field):
        codenames = set(field.queryset.values_list('codename', flat=True))
        self.assertTrue(codenames)
        self.assertTrue(all(name.startswith('manage_') for name in codenames))
        self.assertIn('manage_membership', codenames)
        self.assertIn('manage_staff_accounts', codenames)
        self.assertNotIn('view_churchmembership', codenames)
        self.assertNotIn('export_churchmembership', codenames)
        self.assertNotIn('view_sensitive_membership', codenames)

    def test_group_form_only_offers_manage_permissions(self):
        response = self.client.get(reverse('admin:auth_group_add'))
        self.assertEqual(response.status_code, 200)
        field = response.context['adminform'].form.fields['permissions']
        self.assert_only_manage_permissions(field)

    def test_user_form_only_offers_manage_permissions(self):
        target = User.objects.create_user(
            'picked', 'picked@example.com', STRONG
        )
        response = self.client.get(
            reverse('admin:auth_user_change', args=[target.pk])
        )
        self.assertEqual(response.status_code, 200)
        field = response.context['adminform'].form.fields['user_permissions']
        self.assert_only_manage_permissions(field)


class SetupRolesTests(TestCase):
    def test_command_is_idempotent_and_keeps_manual_permissions(self):
        call_command('setup_roles', stdout=StringIO())
        initial_count = Group.objects.count()
        self.assertEqual(initial_count, len(ROLE_GROUPS))

        group = Group.objects.get(name='Blackboard Manager')
        assigned = {
            f'{permission.content_type.app_label}.{permission.codename}'
            for permission in group.permissions.all()
        }
        self.assertEqual(
            assigned,
            set(ROLE_GROUPS['Blackboard Manager']),
        )

        manual = Permission.objects.get(
            content_type__app_label='blackboard',
            codename='view_devotion',
        )
        group.permissions.add(manual)

        call_command('setup_roles', stdout=StringIO())
        self.assertEqual(Group.objects.count(), initial_count)
        self.assertTrue(group.permissions.filter(pk=manual.pk).exists())


class AdminRegistryTests(TestCase):
    def test_every_registered_model_uses_an_area_permission(self):
        for model, model_admin in admin.site._registry.items():
            message = f'{model._meta.label} does not use AreaPermissionMixin'
            self.assertIsInstance(model_admin, AreaPermissionMixin, message)
            self.assertIn(
                model_admin.area_permission,
                AREA_PERMISSIONS,
                f'{model._meta.label} has an unknown area permission',
            )

    def test_every_area_permission_exists(self):
        for dotted_name in AREA_PERMISSIONS:
            app_label, codename = dotted_name.split('.', 1)
            self.assertTrue(
                Permission.objects.filter(
                    content_type__app_label=app_label,
                    codename=codename,
                ).exists(),
                dotted_name,
            )
