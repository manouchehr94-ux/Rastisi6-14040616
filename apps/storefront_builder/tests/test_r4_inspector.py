import dataclasses
import json
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse

from apps.storefront_builder import section_registry as section_registry_module
from apps.storefront_builder.models import StorefrontLayoutVersion, StorefrontPage, StorefrontSection
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.settings_schema import SettingsField, SettingsSchema
from apps.stores.models import Store

from .test_r4_mutation_api import R4MutationApiTestCase


def _inspector_url(pk):
    return reverse("dashboard:storefront-builder-r4-section-inspector", args=[pk])


class RichTextInspectorTests(R4MutationApiTestCase):
    def setUp(self):
        super().setUp()
        self.rich_text_section = StorefrontSection.objects.create(
            version=self.draft, section_key="rich_text", order=1,
        )

    def test_rich_text_inspector_shell_and_tabs(self):
        response = self.client.get(_inspector_url(self.rich_text_section.pk))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        self.assertContains(response, "data-r4-section-inspector")
        self.assertContains(response, f'data-r4-section-id="{self.rich_text_section.pk}"')
        self.assertContains(response, 'data-r4-tab="basic"')
        self.assertContains(response, 'data-r4-tab="advanced"')
        self.assertContains(response, 'aria-selected="true"')
        self.assertContains(response, 'aria-selected="false"')

        # Advanced panel is initially hidden; Basic is not.
        advanced_idx = content.index('data-r4-tab-panel="advanced"')
        self.assertIn("hidden", content[advanced_idx:advanced_idx + 60])

        self.assertContains(response, 'data-r4-field-key="body_html"')
        self.assertContains(response, 'data-r4-field-type="rich_text"')
        self.assertContains(response, "<textarea")
        self.assertContains(response, "متن")  # schema label

        self.assertNotContains(response, "<iframe")
        self.assertNotContains(response, "storefront-builder/sections/")
        self.assertNotContains(response, "sfb-modal")
        self.assertNotContains(response, '<form')


class HeroInspectorGroupSplitTests(R4MutationApiTestCase):
    def test_basic_and_advanced_fields_come_from_schema_group(self):
        response = self.client.get(_inspector_url(self.section.pk))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        basic_start = content.index('data-r4-tab-panel="basic"')
        advanced_start = content.index('data-r4-tab-panel="advanced"')
        basic_chunk = content[basic_start:advanced_start]
        advanced_chunk = content[advanced_start:]

        for key in ("hero_style", "autoplay"):
            self.assertIn(f'data-r4-field-key="{key}"', basic_chunk)
        for key in ("interval_ms", "show_arrows", "show_dots", "loop", "text_position"):
            self.assertIn(f'data-r4-field-key="{key}"', advanced_chunk)

        # None of the advanced-only keys leak into the basic panel.
        for key in ("interval_ms", "show_arrows", "show_dots", "loop", "text_position"):
            self.assertNotIn(f'data-r4-field-key="{key}"', basic_chunk)


class CurrentValueHydrationTests(R4MutationApiTestCase):
    def test_hero_field_values_reflect_persisted_non_default_settings(self):
        self.section.settings = {
            **self.section.settings,
            "autoplay": False,
            "interval_ms": 4500,
            "text_position": "center",
        }
        self.section.save(update_fields=["settings"])

        response = self.client.get(_inspector_url(self.section.pk))
        content = response.content.decode()
        script_start = content.index('id="r4InspectorFieldValues"')
        json_start = content.index(">", script_start) + 1
        json_end = content.index("</script>", json_start)
        field_values = json.loads(content[json_start:json_end])

        self.assertIs(field_values["autoplay"], False)
        self.assertEqual(field_values["interval_ms"], 4500)
        self.assertEqual(field_values["text_position"], "center")
        # Untouched fields still surface their schema default.
        self.assertEqual(field_values["hero_style"], "overlay")

    def test_rich_text_field_values_reflect_persisted_body_html(self):
        rich_text_section = StorefrontSection.objects.create(
            version=self.draft, section_key="rich_text", order=1,
            settings={"body_html": "<p>متن فعلی</p>"},
        )
        response = self.client.get(_inspector_url(rich_text_section.pk))
        content = response.content.decode()
        script_start = content.index('id="r4InspectorFieldValues"')
        json_start = content.index(">", script_start) + 1
        json_end = content.index("</script>", json_start)
        field_values = json.loads(content[json_start:json_end])
        self.assertEqual(field_values["body_html"], "<p>متن فعلی</p>")


class ActiveDraftTenantScopingTests(R4MutationApiTestCase):
    def test_foreign_store_section_is_not_found(self):
        other_store = Store.objects.create(
            name="فروشگاه دیگر بازرس", slug="r4-inspector-other-store",
            admin_subdomain="r4-inspector-other-store",
        )
        other_draft = svc.get_or_create_draft(other_store)
        other_section = StorefrontSection.objects.create(
            version=other_draft, section_key="hero_banner", order=0,
        )
        response = self.client.get(_inspector_url(other_section.pk))
        self.assertEqual(response.status_code, 404)

    def test_published_version_section_is_not_found(self):
        published = StorefrontLayoutVersion.objects.create(
            layout=self.layout, version_number=999,
            status=StorefrontLayoutVersion.Status.PUBLISHED,
        )
        StorefrontPage.ensure_version_pages(published)
        published_section = StorefrontSection.objects.create(
            version=published, section_key="hero_banner", order=0,
        )
        response = self.client.get(_inspector_url(published_section.pk))
        self.assertEqual(response.status_code, 404)


class FeatureGateTests(R4MutationApiTestCase):
    def test_inspector_unavailable_when_r4_gate_is_off(self):
        self.layout.r4_editor_enabled = False
        self.layout.save(update_fields=["r4_editor_enabled"])
        response = self.client.get(_inspector_url(self.section.pk))
        self.assertEqual(response.status_code, 404)


class NonSchemaSectionTests(R4MutationApiTestCase):
    def test_single_banner_section_inspector_is_not_found(self):
        # ``faq`` was this test's original representative — Task 6 Group D
        # later gave it a real schema (the new ``repeater`` field type's
        # first user), so it no longer qualifies. ``single_banner`` is the
        # correct representative now: it has an explicit FIXED/STATIC
        # disposition and will never legitimately gain a schema (see its
        # SectionDefinition comment in section_registry.py).
        single_banner_section = StorefrontSection.objects.create(
            version=self.draft, section_key="single_banner", order=1,
        )
        response = self.client.get(_inspector_url(single_banner_section.pk))
        self.assertEqual(response.status_code, 404)


class MethodContractTests(R4MutationApiTestCase):
    def test_post_to_inspector_endpoint_is_405(self):
        response = self.client.post(_inspector_url(self.section.pk))
        self.assertEqual(response.status_code, 405)


class UnsupportedWidgetContractTests(R4MutationApiTestCase):
    def test_unsupported_field_type_raises_improperly_configured(self):
        real_definition = section_registry_module.get_definition("hero_banner")
        bad_schema = SettingsSchema(fields=(
            SettingsField("swatch", "رنگ", "color", "basic"),
        ))
        bad_definition = dataclasses.replace(real_definition, settings_schema=bad_schema)
        with patch(
            "apps.storefront_builder.r4_views.section_registry.get_definition",
            return_value=bad_definition,
        ):
            with self.assertRaises(ImproperlyConfigured):
                self.client.get(_inspector_url(self.section.pk))


class CsrfCookieOnEditorLoadTests(R4MutationApiTestCase):
    def test_r4_editor_response_sets_csrf_cookie(self):
        response = self.client.get(reverse("dashboard:storefront-builder-r4-editor"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(settings.CSRF_COOKIE_NAME, response.cookies)


class R4EditorJsSourceContractTests(R4MutationApiTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.js_source = Path(
            settings.BASE_DIR,
            "apps/storefront_builder/static/storefront_builder/r4_editor.js",
        ).read_text(encoding="utf-8")

    def test_open_section_entry_point_exists(self):
        self.assertIn("openSection = function", self.js_source)

    def test_accepts_both_select_section_and_open_section_settings(self):
        self.assertIn("sfb:selectSection", self.js_source)
        self.assertIn("sfb:openSectionSettings", self.js_source)

    def test_does_not_handle_out_of_scope_preview_events(self):
        for event_type in ("sfb:openEntityEditor", "sfb:openHeaderSettings", "sfb:openFooterSettings"):
            self.assertNotIn(event_type, self.js_source)

    def test_validates_message_origin(self):
        self.assertIn("evt.origin", self.js_source)
        self.assertIn("window.location.origin", self.js_source)

    def test_validates_message_source_against_preview_frame(self):
        self.assertIn("evt.source", self.js_source)
        self.assertIn("previewFrame.contentWindow", self.js_source)

    def test_has_one_enqueue_and_one_send_mutation_function(self):
        self.assertEqual(self.js_source.count("enqueueMutation = function"), 1)
        self.assertEqual(self.js_source.count("sendMutation = function"), 1)

    def test_base_revision_uses_in_memory_revision(self):
        self.assertIn("base_revision: R4.revision", self.js_source)

    def test_revision_updated_from_server_response_only(self):
        self.assertIn("new_revision", self.js_source)
        self.assertIn("R4.revision = result.body.new_revision", self.js_source)

    def test_explicit_409_conflict_handling(self):
        self.assertIn("409", self.js_source)
        self.assertIn("conflict", self.js_source)

    def test_conflict_blocks_further_automatic_mutation_without_retry(self):
        # The same conflict guard must gate both enqueueing new mutations
        # and sending them — no automatic replay of the stale mutation.
        self.assertGreaterEqual(self.js_source.count("if (R4.conflict) return"), 2)
        self.assertNotIn("retry", self.js_source.lower())

    def test_reload_is_the_explicit_conflict_recovery_action(self):
        self.assertIn("window.location.reload()", self.js_source)

    def test_uses_task5_mutate_endpoint_and_not_r3_settings_endpoint(self):
        self.assertIn("mutate/", self.js_source)
        self.assertNotIn("section-settings", self.js_source)
        self.assertNotIn("/admin-portal/", self.js_source)

    def test_does_not_open_a_modal(self):
        self.assertNotIn("modal", self.js_source.lower())


# ------------------------------------------------------------------------
# Task 6 visual/product correction pass — the owner rejected the raw
# unstyled screenshots (visible <h2>/<p> tags, no sidebar collapse, no
# Inspector polish). This is a presentation-layer-only correction; the
# functional Task 6 contracts above must keep passing unmodified.
# ------------------------------------------------------------------------


class RichTextUsesMerchantEditorTests(R4MutationApiTestCase):
    def setUp(self):
        super().setUp()
        self.rich_text_section = StorefrontSection.objects.create(
            version=self.draft, section_key="rich_text", order=1,
        )

    def test_rich_text_field_requests_existing_ckeditor_mount_contract(self):
        response = self.client.get(_inspector_url(self.rich_text_section.pk))
        self.assertContains(response, 'x-data="storefrontRichTextEditor()"')
        self.assertContains(response, 'x-init="mount()"')
        self.assertContains(response, "sfb-rich-editor")
        # The backing textarea must still carry the R4 field contract so
        # hydration/mutation keep working — this is additive styling, not
        # a second rich-text system.
        self.assertContains(response, 'data-r4-field-key="body_html"')
        self.assertContains(response, 'data-r4-field-type="rich_text"')


class R4EditorSidebarToggleMarkupTests(R4MutationApiTestCase):
    def test_editor_shell_includes_accessible_sidebar_toggle(self):
        response = self.client.get(reverse("dashboard:storefront-builder-r4-editor"))
        self.assertContains(response, 'id="r4SidebarToggle"')
        self.assertContains(response, "aria-label=")
        self.assertContains(response, 'aria-expanded="false"')


class R4EditorJsSidebarContractTests(R4MutationApiTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.js_source = Path(
            settings.BASE_DIR,
            "apps/storefront_builder/static/storefront_builder/r4_editor.js",
        ).read_text(encoding="utf-8")

    def test_js_toggles_r4_specific_sidebar_expanded_state(self):
        self.assertIn("r4SidebarToggle", self.js_source)
        self.assertIn("r4SidebarExpanded", self.js_source)

    def test_js_does_not_persist_sidebar_state_across_loads(self):
        self.assertNotIn("localStorage", self.js_source)

    def test_write_endpoints_are_only_the_sanctioned_r4_targets(self):
        # R4 Task 11 legitimately adds two more sanctioned POST endpoints
        # (history/, publish/) alongside the original mutate/ — this guard
        # is "no ROGUE extra write path", not "exactly one POST forever".
        self.assertIn("mutate/", self.js_source)
        self.assertIn("history/", self.js_source)
        self.assertIn("publish/", self.js_source)
        self.assertEqual(self.js_source.count("method: 'POST'"), 3)

    def test_rich_text_save_flows_through_enqueue_mutation(self):
        self.assertIn("sfb-rich-editor", self.js_source)
        self.assertIn("focusout", self.js_source)
        # The focusout handler must itself call the same single queue —
        # not a second/parallel save path.
        focusout_idx = self.js_source.index("focusout")
        self.assertIn("enqueueMutation", self.js_source[focusout_idx:focusout_idx + 800])


class BaseAdminTemplateUntouchedTests(R4MutationApiTestCase):
    def test_base_admin_template_has_no_r4_specific_markup(self):
        base_admin_source = Path(
            settings.BASE_DIR,
            "apps/dashboard/templates/dashboard/base_admin.html",
        ).read_text(encoding="utf-8")
        self.assertNotIn("r4Sidebar", base_admin_source)
        self.assertNotIn("R4EditorSidebar", base_admin_source)
        self.assertNotIn("data-r4", base_admin_source)


class InspectorArchitectureUnchangedByPolishTests(R4MutationApiTestCase):
    def test_inspector_still_has_exactly_basic_and_advanced_tabs(self):
        response = self.client.get(_inspector_url(self.section.pk))
        self.assertContains(response, 'data-r4-tab="basic"')
        self.assertContains(response, 'data-r4-tab="advanced"')
        self.assertEqual(response.content.decode().count('role="tab"'), 2)

    def test_inspector_still_has_no_r3_modal_iframe_or_form_action(self):
        response = self.client.get(_inspector_url(self.section.pk))
        self.assertNotContains(response, "<iframe")
        self.assertNotContains(response, "sfb-modal")
        self.assertNotContains(response, "<form")


# ------------------------------------------------------------------------
# Task 7 — generic appearance_override Inspector widget (typography-only
# first slice). Hero Advanced gains one typed compound field; every other
# field type's rendering/unsupported-type contract must stay unchanged.
# ------------------------------------------------------------------------


class AppearanceOverrideWidgetTests(R4MutationApiTestCase):
    def test_hero_advanced_renders_typed_typography_controls(self):
        response = self.client.get(_inspector_url(self.section.pk))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        advanced_start = content.index('data-r4-tab-panel="advanced"')
        advanced_chunk = content[advanced_start:]

        self.assertIn('data-r4-field-key="appearance_overrides"', advanced_chunk)
        self.assertIn('data-r4-field-type="appearance_override"', advanced_chunk)
        self.assertIn("data-r4-appearance-enabled", advanced_chunk)
        self.assertIn("data-r4-appearance-font", advanced_chunk)
        self.assertIn("data-r4-appearance-type-scale", advanced_chunk)
        # Curated font/type-scale choices are real <option> controls, not a
        # free-text/JSON/CSS field.
        self.assertIn("Vazirmatn", advanced_chunk)
        self.assertIn("<select", advanced_chunk)

    def test_no_json_or_css_free_text_input_for_appearance_override(self):
        response = self.client.get(_inspector_url(self.section.pk))
        content = response.content.decode()
        self.assertNotIn('data-r4-field-type="json"', content)
        # No CSS/style free-text input anywhere in the appearance widget.
        advanced_start = content.index('data-r4-tab-panel="advanced"')
        advanced_chunk = content[advanced_start:]
        appearance_start = advanced_chunk.index('data-r4-field-type="appearance_override"')
        appearance_chunk = advanced_chunk[appearance_start:appearance_start + 1500]
        self.assertNotIn("<textarea", appearance_chunk)
        self.assertNotIn('type="text"', appearance_chunk)

    def test_uses_no_r3_endpoint_and_no_new_endpoint(self):
        response = self.client.get(_inspector_url(self.section.pk))
        content = response.content.decode()
        self.assertNotIn("/admin-portal/", content)
        self.assertNotIn("section-settings", content)

    def test_inherited_appearance_projection_is_typed_and_minimal(self):
        response = self.client.get(_inspector_url(self.section.pk))
        content = response.content.decode()
        script_start = content.index('id="r4InspectorInheritedAppearance"')
        json_start = content.index(">", script_start) + 1
        json_end = content.index("</script>", json_start)
        inherited = json.loads(content[json_start:json_end])

        self.assertIn("appearance_overrides", inherited)
        projection = inherited["appearance_overrides"]
        self.assertEqual(set(projection), {"font", "type_scale"})

    def test_rich_text_inspector_unaffected_by_appearance_override_support(self):
        rich_text_section = StorefrontSection.objects.create(
            version=self.draft, section_key="rich_text", order=1,
        )
        response = self.client.get(_inspector_url(rich_text_section.pk))
        content = response.content.decode()
        self.assertNotIn("data-r4-appearance-enabled", content)
        self.assertIn('data-r4-field-key="body_html"', content)

    def test_color_field_type_remains_unsupported(self):
        real_definition = section_registry_module.get_definition("hero_banner")
        bad_schema = SettingsSchema(fields=(
            SettingsField("swatch", "رنگ", "color", "basic"),
        ))
        bad_definition = dataclasses.replace(real_definition, settings_schema=bad_schema)
        with patch(
            "apps.storefront_builder.r4_views.section_registry.get_definition",
            return_value=bad_definition,
        ):
            with self.assertRaises(ImproperlyConfigured):
                self.client.get(_inspector_url(self.section.pk))


# ------------------------------------------------------------------------
# Task 9 — Product/Brand now attach a settings_schema containing a typed
# resource_source ("source") field. The generic Inspector must render it
# (no 500, no Product-/Brand-specific template branch) as a clean
# READ-ONLY summary — Task 10 builds the actual interactive Picker.
# ------------------------------------------------------------------------


class ResourceSourceWidgetTests(R4MutationApiTestCase):
    def setUp(self):
        super().setUp()
        self.product_section = StorefrontSection.objects.create(
            version=self.draft, section_key="product_section", order=1,
            settings={
                "data_source": "manual", "source_id": None, "product_ids": [7, 3],
                "item_limit": 8, "display_mode": "carousel", "show_view_all": True,
                "title": "", "subtitle": "", "carousel_autoplay": False,
                "carousel_interval_ms": 3500, "carousel_show_arrows": True,
                "header_position": "above",
            },
        )
        self.brand_section = StorefrontSection.objects.create(
            version=self.draft, section_key="brand_carousel", order=2,
            settings={"title": "", "display_mode": "grid", "show_view_all": False, "brand_ids": []},
        )

    def test_product_inspector_returns_200_with_no_r3_modal_or_form(self):
        response = self.client.get(_inspector_url(self.product_section.pk))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<iframe")
        self.assertNotContains(response, "sfb-modal")
        self.assertNotContains(response, "<form")

    def test_brand_inspector_returns_200_with_no_r3_modal_or_form(self):
        response = self.client.get(_inspector_url(self.brand_section.pk))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<iframe")
        self.assertNotContains(response, "sfb-modal")
        self.assertNotContains(response, "<form")

    def test_resource_source_rendered_generically_not_by_section_name(self):
        template_source = Path(
            settings.BASE_DIR,
            "apps/storefront_builder/templates/dashboard/storefront_builder/r4/partials/settings_field.html",
        ).read_text(encoding="utf-8")
        self.assertNotIn("product_section", template_source)
        self.assertNotIn("brand_carousel", template_source)
        self.assertIn('field.field_type == "resource_source"', template_source)

    def test_product_current_value_projected_from_legacy_manual_settings(self):
        response = self.client.get(_inspector_url(self.product_section.pk))
        content = response.content.decode()
        self.assertIn("دستی", content)  # mode label
        self.assertIn("محصول", content)  # kind label
        self.assertNotIn("جدیدترین", content)  # NOT the schema default ("newest")

    def test_brand_current_value_projected_from_legacy_empty_brand_ids(self):
        response = self.client.get(_inspector_url(self.brand_section.pk))
        content = response.content.decode()
        self.assertIn("خودکار", content)  # mode label
        self.assertIn("همه‌ی موارد فعال", content)  # all_active auto_rule label
        self.assertIn("برند", content)  # kind label

    def test_no_picker_search_or_overlay_markup(self):
        for pk in (self.product_section.pk, self.brand_section.pk):
            response = self.client.get(_inspector_url(pk))
            content = response.content.decode()
            self.assertNotIn("data-r4-picker", content)
            self.assertNotIn("data-r4-resource-search", content)
            self.assertNotIn('type="search"', content)
            self.assertNotIn("data-r4-manual-select", content)

    def test_no_new_r4_urls_were_added_for_the_picker(self):
        from apps.dashboard import urls as dashboard_urls
        url_names = {pattern.name for pattern in dashboard_urls.urlpatterns if getattr(pattern, "name", None)}
        for forbidden in ("storefront-builder-r4-resource-search", "storefront-builder-r4-picker"):
            self.assertNotIn(forbidden, url_names)

    def test_resource_source_field_is_read_only_no_input_control(self):
        response = self.client.get(_inspector_url(self.product_section.pk))
        content = response.content.decode()
        basic_start = content.index('data-r4-tab-panel="basic"')
        advanced_start = content.index('data-r4-tab-panel="advanced"')
        source_field_start = content.index('data-r4-field-type="resource_source"', basic_start)
        self.assertLess(source_field_start, advanced_start)
        next_field_start = content.index('data-r4-field-row', source_field_start + 1)
        source_chunk = content[source_field_start:next_field_start]
        self.assertNotIn("<input", source_chunk)
        self.assertNotIn("<select", source_chunk)
        self.assertNotIn("<textarea", source_chunk)



class BrandCarouselV02InspectorFilteringTests(R4MutationApiTestCase):
    """Phase 3 (V02) — the "مشاهده همه" (show_view_all) control is only
    offered when the active variant/destination can render an actionable
    anchor. Read-only filtering; dormant stored values are never mutated."""

    def _brand_section(self, *, display_mode="grid", show_view_all=False, destination=None):
        settings = {
            "title": "", "display_mode": display_mode,
            "show_view_all": show_view_all, "brand_ids": [],
        }
        if destination is not None:
            settings["destination"] = destination
        return StorefrontSection.objects.create(
            version=self.draft, section_key="brand_carousel", order=1, settings=settings,
        )

    def test_grid_with_valid_destination_offers_control(self):
        section = self._brand_section(
            display_mode="grid", destination={"destination_type": "search"},
        )
        response = self.client.get(_inspector_url(section.pk))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-r4-field-key="show_view_all"')

    def test_beauty_tabs_hides_control(self):
        section = self._brand_section(
            display_mode="beauty_tabs", destination={"destination_type": "search"},
        )
        response = self.client.get(_inspector_url(section.pk))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'data-r4-field-key="show_view_all"')

    def test_grid_without_resolving_destination_hides_control(self):
        section = self._brand_section(display_mode="grid", destination={"destination_type": "none"})
        response = self.client.get(_inspector_url(section.pk))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'data-r4-field-key="show_view_all"')

    def test_hiding_control_does_not_mutate_stored_settings(self):
        section = self._brand_section(
            display_mode="beauty_tabs", show_view_all=True,
            destination={"destination_type": "search"},
        )
        before = dict(section.settings)
        self.client.get(_inspector_url(section.pk))
        section.refresh_from_db()
        self.assertEqual(section.settings, before)
        self.assertTrue(section.settings["show_view_all"])  # dormant, intact
