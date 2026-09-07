"""G2.3 — Builder/Public content & section-appearance consistency.

Three verified manual-QA defects on the G2.2 stack (base 0276a5d):

  A. Brand section layout breaks after a real Brand-name edit.
  B. Brand + Featured Collections visible/editable in Builder but ABSENT from
     the public storefront after Publish.
  C. The "Section Background" (نوع پس‌زمینه) control is a no-op.

Every test drives REAL production routes/services (Golden apply command, the
real section-settings mutation route, the real Publish service, the real
public storefront GET). Tests prove render/persist semantics, not merely that
JSON contains a key.
"""

import shutil
import tempfile
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.template.loader import render_to_string
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Brand, MerchantCollection
from apps.catalog.services.brand_service import update_brand
from apps.storefront_builder.models import StorefrontSection
from apps.storefront_builder import section_registry
from apps.storefront_builder.services import layout_service, render_service
from apps.stores.management.commands.seed_ready_template_fashion_demo import STORE_SLUG
from apps.stores.models import Store, StoreMembership

User = get_user_model()


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class _GoldenBase(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._mr = tempfile.mkdtemp()
        cls._ov = override_settings(MEDIA_ROOT=cls._mr)
        cls._ov.enable()

    @classmethod
    def tearDownClass(cls):
        cls._ov.disable()
        shutil.rmtree(cls._mr, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        cache.clear()
        call_command("apply_golden_reference_storefront", stdout=StringIO())
        self.store = Store.objects.get(slug=STORE_SLUG)
        self.user = User.objects.create_user(username="g23owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.user, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.host = f"{self.store.admin_subdomain}.rastisi.localhost"
        self.client = Client(HTTP_HOST=self.host)
        self.client.force_login(self.user)

    # -- helpers ---------------------------------------------------------

    def _draft_home(self):
        draft = layout_service.get_or_create_draft(self.store)
        return draft, draft.get_page("home")

    def _section(self, page, key):
        return page.sections.filter(section_key=key).first()

    def _settings_url(self, section):
        return reverse("dashboard:storefront-builder-section-settings", args=[section.pk])

    def _public_home_html(self):
        resp = self.client.get("/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        return resp.content.decode("utf-8")

    def _preview_home_html(self):
        resp = self.client.get(
            reverse("dashboard:storefront-builder-preview") + "?page=home", HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 200)
        return resp.content.decode("utf-8")


# =====================================================================
# DEFECT A — Brand section layout after a real Brand-name edit
# =====================================================================
class DefectABrandLayoutAfterEditTests(_GoldenBase):
    def _brand_item_html(self, home):
        """Render the brand section through the REAL production render
        pipeline (build_page_render_items -> responsive_section_wrapper),
        returning the section's rendered HTML."""
        items = render_service.build_page_render_items(home, self.store)
        item = next(i for i in items if i["section"].section_key == "brand_carousel")
        return item, render_to_string(
            "storefront_builder/partials/responsive_section_wrapper.html",
            {"item": item, "is_preview": True, "is_builder_preview": True},
        )

    def test_brand_edit_preserves_layout_class_contract(self):
        """A real Brand-name edit must NOT change the brand section's layout
        contract: the container class stays the same (carousel -> brand-carousel),
        the brand count is unchanged, and no brand is dropped."""
        _, home = self._draft_home()
        brand_sec = self._section(home, "brand_carousel")
        self.assertIsNotNone(brand_sec)

        before_item, before_html = self._brand_item_html(home)
        before_count = len(before_item["context"]["brands"])
        before_mode = before_item["context"]["brand_carousel_settings"]["display_mode"]
        self.assertGreater(before_count, 0)

        # Real content edit of a brand name.
        b = Brand.objects.filter(store=self.store, is_active=True).first()
        update_brand(b, name="برند ویرایش‌شده جدید")

        after_item, after_html = self._brand_item_html(home)
        self.assertEqual(len(after_item["context"]["brands"]), before_count, "brand count changed after a name edit")
        self.assertEqual(after_item["context"]["brand_carousel_settings"]["display_mode"], before_mode, "display_mode drifted after a name edit")

        # carousel display_mode must yield the horizontal-row container class.
        if before_mode == "carousel":
            self.assertIn("brand-carousel", after_html, "carousel brand section lost its .brand-carousel layout container")
        self.assertIn("برند ویرایش‌شده جدید", after_html)

    def test_brand_carousel_has_inline_horizontal_layout_fallback(self):
        """Defect A hardening: the carousel brand layout must not depend
        *solely* on the external home.css `.brand-carousel{display:flex}`
        rule (whose non-application in a reloaded Builder Preview iframe is
        the observed 'cards collapse into a narrow vertical column'). The
        grid branch already ships an inline `grid-template-columns` fallback;
        the carousel branch must ship an equivalent inline `display:flex`
        fallback so a horizontal row survives even if the stylesheet is
        momentarily unavailable."""
        _, home = self._draft_home()
        brand_sec = self._section(home, "brand_carousel")
        # Force carousel mode explicitly (the Golden default).
        brand_sec.settings = {**(brand_sec.settings or {}), "display_mode": "carousel"}
        brand_sec.save(update_fields=["settings"])
        item, _html = self._brand_item_html(home)
        section_html = render_to_string(
            "storefront_builder/sections/brand_carousel.html", item["context"],
        )
        # The carousel container must carry an inline flex fallback.
        self.assertIn("brand-carousel", section_html)
        self.assertIn("display:flex", section_html,
                      "carousel brand container has no inline horizontal-layout fallback (Defect A)")


# =====================================================================
# DEFECT B — Brand + Featured Collections round-trip Preview->Publish->Public
# =====================================================================
class DefectBBrandRoundTripTests(_GoldenBase):
    def test_brand_section_survives_publish_into_public(self):
        _, home = self._draft_home()
        brand_sec = self._section(home, "brand_carousel")
        self.assertIsNotNone(brand_sec, "Golden draft must have a brand_carousel section")

        # Preview shows the brand section content.
        preview = self._preview_home_html()
        self.assertIn('data-section-key="brand_carousel"', preview)

        # Edit a brand, then Publish through the real service.
        b = Brand.objects.filter(store=self.store, is_active=True).first()
        update_brand(b, name="برند منتشر")
        layout_service.publish(self.store)

        # Public must still render the brand section + the edited brand.
        public = self._public_home_html()
        self.assertIn("brand-carousel", public, "brand section absent from public after publish")
        self.assertIn("برند منتشر", public, "edited brand content absent from public after publish")


class DefectBFeaturedCollectionsRoundTripTests(_GoldenBase):
    def test_collection_tiles_survive_publish_into_public(self):
        _, home = self._draft_home()
        col_sec = self._section(home, "collection_tiles")
        self.assertIsNotNone(col_sec, "Golden draft must have a collection_tiles section")

        preview = self._preview_home_html()
        self.assertIn('data-section-key="collection_tiles"', preview)

        # Edit a collection name, then publish.
        c = MerchantCollection.objects.filter(store=self.store, is_active=True).first()
        self.assertIsNotNone(c)
        c.name = "کالکشن منتشر"
        c.save(update_fields=["name"])
        layout_service.publish(self.store)

        public = self._public_home_html()
        self.assertIn("کالکشن منتشر", public, "featured collection absent from public after publish")


# =====================================================================
# DEFECT C — Section Background control end-to-end
# =====================================================================
class DefectCSectionBackgroundTests(_GoldenBase):
    def _bg_section(self, home):
        # category_grid is background-aware and has a settings form.
        return self._section(home, "category_grid")

    def _post_settings(self, section, extra):
        base = {
            "title": (section.settings or {}).get("title", ""),
            "display_mode": (section.settings or {}).get("display_mode", "fashion_tiles"),
            "item_limit": (section.settings or {}).get("item_limit", 12),
            "motion_style": "none",
        }
        base.update(extra)
        return self.client.post(self._settings_url(section), base, HTTP_HOST=self.host)

    # 1. MUTATION / PERSISTENCE ----------------------------------------
    def test_palette_mode_persists_when_only_mode_selected(self):
        """A merchant selecting a palette background whose companion field is
        left at its natural default MUST persist as palette — not silently
        downgrade to theme (the observed 'nothing changes')."""
        _, home = self._draft_home()
        sec = self._bg_section(home)
        # The exact minimal payload a merchant produces by only changing the
        # background type to 'palette' (companion palette-role field left
        # unset / not touched).
        self._post_settings(sec, {"background_mode": "palette"})
        sec.refresh_from_db()
        self.assertEqual((sec.settings or {}).get("background", {}).get("mode"), "palette",
                         "palette selection silently downgraded to theme (Defect C)")

    def test_custom_color_mode_persists_when_only_mode_selected(self):
        _, home = self._draft_home()
        sec = self._bg_section(home)
        self._post_settings(sec, {"background_mode": "color"})
        sec.refresh_from_db()
        self.assertEqual((sec.settings or {}).get("background", {}).get("mode"), "color",
                         "custom-color selection silently downgraded to theme (Defect C)")

    # 2. PREVIEW RENDER ------------------------------------------------
    def test_palette_background_changes_preview_render(self):
        _, home = self._draft_home()
        sec = self._bg_section(home)
        self._post_settings(sec, {"background_mode": "palette", "background_palette_role": "tone-2"})
        preview = self._preview_home_html()
        self.assertIn('data-bg-mode="palette"', preview)
        self.assertIn('data-palette-role="tone-2"', preview)

    def test_color_mode_without_color_paints_no_background(self):
        """G2.3 review follow-up: selecting 'custom color' but never picking a
        colour must keep the mode (no silent theme downgrade) yet paint NO
        background — never a surprise hardcoded red. The wrapper only emits an
        inline background-color when a real colour is set."""
        _, home = self._draft_home()
        sec = self._bg_section(home)
        self._post_settings(sec, {"background_mode": "color"})
        sec.refresh_from_db()
        self.assertEqual((sec.settings or {}).get("background", {}).get("mode"), "color")
        self.assertEqual((sec.settings or {}).get("background", {}).get("color"), "")
        preview = self._preview_home_html()
        # No accidental red / no inline background-color painted for this section.
        self.assertNotIn("#F53247", preview)

    def test_palette_pattern_without_role_persists_with_default_role(self):
        """The empty-companion defaulting must apply to BOTH palette modes."""
        _, home = self._draft_home()
        sec = self._bg_section(home)
        self._post_settings(sec, {
            "background_mode": "palette_pattern",
            "background_pattern_slug": "commerce-doodle",
        })
        sec.refresh_from_db()
        bg = (sec.settings or {}).get("background", {})
        self.assertEqual(bg.get("mode"), "palette_pattern")
        self.assertEqual(bg.get("palette_role"), "tone-1")

    # 4. CUSTOM COLOR INDEPENDENCE -------------------------------------
    def test_custom_color_renders_independent_hex(self):
        _, home = self._draft_home()
        sec = self._bg_section(home)
        self._post_settings(sec, {"background_mode": "color", "background_color": "#123456"})
        sec.refresh_from_db()
        self.assertEqual((sec.settings or {}).get("background", {}).get("color"), "#123456")
        preview = self._preview_home_html()
        self.assertIn("#123456", preview)

    # 5. PUBLISH / PUBLIC ----------------------------------------------
    def test_background_survives_publish_into_public(self):
        _, home = self._draft_home()
        sec = self._bg_section(home)
        self._post_settings(sec, {"background_mode": "palette", "background_palette_role": "tone-3"})
        layout_service.publish(self.store)
        public = self._public_home_html()
        self.assertIn('data-bg-mode="palette"', public)
        self.assertIn('data-palette-role="tone-3"', public)

    # 6. INVALID INPUT --------------------------------------------------
    def test_invalid_palette_role_does_not_persist_bogus(self):
        _, home = self._draft_home()
        sec = self._bg_section(home)
        self._post_settings(sec, {"background_mode": "palette", "background_palette_role": "tone-99"})
        sec.refresh_from_db()
        bg = (sec.settings or {}).get("background", {})
        # Bogus role must never be stored; must not raise; safe fallback.
        self.assertNotEqual(bg.get("palette_role"), "tone-99")

    def test_malformed_color_rejected_safely(self):
        _, home = self._draft_home()
        sec = self._bg_section(home)
        before = (sec.settings or {}).get("background", {})
        resp = self._post_settings(sec, {"background_mode": "color", "background_color": "not-a-color"})
        sec.refresh_from_db()
        after = (sec.settings or {}).get("background", {})
        # Must not store a malformed color.
        self.assertNotEqual(after.get("color"), "not-a-color")

    # 7. TENANT ISOLATION ----------------------------------------------
    def test_background_change_is_store_scoped(self):
        # Store A change must not touch Store B's sections.
        other = Store.objects.create(
            name="فروشگاه دیگر", slug="g23-other-store", admin_subdomain="g23-other-store",
        )
        other_draft = layout_service.get_or_create_draft(other)
        other_home = other_draft.get_page("home")
        other_sec = other_home.sections.filter(section_key="category_grid").first()
        other_before = (other_sec.settings or {}).get("background") if other_sec else None

        _, home = self._draft_home()
        sec = self._bg_section(home)
        self._post_settings(sec, {"background_mode": "palette", "background_palette_role": "tone-1"})

        if other_sec:
            other_sec.refresh_from_db()
            self.assertEqual((other_sec.settings or {}).get("background"), other_before,
                             "changing store A background mutated store B")



# =====================================================================
# V06 / A06 — Brand tile CSS must live in the shared Builder stylesheet,
# not only in the Home-only home.css. The four non-Home public envelopes
# (product_list / product_detail / collection_detail / cart) load
# storefront_builder.css but NOT home.css, so a brand_carousel placed on
# any of them lacked all brand tile/logo sizing rules.
# =====================================================================
class BrandTileCssIsInSharedBuilderStylesheetTests(TestCase):
    """The Brand-tile presentation rules must be present in the shared
    ``storefront_builder.css`` (loaded by every V2 envelope), mirroring the
    Home-only ``home.css`` values, so a brand_carousel on a non-Home page is
    styled identically. Reads the real stylesheet source (not a computed
    style) — a static-asset contract, exactly like the base.html attribution
    source test in test_page_shell.py.
    """

    def _builder_css(self):
        from pathlib import Path

        from django.contrib.staticfiles import finders

        path = finders.find("css/storefront_builder.css")
        self.assertIsNotNone(path, "storefront_builder.css must be resolvable via staticfiles")
        return Path(path).read_text(encoding="utf-8")

    def _home_css(self):
        from pathlib import Path

        from django.contrib.staticfiles import finders

        path = finders.find("css/home.css")
        self.assertIsNotNone(path, "home.css must be resolvable via staticfiles")
        return Path(path).read_text(encoding="utf-8")

    def test_brand_tile_selectors_present_in_shared_builder_stylesheet(self):
        css = self._builder_css()
        # The five Brand-scoped selectors that previously lived ONLY in home.css.
        self.assertIn(".brand-tile", css, "brand tile base rule missing from storefront_builder.css")
        self.assertIn(".brand-tile img", css, "brand logo sizing rule missing from storefront_builder.css")
        self.assertIn(".brand-tile-name", css, "brand name-fallback rule missing from storefront_builder.css")
        self.assertIn(".brand-carousel", css, "brand carousel container rule missing from storefront_builder.css")
        self.assertIn(".brand-carousel .brand-tile", css, "brand carousel tile rule missing from storefront_builder.css")

    def test_brand_logo_max_height_matches_home_css(self):
        """The logo cap must mirror Home's EFFECTIVE (cascade-resolved) value so
        Home is unchanged and non-Home is fixed to the SAME sizing.

        home.css defines TWO .brand-tile img blocks of identical specificity: an
        early block (`max-height:40px`) and a later "dense" block
        (`max-height:48px`). On Home the dense block wins by source order, so the
        effective logo cap is 48px. Since storefront_builder.css loads AFTER
        home.css on the Home envelope, the shared sheet must carry 48px (the
        dense/effective value) — carrying 40px would OVERRIDE and shrink Home's
        logos, a regression. So we assert the effective value, not the first."""
        css = self._builder_css()
        # Effective Home value (dense block wins): `.brand-tile img{max-height:48px}`
        self.assertIn("max-height:48px", css)
        self.assertIn("object-fit:contain", css)
        # And it must NOT carry the stale first-block value that would change Home.
        self.assertNotIn("max-height:40px", css)

    def test_brand_shared_rules_are_noop_over_home_effective_cascade(self):
        """Home-unchanged guard. The shared sheet loads AFTER home.css on the
        Home envelope, so for every property both home.css blocks set, the shared
        value must equal Home's EFFECTIVE (dense-block, later-wins) value — making
        the override a NO-OP so Home stays pixel-identical. Verify the logo cap:
        the shared sheet mirrors home.css's DENSE block (48px), which is the value
        that actually governs Home."""
        css = self._builder_css()
        home = self._home_css()
        # home.css DENSE block (the one that wins on Home) sets 48px.
        self.assertIn(".brand-tile img{max-height:48px}", home)
        # The shared sheet must mirror that governing value, so overriding = no-op.
        self.assertIn("max-height:48px", css)
        # Effective dense values for the other both-set properties must also match.
        self.assertIn("min-height:72px", css)   # dense-only
        self.assertIn("border-radius:6px", css)  # dense wins over 12px
        self.assertIn("background:#fff", css)    # dense wins over var(--card)
        self.assertIn("gap:9px", css)            # dense wins over 14px
        self.assertIn("flex:0 0 150px", css)     # dense wins over 140px

    def test_home_css_brand_rules_are_not_deleted(self):
        """Regression guard: adding rules to the shared sheet must NOT remove
        the original Home-only rules (Home must stay byte-identical)."""
        home = self._home_css()
        self.assertIn(".brand-tile", home)
        self.assertIn(".brand-carousel", home)
        self.assertIn(".brand-tile img{max-height:40px", home)

    def test_brand_selectors_are_scoped_no_global_spill(self):
        """Every Brand rule added to the shared sheet must be anchored on a
        ``.brand-`` selector — no bare element/global selector spill."""
        css = self._builder_css()
        # Isolate the brand block we add (delimited by a stable marker comment).
        marker = "brand carousel/grid (shared with home.css"
        self.assertIn(marker, css, "expected a delimited, commented Brand block in storefront_builder.css")
        block = css.split(marker, 1)[1]
        # Take lines until the next top-level comment banner or EOF.
        lines = []
        for line in block.splitlines()[1:]:
            if line.strip().startswith("/* ===="):
                break
            lines.append(line)
        rule_lines = [ln.strip() for ln in lines if ln.strip() and "{" in ln]
        for rule in rule_lines:
            selector = rule.split("{", 1)[0].strip()
            self.assertIn("brand-", selector, f"non-brand-scoped selector leaked into Brand CSS block: {selector!r}")



# =====================================================================
# A06 — Brand presence + shared Builder stylesheet on a NON-Home public
# route. The four non-Home V2 envelopes load storefront_builder.css (not
# home.css); a brand_carousel placed on a non-Home page must render AND
# that page must serve storefront_builder.css so the (V06/A06) brand tile
# rules actually apply.
# =====================================================================
class BrandOnNonHomePublicRouteTests(_GoldenBase):
    def _first_product(self):
        from apps.catalog.models import Product

        return Product.objects.filter(store=self.store, status=Product.Status.ACTIVE).first()

    def test_brand_section_on_product_detail_renders_and_serves_builder_css(self):
        from apps.catalog.models import Brand

        product = self._first_product()
        self.assertIsNotNone(product, "golden store must have at least one active product")
        brand = Brand.objects.filter(store=self.store, is_active=True).first()
        self.assertIsNotNone(brand)

        draft = layout_service.get_or_create_draft(self.store)
        pdp_page = draft.get_page("product_detail")
        StorefrontSection.objects.create(
            page=pdp_page, section_key="brand_carousel", order=500,
            settings={"title": "برندهای صفحه محصول", "display_mode": "grid",
                      "brand_ids": [], "show_view_all": False},
        )
        layout_service.publish(self.store)

        resp = self.client.get(
            reverse("catalog:product-detail", args=[product.slug]), HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        # Brand section present on this non-Home public page.
        self.assertIn("برندهای صفحه محصول", body)
        self.assertIn("brand-tile", body)
        self.assertIn(f"?brand={brand.slug}", body)
        # And the page serves the shared Builder stylesheet (where the brand
        # tile CSS now lives) — NOT the Home-only home.css.
        self.assertIn("css/storefront_builder.css", body)
        self.assertNotIn("css/home.css", body)



# =====================================================================
# Task 5 (V06/A06 for Collection) — the collection-tiles CAROUSEL sizing
# rule must live in the shared Builder stylesheet, not only in the
# Home-only home.css. The four non-Home public envelopes (product_list /
# product_detail / collection_detail / cart) load storefront_builder.css
# but NOT home.css, so a collection_tiles section rendered in its
# ``carousel`` (tiles-carousel) variant on any of them lacked its
# per-tile flex-basis / scroll-snap sizing. (The grid variant is fine:
# ``.pcard``/``.grid``/``.g4`` already live in product_card.css.)
# =====================================================================
class CollectionCarouselCssIsInSharedBuilderStylesheetTests(TestCase):
    """The collection-tiles carousel tile-basis rules must be present in the
    shared ``storefront_builder.css`` (loaded by every non-Home V2 envelope),
    mirroring the Home-only ``home.css`` EFFECTIVE values, so a
    collection_tiles carousel on a non-Home page is sized identically. Reads
    the real stylesheet source (a static-asset contract), mirroring the Brand
    ``BrandTileCssIsInSharedBuilderStylesheetTests`` above.
    """

    def _builder_css(self):
        from pathlib import Path

        from django.contrib.staticfiles import finders

        path = finders.find("css/storefront_builder.css")
        self.assertIsNotNone(path, "storefront_builder.css must be resolvable via staticfiles")
        return Path(path).read_text(encoding="utf-8")

    def _home_css(self):
        from pathlib import Path

        from django.contrib.staticfiles import finders

        path = finders.find("css/home.css")
        self.assertIsNotNone(path, "home.css must be resolvable via staticfiles")
        return Path(path).read_text(encoding="utf-8")

    def test_collection_carousel_selector_present_in_shared_builder_stylesheet(self):
        css = self._builder_css()
        # The carousel tile-basis selector that previously lived ONLY in home.css.
        self.assertIn(
            ".collection-tiles-carousel.tiles-carousel .pcard", css,
            "collection carousel tile-basis rule missing from storefront_builder.css",
        )

    def test_collection_carousel_basis_matches_home_css_effective_value(self):
        """The shared sheet must mirror Home's EFFECTIVE (cascade-resolved)
        value so Home is unchanged and non-Home is fixed to the SAME sizing.

        home.css defines exactly ONE base block for this selector
        (`flex:0 0 220px;scroll-snap-align:start`) plus one responsive
        (`@media(max-width:680px){...flex-basis:180px}`) block — there is NO
        later overriding block of the same selector, so the effective values
        are those literal ones. Since storefront_builder.css loads AFTER
        home.css on the Home envelope, carrying these exact values makes the
        override a NO-OP (Home pixel-identical)."""
        css = self._builder_css()
        self.assertIn("flex:0 0 220px", css)
        self.assertIn("scroll-snap-align:start", css)
        # The responsive (<=680px) basis must also be mirrored.
        self.assertIn("flex-basis:180px", css)

    def test_collection_carousel_shared_rule_is_noop_over_home_effective_cascade(self):
        """Home-unchanged guard. The shared sheet loads AFTER home.css on the
        Home envelope; for the carousel tile-basis selector the shared value
        must equal Home's EFFECTIVE (there is a single governing block, so its
        literal value) — making the override a NO-OP so Home stays
        pixel-identical."""
        css = self._builder_css()
        home = self._home_css()
        # home.css's governing block for this selector (the value that wins on Home).
        self.assertIn(
            ".collection-tiles-carousel.tiles-carousel .pcard{flex:0 0 220px;scroll-snap-align:start}",
            home,
        )
        # The shared sheet must mirror that governing value, so overriding = no-op.
        self.assertIn("flex:0 0 220px", css)
        self.assertIn("scroll-snap-align:start", css)
        # And the responsive value home.css sets under max-width:680px.
        self.assertIn("flex-basis:180px", home)
        self.assertIn("flex-basis:180px", css)

    def test_home_css_collection_carousel_rule_is_not_deleted(self):
        """Regression guard: adding rules to the shared sheet must NOT remove
        the original Home-only rule (Home must stay byte-identical)."""
        home = self._home_css()
        self.assertIn(".collection-tiles-carousel.tiles-carousel .pcard{flex:0 0 220px", home)
        self.assertIn("flex-basis:180px", home)

    def test_collection_carousel_selectors_are_scoped_no_global_spill(self):
        """Every Collection carousel rule added to the shared sheet must be
        anchored on a ``.collection-tiles-carousel`` / ``.tiles-carousel``
        selector — no bare element/global selector spill onto ``.pcard``
        generally (the grid variant's ``.pcard`` sizing comes from
        product_card.css and must stay untouched)."""
        css = self._builder_css()
        marker = "collection tiles carousel (shared with home.css"
        self.assertIn(marker, css, "expected a delimited, commented Collection block in storefront_builder.css")
        block = css.split(marker, 1)[1]
        lines = []
        for line in block.splitlines()[1:]:
            if line.strip().startswith("/* ===="):
                break
            lines.append(line)
        rule_lines = [ln.strip() for ln in lines if ln.strip() and "{" in ln and not ln.strip().startswith("@")]
        for rule in rule_lines:
            selector = rule.split("{", 1)[0].strip()
            self.assertIn(
                "collection-tiles-carousel", selector,
                f"non-collection-scoped selector leaked into Collection CSS block: {selector!r}",
            )
