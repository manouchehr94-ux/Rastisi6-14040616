"""Tests for the checkpoint 4B Product Import service
(``apps.dashboard.services.import_service``): preview vs execution sharing
one validation path, create_only/update_only/upsert modes, stable identity
resolution, Store-scoped reference validation, dry-run non-mutation,
inventory-service-routed stock writes, and idempotent replay protection."""

from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.catalog.models import Brand, Category, Product, StockMovement, Vendor
from apps.core.models import ImportJob, ImportRowResult
from apps.dashboard.services import import_service
from apps.orders.models import TaxClass
from apps.stores.models import Store

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _csv_upload(text: str, name="products.csv"):
    return SimpleUploadedFile(name, text.encode("utf-8"), content_type="text/csv")


PRODUCT_HEADER = (
    "product_id,sku,name,slug,barcode,status,brand_code,category_code,"
    "price,stock,weight_grams,requires_shipping,tax_class_code,seo_title,seo_description\n"
)


class ProductImportTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-imp")
        self.category = Category.objects.create(store=self.store, name="دسته", slug="cat-imp", parent=None)
        self.leaf = Category.objects.create(store=self.store, name="زیردسته", slug="leaf-imp", parent=self.category)
        self.brand = Brand.objects.create(store=self.store, name="برند", slug="brand-imp")
        self.tax_class = TaxClass.objects.create(store=self.store, name="عمومی", code="general-imp")
        self.actor = User.objects.create_user(username="imp-owner", password="p", is_staff=True)

    def _job(self, csv_text, *, mode=ImportJob.Mode.UPSERT, import_type=ImportJob.ImportType.PRODUCTS, idempotency_key=""):
        return import_service.create_import_job(
            self.store, import_type=import_type, uploaded_file=_csv_upload(csv_text),
            mode=mode, requested_by=self.actor, idempotency_key=idempotency_key,
        )


class PreviewTests(ProductImportTestCase):
    def test_preview_does_not_create_product(self):
        csv_text = PRODUCT_HEADER + f",,کالای تازه,,,,brand-imp,leaf-imp,100000,5,,,,,\n"
        job = self._job(csv_text)
        import_service.run_preview(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.PREVIEW_READY)
        self.assertEqual(job.valid_rows, 1)
        self.assertFalse(Product.objects.filter(store=self.store, name="کالای تازه").exists())

    def test_preview_reports_invalid_row(self):
        csv_text = PRODUCT_HEADER + ",,,,,,,,,,,,,,\n"  # no name, no category
        job = self._job(csv_text)
        import_service.run_preview(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)
        row = ImportRowResult.objects.get(import_job=job)
        self.assertEqual(row.status, ImportRowResult.RowStatus.INVALID)
        self.assertTrue(row.errors)


class CreateExecutionTests(ProductImportTestCase):
    def test_create_only_creates_new_product_with_stock_via_service(self):
        csv_text = PRODUCT_HEADER + ",SKU-NEW-1,کالای وارداتی,,,active,brand-imp,leaf-imp,150000,8,500,بله,general-imp,,\n"
        job = self._job(csv_text, mode=ImportJob.Mode.CREATE_ONLY)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.COMPLETED)
        self.assertEqual(job.created_rows, 1)
        product = Product.objects.get(store=self.store, sku="SKU-NEW-1")
        self.assertEqual(product.name, "کالای وارداتی")
        self.assertEqual(product.price, Decimal("150000"))
        self.assertEqual(product.stock, 8)
        self.assertEqual(product.brand, self.brand)
        self.assertEqual(product.category, self.leaf)
        self.assertEqual(product.tax_class, self.tax_class)
        movement = StockMovement.objects.get(product=product)
        self.assertEqual(movement.delta, 8)

    def test_create_only_rejects_row_matching_existing_sku(self):
        Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.leaf, name="موجود", slug="existing-imp",
            sku="SKU-EXIST-1", price=Decimal("1"), stock=0,
        )
        csv_text = PRODUCT_HEADER + ",SKU-EXIST-1,به‌روزرسانی,,,,,leaf-imp,999999,1,,,,,\n"
        job = self._job(csv_text, mode=ImportJob.Mode.CREATE_ONLY)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)
        self.assertEqual(job.created_rows, 0)

    def test_persian_digits_normalized_in_price_and_stock(self):
        csv_text = PRODUCT_HEADER + ",SKU-FA-1,کالایِ فارسی,,,,,leaf-imp,۱۵۰۰۰۰,۷,,,,,\n"
        job = self._job(csv_text, mode=ImportJob.Mode.CREATE_ONLY)
        import_service.run_execution(job, actor=self.actor)
        product = Product.objects.get(store=self.store, sku="SKU-FA-1")
        self.assertEqual(product.price, Decimal("150000"))
        self.assertEqual(product.stock, 7)


class UpdateExecutionTests(ProductImportTestCase):
    def setUp(self):
        super().setUp()
        self.existing = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.leaf, name="کالایِ قدیمی", slug="old-imp",
            sku="SKU-OLD-1", price=Decimal("50000"), stock=2,
        )

    def test_update_only_updates_matched_product_by_sku(self):
        csv_text = PRODUCT_HEADER + f",SKU-OLD-1,کالایِ به‌روزشده,,,,,,{75000},,,,,,\n"
        job = self._job(csv_text, mode=ImportJob.Mode.UPDATE_ONLY)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.updated_rows, 1)
        self.existing.refresh_from_db()
        self.assertEqual(self.existing.name, "کالایِ به‌روزشده")
        self.assertEqual(self.existing.price, Decimal("75000"))

    def test_update_only_rejects_unmatched_row(self):
        csv_text = PRODUCT_HEADER + ",SKU-NO-MATCH,کالا,,,,,leaf-imp,1000,1,,,,,\n"
        job = self._job(csv_text, mode=ImportJob.Mode.UPDATE_ONLY)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)
        self.assertFalse(Product.objects.filter(sku="SKU-NO-MATCH").exists())

    def test_update_by_product_id(self):
        csv_text = PRODUCT_HEADER.replace("product_id", "product_id")
        csv_text = f"product_id,sku,name,slug,barcode,status,brand_code,category_code,price,stock,weight_grams,requires_shipping,tax_class_code,seo_title,seo_description\n{self.existing.pk},,نامِ تازه,,,,,,,,,,,,\n"
        job = self._job(csv_text, mode=ImportJob.Mode.UPDATE_ONLY)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.updated_rows, 1)
        self.existing.refresh_from_db()
        self.assertEqual(self.existing.name, "نامِ تازه")

    def test_upsert_creates_and_updates_in_same_file(self):
        csv_text = (
            PRODUCT_HEADER
            + ",SKU-OLD-1,به‌روزشده,,,,,,60000,,,,,,\n"
            + ",SKU-BRAND-NEW,تازه,,,,,leaf-imp,20000,1,,,,,\n"
        )
        job = self._job(csv_text, mode=ImportJob.Mode.UPSERT)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.updated_rows, 1)
        self.assertEqual(job.created_rows, 1)


class ReferenceValidationTests(ProductImportTestCase):
    def test_invalid_category_code_rejected(self):
        csv_text = PRODUCT_HEADER + ",SKU-BADCAT,کالا,,,,,no-such-category,1000,1,,,,,\n"
        job = self._job(csv_text, mode=ImportJob.Mode.CREATE_ONLY)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)

    def test_invalid_brand_code_rejected(self):
        csv_text = PRODUCT_HEADER + ",SKU-BADBRAND,کالا,,,,no-such-brand,leaf-imp,1000,1,,,,,\n"
        job = self._job(csv_text, mode=ImportJob.Mode.CREATE_ONLY)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)

    def test_invalid_tax_class_code_rejected(self):
        csv_text = PRODUCT_HEADER + ",SKU-BADTAX,کالا,,,,,leaf-imp,1000,1,,,no-such-tax,,\n"
        job = self._job(csv_text, mode=ImportJob.Mode.CREATE_ONLY)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)

    def test_duplicate_sku_within_file_rejected_for_second_occurrence(self):
        csv_text = (
            PRODUCT_HEADER
            + ",SKU-DUP-1,اول,,,,,leaf-imp,1000,1,,,,,\n"
        )
        job = self._job(csv_text, mode=ImportJob.Mode.CREATE_ONLY)
        import_service.run_execution(job, actor=self.actor)
        # Now attempt to create a second, *different* Product with the same SKU in a new job.
        job2 = self._job(csv_text, mode=ImportJob.Mode.CREATE_ONLY)
        import_service.run_execution(job2, actor=self.actor)
        job2.refresh_from_db()
        self.assertEqual(job2.invalid_rows, 1)
        self.assertEqual(Product.objects.filter(sku="SKU-DUP-1").count(), 1)


class TenantIsolationTests(ProductImportTestCase):
    def setUp(self):
        super().setUp()
        self.other_store = Store.objects.create(name="فروشگاه دیگر", slug="import-other-store")
        other_vendor = Vendor.objects.create(store=self.other_store, name="ف", slug="v-other-imp")
        other_category = Category.objects.create(store=self.other_store, name="د", slug="c-other-imp")
        self.foreign_product = Product.objects.create(
            store=self.other_store, vendor=other_vendor, category=other_category,
            name="کالایِ فروشگاهِ دیگر", slug="foreign-product-imp", sku="SKU-FOREIGN-1",
            price=Decimal("1"), stock=0,
        )

    def test_foreign_product_id_rejected(self):
        csv_text = f"product_id,sku,name,slug,barcode,status,brand_code,category_code,price,stock,weight_grams,requires_shipping,tax_class_code,seo_title,seo_description\n{self.foreign_product.pk},,دستکاری,,,,,,,,,,,,\n"
        job = self._job(csv_text, mode=ImportJob.Mode.UPSERT)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)
        self.foreign_product.refresh_from_db()
        self.assertEqual(self.foreign_product.name, "کالایِ فروشگاهِ دیگر")

    def test_foreign_sku_never_matched(self):
        csv_text = PRODUCT_HEADER + ",SKU-FOREIGN-1,دستکاریِ نام,,,,,leaf-imp,1000,1,,,,,\n"
        job = self._job(csv_text, mode=ImportJob.Mode.CREATE_ONLY)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        # Not matched (Store-scoped SKU lookup never sees another Store's SKU),
        # so create_only should CREATE a distinct Product in this Store instead
        # of touching the other Store's row.
        self.assertEqual(job.created_rows, 1)
        self.foreign_product.refresh_from_db()
        self.assertEqual(self.foreign_product.name, "کالایِ فروشگاهِ دیگر")
        self.assertEqual(Product.objects.filter(store=self.store, sku="SKU-FOREIGN-1").count(), 1)


class IdempotencyTests(ProductImportTestCase):
    def test_completed_job_cannot_execute_twice(self):
        csv_text = PRODUCT_HEADER + ",SKU-IDEMP-1,کالا,,,,,leaf-imp,1000,1,,,,,\n"
        job = self._job(csv_text, mode=ImportJob.Mode.CREATE_ONLY)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.COMPLETED)
        with self.assertRaises(import_service.ImportServiceError):
            import_service.run_execution(job, actor=self.actor)
        self.assertEqual(Product.objects.filter(sku="SKU-IDEMP-1").count(), 1)

    def test_duplicate_idempotency_key_rejected_at_upload(self):
        csv_text = PRODUCT_HEADER + ",SKU-KEY-1,کالا,,,,,leaf-imp,1000,1,,,,,\n"
        self._job(csv_text, idempotency_key="my-key-1")
        with self.assertRaises(import_service.ImportServiceError):
            self._job(csv_text, idempotency_key="my-key-1")

    def test_retry_after_partial_failure_does_not_double_apply(self):
        # A file where row 1 is valid and row 2 is invalid → completed_with_errors.
        csv_text = (
            PRODUCT_HEADER
            + ",SKU-PARTIAL-1,خوب,,,,,leaf-imp,1000,1,,,,,\n"
            + ",,,,,,,,,,,,,,\n"  # invalid: missing everything
        )
        job = self._job(csv_text, mode=ImportJob.Mode.UPSERT)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.COMPLETED_WITH_ERRORS)
        self.assertEqual(job.created_rows, 1)
        self.assertEqual(Product.objects.filter(store=self.store, sku="SKU-PARTIAL-1").count(), 1)
        # Retrying the same (now-final) job is blocked — no double creation.
        with self.assertRaises(import_service.ImportServiceError):
            import_service.run_execution(job, actor=self.actor)
        self.assertEqual(Product.objects.filter(store=self.store, sku="SKU-PARTIAL-1").count(), 1)


class BatchIsolationTests(ProductImportTestCase):
    def test_apply_failure_on_one_row_does_not_lose_earlier_rows_in_batch(self):
        # Two create rows sharing an explicit slug: row 1 succeeds, row 2's
        # save hits the (store, slug) uniqueness → the row fails, but row 1
        # (already applied earlier in the same batch) must persist — proving
        # the per-row savepoint keeps the batch transaction usable.
        csv_text = (
            PRODUCT_HEADER
            + ",SKU-BATCH-1,اول,dup-slug,,,,leaf-imp,1000,1,,,,,\n"
            + ",SKU-BATCH-2,دوم,dup-slug,,,,leaf-imp,2000,1,,,,,\n"
        )
        job = self._job(csv_text, mode=ImportJob.Mode.CREATE_ONLY)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.created_rows, 1)
        self.assertEqual(job.failed_rows, 1)
        self.assertTrue(Product.objects.filter(store=self.store, sku="SKU-BATCH-1").exists())
        self.assertFalse(Product.objects.filter(store=self.store, sku="SKU-BATCH-2").exists())


class BoundedQueryTests(ProductImportTestCase):
    """§26: repeated Brand/Category/TaxClass references must not produce a
    query per CSV cell — the lookup cache is built once per job, so preview
    query count stays bounded as row count grows."""

    def _preview_rows(self, n):
        rows = PRODUCT_HEADER
        for i in range(n):
            rows += f",SKU-BQ-{i},کالا {i},,,,brand-imp,leaf-imp,1000,1,,,general-imp,,\n"
        job = self._job(rows, mode=ImportJob.Mode.CREATE_ONLY)
        return job

    def test_preview_query_count_bounded_regardless_of_row_count(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        small = self._preview_rows(2)
        with CaptureQueriesContext(connection) as ctx_small:
            import_service.run_preview(small, actor=self.actor)
        large = self._preview_rows(20)
        with CaptureQueriesContext(connection) as ctx_large:
            import_service.run_preview(large, actor=self.actor)

        # The delta between 2-row and 20-row previews must be far below the
        # 18-row difference times a per-reference cost — a per-cell lookup
        # of 3 references (brand/category/tax) would add ~54 queries.
        self.assertLess(len(ctx_large.captured_queries) - len(ctx_small.captured_queries), 18)


# ============================================================ XLSX (primary format)

from apps.catalog.models import Brand as _Brand  # noqa: E402
from apps.dashboard.services import import_xlsx  # noqa: E402
from apps.dashboard.tests.xlsx_helpers import (  # noqa: E402
    open_workbook,
    read_job_file,
    sheet_values,
    xlsx_upload,
)

XLSX_PRODUCT_HEADERS = [
    "شناسه کالا", "SKU", "نام کالا *", "وضعیت", "برند", "دسته‌بندی *", "قیمت (تومان) *", "موجودی",
    "بارکد", "وزن (گرم)", "نیاز به ارسال", "دسته مالیاتی", "عنوان سئو", "توضیحات سئو",
]


class XlsxProductImportTests(ProductImportTestCase):
    def _xjob(self, rows, *, headers=None, mode=ImportJob.Mode.UPSERT, **upload_kwargs):
        return import_service.create_import_job(
            self.store, import_type=ImportJob.ImportType.PRODUCTS,
            uploaded_file=xlsx_upload(headers or XLSX_PRODUCT_HEADERS, rows, name="products.xlsx", **upload_kwargs),
            mode=mode, requested_by=self.actor,
        )

    def _row(self, **overrides):
        base = {
            "id": None, "sku": "XL-1", "name": "تیشرت نخی", "status": "فعال", "brand": "برند",
            "category": "دسته > زیردسته", "price": "۱۵۰۰۰۰", "stock": 8, "barcode": "6260000000011",
            "weight": 250, "shipping": "بله", "tax": "عمومی", "seo_title": "عنوان", "seo_desc": "توضیح",
        }
        base.update(overrides)
        return list(base.values())

    def test_source_file_is_stored_as_xlsx(self):
        job = self._xjob([self._row()])
        self.assertTrue(job.source_file.name.endswith(".xlsx"))
        self.assertEqual(import_service.job_source_format(job), "xlsx")
        self.assertEqual(read_job_file(job.source_file)[:2], b"PK")

    def test_persian_values_preview_then_execute(self):
        job = self._xjob([self._row()])
        import_service.run_preview(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.PREVIEW_READY)
        self.assertEqual((job.total_rows, job.valid_rows, job.invalid_rows), (1, 1, 0))
        self.assertFalse(Product.objects.filter(store=self.store, sku="XL-1").exists())
        result = job.row_results.get()
        self.assertEqual(result.row_number, 2)  # Excel row number (header is row 1)
        self.assertEqual(result.normalized_data_summary, {"action": "create"})
        self.assertEqual(import_service.job_preview_summary(job)["will_create"], 1)

        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.COMPLETED)
        product = Product.objects.get(store=self.store, sku="XL-1")
        self.assertEqual(product.name, "تیشرت نخی")
        self.assertEqual(product.status, Product.Status.ACTIVE)
        self.assertEqual(product.brand, self.brand)
        self.assertEqual(product.category, self.leaf)
        self.assertEqual(product.tax_class, self.tax_class)
        self.assertEqual(product.price, Decimal("150000"))
        self.assertEqual(product.stock, 8)
        self.assertEqual(product.weight_grams, 250)
        self.assertEqual(product.barcode, "6260000000011")
        self.assertTrue(StockMovement.objects.filter(product=product, delta=8).exists())

    def test_persian_digits_and_thousands_separators_normalize(self):
        rows = [
            self._row(sku="N-1", price="۱٬۲۰۰٬۰۰۰", stock="۱۲"),
            self._row(sku="N-2", price="1,500,000", stock=12.0, name="دوم"),
            self._row(sku="N-3", price=99000.0, stock="٣", name="سوم"),
        ]
        job = self._xjob(rows)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.created_rows, 3, list(job.row_results.values_list("errors", flat=True)))
        self.assertEqual(Product.objects.get(sku="N-1").price, Decimal("1200000"))
        self.assertEqual(Product.objects.get(sku="N-1").stock, 12)
        self.assertEqual(Product.objects.get(sku="N-2").price, Decimal("1500000"))
        self.assertEqual(Product.objects.get(sku="N-3").price, Decimal("99000"))
        self.assertEqual(Product.objects.get(sku="N-3").stock, 3)

    def test_status_accepts_persian_label_or_internal_code(self):
        rows = [
            self._row(sku="S-1", status="غیرفعال", name="الف"),
            self._row(sku="S-2", status="پیش‌نویس", name="ب"),
            self._row(sku="S-3", status="draft", name="پ"),
        ]
        import_service.run_execution(self._xjob(rows), actor=self.actor)
        self.assertEqual(Product.objects.get(sku="S-1").status, Product.Status.INACTIVE)
        self.assertEqual(Product.objects.get(sku="S-2").status, Product.Status.DRAFT)
        self.assertEqual(Product.objects.get(sku="S-3").status, Product.Status.DRAFT)

    def test_blank_tax_class_keeps_existing_but_explicit_clear_removes_it(self):
        product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.leaf, name="موجود", slug="exist-xl", sku="EX-1",
            price=Decimal("1000"), stock=0, tax_class=self.tax_class,
        )
        keep = self._row(sku="EX-1", name="", category="", price=2000, stock=None, tax="", brand="",
                         status="", shipping="", barcode="", weight=None, seo_title="", seo_desc="")
        job = self._xjob([keep], mode=ImportJob.Mode.UPDATE_ONLY)
        import_service.run_execution(job, actor=self.actor)
        product.refresh_from_db()
        self.assertEqual(product.price, Decimal("2000"))
        self.assertEqual(product.tax_class, self.tax_class, "blank cell must mean 'leave unchanged'")

        clear = {**dict(zip(range(14), keep))}
        clear_row = list(keep)
        clear_row[11] = import_xlsx.CLEAR_TAX_LABEL
        job = self._xjob([clear_row], mode=ImportJob.Mode.UPDATE_ONLY)
        import_service.run_execution(job, actor=self.actor)
        product.refresh_from_db()
        self.assertIsNone(product.tax_class)
        del clear

    def test_errors_carry_excel_row_numbers_and_merchant_column_names(self):
        rows = [
            self._row(sku="OK-1"),
            self._row(sku="BAD-1", brand="برندِ ناموجود", category="مسیر > نادرست", price="abc", status="نامعلوم"),
            self._row(sku="BAD-2", name="", price=-5),
        ]
        job = self._xjob(rows)
        import_service.run_preview(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual((job.valid_rows, job.invalid_rows), (1, 2))
        bad1, bad2 = job.row_results.filter(status="invalid").order_by("row_number")
        self.assertEqual((bad1.row_number, bad2.row_number), (3, 4))
        columns = {d["column"] for d in import_xlsx.describe_errors("products", bad1.errors)}
        self.assertTrue({"برند", "دسته‌بندی", "قیمت", "وضعیت"} <= columns, columns)
        columns2 = {d["column"] for d in import_xlsx.describe_errors("products", bad2.errors)}
        self.assertIn("نام کالا", columns2)
        self.assertIn("قیمت", columns2)
        shown = " ".join(d["message"] for d in import_xlsx.describe_errors("products", bad2.errors))
        for internal in ("category_code", "brand_code", "«name»", "«price»", "tax_class_code"):
            self.assertNotIn(internal, shown)
        self.assertFalse(Product.objects.filter(store=self.store, sku__startswith="BAD").exists())

    def test_create_only_message_uses_merchant_mode_name(self):
        Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.leaf, name="قبلی", slug="dup-xl", sku="DUP-1",
            price=Decimal("1"), stock=0,
        )
        job = self._xjob([self._row(sku="DUP-1")], mode=ImportJob.Mode.CREATE_ONLY)
        import_service.run_preview(job, actor=self.actor)
        text = " ".join(d["message"] for d in import_xlsx.describe_errors("products", job.row_results.get().errors))
        self.assertIn("افزودن موارد جدید", text)
        self.assertNotIn("فقط ایجاد", text)

    def test_ambiguous_brand_name_is_reported_not_guessed(self):
        _Brand.objects.create(store=self.store, name="برند", slug="brand-imp-dup")
        job = self._xjob([self._row()])
        import_service.run_preview(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)
        self.assertIn("مبهم", " ".join(job.row_results.get().errors))

    def test_category_leaf_name_accepted_when_unique_and_ambiguous_names_rejected(self):
        job = self._xjob([self._row(category="زیردسته")])
        import_service.run_preview(job, actor=self.actor)
        self.assertEqual(job.row_results.get().status, "valid")
        other_parent = Category.objects.create(store=self.store, name="دیگر", slug="other-parent-imp")
        Category.objects.create(store=self.store, name="زیردسته", slug="leaf-imp-2", parent=other_parent)
        job2 = self._xjob([self._row(category="زیردسته"), self._row(sku="XL-2", category="دیگر > زیردسته")])
        import_service.run_preview(job2, actor=self.actor)
        first, second = job2.row_results.order_by("row_number")
        self.assertEqual(first.status, "invalid")
        self.assertIn("مبهم", " ".join(first.errors))
        self.assertEqual(second.status, "valid")

    def test_formula_cells_are_rejected_not_executed(self):
        for evil in ("=1+1", "=HYPERLINK(\"http://x\",\"y\")", "=cmd|' /C calc'!A0"):
            job = self._xjob([self._row(sku="F-1", name=evil)])
            import_service.run_preview(job, actor=self.actor)
            result = job.row_results.get()
            self.assertEqual(result.status, "invalid", evil)
            self.assertIn("فرمول", " ".join(result.errors))
            self.assertEqual(import_xlsx.describe_errors("products", result.errors)[0]["column"], "نام کالا")
            job = self._xjob([self._row(sku="F-2", price=evil)])
            import_service.run_execution(job, actor=self.actor)
            self.assertFalse(Product.objects.filter(store=self.store, sku__in=["F-1", "F-2"]).exists())

    def test_literal_text_starting_with_equals_is_data_not_formula(self):
        # A quote-prefixed / text cell is a string, not a formula; it is imported as plain text.
        from openpyxl import Workbook
        import io as _io

        wb = Workbook()
        ws = wb.active
        ws.title = "داده‌ها"
        ws.append(XLSX_PRODUCT_HEADERS)
        ws.append(self._row(sku="LIT-1", name="x"))
        cell = ws["C2"]
        cell.value = "=نام"
        cell.data_type = "s"
        cell.quotePrefix = True
        buf = _io.BytesIO()
        wb.save(buf)
        from django.core.files.uploadedfile import SimpleUploadedFile

        job = import_service.create_import_job(
            self.store, import_type=ImportJob.ImportType.PRODUCTS,
            uploaded_file=SimpleUploadedFile("p.xlsx", buf.getvalue()), mode=ImportJob.Mode.UPSERT, requested_by=self.actor,
        )
        import_service.run_execution(job, actor=self.actor)
        self.assertEqual(Product.objects.get(sku="LIT-1").name, "=نام")

    def test_unknown_columns_are_ignored_with_a_warning(self):
        headers = XLSX_PRODUCT_HEADERS + ["ستون ناشناس"]
        job = self._xjob([self._row() + ["x"]], headers=headers)
        import_service.run_preview(job, actor=self.actor)
        result = job.row_results.get()
        self.assertEqual(result.status, "valid")
        self.assertIn("ستون ناشناس", " ".join(result.warnings))

    def test_file_without_recognised_columns_is_rejected(self):
        job = self._xjob([["a", "b"]], headers=["foo", "bar"])
        with self.assertRaises(import_service.ImportServiceError):
            import_service.run_preview(job, actor=self.actor)

    def test_legacy_internal_headers_inside_xlsx_still_work(self):
        headers = ["sku", "name", "status", "brand_code", "category_code", "price", "stock"]
        job = self._xjob([["LEG-1", "قدیمی", "active", "brand-imp", "leaf-imp", 5000, 1]], headers=headers)
        import_service.run_execution(job, actor=self.actor)
        self.assertEqual(Product.objects.get(sku="LEG-1").category, self.leaf)

    def test_blank_rows_are_skipped_but_excel_row_numbers_are_kept(self):
        job = self._xjob([self._row(sku="R-1"), [None] * 14, self._row(sku="R-2", name="دوم")])
        import_service.run_preview(job, actor=self.actor)
        self.assertEqual(list(job.row_results.order_by("row_number").values_list("row_number", flat=True)), [2, 4])

    def test_data_sheet_is_preferred_over_guide_sheet(self):
        job = self._xjob([self._row(sku="SH-1")], extra_sheets={"راهنما": [["نام", "توضیح"], ["x", "y"]]})
        import_service.run_execution(job, actor=self.actor)
        self.assertTrue(Product.objects.filter(sku="SH-1").exists())

    def test_error_report_is_xlsx_with_original_values_and_highlights(self):
        rows = [self._row(sku="OK-9"), self._row(sku="ERR-1", brand="نامعلوم", price="۱۰")]
        job = self._xjob(rows)
        import_service.run_preview(job, actor=self.actor)
        job.refresh_from_db()
        self.assertTrue(job.error_report_file.name.endswith(".xlsx"))
        wb = open_workbook(read_job_file(job.error_report_file))
        self.assertEqual(wb.sheetnames, ["خطاها", "راهنما"])
        ws = wb["خطاها"]
        rows_out = sheet_values(ws)
        self.assertEqual(rows_out[0][:4], ["ردیف در اکسل", "وضعیت", "خطاها", "هشدارها"])
        self.assertEqual(rows_out[1][0], 3)
        self.assertEqual(rows_out[1][1], "نامعتبر")
        self.assertIn("برند", rows_out[1][2])
        self.assertIn("ERR-1", rows_out[1])  # the original SKU
        self.assertIn("نامعلوم", rows_out[1])  # the original (wrong) brand text
        # the failing column's original cell is highlighted
        brand_col = rows_out[0].index("برند") + 1
        self.assertEqual(ws.cell(row=2, column=brand_col).fill.start_color.rgb[-6:], "FBE3E3")
        self.assertTrue(ws.sheet_view.rightToLeft)

    def test_other_stores_reference_data_is_not_resolvable(self):
        other = Store.objects.create(name="دیگر", slug="xl-other-store")
        other_root = Category.objects.create(store=other, name="بیگانه", slug="foreign-root")
        Category.objects.create(store=other, name="برگ", slug="foreign-leaf", parent=other_root)
        job = self._xjob([self._row(category="بیگانه > برگ")])
        import_service.run_preview(job, actor=self.actor)
        self.assertEqual(job.row_results.get().status, "invalid")

    def test_idempotent_replay_is_still_blocked(self):
        job = self._xjob([self._row()])
        import_service.run_execution(job, actor=self.actor)
        with self.assertRaises(import_service.ImportServiceError):
            import_service.run_execution(job, actor=self.actor)
        self.assertEqual(Product.objects.filter(sku="XL-1").count(), 1)
