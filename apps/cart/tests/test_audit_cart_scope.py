"""``audit_cart_scope`` is strictly read-only, masks personal data and reports the cases the Cart.store backfill needs a human decision for."""

import json
from decimal import Decimal
from io import StringIO

from django.apps import apps as django_apps
from django.core.management import call_command
from django.db import DatabaseError, connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.cart.management.commands.audit_cart_scope import read_only_guard
from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product, Vendor
from apps.customers.models import Address, Customer
from apps.orders.models import Order, PaymentGateway, ShippingMethod
from apps.orders.services.order_service import create_order_from_cart
from apps.stores.models import Store
from django.contrib.auth import get_user_model

User = get_user_model()
SECRET_TOKEN = "SUPER-SECRET-TOKEN-VALUE-0123456789"
SESSION = "sessionkeyabcdefghijklmnop123456"


class AuditCartScopeTests(TestCase):
    def setUp(self):
        self.a = Store.objects.get(slug="akhlaghi")
        self.b = Store.objects.create(name="Audit B", slug="audit-store-b", status=Store.Status.ACTIVE)
        self.prod = {}
        self.ship = {}
        self.gw = {}
        self.vendor = {}
        for tag, s in (("a", self.a), ("b", self.b)):
            self.vendor[tag] = Vendor.objects.create(store=s, name=f"v{tag}", slug=f"aud-v-{tag}")
            cat = Category.objects.create(store=s, name=f"c{tag}", slug=f"aud-c-{tag}")
            self.prod[tag] = Product.objects.create(store=s, vendor=self.vendor[tag], category=cat, name=f"p{tag}", slug=f"aud-p-{tag}", sku=f"AUD-{tag}", price=Decimal("1000"), stock=50)
            self.ship[tag] = ShippingMethod.objects.create(store=s, name="پست", slug=f"aud-s-{tag}", cost=Decimal("0"))
            self.gw[tag] = PaymentGateway.objects.create(store=s, name="g", slug=f"aud-g-{tag}")
        self.people = {}
        for n, name in enumerate(("X", "Y", "Z", "W", "V", "U"), start=1):
            user = User.objects.create_user(username=f"0912000900{n}", password="x12345678")
            self.people[name] = Customer.objects.create(user=user, full_name=f"نام محرمانه {name}", phone=f"0912000900{n}")

        def cart(customer=None, session="", token=""):
            return Cart.objects.create(customer=customer, session_key=session, checkout_token=token)

        def line(c, product, qty=1, gift=False, msg=""):
            return CartItem.objects.create(cart=c, product=product, quantity=qty, unit_price=Decimal("1000"), gift_wrap_selected=gift, gift_message=msg)

        # X: one cart mixing both stores
        self.mixed = cart(self.people["X"]); line(self.mixed, self.prod["a"]); line(self.mixed, self.prod["b"], gift=True, msg="پیام خصوصی")
        # Y: two carts, both with store-A items (duplicate)
        self.dup1 = cart(self.people["Y"]); line(self.dup1, self.prod["a"])
        self.dup2 = cart(self.people["Y"]); line(self.dup2, self.prod["a"], 3)
        # Z: empty cart whose token belongs to Z's own order (derivable)
        zc = cart(self.people["Z"]); line(zc, self.prod["a"])
        addr = Address.objects.create(customer=self.people["Z"], receiver_name="z", phone="09120009003", province="t", city="t", full_address="x")
        order = create_order_from_cart(zc, customer=self.people["Z"], vendor=self.vendor["a"], address=addr, shipping_method=self.ship["a"],
                                       payment_gateway=self.gw["a"], store=self.a, idempotency_key=SECRET_TOKEN)
        zc.items.all().delete(); Cart.objects.filter(pk=zc.pk).update(checkout_token=SECRET_TOKEN)
        self.z_cart = zc
        # W: empty customer cart, no orders, no token (ambiguous)
        self.w_cart = cart(self.people["W"])
        # V: cart whose token equals Z's order key (another customer's order → critical)
        self.v_cart = cart(self.people["V"], token=SECRET_TOKEN); line(self.v_cart, self.prod["b"])
        # U: orphan token (no order) with an item
        self.u_cart = cart(self.people["U"], token="orphan-token-xyz-987654321"); line(self.u_cart, self.prod["a"])
        # guests
        self.g1 = cart(session=SESSION); line(self.g1, self.prod["b"])
        self.g_empty = cart(session="emptyguestsession0000000000000000")

    def run_cmd(self, *args):
        out = StringIO()
        call_command("audit_cart_scope", *args, stdout=out)
        return out.getvalue()

    def snapshot(self):
        counts = {m._meta.label: m.objects.count() for m in django_apps.get_models() if m._meta.managed and not m._meta.proxy}
        rows = {
            "cart": list(Cart.objects.order_by("pk").values()), "item": list(CartItem.objects.order_by("pk").values()),
            "order": list(Order.objects.order_by("pk").values_list("pk", "idempotency_key", "updated_at")),
            "customer": list(Customer.objects.order_by("pk").values_list("pk", "updated_at")),
        }
        return counts, rows

    def test_it_changes_nothing_and_issues_no_write_statement(self):
        before = self.snapshot()
        with CaptureQueriesContext(connection) as ctx:
            self.run_cmd(); self.run_cmd("--json", "--limit", "5")
        self.assertEqual(self.snapshot(), before)
        writes = [q["sql"] for q in ctx.captured_queries if q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "ALTER", "DROP"))]
        self.assertEqual(writes, [])

    def test_the_database_level_guard_really_blocks_writes_and_is_lifted_afterwards(self):
        with self.assertRaises(DatabaseError):
            with read_only_guard():
                Cart.objects.create(session_key="should-never-be-written")
        self.assertFalse(Cart.objects.filter(session_key="should-never-be-written").exists())
        Cart.objects.create(session_key="writable-again-after-guard")                      # the guard is not left switched on
        self.assertTrue(Cart.objects.filter(session_key="writable-again-after-guard").exists())

    def test_output_has_no_personal_data_session_keys_or_full_tokens(self):
        for text in (self.run_cmd(), self.run_cmd("--json")):
            for forbidden in (SECRET_TOKEN, "orphan-token-xyz-987654321", SESSION, "emptyguestsession", "نام محرمانه", "پیام خصوصی", "0912000900"):
                self.assertNotIn(forbidden, text)
        self.assertIn("tok:", self.run_cmd())

    def test_summary_numbers(self):
        s = json.loads(self.run_cmd("--json"))["summary"]
        self.assertEqual(s["carts"], Cart.objects.count())
        self.assertEqual(s["items"], CartItem.objects.count())
        self.assertEqual(s["guest_carts"], 2)
        self.assertEqual(s["customer_carts"], Cart.objects.count() - 2)
        self.assertEqual(s["mixed_store_carts"], 1)
        self.assertEqual(s["duplicate_owner_store_pairs"], 1)
        self.assertEqual(s["owners_with_more_than_one_cart"], 1)
        self.assertEqual(s["empty_carts"], 3)                                               # Z's, W's and the empty guest cart
        self.assertEqual(s["carts_with_checkout_token"], 3)
        self.assertEqual(s["tokens_linked_to_an_order_of_the_same_customer"], 1)
        self.assertEqual(s["tokens_linked_to_another_customers_order"], 1)
        self.assertEqual(s["tokens_without_any_order"], 1)
        self.assertEqual(s["lines_with_gift_wrap"], 1)
        self.assertEqual(s["lines_with_gift_message"], 1)

    def test_ambiguous_cases_are_flagged_for_a_human_decision(self):
        report = json.loads(self.run_cmd("--json"))
        reasons = [a["reason"].split(":")[0] for a in report["details"]["ambiguous"]]
        for expected in ("mixed_store_cart", "duplicate_cart_for_owner_and_store", "token_matches_order_of_another_customer",
                         "empty_customer_cart_without_derivable_store", "empty_guest_cart_without_token"):
            self.assertIn(expected, reasons)
        self.assertNotIn("empty_customer_cart_without_derivable_store", [r for r, a in zip(reasons, report["details"]["ambiguous"]) if a.get("cart") == self.z_cart.pk])
        self.assertEqual(report["summary"]["ambiguous_cases_needing_a_decision"], len(reasons))

    def test_limit_caps_detail_lists_but_not_the_summary(self):
        report = json.loads(self.run_cmd("--json", "--limit", "1"))
        self.assertLessEqual(len(report["details"]["empty_carts"]), 1)
        self.assertEqual(report["summary"]["empty_carts"], 3)
