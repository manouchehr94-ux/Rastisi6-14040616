"""R4-13 — offer pictures: where the empty space came from, and the limited Design Studio zoom.

Measured in a real browser on a store with real uploads (300x400 portrait bag, 1600x1200 landscape shoe):

* «پیشنهاد شگفت‌انگیز» (amazing_offers) at 390/320px: the picture column was a fixed 120px, the frame 260px tall (surface mode) and the picture had
  10px of padding, so a landscape photo covered ~24% of its frame — 76% of the frame was TEMPLATE letterbox, ~3% the file's own backdrop.
  The frame is now a 4:3 plate above the copy on phones (wider column on tablets), 6px inset in «نمایش کامل» and none in «پر کردن قاب».
* «پیشنهادهای لحظه‌ای» (spotlight): its frame is bound by the equal-height row beside the hero on desktop; «پر کردن قاب» fills it (R4-12).
* The empty margin that belongs to the FILE (backdrop, borders) is removed by «بزرگ‌نمایی تصویر» (image_zoom), per section, without touching the file.
"""

import re
from pathlib import Path

from django.test import SimpleTestCase

from apps.storefront_builder import design_block, section_registry
from apps.storefront_builder.design_block import DesignSettingsError, render_attributes, validate_design_settings

APPS = Path(__file__).resolve().parents[2]
BUILDER_CSS = (APPS / "storefront_builder" / "static" / "css" / "storefront_builder.css").read_text(encoding="utf-8")
CSS = re.sub(r"/\*.*?\*/", "", BUILDER_CSS, flags=re.S)

ZOOM_SECTIONS = ("amazing_offers", "newest_products", "best_sellers", "discounted_products", "product_section")


def _r413_css():
    """The R4-13 block (after its banner comment) — rules there must stay section-internal."""
    start = BUILDER_CSS.index("R4-13 — offer pictures")
    return re.sub(r"/\*.*?\*/", "", BUILDER_CSS[start - 100:], flags=re.S)


class AmazingOfferFrameTests(SimpleTestCase):
    def test_phone_frame_is_a_ratio_plate_above_the_copy_not_a_120px_column(self):
        css = _r413_css()
        phone = css[css.index("@media(max-width:680px){"):]
        self.assertIn(".rsec .amazing-offers-section .special-main{grid-template-columns:minmax(0,1fr)}", phone)
        self.assertRegex(phone, r"\.special-main>a\.special-image\{order:-1;height:auto;aspect-ratio:4/3;width:min\(100%,420px\)")

    def test_tablet_frame_follows_the_photo_ratio(self):
        css = _r413_css()
        self.assertRegex(css, r"@media\(min-width:681px\) and \(max-width:1000px\)\{[^@]*special-image\{height:auto;aspect-ratio:4/3\}")

    def test_the_old_fixed_phone_frame_is_still_overridden_by_specificity_not_removed(self):
        """The base rules stay (other templates share them); the R4-13 selectors out-rank the surface-mode 260px height."""
        self.assertIn(".rsec[data-bg-mode=\"surface\"] .amazing-offers-section .special-image{height:260px}", CSS)
        self.assertIn(".rsec .amazing-offers-section .special-main>a.special-image", _r413_css())

    def test_fill_mode_has_no_inner_margin(self):
        css = _r413_css()
        self.assertIn('.rsec[data-d~="fill"] .amazing-offers-section .special-image>img{padding:0}', css)
        # ... and it is declared after the phone inset so it wins the equal-specificity tie
        self.assertGreater(css.index('data-d~="fill"'), css.index(".special-image>img{padding:6px}"))

    def test_rows_columns_and_their_tools_are_untouched(self):
        css = _r413_css()
        for forbidden in ("columns_visual", "layout-columns", ".rsec-row", "data-row", "r4-column", ".special-wrap", ".special-list"):
            self.assertNotIn(forbidden, css)


class ImageZoomPropertyTests(SimpleTestCase):
    def test_property_is_a_bounded_choice_in_the_image_group(self):
        prop = design_block.DESIGN_PROPERTIES["image_zoom"]
        self.assertEqual((prop.kind, prop.group), ("choice", "image"))
        self.assertEqual([c for c, _ in prop.choices if c], ["110", "125", "150", "175"])

    def test_only_picture_owning_product_sections_offer_it(self):
        for key in ZOOM_SECTIONS:
            self.assertIn("image_zoom", design_block.applicable_properties(key), key)
        for key in ("hero_banner", "blog_posts", "category_grid", "collection_tiles", "trust_features"):
            if key in section_registry.SECTION_REGISTRY:
                self.assertNotIn("image_zoom", design_block.applicable_properties(key), key)

    def test_invalid_zoom_is_rejected_and_neutral_is_dropped(self):
        applicable = design_block.applicable_properties("amazing_offers")
        self.assertEqual(validate_design_settings({"image_zoom": "125"}, applicable), {"image_zoom": "125"})
        self.assertEqual(validate_design_settings({"image_zoom": ""}, applicable), {})
        for bad in ("300", "1.25", "0", "-10", "<b>"):
            with self.assertRaises(DesignSettingsError):
                validate_design_settings({"image_zoom": bad}, applicable)
        with self.assertRaises(DesignSettingsError):
            validate_design_settings({"image_zoom": "125"}, design_block.applicable_properties("hero_banner"))

    def test_render_emits_flag_and_variable_only_when_set(self):
        self.assertEqual((render_attributes({})["flags"], render_attributes({})["style"]), ("", ""))
        out = render_attributes({"image_zoom": "150"})
        self.assertIn("zoom", out["flags"].split())
        self.assertIn("--d-zoom:1.5", out["style"])
        self.assertNotIn("zoom", render_attributes({"image_fit": "cover"})["flags"].split())

    def test_cover_sets_the_fill_flag_contain_does_not(self):
        self.assertIn("fill", render_attributes({"image_fit": "cover"})["flags"].split())
        self.assertNotIn("fill", render_attributes({"image_fit": "contain"})["flags"].split())
        self.assertIn("fit", render_attributes({"image_fit": "contain"})["flags"].split())

    def test_zoom_of_one_section_does_not_leak_into_another(self):
        """Each section renders its own --d-zoom on its own wrapper; a section without the key has neither flag nor variable."""
        first = render_attributes({"image_zoom": "125"}, design_block.applicable_properties("amazing_offers"))
        second = render_attributes({}, design_block.applicable_properties("amazing_offers"))
        self.assertIn("--d-zoom:1.25", first["style"])
        self.assertNotIn("zoom", second["flags"].split())
        self.assertNotIn("--d-zoom", second["style"])

    def test_dormant_zoom_on_a_section_without_the_capability_renders_nothing(self):
        out = render_attributes({"image_zoom": "175"}, design_block.applicable_properties("hero_banner"))
        self.assertNotIn("zoom", out["flags"].split())


class ImageZoomCssTests(SimpleTestCase):
    def test_zoom_scales_inside_the_frame_around_the_focal_side(self):
        rule = ('.rsec[data-d~="zoom"] :is(.pcard .img,.special-image)>img[data-img-role]'
                '{transform:scale(var(--d-zoom,1));transform-origin:var(--img-pos,center)}')
        self.assertIn(rule, CSS)

    def test_frames_that_zoom_clip_their_picture(self):
        """The zoom may never spill outside the frame: both frames are overflow:hidden through the contract rule."""
        self.assertRegex(CSS, r":where\(\.special-image,[^{}]*\.pcard \.img,[^{}]*\)\{position:relative;overflow:hidden\}")

    def test_hover_zoom_composes_with_the_owner_zoom_instead_of_resetting_it(self):
        self.assertIn('html[data-sfb-image-hover="zoom"] .rsec[data-d~="zoom"] .pcard:hover .img>img[data-img-role]{transform:scale(calc(var(--d-zoom,1)*1.08))}', CSS)
        self.assertIn('html[data-sfb-image-hover="none"] .rsec[data-d~="zoom"] .pcard:hover .img>img[data-img-role]{transform:scale(var(--d-zoom,1))}', CSS)

    def test_the_zoom_variable_is_set_per_section_wrapper_not_globally(self):
        self.assertNotRegex(CSS, r":root\s*\{[^}]*--d-zoom")
        self.assertNotRegex(CSS, r"(?:^|\})\s*(?:html|body)\s*\{[^}]*--d-zoom")
