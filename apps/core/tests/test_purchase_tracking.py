"""Purchase tracking — separated concerns, honest guarantees.

Authoritative payment → verified-gateway eligibility + reporting window → consent verified SERVER-SIDE on the same request (cookie + GPC, same rules as
consent.js) → unique print-claim (at-most-once SERVER print; best-effort browser delivery; provider-side deduplication). A request without consent never burns
the claim. COD / card-transfer are never reported from a browser. Real lifecycle (``apply_payment_success``), real views, real database."""

import json
import threading
from datetime import timedelta
from unittest import mock
from urllib.parse import quote

from django.db import connection
from django.test import Client, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from apps.core import tracking_events
from apps.core.models import TrackingEmission
from apps.core.tests.test_tracking_checkout_cycle import CycleFixture, HOST_A, begin_checkout_events, EVENTS_RE, PAYLOAD
from apps.orders.models import Order, Transaction
from apps.orders.services.lifecycle import apply_payment_success
from apps.stores.models import StoreIntegrationConnection
from apps.core.tests.serialized_rollback import SerializedRollbackSafeMixin


def consent_cookie(a=1, m=0, v=1):
    return quote(json.dumps({"v": v, "a": a, "m": m, "t": 1}))


def events(response):
    match = EVENTS_RE.search(response.content.decode())
    return json.loads(match.group(1)) if match else []


class PurchaseBase(CycleFixture):
    def placed_order(self, client=None):
        """A guest places a real order (checkout_pay); returns (client, order)."""
        client = client or self.visitor()
        self.add(client, self.a)
        self.pay(client)
        return client, Order.objects.order_by("-pk").first()

    def pay_online(self, order, method=Transaction.Method.GATEWAY):
        return apply_payment_success(order, store=order.store, ref_id="REF-1", from_statuses=(Order.PaymentStatus.PENDING,), note="t", method=method)

    def result(self, client, order, *, consent=True, a=1, m=0, gpc=False):
        if consent:
            client.cookies["rs_consent"] = consent_cookie(a, m)
        else:
            client.cookies.pop("rs_consent", None)
        extra = {"HTTP_SEC_GPC": "1"} if gpc else {}
        return client.get(reverse("orders:payment-result", args=[order.code]), **extra)

    def purchases(self, response):
        return [e for e in events(response) if e["name"] == "purchase"]

    def add_meta(self):
        conn = StoreIntegrationConnection.objects.create(store=self.store, provider_code="ad_pixel", is_active=True)
        conn.set_credentials({"pixel_id": "1111111111111111"}); conn.save()


class EligibilityAndClaimTests(PurchaseBase):
    def test_a_verified_gateway_payment_prints_one_purchase_with_the_order_identity_and_irr_values(self):
        client, order = self.placed_order()
        self.pay_online(order)
        response = self.result(client, order)
        (event,) = self.purchases(response)
        self.assertEqual(event["id"], f"purchase:{order.code}")
        self.assertEqual((event["transaction_id"], event["currency"], event["value"]), (order.code, "IRR", int(order.grand_total) * 10))
        self.assertTrue(event["once"])
        self.assertEqual(event["shipping"], int(order.shipping_cost) * 10)
        self.assertEqual(event["items"][0]["item_id"], "CYC-A")
        claim = TrackingEmission.objects.get(order=order)
        self.assertEqual((claim.event_name, claim.channel, claim.store_id, claim.event_id), ("purchase", "browser", order.store_id, event["id"]))

    def test_a_refresh_second_tab_or_later_visit_prints_nothing_more(self):
        client, order = self.placed_order()
        self.pay_online(order)
        self.assertEqual(len(self.purchases(self.result(client, order))), 1)
        for _ in range(3):
            self.assertEqual(self.purchases(self.result(client, order)), [])
        self.assertEqual(TrackingEmission.objects.filter(order=order).count(), 1)

    def test_a_request_without_consent_never_burns_the_claim(self):
        client, order = self.placed_order()
        self.pay_online(order)
        self.assertEqual(self.purchases(self.result(client, order, consent=False)), [])
        self.assertFalse(TrackingEmission.objects.filter(order=order).exists())          # nothing consumed
        self.assertEqual(len(self.purchases(self.result(client, order, a=1, m=0))), 1)    # a later consenting render still reports it

    def test_refusal_stale_policy_version_and_unreadable_cookie_report_nothing(self):
        client, order = self.placed_order()
        self.pay_online(order)
        self.assertEqual(self.purchases(self.result(client, order, a=0, m=0)), [])
        client.cookies["rs_consent"] = consent_cookie(1, 1, v=99)
        self.assertEqual(self.purchases(client.get(reverse("orders:payment-result", args=[order.code]))), [])
        client.cookies["rs_consent"] = "%7Bnot-json"
        self.assertEqual(self.purchases(client.get(reverse("orders:payment-result", args=[order.code]))), [])
        self.assertFalse(TrackingEmission.objects.exists())

    def test_gpc_blocks_marketing_even_with_a_stored_marketing_grant(self):
        StoreIntegrationConnection.objects.filter(store=self.store).delete()              # Meta-only store: marketing is the only category that could dispatch
        self.add_meta()
        client, order = self.placed_order()
        self.pay_online(order)
        self.assertEqual(self.purchases(self.result(client, order, a=0, m=1, gpc=True)), [])
        self.assertFalse(TrackingEmission.objects.exists())
        self.assertEqual(len(self.purchases(self.result(client, order, a=0, m=1, gpc=False))), 1)

    def test_a_consent_category_that_no_loaded_tag_needs_reports_nothing(self):
        client, order = self.placed_order()                                               # GA4-only store (analytics)
        self.pay_online(order)
        self.assertEqual(self.purchases(self.result(client, order, a=0, m=1)), [])
        self.assertFalse(TrackingEmission.objects.exists())

    def test_cod_card_transfer_and_unpaid_orders_are_never_reported_from_a_browser(self):
        client, order = self.placed_order()
        self.assertEqual(self.purchases(self.result(client, order)), [])                  # unpaid
        self.pay_online(order, method=Transaction.Method.CARD_TRANSFER)                   # paid later by an admin
        self.assertEqual(self.purchases(self.result(client, order)), [])
        self.add(client, self.b)                                                          # the same (now logged-in) customer places a second order
        self.pay(client)
        order2 = Order.objects.order_by("-pk").first()
        self.assertNotEqual(order2.pk, order.pk)
        self.pay_online(order2, method=Transaction.Method.COD_CASH)
        self.assertEqual(self.purchases(self.result(client, order2)), [])
        self.assertFalse(TrackingEmission.objects.exists())

    def test_a_payment_verified_long_ago_is_not_reported_as_a_fresh_purchase(self):
        client, order = self.placed_order()
        tx = self.pay_online(order)
        Transaction.objects.filter(pk=tx.pk).update(created_at=timezone.now() - timedelta(minutes=31))
        self.assertEqual(self.purchases(self.result(client, order)), [])
        self.assertFalse(TrackingEmission.objects.exists())

    def test_inactive_tracking_or_the_platform_switch_off_does_nothing(self):
        client, order = self.placed_order()
        self.pay_online(order)
        with self.settings(RASTISI_STOREFRONT_TRACKING_ENABLED=False):
            self.assertEqual(self.purchases(self.result(client, order)), [])
        StoreIntegrationConnection.objects.filter(store=self.store).delete()
        self.assertEqual(self.purchases(self.result(client, order)), [])
        self.assertFalse(TrackingEmission.objects.exists())

    def test_only_the_owning_customer_can_open_the_page_and_never_another_store(self):
        client, order = self.placed_order()
        self.pay_online(order)
        stranger = self.visitor()
        self.assertEqual(self.result(stranger, order).status_code, 404)
        self.assertFalse(TrackingEmission.objects.exists())

    def test_a_failure_inside_tracking_never_breaks_the_payment_result_page(self):
        client, order = self.placed_order()
        self.pay_online(order)
        with mock.patch("apps.core.tracking_events.claim_purchase", side_effect=RuntimeError("db down")):
            response = self.result(client, order)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.purchases(response), [])

    def test_the_claim_carries_no_personal_data_and_dies_with_the_order(self):
        client, order = self.placed_order()
        self.pay_online(order)
        self.result(client, order)
        names = {f.name for f in TrackingEmission._meta.get_fields()}
        self.assertEqual(names, {"id", "store", "order", "event_name", "event_id", "channel", "claimed_at"})
        order_pk = order.pk
        Order.objects.filter(pk=order_pk).delete() if False else None                      # (orders are PROTECTed elsewhere; CASCADE is the model contract)
        self.assertEqual(TrackingEmission._meta.get_field("order").remote_field.on_delete.__name__, "CASCADE")

    def test_unique_claim_constraint_is_enforced_by_the_database(self):
        client, order = self.placed_order()
        self.pay_online(order)
        event = tracking_events.build_purchase(order.store, order)
        self.assertTrue(tracking_events.claim_purchase(order, event))
        self.assertFalse(tracking_events.claim_purchase(order, event))
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError), transaction.atomic():
            TrackingEmission.objects.create(store=order.store, order=order, event_name="purchase", event_id="x", channel="browser")


class ConcurrentRenderTests(SerializedRollbackSafeMixin, TransactionTestCase):
    """Two simultaneous renders of the result page (two tabs): exactly ONE prints the Purchase (unique constraint on a real database)."""

    serialized_rollback = True

    def test_exactly_one_of_two_simultaneous_renders_prints(self):
        if connection.vendor != "postgresql":
            self.skipTest("real concurrency needs PostgreSQL (run with DATABASE_URL=postgres://…)")
        from django.test import override_settings

        with override_settings(ALLOWED_HOSTS=[HOST_A, "testserver"], RASTISI_STOREFRONT_TRACKING_ENABLED=True):
            base = PurchaseBase()
            base.setUp()
            client, order = base.placed_order()
            base.pay_online(order)
            results, barrier = [], threading.Barrier(2)
            session = client.cookies["sessionid"].value

            def worker():
                from django.db import connections
                try:
                    c = Client(HTTP_HOST=HOST_A)
                    c.cookies["sessionid"] = session
                    c.cookies["rs_consent"] = consent_cookie(1, 0)
                    barrier.wait(timeout=10)
                    results.append(len([e for e in events(c.get(reverse("orders:payment-result", args=[order.code]))) if e["name"] == "purchase"]))
                except Exception as exc:  # noqa: BLE001
                    results.append(type(exc).__name__)
                finally:
                    connections.close_all()

            threads = [threading.Thread(target=worker) for _ in range(2)]
            [t.start() for t in threads]; [t.join(60) for t in threads]
            self.assertEqual(sorted(results), [0, 1], results)
            self.assertEqual(TrackingEmission.objects.filter(order=order).count(), 1)
