"""دستورِ idempotent برایِ ساختِ فروشگاهِ Demo کاملاً جدا و قطعی «Rasti Mode
Demo» — نسخه‌یِ «Real Catalog» (پوشاک/کفش/کیف) — مأموریتِ «Rasti Mode Demo
— COMPLETE REAL CATALOG + MEDIA + CONTENT + ALL 8 READY TEMPLATE REAL
PREVIEWS».

نامِ دستور عمداً همان نامِ قبلی (``seed_ready_template_fashion_demo``)
نگه داشته شده — بازنویسیِ آن باعثِ شکستنِ همه‌یِ دستورهایِ Windows QA و
تست‌هایِ ثبت‌شده در فازهایِ قبلی می‌شد؛ «fashion» این‌جا هم‌چنان یک چترِ
درستِ صنعتِ retail برایِ پوشاک+کفش+کیف است.

منبعِ واقعیِ تصویر: ۳۴۵ عکسِ QA کاربر در ``raw_user_catalog/`` — پس از
ممیزیِ بصریِ کامل (دفترچه‌یِ اجرا را ببینید)، دقیقاً ۵۰ عکسِ منحصربه‌فرد
انتخاب و توسط
``apps/stores/demo_assets/rasti_mode_demo/scripts/select_and_process_media.py``
به ``products/<SKU>/01|02|03.webp`` (۱۲۰۰×۱۶۰۰، بومِ خنثی، بدونِ کراپِ
مخرب) پردازش شده‌اند؛ این دستور هرگز از ``raw_user_catalog/`` مستقیماً
نمی‌خواند یا آن را عمومی نمی‌کند.

ایزوله/Tenant-scoped: فقط رکوردهایِ Storeِ ثابتِ Demo (اسلاگِ
``rasti-mode-demo``) — هرگز ``rastisi-fashion-test``، ``akhlaghi``، یا هیچ
Storeِ واقعیِ مرچنت. ``--reset`` هم فقط همینِ اسلاگِ ثابت را حذف می‌کند.

Idempotent: اجرایِ دوباره رکوردِ تکراری نمی‌سازد؛ فیلدهایِ درجه‌یک
(قیمت/تخفیف/برند/محصول‌نوع) در هر اجرا با ماتریسِ ثابت همگام می‌شوند.

از موتورِ واقعیِ Attribute/Option/Variant برایِ کالاهایِ دارایِ
رنگ/سایز استفاده می‌کند؛ کیف‌ها (بدونِ سایزِ معنادار — طبقِ الزامِ صریحِ
کار) به‌صورتِ ``ProductType.SIMPLE`` با ``Product.stock`` مستقیم می‌مانند.

استفاده:
    python manage.py seed_ready_template_fashion_demo
    python manage.py seed_ready_template_fashion_demo --owner-username <کاربرِ موجود>
    python manage.py seed_ready_template_fashion_demo --reset
"""

from __future__ import annotations

import hashlib
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from PIL import Image, ImageDraw

from apps.catalog.models import (
    Brand,
    Category,
    MerchantCollection,
    Product,
    ProductOption,
    ProductTag,
    ProductVariant,
    Vendor,
)
from apps.catalog.services import collection_service, variant_engine_service
from apps.catalog.services.product_image_service import add_product_image, set_image_option_value
from apps.core.models import ShopSettings
from apps.content.models import (
    DestinationType,
    FooterSettings,
    HeroSlide,
    Menu,
    MenuItem,
    PromotionalBanner,
    StoryRailItem,
)
from apps.stores.hostnames import normalize_admin_subdomain
from apps.stores.models import Store, StoreDomain, StoreMembership

User = get_user_model()

# ------------------------------------------------------------------ شناسهٔ فروشگاه

STORE_SLUG = "rasti-mode-demo"
STORE_NAME = "Rasti Mode Demo"

# Owner provisioning (G2.1 hardening) — the seed NEVER auto-creates a
# credentialed owner and NEVER mutates an existing user's authentication
# credentials (password/email/phone/active state). The only owner path is the
# explicit, safe ``--owner-username <existing user>``: that user is resolved and
# given ONLY the OWNER StoreMembership for this demo store. Create the owner
# separately in local development, then pass it explicitly.
STORE_ADMIN_SUBDOMAIN = "rasti-mode-demo"
# پیشوندِ میزبانِ عمومیِ Storefront — عمداً از میزبانِ ادمین جدا است، دقیقاً
# همان الگویِ ``AdminSubdomainIndependentOfPublicDomainTests``. سافیکسِ
# واقعی از ``settings.RASTISI_ADMIN_DOMAIN_SUFFIX`` در زمانِ اجرا خوانده
# می‌شود (نه هاردکد) تا هم در DEBUG (``rastisi.localhost`` — التِ
# ``ALLOWED_HOSTS`` عریضِ آن را می‌پذیرد) و هم در Production (``rastisi.ir``)
# درست باشد.
STORE_PUBLIC_HOST_PREFIX = f"shop-{STORE_ADMIN_SUBDOMAIN}"

VENDOR = {"name": "Rasti Mode Demo Vendor", "slug": "rasti-mode-demo-vendor"}

DEMO_ASSETS_DIR = Path(__file__).resolve().parents[2] / "demo_assets" / "rasti_mode_demo"
PRODUCT_MEDIA_DIR = DEMO_ASSETS_DIR / "products"

# ------------------------------------------------------------------ برندها (دقیقاً ۶، بدونِ لوگویِ واقعی/حدسی)
# طبقِ الزامِ صریحِ کار: چون تصاویرِ خام برخی علائمِ تجاریِ واقعی را نشان
# می‌دهند (نایک/آدیداس/پوما/کانورس/...) و منشأِ لایسنسِ آن‌ها اثبات‌نشده
# است، تصمیمِ عمدی این است که هیچ برندِ واقعی حدس زده/استفاده نشود —
# همه‌یِ ۵۰ کالا زیرِ همین ۶ برندِ ساختگیِ Demo قرار می‌گیرند.

BRAND_NAMES = ["Demo Motion", "Demo Urban", "Demo Denim", "Demo Layer", "Demo Carry", "Demo Muse"]

# ------------------------------------------------------------------ دسته‌بندی‌ها (۱۰ برگِ معنایی زیرِ ۳ گروهِ ریشه — نه مسطح)
# G2.1 (Defect B): این ۱۰ نام، برگ‌هایِ درختِ دسته‌بندی‌اند و زیرِ ۳ گروهِ
# ریشه (کفش/پوشاک/کیف) قرار می‌گیرند — نه ۱۰ ریشه‌یِ مسطح. کالا فقط به یک
# برگ وصل می‌شود (قراردادِ leaf_categories که ادیتورِ کالا استفاده می‌کند).
# نگاه کنید به _seed_categories برایِ ساختِ درخت.
# تنقیحِ صریحِ طبقه‌بندیِ پیشنهادیِ کار (باید در گزارشِ پایانی توضیح داده
# شود): از میانِ ۳۴۵ عکسِ خام، فولدرِ ۳ عملاً یک‌دست «ژاکت/بامبر/چرم»
# است و تنها یک عکسِ هودیِ واقعی در کلِ مجموعه وجود دارد — اجبارِ ۵ کالایِ
# «هودی و سویشرت» با تنها ۱ عکسِ واقعی همان نقضِ صریحاً ممنوعِ کار است
# («هرگز یک کتانی را پیراهن نامیدن»). به‌جایِ آن، فولدرِ ۳ به دو دسته‌یِ
# واقعاً موجود در تصاویر تقسیم شد: «کاپشن و بامبر» (بامبر/کالج/هودیِ
# تنها) و «ژاکت چرم و اورشرت» (چرم/جین/اورشرت) — هر دو با شواهدِ بصریِ
# کافی.

CATEGORY_NAMES = [
    "کتانی رانینگ",
    "کتانی کژوال",
    "شلوار کژوال",
    "شلوار جین",
    "کاپشن و بامبر",
    "ژاکت چرم و اورشرت",
    "کفش زنانه",
    "صندل و دمپایی",
    "کیف دستی و Tote",
    "کیف دوشی و مجلسی",
]

# دسته‌هایی که کیف هستند — بدونِ محورِ سایز (SIMPLE product_type).
BAG_CATEGORIES = {"کیف دستی و Tote", "کیف دوشی و مجلسی"}

# ------------------------------------------------------------------ برچسب‌ها (معنادار، بدونِ نویزِ بی‌هدف)

TAG_NAMES = ["جدید", "پرفروش", "تخفیف‌دار", "انتخاب فصل", "اسپرت", "کژوال", "روزمره", "مینیمال", "پریمیوم"]

SPORTY_CATEGORIES = {"کتانی رانینگ", "کتانی کژوال", "کاپشن و بامبر"}
CASUAL_CATEGORIES = {"شلوار کژوال", "شلوار جین", "ژاکت چرم و اورشرت", "کفش زنانه", "صندل و دمپایی"}
MINIMAL_CATEGORIES = BAG_CATEGORIES
SEASONAL_PICK_SKUS = {"FSH-004", "FSH-014", "FSH-024", "FSH-034", "FSH-044"}
PREMIUM_SKUS = {"FSH-026", "FSH-030", "FSH-034", "FSH-045", "FSH-032", "FSH-005"}

# ------------------------------------------------------------------ کالکشن‌ها

COLLECTIONS = [
    {"name": "جدیدترین‌ها", "description": "تازه‌ترین اضافه‌شده‌های فروشگاهِ نمایشیِ Rasti Mode."},
    {"name": "پرفروش‌ها", "description": "پرطرفدارترین انتخاب‌های فروشگاهِ نمایشیِ Rasti Mode."},
    {"name": "تخفیف‌های منتخب", "description": "کالاهایِ تخفیف‌دارِ منتخبِ فروشگاهِ نمایشیِ Rasti Mode."},
    {"name": "انتخاب فصل", "description": "ترکیبِ پیشنهادیِ فصل در فروشگاهِ نمایشیِ Rasti Mode."},
    {"name": "کفش و کتانی", "description": "کتانی، کفشِ زنانه و صندل — منتخبِ فروشگاهِ نمایشیِ Rasti Mode."},
    {"name": "کیف و اکسسوری", "description": "کیفِ دستی، دوشی و مجلسی — منتخبِ فروشگاهِ نمایشیِ Rasti Mode."},
]

# ------------------------------------------------------------------ نگاشتِ رنگِ فارسی → Hex تقریبی (فقط برایِ swatch)

COLOR_HEX = {
    "سبز": "#4B6B3A", "مشکی": "#1A1A1A", "آبی روشن": "#8FB6D9", "کرم": "#F1E9D8",
    "سرمه‌ای": "#1E3A5F", "صورتی": "#F4B4C6", "سفید": "#F9FAFB", "طوسی": "#8C8C8C",
    "آبی": "#3B5B8C", "دودی": "#5C6066", "خاکی": "#A38F6D", "قرمز": "#B23A2E",
    "زرد": "#D9B23C", "قهوه‌ای": "#6B4A32", "زیتونی": "#6B7B3A", "بژ": "#E8DCC8",
    # رنگ‌هایِ دورنگِ واقعی (مأموریتِ چندرنگِ Issue 2) — فقط برایِ swatch:
    "سفید-صورتی": "#F0C9D2", "کرم-مشکی": "#D8CBB0", "زیتونی-کرم": "#A9A26A",
}
_FALLBACK_COLOR_HEX = "#9CA3AF"

IN_STOCK = "IN_STOCK"
OUT_OF_STOCK = "OUT_OF_STOCK"
PARTIAL_VARIANT_STOCK = "PARTIAL_VARIANT_STOCK"

_HEALTHY_VARIANT_STOCK = 14
_PARTIAL_HEALTHY_VARIANT_STOCK = 10
_SIMPLE_HEALTHY_STOCK = 18

# ------------------------------------------------------------------ ماتریسِ کالا (دقیقاً ۵۰ ردیف)
# فرمت: (کد, دسته, نامِ کالا, برند, قیمتِ‌عادی, قیمتِ‌حراج‌یا‌None, رنگ, [سایزها]‌یا‌None, وضعیتِ‌موجودی)
# [سایزها]=None یعنی کالایِ SIMPLE بدونِ محورِ تنوع (فقط کیف‌ها).

PRODUCT_MATRIX = [
    ("FSH-001", "کتانی رانینگ", "کتانی رانینگ چانکی سبز-کرم", "Demo Motion", 3450000, 2750000, "سبز", ["40", "41", "42", "43", "44"], OUT_OF_STOCK),
    ("FSH-002", "کتانی رانینگ", "کتانی رانینگ بندی مشکی", "Demo Motion", 4150000, None, "مشکی", ["41", "42", "43", "44", "45"], PARTIAL_VARIANT_STOCK),
    ("FSH-003", "کتانی رانینگ", "کتانی رانینگ سبک آبی روشن", "Demo Urban", 2890000, 2390000, "آبی روشن", ["39", "40", "41", "42", "43"], IN_STOCK),
    ("FSH-004", "کتانی رانینگ", "کتانی رانینگ چانکی کلاسیک", "Demo Motion", 3950000, None, ("کرم", "سفید"), ["40", "41", "42", "43"], PARTIAL_VARIANT_STOCK),
    ("FSH-005", "کتانی رانینگ", "کتانی رانینگ مسابقه‌ای مشکی-سفید", "Demo Motion", 6450000, 5290000, "مشکی", ["40", "41", "42", "43", "44"], IN_STOCK),

    ("FSH-006", "کتانی کژوال", "کتانی کژوال کلاسیک راه‌راه", "Demo Urban", 3250000, None, ("مشکی", "سفید"), ["39", "40", "41", "42"], OUT_OF_STOCK),
    ("FSH-007", "کتانی کژوال", "کتانی کژوال کلاسیک مشکی", "Demo Urban", 2950000, 2450000, "مشکی", ["40", "41", "42", "43", "44"], PARTIAL_VARIANT_STOCK),
    ("FSH-008", "کتانی کژوال", "کتانی کژوال بلند کلاسیک", "Demo Urban", 3650000, None, ("سفید-صورتی", "مشکی"), ["37", "38", "39", "40", "41"], IN_STOCK),
    ("FSH-009", "کتانی کژوال", "کتانی کژوال اسپرت سفید-مشکی", "Demo Motion", 3150000, 2690000, "سفید", ["40", "41", "42", "43", "44"], IN_STOCK),
    ("FSH-010", "کتانی کژوال", "کتانی کژوال ساده سفید", "Demo Urban", 2690000, None, "سفید", ["39", "40", "41", "42", "43"], IN_STOCK),

    ("FSH-011", "شلوار کژوال", "شلوار کتان کژوال سرمه‌ای", "Demo Denim", 2450000, 1990000, "سرمه‌ای", ["30", "32", "34", "36"], OUT_OF_STOCK),
    ("FSH-012", "شلوار کژوال", "شلوار کتان بندی کژوال", "Demo Denim", 2690000, None, ("بژ", "سرمه‌ای"), ["30", "32", "34", "36", "38"], PARTIAL_VARIANT_STOCK),
    ("FSH-013", "شلوار کژوال", "شلوار کتان مشکی روزمره", "Demo Urban", 2290000, 1890000, "مشکی", ["28", "30", "32", "34"], IN_STOCK),
    ("FSH-014", "شلوار کژوال", "شلوار کتان کرم ریلکس", "Demo Denim", 2850000, None, "کرم", ["30", "32", "34", "36"], IN_STOCK),
    ("FSH-015", "شلوار کژوال", "شلوار کتان زیتونی کژوال", "Demo Denim", 3150000, None, "زیتونی", ["30", "32", "34", "36", "38"], IN_STOCK),

    ("FSH-016", "شلوار جین", "شلوار جین طوسی راسته", "Demo Denim", 3450000, None, "طوسی", ["28", "30", "32", "34"], OUT_OF_STOCK),
    ("FSH-017", "شلوار جین", "شلوار جین آبی متوسط اسلیم", "Demo Denim", 3250000, 2690000, "آبی", ["30", "32", "34", "36"], PARTIAL_VARIANT_STOCK),
    ("FSH-018", "شلوار جین", "شلوار جین آبی روشن مام‌فیت", "Demo Denim", 3650000, None, "آبی روشن", ["28", "30", "32", "34"], IN_STOCK),
    ("FSH-019", "شلوار جین", "شلوار جین آبی ریلکس‌فیت", "Demo Layer", 3890000, None, "آبی روشن", ["30", "32", "34", "36", "38"], IN_STOCK),
    ("FSH-020", "شلوار جین", "شلوار جین آبی راسته کلاسیک", "Demo Denim", 3050000, 2590000, "آبی", ["30", "32", "34", "36"], IN_STOCK),

    ("FSH-021", "کاپشن و بامبر", "کاپشن بامبر زیتونی", "Demo Layer", 5450000, None, "زیتونی", ["S", "M", "L", "XL"], OUT_OF_STOCK),
    ("FSH-022", "کاپشن و بامبر", "کاپشن بامبر کالج", "Demo Layer", 6250000, None, ("کرم-مشکی", "زیتونی-کرم"), ["S", "M", "L", "XL", "XXL"], PARTIAL_VARIANT_STOCK),
    ("FSH-023", "کاپشن و بامبر", "کاپشن بامبر مشکی ساده", "Demo Layer", 5950000, 4950000, "مشکی", ["M", "L", "XL"], IN_STOCK),
    ("FSH-024", "کاپشن و بامبر", "هودی زیپ‌دار آبی", "Demo Urban", 4450000, 3790000, "آبی", ["S", "M", "L", "XL"], IN_STOCK),
    ("FSH-025", "کاپشن و بامبر", "کاپشن بامبر دودی", "Demo Motion", 5150000, None, "دودی", ["M", "L", "XL", "XXL"], IN_STOCK),

    ("FSH-026", "ژاکت چرم و اورشرت", "ژاکت چرم مشکی موتوری", "Demo Layer", 9450000, 7590000, "مشکی", ["S", "M", "L", "XL"], OUT_OF_STOCK),
    ("FSH-027", "ژاکت چرم و اورشرت", "ژاکت جین آبی کلاسیک", "Demo Denim", 6950000, None, "آبی", ["S", "M", "L"], PARTIAL_VARIANT_STOCK),
    ("FSH-028", "ژاکت چرم و اورشرت", "اورشرت کتان خاکی", "Demo Layer", 5450000, None, "خاکی", ["M", "L", "XL"], IN_STOCK),
    ("FSH-029", "ژاکت چرم و اورشرت", "اورشرت زیپ‌دار قرمز", "Demo Layer", 5850000, 4890000, "قرمز", ["S", "M", "L", "XL"], IN_STOCK),
    ("FSH-030", "ژاکت چرم و اورشرت", "اورشرت زیتونی تیره", "Demo Muse", 6250000, None, "زیتونی", ["M", "L", "XL", "XXL"], IN_STOCK),

    ("FSH-031", "کفش زنانه", "کفش تخت زنانه کرم", "Demo Muse", 2450000, None, "کرم", ["36", "37", "38", "39"], OUT_OF_STOCK),
    ("FSH-032", "کفش زنانه", "کفش پاشنه‌بلند قهوه‌ای", "Demo Muse", 3650000, 2950000, "قهوه‌ای", ["36", "37", "38", "39", "40"], PARTIAL_VARIANT_STOCK),
    ("FSH-033", "کفش زنانه", "بوت مچی زنانه مشکی", "Demo Muse", 4250000, None, "مشکی", ["37", "38", "39", "40"], IN_STOCK),
    ("FSH-034", "کفش زنانه", "کفش مویل زنانه قهوه‌ای", "Demo Urban", 2890000, None, "قهوه‌ای", ["36", "37", "38", "39"], IN_STOCK),
    ("FSH-035", "کفش زنانه", "کفش لوفر زنانه مشکی", "Demo Muse", 3150000, 2650000, "مشکی", ["37", "38", "39", "40"], IN_STOCK),

    ("FSH-036", "صندل و دمپایی", "صندل جواهرنشان قهوه‌ای", "Demo Muse", 2250000, None, "قهوه‌ای", ["36", "37", "38", "39"], OUT_OF_STOCK),
    ("FSH-037", "صندل و دمپایی", "دمپایی انگشتی کلاسیک مشکی", "Demo Muse", 2050000, None, "مشکی", ["37", "38", "39", "40"], PARTIAL_VARIANT_STOCK),
    ("FSH-038", "صندل و دمپایی", "دمپایی حلقه‌ای سبز تیره", "Demo Muse", 2150000, 1790000, "سبز", ["36", "37", "38"], IN_STOCK),
    ("FSH-039", "صندل و دمپایی", "صندل دوبنده", "Demo Urban", 2650000, 2190000, ("مشکی", "طوسی"), ["37", "38", "39", "40"], IN_STOCK),
    ("FSH-040", "صندل و دمپایی", "دمپایی قلب‌نشان", "Demo Muse", 2050000, None, ("کرم", "قهوه‌ای", "مشکی"), ["36", "37", "38", "39"], IN_STOCK),

    ("FSH-041", "کیف دستی و Tote", "کیف تُت چرم مشکی", "Demo Carry", 4450000, 3650000, "مشکی", None, OUT_OF_STOCK),
    ("FSH-042", "کیف دستی و Tote", "کیف تُت زیتونی", "Demo Carry", 3950000, None, "زیتونی", None, IN_STOCK),
    ("FSH-043", "کیف دستی و Tote", "کیف تُت جیر قهوه‌ای", "Demo Carry", 4650000, 3890000, "قهوه‌ای", None, IN_STOCK),
    ("FSH-044", "کیف دستی و Tote", "کیف تُت روزمره مشکی", "Demo Urban", 3450000, None, "مشکی", None, IN_STOCK),
    ("FSH-045", "کیف دستی و Tote", "کیف تُت خاکی بزرگ", "Demo Carry", 5250000, 4390000, "خاکی", None, IN_STOCK),

    ("FSH-046", "کیف دوشی و مجلسی", "کیف دوشی چرم قهوه‌ای", "Demo Carry", 3650000, None, "قهوه‌ای", None, OUT_OF_STOCK),
    ("FSH-047", "کیف دوشی و مجلسی", "کیف دوشی مشکی کلاسیک", "Demo Carry", 2950000, 2450000, "مشکی", None, IN_STOCK),
    ("FSH-048", "کیف دوشی و مجلسی", "کیف دوشی زنجیری مشکی", "Demo Muse", 4150000, None, "مشکی", None, IN_STOCK),
    ("FSH-049", "کیف دوشی و مجلسی", "کیف مجلسی شنیونی", "Demo Carry", 3350000, 2790000, ("زرد", "مشکی"), None, PARTIAL_VARIANT_STOCK),
    ("FSH-050", "کیف دوشی و مجلسی", "کیف دوشی زنجیردار مشکی", "Demo Carry", 3850000, None, "مشکی", None, IN_STOCK),
]

assert len(PRODUCT_MATRIX) == 50
assert len({row[0] for row in PRODUCT_MATRIX}) == 50
assert {row[1] for row in PRODUCT_MATRIX} == set(CATEGORY_NAMES)
assert {row[3] for row in PRODUCT_MATRIX} == set(BRAND_NAMES)


def _compute_discount_percent(regular_price: int, sale_price: int | None) -> int:
    if not sale_price:
        return 0
    factor = Decimal(sale_price) / Decimal(regular_price)
    percent = (Decimal(100) - factor * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return max(0, min(100, int(percent)))


def _tags_for(sku: str, category_fa: str, position_in_category: int, has_discount: bool) -> list[str]:
    """انتساب قطعی و معنادار — نه نویزِ تصادفی. هر قاعده مستقیماً از
    ساختارِ ردیفِ خودِ محصول (نه فراداده‌یِ بیرونی) مشتق می‌شود."""
    tags = []
    if has_discount:
        tags.append("تخفیف‌دار")
    if position_in_category == 5:
        tags.append("جدید")
    if position_in_category == 3:
        tags.append("پرفروش")
    if category_fa in SPORTY_CATEGORIES:
        tags.append("اسپرت")
    elif category_fa in CASUAL_CATEGORIES:
        tags.append("روزمره")
    if category_fa in MINIMAL_CATEGORIES:
        tags.append("مینیمال")
    if sku in SEASONAL_PICK_SKUS:
        tags.append("انتخاب فصل")
    if sku in PREMIUM_SKUS:
        tags.append("پریمیوم")
    return tags


def _description_for(title_fa: str, category_fa: str, color_fa: str, brand: str) -> str:
    return (
        f"{title_fa} از برند {brand} — طراحیِ {category_fa} با رنگِ اصلیِ {color_fa}، "
        "مناسبِ استفاده‌یِ روزمره. این کالا بخشی از فروشگاهِ نمایشیِ Rasti Mode Demo "
        "است و صرفاً برایِ آزمونِ Storefront/قالب‌های آماده استفاده می‌شود."
    )


def _load_processed_image(sku: str, order: int) -> SimpleUploadedFile:
    path = PRODUCT_MEDIA_DIR / sku / f"0{order}.webp"
    data = path.read_bytes()
    return SimpleUploadedFile(f"{sku.lower()}-{order}.webp", data, content_type="image/webp")


def _composite_visual_bytes(*, width: int, height: int, product_paths: list[Path], bg_hex: str) -> bytes:
    """ترکیب‌بندیِ تبلیغاتیِ خالص‌بصری (بدونِ متن) از عکس‌هایِ واقعیِ کالا —
    فقط Pillow، بدونِ هیچ فایل/URL خارجی. متنِ فارسیِ واقعیِ Hero/Banner
    (تیتر/دکمه) هرگز داخلِ خودِ تصویر رسم نمی‌شود — روی فیلدهایِ مدل
    (``title``/``subtitle``/``button_label``) قرار می‌گیرد تا مرورگر با
    فونتِ واقعیِ فارسیِ خودش رندر کند (این Sandbox فونتِ فارسی ندارد)."""
    base = tuple(int(bg_hex.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    canvas = Image.new("RGB", (width, height), base)
    draw = ImageDraw.Draw(canvas)
    # gradient overlay (subtle, left-to-right lightening)
    for x in range(width):
        t = x / max(1, width - 1)
        shade = tuple(min(255, int(c + (255 - c) * 0.18 * t)) for c in base)
        draw.line([(x, 0), (x, height)], fill=shade)

    n = len(product_paths)
    slot_w = width // max(1, n)
    for i, path in enumerate(product_paths):
        with Image.open(path) as prod:
            prod = prod.convert("RGB")
            target_h = int(height * 0.86)
            scale = target_h / prod.height
            target_w = max(1, int(prod.width * scale))
            prod = prod.resize((target_w, target_h), Image.LANCZOS)
            x = i * slot_w + (slot_w - target_w) // 2
            y = (height - target_h) // 2
            canvas.paste(prod, (max(0, x), max(0, y)))
    return _to_jpeg_bytes(canvas)


def _to_jpeg_bytes(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=88, optimize=True)
    return buffer.getvalue()


def _uploaded_composite(*, filename: str, width: int, height: int, product_paths: list[Path], bg_hex: str) -> SimpleUploadedFile:
    data = _composite_visual_bytes(width=width, height=height, product_paths=product_paths, bg_hex=bg_hex)
    return SimpleUploadedFile(filename, data, content_type="image/jpeg")


class Command(BaseCommand):
    help = (
        "می‌سازد/بازمی‌سازد یک فروشگاهِ Demo کاملاً ایزوله و قطعی (پوشاک/کفش/کیف، "
        "«Rasti Mode Demo») با کاتالوگِ واقعیِ برگرفته از ۳۴۵ عکسِ QAی کاربر. "
        "Idempotent، Tenant-scoped."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--owner-username", default="",
            help="یوزرنیمِ یک کاربرِ از‌قبل‌موجود که (اختیاری) مالکِ StoreMembership این فروشگاهِ Demo می‌شود.",
        )
        parser.add_argument(
            "--reset", action="store_true",
            help=(
                f"پیش از ساختنِ دوباره، فقط Storeِ Demo با اسلاگِ ثابتِ «{STORE_SLUG}» را کاملاً حذف "
                "می‌کند — هیچ آرگومانی برایِ تغییرِ این اسلاگ وجود ندارد."
            ),
        )
        parser.add_argument(
            "--ready-template", default="", metavar="KEY",
            help=(
                "Part 2B QA fix — پس از ساختنِ کاتالوگ، همین یک کلیدِ Ready "
                "Template رسمی را روی این Storeِ Demo Apply+Publish کن (مثلاً "
                "«fashion_promo_catalog»). بدونِ این آرگومان، Storeِ Demو دقیقاً "
                "مثلِ قبل بدونِ هیچ Ready Templateِ اعمال‌شده‌ای باقی می‌ماند — "
                "این دستور هرگز خودش، بی‌صدا، یک قالب را انتخاب/قفل نمی‌کند."
            ),
        )

    def handle(self, *args, **options):
        owner = None
        owner_username = (options.get("owner_username") or "").strip()
        if owner_username:
            try:
                owner = User.objects.get(username=owner_username)
            except User.DoesNotExist as exc:
                raise CommandError(f"کاربری با یوزرنیمِ «{owner_username}» یافت نشد.") from exc

        ready_template_key = (options.get("ready_template") or "").strip()
        ready_template_preset = None
        if ready_template_key:
            from apps.storefront_builder.layout_preset_registry import get_layout_preset

            ready_template_preset = get_layout_preset(ready_template_key)
            if ready_template_preset is None or not ready_template_preset.is_ready_template:
                raise CommandError(
                    f"«{ready_template_key}» یک کلیدِ Ready Templateِ رسمی نیست — "
                    "list_ready_templates() را برای فهرستِ معتبر ببینید."
                )

        if options["reset"]:
            self._reset()

        with transaction.atomic():
            store = self._seed_store()
            self._seed_domain(store)
            # Owner is provisioned ONLY when an existing user is passed via
            # --owner-username; that user gets ONLY the StoreMembership (no
            # credential mutation). Without the flag, no owner is created.
            if owner is not None:
                self._seed_membership(store, owner)
            self._seed_shop_settings(store)
            vendor = self._seed_vendor(store)
            categories = self._seed_categories(store)
            brands = self._seed_brands(store)
            tags = self._seed_tags(store)
            products = self._seed_products(store, vendor, categories, brands, tags)
            variant_stats = self._seed_variants(products)
            image_count = self._seed_product_images(products)
            self._seed_category_images(categories, products)
            collections = self._seed_collections(store, products)
            hero_count = self._seed_hero_slides(store, products)
            banner_count = self._seed_banners(store, products)
            story_count = self._seed_story_rail(store, categories, products)
            self._seed_navigation(store, categories, collections)
            self._seed_footer(store, categories, collections)

        applied_template_note = "  Ready Template: هیچ‌کدام (بدونِ --ready-template)\n"
        if ready_template_preset is not None:
            from apps.storefront_builder.services import layout_service, preset_service

            # Controlled seed setup: apply the Ready Template through the
            # lower-level ``apply_preset`` primitive on the store's active Draft.
            # (The merchant-facing checkpoint wrapper is fail-closed for Ready
            # Templates — Architecture Convergence / Phase 1 single-authority rule.)
            seed_draft = layout_service.get_or_create_draft(store)
            preset_service.apply_preset(seed_draft, ready_template_preset)
            layout_service.publish(store)
            applied_template_note = f"  Ready Template: {ready_template_preset.key} (Apply + Publish شد)\n"

        self.stdout.write(self.style.SUCCESS(
            "seed_ready_template_fashion_demo با موفقیت اجرا شد:\n"
            f"  Store: {store.slug} (admin_subdomain={store.admin_subdomain})\n"
            f"  دسته‌بندی: {Category.objects.filter(store=store).count()}\n"
            f"  برند: {Brand.objects.filter(store=store).count()}\n"
            f"  کالا: {Product.objects.filter(store=store).count()}\n"
            f"  تنوع: {variant_stats['total']} (روی {variant_stats['products_with_variants']} کالا)\n"
            f"  تصویرِ کالا: {image_count}\n"
            f"  کالکشن: {len(collections)}\n"
            f"  Hero: {hero_count}  Banner: {banner_count}  Story: {story_count}\n"
            f"{applied_template_note}"
        ))

    # ------------------------------------------------------------------ Reset

    @transaction.atomic
    def _reset(self) -> None:
        existing = Store.objects.filter(slug=STORE_SLUG).first()
        if existing is None:
            self.stdout.write("  --reset: Storeِ Demo از قبل وجود نداشت — چیزی حذف نشد.")
            return
        self.stdout.write(f"  --reset: حذفِ کاملِ Storeِ Demo «{existing.slug}» (pk={existing.pk})…")
        # ترتیبِ امنِ حذف — کشف‌شده حینِ اجرایِ واقعیِ این دستور:
        # ۱) ProductVariant (تا VariantOptionValueِ PROTECTِ ProductOptionValue آزاد شود)،
        # ۲) MenuItem (چون ``MenuItem.menu`` عمداً PROTECT است — نگاه کنید به
        #    مدل — و بدونِ این، CASCADEِ Store روی Menu با ProtectedError می‌شکند)،
        # ۳) Productها (CASCADE به ProductOption/ProductOptionValue، و
        #    آزادکردنِ PROTECTِ Product.category)،
        # ۴) خودِ Store (که Menu/HeroSlide/PromotionalBanner/StoryRailItem/
        #    FooterSettings/MerchantCollection را از طریقِ CASCADEِ store پاک می‌کند).
        ProductVariant.objects.filter(product__store=existing).delete()
        MenuItem.objects.filter(menu__store=existing).delete()
        Product.objects.filter(store=existing).delete()
        existing.delete()

    # ------------------------------------------------------------------ Store/Domain/Membership

    def _seed_store(self) -> Store:
        store, created = Store.objects.get_or_create(
            slug=STORE_SLUG,
            defaults={
                "name": STORE_NAME,
                "admin_subdomain": normalize_admin_subdomain(STORE_ADMIN_SUBDOMAIN),
                "status": Store.Status.ACTIVE,
                "onboarding_stage": Store.OnboardingStage.DONE,
                "onboarding_completed_at": timezone.now(),
            },
        )
        if not created and store.name != STORE_NAME:
            store.name = STORE_NAME
            store.status = Store.Status.ACTIVE
            store.save(update_fields=["name", "status", "updated_at"])
        return store

    def _seed_domain(self, store: Store) -> None:
        from django.conf import settings

        hostname = f"{store.admin_subdomain}.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"
        domain, created = StoreDomain.objects.get_or_create(
            store=store, hostname=hostname,
            defaults={
                "is_primary": True,
                "domain_type": StoreDomain.DomainType.PLATFORM_SUBDOMAIN,
                "verification_status": StoreDomain.VerificationStatus.VERIFIED,
                "verified_at": timezone.now(),
            },
        )
        if not created and domain.verification_status != StoreDomain.VerificationStatus.VERIFIED:
            domain.verification_status = StoreDomain.VerificationStatus.VERIFIED
            domain.verified_at = timezone.now()
            domain.is_primary = True
            domain.save(update_fields=["verification_status", "verified_at", "is_primary", "updated_at"])

        # میزبانِ عمومیِ Storefront — مستقل از میزبانِ ادمینِ بالا (نگاه کنید
        # به توضیحِ ``STORE_PUBLIC_HOST_PREFIX``). این همان دامنه‌ای است که
        # مشتری/QA برایِ دیدنِ HOME/LISTING/PDP/CART واقعی باز می‌کند. سافیکس
        # از همان تنظیمِ Runtime گرفته می‌شود که میزبانِ ادمینِ بالا استفاده
        # کرد — نه هاردکد — تا هم در DEBUG هم در Production درست باشد.
        public_hostname = f"{STORE_PUBLIC_HOST_PREFIX}.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"
        public_domain, public_created = StoreDomain.objects.get_or_create(
            store=store, hostname=public_hostname,
            defaults={
                "is_primary": False,
                "domain_type": StoreDomain.DomainType.CUSTOM_DOMAIN,
                "verification_status": StoreDomain.VerificationStatus.VERIFIED,
                "verified_at": timezone.now(),
            },
        )
        if not public_created and public_domain.verification_status != StoreDomain.VerificationStatus.VERIFIED:
            public_domain.verification_status = StoreDomain.VerificationStatus.VERIFIED
            public_domain.verified_at = timezone.now()
            public_domain.save(update_fields=["verification_status", "verified_at", "updated_at"])

    def _seed_membership(self, store: Store, owner) -> None:
        """Give the (explicitly-provided) ``owner`` user ONLY the OWNER
        StoreMembership for this demo store. This never touches the user's
        authentication credentials (password/email/phone/active state) — the
        seed is not an identity-provisioning tool."""
        membership, created = StoreMembership.objects.get_or_create(
            store=store, user=owner,
            defaults={
                "role": StoreMembership.Role.OWNER,
                "status": StoreMembership.MembershipStatus.ACTIVE,
                "accepted_at": timezone.now(),
            },
        )
        # Converge an EXISTING membership to OWNER+ACTIVE regardless of its
        # prior role/status — the command contract is that the provided user
        # becomes the OWNER of this store (an already-ACTIVE non-OWNER row, e.g.
        # ADMINISTRATOR, must be promoted, not left as-is).
        if not created and (
            membership.role != StoreMembership.Role.OWNER
            or membership.status != StoreMembership.MembershipStatus.ACTIVE
        ):
            membership.role = StoreMembership.Role.OWNER
            membership.status = StoreMembership.MembershipStatus.ACTIVE
            membership.accepted_at = membership.accepted_at or timezone.now()
            membership.save(update_fields=["role", "status", "accepted_at", "updated_at"])

    # ------------------------------------------------------------------ ShopSettings

    def _seed_shop_settings(self, store: Store) -> None:
        """بدونِ این رکورد، PDPِ واقعی (``build_product_detail_context`` →
        ``is_gift_wrap_available`` → ``ShopSettings.load``) با
        ``ShopSettingsNotProvisionedError`` می‌شکند — کشف‌شده حینِ
        تأییدِ Storefrontِ واقعی روی این Storeِ Demo."""
        settings_row = ShopSettings.provision_for(store)
        changed = False
        if not settings_row.tagline:
            settings_row.tagline = "پوشاک، کفش و کیف — فروشگاهِ نمایشیِ Rasti Mode"
            changed = True
        if not settings_row.description:
            settings_row.description = (
                "Rasti Mode Demo یک فروشگاهِ نمایشیِ ایزوله برایِ آزمونِ Storefront و "
                "قالب‌های آماده‌یِ راستی‌سی است."
            )
            changed = True
        if not settings_row.contact_phone:
            settings_row.contact_phone = "02100000000"
            changed = True
        if not settings_row.contact_email:
            settings_row.contact_email = "demo@rasti-mode-demo.internal"
            changed = True
        if changed:
            settings_row.save()

    # ------------------------------------------------------------------ Vendor/Category/Brand/Tags

    def _seed_vendor(self, store: Store) -> Vendor:
        vendor, _ = Vendor.objects.get_or_create(
            store=store, slug=VENDOR["slug"], defaults={"name": VENDOR["name"], "is_active": True},
        )
        return vendor

    def _seed_categories(self, store: Store) -> dict:
        """Seed a real 2-level category tree (group parents -> the 10 leaves).

        G2.1 Defect B: products may only be attached to LEAF categories
        (``catalog_admin_service.leaf_categories`` = ``parent__isnull=False`` AND
        no children), which the Product Editor uses. Flat root categories are
        therefore never valid product categories. We keep the exact 10 semantic
        categories but nest each under a group parent, so:
          - the 10 remain the leaves products attach to (this method still
            returns ``{leaf_name: leaf_category}`` — downstream seeding for
            images / story-rail / navigation is unchanged);
          - the storefront nav (``parent__isnull=True``) now shows the 3 groups
            as top-level entries with the 10 as their populated children (a
            better mega-menu), and the listing filter's parent→children match
            (``category__parent__slug``) surfaces a group's leaf products.
        Idempotent via ``get_or_create(store, slug)``; tenant-scoped.
        """
        # 3 group parents -> their leaf category names (order preserved to match
        # CATEGORY_NAMES' original ordering within each group).
        groups = {
            "کفش": ["کتانی رانینگ", "کتانی کژوال", "کفش زنانه", "صندل و دمپایی"],
            "پوشاک": ["شلوار کژوال", "شلوار جین", "کاپشن و بامبر", "ژاکت چرم و اورشرت"],
            "کیف": ["کیف دستی و Tote", "کیف دوشی و مجلسی"],
        }
        # Preserve each leaf's original display order from CATEGORY_NAMES.
        leaf_order = {name: index for index, name in enumerate(CATEGORY_NAMES)}

        by_name = {}
        for group_order, (group_name, leaf_names) in enumerate(groups.items()):
            group_slug = slugify(group_name, allow_unicode=True)
            group, _ = Category.objects.get_or_create(
                store=store, slug=group_slug,
                defaults={"name": group_name, "order": group_order, "is_active": True},
            )
            # A pre-existing flat root from an older seed must become a group
            # root too — it already has parent=None, so nothing to change; ensure
            # it is not accidentally parented.
            if group.parent_id is not None:
                group.parent = None
                group.save(update_fields=["parent", "updated_at"])
            for name in leaf_names:
                slug = slugify(name, allow_unicode=True)
                leaf, created = Category.objects.get_or_create(
                    store=store, slug=slug,
                    defaults={
                        "name": name, "order": leaf_order[name], "is_active": True, "parent": group,
                    },
                )
                # Re-home a leaf that an older seed created as a flat root.
                if leaf.parent_id != group.id:
                    leaf.parent = group
                    leaf.save(update_fields=["parent", "updated_at"])
                by_name[name] = leaf
        return by_name

    def _seed_brands(self, store: Store) -> dict:
        by_name = {}
        for index, name in enumerate(BRAND_NAMES):
            slug = slugify(name, allow_unicode=True)
            brand, _ = Brand.objects.get_or_create(
                store=store, slug=slug, defaults={"name": name, "sort_order": index, "is_active": True},
            )
            by_name[name] = brand
        return by_name

    def _seed_tags(self, store: Store) -> dict:
        by_name = {}
        for name in TAG_NAMES:
            tag, _ = ProductTag.objects.get_or_create(
                store=store, code=slugify(name, allow_unicode=True), defaults={"name": name, "is_active": True},
            )
            by_name[name] = tag
        return by_name

    # ------------------------------------------------------------------ Products

    def _seed_products(self, store: Store, vendor: Vendor, categories: dict, brands: dict, tags: dict) -> list:
        products = []
        category_position = {}
        for row in PRODUCT_MATRIX:
            code, category_name, name, brand_name, regular_price, sale_price, color, sizes, stock_state = row
            # طبقِ الزامِ Issue 2 (پستِ‌دمو hardening): ``color`` یا یک رشته‌یِ
            # تک‌رنگ است یا یک tuple از رنگ‌هایِ واقعیِ چندگانه (به همان
            # ترتیبِ تصاویرِ پردازش‌شده در manifest) — این‌جا همیشه به یک
            # tuple نرمال می‌شود تا بقیه‌یِ کد یک‌دست باشد.
            colors = color if isinstance(color, tuple) else (color,)
            category_position[category_name] = category_position.get(category_name, 0) + 1
            position = category_position[category_name]

            category = categories[category_name]
            brand = brands[brand_name]
            slug = f"{slugify(name, allow_unicode=True)}-{code.lower()}"
            discount_percent = _compute_discount_percent(regular_price, sale_price)
            is_bag = category_name in BAG_CATEGORIES
            # کیفِ چندرنگ (Issue 2): بدونِ محورِ سایز اما با محورِ رنگِ
            # واقعی — پس دیگر SIMPLE نیست، باید VARIABLE باشد تا تنوعِ
            # رنگ‌محور واقعی (نه فقط یک برچسبِ ساختگی) ساخته شود.
            product_type = Product.ProductType.SIMPLE if (is_bag and len(colors) == 1) else Product.ProductType.VARIABLE

            product, created = Product.objects.get_or_create(
                store=store, sku=code,
                defaults={
                    "vendor": vendor, "category": category, "brand": brand,
                    "name": name, "slug": slug,
                    "description": _description_for(name, category_name, colors[0], brand_name),
                    "price": regular_price, "discount_percent": discount_percent,
                    "status": Product.Status.ACTIVE,
                    "product_type": product_type,
                    "unit": Product.Unit.PIECE,
                },
            )
            if not created:
                changed_fields = []
                if product.discount_percent != discount_percent:
                    product.discount_percent = discount_percent
                    changed_fields.append("discount_percent")
                if int(product.price) != regular_price:
                    product.price = regular_price
                    changed_fields.append("price")
                if product.product_type != product_type:
                    product.product_type = product_type
                    changed_fields.append("product_type")
                if product.brand_id != brand.id:
                    product.brand = brand
                    changed_fields.append("brand")
                if product.category_id != category.id:
                    product.category = category
                    changed_fields.append("category")
                if changed_fields:
                    product.save(update_fields=[*changed_fields, "updated_at"])

            tag_names = _tags_for(code, category_name, position, discount_percent > 0)
            product.tags.set([tags[t] for t in tag_names])

            products.append((product, colors, sizes, stock_state, is_bag))
        return products

    # ------------------------------------------------------------------ Variants (apparel/footwear) + SIMPLE stock (bags)

    def _seed_variants(self, products: list) -> dict:
        total = 0
        products_with_variants = 0

        for product, colors, sizes, stock_state, is_bag in products:
            if is_bag and len(colors) == 1:
                # کیفِ تک‌رنگ: بدونِ محورِ رنگ/سایز — SIMPLE با Product.stock مستقیم.
                new_stock = 0 if stock_state == OUT_OF_STOCK else _SIMPLE_HEALTHY_STOCK
                if product.stock != new_stock:
                    product.stock = new_stock
                    product.save(update_fields=["stock", "updated_at"])
                continue

            # از این‌جا به بعد: کالایِ دارایِ محورِ تنوعِ واقعی — یا پوشاک/کفشِ
            # همیشگی (رنگ×سایز)، یا کیفِ چندرنگِ Issue 2 (فقط محورِ رنگ،
            # بدونِ سایز — کیف اصلاً سایزِ معنادار ندارد).
            if not product.options.filter(is_active=True).exists():
                variant_engine_service.add_product_option(
                    product, label="رنگ", input_type=ProductOption.InputType.COLOR,
                    values=list(colors),
                    color_hex_by_label={c: COLOR_HEX.get(c, _FALLBACK_COLOR_HEX) for c in colors},
                )
                if sizes:
                    variant_engine_service.add_product_option(product, label="سایز", values=sizes)

            variant_engine_service.generate_variants(product)

            first_size = sizes[0] if sizes else None
            first_color = colors[0]
            variants = list(product.variants.filter(is_obsolete=False))
            to_update = []
            product_total_stock = 0
            for variant in variants:
                # محورِ «رنگ» همیشه اول اضافه می‌شود، پس بخشِ اولِ
                # ``value`` (پیش از اولین " / " اگر سایز هم باشد، یا کلِ
                # مقدار اگر فقط محورِ رنگ باشد) همیشه برچسبِ رنگِ همین
                # تنوع است.
                color_label, _, size_label = variant.value.partition(" / ")
                if stock_state == OUT_OF_STOCK:
                    new_stock = 0
                elif stock_state == PARTIAL_VARIANT_STOCK and first_size is not None and size_label == first_size:
                    # ناموجودیِ اولین سایز — چون این شرط رویِ *همه‌یِ*
                    # رنگ‌ها اعمال می‌شود، به‌طورِ طبیعی از مرزِ رنگ عبور
                    # می‌کند (دقیقاً الزامِ صریحِ کار).
                    new_stock = 0
                elif stock_state == PARTIAL_VARIANT_STOCK and first_size is None:
                    # کیفِ چندرنگِ بدونِ سایز: فقط اولین رنگِ (کاور) ناموجود
                    # می‌شود — نمونه‌یِ partial-stock که از مرزِ رنگ عبور
                    # می‌کند بدونِ محورِ سایز.
                    new_stock = 0 if color_label == first_color else _SIMPLE_HEALTHY_STOCK
                elif stock_state == PARTIAL_VARIANT_STOCK:
                    new_stock = _PARTIAL_HEALTHY_VARIANT_STOCK
                else:
                    new_stock = _HEALTHY_VARIANT_STOCK if sizes else _SIMPLE_HEALTHY_STOCK
                product_total_stock += new_stock
                if variant.stock != new_stock:
                    variant.stock = new_stock
                    to_update.append(variant)
            if to_update:
                ProductVariant.objects.bulk_update(to_update, ["stock"])

            if product.stock != product_total_stock:
                product.stock = product_total_stock
                product.save(update_fields=["stock", "updated_at"])

            total += len(variants)
            if variants:
                products_with_variants += 1

        return {"total": total, "products_with_variants": products_with_variants}

    # ------------------------------------------------------------------ Images (real processed WebP — never raw_user_catalog)

    def _seed_product_images(self, products: list) -> int:
        created_count = 0
        for product, colors, _sizes, _stock_state, _is_bag in products:
            if product.images.count() >= 3:
                continue
            color_option = product.options.filter(label="رنگ", is_active=True).first()
            value_by_label = {}
            if color_option is not None:
                value_by_label = {v.label: v for v in color_option.values.filter(is_active=True)}

            for order in (1, 2, 3):
                image = add_product_image(
                    product, _load_processed_image(product.sku, order),
                    alt=f"{product.name} — تصویر {order}",
                )
                # نگاشتِ واقعیِ رنگ→تصویر (Issue 2): ترتیبِ تصویرِ ۱..۳ دقیقاً
                # با ترتیبِ رنگ‌هایِ واقعیِ اعلام‌شده در manifest یکی است —
                # برایِ کالایِ چندرنگ هر تصویر به رنگِ واقعیِ خودش وصل
                # می‌شود؛ برایِ کالایِ تک‌رنگ هر سه تصویر به همان تنها مقدارِ
                # رنگِ موجود وصل می‌شوند (هرگز نگاشتِ ساختگی/حدسی).
                color_for_order = colors[min(order - 1, len(colors) - 1)]
                value = value_by_label.get(color_for_order)
                if value is not None:
                    set_image_option_value(image, value)
                created_count += 1
        return created_count

    def _seed_category_images(self, categories: dict, products: list) -> int:
        """۱۰ تصویرِ واقعاً مفیدِ دسته‌بندی — از عکسِ واقعیِ کاورِ اولین
        کالایِ هر دسته (بدونِ هیچ منبعِ خارجی)."""
        cover_by_category: dict[str, str] = {}
        for product, *_rest in products:
            cover_by_category.setdefault(product.category.name, product.sku)

        created_count = 0
        for category_name, category in categories.items():
            if category.image:
                continue
            sku = cover_by_category.get(category_name)
            if sku is None:
                continue
            source_path = PRODUCT_MEDIA_DIR / sku / "01.webp"
            data = _composite_visual_bytes(
                width=800, height=600, product_paths=[source_path],
                bg_hex=COLOR_HEX.get(next(c for p, c, *_ in products if p.sku == sku)[0], _FALLBACK_COLOR_HEX),
            )
            category.image = SimpleUploadedFile(f"category-{category.slug}.jpg", data, content_type="image/jpeg")
            category.save(update_fields=["image", "updated_at"])
            created_count += 1
        return created_count

    # ------------------------------------------------------------------ Collections

    def _seed_collections(self, store: Store, products: list) -> list:
        all_products = [p for p, *_ in products]
        discounted = [p for p in all_products if p.discount_percent > 0]
        footwear_bag_categories_shoes = {"کتانی رانینگ", "کتانی کژوال", "کفش زنانه", "صندل و دمپایی"}
        bags_categories = BAG_CATEGORIES
        member_map = {
            "جدیدترین‌ها": all_products[-10:],
            "پرفروش‌ها": all_products[:10],
            "تخفیف‌های منتخب": discounted,
            "انتخاب فصل": [p for p in all_products if p.sku in SEASONAL_PICK_SKUS],
            "کفش و کتانی": [p for p in all_products if p.category.name in footwear_bag_categories_shoes],
            "کیف و اکسسوری": [p for p in all_products if p.category.name in bags_categories],
        }

        collections = []
        for definition in COLLECTIONS:
            name = definition["name"]
            collection, _ = MerchantCollection.objects.get_or_create(
                store=store, name=name,
                defaults={
                    "slug": slugify(name, allow_unicode=True),
                    "description": definition["description"],
                    "is_active": True,
                },
            )
            collection_service.add_products(collection, member_map[name])
            collections.append(collection)
        return collections

    # ------------------------------------------------------------------ Hero / Banners / Story rail

    def _seed_hero_slides(self, store: Store, products: list) -> int:
        by_sku = {p.sku: p for p, *_ in products}
        slides = [
            {
                "title": "کالکشن پاییز و زمستان Rasti Mode",
                "subtitle": "کاپشن، ژاکت و کتانی‌های تازه — برایِ استایلِ روزمره",
                "button_label": "مشاهده کالکشن",
                "skus": ["FSH-023", "FSH-026", "FSH-002"],
                "bg": "#3A2F28",
            },
            {
                "title": "دنیایِ کیف Rasti Mode",
                "subtitle": "کیفِ دستی، دوشی و مجلسی برایِ هر موقعیت",
                "button_label": "خرید کیف",
                "skus": ["FSH-041", "FSH-046", "FSH-049"],
                "bg": "#2B2320",
            },
            {
                "title": "کفش و کتانیِ منتخب",
                "subtitle": "از کتانیِ رانینگ تا کفشِ زنانه — همه در یک‌جا",
                "button_label": "مشاهده کفش‌ها",
                "skus": ["FSH-001", "FSH-033", "FSH-038"],
                "bg": "#242A32",
            },
            {
                "title": "تخفیف‌هایِ ویژهٔ این هفته",
                "subtitle": "تا ۲۵٪ تخفیف رویِ منتخبی از کالاهایِ فروشگاه",
                "button_label": "مشاهده تخفیف‌ها",
                "skus": ["FSH-005", "FSH-017", "FSH-039"],
                "bg": "#1F1F1F",
            },
        ]
        created_count = 0
        for order, data in enumerate(slides):
            slide = HeroSlide.objects.filter(store=store, title=data["title"]).first()
            if slide is not None:
                changed = False
                for field, value in (
                    ("subtitle", data["subtitle"]), ("display_order", order), ("is_active", True),
                    ("show_button", True), ("button_label", data["button_label"]),
                    ("destination_type", DestinationType.SEARCH),
                ):
                    if getattr(slide, field) != value:
                        setattr(slide, field, value)
                        changed = True
                if changed:
                    slide.save()
                continue
            slide = HeroSlide(
                store=store, title=data["title"], subtitle=data["subtitle"], display_order=order,
                is_active=True, show_button=True, button_label=data["button_label"],
                destination_type=DestinationType.SEARCH,
            )
            paths = [PRODUCT_MEDIA_DIR / sku / "01.webp" for sku in data["skus"] if sku in by_sku]
            slide.desktop_image = _uploaded_composite(
                filename=f"hero-{order}.jpg", width=1600, height=700, product_paths=paths, bg_hex=data["bg"],
            )
            slide.save()
            created_count += 1
        return created_count

    def _seed_banners(self, store: Store, products: list) -> int:
        by_sku = {p.sku: p for p, *_ in products}
        banners = [
            ("کاپشن و بامبر جدید", ["FSH-021", "FSH-024"], "#39352E"),
            ("جین‌های پرفروش", ["FSH-017", "FSH-020"], "#25344A"),
            ("کتانی رانینگ", ["FSH-004", "FSH-005"], "#2E2E2E"),
            ("کیف تُت روزمره", ["FSH-042", "FSH-044"], "#2A2320"),
            ("صندل تابستانه", ["FSH-036", "FSH-040"], "#3A3226"),
            ("کفش زنانهٔ مجلسی", ["FSH-032", "FSH-035"], "#332B2B"),
        ]
        created_count = 0
        for order, (title, skus, bg) in enumerate(banners):
            banner = PromotionalBanner.objects.filter(store=store, title=title).first()
            if banner is not None:
                changed = False
                for field, value in (
                    ("display_order", order), ("is_active", True),
                    ("show_button", False), ("destination_type", DestinationType.SEARCH),
                ):
                    if getattr(banner, field) != value:
                        setattr(banner, field, value)
                        changed = True
                if changed:
                    banner.save()
                continue
            banner = PromotionalBanner(
                store=store, title=title, display_order=order, is_active=True,
                show_button=False, destination_type=DestinationType.SEARCH,
            )
            paths = [PRODUCT_MEDIA_DIR / sku / "01.webp" for sku in skus if sku in by_sku]
            banner.desktop_image = _uploaded_composite(
                filename=f"banner-{order}.jpg", width=1200, height=500, product_paths=paths, bg_hex=bg,
            )
            banner.save()
            created_count += 1
        return created_count

    def _seed_story_rail(self, store: Store, categories: dict, products: list) -> int:
        cover_by_category: dict[str, str] = {}
        for product, *_rest in products:
            cover_by_category.setdefault(product.category.name, product.sku)

        created_count = 0
        for order, category_name in enumerate(CATEGORY_NAMES):
            category = categories[category_name]
            title = category_name[:20]
            item = StoryRailItem.objects.filter(store=store, title=title, display_order=order).first()
            if item is not None:
                continue
            sku = cover_by_category[category_name]
            item = StoryRailItem(
                store=store, title=title, display_order=order, is_active=True,
                destination_type=DestinationType.CATEGORY, destination_category=category,
            )
            path = PRODUCT_MEDIA_DIR / sku / "01.webp"
            item.image = _uploaded_composite(
                filename=f"story-{order}.jpg", width=400, height=400, product_paths=[path],
                bg_hex=COLOR_HEX.get(next(c for p, c, *_ in products if p.sku == sku)[0], _FALLBACK_COLOR_HEX),
            )
            item.save()
            created_count += 1
        return created_count

    # ------------------------------------------------------------------ Navigation / Footer

    def _seed_navigation(self, store: Store, categories: dict, collections: list) -> None:
        menu, _ = Menu.objects.get_or_create(
            store=store, location=Menu.Location.HEADER, defaults={"title": "منوی اصلی", "is_active": True},
        )
        order = 0
        for category_name in CATEGORY_NAMES:
            category = categories[category_name]
            MenuItem.objects.get_or_create(
                menu=menu, title=category_name, parent=None,
                defaults={
                    "display_order": order, "is_active": True,
                    "destination_type": DestinationType.CATEGORY, "destination_category": category,
                },
            )
            order += 1

        collection_by_name = {c.name: c for c in collections}
        for title in ("جدیدترین‌ها", "پرفروش‌ها", "تخفیف‌های منتخب"):
            collection = collection_by_name.get(title)
            if collection is None:
                continue
            MenuItem.objects.get_or_create(
                menu=menu, title=title, parent=None,
                defaults={
                    "display_order": order, "is_active": True,
                    "destination_type": DestinationType.COLLECTION, "destination_collection": collection,
                },
            )
            order += 1

        footer_menu, _ = Menu.objects.get_or_create(
            store=store, location=Menu.Location.FOOTER_1,
            defaults={"title": "راهنمای خرید", "is_active": True},
        )
        footer_entries = [
            ("جستجوی محصولات", DestinationType.SEARCH, None),
            ("سبد خرید", DestinationType.CART, None),
            ("تازه‌ترین‌ها", DestinationType.COLLECTION, collection_by_name.get("جدیدترین‌ها")),
            ("تخفیف‌های منتخب", DestinationType.COLLECTION, collection_by_name.get("تخفیف‌های منتخب")),
        ]
        for f_order, (item_title, destination_type, target) in enumerate(footer_entries):
            if destination_type == DestinationType.COLLECTION and target is None:
                continue
            defaults = {"display_order": f_order, "is_active": True, "destination_type": destination_type}
            if destination_type == DestinationType.COLLECTION:
                defaults["destination_collection"] = target
            MenuItem.objects.get_or_create(menu=footer_menu, title=item_title, parent=None, defaults=defaults)

    def _seed_footer(self, store: Store, categories: dict, collections: list) -> None:
        footer = FooterSettings.provision_for(store)
        changed = False
        if not footer.description:
            footer.description = (
                "Rasti Mode Demo یک فروشگاهِ نمایشیِ ایزوله برایِ آزمونِ Storefront و "
                "قالب‌های آماده‌یِ راستی‌سی است — پوشاک، کفش و کیف با دادهٔ کاملاً قطعی."
            )
            changed = True
        if not footer.address:
            footer.address = "تهران — آدرسِ نمایشیِ Demo (بدونِ آدرسِ واقعی)"
            changed = True
        if not footer.phone:
            footer.phone = "02100000000"
            changed = True
        if not footer.email:
            footer.email = "demo@rasti-mode-demo.internal"
            changed = True
        if not footer.copyright_text:
            footer.copyright_text = "© Rasti Mode Demo — یک فروشگاهِ نمایشیِ راستی‌سی"
            changed = True
        if not footer.working_hours:
            footer.working_hours = "شنبه تا پنج‌شنبه، ۹ تا ۱۸ (نمایشی)"
            changed = True
        if changed:
            footer.save()
