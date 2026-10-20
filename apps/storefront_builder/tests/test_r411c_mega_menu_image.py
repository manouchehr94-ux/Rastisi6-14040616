"""R4-11c — the category picture in the header mega menu.

It used to be a full-width 108px strip with ``object-fit:cover`` (the R4-11 ``category`` role default) under a caption overlay: a square /
portrait photo lost 50-78% of itself. It is now a compact card — the WHOLE picture in a fixed 4:3 thumbnail frame + the name — for both
mega-menu implementations (the R4 header ``.gh-cat-mega-promo`` and the shared-shell header ``.cat-mega-promo``)."""

import re
from pathlib import Path

from types import SimpleNamespace

from django.template.loader import render_to_string
from django.test import SimpleTestCase

APPS = Path(__file__).resolve().parents[2]
BUILDER_CSS = (APPS / "storefront_builder" / "static" / "css" / "storefront_builder.css").read_text(encoding="utf-8")
LAYOUT_CSS = (APPS / "core" / "static" / "css" / "layout.css").read_text(encoding="utf-8")
HEADERS = APPS / "storefront_builder" / "templates" / "storefront_builder" / "partials"


def _blocks(css, selector):
    """Every declaration block written for exactly this selector, in source order (comments ignored)."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return ";".join(re.findall(r"(?:^|\})\s*" + re.escape(selector) + r"\s*\{([^{}]*)\}", css))


class MegaMenuPictureIsACompactWholePictureCardTests(SimpleTestCase):
    CASES = (
        ("builder header", BUILDER_CSS, ".gh-cat-mega-promo"),
        ("shared-shell header", LAYOUT_CSS, ".cat-mega-promo"),
    )

    def test_thumbnail_frame_is_fixed_and_shows_the_whole_picture(self):
        for label, css, root in self.CASES:
            image = _blocks(css, f"{root} img[data-img-role]")
            self.assertIn("width:96px", image, label)
            self.assertIn("height:72px", image, label)
            self.assertIn("object-fit:var(--img-fit,contain)", image, label)
            self.assertNotIn("cover", image, label)
            self.assertNotRegex(image, r"(?<![-\w])height:\s*(100%|auto)", label)

    def test_it_is_no_longer_a_full_width_strip_with_a_caption_laid_over_the_picture(self):
        for label, css, root in self.CASES:
            card = _blocks(css, root)
            self.assertIn("display:flex", card, label)
            self.assertRegex(card, r"max-width:\s*\d+px", label)
            caption = _blocks(css, f"{root} span")
            self.assertIn("position:static", caption, label)
            self.assertNotIn("linear-gradient", caption, label)
            self.assertNotRegex(_blocks(css, f"{root} img"), r"object-fit:var\(--img-fit,cover\)")

    def test_every_mega_menu_markup_gives_the_picture_the_category_role(self):
        for rel in ("global_header/_shared/category_mega_menu.html", "page_shell_header.html"):
            source = (HEADERS / rel).read_text(encoding="utf-8")
            promo = re.search(r'<a class="(?:gh-)?cat-mega-promo".*?</a>', source, re.S)
            self.assertIsNotNone(promo, rel)
            self.assertIn('data-img-role="category"', promo.group(0), rel)

    def test_mobile_sheet_keeps_the_card_compact(self):
        self.assertIn("max-width:none", _blocks(BUILDER_CSS, ".gh--marketplace .gh-cat-mega-promo"))
        # the compact card keeps its 96x72 thumbnail there too: no phone rule resizes the picture
        for mobile_rule in re.findall(r"[^{}]*\.gh-cat-mega-promo img[^{}]*\{[^{}]*\}", BUILDER_CSS):
            self.assertNotIn("height:108px", mobile_rule)


class MegaMenuRendersTheCategoryPictureAsACardTests(SimpleTestCase):
    def _category(self, image=True):
        return SimpleNamespace(
            id=7, pk=7, slug="shoes", name="کفش", icon="👞",
            image=SimpleNamespace(url="/media/categories/images/shoes.jpg") if image else None,
            children=SimpleNamespace(all=[SimpleNamespace(slug="formal", name="رسمی", icon="")]),
        )

    def test_card_markup_has_the_picture_and_the_name_and_no_inline_sizing(self):
        html = render_to_string(
            "storefront_builder/partials/global_header/_shared/category_mega_menu.html", {"nav_categories": [self._category()]},
        )
        card = re.search(r'<a class="gh-cat-mega-promo".*?</a>', html, re.S).group(0)
        self.assertIn('src="/media/categories/images/shoes.jpg"', card)
        self.assertIn('data-img-role="category"', card)
        self.assertIn("<span>کفش</span>", card)
        self.assertNotIn("style=", card)

    def test_a_category_without_a_picture_renders_no_card(self):
        html = render_to_string(
            "storefront_builder/partials/global_header/_shared/category_mega_menu.html", {"nav_categories": [self._category(image=False)]},
        )
        self.assertNotIn("gh-cat-mega-promo", html)
