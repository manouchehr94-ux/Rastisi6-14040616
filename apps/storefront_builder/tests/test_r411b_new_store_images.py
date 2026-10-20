"""R4-11b — what a brand-new store's first real uploads exposed (found with a disposable store, real uploads, real browser).

* a single banner must keep a definite, visible frame where its card shrinks to its content (tablet / phone);
* every storefront page that renders the R4 header / footer / bottom-nav must load the sheet those partials are styled by;
* the owner can give a category a picture from the admin panel (the storefront category sections show it);
* admin-panel thumbnails of logos and product photos show the WHOLE picture, never a crop."""

import re
from io import BytesIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.catalog.models import Category
from apps.stores.models import Store, StoreMembership

User = get_user_model()
APPS = Path(__file__).resolve().parents[2]
BUILDER_CSS = (APPS / "storefront_builder" / "static" / "css" / "storefront_builder.css").read_text(encoding="utf-8")


def _rule(css, selector):
    """Every declaration block written for exactly this selector, in source order (the later ones win in the cascade)."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return ";".join(re.findall(r"(?:^|\})\s*" + re.escape(selector) + r"\s*\{([^{}]*)\}", css))


class SingleBannerKeepsItsFrameTests(SimpleTestCase):
    def test_banner_picture_has_a_definite_width_and_the_card_may_shrink(self):
        picture = _rule(BUILDER_CSS, ".promo-dark .mini picture")
        self.assertRegex(picture, r"(?<![-\w])width:\s*\d+px", "a percentage width resolves to 0 in a shrink-to-fit card")
        self.assertNotRegex(picture, r"(?<![-\w])width:\s*100%")
        self.assertIn("max-width:100%", picture)
        self.assertIn("min-width:0", picture)
        card = _rule(BUILDER_CSS, ".promo-dark .mini")
        self.assertIn("max-width:min(300px,100%)", card)


class FrameRuleDoesNotOverrideAFramesOwnPositionTests(SimpleTestCase):
    def test_generic_frame_rule_has_zero_specificity(self):
        """`position:relative` on every image frame collapsed the atelier category media (position:absolute; inset:0 inside its
        tile) to height 0, so those tiles showed no picture at all."""
        self.assertRegex(BUILDER_CSS, r":where\(\.special-image,[^{}]*\.category-atelier-media[^{}]*\)\{position:relative;overflow:hidden\}")
        atelier = _rule(BUILDER_CSS, ".category-atelier-media")
        self.assertIn("position:absolute", atelier)
        self.assertIn("inset:0", atelier)


class EveryCategoryMediaFrameIsInTheContractTests(SimpleTestCase):
    """The category_grid templates emit one `category-*-media` frame per visual style; every one must be a contract frame, or a portrait
    upload overflows it (pastel) / is sized by the picture (gradient)."""

    def test_every_category_media_class_in_the_template_is_a_registered_frame(self):
        template = (APPS / "storefront_builder" / "templates" / "storefront_builder" / "sections" / "category_grid.html").read_text(encoding="utf-8")
        lists = re.findall(r":(?:where|is)\((\.special-image,[^{}]*?)\)(?:>img|\{position:relative)", BUILDER_CSS)
        self.assertEqual(len(lists), 2, "the frame list and the fill list")
        missing = [c for c in sorted(set(re.findall(r'class="(category-[a-z-]*-media)"', template)))
                   if any(f".{c}" not in one for one in lists)]
        self.assertEqual(missing, [])


class LuxuryHeroFillsItsFrameTests(SimpleTestCase):
    def test_picture_is_absolutely_positioned_so_a_tall_upload_cannot_stretch_the_hero(self):
        rule = _rule(BUILDER_CSS, ".hero-luxury-media picture,.hero-luxury-media img")
        self.assertIn("position:absolute", rule)
        self.assertIn("inset:0", rule)
        self.assertIn("min-height:470px", _rule(BUILDER_CSS, ".hero-luxury-media"))


class ShellPagesLoadTheBuilderSheetTests(SimpleTestCase):
    """The shell's header / footer / mobile nav are styled by storefront_builder.css; without it the logo and the bottom-nav icons
    render at their natural (huge) size."""

    TEMPLATE_DIRS = [APPS / app / "templates" for app in ("catalog", "orders", "customers", "blog", "content", "cart")]

    def test_every_shell_page_that_keeps_the_shell_header_loads_storefront_builder_css(self):
        missing = []
        for base in self.TEMPLATE_DIRS:
            for path in base.rglob("*.html"):
                source = path.read_text(encoding="utf-8")
                if not re.search(r"""{%\s*extends\s+["']storefront_shell\.html["']""", source):
                    continue
                if re.search(r"{%\s*block\s+header\s*%}", source):
                    continue  # draws its own header (checkout, payment result)
                if "storefront_builder.css" not in source:
                    missing.append(str(path.relative_to(APPS)))
        self.assertEqual(missing, [], "these pages render the R4 header without its stylesheet")


class AdminThumbnailsShowTheWholePictureTests(SimpleTestCase):
    def test_list_thumbnails_contain(self):
        for rel in ("brands_table.html", "collections_table.html", "products_table_inner.html"):
            source = (APPS / "dashboard" / "templates" / "dashboard" / "partials" / rel).read_text(encoding="utf-8")
            self.assertNotIn("object-fit:cover", source, rel)
            self.assertIn("object-fit:contain", source, rel)

    def test_product_gallery_manager_contains(self):
        css = (APPS / "dashboard" / "static" / "css" / "product_entry_prototype.css").read_text(encoding="utf-8")
        rule = _rule(css, ".pe-prototype .thumb img,.pe-prototype .img-manage-thumb")
        self.assertIn("object-fit:contain", rule)
        self.assertNotIn("object-fit:cover", rule)


def _png(w=600, h=400):
    buf = BytesIO()
    Image.new("RGB", (w, h), (30, 90, 160)).save(buf, "PNG")
    return SimpleUploadedFile("cat.png", buf.getvalue(), content_type="image/png")


class CategoryImageCanBeUploadedFromTheAdminTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        self.main = Category.objects.create(store=self.store, name="گروه تصویر", slug="img-main", icon="📦")
        self.staff = User.objects.create_user(username="09121123055", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.login(username="09121123055", password="pass12345")

    def test_add_main_group_with_a_picture(self):
        response = self.client.post(reverse("dashboard:category-add-main"), {"name": "با تصویر", "icon": "🖼️", "image": _png()})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Category.objects.get(name="با تصویر").image)

    def test_edit_sets_and_clears_the_picture(self):
        url = reverse("dashboard:category-edit", args=[self.main.pk])
        self.client.post(url, {"name": "گروه تصویر", "icon": "📦", "image": _png()})
        self.main.refresh_from_db()
        self.assertTrue(self.main.image)
        kept = self.main.image.name
        self.client.post(url, {"name": "گروه تصویر", "icon": "📦"})  # no file: the picture stays
        self.main.refresh_from_db()
        self.assertEqual(self.main.image.name, kept)
        self.client.post(url, {"name": "گروه تصویر", "icon": "📦", "clear_image": "1"})
        self.main.refresh_from_db()
        self.assertFalse(self.main.image)

    def test_the_modals_offer_a_file_input_and_encode_multipart(self):
        edit = self.client.get(reverse("dashboard:category-edit", args=[self.main.pk])).content.decode()
        self.assertIn('type="file"', edit)
        self.assertIn('hx-encoding="multipart/form-data"', edit)
        listing = self.client.get(reverse("dashboard:category-list")).content.decode()
        self.assertIn('name="image"', listing)
