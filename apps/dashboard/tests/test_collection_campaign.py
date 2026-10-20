"""RS-01 — opt-in, explicit collection campaign: one price/deadline source (Product discount fields), server clock,
preview before write, store scoping, boundary and timezone behaviour."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import MerchantCollection, Product, Vendor
from apps.catalog.services import collection_service, promotion_service
from apps.stores.models import Store, StoreMembership

User = get_user_model()
HOST = "campaign.rastisi.localhost"


def _product(store, n, price="1000000", **kw):
    vendor, _ = Vendor.objects.get_or_create(store=store, slug=f"v-{store.pk}", defaults={"name": "فروشنده"})
    return Product.objects.create(
        store=store, vendor=vendor, name=f"کالا {n}", slug=f"camp-{store.pk}-{n}", sku=f"CAMP-{store.pk}-{n}",
        price=Decimal(price), status=Product.Status.ACTIVE, **kw,
    )


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class CampaignServiceTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        self.other = Store.objects.create(name="دیگر", slug="camp-other")
        self.coll = MerchantCollection.objects.create(store=self.store, name="منتخب", slug="camp-picks")
        self.products = [_product(self.store, i) for i in range(3)]
        for p in self.products:
            collection_service.add_product(self.coll, p)
        self.now = timezone.now()

    def schedule(self, **kw):
        args = dict(discount_percent=20, starts_at=self.now, ends_at=self.now + timedelta(hours=5), now=self.now)
        args.update(kw)
        return promotion_service.schedule_collection_promotion(self.coll, **args)

    def test_nothing_is_applied_without_an_explicit_call(self):
        for p in self.products:
            p.refresh_from_db()
            self.assertEqual((p.discount_percent, p.discount_ends_at), (0, None))
        self.assertEqual(promotion_service.collection_promotion_summary(self.coll, self.now)["status"], "none")

    def test_schedule_writes_the_one_source_and_status_follows_the_clock(self):
        self.schedule(starts_at=self.now + timedelta(hours=1), ends_at=self.now + timedelta(hours=5))
        summary = promotion_service.collection_promotion_summary(self.coll, self.now)
        self.assertEqual(summary["status"], "scheduled")
        self.assertEqual(self.products[0].__class__.objects.get(pk=self.products[0].pk).final_price, Decimal("1000000"))
        during = self.now + timedelta(hours=2)
        self.assertEqual(promotion_service.collection_promotion_summary(self.coll, during)["status"], "active")
        self.assertEqual(promotion_service.collection_promotion_summary(self.coll, during)["deadline"], self.now + timedelta(hours=5))
        after = self.now + timedelta(hours=5)
        self.assertEqual(promotion_service.collection_promotion_summary(self.coll, after)["status"], "ended")

    def test_boundary_is_half_open_start_inclusive_end_exclusive(self):
        self.schedule()
        p = Product.objects.get(pk=self.products[0].pk)
        end = self.now + timedelta(hours=5)
        self.assertTrue(p.is_discount_active(self.now))
        self.assertTrue(p.is_discount_active(end - timedelta(microseconds=1)))
        self.assertFalse(p.is_discount_active(end))
        self.assertEqual(p.final_price, Decimal("800000"))

    def test_idempotent_and_duplicate_submit_is_safe(self):
        first = self.schedule()
        second = self.schedule()
        self.assertEqual(first["updated"], second["updated"])
        self.assertEqual(set(Product.objects.filter(pk__in=[p.pk for p in self.products]).values_list("discount_percent", flat=True)), {20})

    def test_only_this_collection_of_this_store_is_touched(self):
        outsider = _product(self.store, 99)
        foreign = _product(self.other, 1)
        self.schedule()
        for p in (outsider, foreign):
            p.refresh_from_db()
            self.assertEqual((p.discount_percent, p.discount_ends_at), (0, None))

    def test_price_inquiry_products_are_skipped(self):
        inq = _product(self.store, 50)
        collection_service.add_product(self.coll, inq)
        Product.objects.filter(pk=inq.pk).update(is_price_inquiry=True)  # effective flag is denormalised
        result = self.schedule()
        inq.refresh_from_db()
        self.assertEqual(inq.discount_percent, 0)
        self.assertEqual(result["updated"], 3)

    def test_validation(self):
        bad = [
            dict(discount_percent=0), dict(discount_percent=101), dict(discount_percent="x"),
            dict(ends_at=None), dict(ends_at=self.now - timedelta(hours=1)),
            dict(starts_at=self.now + timedelta(hours=6), ends_at=self.now + timedelta(hours=5)),
            dict(ends_at=self.now + timedelta(days=91)),
            dict(ends_at=(self.now + timedelta(hours=5)).replace(tzinfo=None)),
        ]
        for kw in bad:
            with self.assertRaises(promotion_service.PromotionError, msg=str(kw)):
                self.schedule(**kw)
        self.assertEqual(Product.objects.filter(discount_percent__gt=0).count(), 0)

    def test_existing_discounts_are_reported_before_overwrite(self):
        Product.objects.filter(pk=self.products[0].pk).update(discount_percent=5)
        preview = promotion_service.preview_collection_promotion(
            self.coll, discount_percent=20, starts_at=self.now, ends_at=self.now + timedelta(hours=5), now=self.now,
        )
        self.assertEqual(preview["overwritten"], 1)
        self.assertEqual(Product.objects.get(pk=self.products[0].pk).discount_percent, 5)  # preview wrote nothing

    def test_end_now_restores_full_price_everywhere_via_the_single_source(self):
        self.schedule()
        later = self.now + timedelta(hours=1)
        promotion_service.end_collection_promotion(self.coll, now=later)
        p = Product.objects.get(pk=self.products[0].pk)
        self.assertFalse(p.is_discount_active(later))
        self.assertEqual(p.discount_percent, 20)  # not erased; can be restarted deliberately
        self.assertEqual(promotion_service.collection_promotion_summary(self.coll, later)["status"], "ended")

    def test_deadline_is_stored_not_regenerated(self):
        self.schedule()
        a = promotion_service.collection_promotion_summary(self.coll, self.now + timedelta(minutes=1))["deadline"]
        b = promotion_service.collection_promotion_summary(self.coll, self.now + timedelta(hours=2))["deadline"]
        self.assertEqual(a, b)

    def test_expired_discount_is_off_in_listing_query(self):
        self.schedule()
        in_window = Product.objects.filter(promotion_service.active_discount_q(self.now + timedelta(hours=1)), store=self.store).count()
        after = Product.objects.filter(promotion_service.active_discount_q(self.now + timedelta(hours=5)), store=self.store).count()
        self.assertEqual((in_window, after), (3, 0))


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class CampaignSingleClockTests(TestCase):
    """Listing card, PDP/cart/checkout live price and the API all read the same stored window: they flip together."""

    def test_every_price_path_turns_off_at_the_stored_end(self):
        from unittest import mock

        from apps.catalog.services.pricing_service import resolve_effective_price
        from apps.catalog.services.product_card_service import build_product_card_data

        store = Store.objects.get(slug="akhlaghi")
        coll = MerchantCollection.objects.create(store=store, name="ساعت", slug="camp-clock")
        product = _product(store, 300)
        collection_service.add_product(coll, product)
        now = timezone.now()
        promotion_service.schedule_collection_promotion(
            coll, discount_percent=25, starts_at=now, ends_at=now + timedelta(hours=1), now=now,
        )
        product = Product.objects.get(pk=product.pk)
        with mock.patch("django.utils.timezone.now", return_value=now + timedelta(minutes=59)):
            self.assertTrue(build_product_card_data(product).is_on_sale)
            self.assertEqual(resolve_effective_price(product), Decimal("750000"))
            self.assertEqual(product.final_price, Decimal("750000"))
        with mock.patch("django.utils.timezone.now", return_value=now + timedelta(hours=1)):
            self.assertFalse(build_product_card_data(product).is_on_sale)
            self.assertEqual(resolve_effective_price(product), Decimal("1000000"))
            self.assertEqual(product.final_price, Decimal("1000000"))


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class CampaignViewTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.owner = User.objects.create_user(username="09123700001", password="pass12345")
        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="09123700001", password="pass12345")
        self.coll = MerchantCollection.objects.create(store=self.store, name="منتخب", slug="camp-v")
        self.products = [_product(self.store, 200 + i) for i in range(2)]
        for p in self.products:
            collection_service.add_product(self.coll, p)
        self.url = reverse("dashboard:collection-campaign", args=[self.coll.pk])

    def fields(self, **kw):
        end = timezone.localtime(timezone.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        data = {"percent": "15", "start_mode": "now", "starts_at": "", "ends_at": end, "hours": ""}
        data.update(kw)
        return data

    def confirm(self, **kw):
        """Preview first (as the browser does) and then confirm with the token the preview issued."""
        import re

        fields = self.fields(**kw)
        preview = self.client.post(self.url, {**fields, "action": "preview"})
        match = re.search(r'name="confirm_token" value="([^"]+)"', preview.content.decode())
        token = match.group(1) if match else ""
        return self.client.post(self.url, {**fields, "action": "confirm", "acknowledge": "1", "confirm_token": token})

    def end(self, mode, acknowledge="1", token=True):
        import re

        preview = self.client.post(self.url, {"action": "end_preview", "mode": mode})
        match = re.search(r'name="confirm_token" value="([^"]+)"', preview.content.decode())
        data = {"action": "end_confirm", "mode": mode, "acknowledge": acknowledge, "confirm_token": match.group(1) if (match and token) else ""}
        return self.client.post(self.url, data)

    def test_get_shows_status_and_writes_nothing(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "کمپینی ثبت نشده")
        self.assertEqual(Product.objects.filter(discount_percent__gt=0).count(), 0)

    def test_preview_does_not_write(self):
        resp = self.client.post(self.url, {**self.fields(), "action": "preview"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "پیش‌نمایش (هنوز چیزی نوشته نشده)")
        self.assertEqual(Product.objects.filter(discount_percent__gt=0).count(), 0)

    def test_confirm_requires_acknowledgement_then_writes(self):
        resp = self.client.post(self.url, {**self.fields(), "action": "confirm"})
        self.assertContains(resp, "ابتدا پیش‌نمایش را ببینید")
        self.assertEqual(Product.objects.filter(discount_percent__gt=0).count(), 0)
        resp = self.client.post(self.url, {**self.fields(), "action": "confirm", "acknowledge": "1"})   # no token ⇒ still nothing
        self.assertEqual(Product.objects.filter(discount_percent__gt=0).count(), 0)
        resp = self.confirm()
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Product.objects.filter(store=self.store, discount_percent=15, discount_ends_at__isnull=False).count(), 2)

    def test_hours_shortcut_and_end_button(self):
        resp = self.confirm(ends_at="", hours="6")
        self.assertEqual(resp.status_code, 302)
        p = Product.objects.get(pk=self.products[0].pk)
        self.assertAlmostEqual((p.discount_ends_at - p.discount_starts_at).total_seconds(), 6 * 3600, delta=2)
        self.end("end")
        p.refresh_from_db()
        self.assertFalse(p.is_discount_active())

    def test_invalid_input_shows_a_persian_error_and_keeps_values(self):
        resp = self.client.post(self.url, {**self.fields(percent="500"), "action": "preview"})
        self.assertContains(resp, "درصد تخفیف باید بین")
        self.assertContains(resp, 'value="500"')

    def test_timezone_local_input_is_interpreted_in_store_timezone(self):
        resp = self.confirm(start_mode="at", starts_at="2030-01-10T10:00", ends_at="2030-01-11T10:00")
        self.assertEqual(resp.status_code, 302)
        p = Product.objects.get(pk=self.products[0].pk)
        self.assertEqual(timezone.localtime(p.discount_starts_at).strftime("%Y-%m-%d %H:%M"), "2030-01-10 10:00")

    def test_other_store_collection_is_404_and_anonymous_is_redirected(self):
        other = Store.objects.create(name="دیگر", slug="camp-v-other")
        foreign = MerchantCollection.objects.create(store=other, name="بیگانه", slug="camp-alien")
        self.assertEqual(self.client.get(reverse("dashboard:collection-campaign", args=[foreign.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("dashboard:collection-campaign", args=[foreign.pk]), {**self.fields(), "action": "confirm", "acknowledge": "1", "confirm_token": "x"}).status_code, 404)
        self.client.logout()
        self.assertNotEqual(self.client.get(self.url).status_code, 200)


class CampaignClarityTests(CampaignViewTests):
    """FOLLOWUP-06 — a campaign is a discount WITH an end date; the product's own standing (open-ended) discounts are separate and are never ended by the campaign tools."""

    def setUp(self):
        super().setUp()
        self.standing = Product.objects.filter(pk=self.products[0].pk)
        self.standing.update(discount_percent=30)                       # a permanent product discount (no end date)

    def test_standing_discounts_are_reported_separately_and_end_now_never_touches_them(self):
        resp = self.client.get(self.url)
        self.assertContains(resp, "تخفیفِ ثابتِ خودِ کالاها (مستقل از کمپین)")
        self.assertContains(resp, "کمپینی ثبت نشده")
        self.assertNotContains(resp, "پیش‌نمایشِ پایانِ کمپین")        # nothing timed ⇒ no end button at all
        r = self.end("end")
        p = Product.objects.get(pk=self.products[0].pk)
        self.assertEqual((p.discount_percent, p.discount_ends_at), (30, None))

    def test_end_preview_lists_skus_and_prices_and_writes_nothing(self):
        self.confirm()                                                  # campaign on both products (replaces the standing one, snapshotted)
        before = list(Product.objects.order_by("pk").values_list("pk", "discount_percent", "discount_ends_at"))
        resp = self.client.post(self.url, {"action": "end_preview", "mode": "end"})
        self.assertContains(resp, "پیش‌نمایشِ پایانِ کمپین (هنوز چیزی تغییر نکرده)")
        self.assertContains(resp, self.products[0].sku)
        self.assertEqual(list(Product.objects.order_by("pk").values_list("pk", "discount_percent", "discount_ends_at")), before)

    def test_end_needs_the_previewed_token_and_acknowledgement(self):
        self.confirm()
        self.end("end", acknowledge="")                                  # no checkbox
        self.end("end", token=False)                                     # no token
        self.assertTrue(all(p.is_discount_active() for p in Product.objects.filter(store=self.store, discount_percent__gt=0)))
        self.end("end")
        self.assertFalse(any(p.is_discount_active() for p in Product.objects.filter(store=self.store, discount_percent__gt=0)))

    def test_restore_brings_back_the_standing_discount_and_leaves_edited_products_alone(self):
        self.confirm()
        edited = Product.objects.get(pk=self.products[1].pk)
        Product.objects.filter(pk=edited.pk).update(discount_percent=7)  # the merchant changed it after the campaign
        self.end("restore")
        first = Product.objects.get(pk=self.products[0].pk)
        self.assertEqual((first.discount_percent, first.discount_ends_at), (30, None))   # back to its own standing discount
        self.assertEqual(Product.objects.get(pk=edited.pk).discount_percent, 7)           # untouched

    def test_schedule_preview_flags_the_standing_discount_it_would_replace(self):
        resp = self.client.post(self.url, {**self.fields(), "action": "preview"})
        self.assertContains(resp, "جایگزینِ تخفیفِ فعلی")
        self.assertContains(resp, "از «بازگرداندنِ تخفیفِ قبل از کمپین» قابل برگشت است")


# CampaignClarityTests reuses CampaignViewTests' fixtures/helpers only — not its inherited test methods.
for _name in [n for n in dir(CampaignViewTests) if n.startswith("test_") and n not in CampaignClarityTests.__dict__]:
    setattr(CampaignClarityTests, _name, None)
