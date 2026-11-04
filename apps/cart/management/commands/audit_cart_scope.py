"""``manage.py audit_cart_scope`` — READ-ONLY audit of carts before the ``Cart.store`` migration (docs/admin-modernization/CART_STORE_SCOPING_PLAN.md).

Guarantees
* No ``save`` / ``update`` / ``delete`` / ``bulk_*`` / ``get_or_create`` / migration / backfill anywhere in this module — it only runs ``SELECT``s.
* Defence in depth: the whole run executes inside a database-level read-only guard (PostgreSQL ``SET LOCAL transaction_read_only = on``;
  SQLite ``PRAGMA query_only = ON``), so even a future code mistake could not write.
* The report contains NO personal data, session keys or checkout tokens: customers are internal numeric ids, guests are ``sk:<8 hex of sha256>``,
  tokens are ``tok:<8 hex of sha256>`` (just enough to tell two carts apart), stores are slugs.

Usage: ``python manage.py audit_cart_scope [--limit 50] [--json]`` (``--limit`` caps each detail list; summary counts are always complete)."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from contextlib import contextmanager

from django.core.management.base import BaseCommand
from django.db import connection, transaction

from apps.cart.models import Cart, CartItem
from apps.orders.models import Order


@contextmanager
def read_only_guard():
    """Make every write fail at the database level for the duration of the block (and always lift the guard afterwards)."""
    vendor = connection.vendor
    if vendor == "sqlite":
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA query_only = ON")
        try:
            with transaction.atomic():
                yield
        finally:  # outside the atomic block, so it also runs after an error inside it
            with connection.cursor() as cursor:
                cursor.execute("PRAGMA query_only = OFF")
    elif vendor == "postgresql":
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL transaction_read_only = on")  # reset automatically when the transaction ends
            yield
    else:  # pragma: no cover - other backends: rely on the module only containing SELECTs
        with transaction.atomic():
            yield


def _fp(prefix: str, value: str) -> str:
    return f"{prefix}:{hashlib.sha256(value.encode()).hexdigest()[:8]}" if value else f"{prefix}:-"


def build_report(limit: int = 50) -> dict:
    carts = list(Cart.objects.values("pk", "customer_id", "session_key", "checkout_token", "created_at"))
    items = list(CartItem.objects.values("cart_id", "product__store__slug", "gift_wrap_selected", "gift_message", "variant_id"))
    by_cart: dict[int, list[dict]] = defaultdict(list)
    for row in items:
        by_cart[row["cart_id"]].append(row)

    orders_by_key = {}
    for key, customer_id, store_slug, order_pk in Order.objects.exclude(idempotency_key="").values_list(
        "idempotency_key", "customer_id", "store__slug", "pk"
    ):
        orders_by_key[key] = (customer_id, store_slug)
    customer_order_stores: dict[int, set] = defaultdict(set)
    for customer_id, store_slug in Order.objects.values_list("customer_id", "store__slug").distinct():
        customer_order_stores[customer_id].add(store_slug)

    def describe(cart) -> dict:
        its = by_cart.get(cart["pk"], [])
        stores = defaultdict(int)
        for it in its:
            stores[it["product__store__slug"]] += 1
        return {
            "cart": cart["pk"],
            "kind": "customer" if cart["customer_id"] else "guest",
            "customer": cart["customer_id"],
            "session": _fp("sk", cart["session_key"]) if not cart["customer_id"] else None,
            "token": _fp("tok", cart["checkout_token"]) if cart["checkout_token"] else None,
            "items": len(its),
            "stores": dict(stores),
        }

    described = [describe(c) for c in carts]
    guests = [d for d in described if d["kind"] == "guest"]
    customers = [d for d in described if d["kind"] == "customer"]
    empty = [d for d in described if d["items"] == 0]
    mixed = [d for d in described if len(d["stores"]) > 1]

    # (customer, store) / (session, store) pairs that more than one cart would claim
    pair_carts: dict[tuple, list[int]] = defaultdict(list)
    for d in described:
        owner = ("c", d["customer"]) if d["kind"] == "customer" else ("g", d["session"])
        for store_slug in d["stores"]:
            pair_carts[owner + (store_slug,)].append(d["cart"])
    duplicates = [
        {"owner": f"{k[0]}:{k[1]}", "store": k[2], "carts": sorted(v)} for k, v in pair_carts.items() if len(set(v)) > 1
    ]
    # more than one cart for the same customer / session, regardless of items (empty duplicates included)
    per_owner: dict[tuple, list[int]] = defaultdict(list)
    for d in described:
        per_owner[("c", d["customer"]) if d["kind"] == "customer" else ("g", d["session"])].append(d["cart"])
    multi_cart_owners = [{"owner": f"{k[0]}:{k[1]}", "carts": sorted(v)} for k, v in per_owner.items() if len(v) > 1]

    with_token = [d for d, c in zip(described, carts) if c["checkout_token"]]
    token_to_order, token_orphan, token_foreign = [], [], []
    for d, c in zip(described, carts):
        if not c["checkout_token"]:
            continue
        hit = orders_by_key.get(c["checkout_token"])
        if hit is None:
            token_orphan.append(d)
        elif d["kind"] == "customer" and hit[0] == d["customer"]:
            token_to_order.append({**d, "order_store": hit[1]})
        else:
            token_foreign.append({**d, "order_store": hit[1]})

    ambiguous = []
    for d in mixed:
        ambiguous.append({"reason": "mixed_store_cart: choose which store keeps the original cart/token", **d})
    for dup in duplicates:
        ambiguous.append({"reason": "duplicate_cart_for_owner_and_store: merge policy needed", **dup})
    for d in token_foreign:
        ambiguous.append({"reason": "token_matches_order_of_another_customer: investigate", **d})
    for d in empty:
        if d["kind"] == "customer":
            cart_row = next(c for c in carts if c["pk"] == d["cart"])
            derivable = bool(
                (cart_row["checkout_token"] and cart_row["checkout_token"] in orders_by_key)
                or customer_order_stores.get(d["customer"])
            )
            if not derivable:
                ambiguous.append({"reason": "empty_customer_cart_without_derivable_store: delete / keep policy needed", **d})
        else:
            if d["token"] is None:
                ambiguous.append({"reason": "empty_guest_cart_without_token: delete policy needed", **d})
    for d, c in zip(described, carts):
        if d["kind"] == "guest" and not c["session_key"]:
            ambiguous.append({"reason": "guest_cart_without_session_key: unaddressable", **d})

    gift_lines = sum(1 for it in items if it["gift_wrap_selected"])
    return {
        "summary": {
            "carts": len(carts), "items": len(items), "guest_carts": len(guests), "customer_carts": len(customers),
            "empty_carts": len(empty), "mixed_store_carts": len(mixed), "duplicate_owner_store_pairs": len(duplicates),
            "owners_with_more_than_one_cart": len(multi_cart_owners), "carts_with_checkout_token": len(with_token),
            "tokens_linked_to_an_order_of_the_same_customer": len(token_to_order), "tokens_without_any_order": len(token_orphan),
            "tokens_linked_to_another_customers_order": len(token_foreign), "lines_with_gift_wrap": gift_lines,
            "lines_with_gift_message": sum(1 for it in items if it["gift_message"]), "ambiguous_cases_needing_a_decision": len(ambiguous),
        },
        "details": {
            "mixed_store_carts": mixed[:limit], "duplicates": duplicates[:limit], "owners_with_more_than_one_cart": multi_cart_owners[:limit],
            "empty_carts": empty[:limit], "tokens_linked_to_order": token_to_order[:limit], "tokens_without_order": token_orphan[:limit],
            "tokens_linked_to_another_customer": token_foreign[:limit], "ambiguous": ambiguous[:limit],
        },
    }


class Command(BaseCommand):
    help = "READ-ONLY audit of carts for the Cart.store migration (no writes, no personal data, no full tokens)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50, help="max rows per detail list (summary counts are always complete)")
        parser.add_argument("--json", action="store_true", help="print the (masked) report as JSON")

    def handle(self, *args, **options):
        with read_only_guard():
            report = build_report(limit=max(0, options["limit"]))
        if options["json"]:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, default=str))
            return
        self.stdout.write("== audit_cart_scope (READ-ONLY) ==")
        for key, value in report["summary"].items():
            self.stdout.write(f"{key:50s} {value}")
        for name, rows in report["details"].items():
            if not rows:
                continue
            self.stdout.write(f"\n-- {name} (max {options['limit']}) --")
            for row in rows:
                self.stdout.write("  " + json.dumps(row, ensure_ascii=False, default=str))
        self.stdout.write("\nNo data was changed. Personal data, session keys and full tokens are never printed.")
