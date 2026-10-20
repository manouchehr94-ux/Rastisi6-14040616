import json

from django.test import SimpleTestCase
from django.urls import reverse

from apps.storefront_builder import appearance_registry, section_registry
from apps.storefront_builder.models import StorefrontLayoutVersion, StorefrontPage, StorefrontSection
from apps.storefront_builder.services import render_service
from apps.storefront_builder.services.section_appearance_service import resolve_section_appearance
from apps.storefront_builder.settings_schema import SettingsSchemaError, validate_appearance_overrides

from .test_r4_mutation_api import R4MutationApiTestCase


def _global_appearance(**overrides):
    base = {
        "font": "Tahoma",
        "type_scale": "normal",
        "palette_slug": "some-palette",
        "color_overrides": {"primary": "#123456"},
        "template_slug": "modern",
    }
    base.update(overrides)
    return base


class ValidateAppearanceOverridesTests(SimpleTestCase):
    def test_none_and_empty_resolve_to_empty_dict(self):
        self.assertEqual(validate_appearance_overrides(None), {})
        self.assertEqual(validate_appearance_overrides({}), {})

    def test_enabled_font_only(self):
        cleaned = validate_appearance_overrides({
            "typography": {"enabled": True, "font": "Vazirmatn"},
        })
        self.assertEqual(cleaned, {"typography": {"enabled": True, "font": "Vazirmatn"}})

    def test_enabled_type_scale_only(self):
        cleaned = validate_appearance_overrides({
            "typography": {"enabled": True, "type_scale": "compact"},
        })
        self.assertEqual(cleaned, {"typography": {"enabled": True, "type_scale": "compact"}})

    def test_enabled_both_font_and_type_scale(self):
        cleaned = validate_appearance_overrides({
            "typography": {"enabled": True, "font": "Georgia", "type_scale": "large"},
        })
        self.assertEqual(
            cleaned,
            {"typography": {"enabled": True, "font": "Georgia", "type_scale": "large"}},
        )

    def test_disabled_cleans_sparsely_dropping_stale_values(self):
        cleaned = validate_appearance_overrides({
            "typography": {"enabled": False, "font": "Arial", "type_scale": "large"},
        })
        self.assertEqual(cleaned, {"typography": {"enabled": False}})

    def test_reject_non_object_appearance_overrides(self):
        with self.assertRaises(SettingsSchemaError):
            validate_appearance_overrides("not-an-object")
        with self.assertRaises(SettingsSchemaError):
            validate_appearance_overrides(["typography"])

    def test_reject_non_object_typography(self):
        with self.assertRaises(SettingsSchemaError):
            validate_appearance_overrides({"typography": "not-an-object"})

    def test_reject_unknown_top_level_key(self):
        with self.assertRaises(SettingsSchemaError):
            validate_appearance_overrides({"colors": {}})

    def test_reject_unknown_typography_key(self):
        with self.assertRaises(SettingsSchemaError):
            validate_appearance_overrides({
                "typography": {"enabled": True, "css": "body{color:red}"},
            })
        with self.assertRaises(SettingsSchemaError):
            validate_appearance_overrides({
                "typography": {"enabled": True, "font_size": "40px"},
            })
        with self.assertRaises(SettingsSchemaError):
            validate_appearance_overrides({
                "typography": {"enabled": True, "style": "italic"},
            })
        with self.assertRaises(SettingsSchemaError):
            validate_appearance_overrides({
                "typography": {"enabled": True, "class": "x"},
            })
        with self.assertRaises(SettingsSchemaError):
            validate_appearance_overrides({
                "typography": {"enabled": True, "html": "<b>x</b>"},
            })
        with self.assertRaises(SettingsSchemaError):
            validate_appearance_overrides({
                "typography": {"enabled": True, "javascript": "alert(1)"},
            })
        with self.assertRaises(SettingsSchemaError):
            validate_appearance_overrides({
                "typography": {"enabled": True, "tokens": {"a": 1}},
            })

    def test_reject_font_outside_allowlist(self):
        with self.assertRaises(SettingsSchemaError):
            validate_appearance_overrides({
                "typography": {"enabled": True, "font": "ComicSans"},
            })

    def test_reject_type_scale_outside_allowlist(self):
        with self.assertRaises(SettingsSchemaError):
            validate_appearance_overrides({
                "typography": {"enabled": True, "type_scale": "huge"},
            })

    def test_reject_non_boolean_enabled(self):
        with self.assertRaises(SettingsSchemaError):
            validate_appearance_overrides({"typography": {"enabled": "true"}})
        with self.assertRaises(SettingsSchemaError):
            validate_appearance_overrides({"typography": {"enabled": 1}})

    def test_does_not_mutate_input(self):
        raw = {"typography": {"enabled": True, "font": "Vazirmatn", "type_scale": "compact"}}
        raw_copy = json.loads(json.dumps(raw))
        validate_appearance_overrides(raw)
        self.assertEqual(raw, raw_copy)

    def test_allowlists_come_from_appearance_registry(self):
        for font in appearance_registry.FONT_CHOICES:
            validate_appearance_overrides({"typography": {"enabled": True, "font": font}})
        for scale in appearance_registry.TYPE_SCALE_CHOICES:
            validate_appearance_overrides({"typography": {"enabled": True, "type_scale": scale}})


class ResolveSectionAppearanceTests(SimpleTestCase):
    def test_no_override_returns_global_values_unmutated(self):
        global_appearance = _global_appearance()
        global_copy = json.loads(json.dumps(global_appearance))
        resolved = resolve_section_appearance(global_appearance, {})
        self.assertEqual(resolved["font"], "Tahoma")
        self.assertEqual(resolved["type_scale"], "normal")
        self.assertEqual(resolved["palette_slug"], global_appearance["palette_slug"])
        self.assertEqual(global_appearance, global_copy)

    def test_enabled_font_only_override(self):
        global_appearance = _global_appearance()
        settings = {"appearance_overrides": {"typography": {"enabled": True, "font": "Vazirmatn"}}}
        resolved = resolve_section_appearance(global_appearance, settings)
        self.assertEqual(resolved["font"], "Vazirmatn")
        self.assertEqual(resolved["type_scale"], "normal")
        self.assertEqual(resolved["palette_slug"], global_appearance["palette_slug"])

    def test_enabled_type_scale_only_override(self):
        global_appearance = _global_appearance()
        settings = {"appearance_overrides": {"typography": {"enabled": True, "type_scale": "compact"}}}
        resolved = resolve_section_appearance(global_appearance, settings)
        self.assertEqual(resolved["type_scale"], "compact")
        self.assertEqual(resolved["font"], "Tahoma")

    def test_enabled_both_override(self):
        global_appearance = _global_appearance()
        settings = {
            "appearance_overrides": {
                "typography": {"enabled": True, "font": "Georgia", "type_scale": "large"},
            },
        }
        resolved = resolve_section_appearance(global_appearance, settings)
        self.assertEqual(resolved["font"], "Georgia")
        self.assertEqual(resolved["type_scale"], "large")
        # only those two global keys changed
        self.assertEqual(resolved["palette_slug"], global_appearance["palette_slug"])
        self.assertEqual(resolved["color_overrides"], global_appearance["color_overrides"])
        self.assertEqual(resolved["template_slug"], global_appearance["template_slug"])

    def test_disabled_override_resolves_exactly_as_global(self):
        global_appearance = _global_appearance()
        settings = {
            "appearance_overrides": {
                "typography": {"enabled": False, "font": "Georgia", "type_scale": "large"},
            },
        }
        resolved = resolve_section_appearance(global_appearance, settings)
        self.assertEqual(resolved["font"], "Tahoma")
        self.assertEqual(resolved["type_scale"], "normal")

    def test_unrelated_global_keys_preserved(self):
        global_appearance = _global_appearance()
        settings = {
            "appearance_overrides": {
                "typography": {"enabled": True, "font": "Georgia"},
            },
        }
        resolved = resolve_section_appearance(global_appearance, settings)
        self.assertEqual(resolved["palette_slug"], "some-palette")
        self.assertEqual(resolved["color_overrides"], {"primary": "#123456"})

    def test_does_not_mutate_inputs(self):
        global_appearance = _global_appearance()
        global_copy = json.loads(json.dumps(global_appearance))
        settings = {"appearance_overrides": {"typography": {"enabled": True, "font": "Georgia"}}}
        settings_copy = json.loads(json.dumps(settings))
        resolve_section_appearance(global_appearance, settings)
        self.assertEqual(global_appearance, global_copy)
        self.assertEqual(settings, settings_copy)

    def test_malformed_persisted_override_falls_back_to_global_without_crashing(self):
        global_appearance = _global_appearance()
        settings = {"appearance_overrides": {"typography": {"enabled": True, "font": "NotARealFont"}}}
        resolved = resolve_section_appearance(global_appearance, settings)
        self.assertEqual(resolved["font"], "Tahoma")


class HeroSchemaFieldTests(SimpleTestCase):
    def test_hero_banner_has_appearance_override_advanced_field(self):
        hero = section_registry.get_definition("hero_banner")
        field = hero.settings_schema.get_field("appearance_overrides")
        self.assertIsNotNone(field)
        self.assertEqual(field.field_type, "appearance_override")
        self.assertEqual(field.group, "advanced")
        self.assertEqual(field.default, {})

    def test_other_sections_do_not_get_the_field(self):
        for key in ("rich_text", "image_slider", "faq"):
            definition = section_registry.get_definition(key)
            if definition.settings_schema is None:
                continue
            self.assertIsNone(definition.settings_schema.get_field("appearance_overrides"))


class WrapperSparseBehaviorTests(SimpleTestCase):
    def test_absent_override_preserves_pre_task7_hero_settings_shape(self):
        hero = section_registry.get_definition("hero_banner")
        cleaned = hero.validate_settings({"autoplay": False})
        self.assertNotIn("appearance_overrides", cleaned)

    def test_absent_override_default_shape_unchanged(self):
        hero = section_registry.get_definition("hero_banner")
        defaults = hero.default_settings()
        self.assertNotIn("appearance_overrides", defaults)

    def test_explicit_override_survives_the_legacy_validator_chain(self):
        hero = section_registry.get_definition("hero_banner")
        cleaned = hero.validate_settings({
            "autoplay": False,
            "appearance_overrides": {"typography": {"enabled": True, "font": "Vazirmatn"}},
        })
        self.assertEqual(
            cleaned["appearance_overrides"],
            {"typography": {"enabled": True, "font": "Vazirmatn"}},
        )

    def test_image_slider_ignores_appearance_overrides_key(self):
        # image_slider shares _validate_slider_settings with hero_banner but
        # is NOT in sections_with_capability("appearance_override").
        image_slider = section_registry.get_definition("image_slider")
        cleaned = image_slider.validate_settings({
            "appearance_overrides": {"typography": {"enabled": True, "font": "Vazirmatn"}},
        })
        self.assertNotIn("appearance_overrides", cleaned)


class RendererEffectiveAppearanceTests(R4MutationApiTestCase):
    """Integration coverage: a real persisted page with a hero_banner +
    rich_text sibling, global font=Tahoma/type_scale=normal."""

    def setUp(self):
        super().setUp()
        self.draft.appearance_config = {**(self.draft.appearance_config or {}), "font": "Tahoma", "type_scale": "normal"}
        self.draft.save(update_fields=["appearance_config"])
        self.sibling = StorefrontSection.objects.create(
            version=self.draft, section_key="rich_text", order=1,
        )

    def _items_by_key(self, page):
        items = render_service.build_page_render_items(page, self.store)
        return {item["section"].section_key: item for item in items}

    def test_no_override_hero_and_sibling_both_inherit_global(self):
        page = self.draft.get_page(StorefrontPage.PageType.HOME)
        items = self._items_by_key(page)
        hero_appearance = items["hero_banner"]["context"]["effective_section_appearance"]
        sibling_appearance = items["rich_text"]["context"]["effective_section_appearance"]
        self.assertEqual(hero_appearance["font"], "Tahoma")
        self.assertEqual(hero_appearance["type_scale"], "normal")
        self.assertEqual(sibling_appearance["font"], "Tahoma")
        self.assertEqual(sibling_appearance["type_scale"], "normal")

    def test_hero_override_does_not_leak_to_sibling(self):
        self.section.settings = {
            **self.section.settings,
            "appearance_overrides": {
                "typography": {"enabled": True, "font": "Vazirmatn", "type_scale": "compact"},
            },
        }
        self.section.save(update_fields=["settings"])

        page = self.draft.get_page(StorefrontPage.PageType.HOME)
        items = self._items_by_key(page)
        hero_appearance = items["hero_banner"]["context"]["effective_section_appearance"]
        sibling_appearance = items["rich_text"]["context"]["effective_section_appearance"]

        self.assertEqual(hero_appearance["font"], "Vazirmatn")
        self.assertEqual(hero_appearance["type_scale"], "compact")
        self.assertEqual(sibling_appearance["font"], "Tahoma")
        self.assertEqual(sibling_appearance["type_scale"], "normal")

        # unrelated global keys preserved on both
        self.assertEqual(hero_appearance["palette_slug"], sibling_appearance["palette_slug"])
        self.assertEqual(hero_appearance["color_overrides"], sibling_appearance["color_overrides"])

    def test_disabling_override_returns_hero_to_global(self):
        self.section.settings = {
            **self.section.settings,
            "appearance_overrides": {"typography": {"enabled": False}},
        }
        self.section.save(update_fields=["settings"])
        page = self.draft.get_page(StorefrontPage.PageType.HOME)
        items = self._items_by_key(page)
        hero_appearance = items["hero_banner"]["context"]["effective_section_appearance"]
        self.assertEqual(hero_appearance["font"], "Tahoma")
        self.assertEqual(hero_appearance["type_scale"], "normal")

    def test_effective_section_typography_resolved_from_appearance_registry(self):
        self.section.settings = {
            **self.section.settings,
            "appearance_overrides": {
                "typography": {"enabled": True, "type_scale": "compact"},
            },
        }
        self.section.save(update_fields=["settings"])
        page = self.draft.get_page(StorefrontPage.PageType.HOME)
        items = self._items_by_key(page)
        typography = items["hero_banner"]["context"]["effective_section_typography"]
        self.assertEqual(typography, appearance_registry.resolve_typography("compact"))

    def test_split_variant_also_carries_effective_typography(self):
        self.section.settings = {
            **self.section.settings,
            "hero_style": "split",
            "appearance_overrides": {
                "typography": {"enabled": True, "font": "Georgia"},
            },
        }
        self.section.save(update_fields=["settings"])
        page = self.draft.get_page(StorefrontPage.PageType.HOME)
        items = self._items_by_key(page)
        hero_item = items["hero_banner"]
        self.assertIn("hero_banner_split", hero_item["template_name"])
        self.assertEqual(hero_item["context"]["effective_section_appearance"]["font"], "Georgia")


class PreviewPublicSharedRenderTests(R4MutationApiTestCase):
    def test_draft_and_published_use_the_same_render_computation(self):
        self.draft.appearance_config = {**(self.draft.appearance_config or {}), "font": "Georgia", "type_scale": "large"}
        self.draft.save(update_fields=["appearance_config"])
        self.section.settings = {
            **self.section.settings,
            "appearance_overrides": {"typography": {"enabled": True, "font": "Vazirmatn"}},
        }
        self.section.save(update_fields=["settings"])

        published = StorefrontLayoutVersion.objects.create(
            layout=self.layout, version_number=999,
            status=StorefrontLayoutVersion.Status.PUBLISHED,
            appearance_config=self.draft.appearance_config,
        )
        StorefrontPage.ensure_version_pages(published)
        published_page = published.get_page(StorefrontPage.PageType.HOME)
        published_hero = StorefrontSection.objects.create(
            page=published_page, section_key="hero_banner", order=0,
            settings=self.section.settings,
        )

        draft_page = self.draft.get_page(StorefrontPage.PageType.HOME)
        draft_items = {i["section"].section_key: i for i in render_service.build_page_render_items(draft_page, self.store)}
        published_items = {i["section"].section_key: i for i in render_service.build_page_render_items(published_page, self.store)}

        self.assertEqual(
            draft_items["hero_banner"]["context"]["effective_section_appearance"]["font"],
            published_items["hero_banner"]["context"]["effective_section_appearance"]["font"],
        )
        self.assertEqual(draft_items["hero_banner"]["context"]["effective_section_appearance"]["font"], "Vazirmatn")


class MutationRegressionAppearanceOverrideTests(R4MutationApiTestCase):
    def test_successful_appearance_override_mutation(self):
        starting_revision = self.draft.edit_revision
        response = self.client.post(
            reverse("dashboard:storefront-builder-r4-mutation"),
            data=json.dumps({
                "base_revision": starting_revision,
                "mutation": {
                    "type": "section.update_settings",
                    "section_id": self.section.pk,
                    "patch": {
                        "appearance_overrides": {
                            "typography": {"enabled": True, "font": "Vazirmatn", "type_scale": "compact"},
                        },
                    },
                },
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["new_revision"], starting_revision + 1)

        self.section.refresh_from_db()
        self.assertEqual(
            self.section.settings["appearance_overrides"],
            {"typography": {"enabled": True, "font": "Vazirmatn", "type_scale": "compact"}},
        )
        # existing Hero wrapper settings survive
        self.assertIn("responsive", self.section.settings)
        self.assertEqual(self.section.settings["hero_style"], "overlay")

        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, starting_revision + 1)

    def test_invalid_font_is_rejected_with_no_mutation(self):
        starting_revision = self.draft.edit_revision
        original_settings = dict(self.section.settings)
        response = self.client.post(
            reverse("dashboard:storefront-builder-r4-mutation"),
            data=json.dumps({
                "base_revision": starting_revision,
                "mutation": {
                    "type": "section.update_settings",
                    "section_id": self.section.pk,
                    "patch": {
                        "appearance_overrides": {
                            "typography": {"enabled": True, "font": "ComicSans"},
                        },
                    },
                },
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_settings")
        self.section.refresh_from_db()
        self.assertEqual(self.section.settings, original_settings)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, starting_revision)
