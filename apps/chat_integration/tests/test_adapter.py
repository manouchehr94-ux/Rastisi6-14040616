import logging
import uuid
from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.chat_integration import client, conf
from apps.chat_integration.services import enablement, identity_service, tenant_service
from apps.core.models import AuditLogEntry
from apps.stores.models import Store, StoreDomain, StoreIntegrationConnection, StoreMembership

from .base import (
    CHAT_SETTINGS, PASSWORD, PLATFORM_ADMIN_HOST, ChatTestCase, fragment_assertion, make_customer, make_member,
    make_store, verify_jwt,
)

Role = StoreMembership.Role


# ------------------------------------------------------------------------------------------ default OFF
class DisabledByDefaultTests(TestCase):
    """Deploying this code must enable NOTHING."""

    def test_global_flag_defaults_to_off(self):
        from django.conf import settings
        self.assertFalse(settings.RASTICHAT_INTEGRATION_ENABLED)
        self.assertFalse(conf.globally_enabled())

    def test_no_store_has_chat_and_every_entry_point_is_absent(self):
        store = make_store("off", host="shop-off.example.com")
        make_member(store, "off-owner", Role.OWNER)
        self.assertFalse(enablement.chat_enabled_for_store(store))
        with override_settings(ALLOWED_HOSTS=["shop-off.example.com", "testserver"]):
            self.assertEqual(self.client.get("/chat/identity/", HTTP_HOST="shop-off.example.com").status_code, 404)
            page = self.client.get("/", HTTP_HOST="shop-off.example.com")
            self.assertNotContains(page, "RastiChat", status_code=page.status_code)
            self.assertNotContains(page, "/chat/identity/", status_code=page.status_code)

    def test_enabling_requires_the_global_flag(self):
        store = make_store("off2")
        with self.assertRaises(enablement.ChatEnablementError):
            enablement.enable_for_store(store, actor=None)
        self.assertFalse(StoreIntegrationConnection.objects.filter(store=store).exists())

    def test_misconfiguration_fails_fast_at_startup_only_when_enabled(self):
        conf.validate_settings()                                                   # off: always fine
        with override_settings(RASTICHAT_INTEGRATION_ENABLED=True, RASTICHAT_BASE_URL="", RASTICHAT_KEY_ID="",
                               RASTICHAT_PRIVATE_KEY="", RASTICHAT_PRIVATE_KEY_FILE=""):
            with self.assertRaises(ImproperlyConfigured) as ctx:
                conf.validate_settings()
        self.assertIn("RASTICHAT_BASE_URL", str(ctx.exception))
        self.assertIn("RASTICHAT_PRIVATE_KEY", str(ctx.exception))

    def test_provider_is_not_in_the_merchant_facing_integration_registry(self):
        from apps.stores.integrations.registry import get_provider
        self.assertIsNone(get_provider(enablement.PROVIDER_CODE))                  # merchants can never self-enable chat


# ------------------------------------------------------------------------------------------ client / signing
@override_settings(**CHAT_SETTINGS)
class ClientSigningTests(SimpleTestCase):
    def test_assertion_is_signed_with_our_key_and_carries_only_server_side_claims(self):
        token = client.make_assertion(actor="customer", sub="c7", tenant="tenant-uuid", name="Sara", origin="https://shop.example.com")
        header, claims = verify_jwt(token)
        self.assertEqual(header, {"alg": "EdDSA", "typ": "JWT", "kid": "ick_testkey"})
        self.assertEqual((claims["iss"], claims["aud"], claims["actor"], claims["sub"], claims["tenant"]),
                         ("rastisi", "rastichat:identity", "customer", "c7", "tenant-uuid"))
        self.assertLessEqual(claims["exp"] - claims["iat"], 120)
        self.assertNotIn("role", claims)
        self.assertNotEqual(token, client.make_assertion(actor="customer", sub="c7", tenant="tenant-uuid"))   # fresh jti every time

    def test_a_tampered_assertion_does_not_verify(self):
        from cryptography.exceptions import InvalidSignature
        token = client.make_assertion(actor="tenant_staff", sub="u1", tenant="t", role="operator")
        head, payload, sig = token.split(".")
        forged_payload = payload[:-4] + ("AAAA" if payload[-4:] != "AAAA" else "BBBB")
        with self.assertRaises((InvalidSignature, ValueError)):
            verify_jwt(f"{head}.{forged_payload}.{sig}")

    def test_api_request_is_bound_to_method_path_body_and_short_lived(self):
        captured = {}

        def fake_http(method, url, data=None, headers=None, timeout=None, allow_redirects=None):
            captured.update(method=method, url=url, data=data, headers=headers, allow_redirects=allow_redirects, timeout=timeout)
            resp = mock.Mock(status_code=200)
            resp.json.return_value = {"ok": True}
            return resp
        with mock.patch("apps.chat_integration.client.requests.request", side_effect=fake_http):
            client.request("PUT", "/api/v1/integrations/tenants/abc/", {"display_name": "S"})
        self.assertEqual(captured["url"], "https://chat.example.test/api/v1/integrations/tenants/abc/")
        self.assertFalse(captured["allow_redirects"])
        token = captured["headers"]["Authorization"].removeprefix("Bearer ")
        _, claims = verify_jwt(token)
        import base64, hashlib
        self.assertEqual((claims["htm"], claims["htu"], claims["aud"]), ("PUT", "/api/v1/integrations/tenants/abc/", "rastichat:api"))
        self.assertEqual(claims["bh"], base64.urlsafe_b64encode(hashlib.sha256(captured["data"]).digest()).rstrip(b"=").decode())
        self.assertLessEqual(claims["exp"] - claims["iat"], 60)
        self.assertEqual(captured["timeout"], (3.05, 10))

    def test_errors_surface_the_contract_code_and_never_log_the_token(self):
        resp = mock.Mock(status_code=403)
        resp.json.return_value = {"error": {"code": "scope_denied", "message": "no"}}
        with mock.patch("apps.chat_integration.client.requests.request", return_value=resp), self.assertLogs("apps.chat_integration.client", "WARNING") as logs:
            with self.assertRaises(client.RastiChatError) as ctx:
                client.request("GET", "/api/v1/integrations/me/")
        self.assertEqual((ctx.exception.status, ctx.exception.code), (403, "scope_denied"))
        joined = " ".join(logs.output)
        self.assertNotIn("Bearer", joined)
        self.assertNotIn("eyJ", joined)

    def test_unreachable_rastichat_is_a_clean_error(self):
        import requests
        with mock.patch("apps.chat_integration.client.requests.request", side_effect=requests.ConnectionError("x")):
            with self.assertRaises(client.RastiChatError):
                client.request("GET", "/api/v1/integrations/me/")

    @override_settings(RASTICHAT_PRIVATE_KEY="", RASTICHAT_PRIVATE_KEY_FILE="")
    def test_missing_key_is_refused_not_guessed(self):
        with self.assertRaises(client.RastiChatError):
            client.make_assertion(actor="customer", sub="c1", tenant="t")


# ------------------------------------------------------------------------------------------ enablement / tenant mapping
class EnablementTests(ChatTestCase):
    def setUp(self):
        super().setUp()
        self.store = make_store("pilot", host="shop-a.example.com")
        self.owner = make_member(self.store, "pilot-owner", Role.OWNER)

    def test_enable_provisions_the_tenant_then_turns_chat_on(self):
        self.assertFalse(enablement.chat_enabled_for_store(self.store))
        enablement.enable_for_store(self.store, actor=self.owner)
        self.assertTrue(enablement.chat_enabled_for_store(self.store))
        self.assertEqual(enablement.project_public_key(self.store), "11111111-2222-3333-4444-555555555555")
        call = self.calls[0]
        self.assertEqual((call["method"], call["path"]), ("PUT", f"/api/v1/integrations/tenants/{self.store.public_id}/"))
        body = call["body"]
        self.assertEqual(body["display_name"], self.store.name)
        self.assertEqual(body["verified_domains"], ["shop-a.example.com"])
        self.assertEqual(body["status"], "active")
        self.assertEqual(body["defaults"]["widget"]["launcher"]["mode"], "icon")           # icon only
        self.assertFalse(body["defaults"]["widget"]["pre_chat"]["enabled"])                # no questions
        self.assertTrue(AuditLogEntry.objects.filter(store=self.store, action_code="chat.enabled").exists())

    def test_the_tenant_id_is_the_stores_public_uuid_never_a_browser_value(self):
        self.assertEqual(tenant_service.external_tenant_id(self.store), str(self.store.public_id))

    def test_only_verified_unretired_domains_are_sent(self):
        StoreDomain.objects.create(store=self.store, hostname="unverified.example.com", domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
                                   verification_status=StoreDomain.VerificationStatus.UNVERIFIED)
        StoreDomain.objects.create(store=self.store, hostname="retired.example.com", domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
                                   verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=__import__("django").utils.timezone.now(),
                                   retired_at=__import__("django").utils.timezone.now())
        self.assertEqual(tenant_service.verified_hostnames(self.store), ["shop-a.example.com"])

    def test_chat_is_never_enabled_when_rastichat_fails(self):
        self.fail_requests = True
        with self.assertRaises(client.RastiChatError):
            enablement.enable_for_store(self.store, actor=self.owner)
        self.assertFalse(enablement.chat_enabled_for_store(self.store))
        self.assertFalse(StoreIntegrationConnection.objects.filter(store=self.store, is_active=True).exists())

    def test_inactive_store_cannot_be_enabled_and_suspension_hides_chat_immediately(self):
        suspended = make_store("sus", active=False)
        with self.assertRaises(enablement.ChatEnablementError):
            enablement.enable_for_store(suspended, actor=None)
        self.enable(self.store)
        self.store.status = Store.Status.SUSPENDED
        self.store.save()
        self.assertFalse(enablement.chat_enabled_for_store(self.store))

    def test_enable_is_idempotent_and_disable_is_an_instant_rollback(self):
        self.enable(self.store, self.owner)
        self.enable(self.store, self.owner)
        self.assertEqual(StoreIntegrationConnection.objects.filter(store=self.store, provider_code="rastichat").count(), 1)
        enablement.disable_for_store(self.store, actor=self.owner)
        self.assertFalse(enablement.chat_enabled_for_store(self.store))
        self.assertTrue(AuditLogEntry.objects.filter(store=self.store, action_code="chat.disabled").exists())

    def test_enabling_one_store_never_enables_another(self):
        other = make_store("other", host="shop-b.example.com")
        self.enable(self.store)
        self.assertTrue(enablement.chat_enabled_for_store(self.store))
        self.assertFalse(enablement.chat_enabled_for_store(other))

    def test_a_global_switch_off_overrides_every_store(self):
        self.enable(self.store)
        with override_settings(RASTICHAT_INTEGRATION_ENABLED=False):
            self.assertFalse(enablement.chat_enabled_for_store(self.store))


# ------------------------------------------------------------------------------------------ customer -> store
class CustomerFlowTests(ChatTestCase):
    def setUp(self):
        super().setUp()
        self.a = make_store("shop-a", host="shop-a.example.com")
        self.b = make_store("shop-b", host="shop-b.example.com")
        self.enable(self.a)
        self.customer = make_customer("alice", "09120000001")

    def identity(self, host, **extra):
        return self.client.get("/chat/identity/", HTTP_HOST=host, **extra)

    def test_widget_script_appears_only_on_the_enabled_stores_pages(self):
        page_a = self.client.get("/", HTTP_HOST="shop-a.example.com").content.decode()
        self.assertIn("https://chat.example.test/widget.js", page_a)
        self.assertIn("11111111-2222-3333-4444-555555555555", page_a)
        self.assertIn("/chat/identity/", page_a)
        self.assertNotIn("PRIVATE KEY", page_a)
        self.assertNotIn("ick_testkey", page_a)
        page_b = self.client.get("/", HTTP_HOST="shop-b.example.com").content.decode()
        self.assertNotIn("widget.js", page_b)

    def test_authenticated_customer_gets_a_signed_assertion_for_this_stores_tenant(self):
        self.client.force_login(self.customer.user)
        response = self.identity("shop-a.example.com")
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])                               # never cached
        _, claims = verify_jwt(response.content.decode())
        self.assertEqual((claims["actor"], claims["sub"], claims["tenant"]), ("customer", f"c{self.customer.pk}", str(self.a.public_id)))
        self.assertEqual(claims["origin"], "http://shop-a.example.com")
        self.assertEqual(claims["name"], self.customer.full_name)
        self.assertEqual(set(claims) - {"iss", "aud", "sub", "actor", "iat", "exp", "jti", "tenant", "name", "origin"}, set())   # no phone/email

    def test_browser_supplied_store_user_or_role_parameters_are_ignored(self):
        self.client.force_login(self.customer.user)
        response = self.client.get("/chat/identity/", {"tenant": str(self.b.public_id), "store": self.b.pk, "role": "owner",
                                                      "sub": "c999", "actor": "platform_staff"}, HTTP_HOST="shop-a.example.com")
        _, claims = verify_jwt(response.content.decode())
        self.assertEqual((claims["tenant"], claims["sub"], claims["actor"]), (str(self.a.public_id), f"c{self.customer.pk}", "customer"))
        self.assertNotIn("role", claims)

    def test_guest_gets_401_and_therefore_a_guest_widget(self):
        self.assertEqual(self.identity("shop-a.example.com").status_code, 401)

    def test_inactive_account_gets_no_assertion(self):
        self.client.force_login(self.customer.user)
        self.customer.user.is_active = False
        self.customer.user.save()
        self.assertIn(self.identity("shop-a.example.com").status_code, (401, 404))

    def test_a_non_customer_user_gets_no_customer_assertion(self):
        staff = make_member(self.a, "staff-only", Role.OWNER)
        self.client.force_login(staff)
        self.assertEqual(self.identity("shop-a.example.com").status_code, 401)

    def test_other_store_and_unknown_host_are_404(self):
        self.client.force_login(self.customer.user)
        self.assertEqual(self.identity("shop-b.example.com").status_code, 404)        # chat not enabled for B
        self.assertEqual(self.identity("localhost").status_code, 404)
        self.assertEqual(self.client.post("/chat/identity/", HTTP_HOST="shop-a.example.com").status_code, 405)

    def test_suspended_store_stops_serving_identity(self):
        self.client.force_login(self.customer.user)
        self.a.status = Store.Status.SUSPENDED
        self.a.save()
        self.assertEqual(self.identity("shop-a.example.com").status_code, 404)


# ------------------------------------------------------------------------------------------ store staff -> chat inboxes / platform support
@override_settings(ALLOWED_HOSTS=CHAT_SETTINGS["ALLOWED_HOSTS"])
class MerchantFlowTests(ChatTestCase):
    def setUp(self):
        super().setUp()
        self.a = make_store("msa", host="shop-a.example.com")
        self.b = make_store("msb", host="shop-b.example.com")
        self.enable(self.a)
        self.enable(self.b)
        self.owner = make_member(self.a, "ms-owner", Role.OWNER)
        self.admin = make_member(self.a, "ms-admin", Role.ADMINISTRATOR)
        self.order_mgr = make_member(self.a, "ms-order", Role.ORDER_MANAGER)
        self.catalog = make_member(self.a, "ms-catalog", Role.CATALOG_MANAGER)
        self.analyst = make_member(self.a, "ms-analyst", Role.ANALYST)
        self.b_admin = make_member(self.b, "ms-b-admin", Role.ADMINISTRATOR)
        self.host_a = "msa.rastisi.localhost"
        self.host_b = "msb.rastisi.localhost"

    def go(self, user, name, host=None):
        self.client.force_login(user)
        return self.client.get(reverse(name), HTTP_HOST=host or self.host_a)

    def test_roles_map_to_generic_chat_roles_and_the_tenant_comes_from_the_admin_host(self):
        for user, expected in ((self.owner, "owner"), (self.admin, "admin"), (self.order_mgr, "operator")):
            response = self.go(user, "dashboard:chat-customers")
            self.assertEqual(response.status_code, 302, user.username)
            base, assertion, next_path = fragment_assertion(response)
            self.assertEqual((base, next_path), ("https://chat.example.test/admin/sso", "/"))
            _, claims = verify_jwt(assertion)
            self.assertEqual((claims["actor"], claims["role"], claims["tenant"]), ("tenant_staff", expected, str(self.a.public_id)))
            self.assertEqual(claims["sub"], f"u{user.pk}.{self.a.public_id}")   # one RastiChat identity PER STORE
            self.assertIn("no-store", response["Cache-Control"])
            self.assertEqual(response["Referrer-Policy"], "no-referrer")

    def test_roles_without_a_chat_role_get_403_and_no_assertion(self):
        for user in (self.catalog, self.analyst):
            response = self.go(user, "dashboard:chat-customers")
            self.assertEqual(response.status_code, 403, user.username)
            self.assertNotIn("Location", response)

    def test_platform_support_is_owner_and_administrator_only(self):
        for user, ok in ((self.owner, True), (self.admin, True), (self.order_mgr, False), (self.catalog, False)):
            response = self.go(user, "dashboard:chat-support")
            self.assertEqual(response.status_code, 302 if ok else 403, user.username)
        _, assertion, next_path = fragment_assertion(self.go(self.admin, "dashboard:chat-support"))
        self.assertEqual(next_path, "/support")
        self.assertEqual(verify_jwt(assertion)[1]["role"], "admin")

    def test_staff_are_synced_to_rastichat_before_the_browser_arrives(self):
        self.go(self.order_mgr, "dashboard:chat-customers")
        sync = [c for c in self.calls if "/members/" in c["path"]]
        self.assertEqual(len(sync), 1)
        self.assertEqual((sync[0]["method"], sync[0]["path"], sync[0]["body"]["role"]),
                         ("PUT", f"/api/v1/integrations/tenants/{self.a.public_id}/members/u{self.order_mgr.pk}.{self.a.public_id}/", "operator"))

    def test_a_person_with_two_stores_gets_a_separate_chat_identity_in_each(self):
        """Isolation by construction: entering through store B can never expose store A's inbox to the same person."""
        from apps.stores.models import StoreMembership
        from django.utils import timezone
        StoreMembership.objects.create(store=self.b, user=self.owner, role=StoreMembership.Role.OWNER,
                                       status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
        self.client.force_login(self.owner)
        subs = {}
        for store, host in ((self.a, self.host_a), (self.b, self.host_b)):
            response = self.client.get("/admin-portal/chat/customers/", HTTP_HOST=host)
            self.assertEqual(response.status_code, 302, store.slug)
            subs[store.slug] = verify_jwt(fragment_assertion(response)[1])[1]["sub"]
        self.assertEqual(len(set(subs.values())), 2)

    def test_an_admin_of_store_A_cannot_reach_store_Bs_chat_through_either_host(self):
        # on B's admin host the user is not a member of B -> staff_required refuses (redirect, no assertion)
        response = self.go(self.admin, "dashboard:chat-customers", host=self.host_b)
        self.assertNotIn("#assertion=", response.get("Location", ""))
        # a multi-store admin must pick the store by using THAT store's admin host: each host yields only its own tenant
        both = make_member(self.b, "ms-both", Role.OWNER)
        StoreMembership.objects.create(store=self.a, user=both, role=Role.ADMINISTRATOR, status=StoreMembership.MembershipStatus.ACTIVE,
                                       accepted_at=__import__("django").utils.timezone.now())
        tenants = {}
        for label, host in (("a", self.host_a), ("b", self.host_b)):
            _, assertion, _ = fragment_assertion(self.go(both, "dashboard:chat-customers", host=host))
            tenants[label] = verify_jwt(assertion)[1]
        self.assertEqual(tenants["a"]["tenant"], str(self.a.public_id))
        self.assertEqual(tenants["b"]["tenant"], str(self.b.public_id))
        self.assertEqual((tenants["a"]["role"], tenants["b"]["role"]), ("admin", "owner"))     # exact role per store, never one for both

    def test_revoked_member_and_guest_cannot_use_chat(self):
        from apps.stores.services import membership_service
        membership_service.revoke_membership(StoreMembership.objects.get(store=self.a, user=self.order_mgr))
        response = self.go(self.order_mgr, "dashboard:chat-customers")
        self.assertNotIn("#assertion=", response.get("Location", ""))
        self.client.logout()
        guest = self.client.get(reverse("dashboard:chat-customers"), HTTP_HOST=self.host_a)
        self.assertNotIn("#assertion=", guest.get("Location", ""))

    def test_store_without_chat_enabled_404s_even_for_its_owner(self):
        enablement.disable_for_store(self.a, actor=self.owner)
        self.assertEqual(self.go(self.owner, "dashboard:chat-customers").status_code, 404)
        self.assertEqual(self.go(self.owner, "dashboard:chat-support").status_code, 404)

    def test_navigation_entries_follow_the_flag_and_the_role(self):
        def nav_texts(user, host):
            self.client.force_login(user)
            return self.client.get(reverse("dashboard:dashboard"), HTTP_HOST=host).content.decode()
        owner_page = nav_texts(self.owner, self.host_a)
        self.assertIn("گفتگوی مشتریان", owner_page)
        self.assertIn("پشتیبانی پلتفرم", owner_page)
        order_page = nav_texts(self.order_mgr, self.host_a)
        self.assertIn("گفتگوی مشتریان", order_page)
        self.assertNotIn("پشتیبانی پلتفرم", order_page)
        enablement.disable_for_store(self.a, actor=self.owner)
        self.assertNotIn("گفتگوی مشتریان", nav_texts(self.owner, self.host_a))


# ------------------------------------------------------------------------------------------ platform owner -> store
@override_settings(ALLOWED_HOSTS=CHAT_SETTINGS["ALLOWED_HOSTS"])
class PlatformFlowTests(ChatTestCase):
    def setUp(self):
        super().setUp()
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.superuser = User.objects.create_user(username="pf-super@example.com", email="pf-super@example.com", password=PASSWORD,
                                                  is_staff=True, is_superuser=True)
        self.staff_only = User.objects.create_user(username="pf-staff@example.com", email="pf-staff@example.com", password=PASSWORD, is_staff=True)
        self.store = make_store("pf-store", host="shop-a.example.com")
        self.owner = make_member(self.store, "pf-owner", Role.OWNER)
        # the platform-admin URLconf is host-isolated (not the default urlconf): use the literal paths, like the existing tests
        paths = {
            "store-detail": "/stores/{0}/", "store-chat-enable": "/stores/{0}/chat/enable/",
            "store-chat-disable": "/stores/{0}/chat/disable/", "store-chat-message": "/stores/{0}/chat/message/",
            "chat-inbox": "/chat/inbox/", "user-suspend": "/users/{0}/suspend/",
        }
        self.url = lambda name, *a: paths[name].format(*a)
        self.client.force_login(self.superuser)

    def get(self, name, *a, **kw):
        return self.client.get(self.url(name, *a), HTTP_HOST=PLATFORM_ADMIN_HOST, **kw)

    def post(self, name, data=None, *a):
        return self.client.post(self.url(name, *a), data or {}, HTTP_HOST=PLATFORM_ADMIN_HOST)

    def test_only_the_platform_owner_can_enable_disable_and_message(self):
        for who in (self.staff_only, self.owner):
            self.client.force_login(who)
            for name in ("store-chat-enable", "store-chat-disable"):
                self.assertEqual(self.post(name, None, self.store.public_id).status_code, 302)
                self.assertIn("login", self.post(name, None, self.store.public_id)["Location"])
            self.assertIn("login", self.get("store-chat-message", self.store.public_id)["Location"])
            self.assertIn("login", self.get("chat-inbox")["Location"])
        self.assertFalse(enablement.chat_enabled_for_store(self.store))
        self.assertEqual(self.calls, [])

    def test_owner_enables_a_pilot_store_and_the_page_reflects_it(self):
        page = self.get("store-detail", self.store.public_id, data={"tab": "chat"})
        self.assertContains(page, "فعال‌سازی گفتگو برای این فروشگاه")
        self.post("store-chat-enable", None, self.store.public_id)
        self.assertTrue(enablement.chat_enabled_for_store(self.store))
        page = self.get("store-detail", self.store.public_id, data={"tab": "chat"})
        self.assertContains(page, "فعال برای این فروشگاه")
        self.assertContains(page, "ارسال پیام به مدیر فروشگاه")
        self.post("store-chat-disable", None, self.store.public_id)
        self.assertFalse(enablement.chat_enabled_for_store(self.store))

    def test_enable_failure_is_reported_and_nothing_is_enabled(self):
        self.fail_requests = True
        response = self.client.post(self.url("store-chat-enable", self.store.public_id), HTTP_HOST=PLATFORM_ADMIN_HOST, follow=True)
        self.assertContains(response, "گفتگو فعال نشد")
        self.assertFalse(enablement.chat_enabled_for_store(self.store))

    def test_chat_tab_is_absent_when_the_integration_is_globally_off(self):
        with override_settings(RASTICHAT_INTEGRATION_ENABLED=False):
            self.assertNotContains(self.get("store-detail", self.store.public_id), "گفتگوی آنلاین")

    def test_platform_owner_messages_a_store_that_never_wrote_first(self):
        self.enable(self.store, self.superuser)
        form = self.get("store-chat-message", self.store.public_id)
        self.assertEqual(form.status_code, 200)
        key = str(form.context["idempotency_key"])
        response = self.post("store-chat-message", {"subject": "اطلاعیه", "message": "سلام، لطفاً اشتراک را بررسی کنید", "idempotency_key": key}, self.store.public_id)
        self.assertEqual(response.status_code, 302)
        member_call, start_call = self.calls
        self.assertEqual((member_call["method"], member_call["path"], member_call["body"]["role"]),
                         ("PUT", f"/api/v1/integrations/platform/members/u{self.superuser.pk}/", "owner"))
        self.assertEqual(start_call["path"], f"/api/v1/integrations/tenants/{self.store.public_id}/support-conversations/")
        self.assertEqual(start_call["body"]["initiator_user_id"], f"u{self.superuser.pk}")
        self.assertEqual((start_call["body"]["subject"], start_call["body"]["message"]), ("اطلاعیه", "سلام، لطفاً اشتراک را بررسی کنید"))
        self.assertEqual(start_call["idempotency_key"], f"rs-{key}")
        self.assertTrue(AuditLogEntry.objects.filter(store=self.store, action_code="chat.platform_message_sent").exists())

    def test_double_submit_uses_the_same_idempotency_key_so_rastichat_dedupes(self):
        self.enable(self.store, self.superuser)
        key = str(uuid.uuid4())
        for _ in range(2):
            self.post("store-chat-message", {"subject": "s", "message": "hello", "idempotency_key": key}, self.store.public_id)
        keys = {c["idempotency_key"] for c in self.calls if c["path"].endswith("/support-conversations/")}
        self.assertEqual(keys, {f"rs-{key}"})

    def test_invalid_or_empty_submissions_make_no_call(self):
        self.enable(self.store, self.superuser)
        for data in ({"message": "x", "idempotency_key": "not-a-uuid"}, {"message": "   ", "idempotency_key": str(uuid.uuid4())}):
            self.post("store-chat-message", data, self.store.public_id)
        self.assertEqual(self.calls, [])

    def test_rastichat_failure_gives_a_friendly_error(self):
        self.enable(self.store, self.superuser)
        self.fail_requests = True
        response = self.client.post(self.url("store-chat-message", self.store.public_id),
                                    {"message": "hello", "idempotency_key": str(uuid.uuid4())}, HTTP_HOST=PLATFORM_ADMIN_HOST, follow=True)
        self.assertContains(response, "ارسال پیام ناموفق بود")

    def test_messaging_a_store_without_chat_404s_and_other_stores_are_unaffected(self):
        self.assertEqual(self.get("store-chat-message", self.store.public_id).status_code, 404)

    def test_platform_inbox_sso_uses_a_platform_staff_assertion(self):
        response = self.get("chat-inbox")
        base, assertion, next_path = fragment_assertion(response)
        self.assertEqual((base, next_path), ("https://chat.example.test/platform/sso", "/inbox"))
        _, claims = verify_jwt(assertion)
        self.assertEqual((claims["actor"], claims["role"], claims["sub"]), ("platform_staff", "owner", f"u{self.superuser.pk}"))
        self.assertNotIn("tenant", claims)


# ------------------------------------------------------------------------------------------ lifecycle hooks
class LifecycleHookTests(ChatTestCase):
    def setUp(self):
        super().setUp()
        self.store = make_store("hk", host="shop-a.example.com")
        self.owner = make_member(self.store, "hk-owner", Role.OWNER)
        self.operator = make_member(self.store, "hk-op", Role.ORDER_MANAGER)
        self.enable(self.store)

    def removals(self):
        return [c for c in self.calls if c["method"] == "DELETE"]

    def test_store_suspension_and_activation_propagate_after_commit(self):
        from apps.stores.services.store_status_service import activate_store, suspend_store
        with self.captureOnCommitCallbacks(execute=True):
            suspend_store(self.store, actor=self.owner, reason="test")
        self.assertEqual(self.calls[-1]["body"], {"status": "suspended"})
        with self.captureOnCommitCallbacks(execute=True):
            activate_store(self.store, actor=self.owner)
        self.assertEqual(self.calls[-1]["body"], {"status": "active"})

    def test_stores_without_chat_make_no_calls(self):
        other = make_store("hk-other")
        from apps.stores.services.store_status_service import suspend_store
        with self.captureOnCommitCallbacks(execute=True):
            suspend_store(other, actor=self.owner, reason="test")
        self.assertEqual(self.calls, [])

    def test_revoking_a_member_removes_their_chat_access(self):
        from apps.stores.services import membership_service
        with self.captureOnCommitCallbacks(execute=True):
            membership_service.revoke_membership(StoreMembership.objects.get(store=self.store, user=self.operator))
        self.assertEqual([c["path"] for c in self.removals()],
                         [f"/api/v1/integrations/tenants/{self.store.public_id}/members/u{self.operator.pk}.{self.store.public_id}/"])

    def test_role_change_removes_access_only_when_the_new_role_has_no_chat_role(self):
        from apps.stores.services import membership_service
        membership = StoreMembership.objects.get(store=self.store, user=self.operator)
        with self.captureOnCommitCallbacks(execute=True):
            membership_service.change_role(membership, new_role=Role.ADMINISTRATOR)
        self.assertEqual(self.removals(), [])
        with self.captureOnCommitCallbacks(execute=True):
            membership_service.change_role(membership, new_role=Role.ANALYST)
        self.assertEqual(len(self.removals()), 1)

    def test_a_failing_rastichat_never_breaks_the_rastisi_operation(self):
        from apps.stores.services import membership_service
        self.fail_requests = True
        with self.captureOnCommitCallbacks(execute=True):
            membership_service.revoke_membership(StoreMembership.objects.get(store=self.store, user=self.operator))
        self.assertEqual(StoreMembership.objects.get(store=self.store, user=self.operator).status, StoreMembership.MembershipStatus.REVOKED)

    def test_suspending_a_user_disables_their_chat_identity(self):
        from django.contrib.auth import get_user_model
        superuser = get_user_model().objects.create_user(username="hk-super", email="hk-super@example.com", password=PASSWORD,
                                                        is_staff=True, is_superuser=True)
        self.client.force_login(superuser)
        with override_settings(ALLOWED_HOSTS=CHAT_SETTINGS["ALLOWED_HOSTS"]), self.captureOnCommitCallbacks(execute=True):
            self.client.post(f"/users/{self.operator.pk}/suspend/", {"reason": "x"},
                             HTTP_HOST=PLATFORM_ADMIN_HOST)
        paths = [c["path"] for c in self.calls]
        self.assertIn(f"/api/v1/integrations/users/u{self.operator.pk}.{self.store.public_id}/disable/", paths)   # per-store identity
        self.assertIn(f"/api/v1/integrations/users/u{self.operator.pk}/disable/", paths)                         # platform-level identity


# ------------------------------------------------------------------------------------------ reconcile command
class SyncCommandTests(ChatTestCase):
    def test_sync_resends_only_enabled_stores_and_never_enables_anything(self):
        on = make_store("sync-on", host="shop-a.example.com")
        off = make_store("sync-off")
        self.enable(on)
        on.name = "Renamed"
        on.save()
        call_command("chat_sync_tenants")
        puts = [c for c in self.calls if c["method"] == "PUT"]
        self.assertEqual(len(puts), 1)
        self.assertEqual((puts[0]["path"], puts[0]["body"]["display_name"]), (f"/api/v1/integrations/tenants/{on.public_id}/", "Renamed"))
        self.assertFalse(enablement.chat_enabled_for_store(off))

    def test_dry_run_calls_nothing(self):
        self.enable(make_store("sync-dry", host="shop-a.example.com"))
        call_command("chat_sync_tenants", dry_run=True)
        self.assertEqual(self.calls, [])
