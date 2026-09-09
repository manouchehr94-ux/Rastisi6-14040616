from django.test import SimpleTestCase

from apps.storefront_builder import resource_source as resource_source_module
from apps.storefront_builder import section_registry
from apps.storefront_builder.section_registry import SectionDefinition, get_definition
from apps.storefront_builder.settings_schema import (
    SettingsField,
    SettingsSchema,
    SettingsSchemaError,
    clean_schema_patch,
    clean_section_schema_patch,
    normalize_digits,
    serialize_schema,
)


class DigitNormalizationTests(SimpleTestCase):
    def test_normalize_digits_converts_persian_digits(self):
        self.assertEqual(normalize_digits("۱۲"), "12")

    def test_normalize_digits_converts_arabic_indic_digits(self):
        self.assertEqual(normalize_digits("١٢"), "12")

    def test_normalize_digits_passes_through_ascii_digits(self):
        self.assertEqual(normalize_digits("12"), "12")


class SettingsFieldAndSchemaContractTests(SimpleTestCase):
    def test_duplicate_field_key_is_rejected(self):
        with self.assertRaises(SettingsSchemaError):
            SettingsSchema(fields=(
                SettingsField("title", "عنوان", "text", "basic"),
                SettingsField("title", "عنوان دوباره", "text", "basic"),
            ))

    def test_invalid_field_type_is_rejected(self):
        with self.assertRaises(SettingsSchemaError):
            SettingsField("title", "عنوان", "raw_html", "basic")

    def test_invalid_group_is_rejected(self):
        with self.assertRaises(SettingsSchemaError):
            SettingsField("title", "عنوان", "text", "expert")

    def test_choices_are_normalized_to_immutable_tuple(self):
        field = SettingsField(
            "hero_style", "مدل نمایش", "choice", "basic",
            choices=[("overlay", "overlay"), ("split", "split")],
        )
        self.assertIsInstance(field.choices, tuple)
        self.assertEqual(field.choices, (("overlay", "overlay"), ("split", "split")))

    def test_schema_fields_are_normalized_to_immutable_tuple(self):
        schema = SettingsSchema(fields=[SettingsField("title", "عنوان", "text", "basic")])
        self.assertIsInstance(schema.fields, tuple)


class CleanSchemaPatchTests(SimpleTestCase):
    def test_integer_field_accepts_persian_digits(self):
        schema = SettingsSchema(fields=(
            SettingsField("item_limit", "تعداد", "integer", "basic", min_value=2, max_value=24),
        ))
        cleaned = clean_schema_patch(schema, {"item_limit": "۱۲"}, {})
        self.assertEqual(cleaned["item_limit"], 12)

    def test_integer_field_accepts_arabic_indic_digits(self):
        schema = SettingsSchema(fields=(
            SettingsField("item_limit", "تعداد", "integer", "basic", min_value=2, max_value=24),
        ))
        cleaned = clean_schema_patch(schema, {"item_limit": "١٢"}, {})
        self.assertEqual(cleaned["item_limit"], 12)

    def test_unknown_key_is_rejected(self):
        schema = SettingsSchema(fields=(
            SettingsField("title", "عنوان", "text", "basic"),
        ))
        with self.assertRaisesMessage(ValueError, "Unknown settings key"):
            clean_schema_patch(schema, {"not_allowed": "x"}, {})

    def test_unknown_key_error_is_settings_schema_error(self):
        schema = SettingsSchema(fields=(
            SettingsField("title", "عنوان", "text", "basic"),
        ))
        with self.assertRaises(SettingsSchemaError):
            clean_schema_patch(schema, {"not_allowed": "x"}, {})

    def test_patch_preserves_unmanaged_legacy_keys(self):
        schema = SettingsSchema(fields=(
            SettingsField("title", "عنوان", "text", "basic"),
        ))
        current = {"title": "قدیم", "responsive": {"hide_on_mobile": False}}
        cleaned = clean_schema_patch(schema, {"title": "جدید"}, current)
        self.assertEqual(cleaned["title"], "جدید")
        self.assertEqual(cleaned["responsive"], {"hide_on_mobile": False})

    def test_patch_does_not_mutate_current_settings_or_raw_patch(self):
        schema = SettingsSchema(fields=(
            SettingsField("title", "عنوان", "text", "basic"),
        ))
        current = {"title": "قدیم", "responsive": {"hide_on_mobile": False}}
        raw_patch = {"title": "جدید"}
        clean_schema_patch(schema, raw_patch, current)
        self.assertEqual(current, {"title": "قدیم", "responsive": {"hide_on_mobile": False}})
        self.assertEqual(raw_patch, {"title": "جدید"})

    def test_preserve_unmanaged_false_drops_undeclared_legacy_keys(self):
        schema = SettingsSchema(
            fields=(SettingsField("title", "عنوان", "text", "basic"),),
            preserve_unmanaged=False,
        )
        current = {"title": "قدیم", "responsive": {"hide_on_mobile": False}}
        cleaned = clean_schema_patch(schema, {"title": "جدید"}, current)
        self.assertEqual(cleaned, {"title": "جدید"})

    def test_integer_lower_bound_is_enforced(self):
        schema = SettingsSchema(fields=(
            SettingsField("item_limit", "تعداد", "integer", "basic", min_value=2, max_value=24),
        ))
        with self.assertRaises(SettingsSchemaError):
            clean_schema_patch(schema, {"item_limit": 1}, {})

    def test_integer_upper_bound_is_enforced(self):
        schema = SettingsSchema(fields=(
            SettingsField("item_limit", "تعداد", "integer", "basic", min_value=2, max_value=24),
        ))
        with self.assertRaises(SettingsSchemaError):
            clean_schema_patch(schema, {"item_limit": 25}, {})

    def test_choice_value_must_be_in_declared_choices(self):
        schema = SettingsSchema(fields=(
            SettingsField(
                "hero_style", "مدل نمایش", "choice", "basic",
                choices=(("overlay", "overlay"), ("split", "split")),
            ),
        ))
        cleaned = clean_schema_patch(schema, {"hero_style": "split"}, {})
        self.assertEqual(cleaned["hero_style"], "split")
        with self.assertRaises(SettingsSchemaError):
            clean_schema_patch(schema, {"hero_style": "not_a_choice"}, {})

    def test_text_max_length_is_enforced(self):
        schema = SettingsSchema(fields=(
            SettingsField("title", "عنوان", "text", "basic", max_length=5),
        ))
        cleaned = clean_schema_patch(schema, {"title": "abcde"}, {})
        self.assertEqual(cleaned["title"], "abcde")
        with self.assertRaises(SettingsSchemaError):
            clean_schema_patch(schema, {"title": "abcdef"}, {})


class SerializeSchemaTests(SimpleTestCase):
    def test_serialize_schema_is_json_safe_and_preserves_order(self):
        schema = SettingsSchema(fields=(
            SettingsField("title", "عنوان", "text", "basic", default="", max_length=40),
            SettingsField(
                "item_limit", "تعداد", "integer", "advanced",
                default=8, min_value=2, max_value=24,
            ),
        ))
        payload = serialize_schema(schema)

        self.assertEqual(payload["preserve_unmanaged"], True)
        self.assertEqual([f["key"] for f in payload["fields"]], ["title", "item_limit"])

        first = payload["fields"][0]
        self.assertEqual(first["key"], "title")
        self.assertEqual(first["label"], "عنوان")
        self.assertEqual(first["field_type"], "text")
        self.assertEqual(first["group"], "basic")
        self.assertEqual(first["default"], "")
        self.assertEqual(first["required"], False)
        self.assertEqual(first["choices"], [])
        self.assertIsNone(first["min_value"])
        self.assertIsNone(first["max_value"])
        self.assertEqual(first["max_length"], 40)
        self.assertIsNone(first["widget_hint"])

        import json
        json.dumps(payload)


class SectionDefinitionSettingsSchemaCompatibilityTests(SimpleTestCase):
    def test_existing_style_definition_construction_defaults_settings_schema_to_none(self):
        definition = SectionDefinition(
            key="dummy",
            label_fa="آزمایشی",
            icon="icon",
            template_name="dummy.html",
            validate_settings=lambda settings: settings,
            default_settings=lambda: {},
        )
        self.assertIsNone(definition.settings_schema)


# ------------------------------------------------------------------------
# Corrective review pass (post-acf7a48)
# ------------------------------------------------------------------------


class PreserveUnmanagedFalseRetainsDeclaredCurrentValuesTests(SimpleTestCase):
    def test_partial_patch_retains_other_declared_current_values_and_drops_unmanaged(self):
        schema = SettingsSchema(
            fields=(
                SettingsField("title", "عنوان", "text", "basic"),
                SettingsField("subtitle", "زیرعنوان", "text", "basic"),
            ),
            preserve_unmanaged=False,
        )
        current = {
            "title": "old title",
            "subtitle": "old subtitle",
            "responsive": {"hide_on_mobile": False},
        }
        cleaned = clean_schema_patch(schema, {"title": "new title"}, current)
        self.assertEqual(cleaned, {"title": "new title", "subtitle": "old subtitle"})

    def test_partial_patch_with_preserve_unmanaged_false_does_not_mutate_inputs(self):
        schema = SettingsSchema(
            fields=(
                SettingsField("title", "عنوان", "text", "basic"),
                SettingsField("subtitle", "زیرعنوان", "text", "basic"),
            ),
            preserve_unmanaged=False,
        )
        current = {
            "title": "old title",
            "subtitle": "old subtitle",
            "responsive": {"hide_on_mobile": False},
        }
        raw_patch = {"title": "new title"}
        clean_schema_patch(schema, raw_patch, current)
        self.assertEqual(current, {
            "title": "old title",
            "subtitle": "old subtitle",
            "responsive": {"hide_on_mobile": False},
        })
        self.assertEqual(raw_patch, {"title": "new title"})


class BooleanCleaningTests(SimpleTestCase):
    def _schema(self):
        return SettingsSchema(fields=(
            SettingsField("autoplay", "پخش خودکار", "boolean", "basic"),
        ))

    def test_python_booleans_pass_through(self):
        schema = self._schema()
        self.assertIs(clean_schema_patch(schema, {"autoplay": True}, {})["autoplay"], True)
        self.assertIs(clean_schema_patch(schema, {"autoplay": False}, {})["autoplay"], False)

    def test_string_true_false_case_insensitive_and_trimmed(self):
        schema = self._schema()
        self.assertIs(clean_schema_patch(schema, {"autoplay": "true"}, {})["autoplay"], True)
        self.assertIs(clean_schema_patch(schema, {"autoplay": "  TRUE  "}, {})["autoplay"], True)
        self.assertIs(clean_schema_patch(schema, {"autoplay": "false"}, {})["autoplay"], False)
        self.assertIs(clean_schema_patch(schema, {"autoplay": "  FALSE  "}, {})["autoplay"], False)

    def test_string_1_0_on_off(self):
        schema = self._schema()
        self.assertIs(clean_schema_patch(schema, {"autoplay": "1"}, {})["autoplay"], True)
        self.assertIs(clean_schema_patch(schema, {"autoplay": "0"}, {})["autoplay"], False)
        self.assertIs(clean_schema_patch(schema, {"autoplay": "on"}, {})["autoplay"], True)
        self.assertIs(clean_schema_patch(schema, {"autoplay": "off"}, {})["autoplay"], False)

    def test_integer_1_0(self):
        schema = self._schema()
        self.assertIs(clean_schema_patch(schema, {"autoplay": 1}, {})["autoplay"], True)
        self.assertIs(clean_schema_patch(schema, {"autoplay": 0}, {})["autoplay"], False)

    def test_ambiguous_string_values_are_rejected(self):
        schema = self._schema()
        for value in ("yes", "no", "anything"):
            with self.assertRaises(SettingsSchemaError):
                clean_schema_patch(schema, {"autoplay": value}, {})

    def test_ambiguous_integer_values_are_rejected(self):
        schema = self._schema()
        for value in (2, -1):
            with self.assertRaises(SettingsSchemaError):
                clean_schema_patch(schema, {"autoplay": value}, {})

    def test_none_is_rejected(self):
        schema = self._schema()
        with self.assertRaises(SettingsSchemaError):
            clean_schema_patch(schema, {"autoplay": None}, {})


class MalformedSchemaDefinitionTests(SimpleTestCase):
    def test_empty_field_key_is_rejected(self):
        with self.assertRaises(SettingsSchemaError):
            SettingsField("", "عنوان", "text", "basic")

    def test_malformed_choice_pair_is_rejected_at_field_construction(self):
        with self.assertRaises(SettingsSchemaError):
            SettingsField(
                "hero_style", "مدل نمایش", "choice", "basic",
                choices=(("overlay",),),
            )

    def test_choice_values_and_labels_must_be_strings(self):
        with self.assertRaises(SettingsSchemaError):
            SettingsField(
                "item_limit", "تعداد", "choice", "basic",
                choices=((1, "one"),),
            )
        with self.assertRaises(SettingsSchemaError):
            SettingsField(
                "item_limit", "تعداد", "choice", "basic",
                choices=(("one", 1),),
            )

    def test_incoherent_integer_bounds_are_rejected(self):
        with self.assertRaises(SettingsSchemaError):
            SettingsField(
                "item_limit", "تعداد", "integer", "basic",
                min_value=10, max_value=2,
            )

    def test_negative_max_length_is_rejected(self):
        with self.assertRaises(SettingsSchemaError):
            SettingsField("title", "عنوان", "text", "basic", max_length=-1)

    def test_schema_fields_must_be_settings_field_instances(self):
        with self.assertRaises(SettingsSchemaError):
            SettingsSchema(fields=("not-a-settings-field",))


class JsonSafeDefaultTests(SimpleTestCase):
    def test_non_json_safe_default_is_rejected_at_field_construction(self):
        with self.assertRaises(SettingsSchemaError):
            SettingsField("title", "عنوان", "text", "basic", default=object())

    def test_json_compatible_primitive_defaults_are_accepted(self):
        SettingsField("title", "عنوان", "text", "basic", default="")
        SettingsField("item_limit", "تعداد", "integer", "basic", default=8)
        SettingsField("autoplay", "پخش خودکار", "boolean", "basic", default=True)
        SettingsField("tags", "برچسب‌ها", "text", "basic", default=["a", "b"])
        SettingsField("meta", "متا", "text", "basic", default={"a": 1})


# ------------------------------------------------------------------------
# Task 4 — register schemas for Rich Text and Hero without deleting the
# legacy validators. All fixtures below are built from the ACTUAL
# repository registry (get_definition(...).default_settings()/
# validate_settings(...)), never invented shapes.
# ------------------------------------------------------------------------


class RichTextSchemaRegistrationTests(SimpleTestCase):
    def test_rich_text_is_schema_enabled_with_exactly_body_html(self):
        rich_text = section_registry.get_definition("rich_text")
        self.assertIsNotNone(rich_text.settings_schema)
        self.assertEqual(
            [f.key for f in rich_text.settings_schema.fields],
            ["body_html"],
        )

    def test_rich_text_body_html_field_metadata_matches_legacy_contract(self):
        rich_text = section_registry.get_definition("rich_text")
        field = rich_text.settings_schema.get_field("body_html")
        self.assertEqual(field.field_type, "rich_text")
        self.assertEqual(field.group, "basic")
        self.assertEqual(field.default, "")
        self.assertEqual(field.max_length, section_registry._MAX_RICH_TEXT_LENGTH)
        self.assertEqual(field.widget_hint, "merchant_rich_text")


class HeroBannerSchemaRegistrationTests(SimpleTestCase):
    def test_hero_banner_is_schema_enabled(self):
        hero = section_registry.get_definition("hero_banner")
        self.assertIsNotNone(hero.settings_schema)

    def test_hero_banner_field_keys_are_in_declared_order(self):
        hero = section_registry.get_definition("hero_banner")
        self.assertEqual(
            [f.key for f in hero.settings_schema.fields],
            [
                "hero_style",
                "autoplay",
                "interval_ms",
                "show_arrows",
                "show_dots",
                "loop",
                "text_position",
                "appearance_overrides",
            ],
        )

    def test_hero_style_field_matches_legacy_contract(self):
        hero = section_registry.get_definition("hero_banner")
        field = hero.settings_schema.get_field("hero_style")
        self.assertEqual(field.field_type, "choice")
        self.assertEqual(field.default, "overlay")
        self.assertEqual(
            set(field.choices),
            {(choice, choice) for choice in section_registry.HERO_STYLE_CHOICES},
        )

    def test_autoplay_field_matches_legacy_contract(self):
        hero = section_registry.get_definition("hero_banner")
        field = hero.settings_schema.get_field("autoplay")
        self.assertEqual(field.field_type, "boolean")
        self.assertEqual(field.default, True)

    def test_interval_ms_field_matches_legacy_contract(self):
        hero = section_registry.get_definition("hero_banner")
        field = hero.settings_schema.get_field("interval_ms")
        self.assertEqual(field.field_type, "integer")
        self.assertEqual(field.default, section_registry._SLIDER_DEFAULT_INTERVAL_MS)
        self.assertEqual(field.min_value, section_registry._SLIDER_MIN_INTERVAL_MS)
        self.assertEqual(field.max_value, section_registry._SLIDER_MAX_INTERVAL_MS)
        self.assertEqual(field.group, "advanced")

    def test_show_arrows_show_dots_loop_fields_match_legacy_contract(self):
        hero = section_registry.get_definition("hero_banner")
        for key in ("show_arrows", "show_dots", "loop"):
            field = hero.settings_schema.get_field(key)
            self.assertEqual(field.field_type, "boolean")
            self.assertEqual(field.default, True)
            self.assertEqual(field.group, "advanced")

    def test_text_position_field_matches_legacy_contract(self):
        hero = section_registry.get_definition("hero_banner")
        field = hero.settings_schema.get_field("text_position")
        self.assertEqual(field.field_type, "choice")
        self.assertEqual(field.default, "end")
        self.assertEqual(
            set(field.choices), {("start", "ابتدا"), ("center", "وسط"), ("end", "انتها")}
        )
        self.assertEqual(field.group, "advanced")


class NoOtherSectionBecomesSchemaEnabledTests(SimpleTestCase):
    def test_image_slider_is_now_schema_enabled_via_its_own_schema(self):
        # image_slider shares _validate_slider_settings/default_slider_settings
        # with hero_banner but has no `variants` registered, so Task 4
        # deliberately did NOT schema-enable it just because it shares the
        # validator function. Task 6 gives it its own IMAGE_SLIDER_SCHEMA
        # (identical to HERO_BANNER_SCHEMA minus the hero_style field, which
        # only has a rendered control on hero_banner's settings form).
        image_slider = section_registry.get_definition("image_slider")
        self.assertIsNotNone(image_slider.settings_schema)
        field_keys = {field.key for field in image_slider.settings_schema.fields}
        self.assertNotIn("hero_style", field_keys)

    def test_representative_unrelated_section_is_still_unschematized(self):
        faq = section_registry.get_definition("faq")
        self.assertIsNone(faq.settings_schema)


class SchemaEnablementRegistryGuardTests(SimpleTestCase):
    """Phase 4 (Task 4) — backfills the R4-schema-enable guard across the
    WHOLE registry, not just the two sampled families
    (``NoOtherSectionBecomesSchemaEnabledTests`` above only ever checked
    ``image_slider``/``faq``). As Task 6 gives each of the remaining MIGRATE
    families its own R4 settings schema, this test fails immediately unless
    that family's key is deliberately added to ``EXPECTED_SCHEMA_ENABLED``
    (unschematized is implicit: any registered key not in that set) in the
    SAME change — no family can become schema-enabled (or silently regress
    to unschematized) without this guard noticing."""

    # The families with an R4 settings schema today (Phase 3's two
    # certified pilots — brand_carousel, collection_tiles — plus
    # hero_banner, rich_text, product_section; Task 6 adds category_grid,
    # image_slider, blog_posts, amazing_offers, quick_links, video_section,
    # newsletter, image_text, multi_banner, and Group B's
    # newest_products/best_sellers/discounted_products/promo_cards.
    # single_banner is deliberately excluded: it has no settings-driven
    # field at all (Task 6 Group C fixed/static disposition).
    EXPECTED_SCHEMA_ENABLED = frozenset({
        "hero_banner",
        "brand_carousel",
        "rich_text",
        "product_section",
        "collection_tiles",
        "category_grid",
        "image_slider",
        "blog_posts",
        "amazing_offers",
        "quick_links",
        "video_section",
        "newsletter",
        "image_text",
        "multi_banner",
        "newest_products",
        "best_sellers",
        "discounted_products",
        "promo_cards",
    })

    def test_every_registered_section_key_matches_its_expected_schema_state(self):
        definitions = section_registry.list_definitions()
        registered_keys = {definition.key for definition in definitions}
        # The guard set must itself track the registry — a typo'd or
        # retired key here must fail loudly, not silently no-op.
        self.assertTrue(self.EXPECTED_SCHEMA_ENABLED.issubset(registered_keys))

        mismatches = []
        for definition in definitions:
            expected_enabled = definition.key in self.EXPECTED_SCHEMA_ENABLED
            actually_enabled = definition.settings_schema is not None
            if expected_enabled != actually_enabled:
                mismatches.append((definition.key, expected_enabled, actually_enabled))
        self.assertEqual(
            mismatches, [],
            f"schema-enablement drift (key, expected_enabled, actually_enabled): {mismatches}",
        )


class CleanSectionSchemaPatchBridgeTests(SimpleTestCase):
    def test_definition_without_schema_is_rejected(self):
        definition = SectionDefinition(
            key="dummy",
            label_fa="آزمایشی",
            icon="icon",
            template_name="dummy.html",
            validate_settings=lambda settings: settings,
            default_settings=lambda: {},
        )
        with self.assertRaisesMessage(SettingsSchemaError, "Section is not schema-enabled"):
            clean_section_schema_patch(definition, {"anything": "x"}, {})

    def test_rich_text_bridge_matches_legacy_validator_result(self):
        rich_text = section_registry.get_definition("rich_text")
        current = rich_text.validate_settings(rich_text.default_settings())

        bridged = clean_section_schema_patch(
            rich_text, {"body_html": "<p>سلام</p>"}, current,
        )

        expected = rich_text.validate_settings({**current, "body_html": "<p>سلام</p>"})
        self.assertEqual(bridged, expected)

    def test_hero_preserves_supported_legacy_wrapper_blocks(self):
        hero = section_registry.get_definition("hero_banner")
        current = hero.validate_settings(hero.default_settings())
        # These are the ACTUAL wrapper blocks the finalized hero_banner
        # validator chain supports (see _finalize_registry / the
        # *_AWARE_SECTION_KEYS allowlists in section_registry.py):
        # responsive (all sections), motion, layout, background, spacing.
        for expected_block in ("responsive", "motion", "layout", "background", "spacing"):
            self.assertIn(expected_block, current)

        raw_patch = {"autoplay": False}
        raw_patch_copy = dict(raw_patch)
        current_copy = dict(current)

        bridged = clean_section_schema_patch(hero, raw_patch, current)

        self.assertIs(bridged["autoplay"], False)
        for block_key in ("responsive", "motion", "layout", "background", "spacing"):
            self.assertEqual(bridged[block_key], current[block_key])
        # the bridge's final step already ran definition.validate_settings,
        # so re-running it must be a no-op (proves it's an accepted shape).
        self.assertEqual(hero.validate_settings(bridged), bridged)
        self.assertEqual(raw_patch, raw_patch_copy)
        self.assertEqual(current, current_copy)

    def test_hero_interval_ms_accepts_persian_digits_through_the_bridge(self):
        hero = section_registry.get_definition("hero_banner")
        current = hero.validate_settings(hero.default_settings())
        bridged = clean_section_schema_patch(hero, {"interval_ms": "۴۵۰۰"}, current)
        self.assertEqual(bridged["interval_ms"], 4500)
        self.assertIsInstance(bridged["interval_ms"], int)

    def test_hero_unknown_key_is_rejected_before_reaching_legacy_validator(self):
        hero = section_registry.get_definition("hero_banner")
        current = hero.validate_settings(hero.default_settings())
        with self.assertRaises(SettingsSchemaError):
            clean_section_schema_patch(hero, {"not_a_real_field": "x"}, current)


# ------------------------------------------------------------------------
# Phase 3 — V01 desired-invariant (RED): once a merchant has explicitly
# chosen a local variant (display_mode) for a brand_carousel, a later
# non-variant patch (e.g. a title rename) must PRESERVE that explicit
# intent. Today the marker is dropped by the section's own validator (only
# hero_banner is appearance-override-aware), so this is the planned RED.
# ------------------------------------------------------------------------


class Phase3BrandPreservationTests(SimpleTestCase):
    def test_variant_intent_survives_title_patch(self):
        definition = get_definition('brand_carousel')
        selected = clean_section_schema_patch(
            definition, {'display_mode': 'carousel'}, definition.default_settings())
        renamed = clean_section_schema_patch(definition, {'title': 'Phase3'}, selected)
        self.assertTrue(renamed.get('appearance_overrides', {}).get('variant_explicit'))
        self.assertEqual(renamed['display_mode'], 'carousel')

    def test_variant_intent_survives_variant_then_title_then_source_sequence(self):
        # V01 regression: the marker must survive a WHOLE chain of unrelated
        # non-variant edits, not just a single title patch.
        definition = get_definition('brand_carousel')
        selected = clean_section_schema_patch(
            definition, {'display_mode': 'carousel'}, definition.default_settings())
        renamed = clean_section_schema_patch(definition, {'title': 'Phase3'}, selected)
        # a subsequent source edit (a genuine non-variant patch) still keeps it.
        sourced = clean_section_schema_patch(
            definition,
            {'source': resource_source_module.serialize_resource_source(
                resource_source_module.ResourceSource(kind='brand', mode='auto', auto_rule='all_active'))},
            renamed,
        )
        self.assertTrue(sourced.get('appearance_overrides', {}).get('variant_explicit'))
        self.assertEqual(sourced['display_mode'], 'carousel')

    def test_historically_unmarked_row_stays_unmarked_after_title_patch(self):
        # V01: a section that never had an explicit marker must NOT gain one
        # from an ordinary non-variant edit (no marker invented where none
        # existed).
        definition = get_definition('brand_carousel')
        current = definition.validate_settings(definition.default_settings())
        self.assertNotIn('appearance_overrides', current)
        renamed = clean_section_schema_patch(definition, {'title': 'x'}, current)
        self.assertIsNone(renamed.get('appearance_overrides', {}).get('variant_explicit'))

    def test_client_cannot_inject_variant_explicit_via_raw_payload(self):
        # V01: appearance_overrides is NOT schema-declared for brand_carousel,
        # so a raw patch trying to smuggle the trusted marker is rejected as
        # an unknown key — the client can never manufacture explicit intent.
        definition = get_definition('brand_carousel')
        current = definition.validate_settings(definition.default_settings())
        with self.assertRaises(SettingsSchemaError):
            clean_section_schema_patch(
                definition,
                {'appearance_overrides': {'variant_explicit': True}},
                current,
            )

    def test_direct_validate_settings_preserves_trusted_marker(self):
        # V01: the validator-level fix (used by BOTH the R4 bridge and the
        # legacy validate_settings path) carries a trusted, already-present
        # marker through unchanged.
        definition = get_definition('brand_carousel')
        seeded = {
            'title': '', 'display_mode': 'carousel', 'show_view_all': False,
            'brand_ids': [], 'appearance_overrides': {'variant_explicit': True},
        }
        validated = definition.validate_settings(seeded)
        self.assertTrue(validated.get('appearance_overrides', {}).get('variant_explicit'))

    def test_direct_validate_settings_never_forges_marker_from_non_bool(self):
        # V01: only a genuine boolean True is trusted — a truthy-but-non-True
        # value is not carried, so no marker is forged from junk input.
        definition = get_definition('brand_carousel')
        seeded = {
            'title': '', 'display_mode': 'carousel', 'show_view_all': False,
            'brand_ids': [], 'appearance_overrides': {'variant_explicit': 'yes'},
        }
        validated = definition.validate_settings(seeded)
        self.assertIsNone(validated.get('appearance_overrides', {}).get('variant_explicit'))


class Phase3SharedPilotPreservationTests(SimpleTestCase):
    """Task 6 proof that both pilots honor the shared edit-sequence contract."""

    def test_variant_title_source_sequence_preserves_marker_variant_and_source_order(self):
        # A regression in either pilot's validator wrapper would drop the
        # trusted marker, reset the chosen variant, or reorder the manual
        # resource selection during an unrelated title/source edit.
        cases = (
            {
                "section_key": "brand_carousel",
                "variant_key": "display_mode",
                "variant": "carousel",
                "resource_kind": "brand",
                "legacy_ids_key": "brand_ids",
                "manual_ids": (13, 7),
            },
            {
                "section_key": "collection_tiles",
                "variant_key": "tile_style",
                "variant": "carousel",
                "resource_kind": "collection",
                "legacy_ids_key": "collection_ids",
                "manual_ids": (23, 17),
            },
        )

        for case in cases:
            with self.subTest(section_key=case["section_key"]):
                definition = get_definition(case["section_key"])
                selected = clean_section_schema_patch(
                    definition,
                    {case["variant_key"]: case["variant"]},
                    definition.default_settings(),
                )
                renamed = clean_section_schema_patch(
                    definition,
                    {"title": "Task 6 shared title"},
                    selected,
                )
                sourced = clean_section_schema_patch(
                    definition,
                    {
                        "source": resource_source_module.serialize_resource_source(
                            resource_source_module.ResourceSource(
                                kind=case["resource_kind"],
                                mode="manual",
                                manual_ids=case["manual_ids"],
                            )
                        )
                    },
                    renamed,
                )

                self.assertTrue(
                    sourced.get("appearance_overrides", {}).get("variant_explicit")
                )
                self.assertEqual(sourced[case["variant_key"]], case["variant"])
                self.assertEqual(sourced["title"], "Task 6 shared title")
                self.assertEqual(
                    sourced[case["legacy_ids_key"]], list(case["manual_ids"])
                )
                self.assertNotIn("source", sourced)

    def test_unsupported_new_marker_write_is_rejected_for_both_pilots(self):
        # Removing either schema's unknown-key guard would let a client forge
        # the server-owned local-variant authority marker.
        for section_key in ("brand_carousel", "collection_tiles"):
            with self.subTest(section_key=section_key):
                definition = get_definition(section_key)
                with self.assertRaises(SettingsSchemaError):
                    clean_section_schema_patch(
                        definition,
                        {"appearance_overrides": {"variant_explicit": True}},
                        definition.default_settings(),
                    )

    def test_compatible_dormant_values_survive_non_owning_edits_for_both_pilots(self):
        # Brand deliberately retains its inactive view-all destination and
        # legacy responsive column values. Collection has no column contract;
        # it retains only its supported visibility/background/spacing blocks.
        cases = (
            {
                "section_key": "brand_carousel",
                "variant_key": "display_mode",
                "variant": "beauty_tabs",
                "resource_kind": "brand",
                "legacy_ids_key": "brand_ids",
                "manual_ids": (31, 29),
                "seed": {
                    "show_view_all": True,
                    "destination": {
                        "destination_type": "external",
                        "destination_id": None,
                        "destination_external_url": "https://example.com/brands",
                        "open_in_new_tab": True,
                    },
                    "responsive": {
                        "hide_on_desktop": False,
                        "hide_on_tablet": True,
                        "hide_on_mobile": False,
                        "desktop_columns": 3,
                        "tablet_columns": 2,
                        "mobile_columns": 1,
                    },
                },
            },
            {
                "section_key": "collection_tiles",
                "variant_key": "tile_style",
                "variant": "carousel",
                "resource_kind": "collection",
                "legacy_ids_key": "collection_ids",
                "manual_ids": (43, 41),
                "seed": {
                    "responsive": {
                        "hide_on_desktop": False,
                        "hide_on_tablet": False,
                        "hide_on_mobile": True,
                    },
                },
            },
        )

        for case in cases:
            with self.subTest(section_key=case["section_key"]):
                definition = get_definition(case["section_key"])
                current = {
                    **definition.default_settings(),
                    **case["seed"],
                    "background": {
                        "mode": "color",
                        "color": "#123456",
                        "media_asset_id": None,
                        "pattern_slug": "",
                        "palette_role": "",
                    },
                    "spacing": {
                        "vertical_spacing": "small",
                        "advanced": {
                            "padding_top": 12,
                            "padding_bottom": None,
                            "margin_top": None,
                            "margin_bottom": 8,
                        },
                    },
                }
                current = definition.validate_settings(current)
                varied = clean_section_schema_patch(
                    definition,
                    {case["variant_key"]: case["variant"]},
                    current,
                )
                renamed = clean_section_schema_patch(
                    definition, {"title": "Dormant values retained"}, varied,
                )
                sourced = clean_section_schema_patch(
                    definition,
                    {
                        "source": resource_source_module.serialize_resource_source(
                            resource_source_module.ResourceSource(
                                kind=case["resource_kind"],
                                mode="manual",
                                manual_ids=case["manual_ids"],
                            )
                        )
                    },
                    renamed,
                )

                self.assertEqual(sourced[case["variant_key"]], case["variant"])
                self.assertEqual(
                    sourced[case["legacy_ids_key"]], list(case["manual_ids"])
                )
                self.assertEqual(sourced["background"]["color"], "#123456")
                self.assertEqual(sourced["spacing"]["vertical_spacing"], "small")
                self.assertEqual(sourced["spacing"]["advanced"]["padding_top"], 12)
                self.assertEqual(sourced["spacing"]["advanced"]["margin_bottom"], 8)
                self.assertEqual(sourced["responsive"], current["responsive"])

                if case["section_key"] == "brand_carousel":
                    self.assertIs(sourced["show_view_all"], True)
                    self.assertEqual(sourced["destination"], current["destination"])
                else:
                    self.assertNotIn("show_view_all", sourced)
                    self.assertNotIn("desktop_columns", sourced["responsive"])
