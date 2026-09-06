import dataclasses
import inspect
import re

from django.test import TestCase

from apps.storefront_builder import section_registry as section_registry_module
from apps.storefront_builder import variant_contract as variant_contract_module
from apps.storefront_builder.models import StorefrontPage
from apps.storefront_builder.section_registry import (
    ALL_PAGE_TYPES,
    BACKGROUND_AWARE_SECTION_KEYS,
    BACKGROUND_MODE_CHOICES,
    CARD_AWARE_SECTION_KEYS,
    COLUMN_AWARE_SECTION_KEYS,
    COLUMN_VISUAL_SECTION_KEYS,
    CONTENT_WIDTH_CHOICES,
    DESTINATION_AWARE_SECTION_KEYS,
    HEIGHT_CHOICES,
    IMAGE_RATIO_CHOICES,
    QUICK_ADD_REVEAL_CHOICES,
    LAYOUT_HEIGHT_AWARE_SECTION_KEYS,
    LAYOUT_WIDTH_AWARE_SECTION_KEYS,
    MOTION_AWARE_SECTION_KEYS,
    MOTION_CHOICES,
    MULTI_BANNER_KNOWN_LAYOUT_VARIANTS,
    PAGE_TYPE_CART,
    PAGE_TYPE_COLLECTION,
    PAGE_TYPE_HOME,
    PAGE_TYPE_LISTING,
    PAGE_TYPE_PRODUCT_DETAIL,
    PAGE_TYPE_SEARCH,
    PRODUCT_SECTION_DISPLAY_MODES,
    SECTION_LIBRARY_CATEGORIES,
    SECTION_REGISTRY,
    SPACING_AWARE_SECTION_KEYS,
    SPACING_SIZE_CHOICES,
    BackgroundSettingsError,
    CardSettingsError,
    DestinationSettingsError,
    LayoutSettingsError,
    MotionSettingsError,
    NewsletterSettingsError,
    ProductSectionSettingsError,
    ResponsiveSettingsError,
    SectionDefinition,
    SpacingSettingsError,
    UnknownSectionTypeError,
    default_background_settings,
    default_card_settings,
    default_destination_settings,
    default_layout_settings,
    default_motion_settings,
    default_responsive_settings,
    default_spacing_settings,
    get_definition,
    is_section_allowed_on_page,
    is_valid_section_key,
    list_definitions,
    list_library_groups,
    validate_background_settings,
    validate_card_settings,
    validate_destination_settings,
    validate_layout_settings,
    validate_motion_settings,
    validate_responsive_settings,
    validate_spacing_settings,
)
from apps.storefront_builder.variant_contract import (
    ENGINE_SCHEMA_VERSION,
    SECTION_VARIANT_RENDERER_NAMESPACE,
    SUPPORTED_ENGINE_SCHEMA_VERSIONS,
    InvalidVariantDefinitionError,
    UnsupportedEngineSchemaVersionError,
    VariantDefinition,
    build_template_provenance,
    get_variant,
    list_variants,
    resolve_active_variant,
    resolve_capabilities,
    resolve_motion_defaults,
    resolve_renderer_template,
    resolve_required_data,
    resolve_responsive_defaults,
    resolve_supported_settings,
    validate_template_provenance,
    validate_variant_definition,
    validate_variants,
)

EXPECTED_KEYS = {
    "announcement_bar", "hero_banner", "image_slider", "single_banner",
    "multi_banner", "category_grid", "featured_products", "newest_products",
    "best_sellers", "discounted_products", "amazing_offers", "brand_carousel",
    "promo_cards", "rich_text", "image_text", "product_section", "trust_features",
    "collection_tiles", "quick_links", "faq", "testimonials", "video_section",
    # story_rail is a deliberate, intentional addition (Phase 5 Family
    # Implementation checkpoint) — dedicated coverage already exists in
    # test_shared_capabilities.py::StoryRailSectionTests (registered,
    # definition attributes, family-default wiring) and this file's own
    # SectionRegistryTests already exercises story_rail indirectly via
    # list_definitions()/ResponsiveIntegrationAcrossRegistryTests. This
    # fixture was simply never updated when story_rail was added.
    "story_rail",
    # newsletter — Phase 3 (Home page reusable blocks), dedicated coverage
    # in test_views.py::NewsletterSectionTests and apps.content's own
    # NewsletterSubscriber/subscribe_to_newsletter/view tests.
    "newsletter",
    # Phase 5 — context-aware product_detail-only section types, dedicated
    # coverage in test_render_service.py/test_page_shell.py.
    "product_main", "product_description", "product_video", "related_products",
    # Phase 5 — context-aware listing+search section type.
    "product_listing",
    # Phase 5 — context-aware collection-only section types.
    "collection_header", "collection_products",
    # Phase 5 — context-aware cart-only section types.
    "cart_items", "cart_summary",
    # Phase 3 (Universal Storefront — V5 Golden Homepage) — genuinely new,
    # deliberately simple "Blog" block (no existing block covered this
    # role in the V5→Universal Block mapping); dedicated coverage in
    # test_phase3_v5_golden.py.
    "blog_posts",
    # Site-target-overhaul Part 2B (ibolak Home rebuild) — a self-contained
    # campaign hero, deliberately independent of the shared HeroSlide model
    # ``hero_banner``/``image_slider`` read from; dedicated coverage in
    # test_u10_ready_template_catalog.py::FashionPromoCatalogIsolationTests.
    "fashion_lifestyle_hero",
    # Site-target-overhaul Part 2D (ibolak final Home fidelity pass) — the
    # generic, ID-free, multi-row merchandising wall; dedicated coverage in
    # test_u10_ready_template_catalog.py::FashionPromoCatalogIsolationTests
    # and test_render_service.py::CatalogProductWallContextTests.
    "catalog_product_wall",
}


class SectionRegistryTests(TestCase):
    def test_all_required_keys_registered(self):
        self.assertEqual(set(SECTION_REGISTRY.keys()), EXPECTED_KEYS)

    def test_get_definition_valid(self):
        definition = get_definition("hero_banner")
        self.assertEqual(definition.key, "hero_banner")
        self.assertTrue(definition.template_name.startswith("storefront_builder/sections/"))

    def test_get_definition_unknown_key_rejected(self):
        with self.assertRaises(UnknownSectionTypeError):
            get_definition("<script>alert(1)</script>")

    def test_get_definition_unknown_key_never_returns_template(self):
        """A bogus key must never resolve to any template path."""
        try:
            get_definition("not_a_real_section")
        except UnknownSectionTypeError as exc:
            self.assertIn("not_a_real_section", str(exc))
        else:
            self.fail("expected UnknownSectionTypeError")

    def test_is_valid_section_key(self):
        self.assertTrue(is_valid_section_key("category_grid"))
        self.assertFalse(is_valid_section_key("totally_made_up"))

    def test_list_definitions_matches_registry_size(self):
        self.assertEqual(len(list_definitions()), len(SECTION_REGISTRY))

    def test_singleton_sections_capped_at_one(self):
        # hero_banner دیگر singleton نیست (چکپوینتِ اسلایدرِ اصلی) — یک
        # مرچنت باید بتواند چند نمونه‌ی مستقل از اسلایدر داشته باشد.
        for key in ("announcement_bar", "trust_features"):
            definition = get_definition(key)
            self.assertEqual(definition.max_instances, 1)
            self.assertFalse(definition.duplicable)

    def test_hero_banner_is_now_duplicable(self):
        """اسلایدر اصلی باید بتواند چند نمونه‌ی مستقل (با اسلایدهای
        متفاوت) داشته باشد — نگاه کنید به ``HeroSlide.section``."""
        definition = get_definition("hero_banner")
        self.assertTrue(definition.duplicable)
        self.assertIsNone(definition.max_instances)

    def test_announcement_bar_is_hidden_from_add_section_library(self):
        """چکپوینتِ ۹: نوارِ اعلانِ section (متنِ سخت‌کدشده، بدونِ تنظیماتِ
        واقعی) با تنظیماتِ نوارِ اعلانِ هدر (متن/فعال‌بودنِ واقعاً
        قابل‌تنظیم) هم‌پوشانی داشت — امکانِ ساختِ نمونه‌ی *جدید* از این
        نوع پنهان شده تا مرچنت به‌جایش از تنظیماتِ هدر استفاده کند؛
        نمونه‌های قدیمیِ موجود هم‌چنان کاملاً کار می‌کنند (تغییر نکرده)."""
        definition = get_definition("announcement_bar")
        self.assertTrue(definition.hidden_from_library)
        self.assertTrue(definition.removable)
        # منطقِ render/validate/default دست‌نخورده مانده — فقط از کتابخانه پنهان است
        self.assertEqual(definition.validate_settings({"foo": "bar"})["foo"], "bar")

    def test_most_sections_are_not_hidden_from_library(self):
        definitions = list_definitions()
        visible = [d for d in definitions if not d.hidden_from_library]
        self.assertGreater(len(visible), len(definitions) - 2)

    def test_every_registered_definition_has_a_valid_library_category(self):
        for definition in list_definitions():
            self.assertIn(
                definition.category_fa, SECTION_LIBRARY_CATEGORIES,
                f"{definition.key} has an unregistered category_fa: {definition.category_fa!r}",
            )

    def test_library_groups_cover_every_visible_definition_exactly_once(self):
        groups = list_library_groups()
        category_names = [name for name, _members in groups]
        self.assertEqual(category_names, sorted(category_names, key=SECTION_LIBRARY_CATEGORIES.index))

        seen_keys = []
        for _category, members in groups:
            seen_keys.extend(d.key for d in members)
        visible_keys = {d.key for d in list_definitions() if not d.hidden_from_library}
        self.assertEqual(set(seen_keys), visible_keys)
        self.assertEqual(len(seen_keys), len(set(seen_keys)))  # هیچ کلیدی دوبار ظاهر نمی‌شود

    def test_library_groups_never_include_hidden_types(self):
        groups = list_library_groups()
        all_keys = {d.key for _category, members in groups for d in members}
        self.assertNotIn("announcement_bar", all_keys)

    def test_library_groups_never_render_an_empty_category(self):
        for _category, members in list_library_groups():
            self.assertGreater(len(members), 0)

    def test_validate_settings_rejects_non_dict(self):
        definition = get_definition("announcement_bar")
        with self.assertRaises(ValueError):
            definition.validate_settings("not a dict")

    def test_validate_settings_accepts_dict(self):
        """از فازِ D به بعد، خروجیِ هر validate_settings همیشه یک بلوکِ
        ``responsive`` پیش‌فرض (نمایان همه‌جا) هم دارد — بدونِ تغییرِ
        رفتارِ خودِ منطقِ passthrough."""
        definition = get_definition("announcement_bar")
        result = definition.validate_settings({"foo": "bar"})
        self.assertEqual(result["foo"], "bar")
        self.assertEqual(result["responsive"], {
            "hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False,
        })


class ProductSectionSettingsTests(TestCase):
    def setUp(self):
        self.definition = get_definition("product_section")

    def _validate(self, **overrides):
        raw = {"data_source": "newest"} | overrides
        return self.definition.validate_settings(raw)

    def test_defaults_are_already_valid(self):
        cleaned = self.definition.validate_settings(self.definition.default_settings())
        self.assertEqual(cleaned["data_source"], "newest")

    def test_rejects_unknown_data_source(self):
        with self.assertRaises(ProductSectionSettingsError):
            self._validate(data_source="totally_made_up")

    def test_rejects_missing_data_source(self):
        with self.assertRaises(ProductSectionSettingsError):
            self.definition.validate_settings({})

    def test_display_mode_falls_back_to_carousel_on_invalid_value(self):
        cleaned = self._validate(display_mode="not_a_mode")
        self.assertEqual(cleaned["display_mode"], "carousel")

    def test_display_mode_grid_is_accepted(self):
        cleaned = self._validate(display_mode="grid")
        self.assertEqual(cleaned["display_mode"], "grid")

    def test_display_mode_campaign_band_is_accepted(self):
        cleaned = self._validate(display_mode="campaign_band")
        self.assertEqual(cleaned["display_mode"], "campaign_band")

    def test_product_section_registered_variants_match_closed_display_modes(self):
        self.assertEqual(
            {variant.key for variant in self.definition.variants},
            set(PRODUCT_SECTION_DISPLAY_MODES),
        )

    def test_item_limit_clamped_to_safe_range(self):
        self.assertEqual(self._validate(item_limit=0)["item_limit"], 2)
        self.assertEqual(self._validate(item_limit=999)["item_limit"], 24)
        self.assertEqual(self._validate(item_limit=8)["item_limit"], 8)

    def test_item_limit_non_numeric_rejected(self):
        with self.assertRaises(ProductSectionSettingsError):
            self._validate(item_limit="abc")

    def test_carousel_behavior_defaults_are_backward_compatible(self):
        cleaned = self._validate()
        self.assertFalse(cleaned["carousel_autoplay"])
        self.assertEqual(cleaned["carousel_interval_ms"], 3500)
        self.assertTrue(cleaned["carousel_show_arrows"])
        self.assertEqual(cleaned["header_position"], "above")

    def test_carousel_behavior_is_validated_and_clamped(self):
        cleaned = self._validate(
            carousel_autoplay=True, carousel_interval_ms=99999,
            carousel_show_arrows=False, header_position="inside",
        )
        self.assertTrue(cleaned["carousel_autoplay"])
        self.assertEqual(cleaned["carousel_interval_ms"], 10000)
        self.assertFalse(cleaned["carousel_show_arrows"])
        self.assertEqual(cleaned["header_position"], "inside")

    def test_invalid_carousel_interval_is_rejected(self):
        with self.assertRaises(ProductSectionSettingsError):
            self._validate(carousel_interval_ms="fast")

    def test_title_and_subtitle_trimmed_and_capped(self):
        cleaned = self._validate(title="  عنوان  ", subtitle="  زیرعنوان  ")
        self.assertEqual(cleaned["title"], "عنوان")
        self.assertEqual(cleaned["subtitle"], "زیرعنوان")
        long_title = "الف" * 200
        cleaned = self._validate(title=long_title)
        self.assertEqual(len(cleaned["title"]), 60)

    def test_collection_requires_source_id(self):
        with self.assertRaises(ProductSectionSettingsError):
            self._validate(data_source="collection")

    def test_collection_accepts_positive_source_id(self):
        cleaned = self._validate(data_source="collection", source_id=5)
        self.assertEqual(cleaned["source_id"], 5)
        self.assertEqual(cleaned["product_ids"], [])

    def test_collection_rejects_non_positive_source_id(self):
        with self.assertRaises(ProductSectionSettingsError):
            self._validate(data_source="collection", source_id=0)
        with self.assertRaises(ProductSectionSettingsError):
            self._validate(data_source="collection", source_id=-3)

    def test_category_and_brand_also_require_source_id(self):
        for source in ("category", "brand"):
            with self.assertRaises(ProductSectionSettingsError):
                self._validate(data_source=source)
            cleaned = self._validate(data_source=source, source_id=1)
            self.assertEqual(cleaned["source_id"], 1)

    def test_algorithmic_sources_ignore_source_id(self):
        for source in ("newest", "discounted", "best_sellers", "most_viewed"):
            cleaned = self._validate(data_source=source, source_id=999)
            self.assertIsNone(cleaned["source_id"])

    def test_manual_requires_at_least_one_product(self):
        with self.assertRaises(ProductSectionSettingsError):
            self._validate(data_source="manual", product_ids=[])

    def test_manual_deduplicates_and_preserves_order(self):
        cleaned = self._validate(data_source="manual", product_ids=[5, 3, 5, 7])
        self.assertEqual(cleaned["product_ids"], [5, 3, 7])
        self.assertIsNone(cleaned["source_id"])

    def test_manual_drops_non_positive_ids(self):
        cleaned = self._validate(data_source="manual", product_ids=[0, -1, 4])
        self.assertEqual(cleaned["product_ids"], [4])

    def test_manual_product_ids_capped(self):
        cleaned = self._validate(data_source="manual", product_ids=list(range(1, 200)))
        self.assertEqual(len(cleaned["product_ids"]), 60)

    def test_non_manual_source_ignores_product_ids(self):
        cleaned = self._validate(data_source="newest", product_ids=[1, 2, 3])
        self.assertEqual(cleaned["product_ids"], [])

    def test_show_view_all_defaults_true(self):
        self.assertTrue(self._validate()["show_view_all"])

    def test_show_view_all_accepts_false(self):
        self.assertFalse(self._validate(show_view_all=False)["show_view_all"])


    def test_valid_card_styles_accepted(self):
        for style in ("standard", "compact", "minimal"):
            self.assertEqual(validate_card_settings({"card_style": style})["card_style"], style)

    def test_unknown_card_style_falls_back_to_standard(self):
        self.assertEqual(validate_card_settings({"card_style": "v5-only"})["card_style"], "standard")

    def test_non_dict_rejected(self):
        with self.assertRaises(ProductSectionSettingsError):
            self.definition.validate_settings("not a dict")

    def test_unknown_keys_silently_dropped(self):
        cleaned = self._validate(evil_field="<script>")
        self.assertNotIn("evil_field", cleaned)


class CategoryGridSettingsTests(TestCase):
    def setUp(self):
        self.definition = get_definition("category_grid")

    def test_defaults_when_empty(self):
        cleaned = self.definition.validate_settings({})
        self.assertEqual(cleaned["category_ids"], [])
        self.assertEqual(cleaned["display_mode"], "grid")
        self.assertEqual(cleaned["title"], "")

    def test_non_dict_rejected(self):
        with self.assertRaises(ValueError):
            self.definition.validate_settings("not a dict")

    def test_category_ids_deduplicated_preserving_order(self):
        cleaned = self.definition.validate_settings({"category_ids": [5, 3, 5, 3, 8]})
        self.assertEqual(cleaned["category_ids"], [5, 3, 8])

    def test_non_positive_ids_dropped(self):
        cleaned = self.definition.validate_settings({"category_ids": [0, -1, 4]})
        self.assertEqual(cleaned["category_ids"], [4])

    def test_invalid_display_mode_falls_back_to_grid(self):
        cleaned = self.definition.validate_settings({"display_mode": "not-a-real-mode"})
        self.assertEqual(cleaned["display_mode"], "grid")

    def test_carousel_display_mode_accepted(self):
        cleaned = self.definition.validate_settings({"display_mode": "carousel"})
        self.assertEqual(cleaned["display_mode"], "carousel")

    def test_image_strip_display_mode_accepted(self):
        cleaned = self.definition.validate_settings({"display_mode": "image_strip"})
        self.assertEqual(cleaned["display_mode"], "image_strip")

    def test_item_limit_defaults_and_clamps_for_dense_or_sparse_compositions(self):
        self.assertEqual(self.definition.validate_settings({})["item_limit"], 12)
        self.assertEqual(self.definition.validate_settings({"item_limit": 1})["item_limit"], 2)
        self.assertEqual(self.definition.validate_settings({"item_limit": 6})["item_limit"], 6)
        self.assertEqual(self.definition.validate_settings({"item_limit": 99})["item_limit"], 12)

    def test_non_numeric_item_limit_rejected(self):
        with self.assertRaises(ValueError):
            self.definition.validate_settings({"item_limit": "many"})

    def test_title_trimmed_and_capped(self):
        cleaned = self.definition.validate_settings({"title": "  " + ("ط" * 100) + "  "})
        self.assertEqual(len(cleaned["title"]), 60)
        self.assertFalse(cleaned["title"].startswith(" "))

    def test_category_grid_is_per_instance_duplicable(self):
        self.assertTrue(self.definition.duplicable)
        self.assertIsNone(self.definition.max_instances)


class BrandCarouselSettingsTests(TestCase):
    def setUp(self):
        self.definition = get_definition("brand_carousel")

    def test_defaults_when_empty(self):
        cleaned = self.definition.validate_settings({})
        self.assertEqual(cleaned["brand_ids"], [])
        self.assertEqual(cleaned["display_mode"], "grid")
        self.assertFalse(cleaned["show_view_all"])
        # عضوِ DESTINATION_AWARE_SECTION_KEYS است — بلوکِ destination هم باید حاضر باشد
        self.assertEqual(cleaned["destination"]["destination_type"], "none")

    def test_non_dict_rejected(self):
        with self.assertRaises(ValueError):
            self.definition.validate_settings("not a dict")

    def test_brand_ids_deduplicated_preserving_order(self):
        cleaned = self.definition.validate_settings({"brand_ids": [7, 2, 7]})
        self.assertEqual(cleaned["brand_ids"], [7, 2])

    def test_show_view_all_accepts_true(self):
        cleaned = self.definition.validate_settings({"show_view_all": True})
        self.assertTrue(cleaned["show_view_all"])

    def test_brand_carousel_is_per_instance_duplicable(self):
        self.assertTrue(self.definition.duplicable)
        self.assertIsNone(self.definition.max_instances)


class CollectionTilesSettingsTests(TestCase):
    def setUp(self):
        self.definition = get_definition("collection_tiles")

    def test_defaults_when_empty(self):
        cleaned = self.definition.validate_settings({})
        self.assertEqual(cleaned["collection_ids"], [])
        self.assertEqual(cleaned["title"], "")

    def test_non_dict_rejected(self):
        with self.assertRaises(ValueError):
            self.definition.validate_settings("not a dict")

    def test_collection_ids_deduplicated_preserving_order(self):
        cleaned = self.definition.validate_settings({"collection_ids": [9, 1, 9]})
        self.assertEqual(cleaned["collection_ids"], [9, 1])

    def test_duplicable_and_unbounded(self):
        self.assertTrue(self.definition.duplicable)
        self.assertIsNone(self.definition.max_instances)


class QuickLinksSettingsTests(TestCase):
    def setUp(self):
        self.definition = get_definition("quick_links")

    def test_defaults_when_empty(self):
        cleaned = self.definition.validate_settings({})
        self.assertIsNone(cleaned["menu_id"])
        self.assertEqual(cleaned["title"], "")

    def test_non_dict_rejected(self):
        with self.assertRaises(ValueError):
            self.definition.validate_settings("not a dict")

    def test_menu_id_accepted(self):
        cleaned = self.definition.validate_settings({"menu_id": 7})
        self.assertEqual(cleaned["menu_id"], 7)

    def test_non_positive_menu_id_becomes_none(self):
        cleaned = self.definition.validate_settings({"menu_id": -3})
        self.assertIsNone(cleaned["menu_id"])

    def test_invalid_menu_id_rejected(self):
        with self.assertRaises(ValueError):
            self.definition.validate_settings({"menu_id": "not-a-number"})


class FaqSettingsTests(TestCase):
    def setUp(self):
        self.definition = get_definition("faq")

    def test_defaults_when_empty(self):
        cleaned = self.definition.validate_settings({})
        self.assertEqual(cleaned["items"], [])
        self.assertEqual(cleaned["title"], "سوالات متداول")

    def test_non_dict_rejected(self):
        with self.assertRaises(ValueError):
            self.definition.validate_settings("not a dict")

    def test_items_with_both_fields_kept(self):
        cleaned = self.definition.validate_settings({"items": [{"question": "س", "answer": "پ"}]})
        self.assertEqual(cleaned["items"], [{"question": "س", "answer": "پ"}])

    def test_items_missing_a_field_dropped(self):
        cleaned = self.definition.validate_settings({"items": [{"question": "س", "answer": ""}]})
        self.assertEqual(cleaned["items"], [])

    def test_non_list_items_rejected(self):
        with self.assertRaises(ValueError):
            self.definition.validate_settings({"items": "not a list"})

    def test_items_capped_at_twenty(self):
        raw_items = [{"question": f"س{i}", "answer": f"پ{i}"} for i in range(30)]
        cleaned = self.definition.validate_settings({"items": raw_items})
        self.assertEqual(len(cleaned["items"]), 20)


class TestimonialsSettingsTests(TestCase):
    def setUp(self):
        self.definition = get_definition("testimonials")

    def test_defaults_when_empty(self):
        cleaned = self.definition.validate_settings({})
        self.assertEqual(cleaned["items"], [])
        self.assertEqual(cleaned["title"], "نظرات مشتریان")

    def test_items_requires_name_and_quote_role_optional(self):
        cleaned = self.definition.validate_settings({"items": [{"name": "علی", "quote": "عالی بود", "role": ""}]})
        self.assertEqual(cleaned["items"], [{"name": "علی", "quote": "عالی بود", "role": ""}])

    def test_items_missing_quote_dropped(self):
        cleaned = self.definition.validate_settings({"items": [{"name": "علی", "quote": ""}]})
        self.assertEqual(cleaned["items"], [])


class VideoSectionSettingsTests(TestCase):
    def setUp(self):
        self.definition = get_definition("video_section")

    def test_defaults_when_empty(self):
        cleaned = self.definition.validate_settings({})
        self.assertEqual(cleaned["video_url"], "")

    def test_non_dict_rejected(self):
        with self.assertRaises(ValueError):
            self.definition.validate_settings("not a dict")

    def test_valid_youtube_url_accepted(self):
        cleaned = self.definition.validate_settings({"video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})
        self.assertIn("youtube.com", cleaned["video_url"])

    def test_unrecognized_url_rejected(self):
        with self.assertRaises(ValueError):
            self.definition.validate_settings({"video_url": "https://example.com/not-a-video"})

    def test_dangerous_scheme_rejected(self):
        with self.assertRaises(ValueError):
            self.definition.validate_settings({"video_url": "javascript:alert(1)//youtube.com/watch?v=dQw4w9WgXcQ"})

    def test_empty_url_allowed_not_configured_yet(self):
        cleaned = self.definition.validate_settings({"video_url": ""})
        self.assertEqual(cleaned["video_url"], "")


class ResponsiveSettingsContractTests(TestCase):
    """اعتبارسنجیِ خودِ ``validate_responsive_settings`` — تابعِ مشترکِ
    فازِ D، مستقل از این‌که کدام نوعِ section از آن استفاده می‌کند."""

    def test_none_input_means_fully_visible_defaults(self):
        cleaned = validate_responsive_settings(None, supports_columns=False)
        self.assertEqual(cleaned, {"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False})

    def test_default_responsive_settings_matches_none_input(self):
        self.assertEqual(
            default_responsive_settings(supports_columns=False),
            validate_responsive_settings(None, supports_columns=False),
        )

    def test_non_dict_rejected(self):
        with self.assertRaises(ResponsiveSettingsError):
            validate_responsive_settings("not a dict", supports_columns=False)

    def test_booleans_strictly_normalized(self):
        cleaned = validate_responsive_settings(
            {"hide_on_desktop": 1, "hide_on_tablet": 0, "hide_on_mobile": "yes"}, supports_columns=False,
        )
        self.assertEqual(cleaned, {"hide_on_desktop": True, "hide_on_tablet": False, "hide_on_mobile": True})

    def test_unknown_keys_silently_dropped(self):
        cleaned = validate_responsive_settings({"hide_on_desktop": True, "evil": "<script>"}, supports_columns=False)
        self.assertNotIn("evil", cleaned)

    def test_columns_absent_when_not_supported(self):
        cleaned = validate_responsive_settings({"desktop_columns": 3}, supports_columns=False)
        self.assertNotIn("desktop_columns", cleaned)

    def test_columns_default_when_supported(self):
        cleaned = validate_responsive_settings(None, supports_columns=True)
        self.assertEqual(cleaned["desktop_columns"], 4)
        self.assertEqual(cleaned["tablet_columns"], 3)
        self.assertEqual(cleaned["mobile_columns"], 2)

    def test_columns_accept_closed_choices(self):
        cleaned = validate_responsive_settings(
            {"desktop_columns": 6, "tablet_columns": 1, "mobile_columns": 1}, supports_columns=True,
        )
        self.assertEqual(cleaned["desktop_columns"], 6)
        self.assertEqual(cleaned["tablet_columns"], 1)
        self.assertEqual(cleaned["mobile_columns"], 1)

    def test_columns_reject_out_of_range_values(self):
        with self.assertRaises(ResponsiveSettingsError):
            validate_responsive_settings({"desktop_columns": 7}, supports_columns=True)
        with self.assertRaises(ResponsiveSettingsError):
            validate_responsive_settings({"tablet_columns": 4}, supports_columns=True)
        with self.assertRaises(ResponsiveSettingsError):
            validate_responsive_settings({"mobile_columns": 3}, supports_columns=True)

    def test_columns_reject_non_numeric(self):
        with self.assertRaises(ResponsiveSettingsError):
            validate_responsive_settings({"desktop_columns": "abc"}, supports_columns=True)

    def test_columns_reject_zero_and_negative(self):
        with self.assertRaises(ResponsiveSettingsError):
            validate_responsive_settings({"mobile_columns": 0}, supports_columns=True)
        with self.assertRaises(ResponsiveSettingsError):
            validate_responsive_settings({"desktop_columns": -1}, supports_columns=True)


class ResponsiveIntegrationAcrossRegistryTests(TestCase):
    """هر ۱۷ تعریفِ Section Registry باید بلوکِ responsive را پشتیبانی
    کند — نه فقط product_section."""

    def test_every_definition_default_settings_has_responsive_block(self):
        for definition in list_definitions():
            defaults = definition.default_settings()
            self.assertIn("responsive", defaults, definition.key)
            self.assertEqual(defaults["responsive"]["hide_on_desktop"], False, definition.key)

    def test_every_definition_has_settings_form(self):
        for definition in list_definitions():
            self.assertTrue(definition.has_settings_form, definition.key)

    def test_column_aware_keys_get_column_defaults(self):
        for key in COLUMN_AWARE_SECTION_KEYS:
            defaults = get_definition(key).default_settings()
            self.assertIn("desktop_columns", defaults["responsive"], key)

    def test_non_column_aware_keys_have_no_column_fields(self):
        for key, definition in SECTION_REGISTRY.items():
            if key in COLUMN_AWARE_SECTION_KEYS:
                continue
            defaults = definition.default_settings()
            self.assertNotIn("desktop_columns", defaults["responsive"], key)

    def test_existing_settings_without_responsive_key_still_validate(self):
        """سکشن‌هایِ از‌قبل‌موجود که هرگز از این فرم عبور نکرده‌اند —
        شبیه‌سازیِ ذخیره‌ی مجددِ تنظیماتِ فعلی‌شان بدونِ کلیدِ
        responsive نباید کرش کند و باید پیش‌فرضِ نمایان‌همه‌جا بدهد."""
        definition = get_definition("hero_banner")
        cleaned = definition.validate_settings({})
        self.assertEqual(cleaned["responsive"]["hide_on_desktop"], False)

    def test_product_section_non_dict_still_raises_typed_error(self):
        """اطمینان از این‌که پوششِ responsive نوعِ خطایِ اختصاصیِ
        product_section را با یک ValueError عمومی جایگزین نکرده."""
        definition = get_definition("product_section")
        with self.assertRaises(ProductSectionSettingsError):
            definition.validate_settings("not a dict")


class DestinationSettingsTests(TestCase):
    """قراردادِ مشترکِ بلوکِ ``destination`` — چکپوینتِ استانداردسازیِ لینک."""

    def test_default_is_no_destination(self):
        self.assertEqual(default_destination_settings(), {
            "destination_type": "none",
            "destination_id": None,
            "destination_external_url": "",
            "open_in_new_tab": False,
        })

    def test_none_type_ignores_extra_fields(self):
        cleaned = validate_destination_settings({"destination_type": "none", "destination_id": 5})
        self.assertEqual(cleaned["destination_type"], "none")
        self.assertIsNone(cleaned["destination_id"])

    def test_category_requires_positive_id(self):
        with self.assertRaises(DestinationSettingsError):
            validate_destination_settings({"destination_type": "category", "destination_id": None})
        with self.assertRaises(DestinationSettingsError):
            validate_destination_settings({"destination_type": "category", "destination_id": -1})

    def test_category_accepts_positive_id(self):
        cleaned = validate_destination_settings({"destination_type": "category", "destination_id": "7"})
        self.assertEqual(cleaned["destination_id"], 7)

    def test_collection_type_accepted(self):
        cleaned = validate_destination_settings({"destination_type": "collection", "destination_id": 3})
        self.assertEqual(cleaned["destination_type"], "collection")
        self.assertEqual(cleaned["destination_id"], 3)

    def test_external_requires_safe_url(self):
        with self.assertRaises(DestinationSettingsError):
            validate_destination_settings({"destination_type": "external", "destination_external_url": "javascript:alert(1)"})
        cleaned = validate_destination_settings({"destination_type": "external", "destination_external_url": "https://example.com"})
        self.assertEqual(cleaned["destination_external_url"], "https://example.com")

    def test_unknown_type_rejected(self):
        with self.assertRaises(DestinationSettingsError):
            validate_destination_settings({"destination_type": "not-a-real-type"})

    def test_search_type_accepted_and_needs_no_id(self):
        cleaned = validate_destination_settings({"destination_type": "search"})
        self.assertEqual(cleaned["destination_type"], "search")
        self.assertIsNone(cleaned["destination_id"])

    def test_cart_type_accepted_and_needs_no_id(self):
        cleaned = validate_destination_settings({"destination_type": "cart"})
        self.assertEqual(cleaned["destination_type"], "cart")
        self.assertIsNone(cleaned["destination_id"])

    def test_none_raw_defaults(self):
        self.assertEqual(validate_destination_settings(None), default_destination_settings())

    def test_non_dict_rejected(self):
        with self.assertRaises(DestinationSettingsError):
            validate_destination_settings("nope")

    def test_open_in_new_tab_coerced_bool(self):
        cleaned = validate_destination_settings({"destination_type": "none", "open_in_new_tab": 1})
        self.assertIs(cleaned["open_in_new_tab"], True)


class DestinationAwareIntegrationTests(TestCase):
    def test_destination_aware_keys_get_destination_defaults(self):
        for key in DESTINATION_AWARE_SECTION_KEYS:
            defaults = get_definition(key).default_settings()
            self.assertIn("destination", defaults, key)
            self.assertEqual(defaults["destination"]["destination_type"], "none", key)

    def test_non_destination_aware_keys_have_no_destination_field(self):
        for key, definition in SECTION_REGISTRY.items():
            if key in DESTINATION_AWARE_SECTION_KEYS:
                continue
            defaults = definition.default_settings()
            self.assertNotIn("destination", defaults, key)

    def test_existing_settings_without_destination_key_still_validate(self):
        definition = get_definition("image_text")
        cleaned = definition.validate_settings({"title": "hi"})
        self.assertEqual(cleaned["destination"]["destination_type"], "none")

    def test_product_section_destination_round_trips(self):
        definition = get_definition("product_section")
        cleaned = definition.validate_settings({
            "data_source": "newest",
            "destination": {"destination_type": "collection", "destination_id": 4},
        })
        self.assertEqual(cleaned["destination"]["destination_type"], "collection")
        self.assertEqual(cleaned["destination"]["destination_id"], 4)


class MotionSettingsTests(TestCase):
    """Phase 3 (کتابخانه‌ی بلوک‌های صفحه اصلی) — بلوکِ مشترکِ «حرکت»."""

    def test_default_is_none(self):
        self.assertEqual(default_motion_settings(), {"style": "none"})

    def test_none_raw_defaults(self):
        self.assertEqual(validate_motion_settings(None), default_motion_settings())

    def test_valid_styles_accepted(self):
        for style in MOTION_CHOICES:
            self.assertEqual(validate_motion_settings({"style": style}), {"style": style})

    def test_unknown_style_falls_back_to_none(self):
        """برخلافِ destination (که خطا می‌دهد)، سبکِ نامعتبر بی‌صدا به
        none بازمی‌گردد — یک جلوه‌ی صرفاً بصری هرگز نباید کلِ فرمِ
        ذخیره‌سازی را رد کند."""
        self.assertEqual(validate_motion_settings({"style": "not-a-real-style"}), {"style": "none"})

    def test_non_dict_rejected(self):
        with self.assertRaises(MotionSettingsError):
            validate_motion_settings("nope")


class MotionAwareIntegrationTests(TestCase):
    def test_motion_aware_keys_get_motion_defaults(self):
        for key in MOTION_AWARE_SECTION_KEYS:
            defaults = get_definition(key).default_settings()
            self.assertIn("motion", defaults, key)
            self.assertEqual(defaults["motion"]["style"], "none", key)

    def test_non_motion_aware_keys_have_no_motion_field(self):
        for key, definition in SECTION_REGISTRY.items():
            if key in MOTION_AWARE_SECTION_KEYS:
                continue
            defaults = definition.default_settings()
            self.assertNotIn("motion", defaults, key)

    def test_existing_settings_without_motion_key_still_validate(self):
        definition = get_definition("category_grid")
        cleaned = definition.validate_settings({"title": "hi"})
        self.assertEqual(cleaned["motion"]["style"], "none")

    def test_motion_round_trips(self):
        definition = get_definition("hero_banner")
        cleaned = definition.validate_settings({"motion": {"style": "fade"}})
        self.assertEqual(cleaned["motion"]["style"], "fade")


class MultiBannerColumnLayoutTests(TestCase):
    """Phase 3 — ``multi_banner`` از ``COLUMN_AWARE`` به ``COLUMN_VISUAL``
    منتقل شد (چیدمانِ گریدِ واقعی، نگاه کنید به multi_banner.html)."""

    def test_multi_banner_is_column_aware_and_visual(self):
        self.assertIn("multi_banner", COLUMN_AWARE_SECTION_KEYS)
        self.assertIn("multi_banner", COLUMN_VISUAL_SECTION_KEYS)

    def test_other_previously_static_types_remain_non_visual(self):
        for key in ("category_grid", "promo_cards", "brand_carousel"):
            self.assertIn(key, COLUMN_AWARE_SECTION_KEYS)
            self.assertNotIn(key, COLUMN_VISUAL_SECTION_KEYS)


class CardSettingsTests(TestCase):
    """Phase 8 P0-2 — بلوکِ مشترکِ «ظاهرِ کارتِ محصول»."""

    def test_default_shows_everything_square(self):
        defaults = default_card_settings()
        self.assertEqual(defaults, {
            "show_brand": True, "show_price": True, "show_badge": True,
            "show_wishlist": True, "show_quick_add": True, "show_rating": True, "card_border": True,
            "image_ratio": "square", "quick_add_reveal": "hover_slide", "card_style": "standard",
        })

    def test_none_raw_defaults(self):
        self.assertEqual(validate_card_settings(None), default_card_settings())

    def test_explicit_false_toggles_are_respected(self):
        cleaned = validate_card_settings({
            "show_brand": False, "show_price": False, "show_badge": False,
            "show_wishlist": False, "show_quick_add": False, "show_rating": False, "card_border": False,
        })
        for key in ("show_brand", "show_price", "show_badge", "show_wishlist", "show_quick_add", "show_rating", "card_border"):
            self.assertFalse(cleaned[key], key)

    def test_valid_image_ratios_accepted(self):
        for ratio in IMAGE_RATIO_CHOICES:
            self.assertEqual(validate_card_settings({"image_ratio": ratio})["image_ratio"], ratio)

    def test_unknown_image_ratio_falls_back_to_square(self):
        self.assertEqual(validate_card_settings({"image_ratio": "circle"})["image_ratio"], "square")

    def test_valid_quick_add_reveal_modes_accepted(self):
        for mode in QUICK_ADD_REVEAL_CHOICES:
            self.assertEqual(validate_card_settings({"quick_add_reveal": mode})["quick_add_reveal"], mode)

    def test_unknown_quick_add_reveal_falls_back_to_hover_slide(self):
        self.assertEqual(validate_card_settings({"quick_add_reveal": "bounce"})["quick_add_reveal"], "hover_slide")

    def test_non_dict_rejected(self):
        with self.assertRaises(CardSettingsError):
            validate_card_settings("nope")


class CardAwareIntegrationTests(TestCase):
    def test_card_aware_keys_get_card_defaults(self):
        for key in CARD_AWARE_SECTION_KEYS:
            defaults = get_definition(key).default_settings()
            self.assertIn("card", defaults, key)
            self.assertEqual(defaults["card"], default_card_settings(), key)

    def test_non_card_aware_keys_have_no_card_field(self):
        for key, definition in SECTION_REGISTRY.items():
            if key in CARD_AWARE_SECTION_KEYS:
                continue
            defaults = definition.default_settings()
            self.assertNotIn("card", defaults, key)

    def test_card_round_trips(self):
        definition = get_definition("product_section")
        cleaned = definition.validate_settings({
            "data_source": "newest", "card": {"show_brand": False, "image_ratio": "portrait"},
        })
        self.assertFalse(cleaned["card"]["show_brand"])
        self.assertEqual(cleaned["card"]["image_ratio"], "portrait")

    def test_unknown_card_awareness_types_are_the_expected_nine(self):
        """طبقِ برنامه‌ی پیاده‌سازیِ فاز ۸ — همان ۸ نوعی که واقعاً کارتِ
        محصول رندر می‌کنند (به‌علاوه‌ی amazing_offers)."""
        self.assertEqual(CARD_AWARE_SECTION_KEYS, frozenset({
            "product_section", "featured_products", "newest_products", "best_sellers",
            "discounted_products", "amazing_offers", "related_products", "product_listing",
            "collection_products",
            # Part 2D — catalog_product_wall's per-group rows render real
            # product cards too (see its own SectionDefinition comment).
            "catalog_product_wall",
        }))


class Phase8ColumnExpansionTests(TestCase):
    """Phase 8 P0-2 — کنترلِ «تعدادِ ستون‌ها» از ۲ نوع به ۸ نوعِ محصولی
    گسترش یافت؛ سه نوعِ غیرِمحصولیِ قبلی (category_grid/promo_cards/
    brand_carousel) عمداً دست‌نخورده باقی می‌مانند (نگاه کنید به
    MultiBannerColumnLayoutTests بالا)."""

    def test_all_eight_product_listing_types_are_column_visual(self):
        expected = {
            "product_section", "multi_banner", "featured_products", "newest_products",
            "best_sellers", "discounted_products", "related_products", "collection_products",
            "product_listing",
            # Part 2D — catalog_product_wall's rows use the same
            # .rsec-cols mechanism as product_section.
            "catalog_product_wall",
        }
        self.assertEqual(expected, COLUMN_VISUAL_SECTION_KEYS)
        for key in expected:
            self.assertIn(key, COLUMN_AWARE_SECTION_KEYS, key)


class LayoutSettingsTests(TestCase):
    """Phase 8 P0-5 — بلوکِ مشترکِ «اندازه‌ی بخش» (عرض/ارتفاع)."""

    def test_default_is_standard(self):
        self.assertEqual(
            default_layout_settings(supports_height=True),
            {"content_width": "standard", "height": "standard"},
        )
        self.assertEqual(
            default_layout_settings(supports_height=False),
            {"content_width": "standard"},
        )

    def test_none_raw_defaults(self):
        self.assertEqual(validate_layout_settings(None, supports_height=True), default_layout_settings(supports_height=True))

    def test_valid_widths_accepted(self):
        for width in CONTENT_WIDTH_CHOICES:
            self.assertEqual(
                validate_layout_settings({"content_width": width}, supports_height=False)["content_width"], width,
            )

    def test_valid_heights_accepted(self):
        for height in HEIGHT_CHOICES:
            self.assertEqual(
                validate_layout_settings({"height": height}, supports_height=True)["height"], height,
            )

    def test_unknown_width_falls_back_to_standard(self):
        self.assertEqual(
            validate_layout_settings({"content_width": "huge"}, supports_height=False)["content_width"], "standard",
        )

    def test_height_absent_when_not_supported(self):
        cleaned = validate_layout_settings({"height": "tall"}, supports_height=False)
        self.assertNotIn("height", cleaned)

    def test_non_dict_rejected(self):
        with self.assertRaises(LayoutSettingsError):
            validate_layout_settings("nope", supports_height=True)


class LayoutAwareIntegrationTests(TestCase):
    def test_width_aware_keys_get_layout_defaults(self):
        for key in LAYOUT_WIDTH_AWARE_SECTION_KEYS:
            defaults = get_definition(key).default_settings()
            self.assertIn("layout", defaults, key)
            self.assertEqual(defaults["layout"]["content_width"], "standard", key)
            self.assertEqual("height" in defaults["layout"], key in LAYOUT_HEIGHT_AWARE_SECTION_KEYS, key)

    def test_non_width_aware_keys_have_no_layout_field(self):
        for key, definition in SECTION_REGISTRY.items():
            if key in LAYOUT_WIDTH_AWARE_SECTION_KEYS:
                continue
            defaults = definition.default_settings()
            self.assertNotIn("layout", defaults, key)

    def test_height_only_aware_for_hero_and_slider(self):
        self.assertEqual(LAYOUT_HEIGHT_AWARE_SECTION_KEYS, frozenset({"hero_banner", "image_slider"}))
        self.assertTrue(LAYOUT_HEIGHT_AWARE_SECTION_KEYS.issubset(LAYOUT_WIDTH_AWARE_SECTION_KEYS))

    def test_layout_round_trips(self):
        definition = get_definition("image_text")
        cleaned = definition.validate_settings({"layout": {"content_width": "full"}})
        self.assertEqual(cleaned["layout"]["content_width"], "full")
        self.assertNotIn("height", cleaned["layout"])


class BackgroundSettingsTests(TestCase):
    """spec §9 (Background System) + §10.2 (Custom Color Overrides)."""

    def test_missing_key_defaults_to_theme(self):
        cleaned = validate_background_settings(None)
        self.assertEqual(cleaned, default_background_settings())
        self.assertEqual(cleaned["mode"], "theme")

    def test_valid_color_mode(self):
        cleaned = validate_background_settings({"mode": "color", "color": "#E62B35"})
        self.assertEqual(cleaned["mode"], "color")
        self.assertEqual(cleaned["color"], "#E62B35")

    def test_invalid_hex_color_rejected(self):
        with self.assertRaises(BackgroundSettingsError):
            validate_background_settings({"mode": "color", "color": "not-a-color"})

    def test_color_mode_without_color_keeps_mode_but_leaves_color_empty(self):
        """G2.3 (Defect C) — a VALID ``color`` selection with an empty color
        field must NOT silently downgrade to ``theme`` (that was the observed
        "I change نوع پس‌زمینه but nothing happens" bug): the merchant's
        explicit "custom color" mode is honoured. The color itself stays
        EMPTY (no hardcoded fallback hex) so the wrapper paints nothing until
        the merchant picks a colour — the mode is remembered, but no
        unwanted/off-palette background is applied. Malformed colours are
        still rejected (see ``test_invalid_hex_color_rejected``)."""
        cleaned = validate_background_settings({"mode": "color", "color": ""})
        self.assertEqual(cleaned["mode"], "color")
        self.assertEqual(cleaned["color"], "")

    def test_valid_image_mode_stores_media_asset_id_not_a_url(self):
        """Phase 1 correction (tenant safety): تنظیماتِ خامِ mode=image فقط
        یک شناسه‌ی عددیِ اشاره‌گر به MediaAsset را می‌پذیرد، هرگز یک رشته‌ی
        URL دلخواه را — حلِ مالکیتِ Store در
        ``apps.content.services.resolve_background_media_url`` است، نه اینجا."""
        cleaned = validate_background_settings({"mode": "image", "media_asset_id": 42})
        self.assertEqual(cleaned["mode"], "image")
        self.assertEqual(cleaned["media_asset_id"], 42)
        self.assertNotIn("image_url", cleaned)

    def test_image_mode_without_media_asset_id_falls_back_to_theme(self):
        cleaned = validate_background_settings({"mode": "image"})
        self.assertEqual(cleaned["mode"], "theme")
        self.assertIsNone(cleaned["media_asset_id"])

    def test_non_integer_media_asset_id_rejected(self):
        with self.assertRaises(BackgroundSettingsError):
            validate_background_settings({"mode": "image", "media_asset_id": "not-a-number"})

    def test_non_positive_media_asset_id_rejected(self):
        with self.assertRaises(BackgroundSettingsError):
            validate_background_settings({"mode": "image", "media_asset_id": 0})

    def test_arbitrary_url_in_media_asset_id_field_rejected(self):
        """طبقِ تصمیمِ ایمنیِ مستأجر: حتی اگر مرچنت/کلاینتِ مخرب سعی کند یک
        رشته‌ی URL را در همان کلید پاس بدهد، به‌عنوانِ شناسه‌ی نامعتبر رد
        می‌شود — نه اینکه بی‌صدا به‌عنوانِ URL پذیرفته شود."""
        with self.assertRaises(BackgroundSettingsError):
            validate_background_settings({"mode": "image", "media_asset_id": "https://evil.example.com/x.jpg"})

    def test_registered_pattern_is_preserved_and_unknown_pattern_falls_back(self):
        cleaned = validate_background_settings({"mode": "pattern", "pattern_slug": "commerce-doodle", "color": "#F53247"})
        self.assertEqual(cleaned["mode"], "pattern")
        self.assertEqual(cleaned["pattern_slug"], "commerce-doodle")
        self.assertEqual(cleaned["color"], "#F53247")

        unknown = validate_background_settings({"mode": "pattern", "pattern_slug": "stationery"})
        self.assertEqual(unknown["mode"], "theme")
        self.assertEqual(unknown["pattern_slug"], "")

    def test_pattern_color_uses_same_hex_validation_as_solid_background(self):
        with self.assertRaises(BackgroundSettingsError):
            validate_background_settings({"mode": "pattern", "pattern_slug": "commerce-doodle", "color": "red"})

    def test_unknown_mode_falls_back_to_theme(self):
        cleaned = validate_background_settings({"mode": "not-a-real-mode"})
        self.assertEqual(cleaned["mode"], "theme")

    def test_non_dict_rejected(self):
        with self.assertRaises(BackgroundSettingsError):
            validate_background_settings("nope")


class BackgroundAwareIntegrationTests(TestCase):
    def test_background_aware_keys_get_background_defaults(self):
        for key in BACKGROUND_AWARE_SECTION_KEYS:
            defaults = get_definition(key).default_settings()
            self.assertIn("background", defaults, key)
            self.assertEqual(defaults["background"]["mode"], "theme", key)

    def test_non_background_aware_keys_have_no_background_field(self):
        for key, definition in SECTION_REGISTRY.items():
            if key in BACKGROUND_AWARE_SECTION_KEYS:
                continue
            defaults = definition.default_settings()
            self.assertNotIn("background", defaults, key)

    def test_protected_context_sections_excluded(self):
        """spec §59 — sectionهایِ حیاتیِ محافظت‌شده (خرید/سبد/لیست) عمداً
        از override پس‌زمینه کنار گذاشته شده‌اند."""
        protected = {"product_main", "product_listing", "cart_items", "cart_summary", "collection_products"}
        self.assertTrue(protected.isdisjoint(BACKGROUND_AWARE_SECTION_KEYS))

    def test_background_round_trips(self):
        definition = get_definition("multi_banner")
        cleaned = definition.validate_settings({"background": {"mode": "color", "color": "#112233"}})
        self.assertEqual(cleaned["background"]["mode"], "color")
        self.assertEqual(cleaned["background"]["color"], "#112233")


class SpacingSettingsTests(TestCase):
    """spec §8 (Basic: Small/Normal/Large — Advanced: exact padding/margin)."""

    def test_missing_key_defaults_to_normal_no_advanced_override(self):
        cleaned = validate_spacing_settings(None)
        self.assertEqual(cleaned, default_spacing_settings())
        self.assertEqual(cleaned["vertical_spacing"], "normal")
        self.assertTrue(all(v is None for v in cleaned["advanced"].values()))

    def test_valid_basic_size(self):
        cleaned = validate_spacing_settings({"vertical_spacing": "large"})
        self.assertEqual(cleaned["vertical_spacing"], "large")

    def test_unknown_size_falls_back_to_normal(self):
        cleaned = validate_spacing_settings({"vertical_spacing": "huge"})
        self.assertEqual(cleaned["vertical_spacing"], "normal")

    def test_advanced_override_clamped_to_range(self):
        cleaned = validate_spacing_settings({"advanced": {"padding_top": 9999, "margin_top": -50}})
        self.assertEqual(cleaned["advanced"]["padding_top"], 200)
        self.assertEqual(cleaned["advanced"]["margin_top"], 0)

    def test_advanced_field_left_none_when_not_supplied(self):
        cleaned = validate_spacing_settings({"advanced": {"padding_top": 40}})
        self.assertEqual(cleaned["advanced"]["padding_top"], 40)
        self.assertIsNone(cleaned["advanced"]["padding_bottom"])

    def test_non_numeric_advanced_value_rejected(self):
        with self.assertRaises(SpacingSettingsError):
            validate_spacing_settings({"advanced": {"padding_top": "lots"}})

    def test_non_dict_rejected(self):
        with self.assertRaises(SpacingSettingsError):
            validate_spacing_settings("nope")


class SpacingAwareIntegrationTests(TestCase):
    def test_spacing_aware_keys_get_spacing_defaults(self):
        for key in SPACING_AWARE_SECTION_KEYS:
            defaults = get_definition(key).default_settings()
            self.assertIn("spacing", defaults, key)
            self.assertEqual(defaults["spacing"]["vertical_spacing"], "normal", key)

    def test_non_spacing_aware_keys_have_no_spacing_field(self):
        for key, definition in SECTION_REGISTRY.items():
            if key in SPACING_AWARE_SECTION_KEYS:
                continue
            defaults = definition.default_settings()
            self.assertNotIn("spacing", defaults, key)

    def test_background_and_spacing_share_exactly_the_same_allowlist(self):
        self.assertEqual(BACKGROUND_AWARE_SECTION_KEYS, SPACING_AWARE_SECTION_KEYS)


class NewsletterSectionRegistryTests(TestCase):
    """Phase 3 — بلوکِ «خبرنامه» در Section Registry."""

    def test_registered_single_instance_only(self):
        definition = get_definition("newsletter")
        self.assertEqual(definition.max_instances, 1)
        self.assertFalse(definition.duplicable)

    def test_default_settings(self):
        defaults = get_definition("newsletter").default_settings()
        self.assertEqual(defaults["title"], "عضویت در خبرنامه")
        self.assertEqual(defaults["button_label"], "عضویت")

    def test_blank_title_and_button_label_falls_back(self):
        cleaned = get_definition("newsletter").validate_settings({"title": "", "button_label": ""})
        self.assertEqual(cleaned["button_label"], "عضویت")
        self.assertEqual(cleaned["title"], "")

    def test_custom_values_round_trip(self):
        cleaned = get_definition("newsletter").validate_settings({
            "title": "عنوانِ من", "subtitle": "زیرعنوانِ من", "button_label": "برو",
        })
        self.assertEqual(cleaned["title"], "عنوانِ من")
        self.assertEqual(cleaned["subtitle"], "زیرعنوانِ من")
        self.assertEqual(cleaned["button_label"], "برو")

    def test_non_dict_rejected(self):
        with self.assertRaises(NewsletterSettingsError):
            get_definition("newsletter").validate_settings("nope")


class PageTypeConstantsMatchModelTests(TestCase):
    """Phase 5: چون ``section_registry.py`` عمداً به ``models.py`` وابسته
    نیست (فلسفه‌ی «دیکشنری ثابت پایتونی» بالا)، ثابت‌های ``PAGE_TYPE_*``
    اینجا مستقل تکرار شده‌اند — این تست تضمین می‌کند اگر روزی
    ``StorefrontPage.PageType`` تغییر کند، این فایل خاموش از هماهنگی
    نمی‌افتد."""

    def test_all_page_types_matches_model_enum_exactly(self):
        self.assertEqual(ALL_PAGE_TYPES, frozenset(StorefrontPage.PageType.values))

    def test_individual_constants_match_model_values(self):
        self.assertEqual(
            {PAGE_TYPE_HOME, PAGE_TYPE_PRODUCT_DETAIL, PAGE_TYPE_LISTING, PAGE_TYPE_COLLECTION, PAGE_TYPE_SEARCH, PAGE_TYPE_CART},
            set(StorefrontPage.PageType.values),
        )


class PageTypeAllowlistTests(TestCase):
    #: انواعِ context-aware (Phase 5) عمداً از تستِ «همه‌جا مجاز» مستثنی‌اند —
    #: page_types محدودشان اینجا، در ``test_context_aware_types_restricted_to_their_own_page``
    #: به‌ازایِ هرکدام جداگانه اثبات می‌شود.
    _CONTEXT_AWARE_PAGE_TYPES = {
        "product_main": frozenset({PAGE_TYPE_PRODUCT_DETAIL}),
        "product_description": frozenset({PAGE_TYPE_PRODUCT_DETAIL}),
        "product_video": frozenset({PAGE_TYPE_PRODUCT_DETAIL}),
        "related_products": frozenset({PAGE_TYPE_PRODUCT_DETAIL}),
        "product_listing": frozenset({PAGE_TYPE_LISTING, PAGE_TYPE_SEARCH}),
        "collection_header": frozenset({PAGE_TYPE_COLLECTION}),
        "collection_products": frozenset({PAGE_TYPE_COLLECTION}),
        "cart_items": frozenset({PAGE_TYPE_CART}),
        "cart_summary": frozenset({PAGE_TYPE_CART}),
        "fashion_lifestyle_hero": frozenset({PAGE_TYPE_HOME}),
        "catalog_product_wall": frozenset({PAGE_TYPE_HOME}),
    }

    def test_existing_section_types_default_to_all_pages(self):
        """۱۷ نوعِ محتواییِ عمومیِ موجود از پیش نباید با این چکپوینت رفتار
        تغییر کنند — پیش‌فرض یعنی «همه‌جا مجاز»."""
        for key in EXPECTED_KEYS - set(self._CONTEXT_AWARE_PAGE_TYPES):
            definition = get_definition(key)
            self.assertEqual(definition.page_types, ALL_PAGE_TYPES, key)
            for page_type in StorefrontPage.PageType.values:
                self.assertTrue(is_section_allowed_on_page(key, page_type), f"{key} on {page_type}")

    def test_context_aware_types_restricted_to_their_own_page(self):
        for key, expected_pages in self._CONTEXT_AWARE_PAGE_TYPES.items():
            definition = get_definition(key)
            self.assertEqual(definition.page_types, expected_pages, key)
            for page_type in StorefrontPage.PageType.values:
                allowed = is_section_allowed_on_page(key, page_type)
                self.assertEqual(allowed, page_type in expected_pages, f"{key} on {page_type}")

    def test_unknown_section_key_never_allowed_on_any_page(self):
        for page_type in StorefrontPage.PageType.values:
            self.assertFalse(is_section_allowed_on_page("does_not_exist", page_type))

    def test_list_library_groups_unfiltered_includes_page_restricted_types_too(self):
        """بدونِ ``page_type``، فیلتری اعمال نمی‌شود — کتابخانه‌ی نامحدود
        شاملِ حتی انواعِ محدودشده (مثلِ product_main) هم می‌شود."""
        unfiltered_keys = {d.key for _c, members in list_library_groups() for d in members}
        self.assertIn("product_main", unfiltered_keys)

    def test_list_library_groups_can_be_scoped_to_a_page_type(self):
        cart_keys = {d.key for _c, members in list_library_groups(page_type=PAGE_TYPE_CART) for d in members}
        product_detail_keys = {
            d.key for _c, members in list_library_groups(page_type=PAGE_TYPE_PRODUCT_DETAIL) for d in members
        }
        context_aware = {"product_main", "product_description", "product_video", "related_products"}
        # کتابخانه‌ی product_detail دقیقاً همان ۴ نوعِ context-aware را
        # نسبت به کتابخانه‌ی cart بیشتر دارد — بقیه (همه‌ی انواعِ عمومی)
        # روی هر دو صفحه یکسان‌اند.
        self.assertEqual(product_detail_keys - cart_keys, context_aware)
        self.assertTrue(context_aware <= product_detail_keys)
        self.assertFalse(context_aware & cart_keys)


# ============================================================================
# U1A — Engine Metadata Contract Foundation
#
# These tests prove the additive ``SectionDefinition``/``VariantDefinition``
# contract (apps/storefront_builder/variant_contract.py) is backwards
# compatible: every existing section keeps constructing/rendering exactly as
# before, and the new resolution helpers fail safely for the 31 section
# types that declare no variants. Nothing here changes persisted setting
# keys, template output, or SECTION_REGISTRY's key set.
# ============================================================================

#: U1A test #13 — the SECTION_REGISTRY key set must remain exactly this,
#: unchanged by the metadata contract. Reuses the same 34-key fixture
#: already asserted by ``SectionRegistryTests.test_all_required_keys_registered``
#: above, restated explicitly here so this file's own U1A suite proves it
#: independently of that other test.
U1A_EXPECTED_SECTION_KEYS = EXPECTED_KEYS


class U1ABackwardsCompatibilityTests(TestCase):
    """Test #1, #13, #14, #15 — nothing about the existing registry moved."""

    def test_all_34_definitions_still_construct_and_are_gettable(self):
        self.assertEqual(len(list_definitions()), 36)
        for key in U1A_EXPECTED_SECTION_KEYS:
            definition = get_definition(key)
            self.assertEqual(definition.key, key)

    def test_section_registry_key_set_unchanged(self):
        self.assertEqual(set(SECTION_REGISTRY.keys()), U1A_EXPECTED_SECTION_KEYS)

    def test_hero_banner_and_image_slider_both_still_exist_unmerged(self):
        """R1 flagged de-duplicating these two keys as MEDIUM compatibility
        risk and explicitly out of scope for U1A — this test locks in that
        neither key was merged, renamed, or aliased. Each keeps its own
        distinct ``template_name`` (they only share their *rendered body*
        via a common ``{% include %}`` partial at the template layer, which
        is unrelated to and untouched by this dataclass-level change); what
        they do already share, unchanged, is the same validator/defaults
        function objects."""
        hero = get_definition("hero_banner")
        slider = get_definition("image_slider")
        self.assertEqual(hero.key, "hero_banner")
        self.assertEqual(slider.key, "image_slider")
        self.assertNotEqual(hero.template_name, slider.template_name)
        # Both still resolve through the identical shared slider settings
        # contract (proven behaviourally, since the wrapped closures aren't
        # directly comparable by identity after _finalize_registry).
        self.assertEqual(hero.default_settings(), slider.default_settings())

    def test_default_settings_output_for_the_three_precedent_sections_is_unchanged(self):
        """Locks in the exact ``default_settings()`` shape for the three
        proven variant precedents — proves populating ``variants``/
        ``default_variant``/``variant_setting_key`` did not alter what
        ``validate_settings``/``default_settings`` themselves produce."""
        category_defaults = get_definition("category_grid").default_settings()
        self.assertEqual(category_defaults["display_mode"], "grid")
        self.assertEqual(category_defaults["category_ids"], [])

        brand_defaults = get_definition("brand_carousel").default_settings()
        self.assertEqual(brand_defaults["display_mode"], "grid")
        self.assertEqual(brand_defaults["brand_ids"], [])

        product_defaults = get_definition("product_section").default_settings()
        self.assertEqual(product_defaults["display_mode"], "carousel")
        self.assertEqual(product_defaults["data_source"], "newest")

    def test_multi_banner_validator_still_passes_through_any_shape_unchanged(self):
        """Proves R1 §9's instruction was followed literally: validation was
        NOT narrowed. An arbitrary, never-seen-before ``layout_variant``
        string must still pass through unchanged, exactly like a known one."""
        definition = get_definition("multi_banner")
        for value in (*MULTI_BANNER_KNOWN_LAYOUT_VARIANTS, "some-future-value-nobody-wrote-yet"):
            cleaned = definition.validate_settings({"layout_variant": value})
            self.assertEqual(cleaned["layout_variant"], value)


class U1ACapabilitiesConsistencyTests(TestCase):
    """Test #8 — capabilities are immutable (frozenset) and, per R1 §7,
    consistent with the pre-existing allowlists they were derived from."""

    _ALLOWLIST_BY_CAPABILITY = {
        "card": CARD_AWARE_SECTION_KEYS,
        "background": BACKGROUND_AWARE_SECTION_KEYS,
        "spacing": SPACING_AWARE_SECTION_KEYS,
        "motion": MOTION_AWARE_SECTION_KEYS,
        "destination": DESTINATION_AWARE_SECTION_KEYS,
        "layout_width": LAYOUT_WIDTH_AWARE_SECTION_KEYS,
        "layout_height": LAYOUT_HEIGHT_AWARE_SECTION_KEYS,
        "columns": COLUMN_AWARE_SECTION_KEYS,
        "columns_visual": COLUMN_VISUAL_SECTION_KEYS,
    }

    def test_capabilities_field_is_a_frozenset_on_every_definition(self):
        for definition in list_definitions():
            self.assertIsInstance(definition.capabilities, frozenset, definition.key)

    def test_every_definition_declares_the_responsive_capability(self):
        """``_with_responsive`` applies unconditionally to all 34 keys."""
        for definition in list_definitions():
            self.assertIn("responsive", definition.capabilities, definition.key)

    def test_capabilities_agree_with_every_pre_existing_allowlist(self):
        for capability, allowlist in self._ALLOWLIST_BY_CAPABILITY.items():
            for definition in list_definitions():
                expected = definition.key in allowlist
                actual = capability in definition.capabilities
                self.assertEqual(
                    actual, expected,
                    f"{definition.key}: capability {capability!r} disagrees with its allowlist",
                )

    def test_resolve_capabilities_matches_definition_field_with_no_variant(self):
        definition = get_definition("rich_text")
        self.assertEqual(resolve_capabilities(definition), definition.capabilities)


class U1AVariantContractTests(TestCase):
    """Test #2, #3, #6, #7, #9, #10, #11 — the resolution helpers."""

    def test_definition_with_no_variants_resolves_safely(self):
        """Test #2 — 31 of 34 sections declare no variants at all."""
        definition = get_definition("rich_text")
        self.assertEqual(list_variants(definition), ())
        self.assertIsNone(resolve_active_variant(definition, {"body_html": "x"}))
        self.assertIsNone(resolve_active_variant(definition, None))

    def test_category_grid_declares_all_four_known_variants(self):
        """Test #3 — a definition can declare multiple variants."""
        definition = get_definition("category_grid")
        keys = {v.key for v in list_variants(definition)}
        self.assertEqual(keys, {"grid", "carousel", "circular", "image_strip", "fashion_flat", "fashion_mosaic", "beauty_icons", "chocolate_story", "chocolate_badges", "atelier_mosaic", "luxury_shortcuts"})
        self.assertEqual(definition.default_variant, "grid")
        self.assertEqual(definition.variant_setting_key, "display_mode")

    def test_proven_precedents_map_without_changing_the_persisted_setting_key(self):
        """Test #6 — category_grid/brand_carousel/product_section keep using
        their existing ``display_mode`` key; the general contract reads it
        through ``variant_setting_key``, not a renamed ``"variant"`` key."""
        cases = (
            ("category_grid", {"display_mode": "carousel"}),
            ("brand_carousel", {"display_mode": "carousel"}),
            # product_section requires a valid data_source too — only
            # display_mode is the variant-selecting key.
            ("product_section", {"display_mode": "grid", "data_source": "newest"}),
        )
        for section_key, raw_settings in cases:
            definition = get_definition(section_key)
            settings = definition.validate_settings(raw_settings)
            self.assertEqual(settings["display_mode"], raw_settings["display_mode"])  # persisted key untouched
            variant = resolve_active_variant(definition, settings)
            self.assertIsNotNone(variant, section_key)
            self.assertEqual(variant.key, raw_settings["display_mode"], section_key)

    def test_default_variant_is_deterministic_when_setting_is_missing_or_invalid(self):
        """Test #7 + #11 — missing/garbage values fail safely to
        ``default_variant``, never an exception, never a site-specific
        fallback."""
        definition = get_definition("category_grid")
        self.assertEqual(resolve_active_variant(definition, {}).key, "grid")
        self.assertEqual(resolve_active_variant(definition, None).key, "grid")
        self.assertEqual(
            resolve_active_variant(definition, {"display_mode": "not_a_real_variant"}).key, "grid",
        )
        self.assertEqual(
            resolve_active_variant(definition, {"display_mode": "<script>x</script>"}).key, "grid",
        )

    def test_get_variant_returns_none_for_unknown_key_without_raising(self):
        definition = get_definition("brand_carousel")
        self.assertIsNone(get_variant(definition, "does-not-exist"))
        self.assertIsNone(get_variant(definition, None))
        self.assertIsNone(get_variant(definition, ""))

    def test_supported_settings_defaults_to_none_meaning_everything_supported(self):
        """Test #9 — deterministic, and matches the current real behaviour
        (every existing section supports its own full settings shape)."""
        definition = get_definition("product_section")
        self.assertIsNone(resolve_supported_settings(definition))
        variant = get_variant(definition, "grid")
        self.assertIsNone(resolve_supported_settings(definition, variant))

    def test_required_data_defaults_to_empty_frozenset(self):
        """Test #10 — deterministic empty set, not None/crash."""
        definition = get_definition("hero_banner")
        self.assertEqual(resolve_required_data(definition), frozenset())


class U1AVariantRendererSafetyTests(TestCase):
    """Test #4, #5 — renderer override is optional and only ever comes from
    Python-authored registry metadata. Uses synthetic, unregistered
    VariantDefinition instances so no production template/section is
    touched — U1A introduces no new visual variant."""

    def test_renderer_defaults_to_none_and_falls_back_to_section_template(self):
        """Test #4 — the three real precedents all leave renderer unset
        (Pattern A: same template, different settings)."""
        definition = get_definition("category_grid")
        for variant in list_variants(definition):
            self.assertIsNone(variant.renderer)
            self.assertEqual(resolve_renderer_template(definition, variant), definition.template_name)
        self.assertEqual(resolve_renderer_template(definition, None), definition.template_name)

    def test_renderer_override_when_present_comes_only_from_the_variant_object(self):
        """Test #5 — Pattern B, proven with a synthetic definition. No real
        section is given a second template in U1A."""
        synthetic = VariantDefinition(
            key="alt_layout", label_fa="چیدمانِ جایگزین (آزمایشی)",
            renderer="storefront_builder/sections/synthetic_alt.html",
        )
        validate_variant_definition(synthetic)  # must not raise — well-formed
        section = get_definition("rich_text")
        self.assertEqual(resolve_renderer_template(section, synthetic), "storefront_builder/sections/synthetic_alt.html")
        # Still falls back correctly for a variant that doesn't override it.
        bare = VariantDefinition(key="bare", label_fa="ساده")
        self.assertEqual(resolve_renderer_template(section, bare), section.template_name)

    def test_unsafe_renderer_paths_are_rejected_at_definition_time(self):
        with self.assertRaises(InvalidVariantDefinitionError):
            validate_variant_definition(VariantDefinition(key="x", label_fa="x", renderer="../../etc/passwd"))
        with self.assertRaises(InvalidVariantDefinitionError):
            validate_variant_definition(VariantDefinition(key="x", label_fa="x", renderer="/etc/passwd"))
        with self.assertRaises(InvalidVariantDefinitionError):
            validate_variant_definition(VariantDefinition(key="x", label_fa="x", renderer=""))

    def test_duplicate_variant_keys_rejected(self):
        with self.assertRaises(InvalidVariantDefinitionError):
            validate_variants(
                (VariantDefinition(key="a", label_fa="A"), VariantDefinition(key="a", label_fa="A دوباره")),
                default_variant=None,
            )

    def test_default_variant_must_reference_a_real_variant_key(self):
        with self.assertRaises(InvalidVariantDefinitionError):
            validate_variants(
                (VariantDefinition(key="a", label_fa="A"),), default_variant="does-not-exist",
            )

    def test_empty_variant_tuple_is_always_valid(self):
        validate_variants((), default_variant=None)  # must not raise


class U1AResponsiveMotionDefaultsExposureTests(TestCase):
    """Section 5 — least-invasive exposure of responsive/motion defaults,
    derived from the single existing source of truth
    (``definition.default_settings()``), never a second copy that could
    desync from real rendering."""

    def test_responsive_defaults_match_default_settings_for_every_definition(self):
        for definition in list_definitions():
            self.assertEqual(
                resolve_responsive_defaults(definition),
                definition.default_settings().get("responsive", {}),
                definition.key,
            )

    def test_motion_defaults_present_only_for_motion_aware_sections(self):
        for definition in list_definitions():
            expected = definition.default_settings().get("motion")
            actual = resolve_motion_defaults(definition)
            if expected is None:
                self.assertIsNone(actual, definition.key)
            else:
                self.assertEqual(actual, expected, definition.key)

    def test_variant_level_override_takes_precedence_when_declared(self):
        section = get_definition("hero_banner")  # a real MOTION_AWARE section
        override_variant = VariantDefinition(
            key="v", label_fa="v", motion_defaults={"style": "fade"}, responsive_defaults={"hide_on_mobile": True},
        )
        self.assertEqual(resolve_motion_defaults(section, override_variant), {"style": "fade"})
        self.assertEqual(resolve_responsive_defaults(section, override_variant), {"hide_on_mobile": True})


class U1ANoTenantOrTemplateForkingTests(TestCase):
    """Test #12 — the metadata contract module itself introduces no
    ``template_key``/``store.slug``/``family_slug`` branching (the exact
    anti-pattern this phase exists to guard against)."""

    def test_variant_contract_source_contains_no_forbidden_forking_conditionals(self):
        """External-review correction (U1A pre-commit pass, item 5) — the
        original version of this test imported ``section_registry_module``
        but only scanned ``variant_contract_module``, missing the module
        that actually holds the metadata contract's registration surface
        (``SectionDefinition``, ``_finalize_registry``, the three populated
        ``variants`` tuples). Both U1A metadata-implementation surfaces are
        scanned now.

        Checks for the actual anti-pattern (a live conditional branching on
        a template/tenant identifier), not for the words themselves — this
        module's own docstrings/comments necessarily *name* the forbidden
        pattern in prose (here, and in R1/U1A task comments already present
        in ``section_registry.py``) to document why it must never appear as
        code; a plain substring search would false-positive on that prose,
        so this matches only an actual comparison (``== ``), not a mention."""
        forbidden_patterns = (
            r"template_key\s*==", r"store\.slug\s*==", r"family_slug\s*==",
            r"store_id\s*==", r"\bsite\s*==",
        )
        for module in (variant_contract_module, section_registry_module):
            source = inspect.getsource(module)
            for pattern in forbidden_patterns:
                self.assertIsNone(re.search(pattern, source), f"{module.__name__}: {pattern}")

    def test_variant_resolution_is_a_pure_function_of_its_arguments(self):
        """Calling resolve_active_variant twice with identical inputs must
        return the same result — no hidden global/tenant state."""
        definition = get_definition("brand_carousel")
        settings = {"display_mode": "carousel"}
        first = resolve_active_variant(definition, settings)
        second = resolve_active_variant(definition, settings)
        self.assertEqual(first.key, second.key)


# ============================================================================
# U1A pre-commit correction pass (external review, 6 items) — see
# docs/architecture/UNIVERSAL_STOREFRONT_U1A_TEMPLATE_REGISTRY_DECISION.md
# for item 4 (documentation-only, no test needed). Items 1/2/3/6 below.
# ============================================================================


def _synthetic_section_definition(**overrides) -> SectionDefinition:
    """A standalone SectionDefinition, never registered in SECTION_REGISTRY,
    used only to prove the dataclass-level immutability contract in
    isolation — no production section/template is touched by these tests."""
    base = dict(
        key="synthetic", label_fa="ساختگی", icon="x",
        template_name="storefront_builder/sections/synthetic.html",
        validate_settings=lambda raw: raw, default_settings=lambda: {},
    )
    base.update(overrides)
    return SectionDefinition(**base)


class U1ACorrectionImmutabilityTests(TestCase):
    """Item 1 — registry metadata must be actually immutable/normalized at
    construction time, not just type-hinted as such."""

    def test_section_definition_rejects_direct_attribute_reassignment(self):
        definition = get_definition("category_grid")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            definition.capabilities = frozenset()

    def test_variant_definition_rejects_direct_attribute_reassignment(self):
        variant = get_definition("category_grid").variants[0]
        with self.assertRaises(dataclasses.FrozenInstanceError):
            variant.capabilities = frozenset()

    def test_section_definition_coerces_mutable_inputs_to_frozenset(self):
        """A caller passing a plain ``set``/``list`` must not leave that
        exact mutable object stored on the definition."""
        original_capabilities = {"a", "b"}
        original_required_data = ["c", "d"]
        definition = _synthetic_section_definition(
            capabilities=original_capabilities, required_data=original_required_data,
        )
        self.assertIsInstance(definition.capabilities, frozenset)
        self.assertIsInstance(definition.required_data, frozenset)
        self.assertEqual(definition.capabilities, {"a", "b"})
        # Mutating the caller's original object afterwards must not affect
        # the stored definition — proves a copy was made, not a reference.
        original_capabilities.add("z")
        self.assertNotIn("z", definition.capabilities)

    def test_section_definition_variants_tuple_coerced_from_list(self):
        v = VariantDefinition(key="a", label_fa="A")
        definition = _synthetic_section_definition(variants=[v], default_variant="a")
        self.assertIsInstance(definition.variants, tuple)

    def test_variant_definition_coerces_mutable_capability_inputs(self):
        original = {"x"}
        variant = VariantDefinition(key="v", label_fa="v", capabilities=original, required_data=["y"])
        self.assertIsInstance(variant.capabilities, frozenset)
        self.assertIsInstance(variant.required_data, frozenset)
        original.add("z")
        self.assertNotIn("z", variant.capabilities)

    def test_variant_definition_responsive_and_motion_defaults_are_read_only(self):
        original = {"hide_on_mobile": True}
        variant = VariantDefinition(key="v", label_fa="v", responsive_defaults=original, motion_defaults=dict(style="fade"))
        # Stored value is a read-only view, not the caller's original dict.
        with self.assertRaises(TypeError):
            variant.responsive_defaults["x"] = 1
        with self.assertRaises(TypeError):
            variant.motion_defaults["x"] = 1
        # Mutating the caller's original dict afterwards must not leak in.
        original["hide_on_mobile"] = False
        self.assertTrue(variant.responsive_defaults["hide_on_mobile"])

    def test_none_responsive_and_motion_defaults_stay_none(self):
        """The None-vs-value distinction (item 2's same principle, applied
        to these two fields) must survive normalization untouched."""
        variant = VariantDefinition(key="v", label_fa="v")
        self.assertIsNone(variant.responsive_defaults)
        self.assertIsNone(variant.motion_defaults)

    def test_resolvers_still_return_ordinary_mutable_dict_copies(self):
        """The public resolver API is unchanged by the hardening — callers
        of resolve_responsive_defaults/resolve_motion_defaults still get a
        plain, freely-mutable dict of their own."""
        variant = VariantDefinition(key="v", label_fa="v", motion_defaults={"style": "fade"})
        section = get_definition("hero_banner")
        result = resolve_motion_defaults(section, variant)
        self.assertIsInstance(result, dict)
        result["style"] = "slide"  # must not raise, and must not mutate the variant
        self.assertEqual(variant.motion_defaults["style"], "fade")


class U1ACorrectionSupportedSettingsSemanticsTests(TestCase):
    """Item 2 — None (inherit/unrestricted) vs. frozenset() (explicitly
    zero) must remain distinguishable through the whole resolution path."""

    def test_a_section_supported_settings_none_resolves_to_none(self):
        definition = _synthetic_section_definition(supported_settings=None)
        self.assertIsNone(resolve_supported_settings(definition))

    def test_b_section_supported_settings_empty_frozenset_resolves_to_empty_frozenset_not_none(self):
        definition = _synthetic_section_definition(supported_settings=frozenset())
        result = resolve_supported_settings(definition)
        self.assertIsNotNone(result)
        self.assertEqual(result, frozenset())

    def test_c_variant_empty_frozenset_overrides_nonempty_section_value(self):
        definition = _synthetic_section_definition(supported_settings=frozenset({"title", "subtitle"}))
        variant = VariantDefinition(key="v", label_fa="v", supported_settings=frozenset())
        result = resolve_supported_settings(definition, variant)
        self.assertIsNotNone(result)
        self.assertEqual(result, frozenset())

    def test_d_variant_none_inherits_section_level_value(self):
        definition = _synthetic_section_definition(supported_settings=frozenset({"title"}))
        variant = VariantDefinition(key="v", label_fa="v", supported_settings=None)
        self.assertEqual(resolve_supported_settings(definition, variant), frozenset({"title"}))


class U1ACorrectionRendererNamespaceTests(TestCase):
    """Item 3 — renderer must be a trusted local section-template path,
    constrained to the closed ``SECTION_VARIANT_RENDERER_NAMESPACE``, never
    reachable from persisted merchant settings."""

    def test_none_still_valid_for_pattern_a(self):
        validate_variant_definition(VariantDefinition(key="a", label_fa="a", renderer=None))  # must not raise

    def test_accepted_path_inside_the_section_template_namespace(self):
        self.assertEqual(SECTION_VARIANT_RENDERER_NAMESPACE, "storefront_builder/sections/")
        validate_variant_definition(
            VariantDefinition(key="a", label_fa="a", renderer="storefront_builder/sections/alt_layout.html"),
        )  # must not raise

    def test_rejected_absolute_path(self):
        with self.assertRaises(InvalidVariantDefinitionError):
            validate_variant_definition(
                VariantDefinition(key="a", label_fa="a", renderer="/storefront_builder/sections/x.html"),
            )

    def test_rejected_path_traversal(self):
        with self.assertRaises(InvalidVariantDefinitionError):
            validate_variant_definition(
                VariantDefinition(key="a", label_fa="a", renderer="storefront_builder/sections/../../../etc/passwd"),
            )

    def test_rejected_windows_drive_path(self):
        for renderer in (r"C:\storefront_builder\sections\x.html", "C:/storefront_builder/sections/x.html"):
            with self.assertRaises(InvalidVariantDefinitionError):
                validate_variant_definition(VariantDefinition(key="a", label_fa="a", renderer=renderer))

    def test_rejected_backslash_path(self):
        with self.assertRaises(InvalidVariantDefinitionError):
            validate_variant_definition(
                VariantDefinition(key="a", label_fa="a", renderer=r"storefront_builder\sections\x.html"),
            )

    def test_rejected_unc_like_path(self):
        with self.assertRaises(InvalidVariantDefinitionError):
            validate_variant_definition(
                VariantDefinition(key="a", label_fa="a", renderer=r"\\server\share\x.html"),
            )

    def test_rejected_empty_renderer(self):
        with self.assertRaises(InvalidVariantDefinitionError):
            validate_variant_definition(VariantDefinition(key="a", label_fa="a", renderer=""))

    def test_rejected_outside_allowed_namespace(self):
        for renderer in (
            "catalog/templates/catalog/product_card.html",
            "storefront_builder/partials/hero_slider_body.html",
            "storefront_builder/sectionsx/evil.html",  # prefix-looking but not the real namespace
        ):
            with self.assertRaises(InvalidVariantDefinitionError):
                validate_variant_definition(VariantDefinition(key="a", label_fa="a", renderer=renderer))

    def test_no_renderer_path_can_originate_from_persisted_settings(self):
        """Structural guarantee, not just a unit test of one function:
        resolve_renderer_template never reads a "renderer" key out of a
        settings dict — its only inputs are the SectionDefinition and a
        VariantDefinition, both Python objects, never raw JSON."""
        signature = inspect.signature(resolve_renderer_template)
        self.assertEqual(list(signature.parameters), ["definition", "variant"])

    def test_existing_three_precedents_are_untouched_pattern_a_renderer_none(self):
        """Do-not-change guarantee (§7) — the three real, live variants
        still declare no renderer override at all."""
        for section_key in ("category_grid", "brand_carousel", "product_section"):
            for variant in get_definition(section_key).variants:
                self.assertIsNone(variant.renderer, f"{section_key}.{variant.key}")


class U1ACorrectionEngineSchemaVersionTests(TestCase):
    """Item 6 — a future/unsupported schema_version must never be silently
    treated as known-compatible; missing provenance must still resolve
    safely to the current neutral shape."""

    def test_missing_provenance_entirely_resolves_to_current_neutral_shape(self):
        for raw in (None, {}, "not-a-dict", 42):
            result = validate_template_provenance(raw)
            self.assertEqual(result, build_template_provenance())
            self.assertEqual(result["engine"]["schema_version"], ENGINE_SCHEMA_VERSION)
            self.assertIsNone(result["template"]["key"])

    def test_engine_dict_present_without_schema_version_key_still_resolves_safely(self):
        result = validate_template_provenance({"engine": {}, "template": {"key": "modern", "version": "1"}})
        self.assertEqual(result["engine"]["schema_version"], ENGINE_SCHEMA_VERSION)
        self.assertEqual(result["template"]["key"], "modern")

    def test_current_supported_schema_version_round_trips(self):
        raw = build_template_provenance(template_key="dense_catalog", template_version="1")
        result = validate_template_provenance(raw)
        self.assertEqual(result, raw)

    def test_unsupported_future_schema_version_raises_explicitly(self):
        with self.assertRaises(UnsupportedEngineSchemaVersionError):
            validate_template_provenance({"engine": {"schema_version": 999}})

    def test_non_integer_schema_version_raises_explicitly_not_silently_defaulted(self):
        with self.assertRaises(UnsupportedEngineSchemaVersionError):
            validate_template_provenance({"engine": {"schema_version": "not-a-number"}})

    def test_strict_int_type_rejects_every_merely_coercible_value(self):
        """U1A final correction, item 1 — ``int(x)`` would happily accept
        every one of these; the contract must not. Each of these must raise
        rather than silently normalize to ``1``."""
        for bad_version in (999, True, False, 1.0, 1.9, "1", "01", None):
            with self.assertRaises(UnsupportedEngineSchemaVersionError, msg=repr(bad_version)):
                validate_template_provenance({"engine": {"schema_version": bad_version}})

    def test_a_real_python_int_is_still_accepted_when_supported(self):
        result = validate_template_provenance({"engine": {"schema_version": 1}})
        self.assertEqual(result["engine"]["schema_version"], 1)
        self.assertIs(type(result["engine"]["schema_version"]), int)

    def test_supported_versions_set_currently_contains_only_the_current_version(self):
        self.assertEqual(SUPPORTED_ENGINE_SCHEMA_VERSIONS, frozenset({ENGINE_SCHEMA_VERSION}))


class U1AFinalDeepImmutabilityTests(TestCase):
    """U1A final correction, item 2 — the earlier ``MappingProxyType(dict(...))``
    hardening only protected the outer mapping; a nested dict/list inside
    ``responsive_defaults``/``motion_defaults`` was still an ordinary
    mutable object. Proves the fix at every depth (cases A-E from the
    correction brief), for both fields."""

    def test_a_top_level_mutation_is_rejected(self):
        variant = VariantDefinition(key="v", label_fa="v", responsive_defaults={"mobile": {"columns": 2}})
        with self.assertRaises(TypeError):
            variant.responsive_defaults["mobile"] = {}

    def test_b_nested_mapping_mutation_is_rejected(self):
        variant = VariantDefinition(key="v", label_fa="v", responsive_defaults={"mobile": {"columns": 2}})
        with self.assertRaises(TypeError):
            variant.responsive_defaults["mobile"]["columns"] = 99

    def test_c_mutating_the_original_input_after_construction_does_not_leak_in(self):
        original = {"mobile": {"columns": 2}}
        variant = VariantDefinition(key="v", label_fa="v", responsive_defaults=original)
        original["mobile"]["columns"] = 999
        original["desktop"] = {"columns": 6}
        self.assertEqual(variant.responsive_defaults["mobile"]["columns"], 2)
        self.assertNotIn("desktop", variant.responsive_defaults)

    def test_d_mutating_a_resolve_responsive_defaults_result_does_not_mutate_the_variant(self):
        variant = VariantDefinition(key="v", label_fa="v", responsive_defaults={"mobile": {"columns": 2}})
        section = get_definition("hero_banner")  # a real MOTION_AWARE/responsive section
        resolved = resolve_responsive_defaults(section, variant)
        self.assertIsInstance(resolved, dict)
        self.assertIsInstance(resolved["mobile"], dict)  # thawed, not still a MappingProxyType
        resolved["mobile"]["columns"] = 12345
        resolved["desktop"] = {"columns": 6}
        self.assertEqual(variant.responsive_defaults["mobile"]["columns"], 2)
        self.assertNotIn("desktop", variant.responsive_defaults)

    def test_e_same_invariant_for_motion_defaults(self):
        variant = VariantDefinition(key="v", label_fa="v", motion_defaults={"style": "fade", "easing": {"curve": "ease-out"}})
        with self.assertRaises(TypeError):
            variant.motion_defaults["style"] = "slide"
        with self.assertRaises(TypeError):
            variant.motion_defaults["easing"]["curve"] = "linear"

        section = get_definition("hero_banner")
        resolved = resolve_motion_defaults(section, variant)
        self.assertIsInstance(resolved, dict)
        self.assertIsInstance(resolved["easing"], dict)
        resolved["easing"]["curve"] = "linear"
        self.assertEqual(variant.motion_defaults["easing"]["curve"], "ease-out")

    def test_lists_and_sets_inside_metadata_are_also_frozen_and_thawed(self):
        """Beyond the brief's A-E (which only name mappings) — the freeze
        helper is documented to also normalize list/tuple/set/frozenset;
        prove that generality actually holds, not just for dicts."""
        variant = VariantDefinition(
            key="v", label_fa="v",
            responsive_defaults={"breakpoints": [320, 768, 1024], "roles": {"admin", "owner"}},
        )
        self.assertIsInstance(variant.responsive_defaults["breakpoints"], tuple)
        self.assertIsInstance(variant.responsive_defaults["roles"], frozenset)
        with self.assertRaises(AttributeError):
            variant.responsive_defaults["breakpoints"].append(1440)

        section = get_definition("hero_banner")
        resolved = resolve_responsive_defaults(section, variant)
        self.assertIsInstance(resolved["breakpoints"], list)
        self.assertIsInstance(resolved["roles"], set)
        resolved["breakpoints"].append(1440)
        self.assertNotIn(1440, variant.responsive_defaults["breakpoints"])


class CatalogProductWallSettingsTests(TestCase):
    """Site-target-overhaul Part 2D — ``catalog_product_wall``'s own
    settings never carry a ``source_id`` or any Store-specific reference;
    they only ever describe HOW to resolve the current Store's real data
    (which source, how many groups, how many products per group)."""

    def _validate(self, raw):
        return section_registry_module._validate_catalog_product_wall_settings(raw)

    def test_registered_and_page_restricted_to_home(self):
        definition = get_definition("catalog_product_wall")
        self.assertEqual(definition.page_types, frozenset({"home"}))

    def test_invalid_source_mode_falls_back_to_categories_then_collections(self):
        cleaned = self._validate({"source_mode": "not-a-real-mode"})
        self.assertEqual(cleaned["source_mode"], "categories_then_collections")

    def test_all_three_real_source_modes_are_accepted(self):
        for mode in section_registry_module.CATALOG_PRODUCT_WALL_SOURCE_MODES:
            cleaned = self._validate({"source_mode": mode})
            self.assertEqual(cleaned["source_mode"], mode)

    def test_layout_modes_are_closed_and_invalid_values_fall_back_to_rows(self):
        for mode in section_registry_module.CATALOG_PRODUCT_WALL_LAYOUT_MODES:
            cleaned = self._validate({"layout_mode": mode})
            self.assertEqual(cleaned["layout_mode"], mode)
        self.assertEqual(self._validate({"layout_mode": "merchant-special"})["layout_mode"], "rows")

    def test_layout_modes_are_registered_structural_variants(self):
        definition = get_definition("catalog_product_wall")
        self.assertEqual(
            tuple(variant.key for variant in definition.variants),
            section_registry_module.CATALOG_PRODUCT_WALL_LAYOUT_MODES,
        )
        self.assertEqual(definition.variant_setting_key, "layout_mode")
        self.assertEqual(definition.default_variant, "rows")

    def test_title_is_bounded_display_copy_not_a_data_reference(self):
        cleaned = self._validate({"title": "فروش ویژه"})
        self.assertEqual(cleaned["title"], "فروش ویژه")
        self.assertNotIn("source_id", cleaned)

    def test_max_groups_is_clamped_to_the_registered_range(self):
        self.assertEqual(self._validate({"max_groups": 0})["max_groups"], 1)
        self.assertEqual(self._validate({"max_groups": 999})["max_groups"], 12)
        self.assertEqual(self._validate({"max_groups": 6})["max_groups"], 6)

    def test_non_numeric_max_groups_raises_a_clear_error(self):
        with self.assertRaises(section_registry_module.CatalogProductWallSettingsError):
            self._validate({"max_groups": "not-a-number"})

    def test_no_source_id_field_exists_anywhere_in_the_cleaned_settings(self):
        cleaned = self._validate({})
        self.assertNotIn("source_id", cleaned)
        self.assertNotIn("category_ids", cleaned)
        self.assertNotIn("collection_ids", cleaned)

    def test_default_settings_match_a_pass_through_empty_dict(self):
        self.assertEqual(
            section_registry_module.default_catalog_product_wall_settings(),
            self._validate({}),
        )



class BrandCarouselPageTypeMembershipTests(TestCase):
    """A06 — brand_carousel must be allowed on EXACTLY the six page types
    it is certified for: home, product_detail, listing, search, collection,
    cart. Registry-level equality (not a loose superset check) so a future
    accidental narrowing/widening is caught."""

    def test_brand_carousel_allowed_on_exactly_the_six_page_types(self):
        definition = get_definition("brand_carousel")
        self.assertEqual(
            set(definition.page_types),
            {
                PAGE_TYPE_HOME, PAGE_TYPE_PRODUCT_DETAIL, PAGE_TYPE_LISTING,
                PAGE_TYPE_SEARCH, PAGE_TYPE_COLLECTION, PAGE_TYPE_CART,
            },
        )
        # equivalently, it spans the full ALL_PAGE_TYPES set (six).
        self.assertEqual(set(definition.page_types), set(ALL_PAGE_TYPES))
        self.assertEqual(len(definition.page_types), 6)

    def test_is_section_allowed_on_page_true_for_each_of_the_six(self):
        for page_type in (
            PAGE_TYPE_HOME, PAGE_TYPE_PRODUCT_DETAIL, PAGE_TYPE_LISTING,
            PAGE_TYPE_SEARCH, PAGE_TYPE_COLLECTION, PAGE_TYPE_CART,
        ):
            self.assertTrue(
                is_section_allowed_on_page("brand_carousel", page_type),
                f"brand_carousel should be allowed on {page_type}",
            )
