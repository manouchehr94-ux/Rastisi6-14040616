"""Tests for the checkpoint 4B Inventory Import service — every successful
row routes through inventory_service.adjust_warehouse_stock (StockMovement
created, aggregate stock kept consistent, reservation-safety enforced);
the import service never writes WarehouseInventory/Product.stock/
ProductVariant.stock directly (ADR-60)."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.catalog.models import (
    Category,
    InventoryReservation,
    Product,
    ProductVariant,
    StockMovement,
    Vendor,
    Warehouse,
    WarehouseInventory,
)
from apps.core.models import ImportJob, ImportRowResult
from apps.dashboard.services import import_service
from apps.stores.models import Store

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _csv_upload(text: str, name="inventory.csv"):
    return SimpleUploadedFile(name, text.encode("utf-8"), content_type="text/csv")


INV_HEADER = "warehouse_code,product_id,product_sku,variant_id,variant_sku,mode,quantity,reason,note\n"


class InventoryImportTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-iimp")
        self.category = Category.objects.create(store=self.store, name="دسته", slug="cat-iimp")
        self.actor = User.objects.create_user(username="iimp-owner", password="p", is_staff=True)
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالا",
            slug="prod-iimp", sku="SKU-IIMP-1", price=Decimal("100000"), stock=0,
        )
        self.warehouse = Warehouse.objects.filter(store=self.store, is_default=True).first()

    def _job(self, csv_text, *, mode=ImportJob.Mode.UPSERT, idempotency_key=""):
        job = import_service.create_import_job(
            self.store, import_type=ImportJob.ImportType.INVENTORY, uploaded_file=_csv_upload(csv_text),
            mode=mode, requested_by=self.actor, idempotency_key=idempotency_key,
        )
        # execution requires a completed preview (UPLOADED jobs are never executable)
        import_service.run_preview(job, actor=self.actor)
        return job


class AdjustmentTests(InventoryImportTestCase):
    def test_positive_adjustment_creates_stock_movement(self):
        csv_text = INV_HEADER + f"{self.warehouse.code},,SKU-IIMP-1,,,adjustment,10,شمارشِ سالانه,اتاقِ ۲\n"
        job = self._job(csv_text)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.COMPLETED)
        self.assertEqual(job.updated_rows, 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)
        movement = StockMovement.objects.get(product=self.product)
        self.assertEqual(movement.delta, 10)
        self.assertEqual(movement.warehouse, self.warehouse)
        self.assertEqual(movement.actor, self.actor)
        self.assertEqual(movement.reason, StockMovement.Reason.IMPORT_ADJUSTMENT)
        self.assertIn("شمارشِ سالانه", movement.note)

    def test_negative_adjustment(self):
        csv_text = INV_HEADER + (
            f"{self.warehouse.code},,SKU-IIMP-1,,,adjustment,20,,\n"
            f"{self.warehouse.code},,SKU-IIMP-1,,,adjustment,-5,,\n"
        )
        job = self._job(csv_text)
        import_service.run_execution(job, actor=self.actor)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 15)

    def test_persian_digit_quantity_normalized(self):
        csv_text = INV_HEADER + f"{self.warehouse.code},,SKU-IIMP-1,,,adjustment,۱۲,,\n"
        job = self._job(csv_text)
        import_service.run_execution(job, actor=self.actor)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 12)


class SetOnHandTests(InventoryImportTestCase):
    def test_set_on_hand_computes_delta(self):
        csv_text = INV_HEADER + f"{self.warehouse.code},,SKU-IIMP-1,,,set_on_hand,25,,\n"
        job = self._job(csv_text)
        import_service.run_execution(job, actor=self.actor)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 25)

    def test_negative_set_on_hand_rejected(self):
        csv_text = INV_HEADER + f"{self.warehouse.code},,SKU-IIMP-1,,,set_on_hand,-3,,\n"
        job = self._job(csv_text)
        with self.assertRaises(import_service.ImportExecutionBlocked):
            import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)

    def test_zero_delta_skipped(self):
        csv_text = INV_HEADER + f"{self.warehouse.code},,SKU-IIMP-1,,,set_on_hand,0,,\n"
        job = self._job(csv_text)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.skipped_rows, 1)


class VariantInventoryTests(InventoryImportTestCase):
    def setUp(self):
        super().setUp()
        self.variant = ProductVariant.objects.create(
            product=self.product, store=self.store, attribute="رنگ", value="قرمز",
            sku="VAR-IIMP-1", stock=0,
        )

    def test_variant_inventory_adjustment(self):
        csv_text = INV_HEADER + f"{self.warehouse.code},,SKU-IIMP-1,,VAR-IIMP-1,adjustment,6,,\n"
        job = self._job(csv_text)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.updated_rows, 1)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 6)
        movement = StockMovement.objects.get(variant=self.variant)
        self.assertEqual(movement.delta, 6)

    def test_variant_belonging_to_other_product_rejected(self):
        other_product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="دیگر",
            slug="other-iimp", sku="SKU-IIMP-2", price=Decimal("1"), stock=0,
        )
        csv_text = INV_HEADER + f"{self.warehouse.code},,SKU-IIMP-2,,VAR-IIMP-1,adjustment,1,,\n"
        job = self._job(csv_text)
        with self.assertRaises(import_service.ImportExecutionBlocked):
            import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)


class ReservationSafetyTests(InventoryImportTestCase):
    def setUp(self):
        super().setUp()
        # Seed 10 on-hand via an import, then reserve 7.
        csv_text = INV_HEADER + f"{self.warehouse.code},,SKU-IIMP-1,,,set_on_hand,10,,\n"
        job = self._job(csv_text)
        import_service.run_execution(job, actor=self.actor)
        InventoryReservation.objects.create(
            store=self.store, product=self.product, variant=None, quantity=7,
            status=InventoryReservation.Status.ACTIVE,
        )

    def test_reduction_below_active_reservation_rejected(self):
        csv_text = INV_HEADER + f"{self.warehouse.code},,SKU-IIMP-1,,,adjustment,-5,,\n"
        job = self._job(csv_text)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.failed_rows, 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)

    def test_set_on_hand_below_reservation_rejected(self):
        csv_text = INV_HEADER + f"{self.warehouse.code},,SKU-IIMP-1,,,set_on_hand,3,,\n"
        job = self._job(csv_text)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.failed_rows, 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)

    def test_reduction_to_exactly_reserved_allowed(self):
        csv_text = INV_HEADER + f"{self.warehouse.code},,SKU-IIMP-1,,,set_on_hand,7,,\n"
        job = self._job(csv_text)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.updated_rows, 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 7)


class ValidationTests(InventoryImportTestCase):
    def test_missing_warehouse_rejected(self):
        csv_text = INV_HEADER + ",,SKU-IIMP-1,,,adjustment,5,,\n"
        job = self._job(csv_text)
        with self.assertRaises(import_service.ImportExecutionBlocked):
            import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)

    def test_unknown_warehouse_rejected(self):
        csv_text = INV_HEADER + "no-such-wh,,SKU-IIMP-1,,,adjustment,5,,\n"
        job = self._job(csv_text)
        with self.assertRaises(import_service.ImportExecutionBlocked):
            import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)

    def test_missing_product_rejected(self):
        csv_text = INV_HEADER + f"{self.warehouse.code},,,,,adjustment,5,,\n"
        job = self._job(csv_text)
        with self.assertRaises(import_service.ImportExecutionBlocked):
            import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)

    def test_invalid_mode_rejected(self):
        csv_text = INV_HEADER + f"{self.warehouse.code},,SKU-IIMP-1,,,teleport,5,,\n"
        job = self._job(csv_text)
        with self.assertRaises(import_service.ImportExecutionBlocked):
            import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)

    def test_non_numeric_quantity_rejected(self):
        csv_text = INV_HEADER + f"{self.warehouse.code},,SKU-IIMP-1,,,adjustment,abc,,\n"
        job = self._job(csv_text)
        with self.assertRaises(import_service.ImportExecutionBlocked):
            import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)

    def test_dry_run_does_not_change_stock(self):
        csv_text = INV_HEADER + f"{self.warehouse.code},,SKU-IIMP-1,,,adjustment,5,,\n"
        job = self._job(csv_text)
        import_service.run_preview(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.PREVIEW_READY)
        self.assertEqual(job.valid_rows, 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 0)
        self.assertFalse(StockMovement.objects.filter(product=self.product).exists())


class ReplayTests(InventoryImportTestCase):
    def test_completed_job_cannot_replay(self):
        csv_text = INV_HEADER + f"{self.warehouse.code},,SKU-IIMP-1,,,adjustment,5,,\n"
        job = self._job(csv_text)
        import_service.run_execution(job, actor=self.actor)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 5)
        with self.assertRaises(import_service.ImportServiceError):
            import_service.run_execution(job, actor=self.actor)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 5)  # not applied twice


class TenantIsolationTests(InventoryImportTestCase):
    def setUp(self):
        super().setUp()
        self.other_store = Store.objects.create(name="فروشگاه دیگر", slug="iimp-other-store")
        self.foreign_warehouse = Warehouse.objects.create(store=self.other_store, name="خارجی", code="foreign-wh-iimp")
        other_vendor = Vendor.objects.create(store=self.other_store, name="ف", slug="v-other-iimp")
        other_category = Category.objects.create(store=self.other_store, name="د", slug="c-other-iimp")
        self.foreign_product = Product.objects.create(
            store=self.other_store, vendor=other_vendor, category=other_category, name="خارجی",
            slug="foreign-prod-iimp", sku="SKU-FOREIGN-IIMP", price=Decimal("1"), stock=0,
        )

    def test_foreign_warehouse_rejected(self):
        csv_text = INV_HEADER + f"foreign-wh-iimp,,SKU-IIMP-1,,,adjustment,5,,\n"
        job = self._job(csv_text)
        with self.assertRaises(import_service.ImportExecutionBlocked):
            import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)

    def test_foreign_product_id_rejected(self):
        csv_text = INV_HEADER + f"{self.warehouse.code},{self.foreign_product.pk},,,,adjustment,5,,\n"
        job = self._job(csv_text)
        with self.assertRaises(import_service.ImportExecutionBlocked):
            import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)
        self.foreign_product.refresh_from_db()
        self.assertEqual(self.foreign_product.stock, 0)


# ============================================================ XLSX (primary format)

from apps.catalog.models import Warehouse as _Warehouse  # noqa: E402
from apps.dashboard.services import import_xlsx  # noqa: E402
from apps.dashboard.tests.xlsx_helpers import xlsx_upload  # noqa: E402

XLSX_INV_HEADERS = [
    "انبار *", "شناسه کالا", "SKU کالا", "شناسه تنوع", "SKU تنوع", "نوع عملیات *", "مقدار *", "دلیل", "توضیح",
]
OP_SET = "تنظیم موجودی نهایی"
OP_ADJUST = "افزایش/کاهش موجودی"


class XlsxInventoryImportTests(InventoryImportTestCase):
    def _xjob(self, rows, *, headers=None):
        job = import_service.create_import_job(
            self.store, import_type=ImportJob.ImportType.INVENTORY,
            uploaded_file=xlsx_upload(headers or XLSX_INV_HEADERS, rows, name="inventory.xlsx"),
            mode=ImportJob.Mode.UPSERT, requested_by=self.actor,
        )
        # execution requires a completed preview (UPLOADED jobs are never executable)
        import_service.run_preview(job, actor=self.actor)
        return job

    def _row(self, op, qty, *, sku="SKU-IIMP-1", warehouse=None, reason="شمارش", note=""):
        return [warehouse or self.warehouse.name, None, sku, None, None, op, qty, reason, note]

    def test_set_final_inventory_vs_increase_decrease(self):
        # set → exactly the entered number
        job = self._xjob([self._row(OP_SET, 10)])
        import_service.run_preview(job, actor=self.actor)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 0, "preview must not change stock")
        self.assertEqual(job.row_results.get().normalized_data_summary, {"action": "update"})
        import_service.run_execution(job, actor=self.actor)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)
        # adjust +5 → 15, adjust -3 → 12 (negative decreases)
        job = self._xjob([self._row(OP_ADJUST, 5), self._row(OP_ADJUST, -3)])
        import_service.run_execution(job, actor=self.actor)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 12)
        # set again → exactly 4, regardless of the current 12
        import_service.run_execution(self._xjob([self._row(OP_SET, 4)]), actor=self.actor)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 4)

    def test_persian_digits_negative_numbers_and_warehouse_name(self):
        import_service.run_execution(self._xjob([self._row(OP_SET, "۲۰")]), actor=self.actor)
        job = self._xjob([self._row(OP_ADJUST, "-۵")])
        import_service.run_execution(job, actor=self.actor)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 15)
        movement = StockMovement.objects.filter(product=self.product).order_by("-pk").first()
        self.assertEqual(movement.delta, -5)
        self.assertEqual(movement.reason, StockMovement.Reason.IMPORT_ADJUSTMENT)
        self.assertIn("شمارش", movement.note)

    def test_operation_must_be_chosen_explicitly(self):
        job = self._xjob([self._row("", 5)])
        import_service.run_preview(job, actor=self.actor)
        result = job.row_results.get()
        self.assertEqual(result.status, "invalid")
        shown = import_xlsx.describe_errors("inventory", result.errors)
        self.assertIn("نوعِ عملیات", shown[0]["message"])

    def test_operation_synonyms_and_internal_codes_are_understood(self):
        rows = [self._row("set_on_hand", 6), self._row("تنظیم موجودی", 7), self._row("adjustment", 1), self._row("افزایش/کاهش", 1)]
        job = self._xjob(rows)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.failed_rows + job.invalid_rows, 0, list(job.row_results.values_list("errors", flat=True)))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 9)

    def test_unknown_operation_and_warehouse_use_merchant_wording(self):
        job = self._xjob([self._row("چیز دیگر", 1), self._row(OP_SET, 1, warehouse="انبار ناموجود")])
        import_service.run_preview(job, actor=self.actor)
        first, second = job.row_results.order_by("row_number")
        self.assertEqual((first.row_number, second.row_number), (2, 3))
        d1 = import_xlsx.describe_errors("inventory", first.errors)[0]
        d2 = import_xlsx.describe_errors("inventory", second.errors)[0]
        self.assertEqual(d1["column"], "نوع عملیات")
        self.assertIn("تنظیم موجودی نهایی", d1["message"])
        self.assertNotIn("set_on_hand", d1["message"])
        self.assertEqual(d2["column"], "انبار")
        self.assertNotIn("warehouse_code", d2["message"])

    def test_negative_final_inventory_is_rejected_with_merchant_wording(self):
        job = self._xjob([self._row(OP_SET, -2)])
        import_service.run_preview(job, actor=self.actor)
        detail = import_xlsx.describe_errors("inventory", job.row_results.get().errors)[0]
        self.assertIn("تنظیم موجودی نهایی", detail["message"])
        self.assertEqual(detail["column"], "مقدار")

    def test_reservation_safety_still_applies_to_xlsx_rows(self):
        import_service.run_execution(self._xjob([self._row(OP_SET, 10)]), actor=self.actor)
        InventoryReservation.objects.create(
            store=self.store, product=self.product, variant=None, quantity=7,
            status=InventoryReservation.Status.ACTIVE,
        )
        movements_before = StockMovement.objects.filter(store=self.store).count()
        job = self._xjob([self._row(OP_ADJUST, -5), self._row(OP_SET, 3), self._row(OP_SET, 7)])
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        # reservation safety is enforced at apply time: the offending rows fail and,
        # because import is all-or-nothing, the valid row (set to 7) is rolled back too.
        self.assertEqual(job.status, ImportJob.Status.FAILED)
        self.assertGreaterEqual(job.failed_rows, 1)
        self.assertEqual(job.updated_rows, 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)
        self.assertEqual(StockMovement.objects.filter(store=self.store).count(), movements_before)

    def test_duplicate_warehouse_names_are_ambiguous(self):
        _Warehouse.objects.create(store=self.store, name=self.warehouse.name, code="dup-wh-xl")
        job = self._xjob([self._row(OP_SET, 1)])
        import_service.run_preview(job, actor=self.actor)
        self.assertIn("مبهم", " ".join(job.row_results.get().errors))

    def test_other_stores_warehouse_is_not_resolvable(self):
        other = Store.objects.create(name="دیگر", slug="xl-inv-other")
        _Warehouse.objects.create(store=other, name="انبارِ بیگانه", code="foreign-wh-xl")
        job = self._xjob([self._row(OP_SET, 1, warehouse="انبارِ بیگانه")])
        import_service.run_preview(job, actor=self.actor)
        self.assertEqual(job.row_results.get().status, "invalid")

    def test_formula_in_quantity_is_rejected(self):
        job = self._xjob([self._row(OP_SET, "=5+5")])
        with self.assertRaises(import_service.ImportExecutionBlocked):
            import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 0)
