"""Payment-engine migration compatibility & backward safety (reconciled graph).

Two lineages independently added an ``orders`` migration ``0020`` on top of ``0019_reconciliation_evidence_level``:
the canonical card-transfer work (``0020_card_transfer``, kept AS IS and first) and the payment-engine work. The engine's
schema delta was NOT auto-merged: it was regenerated from the final merged model state as ONE additive migration on top of
the canonical ``0020_card_transfer``:

* ``0021_payment_engine_unified`` — AddField ``PaymentAttempt.gateway_redirect_url``; AlterField ``PaymentAttempt.status``
  (choices + max_length 15 -> 20, widening only); AlterField ``PaymentGatewayConfig.gateway_code`` (the UNION of every
  provider code, choices-only); AlterField ``PaymentReconciliation.kind`` (adds ``settlement_uncertain``, choices-only);
  CreateModel ``PaymentTransactionEvent`` (new append-only table).

These tests assert the graph has a single leaf, the migration is ADDITIVE and BACKWARD-COMPATIBLE, and that pre-upgrade
rows still load and behave.
"""

from __future__ import annotations

import io
from decimal import Decimal

from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.db.migrations.loader import MigrationLoader
from django.test import TestCase

from apps.orders.encryption import reset_fernet
from apps.orders.models import PaymentGatewayConfig
from apps.stores.models import Store

NEW_MIGRATIONS = ["0021_payment_engine_unified"]

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

    def test_gateway_code_alterfield_only_widens_choices_and_union_is_complete(self):
        loader = MigrationLoader(None, ignore_no_migrations=True)
        migration = loader.get_migration("orders", "0021_payment_engine_unified")
        alters = [op for op in migration.operations if type(op).__name__ == "AlterField" and op.name == "gateway_code"]
        self.assertEqual(len(alters), 1)
        op = alters[0]
        self.assertEqual(op.model_name, "paymentgatewayconfig")
        self.assertEqual(op.field.max_length, 30)           # unchanged db type
        self.assertFalse(op.field.null)
        codes = {c for c, _ in op.field.choices}
        self.assertEqual(codes, {"zibal", "cod", "zarinpal", "card_to_card", "pasargad", "saman", "parsian", "mellat", "sadad", "tejarat", "snappay", "torobpay"})

    def test_attempt_status_only_widens(self):
        loader = MigrationLoader(None, ignore_no_migrations=True)
        migration = loader.get_migration("orders", "0021_payment_engine_unified")
        op = next(o for o in migration.operations if type(o).__name__ == "AlterField" and o.name == "status")
        self.assertEqual(op.field.max_length, 20)           # was 15: widening a varchar is lossless
        old = {"created", "requesting", "redirect_ready", "pending", "succeeded", "failed", "canceled", "expired"}
        self.assertTrue(old <= {c for c, _ in op.field.choices})

    def test_single_leaf_and_canonical_card_transfer_migration_is_preserved_as_parent(self):
        loader = MigrationLoader(None, ignore_no_migrations=True)
        leaves = [k for k in loader.graph.leaf_nodes() if k[0] == "orders"]
        self.assertEqual(leaves, [("orders", "0021_payment_engine_unified")])
        migration = loader.get_migration("orders", "0021_payment_engine_unified")
        self.assertIn(("orders", "0020_card_transfer"), migration.dependencies)
        self.assertTrue(loader.get_migration("orders", "0020_card_transfer"))   # never renumbered / replaced

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

    def test_pre_upgrade_zibal_and_cod_configs_survive_additive_choice_extension(self):
        """§2 discrepancy regression: a pre-existing merchant's zibal AND cod
        PaymentGatewayConfig rows must survive the additive gateway_code choice
        extension (0006 -> 0021 -> 0022) with NOTHING dropped, renamed,
        duplicated, or disconnected.

        Asserts for BOTH legacy codes, after reload:
          * gateway_code is byte-identical to what was saved (not renamed);
          * encrypted credentials still decrypt to the original payload;
          * readiness_status still derives to CONNECTED (not disconnected);
          * exactly one row exists per (store, gateway_code) — nothing was
            duplicated — and the uniq_gateway_config_per_store UniqueConstraint
            still rejects a duplicate insert for the same store.
        """
        # A pre-existing merchant configured zibal (online) + cod (offline),
        # exactly as could have existed on base commit 7d311556 when only these
        # two codes were valid.
        zibal = PaymentGatewayConfig(
            store=self.store, gateway_code="zibal", is_active=True
        )
        zibal.set_credentials({"merchant": "pre-existing-zibal-merchant"})
        zibal.save()
        cod = PaymentGatewayConfig(
            store=self.store, gateway_code="cod", is_active=True
        )
        cod.save()

        # Reload from the DB (simulates loading after the additive migrations).
        reloaded_zibal = PaymentGatewayConfig.objects.get(
            store=self.store, gateway_code="zibal"
        )
        reloaded_cod = PaymentGatewayConfig.objects.get(
            store=self.store, gateway_code="cod"
        )

        # gateway_code intact (not dropped / renamed).
        self.assertEqual(reloaded_zibal.gateway_code, "zibal")
        self.assertEqual(reloaded_cod.gateway_code, "cod")

        # Credentials intact and still decryptable.
        self.assertEqual(
            reloaded_zibal.get_credentials()["merchant"],
            "pre-existing-zibal-merchant",
        )
        self.assertEqual(reloaded_cod.get_credentials(), {})

        # Readiness intact (not disconnected) — both derive to CONNECTED.
        self.assertEqual(
            reloaded_zibal.readiness_status,
            PaymentGatewayConfig.ReadinessStatus.CONNECTED,
        )
        self.assertEqual(
            reloaded_cod.readiness_status,
            PaymentGatewayConfig.ReadinessStatus.CONNECTED,
        )

        # Nothing duplicated: exactly one row per (store, gateway_code).
        self.assertEqual(
            PaymentGatewayConfig.objects.filter(
                store=self.store, gateway_code="zibal"
            ).count(),
            1,
        )
        self.assertEqual(
            PaymentGatewayConfig.objects.filter(
                store=self.store, gateway_code="cod"
            ).count(),
            1,
        )

        # The uniq_gateway_config_per_store UniqueConstraint is still enforced:
        # a second zibal config for the same store must be rejected.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PaymentGatewayConfig.objects.create(
                    store=self.store, gateway_code="zibal", is_active=True
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
