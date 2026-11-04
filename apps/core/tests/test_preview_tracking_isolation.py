"""Analytics contamination from previews: a preview of a PUBLISHED store (draft preview, Ready Template live preview, builder preview) is rendered on the ADMIN host through the
public shell. The server never prints tag code, but it DOES print the consent config (store ids) and consent.js — which lets the visitor-consent flow load GA4/GTM/Meta for what is
only the owner previewing. Preview routes must print neither; real storefront pages (published, custom domain) and tenant isolation must be unchanged."""

from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import ShopSettings
from apps.stores.models import Store, StoreDomain, StoreIntegrationConnection, StoreMembership

User = get_user_model()
SUFFIX = "panel.brand-example.ir"
ADMIN_HOST = f"ptk.{SUFFIX}"
PUBLIC_HOST = "shop.brand-example.ir"
OTHER_HOST = "other-shop.brand-example.ir"
IDS_A = {"google_analytics": ("measurement_id", "G-AAAA1111"), "google_tag_manager": ("container_id", "GTM-AAA111"), "ad_pixel": ("pixel_id", "1111111111111111")}
IDS_B = {"google_analytics": ("measurement_id", "G-BBBB2222"), "google_tag_manager": ("container_id", "GTM-BBB222"), "ad_pixel": ("pixel_id", "2222222222222222")}
PREVIEWS = (
    ("dashboard:storefront-builder-draft-preview", {}, {}),
    ("dashboard:storefront-builder-preview", {}, {}),
    ("dashboard:storefront-builder-template-live-preview", {"key": "almas_luxury"}, {"data": "merchant"}),
)


def _connect(store, ids):
    for code, (field, value) in ids.items():
        conn = StoreIntegrationConnection.objects.create(store=store, provider_code=code, is_active=True)
        conn.set_credentials({field: value})
        conn.save()


@override_settings(ALLOWED_HOSTS=[ADMIN_HOST, PUBLIC_HOST, OTHER_HOST, "testserver"], RASTISI_ADMIN_DOMAIN_SUFFIX=SUFFIX, RASTISI_STOREFRONT_TRACKING_ENABLED=True,
                   RASTISI_TEMPLATE_GALLERY_RESTRICTED=False)
class PreviewTrackingIsolationTests(TestCase):
    def setUp(self):
        cache.clear()
        patcher = mock.patch("apps.stores.services.publication_service.is_publicly_visible", return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.store = Store.objects.get(slug="akhlaghi")
        self.store.admin_subdomain = "ptk"
        self.store.save(update_fields=["admin_subdomain"])
        StoreDomain.objects.create(store=self.store, hostname=PUBLIC_HOST, is_primary=True, domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
                                   verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now())
        _connect(self.store, IDS_A)
        self.other = Store.objects.create(name="Other", slug="pt-other", status=Store.Status.ACTIVE, admin_subdomain="pto")
        ShopSettings.provision_for(self.other)
        StoreDomain.objects.create(store=self.other, hostname=OTHER_HOST, is_primary=True, domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
                                   verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now())
        _connect(self.other, IDS_B)
        self.owner = User.objects.create_user(username="pt-owner", password="x12345678", is_staff=True)
        StoreMembership.objects.create(store=self.store, user=self.owner, role=StoreMembership.Role.OWNER, status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
        from apps.storefront_builder.services import layout_service

        layout_service.get_or_create_layout(self.store)
        layout_service.get_or_create_draft(self.store, user=self.owner)
        self.admin = Client(HTTP_HOST=ADMIN_HOST)
        self.admin.force_login(self.owner)

    def page(self, name, kwargs, client=None, **params):
        return (client or self.admin).get(reverse(name, kwargs=kwargs), params)

    def printed(self, html):
        return {"config": 'id="rs-consent-config"' in html, "script": "core/consent.js" in html,
                "ids": [v for _f, v in IDS_A.values() if v in html]}

    # ---- the leak (reproduction) and its fix ----------------------------------------------------------------------------------------
    def test_no_preview_route_prints_the_consent_config_ids_or_consent_script(self):
        for name, kwargs, params in PREVIEWS:
            response = self.page(name, kwargs, **params)
            self.assertEqual(response.status_code, 200, name)
            self.assertEqual(self.printed(response.content.decode()), {"config": False, "script": False, "ids": []}, name)

    def test_the_draft_preview_with_a_page_selector_and_the_merchant_data_template_preview_are_also_clean(self):
        for response in (self.page("dashboard:storefront-builder-draft-preview", {}, page="product_detail"),
                         self.page("dashboard:storefront-builder-template-live-preview", {"key": "almas_luxury"}, data="merchant")):
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.printed(response.content.decode()), {"config": False, "script": False, "ids": []})

    # ---- ordinary tracking is preserved ---------------------------------------------------------------------------------------------
    def test_the_published_custom_domain_storefront_still_prints_the_config_for_its_own_store(self):
        html = Client(HTTP_HOST=PUBLIC_HOST).get("/").content.decode()
        got = self.printed(html)
        self.assertTrue(got["config"] and got["script"])
        self.assertEqual(sorted(got["ids"]), sorted(v for _f, v in IDS_A.values()))
        self.assertNotIn(IDS_B["google_analytics"][1], html)                                       # tenant isolation: never another store's ids

    def test_another_stores_storefront_carries_only_its_own_ids(self):
        html = Client(HTTP_HOST=OTHER_HOST).get("/").content.decode()
        self.assertIn(IDS_B["google_analytics"][1], html)
        for _f, value in IDS_A.values():
            self.assertNotIn(value, html)

    @override_settings(RASTISI_STOREFRONT_TRACKING_ENABLED=False)
    def test_the_platform_flag_off_keeps_everything_off_everywhere(self):
        for host in (PUBLIC_HOST, OTHER_HOST):
            self.assertFalse(self.printed(Client(HTTP_HOST=host).get("/").content.decode())["config"])
        for name, kwargs, params in PREVIEWS:
            self.assertFalse(self.printed(self.page(name, kwargs, **params).content.decode())["config"])

    def test_admin_pages_never_carry_storefront_tracking(self):
        html = self.admin.get(reverse("dashboard:dashboard")).content.decode()
        self.assertFalse(self.printed(html)["config"])

    def test_anonymous_visitors_cannot_use_preview_routes_at_all(self):
        for name, kwargs, params in PREVIEWS:
            self.assertNotEqual(Client(HTTP_HOST=ADMIN_HOST).get(reverse(name, kwargs=kwargs), params).status_code, 200, name)
