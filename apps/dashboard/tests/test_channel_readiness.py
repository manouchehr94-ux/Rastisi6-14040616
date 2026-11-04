"""Product-data readiness for comparison channels (Torob) and the honest Merchant Center state: internal checks only, store-scoped, nothing sent anywhere."""

import socket
from decimal import Decimal
from unittest import mock

from django.urls import reverse

from apps.dashboard.tests.integration_pages import all_views_html, view_html

from apps.catalog.models import Category, Product, ProductImage, Vendor
from apps.dashboard.services import channel_readiness_service as svc
from apps.dashboard.tests.test_permission_enforcement import PermissionEnforcementTestCase
from apps.stores.models import Store


class ReadinessTests(PermissionEnforcementTestCase):
    def mk(self, store, slug, *, price="100000", stock=5, image=True, name=None, **extra):
        vendor, _ = Vendor.objects.get_or_create(store=store, slug="rv", defaults={"name": "V"})
        category, _ = Category.objects.get_or_create(store=store, slug="rc", defaults={"name": "C"})
        product = Product.objects.create(store=store, vendor=vendor, category=category, name=name if name is not None else slug, slug=slug, price=Decimal(price),
                                         stock=stock, status=Product.Status.ACTIVE, sku=f"SKU-{slug}", **extra)
        if image:
            ProductImage.objects.create(product=product, image="p/x.png", is_cover=True)
        return product

    def setUp(self):
        super().setUp()
        self.base = svc.readiness(self.store)["total"]

    def test_complete_products_are_ready_and_out_of_stock_is_informational_only(self):
        self.mk(self.store, "ok-1")
        self.mk(self.store, "sold-out", stock=0)
        r = svc.readiness(self.store)
        self.assertEqual(r["total"] - self.base, 2)
        keys = {row["key"]: row for row in r["rows"]}
        self.assertFalse(keys["out_of_stock"]["blocking"])
        self.assertEqual(r["not_ready"], self.base)                     # nothing new is blocked: sold-out is still ready (shown as unavailable)

    def test_missing_image_price_and_inquiry_mode_are_named_and_blocking(self):
        self.mk(self.store, "no-img", image=False, name="بدون تصویر")
        self.mk(self.store, "zero-price", price="0", name="بدون قیمت")
        r = svc.readiness(self.store)
        rows = {row["key"]: row for row in r["rows"]}
        self.assertTrue(rows["no_image"]["blocking"] and "بدون تصویر" in rows["no_image"]["samples"])
        self.assertTrue(rows["no_price"]["blocking"] and "بدون قیمت" in rows["no_price"]["samples"])
        self.assertIn("اطلاعات ناقص", r["summary"])

    def test_another_stores_products_never_count_or_appear(self):
        other = Store.objects.create(name="O", slug="rdy-other", status=Store.Status.ACTIVE)
        self.mk(other, "other-bad", image=False, name="OTHER-STORE-PRODUCT")
        r = svc.readiness(self.store)
        self.assertNotIn("OTHER-STORE-PRODUCT", str(r))
        self.assertEqual(r["total"], self.base)

    def test_the_page_shows_the_readiness_inside_the_torob_card_and_sends_nothing(self):
        self.mk(self.store, "page-bad", image=False, name="کالای بدون تصویر صفحه")
        self._login(self.owner)
        with mock.patch.object(socket.socket, "connect", side_effect=AssertionError("external connection")):
            torob = view_html(self.client, "torob")
        self.assertIn('data-testid="torob-readiness"', torob)
        self.assertIn("کالای بدون تصویر صفحه", torob)
        self.assertIn("چیزی به ترب ارسال نمی‌شود", torob)

    def test_merchant_center_is_honestly_unsupported_with_no_form_or_connection(self):
        status = svc.merchant_center_status(self.store)
        self.assertEqual(status["state"], "unsupported")
        self.assertIn("ایران", status["text"])
        self._login(self.owner)
        html = all_views_html(self.client)
        future = html.split('data-testid="int-section-future"')[1]
        self.assertIn("پشتیبانی نمی‌شود", future)
        self.assertIn("Merchant Center", future)
        self.assertNotIn("<form", future.split("</details>")[0])
