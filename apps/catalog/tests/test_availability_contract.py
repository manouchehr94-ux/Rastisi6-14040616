"""Availability contract: ONE definition (stock − active reservations; variants
for variable products) drives the home rails (exclude), the listing/collection
order (available first, user sort inside each group) and the in_stock filter."""

from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import (
    Category, InventoryReservation, Product, ProductVariant, Vendor,
)
from apps.catalog.services import availability_service, inventory_service
from apps.stores.models import Store


class AvailabilityBase(TestCase):
    def setUp(self):
        cache.clear()
        self.store = Store.objects.get(slug="akhlaghi")
        self.vendor = Vendor.objects.create(store=self.store, name="ف", slug="shop-av")
        self.cat = Category.objects.create(store=self.store, name="د", slug="cat-av")
        self.n = 0

    def make(self, slug, *, stock=5, price=100000, ptype=Product.ProductType.SIMPLE):
        self.n += 1
        return Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.cat, name=slug, slug=slug,
            sku=f"AV{self.n}", price=Decimal(price), stock=stock, product_type=ptype,
        )

    def variant(self, product, value, stock, active=True):
        return ProductVariant.objects.create(
            product=product, store=self.store, attribute="سایز", value=value, stock=stock, is_active=active,
        )

    def reserve(self, product, qty, variant=None):
        return InventoryReservation.objects.create(
            store=self.store, product=product, variant=variant, quantity=qty,
            status=InventoryReservation.Status.ACTIVE,
        )

    def available(self):
        return set(
            availability_service.available_only(Product.objects.filter(store=self.store)).values_list("slug", flat=True)
        )


class DefinitionTests(AvailabilityBase):
    def test_simple_product_stock_and_reservations(self):
        self.make("in-stock")
        self.make("zero", stock=0)
        reserved = self.make("all-reserved", stock=3)
        self.reserve(reserved, 3)
        partly = self.make("part-reserved", stock=3)
        self.reserve(partly, 2)
        self.assertEqual(self.available(), {"in-stock", "part-reserved"})

    def test_variable_product_needs_a_sellable_active_variant(self):
        sellable = self.make("var-ok", stock=0, ptype=Product.ProductType.VARIABLE)
        self.variant(sellable, "M", 2)
        none_left = self.make("var-none", stock=99, ptype=Product.ProductType.VARIABLE)
        self.variant(none_left, "M", 0)
        inactive = self.make("var-inactive", stock=99, ptype=Product.ProductType.VARIABLE)
        self.variant(inactive, "M", 5, active=False)
        reserved = self.make("var-reserved", stock=0, ptype=Product.ProductType.VARIABLE)
        v = self.variant(reserved, "L", 2)
        self.reserve(reserved, 2, variant=v)
        self.assertEqual(self.available(), {"var-ok"})

    def test_matches_inventory_service_for_every_simple_case(self):
        products = [self.make(f"s{i}", stock=i) for i in range(4)]
        self.reserve(products[2], 1)
        self.reserve(products[3], 3)
        in_set = self.available()
        for p in products:
            p.refresh_from_db()
            self.assertEqual(
                p.slug in in_set,
                inventory_service.get_available_quantity(product=p) > 0, p.slug,
            )

    def test_other_store_reservations_do_not_leak(self):
        p = self.make("mine", stock=2)
        self.assertEqual(self.available(), {"mine"})
        self.reserve(p, 2)
        self.assertEqual(self.available(), set())


class OrderingTests(AvailabilityBase):
    def test_available_first_keeps_user_sort_inside_each_group(self):
        a_cheap = self.make("a-cheap", price=1000)
        a_dear = self.make("a-dear", price=9000)
        o_cheap = self.make("o-cheap", stock=0, price=500)
        o_dear = self.make("o-dear", stock=0, price=8000)
        qs = availability_service.order_available_first(Product.objects.filter(store=self.store), "price", "id")
        self.assertEqual(
            [p.slug for p in qs], ["a-cheap", "a-dear", "o-cheap", "o-dear"],
        )
        self.assertEqual(
            [p.slug for p in availability_service.order_available_first(
                Product.objects.filter(store=self.store), "-price", "id")],
            ["a-dear", "a-cheap", "o-dear", "o-cheap"],
        )
        self.assertTrue(all((a_cheap, a_dear, o_cheap, o_dear)))

    def test_listing_page_puts_unavailable_last_and_in_stock_filter_excludes_them(self):
        self.make("zz-out", stock=0, price=1)       # would be first by price
        self.make("aa-in", stock=4, price=999999)
        response = self.client.get(reverse("catalog:product-list"), {"sort": "price_asc"})
        body = response.content.decode()
        self.assertLess(body.index("aa-in"), body.index("zz-out"))
        only = self.client.get(reverse("catalog:product-list"), {"in_stock": "1"})
        self.assertContains(only, "aa-in")
        self.assertNotContains(only, "zz-out")

    def test_partition_and_exclude_helpers_are_stable(self):
        a = self.make("p-a")
        o = self.make("p-o", stock=0)
        b = self.make("p-b")
        self.assertEqual(
            [p.slug for p in availability_service.partition_available_first([a, o, b])], ["p-a", "p-b", "p-o"],
        )
        self.assertEqual([p.slug for p in availability_service.only_available([a, o, b])], ["p-a", "p-b"])


class HomeRailTests(AvailabilityBase):
    """Home rails never choose an unavailable product (and do not backfill the
    rail with one); the same rail on another page lists available first."""

    def section(self, page_type, **settings):
        from types import SimpleNamespace

        return SimpleNamespace(
            page=SimpleNamespace(page_type=page_type),
            settings={"item_limit": 4, **settings},
        )

    def test_newest_rail_excludes_unavailable_on_home_and_does_not_backfill(self):
        from apps.storefront_builder.services import render_service

        self.make("h-in-1")
        self.make("h-out", stock=0)
        self.make("h-in-2")
        home = render_service._newest_products_context(self.store, self.section("home"))
        self.assertEqual(sorted(p.slug for p in home["products"]), ["h-in-1", "h-in-2"])
        listing = render_service._newest_products_context(self.store, self.section("listing"))
        listed = list(listing["products"])
        self.assertEqual(len(listed), 3)
        self.assertEqual(listed[-1].slug, "h-out")

    def test_zero_available_products_gives_an_empty_rail_not_unavailable_filler(self):
        from apps.storefront_builder.services import render_service

        self.make("only-out", stock=0)
        home = render_service._newest_products_context(self.store, self.section("home"))
        self.assertEqual(list(home["products"]), [])

    def test_data_source_resolvers_follow_the_same_rule(self):
        from apps.storefront_builder.services import section_data_service as sds

        a = self.make("r-in")
        o = self.make("r-out", stock=0)
        settings = {"item_limit": 4, "data_source": "manual", "product_ids": [o.pk, a.pk]}
        excl, _ = sds.resolve_products(self.store, settings, availability=sds.AVAILABILITY_EXCLUDE)
        self.assertEqual([p.slug for p in excl], ["r-in"])
        first, _ = sds.resolve_products(self.store, settings, availability=sds.AVAILABILITY_FIRST)
        self.assertEqual([p.slug for p in first], ["r-in", "r-out"])
        untouched, _ = sds.resolve_products(self.store, settings)
        self.assertEqual([p.slug for p in untouched], ["r-out", "r-in"])

    def test_amazing_offers_never_features_an_unavailable_product_on_home(self):
        from apps.storefront_builder.services import render_service

        out = self.make("ao-out", stock=0)
        out.discount_percent = 50
        out.save(update_fields=["discount_percent"])
        live = self.make("ao-in")
        live.discount_percent = 10
        live.save(update_fields=["discount_percent"])
        context = render_service._amazing_offers_context(self.store, self.section("home"))
        self.assertEqual([p.slug for p in context["products"]], ["ao-in"])


class CardFlagFollowsTheContractTests(AvailabilityBase):
    def test_variable_product_with_sellable_variant_is_not_badged_out_of_stock(self):
        from apps.catalog.services.product_card_service import build_product_card_data

        p = self.make("var-card", stock=0, ptype=Product.ProductType.VARIABLE)
        self.variant(p, "M", 3)
        self.assertFalse(build_product_card_data(p).is_out_of_stock)

    def test_variable_product_without_sellable_variant_is_out_of_stock(self):
        from apps.catalog.services.product_card_service import build_product_card_data

        p = self.make("var-card-out", stock=9, ptype=Product.ProductType.VARIABLE)
        self.variant(p, "M", 0)
        self.assertTrue(build_product_card_data(p).is_out_of_stock)

    def test_annotated_products_use_the_annotation_without_extra_queries(self):
        from apps.catalog.services.product_card_service import build_product_card_data

        self.make("ann-in")
        self.make("ann-out", stock=0)
        products = list(availability_service.order_available_first(Product.objects.filter(store=self.store), "id"))
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as queries:
            flags = [build_product_card_data(p).is_out_of_stock for p in products]
        self.assertEqual(flags, [False, True])
        availability_queries = [
            q["sql"] for q in queries.captured_queries
            if "catalog_inventoryreservation" in q["sql"] or "catalog_productvariant" in q["sql"]
        ]
        self.assertEqual(availability_queries, [])
