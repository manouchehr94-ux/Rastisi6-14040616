"""«استعلام قیمت»: precedence (explicit product > category chain/collection >
standard), server-side purchase blocking on EVERY add path and at order
placement, no price leaking to the page/SEO, and an honest destination."""

import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.cart.models import Cart, CartItem
from apps.cart.services.cart_service import PriceInquiryOnlyError, add_item_to_cart
from apps.catalog.models import (
    Category, MerchantCollection, MerchantCollectionItem, PriceMode, Product, Vendor,
)
from apps.catalog.services import pricing_mode_service as pms
from apps.catalog.services.product_card_service import build_product_card_data
from apps.content.models import ContentPage
from apps.customers.models import Customer
from apps.orders.models import Order
from apps.stores.models import Store

User = get_user_model()


class InquiryBase(TestCase):
    def setUp(self):
        cache.clear()
        self.store = Store.objects.get(slug="akhlaghi")
        self.vendor = Vendor.objects.create(store=self.store, name="ف", slug="shop-inq")
        self.group = Category.objects.create(store=self.store, name="گروه", slug="grp-inq")
        self.sub = Category.objects.create(store=self.store, name="زیرگروه", slug="sub-inq", parent=self.group)
        self.other = Category.objects.create(store=self.store, name="دیگر", slug="oth-inq")
        self.n = 0

    def make(self, slug, category=None, **extra):
        self.n += 1
        return Product.objects.create(
            store=self.store, vendor=self.vendor, category=category or self.other, name=slug, slug=slug,
            sku=f"INQ{self.n}", price=Decimal("100000"), stock=5, **extra,
        )

    def refresh(self, *products):
        for p in products:
            p.refresh_from_db()


class PrecedenceTests(InquiryBase):
    def test_default_is_standard(self):
        p = self.make("plain")
        self.assertFalse(p.is_price_inquiry)

    def test_explicit_product_inquiry(self):
        p = self.make("explicit", price_mode_override=PriceMode.INQUIRY)
        self.assertTrue(p.is_price_inquiry)

    def test_category_rule_covers_descendants_and_can_be_cleared(self):
        a = self.make("in-group", category=self.group)
        b = self.make("in-sub", category=self.sub)
        c = self.make("elsewhere", category=self.other)
        self.group.price_mode = PriceMode.INQUIRY
        self.group.save()
        self.refresh(a, b, c)
        self.assertEqual((a.is_price_inquiry, b.is_price_inquiry, c.is_price_inquiry), (True, True, False))
        self.group.price_mode = PriceMode.STANDARD
        self.group.save()
        self.refresh(a, b)
        self.assertEqual((a.is_price_inquiry, b.is_price_inquiry), (False, False))

    def test_explicit_standard_beats_group_rule(self):
        exempt = self.make("exempt", category=self.group, price_mode_override=PriceMode.STANDARD)
        covered = self.make("covered", category=self.group)
        self.group.price_mode = PriceMode.INQUIRY
        self.group.save()
        self.refresh(exempt, covered)
        self.assertFalse(exempt.is_price_inquiry)
        self.assertTrue(covered.is_price_inquiry)

    def test_collection_rule_follows_membership_and_activity(self):
        a, b = self.make("c-a"), self.make("c-b")
        col = MerchantCollection.objects.create(
            store=self.store, name="انتخابی", slug="sel-inq", price_mode=PriceMode.INQUIRY,
        )
        MerchantCollectionItem.objects.create(collection=col, product=a)
        self.refresh(a, b)
        self.assertEqual((a.is_price_inquiry, b.is_price_inquiry), (True, False))
        MerchantCollectionItem.objects.filter(collection=col, product=a).delete()
        self.refresh(a)
        self.assertFalse(a.is_price_inquiry)
        MerchantCollectionItem.objects.create(collection=col, product=b)
        col.is_active = False
        col.save()
        self.refresh(b)
        self.assertFalse(b.is_price_inquiry)

    def test_moving_product_between_categories_resyncs(self):
        self.group.price_mode = PriceMode.INQUIRY
        self.group.save()
        p = self.make("mover", category=self.other)
        self.assertFalse(p.is_price_inquiry)
        p.category = self.group
        p.save()
        self.refresh(p)
        self.assertTrue(p.is_price_inquiry)

    def test_bulk_set_never_touches_other_store(self):
        from apps.stores.services.platform_code_service import generate_unique_platform_code

        mine = self.make("mine-bulk")
        other_store = Store.objects.create(
            name="O", slug="inq-other", status=Store.Status.ACTIVE, platform_code=generate_unique_platform_code(),
        )
        vendor = Vendor.objects.create(store=other_store, name="ف", slug="shop-inq-o")
        theirs = Product.objects.create(
            store=other_store, vendor=vendor, name="theirs", slug="theirs", sku="THEIRS", price=Decimal("5"), stock=1,
        )
        updated = pms.bulk_set_product_mode(self.store, [mine, theirs], PriceMode.INQUIRY)
        self.refresh(mine, theirs)
        self.assertEqual(updated, 1)
        self.assertTrue(mine.is_price_inquiry)
        self.assertFalse(theirs.is_price_inquiry)
        self.assertEqual(theirs.price_mode_override, "")

    def test_real_price_stock_and_discount_are_never_modified(self):
        p = self.make("untouched", discount_percent=10)
        pms.set_product_mode(p, PriceMode.INQUIRY)
        self.refresh(p)
        self.assertEqual((p.price, p.stock, p.discount_percent), (Decimal("100000"), 5, 10))


class PurchaseBlockingTests(InquiryBase):
    def setUp(self):
        super().setUp()
        self.product = self.make("blocked", price_mode_override=PriceMode.INQUIRY)

    def test_service_add_is_refused_for_simple_product(self):
        cart = Cart.objects.create(session_key="s-inq")
        with self.assertRaises(PriceInquiryOnlyError):
            add_item_to_cart(cart, self.product, None, 1)
        self.assertFalse(cart.items.exists())

    def test_http_add_is_refused_with_message_and_adds_nothing(self):
        response = self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 1})
        self.assertEqual(CartItem.objects.count(), 0)
        trigger = json.loads(response.headers.get("HX-Trigger", "{}"))
        self.assertIn("استعلام", json.dumps(trigger, ensure_ascii=False))

    def test_quick_add_style_hx_post_is_refused_too(self):
        response = self.client.post(
            reverse("cart:add", args=[self.product.slug]), {"quantity": 1}, HTTP_HX_REQUEST="true",
        )
        self.assertEqual(CartItem.objects.count(), 0)
        self.assertNotEqual(response.status_code, 500)

    def test_stale_cart_item_cannot_be_ordered_after_product_becomes_inquiry(self):
        product = self.make("later-inquiry")
        user = User.objects.create_user(username="09120000555", password="pass12345")
        customer = Customer.objects.create(user=user, full_name="م", phone="09120000555")
        cart = Cart.objects.create(customer=customer)
        add_item_to_cart(cart, product, None, 1)
        pms.set_product_mode(product, PriceMode.INQUIRY)
        from apps.orders.services.order_service import _lock_and_revalidate_items

        with self.assertRaises(ValueError) as ctx:
            _lock_and_revalidate_items(list(cart.items.select_related("product", "variant")), store=self.store)
        self.assertIn("استعلام", str(ctx.exception))
        self.assertFalse(Order.objects.filter(customer=customer).exists())


class DisplayTests(InquiryBase):
    def test_card_hides_price_discount_and_quick_add(self):
        p = self.make("card-inq", discount_percent=30, price_mode_override=PriceMode.INQUIRY)
        data = build_product_card_data(p)
        self.assertTrue(data.is_price_inquiry)
        self.assertFalse(data.is_on_sale)
        self.assertEqual(data.discount_percent, 0)
        self.assertFalse(data.is_quick_add_eligible)

    def _about(self):
        return ContentPage.objects.create(
            store=self.store, title="درباره ما", slug="about-us", status=ContentPage.Status.PUBLISHED,
            published_at=timezone.now(),
        )

    def test_destination_is_this_stores_about_page_or_nothing(self):
        self.assertIsNone(pms.inquiry_destination_url(self.store))
        page = self._about()
        self.assertEqual(pms.inquiry_destination_url(self.store), page.get_absolute_url())

    def test_listing_shows_inquiry_label_not_the_price(self):
        self._about()
        self.make("shown-inq", price_mode_override=PriceMode.INQUIRY)
        self.make("shown-std")
        html = self.client.get(reverse("catalog:product-list")).content.decode()
        self.assertIn("استعلام قیمت", html)
        self.assertIn("about-us", html)

    def test_product_page_has_no_price_json_no_buy_button_and_no_offer_in_seo(self):
        self._about()
        p = self.make("pdp-inq", discount_percent=20, price_mode_override=PriceMode.INQUIRY)
        html = self.client.get(reverse("catalog:product-detail", args=[p.slug])).content.decode()
        self.assertIn("استعلام قیمت", html)
        self.assertNotIn("افزودن به سبد خرید", html)
        self.assertNotIn('"offers"', html)
        self.assertNotIn("product:price:amount", html)
        self.assertNotIn("100000", html.replace("۱۰۰", ""))  # raw price must not be embedded

    def test_price_filter_and_price_sort_treat_inquiry_products_honestly(self):
        self.make("cheap", price_mode_override=PriceMode.STANDARD)
        inq = self.make("inq-p", price_mode_override=PriceMode.INQUIRY)
        inq.price = Decimal("1")
        inq.save(update_fields=["price"])
        filtered = self.client.get(reverse("catalog:product-list"), {"min_price": "0", "max_price": "99999999"})
        self.assertContains(filtered, "cheap")
        self.assertNotContains(filtered, "inq-p")
        ordered = self.client.get(reverse("catalog:product-list"), {"sort": "price_asc"}).content.decode()
        self.assertLess(ordered.index("cheap"), ordered.index("inq-p"))


class RecomputeIsNotTriggeredByIrrelevantSavesTests(InquiryBase):
    def test_rename_or_reorder_of_a_category_or_collection_does_not_recompute_the_store(self):
        from unittest import mock

        col = MerchantCollection.objects.create(store=self.store, name="ک", slug="irr-col")
        with mock.patch.object(pms, "recompute_store") as spy:
            self.group.name = "نام جدید"
            self.group.order = 7
            self.group.save()
            col.name = "نام کالکشن"
            col.save()
            self.assertEqual(spy.call_count, 0)
            self.group.price_mode = PriceMode.INQUIRY
            self.group.save()
            col.is_active = False
            col.save()
            self.assertEqual(spy.call_count, 2)

    def test_reparenting_a_category_resyncs_its_products(self):
        self.group.price_mode = PriceMode.INQUIRY
        self.group.save()
        p = self.make("reparent", category=self.other)
        self.assertFalse(p.is_price_inquiry)
        self.other.parent = self.group
        self.other.save()
        self.refresh(p)
        self.assertTrue(p.is_price_inquiry)


class CascadeDeletionIsSafeTests(InquiryBase):
    def test_deleting_a_product_or_a_collection_with_members_does_not_crash(self):
        a, b = self.make("del-a"), self.make("del-b")
        col = MerchantCollection.objects.create(store=self.store, name="ح", slug="del-col", price_mode=PriceMode.INQUIRY)
        MerchantCollectionItem.objects.create(collection=col, product=a)
        MerchantCollectionItem.objects.create(collection=col, product=b)
        a.delete()
        self.refresh(b)
        self.assertTrue(b.is_price_inquiry)
        col.delete()
        self.refresh(b)
        self.assertFalse(b.is_price_inquiry)
