"""موتورِ واردات (Import) — کالا/تنوع/موجودی — checkpoint 4B. فایلِ اصلی XLSX
است (``import_xlsx``: هدرها/مقدارهایِ فارسی ← کلیدهایِ داخلیِ همین ماژول)؛ CSV
برایِ سازگاری با فایل‌هایِ قدیمی همچنان پذیرفته می‌شود.

نگاه کنید به ADR-55 (چرخه‌ی عمرِ Job)، ADR-56 (اتمیکیِ دسته‌ای)، ADR-57
(تشخیصِ هویتِ پایدار)، ADR-58 (یکپارچگیِ سرویسِ کالا)، ADR-59 (تنوع و
موتورِ تنوع)، ADR-60 (موجودی و ایمنیِ رزرو)، ADR-61 (idempotency) در
``SAAS_DOMAIN_DECISIONS.md``.

**قاعده‌ی طلایی**: پیش‌نمایش (dry-run) و اجرا از دقیقاً همان مسیرِ
اعتبارسنجی عبور می‌کنند — ``_validate_product_row``/``_validate_variant_row``/
``_validate_inventory_row`` هیچ‌گاه دو نسخه ندارند؛ فقط پارامترِ
``dry_run`` تعیین می‌کند که آیا در انتها چیزی در دیتابیس نوشته شود یا نه."""

from dataclasses import dataclass, field as dataclass_field

from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Brand, Category, Product, ProductOption, ProductVariant, StockMovement, Warehouse
from apps.catalog.services.inventory_service import (
    InsufficientStockError,
    InvalidRestockWarehouseError,
    adjust_stock_manually,
    adjust_warehouse_stock,
)
from apps.catalog.services.variant_engine_service import VariantEngineError, generate_variants, set_default_variant
from apps.core.models import ImportJob, ImportRowResult
from apps.core.services.audit_service import record_audit_event
from apps.core.services import xlsx_utils
from apps.core.services.csv_utils import (
    CsvRowLimitExceededError,
    CsvUploadError,
    normalize_import_text,
    parse_import_bool,
    parse_import_decimal,
    parse_import_int,
    read_csv_rows_bounded,
)
from apps.core.utils import normalization_key
from apps.dashboard.services.catalog_admin_service import default_vendor, generate_unique_slug
from apps.orders.models import TaxClass

DEFAULT_BATCH_SIZE = 100
MAX_VARIANT_OPTION_AXES = 3
#: سقفِ تعدادِ ردیفِ خطا که برایِ یک Job در دیتابیس نگه داشته می‌شود
#: (checkpoint 4B §22) — ``ImportRowResult`` همیشه برایِ همه‌ی ردیف‌ها ساخته
#: می‌شود، اما اگر تعدادِ ردیف‌هایِ نامعتبر/ناموفق از این عدد بیشتر شود،
#: ``error_summary`` این را صریحاً اعلام می‌کند (نه این‌که بی‌صدا قطع شود).
MAX_STORED_ERROR_ROWS = 5_000

PRODUCT_STATUS_VALUES = {choice for choice, _ in Product.Status.choices}

#: تعریفِ ستون‌هایِ هر نوعِ واردات — منبعِ واحدِ حقیقت برایِ دانلودِ
#: قالبِ CSV و راهنمایِ UI (checkpoint 4B §19). ستونِ اول در هر فهرست،
#: ستونِ هدرِ فایلِ قالب است.
IMPORT_COLUMNS = {
    ImportJob.ImportType.PRODUCTS: [
        "product_id", "sku", "name", "slug", "barcode", "status", "brand_code", "category_code",
        "price", "stock", "weight_grams", "requires_shipping", "tax_class_code",
        "seo_title", "seo_description",
    ],
    ImportJob.ImportType.VARIANTS: [
        "product_id", "product_sku", "variant_id", "variant_sku", "barcode",
        "option_1_code", "option_1_value_code", "option_2_code", "option_2_value_code",
        "option_3_code", "option_3_value_code",
        "price", "compare_at_price", "cost", "stock", "weight_grams", "is_active", "is_default",
    ],
    ImportJob.ImportType.INVENTORY: [
        "warehouse_code", "product_id", "product_sku", "variant_id", "variant_sku",
        "mode", "quantity", "reason", "note",
    ],
}


class ImportServiceError(Exception):
    """خطای سطحِ Job (نه ردیف) — مثلاً حالتِ اجرا یا نوعِ واردات نامعتبر است."""


@dataclass
class RowOutcome:
    row_number: int
    source_identifier: str
    status: str  # valid / invalid / created / updated / skipped / failed
    errors: list = dataclass_field(default_factory=list)
    warnings: list = dataclass_field(default_factory=list)
    target_object_type: str = ""
    target_object_id: int | None = None
    normalized_data_summary: dict = dataclass_field(default_factory=dict)


# ================================================================== کالا (Product)

def _product_lookup_cache(store, rows: list[dict]) -> dict:
    """پیش‌واکشیِ یک‌جای مرجع‌هایِ Store-scoped — به‌جایِ یک کوئری به‌ازایِ
    هر سلولِ CSV (checkpoint 4B §26). فقط شناسه‌هایی که واقعاً در فایل
    ارجاع شده‌اند واکشی می‌شوند، نه کلِ کاتالوگ."""
    product_ids = set()
    skus = set()
    for row in rows:
        raw_id = normalize_import_text(row.get("product_id"))
        if raw_id.isdigit():
            product_ids.add(int(raw_id))
        sku = normalize_import_text(row.get("sku"))
        if sku:
            skus.add(sku)

    products_by_id = {
        p.pk: p for p in Product.objects.filter(store=store, pk__in=product_ids).select_related("brand", "category", "tax_class")
    }
    products_by_sku = {
        p.sku: p for p in Product.objects.filter(store=store, sku__in=skus).select_related("brand", "category", "tax_class")
    }
    foreign_product_ids = set(
        Product.objects.filter(pk__in=product_ids).exclude(store=store).values_list("pk", flat=True)
    )
    return {
        "products_by_id": products_by_id,
        "products_by_sku": products_by_sku,
        "foreign_product_ids": foreign_product_ids,
        "brands_by_slug": {b.slug: b for b in Brand.objects.filter(store=store)},
        "categories_by_slug": {c.slug: c for c in Category.objects.filter(store=store, parent__isnull=False)},
        "tax_classes_by_code": {t.code: t for t in TaxClass.objects.filter(store=store)},
        "default_vendor": default_vendor(store),
    }


def _resolve_product_identity(store, row: dict, *, cache: dict):
    """اولویتِ هویتِ پایدار (checkpoint 4B §7): شناسه‌ی Store-scoped >
    SKUِ Store-scoped > بدونِ تطبیق. یک شناسه‌ی متعلق به Store دیگر همیشه
    خطا است — هرگز بی‌صدا به SKU سقوط نمی‌کند."""
    raw_id = normalize_import_text(row.get("product_id"))
    if raw_id:
        if not raw_id.isdigit():
            return None, f"«product_id» نامعتبر است: {raw_id}"
        product_id = int(raw_id)
        if product_id in cache["foreign_product_ids"]:
            return None, "این شناسه‌ی کالا متعلق به فروشگاه دیگری است."
        product = cache["products_by_id"].get(product_id)
        if product is None:
            return None, f"کالایی با شناسه‌ی «{product_id}» در این فروشگاه یافت نشد."
        return product, None

    sku = normalize_import_text(row.get("sku"))
    if sku:
        return cache["products_by_sku"].get(sku), None

    return None, None


def _validate_product_row(row_number: int, row: dict, *, store, mode: str, cache: dict) -> tuple[RowOutcome, dict | None, "Product | None"]:
    """اعتبارسنجیِ یک ردیفِ واردات کالا — چه در پیش‌نمایش چه در اجرا صدا
    زده می‌شود. خروجی: (نتیجه، دیکشنریِ فیلدهایِ نرمال‌شده یا None اگر
    نامعتبر، Productِ هدف یا None اگر ایجادِ تازه لازم است)."""
    errors, warnings = [], []
    sku = normalize_import_text(row.get("sku"))
    source_identifier = normalize_import_text(row.get("product_id")) or sku or f"row-{row_number}"

    existing_product, identity_error = _resolve_product_identity(store, row, cache=cache)
    if identity_error:
        errors.append(identity_error)

    is_update = existing_product is not None
    if mode == ImportJob.Mode.CREATE_ONLY and is_update:
        errors.append("این ردیف با کالایِ موجود مطابقت دارد؛ حالتِ «فقط ایجاد» آن را رد می‌کند.")
    if mode == ImportJob.Mode.UPDATE_ONLY and not is_update and not identity_error:
        errors.append("این ردیف با هیچ کالایِ موجودی مطابقت ندارد؛ حالتِ «فقط به‌روزرسانی» آن را رد می‌کند.")

    name = normalize_import_text(row.get("name"))
    if not name and not is_update:
        errors.append("«name» برایِ ایجادِ کالایِ تازه الزامی است.")
    elif not name and is_update:
        name = existing_product.name

    if sku and not is_update:
        # SKU باید در همین Store یکتا باشد؛ برخوردِ آن با کالایِ دیگر (نه
        # همان کالایِ در حالِ به‌روزرسانی) خطاست.
        clashing = cache["products_by_sku"].get(sku)
        if clashing is not None and (existing_product is None or clashing.pk != existing_product.pk):
            errors.append(f"SKUِ «{sku}» قبلاً به کالایِ دیگری اختصاص دارد.")

    status = normalize_import_text(row.get("status")) or (existing_product.status if is_update else Product.Status.ACTIVE)
    if status not in PRODUCT_STATUS_VALUES:
        errors.append(f"وضعیتِ «{status}» نامعتبر است.")

    price = None
    try:
        price = parse_import_decimal(row.get("price"), field_name="قیمت")
    except ValueError as exc:
        errors.append(str(exc))
    if price is None and not is_update:
        errors.append("«price» برایِ ایجادِ کالایِ تازه الزامی است.")
    elif price is not None and price < 0:
        errors.append("قیمت نمی‌تواند منفی باشد.")

    stock = None
    try:
        stock = parse_import_int(row.get("stock"), field_name="موجودی")
    except ValueError as exc:
        errors.append(str(exc))
    if stock is not None and stock < 0:
        errors.append("موجودی نمی‌تواند منفی باشد.")

    weight_grams = None
    try:
        weight_grams = parse_import_int(row.get("weight_grams"), field_name="وزن")
    except ValueError as exc:
        errors.append(str(exc))

    requires_shipping = True
    try:
        requires_shipping = parse_import_bool(
            row.get("requires_shipping"),
            default=existing_product.requires_shipping if is_update else True,
        )
    except ValueError as exc:
        errors.append(str(exc))

    brand = None
    brand_code = normalize_import_text(row.get("brand_code"))
    if brand_code:
        brand = cache["brands_by_slug"].get(brand_code)
        if brand is None:
            errors.append(f"برندِ «{brand_code}» در این فروشگاه یافت نشد.")

    category = None
    category_code = normalize_import_text(row.get("category_code"))
    if category_code:
        category = cache["categories_by_slug"].get(category_code)
        if category is None:
            errors.append(f"دسته‌بندیِ «{category_code}» در این فروشگاه یافت نشد (یا زیردسته نیست).")
    elif not is_update:
        errors.append("«category_code» برایِ ایجادِ کالایِ تازه الزامی است.")

    tax_class = None
    tax_class_code = normalize_import_text(row.get("tax_class_code"))
    tax_class_cleared = False
    if tax_class_code:
        tax_class = cache["tax_classes_by_code"].get(tax_class_code)
        if tax_class is None:
            errors.append(f"دسته‌ی مالیاتیِ «{tax_class_code}» در این فروشگاه یافت نشد.")
        elif not tax_class.is_active:
            warnings.append(f"دسته‌ی مالیاتیِ «{tax_class_code}» غیرفعال است.")
    elif "tax_class_code" in row and is_update:
        tax_class_cleared = True  # explicit empty column value on update → clear override

    vendor = cache["default_vendor"]
    if not is_update and vendor is None:
        errors.append("این فروشگاه هنوز هیچ فروشنده‌ای ندارد؛ کالای تازه قابل‌ایجاد نیست.")

    if errors:
        outcome = RowOutcome(
            row_number=row_number, source_identifier=source_identifier, status=ImportRowResult.RowStatus.INVALID,
            errors=errors, warnings=warnings,
        )
        return outcome, None, existing_product

    normalized = {
        "name": name, "sku": sku, "slug": normalize_import_text(row.get("slug")),
        "barcode": normalize_import_text(row.get("barcode")),
        "status": status, "price": price, "stock": stock, "weight_grams": weight_grams,
        "requires_shipping": requires_shipping,
        "brand": brand, "category": category, "tax_class": tax_class, "tax_class_cleared": tax_class_cleared,
        "seo_title": normalize_import_text(row.get("seo_title")),
        "seo_description": normalize_import_text(row.get("seo_description")),
    }
    outcome = RowOutcome(
        row_number=row_number, source_identifier=source_identifier, status=ImportRowResult.RowStatus.VALID,
        warnings=warnings,
    )
    return outcome, normalized, existing_product


def _apply_product_row(*, store, normalized: dict, existing_product, vendor, actor) -> tuple[Product, bool]:
    """اعمالِ واقعیِ یک ردیفِ معتبر — فقط از مسیرِ سرویس/مدل (``full_clean``،
    ``generate_unique_slug``، ``adjust_stock_manually``) — هرگز موجودی را
    مستقیم نمی‌نویسد (checkpoint 4B §8/§10). ``vendor`` فقط برایِ ایجادِ
    کالایِ تازه لازم است (Store-scoped، از ``default_vendor`` در کش)."""
    is_create = existing_product is None
    product = existing_product or Product(store=store, vendor=vendor, category=normalized["category"])

    if not is_create and normalized["category"] is not None:
        product.category = normalized["category"]

    product.name = normalized["name"]
    if normalized["sku"]:
        product.sku = normalized["sku"]
    elif is_create:
        product.sku = ""
    product.slug = normalized["slug"] or generate_unique_slug(Product, normalized["name"], store=store, instance=product)
    if normalized["barcode"]:
        product.barcode = normalized["barcode"]
    product.status = normalized["status"]
    if normalized["weight_grams"] is not None:
        product.weight_grams = normalized["weight_grams"]
    product.requires_shipping = normalized["requires_shipping"]
    if normalized["brand"] is not None:
        product.brand = normalized["brand"]
    if normalized["tax_class"] is not None:
        product.tax_class = normalized["tax_class"]
    elif normalized["tax_class_cleared"]:
        product.tax_class = None
    if normalized["price"] is not None:
        product.price = normalized["price"]
    if normalized["seo_title"]:
        product.seo_title = normalized["seo_title"]
    if normalized["seo_description"]:
        product.seo_description = normalized["seo_description"]

    product.full_clean(exclude=["stock"])
    product.save()

    if normalized["stock"] is not None:
        adjust_stock_manually(store=store, product=product, new_stock=normalized["stock"], actor=actor, note="Import")

    return product, is_create


# ================================================================== تنوع (Variant)
#
# نگاه کنید به ADR-59. این کدبیس هیچ فیلدِ «کد»ی روی ProductOption/
# ProductOptionValue ندارد (فقط ``label``/``normalized_label``) — پس
# ستون‌هایِ ``option_N_code``/``option_N_value_code`` با تطبیقِ
# normalized_label حل می‌شوند، نه یک فیلدِ کدِ جداگانه (که وجود ندارد).
#
# موتورِ تنوع (``generate_variants``) رویِ *همه‌ی* مقادیرِ فعالِ محورهایِ
# کالا حاصل‌ضربِ دکارتی می‌سازد — نه فقط ترکیب‌هایِ ذکرشده در فایل. واردات
# تنوع هرگز محور/مقدارِ تازه نمی‌سازد (آن‌ها باید از پیش، از طریقِ UIِ
# محورهایِ تنوع، فعال شده باشند) — فقط از رویِ ترکیبِ مقادیرِ *موجود و
# فعال* شناسه می‌سازد، سپس (فقط اگر لازم باشد) ``generate_variants`` را
# یک‌بار به‌ازایِ هر کالا صدا می‌زند تا آن ترکیب واقعاً یک ردیفِ
# ProductVariant داشته باشد، و در انتها ستون‌هایِ فایل (SKU/قیمت/موجودی/...)
# را رویِ همان تنوع اعمال می‌کند.


def _variant_lookup_cache(store, rows: list[dict]) -> dict:
    product_ids, product_skus, variant_ids, variant_skus = set(), set(), set(), set()
    for row in rows:
        raw_pid = normalize_import_text(row.get("product_id"))
        if raw_pid.isdigit():
            product_ids.add(int(raw_pid))
        psku = normalize_import_text(row.get("product_sku"))
        if psku:
            product_skus.add(psku)
        raw_vid = normalize_import_text(row.get("variant_id"))
        if raw_vid.isdigit():
            variant_ids.add(int(raw_vid))
        vsku = normalize_import_text(row.get("variant_sku"))
        if vsku:
            variant_skus.add(vsku)

    products_by_id = {p.pk: p for p in Product.objects.filter(store=store, pk__in=product_ids)}
    products_by_sku = {p.sku: p for p in Product.objects.filter(store=store, sku__in=product_skus)}
    foreign_product_ids = set(
        Product.objects.filter(pk__in=product_ids).exclude(store=store).values_list("pk", flat=True)
    )

    all_products = list(products_by_id.values()) + list(products_by_sku.values())
    product_pks = {p.pk for p in all_products}

    variants_by_id = {
        v.pk: v for v in ProductVariant.objects.filter(store=store, pk__in=variant_ids).select_related("product")
    }
    variants_by_sku = {
        v.sku: v for v in ProductVariant.objects.filter(store=store, sku__in=variant_skus).select_related("product")
    }
    foreign_variant_ids = set(
        ProductVariant.objects.filter(pk__in=variant_ids).exclude(store=store).values_list("pk", flat=True)
    )

    options_by_product: dict[int, dict[str, ProductOption]] = {}
    values_by_option: dict[int, dict[str, "object"]] = {}
    existing_variants_by_combination: dict[int, dict[str, ProductVariant]] = {}
    legacy_products: set[int] = set()
    for product in Product.objects.filter(pk__in=product_pks).prefetch_related("options__values", "variants"):
        legacy = product.variants.filter(combination_key="").exists()
        if legacy:
            legacy_products.add(product.pk)
        options_by_product[product.pk] = {
            normalization_key(o.label): o for o in product.options.all() if o.is_active
        }
        for option in product.options.all():
            values_by_option[option.pk] = {
                normalization_key(v.label): v for v in option.values.all() if v.is_active
            }
        existing_variants_by_combination[product.pk] = {
            v.combination_key: v for v in product.variants.all() if v.combination_key
        }

    return {
        "products_by_id": products_by_id, "products_by_sku": products_by_sku,
        "foreign_product_ids": foreign_product_ids,
        "variants_by_id": variants_by_id, "variants_by_sku": variants_by_sku,
        "foreign_variant_ids": foreign_variant_ids,
        "options_by_product": options_by_product, "values_by_option": values_by_option,
        "existing_variants_by_combination": existing_variants_by_combination,
        "legacy_products": legacy_products,
        "regenerated_product_ids": set(),
    }


def _resolve_variant_parent_product(store, row: dict, *, cache: dict):
    raw_pid = normalize_import_text(row.get("product_id"))
    if raw_pid:
        if not raw_pid.isdigit():
            return None, f"«product_id» نامعتبر است: {raw_pid}"
        product_id = int(raw_pid)
        if product_id in cache["foreign_product_ids"]:
            return None, "این شناسه‌ی کالا متعلق به فروشگاه دیگری است."
        product = cache["products_by_id"].get(product_id)
        if product is None:
            return None, f"کالایی با شناسه‌ی «{product_id}» در این فروشگاه یافت نشد."
        return product, None

    psku = normalize_import_text(row.get("product_sku"))
    if psku:
        product = cache["products_by_sku"].get(psku)
        if product is None:
            return None, f"کالایی با SKUِ «{psku}» در این فروشگاه یافت نشد."
        return product, None

    return None, "یکی از «product_id» یا «product_sku» الزامی است."


def _resolve_variant_option_pairs(product, row: dict, *, cache: dict):
    """جفت‌هایِ (ProductOption، ProductOptionValue) را از رویِ ستون‌هایِ
    ``option_N_code``/``option_N_value_code`` حل می‌کند — فقط اگر محور/مقدار
    از پیش رویِ همین کالا فعال باشد (هرگز محور/مقدارِ تازه نمی‌سازد)."""
    pairs = []
    errors = []
    options_by_label = cache["options_by_product"].get(product.pk, {})
    for axis_index in range(1, MAX_VARIANT_OPTION_AXES + 1):
        option_code = normalize_import_text(row.get(f"option_{axis_index}_code"))
        value_code = normalize_import_text(row.get(f"option_{axis_index}_value_code"))
        if not option_code and not value_code:
            continue
        if not option_code or not value_code:
            errors.append(f"محورِ {axis_index}: هم کدِ محور و هم کدِ مقدار باید داده شوند.")
            continue
        option = options_by_label.get(normalization_key(option_code))
        if option is None:
            errors.append(f"محورِ «{option_code}» رویِ این کالا فعال نیست.")
            continue
        value = cache["values_by_option"].get(option.pk, {}).get(normalization_key(value_code))
        if value is None:
            errors.append(f"مقدارِ «{value_code}» برایِ محورِ «{option_code}» فعال نیست.")
            continue
        pairs.append((option, value))
    return pairs, errors


def _combination_key_for_pairs(pairs) -> str:
    return "-".join(str(value.pk) for _option, value in sorted(pairs, key=lambda pair: pair[1].pk))


def _validate_variant_row(row_number: int, row: dict, *, store, mode: str, cache: dict):
    errors, warnings = [], []
    source_identifier = (
        normalize_import_text(row.get("variant_id"))
        or normalize_import_text(row.get("variant_sku"))
        or f"row-{row_number}"
    )

    # ۱) ابتدا تنوع را (اگر شناسه‌ی تنوع/SKUِ تنوع داده شده) حل می‌کنیم — چون
    # یک ``variant_id`` معتبر خودش کالایِ والد را مشخص می‌کند و نیازی به
    # ذکرِ مجددِ ``product_id``/``product_sku`` نیست (checkpoint 4B §11).
    existing_variant = None
    raw_vid = normalize_import_text(row.get("variant_id"))
    variant_sku = normalize_import_text(row.get("variant_sku"))
    if raw_vid:
        if not raw_vid.isdigit():
            errors.append(f"«variant_id» نامعتبر است: {raw_vid}")
        else:
            variant_id = int(raw_vid)
            if variant_id in cache["foreign_variant_ids"]:
                errors.append("این شناسه‌ی تنوع متعلق به فروشگاه دیگری است.")
            else:
                existing_variant = cache["variants_by_id"].get(variant_id)
                if existing_variant is None:
                    errors.append(f"تنوعی با شناسه‌ی «{variant_id}» در این فروشگاه یافت نشد.")
    elif variant_sku:
        existing_variant = cache["variants_by_sku"].get(variant_sku)

    # ۲) کالایِ والد: مرجعِ صریح (product_id/product_sku) در اولویت است؛ در
    # نبودِ آن، از تنوعِ حل‌شده استخراج می‌شود. اگر هر دو داده شده باشند،
    # باید سازگار باشند.
    has_product_ref = bool(normalize_import_text(row.get("product_id")) or normalize_import_text(row.get("product_sku")))
    product = None
    if has_product_ref:
        product, product_error = _resolve_variant_parent_product(store, row, cache=cache)
        if product_error:
            errors.append(product_error)
    elif existing_variant is not None:
        product = existing_variant.product
    elif not errors:
        errors.append("یکی از «product_id»، «product_sku»، «variant_id» یا «variant_sku» الزامی است.")

    if existing_variant is not None and product is not None and existing_variant.product_id != product.pk:
        errors.append("این تنوع متعلق به کالایِ دیگری است.")

    if product is not None:
        source_identifier = source_identifier if raw_vid or variant_sku else f"{product.sku or product.pk}-row-{row_number}"
        if product.pk in cache["legacy_products"]:
            errors.append("این کالا هنوز تنوع‌هایِ تک‌محوره‌ی قدیمی دارد؛ موتورِ چندمحوره برایِ آن قابل‌اجرا نیست.")

    pairs, pair_errors = [], []
    combination_key = ""
    if not errors and product is not None:
        pairs, pair_errors = _resolve_variant_option_pairs(product, row, cache=cache)
        errors.extend(pair_errors)
        if pairs and not pair_errors:
            combination_key = _combination_key_for_pairs(pairs)
            if existing_variant is None:
                existing_variant = cache["existing_variants_by_combination"].get(product.pk, {}).get(combination_key)

    is_update = existing_variant is not None
    if mode == ImportJob.Mode.CREATE_ONLY and is_update:
        errors.append("این ردیف با تنوعِ موجود مطابقت دارد؛ حالتِ «فقط ایجاد» آن را رد می‌کند.")
    if mode == ImportJob.Mode.UPDATE_ONLY and not is_update:
        errors.append("این ردیف با هیچ تنوعِ موجودی مطابقت ندارد؛ حالتِ «فقط به‌روزرسانی» آن را رد می‌کند.")
    if not is_update and not combination_key and not errors:
        errors.append("برایِ ایجادِ تنوعِ تازه، محورها/مقادیرِ آن (option_N_code/option_N_value_code) الزامی است.")

    if variant_sku and (existing_variant is None or existing_variant.sku != variant_sku):
        clashing = cache["variants_by_sku"].get(variant_sku)
        if clashing is not None and (existing_variant is None or clashing.pk != existing_variant.pk):
            errors.append(f"SKUِ تنوعِ «{variant_sku}» قبلاً به تنوعِ دیگری اختصاص دارد.")

    extra_price = compare_at_price = cost = stock = weight_grams = None
    try:
        extra_price = parse_import_decimal(row.get("price"), field_name="تغییرِ قیمت")
    except ValueError as exc:
        errors.append(str(exc))
    try:
        compare_at_price = parse_import_decimal(row.get("compare_at_price"), field_name="قیمتِ مقایسه‌ای")
    except ValueError as exc:
        errors.append(str(exc))
    try:
        cost = parse_import_decimal(row.get("cost"), field_name="بهایِ تمام‌شده")
    except ValueError as exc:
        errors.append(str(exc))
    try:
        stock = parse_import_int(row.get("stock"), field_name="موجودی")
        if stock is not None and stock < 0:
            errors.append("موجودی نمی‌تواند منفی باشد.")
    except ValueError as exc:
        errors.append(str(exc))
    try:
        weight_grams = parse_import_int(row.get("weight_grams"), field_name="وزن")
    except ValueError as exc:
        errors.append(str(exc))

    is_active = True
    try:
        is_active = parse_import_bool(row.get("is_active"), default=existing_variant.is_active if is_update else True)
    except ValueError as exc:
        errors.append(str(exc))
    is_default = False
    try:
        is_default = parse_import_bool(row.get("is_default"), default=False)
    except ValueError as exc:
        errors.append(str(exc))

    if errors:
        outcome = RowOutcome(
            row_number=row_number, source_identifier=source_identifier,
            status=ImportRowResult.RowStatus.INVALID, errors=errors, warnings=warnings,
        )
        return outcome, None, existing_variant, product

    normalized = {
        "product": product, "pairs": pairs, "combination_key": combination_key,
        "sku": variant_sku, "barcode": normalize_import_text(row.get("barcode")),
        "extra_price": extra_price, "compare_at_price": compare_at_price, "cost": cost,
        "stock": stock, "weight_grams": weight_grams, "is_active": is_active, "is_default": is_default,
    }
    outcome = RowOutcome(
        row_number=row_number, source_identifier=source_identifier,
        status=ImportRowResult.RowStatus.VALID, warnings=warnings,
    )
    return outcome, normalized, existing_variant, product


def _apply_variant_row(*, store, normalized: dict, existing_variant, cache: dict, actor):
    product = normalized["product"]
    variant = existing_variant

    if variant is None:
        # ترکیب هنوز رویِ کالا وجود ندارد؛ محورها/مقادیر از پیش فعال‌اند
        # (اعتبارسنجی این را تضمین کرده) — فقط یک‌بار به‌ازایِ این کالا
        # ``generate_variants`` صدا زده می‌شود تا این ترکیب هم یک
        # ProductVariant واقعی داشته باشد (idempotent، هیچ ترکیبِ دیگری را
        # حذف/دوباره نمی‌سازد).
        if product.pk not in cache["regenerated_product_ids"]:
            generate_variants(product)
            cache["regenerated_product_ids"].add(product.pk)
            cache["existing_variants_by_combination"][product.pk] = {
                v.combination_key: v for v in product.variants.filter(combination_key__gt="")
            }
        variant = cache["existing_variants_by_combination"].get(product.pk, {}).get(normalized["combination_key"])
        if variant is None:
            raise VariantEngineError("این ترکیب پس از بازتولیدِ تنوع‌ها هم ساخته نشد.")
        is_create = True
    else:
        is_create = False

    if normalized["sku"]:
        variant.sku = normalized["sku"]
    if normalized["barcode"]:
        variant.barcode = normalized["barcode"]
    if normalized["extra_price"] is not None:
        variant.extra_price = normalized["extra_price"]
    if normalized["compare_at_price"] is not None:
        variant.compare_at_price = normalized["compare_at_price"]
    if normalized["cost"] is not None:
        variant.cost = normalized["cost"]
    variant.is_active = normalized["is_active"]
    variant.full_clean(exclude=["normalized_attribute", "normalized_value"])
    variant.save()

    if normalized["stock"] is not None:
        adjust_stock_manually(store=store, product=product, variant=variant, new_stock=normalized["stock"], actor=actor, note="Import")

    if normalized["is_default"] and variant.is_active:
        set_default_variant(product, variant)

    cache["variants_by_sku"][variant.sku] = variant
    cache["variants_by_id"][variant.pk] = variant
    cache["existing_variants_by_combination"].setdefault(product.pk, {})[variant.combination_key] = variant

    return variant, is_create


@transaction.atomic
def _execute_variant_batch(store, batch, *, mode, cache, actor, dry_run: bool) -> list[RowOutcome]:
    from django.core.exceptions import ValidationError

    outcomes = []
    for row_number, row in batch:
        outcome, normalized, existing_variant, _product = _validate_variant_row(
            row_number, row, store=store, mode=mode, cache=cache,
        )
        if normalized is None:
            outcomes.append(outcome)
            continue
        if dry_run:
            outcome.normalized_data_summary = {"action": "update" if existing_variant is not None else "create"}
            outcomes.append(outcome)
            continue
        try:
            with transaction.atomic():  # savepoint به‌ازایِ هر ردیف (ADR-56)
                variant, is_create = _apply_variant_row(
                    store=store, normalized=normalized, existing_variant=existing_variant, cache=cache, actor=actor,
                )
            outcome.status = ImportRowResult.RowStatus.CREATED if is_create else ImportRowResult.RowStatus.UPDATED
            outcome.target_object_type = "ProductVariant"
            outcome.target_object_id = variant.pk
        except (ValidationError, VariantEngineError) as exc:
            outcome.status = ImportRowResult.RowStatus.FAILED
            if isinstance(exc, ValidationError):
                outcome.errors.extend(sum(exc.message_dict.values(), []) if hasattr(exc, "message_dict") else exc.messages)
            else:
                outcome.errors.append(str(exc))
        except Exception as exc:  # noqa: BLE001
            outcome.status = ImportRowResult.RowStatus.FAILED
            outcome.errors.append(str(exc))
        outcomes.append(outcome)
    return outcomes


# ================================================================== موجودی (Inventory)
#
# نگاه کنید به ADR-60. هیچ ردیفی مستقیماً ``WarehouseInventory``/
# ``Product.stock``/``ProductVariant.stock`` را نمی‌نویسد — همه از
# ``inventory_service.adjust_warehouse_stock`` عبور می‌کنند که خودش
# ``StockMovement`` می‌سازد، تجمیعِ موجودی را هم‌راستا نگه می‌دارد، و
# تغییری که موجودیِ در دسترس را زیرِ رزروِ فعال ببرد رد می‌کند.

INVENTORY_ROW_MODES = {"adjustment", "set_on_hand"}


def _inventory_lookup_cache(store, rows: list[dict]) -> dict:
    warehouse_codes, product_ids, product_skus, variant_ids, variant_skus = set(), set(), set(), set(), set()
    for row in rows:
        code = normalize_import_text(row.get("warehouse_code"))
        if code:
            warehouse_codes.add(code)
        raw_pid = normalize_import_text(row.get("product_id"))
        if raw_pid.isdigit():
            product_ids.add(int(raw_pid))
        psku = normalize_import_text(row.get("product_sku"))
        if psku:
            product_skus.add(psku)
        raw_vid = normalize_import_text(row.get("variant_id"))
        if raw_vid.isdigit():
            variant_ids.add(int(raw_vid))
        vsku = normalize_import_text(row.get("variant_sku"))
        if vsku:
            variant_skus.add(vsku)

    return {
        "warehouses_by_code": {w.code: w for w in Warehouse.objects.filter(store=store, code__in=warehouse_codes)},
        "products_by_id": {p.pk: p for p in Product.objects.filter(store=store, pk__in=product_ids)},
        "products_by_sku": {p.sku: p for p in Product.objects.filter(store=store, sku__in=product_skus)},
        "foreign_product_ids": set(
            Product.objects.filter(pk__in=product_ids).exclude(store=store).values_list("pk", flat=True)
        ),
        "variants_by_id": {
            v.pk: v for v in ProductVariant.objects.filter(store=store, pk__in=variant_ids).select_related("product")
        },
        "variants_by_sku": {
            v.sku: v for v in ProductVariant.objects.filter(store=store, sku__in=variant_skus).select_related("product")
        },
        "foreign_variant_ids": set(
            ProductVariant.objects.filter(pk__in=variant_ids).exclude(store=store).values_list("pk", flat=True)
        ),
    }


def _validate_inventory_row(row_number: int, row: dict, *, store, mode: str, cache: dict):
    errors, warnings = [], []
    source_identifier = (
        normalize_import_text(row.get("variant_sku"))
        or normalize_import_text(row.get("product_sku"))
        or normalize_import_text(row.get("product_id"))
        or f"row-{row_number}"
    )

    warehouse = None
    warehouse_code = normalize_import_text(row.get("warehouse_code"))
    if not warehouse_code:
        errors.append("«warehouse_code» الزامی است.")
    else:
        warehouse = cache["warehouses_by_code"].get(warehouse_code)
        if warehouse is None:
            errors.append(f"انباری با کدِ «{warehouse_code}» در این فروشگاه یافت نشد.")

    # کالا (الزامی)
    product = None
    raw_pid = normalize_import_text(row.get("product_id"))
    psku = normalize_import_text(row.get("product_sku"))
    if raw_pid:
        if not raw_pid.isdigit():
            errors.append(f"«product_id» نامعتبر است: {raw_pid}")
        elif int(raw_pid) in cache["foreign_product_ids"]:
            errors.append("این شناسه‌ی کالا متعلق به فروشگاه دیگری است.")
        else:
            product = cache["products_by_id"].get(int(raw_pid))
            if product is None:
                errors.append(f"کالایی با شناسه‌ی «{raw_pid}» در این فروشگاه یافت نشد.")
    elif psku:
        product = cache["products_by_sku"].get(psku)
        if product is None:
            errors.append(f"کالایی با SKUِ «{psku}» در این فروشگاه یافت نشد.")
    else:
        errors.append("یکی از «product_id» یا «product_sku» الزامی است.")

    # تنوع (اختیاری) — اگر داده شود باید به همین کالا تعلق داشته باشد
    variant = None
    raw_vid = normalize_import_text(row.get("variant_id"))
    vsku = normalize_import_text(row.get("variant_sku"))
    if raw_vid:
        if not raw_vid.isdigit():
            errors.append(f"«variant_id» نامعتبر است: {raw_vid}")
        elif int(raw_vid) in cache["foreign_variant_ids"]:
            errors.append("این شناسه‌ی تنوع متعلق به فروشگاه دیگری است.")
        else:
            variant = cache["variants_by_id"].get(int(raw_vid))
            if variant is None:
                errors.append(f"تنوعی با شناسه‌ی «{raw_vid}» در این فروشگاه یافت نشد.")
    elif vsku:
        variant = cache["variants_by_sku"].get(vsku)
        if variant is None:
            errors.append(f"تنوعی با SKUِ «{vsku}» در این فروشگاه یافت نشد.")
    if variant is not None and product is not None and variant.product_id != product.pk:
        errors.append("این تنوع متعلق به کالایِ دیگری است.")

    row_mode = normalize_import_text(row.get("mode")).lower() or "adjustment"
    if row_mode not in INVENTORY_ROW_MODES:
        errors.append(f"حالتِ ردیفِ «{row_mode}» نامعتبر است (فقط adjustment/set_on_hand).")

    quantity = None
    try:
        quantity = parse_import_int(row.get("quantity"), field_name="تعداد")
    except ValueError as exc:
        errors.append(str(exc))
    if quantity is None:
        errors.append("«quantity» الزامی است.")
    elif row_mode == "set_on_hand" and quantity < 0:
        errors.append("در حالتِ set_on_hand، تعداد نمی‌تواند منفی باشد.")

    if errors:
        outcome = RowOutcome(
            row_number=row_number, source_identifier=source_identifier,
            status=ImportRowResult.RowStatus.INVALID, errors=errors, warnings=warnings,
        )
        return outcome, None
    normalized = {
        "warehouse": warehouse, "product": product, "variant": variant, "row_mode": row_mode,
        "quantity": quantity, "reason": normalize_import_text(row.get("reason")),
        "note": normalize_import_text(row.get("note")),
    }
    outcome = RowOutcome(
        row_number=row_number, source_identifier=source_identifier,
        status=ImportRowResult.RowStatus.VALID, warnings=warnings,
    )
    return outcome, normalized


def _apply_inventory_row(*, store, normalized: dict, actor):
    """موجودی را از مسیرِ ``adjust_warehouse_stock`` تغییر می‌دهد — reasonِ
    آزادِ CSV و noteِ CSV هر دو در ``StockMovement.note`` حفظ می‌شوند، اما
    ``StockMovement.reason`` همیشه ``IMPORT_ADJUSTMENT`` است تا تاکسونومیِ
    دلیلِ دفترِ موجودی دست‌نخورده بماند."""
    note_parts = [part for part in (normalized["reason"], normalized["note"]) if part]
    combined_note = " — ".join(note_parts)[:500] if note_parts else "Import"
    movement = adjust_warehouse_stock(
        store=store, warehouse=normalized["warehouse"], product=normalized["product"],
        variant=normalized["variant"], mode=normalized["row_mode"], quantity=normalized["quantity"],
        reason=StockMovement.Reason.IMPORT_ADJUSTMENT, actor=actor, note=combined_note,
    )
    return movement


@transaction.atomic
def _execute_inventory_batch(store, batch, *, mode, cache, actor, dry_run: bool) -> list[RowOutcome]:
    outcomes = []
    for row_number, row in batch:
        outcome, normalized = _validate_inventory_row(row_number, row, store=store, mode=mode, cache=cache)
        if normalized is None:
            outcomes.append(outcome)
            continue
        if dry_run:
            outcome.normalized_data_summary = {"action": "update"}
            outcomes.append(outcome)
            continue
        try:
            movement = _apply_inventory_row(store=store, normalized=normalized, actor=actor)
            target = normalized["variant"] or normalized["product"]
            outcome.status = ImportRowResult.RowStatus.UPDATED
            outcome.target_object_type = "ProductVariant" if normalized["variant"] else "Product"
            outcome.target_object_id = target.pk
            if movement is None:
                outcome.warnings.append("دلتا صفر بود؛ هیچ تغییری اعمال نشد.")
                outcome.status = ImportRowResult.RowStatus.SKIPPED
        except (InsufficientStockError, InvalidRestockWarehouseError, ValueError) as exc:
            outcome.status = ImportRowResult.RowStatus.FAILED
            outcome.errors.append(str(exc))
        except Exception as exc:  # noqa: BLE001
            outcome.status = ImportRowResult.RowStatus.FAILED
            outcome.errors.append(str(exc))
        outcomes.append(outcome)
    return outcomes


# ================================================================== موتورِ اجرایِ عمومی


def _row_identifier(row: dict, number: int) -> str:
    for key in ("variant_sku", "product_sku", "sku", "product_id", "variant_id"):
        value = normalize_import_text(row.get(key))
        if value:
            return value
    return f"row-{number}"

def _chunked(sequence: list, size: int):
    for start in range(0, len(sequence), size):
        yield sequence[start:start + size]


@transaction.atomic
def _execute_product_batch(store, batch, *, mode, cache, actor, dry_run: bool) -> list[RowOutcome]:
    from django.core.exceptions import ValidationError

    outcomes = []
    for row_number, row in batch:
        outcome, normalized, existing_product = _validate_product_row(row_number, row, store=store, mode=mode, cache=cache)
        if normalized is None:
            outcomes.append(outcome)
            continue
        if dry_run:
            outcome.normalized_data_summary = {"action": "update" if existing_product is not None else "create"}
            outcomes.append(outcome)
            continue
        # بودجه‌ی ساختِ کالا (§16): اگر این ردیف یک کالایِ تازه می‌سازد و
        # بودجه پُر شده، همین ردیف ناموفق می‌شود (نه کلِ واردات) — ردیف‌هایِ
        # به‌روزرسانی مشمول نیستند. بودجه‌ی ``None`` یعنی نامحدود.
        budget = cache.get("_product_create_budget")
        if existing_product is None and budget is not None and budget <= 0:
            outcome.status = ImportRowResult.RowStatus.FAILED
            outcome.errors.append(
                "سقفِ پلنِ فعلیِ شما برایِ تعدادِ کالاها پُر شده است؛ این کالایِ تازه وارد نشد."
            )
            outcomes.append(outcome)
            continue
        try:
            # savepoint به‌ازایِ هر ردیف: یک خطایِ سطحِ دیتابیس در اعمالِ این
            # ردیف فقط تا همین savepoint برمی‌گردد و تراکنشِ batch را برایِ
            # ردیف‌هایِ بعدی سالم نگه می‌دارد (ADR-56).
            with transaction.atomic():
                product, is_create = _apply_product_row(
                    store=store, normalized=normalized, existing_product=existing_product,
                    vendor=cache["default_vendor"], actor=actor,
                )
            if is_create and budget is not None:
                cache["_product_create_budget"] = budget - 1
            outcome.status = ImportRowResult.RowStatus.CREATED if is_create else ImportRowResult.RowStatus.UPDATED
            outcome.target_object_type = "Product"
            outcome.target_object_id = product.pk
            # کش را برایِ ردیف‌هایِ بعدیِ همین اجرا هم‌راستا نگه می‌دارد (مثلاً
            # دو ردیف که یکی کالا می‌سازد و دیگری با SKUِ همان کالا آن را
            # به‌روزرسانی می‌کند).
            cache["products_by_sku"][product.sku] = product
            cache["products_by_id"][product.pk] = product
        except ValidationError as exc:
            outcome.status = ImportRowResult.RowStatus.FAILED
            messages = sum(exc.message_dict.values(), []) if hasattr(exc, "message_dict") else exc.messages
            outcome.errors.extend(messages)
        except Exception as exc:  # noqa: BLE001 — یک ردیفِ ناموفق نباید کل Job را متوقف کند
            outcome.status = ImportRowResult.RowStatus.FAILED
            outcome.errors.append(str(exc))
        outcomes.append(outcome)
    return outcomes


_BATCH_EXECUTORS = {
    ImportJob.ImportType.PRODUCTS: (_product_lookup_cache, _execute_product_batch),
    ImportJob.ImportType.VARIANTS: (_variant_lookup_cache, _execute_variant_batch),
    ImportJob.ImportType.INVENTORY: (_inventory_lookup_cache, _execute_inventory_batch),
}


def run_import(job: ImportJob, rows: list[dict], *, actor, batch_size: int = DEFAULT_BATCH_SIZE) -> ImportJob:
    """موتورِ عمومیِ پیش‌نمایش/اجرا — برایِ هر سه نوعِ واردات یکسان است
    (checkpoint 4B §16). ``job.dry_run`` تعیین می‌کند پیش‌نمایش است یا اجرا؛
    ``job.status`` بر همان اساس تنظیم می‌شود. هر batch در تراکنشِ اتمیکِ
    خودش اجرا می‌شود — شکستِ یک batch سایرِ batchهایِ موفق را برنمی‌گرداند
    (ADR-56)."""
    if job.import_type not in _BATCH_EXECUTORS:
        raise ImportServiceError(f"نوعِ واردات «{job.import_type}» پشتیبانی نمی‌شود.")
    build_cache, execute_batch = _BATCH_EXECUTORS[job.import_type]

    job.status = ImportJob.Status.VALIDATING if job.dry_run else ImportJob.Status.PROCESSING
    job.started_at = timezone.now()
    job.save(update_fields=["status", "started_at"])

    cache = build_cache(job.store, rows)
    # بودجه‌ی ساختِ کالا برایِ اجرا (نه پیش‌نمایش) در کش گذاشته می‌شود تا
    # واردات نتواند سقفِ عددیِ کالا را دور بزند (§16). ردیف‌هایِ به‌روزرسانی
    # بی‌اثر از این بودجه عبور می‌کنند؛ فقط ساختِ کالایِ تازه شمرده می‌شود.
    # تنوع‌ها از مسیرِ ``generate_variants`` (که خودش گیت دارد) عبور می‌کنند و
    # موجودی هرگز رکوردِ تازه نمی‌سازد، پس فقط واردات کالا بودجه لازم دارد.
    if not job.dry_run and job.import_type == ImportJob.ImportType.PRODUCTS:
        from apps.subscriptions.services.enforcement import product_creation_budget

        cache["_product_create_budget"] = product_creation_budget(job.store)
    # ردیف‌هایِ XLSX شماره‌ی واقعیِ ردیفِ اکسل را دارند (``__row_number__``)؛ ردیف‌هایِ
    # CSV همان شماره‌ی ترتیبی. ردیفی که خواندنِ فایل از پیش ردش کرده (مثلاً سلولِ
    # فرمولی) هرگز به اعتبارسنج نمی‌رسد.
    numbered_rows, pre_rejected = [], []
    for index, row in enumerate(rows, start=1):
        number = row.get("__row_number__") or index
        if row.get("__errors__"):
            pre_rejected.append(RowOutcome(
                row_number=number, source_identifier=_row_identifier(row, number),
                status=ImportRowResult.RowStatus.INVALID, errors=list(row["__errors__"]),
                warnings=list(row.get("__warnings__", [])),
            ))
        else:
            numbered_rows.append((number, row))

    all_outcomes: list[RowOutcome] = list(pre_rejected)
    for batch in _chunked(numbered_rows, batch_size):
        batch_outcomes = execute_batch(job.store, batch, mode=job.mode, cache=cache, actor=actor, dry_run=job.dry_run)
        warnings_by_number = {n: r["__warnings__"] for n, r in batch if r.get("__warnings__")}
        for outcome in batch_outcomes:
            if outcome.row_number in warnings_by_number:
                outcome.warnings = list(warnings_by_number[outcome.row_number]) + list(outcome.warnings)
        all_outcomes.extend(batch_outcomes)
    all_outcomes.sort(key=lambda o: o.row_number)

    ImportRowResult.objects.filter(import_job=job).delete()
    ImportRowResult.objects.bulk_create([
        ImportRowResult(
            import_job=job, row_number=o.row_number, source_identifier=o.source_identifier[:120],
            status=o.status, errors=o.errors, warnings=o.warnings,
            target_object_type=o.target_object_type, target_object_id=o.target_object_id,
            normalized_data_summary=o.normalized_data_summary,
        )
        for o in all_outcomes
    ])

    counts = {status: 0 for status in (
        ImportRowResult.RowStatus.VALID, ImportRowResult.RowStatus.INVALID,
        ImportRowResult.RowStatus.CREATED, ImportRowResult.RowStatus.UPDATED,
        ImportRowResult.RowStatus.SKIPPED, ImportRowResult.RowStatus.FAILED,
    )}
    for o in all_outcomes:
        counts[o.status] = counts.get(o.status, 0) + 1

    job.total_rows = len(all_outcomes)
    job.valid_rows = counts[ImportRowResult.RowStatus.VALID]
    job.invalid_rows = counts[ImportRowResult.RowStatus.INVALID]
    job.created_rows = counts[ImportRowResult.RowStatus.CREATED]
    job.updated_rows = counts[ImportRowResult.RowStatus.UPDATED]
    job.skipped_rows = counts[ImportRowResult.RowStatus.SKIPPED]
    job.failed_rows = counts[ImportRowResult.RowStatus.FAILED]
    job.completed_at = timezone.now()

    if job.dry_run:
        job.status = ImportJob.Status.PREVIEW_READY
    elif job.total_rows == 0:
        job.status = ImportJob.Status.FAILED
        job.error_summary = "فایل هیچ ردیفی نداشت."
    elif job.failed_rows == 0 and job.invalid_rows == 0:
        job.status = ImportJob.Status.COMPLETED
    elif job.created_rows == 0 and job.updated_rows == 0:
        job.status = ImportJob.Status.FAILED
        job.error_summary = f"{job.invalid_rows} ردیفِ نامعتبر، {job.failed_rows} ردیفِ ناموفق."
    else:
        job.status = ImportJob.Status.COMPLETED_WITH_ERRORS
        job.error_summary = f"{job.invalid_rows} ردیفِ نامعتبر، {job.failed_rows} ردیفِ ناموفق."

    job.save(update_fields=[
        "total_rows", "valid_rows", "invalid_rows", "created_rows", "updated_rows",
        "skipped_rows", "failed_rows", "completed_at", "status", "error_summary",
    ])

    action_code = "import.preview_completed" if job.dry_run else "import.execution_completed"
    record_audit_event(
        store=job.store, actor=actor, action_code=action_code,
        object_type="ImportJob", object_id=str(job.pk),
        object_label=f"{job.get_import_type_display()} — {job.total_rows} ردیف",
        after={
            "total_rows": job.total_rows, "valid_rows": job.valid_rows, "invalid_rows": job.invalid_rows,
            "created_rows": job.created_rows, "updated_rows": job.updated_rows,
            "skipped_rows": job.skipped_rows, "failed_rows": job.failed_rows, "status": job.status,
        },
    )
    return job


# ================================================================== چرخه‌ی عمرِ Job (آپلود/پیش‌نمایش/اجرا)

def create_import_job(store, *, import_type: str, uploaded_file, mode: str, requested_by, idempotency_key: str = "") -> ImportJob:
    """یک ``ImportJob`` تازه می‌سازد و فایلِ آپلودی (xlsx یا csv) را در
    ذخیره‌سازیِ خصوصی و *در قالبِ اصلیِ خودش* می‌نویسد — نگاه کنید به ADR-62.
    هرگز چیزی از فایل نمی‌خواند/پردازش نمی‌کند (آن کارِ ``run_preview``ست)؛ فقط
    ساختارِ امنِ فایل را بررسی می‌کند (پسوند/حجم/ZIP/ماکرو)."""
    if import_type not in ImportJob.ImportType.values:
        raise ImportServiceError(f"نوعِ واردات «{import_type}» نامعتبر است.")
    if mode not in ImportJob.Mode.values:
        raise ImportServiceError(f"حالتِ «{mode}» نامعتبر است.")
    # گیتِ قابلیتِ واردات (checkpoint 5A، §16) — اگر پلن واردات ندارد، حتی
    # آپلود هم مجاز نیست. سقفِ ردیف/بودجه‌ی ساختِ کالا هنگامِ اجرا بررسی می‌شوند.
    from apps.subscriptions.services.enforcement import enforce_import_allowed

    enforce_import_allowed(store)
    try:
        extension = xlsx_utils.validate_import_upload(uploaded_file)
    except (xlsx_utils.XlsxUploadError, CsvUploadError) as exc:
        # به یک خطایِ سطحِ Job تبدیل می‌شود تا فراخوان فقط یک نوع استثنا را
        # مدیریت کند (پیام همان است، برایِ نمایشِ مستقیم به کاربر امن).
        raise ImportServiceError(str(exc)) from exc
    if idempotency_key and ImportJob.objects.filter(store=store, idempotency_key=idempotency_key).exists():
        raise ImportServiceError("این کلیدِ یکتا قبلاً برایِ یک واردات دیگر استفاده شده است.")

    job = ImportJob.objects.create(
        store=store, import_type=import_type, original_filename=(uploaded_file.name or "")[:255],
        status=ImportJob.Status.UPLOADED, requested_by=requested_by, mode=mode,
        dry_run=True, idempotency_key=idempotency_key,
    )
    job.source_file.save(f"{import_type}-{job.pk}{extension}", uploaded_file, save=True)
    record_audit_event(
        store=store, actor=requested_by, action_code="import.uploaded",
        object_type="ImportJob", object_id=str(job.pk), object_label=job.original_filename,
        metadata={"import_type": import_type, "mode": mode, "format": extension.lstrip(".")},
    )
    return job


def job_source_format(job: ImportJob) -> str:
    """قالبِ واقعیِ فایلِ منبع (``xlsx`` یا ``csv``) از روی پسوندِ ذخیره‌شده."""
    return "xlsx" if (job.source_file.name or "").lower().endswith(".xlsx") else "csv"


def read_job_rows(job: ImportJob) -> list[dict]:
    """محتوایِ فایلِ منبعِ Job را به فهرستی از دیکشنری‌هایِ نرمال‌شده (با کلیدهایِ
    داخلی) تبدیل می‌کند — آپلود/پیش‌نمایش/اجرا هر سه از همین تابع می‌خوانند
    (بدونِ منطقِ موازیِ دوم). XLSX از لایه‌ی نگاشتِ ``import_xlsx`` می‌گذرد؛ CSV
    مثلِ قبل مستقیم خوانده می‌شود."""
    job.source_file.open("rb")
    try:
        if job_source_format(job) == "xlsx":
            from apps.dashboard.services import import_xlsx

            try:
                return import_xlsx.parse_xlsx_import(job.source_file, job.import_type, job.store).rows
            except (xlsx_utils.XlsxReadError, xlsx_utils.XlsxRowLimitExceededError) as exc:
                raise ImportServiceError(str(exc)) from exc
        try:
            return list(read_csv_rows_bounded(job.source_file))
        except (CsvUploadError, CsvRowLimitExceededError) as exc:
            raise ImportServiceError(str(exc)) from exc
    finally:
        job.source_file.close()


def run_preview(job: ImportJob, *, actor) -> ImportJob:
    """پیش‌نمایشِ (dry-run) یک Job — هرگز چیزی در دیتابیسِ کاتالوگ/موجودی
    نمی‌نویسد؛ فقط ``ImportRowResult``هایِ پیش‌نمایش را می‌سازد."""
    if job.status not in (ImportJob.Status.UPLOADED, ImportJob.Status.PREVIEW_READY):
        raise ImportServiceError("این Job دیگر قابلِ پیش‌نمایش نیست.")
    job.dry_run = True
    rows = read_job_rows(job)
    job = run_import(job, rows, actor=actor)
    _generate_error_report(job)  # پیش از اجرا هم می‌شود ردیف‌هایِ مشکل‌دار را اصلاح کرد
    return job


def run_execution(job: ImportJob, *, actor) -> ImportJob:
    """اجرایِ واقعیِ یک Job — نگاه کنید به ADR-61: یک Jobِ قبلاً
    تکمیل‌شده (هر یک از ``ImportJob.FINAL_STATUSES``) هرگز دوباره اجرا
    نمی‌شود، حتی اگر این تابع دوباره صدا زده شود (idempotent replay-safe)."""
    if job.status in ImportJob.FINAL_STATUSES:
        raise ImportServiceError("این Job قبلاً به پایان رسیده — دوباره اجرا نمی‌شود.")
    job.dry_run = False
    # بازبینیِ اشتراک هنگامِ اجرا (checkpoint 5A، §16): ممکن است بینِ آپلود/
    # پیش‌نمایش و اجرا پلن تنزل کرده باشد. قابلیتِ واردات و سقفِ ماهانه‌ی ردیف
    # هر دو دوباره بررسی می‌شوند — سقفِ ردیف کلِ فایل را می‌سنجد و در صورتِ
    # عبور کلِ واردات را رد می‌کند (بدونِ کوتاه‌سازیِ خاموش).
    from apps.subscriptions.services.enforcement import (
        check_import_row_budget,
        consume_import_rows,
        enforce_import_allowed,
    )

    enforce_import_allowed(job.store)
    rows = read_job_rows(job)
    check_import_row_budget(job.store, len(rows))
    record_audit_event(
        store=job.store, actor=actor, action_code="import.execution_started",
        object_type="ImportJob", object_id=str(job.pk),
        object_label=f"{job.get_import_type_display()} — حالتِ {job.get_mode_display()}",
    )
    job = run_import(job, rows, actor=actor)
    # مصرفِ ردیفِ ماهانه فقط پس از اجرایِ واقعی و یک‌بار به‌ازایِ هر Job ثبت
    # می‌شود (Jobِ نهایی‌شده دوباره اجرا نمی‌شود ⇒ دوباره‌شماری رخ نمی‌دهد).
    consume_import_rows(job.store, job.total_rows)
    _generate_error_report(job)
    return job


# ================================================================== گزارشِ خطا و قالب‌ها

def build_template_csv(import_type: str) -> str:
    """قالبِ CSVِ قدیمی (فقط هدرِ ستون‌هایِ داخلی) — فقط برایِ سازگاریِ عقب‌رو
    نگه داشته شده؛ قالبِ اصلی ``build_template_xlsx`` است."""
    import io

    from apps.core.services.csv_utils import write_csv_rows

    columns = IMPORT_COLUMNS.get(import_type)
    if columns is None:
        raise ImportServiceError(f"نوعِ واردات «{import_type}» نامعتبر است.")
    buffer = io.StringIO()
    write_csv_rows(buffer, header=columns, rows=[])
    return buffer.getvalue()


def build_template_xlsx(store, import_type: str) -> bytes:
    """قالبِ راهنمادارِ XLSX در بافتِ همین Store (فهرست‌هایِ برند/دسته‌بندی/انبار/...)."""
    from apps.dashboard.services import import_xlsx

    if import_type not in IMPORT_COLUMNS:
        raise ImportServiceError(f"نوعِ واردات «{import_type}» نامعتبر است.")
    return import_xlsx.build_template_xlsx(import_type, store)


def _generate_error_report(job: ImportJob) -> None:
    """گزارشِ خطایِ XLSXِ خصوصی (فقط ردیف‌هایِ نامعتبر/ناموفق) با مقدارهایِ
    اصلیِ همان ردیف‌ها. همه‌ی مقدارها از ``xlsx_utils.set_text`` می‌گذرند (بدونِ
    فرمول، ADR-51). اگر هیچ ردیفِ مشکل‌داری نباشد، فایلی ساخته نمی‌شود و
    گزارشِ قدیمی پاک می‌شود."""
    from django.core.files.base import ContentFile

    from apps.dashboard.services import import_xlsx

    error_rows = list(job.row_results.filter(
        status__in=[ImportRowResult.RowStatus.INVALID, ImportRowResult.RowStatus.FAILED]
    ).order_by("row_number"))
    if not error_rows:
        return

    try:
        source = read_job_rows(job)
    except ImportServiceError:
        source = []
    source_rows = {}
    for index, row in enumerate(source, start=1):
        number = row.get("__row_number__") or index
        if "__raw__" not in row:  # CSV: سرستون‌ها همان کلیدهایِ فایل‌اند
            row = {**row, "__raw__": [(k, v or "") for k, v in row.items() if not str(k).startswith("__")]}
        source_rows[number] = row

    content = import_xlsx.build_error_report_xlsx(job, error_rows, source_rows, job.import_type)
    if job.error_report_file:
        job.error_report_file.delete(save=False)
    job.error_report_file.save(f"errors-{job.pk}.xlsx", ContentFile(content), save=True)


def job_preview_summary(job: ImportJob) -> dict:
    """شمارنده‌هایِ پیش‌نمایش برایِ UI: کل، ساخته‌می‌شوند، بروزرسانی‌می‌شوند، نامعتبر، هشدار."""
    rows = job.row_results.all()
    will_create = rows.filter(normalized_data_summary__action="create").count()
    will_update = rows.filter(normalized_data_summary__action="update").count()
    with_warnings = sum(1 for warnings in rows.values_list("warnings", flat=True) if warnings)
    return {
        "total": job.total_rows, "will_create": will_create, "will_update": will_update,
        "invalid": job.invalid_rows + job.failed_rows, "warnings": with_warnings,
    }


IMPORT_FILE_RETENTION_DAYS = 30


def cleanup_import_files(store=None, *, now=None, retention_days: int = IMPORT_FILE_RETENTION_DAYS) -> int:
    """فایلِ منبع و گزارشِ خطایِ ``ImportJob``هایِ قدیمی‌تر از
    ``retention_days`` را از دیسک حذف می‌کند — امّا رکوردِ Job و شمارنده‌ها/
    نتیجه‌ی ردیف‌ها دست‌نخورده می‌مانند (تاریخچه حفظ می‌شود). Store-safe،
    batch-safe (``iterator``)، و idempotent (حذفِ فایلِ از قبل حذف‌شده
    بی‌اثر است). تعدادِ Jobهایی که حداقل یک فایلِ آن‌ها حذف شد را برمی‌گرداند
    — نگاه کنید به ADR-62."""
    now = now or timezone.now()
    cutoff = now - timezone.timedelta(days=retention_days)
    qs = ImportJob.objects.filter(created_at__lt=cutoff)
    if store is not None:
        qs = qs.filter(store=store)

    count = 0
    for job in qs.iterator(chunk_size=200):
        touched = False
        if job.source_file:
            job.source_file.delete(save=False)
            touched = True
        if job.error_report_file:
            job.error_report_file.delete(save=False)
            touched = True
        if touched:
            job.save(update_fields=["source_file", "error_report_file"])
            count += 1
    return count


def cancel_import_job(job: ImportJob, *, actor) -> ImportJob:
    """یک Jobِ هنوز اجرانشده را لغو می‌کند (فقط از حالت‌هایِ پیش از اجرا)."""
    if job.status in ImportJob.FINAL_STATUSES:
        raise ImportServiceError("این Job قبلاً به پایان رسیده و قابلِ لغو نیست.")
    job.status = ImportJob.Status.CANCELLED
    job.completed_at = timezone.now()
    job.save(update_fields=["status", "completed_at"])
    record_audit_event(
        store=job.store, actor=actor, action_code="import.cancelled",
        object_type="ImportJob", object_id=str(job.pk), object_label=job.original_filename,
    )
    return job
