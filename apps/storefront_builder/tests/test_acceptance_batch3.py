"""Acceptance Batch 3 (post-U11) — «Real Ready-Template Gallery Previews /
Thumbnails».

Real gap: the merchant-facing Ready Template Gallery (U8) showed each card
with only a flat 3-color swatch strip — no structural preview at all, so a
merchant could not tell one Template's actual design language from
another before applying it.

Architecture: ``services/template_preview_service.build_template_thumbnail_svg``
computes a deterministic inline SVG schematic purely from real registry
data (resolved palette/theme-role colors, the Preset's real
``pages["home"]`` composition, ``appearance.density``) — no screenshot, no
database row, no second hand-maintained renderer, no Playwright/browser
process at request time. See that module's own docstring for the full
rationale; this file only tests the resulting contract.

Note on tests M-P from the master contract ("if implementing a thumbnail
generation command/tool..."): this Batch deliberately does NOT add a
static-asset generation command, manifest, or file-based pipeline — the
thumbnail is computed live from in-memory registry data on every request
(cheap, always-fresh, immune to going stale). M-P therefore do not apply;
this is documented in the execution ledger's Batch 3 entry.
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.models import StorefrontLayoutVersion
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services import preset_service
from apps.storefront_builder.services import template_preview_service as tps
from apps.stores.authorization import STOREFRONT_LAYOUT_MANAGE
from apps.stores.models import Store, StoreDomain, StoreMembership

User = get_user_model()

ADMIN_HOST = "sfb-batch3.rastisi.localhost"
PUBLIC_HOST = "sfb-batch3.example.com"

READY_TEMPLATE_KEYS = (
    "dense_marketplace", "premium_leather", "warm_boutique", "fashion_promo_catalog",
    "playful_lifestyle", "utility_catalog", "editorial_jewelry", "dark_digital",
)

#: Note: the standard SVG root element always declares
#: xmlns="http://www.w3.org/2000/svg" — a required namespace URI, not a
#: "remote reference image"; the real forbidden signal is an embedded/
#: linked external image (`<image>` / `xlink:href`) or reference-store
#: branding text.
_FORBIDDEN_STRINGS = ("rastisi-fashion-test", "<image", "xlink:href")


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _second_store():
    store, _ = Store.objects.get_or_create(
        slug="sfb-batch3-store-b", defaults=dict(name="فروشگاه دوم Batch 3", status=Store.Status.ACTIVE),
    )
    return store


class ThumbnailServiceTests(TestCase):
    """Tests A-D, J, L at the pure-function level — no HTTP involved."""

    def test_a_original_preview_targets_remain_official_templates(self):
        self.assertTrue(
            set(READY_TEMPLATE_KEYS).issubset({p.key for p in lpr.list_ready_templates()})
        )

    def test_b_every_official_ready_template_resolves_a_visual_thumbnail(self):
        for key in READY_TEMPLATE_KEYS:
            preset = lpr.get_layout_preset(key)
            svg = tps.resolve_gallery_thumbnail(preset)
            self.assertTrue(svg.startswith("<svg"), key)
            self.assertTrue(svg.endswith("</svg>"), key)
            self.assertGreater(svg.count("<rect"), 3, f"{key} thumbnail looks empty")

    def test_c_no_two_templates_share_an_accidental_identical_or_mismatched_thumbnail(self):
        thumbnails = {key: tps.build_template_thumbnail_svg(lpr.get_layout_preset(key)) for key in READY_TEMPLATE_KEYS}
        self.assertEqual(len(set(thumbnails.values())), len(READY_TEMPLATE_KEYS))
        # Determinism: the same key always resolves the same markup.
        for key in READY_TEMPLATE_KEYS:
            again = tps.build_template_thumbnail_svg(lpr.get_layout_preset(key))
            self.assertEqual(again, thumbnails[key], key)

    def test_d_a_broken_thumbnail_computation_degrades_to_a_safe_placeholder(self):
        from unittest import mock

        preset = lpr.get_layout_preset("dense_marketplace")
        with mock.patch(
            "apps.storefront_builder.services.template_preview_service.build_template_thumbnail_svg",
            side_effect=RuntimeError("simulated broken preset shape"),
        ):
            svg = tps.resolve_gallery_thumbnail(preset)
        self.assertTrue(svg.startswith("<svg"))
        self.assertTrue(svg.endswith("</svg>"))

    def test_j_thumbnails_contain_no_forbidden_branding_or_remote_references(self):
        for key in READY_TEMPLATE_KEYS:
            svg = tps.build_template_thumbnail_svg(lpr.get_layout_preset(key))
            for forbidden in _FORBIDDEN_STRINGS:
                self.assertNotIn(forbidden, svg, f"{key}: found forbidden fragment {forbidden!r}")

    def test_l_thumbnail_is_pure_global_registry_data_no_store_identity(self):
        """Tenant isolation at the source: the thumbnail function never
        takes a store/request — it is a pure function of `LayoutPresetDefinition`,
        so it cannot leak any store's products/categories/media/identity."""
        preset = lpr.get_layout_preset("dense_marketplace")
        svg_a = tps.build_template_thumbnail_svg(preset)
        for name in ("akhlaghi", _second_store().slug):
            self.assertNotIn(name, svg_a)
        # calling it again (simulating "for a different store's Gallery")
        # yields byte-identical output.
        svg_b = tps.build_template_thumbnail_svg(preset)
        self.assertEqual(svg_a, svg_b)


@override_settings(ALLOWED_HOSTS=[ADMIN_HOST, PUBLIC_HOST, "testserver"])
class GalleryPreviewIntegrationTests(TestCase):
    """Tests B/I/K at the HTTP/template level, and the full no-mutation
    contract (E-H) plus tenant isolation (L) end-to-end."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.store.admin_subdomain = ADMIN_HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        StoreDomain.objects.create(
            store=self.store, hostname=PUBLIC_HOST, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.staff = User.objects.create_user(username="batch3_gallery_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.admin_client = Client(HTTP_HOST=ADMIN_HOST)
        self.admin_client.login(username="batch3_gallery_owner", password="pass12345")
        self.url = reverse("dashboard:storefront-builder-templates")

    def test_b_every_card_renders_an_svg_thumbnail(self):
        response = self.admin_client.get(self.url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertEqual(content.count('<div class="tpl-thumb"'), 53)
        # Every card must carry its own thumbnail — an inline SVG or a screenshot
        # image. (This used to count every "<svg" on the page, which only reached 50
        # because the admin sidebar's nav icons were included in the total.)
        from bs4 import BeautifulSoup

        thumbs = BeautifulSoup(content, "html.parser").select(".tpl-thumb")
        self.assertEqual(len(thumbs), 53)
        missing = [t.get("aria-label") for t in thumbs if not (t.find("svg") or t.find("img"))]
        self.assertEqual(missing, [], "template cards without a thumbnail")

    def test_i_current_template_badge_and_disabled_action_still_correct(self):
        draft = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft, lpr.get_layout_preset("dark_digital"))
        response = self.admin_client.get(self.url)
        cards = {c["preset"].key: c for c in response.context["template_cards"]}
        self.assertTrue(cards["dark_digital"]["is_current"])
        self.assertContains(response, "قالبِ فعلی")
        self.assertContains(response, "در حال استفاده")
        self.assertNotContains(response, 'name="preset_key" value="dark_digital"')
        # the current card still gets a real thumbnail, not a blank slot —
        # either the Batch 3 SVG schematic, or (post-Batch-4) a real
        # captured screenshot when one exists for this Template.
        card = cards["dark_digital"]
        self.assertTrue(
            card["thumbnail_svg"].startswith("<svg") or bool(card.get("thumbnail_url")),
        )

    def test_k_mobile_usable_thumbnail_markup_is_responsive_not_fixed_pixels(self):
        response = self.admin_client.get(self.url)
        content = response.content.decode()
        self.assertIn(".tpl-thumb{", content)
        # a responsive sizing rule (percentage width, not a hard pixel box)
        # so the card scales down on a narrow/mobile viewport.
        thumb_rule_start = content.index(".tpl-thumb{")
        thumb_rule = content[thumb_rule_start:content.index("}", thumb_rule_start)]
        self.assertIn("width:100%", thumb_rule)

    def test_no_internal_registry_keys_or_json_leak_into_the_page(self):
        response = self.admin_client.get(self.url)
        content = response.content.decode()
        self.assertNotIn("template_baseline_snapshot", content)
        self.assertNotIn("template_slot_key", content)

    # --- No-mutation contract (E-H) ---

    def test_e_gallery_get_does_not_change_draft_version_id_or_content(self):
        draft_before = svc.get_or_create_draft(self.store)
        draft_before_id = draft_before.pk
        appearance_before = dict(draft_before.appearance_config)
        header_before = dict(draft_before.header_config)
        footer_before = dict(draft_before.footer_config)
        provenance_before = dict(draft_before.template_provenance)
        snapshot_before = dict(draft_before.template_baseline_snapshot)

        response = self.admin_client.get(self.url)
        self.assertEqual(response.status_code, 200)

        layout = svc.get_or_create_layout(self.store)
        self.assertEqual(layout.draft_version_id, draft_before_id)
        draft_before.refresh_from_db()
        self.assertEqual(draft_before.appearance_config, appearance_before)
        self.assertEqual(draft_before.header_config, header_before)
        self.assertEqual(draft_before.footer_config, footer_before)
        self.assertEqual(draft_before.template_provenance, provenance_before)
        self.assertEqual(draft_before.template_baseline_snapshot, snapshot_before)

    def test_f_gallery_get_does_not_change_published_version(self):
        draft = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft, lpr.get_layout_preset("dense_marketplace"))
        svc.publish(self.store)
        layout = svc.get_or_create_layout(self.store)
        published_before_id = layout.published_version_id
        fingerprint_before = layout.published_version.content_fingerprint

        self.admin_client.get(self.url)

        layout.refresh_from_db()
        self.assertEqual(layout.published_version_id, published_before_id)
        layout.published_version.refresh_from_db()
        self.assertEqual(layout.published_version.content_fingerprint, fingerprint_before)

    def test_g_gallery_get_creates_no_version_history(self):
        svc.get_or_create_draft(self.store)
        layout = svc.get_or_create_layout(self.store)
        versions_before = layout.versions.count()

        for _ in range(3):
            self.admin_client.get(self.url)

        layout.refresh_from_db()
        self.assertEqual(layout.versions.count(), versions_before)

    def test_h_gallery_get_never_calls_the_template_mutation_service(self):
        from unittest import mock

        svc.get_or_create_draft(self.store)
        with mock.patch.object(preset_service, "apply_preset") as mocked_apply, \
             mock.patch.object(preset_service, "apply_preset_with_checkpoint") as mocked_apply_checkpoint:
            response = self.admin_client.get(self.url)
        self.assertEqual(response.status_code, 200)
        mocked_apply.assert_not_called()
        mocked_apply_checkpoint.assert_not_called()

    def test_l_cross_store_gallery_browsing_does_not_leak_or_cross_contaminate(self):
        other_store = _second_store()
        other_draft = svc.get_or_create_draft(other_store)
        preset_service.apply_preset(other_draft, lpr.get_layout_preset("dark_digital"))

        response = self.admin_client.get(self.url)
        cards = {c["preset"].key: c for c in response.context["template_cards"]}
        self.assertFalse(cards["dark_digital"]["is_current"])
        content = response.content.decode()
        self.assertNotIn(other_store.slug, content)
        self.assertNotIn(other_store.name, content)
