"""FOLLOWUP-05 — security audit of team management, as executable tests.

Threat model covered: review-step bypass by a hand-made POST, forged / replayed / expired / re-targeted confirmation tokens,
privilege escalation by role, cross-tenant IDOR, CSRF, immediate loss of access after revoke, ownership-transfer safety,
audit trail without secrets, and the seat-limit exception contract."""

import re
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import AuditLogEntry
from apps.dashboard import staff_confirm
from apps.dashboard.tests.staff_flow import confirmed_action, confirmed_add, token_from
from apps.stores.models import Store, StoreMembership
from apps.stores.services import membership_service as ms
from apps.subscriptions.services.entitlement_service import UsageLimitExceeded

User = get_user_model()
HOST = f"staffsec.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"
ROLE = StoreMembership.Role
ACTIVE = StoreMembership.MembershipStatus.ACTIVE


def _member(store, phone, role, status=ACTIVE, password="pass12345"):
    user = User.objects.create_user(username=phone, password=password, is_staff=True)
    kwargs = {"accepted_at": timezone.now()}
    if status == StoreMembership.MembershipStatus.REVOKED:
        kwargs["revoked_at"] = timezone.now()
    return StoreMembership.objects.create(store=store, user=user, role=role, status=status, **kwargs)


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class Base(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.owner_m = _member(self.store, "09127700001", ROLE.OWNER)
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="09127700001", password="pass12345")
        self.add_url = reverse("dashboard:staff-add")

    def login_as(self, username):
        client = Client(HTTP_HOST=HOST)
        client.login(username=username, password="pass12345")
        return client


class ReviewBypassTests(Base):
    PAYLOAD = {"phone": "09127700100", "role": ROLE.ANALYST, "full_name": "علی", "email": ""}

    def exists(self, phone="09127700100"):
        return StoreMembership.objects.filter(store=self.store, user__username=phone).exists()

    def test_direct_post_without_review_never_adds_anyone(self):
        for extra in ({}, {"step": "confirm"}, {"step": "confirm", "review_token": "x"}, {"step": "confirm", "review_token": ""}):
            r = self.client.post(self.add_url, {**self.PAYLOAD, **extra})
            self.assertEqual(r.status_code, 200, extra)
            self.assertContains(r, "مرحلهٔ «بررسی و تأیید»")
        self.assertFalse(self.exists())
        self.assertFalse(User.objects.filter(username="09127700100").exists(), "no orphan account either")

    def test_review_then_confirm_adds_exactly_once(self):
        r = confirmed_add(self.client, self.add_url, self.PAYLOAD)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(self.exists())
        r2 = confirmed_add(self.client, self.add_url, self.PAYLOAD)  # second time: already an active member
        self.assertEqual(StoreMembership.objects.filter(store=self.store, user__username="09127700100").count(), 1)

    def test_token_is_bound_to_the_exact_reviewed_values(self):
        review = self.client.post(self.add_url, {**self.PAYLOAD, "step": "review"})
        token = token_from(review)
        tampered = {**self.PAYLOAD, "role": ROLE.CATALOG_MANAGER}      # escalate the role after review
        r = self.client.post(self.add_url, {**tampered, "step": "confirm", "review_token": token})
        self.assertFalse(self.exists())
        other_phone = {**self.PAYLOAD, "phone": "09127700101"}          # point the token at another person
        self.client.post(self.add_url, {**other_phone, "step": "confirm", "review_token": token})
        self.assertFalse(self.exists("09127700101"))

    def test_token_is_bound_to_the_issuing_user_and_store_and_expires(self):
        token = token_from(self.client.post(self.add_url, {**self.PAYLOAD, "step": "review"}))
        # another owner (another session) cannot replay it
        other_owner_user = User.objects.create_user(username="09127700009", password="pass12345", is_staff=True)
        other_store = Store.objects.create(name="B", slug="staffsec-b", status=Store.Status.ACTIVE, admin_subdomain="staffsec-b")
        StoreMembership.objects.create(store=other_store, user=other_owner_user, role=ROLE.OWNER, status=ACTIVE, accepted_at=timezone.now())
        c = Client(HTTP_HOST=f"staffsec-b.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}")
        with override_settings(ALLOWED_HOSTS=["*"]):
            c.login(username="09127700009", password="pass12345")
            c.post(self.add_url, {**self.PAYLOAD, "step": "confirm", "review_token": token})
        self.assertFalse(StoreMembership.objects.filter(user__username="09127700100").exists())
        with patch.object(staff_confirm, "MAX_AGE_SECONDS", -1):          # expired
            self.client.post(self.add_url, {**self.PAYLOAD, "step": "confirm", "review_token": token})
        self.assertFalse(self.exists())

    def test_invalid_data_is_still_rejected_before_any_token_is_issued(self):
        r = self.client.post(self.add_url, {"phone": "12ab", "role": ROLE.ANALYST, "step": "review"})
        self.assertIsNone(token_from(r))
        r = self.client.post(self.add_url, {"phone": "09127700102", "role": ROLE.OWNER, "step": "review"})
        self.assertIsNone(token_from(r))


class SensitiveActionConfirmationTests(Base):
    def setUp(self):
        super().setUp()
        self.member = _member(self.store, "09127700200", ROLE.ANALYST)

    def url(self, name, m=None):
        return reverse(f"dashboard:{name}", args=[(m or self.member).pk])

    def test_change_role_requires_the_confirmation_token(self):
        r = self.client.post(self.url("staff-change-role"), {"role": ROLE.ORDER_MANAGER})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "تأیید تغییر نقش")
        self.member.refresh_from_db()
        self.assertEqual(self.member.role, ROLE.ANALYST)
        forged = self.client.post(self.url("staff-change-role"), {"role": ROLE.ORDER_MANAGER, "confirm_token": "forged"})
        self.member.refresh_from_db()
        self.assertEqual(self.member.role, ROLE.ANALYST)
        # token for ORDER_MANAGER cannot be reused for another (higher) role
        token = token_from(r)
        self.client.post(self.url("staff-change-role"), {"role": ROLE.ADMINISTRATOR, "confirm_token": token})
        self.member.refresh_from_db()
        self.assertEqual(self.member.role, ROLE.ANALYST)
        confirmed_action(self.client, self.url("staff-change-role"), {"role": ROLE.ORDER_MANAGER})
        self.member.refresh_from_db()
        self.assertEqual(self.member.role, ROLE.ORDER_MANAGER)

    def test_token_for_one_member_cannot_act_on_another(self):
        other = _member(self.store, "09127700201", ROLE.ANALYST)
        token = token_from(self.client.post(self.url("staff-revoke")))
        self.client.post(self.url("staff-revoke", other), {"confirm_token": token})
        other.refresh_from_db()
        self.assertEqual(other.status, ACTIVE)

    def test_revoke_and_reactivate_need_confirmation(self):
        r = self.client.post(self.url("staff-revoke"))
        self.assertContains(r, "تأیید لغو عضویت")
        self.member.refresh_from_db()
        self.assertEqual(self.member.status, ACTIVE)
        confirmed_action(self.client, self.url("staff-revoke"))
        self.member.refresh_from_db()
        self.assertEqual(self.member.status, StoreMembership.MembershipStatus.REVOKED)
        self.client.post(self.url("staff-reactivate"))
        self.member.refresh_from_db()
        self.assertEqual(self.member.status, StoreMembership.MembershipStatus.REVOKED)
        confirmed_action(self.client, self.url("staff-reactivate"))
        self.member.refresh_from_db()
        self.assertEqual(self.member.status, ACTIVE)

    def test_ownership_transfer_needs_token_and_the_typed_phone(self):
        admin = _member(self.store, "09127700202", ROLE.ADMINISTRATOR)
        url = self.url("staff-transfer-ownership", admin)
        self.client.post(url)                                           # no token
        wrong = confirmed_action(self.client, url, extra={"confirm_phone": "09127700999"})   # wrong typed phone
        self.client.post(url, {"confirm_token": token_from(self.client.post(url)), "confirm_phone": ""})
        admin.refresh_from_db(); self.owner_m.refresh_from_db()
        self.assertEqual((admin.role, self.owner_m.role), (ROLE.ADMINISTRATOR, ROLE.OWNER))
        confirmed_action(self.client, url, extra={"confirm_phone": "۰۹۱۲۷۷۰۰۲۰۲"})            # Persian digits are normalised
        admin.refresh_from_db(); self.owner_m.refresh_from_db()
        self.assertEqual((admin.role, self.owner_m.role), (ROLE.OWNER, ROLE.ADMINISTRATOR))
        self.assertEqual(StoreMembership.objects.filter(store=self.store, role=ROLE.OWNER, status=ACTIVE).count(), 1)

    def test_transfer_to_a_revoked_or_self_target_is_refused(self):
        revoked = _member(self.store, "09127700203", ROLE.ADMINISTRATOR, status=StoreMembership.MembershipStatus.REVOKED)
        confirmed_action(self.client, self.url("staff-transfer-ownership", revoked), extra={"confirm_phone": revoked.user.username})
        revoked.refresh_from_db(); self.owner_m.refresh_from_db()
        self.assertEqual((revoked.role, self.owner_m.role), (ROLE.ADMINISTRATOR, ROLE.OWNER))
        confirmed_action(self.client, self.url("staff-transfer-ownership", self.owner_m), extra={"confirm_phone": "09127700001"})
        self.owner_m.refresh_from_db()
        self.assertEqual(self.owner_m.role, ROLE.OWNER)

    def test_owner_cannot_be_revoked_or_demoted_and_self_protection_holds(self):
        confirmed_action(self.client, self.url("staff-revoke", self.owner_m))
        confirmed_action(self.client, self.url("staff-change-role", self.owner_m), {"role": ROLE.ANALYST})
        self.owner_m.refresh_from_db()
        self.assertEqual((self.owner_m.role, self.owner_m.status), (ROLE.OWNER, ACTIVE))


class PermissionMatrixTests(Base):
    """Every team-management view × every role × anonymous × another tenant."""

    VIEWS = ("staff-list", "staff-add", "staff-change-role", "staff-revoke", "staff-reactivate", "staff-transfer-ownership")

    def setUp(self):
        super().setUp()
        self.target = _member(self.store, "09127700300", ROLE.ANALYST)

    def hit(self, client, name, method="get", target=None):
        url = reverse(f"dashboard:{name}", args=[(target or self.target).pk]) if name not in ("staff-list", "staff-add") else reverse(f"dashboard:{name}")
        return getattr(client, method)(url, {"role": ROLE.ADMINISTRATOR} if method == "post" else {})

    def test_every_non_owner_role_is_denied_everywhere_and_nothing_changes(self):
        for i, role in enumerate((ROLE.ADMINISTRATOR, ROLE.CATALOG_MANAGER, ROLE.ORDER_MANAGER, ROLE.CONTENT_EDITOR, ROLE.ANALYST)):
            phone = f"091277004{i:02d}"
            _member(self.store, phone, role)
            client = self.login_as(phone)
            for name in self.VIEWS:
                for method in ("get", "post"):
                    resp = self.hit(client, name, method)
                    self.assertIn(resp.status_code, (403, 405), f"{role} {method} {name} -> {resp.status_code}")
        self.target.refresh_from_db()
        self.assertEqual((self.target.role, self.target.status), (ROLE.ANALYST, ACTIVE))
        self.assertEqual(StoreMembership.objects.filter(store=self.store, role=ROLE.OWNER, status=ACTIVE).count(), 1)

    def test_anonymous_is_redirected_and_changes_nothing(self):
        anon = Client(HTTP_HOST=HOST)
        for name in self.VIEWS:
            for method in ("get", "post"):
                resp = self.hit(anon, name, method)
                self.assertIn(resp.status_code, (302, 403, 405), f"{method} {name}")
                self.assertNotEqual(resp.status_code, 200)
        self.target.refresh_from_db()
        self.assertEqual((self.target.role, self.target.status), (ROLE.ANALYST, ACTIVE))

    def test_other_tenant_owner_gets_404_for_this_stores_members_on_every_object_view(self):
        other_store = Store.objects.create(name="B", slug="staffsec-c", status=Store.Status.ACTIVE, admin_subdomain="staffsec-c")
        _member(other_store, "09127700500", ROLE.OWNER)
        c = Client(HTTP_HOST=f"staffsec-c.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}")
        with override_settings(ALLOWED_HOSTS=["*"]):
            c.login(username="09127700500", password="pass12345")
            for name in self.VIEWS[2:]:
                for method in ("get", "post"):
                    resp = self.hit(c, name, method)
                    self.assertIn(resp.status_code, (404, 405), f"{method} {name} -> {resp.status_code}")
        self.target.refresh_from_db()
        self.assertEqual((self.target.role, self.target.status), (ROLE.ANALYST, ACTIVE))

    def test_csrf_is_enforced_on_every_mutating_staff_view(self):
        c = Client(HTTP_HOST=HOST, enforce_csrf_checks=True)
        c.login(username="09127700001", password="pass12345")
        for name in self.VIEWS[1:]:
            resp = self.hit(c, name, "post")
            self.assertEqual(resp.status_code, 403, name)
        self.target.refresh_from_db()
        self.assertEqual((self.target.role, self.target.status), (ROLE.ANALYST, ACTIVE))


class AccessAfterRevokeTests(Base):
    def test_revoked_member_loses_access_on_the_very_next_request(self):
        m = _member(self.store, "09127700600", ROLE.ORDER_MANAGER)
        session_client = self.login_as("09127700600")
        self.assertEqual(session_client.get(reverse("dashboard:order-list")).status_code, 200)
        confirmed_action(self.client, reverse("dashboard:staff-revoke", args=[m.pk]))
        resp = session_client.get(reverse("dashboard:order-list"))
        self.assertNotEqual(resp.status_code, 200, "an already-open session must not survive the revoke")

    def test_role_downgrade_applies_immediately_to_open_sessions(self):
        m = _member(self.store, "09127700601", ROLE.ANALYST)
        session_client = self.login_as("09127700601")
        probe = reverse("dashboard:collection-list")
        self.assertEqual(session_client.get(probe).status_code, 403)
        confirmed_action(self.client, reverse("dashboard:staff-change-role", args=[m.pk]), {"role": ROLE.ADMINISTRATOR})
        self.assertEqual(session_client.get(probe).status_code, 200)
        confirmed_action(self.client, reverse("dashboard:staff-change-role", args=[m.pk]), {"role": ROLE.ANALYST})
        self.assertEqual(session_client.get(probe).status_code, 403)


class AuditTrailAndSeatContractTests(Base):
    def test_audit_events_exist_and_contain_no_secrets(self):
        confirmed_add(self.client, self.add_url, {"phone": "09127700700", "role": ROLE.ANALYST})
        m = StoreMembership.objects.get(store=self.store, user__username="09127700700")
        confirmed_action(self.client, reverse("dashboard:staff-change-role", args=[m.pk]), {"role": ROLE.CONTENT_EDITOR})
        confirmed_action(self.client, reverse("dashboard:staff-revoke", args=[m.pk]))
        codes = set(AuditLogEntry.objects.filter(store=self.store).values_list("action_code", flat=True))
        self.assertTrue({"staff.added", "staff.role_changed", "staff.revoked"} <= codes, codes)
        blob = " ".join(
            str(getattr(e, f)) for e in AuditLogEntry.objects.filter(store=self.store, action_code__startswith="staff.")
            for f in ("before_summary", "after_summary", "metadata", "object_label", "object_type", "object_id")
            if hasattr(e, f)
        )
        self.assertTrue(blob.strip())
        for secret in ("pass12345", "password", "token", "otp", "OTP"):
            self.assertNotIn(secret, blob)

    def test_seat_limit_keeps_its_exception_contract_and_the_view_shows_a_message(self):
        with patch("apps.subscriptions.services.enforcement.enforce_can_add_staff", side_effect=UsageLimitExceeded("staff.members")):
            with self.assertRaises(UsageLimitExceeded):
                ms.add_staff_member(self.store, phone="09127700800", role=ROLE.ANALYST, invited_by=None)
            r = confirmed_add(self.client, self.add_url, {"phone": "09127700801", "role": ROLE.ANALYST})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "به سقفِ پلنِ فعلیِ شما")
        self.assertFalse(User.objects.filter(username="09127700801").exists())
