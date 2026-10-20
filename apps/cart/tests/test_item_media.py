"""RS-10 — cart/checkout/mini-cart show the real product (or chosen variant) image, from ONE resolver."""

import io
import shutil
import tempfile
from decimal import Decimal

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.cart.models import Cart, CartItem
from apps.cart.services import item_media
from apps.catalog.models import Category, Product, ProductImage, ProductVariant, Vendor
from apps.orders.models import PaymentGateway, ShippingMethod
from apps.stores.models import Store


_MEDIA = tempfile.mkdtemp(prefix="rs10-media-")


def _png(color):
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), color).save(buf, "PNG")
    return ContentFile(buf.getvalue(), name=f"{color}.png")


@override_settings(MEDIA_ROOT=_MEDIA)
class CartItemImageTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_MEDIA, ignore_errors=True)

    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        vendor = Vendor.objects.create(store=self.store, name="V", slug="v-im")
        cat = Category.objects.create(store=self.store, name="C", slug="c-im")
        self.product = Product.objects.create(
            store=self.store, vendor=vendor, category=cat, name="کتانی رانینگ", slug="k-im", sku="IM1", price=Decimal("100000"),
            stock=9, product_type=Product.ProductType.VARIABLE,
        )
        self.cover = ProductImage.objects.create(product=self.product, image=_png("red"), alt="کاور", is_cover=True)
        self.black = ProductVariant.objects.create(product=self.product, attribute="رنگ", value="مشکی", price=Decimal("100000"), stock=5)
        self.white = ProductVariant.objects.create(product=self.product, attribute="رنگ", value="سفید", price=Decimal("100000"), stock=5)
        self.black_img = ProductImage.objects.create(product=self.product, variant=self.black, image=_png("black"), alt="مشکی")
        ShippingMethod.objects.create(store=self.store, name="پست", slug="p-im", cost=1000)
        PaymentGateway.objects.create(store=self.store, name="G", slug="g-im")
        self.cart = Cart.objects.create(session_key="im")

    def item(self, variant):
        return CartItem.objects.create(cart=self.cart, product=self.product, variant=variant, quantity=1, unit_price=Decimal("100000"))

    def test_variant_image_beats_cover_and_cover_is_the_fallback(self):
        black, white = self.item(self.black), self.item(self.white)
        self.assertIn("black", item_media.cart_item_image(black).url)
        self.assertEqual(item_media.cart_item_image(black).alt, "مشکی")
        self.assertEqual(item_media.cart_item_image(white).url, self.cover.image.url)

    def test_no_image_at_all_returns_none_so_the_template_shows_the_standard_placeholder(self):
        ProductImage.objects.all().delete()
        self.assertIsNone(item_media.cart_item_image(self.item(self.black)))

    def test_a_missing_file_is_not_rendered_as_a_broken_image(self):
        default_storage.delete(self.cover.image.name)
        self.assertIsNone(item_media.cart_item_image(self.item(self.white)))

    def test_cart_page_and_checkout_show_the_variant_image(self):
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 1, "variant_id": self.black.pk})
        cart_html = self.client.get(reverse("cart:detail")).content.decode()
        checkout_html = self.client.get(reverse("orders:checkout-step1")).content.decode()
        for html in (cart_html, checkout_html):
            self.assertIn('class="thumb has-img"', html)
            self.assertIn("black", html)
            self.assertNotIn("thumb-fallback", html)

    def test_real_image_wins_over_the_emoji_placeholder_which_only_appears_without_media(self):
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 1, "variant_id": self.white.pk})
        self.assertNotIn("thumb-fallback", self.client.get(reverse("cart:detail")).content.decode())
        ProductImage.objects.all().delete()
        self.assertIn("thumb-fallback", self.client.get(reverse("cart:detail")).content.decode())
