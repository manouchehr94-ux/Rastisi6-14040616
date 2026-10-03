#!/usr/bin/env python
"""Reproducible campaign-engine benchmark (synthetic, non-personal data only).

Usage (never against production; point DATABASE_URL at a disposable PostgreSQL database):

  # 1) create schema + synthetic data (>=100k customers) with THIS code version
  DATABASE_URL=postgres://u:p@host/bench python manage.py migrate
  DATABASE_URL=... python tools/bench/campaign_benchmark.py seed --customers 100000

  # 2) measure (each scenario runs in a fresh subprocess so peak RSS is clean)
  DATABASE_URL=... python tools/bench/campaign_benchmark.py run [--issue-sample 5000]

Metrics per scenario: wall time, SQL query count, SQL time, peak RSS, eligible count.
Nothing is committed to git; the generated dataset lives only in the target database."""

import argparse
import json
import os
import random
import resource
import subprocess
import sys
import time
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "shop_core.settings")
import django  # noqa: E402

django.setup()

from django.db import connection  # noqa: E402

SLUG = "bench"
M = 1_000_000


def trees(product_ids):
    return {
        "aggregate_order_count": {"type": "group", "op": "and", "children": [{"type": "order_count", "op": "gte", "value": 2}]},
        "aggregate_spend": {"type": "group", "op": "and", "children": [{"type": "order_total", "op": "gte", "value": 3 * M}]},
        "nested_and_or_not": {"type": "group", "op": "and", "children": [
            {"type": "group", "op": "or", "children": [
                {"type": "line_match", "product_ids": product_ids[:20]},
                {"type": "order_total", "op": "gt", "value": 8 * M},
            ]},
            {"type": "group", "op": "and", "negate": True, "children": [
                {"type": "order_history", "state": "canceled", "exists": True},
            ]},
        ]},
        "customer_only_all": {},
    }


def seed(customers: int):
    from django.contrib.auth import get_user_model
    from django.utils import timezone

    from apps.catalog.models import Category, Product, Vendor
    from apps.customers.models import Customer
    from apps.orders.models import Order, OrderItem, PaymentGateway, ShippingMethod, Transaction
    from apps.stores.models import Store

    random.seed(42)
    if Store.objects.filter(slug=SLUG).exists():
        sys.exit("store 'bench' already exists — use a fresh database")
    store = Store.objects.create(name="bench", slug=SLUG, status=Store.Status.ACTIVE)
    vendor = Vendor.objects.create(store=store, name="v", slug="v")
    cat = Category.objects.create(store=store, name="c", slug="c")
    products = Product.objects.bulk_create([
        Product(store=store, vendor=vendor, category=cat, name=f"p{i}", slug=f"p{i}", sku=f"S{i}",
                price=Decimal(100000 + 50000 * (i % 20)), stock=10**6) for i in range(200)])
    ship = ShippingMethod.objects.create(store=store, name="post", slug="post", cost=Decimal(45000))
    gw = PaymentGateway.objects.create(store=store, name="zibal", slug="zibal")
    User = get_user_model()
    users = User.objects.bulk_create([User(username=f"0913{n:07d}", password="!") for n in range(customers)], batch_size=5000)
    cs = Customer.objects.bulk_create([
        Customer(user=u, full_name=f"c{n}", phone=f"0913{n:07d}", accepts_promotional_sms=(n % 4 == 0),
                 accepts_promotional_email=(n % 5 == 0)) for n, u in enumerate(users)], batch_size=5000)
    statuses = [("delivered", "paid"), ("processing", "paid"), ("pending", "pending"), ("canceled", "pending"), ("shipped", "paid")]
    orders = []
    for i in range(int(customers * 1.5)):
        st, ps = random.choice(statuses)
        total = Decimal(random.randrange(1, 40) * 100000)
        orders.append(Order(code=f"BN{i:08d}", store=store, customer=cs[random.randrange(customers)], vendor=vendor,
                            shipping_method=ship, payment_gateway=gw, status=st, payment_status=ps, items_total=total,
                            shipping_cost=Decimal(45000), grand_total=total + 45000, address={}))
    Order.objects.bulk_create(orders, batch_size=5000)
    orders = list(Order.objects.filter(store=store).only("id", "payment_status", "grand_total"))
    OrderItem.objects.bulk_create([
        OrderItem(order=o, product=products[random.randrange(200)], product_name="p", sku="S", quantity=1 + (o.pk % 3),
                  unit_price=Decimal(100000), line_total=Decimal(100000) * (1 + (o.pk % 3))) for o in orders for _ in range(2)], batch_size=5000)
    Transaction.objects.bulk_create([
        Transaction(code=f"TB{o.pk:09d}", order=o, gateway=gw, amount=o.grand_total, status="ok", ref_id=f"R{o.pk}")
        for o in orders if o.payment_status == "paid"], batch_size=5000)
    print(f"seeded customers={customers} orders={len(orders)} at {timezone.now():%H:%M:%S}")


class QueryCounter:
    def __init__(self):
        self.n = 0
        self.seconds = 0.0

    def __call__(self, execute, sql, params, many, context):
        t = time.perf_counter()
        try:
            return execute(sql, params, many, context)
        finally:
            self.n += 1
            self.seconds += time.perf_counter() - t


def make_campaign(store, name, tree):
    from apps.engagement.models import Campaign

    c, _ = Campaign.objects.update_or_create(store=store, name=f"bench-{name}", defaults=dict(
        rules=tree, status=Campaign.Status.ACTIVE, trigger_type=Campaign.Trigger.MANUAL, coupon_type="percent",
        coupon_value=10, personalized=True, channels=["sms", "email"], code_prefix="BN",
    ))
    return c


def one(scenario: str, mode: str, issue_sample: int):
    from apps.catalog.models import Product
    from apps.engagement.services import campaign_service as cs
    from apps.stores.models import Store

    store = Store.objects.get(slug=SLUG)
    tree = trees(list(Product.objects.filter(store=store).values_list("pk", flat=True)[:50]))[scenario]
    campaign = make_campaign(store, scenario, tree)
    counter = QueryCounter()
    base_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    started = time.perf_counter()
    with connection.execute_wrapper(counter):
        if mode == "eligible":
            n = sum(1 for _ in cs.compute_eligible(campaign))
        elif mode == "preview":
            n = cs.preview(campaign)["count"]
        else:  # issue a bounded sample through the real execute path
            ids = []
            for cid in cs.compute_eligible(campaign):
                ids.append(cid)
                if len(ids) >= issue_sample:
                    break
            run = cs.execute_campaign(campaign, candidate_ids=ids)
            n = run.issued + run.skipped_existing
    wall = time.perf_counter() - started
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    print(json.dumps({"scenario": scenario, "mode": mode, "count": n, "wall_s": round(wall, 2), "queries": counter.n,
                      "sql_s": round(counter.seconds, 2), "peak_rss_mb": round(peak / 1024, 1),
                      "rss_growth_mb": round((peak - base_rss) / 1024, 1)}))


def run_all(issue_sample: int):
    print(f"{'scenario':24} {'mode':9} {'count':>8} {'wall_s':>8} {'queries':>8} {'sql_s':>7} {'peakMB':>8} {'growthMB':>9}")
    for scenario in trees([1]).keys():
        for mode in ("eligible", "preview"):
            out = subprocess.run([sys.executable, __file__, "one", scenario, mode, str(issue_sample)],
                                 capture_output=True, text=True, env=os.environ)
            if out.returncode:
                print(scenario, mode, "FAILED", out.stderr[-300:])
                continue
            r = json.loads(out.stdout.strip().splitlines()[-1])
            print(f"{r['scenario']:24} {r['mode']:9} {r['count']:>8} {r['wall_s']:>8} {r['queries']:>8} {r['sql_s']:>7} {r['peak_rss_mb']:>8} {r['rss_growth_mb']:>9}")
    r = subprocess.run([sys.executable, __file__, "one", "aggregate_order_count", "issue", str(issue_sample)],
                       capture_output=True, text=True, env=os.environ)
    print("issuance:", r.stdout.strip().splitlines()[-1] if r.returncode == 0 else r.stderr[-300:])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("seed")
    s.add_argument("--customers", type=int, default=100000)
    r = sub.add_parser("run")
    r.add_argument("--issue-sample", type=int, default=5000)
    o = sub.add_parser("one")
    o.add_argument("scenario")
    o.add_argument("mode")
    o.add_argument("issue_sample", type=int, nargs="?", default=5000)
    a = ap.parse_args()
    if a.cmd == "seed":
        seed(a.customers)
    elif a.cmd == "run":
        run_all(a.issue_sample)
    else:
        one(a.scenario, a.mode, a.issue_sample)
