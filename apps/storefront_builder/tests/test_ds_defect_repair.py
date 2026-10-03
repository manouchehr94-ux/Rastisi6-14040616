"""R4 Design Studio defect-repair regressions (D-001 .. D-004).

Baseline: certified Windows Final QA SHA 10f0570. Each test class pins one
certified defect independently.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

from django.urls import reverse

from decimal import Decimal

from apps.catalog.models import Brand, Category, MerchantCollection, Product, Vendor
from apps.content.models import HeroSlide, PromotionalBanner, StoryRailItem

from .test_media_views import MediaViewsTestCase, _img

STATIC_DIR = Path(__file__).resolve().parent.parent / "static" / "storefront_builder"


class D001RedoShortcutHelpTextTests(MediaViewsTestCase):
    def test_help_text_documents_real_redo_shortcut(self):
        js = (STATIC_DIR / "r4_studio.js").read_text(encoding="utf-8")
        self.assertNotIn("· Shift + Z: بازگردانی", js)
        self.assertIn("Ctrl / ⌘ + Shift + Z: بازگردانی", js)

    def test_keyboard_handler_unchanged(self):
        """Real behavior: Ctrl/Cmd+Z = undo, Ctrl/Cmd+Shift+Z = redo."""
        js = (STATIC_DIR / "r4_studio.js").read_text(encoding="utf-8")
        self.assertIn("(evt.ctrlKey || evt.metaKey) && String(evt.key).toLowerCase() === 'z'", js)
        self.assertIn("historyCommand(evt.shiftKey ? 'redo' : 'undo')", js)


class D002MediaEditIsActiveTests(MediaViewsTestCase):
    def _edit_url(self, section, kind, pk):
        return reverse("dashboard:storefront-builder-section-media-edit", args=[section.pk, kind, pk])

    def test_hero_true_to_false_persists_and_preserves_fields(self):
        slide = HeroSlide.objects.create(
            store=self.store, section=self.hero_section, title="اسلاید", subtitle="زیر",
            button_label="برو", show_button=False, desktop_image=_img(), is_active=True, display_order=3,
        )
        # Real browser semantics: unchecked checkbox key is OMITTED.
        resp = self.client.post(
            self._edit_url(self.hero_section, "hero-slides", slide.pk),
            {"title": "اسلاید", "subtitle": "زیر", "button_label": "برو", "destination_type": "none"},
        )
        self.assertEqual(resp.status_code, 302)
        slide.refresh_from_db()
        self.assertFalse(slide.is_active)
        self.assertEqual(slide.title, "اسلاید")
        self.assertEqual(slide.subtitle, "زیر")
        self.assertEqual(slide.button_label, "برو")
        self.assertEqual(slide.display_order, 3)
        self.assertTrue(slide.desktop_image)

    def test_hero_false_to_true_persists(self):
        slide = HeroSlide.objects.create(
            store=self.store, section=self.hero_section, title="غیرفعال", desktop_image=_img(), is_active=False,
        )
        resp = self.client.post(
            self._edit_url(self.hero_section, "hero-slides", slide.pk),
            {"title": "غیرفعال", "destination_type": "none", "is_active": "on"},
        )
        self.assertEqual(resp.status_code, 302)
        slide.refresh_from_db()
        self.assertTrue(slide.is_active)

    def test_banner_and_story_true_to_false_persist(self):
        banner = PromotionalBanner.objects.create(
            store=self.store, section=self.banner_section, title="ب", desktop_image=_img(), is_active=True,
        )
        story = StoryRailItem.objects.create(
            store=self.store, section=self.story_section, title="س", image=_img(), is_active=True,
        )
        self.client.post(self._edit_url(self.banner_section, "banners", banner.pk),
                         {"title": "ب", "destination_type": "none"})
        self.client.post(self._edit_url(self.story_section, "story-items", story.pk),
                         {"title": "س", "destination_type": "none"})
        banner.refresh_from_db()
        story.refresh_from_db()
        self.assertFalse(banner.is_active)
        self.assertFalse(story.is_active)

    def test_edit_form_renders_inactive_item_unchecked(self):
        """The checkbox must reflect the stored False (``default:True`` used to
        re-check it, so re-saving silently re-activated the item)."""
        slide = HeroSlide.objects.create(
            store=self.store, section=self.hero_section, title="غ", desktop_image=_img(), is_active=False,
        )
        resp = self.client.get(self._edit_url(self.hero_section, "hero-slides", slide.pk))
        html = resp.content.decode()
        tag = re.search(r'<input type="checkbox" name="is_active"[^>]*>', html).group(0)
        self.assertNotIn("checked", tag)

    def test_edit_form_renders_active_item_checked_and_add_form_defaults_checked(self):
        slide = HeroSlide.objects.create(
            store=self.store, section=self.hero_section, title="ف", desktop_image=_img(), is_active=True,
        )
        html = self.client.get(self._edit_url(self.hero_section, "hero-slides", slide.pk)).content.decode()
        self.assertIn("checked", re.search(r'<input type="checkbox" name="is_active"[^>]*>', html).group(0))
        add = reverse("dashboard:storefront-builder-section-media-add", args=[self.hero_section.pk, "hero-slides"])
        html = self.client.get(add).content.decode()
        self.assertIn("checked", re.search(r'<input type="checkbox" name="is_active"[^>]*>', html).group(0))

    def test_list_toggle_still_works_both_directions(self):
        slide = HeroSlide.objects.create(
            store=self.store, section=self.hero_section, title="ت", desktop_image=_img(), is_active=True,
        )
        url = reverse("dashboard:storefront-builder-section-media-toggle",
                      args=[self.hero_section.pk, "hero-slides", slide.pk])
        self.client.post(url)
        slide.refresh_from_db()
        self.assertFalse(slide.is_active)
        self.client.post(url)
        slide.refresh_from_db()
        self.assertTrue(slide.is_active)


class _DestinationFixtureMixin:
    def _make_targets(self):
        self.cat = Category.objects.create(store=self.store, name="دسته D", slug="d-cat", is_active=True)
        self.brand = Brand.objects.create(store=self.store, name="برند D", slug="d-brand", is_active=True)
        self.coll = MerchantCollection.objects.create(store=self.store, name="کالکشن D", slug="d-coll", is_active=True)
        vendor = Vendor.objects.create(store=self.store, name="فروشنده D", slug="d-vendor")
        self.product = Product.objects.create(
            store=self.store, vendor=vendor, category=self.cat, name="محصول D", slug="d-prod",
            sku="SKU-D-1", price=Decimal("1000"), status=Product.Status.ACTIVE,
        )

    def _edit(self, slide, post):
        return self.client.post(
            reverse("dashboard:storefront-builder-section-media-edit",
                    args=[self.hero_section.pk, "hero-slides", slide.pk]),
            {"title": "اسلاید", "is_active": "on", **post},
        )

    def _stale_siblings(self):
        """What a real browser submits: every hidden sibling control keeps
        its DOM value (``x-show`` only hides, never disables)."""
        return {
            "destination_category": str(self.cat.pk),
            "destination_brand": str(self.brand.pk),
            "destination_collection": str(self.coll.pk),
            "destination_product": str(self.product.pk),
            "destination_external_url": "https://stale.example.com",
        }

    def _values(self, slide):
        slide.refresh_from_db()
        return (
            slide.destination_type, slide.destination_category_id, slide.destination_brand_id,
            slide.destination_collection_id, slide.destination_product_id,
            slide.destination_external_url,
        )


class D003DestinationTransitionTests(_DestinationFixtureMixin, MediaViewsTestCase):
    """Each transition is submitted ONCE with every stale sibling present."""

    def setUp(self):
        super().setUp()
        self._make_targets()

    def _target_post(self, dtype):
        stale = self._stale_siblings()
        post = {"destination_type": dtype}
        post.update(stale)
        if dtype == "external":
            post["destination_external_url"] = "https://new.example.com/x"
        return post

    def _expected(self, dtype):
        return {
            "none": ("none", None, None, None, None, ""),
            "search": ("search", None, None, None, None, ""),
            "cart": ("cart", None, None, None, None, ""),
            "category": ("category", self.cat.pk, None, None, None, ""),
            "brand": ("brand", None, self.brand.pk, None, None, ""),
            "collection": ("collection", None, None, self.coll.pk, None, ""),
            "product": ("product", None, None, None, self.product.pk, ""),
            "external": ("external", None, None, None, None, "https://new.example.com/x"),
        }[dtype]

    def _seed(self, dtype):
        kwargs = {
            "category": {"destination_category": self.cat},
            "brand": {"destination_brand": self.brand},
            "collection": {"destination_collection": self.coll},
            "product": {"destination_product": self.product},
            "external": {"destination_external_url": "https://old.example.com"},
        }.get(dtype, {})
        return HeroSlide.objects.create(
            store=self.store, section=self.hero_section, title="اسلاید", desktop_image=_img(),
            destination_type=dtype, **kwargs,
        )

    TYPES = ["none", "category", "brand", "collection", "product", "search", "cart", "external"]

    def test_every_transition_persists_on_first_save(self):
        for src in self.TYPES:
            for dst in self.TYPES:
                if src == dst:
                    continue
                with self.subTest(src=src, dst=dst):
                    slide = self._seed(src)
                    resp = self._edit(slide, self._target_post(dst))
                    self.assertEqual(resp.status_code, 302, f"{src}->{dst} did not save on first POST")
                    self.assertEqual(self._values(slide), self._expected(dst))
                    slide.delete()

    def test_add_with_stale_siblings_persists_only_selected(self):
        for dst in self.TYPES:
            with self.subTest(dst=dst):
                HeroSlide.objects.filter(section=self.hero_section).delete()
                resp = self.client.post(
                    reverse("dashboard:storefront-builder-section-media-add",
                            args=[self.hero_section.pk, "hero-slides"]),
                    {"title": "جدید", "is_active": "on", "desktop_image": _img(), **self._target_post(dst)},
                )
                self.assertEqual(resp.status_code, 302)
                self.assertEqual(self._values(HeroSlide.objects.get(section=self.hero_section)), self._expected(dst))

    def test_selected_type_with_empty_value_still_rejected(self):
        """Gating must not weaken validation: a type whose own value is
        missing is still a validation error, DB unchanged."""
        slide = self._seed("category")
        for dst, own in (("brand", "destination_brand"), ("collection", "destination_collection"),
                         ("product", "destination_product"), ("category", "destination_category")):
            with self.subTest(dst=dst):
                post = self._stale_siblings()
                post[own] = ""
                post["destination_type"] = dst
                resp = self._edit(slide, post)
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(self._values(slide)[0], "category")
        resp = self._edit(slide, {"destination_type": "external", "destination_external_url": "",
                                  **{k: v for k, v in self._stale_siblings().items()
                                     if k != "destination_external_url"}})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._values(slide)[0], "category")

    def test_cross_store_target_still_rejected(self):
        from apps.stores.models import Store
        other = Store.objects.exclude(pk=self.store.pk).first()
        if other is None:
            other = Store.objects.create(name="فروشگاه دیگر", slug="other-d003")
        foreign = Category.objects.create(store=other, name="بیگانه", slug="foreign-cat", is_active=True)
        slide = self._seed("none")
        resp = self._edit(slide, {"destination_type": "category", "destination_category": str(foreign.pk)})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._values(slide)[0], "none")


_PICKER_CALL = re.compile(r"x-data=\"(destinationPicker\((?:.|\n)*?\))\"")


class D004DestinationPickerSerializationTests(_DestinationFixtureMixin, MediaViewsTestCase):
    """The rendered ``x-data="destinationPicker(...)"`` expression must be
    valid JavaScript for every destination type with a NULL id."""

    def setUp(self):
        super().setUp()
        self._make_targets()

    def _picker_call(self, html):
        m = _PICKER_CALL.search(html)
        self.assertIsNotNone(m, "destinationPicker x-data not rendered")
        return m.group(1).replace("&#x27;", "'").replace("&quot;", '"')

    def _render_edit(self, slide):
        url = reverse("dashboard:storefront-builder-section-media-edit",
                      args=[self.hero_section.pk, "hero-slides", slide.pk])
        return self._picker_call(self.client.get(url).content.decode())

    def _run_in_node(self, call):
        node = shutil.which("node")
        if not node:
            self.skipTest("node not available")
        js = (STATIC_DIR / "destination_picker.js").read_text(encoding="utf-8")
        script = f"var window = {{}};\n{js}\nvar destinationPicker = window.destinationPicker;\n" \
                 f"console.log(JSON.stringify({call}));"
        out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def _null_id_slide(self, dtype):
        slide = HeroSlide.objects.create(
            store=self.store, section=self.hero_section, title="ن", desktop_image=_img(),
        )
        # An orphaned/legacy row (e.g. FK SET_NULL) — bypasses full_clean on purpose.
        HeroSlide.objects.filter(pk=slide.pk).update(destination_type=dtype)
        return slide

    def test_null_id_renders_valid_js_for_every_destination_type(self):
        for dtype in ["none", "category", "brand", "collection", "product", "search", "cart", "external"]:
            with self.subTest(dtype=dtype):
                call = self._render_edit(self._null_id_slide(dtype))
                self.assertNotIn("None", call)
                state = self._run_in_node(call)
                self.assertEqual(state["type"], dtype)
                self.assertIsNone(state["productId"])

    def test_populated_product_still_serialized_correctly(self):
        slide = HeroSlide.objects.create(
            store=self.store, section=self.hero_section, title="ن", desktop_image=_img(),
            destination_type="product", destination_product=self.product,
        )
        state = self._run_in_node(self._render_edit(slide))
        self.assertEqual(state, {"type": "product", "productId": self.product.pk, "productName": "محصول D"})

    def test_product_name_with_quotes_is_js_safe(self):
        self.product.name = "It's \"x\" </script>"
        self.product.save(update_fields=["name"])
        slide = HeroSlide.objects.create(
            store=self.store, section=self.hero_section, title="ن", desktop_image=_img(),
            destination_type="product", destination_product=self.product,
        )
        state = self._run_in_node(self._render_edit(slide))
        self.assertEqual(state["productName"], "It's \"x\" </script>")

    def test_add_form_renders_valid_js(self):
        url = reverse("dashboard:storefront-builder-section-media-add", args=[self.hero_section.pk, "hero-slides"])
        state = self._run_in_node(self._picker_call(self.client.get(url).content.decode()))
        self.assertEqual(state["type"], "none")

    def test_section_destination_fields_block_null_id_is_valid_js(self):
        from django.template.loader import render_to_string
        for dtype in ["category", "brand", "collection", "product"]:
            with self.subTest(dtype=dtype):
                section = type("S", (), {"pk": 1, "settings": {"destination": {
                    "destination_type": dtype, "destination_id": None}}})()
                html = render_to_string(
                    "dashboard/storefront_builder/partials/section_destination_fields.html",
                    {"section": section, "destination_product_name": ""},
                )
                call = self._picker_call(html)
                self.assertNotIn("None", call)
                self._run_in_node(call)
