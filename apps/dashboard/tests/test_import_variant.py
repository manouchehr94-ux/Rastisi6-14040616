"""Tests for the checkpoint 4B Variant Import service — reuses the real
Variant Engine (``variant_engine_service.generate_variants``/
``set_default_variant``), never creates ``VariantOptionValue`` rows or
combination keys by hand."""

from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.catalog.models import Category, Product, ProductImage, ProductVariant, StockMovement, Vendor
from apps.catalog.services.variant_engine_service import add_option_value, add_product_option, generate_variants
from apps.core.models import ImportJob, ImportRowResult
from apps.dashboard.services import import_service
from apps.stores.models import Store

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _csv_upload(text: str, name="variants.csv"):
    return SimpleUploadedFile(name, text.encode("utf-8"), content_type="text/csv")


VARIANT_HEADER = (
    "product_id,product_sku,variant_id,variant_sku,barcode,"
    "option_1_code,option_1_value_code,option_2_code,option_2_value_code,"
    "price,compare_at_price,cost,stock,weight_grams,is_active,is_default\n"
)


class VariantImportTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-vimp")
        self.category = Category.objects.create(store=self.store, name="دسته", slug="cat-vimp")
        self.actor = User.objects.create_user(username="vimp-owner", password="p", is_staff=True)

        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالایِ چندمحوره",
            slug="multi-axis-vimp", sku="SKU-VIMP-1", price=Decimal("100000"), stock=0,
            product_type=Product.ProductType.VARIABLE,
        )
        self.color_option = add_product_option(self.product, label="رنگ", values=["قرمز", "آبی"])
        self.red_value = self.color_option.values.get(label="قرمز")
        self.blue_value = self.color_option.values.get(label="آبی")

    def _job(self, csv_text, *, mode=ImportJob.Mode.UPSERT, idempotency_key=""):
        return import_service.create_import_job(
            self.store, import_type=ImportJob.ImportType.VARIANTS, uploaded_file=_csv_upload(csv_text),
            mode=mode, requested_by=self.actor, idempotency_key=idempotency_key,
        )


class NewCombinationTests(VariantImportTestCase):
    def test_creates_new_combination_via_engine(self):
        self.assertEqual(self.product.variants.count(), 0)
        csv_text = VARIANT_HEADER + f",SKU-VIMP-1,,VAR-RED,BAR-RED,رنگ,قرمز,,,15000,,8000,5,,بله,\n"
        job = self._job(csv_text, mode=ImportJob.Mode.CREATE_ONLY)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.COMPLETED)
        self.assertEqual(job.created_rows, 1)
        # generate_variants is exhaustive — both combinations now exist.
        self.assertEqual(self.product.variants.exclude(combination_key="").count(), 2)
        variant = ProductVariant.objects.get(product=self.product, sku="VAR-RED")
        self.assertEqual(variant.extra_price, Decimal("15000"))
        self.assertEqual(variant.cost, Decimal("8000"))
        self.assertEqual(variant.stock, 5)
        movement = StockMovement.objects.get(variant=variant)
        self.assertEqual(movement.delta, 5)

    def test_missing_option_value_for_new_combination_rejected(self):
        csv_text = VARIANT_HEADER + ",SKU-VIMP-1,,VAR-GREEN,,رنگ,سبز,,,1000,,,1,,,\n"
        job = self._job(csv_text, mode=ImportJob.Mode.CREATE_ONLY)
        with self.assertRaises(import_service.ImportExecutionBlocked):
            import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)
        self.assertEqual(self.product.variants.count(), 0)


class ExistingCombinationTests(VariantImportTestCase):
    def setUp(self):
        super().setUp()
        generate_variants(self.product)
        self.red_variant = ProductVariant.objects.get(product=self.product, combination_key__gt="", value="قرمز")

    def test_update_by_variant_id(self):
        csv_text = (
            f"product_id,product_sku,variant_id,variant_sku,barcode,option_1_code,option_1_value_code,"
            f"option_2_code,option_2_value_code,price,compare_at_price,cost,stock,weight_grams,is_active,is_default\n"
            f",,{self.red_variant.pk},NEW-SKU-RED,,,,,,25000,,,3,,,\n"
        )
        job = self._job(csv_text, mode=ImportJob.Mode.UPDATE_ONLY)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.updated_rows, 1)
        self.red_variant.refresh_from_db()
        self.assertEqual(self.red_variant.sku, "NEW-SKU-RED")
        self.assertEqual(self.red_variant.extra_price, Decimal("25000"))
        self.assertEqual(self.red_variant.stock, 3)

    def test_update_by_option_combination(self):
        csv_text = VARIANT_HEADER + ",SKU-VIMP-1,,,,رنگ,قرمز,,,30000,,,,,,\n"
        job = self._job(csv_text, mode=ImportJob.Mode.UPDATE_ONLY)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.updated_rows, 1)
        self.red_variant.refresh_from_db()
        self.assertEqual(self.red_variant.extra_price, Decimal("30000"))

    def test_update_preserves_sku_when_not_provided(self):
        self.red_variant.sku = "ORIGINAL-SKU"
        self.red_variant.save(update_fields=["sku"])
        csv_text = VARIANT_HEADER + ",SKU-VIMP-1,,,,رنگ,قرمز,,,5000,,,,,,\n"
        job = self._job(csv_text, mode=ImportJob.Mode.UPDATE_ONLY)
        import_service.run_execution(job, actor=self.actor)
        self.red_variant.refresh_from_db()
        self.assertEqual(self.red_variant.sku, "ORIGINAL-SKU")

    def test_update_preserves_variant_images(self):
        image = ProductImage.objects.create(
            product=self.product, variant=self.red_variant,
            image="products/gallery/red.jpg", order=0,
        )
        csv_text = VARIANT_HEADER + ",SKU-VIMP-1,,,,رنگ,قرمز,,,9999,,,,,,\n"
        job = self._job(csv_text, mode=ImportJob.Mode.UPDATE_ONLY)
        import_service.run_execution(job, actor=self.actor)
        image.refresh_from_db()
        self.assertEqual(image.variant_id, self.red_variant.pk)
        self.assertTrue(ProductImage.objects.filter(pk=image.pk, variant=self.red_variant).exists())

    def test_update_preserves_variant_primary_key(self):
        original_pk = self.red_variant.pk
        csv_text = VARIANT_HEADER + ",SKU-VIMP-1,,,,رنگ,قرمز,,,1111,,,,,,\n"
        job = self._job(csv_text, mode=ImportJob.Mode.UPDATE_ONLY)
        import_service.run_execution(job, actor=self.actor)
        self.red_variant.refresh_from_db()
        self.assertEqual(self.red_variant.pk, original_pk)
        self.assertEqual(self.red_variant.extra_price, Decimal("1111"))

    def test_create_only_rejects_existing_combination(self):
        csv_text = VARIANT_HEADER + ",SKU-VIMP-1,,,,رنگ,قرمز,,,1000,,,,,,\n"
        job = self._job(csv_text, mode=ImportJob.Mode.CREATE_ONLY)
        with self.assertRaises(import_service.ImportExecutionBlocked):
            import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)

    def test_is_default_sets_default_variant(self):
        blue_variant = ProductVariant.objects.get(product=self.product, combination_key__gt="", value="آبی")
        csv_text = (
            f"product_id,product_sku,variant_id,variant_sku,barcode,option_1_code,option_1_value_code,"
            f"option_2_code,option_2_value_code,price,compare_at_price,cost,stock,weight_grams,is_active,is_default\n"
            f",,{blue_variant.pk},,,,,,,,,,,,,بله\n"
        )
        job = self._job(csv_text, mode=ImportJob.Mode.UPDATE_ONLY)
        import_service.run_execution(job, actor=self.actor)
        blue_variant.refresh_from_db()
        self.assertTrue(blue_variant.is_default)


class ValidationTests(VariantImportTestCase):
    def test_missing_product_reference_rejected(self):
        csv_text = VARIANT_HEADER + ",,,,,,,,,,,,,,,\n"
        job = self._job(csv_text, mode=ImportJob.Mode.UPSERT)
        with self.assertRaises(import_service.ImportExecutionBlocked):
            import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)

    def test_invalid_option_code_rejected(self):
        csv_text = VARIANT_HEADER + ",SKU-VIMP-1,,,,اندازه,بزرگ,,,1000,,,,,,\n"
        job = self._job(csv_text, mode=ImportJob.Mode.UPSERT)
        with self.assertRaises(import_service.ImportExecutionBlocked):
            import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)

    def test_dry_run_does_not_create_variant(self):
        csv_text = VARIANT_HEADER + ",SKU-VIMP-1,,VAR-PREVIEW,,رنگ,قرمز,,,1000,,,,,,\n"
        job = self._job(csv_text, mode=ImportJob.Mode.CREATE_ONLY)
        import_service.run_preview(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.PREVIEW_READY)
        self.assertEqual(self.product.variants.count(), 0)


class LegacyProductRejectionTests(VariantImportTestCase):
    def test_legacy_variant_product_rejected(self):
        legacy_product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالایِ قدیمی",
            slug="legacy-vimp", sku="SKU-LEGACY-1", price=Decimal("1"), stock=0,
        )
        ProductVariant.objects.create(
            product=legacy_product, store=self.store, attribute="رنگ", value="قرمز", stock=1,
        )
        csv_text = VARIANT_HEADER + ",SKU-LEGACY-1,,,,,,,,,,,,,,\n"
        job = self._job(csv_text, mode=ImportJob.Mode.UPSERT)
        with self.assertRaises(import_service.ImportExecutionBlocked):
            import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)


class TenantIsolationTests(VariantImportTestCase):
    def setUp(self):
        super().setUp()
        generate_variants(self.product)
        self.other_store = Store.objects.create(name="فروشگاه دیگر", slug="vimp-other-store")
        other_vendor = Vendor.objects.create(store=self.other_store, name="ف", slug="v-other-vimp")
        other_category = Category.objects.create(store=self.other_store, name="د", slug="c-other-vimp")
        self.foreign_product = Product.objects.create(
            store=self.other_store, vendor=other_vendor, category=other_category, name="کالایِ خارجی",
            slug="foreign-vimp", sku="SKU-FOREIGN-VIMP", price=Decimal("1"), stock=0,
        )

    def test_foreign_product_id_rejected(self):
        csv_text = (
            f"product_id,product_sku,variant_id,variant_sku,barcode,option_1_code,option_1_value_code,"
            f"option_2_code,option_2_value_code,price,compare_at_price,cost,stock,weight_grams,is_active,is_default\n"
            f"{self.foreign_product.pk},,,,,,,,,,,,,,,\n"
        )
        job = self._job(csv_text, mode=ImportJob.Mode.UPSERT)
        with self.assertRaises(import_service.ImportExecutionBlocked):
            import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)

    def test_foreign_variant_id_rejected(self):
        foreign_variant = ProductVariant.objects.create(
            product=self.foreign_product, store=self.other_store, attribute="رنگ", value="قرمز", stock=1,
        )
        csv_text = (
            f"product_id,product_sku,variant_id,variant_sku,barcode,option_1_code,option_1_value_code,"
            f"option_2_code,option_2_value_code,price,compare_at_price,cost,stock,weight_grams,is_active,is_default\n"
            f",SKU-VIMP-1,{foreign_variant.pk},,,,,,,,,,,,,\n"
        )
        job = self._job(csv_text, mode=ImportJob.Mode.UPSERT)
        with self.assertRaises(import_service.ImportExecutionBlocked):
            import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)


# ============================================================ XLSX (primary format)

from apps.dashboard.services import import_xlsx  # noqa: E402
from apps.dashboard.tests.xlsx_helpers import xlsx_upload  # noqa: E402

XLSX_VARIANT_HEADERS = [
    "شناسه کالا", "SKU کالا *", "شناسه تنوع", "SKU تنوع", "بارکد", "نام ویژگی ۱", "مقدار ویژگی ۱",
    "نام ویژگی ۲", "مقدار ویژگی ۲", "تغییر قیمت (تومان)", "قیمت مقایسه‌ای (تومان)", "بهای تمام‌شده (تومان)",
    "موجودی", "وزن (گرم)", "فعال", "پیش‌فرض",
]


class XlsxVariantImportTests(VariantImportTestCase):
    def _xjob(self, rows, *, mode=ImportJob.Mode.UPSERT):
        return import_service.create_import_job(
            self.store, import_type=ImportJob.ImportType.VARIANTS,
            uploaded_file=xlsx_upload(XLSX_VARIANT_HEADERS, rows, name="variants.xlsx"),
            mode=mode, requested_by=self.actor,
        )

    def _row(self, **kw):
        base = {
            "pid": None, "psku": "SKU-VIMP-1", "vid": None, "vsku": "XV-RED", "barcode": None,
            "o1": "رنگ", "v1": "قرمز", "o2": None, "v2": None, "price": "۱۵٬۰۰۰", "cmp": None, "cost": 8000,
            "stock": "۵", "weight": None, "active": "بله", "default": "بله",
        }
        base.update(kw)
        return list(base.values())

    def test_create_variant_from_persian_headers_and_values(self):
        job = self._xjob([self._row()], mode=ImportJob.Mode.CREATE_ONLY)
        import_service.run_preview(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.valid_rows, 1)
        self.assertEqual(job.row_results.get().normalized_data_summary, {"action": "create"})
        self.assertEqual(self.product.variants.count(), 0)
        import_service.run_execution(job, actor=self.actor)
        variant = ProductVariant.objects.get(product=self.product, sku="XV-RED")
        self.assertEqual(variant.extra_price, Decimal("15000"))
        self.assertEqual(variant.cost, Decimal("8000"))
        self.assertEqual(variant.stock, 5)
        self.assertTrue(variant.is_default)

    def test_update_existing_combination_by_option_names(self):
        generate_variants(self.product)
        job = self._xjob([self._row(vsku="XV-NEW", price=777, stock=None, default=None)], mode=ImportJob.Mode.UPDATE_ONLY)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.updated_rows, 1)
        self.assertEqual(ProductVariant.objects.get(product=self.product, sku="XV-NEW").extra_price, Decimal("777"))

    def test_errors_name_the_option_columns_in_merchant_language(self):
        job = self._xjob([self._row(v1="سبز"), self._row(psku="NOPE", vsku="X2")])
        import_service.run_preview(job, actor=self.actor)
        bad_value, bad_product = job.row_results.order_by("row_number")
        d = import_xlsx.describe_errors("variants", bad_value.errors)
        self.assertEqual((bad_value.row_number, d[0]["column"]), (2, "مقدار ویژگی ۱"))
        self.assertNotIn("option_1", d[0]["message"])
        self.assertNotIn("محور", d[0]["message"])
        self.assertEqual(bad_product.row_number, 3)
        self.assertEqual(import_xlsx.describe_errors("variants", bad_product.errors)[0]["column"], "SKU کالا")

    def test_missing_option_names_message_is_not_technical(self):
        job = self._xjob([self._row(o1=None, v1=None, vsku="X3")], mode=ImportJob.Mode.CREATE_ONLY)
        import_service.run_preview(job, actor=self.actor)
        text = " ".join(d["message"] for d in import_xlsx.describe_errors("variants", job.row_results.get().errors))
        self.assertIn("نامِ ویژگی", text)
        self.assertNotIn("option_N_code", text)
