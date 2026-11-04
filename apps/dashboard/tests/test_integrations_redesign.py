"""Integrations page redesign (horizontal categories + per-service cards + management drawer).

Covers: every tab renders and switches without touching data; the four SEPARATE answers per service (QA-05); proportionate GA4/GTM guidance (QA-06);
backend-only ID validation / saving / disabling; permission + CSRF + tenant isolation; Torob readiness semantics; eNamad choice-vs-real-display.
Nothing here contacts an external service (a socket guard enforces it) and nothing turns tracking on globally.
"""

import socket
from decimal import Decimal
from unittest import mock

from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, Product, ProductImage, Vendor
from apps.dashboard.services import channel_readiness_service as readiness
from apps.dashboard.services import search_visibility_service as svs
from apps.dashboard.tests.integration_pages import VIEWS, all_views_html, view_html, view_url
from apps.dashboard.tests.test_permission_enforcement import PermissionEnforcementTestCase, _user_with_role
from apps.stores.models import Store, StoreDomain, StoreIntegrationConnection, StoreMembership
from apps.stores.services import integration_service


class _Base(PermissionEnforcementTestCase):
    def setUp(self):
        super().setUp()
        guard = mock.patch.object(socket.socket, "connect", side_effect=AssertionError("an external connection was attempted"))
        guard.start()
        self.addCleanup(guard.stop)
        self._login(self.owner)

    def post(self, name, code, **data):
        return self.client.post(reverse(f"dashboard:settings-integration-{name}", args=[code]), data)

    def saved(self, code, store=None):
        conn = StoreIntegrationConnection.objects.filter(store=store or self.store, provider_code=code).first()
        return conn.get_credentials() if conn else {}

    def row(self, code, store=None):
        return next(r for r in integration_service.connections_context(store=store or self.store) if r["provider"].code == code)

    def card(self, html, code):
        return html.split(f'data-testid="integration-{code}"')[1].split("</article>")[0]


class TabsTests(_Base):
    def test_every_tab_renders_with_its_own_selected_state(self):
        for view in VIEWS:
            response = self.client.get(view_url(view))
            self.assertEqual(response.status_code, 200, view)
            html = response.content.decode()
            self.assertIn(f'data-subtab="integrations-{view}"', html)
            self.assertRegex(html, rf'class="admin-subtab active" data-subtab="integrations-{view}" href="[^"]*" aria-current="page"')
            self.assertEqual(html.count('aria-current="page" '), html.count('aria-current="page" '))
            self.assertIn(f'data-view="{view}"', html)

    def test_the_old_right_side_category_menu_is_gone_and_the_main_sidebar_is_untouched(self):
        html = self.client.get(view_url("analytics")).content.decode()
        self.assertNotIn("int-section-", html)                        # the A–E accordion groups
        self.assertNotIn("au-acc__trigger", html)
        self.assertIn('class="admin-subtabs"', html)                   # one horizontal bar, rendered once by the shared layout
        self.assertEqual(html.count('class="admin-subtabs"'), 1)

    def test_switching_tabs_never_changes_saved_data(self):
        self.post("connect", "google_analytics", measurement_id="G-ABC1234DEF")
        before = self.saved("google_analytics")
        all_views_html(self.client)
        self.assertEqual(self.saved("google_analytics"), before)
        self.assertIn("G-ABC1234DEF", view_html(self.client, "analytics"))
        self.assertNotIn("G-ABC1234DEF", view_html(self.client, "torob"))          # other categories do not carry it

    def test_a_save_returns_to_the_tab_that_holds_the_service(self):
        for code, field, value, view in (("google_analytics", "measurement_id", "G-ABC1234DEF", "analytics"), ("torob", "merchant_id", "SHOP-77", "torob"),
                                         ("ad_pixel", "pixel_id", "1234567890123456", "analytics")):
            response = self.post("connect", code, **{field: value})
            self.assertEqual(response["Location"], f"/admin-portal/settings/?section=integrations&view={view}")


class FourAnswersTests(_Base):
    """QA-05: saved / use enabled / ready / live are four different facts — and the page never mixes them."""

    def axes(self, code, view="analytics"):
        card = self.card(view_html(self.client, view), code)
        return {key: card.split(f'data-testid="int-axis-{key}" data-on="')[1][0] == "1" for key in ("saved", "enabled", "ready", "live")}, card

    def test_nothing_saved(self):
        axes, _ = self.axes("google_analytics")
        self.assertEqual(axes, {"saved": False, "enabled": False, "ready": False, "live": False})

    def test_saved_and_enabled_but_platform_tracking_is_off_is_not_live_and_says_why(self):
        self.post("connect", "google_analytics", measurement_id="G-ABC1234DEF")
        axes, card = self.axes("google_analytics")
        self.assertEqual(axes, {"saved": True, "enabled": True, "ready": True, "live": False})
        self.assertIn("منتظر فعال‌سازی ردیابی توسط مدیر پلتفرم", card)
        self.assertNotIn("ردیابی فعال است", card)
        self.assertNotIn("روشن است؟ بله", view_html(self.client, "analytics"))        # the contradictory old phrase

    def test_platform_on_but_a_local_address_waits_for_the_public_address(self):
        self.post("connect", "google_tag_manager", container_id="GTM-ABC1234")
        with override_settings(RASTISI_STOREFRONT_TRACKING_ENABLED=True), mock.patch.object(svs, "store_live", return_value=False):
            axes, card = self.axes("google_tag_manager")
        self.assertFalse(axes["live"])
        self.assertIn("آدرس عمومی", card)

    def test_live_only_when_platform_public_address_and_enabled_all_hold_and_consent_is_still_the_visitors(self):
        self.post("connect", "ad_pixel", pixel_id="1234567890123456")
        with override_settings(RASTISI_STOREFRONT_TRACKING_ENABLED=True), mock.patch.object(svs, "store_live", return_value=True):
            axes, card = self.axes("ad_pixel")
        self.assertEqual(axes, {"saved": True, "enabled": True, "ready": True, "live": True})
        self.assertIn("پس از موافقت بازدیدکننده", card)

    def test_saved_but_switched_off_keeps_the_id_and_is_neither_ready_nor_live(self):
        self.post("connect", "google_analytics", measurement_id="G-ABC1234DEF")
        self.post("disconnect", "google_analytics")
        axes, card = self.axes("google_analytics")
        self.assertEqual(axes, {"saved": True, "enabled": False, "ready": False, "live": False})
        self.assertIn("خاموش", card)
        self.assertEqual(self.saved("google_analytics")["measurement_id"], "G-ABC1234DEF")

    def test_torob_is_never_operational_and_never_live(self):
        self.post("connect", "torob", merchant_id="SHOP-77")
        axes, card = self.axes("torob", "torob")
        self.assertEqual(axes, {"saved": True, "enabled": True, "ready": False, "live": False})
        self.assertIn("فید یا API", card)

    def test_the_success_message_says_only_that_the_id_was_saved(self):
        response = self.client.post(reverse("dashboard:settings-integration-connect", args=["google_analytics"]), {"measurement_id": "G-ABC1234DEF"}, follow=True)
        text = " ".join(str(m) for m in response.context["messages"])
        self.assertIn("ذخیره شد", text)
        self.assertIn("به‌معنی فعال‌شدن ردیابی", text)
        for word in ("تأیید شد", "وصل شد", "متصل شد", "verified", "با موفقیت متصل"):
            self.assertNotIn(word, text)


class GuidanceTests(_Base):
    """QA-06: the supported GA4 + GTM combination gets proportionate guidance, never an alarm; behaviour (GTM wins) is unchanged."""

    def rows(self):
        return integration_service.connections_context(store=self.store)

    def test_guidance_per_combination(self):
        self.assertIsNone(svs.tracking_guidance(self.rows()))
        self.post("connect", "google_analytics", measurement_id="G-ABC1234DEF")
        self.assertEqual(svs.tracking_guidance(self.rows())["state"], "ga4")
        self.post("connect", "google_tag_manager", container_id="GTM-ABC1234")
        both = svs.tracking_guidance(self.rows())
        self.assertEqual(both["state"], "both")
        joined = " ".join(both["points"])
        self.assertIn("خطا نیست", joined)
        self.assertIn("داخل کانتینر GTM", joined)
        self.assertIn("نمی‌تواند", joined)                                  # it cannot inspect the container
        self.post("disconnect", "google_analytics")
        self.assertEqual(svs.tracking_guidance(self.rows())["state"], "gtm")

    def test_the_old_red_alarm_is_gone_from_the_page(self):
        self.post("connect", "google_analytics", measurement_id="G-ABC1234DEF")
        self.post("connect", "google_tag_manager", container_id="GTM-ABC1234")
        html = view_html(self.client, "analytics")
        self.assertNotIn("au-note--danger", html.split('data-testid="tracking-guidance"')[1].split("</aside>")[0])
        self.assertNotIn('data-testid="duplicate-tracking-warning"', html)

    def test_gtm_still_wins_over_direct_ga4_and_consent_is_still_required(self):
        """The behaviour the guidance describes is the engine's own (pinned in apps.core.tests.test_consent_engine): GTM only, GA4 not direct, opt-in."""
        from apps.core import consent

        cfg = consent.build_config({"ga4": "G-ABC1234DEF", "gtm": "GTM-ABC1234"})
        self.assertEqual([item["tracker"] for item in cfg["load"]], ["gtm"])
        self.assertTrue(cfg["ga4_via_gtm"])
        self.assertEqual(cfg["policy"], "opt_in")
        only_ga4 = consent.build_config({"ga4": "G-ABC1234DEF"})
        self.assertEqual([item["tracker"] for item in only_ga4["load"]], ["ga4"])
        self.assertFalse(only_ga4["ga4_via_gtm"])
        self.assertEqual(set(cfg["signals"]["default_denied"]) >= {"ad_storage", "analytics_storage"}, True)     # denied until the visitor decides


class ValidationAndSecurityTests(_Base):
    BAD = {
        "google_analytics": ("measurement_id", ["UA-1234", "G-<script>", "g-abc1234def", "G-ABC1234DEF<img src=x>", "G-" + "A" * 700, "javascript:alert(1)"]),
        "google_tag_manager": ("container_id", ["GTM-<script>alert(1)</script>", "gtm-abc1234", "GTM-" + "A" * 700, "GTM-AB CD12"]),
        "ad_pixel": ("pixel_id", ["12ab", "<script>", "1" * 700, "123456789"]),
        "torob": ("merchant_id", ["<script>alert(1)</script>", 'a" onmouseover="x', "x" * 700, "جعلی", "a b"]),
    }

    def test_backend_rejects_bad_values_whatever_the_browser_did_and_keeps_the_previous_valid_value(self):
        good = {"google_analytics": "G-ABC1234DEF", "google_tag_manager": "GTM-ABC1234", "ad_pixel": "1234567890123456", "torob": "SHOP-77"}
        for code, (field, bad_values) in self.BAD.items():
            self.post("connect", code, **{field: good[code]})
            for bad in bad_values:
                response = self.post("connect", code, **{field: bad})
                self.assertEqual(response.status_code, 302, (code, bad))
                self.assertEqual(self.saved(code)[field], good[code], (code, bad))          # the last VALID value survives a rejected attempt

    def test_a_rejected_value_shows_a_field_error_and_the_typed_text_but_stores_nothing(self):
        self.post("connect", "google_analytics", measurement_id="G-ABC1234DEF")
        self.post("connect", "google_analytics", measurement_id="oops")
        html = view_html(self.client, "analytics")
        drawer = html.split('data-testid="drawer-google_analytics"')[1].split("</dialog>")[0]
        self.assertIn('data-autoopen="1"', html)
        self.assertIn('aria-invalid="true"', drawer)
        self.assertIn('value="oops"', drawer)                                           # what the seller typed, so they can fix it
        self.assertEqual(self.saved("google_analytics")["measurement_id"], "G-ABC1234DEF")
        again = view_html(self.client, "analytics").split('data-testid="drawer-google_analytics"')[1].split("</dialog>")[0]
        self.assertNotIn('aria-invalid="true"', again)                                  # one-shot: a refresh shows the real stored value
        self.assertIn('value="G-ABC1234DEF"', again)

    def test_values_are_escaped_and_no_markup_or_script_is_ever_stored_or_rendered(self):
        self.post("connect", "torob", merchant_id="<script>alert(1)</script>")
        html = all_views_html(self.client)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertEqual(self.saved("torob"), {})

    def test_enamad_rejects_script_and_overlong_values_on_the_server(self):
        for field, bad in (("verification_meta_tag", "<script>alert(1)</script>"), ("verification_meta_tag", '<meta name="x" content="' + "a" * 900 + '">'),
                           ("enamad_id", "12<script>"), ("enamad_auth_code", "../../x")):
            values = {"verification_meta_tag": "", "enamad_id": "", "enamad_auth_code": ""}
            values[field] = bad
            if field in ("enamad_id", "enamad_auth_code"):
                values["enamad_id" if field == "enamad_auth_code" else "enamad_auth_code"] = "94MqMPJEnuahlSHjb9kP" if field == "enamad_id" else "221617"
            self.post("connect", "enamad", **values)
            self.assertFalse(StoreIntegrationConnection.objects.filter(store=self.store, provider_code="enamad").exists(), (field, bad))

    def test_disable_keeps_the_id_and_reenable_restores_it(self):
        self.post("connect", "ad_pixel", pixel_id="1234567890123456")
        self.post("disconnect", "ad_pixel")
        row = self.row("ad_pixel")
        self.assertFalse(row["is_connected"])
        self.assertEqual(row["credentials"]["pixel_id"], "1234567890123456")
        self.post("toggle", "ad_pixel")
        self.assertTrue(self.row("ad_pixel")["is_connected"])

    def test_refresh_and_resubmit_are_consistent(self):
        for _ in range(2):
            self.post("connect", "torob", merchant_id="SHOP-77")
        self.assertEqual(StoreIntegrationConnection.objects.filter(store=self.store, provider_code="torob").count(), 1)
        self.assertIn('value="SHOP-77"', view_html(self.client, "torob"))

    def test_csrf_is_enforced_on_every_mutating_endpoint(self):
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.owner)
        for name in ("connect", "test", "toggle", "disconnect"):
            response = strict.post(reverse(f"dashboard:settings-integration-{name}", args=["torob"]), {"merchant_id": "SHOP-77"})
            self.assertEqual(response.status_code, 403, name)
        self.assertFalse(StoreIntegrationConnection.objects.filter(store=self.store, provider_code="torob").exists())

    def test_only_a_settings_manager_may_save_disable_or_even_view(self):
        self.post("connect", "torob", merchant_id="SHOP-77")
        for user in (self.catalog_manager, self.order_manager, self.content_editor, self.analyst):
            self._login(user)
            self.assertEqual(self.client.get(view_url("analytics")).status_code, 403, user.username)
            for name in ("connect", "disconnect", "toggle", "test"):
                self.assertEqual(self.post(name, "torob", merchant_id="HACK-1").status_code, 403, (user.username, name))
        self.assertEqual(self.saved("torob")["merchant_id"], "SHOP-77")
        self.assertTrue(self.row("torob")["is_connected"])

    def test_anonymous_users_are_sent_to_login_and_change_nothing(self):
        anon = Client()
        for name in ("connect", "disconnect", "toggle", "test"):
            self.assertEqual(anon.post(reverse(f"dashboard:settings-integration-{name}", args=["torob"]), {"merchant_id": "X1"}).status_code, 302)
        self.assertFalse(StoreIntegrationConnection.objects.filter(provider_code="torob", store=self.store).exists())

    def test_get_is_not_accepted_for_mutations_and_an_unknown_provider_is_404(self):
        self.assertEqual(self.client.get(reverse("dashboard:settings-integration-connect", args=["torob"])).status_code, 405)
        self.assertEqual(self.post("connect", "no-such-service", x="1").status_code, 404)

    def _admin_host(self, store, label):
        from django.conf import settings

        host = f"{label}.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"
        StoreDomain.objects.create(store=store, hostname=host, is_primary=True, domain_type=StoreDomain.DomainType.PLATFORM_SUBDOMAIN,
                                   verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now())
        store.admin_subdomain = label
        store.save(update_fields=["admin_subdomain"])
        return host

    def test_tenant_isolation_another_stores_member_cannot_read_or_change_this_stores_integrations(self):
        other = Store.objects.create(name="Other", slug="redesign-other", status=Store.Status.ACTIVE)
        outsider = _user_with_role(other, "redesign-outsider", StoreMembership.Role.OWNER)
        from apps.core.models import ShopSettings

        ShopSettings.provision_for(other)
        host_a, host_b = self._admin_host(self.store, "rd-a"), self._admin_host(other, "rd-b")
        with override_settings(ALLOWED_HOSTS=[host_a, host_b, "testserver"]):
            owner_a = Client(HTTP_HOST=host_a)
            owner_a.force_login(self.owner)
            owner_a.post(reverse("dashboard:settings-integration-connect", args=["torob"]), {"merchant_id": "SHOP-77"})
            self.assertEqual(self.saved("torob")["merchant_id"], "SHOP-77")
            # the outsider (owner of ANOTHER store) on THIS store's host: no read, no write
            evil = Client(HTTP_HOST=host_a)
            evil.force_login(outsider)
            self.assertIn(evil.get(view_url("torob")).status_code, (302, 403, 404))
            for name in ("connect", "disconnect", "toggle", "test"):
                self.assertIn(evil.post(reverse(f"dashboard:settings-integration-{name}", args=["torob"]), {"merchant_id": "EVIL-1"}).status_code, (302, 403, 404), name)
            self.assertEqual(self.saved("torob")["merchant_id"], "SHOP-77")
            self.assertTrue(self.row("torob")["is_connected"])
            self.assertFalse(StoreIntegrationConnection.objects.filter(store=other).exists())
            # this store's owner on the OTHER store's host: also nothing
            cross = Client(HTTP_HOST=host_b)
            cross.force_login(self.owner)
            cross.post(reverse("dashboard:settings-integration-connect", args=["torob"]), {"merchant_id": "CROSS-1"})
            self.assertFalse(StoreIntegrationConnection.objects.filter(store=other).exists())
            self.assertEqual(self.saved("torob")["merchant_id"], "SHOP-77")
            # the outsider's own store is independent and sees only its own value
            mine = Client(HTTP_HOST=host_b)
            mine.force_login(outsider)
            mine.post(reverse("dashboard:settings-integration-connect", args=["torob"]), {"merchant_id": "OTHER-9"})
            self.assertEqual(self.saved("torob", other)["merchant_id"], "OTHER-9")
            self.assertEqual(self.saved("torob")["merchant_id"], "SHOP-77")
            page = mine.get(view_url("torob")).content.decode()
            self.assertIn("OTHER-9", page)
            self.assertNotIn("SHOP-77", page)

    def test_the_audit_log_does_not_contain_the_identifier_values(self):
        from apps.core.models import AuditLogEntry

        self.post("connect", "google_analytics", measurement_id="G-ABC1234DEF")
        dump = " ".join(f"{e.metadata} {e.object_label}" for e in AuditLogEntry.objects.filter(store=self.store))
        self.assertNotIn("G-ABC1234DEF", dump)


class TorobReadinessTests(_Base):
    def mk(self, slug, *, price="100000", stock=5, image=True, name=None, status=Product.Status.ACTIVE, store=None):
        store = store or self.store
        vendor, _ = Vendor.objects.get_or_create(store=store, slug="rr-v", defaults={"name": "V"})
        category, _ = Category.objects.get_or_create(store=store, slug="rr-c", defaults={"name": "C"})
        product = Product.objects.create(store=store, vendor=vendor, category=category, name=name or slug, slug=slug, price=Decimal(price), stock=stock,
                                         status=status, sku=f"SKU-{slug}")
        if image:
            ProductImage.objects.create(product=product, image="p/x.png", is_cover=True)
        return product

    def test_ready_means_title_price_and_image_and_stock_is_separate(self):
        base = readiness.readiness(self.store)
        self.mk("rr-ok")
        self.mk("rr-oos", stock=0)                          # out of stock but complete → still READY
        self.mk("rr-noimg", image=False)                    # blocking
        self.mk("rr-noimg-oos", image=False, stock=0)       # BOTH no image and out of stock → overlap, not ready
        r = readiness.readiness(self.store)
        self.assertEqual(r["total"] - base["total"], 4)
        self.assertEqual(r["ready"] - base["ready"], 2)
        self.assertEqual(r["not_ready"] - base["not_ready"], 2)
        counts = {row["key"]: row["count"] for row in r["rows"]}
        base_counts = {row["key"]: row["count"] for row in base["rows"]}
        self.assertEqual(counts["no_image"] - base_counts.get("no_image", 0), 2)
        self.assertEqual(counts["out_of_stock"] - base_counts.get("out_of_stock", 0), 2)       # the two groups OVERLAP by one product
        self.assertEqual(r["ready_out_of_stock"] - base["ready_out_of_stock"], 1)
        self.assertEqual(r["ready_in_stock"] + r["ready_out_of_stock"], r["ready"])               # the split adds up

    def test_a_product_without_a_price_is_never_also_out_of_stock(self):
        self.mk("rr-noprice", price="0", stock=0)
        keys = {row["key"] for row in readiness.readiness(self.store)["rows"]}
        self.assertIn("no_price", keys)
        for sample in (row for row in readiness.readiness(self.store)["rows"] if row["key"] == "out_of_stock"):
            self.assertNotIn("rr-noprice", sample["samples"])

    def test_inactive_and_other_store_products_are_not_counted(self):
        base = readiness.readiness(self.store)["total"]
        self.mk("rr-draft", status=Product.Status.DRAFT)
        other = Store.objects.create(name="O2", slug="rr-other", status=Store.Status.ACTIVE)
        self.mk("rr-foreign", store=other)
        self.assertEqual(readiness.readiness(self.store)["total"], base)

    def test_the_page_explains_the_overlap_and_that_saving_an_id_is_not_a_connection(self):
        self.mk("rr-ok")
        self.mk("rr-oos", stock=0)
        html = view_html(self.client, "torob")
        for marker in ("torob-stat-total", "torob-stat-ready", "torob-stat-not-ready", "torob-stat-oos", "torob-overlap-note"):
            self.assertIn(f'data-testid="{marker}"', html)
        self.assertIn("جمع ردیف‌ها با «کالای بررسی‌شده» برابر نیست", html)
        self.assertIn("اتصال عملیاتی نیست", html)
        self.assertNotIn("feed.xml", html)

    def test_query_count_does_not_grow_with_the_catalogue(self):
        for i in range(3):
            self.mk(f"rr-q{i}")
        with self.assertNumQueries(readiness_queries := self._count()):
            readiness.readiness(self.store)
        for i in range(3, 9):
            self.mk(f"rr-q{i}")
        with self.assertNumQueries(readiness_queries):
            readiness.readiness(self.store)

    def _count(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as ctx:
            readiness.readiness(self.store)
        return len(ctx)


class EnamadDisplayTests(_Base):
    META = '<meta name="enamad-verification" content="merchant-token-123">'

    def verified_domain(self):
        return StoreDomain.objects.create(store=self.store, hostname="shop.example.ir", domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
                                          verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now())

    def test_the_footer_checkbox_is_the_sellers_choice_and_the_real_state_is_shown_beside_it(self):
        self.post("connect", "enamad", verification_meta_tag=self.META, enamad_show_badge="1")
        drawer = view_html(self.client, "enamad").split('data-testid="drawer-enamad"')[1].split("</dialog>")[0]
        self.assertIn('data-testid="int-enamad_show_badge"', drawer)
        self.assertRegex(drawer, r'data-testid="int-enamad_show_badge"[^>]* checked')              # ticked although no ID is saved…
        self.assertIn('data-testid="enamad-real-display" data-shown="0"', drawer)                  # …and the page says nothing is shown
        self.assertIn("این فقط انتخاب شماست", drawer)
        self.assertIn("هنوز ذخیره نشده", drawer)

    def test_no_badge_and_no_partial_link_without_both_identifiers_even_on_a_verified_domain(self):
        self.verified_domain()
        self.post("connect", "enamad", enamad_id="221617", enamad_auth_code="")
        self.assertFalse(StoreIntegrationConnection.objects.filter(store=self.store, provider_code="enamad").exists())
        flow = svs  # noqa: F841  (module imported for symmetry; the flow below is the real source)
        from apps.stores.services import enamad_verification_service as ev

        self.post("connect", "enamad", verification_meta_tag=self.META)
        state = ev.enamad_flow(self.store, self.row("enamad")["credentials"], connected=True)
        self.assertFalse(state["badge_shown"])
        self.assertEqual([s["state"] for s in state["stages"] if s["key"] == "badge"], ["empty"])

    def test_localhost_is_not_a_verified_domain_and_shows_nothing(self):
        self.post("connect", "enamad", enamad_id="221617", enamad_auth_code="94MqMPJEnuahlSHjb9kP", enamad_show_badge="1")
        html = view_html(self.client, "enamad")
        self.assertIn('data-testid="enamad-badge-state" data-shown="0"', html)
        self.assertIn("نه روی آدرس آزمایشی یا localhost", html)
        self.assertNotIn("trustseal.enamad.ir", html)

    def test_with_a_verified_custom_domain_the_state_becomes_shown_but_never_says_verified_by_enamad(self):
        self.verified_domain()
        self.post("connect", "enamad", enamad_id="221617", enamad_auth_code="94MqMPJEnuahlSHjb9kP", enamad_show_badge="1")
        html = view_html(self.client, "enamad")
        self.assertIn('data-testid="enamad-badge-state" data-shown="1"', html)
        self.assertIn("تأییدِ رسمیِ نماد را فقط پنل اینماد می‌دهد", html)
        self.assertNotIn("اینماد تأییدشده است", html)
        self.assertNotIn("تأیید شد", html.split('data-testid="enamad-group"')[1].split("</section>")[0])

    def test_unticking_the_choice_hides_the_seal_but_keeps_the_ids(self):
        self.verified_domain()
        self.post("connect", "enamad", enamad_id="221617", enamad_auth_code="94MqMPJEnuahlSHjb9kP")           # checkbox absent = unticked
        self.assertEqual(self.saved("enamad")["enamad_show_badge"], "0")
        self.assertEqual(self.saved("enamad")["enamad_id"], "221617")
        self.assertIn('data-testid="enamad-badge-state" data-shown="0"', view_html(self.client, "enamad"))

    def test_the_code_is_stored_encrypted_and_never_echoed_into_other_tabs(self):
        self.post("connect", "enamad", enamad_id="221617", enamad_auth_code="94MqMPJEnuahlSHjb9kP", enamad_show_badge="1")
        raw = StoreIntegrationConnection.objects.get(store=self.store, provider_code="enamad").encrypted_credentials
        self.assertNotIn("94MqMPJEnuahlSHjb9kP", str(raw))
        for view in ("overview", "seo", "analytics", "torob", "future"):
            self.assertNotIn("94MqMPJEnuahlSHjb9kP", view_html(self.client, view))
