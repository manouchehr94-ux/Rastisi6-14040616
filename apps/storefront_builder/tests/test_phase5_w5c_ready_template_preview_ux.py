"""P5-W5C — Ready Template Preview UX (in-page Desktop/Tablet/Mobile,
Demo/Merchant data) — focused contract tests.

Written BEFORE the production markup/JS change (strict TDD RED). Exercises
the EXISTING Gallery view (``storefront_template_gallery``) and the
EXISTING canonical live-preview route (``storefront_template_live_preview``)
— W5C adds no new route, renderer, or mutation. These tests prove:

* the Gallery still exposes all 50 registry Ready Templates, each with an
  in-page preview trigger carrying both canonical preview URLs (never a
  client-guessed URL) and a merchant-facing label;
* the dialog markup contains exactly one iframe, wired to the canonical
  route only, with the same 1200/768/390 device-presentation contract R4
  already uses;
* opening/retargeting/switching device/switching data source is entirely
  non-mutating (Draft identity, edit_revision, template_provenance,
  header/footer/appearance config, sections, containers, history count,
  and the Published pointer are all unchanged);
* the existing Apply form, replace-content confirmation, current-template
  badge, and screenshot-fallback authority are all untouched;
* tenant isolation and the invalid-key 404 both continue to hold;
* the dialog markup has a real static accessible contract (dynamic
  focus/keyboard behavior is proven separately by browser QA).
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.models import (
    StorefrontContainer,
    StorefrontEditHistoryEntry,
    StorefrontLayout,
    StorefrontLayoutVersion,
    StorefrontSection,
)
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services import preset_service
from apps.stores.models import Store, StoreDomain, StoreMembership

User = get_user_model()

ADMIN_HOST = "sfb-w5c-gallery-preview.rastisi.localhost"
PUBLIC_HOST = "sfb-w5c-gallery-preview.example.com"

#: Registry-derived, never a second hand-written key list (contract A).
REGISTERED_READY_TEMPLATE_KEYS = [preset.key for preset in lpr.list_ready_templates()]


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _draft_snapshot(draft: StorefrontLayoutVersion) -> dict:
    """Full lifecycle snapshot for the non-mutation proof (contracts H-K),
    matching the established Task-3 snapshot shape."""
    draft.refresh_from_db()
    return {
        "pk": draft.pk,
        "edit_revision": draft.edit_revision,
        "appearance_config": draft.appearance_config,
        "header_config": draft.header_config,
        "footer_config": draft.footer_config,
        "template_provenance": draft.template_provenance,
        "sections": list(
            StorefrontSection.objects.filter(page__version=draft)
            .order_by("page_id", "order", "id")
            .values_list("page_id", "section_key", "order", "settings", "is_locked")
        ),
        "container_count": StorefrontContainer.objects.filter(page__version=draft).count(),
        "history_count": StorefrontEditHistoryEntry.objects.filter(draft_version=draft).count(),
        "published_version_id": StorefrontLayout.objects.get(pk=draft.layout_id).published_version_id,
    }


@override_settings(ALLOWED_HOSTS=[ADMIN_HOST, PUBLIC_HOST, "testserver"])
class GalleryPreviewTriggerTests(TestCase):
    """Contracts A, B, C, D, E, F, G, O, Q."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.store.admin_subdomain = ADMIN_HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        StoreDomain.objects.create(
            store=self.store, hostname=PUBLIC_HOST, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.staff = User.objects.create_user(username="w5c_gallery_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=ADMIN_HOST)
        self.client.login(username="w5c_gallery_owner", password="pass12345")
        self.url = reverse("dashboard:storefront-builder-templates")

    def test_gallery_lists_every_registered_ready_template(self):
        """Contract A — registry-derived, count == 50, never a second
        hand-written 50-key list here."""
        self.assertEqual(len(REGISTERED_READY_TEMPLATE_KEYS), 50)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        for preset in lpr.list_ready_templates():
            self.assertIn(preset.label_fa, html)

    def test_every_card_carries_both_canonical_preview_urls_and_label(self):
        """Contract B, C — both URLs come from Django's own {% url %}
        resolution (reverse()), never a client-guessed pattern."""
        response = self.client.get(self.url)
        html = response.content.decode()
        for preset in lpr.list_ready_templates():
            demo_url = reverse("dashboard:storefront-builder-template-live-preview", kwargs={"key": preset.key})
            merchant_url = demo_url + "?data=merchant"
            self.assertIn(f'data-tpl-preview-url-demo="{demo_url}"', html)
            self.assertIn(f'data-tpl-preview-url-merchant="{merchant_url}"', html)
            self.assertIn(f'data-tpl-preview-label="{preset.label_fa}"', html)

    def test_merchant_url_has_no_tenant_identifying_query_params(self):
        """Contract D — merchant mode is a bare ``?data=merchant``, never a
        store_id/tenant_id/store slug the client could smuggle in."""
        response = self.client.get(self.url)
        html = response.content.decode()
        preset = lpr.list_ready_templates()[0]
        demo_url = reverse("dashboard:storefront-builder-template-live-preview", kwargs={"key": preset.key})
        merchant_url = demo_url + "?data=merchant"
        self.assertIn(f'data-tpl-preview-url-merchant="{merchant_url}"', html)
        self.assertNotIn("store_id=", html)
        self.assertNotIn("tenant_id=", html)

    def test_demo_url_is_the_bare_canonical_route(self):
        """Contract E — Demo mode is the SAME route with no extra params,
        so it continues to resolve to the canonical rasti-mode-demo Store."""
        response = self.client.get(self.url)
        html = response.content.decode()
        preset = lpr.list_ready_templates()[0]
        demo_url = reverse("dashboard:storefront-builder-template-live-preview", kwargs={"key": preset.key})
        self.assertIn(f'data-tpl-preview-url-demo="{demo_url}"', html)

    def test_exactly_one_preview_iframe_in_the_dialog_markup(self):
        """Contract F — one shared dialog/iframe, not one per card."""
        response = self.client.get(self.url)
        html = response.content.decode()
        self.assertEqual(html.count("data-tpl-preview-frame"), 1)
        self.assertEqual(html.count("<iframe"), 1)

    def test_device_controls_expose_the_1200_768_390_contract(self):
        """Contract G — same width contract as R4's own device switcher."""
        response = self.client.get(self.url)
        html = response.content.decode()
        self.assertIn('data-desktop-viewport-width="1200"', html)
        self.assertIn('data-tablet-viewport-width="768"', html)
        self.assertIn('data-mobile-viewport-width="390"', html)
        self.assertIn('data-tpl-preview-device="desktop"', html)
        self.assertIn('data-tpl-preview-device="tablet"', html)
        self.assertIn('data-tpl-preview-device="mobile"', html)

    def test_data_source_controls_present(self):
        response = self.client.get(self.url)
        html = response.content.decode()
        self.assertIn('data-tpl-preview-datasource="merchant"', html)
        self.assertIn('data-tpl-preview-datasource="demo"', html)

    def test_screenshot_fallback_thumbnail_still_rendered(self):
        """Contract O — screenshot/SVG fallback authority untouched; the
        Gallery card thumbnail still renders (screenshot <img> or the SVG
        fallback), unrelated to the new preview trigger wiring."""
        response = self.client.get(self.url)
        html = response.content.decode()
        self.assertIn('class="tpl-thumb"', html)

    def test_invalid_template_key_still_404s(self):
        """Contract Q — unrelated to W5C; regression guard only."""
        response = self.client.get(
            reverse("dashboard:storefront-builder-template-live-preview", kwargs={"key": "not-a-real-key"}),
        )
        self.assertEqual(response.status_code, 404)


@override_settings(ALLOWED_HOSTS=[ADMIN_HOST, PUBLIC_HOST, "testserver"])
class GalleryDialogAccessibilityMarkupTests(TestCase):
    """Contract R (static markup half; dynamic focus/keyboard behavior is
    proven by browser QA)."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.store.admin_subdomain = ADMIN_HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.staff = User.objects.create_user(username="w5c_a11y_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=ADMIN_HOST)
        self.client.login(username="w5c_a11y_owner", password="pass12345")
        self.url = reverse("dashboard:storefront-builder-templates")

    def test_dialog_has_role_dialog_aria_modal_and_labelledby(self):
        response = self.client.get(self.url)
        html = response.content.decode()
        self.assertIn('role="dialog"', html)
        self.assertIn('aria-modal="true"', html)
        self.assertIn("aria-labelledby=", html)

    def test_dialog_has_an_explicit_close_control(self):
        response = self.client.get(self.url)
        html = response.content.decode()
        self.assertIn("data-tpl-preview-close", html)

    def test_device_and_datasource_buttons_expose_aria_pressed(self):
        response = self.client.get(self.url)
        html = response.content.decode()
        self.assertIn('data-tpl-preview-device="desktop" aria-pressed="true"', html)
        self.assertIn('data-tpl-preview-device="tablet" aria-pressed="false"', html)
        self.assertIn('data-tpl-preview-device="mobile" aria-pressed="false"', html)


@override_settings(ALLOWED_HOSTS=[ADMIN_HOST, PUBLIC_HOST, "testserver"])
class GalleryPreviewNonMutationTests(TestCase):
    """Contracts H, I, J, K — opening/retargeting/switching device/
    switching data source must never mutate Draft/Published state.

    Device switching itself never causes any server round-trip (pure CSS
    presentation on the already-loaded iframe — see the implementation
    plan's "Device presentation" section), so at the Django level the only
    round-trips a real merchant session can produce are: the Gallery page
    load, and loading the live-preview route in either data mode (which is
    exactly what "opening the dialog" / "retargeting to another template" /
    "switching data source" each do). This class proves ALL of those are
    non-mutating.
    """

    @classmethod
    def setUpTestData(cls):
        # Demo mode resolves the fixed canonical rasti-mode-demo Store —
        # seed it once per class (heavy pipeline), matching the established
        # Task-2 convention (test_task2_live_demo_template_preview.py).
        from io import StringIO

        call_command("apply_golden_reference_storefront", stdout=StringIO())

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.store.admin_subdomain = ADMIN_HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.staff = User.objects.create_user(username="w5c_nomut_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=ADMIN_HOST)
        self.client.login(username="w5c_nomut_owner", password="pass12345")
        self.gallery_url = reverse("dashboard:storefront-builder-templates")
        self.draft = svc.get_or_create_draft(self.store)

    def _preview_url(self, key, merchant=False):
        url = reverse("dashboard:storefront-builder-template-live-preview", kwargs={"key": key})
        return url + "?data=merchant" if merchant else url

    def test_opening_gallery_is_non_mutating(self):
        before = _draft_snapshot(self.draft)
        response = self.client.get(self.gallery_url)
        self.assertEqual(response.status_code, 200)
        after = _draft_snapshot(self.draft)
        self.assertEqual(before, after)

    def test_opening_demo_preview_is_non_mutating(self):
        preset = lpr.list_ready_templates()[0]
        before = _draft_snapshot(self.draft)
        response = self.client.get(self._preview_url(preset.key, merchant=False))
        self.assertEqual(response.status_code, 200)
        after = _draft_snapshot(self.draft)
        self.assertEqual(before, after)

    def test_opening_merchant_preview_is_non_mutating(self):
        preset = lpr.list_ready_templates()[0]
        before = _draft_snapshot(self.draft)
        response = self.client.get(self._preview_url(preset.key, merchant=True))
        self.assertEqual(response.status_code, 200)
        after = _draft_snapshot(self.draft)
        self.assertEqual(before, after)

    def test_switching_data_source_back_and_forth_is_non_mutating(self):
        """Simulates the dialog's data-source toggle: several round-trips
        between Demo and Merchant for the SAME template."""
        preset = lpr.list_ready_templates()[1]
        before = _draft_snapshot(self.draft)
        for merchant in (True, False, True, False):
            response = self.client.get(self._preview_url(preset.key, merchant=merchant))
            self.assertEqual(response.status_code, 200)
        after = _draft_snapshot(self.draft)
        self.assertEqual(before, after)

    def test_retargeting_to_a_second_template_is_non_mutating(self):
        """Simulates opening Template A, then Template B, in the same
        dialog session (browser QA step 31's non-mutation half)."""
        first, second = lpr.list_ready_templates()[0], lpr.list_ready_templates()[-1]
        before = _draft_snapshot(self.draft)
        self.client.get(self._preview_url(first.key, merchant=True))
        self.client.get(self._preview_url(second.key, merchant=True))
        after = _draft_snapshot(self.draft)
        self.assertEqual(before, after)

    def test_previewing_template_x_does_not_change_current_template_provenance(self):
        """Contract K — apply a real Ready Template first, then preview a
        DIFFERENT one; provenance must still point at the applied one."""
        applied = lpr.get_layout_preset("dense_marketplace")
        preset_service.apply_preset(self.draft, applied)
        provenance_before = _draft_snapshot(self.draft)["template_provenance"]
        self.assertEqual(provenance_before.get("template", {}).get("key"), "dense_marketplace")

        other = lpr.get_layout_preset("premium_leather")
        self.client.get(self._preview_url(other.key, merchant=True))
        self.client.get(self._preview_url(other.key, merchant=False))

        after = _draft_snapshot(self.draft)
        self.assertEqual(after["template_provenance"].get("template", {}).get("key"), "dense_marketplace")


@override_settings(ALLOWED_HOSTS=[ADMIN_HOST, PUBLIC_HOST, "testserver"])
class GalleryApplyPathUnchangedTests(TestCase):
    """Contracts L, M, N — existing Apply path, replace-content
    confirmation, and current-template badge all remain intact."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.store.admin_subdomain = ADMIN_HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.staff = User.objects.create_user(username="w5c_apply_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=ADMIN_HOST)
        self.client.login(username="w5c_apply_owner", password="pass12345")
        self.url = reverse("dashboard:storefront-builder-templates")

    def test_apply_form_still_posts_to_the_existing_endpoint(self):
        response = self.client.get(self.url)
        html = response.content.decode()
        apply_url = reverse("dashboard:storefront-builder-apply-preset")
        self.assertIn(f'action="{apply_url}"', html)
        self.assertIn('name="preset_key"', html)
        self.assertIn("csrfmiddlewaretoken", html)

    def test_no_second_apply_or_preview_mutation_endpoint_introduced(self):
        response = self.client.get(self.url)
        html = response.content.decode()
        for forbidden in ("preview.apply", "modal.apply", "/preview/apply/"):
            self.assertNotIn(forbidden, html)

    def test_replace_content_confirmation_still_gated_correctly(self):
        draft = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft, lpr.get_layout_preset("dense_marketplace"))
        response = self.client.get(self.url)
        html = response.content.decode()
        self.assertIn("confirm(", html)
        self.assertIn('name="confirm_preset_apply" value="1"', html)

    def test_current_template_badge_still_renders(self):
        draft = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft, lpr.get_layout_preset("warm_boutique"))
        response = self.client.get(self.url)
        html = response.content.decode()
        self.assertIn("قالبِ فعلی", html)
        self.assertIn("در حال استفاده", html)


@override_settings(ALLOWED_HOSTS=["sfb-w5c-tenant-a.rastisi.localhost", "sfb-w5c-tenant-b.rastisi.localhost", "testserver"])
class GalleryPreviewTenantIsolationTests(TestCase):
    """Contract P — merchant-mode preview must continue resolving only the
    authenticated merchant's own canonical Store; a query-string attempt to
    name a different Store/tenant must remain ignored."""

    ADMIN_HOST_A = "sfb-w5c-tenant-a.rastisi.localhost"

    def setUp(self):
        cache.clear()
        self.store_a = Store.objects.create(
            slug="w5c-tenant-a", name="W5C Tenant A", admin_subdomain="sfb-w5c-tenant-a",
            status=Store.Status.ACTIVE,
        )
        self.store_b = Store.objects.create(
            slug="w5c-tenant-b", name="W5C Tenant B", admin_subdomain="sfb-w5c-tenant-b",
            status=Store.Status.ACTIVE,
        )
        self.user = User.objects.create_user(username="w5c_tenant_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store_a, user=self.user, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        svc.get_or_create_draft(self.store_a)
        self.client = Client(HTTP_HOST=self.ADMIN_HOST_A)
        self.client.login(username="w5c_tenant_owner", password="pass12345")

    def test_query_string_store_hints_are_ignored_in_merchant_preview(self):
        preset = lpr.list_ready_templates()[0]
        url = reverse("dashboard:storefront-builder-template-live-preview", kwargs={"key": preset.key})
        response = self.client.get(
            f"{url}?data=merchant&store_id={self.store_b.pk}&store={self.store_b.slug}&tenant_id={self.store_b.pk}",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["store"].pk, self.store_a.pk)
