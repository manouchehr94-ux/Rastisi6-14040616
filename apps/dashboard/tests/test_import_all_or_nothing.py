"""Fail-closed, all-or-nothing import safety (data-transfer-safety-v1).

A confirmed file is applied completely or not at all:

* any validation error blocks execution (preview still shows everything);
* the file is re-read and fully re-validated against the *current* Store right
  before the first mutation;
* all business-data writes run inside one outer transaction, so any later
  failure rolls back everything (products, variants, StockMovement, aggregate
  stock, quota consumption) while the failure details are persisted outside it.

The service layer is exercised directly; view tests prove the UI/POST paths
cannot bypass the rule.
"""

from decimal import Decimal
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.catalog.models import (
    InventoryReservation,
    Product,
    ProductVariant,
    StockMovement,
    WarehouseInventory,
)
from apps.core.models import AuditLogEntry, ImportJob, ImportRowResult
from apps.dashboard.services import import_service
from apps.dashboard.tests.test_import_inventory import INV_HEADER, InventoryImportTestCase
from apps.dashboard.tests.test_import_product import PRODUCT_HEADER, ProductImportTestCase
from apps.dashboard.tests.test_import_variant import VARIANT_HEADER, VariantImportTestCase
from apps.dashboard.tests.test_import_views import ImportViewTestCase
from apps.dashboard.tests.xlsx_helpers import xlsx_upload
from apps.stores.models import StoreMembership

Blocked = import_service.ImportExecutionBlocked
SERVICE = "apps.dashboard.services.import_service"


def _product_rows(count, *, prefix="AON"):
    return "".join(
        f",{prefix}-{i},کالای {i},,,active,brand-imp,leaf-imp,{1000 + i},{i},,,,,\n" for i in range(count)
    )


def _actions(store):
    return list(AuditLogEntry.objects.filter(store=store, action_code__startswith="import.").values_list(
        "action_code", flat=True,
    ))


class FailClosedProductTests(ProductImportTestCase):
    def test_one_invalid_row_among_99_valid_changes_nothing(self):
        bad = ",,,,,,,,,,,,,,\n"  # no name / category / price
        csv_text = PRODUCT_HEADER + _product_rows(50) + bad + _product_rows(49, prefix="AOP")
        job = self._job(csv_text, mode=ImportJob.Mode.CREATE_ONLY)
        import_service.run_preview(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual((job.total_rows, job.valid_rows, job.invalid_rows), (100, 99, 1))

        before = Product.objects.filter(store=self.store).count()
        with self.assertRaises(Blocked):
            import_service.run_execution(job, actor=self.actor)
        self.assertEqual(Product.objects.filter(store=self.store).count(), before)
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.PREVIEW_READY)
        self.assertEqual((job.created_rows, job.updated_rows), (0, 0))
        # the merchant can still see exactly which row is wrong
        self.assertEqual(
            list(ImportRowResult.objects.filter(import_job=job, status="invalid").values_list("row_number", flat=True)),
            [51],
        )
        self.assertEqual(import_service.job_execution_blockers(job), ["1 ردیف خطا دارد."])

    def test_blocked_job_can_be_retried_but_never_partially_applied(self):
        job = self._job(PRODUCT_HEADER + _product_rows(3) + ",,,,,,,,,,,,,,\n")
        for _ in range(3):
            with self.assertRaises(Blocked):
                import_service.run_execution(job, actor=self.actor)
        self.assertFalse(Product.objects.filter(store=self.store, sku__startswith="AON-").exists())

    def test_rejection_is_audited_as_validation_rejection_not_success(self):
        job = self._job(PRODUCT_HEADER + _product_rows(2) + ",,,,,,,,,,,,,,\n")
        with self.assertRaises(Blocked):
            import_service.run_execution(job, actor=self.actor)
        actions = _actions(self.store)
        self.assertIn("import.execution_rejected", actions)
        self.assertNotIn("import.execution_completed", actions)
        self.assertNotIn("import.execution_rolled_back", actions)
        entry = AuditLogEntry.objects.get(store=self.store, action_code="import.execution_rejected")
        self.assertEqual(entry.result, AuditLogEntry.ResultStatus.FAILURE)

    def test_execution_time_revalidation_catches_store_changes_after_preview(self):
        csv_text = PRODUCT_HEADER + _product_rows(5)
        job = self._job(csv_text, mode=ImportJob.Mode.CREATE_ONLY)
        import_service.run_preview(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 0)
        self.assertEqual(import_service.job_execution_blockers(job), [])

        # Someone creates one of the SKUs after the preview was produced.
        Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.leaf, name="هم‌زمان", slug="raced-sku",
            sku="AON-3", price=Decimal("1"), stock=0,
        )
        with self.assertRaises(Blocked) as ctx:
            import_service.run_execution(job, actor=self.actor)
        self.assertIn("از زمانِ پیش‌نمایش تغییر کرده", str(ctx.exception))
        self.assertIn("هیچ تغییری اعمال نشد", str(ctx.exception))
        self.assertEqual(
            sorted(Product.objects.filter(store=self.store, sku__startswith="AON-").values_list("sku", flat=True)),
            ["AON-3"],  # only the concurrently created product; nothing from the import
        )
        job.refresh_from_db()
        # back to a *fresh* preview that now shows the conflicting row
        self.assertEqual(job.status, ImportJob.Status.PREVIEW_READY)
        self.assertEqual(job.invalid_rows, 1)
        self.assertEqual(
            ImportRowResult.objects.get(import_job=job, status="invalid").source_identifier, "AON-3",
        )
        self.assertTrue(job.error_report_file)

    def test_revalidation_is_a_full_reread_of_the_source_file_not_the_stale_preview(self):
        job = self._job(PRODUCT_HEADER + _product_rows(2))
        import_service.run_preview(job, actor=self.actor)
        # Tamper with the stored preview rows: they claim everything is fine / broken.
        ImportRowResult.objects.filter(import_job=job).update(status="valid", errors=[])
        with mock.patch(f"{SERVICE}.read_job_rows", wraps=import_service.read_job_rows) as reader:
            import_service.run_execution(job, actor=self.actor)
        # once for the quota check/validation set-up, once is enough: the file was re-read
        self.assertGreaterEqual(reader.call_count, 1)
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.COMPLETED)

    def test_stale_preview_cannot_authorise_a_file_that_is_invalid_now(self):
        job = self._job(PRODUCT_HEADER + _product_rows(2), mode=ImportJob.Mode.UPDATE_ONLY)
        # Preview says "invalid" for both rows (nothing to update); even forcing the stored
        # preview to look clean must not let execution through.
        import_service.run_preview(job, actor=self.actor)
        ImportRowResult.objects.filter(import_job=job).update(status="valid", errors=[])
        ImportJob.objects.filter(pk=job.pk).update(invalid_rows=0, valid_rows=2)
        job.refresh_from_db()
        with self.assertRaises(Blocked):
            import_service.run_execution(job, actor=self.actor)
        self.assertFalse(Product.objects.filter(store=self.store, sku__startswith="AON-").exists())

    def test_permission_subscription_and_row_budget_are_rechecked_at_execution(self):
        job = self._job(PRODUCT_HEADER + _product_rows(2))
        import_service.run_preview(job, actor=self.actor)
        from apps.subscriptions.services.entitlement_service import FeatureNotAvailable, UsageLimitExceeded

        with mock.patch(
            "apps.subscriptions.services.enforcement.enforce_import_allowed",
            side_effect=FeatureNotAvailable("off"),
        ):
            with self.assertRaises(FeatureNotAvailable):
                import_service.run_execution(job, actor=self.actor)
        with mock.patch(
            "apps.subscriptions.services.enforcement.check_import_row_budget",
            side_effect=UsageLimitExceeded("over"),
        ):
            with self.assertRaises(UsageLimitExceeded):
                import_service.run_execution(job, actor=self.actor)
        self.assertFalse(Product.objects.filter(store=self.store, sku__startswith="AON-").exists())
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.PREVIEW_READY)  # untouched, still retryable

    def test_product_creation_budget_blocks_the_whole_file(self):
        job = self._job(PRODUCT_HEADER + _product_rows(4))
        with mock.patch(
            "apps.subscriptions.services.enforcement.product_creation_budget", return_value=2,
        ):
            import_service.run_preview(job, actor=self.actor)
            job.refresh_from_db()
            self.assertTrue(job.error_summary)
            self.assertTrue(import_service.job_execution_blockers(job))
            with self.assertRaises(Blocked) as ctx:
                import_service.run_execution(job, actor=self.actor)
        self.assertIn("پلن", str(ctx.exception))
        self.assertFalse(Product.objects.filter(store=self.store, sku__startswith="AON-").exists())

    def test_empty_file_cannot_be_executed(self):
        job = self._job(PRODUCT_HEADER)
        import_service.run_preview(job, actor=self.actor)
        job.refresh_from_db()
        self.assertTrue(import_service.job_execution_blockers(job))
        with self.assertRaises(Blocked):
            import_service.run_execution(job, actor=self.actor)


class PreviewRequiredServiceTests(ProductImportTestCase):
    """An ``uploaded`` job (no completed preview) is never executable."""

    def _uploaded(self, count=3, **kwargs):
        # ``_job`` previews for convenience; build the raw UPLOADED job explicitly.
        from apps.dashboard.tests.test_import_product import _csv_upload

        return import_service.create_import_job(
            self.store, import_type=ImportJob.ImportType.PRODUCTS,
            uploaded_file=_csv_upload(PRODUCT_HEADER + _product_rows(count)),
            mode=ImportJob.Mode.CREATE_ONLY, requested_by=self.actor, **kwargs,
        )

    def test_uploaded_job_is_refused_with_zero_changes(self):
        from apps.subscriptions import entitlements as ekeys
        from apps.subscriptions.services import usage_service

        job = self._uploaded()
        self.assertEqual(job.status, ImportJob.Status.UPLOADED)
        with self.assertRaises(import_service.ImportServiceError) as ctx:
            import_service.run_execution(job, actor=self.actor)
        self.assertNotIsInstance(ctx.exception, Blocked)
        self.assertIn("پیش‌نمایش", str(ctx.exception))
        self.assertFalse(Product.objects.filter(store=self.store, sku__startswith="AON-").exists())
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.UPLOADED)  # untouched
        self.assertFalse(ImportRowResult.objects.filter(import_job=job).exists())
        self.assertEqual(usage_service.get_period_usage(self.store, ekeys.CATALOG_IMPORT_ROWS_MONTHLY), 0)
        actions = _actions(self.store)
        self.assertNotIn("import.execution_started", actions)
        self.assertNotIn("import.execution_completed", actions)

    def test_uploaded_job_stays_refused_even_when_the_file_is_perfectly_valid_and_repeated(self):
        job = self._uploaded(5)
        for _ in range(3):
            with self.assertRaises(import_service.ImportServiceError):
                import_service.run_execution(job, actor=self.actor)
        self.assertFalse(Product.objects.filter(store=self.store, sku__startswith="AON-").exists())

    def test_after_a_completed_preview_the_same_job_executes(self):
        job = self._uploaded(3)
        with self.assertRaises(import_service.ImportServiceError):
            import_service.run_execution(job, actor=self.actor)
        import_service.run_preview(job, actor=self.actor)
        self.assertEqual(job.status, ImportJob.Status.PREVIEW_READY)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.COMPLETED)
        self.assertEqual(Product.objects.filter(store=self.store, sku__startswith="AON-").count(), 3)

    def test_failed_cancelled_and_validating_jobs_are_not_executable_either(self):
        for status in (ImportJob.Status.FAILED, ImportJob.Status.CANCELLED, ImportJob.Status.VALIDATING):
            with self.subTest(status=status):
                job = self._uploaded(2)
                ImportJob.objects.filter(pk=job.pk).update(status=status)
                job.refresh_from_db()
                with self.assertRaises(import_service.ImportServiceError):
                    import_service.run_execution(job, actor=self.actor)
                self.assertFalse(Product.objects.filter(store=self.store, sku__startswith="AON-").exists())

    def test_claim_requires_preview_ready_even_if_the_in_memory_job_is_stale(self):
        # The caller holds a stale object that still says preview_ready while the row was
        # reset to uploaded in the database: the compare-and-set claim must still refuse.
        job = self._uploaded(2)
        import_service.run_preview(job, actor=self.actor)
        ImportJob.objects.filter(pk=job.pk).update(status=ImportJob.Status.UPLOADED)
        self.assertEqual(job.status, ImportJob.Status.PREVIEW_READY)  # stale
        with self.assertRaises(import_service.ImportServiceError):
            import_service.run_execution(job, actor=self.actor)
        self.assertFalse(Product.objects.filter(store=self.store, sku__startswith="AON-").exists())

    def test_blockers_report_non_preview_states_as_not_executable(self):
        job = self._uploaded(1)
        self.assertTrue(import_service.job_execution_blockers(job))


class AllOrNothingProductTests(ProductImportTestCase):
    def test_runtime_failure_on_a_later_row_rolls_back_earlier_rows_across_batches(self):
        job = self._job(PRODUCT_HEADER + _product_rows(6), mode=ImportJob.Mode.CREATE_ONLY)
        real = import_service._apply_product_row
        calls = {"n": 0}

        def flaky(**kwargs):
            calls["n"] += 1
            if calls["n"] == 5:  # 3rd batch (batch_size=2): rows 1-4 are already written
                raise RuntimeError("disk on fire")
            return real(**kwargs)

        with mock.patch(f"{SERVICE}._apply_product_row", side_effect=flaky):
            import_service.run_execution(job, actor=self.actor, batch_size=2)

        self.assertGreaterEqual(calls["n"], 5)
        self.assertFalse(Product.objects.filter(store=self.store, sku__startswith="AON-").exists())
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.FAILED)
        self.assertEqual((job.created_rows, job.updated_rows), (0, 0))
        self.assertEqual(job.failed_rows, 1)
        self.assertIn("هیچ تغییری روی فروشگاه اعمال نشد", job.error_summary)
        self.assertIn("ردیف 5", job.error_summary)
        self.assertIn("disk on fire", job.error_summary)
        # failure details persisted *outside* the rolled-back transaction
        failed = ImportRowResult.objects.get(import_job=job, status=ImportRowResult.RowStatus.FAILED)
        self.assertEqual(failed.row_number, 5)
        self.assertIn("disk on fire", " ".join(failed.errors))
        others = ImportRowResult.objects.filter(import_job=job).exclude(pk=failed.pk)
        self.assertEqual(others.count(), 5)
        self.assertEqual(set(others.values_list("status", flat=True)), {"valid"})
        self.assertTrue(all("کلِ ورودِ اطلاعات بازگردانده شد" in " ".join(r.warnings) for r in others))
        self.assertTrue(job.error_report_file)

    def test_rollback_is_audited_truthfully(self):
        job = self._job(PRODUCT_HEADER + _product_rows(3), mode=ImportJob.Mode.CREATE_ONLY)
        with mock.patch(f"{SERVICE}._apply_product_row", side_effect=RuntimeError("boom")):
            import_service.run_execution(job, actor=self.actor)
        actions = _actions(self.store)
        self.assertIn("import.execution_started", actions)
        self.assertIn("import.execution_rolled_back", actions)
        self.assertNotIn("import.execution_completed", actions)
        self.assertNotIn("import.execution_rejected", actions)
        entry = AuditLogEntry.objects.get(store=self.store, action_code="import.execution_rolled_back")
        self.assertEqual(entry.result, AuditLogEntry.ResultStatus.FAILURE)

    def test_apply_time_validation_error_rolls_back_and_returns_a_fresh_preview(self):
        # Rows validate clean up-front; a concurrent change lands between the
        # revalidation pass and the mutation phase (simulated by invalidating row 3 only
        # when the apply pass reaches it).
        job = self._job(PRODUCT_HEADER + _product_rows(4), mode=ImportJob.Mode.CREATE_ONLY)
        real = import_service._validate_product_row
        state = {"apply_phase": False}

        def validate(row_number, row, **kwargs):
            outcome, normalized, existing = real(row_number, row, **kwargs)
            if state["apply_phase"] and row_number == 3:
                outcome.status = ImportRowResult.RowStatus.INVALID
                outcome.errors.append("changed meanwhile")
                return outcome, None, None
            return outcome, normalized, existing

        real_apply = import_service._apply_all

        def apply_all(*args, **kwargs):
            state["apply_phase"] = True
            try:
                return real_apply(*args, **kwargs)
            finally:
                state["apply_phase"] = False

        with mock.patch(f"{SERVICE}._validate_product_row", side_effect=validate), \
                mock.patch(f"{SERVICE}._apply_all", side_effect=apply_all):
            with self.assertRaises(Blocked) as ctx:
                import_service.run_execution(job, actor=self.actor, batch_size=2)
        self.assertIn("هم‌زمان", str(ctx.exception))
        self.assertFalse(Product.objects.filter(store=self.store, sku__startswith="AON-").exists())
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.PREVIEW_READY)

    def test_quota_consumption_failure_rolls_back_the_whole_import(self):
        job = self._job(PRODUCT_HEADER + _product_rows(3), mode=ImportJob.Mode.CREATE_ONLY)
        with mock.patch(
            "apps.subscriptions.services.enforcement.consume_import_rows", side_effect=RuntimeError("usage db down"),
        ):
            import_service.run_execution(job, actor=self.actor)
        self.assertFalse(Product.objects.filter(store=self.store, sku__startswith="AON-").exists())
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.FAILED)
        self.assertIn("هیچ تغییری روی فروشگاه اعمال نشد", job.error_summary)

    def test_successful_all_valid_import_is_applied_completely(self):
        job = self._job(PRODUCT_HEADER + _product_rows(7), mode=ImportJob.Mode.CREATE_ONLY)
        import_service.run_execution(job, actor=self.actor, batch_size=3)
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.COMPLETED)
        self.assertEqual((job.total_rows, job.created_rows, job.failed_rows, job.invalid_rows), (7, 7, 0, 0))
        self.assertEqual(Product.objects.filter(store=self.store, sku__startswith="AON-").count(), 7)
        self.assertEqual(job.error_summary, "")
        actions = _actions(self.store)
        self.assertIn("import.execution_completed", actions)
        self.assertNotIn("import.execution_rolled_back", actions)

    def test_completed_job_cannot_be_replayed(self):
        from apps.subscriptions.services import usage_service
        from apps.subscriptions import entitlements as ekeys

        job = self._job(PRODUCT_HEADER + _product_rows(2), mode=ImportJob.Mode.CREATE_ONLY)
        import_service.run_execution(job, actor=self.actor)
        consumed = usage_service.get_period_usage(self.store, ekeys.CATALOG_IMPORT_ROWS_MONTHLY)
        job.refresh_from_db()
        for _ in range(2):
            with self.assertRaises(import_service.ImportServiceError):
                import_service.run_execution(job, actor=self.actor)
        self.assertEqual(Product.objects.filter(store=self.store, sku__startswith="AON-").count(), 2)
        self.assertEqual(usage_service.get_period_usage(self.store, ekeys.CATALOG_IMPORT_ROWS_MONTHLY), consumed)

    def test_rolled_back_job_is_final_and_cannot_be_replayed(self):
        job = self._job(PRODUCT_HEADER + _product_rows(2), mode=ImportJob.Mode.CREATE_ONLY)
        with mock.patch(f"{SERVICE}._apply_product_row", side_effect=RuntimeError("boom")):
            import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        with self.assertRaises(import_service.ImportServiceError):
            import_service.run_execution(job, actor=self.actor)
        self.assertFalse(Product.objects.filter(store=self.store, sku__startswith="AON-").exists())

    def test_job_already_being_processed_cannot_be_started_again(self):
        job = self._job(PRODUCT_HEADER + _product_rows(2), mode=ImportJob.Mode.CREATE_ONLY)
        ImportJob.objects.filter(pk=job.pk).update(status=ImportJob.Status.PROCESSING)
        job.refresh_from_db()
        with self.assertRaises(import_service.ImportServiceError):
            import_service.run_execution(job, actor=self.actor)
        self.assertFalse(Product.objects.filter(store=self.store, sku__startswith="AON-").exists())

    def test_unexpected_error_before_mutation_leaves_job_retryable(self):
        job = self._job(PRODUCT_HEADER + _product_rows(2), mode=ImportJob.Mode.CREATE_ONLY)
        import_service.run_preview(job, actor=self.actor)
        with mock.patch(f"{SERVICE}._validate_all", side_effect=RuntimeError("db hiccup")):
            with self.assertRaises(RuntimeError):
                import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.PREVIEW_READY)  # not stuck in "processing"
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.COMPLETED)

    def test_warnings_without_errors_do_not_block_execution(self):
        # Documented warning policy: warnings are shown but never block.
        headers = ["SKU", "نام کالا *", "وضعیت", "برند", "دسته‌بندی *", "قیمت (تومان) *", "موجودی", "ستونِ ناشناخته"]
        rows = [["AON-W1", "کالا با هشدار", "فعال", "", "دسته > زیردسته", 1000, 1, "x"]]
        job = import_service.create_import_job(
            self.store, import_type=ImportJob.ImportType.PRODUCTS,
            uploaded_file=xlsx_upload(headers, rows, name="warn.xlsx"),
            mode=ImportJob.Mode.CREATE_ONLY, requested_by=self.actor,
        )
        import_service.run_preview(job, actor=self.actor)
        summary = import_service.job_preview_summary(job)
        self.assertEqual((summary["invalid"], summary["warnings"], summary["blockers"]), (0, 1, []))
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.COMPLETED)
        self.assertTrue(Product.objects.filter(store=self.store, sku="AON-W1").exists())


class AllOrNothingInventoryTests(InventoryImportTestCase):
    def setUp(self):
        super().setUp()
        self.second = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالای دوم",
            slug="prod-iimp-2", sku="SKU-IIMP-2", price=Decimal("1"), stock=0,
        )

    def _csv(self, *quantities):
        return INV_HEADER + "".join(
            f"{self.warehouse.code},,{sku},,,adjustment,{qty},,\n" for sku, qty in quantities
        )

    def test_runtime_failure_rolls_back_stock_movements_and_aggregate_stock(self):
        movements_before = StockMovement.objects.filter(store=self.store).count()
        job = self._job(self._csv(("SKU-IIMP-1", 10), ("SKU-IIMP-2", 20), ("SKU-IIMP-1", 5)))
        real = import_service.adjust_warehouse_stock
        calls = {"n": 0}

        def flaky(**kwargs):
            calls["n"] += 1
            if calls["n"] == 3:
                raise RuntimeError("ledger offline")
            return real(**kwargs)

        with mock.patch(f"{SERVICE}.adjust_warehouse_stock", side_effect=flaky):
            import_service.run_execution(job, actor=self.actor, batch_size=1)
        self.assertEqual(calls["n"], 3)  # two rows really wrote before the failure
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.FAILED)
        self.assertEqual(job.updated_rows, 0)
        self.assertEqual(StockMovement.objects.filter(store=self.store).count(), movements_before)
        for product in (self.product, self.second):
            product.refresh_from_db()
            self.assertEqual(product.stock, 0)
        self.assertFalse(
            WarehouseInventory.objects.filter(store=self.store, product__in=[self.product, self.second])
            .exclude(on_hand=0).exists()
        )

    def test_reservation_conflict_rolls_back_the_valid_rows_too(self):
        import_service.run_execution(self._job(self._csv(("SKU-IIMP-1", 10))), actor=self.actor)
        InventoryReservation.objects.create(
            store=self.store, product=self.product, variant=None, quantity=8,
            status=InventoryReservation.Status.ACTIVE,
        )
        movements = StockMovement.objects.filter(store=self.store).count()
        job = self._job(self._csv(("SKU-IIMP-2", 7), ("SKU-IIMP-1", -5)))  # 2nd would dip below the reservation
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.FAILED)
        self.assertEqual(job.updated_rows, 0)
        self.assertEqual(StockMovement.objects.filter(store=self.store).count(), movements)
        self.product.refresh_from_db()
        self.second.refresh_from_db()
        self.assertEqual((self.product.stock, self.second.stock), (10, 0))
        self.assertTrue(ImportRowResult.objects.filter(import_job=job, status="failed").exists())

    def test_all_valid_inventory_import_still_works(self):
        job = self._job(self._csv(("SKU-IIMP-1", 10), ("SKU-IIMP-2", 20)))
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual((job.status, job.updated_rows), (ImportJob.Status.COMPLETED, 2))
        self.product.refresh_from_db()
        self.second.refresh_from_db()
        self.assertEqual((self.product.stock, self.second.stock), (10, 20))
        self.assertEqual(StockMovement.objects.filter(store=self.store, reason="import_adjustment").count(), 2)

    def test_unknown_product_row_blocks_every_row(self):
        job = self._job(self._csv(("SKU-IIMP-1", 10), ("SKU-NOPE", 20)))
        with self.assertRaises(Blocked):
            import_service.run_execution(job, actor=self.actor)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 0)
        self.assertFalse(StockMovement.objects.filter(store=self.store).exists())


class AllOrNothingVariantTests(VariantImportTestCase):
    def _csv(self, *rows):
        return VARIANT_HEADER + "".join(rows)

    def test_one_bad_variant_row_blocks_all_variants(self):
        good = ",SKU-VIMP-1,,VAR-RED,,رنگ,قرمز,,,15000,,,5,,,\n"
        bad = ",SKU-VIMP-1,,VAR-GREEN,,رنگ,سبز,,,1000,,,1,,,\n"
        job = self._job(self._csv(good, bad), mode=ImportJob.Mode.CREATE_ONLY)
        with self.assertRaises(Blocked):
            import_service.run_execution(job, actor=self.actor)
        self.assertEqual(self.product.variants.count(), 0)
        self.assertFalse(StockMovement.objects.filter(store=self.store, product=self.product).exists())

    def test_runtime_failure_rolls_back_variants_and_their_stock(self):
        rows = (
            ",SKU-VIMP-1,,VAR-RED,,رنگ,قرمز,,,15000,,,5,,,\n",
            ",SKU-VIMP-1,,VAR-BLUE,,رنگ,آبی,,,16000,,,6,,,\n",
        )
        job = self._job(self._csv(*rows), mode=ImportJob.Mode.CREATE_ONLY)
        real = import_service._apply_variant_row
        calls = {"n": 0}

        def flaky(**kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("variant write failed")
            return real(**kwargs)

        with mock.patch(f"{SERVICE}._apply_variant_row", side_effect=flaky):
            import_service.run_execution(job, actor=self.actor, batch_size=1)
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.FAILED)
        self.assertEqual(self.product.variants.count(), 0)
        self.assertFalse(ProductVariant.objects.filter(sku__in=["VAR-RED", "VAR-BLUE"]).exists())
        self.assertFalse(StockMovement.objects.filter(store=self.store, product=self.product).exists())

    def test_all_valid_variant_import_still_works(self):
        rows = (
            ",SKU-VIMP-1,,VAR-RED,,رنگ,قرمز,,,15000,,,5,,,\n",
            ",SKU-VIMP-1,,VAR-BLUE,,رنگ,آبی,,,16000,,,6,,,\n",
        )
        job = self._job(self._csv(*rows), mode=ImportJob.Mode.CREATE_ONLY)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual((job.status, job.created_rows), (ImportJob.Status.COMPLETED, 2))
        self.assertEqual(ProductVariant.objects.filter(sku__in=["VAR-RED", "VAR-BLUE"]).count(), 2)


class StrictImportViewTests(ImportViewTestCase):
    def _upload(self, csv_text, mode="create_only"):
        self.client.post(reverse("dashboard:import-upload"), {
            "import_type": "products", "mode": mode,
            "file": SimpleUploadedFile("p.csv", csv_text.encode(), content_type="text/csv"),
        })
        return ImportJob.objects.filter(store=self.store).latest("pk")

    def _rows(self, count, prefix="SV"):
        return "".join(f",{prefix}-{i},کالا {i},,,active,brand-ivw,leaf-ivw,1000,1,,,,,\n" for i in range(count))

    def test_preview_with_an_error_offers_no_execute_button_and_says_why(self):
        job = self._upload(PRODUCT_HEADER + self._rows(3) + ",,,,,,,,,,,,,,\n")
        response = self.client.get(reverse("dashboard:import-detail", args=[job.pk]))
        html = response.content.decode()
        self.assertFalse(response.context["can_execute"])
        self.assertNotIn(reverse("dashboard:import-execute", args=[job.pk]), html)
        self.assertNotIn("تأیید اجرای واقعی", html)
        self.assertIn("این فایل قابل اجرا نیست. ابتدا همه خطاها را اصلاح و فایل را دوباره بارگذاری کنید.", html)
        self.assertNotIn("فایل با موفقیت بررسی شد", html)
        # the old partial-apply wording is gone
        for old in ("فقط ردیف‌هایِ سالم اعمال", "ردیف‌هایِ سالم", "اجرایِ بخشی"):
            self.assertNotIn(old, html)
        self.assertContains(response, "دریافتِ گزارشِ خطا")

    def test_direct_post_cannot_bypass_the_block(self):
        job = self._upload(PRODUCT_HEADER + self._rows(99) + ",,,,,,,,,,,,,,\n")
        self.assertEqual(job.valid_rows, 99)
        response = self.client.post(reverse("dashboard:import-execute", args=[job.pk]), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Product.objects.filter(store=self.store, sku__startswith="SV-").exists())
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.PREVIEW_READY)
        text = " ".join(str(m) for m in response.context["messages"])
        self.assertIn("هیچ تغییری اعمال نشد", text)

    def test_clean_preview_shows_success_copy_and_confirmation_warning(self):
        job = self._upload(PRODUCT_HEADER + self._rows(3))
        html = self.client.get(reverse("dashboard:import-detail", args=[job.pk])).content.decode()
        self.assertIn("فایل با موفقیت بررسی شد. همه ردیف‌ها معتبرند و آماده اجرا هستند.", html)
        self.assertIn("تأیید اجرای واقعی", html)
        self.assertIn("با تأیید، اطلاعاتِ فروشگاه تغییر می‌کند", html)
        self.assertNotIn("این فایل قابل اجرا نیست", html)

    def test_all_valid_file_executes_once_and_replay_is_refused(self):
        job = self._upload(PRODUCT_HEADER + self._rows(3))
        url = reverse("dashboard:import-execute", args=[job.pk])
        self.client.post(url)
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.COMPLETED)
        self.assertEqual(Product.objects.filter(store=self.store, sku__startswith="SV-").count(), 3)
        response = self.client.post(url, follow=True)
        self.assertEqual(Product.objects.filter(store=self.store, sku__startswith="SV-").count(), 3)
        self.assertIn("دوباره اجرا نمی‌شود", " ".join(str(m) for m in response.context["messages"]))
        # no execute button on a finished job
        detail = self.client.get(reverse("dashboard:import-detail", args=[job.pk]))
        self.assertFalse(detail.context["can_execute"])

    def test_store_state_change_between_preview_and_post_returns_to_a_fresh_preview(self):
        job = self._upload(PRODUCT_HEADER + self._rows(3))
        Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.leaf, name="رقیب", slug="rival",
            sku="SV-1", price=Decimal("1"), stock=0,
        )
        response = self.client.post(reverse("dashboard:import-execute", args=[job.pk]), follow=True)
        text = " ".join(str(m) for m in response.context["messages"])
        self.assertIn("از زمانِ پیش‌نمایش تغییر کرده", text)
        self.assertEqual(Product.objects.filter(store=self.store, sku__startswith="SV-").count(), 1)
        self.assertFalse(response.context["can_execute"])
        self.assertEqual(response.context["summary"]["invalid"], 1)

    def test_runtime_failure_shows_failed_result_with_reason_and_no_changes(self):
        job = self._upload(PRODUCT_HEADER + self._rows(3))
        with mock.patch(f"{SERVICE}._apply_product_row", side_effect=RuntimeError("kaboom")):
            response = self.client.post(reverse("dashboard:import-execute", args=[job.pk]), follow=True)
        self.assertFalse(Product.objects.filter(store=self.store, sku__startswith="SV-").exists())
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.FAILED)
        html = response.content.decode()
        self.assertIn("هیچ تغییری روی فروشگاه اعمال نشد", html)
        self.assertIn("kaboom", html)

    def test_warnings_are_visible_and_distinct_from_errors(self):
        headers = ["SKU", "نام کالا *", "وضعیت", "برند", "دسته‌بندی *", "قیمت (تومان) *", "موجودی", "ستونِ اضافه"]
        self.client.post(reverse("dashboard:import-upload"), {
            "import_type": "products", "mode": "create_only",
            "file": xlsx_upload(headers, [["SV-W", "کالا", "فعال", "", "دسته > زیردسته", 10, 1, "x"]], name="w.xlsx"),
        })
        job = ImportJob.objects.get(store=self.store)
        response = self.client.get(reverse("dashboard:import-detail", args=[job.pk]))
        self.assertTrue(response.context["can_execute"])
        html = response.content.decode()
        self.assertIn("فایل با موفقیت بررسی شد", html)
        self.assertIn("هشدارها مانعِ اجرا نیستند", html)
        self.assertIn('class="imp-warn"', html)
        self.assertNotIn('class="imp-err"', html)

    def test_analyst_cannot_execute_and_nothing_changes(self):
        job = self._upload(PRODUCT_HEADER + self._rows(2))
        self._login_as(StoreMembership.Role.ANALYST, "aon-analyst")
        response = self.client.post(reverse("dashboard:import-execute", args=[job.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Product.objects.filter(store=self.store, sku__startswith="SV-").exists())
        detail = self.client.get(reverse("dashboard:import-detail", args=[job.pk]))
        self.assertFalse(detail.context["can_execute"])
        self.assertNotContains(detail, reverse("dashboard:import-execute", args=[job.pk]))

    def test_other_stores_member_cannot_execute_this_job(self):
        from apps.stores.models import Store

        job = self._upload(PRODUCT_HEADER + self._rows(2))
        other = Store.objects.create(name="دیگر", slug="aon-other", admin_subdomain="aon-other")
        # the job is addressed through *another* store's resolution: it must 404
        with mock.patch("apps.dashboard.views._resolve_dashboard_store", return_value=other):
            response = self.client.post(reverse("dashboard:import-execute", args=[job.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Product.objects.filter(store=self.store, sku__startswith="SV-").exists())
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.PREVIEW_READY)

    def test_direct_post_for_an_uploaded_job_changes_nothing(self):
        # create the job through the service only: no upload view, hence no preview
        job = import_service.create_import_job(
            self.store, import_type=ImportJob.ImportType.PRODUCTS,
            uploaded_file=SimpleUploadedFile(
                "p.csv", (PRODUCT_HEADER + self._rows(3)).encode(), content_type="text/csv",
            ),
            mode=ImportJob.Mode.CREATE_ONLY, requested_by=self.owner,
        )
        self.assertEqual(job.status, ImportJob.Status.UPLOADED)
        response = self.client.post(reverse("dashboard:import-execute", args=[job.pk]), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Product.objects.filter(store=self.store, sku__startswith="SV-").exists())
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.UPLOADED)
        text = " ".join(str(m) for m in response.context["messages"])
        self.assertIn("پیش‌نمایش", text)
        self.assertFalse(response.context["can_execute"])
        self.assertNotContains(response, reverse("dashboard:import-execute", args=[job.pk]))
        # once the preview exists the very same job can be confirmed
        import_service.run_preview(job, actor=self.owner)
        self.client.post(reverse("dashboard:import-execute", args=[job.pk]))
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.COMPLETED)

    def test_terminology_in_merchant_import_pages(self):
        job = self._upload(PRODUCT_HEADER + self._rows(1))
        pages = [
            self.client.get(reverse("dashboard:import-list")),
            self.client.get(reverse("dashboard:import-upload")),
            self.client.get(reverse("dashboard:import-detail", args=[job.pk])),
        ]
        for response in pages:
            html = response.content.decode()
            self.assertIn("ورود اطلاعات", html)
            for old in ("واردات داده", "واردات داده‌ها", "صادرات داده"):
                self.assertNotIn(old, html)
