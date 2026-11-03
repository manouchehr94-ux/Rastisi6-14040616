"""FEAT-006 (M8) — migration compatibility & backward safety.

The payment-engine work added three new migrations on top of the base
(``0019_reconciliation_evidence_level``):

* ``0020_alter_paymentattempt_status_paymenttransactionevent`` —
  AlterField (adds refund/settle status choices, choices-only) + CreateModel
  (``PaymentTransactionEvent``, a brand-new additive table).
* ``0021_alter_paymentgatewayconfig_gateway_code`` — AlterField widening the
  ``gateway_code`` choices to add zarinpal + card_to_card (choices-only).
* ``0022_alter_paymentgatewayconfig_gateway_code`` — AlterField widening the
  ``gateway_code`` choices to add the six PSP + two BNPL codes (choices-only).

These tests assert the migrations are ADDITIVE and BACKWARD-COMPATIBLE:

* a pre-upgrade-style ``PaymentGatewayConfig`` row with ``gateway_code`` in
  {zibal, cod} still loads and behaves (credentials decrypt, readiness derives,
  is_configured/is_online work) after the new migrations;
* the two legacy codes remain valid ``GatewayCode`` choices;
* each new migration contains only AlterField/CreateModel (no destructive
  RemoveField/DeleteModel/RenameField that could drop existing data);
* ``makemigrations --check --dry-run`` reports no pending changes (asserted
  here AND in the feature verification step).
"""

from __future__ import annotations

import io
from decimal import Decimal

from django.core.management import call_command
from django.db.migrations.loader import MigrationLoader
from django.test import TestCase

from apps.orders.encryption import reset_fernet
from apps.orders.models import PaymentGatewayConfig
from apps.stores.models import Store

NEW_MIGRATIONS = [
    "0020_alter_paymentattempt_status_paymenttransactionevent",
    "0021_alter_paymentgatewayconfig_gateway_code",
    "0022_alter_paymentgatewayconfig_gateway_code",
]

# Operations that would be destructive to existing data if present in an
# "additive" migration.
DESTRUCTIVE_OPS = {
    "RemoveField",
    "DeleteModel",
    "RenameField",
    "RenameModel",
    "AlterUniqueTogether",
}


class MigrationAdditivityTests(TestCase):
    def test_new_migrations_contain_only_additive_operations(self):
        loader = MigrationLoader(None, ignore_no_migrations=True)
        for name in NEW_MIGRATIONS:
            migration = loader.get_migration("orders", name)
            for op in migration.operations:
                op_name = type(op).__name__
                self.assertNotIn(
                    op_name,
                    DESTRUCTIVE_OPS,
                    f"{name} contains destructive op {op_name}",
                )
                self.assertIn(
                    op_name,
                    {"AlterField", "CreateModel", "AddField", "AddIndex"},
                    f"{name} has unexpected op {op_name}",
                )

    def test_gateway_code_alterfields_only_widen_choices(self):
        """0021/0022 must only change the ``choices`` of gateway_code, never its
        db type / null / max_length in a way that could break existing rows."""
        loader = MigrationLoader(None, ignore_no_migrations=True)
        for name in (
            "0021_alter_paymentgatewayconfig_gateway_code",
            "0022_alter_paymentgatewayconfig_gateway_code",
        ):
            migration = loader.get_migration("orders", name)
            alter_ops = [op for op in migration.operations if type(op).__name__ == "AlterField"]
            self.assertTrue(alter_ops, name)
            for op in alter_ops:
                self.assertEqual(op.model_name, "paymentgatewayconfig")
                self.assertEqual(op.name, "gateway_code")
                # max_length preserved at 30; not nullable.
                self.assertEqual(op.field.max_length, 30)
                self.assertFalse(op.field.null)

    def test_makemigrations_check_is_clean(self):
        """No pending migrations — the committed migrations match the models."""
        out = io.StringIO()
        try:
            call_command(
                "makemigrations", "--check", "--dry-run", stdout=out, stderr=out
            )
        except SystemExit as exc:  # --check exits non-zero if changes are pending
            self.fail(f"makemigrations --check reported pending changes: {out.getvalue()} ({exc})")


class LegacyConfigBackwardCompatTests(TestCase):
    """A pre-upgrade {zibal, cod} config still loads and behaves."""

    def setUp(self):
        reset_fernet()
        self.addCleanup(reset_fernet)
        self.store = Store.objects.create(
            name="legacy", slug="mig-legacy-store", status=Store.Status.ACTIVE
        )

    def test_legacy_codes_are_still_valid_choices(self):
        codes = {c for c, _ in PaymentGatewayConfig.GatewayCode.choices}
        self.assertIn("zibal", codes)
        self.assertIn("cod", codes)

    def test_pre_upgrade_zibal_config_still_loads_and_behaves(self):
        # Simulate a row created BEFORE the new migrations: only the two legacy
        # codes existed then. The row must still load and behave now.
        config = PaymentGatewayConfig(
            store=self.store, gateway_code="zibal", is_active=True
        )
        config.set_credentials({"merchant": "legacy-merchant-id"})
        config.save()

        reloaded = PaymentGatewayConfig.objects.get(pk=config.pk)
        # Credentials still decrypt.
        self.assertEqual(reloaded.get_credentials()["merchant"], "legacy-merchant-id")
        # Online + configured derivation still works.
        self.assertTrue(reloaded.is_online)
        self.assertTrue(reloaded.is_configured)
        # Readiness derives to CONNECTED (configured, non-sandbox).
        self.assertEqual(
            reloaded.readiness_status,
            PaymentGatewayConfig.ReadinessStatus.CONNECTED,
        )

    def test_pre_upgrade_cod_config_still_loads_and_behaves(self):
        config = PaymentGatewayConfig(
            store=self.store, gateway_code="cod", is_active=True
        )
        config.save()
        reloaded = PaymentGatewayConfig.objects.get(pk=config.pk)
        # COD is offline and needs no credentials -> configured & CONNECTED.
        self.assertFalse(reloaded.is_online)
        self.assertTrue(reloaded.is_configured)
        self.assertEqual(
            reloaded.readiness_status,
            PaymentGatewayConfig.ReadinessStatus.CONNECTED,
        )

    def test_legacy_config_is_unaffected_by_new_gateway_codes(self):
        # Adding new codes must not change the behavior of a legacy zibal row.
        legacy = PaymentGatewayConfig(store=self.store, gateway_code="zibal", is_active=True)
        legacy.set_credentials({"merchant": "m"})
        legacy.save()
        # A new-code config in the SAME store coexists without disturbing it.
        new = PaymentGatewayConfig(
            store=self.store, gateway_code="zarinpal", is_active=True
        )
        new.set_credentials({"merchant_id": "z" * 36})
        new.save()
        legacy.refresh_from_db()
        self.assertEqual(legacy.gateway_code, "zibal")
        self.assertEqual(legacy.get_credentials()["merchant"], "m")
        self.assertEqual(
            legacy.readiness_status, PaymentGatewayConfig.ReadinessStatus.CONNECTED
        )


class PaymentTransactionEventTableTests(TestCase):
    """The new additive table exists and is usable (fresh SQLite migrate)."""

    def test_payment_transaction_event_model_is_creatable(self):
        from apps.catalog.models import Vendor
        from apps.customers.models import Customer
        from apps.orders.models import (
            Order,
            PaymentGateway,
            PaymentTransactionEvent,
            ShippingMethod,
        )
        from django.contrib.auth import get_user_model

        store = Store.objects.get(slug="akhlaghi")
        user = get_user_model().objects.create_user(username="pte_user", password="x12345678")
        customer = Customer.objects.create(user=user, full_name="c", phone="09120000002")
        vendor = Vendor.objects.create(store=store, name="v", slug="pte-vendor")
        shipping = ShippingMethod.objects.create(
            store=store, name="p", slug="pte-post", cost=Decimal("0"), is_active=True
        )
        gateway = PaymentGateway.objects.create(
            store=store, name="زیبال", slug="zibal", is_active=True
        )
        order = Order.objects.create(
            code="DM-PTE",
            store=store,
            customer=customer,
            vendor=vendor,
            address={},
            shipping_method=shipping,
            payment_gateway=gateway,
            items_total=Decimal("1000"),
            grand_total=Decimal("1000"),
        )
        event = PaymentTransactionEvent.objects.create(
            store=store,
            order=order,
            event_type="created",
            amount=Decimal("1000"),
            currency="TOMAN",
            message="ساخت تلاش",
        )
        self.assertIsNotNone(event.pk)
        self.assertEqual(event.amount, Decimal("1000"))
        self.assertEqual(event.currency, "TOMAN")
