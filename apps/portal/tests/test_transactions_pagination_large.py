"""Transactions page at scale (FV4): 640 mixed synthetic transactions, identical timestamps, page boundaries, filters, stable order, authorisation.

Fixture (deterministic, synthetic, no gateway contact): 3 stores; 330 subscription + 310 SMS attempts = 640 rows. Timestamps come in groups of 7 rows that
share ONE ``created_at`` (the groups mix both kinds and several stores) so ties straddle the 25-row page boundaries. Statuses/providers cycle so every
filter selects a few hundred rows.

Invariants proven through the real HTTP view (staff session on the Platform Admin host):
* every row appears on exactly one page (no missing, no duplicates) — with no filter and with each filter;
* the concatenation of all pages equals the documented total order ``(created_at desc, subscription before SMS, pk desc)``;
* repeating the whole walk yields the identical sequence (stable); a row inserted with an OLDER timestamp does not reorder the newer ones;
* a page costs a bounded number of queries (it does not load the whole history);
* anonymous and non-staff users never get a transactions page (page 1 or the last page) and never see a store name.

Limits: it proves the ordering/pagination contract on this data shape and on PostgreSQL/SQLite alike; it does not prove behaviour under concurrent inserts
between two page requests (offset pagination can shift then — by design for an admin read-only list).
"""

import math
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.billing.models import SubscriptionPaymentAttempt
from apps.billing.tests.platform_payment_support import open_invoice_for
from apps.sms.models import SmsPackage, SmsPackagePaymentAttempt
from apps.sms.services import balance_service
from apps.stores.models import Store

User = get_user_model()
ADMIN = "platformadmins.rastisi.localhost"
URL = "/payments/transactions/"
N_SUB, N_SMS, PER_PAGE, GROUP = 330, 310, 25, 7
STATUSES = ["pending", "succeeded", "failed", "requires_action", "cancelled", "expired"]
PROVIDERS = ["zibal", "pasargad", "saman"]


class LargeTransactionsPaginationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(username="big-staff@example.com", password="pass-12345-x", is_staff=True, is_superuser=True)
        cls.plain = User.objects.create_user(username="09125558888", password="pass-12345-x")
        cls.stores = [Store.objects.create(name=f"فروشگاه حجیم {c}", slug=f"big-{c}", admin_subdomain=f"big-{c}") for c in "abc"]
        package = SmsPackage.objects.create(name="بسته", credit_amount=100, price=50_000)
        invoices = {s.pk: open_invoice_for(s, code=f"big-inv-{s.pk}", price="100000")[1] for s in cls.stores}
        purchases = {s.pk: balance_service.request_purchase(store=s, package=package) for s in cls.stores}
        subs = [SubscriptionPaymentAttempt(
            store=cls.stores[i % 3], invoice=invoices[cls.stores[i % 3].pk], provider=PROVIDERS[i % 3], status=STATUSES[i % 6],
            amount=invoices[cls.stores[i % 3].pk].amount_due, currency="IRT", public_token=f"big-sub-{i:04d}", idempotency_key=f"big-sk-{i:04d}",
            provider_session_id=f"bs{i}") for i in range(N_SUB)]
        sms = [SmsPackagePaymentAttempt(
            store=cls.stores[i % 3], purchase=purchases[cls.stores[i % 3].pk], provider=PROVIDERS[(i + 1) % 3], status=STATUSES[(i + 2) % 6],
            amount=purchases[cls.stores[i % 3].pk].price, currency="IRT", public_token=f"big-sms-{i:04d}", idempotency_key=f"big-mk-{i:04d}",
            provider_session_id=f"bm{i}") for i in range(N_SMS)]
        SubscriptionPaymentAttempt.objects.bulk_create(subs)
        SmsPackagePaymentAttempt.objects.bulk_create(sms)
        # Timestamps: row slot k (0..639, interleaving the kinds) lands in group k // 7, and every row of a group shares ONE instant.
        base = timezone.now().replace(microsecond=0) - timedelta(days=30)
        subs = list(SubscriptionPaymentAttempt.objects.order_by("pk"))
        smss = list(SmsPackagePaymentAttempt.objects.order_by("pk"))
        slot = 0
        for i in range(max(N_SUB, N_SMS)):
            for batch in (subs, smss):
                if i < len(batch):
                    batch[i].created_at = base + timedelta(minutes=slot // GROUP)
                    slot += 1
        SubscriptionPaymentAttempt.objects.bulk_update(subs, ["created_at"])
        SmsPackagePaymentAttempt.objects.bulk_update(smss, ["created_at"])
        cls.base = base

    # -- helpers ----------------------------------------------------------------------------------------------------------------------------------
    def get(self, page=None, **params):
        self.client.force_login(self.staff)
        if page is not None:
            params["page"] = page
        return self.client.get(URL, params, HTTP_HOST=ADMIN)

    def walk(self, **params):
        """Every page of the filtered list, via HTTP: (list of (kind, pk)), plus the page count and per-page sizes."""
        first = self.get(**params)
        self.assertEqual(first.status_code, 200)
        paginator = first.context["page"].paginator
        seq, sizes = [], []
        for number in range(1, paginator.num_pages + 1):
            rows = self.get(page=number, **params).context["page"].object_list
            sizes.append(len(rows))
            seq.extend((r["kind"], r["attempt"].pk) for r in rows)
        return seq, sizes, paginator

    def expected(self, **flt):
        """The documented total order, computed independently of the view straight from the ORM."""
        rows = []
        kind = flt.get("kind", "")
        for attempt in SubscriptionPaymentAttempt.objects.select_related("store") if kind in ("", "subscription") else []:
            rows.append((attempt.created_at, 1, attempt.pk, "subscription", attempt))
        for attempt in SmsPackagePaymentAttempt.objects.select_related("store") if kind in ("", "sms") else []:
            rows.append((attempt.created_at, 0, attempt.pk, "sms", attempt))
        for key, expect in (("status", "status"), ("provider", "provider")):
            if flt.get(key):
                rows = [r for r in rows if getattr(r[4], expect) == flt[key]]
        if flt.get("q"):
            rows = [r for r in rows if flt["q"] in r[4].store.name]
        rows.sort(key=lambda r: (r[0], r[1], r[2]), reverse=True)
        return [(r[3], r[2]) for r in rows]

    # -- fixture sanity ---------------------------------------------------------------------------------------------------------------------------
    def test_fixture_is_what_the_docstring_says(self):
        self.assertEqual(SubscriptionPaymentAttempt.objects.count(), N_SUB)
        self.assertEqual(SmsPackagePaymentAttempt.objects.count(), N_SMS)
        self.assertGreater(N_SUB + N_SMS, 600)
        stamps = [a.created_at for a in SubscriptionPaymentAttempt.objects.all()] + [a.created_at for a in SmsPackagePaymentAttempt.objects.all()]
        by_instant = {}
        for t in stamps:
            by_instant[t] = by_instant.get(t, 0) + 1
        self.assertEqual(max(by_instant.values()), GROUP)                       # ties of 7 rows exist everywhere …
        self.assertGreater(len([c for c in by_instant.values() if c == GROUP]), 80)
        kinds_per_instant = {}
        for kind, a in [("s", a) for a in SubscriptionPaymentAttempt.objects.all()] + [("m", a) for a in SmsPackagePaymentAttempt.objects.all()]:
            kinds_per_instant.setdefault(a.created_at, set()).add(kind)
        self.assertGreater(sum(1 for v in kinds_per_instant.values() if v == {"s", "m"}), 50)   # ties mix BOTH kinds

    # -- completeness + order ---------------------------------------------------------------------------------------------------------------------
    def test_unfiltered_walk_has_no_missing_or_duplicate_rows_and_follows_the_total_order(self):
        seq, sizes, paginator = self.walk()
        total = N_SUB + N_SMS
        self.assertEqual(paginator.count, total)
        self.assertEqual(paginator.num_pages, math.ceil(total / PER_PAGE))
        self.assertEqual(sizes, [PER_PAGE] * (total // PER_PAGE) + [total % PER_PAGE])           # 25 × 25 + 15
        self.assertEqual(len(seq), total)
        self.assertEqual(len(set(seq)), total, "a transaction appeared on two pages")
        self.assertEqual(set(seq), {("subscription", a.pk) for a in SubscriptionPaymentAttempt.objects.all()} | {("sms", a.pk) for a in SmsPackagePaymentAttempt.objects.all()})
        self.assertEqual(seq, self.expected())

    def test_a_tie_group_that_straddles_a_page_boundary_is_split_consistently(self):
        seq = self.expected()
        groups = {}
        for index, (kind, pk) in enumerate(seq):
            a = (SubscriptionPaymentAttempt if kind == "subscription" else SmsPackagePaymentAttempt).objects.get(pk=pk)
            groups.setdefault(a.created_at, []).append(index)
        straddling = [idx for idx in groups.values() if len(idx) > 1 and idx[0] // PER_PAGE != idx[-1] // PER_PAGE]
        self.assertGreaterEqual(len(straddling), 20)                                            # many tie groups cross a boundary
        walked, _sizes, _p = self.walk()
        self.assertEqual(walked, seq)                                                           # … and still no row is lost or repeated

    def test_walking_twice_gives_the_identical_sequence_and_an_older_insert_does_not_reorder_newer_rows(self):
        first, _s, _p = self.walk()
        second, _s, _p = self.walk()
        self.assertEqual(first, second)
        invoice = SubscriptionPaymentAttempt.objects.first().invoice
        old = SubscriptionPaymentAttempt.objects.create(
            store=self.stores[0], invoice=invoice, provider="zibal", status="pending", amount=invoice.amount_due, currency="IRT",
            public_token="big-old", idempotency_key="big-old-k", provider_session_id="bo")
        SubscriptionPaymentAttempt.objects.filter(pk=old.pk).update(created_at=self.base - timedelta(days=400))
        third, _s, _p = self.walk()
        self.assertEqual(third[:-1], first)                                                     # the new, OLDEST row is last; nothing above moved
        self.assertEqual(third[-1], ("subscription", old.pk))

    # -- filters ----------------------------------------------------------------------------------------------------------------------------------
    def test_each_filter_and_combination_walks_without_gaps_or_duplicates(self):
        cases = [
            {"kind": "subscription"}, {"kind": "sms"}, {"status": "failed"}, {"status": "succeeded"}, {"provider": "pasargad"},
            {"kind": "sms", "status": "pending", "provider": "saman"}, {"kind": "subscription", "provider": "zibal", "status": "requires_action"},
            {"q": "فروشگاه حجیم b"}, {"q": "فروشگاه حجیم c", "status": "expired"},
        ]
        for flt in cases:
            with self.subTest(**flt):
                seq, sizes, paginator = self.walk(**flt)
                want = self.expected(**flt)
                self.assertGreater(len(want), 0)
                self.assertEqual(paginator.count, len(want))
                self.assertEqual(len(set(seq)), len(seq), "duplicate row under filter")
                self.assertEqual(seq, want)
                self.assertTrue(all(s == PER_PAGE for s in sizes[:-1]))
        big = [f for f in cases if len(self.expected(**f)) > 2 * PER_PAGE]
        self.assertGreaterEqual(len(big), 4)                                                    # several filtered lists really span >2 pages

    def test_an_empty_filter_result_is_an_empty_page_not_an_error(self):
        response = self.get(q="هیچ فروشگاهی با این نام نیست")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["page"].object_list), 0)

    def test_out_of_range_and_garbage_page_numbers_fall_back_safely(self):
        last = self.get(page=9999).context["page"]
        self.assertEqual(last.number, math.ceil((N_SUB + N_SMS) / PER_PAGE))
        self.assertEqual(self.get(page="abc").context["page"].number, 1)
        self.assertIn(self.get(page=-3).context["page"].number, (1, last.paginator.num_pages))      # Paginator.get_page clamps a negative number

    # -- cost -------------------------------------------------------------------------------------------------------------------------------------
    def test_a_page_costs_a_bounded_number_of_queries(self):
        counts = {}
        self.get(page=1)                                           # warm one-time caches (content types, session) so the counts are per-page costs
        for number in (1, 13, 26):
            with CaptureQueriesContext(connection) as ctx:
                self.get(page=number)
            counts[number] = len(ctx)
        # constant per page: not proportional to the 640 rows (a per-row query would add ≥ 25 between a 25-row page and a 15-row page)
        self.assertLessEqual(max(counts.values()), 40, counts)
        self.assertEqual(counts[13], counts[26], counts)               # 25-row page vs 15-row page: identical cost ⇒ no per-row query
        with CaptureQueriesContext(connection) as deep:
            self.get(page=26)
        selects = [q["sql"] for q in deep if "paymentattempt" in q["sql"].lower().replace("_", "")]
        self.assertTrue(all("LIMIT" in sql.upper() or "COUNT" in sql.upper() for sql in selects), "an unbounded attempt query ran")

    # -- authorisation ----------------------------------------------------------------------------------------------------------------------------
    def test_anonymous_and_non_staff_never_see_any_page_or_store_name(self):
        for who in (None, self.plain):
            if who is not None:
                self.client.force_login(who)
            else:
                self.client.logout()
            for page in (1, 26, 9999):
                response = self.client.get(URL, {"page": page, "q": "حجیم"}, HTTP_HOST=ADMIN)
                self.assertNotEqual(response.status_code, 200, (who, page))
                self.assertNotContains(response, "فروشگاه حجیم", status_code=response.status_code)
