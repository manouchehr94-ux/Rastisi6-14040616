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
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services import preset_service
from apps.stores.authorization import STOREFRONT_LAYOUT_MANAGE
from apps.stores.models import Store, StoreDomain, StoreMembership

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
        layout.r4_editor_enabled = False
        layout.save(update_fields=["r4_editor_enabled"])

    def test_lists_every_registered_ready_template(self):
        """Acceptance Batch 1 (post-U11) — the Gallery now shows only the
        registry-flagged Ready Templates (`list_ready_templates()`), not
        every `LayoutPresetDefinition` (`list_layout_presets()` still
        returns all 13, including the 5 historical/internal presets kept
        for Advanced-mode use). See test_acceptance_batch1.py for the full
        separation test suite."""
        response = self.admin_client.get(self.url)
        self.assertEqual(response.status_code, 200)
        for preset in lpr.list_ready_templates():
            self.assertContains(response, preset.label_fa)

    def test_no_template_applied_yet_shows_no_current_badge(self):
        response = self.admin_client.get(self.url)
        self.assertNotContains(response, "قالبِ فعلی")
        self.assertNotContains(response, "در حال استفاده")

    def test_applied_template_shows_as_current(self):
        # Acceptance Batch 1 (post-U11): dense_catalog is a historical preset
        # no longer surfaced in the Gallery — use a Ready Template so the
        # "current" card is actually rendered to assert against.
        draft = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft, lpr.get_layout_preset("dense_marketplace"))
        response = self.admin_client.get(self.url)
        self.assertContains(response, "قالبِ فعلی")
        self.assertContains(response, "در حال استفاده")

    def test_header_footer_variant_labels_shown_for_updated_preset(self):
        response = self.admin_client.get(self.url)
        # dense_catalog was assigned marketplace_search_first/marketplace_dense in U7.
        self.assertContains(response, "بازارگاهی (جستجو-محور)")
        self.assertContains(response, "بازارگاهی (فشرده)")

    def test_gallery_view_is_read_only(self):
        """Just viewing the gallery must never write anything — no draft
        mutation, no provenance change, no publish."""
        draft_before = svc.get_or_create_draft(self.store)
        self.assertEqual(draft_before.template_provenance, {})
        self.admin_client.get(self.url)
        draft_after = svc.get_or_create_draft(self.store)
        self.assertEqual(draft_after.pk, draft_before.pk)
        self.assertEqual(draft_after.template_provenance, {})

    def test_apply_form_confirms_before_replacing_existing_content(self):
        draft = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft, lpr.get_layout_preset("clean_minimal"))
        response = self.admin_client.get(self.url)
        # Applying a *different* preset than the current one, when content
        # already exists, must render the JS confirm() guard.
        self.assertContains(response, "confirm(")
        self.assertContains(response, 'name="confirm_preset_apply" value="1"')

    def test_anonymous_request_is_redirected_not_served(self):
        anon_client = Client(HTTP_HOST=ADMIN_HOST)
        response = anon_client.get(self.url)
        self.assertNotEqual(response.status_code, 200)

    def test_gallery_reachable_from_advanced_editor_topbar(self):
        response = self.admin_client.get(reverse("dashboard:storefront-builder-editor"))
        self.assertContains(response, reverse("dashboard:storefront-builder-templates"))

    def test_advanced_editor_reachable_from_gallery(self):
        response = self.admin_client.get(self.url)
        self.assertContains(response, reverse("dashboard:storefront-builder-editor"))


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
