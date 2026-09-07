import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product, Vendor
from apps.customers.models import Customer
from apps.stores.models import Store

User = get_user_model()


class CartAddViewTests(TestCase):
    def setUp(self):
        store = Store.objects.get(slug="akhlaghi")
        vendor = Vendor.objects.create(store=store, name="فروشگاه", slug="shop-cav")
        category = Category.objects.create(store=store, name="دیجیتال", slug="digital-cav")
        self.product = Product.objects.create(
            store=store, vendor=vendor, category=category, name="کالای نمونه", slug="sample-cav",
            sku="SKU-CAV1", price=Decimal("300000"), stock=10,
        )

    def test_add_to_cart_as_guest_creates_session_cart_item(self):
        response = self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CartItem.objects.count(), 1)
        item = CartItem.objects.first()
        self.assertEqual(item.quantity, 2)
        self.assertIsNone(item.cart.customer)

    def test_add_to_cart_response_updates_header_badge_via_oob(self):
        response = self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 1})
        self.assertContains(response, 'id="cart-count"')
        self.assertContains(response, "hx-swap-oob")

    def test_add_to_cart_triggers_toast(self):
        response = self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 1})
        self.assertIn("HX-Trigger", response.headers)
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertIn(self.product.name, trigger["toast"]["message"])

    def test_add_to_cart_as_logged_in_customer_uses_customer_cart(self):
        user = User.objects.create_user(username="cart_view_user", password="pass12345")
        customer = Customer.objects.create(user=user, full_name="مشتری تست", phone="09121110021")
        self.client.login(username="cart_view_user", password="pass12345")
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 1})
        cart = Cart.objects.get(customer=customer)
        self.assertEqual(cart.items.count(), 1)

    def test_add_to_cart_get_not_allowed(self):
        response = self.client.get(reverse("cart:add", args=[self.product.slug]))
        self.assertEqual(response.status_code, 405)

    def test_add_invalid_quantity_is_rejected_not_added(self):
        """Checkpoint (server-side stock enforcement): a non-numeric quantity
        must be rejected outright — it must NOT silently default to 1 and
        succeed, since that would hide a tampered/malformed request behind
        an apparently successful add."""
        response = self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": "not-a-number"})
        self.assertEqual(response.status_code, 200)  # htmx error convention: 200 + err toast, no body swap
        self.assertEqual(CartItem.objects.count(), 0)
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(trigger["toast"]["type"], "err")

    def test_add_zero_quantity_is_rejected_not_added(self):
        response = self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 0})
        self.assertEqual(CartItem.objects.count(), 0)
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(trigger["toast"]["type"], "err")

    def test_add_negative_quantity_is_rejected_not_added(self):
        response = self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": -5})
        self.assertEqual(CartItem.objects.count(), 0)
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(trigger["toast"]["type"], "err")

    def test_add_zero_stock_product_is_rejected(self):
        zero_stock = Product.objects.create(
            store=Store.objects.get(slug="akhlaghi"), vendor=self.product.vendor, category=self.product.category,
            name="کالای بدون موجودی", slug="sample-cav-zero", sku="SKU-CAV-ZERO",
            price=Decimal("100000"), stock=0,
        )
        response = self.client.post(reverse("cart:add", args=[zero_stock.slug]), {"quantity": 1})
        self.assertEqual(CartItem.objects.count(), 0)
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(trigger["toast"]["type"], "err")

    def test_add_quantity_exceeding_stock_is_rejected(self):
        response = self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 999})
        self.assertEqual(CartItem.objects.count(), 0)
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(trigger["toast"]["type"], "err")

    def test_add_zero_stock_variant_is_rejected(self):
        from apps.catalog.models import ProductVariant

        variant = ProductVariant.objects.create(
            product=self.product, attribute="رنگ", value="قرمز", stock=0, is_active=True,
        )
        response = self.client.post(
            reverse("cart:add", args=[self.product.slug]), {"variant_id": variant.pk, "quantity": 1}
        )
        self.assertEqual(CartItem.objects.count(), 0)
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(trigger["toast"]["type"], "err")

    def test_existing_cart_quantity_counted_toward_stock_limit(self):
        """Adding a second time must count the quantity already in the cart
        against available stock, not just the newly-requested quantity."""
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 8})
        self.assertEqual(CartItem.objects.get().quantity, 8)
        # Stock is 10; 8 already in cart + 5 more would be 13 > 10 → rejected.
        response = self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 5})
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(trigger["toast"]["type"], "err")
        self.assertEqual(CartItem.objects.get().quantity, 8)  # unchanged — not partially bumped

    def test_add_within_remaining_stock_after_existing_cart_quantity_succeeds(self):
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 8})
        response = self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 2})
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(trigger["toast"]["type"], "ok")
        self.assertEqual(CartItem.objects.get().quantity, 10)


class CartDetailViewTests(TestCase):
    def setUp(self):
        store = Store.objects.get(slug="akhlaghi")
        vendor = Vendor.objects.create(store=store, name="فروشگاه", slug="shop-cdv")
        category = Category.objects.create(store=store, name="دیجیتال", slug="digital-cdv")
        self.product = Product.objects.create(
            store=store, vendor=vendor, category=category, name="کالای نمونه", slug="sample-cdv",
            sku="SKU-CDV1", price=Decimal("400000"), discount_percent=25, stock=10,
        )

    def test_empty_cart_shows_empty_state(self):
        response = self.client.get(reverse("cart:detail"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "سبد خرید شما خالی است")

    def test_cart_with_items_shows_totals_from_pricing_service(self):
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 2})
        response = self.client.get(reverse("cart:detail"))
        self.assertContains(response, self.product.name)
        totals = response.context["totals"]
        self.assertEqual(totals["items_total"], Decimal("600000"))
        self.assertEqual(totals["product_discount"], Decimal("200000"))

    def test_cart_page_displays_variants_absolute_price_not_product_base_price(self):
        """رگرسیونِ صفحه‌ی سبد — قبل از این وصله، این صفحه همیشه
        product.final_price نمایش می‌داد، حتی وقتی تنوعِ انتخاب‌شده قیمتِ
        مستقلِ کاملاً متفاوتی داشت (مثلاً قیچیِ ایتالیایی)."""
        from apps.catalog.models import ProductVariant

        store = Store.objects.get(slug="akhlaghi")
        vendor = Vendor.objects.create(store=store, name="فروشگاه", slug="shop-cwv")
        category = Category.objects.create(store=store, name="ابزار", slug="tools-cwv")
        scissors = Product.objects.create(
            store=store, vendor=vendor, category=category,
            name="قیچی", slug="scissors-cwv", sku="SKU-SCISSORS-CWV", price=Decimal("1"),
            product_type=Product.ProductType.VARIABLE,
        )
        italian = ProductVariant.objects.create(
            product=scissors, attribute="کشور سازنده", value="ایتالیایی", price=Decimal("800000"), stock=5,
        )
        self.client.post(
            reverse("cart:add", args=[scissors.slug]), {"variant_id": italian.pk, "quantity": 1}
        )
        response = self.client.get(reverse("cart:detail"))
        self.assertContains(response, "۸۰۰٬۰۰۰")
        self.assertNotContains(response, "۱ تومان")

    def test_cart_with_items_links_continue_button_to_checkout(self):
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 1})
        response = self.client.get(reverse("cart:detail"))
        self.assertContains(response, reverse("orders:checkout-step1"))


class CartItemUpdateRemoveTests(TestCase):
    def setUp(self):
        store = Store.objects.get(slug="akhlaghi")
        vendor = Vendor.objects.create(store=store, name="فروشگاه", slug="shop-ciu")
        category = Category.objects.create(store=store, name="دیجیتال", slug="digital-ciu")
        self.product = Product.objects.create(
            store=store, vendor=vendor, category=category, name="کالای نمونه", slug="sample-ciu",
            sku="SKU-CIU1", price=Decimal("100000"), stock=5,
        )
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 1})
        self.item = CartItem.objects.first()

    def test_update_quantity_changes_item(self):
        response = self.client.post(reverse("cart:item-update", args=[self.item.id]), {"quantity": 3})
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 3)

    def test_update_quantity_clamped_to_available_stock(self):
        self.client.post(reverse("cart:item-update", args=[self.item.id]), {"quantity": 999})
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 5)

    def test_update_quantity_never_goes_below_one(self):
        self.client.post(reverse("cart:item-update", args=[self.item.id]), {"quantity": 0})
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 1)

    def test_remove_item_deletes_it(self):
        response = self.client.post(reverse("cart:item-remove", args=[self.item.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CartItem.objects.count(), 0)
        self.assertContains(response, "سبد خرید شما خالی است")

    def test_cannot_update_another_sessions_item(self):
        self.client.cookies.pop("sessionid", None)
        response = self.client.post(reverse("cart:item-update", args=[self.item.id]), {"quantity": 2})
        self.assertEqual(response.status_code, 404)

    def test_quantity_clamped_to_variant_stock_not_product_stock(self):
        """کالای مادر ۵ عدد موجودی دارد، اما تنوعِ انتخاب‌شده فقط ۲ عدد —
        سقفِ تعداد باید موجودیِ همان تنوع باشد، نه کالای مادر."""
        from apps.catalog.models import ProductVariant

        variant = ProductVariant.objects.create(
            product=self.product, attribute="رنگ", value="قرمز", stock=2, is_active=True,
        )
        self.client.post(
            reverse("cart:add", args=[self.product.slug]), {"variant_id": variant.pk, "quantity": 1}
        )
        variant_item = CartItem.objects.get(variant=variant)
        response = self.client.post(reverse("cart:item-update", args=[variant_item.id]), {"quantity": 999})
        self.assertEqual(response.status_code, 200)
        variant_item.refresh_from_db()
        self.assertEqual(variant_item.quantity, 2)


class CartItemUpdateUsesComposedCartSectionsTests(TestCase):
    """Phase 5: وقتی این Store یک composition واقعی برای صفحه‌ی سبد
    منتشر کرده، htmxِ به‌روزرسانی/حذفِ قلم باید همان section‌ها (با همان
    ترتیبِ پیکربندی‌شده در سازنده) را دوباره رندر کند — نه partialِ
    سخت‌کدشده‌ی قدیمی که ترتیب/تنظیماتِ مرچنت را نادیده می‌گرفت."""

    HOST = "cart-compose-test.example.com"

    def setUp(self):
        from django.test import Client, override_settings
        from django.utils import timezone

        from apps.storefront_builder.models import StorefrontSection
        from apps.storefront_builder.services import layout_service as svc
        from apps.stores.models import StoreDomain

        self._override = override_settings(ALLOWED_HOSTS=[self.HOST, "testserver"])
        self._override.enable()
        self.addCleanup(self._override.disable)

        self.store = Store.objects.get(slug="akhlaghi")
        StoreDomain.objects.create(
            store=self.store, hostname=self.HOST, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        vendor = Vendor.objects.create(store=self.store, name="فروشگاه ترکیب سبد", slug="shop-cart-compose")
        category = Category.objects.create(store=self.store, name="دیجیتال ترکیب سبد", slug="digital-cart-compose")
        self.product = Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="کالای ترکیب سبد", slug="sample-cart-compose",
            sku="SKU-CARTCOMP1", price=Decimal("120000"), stock=5,
        )

        draft = svc.get_or_create_draft(self.store)
        cart_page = draft.get_page("cart")
        cart_page.sections.all().delete()
        # عمداً ترتیبِ معکوس نسبت به پیش‌فرض (خلاصه قبل از قلم‌ها) — دقیقاً
        # همان چیزی که این تست باید بعد از htmx هم دست‌نخورده ببیند.
        StorefrontSection.objects.create(page=cart_page, section_key="cart_summary", order=0)
        StorefrontSection.objects.create(page=cart_page, section_key="cart_items", order=1)
        svc.publish(self.store)

        self.client = Client(HTTP_HOST=self.HOST)
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 1})
        self.item = CartItem.objects.get(product=self.product)

    def test_update_quantity_preserves_merchant_configured_section_order(self):
        response = self.client.post(reverse("cart:item-update", args=[self.item.id]), {"quantity": 2})
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("خلاصه سفارش", body)
        self.assertIn("کالاهای سبد خرید", body)
        self.assertLess(body.index("خلاصه سفارش"), body.index("کالاهای سبد خرید"))

    def test_update_quantity_still_updates_totals_and_item_count(self):
        response = self.client.post(reverse("cart:item-update", args=[self.item.id]), {"quantity": 3})
        body = response.content.decode()
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 3)
        self.assertIn("۳</span> قلم", body)

    def test_remove_last_item_shows_empty_state_within_composed_section(self):
        response = self.client.post(reverse("cart:item-remove", args=[self.item.id]))
        self.assertContains(response, "سبد خرید شما خالی است")
        # cart_summary باید در حالتِ خالی چیزی رندر نکند (مسئولیتِ حالتِ
        # خالی فقط با cart_items است).
        self.assertNotContains(response, "خلاصه سفارش")



class CartHtmxFragmentCarriesUniversalContextTests(TestCase):
    """V05/A04 — the real Cart HTMX fragment (``_render_cart_container``,
    used by both ``cart:item-update`` and ``cart:item-remove``) must go
    through the SAME universal storefront context the full ``cart_detail``
    page uses, so container layout + appearance version are honoured after
    an HTMX action — not the old partial that ignored them.

    A brand_carousel section is placed in a PUBLISHED cart page; after a real
    POST the response context must carry ``use_container_layout`` /
    ``render_containers`` (ABSENT before the fix), retain the Brand placement
    (source/order/settings), render the brand tile + slug link in the
    fragment, preserve the OOB ``id="cart-count"``, and leave quantities /
    totals unchanged by the presentation change.
    """

    HOST = "cart-brand-fragment.example.com"

    def setUp(self):
        from django.test import Client, override_settings
        from django.utils import timezone

        from apps.catalog.models import Brand
        from apps.storefront_builder.models import StorefrontSection
        from apps.storefront_builder.services import layout_service as svc
        from apps.stores.models import StoreDomain

        self._override = override_settings(ALLOWED_HOSTS=[self.HOST, "testserver"])
        self._override.enable()
        self.addCleanup(self._override.disable)

        self.store = Store.objects.get(slug="akhlaghi")
        StoreDomain.objects.create(
            store=self.store, hostname=self.HOST, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        vendor = Vendor.objects.create(store=self.store, name="فروشگاه برند سبد", slug="shop-cart-brand")
        category = Category.objects.create(store=self.store, name="دیجیتال برند سبد", slug="digital-cart-brand")
        self.product = Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="کالای برند سبد", slug="sample-cart-brand",
            sku="SKU-CARTBRAND1", price=Decimal("150000"), stock=5,
        )
        self.brand = Brand.objects.create(
            store=self.store, name="برند سبد قابل مشاهده", slug="cart-visible-brand", is_active=True,
        )

        draft = svc.get_or_create_draft(self.store)
        cart_page = draft.get_page("cart")
        cart_page.sections.all().delete()
        StorefrontSection.objects.create(page=cart_page, section_key="cart_items", order=0)
        # Brand section placed in the published cart page — must survive the HTMX action.
        StorefrontSection.objects.create(
            page=cart_page, section_key="brand_carousel", order=1,
            settings={"title": "برندهای سبد", "display_mode": "grid", "brand_ids": [], "show_view_all": False},
        )
        svc.publish(self.store)

        self.client = Client(HTTP_HOST=self.HOST)
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 2})
        self.item = CartItem.objects.get(product=self.product)

    def test_update_fragment_context_carries_universal_layout_keys(self):
        response = self.client.post(reverse("cart:item-update", args=[self.item.id]), {"quantity": 3})
        self.assertEqual(response.status_code, 200)
        # These keys are produced ONLY by build_universal_storefront_context.
        self.assertIn("use_container_layout", response.context)
        self.assertIn("render_containers", response.context)
        # storefront_page identifies the resolved published cart page.
        self.assertIsNotNone(response.context["storefront_page"])
        self.assertEqual(response.context["storefront_page"].page_type, "cart")

    def test_remove_fragment_context_carries_universal_layout_keys(self):
        response = self.client.post(reverse("cart:item-remove", args=[self.item.id]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("use_container_layout", response.context)
        self.assertIn("render_containers", response.context)

    def test_fragment_retains_brand_placement_source_order_and_settings(self):
        response = self.client.post(reverse("cart:item-update", args=[self.item.id]), {"quantity": 3})
        keys = [i["section"].section_key for i in response.context["render_items"]]
        self.assertIn("brand_carousel", keys)
        # Merchant-configured order preserved: cart_items (0) before brand_carousel (1).
        self.assertLess(keys.index("cart_items"), keys.index("brand_carousel"))
        brand_item = next(i for i in response.context["render_items"] if i["section"].section_key == "brand_carousel")
        self.assertEqual(brand_item["context"]["brand_carousel_settings"]["title"], "برندهای سبد")
        self.assertEqual(brand_item["context"]["brand_carousel_settings"]["display_mode"], "grid")

    def test_fragment_renders_brand_tile_and_slug_link(self):
        response = self.client.post(reverse("cart:item-update", args=[self.item.id]), {"quantity": 3})
        body = response.content.decode()
        self.assertIn("برندهای سبد", body)
        self.assertIn("برند سبد قابل مشاهده", body)
        self.assertIn("?brand=cart-visible-brand", body)
        self.assertIn('class="brand-tile', body)

    def test_fragment_preserves_oob_cart_count(self):
        response = self.client.post(reverse("cart:item-update", args=[self.item.id]), {"quantity": 3})
        self.assertContains(response, 'id="cart-count"')
        self.assertContains(response, "hx-swap-oob")

    def test_fragment_does_not_change_quantities_or_totals(self):
        before = self.client.get(reverse("cart:detail")).context["totals"]["items_total"]
        response = self.client.post(reverse("cart:item-update", args=[self.item.id]), {"quantity": 3})
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 3)
        # items_total scales with the (legitimately-changed) quantity — the
        # presentation change must not corrupt the totals computation.
        self.assertEqual(response.context["totals"]["items_total"], Decimal("450000"))
        self.assertEqual(before, Decimal("300000"))



class CartHtmxFragmentCarriesCollectionContextTests(TestCase):
    """Task 5 (mirror of CartHtmxFragmentCarriesUniversalContextTests for
    Collection): the real Cart HTMX fragment (``_render_cart_container``, used
    by both ``cart:item-update`` and ``cart:item-remove``) must go through the
    SAME universal storefront context the full ``cart_detail`` page uses, so a
    ``collection_tiles`` section placed on a PUBLISHED cart page survives the
    HTMX swap: its placement (source/order/settings) is retained, the
    container-layout keys (``use_container_layout``/``render_containers``,
    already provided by the Task-3 cart adapter) are present, the collection
    tiles + detail link render in the fragment, the OOB cart count is
    preserved, and quantities/totals are unchanged by the presentation change.

    Per the Task-5 plan this should PASS as-is (the Task-3 cart adapter already
    provides container projection) — it is a regression guard proving Collection
    does not expose a new defect in the shared adapter.
    """

    HOST = "cart-collection-fragment.example.com"

    def setUp(self):
        from django.test import Client, override_settings
        from django.utils import timezone

        from apps.catalog.models import MerchantCollection
        from apps.storefront_builder.models import StorefrontSection
        from apps.storefront_builder.services import layout_service as svc
        from apps.stores.models import StoreDomain

        self._override = override_settings(ALLOWED_HOSTS=[self.HOST, "testserver"])
        self._override.enable()
        self.addCleanup(self._override.disable)

        self.store = Store.objects.get(slug="akhlaghi")
        StoreDomain.objects.create(
            store=self.store, hostname=self.HOST, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        vendor = Vendor.objects.create(store=self.store, name="فروشگاه کالکشن سبد", slug="shop-cart-coll")
        category = Category.objects.create(store=self.store, name="دیجیتال کالکشن سبد", slug="digital-cart-coll")
        self.product = Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="کالای کالکشن سبد", slug="sample-cart-coll",
            sku="SKU-CARTCOLL1", price=Decimal("150000"), stock=5,
        )
        # The collection the tiles section advertises (a distinct subject from
        # the cart line product).
        self.collection = MerchantCollection.objects.create(
            store=self.store, name="کالکشن سبد قابل مشاهده", slug="cart-visible-collection", is_active=True,
        )

        draft = svc.get_or_create_draft(self.store)
        cart_page = draft.get_page("cart")
        cart_page.sections.all().delete()
        StorefrontSection.objects.create(page=cart_page, section_key="cart_items", order=0)
        # Collection tiles placed in the published cart page — must survive the HTMX action.
        StorefrontSection.objects.create(
            page=cart_page, section_key="collection_tiles", order=1,
            settings={"title": "کالکشن‌های سبد", "tile_style": "carousel", "collection_ids": []},
        )
        svc.publish(self.store)

        self.client = Client(HTTP_HOST=self.HOST)
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 2})
        self.item = CartItem.objects.get(product=self.product)

    def test_update_fragment_context_carries_universal_layout_keys(self):
        response = self.client.post(reverse("cart:item-update", args=[self.item.id]), {"quantity": 3})
        self.assertEqual(response.status_code, 200)
        # Container-projection keys provided by the Task-3 cart adapter.
        self.assertIn("use_container_layout", response.context)
        self.assertIn("render_containers", response.context)
        self.assertIsNotNone(response.context["storefront_page"])
        self.assertEqual(response.context["storefront_page"].page_type, "cart")

    def test_remove_fragment_context_carries_universal_layout_keys(self):
        response = self.client.post(reverse("cart:item-remove", args=[self.item.id]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("use_container_layout", response.context)
        self.assertIn("render_containers", response.context)

    def test_fragment_retains_collection_placement_source_order_and_settings(self):
        response = self.client.post(reverse("cart:item-update", args=[self.item.id]), {"quantity": 3})
        keys = [i["section"].section_key for i in response.context["render_items"]]
        self.assertIn("collection_tiles", keys)
        # Merchant-configured order preserved: cart_items (0) before collection_tiles (1).
        self.assertLess(keys.index("cart_items"), keys.index("collection_tiles"))
        coll_item = next(
            i for i in response.context["render_items"] if i["section"].section_key == "collection_tiles"
        )
        # Source/settings survive the swap (title + carousel variant preserved).
        self.assertEqual(coll_item["section"].settings["title"], "کالکشن‌های سبد")
        self.assertEqual(coll_item["section"].settings["tile_style"], "carousel")
        # The auto-selected collection is present in the section context.
        tile_names = [row["collection"].name for row in coll_item["context"]["collection_tiles"]]
        self.assertIn("کالکشن سبد قابل مشاهده", tile_names)

    def test_fragment_renders_collection_tile_and_detail_link(self):
        response = self.client.post(reverse("cart:item-update", args=[self.item.id]), {"quantity": 3})
        body = response.content.decode()
        self.assertIn("کالکشن‌های سبد", body)
        self.assertIn("کالکشن سبد قابل مشاهده", body)
        self.assertIn(f"/collections/{self.collection.slug}/", body)
        # The carousel container variant rendered (its CSS now lives in the
        # shared builder stylesheet the cart envelope loads).
        self.assertIn("tiles-carousel collection-tiles-carousel", body)

    def test_fragment_preserves_oob_cart_count(self):
        response = self.client.post(reverse("cart:item-update", args=[self.item.id]), {"quantity": 3})
        self.assertContains(response, 'id="cart-count"')
        self.assertContains(response, "hx-swap-oob")

    def test_fragment_does_not_change_quantities_or_totals(self):
        before = self.client.get(reverse("cart:detail")).context["totals"]["items_total"]
        response = self.client.post(reverse("cart:item-update", args=[self.item.id]), {"quantity": 3})
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 3)
        # items_total scales with the (legitimately-changed) quantity — the
        # Collection presentation change must not corrupt the totals computation.
        self.assertEqual(response.context["totals"]["items_total"], Decimal("450000"))
        self.assertEqual(before, Decimal("300000"))


class CombinedPilotCartFragmentContractTests(TestCase):
    """Task 6 real update/remove proof with both pilot families published."""

    HOST = "task6-combined-cart.example.com"
    FALLBACK_HOST = "task6-fallback-cart.example.com"

    @classmethod
    def setUpTestData(cls):
        from django.core.cache import cache
        from django.utils import timezone

        from apps.catalog.models import Brand, MerchantCollection
        from apps.content.models import FooterSettings
        from apps.core.models import ShopSettings
        from apps.storefront_builder.models import StorefrontSection
        from apps.storefront_builder.services import container_service
        from apps.storefront_builder.services import layout_service as svc
        from apps.stores.models import StoreDomain

        cls.store = Store.objects.create(
            name="Task 6 combined Cart",
            slug="task6-combined-cart",
            status=Store.Status.ACTIVE,
        )
        ShopSettings.provision_for(cls.store)
        FooterSettings.provision_for(cls.store)
        StoreDomain.objects.create(
            store=cls.store,
            hostname=cls.HOST,
            is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED,
            verified_at=timezone.now(),
        )
        vendor = Vendor.objects.create(store=cls.store, name="Task 6 vendor", slug="task6-vendor")
        category = Category.objects.create(store=cls.store, name="Task 6 category", slug="task6-category")
        cls.product = Product.objects.create(
            store=cls.store,
            vendor=vendor,
            category=category,
            name="Task 6 cart product",
            slug="task6-cart-product",
            sku="TASK6-CART-PRODUCT",
            price=Decimal("150000"),
            stock=5,
        )
        cls.brands = (
            Brand.objects.create(
                store=cls.store, name="Task 6 Brand A", slug="task6-brand-a", is_active=True,
            ),
            Brand.objects.create(
                store=cls.store, name="Task 6 Brand B", slug="task6-brand-b", is_active=True,
            ),
        )
        cls.collections = (
            MerchantCollection.objects.create(
                store=cls.store,
                name="Task 6 Collection A",
                slug="task6-collection-a",
                is_active=True,
            ),
            MerchantCollection.objects.create(
                store=cls.store,
                name="Task 6 Collection B",
                slug="task6-collection-b",
                is_active=True,
            ),
        )

        draft = svc.get_or_create_draft(cls.store)
        cart_page = draft.get_page("cart")
        cart_page.containers.all().delete()
        cart_page.sections.all().delete()
        cart_items = StorefrontSection.objects.create(
            page=cart_page, section_key="cart_items", order=0,
        )
        brand_section = StorefrontSection.objects.create(
            page=cart_page,
            section_key="brand_carousel",
            order=1,
            settings={
                "title": "Task 6 cart brands",
                "display_mode": "beauty_tabs",
                "show_view_all": False,
                "brand_ids": [cls.brands[1].pk, cls.brands[0].pk],
            },
        )
        collection_section = StorefrontSection.objects.create(
            page=cart_page,
            section_key="collection_tiles",
            order=2,
            settings={
                "title": "Task 6 cart collections",
                "tile_style": "carousel",
                "collection_ids": [cls.collections[1].pk, cls.collections[0].pk],
            },
        )
        placements = (
            (cart_items, 7),
            (brand_section, 11),
            (collection_section, 23),
        )
        cls.expected_identity = {}
        for order, (section, gap) in enumerate(placements):
            container = container_service.create_empty_container(
                cart_page, "single", order=order, settings={"gap": gap},
            )
            cell = container.cells.get()
            container_service.place_section(cell, section)
            cls.expected_identity[section.section_key] = {
                "container_stable_id": str(container.stable_id),
                "cell_stable_id": str(cell.stable_id),
                "section_stable_id": str(section.stable_id),
                "container_gap": gap,
            }

        # The real limiter remains active. This class publishes exactly once
        # and clears only the cache key owned by its unique test Store.
        cls.publish_cache_key = f"ratelimit:storefront_layout.publish:{cls.store.pk}"
        cache.delete(cls.publish_cache_key)
        cls.addClassCleanup(cache.delete, cls.publish_cache_key)
        svc.publish(cls.store)

        cls.fallback_store = Store.objects.create(
            name="Task 6 fallback Cart",
            slug="task6-fallback-cart",
            status=Store.Status.ACTIVE,
        )
        ShopSettings.provision_for(cls.fallback_store)
        FooterSettings.provision_for(cls.fallback_store)
        StoreDomain.objects.create(
            store=cls.fallback_store,
            hostname=cls.FALLBACK_HOST,
            is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED,
            verified_at=timezone.now(),
        )
        fallback_vendor = Vendor.objects.create(
            store=cls.fallback_store, name="Task 6 fallback vendor", slug="task6-fallback-vendor",
        )
        fallback_category = Category.objects.create(
            store=cls.fallback_store,
            name="Task 6 fallback category",
            slug="task6-fallback-category",
        )
        cls.fallback_product = Product.objects.create(
            store=cls.fallback_store,
            vendor=fallback_vendor,
            category=fallback_category,
            name="Task 6 fallback product",
            slug="task6-fallback-product",
            sku="TASK6-FALLBACK-PRODUCT",
            price=Decimal("100000"),
            stock=5,
        )

    def setUp(self):
        from django.test import Client, override_settings

        self._hosts = override_settings(
            ALLOWED_HOSTS=[self.HOST, self.FALLBACK_HOST, "testserver"],
        )
        self._hosts.enable()
        self.addCleanup(self._hosts.disable)

        self.client = Client(HTTP_HOST=self.HOST)
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 2})
        self.item = CartItem.objects.get(product=self.product)

        self.fallback_client = Client(HTTP_HOST=self.FALLBACK_HOST)
        self.fallback_client.post(
            reverse("cart:add", args=[self.fallback_product.slug]), {"quantity": 2},
        )
        self.fallback_item = CartItem.objects.get(product=self.fallback_product)

    @staticmethod
    def _pilot_projection(response):
        projection = {}
        for composition in response.context["render_containers"]:
            for cell_entry in composition["cells"]:
                for item in cell_entry["items"]:
                    section_key = item["section"].section_key
                    if section_key not in {"brand_carousel", "collection_tiles"}:
                        continue
                    if section_key == "brand_carousel":
                        resource_ids = [resource.pk for resource in item["context"]["brands"]]
                    else:
                        resource_ids = [
                            row["collection"].pk for row in item["context"]["collection_tiles"]
                        ]
                    projection[section_key] = {
                        "container_stable_id": str(composition["container"].stable_id),
                        "cell_stable_id": str(cell_entry["cell"].stable_id),
                        "section_stable_id": str(item["section"].stable_id),
                        "container_gap": composition["settings"]["gap"],
                        "settings": item["context"]["settings"],
                        "resource_ids": resource_ids,
                    }
        return projection

    def _assert_combined_layout(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertIs(response.context["use_container_layout"], True)
        keys = [item["section"].section_key for item in response.context["render_items"]]
        self.assertEqual(keys, ["cart_items", "brand_carousel", "collection_tiles"])

        projection = self._pilot_projection(response)
        self.assertEqual(set(projection), {"brand_carousel", "collection_tiles"})
        self.assertNotEqual(
            projection["brand_carousel"]["container_stable_id"],
            projection["collection_tiles"]["container_stable_id"],
        )
        self.assertNotEqual(
            projection["brand_carousel"]["cell_stable_id"],
            projection["collection_tiles"]["cell_stable_id"],
        )
        for section_key in ("brand_carousel", "collection_tiles"):
            for identity_key, expected in self.expected_identity[section_key].items():
                self.assertEqual(projection[section_key][identity_key], expected)

        brand = projection["brand_carousel"]
        self.assertEqual(brand["settings"]["title"], "Task 6 cart brands")
        self.assertEqual(brand["settings"]["display_mode"], "beauty_tabs")
        self.assertEqual(brand["resource_ids"], [self.brands[1].pk, self.brands[0].pk])
        collection = projection["collection_tiles"]
        self.assertEqual(collection["settings"]["title"], "Task 6 cart collections")
        self.assertEqual(collection["settings"]["tile_style"], "carousel")
        self.assertEqual(
            collection["resource_ids"], [self.collections[1].pk, self.collections[0].pk],
        )

        body = response.content.decode()
        for expected_text in (
            "Task 6 cart brands",
            "Task 6 Brand A",
            "Task 6 Brand B",
            "Task 6 cart collections",
            "Task 6 Collection A",
            "Task 6 Collection B",
        ):
            self.assertIn(expected_text, body)
        for editor_hook in (
            "sfb-rsec-drag-handle",
            "sfb-rsec-toolbar",
            "sfb-builder-container",
            "data-section-id=",
        ):
            self.assertNotIn(editor_hook, body)
        return projection

    def test_real_update_and_remove_match_full_detail_without_commerce_drift(self):
        update = self.client.post(
            reverse("cart:item-update", args=[self.item.pk]), {"quantity": 3},
        )
        update_projection = self._assert_combined_layout(update)
        detail_after_update = self.client.get(reverse("cart:detail"))
        self.assertEqual(update_projection, self._pilot_projection(detail_after_update))
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 3)
        self.assertEqual(update.context["item_count"], 3)
        self.assertEqual(update.context["totals"]["items_total"], Decimal("450000"))
        self.assertNotIn("errors", update.context)
        self.assertNotIn("HX-Trigger", update.headers)
        self.assertContains(update, 'id="cart-count"')
        self.assertContains(update, "hx-swap-oob")

        remove = self.client.post(reverse("cart:item-remove", args=[self.item.pk]))
        remove_projection = self._assert_combined_layout(remove)
        detail_after_remove = self.client.get(reverse("cart:detail"))
        self.assertEqual(remove_projection, self._pilot_projection(detail_after_remove))
        self.assertFalse(CartItem.objects.filter(pk=self.item.pk).exists())
        self.assertEqual(remove.context["item_count"], 0)
        self.assertEqual(remove.context["totals"]["items_total"], 0)
        self.assertNotIn("errors", remove.context)
        self.assertNotIn("HX-Trigger", remove.headers)

    def test_stock_error_keeps_combined_presentation_and_existing_error_contract(self):
        self.product.stock = 0
        self.product.save(update_fields=["stock"])

        response = self.client.post(
            reverse("cart:item-update", args=[self.item.pk]), {"quantity": 3},
        )
        response_projection = self._assert_combined_layout(response)
        detail_after_error = self.client.get(reverse("cart:detail"))
        self.assertEqual(response_projection, self._pilot_projection(detail_after_error))
        self.assertFalse(CartItem.objects.filter(pk=self.item.pk).exists())
        self.assertEqual(response.context["item_count"], 0)
        self.assertEqual(response.context["totals"]["items_total"], 0)
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(trigger["toast"]["type"], "err")
        self.assertIn("موجود نیست", trigger["toast"]["message"])

    def test_absent_published_composition_uses_safe_fallback_for_update_and_remove(self):
        update = self.fallback_client.post(
            reverse("cart:item-update", args=[self.fallback_item.pk]), {"quantity": 3},
        )
        self.assertEqual(update.status_code, 200)
        self.assertIs(update.context["use_container_layout"], False)
        self.assertEqual(update.context["render_containers"], [])
        self.assertIsNone(update.context["storefront_page"])
        self.assertEqual(
            [item["section"].section_key for item in update.context["render_items"]],
            ["cart_items", "cart_summary"],
        )
        self.fallback_item.refresh_from_db()
        self.assertEqual(self.fallback_item.quantity, 3)
        self.assertEqual(update.context["item_count"], 3)
        self.assertEqual(update.context["totals"]["items_total"], Decimal("300000"))
        self.assertNotIn("errors", update.context)
        self.assertNotIn("sfb-rsec-drag-handle", update.content.decode())
        fallback_detail = self.fallback_client.get(reverse("cart:detail"))
        self.assertEqual(
            [item["section"].section_key for item in update.context["render_items"]],
            [item["section"].section_key for item in fallback_detail.context["render_items"]],
        )

        remove = self.fallback_client.post(
            reverse("cart:item-remove", args=[self.fallback_item.pk]),
        )
        self.assertEqual(remove.status_code, 200)
        self.assertIs(remove.context["use_container_layout"], False)
        self.assertEqual(remove.context["render_containers"], [])
        self.assertFalse(CartItem.objects.filter(pk=self.fallback_item.pk).exists())
        self.assertEqual(remove.context["item_count"], 0)
        self.assertEqual(remove.context["totals"]["items_total"], 0)
        self.assertNotIn("errors", remove.context)
