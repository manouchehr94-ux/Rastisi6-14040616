"""Phase 3 — Universal Storefront: V5 Golden Homepage.

Covers the Owner's explicit Phase 3 test checklist. These tests assert
against real rendered HTML/response data on the public (Published)
storefront and the staff-only (Draft) preview — the same dual-path
discipline every earlier phase's tests use — plus static-source checks
that make the "no V5-specific renderer" promise a permanent, enforced
invariant rather than a one-time claim in a report.

Deliberately NOT covered here (already has dedicated, passing coverage
elsewhere, per each area's own test file):
- row_key/row_span validation itself -> test_row_service.py
- background/spacing rendering mechanics -> test_phase2_universal_renderer.py
- section_registry shape/defaults -> test_section_registry.py
- preset import-time validation -> test_layout_preset_registry.py
- Draft/Preview vs Published header/footer discipline (generic) -> test_page_shell.py
"""

from io import BytesIO
from pathlib import Path

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from decimal import Decimal

from apps.catalog.models import Brand, Category, Product, Vendor
from apps.content.models import MediaAsset
from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder import section_registry
from apps.storefront_builder.models import StorefrontSection
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services import preset_service
from apps.stores.models import Store, StoreDomain

HOST = "sfb-phase3-v5.example.com"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _verified_domain(store, hostname):
    return StoreDomain.objects.create(
        store=store, hostname=hostname, is_primary=True,
        verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
    )


def _img(name="v5-test.png"):
    buf = BytesIO()
    Image.new("RGB", (10, 10), (20, 40, 60)).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


def _discounted_product(store):
    """Acceptance Batch 1 (post-U11) — the V5 preset's several
    ``product_section`` instances (``discounted``/``newest``/``most_viewed``
    data sources) are now hidden on the public/live storefront whenever
    they genuinely resolve to zero products (see
    ``render_service.hide_empty_public_sections``). A single active,
    discounted product satisfies all three data sources at once (an
    active product with ``discount_percent>0`` is also "newest" and
    "most_viewed"), so the tests below that check these titles actually
    render publicly need real data, not an empty store."""
    vendor = Vendor.objects.create(store=store, name="فروشنده V5", slug="v5-vendor")
    category = Category.objects.create(store=store, name="دسته V5", slug="v5-category")
    return Product.objects.create(
        store=store, vendor=vendor, category=category, name="کالای طلاییِ V5",
        slug="v5-golden-product", sku="SKU-V5-GOLDEN", price=Decimal("120000"),
        discount_percent=10, status=Product.Status.ACTIVE, stock=5,
    )


def _product(store, slug, *, discount_percent=0):
    vendor = Vendor.objects.create(store=store, name=f"فروشنده {slug}", slug=f"v-{slug}")
    category = Category.objects.create(store=store, name=f"دسته {slug}", slug=f"c-{slug}")
    return Product.objects.create(
        store=store, vendor=vendor, category=category, name=f"کالای {slug}", slug=slug,
        sku=f"SKU-{slug}", price=Decimal("10000"), status=Product.Status.ACTIVE,
        discount_percent=discount_percent, stock=5,
    )


class V5PresetIsPureDataTests(TestCase):
    """1 — V5 config contains no renderer/template selection at all."""

    def test_preset_definition_has_no_template_or_renderer_field(self):
        field_names = {f.name for f in lpr.dataclasses.fields(lpr.LayoutPresetDefinition)}
        self.assertNotIn("template", field_names)
        self.assertNotIn("template_name", field_names)
        self.assertNotIn("renderer", field_names)

    def test_preset_section_entries_reference_only_universal_section_keys(self):
        preset = lpr.get_layout_preset("v5_golden_homepage")
        for entry in preset.pages["home"]:
            self.assertTrue(section_registry.is_valid_section_key(entry.section_key))
            definition = section_registry.get_definition(entry.section_key)
            # Every template this preset can possibly reach lives under the
            # one shared "sections/" directory used by every other preset.
            self.assertTrue(definition.template_name.startswith("storefront_builder/sections/"))

    def test_v5_uses_normal_type_scale_for_readability(self):
        preset = lpr.get_layout_preset("v5_golden_homepage")
        self.assertEqual(preset.appearance["type_scale"], "normal")

    def test_v42_readability_change_does_not_mutate_clean_minimal_preset(self):
        preset = lpr.get_layout_preset("clean_minimal")
        self.assertEqual(preset.appearance["type_scale"], "compact")

    def test_product_card_keeps_quick_actions_outside_product_link(self):
        template_path = Path(__file__).resolve().parents[2] / "catalog" / "templates" / "catalog" / "partials" / "product_card.html"
        source = template_path.read_text(encoding="utf-8")
        self.assertIn('<article class="pcard ', source)
        self.assertIn('class="pcard-hitarea"', source)
        self.assertNotIn('<a class="pcard style-', source)
        self.assertIn('</a>\n  <div class="img"', source)

    def test_preset_settings_never_hardcode_a_tenant_specific_id(self):
        """Reference Safety — a global preset must never store a specific
        Store's category/brand/collection/product id."""
        suspicious_keys = {"category_ids", "brand_ids", "product_ids", "source_id", "collection_id"}
        preset = lpr.get_layout_preset("v5_golden_homepage")
        for entry in preset.pages["home"]:
            if not entry.settings:
                continue
            for key in suspicious_keys & entry.settings.keys():
                value = entry.settings[key]
                self.assertIn(value, ([], None), f"{entry.section_key}.{key} must stay empty in a global preset")

    def test_v3_reference_composition_uses_six_card_colored_rails_and_no_blog_or_brand_blocks(self):
        preset = lpr.get_layout_preset("v5_golden_homepage")
        entries = list(preset.pages["home"])
        section_keys = [entry.section_key for entry in entries]
        self.assertNotIn("blog_posts", section_keys)
        self.assertNotIn("brand_carousel", section_keys)

        patterned_rails = [
            entry for entry in entries
            if entry.section_key == "product_section"
            and (entry.settings or {}).get("background", {}).get("mode") == "palette_pattern"
        ]
        self.assertEqual(len(patterned_rails), 5)
        self.assertEqual(
            {entry.settings["background"]["pattern_slug"] for entry in patterned_rails},
            {"commerce-doodle"},
        )
        # Phase 3.8 moved the five reference colours into the global palette.
        # Preset data carries semantic roles so changing the Store palette can
        # recolour all rails without rewriting individual section settings.
        self.assertEqual(
            {entry.settings["background"]["palette_role"] for entry in patterned_rails},
            {"tone-1", "tone-2", "tone-3", "tone-4", "tone-5"},
        )
        self.assertTrue(all("color" not in entry.settings["background"] for entry in patterned_rails))
        for entry in patterned_rails:
            self.assertEqual(entry.settings["item_limit"], 6)
            self.assertEqual(entry.settings["responsive"]["desktop_columns"], 6)

    def test_v3_reference_composition_has_banner_pairs_strip_and_six_category_limit(self):
        preset = lpr.get_layout_preset("v5_golden_homepage")
        entries = list(preset.pages["home"])
        category = next(entry for entry in entries if entry.section_key == "category_grid")
        self.assertEqual(category.settings["display_mode"], "image_strip")
        # Phase 3.7 fidelity pass matches the approved reference's seven-item
        # category strip.
        self.assertEqual(category.settings["item_limit"], 7)

        self.assertTrue(any(block.get("type") == "tagline" for block in preset.header["extra_blocks"]))

        banners = [entry for entry in entries if entry.section_key == "multi_banner"]
        variants = [entry.settings.get("layout_variant") for entry in banners]
        self.assertIn("promo-4", variants)
        self.assertGreaterEqual(variants.count("wide-single"), 4)
        self.assertIn("mini-4", variants)
        self.assertIn("strip", variants)

    def test_v3_footer_is_dense_and_uses_existing_universal_footer_capabilities(self):
        preset = lpr.get_layout_preset("v5_golden_homepage")
        footer = preset.footer
        for key in (
            "show_about", "show_contact", "show_categories", "show_quick_links",
            "show_social", "show_trust_badges", "show_payment_logos", "show_copyright",
        ):
            self.assertTrue(footer[key], key)
        self.assertFalse(footer["show_newsletter"])
        self.assertTrue(any(block.get("type") == "custom_text" for block in footer["extra_blocks"]))


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class SameRendererPathAsGenericConfigTests(TestCase):
    """2/13 — the V5 preset renders through the exact same templates/partials
    as a hand-built generic layout; no store/preset-specific branching."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        _verified_domain(self.store, HOST)

    def _apply_v5_preset_and_publish(self):
        draft = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft, lpr.get_layout_preset("v5_golden_homepage"))
        svc.publish(self.store)

    def test_v5_preset_home_uses_home_visual_and_shared_partials(self):
        self._apply_v5_preset_and_publish()
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        template_names = {t.name for t in resp.templates if t.name}
        self.assertIn("catalog/home_visual.html", template_names)
        self.assertIn("storefront_builder/partials/page_shell_header.html", template_names)
        self.assertIn("storefront_builder/partials/page_shell_footer.html", template_names)
        self.assertIn("storefront_builder/partials/render_rows.html", template_names)
        # The one shared per-block wrapper, not a per-preset copy.
        self.assertIn("storefront_builder/partials/responsive_section_wrapper.html", template_names)

    def test_no_v5_specific_template_is_ever_loaded(self):
        self._apply_v5_preset_and_publish()
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        template_names = " ".join(t.name for t in resp.templates if t.name)
        for forbidden in ("v5_home", "beraito", "_v5.html", "_v5_"):
            self.assertNotIn(forbidden, template_names)

    def test_generic_manually_built_layout_uses_identical_template_set(self):
        """A hand-built, non-V5 layout must resolve through the exact same
        template names as the V5 preset — proving there is only ever one
        rendering path, never a second one selected by preset identity."""
        draft = svc.get_or_create_draft(self.store)
        draft.home_page().sections.all().delete()
        StorefrontSection.objects.create(page=draft.home_page(), section_key="hero_banner", order=0)
        StorefrontSection.objects.create(page=draft.home_page(), section_key="trust_features", order=1)
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        generic_templates = {t.name for t in resp.templates if t.name}

        self._apply_v5_preset_and_publish()
        resp2 = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        v5_templates = {t.name for t in resp2.templates if t.name}

        shared = {
            "catalog/home_visual.html",
            "storefront_builder/partials/page_shell_header.html",
            "storefront_builder/partials/page_shell_footer.html",
            "storefront_builder/partials/render_rows.html",
            "storefront_builder/partials/responsive_section_wrapper.html",
        }
        self.assertTrue(shared.issubset(generic_templates))
        self.assertTrue(shared.issubset(v5_templates))


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class HeroInstantOfferIndependentBlocksTests(TestCase):
    """Hero and Instant Offer remain independent Content Blocks.

    Legacy row_key/row_span metadata is preserved during the transition, while
    the actual public layout source of truth is Container -> Cell -> Section.
    """

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        _verified_domain(self.store, HOST)

    def test_hero_and_instant_offer_are_separate_sections_sharing_a_row(self):
        draft = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft, lpr.get_layout_preset("v5_golden_homepage"))
        home = draft.home_page()
        hero = home.sections.get(section_key="hero_banner")
        offer = home.sections.filter(section_key="product_section").order_by("order").first()
        self.assertEqual(hero.row_key, offer.row_key)
        self.assertNotEqual(hero.pk, offer.pk)
        self.assertEqual(hero.row_span, 9)
        self.assertEqual(offer.row_span, 3)
        self.assertTrue(offer.settings["carousel_autoplay"])
        self.assertEqual(offer.settings["header_position"], "inside")
        self.assertEqual(offer.settings["carousel_interval_ms"], 3500)

        # Container/Cell is now the visual layout source of truth. The
        # reference composition is 3/12 offer + 9/12 Hero.
        container = home.containers.get(layout_key="quarter_left")
        cells = list(container.cells.select_related("section").order_by("order", "id"))
        self.assertEqual([cell.span for cell in cells], [3, 9])
        self.assertEqual(cells[0].section_id, offer.pk)
        self.assertEqual(cells[1].section_id, hero.pk)

        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        html = resp.content.decode("utf-8")
        self.assertIn('data-layout="quarter_left"', html)
        self.assertIn("--cell-span:3", html)
        self.assertIn("--cell-span:9", html)
        self.assertNotIn("--row-span:", html)


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class RepeatedProductRailsAndCardStylesTests(TestCase):
    """3/4 — the V5 preset's several product_section instances each render
    their own real content (the PER_INSTANCE_SECTION_KEYS fix), and
    distinct per-instance card styles remain data-driven."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        _verified_domain(self.store, HOST)

    def test_repeated_product_rails_show_distinct_titles(self):
        # Acceptance Batch 1 (post-U11): these titles all belong to
        # data-driven product_section instances (discounted/newest/
        # most_viewed) — a real product is required for any of them to
        # render at all now that a genuinely empty one is hidden on the
        # public storefront (see ``_discounted_product``'s docstring).
        _discounted_product(self.store)
        draft = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft, lpr.get_layout_preset("v5_golden_homepage"))
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        html = resp.content.decode("utf-8")
        for title in ("پیشنهاد لحظه‌ای", "پرفروش‌ترین‌های هفته", "پیشنهادهای منتخب", "محبوب‌ترین انتخاب‌ها", "محبوب‌های فروشگاه"):
            self.assertIn(title, html)

    def test_two_product_section_instances_keep_independent_card_settings(self):
        _product(self.store, "p3-card-a")
        _product(self.store, "p3-card-b")
        draft = svc.get_or_create_draft(self.store)
        home = draft.home_page()
        home.sections.all().delete()
        StorefrontSection.objects.create(
            page=home, section_key="product_section", order=0,
            settings={
                "data_source": "newest", "item_limit": 2, "display_mode": "grid",
                "card": {"image_ratio": "portrait"},
            },
        )
        StorefrontSection.objects.create(
            page=home, section_key="product_section", order=1,
            settings={
                "data_source": "newest", "item_limit": 2, "display_mode": "grid",
                "card": {"image_ratio": "landscape"},
            },
        )
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        html = resp.content.decode("utf-8")
        self.assertIn("ratio-portrait", html)
        self.assertIn("ratio-landscape", html)


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class MegaMenuDataDrivenTests(TestCase):
    """Mega menu capability extension — real Category Tree, multi-column
    child links, optional promo image; never hardcoded categories."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        _verified_domain(self.store, HOST)
        # The mega menu lives in the Universal shell (home_visual.html);
        # without a Published version, catalog:home falls back to the
        # legacy pre-Universal template, which has no mega menu at all.
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)

    def test_mega_menu_renders_real_category_tree_with_promo_image(self):
        parent = Category.objects.create(store=self.store, name="Mega Parent", slug="mega-parent")
        parent.image.save("promo.png", _img(), save=True)
        for i in range(8):
            Category.objects.create(store=self.store, name=f"Mega Child {i}", slug=f"mega-child-{i}", parent=parent)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        html = resp.content.decode("utf-8")
        self.assertIn("cat-mega-rail-item", html)
        self.assertIn("Mega Parent", html)
        self.assertIn("Mega Child 0", html)
        self.assertIn("cat-mega-cols cols-2", html)  # >6 children -> two columns
        self.assertIn("cat-mega-promo", html)

    def test_mega_menu_never_shows_another_stores_categories(self):
        other = Store.objects.create(name="فروشگاه ب", slug="p3-mega-other", admin_subdomain="p3-mega-other")
        Category.objects.create(store=other, name="Foreign Category", slug="foreign-cat")
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertNotContains(resp, "Foreign Category")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class TenantSafeDataAndNoLeakageTests(TestCase):
    """8/9 (checklist) — tenant-safe data end to end for every Phase 3
    addition: category_grid circular mode, brand_carousel, blog_posts
    (platform-wide model, still must not mix store context), amazing_offers."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        _verified_domain(self.store, HOST)

    def _publish_home_with(self, sections):
        draft = svc.get_or_create_draft(self.store)
        home = draft.home_page()
        home.sections.all().delete()
        for order, kwargs in enumerate(sections):
            StorefrontSection.objects.create(page=home, order=order, **kwargs)
        svc.publish(self.store)

    def test_circular_category_grid_shows_only_own_store_categories(self):
        own = Category.objects.create(store=self.store, name="Own Cat", slug="own-cat")
        other = Store.objects.create(name="فروشگاه ج", slug="p3-catgrid-other", admin_subdomain="p3-catgrid-other")
        Category.objects.create(store=other, name="Foreign Cat", slug="foreign-cat-2")
        self._publish_home_with([
            {"section_key": "category_grid", "settings": {
                "title": "", "display_mode": "circular", "category_ids": [own.pk],
            }},
        ])
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        html = resp.content.decode("utf-8")
        self.assertIn("tile-circle", html)
        self.assertIn("Own Cat", html)
        self.assertNotIn("Foreign Cat", html)

    def test_brand_carousel_shows_only_own_store_brands(self):
        own = Brand.objects.create(store=self.store, name="Own Brand", slug="own-brand")
        other = Store.objects.create(name="فروشگاه د", slug="p3-brand-other", admin_subdomain="p3-brand-other")
        Brand.objects.create(store=other, name="Foreign Brand", slug="foreign-brand")
        self._publish_home_with([
            {"section_key": "brand_carousel", "settings": {
                "title": "", "display_mode": "grid", "show_view_all": False, "brand_ids": [own.pk],
            }},
        ])
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        html = resp.content.decode("utf-8")
        self.assertIn("Own Brand", html)
        self.assertNotIn("Foreign Brand", html)

    def test_amazing_offers_never_shows_another_stores_products(self):
        other = Store.objects.create(name="فروشگاه ه", slug="p3-spotlight-other", admin_subdomain="p3-spotlight-other")
        foreign_product = _product(other, "foreign-discount", discount_percent=50)
        self._publish_home_with([
            {"section_key": "amazing_offers", "settings": {"item_limit": 4, "deadline_hours": 8, "title": ""}},
        ])
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertNotContains(resp, foreign_product.name)

    def test_foreign_store_background_media_never_renders_in_v5_rail(self):
        other = Store.objects.create(name="فروشگاه و", slug="p3-bg-other", admin_subdomain="p3-bg-other")
        foreign_asset = MediaAsset.objects.create(store=other, image=_img())
        self._publish_home_with([
            {"section_key": "product_section", "settings": {
                "data_source": "newest", "item_limit": 2, "display_mode": "grid",
                "background": {"mode": "image", "media_asset_id": foreign_asset.pk},
            }},
        ])
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        html = resp.content.decode("utf-8")
        self.assertNotIn("background-image:url(", html)


class BlogPostsPlatformWideButRenderedSafelyTests(TestCase):
    """Blog — genuinely new, deliberately simple block; BlogPost is a
    pre-existing platform-wide model (no store FK), verify it renders real
    data without crashing and respects item_limit."""

    @override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
    def test_blog_posts_respects_item_limit(self):
        from apps.blog.models import BlogPost

        cache.clear()
        store = _akhlaghi()
        _verified_domain(store, HOST)
        for i in range(4):
            BlogPost.objects.create(title=f"Post {i}", slug=f"p3-post-{i}", body="x", published_at=timezone.now())
        draft = svc.get_or_create_draft(store)
        home = draft.home_page()
        home.sections.all().delete()
        StorefrontSection.objects.create(
            page=home, section_key="blog_posts", order=0, settings={"item_limit": 3, "title": ""},
        )
        svc.publish(store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        html = resp.content.decode("utf-8")
        self.assertEqual(html.count("blog-card"), 3)


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class PublicUsesPublishedPreviewUsesDraftTests(TestCase):
    """10 — applying the V5 preset to a Draft must never affect the public
    (Published) storefront until publish() is explicitly called; preview
    must reflect the Draft immediately."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        _verified_domain(self.store, HOST)
        StorefrontSection.objects.create(
            page=svc.get_or_create_draft(self.store).home_page(),
            section_key="trust_features", order=0,
        )
        svc.publish(self.store)

    def test_applying_v5_preset_to_draft_does_not_change_public_page_before_publish(self):
        resp_before = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertNotContains(resp_before, "پیشنهاد لحظه‌ای")

        draft = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft, lpr.get_layout_preset("v5_golden_homepage"))

        resp_after = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertNotContains(resp_after, "پیشنهاد لحظه‌ای")

    def test_publishing_v5_preset_makes_it_appear_publicly(self):
        # Acceptance Batch 1 (post-U11): "پیشنهاد لحظه‌ای" is a
        # data_source="discounted" product_section — a real discounted
        # product is required for it to render at all on the public
        # storefront now that a genuinely empty data section is hidden
        # there (see ``_discounted_product``'s docstring).
        _discounted_product(self.store)
        draft = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft, lpr.get_layout_preset("v5_golden_homepage"))
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertContains(resp, "پیشنهاد لحظه‌ای")


class NoStorePresetSpecificRendererBranchingTests(TestCase):
    """13 — static-source guardrail: the render pipeline and section
    registry must never branch on a preset key, store slug/id, or contain
    a captured-V5 renderer/template reference. Enforced permanently, not
    just claimed in a report."""

    def _read(self, relative_path):
        import pathlib

        base = pathlib.Path(__file__).resolve().parent.parent
        return (base / relative_path).read_text(encoding="utf-8")

    def test_render_service_has_no_preset_or_v5_or_family_branching(self):
        source = self._read("services/render_service.py")
        for forbidden in ('preset.key ==', 'preset ==', "== 'v5'", '== "v5"', "family_slug ==", "store.slug ==", "store.id ==", "beraito"):
            self.assertNotIn(forbidden, source)

    def test_section_registry_has_no_preset_or_v5_or_family_branching(self):
        source = self._read("section_registry.py")
        for forbidden in ('preset.key ==', 'preset ==', "== 'v5'", '== "v5"', "family_slug ==", "beraito"):
            self.assertNotIn(forbidden, source)

    def test_no_v5_or_beraito_renderer_module_exists(self):
        import pathlib

        base = pathlib.Path(__file__).resolve().parent.parent
        forbidden_files = ["beraito_renderer.py", "v5_renderer.py", "v5_home.html"]
        for name in forbidden_files:
            matches = list(base.rglob(name))
            self.assertEqual(matches, [], f"forbidden renderer file exists: {matches}")

    def test_production_templates_never_reference_docs_references_path(self):
        import pathlib

        base = pathlib.Path(__file__).resolve().parent.parent / "templates"
        for path in base.rglob("*.html"):
            content = path.read_text(encoding="utf-8")
            self.assertNotIn("docs/references", content, path)
