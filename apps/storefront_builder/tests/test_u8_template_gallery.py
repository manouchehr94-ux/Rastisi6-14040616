"""U8 — Template-First Merchant Experience.

Audit finding: the apply mechanism (`storefront_apply_layout_preset`) and a
9-entry appearance-token gallery (`appearance_registry.TemplateDefinition`
+ `list_templates()`) already existed, but neither had an actual
merchant-facing browse/preview surface — `list_templates()` was passed into
`appearance_panel.html`'s context and never rendered; `list_layout_presets()`
had zero template references anywhere. A merchant could not discover Ready
Templates at all without already knowing the raw `apply-preset/` POST
endpoint existed.

This phase adds the missing NORMAL-mode entry point: a Template Gallery
(`storefront_template_gallery`) that browses the U7 `LayoutPresetDefinition`
registry (composition + appearance + header/footer variants — the fuller
"Ready Template" shape), shows which one is currently applied (via U7's
`template_provenance`), and applies via the existing, unmodified
`storefront_apply_layout_preset` endpoint (same Draft-only, same
confirm-before-replace safety, same "never auto-publish" contract) — no new
write path was introduced. The separate, still-unused `TemplateDefinition`
appearance-token gallery was deliberately not touched or merged this phase
(see the ledger's Known limitations).
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.tests._gallery_support import (
    gallery_client_templates,
    studio_gallery_response,
)
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services import preset_service
from apps.stores.models import Store, StoreDomain, StoreMembership
from apps.storefront_builder.tests._catalog_count import READY_TEMPLATE_COUNT

User = get_user_model()

ADMIN_HOST = "sfb-u8-gallery.rastisi.localhost"
PUBLIC_HOST = "sfb-u8-gallery.example.com"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


@override_settings(ALLOWED_HOSTS=[ADMIN_HOST, PUBLIC_HOST, "testserver"])
class TemplateGalleryTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.store.admin_subdomain = ADMIN_HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        StoreDomain.objects.create(
            store=self.store, hostname=PUBLIC_HOST, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.staff = User.objects.create_user(username="u8_gallery_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.admin_client = Client(HTTP_HOST=ADMIN_HOST)
        self.admin_client.login(username="u8_gallery_owner", password="pass12345")
        self.url = reverse("dashboard:storefront-builder-templates")
        # Pre-Task-10 CORRECTIVE closure (Item 2) — the legacy editor's own
        # topbar link to the Gallery (test_gallery_reachable_from_advanced_
        # editor_topbar below) now renders only in the still-required FULL
        # legacy body; the Gallery itself is unaffected (its own template,
        # and already globally reachable from base_admin.html's persistent
        # nav/search regardless of this flag).
        layout = svc.get_or_create_layout(self.store)
    def test_legacy_gallery_url_forwards_to_the_studio_gallery_and_opens_it(self):
        response = self.admin_client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"], reverse("dashboard:storefront-builder-r4-editor") + "?open=templates",
        )

    def test_legacy_gallery_url_keeps_the_requested_page(self):
        response = self.admin_client.get(self.url, {"page": "product_detail"})
        self.assertEqual(
            response["Location"],
            reverse("dashboard:storefront-builder-r4-editor") + "?page=product_detail&open=templates",
        )

    def test_studio_gallery_lists_every_registered_ready_template(self):
        """The Studio gallery shows only the registry-flagged Ready Templates (`list_ready_templates()`)."""
        response = studio_gallery_response(self.admin_client)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {t["key"] for t in gallery_client_templates(response)}, {p.key for p in lpr.list_ready_templates()},
        )
        self.assertEqual(len(gallery_client_templates(response)), READY_TEMPLATE_COUNT)
        labels = {t["label"] for t in gallery_client_templates(response)}
        for preset in lpr.list_ready_templates():
            self.assertIn(preset.label_fa, labels)

    def test_no_template_applied_yet_shows_no_current_template(self):
        response = studio_gallery_response(self.admin_client)
        self.assertFalse(any(t["is_current"] for t in gallery_client_templates(response)))

    def test_applied_template_shows_as_current(self):
        # dense_catalog is a historical preset no longer surfaced in the gallery — use a Ready Template.
        draft = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft, lpr.get_layout_preset("dense_marketplace"))
        response = studio_gallery_response(self.admin_client)
        current = [t["key"] for t in gallery_client_templates(response) if t["is_current"]]
        self.assertEqual(current, ["dense_marketplace"])

    def test_header_footer_variant_labels_are_shown_for_every_template(self):
        response = studio_gallery_response(self.admin_client)
        for t in gallery_client_templates(response):
            self.assertTrue(t["header_label"], t["key"])
            self.assertTrue(t["footer_label"], t["key"])

    def test_gallery_url_is_read_only(self):
        """Just following the gallery URL must never write anything — no draft mutation, no provenance change,
        no publish, no new Draft."""
        draft_before = svc.get_or_create_draft(self.store)
        self.assertEqual(draft_before.template_provenance, {})
        self.admin_client.get(self.url)  # the redirect itself
        draft_after = svc.get_or_create_draft(self.store)
        self.assertEqual(draft_after.pk, draft_before.pk)
        self.assertEqual(draft_after.edit_revision, draft_before.edit_revision)
        self.assertEqual(draft_after.template_provenance, {})

    def test_legacy_apply_endpoint_replaces_only_after_explicit_confirmation(self):
        """The compatibility apply endpoint shares the Studio's exact-replace gate: a template switch over existing
        content needs the explicit confirmation flag, and writes nothing without it."""
        draft = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft, lpr.get_layout_preset("dense_marketplace"))
        # merchant work on the Draft: replacing it now discards design work -> explicit confirmation required
        from apps.storefront_builder.models import StorefrontSection

        StorefrontSection.objects.create(
            page=draft.get_page("home"), section_key="rich_text", order=999, settings={"content": "merchant note"},
        )
        apply_url = reverse("dashboard:storefront-builder-apply-preset")
        before = [s.section_key for s in svc.get_or_create_draft(self.store).home_page().sections.order_by("order", "id")]
        refused = self.admin_client.post(apply_url, {"preset_key": "almas_luxury"})
        self.assertEqual(refused.status_code, 302)
        draft.refresh_from_db()
        self.assertEqual(draft.template_provenance["template"]["key"], "dense_marketplace")
        self.assertEqual(before, [s.section_key for s in draft.home_page().sections.order_by("order", "id")])
        accepted = self.admin_client.post(apply_url, {"preset_key": "almas_luxury", "confirm_preset_apply": "1"})
        self.assertEqual(accepted.status_code, 302)
        draft.refresh_from_db()
        self.assertEqual(draft.template_provenance["template"]["key"], "almas_luxury")

    def test_anonymous_request_is_redirected_not_served(self):
        anon_client = Client(HTTP_HOST=ADMIN_HOST)
        response = anon_client.get(self.url)
        self.assertNotEqual(response.status_code, 200)
        self.assertNotIn("open=templates", response.get("Location", ""))


class SharedReplaceCheckHelperTests(TestCase):
    """The gallery's warning and the apply endpoint's server-side guard must
    agree — they now share one helper function rather than two independent
    (and possibly diverging) computations."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_helper_matches_endpoint_behavior_when_content_exists(self):
        from apps.storefront_builder.views import _preset_would_replace_content

        draft = svc.get_or_create_draft(self.store)
        preset = lpr.get_layout_preset("clean_minimal")
        preset_service.apply_preset(draft, preset)
        self.assertTrue(_preset_would_replace_content(draft, preset))

    def test_helper_false_for_untouched_pages(self):
        from apps.storefront_builder.views import _preset_would_replace_content

        draft = svc.get_or_create_draft(self.store)
        draft.get_page("home").sections.all().delete()
        for page_type in lpr.get_layout_preset("clean_minimal").pages:
            draft.get_page(page_type).sections.all().delete()
        preset = lpr.get_layout_preset("clean_minimal")
        self.assertFalse(_preset_would_replace_content(draft, preset))
