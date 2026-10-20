from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.dashboard.tests.staff_flow import confirmed_action, confirmed_add
from django.utils import timezone

from apps.stores.models import Store, StoreMembership
from apps.stores.services.membership_service import add_staff_member, revoke_membership

User = get_user_model()

HOST = f"staff-test.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class StaffViewsTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.owner = User.objects.create_user(username="09122288001", password="pass12345", is_staff=True)
        self.owner_membership = StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="09122288001", password="pass12345")

    def _login_as(self, role, suffix):
        user = User.objects.create_user(username=f"09122288{suffix}", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=user, role=role,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.logout()
        self.client.login(username=user.username, password="pass12345")
        return user


class StaffListViewTests(StaffViewsTestCase):
    def test_renders_list(self):
        response = self.client.get(reverse("dashboard:staff-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "09122288001")

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:staff-list"))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("/admin-portal/login/", response.url)
        self.assertIn("admin_return=", response.url)
    def test_administrator_cannot_view_staff_list(self):
        self._login_as(StoreMembership.Role.ADMINISTRATOR, "101")
        response = self.client.get(reverse("dashboard:staff-list"))
        self.assertEqual(response.status_code, 403)

    def test_analyst_cannot_view_staff_list(self):
        self._login_as(StoreMembership.Role.ANALYST, "102")
        response = self.client.get(reverse("dashboard:staff-list"))
        self.assertEqual(response.status_code, 403)


class StaffAddViewTests(StaffViewsTestCase):
    def test_owner_can_add_staff_member(self):
        response = confirmed_add(self.client, reverse("dashboard:staff-add"), {
            "phone": "09122288200", "role": StoreMembership.Role.CATALOG_MANAGER,
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            StoreMembership.objects.filter(
                store=self.store, user__username="09122288200", status=StoreMembership.MembershipStatus.ACTIVE,
            ).exists()
        )

    def test_invalid_phone_shows_error_not_500(self):
        response = self.client.post(reverse("dashboard:staff-add"), {
            "phone": "bad", "role": StoreMembership.Role.CATALOG_MANAGER,
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(StoreMembership.objects.filter(user__username="bad").exists())

    def test_cannot_add_as_owner_role(self):
        response = self.client.post(reverse("dashboard:staff-add"), {
            "phone": "09122288201", "role": StoreMembership.Role.OWNER,
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            StoreMembership.objects.filter(store=self.store, user__username="09122288201").exists()
        )

    def test_administrator_cannot_add_staff(self):
        self._login_as(StoreMembership.Role.ADMINISTRATOR, "103")
        response = self.client.post(reverse("dashboard:staff-add"), {
            "phone": "09122288202", "role": StoreMembership.Role.ANALYST,
        })
        self.assertEqual(response.status_code, 403)


class StaffChangeRoleViewTests(StaffViewsTestCase):
    def test_owner_can_change_role(self):
        membership = add_staff_member(self.store, phone="09122288300", role=StoreMembership.Role.ANALYST, invited_by=self.owner)
        confirmed_action(self.client, reverse("dashboard:staff-change-role", args=[membership.pk]), {
            "role": StoreMembership.Role.ORDER_MANAGER,
        })
        membership.refresh_from_db()
        self.assertEqual(membership.role, StoreMembership.Role.ORDER_MANAGER)

    def test_cannot_change_role_of_membership_from_other_store(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="staff-other", status=Store.Status.ACTIVE)
        other_user = User.objects.create_user(username="09122288301", is_staff=True)
        other_membership = StoreMembership.objects.create(
            store=other_store, user=other_user, role=StoreMembership.Role.ANALYST,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        response = self.client.post(reverse("dashboard:staff-change-role", args=[other_membership.pk]), {
            "role": StoreMembership.Role.ORDER_MANAGER,
        })
        self.assertEqual(response.status_code, 404)
        other_membership.refresh_from_db()
        self.assertEqual(other_membership.role, StoreMembership.Role.ANALYST)

    def test_get_not_allowed(self):
        membership = add_staff_member(self.store, phone="09122288302", role=StoreMembership.Role.ANALYST, invited_by=self.owner)
        response = self.client.get(reverse("dashboard:staff-change-role", args=[membership.pk]))
        self.assertEqual(response.status_code, 405)


class StaffRevokeViewTests(StaffViewsTestCase):
    def test_renders_confirmation_on_get(self):
        membership = add_staff_member(self.store, phone="09122288400", role=StoreMembership.Role.ANALYST, invited_by=self.owner)
        response = self.client.get(reverse("dashboard:staff-revoke", args=[membership.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "لغو عضویت")

    def test_post_revokes(self):
        membership = add_staff_member(self.store, phone="09122288401", role=StoreMembership.Role.ANALYST, invited_by=self.owner)
        confirmed_action(self.client, reverse("dashboard:staff-revoke", args=[membership.pk]))
        membership.refresh_from_db()
        self.assertEqual(membership.status, StoreMembership.MembershipStatus.REVOKED)

    def test_cannot_revoke_owner(self):
        response = self.client.post(reverse("dashboard:staff-revoke", args=[self.owner_membership.pk]), follow=True)
        self.assertEqual(response.status_code, 200)
        self.owner_membership.refresh_from_db()
        self.assertEqual(self.owner_membership.status, StoreMembership.MembershipStatus.ACTIVE)

    def test_membership_from_other_store_404s(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="staff-other-revoke", status=Store.Status.ACTIVE)
        other_user = User.objects.create_user(username="09122288402", is_staff=True)
        other_membership = StoreMembership.objects.create(
            store=other_store, user=other_user, role=StoreMembership.Role.ANALYST,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        response = self.client.post(reverse("dashboard:staff-revoke", args=[other_membership.pk]))
        self.assertEqual(response.status_code, 404)


class StaffReactivateViewTests(StaffViewsTestCase):
    def test_reactivates_revoked_membership(self):
        membership = add_staff_member(self.store, phone="09122288500", role=StoreMembership.Role.ANALYST, invited_by=self.owner)
        revoke_membership(membership)
        confirmed_action(self.client, reverse("dashboard:staff-reactivate", args=[membership.pk]))
        membership.refresh_from_db()
        self.assertEqual(membership.status, StoreMembership.MembershipStatus.ACTIVE)


class StaffTransferOwnershipViewTests(StaffViewsTestCase):
    def test_renders_confirmation_on_get(self):
        target = add_staff_member(self.store, phone="09122288600", role=StoreMembership.Role.ADMINISTRATOR, invited_by=self.owner)
        response = self.client.get(reverse("dashboard:staff-transfer-ownership", args=[target.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "انتقال مالکیت")

    def test_post_transfers_ownership(self):
        target = add_staff_member(self.store, phone="09122288601", role=StoreMembership.Role.ADMINISTRATOR, invited_by=self.owner)
        confirmed_action(self.client, reverse("dashboard:staff-transfer-ownership", args=[target.pk]), extra={"confirm_phone": target.user.username})
        target.refresh_from_db()
        self.owner_membership.refresh_from_db()
        self.assertEqual(target.role, StoreMembership.Role.OWNER)
        self.assertEqual(self.owner_membership.role, StoreMembership.Role.ADMINISTRATOR)

    def test_former_owner_loses_staff_manage_after_transfer(self):
        target = add_staff_member(self.store, phone="09122288602", role=StoreMembership.Role.ADMINISTRATOR, invited_by=self.owner)
        confirmed_action(self.client, reverse("dashboard:staff-transfer-ownership", args=[target.pk]), extra={"confirm_phone": target.user.username})
        response = self.client.get(reverse("dashboard:staff-list"))
        self.assertEqual(response.status_code, 403)


class StaffCrossStoreIsolationTests(StaffViewsTestCase):
    def test_other_store_owner_cannot_see_this_store_staff(self):
        other_store = Store.objects.create(
            name="فروشگاه دیگر", slug="staff-cross-store", status=Store.Status.ACTIVE, admin_subdomain="staff-cross",
        )
        other_owner = User.objects.create_user(username="09122288700", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=other_store, user=other_owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        client = Client(HTTP_HOST=HOST)
        client.login(username="09122288700", password="pass12345")
        response = client.get(reverse("dashboard:staff-list"))
        # this user has no membership at all in the store this HOST resolves to
        self.assertEqual(response.status_code, 302)
