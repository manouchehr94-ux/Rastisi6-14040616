"""R4-12 — the stacked «پیشنهادهای لحظه‌ای» (spotlight) offer card on tablets / phones.

The owner picked «پر کردن قاب» in Design Studio and the desktop improved, but at 390px the picture stayed small with wide empty sides. The
section setting WAS applied (``--img-fit`` reached every picture at every width); what failed was the frame: a mobile rule capped its HEIGHT at
56vw — a landscape strip (326x218) that overrode the card's own near-square frame — so a portrait/square product was either tiny (contain) or
lost its top and bottom (cover). The bound is now a WIDTH cap, which keeps the frame's aspect ratio (the card's, or the owner's) at every width."""

import re
from pathlib import Path

from django.test import SimpleTestCase

APPS = Path(__file__).resolve().parents[2]
CSS_FILES = {
    "storefront_builder.css": (APPS / "storefront_builder" / "static" / "css" / "storefront_builder.css").read_text(encoding="utf-8"),
    "product_card.css": (APPS / "catalog" / "static" / "css" / "product_card.css").read_text(encoding="utf-8"),
    "home.css": (APPS / "catalog" / "static" / "css" / "home.css").read_text(encoding="utf-8"),
}
BUILDER_CSS = CSS_FILES["storefront_builder.css"]
SPOTLIGHT_FRAME = ".product-section--spotlight .product-spotlight-slide>.pcard .img"


def _blocks(css, selector):
    """Every declaration block written for exactly this selector (comments ignored), in source order."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return ";".join(re.findall(r"(?:^|[{};])\s*" + re.escape(selector) + r"\s*\{([^{}]*)\}", css))


class StackedOfferFrameKeepsItsAspectRatioTests(SimpleTestCase):
    def test_the_stacked_frame_is_bounded_by_width_not_by_a_viewport_height(self):
        rule = _blocks(BUILDER_CSS, SPOTLIGHT_FRAME)
        self.assertIn("width:min(100%,440px)", rule)
        self.assertIn("max-height:none", rule)
        self.assertIn("align-self:center", rule)
        self.assertNotRegex(rule, r"max-height:\s*min\([^)]*vw")

    def test_no_product_card_frame_is_capped_in_viewport_units(self):
        """A `max-height` in vw on a card frame re-shapes it into a strip on a phone and silently overrides «نسبت قاب» and the frame's own
        ratio; sizes of card frames come from aspect-ratio (or a column width), never from a viewport-height cap."""
        offenders = []
        for name, css in CSS_FILES.items():
            for selector, body in re.findall(r"([^{}]*\.pcard[^{}]*\.img[^{}]*)\{([^{}]*)\}", re.sub(r"/\*.*?\*/", "", css, flags=re.S)):
                if re.search(r"max-height:\s*[^;]*\d\s*vw", body):
                    offenders.append(f"{name}: {selector.strip()[:80]}")
        self.assertEqual(offenders, [])

    def test_section_fit_position_and_ratio_reach_the_card_pictures(self):
        """Why «پر کردن قاب» did apply on every device: the design flag feeds the contract variables the card picture reads."""
        self.assertIn('.rsec[data-d~="fit"]{--img-fit:var(--d-fit)}', BUILDER_CSS)
        self.assertIn('.rsec[data-d~="pos"]{--img-pos:var(--d-pos)}', BUILDER_CSS)
        card = CSS_FILES["product_card.css"]
        self.assertRegex(card, r'\.pcard \.img>img\[data-img-role="product"\]\{position:absolute;inset:0;width:100%;height:100%;object-fit:var\(--img-fit,contain\);object-position:var\(--img-pos,center\)\}')
        self.assertIn(".rsec[data-d~=\"ratio\"] :is(.pcard .img,", BUILDER_CSS)
        self.assertRegex(BUILDER_CSS, r'\.rsec\[data-d~="ratio"\] :is\([^{}]*\)\{aspect-ratio:var\(--d-ratio\)!important\}')

    def test_no_card_picture_rule_hard_codes_cover(self):
        """Every `object-fit:cover` on a product-card picture reads the section variable first, so «نحوه جاگیری تصویر» can win on any device."""
        for name, css in CSS_FILES.items():
            for selector, decl in re.findall(r"([^{}]*\.pcard[^{}]*)\{([^{}]*object-fit:\s*cover[^{}]*)\}", re.sub(r"/\*.*?\*/", "", css, flags=re.S)):
                self.assertIn("var(--img-fit", decl, f"{name}: {selector.strip()[:70]} hard-codes cover")
