from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from apps.core.context_processors import shop_settings
from apps.core.models import ShopSettings
from apps.stores.models import Store, StoreDomain
from apps.stores.services import enamad_verification_service, integration_service
from apps.stores.services.enamad_verification_service import (
    EnamadBadgeError,
    EnamadVerificationMetaError,
    parse_enamad_badge_identifiers,
    parse_enamad_verification_meta_tag,
)


class EnamadMetaParserTests(TestCase):
    def test_accepts_exact_name_content_meta(self):
        meta = parse_enamad_verification_meta_tag(
            '<meta name="enamad-verification" content="token-123">'
        )
        self.assertEqual(meta.name, "enamad-verification")
        self.assertEqual(meta.content, "token-123")

    def test_rejects_script_or_extra_element(self):
        with self.assertRaises(EnamadVerificationMetaError):
            parse_enamad_verification_meta_tag(
                '<meta name="x" content="y"><script>alert(1)</script>'
            )

    def test_rejects_http_equiv_even_if_it_is_a_meta_tag(self):
        with self.assertRaises(EnamadVerificationMetaError):
            parse_enamad_verification_meta_tag(
                '<meta http-equiv="refresh" content="0;url=https://evil.example">'
            )

    def test_rejects_event_or_extra_attributes(self):
        with self.assertRaises(EnamadVerificationMetaError):
            parse_enamad_verification_meta_tag(
                '<meta name="x" content="y" onload="alert(1)">'
            )


@override_settings(ALLOWED_HOSTS=["merchant-meta.example", "testserver"])
class MerchantEnamadMetaRenderingTests(TestCase):
    def setUp(self):
        self.store = Store.objects.create(
            name="Meta Merchant",
            slug="meta-merchant",
            admin_subdomain="meta-merchant",
            status=Store.Status.ACTIVE,
            onboarding_completed_at=timezone.now(),
        )
        ShopSettings.provision_for(self.store)
        StoreDomain.objects.create(
            store=self.store,
            hostname="merchant-meta.example",
            is_primary=True,
            domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
            verification_status=StoreDomain.VerificationStatus.VERIFIED,
            verified_at=timezone.now(),
        )
        self.meta_tag = (
            '<meta name="enamad-verification" content="merchant-safe-token">'
        )
        integration_service.connect(
            store=self.store,
            provider_code="enamad",
            values={"verification_meta_tag": self.meta_tag, "enamad_code": ""},
            actor=None,
        )

    def _request(self, host, path="/"):
        request = RequestFactory().get(path, HTTP_HOST=host)
        request.store = self.store
        return request

    def test_context_exposes_parsed_meta_on_own_verified_custom_domain(self):
        context = shop_settings(self._request("merchant-meta.example"))
        self.assertEqual(
            context["SHOP_ENAMAD_VERIFICATION_META_NAME"],
            "enamad-verification",
        )
        self.assertEqual(
            context["SHOP_ENAMAD_VERIFICATION_META_CONTENT"],
            "merchant-safe-token",
        )

    def test_platform_owned_store_subdomain_never_gets_merchant_enamad_meta(self):
        with override_settings(
            ALLOWED_HOSTS=["meta-merchant.rastisi.localhost", "testserver"]
        ):
            context = shop_settings(
                self._request("meta-merchant.rastisi.localhost")
            )
        self.assertEqual(context["SHOP_ENAMAD_VERIFICATION_META_NAME"], "")
        self.assertEqual(context["SHOP_ENAMAD_VERIFICATION_META_CONTENT"], "")

    def test_non_home_page_never_gets_verification_meta(self):
        context = shop_settings(
            self._request("merchant-meta.example", "/products/")
        )
        self.assertEqual(context["SHOP_ENAMAD_VERIFICATION_META_NAME"], "")

    def test_unverified_custom_domain_never_gets_verification_meta(self):
        StoreDomain.objects.filter(hostname="merchant-meta.example").update(
            verification_status=StoreDomain.VerificationStatus.UNVERIFIED,
            verified_at=None,
        )
        with override_settings(
            ALLOWED_HOSTS=["merchant-meta.example", "testserver"]
        ):
            context = shop_settings(self._request("merchant-meta.example"))
        self.assertEqual(context["SHOP_ENAMAD_VERIFICATION_META_NAME"], "")
        self.assertEqual(context["SHOP_ENAMAD_VERIFICATION_META_CONTENT"], "")

    def test_other_stores_verified_domain_never_gets_this_stores_meta(self):
        other_store = Store.objects.create(
            name="Other Merchant",
            slug="other-merchant",
            admin_subdomain="other-merchant",
            status=Store.Status.ACTIVE,
            onboarding_completed_at=timezone.now(),
        )
        ShopSettings.provision_for(other_store)
        StoreDomain.objects.create(
            store=other_store,
            hostname="other-merchant.example",
            is_primary=True,
            domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
            verification_status=StoreDomain.VerificationStatus.VERIFIED,
            verified_at=timezone.now(),
        )
        # other_store has no eNamad integration connected at all — its own
        # verified custom-domain home page must never show store A's meta.
        request = RequestFactory().get("/", HTTP_HOST="other-merchant.example")
        request.store = other_store
        with override_settings(
            ALLOWED_HOSTS=["other-merchant.example", "testserver"]
        ):
            context = shop_settings(request)
        self.assertEqual(context["SHOP_ENAMAD_VERIFICATION_META_NAME"], "")
        self.assertEqual(context["SHOP_ENAMAD_VERIFICATION_META_CONTENT"], "")
        self.assertNotIn("merchant-safe-token", str(context))


class EnamadBadgeParserTests(TestCase):
    """Phase 5 — the final, issued eNamad trust badge is represented as two
    structured identifiers (never a raw HTML/script fragment); RastiSi
    builds the trusted <a>/<img> markup itself from the fixed
    trustseal.enamad.ir origin."""

    def test_accepts_valid_id_and_code(self):
        identifiers = parse_enamad_badge_identifiers("221617", "94MqMPJEnuahlSHjb9kP")
        self.assertEqual(identifiers.enamad_id, "221617")
        self.assertEqual(identifiers.auth_code, "94MqMPJEnuahlSHjb9kP")
        self.assertEqual(
            identifiers.profile_url,
            "https://trustseal.enamad.ir/?id=221617&Code=94MqMPJEnuahlSHjb9kP",
        )
        self.assertEqual(
            identifiers.logo_url,
            "https://trustseal.enamad.ir/logo.aspx?id=221617&Code=94MqMPJEnuahlSHjb9kP",
        )

    def test_both_blank_is_not_configured_not_an_error(self):
        self.assertIsNone(parse_enamad_badge_identifiers("", ""))

    def test_only_id_present_is_rejected(self):
        with self.assertRaises(EnamadBadgeError):
            parse_enamad_badge_identifiers("221617", "")

    def test_only_code_present_is_rejected(self):
        with self.assertRaises(EnamadBadgeError):
            parse_enamad_badge_identifiers("", "94MqMPJEnuahlSHjb9kP")

    def test_non_numeric_id_rejected(self):
        with self.assertRaises(EnamadBadgeError):
            parse_enamad_badge_identifiers("<script>", "94MqMPJEnuahlSHjb9kP")

    def test_id_with_html_injection_rejected(self):
        with self.assertRaises(EnamadBadgeError):
            parse_enamad_badge_identifiers('221617"><script>alert(1)</script>', "code")

    def test_code_with_disallowed_characters_rejected(self):
        with self.assertRaises(EnamadBadgeError):
            parse_enamad_badge_identifiers("221617", "code with spaces & <tags>")

    def test_overlong_code_rejected(self):
        with self.assertRaises(EnamadBadgeError):
            parse_enamad_badge_identifiers("221617", "a" * 65)


@override_settings(ALLOWED_HOSTS=["merchant-badge.example", "testserver"])
class MerchantEnamadBadgeRenderingTests(TestCase):
    def setUp(self):
        self.store = Store.objects.create(
            name="Badge Merchant",
            slug="badge-merchant",
            admin_subdomain="badge-merchant",
            status=Store.Status.ACTIVE,
            onboarding_completed_at=timezone.now(),
        )
        ShopSettings.provision_for(self.store)
        StoreDomain.objects.create(
            store=self.store,
            hostname="merchant-badge.example",
            is_primary=True,
            domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
            verification_status=StoreDomain.VerificationStatus.VERIFIED,
            verified_at=timezone.now(),
        )

    def _request(self, host, path="/"):
        request = RequestFactory().get(path, HTTP_HOST=host)
        request.store = self.store
        return request

    def test_badge_renders_on_verified_custom_domain(self):
        integration_service.connect(
            store=self.store, provider_code="enamad",
            values={"enamad_id": "221617", "enamad_auth_code": "94MqMPJEnuahlSHjb9kP"}, actor=None,
        )
        context = shop_settings(self._request("merchant-badge.example"))
        self.assertEqual(
            context["SHOP_ENAMAD_BADGE_PROFILE_URL"],
            "https://trustseal.enamad.ir/?id=221617&Code=94MqMPJEnuahlSHjb9kP",
        )
        self.assertEqual(
            context["SHOP_ENAMAD_BADGE_LOGO_URL"],
            "https://trustseal.enamad.ir/logo.aspx?id=221617&Code=94MqMPJEnuahlSHjb9kP",
        )

    def test_badge_renders_sitewide_not_only_home(self):
        """Unlike the technical-verification meta, the final badge is a
        normal trust-badge display and is not restricted to the home page."""
        integration_service.connect(
            store=self.store, provider_code="enamad",
            values={"enamad_id": "221617", "enamad_auth_code": "94MqMPJEnuahlSHjb9kP"}, actor=None,
        )
        context = shop_settings(self._request("merchant-badge.example", "/products/"))
        self.assertTrue(context["SHOP_ENAMAD_BADGE_PROFILE_URL"])

    def test_badge_and_meta_are_independent_states(self):
        """A Store may configure only the badge (already issued) without
        ever having stored a technical-verification meta tag."""
        integration_service.connect(
            store=self.store, provider_code="enamad",
            values={"enamad_id": "221617", "enamad_auth_code": "94MqMPJEnuahlSHjb9kP"}, actor=None,
        )
        context = shop_settings(self._request("merchant-badge.example"))
        self.assertTrue(context["SHOP_ENAMAD_BADGE_PROFILE_URL"])
        self.assertEqual(context["SHOP_ENAMAD_VERIFICATION_META_NAME"], "")

    def test_meta_only_does_not_imply_badge(self):
        integration_service.connect(
            store=self.store, provider_code="enamad",
            values={"verification_meta_tag": '<meta name="x" content="y">'}, actor=None,
        )
        context = shop_settings(self._request("merchant-badge.example"))
        self.assertTrue(context["SHOP_ENAMAD_VERIFICATION_META_NAME"])
        self.assertEqual(context["SHOP_ENAMAD_BADGE_PROFILE_URL"], "")

    def test_no_badge_on_unverified_custom_domain(self):
        integration_service.connect(
            store=self.store, provider_code="enamad",
            values={"enamad_id": "221617", "enamad_auth_code": "94MqMPJEnuahlSHjb9kP"}, actor=None,
        )
        StoreDomain.objects.filter(hostname="merchant-badge.example").update(
            verification_status=StoreDomain.VerificationStatus.UNVERIFIED, verified_at=None,
        )
        context = shop_settings(self._request("merchant-badge.example"))
        self.assertEqual(context["SHOP_ENAMAD_BADGE_PROFILE_URL"], "")

    def test_no_badge_on_platform_owned_subdomain(self):
        integration_service.connect(
            store=self.store, provider_code="enamad",
            values={"enamad_id": "221617", "enamad_auth_code": "94MqMPJEnuahlSHjb9kP"}, actor=None,
        )
        with override_settings(ALLOWED_HOSTS=["badge-merchant.rastisi.localhost", "testserver"]):
            context = shop_settings(self._request("badge-merchant.rastisi.localhost"))
        self.assertEqual(context["SHOP_ENAMAD_BADGE_PROFILE_URL"], "")

    def test_corrupt_legacy_badge_value_fails_closed(self):
        connection = integration_service.connect(
            store=self.store, provider_code="enamad",
            values={"enamad_id": "221617", "enamad_auth_code": "94MqMPJEnuahlSHjb9kP"}, actor=None,
        )
        # Simulate a legacy/corrupted stored value (e.g. only one of the two
        # identifiers survives some future migration) bypassing validation.
        connection.set_credentials({"enamad_id": "221617", "enamad_auth_code": ""})
        connection.save()
        context = shop_settings(self._request("merchant-badge.example"))
        self.assertEqual(context["SHOP_ENAMAD_BADGE_PROFILE_URL"], "")

    def test_other_stores_badge_never_leaks_to_this_store(self):
        integration_service.connect(
            store=self.store, provider_code="enamad",
            values={"enamad_id": "999999", "enamad_auth_code": "otherStoresSecretCode"}, actor=None,
        )
        other_store = Store.objects.create(
            name="Other Badge Merchant", slug="other-badge-merchant",
            admin_subdomain="other-badge-merchant", status=Store.Status.ACTIVE,
            onboarding_completed_at=timezone.now(),
        )
        ShopSettings.provision_for(other_store)
        StoreDomain.objects.create(
            store=other_store, hostname="other-badge-merchant.example", is_primary=True,
            domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        request = RequestFactory().get("/", HTTP_HOST="other-badge-merchant.example")
        request.store = other_store
        with override_settings(ALLOWED_HOSTS=["other-badge-merchant.example", "testserver"]):
            context = shop_settings(request)
        self.assertEqual(context["SHOP_ENAMAD_BADGE_PROFILE_URL"], "")
        self.assertNotIn("otherStoresSecretCode", str(context))


@override_settings(ALLOWED_HOSTS=["toggle-badge.example", "testserver"])
class EnamadBadgeDisplayToggleTests(TestCase):
    """The seller can hide the footer seal without losing the saved ids; the state is reported separately from «saved»; another store's seal never shows."""

    def setUp(self):
        self.store = Store.objects.create(name="Toggle Merchant", slug="toggle-merchant", admin_subdomain="toggle-merchant", status=Store.Status.ACTIVE,
                                          onboarding_completed_at=timezone.now())
        ShopSettings.provision_for(self.store)
        StoreDomain.objects.create(store=self.store, hostname="toggle-badge.example", is_primary=True, domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
                                   verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now())
        self.values = {"enamad_id": "221617", "enamad_auth_code": "94MqMPJEnuahlSHjb9kP"}

    def _ctx(self):
        request = RequestFactory().get("/", HTTP_HOST="toggle-badge.example")
        request.store = self.store
        return shop_settings(request)

    def test_default_is_shown_and_switching_off_hides_it_while_the_ids_stay_saved(self):
        integration_service.connect(store=self.store, provider_code="enamad", values={**self.values, "enamad_show_badge": "1"}, actor=None)
        self.assertTrue(self._ctx()["SHOP_ENAMAD_BADGE_PROFILE_URL"])
        integration_service.connect(store=self.store, provider_code="enamad", values={**self.values, "enamad_show_badge": "0"}, actor=None)
        context = self._ctx()
        self.assertFalse(context.get("SHOP_ENAMAD_BADGE_PROFILE_URL"))
        saved = integration_service.connections_context(store=self.store)
        row = next(r for r in saved if r["provider"].code == "enamad")
        self.assertEqual(row["credentials"]["enamad_id"], "221617")
        flow = enamad_verification_service.enamad_flow(self.store, row["credentials"], connected=True)
        self.assertEqual(flow["stages"][1]["state"], "hidden")

    def test_a_connection_that_only_has_the_display_switch_counts_as_nothing_saved(self):
        conn = integration_service.get_or_create_connection(store=self.store, provider_code="enamad")
        conn.set_credentials({"enamad_show_badge": "0"})
        conn.save()
        row = next(r for r in integration_service.connections_context(store=self.store) if r["provider"].code == "enamad")
        self.assertFalse(row["has_saved_credentials"])

    def test_another_stores_seal_never_shows_on_this_stores_domain(self):
        other = Store.objects.create(name="Other Seal", slug="other-seal", admin_subdomain="other-seal", status=Store.Status.ACTIVE)
        integration_service.connect(store=other, provider_code="enamad", values={"enamad_id": "999999", "enamad_auth_code": "OTHERCODE123456789", "enamad_show_badge": "1"}, actor=None)
        self.assertFalse(self._ctx().get("SHOP_ENAMAD_BADGE_PROFILE_URL"))
