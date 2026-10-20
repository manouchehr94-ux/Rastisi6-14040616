"""FOLLOWUP-14 — every visible date is Jalali; every date picker is the central Jalali widget; storage stays Gregorian/UTC."""

import datetime as dt
import json
import re
import shutil
import subprocess
from pathlib import Path

import jdatetime
from django.conf import settings
from django.contrib.auth import get_user_model
from django.template import Context, Template
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import MerchantCollection, Product, Vendor
from apps.catalog.services import collection_service
from apps.stores.models import Store, StoreMembership

REPO = Path(__file__).resolve().parents[3]
JS = REPO / "apps/core/static/core/jalali_picker.js"
User = get_user_model()
HOST = "jalali14.rastisi.localhost"


def render(tpl, **ctx):
    return Template("{% load persian %}" + tpl).render(Context(ctx))


class FilterTests(SimpleTestCase):
    def test_date_and_datetime_render_persian_digits(self):
        self.assertEqual(render("{{ d|jalali }}", d=dt.date(2026, 10, 16)), "۱۴۰۵/۰۷/۲۴")
        self.assertEqual(render("{{ d|jalali_dt }}", d=dt.datetime(2026, 10, 16, 14, 5, tzinfo=dt.timezone.utc)), "۱۴۰۵/۰۷/۲۴ ۱۷:۳۵")

    def test_aware_instants_are_converted_to_the_store_timezone_before_taking_the_day(self):
        # 2026-03-20 20:45 UTC == 00:15 on 1405/01/01 in Tehran (UTC+03:30, no DST since 2022)
        instant = dt.datetime(2026, 3, 20, 20, 45, tzinfo=dt.timezone.utc)
        self.assertEqual(render("{{ d|jalali }}", d=instant), "۱۴۰۵/۰۱/۰۱")
        self.assertEqual(render("{{ d|jalali_dt }}", d=instant), "۱۴۰۵/۰۱/۰۱ ۰۰:۱۵")
        just_before = dt.datetime(2026, 3, 20, 20, 29, 59, tzinfo=dt.timezone.utc)
        self.assertEqual(render("{{ d|jalali_dt }}", d=just_before), "۱۴۰۴/۱۲/۲۹ ۲۳:۵۹")

    def test_leap_esfand_and_year_boundaries(self):
        self.assertEqual(render("{{ d|jalali }}", d=dt.date(2025, 3, 20)), "۱۴۰۳/۱۲/۳۰")   # 1403 is leap
        self.assertEqual(render("{{ d|jalali }}", d=dt.date(2026, 3, 20)), "۱۴۰۴/۱۲/۲۹")   # 1404 is not
        self.assertEqual(render("{{ d|jalali }}", d=dt.date(2026, 3, 21)), "۱۴۰۵/۰۱/۰۱")

    def test_empty_and_garbage_values_render_nothing(self):
        for value in (None, "", "not a date"):
            self.assertEqual(render("{{ d|jalali }}|{{ d|jalali_dt }}", d=value), "|")


class SweepGuardTests(SimpleTestCase):
    """No admin/portal template may show a Gregorian date through Django's ``|date`` filter any more."""

    ALLOWED = ("datetime=", "<input")      # machine-readable attributes and native-input values (the widget converts those)

    def test_no_human_visible_gregorian_date_filter_is_left(self):
        offenders = []
        for base in (REPO / "apps", REPO / "templates"):
            for path in base.rglob("*.html"):
                if "/tests/" in str(path):
                    continue
                for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                    if "|date:" in line and not any(token in line for token in self.ALLOWED):
                        offenders.append(f"{path.relative_to(REPO)}:{number}")
        self.assertEqual(offenders, [])

    def test_bases_load_the_central_widget(self):
        for rel in ("apps/dashboard/templates/dashboard/base_admin.html", "apps/portal/templates/portal/platform_admin/base.html"):
            text = (REPO / rel).read_text(encoding="utf-8")
            self.assertIn("core/jalali_picker.js", text, rel)
            self.assertIn("core/jalali_picker.css", text, rel)

    def test_native_date_inputs_remain_in_the_markup_as_the_no_js_fallback_and_iso_carrier(self):
        for rel in ("apps/dashboard/templates/dashboard/collection_campaign.html", "apps/dashboard/templates/dashboard/coupon_form.html"):
            self.assertRegex((REPO / rel).read_text(encoding="utf-8"), r'type="(date|datetime-local)"')


class WidgetConversionTests(SimpleTestCase):
    """The browser-side calendar math must equal ``jdatetime`` (checked by running the real file under Node)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.node = shutil.which("node")

    def test_js_conversion_matches_jdatetime_over_two_centuries(self):
        if not self.node:
            self.skipTest("node is not installed")
        rows, day, end = [], dt.date(1921, 3, 21), dt.date(2121, 3, 20)
        while day < end:
            j = jdatetime.date.fromgregorian(date=day)
            rows.append([day.year, day.month, day.day, j.year, j.month, j.day, (day.weekday() + 2) % 7])
            day += dt.timedelta(days=1)
        script = (
            "const J=require(process.argv[1]);const rows=JSON.parse(require('fs').readFileSync(0,'utf8'));let bad=0;"
            "for(const [gy,gm,gd,jy,jm,jd,wd] of rows){const j=J.toJalali(gy,gm,gd);const g=J.toGregorian(jy,jm,jd);"
            "if(j.jy!==jy||j.jm!==jm||j.jd!==jd||g.gy!==gy||g.gm!==gm||g.gd!==gd||J.weekdayOf(jy,jm,jd)!==wd)bad++;}"
            "console.log(JSON.stringify({bad,count:rows.length,esfand1403:J.monthLength(1403,12),esfand1404:J.monthLength(1404,12),"
            "p1:J.parseText('۱۴۰۳/۱۲/۳۰'),p2:J.parseText('۱۴۰۴/۱۲/۳۰'),p3:J.parseText('1405-07-24 23:59',true),p4:J.parseText('۱۴۰۵/۰۷/۲۴ ۲۴:۰۰',true),"
            "p5:J.parseText('2026-10-16'),p6:J.parseText('1405/13/01')}));"
        )
        proc = subprocess.run([self.node, "-e", script, str(JS)], input=json.dumps(rows), capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertEqual((out["bad"], out["count"]), (0, len(rows)))
        self.assertEqual((out["esfand1403"], out["esfand1404"]), (30, 29))
        self.assertEqual(out["p1"]["iso"], "2025-03-20")                      # leap Esfand 30 accepted (Persian digits)
        self.assertIsNone(out["p2"])                                          # 1404/12/30 does not exist
        self.assertEqual(out["p3"]["iso"], "2026-10-16T23:59")                # English digits + dash + 24h time
        self.assertIsNone(out["p4"])                                          # 24:00 rejected
        self.assertEqual(out["p5"]["iso"], "2026-10-16")                      # pasted Gregorian ISO is understood
        self.assertIsNone(out["p6"])                                          # month 13 rejected


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class CampaignRoundTripTests(TestCase):
    """The widget submits Gregorian ISO local time (exactly what the view already parses); the page shows the stored value in Jalali."""

    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        owner = User.objects.create_user(username="09127900001", password="pass12345")
        StoreMembership.objects.create(store=self.store, user=owner, role=StoreMembership.Role.OWNER,
                                       status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="09127900001", password="pass12345")
        vendor = Vendor.objects.create(store=self.store, name="v", slug="v-j14")
        product = Product.objects.create(store=self.store, vendor=vendor, name="p", slug="p-j14", sku="J14", price=1000,
                                         status=Product.Status.ACTIVE)
        self.coll = MerchantCollection.objects.create(store=self.store, name="c", slug="c-j14")
        collection_service.add_product(self.coll, product)
        self.url = reverse("dashboard:collection-campaign", args=[self.coll.pk])

    def test_iso_in_jalali_out_and_midnight_boundary_in_tehran(self):
        data = {"percent": "10", "start_mode": "at", "starts_at": "2030-03-20T23:59", "ends_at": "2030-03-21T00:00", "hours": ""}
        # 1409/01/01 is 2030-03-21 (Nowruz); end = exactly Tehran midnight, start one minute earlier.
        # FOLLOWUP-06: a campaign is applied only through preview -> signed confirm token, exactly like the browser does.
        preview = self.client.post(self.url, {**data, "action": "preview"})
        token = re.search(r'name="confirm_token" value="([^"]+)"', preview.content.decode()).group(1)
        self.client.post(self.url, {**data, "action": "confirm", "acknowledge": "1", "confirm_token": token})
        p = Product.objects.get(slug="p-j14")
        self.assertEqual(timezone.localtime(p.discount_starts_at).strftime("%Y-%m-%d %H:%M"), "2030-03-20 23:59")
        self.assertEqual(timezone.localtime(p.discount_ends_at).strftime("%Y-%m-%d %H:%M"), "2030-03-21 00:00")
        html = self.client.get(self.url).content.decode()
        self.assertIn("۱۴۰۹/۰۱/۰۱ ۰۰:۰۰", html)      # the stored deadline as the owner reads it
