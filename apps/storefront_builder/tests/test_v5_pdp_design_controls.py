"""V5 — PDP design controls (بستهٔ ۱): ``product_main`` + ``product_description`` are still ONE Section each, now with generic,
Inspector-editable presentation settings (``pdp_settings``).

Pinned here: the settings vocabulary and its defaults (a Store that never touched them renders exactly what it rendered before), the
write-time cleaner and the never-raising render resolver, the single R4 mutation path (one Revision, Undo / Redo, strict Store scoping,
refusal of out-of-vocabulary input), Draft preview vs Published isolation, the Inspector wiring (tabs, repeater projection), the
accessibility / no-JS contract of the description modes, that no business data (price, stock, variants, the add-to-cart form) is read
from settings, and that the stylesheet has a rule for every value the renderer can emit and names no store or brand."""

import json
import re
from decimal import Decimal
from pathlib import Path

from django.test import Client, SimpleTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Brand, Category, Product, Vendor
from apps.storefront_builder import pdp_settings, section_registry, workspace_layout
from apps.storefront_builder.models import StorefrontPage, StorefrontSection
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services import r4_mutation_service, section_structure_service
from apps.stores.models import Store, StoreDomain

from .test_media_views import HOST, MediaViewsTestCase

APP = Path(__file__).resolve().parents[1]
CSS_RAW = (APP.parent / "catalog" / "static" / "css" / "product_detail.css").read_text(encoding="utf-8")
CSS = re.sub(r"/\*.*?\*/", "", CSS_RAW, flags=re.S)      # rules only — comments may legitimately quote selectors
NEW_CSS = ".qty[hidden]{display:none}" + CSS.split(".qty[hidden]{display:none}", 1)[1]        # the V5 PDP block (rules only)
NEW_CSS_WITH_COMMENTS = CSS_RAW.split("V5 — PDP design controls", 1)[1]
PUBLIC_HOST = "pdp-controls-public.example.com"
PDP = StorefrontPage.PageType.PRODUCT_DETAIL


def _pdp_tag(html):
    """The opening tag of the ``.pdp`` grid (the one element carrying the layout data attributes)."""
    match = re.search(r'<div class="pdp"[^>]*>', html, re.S)
    return match.group(0) if match else ""


def _tabs_tag(html):
    match = re.search(r'<div class="pdp-tabs"[^>]*>', html, re.S)
    return match.group(0) if match else ""


def _data_attrs(tag):
    return dict(re.findall(r'data-([a-z-]+)="([^"]*)"', tag))


class _PdpBase(MediaViewsTestCase):
    def setUp(self):
        super().setUp()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="pdpc-shop")
        self.category = Category.objects.create(store=self.store, name="دسته", slug="pdpc-cat")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالای کنترل‌های طراحی", slug="pdpc-product",
            sku="PDPC-1", price=Decimal("300000"), stock=5, status=Product.Status.ACTIVE,
            description="<p>توضیحات واقعی کالای آزمایشی</p>",
        )
        self.main = self._section("product_main")
        self.desc = self._section("product_description")

    def _section(self, key):
        page = self.draft.get_page(PDP)
        section = page.sections.filter(section_key=key).first()
        return section or section_structure_service.add_section(draft=self.draft, section_key=key, page_type=PDP)

    def _revision(self):
        self.draft.refresh_from_db()
        return self.draft.edit_revision

    def _update(self, section, patch):
        return r4_mutation_service.apply_mutation(
            store=self.store, actor=self.staff, base_revision=self._revision(),
            mutation={"type": "section.update_settings", "section_id": section.pk, "patch": patch},
        )

    def _history(self, command):
        return self.client.post(
            reverse("dashboard:storefront-builder-r4-history"),
            data=json.dumps({"base_revision": self._revision(), "command": command}), content_type="application/json",
        )

    def _preview(self):
        response = self.client.get(reverse("dashboard:storefront-builder-preview") + "?page=product_detail")
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def _stored(self, section):
        section.refresh_from_db()
        return section.settings or {}


# ------------------------------------------------------------------------------------------------------------------------------
class SettingsVocabularyTests(SimpleTestCase):
    def test_every_default_is_a_member_of_its_own_choices_and_is_the_pre_existing_behaviour(self):
        for table in (pdp_settings.PRODUCT_MAIN_CHOICES, pdp_settings.PRODUCT_DESCRIPTION_CHOICES):
            for key, _label, choices, default in table:
                self.assertIn(default, [value for value, _l in choices], key)
        defaults = {key: default for key, _l, _c, default in pdp_settings.PRODUCT_MAIN_CHOICES}
        # the values the storefront rendered before any of these controls existed
        self.assertEqual(defaults["layout_variant"], "standard")
        self.assertEqual(defaults["gallery_position"], "start")
        self.assertEqual(defaults["gallery_split"], "equal")
        self.assertEqual(defaults["thumbs_position"], "auto")
        self.assertEqual(defaults["info_panel"], "plain")
        self.assertEqual(defaults["qty_layout"], "stacked")
        self.assertEqual(defaults["cta_width"], "full")
        # package-1 switches are all ON (everything the page showed stays shown); the three V5 six-site-kit purchase-support blocks are OFF
        # (an existing Store never gains them) and render nothing at all unless a merchant / recipe switches them on
        self.assertEqual({k for k, _l, default in pdp_settings.PRODUCT_MAIN_SWITCHES if default is not True},
                         {"show_low_stock_alert", "show_free_shipping_notice", "show_contact_buttons", "gallery_lightbox"})
        self.assertTrue(all(default is False for k, _l, default in pdp_settings.PRODUCT_MAIN_SWITCHES
                            if k in {"show_low_stock_alert", "show_free_shipping_notice", "show_contact_buttons", "gallery_lightbox"}))
        self.assertEqual({key: d for key, _l, _c, d in pdp_settings.PRODUCT_DESCRIPTION_CHOICES}["layout_mode"], "tabs")

    def test_schema_fields_mirror_the_vocabulary_exactly(self):
        main_keys = {f.key for f in section_registry.get_definition("product_main").settings_schema.fields}
        self.assertTrue(set(pdp_settings.PRODUCT_MAIN_SETTING_KEYS) <= main_keys)
        for field in section_registry.get_definition("product_main").settings_schema.fields:
            if field.key in pdp_settings.PRODUCT_MAIN_SETTING_KEYS and field.field_type == "choice":
                table = {key: (choices, default) for key, _l, choices, default in pdp_settings.PRODUCT_MAIN_CHOICES}
                self.assertEqual(field.choices, table[field.key][0], field.key)
                self.assertEqual(field.default, table[field.key][1], field.key)

    def test_resolver_never_raises_and_falls_back_to_defaults(self):
        for garbage in (None, [], "x", 7, {"cta_size": "huge", "show_sku": "maybe", "gallery_split": ["a"], "layout_variant": 3}):
            view = pdp_settings.resolve_product_main_view(garbage)
            self.assertEqual(view["cta_size"], "normal")
            self.assertEqual(view["layout_variant"], "standard")
            self.assertTrue(view["show_sku"])
            self.assertEqual(view["attrs"], [])
            description = pdp_settings.resolve_product_description_view(garbage)
            self.assertEqual(description["layout_mode"], "tabs")
            self.assertEqual(description["attrs"], [])

    def test_attributes_are_written_only_when_a_value_differs_from_its_default(self):
        self.assertEqual(pdp_settings.resolve_product_main_view({})["attrs"], [])
        view = pdp_settings.resolve_product_main_view(
            {"gallery_position": "end", "cta_size": "large", "gallery_sticky": False, "info_panel": "plain"},
        )
        self.assertEqual(dict(view["attrs"]), {"gallery-pos": "end", "cta-size": "large", "gallery-sticky": "off"})

    def test_write_time_cleaner_keeps_other_keys_and_never_materialises_defaults(self):
        self.assertEqual(pdp_settings.clean_product_main_settings({}), {})
        kept = pdp_settings.clean_product_main_settings({"legacy_unknown": [1, 2], "cta_size": "nope", "show_sku": "false"})
        self.assertEqual(kept, {"legacy_unknown": [1, 2], "cta_size": "normal", "show_sku": False})
        with self.assertRaises(ValueError):
            pdp_settings.clean_product_main_settings("not a dict")

    def test_description_rows_are_deduplicated_ordered_trimmed_and_real(self):
        rows = pdp_settings.effective_description_sections([
            {"key": "review", "label": "  دیدگاه‌ها  ", "visible": True},
            {"key": "bogus", "label": "x"},
            {"key": "review", "label": "تکراری"},
            {"key": "desc", "visible": "false"},
            "garbage",
        ])
        self.assertEqual([r["key"] for r in rows], ["review", "desc", "spec", "brand"])
        self.assertEqual(rows[0]["label"], "دیدگاه‌ها")
        self.assertFalse(rows[1]["visible"])
        self.assertEqual(rows[2]["label"], pdp_settings.PRODUCT_DESCRIPTION_DEFAULT_LABELS["spec"])
        self.assertFalse(rows[3]["visible"], "«برند» is OFF unless the merchant lists it — an existing Store never gains it")
        view = pdp_settings.resolve_product_description_view({}, brand_available=True)
        self.assertEqual([s["key"] for s in view["sections"]], ["desc", "spec", "review"])
        listed = pdp_settings.resolve_product_description_view({"sections": [{"key": "brand"}]}, brand_available=True)
        self.assertEqual([s["key"] for s in listed["sections"]], ["brand", "desc", "spec", "review"])
        unavailable = pdp_settings.resolve_product_description_view({"sections": [{"key": "brand"}]}, brand_available=False)
        self.assertNotIn("brand", [s["key"] for s in unavailable["sections"]], "no empty or decorative tab")

    def test_the_inspector_projection_shows_the_effective_rows_with_blank_default_labels(self):
        rows = pdp_settings.project_description_sections_for_inspector({})["sections"]
        self.assertEqual([r["key"] for r in rows], ["desc", "spec", "review", "brand"])
        self.assertTrue(all(r["label"] == "" for r in rows))
        self.assertEqual([r["visible"] for r in rows], [True, True, True, False])


class WorkspacePlacementTests(SimpleTestCase):
    def test_new_controls_land_in_the_expected_inspector_cards(self):
        fields = {f.key: f for f in section_registry.get_definition("product_main").settings_schema.fields}
        for key in ("gallery_position", "thumbs_position", "info_panel", "price_layout", "qty_layout", "option_shape", "cta_size", "gallery_sticky"):
            self.assertEqual(workspace_layout.classify_field(fields[key]), "layout", key)
        for key in ("show_breadcrumb", "show_sku", "show_quantity", "show_mobile_sticky_bar"):
            self.assertEqual(workspace_layout.classify_field(fields[key]), "source", key)
        description = {f.key: f for f in section_registry.get_definition("product_description").settings_schema.fields}
        for key in ("layout_mode", "tab_style", "tab_align", "panel_style"):
            self.assertEqual(workspace_layout.classify_field(description[key]), "layout", key)
        self.assertEqual(workspace_layout.classify_field(description["sections"]), "items")

    def test_no_other_section_field_was_reclassified(self):
        pdp = {"product_main", "product_description"}
        pattern = re.compile(r"^(gallery|thumbs|info|price|qty|option|cta|tab|panel)_[a-z_]+$")
        for definition in section_registry.list_definitions():
            if definition.key in pdp or definition.settings_schema is None:
                continue
            for field in definition.settings_schema.fields:
                self.assertIsNone(pattern.match(field.key), f"{definition.key}.{field.key} now matches the PDP layout prefixes")


class RegistryContractTests(SimpleTestCase):
    def test_both_stay_single_unified_sections_with_the_existing_flags(self):
        main = section_registry.get_definition("product_main")
        self.assertFalse(main.removable)
        self.assertFalse(main.duplicable)
        self.assertEqual(main.max_instances, 1)
        self.assertEqual(main.page_types, frozenset({"product_detail"}))
        description = section_registry.get_definition("product_description")
        self.assertEqual(description.max_instances, 1)
        self.assertEqual(description.page_types, frozenset({"product_detail"}))

    def test_product_main_stays_protected_from_a_free_section_background(self):
        # spec §59: purchase-critical sections never get an arbitrary fill (it can make the fixed buying text unreadable)
        self.assertNotIn("background", section_registry.get_definition("product_main").capabilities)
        self.assertNotIn("spacing", section_registry.get_definition("product_main").capabilities)
        self.assertIn("design_frame", section_registry.get_definition("product_main").capabilities)

    def test_design_block_is_reused_not_reinvented(self):
        for capability in ("design_text", "design_buttons", "design_price", "design_image_ratio", "design_image_fit"):
            self.assertIn(capability, section_registry.get_definition("product_main").capabilities)
        for capability in ("design_frame", "design_text", "background", "spacing"):
            self.assertIn(capability, section_registry.get_definition("product_description").capabilities)

    def test_the_template_never_reads_business_data_from_settings(self):
        main = (APP / "templates" / "storefront_builder" / "sections" / "product_main.html").read_text(encoding="utf-8")
        for needle in ("settings.price", "settings.stock", "settings.variant", "settings.product", "settings.sku"):
            self.assertNotIn(needle, main)
        self.assertEqual(main.count('x-data="variantSelector('), 1, "one unified variantSelector")
        self.assertEqual(main.count("hx-post="), 1, "one real add-to-cart form")


# ------------------------------------------------------------------------------------------------------------------------------
class ProductMainDefaultsAreUnchangedTests(_PdpBase):
    def test_a_store_that_never_touched_the_controls_renders_the_historical_markup(self):
        html = self._preview()
        tag = _pdp_tag(html)
        self.assertEqual(_data_attrs(tag), {"pdp-layout": "standard"}, "no extra data attribute unless a value differs from its default")
        for needle in ('class="breadcrumb"', 'class="topline"', 'class="sku-line"', 'class="qty"', 'class="pdp-satc"', 'class="pill pill-disc"'):
            self.assertIn(needle, html, needle)
        self.assertNotIn(" hidden>", html.split('class="qty"', 1)[1].split(">", 1)[0] + ">")
        self.assertEqual(html.count('role="tab"'), 3)
        self.assertEqual(_data_attrs(_tabs_tag(html)).keys() & {"tabs-mode", "tab-style", "tab-align", "panel-style"}, set())

    def test_a_never_edited_section_stores_nothing_new(self):
        for section, keys in ((self.main, pdp_settings.PRODUCT_MAIN_SETTING_KEYS), (self.desc, ("layout_mode", "tab_style", "tab_align", "panel_style", "sections"))):
            stored = self._stored(section)
            for key in (*keys, "design"):
                self.assertNotIn(key, stored, f"{section.section_key}.{key} must stay absent until the merchant sets it")


class ProductMainControlsTests(_PdpBase):
    def test_every_choice_value_reaches_the_markup_as_a_data_attribute(self):
        for key, _label, choices, default in pdp_settings.PRODUCT_MAIN_CHOICES:
            if key == "layout_variant":
                continue
            attr = pdp_settings._PRODUCT_MAIN_ATTRIBUTE_NAMES[key]
            for value, _l in choices:
                if value == default:
                    continue
                with self.subTest(key=key, value=value):
                    self._update(self.main, {key: value})
                    self.assertEqual(_data_attrs(_pdp_tag(self._preview())).get(attr), value)
            self._update(self.main, {key: default})
            self.assertNotIn(attr, _data_attrs(_pdp_tag(self._preview())), "back to the default = no attribute")

    def test_layout_variant_keeps_the_preset_written_fashion_value(self):
        self._update(self.main, {"layout_variant": "fashion"})
        self.assertEqual(_data_attrs(_pdp_tag(self._preview()))["pdp-layout"], "fashion")
        # a value a preset wrote directly (not through the Inspector) is honoured as well
        self.main.settings = {"layout_variant": "fashion"}
        self.main.save(update_fields=["settings"])
        self.assertEqual(_data_attrs(_pdp_tag(self._preview()))["pdp-layout"], "fashion")

    def test_switches_hide_only_presentation_never_the_purchase_form(self):
        self._update(self.main, {
            "show_breadcrumb": False, "show_topline": False, "show_sku": False, "show_wishlist": False, "show_discount_badge": False,
            "show_quantity": False, "show_mobile_sticky_bar": False, "gallery_sticky": False,
        })
        html = self._preview()
        for gone in ('class="breadcrumb"', 'class="topline"', 'class="sku-line"', 'class="pdp-satc"', 'class="pill pill-disc"', 'class="wish'):
            self.assertNotIn(gone, html, gone)
        self.assertEqual(_data_attrs(_pdp_tag(html))["gallery-sticky"], "off")
        # the real, single form still carries variant, quantity (hidden control, value 1) and the add-to-cart submit
        self.assertEqual(html.count(f'hx-post="{reverse("cart:add", args=[self.product.slug])}"'), 1, "one real add-to-cart form")
        self.assertIn('name="quantity"', html)
        self.assertIn('name="variant_id"', html)
        self.assertRegex(html, r'<div class="qty" x-data="\{ qty: 1 \}" hidden>')
        self.assertIn("pdp-actions", html)
        self.assertIn('type="submit" class="btn btn-primary"', html)

    def test_option_style_chips_switches_the_swatch_branch_off_for_colours(self):
        self._update(self.main, {"option_style": "chips"})
        html = self._preview()
        self.assertEqual(_data_attrs(_pdp_tag(html))["option-style"], "chips")
        self.assertIn("$el.closest('.pdp').dataset.optionStyle", html)

    def test_price_stock_and_variants_come_from_their_models_not_from_settings(self):
        before = self._preview()
        self._update(self.main, {"price_position": "before_options", "qty_layout": "inline", "info_panel": "card", "show_sku": False})
        after = self._preview()
        for data in ("variant-selector-data", "product-price-data"):
            payload = lambda html: re.search(rf'<script id="{data}" type="application/json">(.*?)</script>', html, re.S).group(1)
            self.assertEqual(payload(before), payload(after), data)
        self.assertIn("کالای کنترل‌های طراحی", after)

    def test_design_block_flags_reach_the_wrapper_and_unsupported_properties_are_refused(self):
        self._update(self.main, {"design": {"radius": 14, "border_width": 2, "border_color": "#334455", "price_color": "#aa2200",
                                            "image_ratio": "portrait", "image_fit": "cover"}})
        html = self._preview()
        wrapper = re.search(r'<div class="rsec[^>]*data-section-key="product_main"[^>]*>', html, re.S).group(0)
        for flag in ("radius", "border", "price", "ratio", "fit"):
            self.assertRegex(wrapper, rf'data-d="[^"]*\b{flag}\b', flag)
        with self.assertRaises(r4_mutation_service.R4MutationError):
            self._update(self.main, {"design": {"columns_desktop": 3}})          # not a property of this section
        with self.assertRaises(r4_mutation_service.R4MutationError):
            self._update(self.main, {"background": {"mode": "color", "color": "#000000"}})   # protected: no free section fill


class ProductMainMutationLifecycleTests(_PdpBase):
    def test_one_mutation_is_one_revision_and_undo_redo_restore_it(self):
        start = self._revision()
        self._update(self.main, {"cta_size": "large", "thumbs_position": "side"})
        self.assertEqual(self._revision(), start + 1, "one Revision per mutation")
        self.assertEqual(self._stored(self.main)["cta_size"], "large")
        self.assertEqual(self._history("undo").status_code, 200)
        self.assertNotIn("cta_size", self._stored(self.main))
        self.assertEqual(_data_attrs(_pdp_tag(self._preview())).get("cta-size"), None)
        self.assertEqual(self._history("redo").status_code, 200)
        self.assertEqual(self._stored(self.main)["cta_size"], "large")
        self.assertEqual(_data_attrs(_pdp_tag(self._preview()))["thumbs"], "side")

    def test_out_of_vocabulary_input_is_refused_with_no_revision_and_no_change(self):
        self._update(self.main, {"cta_size": "large"})
        revision = self._revision()
        for patch in ({"cta_size": "huge"}, {"show_sku": "perhaps"}, {"not_a_setting": 1}, {"gallery_split": ["equal"]}):
            with self.subTest(patch=patch):
                with self.assertRaises(r4_mutation_service.R4MutationError) as caught:
                    self._update(self.main, patch)
                self.assertEqual(str(caught.exception), "invalid_settings")
        self.assertEqual(self._revision(), revision)
        self.assertEqual(self._stored(self.main)["cta_size"], "large")

    def test_restoring_the_default_value_returns_to_the_default_rendering(self):
        self._update(self.main, {"cta_shape": "pill", "info_panel": "outlined"})
        self._update(self.main, {"cta_shape": "rounded", "info_panel": "plain"})
        self.assertEqual(_data_attrs(_pdp_tag(self._preview())), {"pdp-layout": "standard"})

    def test_baseline_reset_restores_generic_pdp_settings_a_ready_template_recipe_carries(self):
        """A Ready Template recipe may carry any of these generic keys; the existing granular reset then restores exactly them.
        (None of today's recipes carries them yet, so the baseline snapshot of an applied preset is extended in the test.)"""
        from apps.storefront_builder import layout_preset_registry
        from apps.storefront_builder.services import preset_service

        preset_service.apply_preset(self.draft, layout_preset_registry.get_layout_preset("dense_marketplace"))
        self.draft = svc.get_or_create_draft(self.store)
        main = self._section("product_main")
        snapshot = self.draft.template_baseline_snapshot
        entry = next(e for e in snapshot["pages"]["product_detail"] if e["slot_key"] == main.template_slot_key)
        entry["settings"] = {**entry["settings"], "cta_size": "large", "info_panel": "card"}
        self.draft.template_baseline_snapshot = snapshot
        self.draft.save(update_fields=["template_baseline_snapshot"])
        self._update(main, {"cta_size": "compact", "info_panel": "outlined", "show_sku": False})

        def reset(**payload):
            return r4_mutation_service.apply_mutation(
                store=self.store, actor=self.staff, base_revision=self._revision(),
                mutation={"section_id": main.pk, **payload},
            )

        reset(type="section.reset_setting_to_baseline", key="cta_size")
        stored = self._stored(main)
        self.assertEqual((stored["cta_size"], stored["info_panel"], stored["show_sku"]), ("large", "outlined", False))
        reset(type="section.reset_to_baseline")
        stored = self._stored(main)
        self.assertEqual((stored["cta_size"], stored["info_panel"]), ("large", "card"))
        self.assertNotIn("show_sku", stored, "a key the recipe does not carry returns to «absent» = its default")
        with self.assertRaises(r4_mutation_service.R4MutationError):
            reset(type="section.reset_setting_to_baseline", key="gallery_split")        # not in the baseline: refused, nothing changes

    def test_a_key_outside_every_baseline_is_returned_to_default_by_choosing_the_default(self):
        self._update(self.main, {"gallery_split": "info_wide"})
        self._update(self.main, {"gallery_split": "equal"})
        self.assertNotIn("gallery-split", _data_attrs(_pdp_tag(self._preview())))


@override_settings(ALLOWED_HOSTS=[HOST, PUBLIC_HOST, "pdp-controls-foreign.example.com", "testserver"])
class DraftPublishAndTenantIsolationTests(_PdpBase):
    def setUp(self):
        super().setUp()
        StoreDomain.objects.create(
            store=self.store, hostname=PUBLIC_HOST, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.public = Client(HTTP_HOST=PUBLIC_HOST)

    def _public_pdp(self):
        response = self.public.get(reverse("catalog:product-detail", args=[self.product.slug]), HTTP_HOST=PUBLIC_HOST)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_draft_edits_show_in_preview_only_until_publish(self):
        svc.publish(self.store)
        self.draft = svc.get_or_create_draft(self.store)
        self.main = self._section("product_main")
        self.desc = self._section("product_description")
        self._update(self.main, {"gallery_position": "end", "show_sku": False})
        self._update(self.desc, {"layout_mode": "stacked"})
        self.assertEqual(_data_attrs(_pdp_tag(self._preview()))["gallery-pos"], "end")
        published = self._public_pdp()
        self.assertNotIn("gallery-pos", _data_attrs(_pdp_tag(published)))
        self.assertNotIn("data-tabs-mode", published)
        svc.publish(self.store)
        published = self._public_pdp()
        self.assertEqual(_data_attrs(_pdp_tag(published))["gallery-pos"], "end")
        self.assertEqual(_data_attrs(_tabs_tag(published))["tabs-mode"], "stacked")
        self.assertNotIn("sku-line", published.split('class="pdp"', 1)[1].split("pdp-tabs", 1)[0])

    def test_a_foreign_store_settings_never_reach_this_store_and_cannot_be_mutated_from_it(self):
        foreign = Store.objects.create(name="فروشگاه بیگانه", slug="pdpc-foreign", status=Store.Status.ACTIVE)
        foreign_draft = svc.get_or_create_draft(foreign)
        foreign_main = foreign_draft.get_page(PDP).sections.filter(section_key="product_main").first() or section_structure_service.add_section(
            draft=foreign_draft, section_key="product_main", page_type=PDP,
        )
        foreign_main.settings = {"cta_size": "large", "info_panel": "outlined"}
        foreign_main.save(update_fields=["settings"])
        svc.publish(foreign)
        svc.publish(self.store)
        html = self._public_pdp()
        self.draft = svc.get_or_create_draft(self.store)          # publishing consumed the Draft; this Store edits a fresh one
        self.assertNotIn("data-cta-size", html)
        self.assertNotIn("data-info-panel", html)
        with self.assertRaises(r4_mutation_service.R4MutationError) as caught:
            self._update(foreign_main, {"cta_size": "compact"})
        self.assertEqual(str(caught.exception), "section_not_found")
        foreign_main.refresh_from_db()
        self.assertEqual(foreign_main.settings["cta_size"], "large")


# ------------------------------------------------------------------------------------------------------------------------------
class ProductDescriptionModesTests(_PdpBase):
    PANELS = ("desc", "spec", "review")

    def _tabs(self, html):
        return _data_attrs(_tabs_tag(html))

    def test_default_is_the_historical_accessible_tablist(self):
        html = self._preview()
        self.assertIn('role="tablist"', html)
        self.assertEqual((html.count('role="tab"'), html.count('role="tabpanel"')), (3, 3))
        self.assertIn("tabs: ['desc', 'spec', 'review']", html)
        for key in self.PANELS:
            self.assertEqual(html.count(f'id="pdp-panel-{key}-{self.product.pk}"'), 1)

    def test_every_mode_keeps_all_real_content_in_the_dom_for_no_js(self):
        for mode in ("tabs", "tabs_vertical", "accordion", "stacked"):
            with self.subTest(mode=mode):
                self._update(self.desc, {"layout_mode": mode})
                html = self._preview()
                self.assertIn("توضیحات واقعی کالای آزمایشی", html)
                self.assertIn('class="spec-table"', html)
                self.assertIn("review-sum", html)
                if mode != "tabs":
                    self.assertEqual(self._tabs(html)["tabs-mode"], mode)

    def test_vertical_and_accordion_are_still_aria_tabs_with_keyboard_support(self):
        self._update(self.desc, {"layout_mode": "tabs_vertical"})
        html = self._preview()
        self.assertIn('aria-orientation="vertical"', _tabs_tag(html))
        self.assertIn("ArrowDown", html)
        self.assertIn("ArrowUp", html)
        self.assertIn("ArrowRight", html)
        self.assertIn("setAttribute('data-enhanced'", html, "vertical grid only after JS — without it every panel simply stays visible")
        self._update(self.desc, {"layout_mode": "tabs"})
        handler = self._preview().split("onKey(e, i) {", 1)[1].split("this.tab = this.tabs[n]", 1)[0]       # the tablist's own key handler
        self.assertIn("ArrowRight", handler)
        self.assertNotIn("ArrowDown", handler, "the default horizontal tablist keeps exactly its historical keys")
        self.assertNotIn("ArrowUp", handler)
        self._update(self.desc, {"layout_mode": "accordion"})
        accordion = self._preview()
        self.assertEqual(self._tabs(accordion)["tabs-mode"], "accordion")
        self.assertEqual((accordion.count('role="tab"'), accordion.count(':aria-expanded="')), (3, 3))

    def test_stacked_is_headings_and_regions_without_tab_semantics_or_hidden_panels(self):
        self._update(self.desc, {"layout_mode": "stacked"})
        html = self._preview()
        self.assertNotIn('role="tab"', html)
        self.assertNotIn('role="tablist"', html)
        self.assertEqual(html.count('class="pdp-sec-title"'), 3)
        self.assertEqual(html.count('class="pdp-tab-panel pdp-sec-panel"'), 3)
        self.assertEqual(html.count('class="pdp-tab-panel pdp-sec-panel" id="pdp-panel-'), 3)
        self.assertNotIn('x-show="tab ===', html.split('class="pdp-tabs"', 1)[1].split('id="review-form-container"', 1)[0])
        for key in self.PANELS:
            self.assertEqual(html.count(f'id="pdp-panel-{key}-{self.product.pk}"'), 1)
            self.assertIn(f'aria-labelledby="pdp-tab-{key}-{self.product.pk}"', html)

    def test_order_labels_and_visibility_of_the_real_sections(self):
        self._update(self.desc, {"sections": [
            {"key": "review", "label": "دیدگاه‌های خریداران", "visible": True},
            {"key": "desc", "label": "", "visible": False},
        ]})
        html = self._preview()
        ids = re.findall(r'id="pdp-tab-([a-z]+)-', html)
        self.assertEqual(ids, ["review", "spec"])
        self.assertIn("دیدگاه‌های خریداران", html)
        self.assertNotIn("توضیحات واقعی کالای آزمایشی", html, "a hidden section renders nothing")
        self.assertIn("tabs: ['review', 'spec']", html)
        first = re.search(r'<button[^>]*id="pdp-tab-review-[^>]*>', html, re.S).group(0)
        self.assertIn('aria-selected="true"', first)

    def test_hiding_everything_renders_no_empty_shell(self):
        self._update(self.desc, {"sections": [{"key": k, "visible": False} for k in self.PANELS]})
        self.assertNotIn('class="pdp-tabs"', self._preview())

    def test_brand_tab_only_exists_with_real_brand_data(self):
        self._update(self.desc, {"sections": [{"key": "brand", "label": "برند", "visible": True}]})
        self.assertNotIn("pdp-tab-brand-", self._preview(), "product without a brand: no tab")
        brand = Brand.objects.create(store=self.store, name="برند آزمایشی", slug="pdpc-brand")
        self.product.brand = brand
        self.product.save(update_fields=["brand"])
        self.assertNotIn("pdp-tab-brand-", self._preview(), "brand without any data: no empty tab")
        brand.description = "توضیح واقعی برند"
        brand.country = "ایران"
        brand.save()
        html = self._preview()
        self.assertIn(f'id="pdp-tab-brand-{self.product.pk}"', html)
        self.assertIn("توضیح واقعی برند", html)
        self.assertIn("ایران", html)
        self._update(self.desc, {"sections": []})
        self.assertNotIn("pdp-tab-brand-", self._preview(), "never shown unless the merchant lists it")

    def test_brand_panel_is_store_scoped_and_links_only_http_websites(self):
        from types import SimpleNamespace

        from apps.storefront_builder.services.render_service import _brand_panel_view

        def brand(store_id, website):
            return SimpleNamespace(store_id=store_id, name="b", name_en="", logo=None, description="d", country="", website=website)

        product = SimpleNamespace(store_id=1)
        self.assertIsNone(_brand_panel_view(brand(2, "https://x.test"), product), "another Store's brand is never shown")
        self.assertIsNone(_brand_panel_view(None, product))
        self.assertEqual(_brand_panel_view(brand(1, "javascript:alert(1)"), product)["website"], "")
        self.assertEqual(_brand_panel_view(brand(1, "https://x.test"), product)["website"], "https://x.test")

    def test_presentation_choices_reach_the_container_and_defaults_do_not(self):
        self._update(self.desc, {"tab_style": "pills", "tab_align": "center", "panel_style": "boxed"})
        attrs = self._tabs(self._preview())
        self.assertEqual((attrs["tab-style"], attrs["tab-align"], attrs["panel-style"]), ("pills", "center", "boxed"))
        self._update(self.desc, {"tab_style": "underline", "tab_align": "start", "panel_style": "plain"})
        self.assertEqual(self._tabs(self._preview()).keys() & {"tab-style", "tab-align", "panel-style"}, set())

    def test_one_revision_per_edit_undo_redo_and_refusal_of_bad_input(self):
        start = self._revision()
        self._update(self.desc, {"layout_mode": "accordion", "sections": [{"key": "spec", "label": "ویژگی‌ها"}]})
        self.assertEqual(self._revision(), start + 1)
        self.assertEqual(self._history("undo").status_code, 200)
        self.assertNotIn("layout_mode", self._stored(self.desc))
        self.assertEqual(self._history("redo").status_code, 200)
        self.assertEqual(self._stored(self.desc)["layout_mode"], "accordion")
        revision = self._revision()
        for patch in ({"layout_mode": "carousel"}, {"sections": [{"key": "a"}] * 9}, {"sections": "x"}, {"bogus": 1}):
            with self.subTest(patch=patch):
                with self.assertRaises(r4_mutation_service.R4MutationError):
                    self._update(self.desc, patch)
        self.assertEqual(self._revision(), revision)

    def test_unknown_or_duplicate_rows_are_cleaned_not_rendered(self):
        self._update(self.desc, {"sections": [{"key": "spec", "label": "الف"}, {"key": "spec", "label": "ب"}, {"key": "desc", "label": "ج"}]})
        stored = self._stored(self.desc)["sections"]
        self.assertEqual([row["key"] for row in stored], ["spec", "desc"])
        self.assertEqual(re.findall(r'id="pdp-tab-([a-z]+)-', self._preview()), ["spec", "desc", "review"])

    def test_the_content_sources_are_unchanged(self):
        template = (APP / "templates" / "storefront_builder" / "sections" / "product_description.html").read_text(encoding="utf-8")
        for source in ("product.description", "spec_variant_summary", "approved_reviews", "rating_breakdown", "review_form.html"):
            self.assertIn(source, template)


class InspectorWiringTests(_PdpBase):
    def _panel(self, html, tab):
        parts = re.split(r'(?=<section[^>]*data-r4-tab-panel=")', html)
        for part in parts:
            if f'data-r4-tab-panel="{tab}"' in part[:200]:
                return part
        return ""

    def test_product_main_now_has_a_working_inspector_with_the_layout_controls_in_the_design_tab(self):
        response = self.client.get(reverse("dashboard:storefront-builder-r4-section-inspector", args=[self.main.pk]))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        design, content = self._panel(html, "design"), self._panel(html, "content")
        for key in ("gallery_position", "thumbs_position", "info_panel", "qty_layout", "cta_size", "option_style"):
            self.assertIn(f'data-r4-field-key="{key}"', design, key)
        for key in ("show_breadcrumb", "show_sku", "show_quantity", "show_mobile_sticky_bar"):
            self.assertIn(f'data-r4-field-key="{key}"', content, key)
        self.assertIn('data-r4-field-key="design"', html)
        self.assertNotIn('data-r4-field-key="background"', html, "a purchase-critical section has no free fill control")

    def test_product_description_inspector_shows_the_three_real_rows_when_nothing_was_edited(self):
        response = self.client.get(reverse("dashboard:storefront-builder-r4-section-inspector", args=[self.desc.pk]))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('data-r4-field-key="layout_mode"', html)
        # the four effective rows (desc / spec / review shown, brand off) + the hidden <template> row
        self.assertEqual(len(re.findall(r'<div class="r4-repeater-row" data-r4-repeater-row>', html)), 4 + 1)
        self.assertIn('data-r4-field-key="background"', html)

    def test_the_inspector_is_read_only(self):
        revision, stored = self._revision(), self._stored(self.main)
        self.client.get(reverse("dashboard:storefront-builder-r4-section-inspector", args=[self.main.pk]))
        self.assertEqual(self._revision(), revision)
        self.assertEqual(self._stored(self.main), stored)


# ------------------------------------------------------------------------------------------------------------------------------
class StylesheetContractTests(SimpleTestCase):
    def test_there_is_a_rule_for_every_value_the_renderer_can_emit(self):
        for key, _label, choices, default in pdp_settings.PRODUCT_MAIN_CHOICES:
            attr = pdp_settings._PRODUCT_MAIN_ATTRIBUTE_NAMES.get(key)
            if not attr or key == "option_style":      # ``option_style=chips`` is consumed by the template's own x-if (no CSS needed)
                continue
            for value, _l in choices:
                if value == default:
                    continue
                self.assertIn(f'[data-{attr}="{value}"]', CSS, f"{key}={value}")
        self.assertIn('[data-gallery-sticky="off"]', CSS)
        for key, _label, choices, default in pdp_settings.PRODUCT_DESCRIPTION_CHOICES:
            attr = pdp_settings._PRODUCT_DESCRIPTION_ATTRIBUTE_NAMES[key]
            for value, _l in choices:
                if value != default:
                    self.assertIn(f'[data-{attr}="{value}"]', CSS, f"{key}={value}")

    def test_design_block_consumers_use_the_shared_tokens(self):
        for token in ("--d-surface", "--d-price", "--d-btn-bg", "--d-ratio", "--d-gap", "--d-accent", "--d-heading", "--d-text"):
            self.assertIn(token, NEW_CSS, token)

    def test_no_store_or_brand_is_named_in_the_new_code(self):
        sources = [
            NEW_CSS_WITH_COMMENTS.lower(),
            (APP / "pdp_settings.py").read_text(encoding="utf-8").lower(),
            (APP / "templates" / "storefront_builder" / "sections" / "product_description.html").read_text(encoding="utf-8").lower(),
        ]
        for forbidden in ("dize", "khaneh", "shokolati", "lilika", "lilium", "asalbanoo", "zhimun", "دیزه", "لیلیکا", "لیلیوم", "عسل", "ژیمون", "شکلاتی"):
            for source in sources:
                self.assertNotIn(forbidden, source, forbidden)

    def test_the_no_js_default_keeps_panels_visible(self):
        self.assertIn(".pdp-tab-panel{display:block}", CSS)
        self.assertNotIn(".tabpane{display:none}", CSS)

    def test_defaults_rely_on_no_new_always_on_rule(self):
        # every V5 rule is attribute-keyed or design-flag-keyed, except the inert ``[hidden]`` reset and the new class names
        for selector in re.findall(r"^([^@{}\n][^{]*)\{", NEW_CSS, re.M):
            for part in (p.strip() for p in re.sub(r":is\([^)]*\)", ":is()", selector).split(",")):
                if not part or part.startswith(("from", "to")):
                    continue
                self.assertTrue(
                    "[data-" in part or part.startswith((".pdp-lowstock", ".pdp-freeship", ".pdp-contact", ".pdp-lb")) or part in (".qty[hidden]", ".pdp-sec-title", ".brand-panel", ".brand-panel .brand-logo", ".brand-panel h3",
                                                 ".brand-panel h3 small", ".brand-panel p", ".brand-panel dl", ".brand-panel dt", ".brand-panel dd")
                    or "[data-enhanced]" in part,
                    f"unconditional rule would change the default rendering: {part}",
                )
