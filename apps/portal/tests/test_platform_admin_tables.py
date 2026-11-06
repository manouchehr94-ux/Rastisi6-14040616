"""Platform Admin tables, filter bars and the transactions page.

* Table cells must stay real table cells (a ``<td class="pa-ltr">`` used to become ``inline-block`` → shorter cell, broken row separator).
* Filter bars are top-aligned so a field's help text can't push its control off the shared row.
* The transactions page lists the FULL history (no silent 300-row cut-off), and search / filters / pagination / permissions work on real rows.
"""

import re
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.test import SimpleTestCase, TestCase

from apps.billing.models import SubscriptionPaymentAttempt
from apps.billing.services import sms_purchase_payment_service as sms_svc
from apps.billing.tests.platform_payment_support import open_invoice_for
from apps.portal import platform_admin_views as views
from apps.sms.models import SmsPackage, SmsPackagePaymentAttempt
from apps.sms.services import balance_service
from apps.stores.models import Store

User = get_user_model()
ADMIN = "platformadmins.rastisi.localhost"
ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "static/portal/css/platform-admin-panel.css").read_text(encoding="utf-8")
TEMPLATES = ROOT / "templates/portal/platform_admin"


class TableCellLayoutGuardTests(SimpleTestCase):
    def test_a_utility_class_that_changes_display_is_overridden_for_table_cells(self):
        """Every class used on a <td>/<th> whose CSS sets a non-table-cell ``display`` must have a ``td.cls`` / ``th.cls`` override."""
        risky = set()
        css = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)                       # a comment before a rule would otherwise hide its selector
        for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
            if re.search(r"(?<![-\w])display\s*:\s*(?!table-cell)[\w-]+", body):
                for sel in selectors.split(","):
                    m = re.fullmatch(r"\s*\.([\w-]+)\s*", sel)          # a bare single-class selector applies to every element, <td> included
                    if m:
                        risky.add(m.group(1))
        overridden = set(re.findall(r"\b(?:td|th)\.([\w-]+)", CSS))
        offenders = {}
        for path in sorted(TEMPLATES.glob("*.html")):
            for tag in re.findall(r"<(?:td|th)\b[^>]*\bclass=\"([^\"]*)\"", path.read_text(encoding="utf-8")):
                for cls in tag.split():
                    if cls in risky and cls not in overridden:
                        offenders.setdefault(cls, set()).add(path.name)
        self.assertEqual(offenders, {}, "classes that pull a table cell out of its row (add a td.<class>{display:table-cell} override)")

    def test_pa_ltr_cells_keep_table_cell_display(self):
        self.assertRegex(CSS, r"td\.pa-ltr\s*,\s*th\.pa-ltr\s*\{[^}]*display\s*:\s*table-cell")

    def test_filter_bars_are_top_aligned_with_actions_on_their_own_row(self):
        rule = re.search(r"\.pa-filters\s*\{([^}]*)\}", CSS).group(1)
        self.assertIn("align-items:start", rule.replace(" ", ""))
        self.assertNotIn("align-items:end", rule.replace(" ", ""))
        self.assertRegex(CSS, r"\.pa-filters \.pa-filter-actions\s*\{[^}]*grid-column\s*:\s*1\s*/\s*-1")

    def test_the_stylesheet_cache_buster_was_bumped_so_browsers_drop_the_old_rule(self):
        base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
        link = re.search(r"platform-admin-panel\.css'\s*%\}\?v=([\w-]+)", base).group(1)
        self.assertNotEqual(link, "20261105-ux1")


class MergedAttemptRowsTests(TestCase):
    """The lazy merged sequence behind the transactions page: exact counts, newest-first, correct slices across both kinds."""

    def setUp(self):
        self.store = Store.objects.create(name="فروشگاه جدول", slug="tbl-store", admin_subdomain="tbl-store")
        self.package = SmsPackage.objects.create(name="بسته", credit_amount=100, price=50_000)
        _sub, self.invoice = open_invoice_for(self.store, code="tbl-inv", price="100000")
        self.n = 0

    def _sub_attempt(self, status="pending", provider="zibal"):
        self.n += 1
        return SubscriptionPaymentAttempt.objects.create(
            store=self.store, invoice=self.invoice, provider=provider, status=status, amount=self.invoice.amount_due, currency="IRT",
            public_token=f"tbl-sub-{self.n}", idempotency_key=f"tbl-sk-{self.n}", provider_session_id=f"s{self.n}")

    def _sms_attempt(self, status="pending", provider="zibal"):
        self.n += 1
        purchase = balance_service.request_purchase(store=self.store, package=self.package)
        return SmsPackagePaymentAttempt.objects.create(
            store=self.store, purchase=purchase, provider=provider, status=status, amount=purchase.price, currency="IRT",
            public_token=f"tbl-sms-{self.n}", idempotency_key=f"tbl-mk-{self.n}", provider_session_id=f"m{self.n}")

    def test_len_counts_both_kinds_and_slices_merge_newest_first_without_gaps_or_duplicates(self):
        made = []
        for i in range(7):
            made.append(self._sub_attempt() if i % 2 == 0 else self._sms_attempt())
        rows = views._attempt_rows()
        self.assertEqual(len(rows), 7)
        everything = rows[0:7]
        self.assertEqual([r["created_at"] for r in everything], sorted((a.created_at for a in made), reverse=True))
        pages = rows[0:3] + rows[3:6] + rows[6:9]
        self.assertEqual([(r["kind"], r["attempt"].pk) for r in pages], [(r["kind"], r["attempt"].pk) for r in everything])
        self.assertEqual(len({(r["kind"], r["attempt"].pk) for r in pages}), 7)

    def test_history_beyond_the_old_300_row_cap_is_reachable_through_pagination(self):
        SubscriptionPaymentAttempt.objects.bulk_create([
            SubscriptionPaymentAttempt(store=self.store, invoice=self.invoice, provider="zibal", status="pending", amount=self.invoice.amount_due,
                                       currency="IRT", public_token=f"bulk-{i}", idempotency_key=f"bulk-k-{i}", provider_session_id=f"b{i}")
            for i in range(310)
        ])
        rows = views._attempt_rows(kind="subscription")
        paginator = Paginator(rows, 25)
        self.assertEqual(paginator.count, 310)                                   # used to be capped at 300
        self.assertEqual(paginator.num_pages, 13)
        last = paginator.get_page(13)
        self.assertEqual(len(last.object_list), 10)
        self.assertEqual(len({r["attempt"].pk for p in range(1, 14) for r in paginator.get_page(p).object_list}), 310)


class TransactionsPageTests(TestCase):
    URL = "/payments/transactions/"

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(username="tbl-staff@example.com", password="pass-12345-x", is_staff=True, is_superuser=True)
        cls.plain = User.objects.create_user(username="09125557777", password="pass-12345-x")
        cls.store_a = Store.objects.create(name="فروشگاهِ الف", slug="tx-a", admin_subdomain="tx-a")
        cls.store_b = Store.objects.create(name="فروشگاهِ ب", slug="tx-b", admin_subdomain="tx-b")
        cls.package = SmsPackage.objects.create(name="بسته", credit_amount=100, price=50_000)

    def _make(self, store, status="pending", provider="zibal", sms=False, n=[0]):
        n[0] += 1
        if not hasattr(self, "_invoices"):
            self._invoices = {}
        if sms:
            purchase = balance_service.request_purchase(store=store, package=self.package)
            return SmsPackagePaymentAttempt.objects.create(
                store=store, purchase=purchase, provider=provider, status=status, amount=purchase.price, currency="IRT",
                public_token=f"tp-sms-{n[0]}", idempotency_key=f"tp-m-{n[0]}", provider_session_id=f"m{n[0]}")
        if store.pk not in self._invoices:                                       # one open invoice per store; many attempts may target it
            self._invoices[store.pk] = open_invoice_for(store, code=f"tp-inv-{store.pk}", price="100000")[1]
        invoice = self._invoices[store.pk]
        return SubscriptionPaymentAttempt.objects.create(
            store=store, invoice=invoice, provider=provider, status=status, amount=invoice.amount_due, currency="IRT",
            public_token=f"tp-sub-{n[0]}", idempotency_key=f"tp-s-{n[0]}", provider_session_id=f"s{n[0]}")

    def get(self, **params):
        self.client.force_login(self.staff)
        return self.client.get(self.URL, params, HTTP_HOST=ADMIN)

    def test_permissions_anonymous_and_non_staff_never_see_transactions(self):
        self._make(self.store_a)
        self.assertNotEqual(self.client.get(self.URL, HTTP_HOST=ADMIN).status_code, 200)
        self.client.force_login(self.plain)
        response = self.client.get(self.URL, HTTP_HOST=ADMIN)
        self.assertNotEqual(response.status_code, 200)
        self.assertNotContains(response, "فروشگاهِ الف", status_code=response.status_code)

    def test_empty_state_when_there_are_genuinely_no_transactions(self):
        response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "تراکنشی یافت نشد")
        self.assertEqual(len(response.context["page"].object_list), 0)

    def test_rows_of_both_kinds_are_listed_with_no_fake_data(self):
        self._make(self.store_a)
        self._make(self.store_b, sms=True)
        response = self.get()
        self.assertEqual({r["kind"] for r in response.context["page"].object_list}, {"subscription", "sms"})
        self.assertNotContains(response, "تراکنشی یافت نشد")

    def test_search_matches_store_name_and_a_miss_shows_the_empty_state(self):
        self._make(self.store_a)
        self._make(self.store_b)
        hit = self.get(q="الف")
        self.assertEqual([r["store"].pk for r in hit.context["page"].object_list], [self.store_a.pk])
        miss = self.get(q="هیچ‌چیز")
        self.assertContains(miss, "تراکنشی یافت نشد")

    def test_filters_by_kind_status_and_provider_and_clear_resets(self):
        self._make(self.store_a, status="succeeded", provider="zibal")
        self._make(self.store_a, status="failed", provider="pasargad")
        self._make(self.store_b, sms=True, status="pending", provider="zibal")
        by = lambda **p: sorted((r["kind"], r["attempt"].status, r["attempt"].provider) for r in self.get(**p).context["page"].object_list)
        self.assertEqual(by(kind="sms"), [("sms", "pending", "zibal")])
        self.assertEqual(by(status="failed"), [("subscription", "failed", "pasargad")])
        self.assertEqual(by(provider="zibal"), [("sms", "pending", "zibal"), ("subscription", "succeeded", "zibal")])
        self.assertEqual(by(kind="subscription", status="succeeded", provider="zibal"), [("subscription", "succeeded", "zibal")])
        self.assertEqual(len(by()), 3)                                            # "پاک‌کردن" = no params = everything
        self.assertEqual(by(kind="bogus"), by())                                  # an unknown kind falls back to all instead of erroring

    def test_the_filter_form_renders_every_control_and_the_clear_link(self):
        html = self.get().content.decode()
        for needle in ('id="flt-q"', 'id="flt-kind"', 'id="flt-status"', 'id="flt-provider"', "اعمالِ فیلتر", "پاک‌کردن", 'class="pa-cardbody pa-filters"'):
            self.assertIn(needle, html)

    def test_pagination_keeps_the_active_filters(self):
        for _ in range(27):
            self._make(self.store_a, status="failed")
        response = self.get(status="failed")
        self.assertEqual(response.context["page"].paginator.count, 27)
        html = response.content.decode()
        self.assertRegex(html, r'href="\?[^"]*status=failed[^"]*page=2|href="\?[^"]*page=2[^"]*status=failed')
