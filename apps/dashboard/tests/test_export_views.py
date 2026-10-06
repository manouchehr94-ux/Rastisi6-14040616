"""Tests for the Export domain: generating real ``.xlsx`` workbooks for all
five export types, their structure/formatting, permission enforcement, tenant
isolation, formula-injection protection, and the authenticated Store-scoped
download view."""

import io
import zipfile
from datetime import datetime
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Brand, Category, Product, Vendor, Warehouse, WarehouseInventory
from apps.core.models import AuditLogEntry, ExportJob
from apps.core.services.export_service import ExportError, generate_export
from apps.customers.models import Customer
from apps.orders.models import (
    Order,
    PaymentGateway,
    ShippingMethod,
    ShippingZone,
    TaxClass,
)
from apps.stores.models import Store, StoreMembership
from apps.dashboard.tests.xlsx_helpers import XLSX_MIME, open_workbook, sheet_values

User = get_user_model()

PRODUCT_HEADERS = [
    "نام کالا", "SKU", "وضعیت", "برند", "دسته‌بندی", "قیمت (تومان)", "موجودی", "بارکد",
    "وزن (گرم)", "نیاز به ارسال", "دسته مالیاتی", "عنوان سئو", "توضیحات سئو",
    "تاریخ ایجاد", "آخرین بروزرسانی", "شناسه کالا", "نشانی صفحه (اسلاگ)",
]
INVENTORY_HEADERS = [
    "انبار", "کالا", "SKU", "تنوع", "موجودی فعلی", "رزرو شده", "موجودی قابل فروش",
    "آستانه هشدار کمبود", "آخرین بروزرسانی", "بارکد", "شناسه کالا", "شناسه تنوع",
]
SHEET_TITLES = {
    "products": "کالاها", "variants": "تنوع‌ها", "inventory": "موجودی انبار",
    "customers": "مشتریان", "orders": "سفارش‌ها",
}


def _workbook(result):
    """Open the XLSX bytes returned by ``generate_export`` (never stored anywhere)."""
    return open_workbook(result.content)

HOST = f"export-test.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class ExportTestCase(TestCase):
    def setUp(self):
        self.client = Client(HTTP_HOST=HOST)
        self.store = _akhlaghi()
        self.store.admin_subdomain = "export-test"
        self.store.save(update_fields=["admin_subdomain"])

        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-exp")
        self.category = Category.objects.create(store=self.store, name="دسته", slug="cat-exp", parent=None)
        self.leaf = Category.objects.create(store=self.store, name="زیردسته", slug="leaf-exp", parent=self.category)
        self.brand = Brand.objects.create(store=self.store, name="برند", slug="brand-exp")
        self.tax_class = TaxClass.objects.create(store=self.store, name="عمومی", code="general-exp")

        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.leaf, brand=self.brand,
            tax_class=self.tax_class,
            name="=cmd|'/c calc'!A1", slug="formula-product-exp", sku="SKU-EXP-1",
            price=Decimal("150000"), stock=30,
        )
        self.warehouse = Warehouse.objects.filter(store=self.store, is_default=True).first()
        if self.warehouse is None:
            self.warehouse = Warehouse.objects.create(
                store=self.store, name="انبار اصلی", code="main-exp", is_default=True,
            )
        WarehouseInventory.objects.filter(store=self.store, warehouse=self.warehouse, product=self.product).delete()
        WarehouseInventory.objects.create(
            store=self.store, warehouse=self.warehouse, product=self.product, on_hand=30,
        )

        user_model_user = User.objects.create_user(username="09121110001", password="pass12345")
        self.customer = Customer.objects.create(
            user=user_model_user, full_name="مشتری تست", phone="09121110001", email="c@example.com",
        )
        self.zone = ShippingZone.objects.create(store=self.store, name="منطقه", code="zone-exp")
        self.shipping_method = ShippingMethod.objects.create(
            store=self.store, zone=self.zone, name="ارسال عادی", slug="std-exp",
        )
        self.gateway = PaymentGateway.objects.create(store=self.store, name="درگاه", slug="gw-exp")
        self.order = Order.objects.create(
            store=self.store, customer=self.customer, vendor=self.vendor, code="ORD-EXP-1",
            address={}, shipping_method=self.shipping_method, payment_gateway=self.gateway,
            status=Order.Status.DELIVERED, payment_status=Order.PaymentStatus.PAID,
            items_total=Decimal("150000"), grand_total=Decimal("150000"),
        )

        self.owner = User.objects.create_user(username="exp-owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.login(username="exp-owner", password="pass12345")

    def _login_as(self, role, suffix):
        user = User.objects.create_user(username=f"exp-role-{suffix}", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=user, role=role,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.logout()
        self.client.login(username=user.username, password="pass12345")


class RunExportServiceTests(ExportTestCase):
    def test_products_export_generates_completed_job_with_row(self):
        result = generate_export(self.store, ExportJob.ExportType.PRODUCTS, requested_by=self.owner)
        self.assertEqual(result.job.status, ExportJob.Status.COMPLETED)
        self.assertEqual(result.row_count, 1)
        self.assertEqual(result.content[:2], b"PK")
        self.assertTrue(result.filename.endswith(".xlsx"))

    def test_variants_export_runs(self):
        result = generate_export(self.store, ExportJob.ExportType.VARIANTS, requested_by=self.owner)
        self.assertEqual(result.job.status, ExportJob.Status.COMPLETED)

    def test_customers_export_scopes_totals_to_store(self):
        result = generate_export(self.store, ExportJob.ExportType.CUSTOMERS, requested_by=self.owner)
        self.assertEqual(result.job.status, ExportJob.Status.COMPLETED)
        self.assertEqual(result.row_count, 1)

    def test_invalid_export_type_rejected(self):
        with self.assertRaises(ExportError):
            generate_export(self.store, "not-a-real-type", requested_by=self.owner)

    def test_completion_is_audit_logged(self):
        generate_export(self.store, ExportJob.ExportType.PRODUCTS, requested_by=self.owner)
        entry = AuditLogEntry.objects.get(store=self.store, action_code="export.completed")
        self.assertIn("xlsx", entry.after_summary)


class XlsxExportStructureTests(ExportTestCase):
    """Every export is a genuine OOXML workbook that opens cleanly in Excel."""

    def test_all_five_export_types_produce_valid_xlsx(self):
        for export_type, sheet_title in SHEET_TITLES.items():
            with self.subTest(export_type=export_type):
                job = generate_export(self.store, export_type, requested_by=self.owner)
                content = job.content
                self.assertTrue(job.filename.endswith(".xlsx"))
                self.assertTrue(zipfile.is_zipfile(io.BytesIO(content)))
                self.assertEqual(content[:2], b"PK")  # not a renamed CSV
                names = zipfile.ZipFile(io.BytesIO(content)).namelist()
                self.assertIn("[Content_Types].xml", names)
                self.assertIn("xl/workbook.xml", names)
                self.assertFalse([n for n in names if "vbaProject" in n])
                wb = open_workbook(content)
                self.assertEqual(wb.sheetnames, [sheet_title, "راهنما"])

    def test_products_header_order_and_values_are_in_separate_cells(self):
        job = generate_export(self.store, ExportJob.ExportType.PRODUCTS, requested_by=self.owner)
        ws = _workbook(job)["کالاها"]
        rows = sheet_values(ws)
        self.assertEqual(rows[0], PRODUCT_HEADERS)
        self.assertEqual(len(rows[0]), len(set(rows[0])), "headers must be distinct cells")
        data = rows[1]
        self.assertEqual(len(data), len(PRODUCT_HEADERS))
        by_header = dict(zip(PRODUCT_HEADERS, data))
        self.assertEqual(by_header["SKU"], "SKU-EXP-1")
        self.assertEqual(by_header["وضعیت"], "فعال")
        self.assertEqual(by_header["برند"], "برند")
        self.assertEqual(by_header["دسته‌بندی"], "دسته > زیردسته")
        self.assertEqual(by_header["دسته مالیاتی"], "عمومی")
        self.assertEqual(by_header["نیاز به ارسال"], "بله")
        self.assertEqual(by_header["شناسه کالا"], self.product.pk)
        self.assertEqual(by_header["نشانی صفحه (اسلاگ)"], "formula-product-exp")
        # nothing is packed into one cell with a delimiter
        self.assertFalse(any(isinstance(v, str) and "," in v and "SKU-EXP-1" in v for v in data))

    def test_persian_text_round_trips_exactly(self):
        persian = "تیشرت نخیِ مردانه، سایز «بزرگ» ژ گ چ پ — ۱۲۳"
        Product.objects.filter(pk=self.product.pk).update(
            name=persian, seo_title="عنوان فارسی", seo_description="توضیحاتِ سئو با نیم‌فاصله و ارقام ۰۱۲۳۴۵۶۷۸۹",
        )
        job = generate_export(self.store, ExportJob.ExportType.PRODUCTS, requested_by=self.owner)
        ws = _workbook(job)["کالاها"]
        self.assertEqual(ws["A2"].value, persian)
        self.assertEqual(ws["L2"].value, "عنوان فارسی")
        self.assertEqual(ws["M2"].value, "توضیحاتِ سئو با نیم‌فاصله و ارقام ۰۱۲۳۴۵۶۷۸۹")
        # the raw bytes are UTF-8 inside the zip, not a legacy code page
        sheet_xml = zipfile.ZipFile(io.BytesIO(job.content)).read("xl/worksheets/sheet1.xml").decode("utf-8")
        self.assertIn(persian, sheet_xml)

    def test_worksheet_presentation(self):
        job = generate_export(self.store, ExportJob.ExportType.PRODUCTS, requested_by=self.owner)
        ws = _workbook(job)["کالاها"]
        self.assertTrue(ws.sheet_view.rightToLeft)
        self.assertEqual(ws.freeze_panes, "A2")
        self.assertEqual(ws.auto_filter.ref, "A1:Q2")
        self.assertTrue(ws["A1"].font.bold)
        self.assertEqual(ws["A1"].fill.fill_type, "solid")
        for letter in "ABCDEF":
            self.assertGreater(ws.column_dimensions[letter].width, 8)
        self.assertGreaterEqual(ws.row_dimensions[1].height, 28)
        # technical columns come last and are visually de-emphasised
        self.assertEqual(ws["P1"].value, "شناسه کالا")
        self.assertNotEqual(ws["P1"].fill.start_color.rgb, ws["A1"].fill.start_color.rgb)

    def test_numbers_are_numeric_cells_with_thousands_format(self):
        job = generate_export(self.store, ExportJob.ExportType.PRODUCTS, requested_by=self.owner)
        ws = _workbook(job)["کالاها"]
        price = ws["F2"]
        self.assertEqual(price.data_type, "n")
        self.assertEqual(price.value, 150000)
        self.assertEqual(price.number_format, "#,##0")
        stock = ws["G2"]
        self.assertEqual((stock.data_type, stock.value), ("n", 30))
        self.assertEqual(ws["I2"].value, None)  # empty weight stays an empty cell, not "0"/"None"

    def test_dates_are_real_excel_datetime_cells(self):
        job = generate_export(self.store, ExportJob.ExportType.PRODUCTS, requested_by=self.owner)
        ws = _workbook(job)["کالاها"]
        for coordinate in ("N2", "O2"):
            cell = ws[coordinate]
            self.assertIsInstance(cell.value, datetime, coordinate)
            self.assertEqual(cell.data_type, "d")
            self.assertIn("yyyy", cell.number_format)
            self.assertIsNone(cell.value.tzinfo)

    def test_formula_like_values_are_literal_text_never_formulas(self):
        evil = ["=cmd|'/c calc'!A1", "+SUM(1,2)", "-2+3", "@SUM(A1)", "=HYPERLINK(\"http://x\",\"y\")"]
        for index, value in enumerate(evil):
            Product.objects.create(
                store=self.store, vendor=self.vendor, category=self.leaf, name=value,
                slug=f"evil-{index}-exp", sku=f"=EV{index}", price=Decimal("1"), stock=1, barcode=value,
                seo_title=value, seo_description=value,
            )
        job = generate_export(self.store, ExportJob.ExportType.PRODUCTS, requested_by=self.owner)
        content = job.content
        ws = open_workbook(content)["کالاها"]
        seen = {ws.cell(row=r, column=1).value for r in range(2, ws.max_row + 1)}
        for value in evil:
            self.assertIn(value, seen)  # exact value preserved, no leading apostrophe added
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                self.assertNotEqual(cell.data_type, "f", cell.coordinate)
                if isinstance(cell.value, str) and cell.value.startswith(("=", "+", "-", "@")):
                    self.assertEqual(cell.data_type, "s")
                    self.assertTrue(cell.quotePrefix, cell.coordinate)
        xml = zipfile.ZipFile(io.BytesIO(content)).read("xl/worksheets/sheet1.xml").decode("utf-8")
        self.assertNotIn("<f>", xml)
        self.assertNotIn("<f ", xml)

    def test_inventory_uses_merchant_language_and_numeric_cells(self):
        job = generate_export(self.store, ExportJob.ExportType.INVENTORY, requested_by=self.owner)
        ws = _workbook(job)["موجودی انبار"]
        rows = sheet_values(ws)
        self.assertEqual(rows[0], INVENTORY_HEADERS)
        self.assertNotIn("on hand", " ".join(rows[0]).lower())
        data = dict(zip(INVENTORY_HEADERS, rows[1]))
        self.assertEqual(data["موجودی فعلی"], 30)
        self.assertEqual(data["رزرو شده"], 0)
        self.assertEqual(data["موجودی قابل فروش"], 30)
        self.assertEqual(data["SKU"], "SKU-EXP-1")
        self.assertIsInstance(data["آخرین بروزرسانی"], datetime)
        self.assertEqual(ws["E2"].data_type, "n")

    def test_variants_customers_and_orders_headers_and_types(self):
        customers = _workbook(generate_export(self.store, ExportJob.ExportType.CUSTOMERS, requested_by=self.owner))["مشتریان"]
        self.assertEqual(sheet_values(customers)[0], [
            "نام مشتری", "موبایل", "ایمیل", "تعداد سفارش", "مجموع خرید (تومان)", "آخرین سفارش", "تاریخ عضویت", "شناسه مشتری",
        ])
        row = dict(zip(sheet_values(customers)[0], sheet_values(customers)[1]))
        self.assertEqual(row["نام مشتری"], "مشتری تست")
        self.assertEqual(row["موبایل"], "09121110001")  # text: leading zero preserved
        self.assertEqual(row["مجموع خرید (تومان)"], 150000)
        self.assertEqual(customers["D2"].data_type, "n")

        orders = _workbook(generate_export(self.store, ExportJob.ExportType.ORDERS, requested_by=self.owner))["سفارش‌ها"]
        header = sheet_values(orders)[0]
        self.assertEqual(header[0], "شماره سفارش")
        self.assertNotIn("IRT", " ".join(map(str, header)))
        row = dict(zip(header, sheet_values(orders)[1]))
        self.assertEqual(row["شماره سفارش"], "ORD-EXP-1")
        self.assertEqual(row["مبلغ نهایی (تومان)"], 150000)
        self.assertEqual(row["وضعیت سفارش"], "تحویل داده شده")
        self.assertEqual(row["وضعیت پرداخت"], "پرداخت‌شده")
        self.assertIsInstance(row["تاریخ ثبت"], datetime)

        variants = _workbook(generate_export(self.store, ExportJob.ExportType.VARIANTS, requested_by=self.owner))["تنوع‌ها"]
        self.assertEqual(sheet_values(variants)[0][:3], ["نام کالا", "ویژگی‌هایِ تنوع", "SKU تنوع"])

    def test_guide_sheet_describes_the_file(self):
        job = generate_export(self.store, ExportJob.ExportType.PRODUCTS, requested_by=self.owner)
        guide = _workbook(job)["راهنما"]
        text = [str(v) for row in sheet_values(guide) for v in row if v is not None]
        joined = "\n".join(text)
        self.assertIn("درباره‌ی این فایل", joined)
        self.assertIn("کالاها", joined)  # export type
        self.assertIn(self.store.name, joined)  # store
        self.assertIn("راستی‌سی", joined)
        self.assertIn("تاریخ تهیه", joined)
        self.assertIn("تعداد ردیف‌ها", joined)
        # per-column descriptions for non-obvious fields
        self.assertIn("مسیرِ کاملِ دسته‌بندی", joined)
        facts = {row[0]: row[1] for row in sheet_values(guide) if row[0] and len(row) > 1}
        self.assertEqual(facts["تعداد ردیف‌ها"], 1)
        self.assertIsInstance(facts["تاریخ تهیه"], datetime)
        # no secrets / internal implementation details
        for forbidden in ("password", "token", "secret", "ExportJob", "openpyxl", "private_storage"):
            self.assertNotIn(forbidden.lower(), joined.lower())

    def test_inventory_guide_explains_whole_store_reservations(self):
        job = generate_export(self.store, ExportJob.ExportType.INVENTORY, requested_by=self.owner)
        guide = _workbook(job)["راهنما"]
        joined = "\n".join(str(v) for row in sheet_values(guide) for v in row if v is not None)
        self.assertIn("کلِ فروشگاه", joined)


class XlsxEmptyExportTests(ExportTestCase):
    def setUp(self):
        super().setUp()
        self.empty_store = Store.objects.create(name="فروشگاهِ خالی", slug="export-empty-store")

    def test_empty_exports_keep_headers_and_explain_why_there_are_no_rows(self):
        for export_type, sheet_title in SHEET_TITLES.items():
            with self.subTest(export_type=export_type):
                job = generate_export(self.empty_store, export_type, requested_by=None)
                self.assertEqual(job.row_count, 0)
                ws = _workbook(job)[sheet_title]
                header = [c.value for c in ws[1]]
                self.assertTrue(all(header))
                self.assertGreaterEqual(len(header), 8)
                self.assertEqual(ws.freeze_panes, "A2")
                self.assertTrue(ws.sheet_view.rightToLeft)
                message = ws["A2"].value
                self.assertTrue(message and ("هیچ" in message or "هنوز" in message), message)
                self.assertIn("A2", [str(r).split(":")[0] for r in ws.merged_cells.ranges])
                guide = _workbook(job)["راهنما"]
                facts = {row[0]: row[1] for row in sheet_values(guide) if row[0] and len(row) > 1}
                self.assertEqual(facts["تعداد ردیف‌ها"], 0)


class DirectDownloadViewTests(ExportTestCase):
    """«دریافت فایل اکسل»: the XLSX is the HTTP response; nothing is retained."""

    def _post(self, export_type=ExportJob.ExportType.PRODUCTS):
        return self.client.post(reverse("dashboard:export-create"), {"export_type": export_type})

    def test_post_returns_the_xlsx_attachment_in_the_same_response(self):
        response = self._post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], XLSX_MIME)
        disposition = response["Content-Disposition"]
        self.assertTrue(disposition.startswith("attachment;"))
        self.assertRegex(disposition, r'filename="rastisi-products-\d{4}-\d{2}-\d{2}\.xlsx"')
        self.assertIn("no-store", response["Cache-Control"])
        body = response.content
        self.assertEqual(body[:2], b"PK")
        self.assertEqual(response["Content-Length"], str(len(body)))
        self.assertEqual(open_workbook(body)["کالاها"]["B2"].value, "SKU-EXP-1")

    def test_every_export_type_downloads_directly_with_xlsx_mime(self):
        for export_type, sheet_title in SHEET_TITLES.items():
            with self.subTest(export_type=export_type):
                response = self._post(export_type)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Content-Type"], XLSX_MIME)
                self.assertIn(f"rastisi-{export_type}-", response["Content-Disposition"])
                self.assertEqual(open_workbook(response.content).sheetnames, [sheet_title, "راهنما"])

    def test_no_file_is_stored_and_job_keeps_only_metadata(self):
        from apps.core.storage import private_storage

        exports_dir = f"exports/{self.store.pk}"

        def stored():
            return set(private_storage.listdir(exports_dir)[1]) if private_storage.exists(exports_dir) else set()

        before = stored()
        response = self._post()
        self.assertEqual(response.status_code, 200)
        job = ExportJob.objects.get(store=self.store)
        self.assertEqual(job.status, ExportJob.Status.COMPLETED)
        self.assertEqual(job.row_count, 1)
        self.assertFalse(job.file)
        self.assertIsNone(job.expires_at)
        self.assertEqual(job.requested_by, self.owner)
        self.assertEqual(stored(), before)  # no new file anywhere under the store's export folder
        # nothing downloadable later: the legacy download URL has nothing to serve
        later = self.client.get(reverse("dashboard:export-download", args=[job.pk]))
        self.assertEqual(later.status_code, 404)

    def test_audit_entry_is_truthful_about_direct_delivery(self):
        self._post()
        entry = AuditLogEntry.objects.get(store=self.store, action_code="export.completed")
        self.assertIn("direct_download", entry.after_summary)
        self.assertIn("retained", entry.after_summary)

    def test_export_page_has_direct_download_actions_and_no_history_table(self):
        response = self.client.get(reverse("dashboard:export-list"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertContains(response, "دریافت فایل اکسل")
        self.assertContains(response, "خروج اطلاعات")
        self.assertContains(response, "فایل روی راستی‌سی نگهداری نمی‌شود")
        self.assertEqual(html.count('name="export_type"'), 5)
        for label in ("کالاها", "تنوع‌ها", "موجودی انبار", "مشتریان", "سفارش‌ها"):
            self.assertIn(label, html)
        self.assertNotIn("تاریخچه‌ی صادرات", html)
        self.assertNotIn("ساختِ فایلِ اکسل", html)
        self.assertNotIn("صادراتِ داده", html)
        # privacy note only for customer/order cards
        self.assertEqual(html.count("اطلاعاتِ شخصیِ مشتریان"), 2)

    def test_unknown_export_type_is_rejected_without_a_job(self):
        response = self._post("nonsense")
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ExportJob.objects.filter(store=self.store).exists())

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(reverse("dashboard:export-create")).status_code, 405)

    def test_failed_generation_consumes_nothing_and_is_audited(self):
        from unittest import mock

        from apps.subscriptions.services import enforcement

        with mock.patch(
            "apps.core.services.export_service.build_export_workbook", side_effect=RuntimeError("boom"),
        ), mock.patch.object(enforcement, "consume_export") as consume:
            response = self._post()
        self.assertEqual(response.status_code, 302)  # back to the page with a message
        consume.assert_not_called()
        job = ExportJob.objects.get(store=self.store)
        self.assertEqual(job.status, ExportJob.Status.FAILED)
        self.assertFalse(job.file)
        self.assertTrue(AuditLogEntry.objects.filter(store=self.store, action_code="export.failed").exists())
        self.assertFalse(AuditLogEntry.objects.filter(store=self.store, action_code="export.completed").exists())

    def test_customers_selected_bulk_export_downloads_directly_too(self):
        response = self.client.post(reverse("dashboard:customer-bulk-action"), {
            "bulk_action": "export-selected", "customer_ids": [str(self.customer.pk)],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], XLSX_MIME)
        self.assertFalse(ExportJob.objects.get(store=self.store).file)


class ExportPermissionTests(ExportTestCase):
    def test_content_editor_cannot_export(self):
        self._login_as(StoreMembership.Role.CONTENT_EDITOR, "1")
        response = self.client.post(
            reverse("dashboard:export-create"), {"export_type": ExportJob.ExportType.PRODUCTS},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(ExportJob.objects.filter(store=self.store).exists())

    def test_catalog_manager_cannot_export_customers(self):
        self._login_as(StoreMembership.Role.CATALOG_MANAGER, "2")
        response = self.client.post(
            reverse("dashboard:export-create"), {"export_type": ExportJob.ExportType.CUSTOMERS},
        )
        self.assertEqual(response.status_code, 403)

    def test_order_manager_can_export_customers(self):
        self._login_as(StoreMembership.Role.ORDER_MANAGER, "3")
        response = self.client.post(
            reverse("dashboard:export-create"), {"export_type": ExportJob.ExportType.CUSTOMERS},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], XLSX_MIME)

    def test_analyst_cannot_export_customers(self):
        self._login_as(StoreMembership.Role.ANALYST, "4")
        response = self.client.post(
            reverse("dashboard:export-create"), {"export_type": ExportJob.ExportType.CUSTOMERS},
        )
        self.assertEqual(response.status_code, 403)

    def test_page_only_offers_types_the_member_may_export(self):
        self._login_as(StoreMembership.Role.CATALOG_MANAGER, "5")
        response = self.client.get(reverse("dashboard:export-list"))
        types = [item["value"] for item in response.context["export_types"]]
        self.assertNotIn("customers", types)
        self.assertIn("products", types)

    def test_anonymous_denied(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("dashboard:export-list")).status_code, 302)
        response = self.client.post(reverse("dashboard:export-create"), {"export_type": "products"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ExportJob.objects.filter(store=self.store).exists())


class LegacyRetainedExportTests(ExportTestCase):
    """Files created before direct download stay downloadable until their own expiry."""

    def _legacy_job(self, *, days=1, store=None, name="legacy-test.csv", payload=b"a,b\n1,2\n"):
        from django.core.files.base import ContentFile

        from apps.core.storage import private_storage

        store = store or self.store
        stored = private_storage.save(f"exports/{store.pk}/{name}", ContentFile(payload))
        self.addCleanup(private_storage.delete, stored)
        return ExportJob.objects.create(
            store=store, export_type=ExportJob.ExportType.PRODUCTS, status=ExportJob.Status.COMPLETED,
            expires_at=timezone.now() + timezone.timedelta(days=days), file=stored, row_count=1,
        )

    def test_unexpired_legacy_csv_still_downloads_with_its_real_type(self):
        job = self._legacy_job()
        response = self.client.get(reverse("dashboard:export-download", args=[job.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn(f"products-{job.pk}.csv", response["Content-Disposition"])
        response.close()

    def test_legacy_xlsx_downloads_as_xlsx_and_is_listed(self):
        job = self._legacy_job(name="legacy.xlsx", payload=b"PK-legacy")
        response = self.client.get(reverse("dashboard:export-download", args=[job.pk]))
        self.assertEqual(response["Content-Type"], XLSX_MIME)
        response.close()
        page = self.client.get(reverse("dashboard:export-list"))
        self.assertEqual([j.pk for j in page.context["legacy_jobs"]], [job.pk])
        self.assertContains(page, "فایل‌هایِ قدیمی")

    def test_expired_legacy_file_is_not_listed_and_cleanup_removes_it(self):
        from apps.core.services.export_service import mark_expired_jobs

        job = self._legacy_job(days=-1)
        page = self.client.get(reverse("dashboard:export-list"))
        self.assertEqual(list(page.context["legacy_jobs"]), [])
        self.assertEqual(mark_expired_jobs(store=self.store), 1)
        job.refresh_from_db()
        self.assertEqual(job.status, ExportJob.Status.EXPIRED)
        self.assertFalse(job.file)

    def test_metadata_only_job_is_not_downloadable(self):
        job = ExportJob.objects.create(
            store=self.store, export_type=ExportJob.ExportType.PRODUCTS, status=ExportJob.Status.COMPLETED,
        )
        self.assertEqual(self.client.get(reverse("dashboard:export-download", args=[job.pk])).status_code, 404)

    def test_pending_job_404(self):
        job = ExportJob.objects.create(store=self.store, export_type=ExportJob.ExportType.PRODUCTS)
        self.assertEqual(self.client.get(reverse("dashboard:export-download", args=[job.pk])).status_code, 404)

    def test_new_exports_never_get_an_expiry_or_file(self):
        generate_export(self.store, ExportJob.ExportType.PRODUCTS, requested_by=self.owner)
        job = ExportJob.objects.get(store=self.store)
        self.assertIsNone(job.expires_at)
        self.assertFalse(job.file)

    def test_legacy_customer_file_needs_customer_export_permission(self):
        job = self._legacy_job()
        job.export_type = ExportJob.ExportType.CUSTOMERS
        job.save(update_fields=["export_type"])
        self._login_as(StoreMembership.Role.CATALOG_MANAGER, "6")
        self.assertEqual(self.client.get(reverse("dashboard:export-download", args=[job.pk])).status_code, 403)


class ExportTenantIsolationTests(ExportTestCase):
    def setUp(self):
        super().setUp()
        self.other_store = Store.objects.create(name="فروشگاه دیگر", slug="export-other-store")

    def test_cannot_download_other_stores_legacy_export(self):
        from django.core.files.base import ContentFile

        from apps.core.storage import private_storage

        stored = private_storage.save(f"exports/{self.other_store.pk}/iso.xlsx", ContentFile(b"PK"))
        self.addCleanup(private_storage.delete, stored)
        other_job = ExportJob.objects.create(
            store=self.other_store, export_type=ExportJob.ExportType.PRODUCTS, status=ExportJob.Status.COMPLETED,
            expires_at=timezone.now() + timezone.timedelta(days=1), file=stored,
        )
        response = self.client.get(reverse("dashboard:export-download", args=[other_job.pk]))
        self.assertEqual(response.status_code, 404)
        page = self.client.get(reverse("dashboard:export-list"))
        self.assertEqual(list(page.context["legacy_jobs"]), [])

    def test_products_export_never_includes_other_stores_products(self):
        other_vendor = Vendor.objects.create(store=self.other_store, name="ف", slug="v-other-exp")
        other_category = Category.objects.create(store=self.other_store, name="د", slug="c-other-exp")
        Product.objects.create(
            store=self.other_store, vendor=other_vendor, category=other_category,
            name="کالای فروشگاه دیگر", slug="other-store-product-exp", sku="SKU-OTHER-EXP",
            price=Decimal("1"), stock=1,
        )
        job = generate_export(self.store, ExportJob.ExportType.PRODUCTS, requested_by=self.owner)
        ws = _workbook(job)["کالاها"]
        cells = [str(c.value) for row in ws.iter_rows() for c in row if c.value is not None]
        self.assertNotIn("کالای فروشگاه دیگر", cells)
        self.assertNotIn("SKU-OTHER-EXP", cells)
        self.assertEqual(job.row_count, 1)

    def test_other_stores_data_never_appears_in_any_export_type(self):
        other_vendor = Vendor.objects.create(store=self.other_store, name="ف", slug="v-other-exp2")
        other_category = Category.objects.create(store=self.other_store, name="د", slug="c-other-exp2")
        other_product = Product.objects.create(
            store=self.other_store, vendor=other_vendor, category=other_category,
            name="محصولِ محرمانه", slug="other-secret-exp", sku="SKU-SECRET", price=Decimal("1"), stock=1,
        )
        for export_type in SHEET_TITLES:
            job = generate_export(self.store, export_type, requested_by=self.owner)
            blob = " ".join(
                str(c.value) for ws in _workbook(job).worksheets for row in ws.iter_rows() for c in row if c.value is not None
            )
            self.assertNotIn("محصولِ محرمانه", blob, export_type)
            self.assertNotIn("SKU-SECRET", blob, export_type)
        self.assertTrue(other_product.pk)
