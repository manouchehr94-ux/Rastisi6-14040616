"""Phase 5 Task 6 — R4 "Storefront Showcase" creation facade.

APPROVED architecture (Option B): "Showcase" is merchant-facing UX only — a
small R4 chooser that CREATES one of four EXISTING canonical sections via the
existing ``section.add`` mutation. It is NOT a persisted section, renderer,
schema, or resource-source contract.

Canonical mapping (immutable at add time):
    Products     -> product_section
    Categories   -> category_grid
    Collections  -> collection_tiles
    Brands       -> brand_carousel

These tests prove the SERVER projection (``showcase_choices``) is derived from
the existing legal, page-filtered ``structure_library`` — never a second
authority — and that no ``storefront_showcase`` key is ever introduced.
"""
from pathlib import Path

from django.conf import settings as dj_settings
from django.urls import reverse

from apps.storefront_builder import section_registry
from apps.storefront_builder.models import StorefrontPage
from apps.storefront_builder.services import layout_service as svc

from .test_views import StorefrontBuilderViewsTestCase

# The four approved content types, in the approved order, and the single
# canonical section each maps to. This is the contract the facade must honor.
_APPROVED_ORDER = ["products", "categories", "collections", "brands"]
_APPROVED_MAPPING = {
    "products": "product_section",
    "categories": "category_grid",
    "collections": "collection_tiles",
    "brands": "brand_carousel",
}


class ShowcaseFacadeServerProjectionTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        layout = svc.get_or_create_layout(self.store)
        layout.r4_editor_enabled = True
        layout.save(update_fields=["r4_editor_enabled"])

    def _editor(self, page="home"):
        return self.client.get(
            reverse("dashboard:storefront-builder-r4-editor") + f"?page={page}"
        )

    def _choices(self, page="home"):
        resp = self._editor(page)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("showcase_choices", resp.context)
        return resp.context["showcase_choices"]

    def test_editor_context_exposes_showcase_choices(self):
        choices = self._choices()
        self.assertTrue(choices, "showcase_choices must be populated on the home page")

    def test_exactly_the_four_approved_content_types_in_order(self):
        choices = self._choices()
        self.assertEqual([c["content_type"] for c in choices], _APPROVED_ORDER)

    def test_each_choice_maps_to_its_canonical_section_key(self):
        choices = self._choices()
        got = {c["content_type"]: c["section_key"] for c in choices}
        self.assertEqual(got, _APPROVED_MAPPING)

    def test_every_choice_carries_a_merchant_label(self):
        choices = self._choices()
        for c in choices:
            self.assertTrue(c.get("label"), f"missing label for {c['content_type']}")

    def test_every_emitted_key_is_in_the_legal_structure_library(self):
        resp = self._editor()
        legal_keys = {
            item["key"]
            for group in resp.context["structure_library"]
            for item in group["items"]
        }
        for c in resp.context["showcase_choices"]:
            self.assertIn(
                c["section_key"], legal_keys,
                f"{c['section_key']} must come from the legal structure_library",
            )

    def test_no_choice_when_its_canonical_section_is_not_in_the_legal_library(self):
        # Monkeypatch the shared legality projection so that on this request
        # the library contains NONE of the four canonical sections; the facade
        # must then emit zero choices (it never bypasses the legal library).
        import apps.storefront_builder.r4_views as r4_views
        original = section_registry.list_library_groups

        def _empty_groups(page_type=None):
            # Return a library with a single unrelated section only.
            return [("محتوا", [section_registry.get_definition("rich_text")])]

        r4_views.section_registry.list_library_groups = _empty_groups
        try:
            choices = self._choices()
        finally:
            r4_views.section_registry.list_library_groups = original
        self.assertEqual(choices, [], "no Showcase choice may be emitted when its canonical section is unavailable")

    def test_no_persisted_storefront_showcase_key_exists(self):
        self.assertNotIn("storefront_showcase", section_registry.SECTION_REGISTRY)
        self.assertFalse(section_registry.is_valid_section_key("storefront_showcase"))

    def test_facade_stores_no_resource_or_layout_settings(self):
        # The choices are pure presentation metadata: content_type/section_key/
        # label/description only — never resource ids, layout, or source rules.
        allowed = {"content_type", "section_key", "label", "description"}
        for c in self._choices():
            self.assertTrue(set(c).issubset(allowed), f"unexpected keys in choice: {set(c) - allowed}")


class ShowcaseChooserMarkupTests(ShowcaseFacadeServerProjectionTests):
    """The rendered R4 editor shows an inline, accessible Showcase chooser whose
    choice buttons carry ONLY the canonical section_key (never a pseudo key)."""

    def test_editor_renders_showcase_chooser_disclosure(self):
        resp = self._editor()
        html = resp.content.decode()
        # A labeled, accessible inline disclosure (details/summary) exists.
        self.assertIn("data-r4-showcase", html)
        self.assertIn("ویترین فروشگاه", html)

    def test_chooser_renders_a_button_per_choice_with_canonical_key(self):
        resp = self._editor()
        html = resp.content.decode()
        for content_type, section_key in _APPROVED_MAPPING.items():
            self.assertIn(f'data-r4-showcase-choice', html)
            self.assertIn(f'data-section-key="{section_key}"', html)

    def test_chooser_never_emits_pseudo_showcase_key(self):
        html = self._editor().content.decode()
        self.assertNotIn("storefront_showcase", html)
        self.assertNotIn('data-section-key="showcase"', html)

    def test_existing_add_section_control_is_preserved(self):
        # Task 6 is additive; the normal Add Section control stays.
        html = self._editor().content.decode()
        self.assertIn('id="r4StructureAddSelect"', html)
        self.assertIn('id="r4StructureAddButton"', html)


class ShowcaseFacadeSourceContractTests(StorefrontBuilderViewsTestCase):
    """Static source-contract checks on the template + client wiring."""

    _EDITOR_HTML = Path(
        dj_settings.BASE_DIR,
        "apps/storefront_builder/templates/dashboard/storefront_builder/r4/editor.html",
    )
    _EDITOR_JS = Path(
        dj_settings.BASE_DIR,
        "apps/storefront_builder/static/storefront_builder/r4_editor.js",
    )

    def test_template_has_no_pseudo_showcase_section_key(self):
        src = self._EDITOR_HTML.read_text(encoding="utf-8")
        self.assertNotIn("storefront_showcase", src)

    def test_js_wires_showcase_choice_through_existing_mutation_path(self):
        src = self._EDITOR_JS.read_text(encoding="utf-8")
        # Delegated handler for a Showcase choice.
        self.assertIn("data-r4-showcase-choice", src)
        # Reuses the single canonical structural mutation path + section.add.
        self.assertIn("enqueueStructuralMutation", src)
        self.assertIn("'section.add'", src)
        # page_type comes from the shell dataset (not re-derived).
        self.assertIn("r4PageType", src)

    def test_js_does_not_introduce_a_new_endpoint_or_pseudo_key(self):
        src = self._EDITOR_JS.read_text(encoding="utf-8")
        self.assertNotIn("storefront_showcase", src)
        # The Showcase handler must not fetch() directly; it uses the queue.
        # (There is no direct fetch in the existing add flow; assert none is
        # added for the showcase choice by checking the handler region only.)
        idx = src.find("data-r4-showcase-choice")
        self.assertNotEqual(idx, -1)
        region = src[idx:idx + 800]
        self.assertNotIn("fetch(", region)



import json

from apps.storefront_builder.models import StorefrontSection


class ShowcaseFacadeCreatesCanonicalSectionTests(StorefrontBuilderViewsTestCase):
    """The facade choice creates the canonical section through the EXISTING
    section.add mutation — never a pseudo storefront_showcase section — and the
    created section then uses its own canonical Inspector/schema."""

    def setUp(self):
        super().setUp()
        self.layout = svc.get_or_create_layout(self.store)
        self.layout.r4_editor_enabled = True
        self.layout.save(update_fields=["r4_editor_enabled"])
        self.draft = svc.get_or_create_draft(self.store, user=self.staff)

    def _add_via_facade(self, section_key, page_type="home"):
        # Mirrors exactly what the client does for a Showcase choice: the
        # existing section.add mutation with the canonical key + current page.
        self.draft.refresh_from_db()
        return self.client.post(
            reverse("dashboard:storefront-builder-r4-mutation"),
            data=json.dumps({
                "base_revision": self.draft.edit_revision,
                "mutation": {
                    "type": "section.add",
                    "section_key": section_key,
                    "page_type": page_type,
                },
            }),
            content_type="application/json",
        )

    def test_each_mapping_creates_its_canonical_section_key(self):
        page = self.draft.get_page(StorefrontPage.PageType.HOME)
        for content_type, section_key in _APPROVED_MAPPING.items():
            with self.subTest(content_type=content_type):
                before = set(page.sections.values_list("pk", flat=True))
                resp = self._add_via_facade(section_key)
                self.assertEqual(resp.status_code, 200, resp.content)
                self.assertIs(resp.json()["ok"], True)
                new = set(page.sections.values_list("pk", flat=True)) - before
                self.assertEqual(len(new), 1)
                created = StorefrontSection.objects.get(pk=new.pop())
                self.assertEqual(created.section_key, section_key)

    def test_page_type_is_preserved(self):
        # Add on the listing page; the created section must live on listing.
        self.client.post(
            reverse("dashboard:storefront-builder-r4-mutation"),
            data=json.dumps({
                "base_revision": self.draft.edit_revision,
                "mutation": {"type": "section.add", "section_key": "product_section", "page_type": "listing"},
            }),
            content_type="application/json",
        )
        listing = self.draft.get_page(StorefrontPage.PageType.LISTING)
        self.assertTrue(listing.sections.filter(section_key="product_section").exists())
        home = self.draft.get_page(StorefrontPage.PageType.HOME)
        self.assertFalse(home.sections.filter(section_key="product_section").exists())

    def test_no_persisted_storefront_showcase_section_is_ever_created(self):
        for section_key in _APPROVED_MAPPING.values():
            self._add_via_facade(section_key)
        self.assertFalse(
            StorefrontSection.objects.filter(section_key="storefront_showcase").exists()
        )

    def test_created_product_section_uses_its_canonical_inspector_schema(self):
        page = self.draft.get_page(StorefrontPage.PageType.HOME)
        before = set(page.sections.values_list("pk", flat=True))
        self._add_via_facade("product_section")
        created_pk = (set(page.sections.values_list("pk", flat=True)) - before).pop()
        resp = self.client.get(
            reverse("dashboard:storefront-builder-r4-section-inspector", args=[created_pk])
        )
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        # The canonical product inspector — source (resource picker) + layout.
        self.assertIn("data-r4-section-inspector", html)
        self.assertIn("resource_source", html)  # canonical product source field
        self.assertIn("display_mode", html)      # canonical product layout field

    def test_created_sections_reach_their_own_inspectors(self):
        page = self.draft.get_page(StorefrontPage.PageType.HOME)
        for section_key in ("category_grid", "collection_tiles", "brand_carousel"):
            with self.subTest(section_key=section_key):
                before = set(page.sections.values_list("pk", flat=True))
                self._add_via_facade(section_key)
                created_pk = (set(page.sections.values_list("pk", flat=True)) - before).pop()
                resp = self.client.get(
                    reverse("dashboard:storefront-builder-r4-section-inspector", args=[created_pk])
                )
                self.assertEqual(resp.status_code, 200)
                self.assertContains(resp, "data-r4-section-inspector")


class ShowcaseFacadeTenantIsolationTests(StorefrontBuilderViewsTestCase):
    """A section created through the facade is a normal canonical section: the
    existing ResourceSource ownership guard still rejects a foreign-store
    resource — the facade introduces no bypass."""

    def setUp(self):
        super().setUp()
        self.layout = svc.get_or_create_layout(self.store)
        self.layout.r4_editor_enabled = True
        self.layout.save(update_fields=["r4_editor_enabled"])
        self.draft = svc.get_or_create_draft(self.store, user=self.staff)

    def test_foreign_store_resource_rejected_on_facade_created_section(self):
        from decimal import Decimal
        from apps.catalog.models import Brand
        from apps.stores.models import Store

        # Create a product_section via the facade path.
        self.client.post(
            reverse("dashboard:storefront-builder-r4-mutation"),
            data=json.dumps({
                "base_revision": self.draft.edit_revision,
                "mutation": {"type": "section.add", "section_key": "brand_carousel", "page_type": "home"},
            }),
            content_type="application/json",
        )
        section = self.draft.get_page(StorefrontPage.PageType.HOME).sections.get(section_key="brand_carousel")

        # A brand belonging to a DIFFERENT store.
        foreign = Store.objects.create(name="فروشگاه بیگانه", slug="showcase-foreign", status=Store.Status.ACTIVE)
        foreign_brand = Brand.objects.create(store=foreign, name="برند بیگانه", slug="foreign-brand")

        self.draft.refresh_from_db()
        resp = self.client.post(
            reverse("dashboard:storefront-builder-r4-mutation"),
            data=json.dumps({
                "base_revision": self.draft.edit_revision,
                "mutation": {
                    "type": "section.update_settings",
                    "section_id": section.pk,
                    "patch": {"source": {"kind": "brand", "mode": "manual", "manual_ids": [foreign_brand.pk]}},
                },
            }),
            content_type="application/json",
        )
        # The existing ownership guard rejects the cross-store id.
        self.assertEqual(resp.status_code, 400, resp.content)
        section.refresh_from_db()
        self.assertNotIn(foreign_brand.pk, (section.settings.get("brand_ids") or []))


class ShowcaseFacadeReadyTemplateGuardTests(StorefrontBuilderViewsTestCase):
    """Task 6 is additive: it must not touch the Ready-Template recipe
    authorities. This guards the recipe files against accidental edits."""

    def test_ready_template_recipe_files_are_untouched_by_task6(self):
        # Historical Task-6 scope guard:
        #   base = post-Task-5 certified checkpoint (Task-6 PR #3 base)
        #   head = exact Task-6 PR #3 head
        # Future workstreams must not affect this historical assertion, so the
        # diff range is the FIXED Task-6 range (never ``...HEAD``): the guard
        # proves TASK 6 ITSELF did not modify the listed canonical authorities.
        import subprocess
        task6_base = "c0ca174475bf19dd5c3ecac3857da479623e1e7d"
        task6_head = "a75711473b791c2add0389913707503bc0024cc0"
        changed = subprocess.run(
            ["git", "diff", "--name-only", f"{task6_base}...{task6_head}"],
            cwd=dj_settings.BASE_DIR,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
        forbidden = {
            "apps/storefront_builder/a8_ready_templates.py",
            "apps/storefront_builder/layout_preset_registry.py",
            "apps/storefront_builder/section_registry.py",
            "apps/storefront_builder/services/render_service.py",
            "apps/storefront_builder/resource_source.py",
            "apps/storefront_builder/models.py",
            "apps/storefront_builder/services/r4_mutation_service.py",
            "apps/storefront_builder/services/section_structure_service.py",
        }
        offenders = forbidden.intersection(changed)
        self.assertEqual(offenders, set(), f"Task 6 must not modify canonical authorities: {offenders}")
