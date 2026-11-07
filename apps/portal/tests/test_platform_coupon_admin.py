"""Platform-owner administration of platform (SaaS) coupons: CRUD, duplicate, enable/disable/archive, stats, history,
authorization (anonymous / non-superuser staff / merchant) and CSRF on every write."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.utils import timezone

from apps.billing.models import PlatformCoupon, PlatformCouponAuditEvent, PlatformCouponRedemption, SubscriptionInvoice
from apps.billing.services import invoice_service, platform_coupon_service as svc
from apps.stores.models import Store, StoreMembership
from apps.subscriptions.models import Plan, PlanVersion
from apps.subscriptions.services import subscription_service as sub_svc

User = get_user_model()
ADMIN = "platformadmins.rastisi.localhost"
LIST = "/coupons/"


class CouponAdminBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cache.clear()
        cls.owner = User.objects.create_user("cp-owner@example.com", password="a-very-strong-pass-1", is_staff=True, is_superuser=True)
        cls.staff = User.objects.create_user("cp-staff@example.com", password="a-very-strong-pass-1", is_staff=True)
        cls.merchant = User.objects.create_user("cp-merchant@example.com", password="a-very-strong-pass-1", is_staff=True)
        cls.store = Store.objects.create(name="فروشگاه کوپن", slug="cp-store", admin_subdomain="cpstore", status=Store.Status.ACTIVE)
        StoreMembership.objects.create(store=cls.store, user=cls.merchant, role=StoreMembership.Role.OWNER,
                                       status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
        cls.plan = Plan.objects.create(code="cp-plan", name="پلن کوپن")
        cls.version = PlanVersion.objects.create(
            plan=cls.plan, version_number=1, status=PlanVersion.Status.PUBLISHED, display_price=Decimal("400000"),
            currency="IRT", billing_interval=PlanVersion.BillingInterval.MONTHLY)

    def owner_client(self, **kw):
        c = Client(HTTP_HOST=ADMIN, **kw)
        c.force_login(self.owner)
        return c

    def payload(self, **over):
        data = {"name": "پاییزه", "code": "fall20", "kind": "percent", "percent": "20", "allow_initial": "on",
                "plans": [self.plan.pk], "intervals": ["monthly"], "store_slugs": "", "max_redemptions": "10"}
        data.update(over)
        return data

    def make(self, **kw):
        kw.setdefault("name", "c")
        kw.setdefault("kind", "percent")
        kw.setdefault("percent", 10)
        kw.setdefault("code", "BASE10")
        return svc.create_coupon(actor=self.owner, **kw)


class OwnerCrudTests(CouponAdminBase):
    def test_list_create_edit_detail_flow_and_rtl(self):
        c = self.owner_client()
        response = c.post("/coupons/add/", self.payload(starts_at="2030-01-01T08:30", ends_at="2030-02-01T20:00"))
        coupon = PlatformCoupon.objects.get(code="FALL20")
        self.assertRedirects(response, f"/coupons/{coupon.pk}/", fetch_redirect_response=False)
        self.assertEqual(coupon.percent, 20)
        self.assertEqual(list(coupon.plans.all()), [self.plan])
        self.assertEqual(coupon.intervals, ["monthly"])
        self.assertEqual(coupon.max_redemptions, 10)
        self.assertEqual(coupon.created_by, self.owner)
        # Tehran wall time is stored as an aware instant (UTC+3:30 / +3:30 no DST), not as naive/UTC-shifted text
        local = timezone.localtime(coupon.starts_at)
        self.assertEqual((local.year, local.month, local.day, local.hour, local.minute), (2030, 1, 1, 8, 30))
        self.assertTrue(timezone.is_aware(coupon.ends_at))
        listing = c.get(LIST).content.decode()
        self.assertIn("FALL20", listing)
        self.assertIn('dir="rtl"', listing)
        self.assertIn('lang="fa"', listing)
        detail = c.get(f"/coupons/{coupon.pk}/")
        self.assertContains(detail, "قابلِ ترکیب نیست")
        self.assertContains(detail, "تاریخچهٔ تغییرات")
        edit_page = c.get(f"/coupons/{coupon.pk}/edit/").content.decode()
        self.assertIn("2030-01-01T08:30", edit_page)           # round-trips in local time for the Persian picker
        self.assertIn("قابلِ ترکیب نیست", edit_page)
        self.assertNotIn('name="stackable"', edit_page)          # no false combinability option
        r = c.post(f"/coupons/{coupon.pk}/edit/", self.payload(percent="35", name="پاییزه ۲"))
        self.assertEqual(r.status_code, 302)
        coupon.refresh_from_db()
        self.assertEqual((coupon.percent, coupon.name), (35, "پاییزه ۲"))
        self.assertTrue(PlatformCouponAuditEvent.objects.filter(coupon=coupon, action="updated", actor=self.owner).exists())

    def test_persian_digits_and_separators_are_accepted(self):
        c = self.owner_client()
        c.post("/coupons/add/", self.payload(code="fa1", kind="fixed", percent="", fixed_amount="۱۲۰٬۰۰۰", max_redemptions="۵"))
        coupon = PlatformCoupon.objects.get(code="FA1")
        self.assertEqual(coupon.fixed_amount, Decimal("120000"))
        self.assertEqual(coupon.max_redemptions, 5)

    def test_validation_errors_do_not_create(self):
        c = self.owner_client()
        for bad in (self.payload(percent="150"), self.payload(name=""), self.payload(code=""),
                    self.payload(starts_at="2030-02-01T00:00", ends_at="2030-01-01T00:00"),
                    self.payload(allow_initial="", store_slugs="no-such-store")):
            if bad.get("allow_initial") == "":
                bad.pop("allow_initial")
            r = c.post("/coupons/add/", bad)
            self.assertEqual(r.status_code, 200, bad)
        self.assertEqual(PlatformCoupon.objects.count(), 0)

    def test_duplicate_code_rejected(self):
        self.make(code="DUP1")
        r = self.owner_client().post("/coupons/add/", self.payload(code="dup1"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(PlatformCoupon.objects.filter(code="DUP1").count(), 1)

    def test_private_store_assignment_and_per_store_limit(self):
        c = self.owner_client()
        c.post("/coupons/add/", self.payload(code="priv", store_slugs="cp-store", max_per_store="1", is_automatic=""))
        coupon = PlatformCoupon.objects.get(code="PRIV")
        self.assertEqual(list(coupon.stores.all()), [self.store])
        self.assertEqual(coupon.max_per_store, 1)

    def test_duplicate_enable_disable_archive(self):
        c = self.owner_client()
        src = self.make(code="SRC10", plans=[self.plan], intervals=["monthly"], min_amount=Decimal("1000"))
        r = c.post(f"/coupons/{src.pk}/duplicate/")
        copy = PlatformCoupon.objects.exclude(pk=src.pk).get()
        self.assertRedirects(r, f"/coupons/{copy.pk}/edit/", fetch_redirect_response=False)
        self.assertEqual(copy.code, "SRC10-COPY")
        self.assertEqual(copy.status, "disabled")
        self.assertEqual((copy.percent, copy.min_amount, copy.intervals), (10, Decimal("1000"), ["monthly"]))
        self.assertEqual(list(copy.plans.all()), [self.plan])
        c.post(f"/coupons/{src.pk}/duplicate/")                    # second copy gets a unique code
        self.assertEqual(PlatformCoupon.objects.filter(code__startswith="SRC10-COPY").count(), 2)

        c.post(f"/coupons/{src.pk}/disable/")
        src.refresh_from_db()
        self.assertEqual(src.status, "disabled")
        c.post(f"/coupons/{src.pk}/enable/")
        src.refresh_from_db()
        self.assertEqual(src.status, "active")
        c.post(f"/coupons/{src.pk}/archive/")
        src.refresh_from_db()
        self.assertEqual(src.status, "archived")
        self.assertNotIn("SRC10<", c.get(LIST).content.decode().replace("SRC10-COPY", ""))   # archived hidden by default
        self.assertIn("SRC10", c.get(LIST, {"state": "archived"}).content.decode())
        # archived coupon cannot be edited, but can be restored; history is kept
        self.assertEqual(c.get(f"/coupons/{src.pk}/edit/").status_code, 302)
        c.post(f"/coupons/{src.pk}/enable/")
        src.refresh_from_db()
        self.assertEqual(src.status, "active")
        actions = set(src.audit_events.values_list("action", flat=True))
        self.assertTrue({"created", "disabled", "enabled", "archived"} <= actions)
        self.assertEqual(c.post(f"/coupons/{src.pk}/explode/").status_code, 302)   # unknown action: no state change
        src.refresh_from_db()
        self.assertEqual(src.status, "active")

    def test_archive_keeps_redeemed_invoice_and_snapshot(self):
        coupon = self.make(code="KEEP10")
        sub = sub_svc.create_subscription(self.store, self.version)
        inv = invoice_service.open_invoice(invoice_service.create_invoice(
            sub, kind="initial", lines=[invoice_service.plan_line_spec(self.version)]))
        svc.apply_coupon_to_invoice(inv, code="KEEP10", actor=self.owner)
        self.owner_client().post(f"/coupons/{coupon.pk}/archive/")
        inv.refresh_from_db()
        self.assertEqual(inv.discount_total, Decimal("40000"))
        self.assertTrue(PlatformCouponRedemption.objects.filter(invoice=inv).exists())

    def test_stats_remaining_total_discount_revenue_and_affected_invoices(self):
        coupon = self.make(code="STAT10", max_redemptions=5)
        sub = sub_svc.create_subscription(self.store, self.version)
        inv = invoice_service.open_invoice(invoice_service.create_invoice(
            sub, kind="initial", lines=[invoice_service.plan_line_spec(self.version)]))
        svc.apply_coupon_to_invoice(inv, code="STAT10", actor=self.owner)
        stats = self.owner_client().get(f"/coupons/{coupon.pk}/").context["stats"]
        self.assertEqual((stats["reserved"], stats["redeemed"], stats["remaining"], stats["affected_invoices"]), (1, 0, 4, 1))
        PlatformCouponRedemption.objects.filter(invoice=inv).update(status="redeemed")
        stats = self.owner_client().get(f"/coupons/{coupon.pk}/").context["stats"]
        self.assertEqual((stats["redeemed"], stats["total_discount"], stats["revenue"], stats["remaining"]),
                         (1, Decimal("40000"), Decimal("360000"), 4))
        page = self.owner_client().get(f"/coupons/{coupon.pk}/").content.decode()
        self.assertIn(inv.number, page)


class OwnerAuthorizationTests(CouponAdminBase):
    def setUp(self):
        self.coupon = self.make(code="AUTH10")

    def urls(self):
        pk = self.coupon.pk
        return {"get": [LIST, "/coupons/add/", f"/coupons/{pk}/", f"/coupons/{pk}/edit/"],
                "post": ["/coupons/add/", f"/coupons/{pk}/edit/", f"/coupons/{pk}/duplicate/", f"/coupons/{pk}/disable/",
                         f"/coupons/{pk}/enable/", f"/coupons/{pk}/archive/"]}

    def assert_denied(self, client):
        before = (PlatformCoupon.objects.count(), PlatformCoupon.objects.get(pk=self.coupon.pk).status)
        for url in self.urls()["get"]:
            r = client.get(url)
            self.assertIn(r.status_code, (302, 403, 404), url)
            self.assertNotIn("AUTH10", r.content.decode(), url)
            if r.status_code == 302:
                self.assertIn("login", r["Location"], url)
        for url in self.urls()["post"]:
            r = client.post(url, self.payload(code="hack"))
            self.assertIn(r.status_code, (302, 403, 404), url)
        self.assertEqual((PlatformCoupon.objects.count(), PlatformCoupon.objects.get(pk=self.coupon.pk).status), before)

    def test_anonymous_forbidden(self):
        self.assert_denied(Client(HTTP_HOST=ADMIN))

    def test_non_superuser_staff_forbidden(self):
        c = Client(HTTP_HOST=ADMIN)
        c.force_login(self.staff)
        self.assert_denied(c)

    def test_merchant_user_forbidden(self):
        c = Client(HTTP_HOST=ADMIN)
        c.force_login(self.merchant)
        self.assert_denied(c)

    def test_coupon_admin_not_reachable_from_merchant_admin_portal(self):
        c = Client(HTTP_HOST=f"cpstore.rastisi.localhost")
        c.force_login(self.owner)
        for url in ("/coupons/", "/admin-portal/platform-coupons/", "/admin-portal/coupons/platform/"):
            self.assertNotIn("AUTH10", c.get(url).content.decode())

    def test_csrf_enforced_on_every_write(self):
        c = Client(HTTP_HOST=ADMIN, enforce_csrf_checks=True)
        c.force_login(self.owner)
        before = PlatformCoupon.objects.get(pk=self.coupon.pk)
        for url in self.urls()["post"]:
            self.assertEqual(c.post(url, self.payload(code="csrf")).status_code, 403, url)
        self.assertEqual(PlatformCoupon.objects.count(), 1)
        self.assertEqual(PlatformCoupon.objects.get(pk=self.coupon.pk).status, before.status)

    def test_writes_reject_get(self):
        c = self.owner_client()
        pk = self.coupon.pk
        for url in (f"/coupons/{pk}/duplicate/", f"/coupons/{pk}/disable/", f"/coupons/{pk}/archive/"):
            self.assertEqual(c.get(url).status_code, 405, url)
        self.assertEqual(PlatformCoupon.objects.get(pk=pk).status, "active")

    def test_nav_entry_is_present(self):
        self.assertIn("کوپن و کمپین", self.owner_client().get(LIST).content.decode())
