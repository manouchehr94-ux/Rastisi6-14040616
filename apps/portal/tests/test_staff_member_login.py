"""RS-14 — an invited team member must be able to sign in with the SAME phone+OTP identity as everybody else
WITHOUT turning into a platform Owner (no OwnerProfile, no trial Store of their own, no owner signup form)."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.portal.models import OwnerProfile
from apps.portal.services import owner_otp_service
from apps.portal.tests._owner_signup import age_otp_cooldown
from apps.sms.services.backends import SmsSendResult
from apps.stores.models import Store, StoreMembership
from apps.stores.services import membership_service

User = get_user_model()
HOST = "rastisi.localhost"
STAFF_PHONE = "09125550123"


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class StaffOtpLoginTests(TestCase):
    def setUp(self):
        cache.clear()
        self.sent = []
        patcher = patch.object(owner_otp_service, "send_platform_otp", side_effect=self._send)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.store = Store.objects.create(name="S", slug="staff-login", admin_subdomain="staff-login", status=Store.Status.ACTIVE)
        self.owner = User.objects.create_user(username="09120000001")
        OwnerProfile.objects.create(user=self.owner, phone="09120000001", full_name="Owner")
        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )

    def _send(self, *, to, code, **_):
        self.sent.append(code)
        return SmsSendResult(success=True, provider_ref_id="t")

    def _otp_login(self, phone):
        self.client.post("/login/", {"phone": phone}, HTTP_HOST=HOST)
        return self.client.post("/verify/", {"code": self.sent[-1]}, HTTP_HOST=HOST)

    def test_added_member_logs_in_by_otp_without_becoming_an_owner(self):
        membership_service.add_staff_member(
            self.store, phone=STAFF_PHONE, role=StoreMembership.Role.CATALOG_MANAGER, invited_by=self.owner,
        )
        stores_before = Store.objects.count()
        response = self._otp_login(STAFF_PHONE)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/app/", "a team member goes to the portal home, not an owner signup step")
        user = User.objects.get(username=STAFF_PHONE)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        self.assertFalse(OwnerProfile.objects.filter(user=user).exists(), "staff must not silently become a platform owner")
        self.assertEqual(Store.objects.count(), stores_before, "no trial store may be provisioned for a team member")

    def test_revoked_member_cannot_use_the_otp_shortcut(self):
        m = membership_service.add_staff_member(
            self.store, phone=STAFF_PHONE, role=StoreMembership.Role.ANALYST, invited_by=self.owner,
        )
        membership_service.revoke_membership(m, actor=self.owner)
        response = self._otp_login(STAFF_PHONE)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertNotEqual(response.get("Location"), "/app/")
