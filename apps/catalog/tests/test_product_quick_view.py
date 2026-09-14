"""Phase 5 Task 5 (MODAL) — public product quick view.

The quick view is rendered SERVER-SIDE inside the canonical product card,
reusing the SAME ``product_card_data`` (U3) truth already resolved for the
card — no second product endpoint, no second serializer, no client fetch.
It reuses the canonical ``cart:add`` path for add-to-cart and the shared
``sfbOverlay`` overlay-mechanics primitive (MDR) for open/close/escape/
focus/scroll-lock. Each card gets a unique dialog id so many cards on one
page never collide.
"""
from decimal import Decimal

from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Category, Product, Vendor
from apps.catalog.services.product_card_service import build_product_card_data
from apps.storefront_builder.section_registry import default_card_settings
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class ProductQuickViewCardContractTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="qv-shop")
        self.category = Category.objects.create(store=self.store, name="دسته", slug="qv-category")

    def _product(self, **kwargs):
        count = Product.objects.count()
        defaults = {
            "store": self.store,
            "vendor": self.vendor,
            "category": self.category,
            "name": "کالای واقعی",
            "slug": f"qv-{count}",
            "sku": f"QV-{count}",
            "price": Decimal("250000"),
            "stock": 5,
            "status": Product.Status.ACTIVE,
            "product_type": Product.ProductType.SIMPLE,
        }
        defaults.update(kwargs)
        return Product.objects.create(**defaults)

    def _render(self, product, **overrides):
        settings = default_card_settings()
        settings.update(overrides)
        return render_to_string(
            "catalog/partials/product_card.html",
            {"product": product, "card_settings": settings},
        )

    def test_card_exposes_quick_view_trigger_with_dialog_semantics(self):
        product = self._product()
        html = self._render(product)
        # A quick view trigger with an accessible label.
        self.assertIn("aria-haspopup=\"dialog\"", html)
        # The dialog element itself with modal semantics.
        self.assertIn('role="dialog"', html)
        self.assertIn('aria-modal="true"', html)

    def test_quick_view_ids_are_instance_safe_not_product_pk_based(self):
        # The SAME product can appear many times on one page (Featured,
        # Newest, Best Sellers, ...). IDs must be per-RENDER-INSTANCE unique,
        # never a static product.pk (which would duplicate). We use Alpine's
        # native x-id/$id() so each mounted card scope gets a unique id and
        # the trigger + dialog + title cross-reference the SAME generated id.
        product = self._product()
        html = self._render(product)
        # No static product.pk-based IDs remain (the source of duplicates).
        self.assertNotIn(f'id="quick-view-{product.pk}"', html)
        self.assertNotIn(f'quick-view-title-{product.pk}', html)
        # The instance-safe mechanism is present.
        self.assertIn("x-id=", html)
        self.assertIn("$id('sfb-quick-view')", html)
        self.assertIn("$id('sfb-quick-view-title')", html)
        # Trigger controls the dialog and the dialog is labelled by the title,
        # all via the same $id() token (dynamic bindings).
        self.assertIn(":aria-controls=\"$id('sfb-quick-view')\"", html)
        self.assertIn(":id=\"$id('sfb-quick-view')\"", html)
        self.assertIn(":aria-labelledby=\"$id('sfb-quick-view-title')\"", html)
        self.assertIn(":id=\"$id('sfb-quick-view-title')\"", html)

    def test_same_product_rendered_multiple_times_has_no_duplicate_static_ids(self):
        # Simulate the real multi-carousel page: the same product rendered
        # several times. With x-id there must be ZERO static id="quick-view*"
        # attributes at all (Alpine generates unique ids at runtime), so the
        # rendered page can never contain duplicate HTML ids for the dialog.
        product = self._product()
        page = "\n".join(self._render(product) for _ in range(4))
        import re
        static_dialog_ids = re.findall(r'\sid="quick-view[^"]*"', page)
        self.assertEqual(
            static_dialog_ids, [],
            f"quick view must not emit static ids that can collide: {static_dialog_ids}",
        )
        # x-id scope appears once per rendered card (one per instance).
        self.assertEqual(page.count("x-id="), 4)

    def test_quick_view_reuses_canonical_card_truth(self):
        product = self._product(name="کالای کوییک", price=Decimal("180000"))
        truth = build_product_card_data(product)
        html = self._render(product)
        # Name and PDP url come straight from the canonical card data.
        self.assertIn(truth.name, html)
        self.assertIn(truth.url, html)

    def test_quick_view_reuses_canonical_cart_add_path(self):
        product = self._product()
        html = self._render(product)
        cart_action = reverse("cart:add", args=[product.slug])
        # cart:add appears; the quick view does not invent a second cart route.
        self.assertIn(cart_action, html)

    def test_quick_view_reuses_shared_overlay_primitive(self):
        product = self._product()
        html = self._render(product)
        self.assertIn("sfbOverlay", html)

    def test_out_of_stock_quick_view_has_no_add_to_cart(self):
        product = self._product(name="ناموجود", stock=0)
        html = self._render(product)
        # Out of stock cards must not offer a cart action anywhere (card or QV).
        self.assertNotIn(reverse("cart:add", args=[product.slug]), html)
