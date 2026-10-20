"""دستور idempotent برای ساختِ یک فروشگاهِ QA/Demo کاملاً جدا (پوشاک) —
«فروشگاه لباس تستی راستی سی» — برایِ آزمونِ بصری/تعاملیِ سیستمِ Layout
Presetِ V2 (Phase 6) رویِ یک مجموعه‌دادهٔ واقعیِ یکسان. پیش از Phase 7
این دستور شش Familyِ قدیمی را منتشر می‌کرد؛ با بازنشستگیِ کاملِ سیستمِ
Family، اکنون یک Layout Preset (``layout_preset_registry``) منتشر
می‌کند — همان مجموعه‌دادهٔ کاتالوگ/محتوا دست‌نخورده می‌ماند.

فقط برایِ محیطِ توسعه: در ``DEBUG=False`` اجرا نمی‌شود (این دستور دادهٔ
تستیِ فراوان می‌سازد و هرگز نباید در یک دیتابیسِ Production اجرا شود).

Idempotent: اجرایِ دوباره رکوردِ تکراری نمی‌سازد — همه‌جا از
``get_or_create``/``update_or_create`` رویِ فیلدِ یکتا (معمولاً ``slug``
درونِ همینِ Store) استفاده می‌شود.

Tenant-scoped: این دستور فقط رکوردهایِ متعلق به همینِ Storeِ QA (یا
User/StoreMembership مرتبط) می‌سازد/می‌خواند — هرگز به Storeِ دیگری
(``akhlaghi`` یا هر Storeِ دیگری که مالک روی همان دیتابیس دارد) دست
نمی‌زند. ``--reset`` هم فقط همینِ Storeِ QA را حذف/بازسازی می‌کند؛
هیچ‌وقت Storeِ دیگری را حذف نمی‌کند.

استفاده:
    python manage.py seed_rastisi_fashion_demo --owner-username <کاربرِ موجود>
    python manage.py seed_rastisi_fashion_demo --owner-username <کاربرِ موجود> --reset
"""

from __future__ import annotations

from decimal import Decimal
from datetime import timedelta
from io import BytesIO
import hashlib

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont

from apps.blog.models import BlogPost
from apps.catalog.models import (
    Brand,
    Category,
    MerchantCollection,
    MerchantCollectionItem,
    Product,
    Vendor,
)
from apps.catalog.services.product_image_service import add_product_image, set_image_variant
from apps.catalog.services.variant_service import create_variant
from apps.content.models import (
    ContentPage,
    DestinationType,
    FooterPaymentLogo,
    FooterSettings,
    FooterTrustBadge,
    HeroSlide,
    Menu,
    MenuItem,
    PromotionalBanner,
    SocialLink,
    StoryRailItem,
)
from apps.core.models import ShopSettings
from apps.storefront_builder import layout_preset_registry
from apps.storefront_builder.services import layout_service, preset_service
from apps.stores.hostnames import normalize_admin_subdomain
from apps.stores.models import Store, StoreDomain, StoreMembership

User = get_user_model()

# --------------------------------------------------------------- شناسهٔ فروشگاه

STORE_SLUG = "rastisi-fashion-test"
STORE_NAME = "فروشگاه لباس تستی راستی سی"
STORE_ADMIN_SUBDOMAIN = "rastisi-fashion-test"

STORE_CONTACT = {
    "tagline": "استایل امروز، انتخاب ماندگار",
    "description": (
        "راستی استایل یک فروشگاه نمایشی پوشاک برای ارزیابی واقعی صفحهٔ فروشگاه است؛ "
        "از لباس روزمره و رسمی تا کفش، کیف و اکسسوری با اطلاعات کامل محصول، تنوع رنگ و سایز."
    ),
    "contact_phone": "09121234567",
    "contact_email": "hello@rastistyle.test",
    "contact_address": "تهران، بلوار میرداماد، مجتمع راستی استایل",
}
STORE_TELEPHONE = "02112345678"
STORE_POSTAL_CODE = "1234512345"
STORE_SUPPORT_HOURS = "شنبه تا چهارشنبه ۹ تا ۱۸ / پنجشنبه ۹ تا ۱۴"

GIFT_WRAP_PRICE = Decimal("25000")

# --------------------------------------------------------------- دسته‌بندی‌ها

PRIMARY_CATEGORIES = [
    {"name": "تی‌شرت و تاپ", "slug": "tshirt-top", "icon": "👕", "children": [
        {"name": "تی‌شرت مردانه", "slug": "tshirt-men"},
        {"name": "تاپ زنانه", "slug": "top-women"},
    ]},
    {"name": "پیراهن", "slug": "shirt", "icon": "👔", "children": [
        {"name": "پیراهن رسمی", "slug": "shirt-formal"},
        {"name": "پیراهن کژوال", "slug": "shirt-casual"},
    ]},
    {"name": "شلوار و جین", "slug": "pants-jeans", "icon": "👖", "children": [
        {"name": "شلوار جین", "slug": "jeans"},
        {"name": "شلوار کتان", "slug": "pants-chino"},
    ]},
    {"name": "مانتو و رویه", "slug": "manto-overlay", "icon": "🧥", "children": [
        {"name": "مانتو مجلسی", "slug": "manto-formal"},
        {"name": "رویه کژوال", "slug": "overlay-casual"},
    ]},
    {"name": "کت و کاپشن", "slug": "coat-jacket", "icon": "🧥", "children": [
        {"name": "کت رسمی", "slug": "coat-formal"},
        {"name": "کاپشن زمستانی", "slug": "jacket-winter"},
    ]},
    {"name": "هودی و سویشرت", "slug": "hoodie-sweatshirt", "icon": "🧶", "children": [
        {"name": "هودی کلاه‌دار", "slug": "hoodie-hooded"},
        {"name": "سویشرت یقه‌گرد", "slug": "sweatshirt-crew"},
    ]},
    {"name": "لباس ورزشی", "slug": "sportswear", "icon": "🏃", "children": [
        {"name": "شلوار ورزشی", "slug": "sport-pants"},
        {"name": "تیشرت ورزشی", "slug": "sport-tshirt"},
    ]},
    {"name": "کفش", "slug": "shoes", "icon": "👟", "children": [
        {"name": "کفش روزمره", "slug": "shoes-casual"},
        {"name": "کفش ورزشی", "slug": "shoes-sport"},
    ]},
    {"name": "کیف", "slug": "bag", "icon": "👜", "children": [
        {"name": "کیف دوشی", "slug": "bag-shoulder"},
        {"name": "کیف دستی", "slug": "bag-handbag"},
    ]},
    {"name": "اکسسوری", "slug": "accessory", "icon": "🧣", "children": [
        {"name": "شال و روسری", "slug": "accessory-scarf"},
        {"name": "کمربند و کلاه", "slug": "accessory-belt-hat"},
    ]},
]

BRANDS = [
    {"name": "آریا استایل", "name_en": "ARIA", "slug": "aria-style", "country": "ایران", "description": "پوشاک مینیمال و روزمره"},
    {"name": "ویرا پوش", "name_en": "VIRA", "slug": "vira-poosh", "country": "ایران", "description": "استایل شهری و نیمه‌رسمی"},
    {"name": "ماهان مد", "name_en": "MAHAN", "slug": "mahan-mode", "country": "ایران", "description": "کالکشن‌های زنانه و اکسسوری"},
    {"name": "رایان کژوال", "name_en": "RAYAN", "slug": "rayan-casual", "country": "ایران", "description": "پوشاک کژوال و ورزشی"},
    {"name": "نورا", "name_en": "NORA", "slug": "nora", "country": "ایران", "description": "مانتو و رویه‌های مدرن"},
    {"name": "اُربان", "name_en": "URBAN", "slug": "urban", "country": "ایران", "description": "استایل خیابانی و راحت"},
]

VENDOR = {"name": "فروشندهٔ QA راستی سی", "slug": "rastisi-fashion-vendor"}

COLLECTIONS = [
    {"name": "پرفروش‌های راستی سی", "slug": "bestsellers-rastisi"},
    {"name": "تازه رسیده‌ها", "slug": "new-arrivals-rastisi"},
    {"name": "تخفیف ویژه", "slug": "special-discount-rastisi"},
    {"name": "استایل روزمره", "slug": "everyday-style-rastisi"},
    {"name": "انتخاب تابستانی", "slug": "summer-pick-rastisi"},
    {"name": "پیشنهاد راستی سی", "slug": "rastisi-recommends"},
]

SIZES = ["S", "M", "L", "XL"]
COLORS = [
    ("مشکی", "#1F2937"),
    ("سفید", "#F9FAFB"),
    ("سرمه‌ای", "#1E3A8A"),
    ("کرم", "#F5E9D6"),
    ("سبز", "#166534"),
    ("آبی", "#2563EB"),
    ("قرمز", "#DC2626"),
]

NAME_PATTERNS = {
    "tshirt-men": "تی‌شرت نخی مردانه مدل {name}",
    "top-women": "تاپ زنانه مدل {name}",
    "shirt-formal": "پیراهن رسمی مدل {name}",
    "shirt-casual": "پیراهن کژوال مدل {name}",
    "jeans": "شلوار جین مدل {name}",
    "pants-chino": "شلوار کتان مدل {name}",
    "manto-formal": "مانتو مجلسی مدل {name}",
    "overlay-casual": "رویهٔ کژوال مدل {name}",
    "coat-formal": "کت رسمی مدل {name}",
    "jacket-winter": "کاپشن زمستانی مدل {name}",
    "hoodie-hooded": "هودی کلاه‌دار مدل {name}",
    "sweatshirt-crew": "سویشرت یقه‌گرد مدل {name}",
    "sport-pants": "شلوار ورزشی مدل {name}",
    "sport-tshirt": "تیشرت ورزشی مدل {name}",
    "shoes-casual": "کفش روزمره مدل {name}",
    "shoes-sport": "کفش ورزشی مدل {name}",
    "bag-shoulder": "کیف دوشی مدل {name}",
    "bag-handbag": "کیف دستی مدل {name}",
    "accessory-scarf": "شال و روسری مدل {name}",
    "accessory-belt-hat": "کمربند و کلاه مدل {name}",
}

FIRST_NAMES = [
    "آریا", "ویرا", "ماهان", "آوا", "رایان", "هانا", "سارینا", "کیانا", "آرمین",
    "دنیز", "پارمیس", "رها", "آرتین", "ستایش", "بردیا", "نیکا", "سام", "یاسمین",
    "پرهام", "الینا",
]

CONTENT_PAGES = [
    {"title": "درباره ما", "slug": "about-us", "footer_column": ContentPage.FooterColumn.QUICK_ACCESS,
     "body": "فروشگاه لباس تستی راستی سی — یک مجموعه‌دادهٔ QA برایِ آزمونِ بصریِ Storefront Builder."},
    {"title": "تماس با ما", "slug": "contact-us", "footer_column": ContentPage.FooterColumn.QUICK_ACCESS,
     "body": f"تلفن: {STORE_TELEPHONE} — ایمیل: {STORE_CONTACT['contact_email']}"},
    {"title": "روش‌های ارسال", "slug": "shipping-methods", "footer_column": ContentPage.FooterColumn.CUSTOMER_SERVICE,
     "body": "این یک متنِ آزمایشیِ روش‌های ارسال است — صرفاً برایِ آزمونِ فروشگاهِ QA."},
    {"title": "شرایط مرجوعی", "slug": "return-policy", "footer_column": ContentPage.FooterColumn.CUSTOMER_SERVICE,
     "body": "این یک متنِ آزمایشیِ شرایطِ مرجوعی است — صرفاً برایِ آزمونِ فروشگاهِ QA."},
    {"title": "راهنمای خرید", "slug": "shopping-guide", "footer_column": ContentPage.FooterColumn.CUSTOMER_SERVICE,
     "body": "این یک متنِ آزمایشیِ راهنمایِ خرید است — صرفاً برایِ آزمونِ فروشگاهِ QA."},
    {"title": "حریم خصوصی", "slug": "privacy-policy", "footer_column": ContentPage.FooterColumn.CUSTOMER_SERVICE,
     "body": "این یک متنِ آزمایشیِ حریمِ خصوصی است — صرفاً برایِ آزمونِ فروشگاهِ QA."},
]

DEFAULT_LAYOUT_PRESET_KEY = "v5_golden_homepage"


def _text_font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.lstrip("#")
    if len(value) != 6:
        return (124, 58, 237)
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _mix(color: tuple[int, int, int], target: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    return tuple(round(a + (b - a) * amount) for a, b in zip(color, target))


def _fashion_kind(label: str) -> str:
    text = (label or "").lower()
    if any(key in text for key in ("شلوار", "جین", "pants", "jeans")):
        return "pants"
    if any(key in text for key in ("کفش", "shoe", "sneaker")):
        return "shoe"
    if any(key in text for key in ("کیف", "bag")):
        return "bag"
    if any(key in text for key in ("شال", "روسری", "کمربند", "کلاه", "accessory")):
        return "accessory"
    if any(key in text for key in ("کت", "کاپشن", "مانتو", "رویه", "hoodie", "هودی")):
        return "outerwear"
    return "top"


def _draw_garment(draw: ImageDraw.ImageDraw, box, color, kind: str, accent) -> None:
    x0, y0, x1, y1 = [int(v) for v in box]
    w, h = x1 - x0, y1 - y0
    cx = x0 + w // 2
    outline = _mix(color, (0, 0, 0), .28)

    if kind == "pants":
        waist_y = y0 + int(h * .10)
        crotch_y = y0 + int(h * .45)
        leg_bottom = y1 - int(h * .06)
        draw.rounded_rectangle((x0 + int(w*.25), waist_y, x1 - int(w*.25), crotch_y), radius=max(6, w//28), fill=color, outline=outline, width=max(2, w//90))
        draw.polygon([(x0+int(w*.28), crotch_y-4), (cx-5, crotch_y), (cx-int(w*.10), leg_bottom), (x0+int(w*.18), leg_bottom)], fill=color, outline=outline)
        draw.polygon([(cx+5, crotch_y), (x1-int(w*.28), crotch_y-4), (x1-int(w*.18), leg_bottom), (cx+int(w*.10), leg_bottom)], fill=color, outline=outline)
        draw.line((cx, waist_y+8, cx, crotch_y-5), fill=accent, width=max(2, w//100))
    elif kind == "shoe":
        sole_y = y0 + int(h*.72)
        draw.rounded_rectangle((x0+int(w*.12), sole_y, x1-int(w*.08), sole_y+int(h*.10)), radius=max(8, h//28), fill=_mix(color,(255,255,255),.15), outline=outline, width=max(2,w//90))
        draw.polygon([(x0+int(w*.20), sole_y), (x0+int(w*.33), y0+int(h*.35)), (x0+int(w*.55), y0+int(h*.38)), (x0+int(w*.70), y0+int(h*.58)), (x1-int(w*.08), sole_y)], fill=color, outline=outline)
        for i in range(3):
            yy=y0+int(h*(.46+i*.06))
            draw.line((x0+int(w*.38),yy,x0+int(w*.58),yy+4),fill=accent,width=max(2,w//100))
    elif kind == "bag":
        by0=y0+int(h*.30)
        by1=y1-int(h*.10)
        draw.rounded_rectangle((x0+int(w*.17),by0,x1-int(w*.17),by1),radius=max(12,w//18),fill=color,outline=outline,width=max(2,w//90))
        draw.arc((x0+int(w*.32),y0+int(h*.08),x1-int(w*.32),y0+int(h*.48)),180,360,fill=outline,width=max(5,w//45))
        draw.rounded_rectangle((cx-int(w*.11),by0+int(h*.16),cx+int(w*.11),by0+int(h*.22)),radius=6,fill=accent)
    elif kind == "accessory":
        draw.ellipse((x0+int(w*.20),y0+int(h*.20),x1-int(w*.20),y1-int(h*.20)),fill=color,outline=outline,width=max(3,w//80))
        draw.ellipse((x0+int(w*.34),y0+int(h*.34),x1-int(w*.34),y1-int(h*.34)),fill=_mix(color,(255,255,255),.55))
        draw.rounded_rectangle((cx-int(w*.06),y0+int(h*.18),cx+int(w*.06),y1-int(h*.18)),radius=8,fill=accent)
    else:
        neck_w=int(w*.16)
        shoulder_y=y0+int(h*.17)
        body_top=y0+int(h*.24)
        body_bottom=y1-int(h*.06)
        if kind == "outerwear":
            left=x0+int(w*.18); right=x1-int(w*.18)
            draw.rounded_rectangle((left,body_top,right,body_bottom),radius=max(14,w//24),fill=color,outline=outline,width=max(2,w//90))
            draw.polygon([(left,body_top+int(h*.06)),(x0+int(w*.04),y0+int(h*.40)),(x0+int(w*.12),y0+int(h*.52)),(left+int(w*.07),y0+int(h*.39))],fill=color,outline=outline)
            draw.polygon([(right,body_top+int(h*.06)),(x1-int(w*.04),y0+int(h*.40)),(x1-int(w*.12),y0+int(h*.52)),(right-int(w*.07),y0+int(h*.39))],fill=color,outline=outline)
            draw.line((cx,body_top+6,cx,body_bottom-8),fill=accent,width=max(2,w//90))
        else:
            points=[(cx-neck_w,body_top),(x0+int(w*.13),shoulder_y+int(h*.08)),(x0+int(w*.03),y0+int(h*.40)),(x0+int(w*.18),y0+int(h*.46)),(x0+int(w*.24),body_bottom),(x1-int(w*.24),body_bottom),(x1-int(w*.18),y0+int(h*.46)),(x1-int(w*.03),y0+int(h*.40)),(x1-int(w*.13),shoulder_y+int(h*.08)),(cx+neck_w,body_top)]
            draw.polygon(points,fill=color,outline=outline)
        draw.ellipse((cx-neck_w,y0+int(h*.09),cx+neck_w,y0+int(h*.27)),fill=_mix(color,(255,255,255),.65),outline=outline)


def _generate_image_bytes(*, width: int, height: int, bg_hex: str, label: str) -> bytes:
    """تصویرِ کاملاً محلی و کپی‌رایت-ایمن برای Demo پوشاک.

    به‌جایِ کارتِ متنیِ قدیمی، یک تصویرِ استودیوییِ تمیز با سیلوئتِ واقعیِ
    نوعِ محصول می‌سازد. هدف، ارزیابیِ جدیِ نسبتِ عکس/کارت/بنر در Storefront
    است؛ هیچ فایل یا URL خارجی در Runtime لازم نیست.
    """
    seed = hashlib.sha256((label or "fashion").encode("utf-8")).digest()
    source = _rgb(bg_hex)
    garment = _mix(source, (30, 30, 36), .24 if sum(source) > 500 else .02)
    accent = _mix(garment, (255, 255, 255), .70)
    kind = _fashion_kind(label)

    # Hero/banner: قاب ادیتوریالِ عریض با دو محصول بزرگ و فضای خالی برای متن HTML.
    if width / max(height, 1) > 1.55:
        base = _mix(source, (250, 249, 246), .40)
        image = Image.new("RGB", (width, height), base)
        draw = ImageDraw.Draw(image)
        draw.ellipse((-int(width*.08), -int(height*.45), int(width*.42), int(height*.90)), fill=_mix(source,(255,255,255),.12))
        draw.ellipse((int(width*.64), int(height*.30), int(width*1.05), int(height*1.18)), fill=_mix(source,(255,255,255),.24))
        # soft floor/shadows
        draw.ellipse((int(width*.08), int(height*.77), int(width*.52), int(height*.92)), fill=_mix(base,(0,0,0),.10))
        draw.ellipse((int(width*.43), int(height*.72), int(width*.80), int(height*.88)), fill=_mix(base,(0,0,0),.08))
        _draw_garment(draw,(width*.10,height*.10,width*.42,height*.84),garment,kind,accent)
        second=_mix(garment,(255,255,255),.30)
        _draw_garment(draw,(width*.44,height*.17,width*.70,height*.78),second,"outerwear" if kind!="outerwear" else "top",_mix(second,(255,255,255),.68))
    else:
        # Product/category: بک‌گراند استودیویی خنثی، سایه، پودیوم و پوشاک.
        bg = (247, 246, 243)
        image = Image.new("RGB", (width, height), bg)
        draw = ImageDraw.Draw(image)
        panel = _mix(source, (255,255,255), .72)
        margin=int(width*.07)
        draw.rounded_rectangle((margin,margin,width-margin,height-margin),radius=max(18,width//22),fill=panel)
        draw.ellipse((int(width*.18),int(height*.76),int(width*.82),int(height*.88)),fill=_mix(panel,(0,0,0),.12))
        shift=(seed[0] % max(1,int(width*.04))) - int(width*.02)
        _draw_garment(draw,(width*.17+shift,height*.10,width*.83+shift,height*.78),garment,kind,accent)

    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=90, optimize=True)
    return buffer.getvalue()


def _uploaded_image(*, filename: str, width: int, height: int, bg_hex: str, label: str) -> SimpleUploadedFile:
    data = _generate_image_bytes(width=width, height=height, bg_hex=bg_hex, label=label)
    return SimpleUploadedFile(filename, data, content_type="image/jpeg")


def _uploaded_brand_logo(*, filename: str, text: str, bg_hex: str) -> SimpleUploadedFile:
    image = Image.new("RGB", (420, 180), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    color = _rgb(bg_hex)
    draw.rounded_rectangle((12, 12, 408, 168), radius=24, outline=_mix(color,(255,255,255),.35), width=3)
    font = _text_font(44)
    label = (text or "STYLE")[:12]
    try:
        bbox = draw.textbbox((0,0), label, font=font)
        tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
    except AttributeError:
        tw, th = draw.textsize(label, font=font)
    draw.text(((420-tw)/2,(180-th)/2-4),label,font=font,fill=color)
    buffer=BytesIO(); image.save(buffer,format="JPEG",quality=92,optimize=True)
    return SimpleUploadedFile(filename,buffer.getvalue(),content_type="image/jpeg")



def _uploaded_footer_badge(*, filename: str, text: str, bg_hex: str) -> SimpleUploadedFile:
    """Small local-only trust/payment badge used by the demo Store."""
    image = Image.new("RGB", (180, 180), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    color = _rgb(bg_hex)
    draw.rounded_rectangle((10, 10, 170, 170), radius=24, outline=_mix(color, (255,255,255), .25), width=4)
    draw.ellipse((54, 28, 126, 100), fill=_mix(color, (255,255,255), .70), outline=color, width=3)
    font = _text_font(24)
    label = (text or "SAFE")[:8]
    try:
        bbox = draw.textbbox((0,0), label, font=font); tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
    except AttributeError:
        tw, th = draw.textsize(label, font=font)
    draw.text(((180-tw)/2, 116), label, font=font, fill=color)
    buffer = BytesIO(); image.save(buffer, format="JPEG", quality=92, optimize=True)
    return SimpleUploadedFile(filename, buffer.getvalue(), content_type="image/jpeg")


class Command(BaseCommand):
    help = (
        "می‌سازد/بازمی‌سازد یک فروشگاهِ QA/Demo کاملاً جدا (پوشاک، «فروشگاه لباس "
        "تستی راستی سی») برایِ آزمونِ بصریِ سیستمِ Layout Presetِ Storefront Builder. "
        "Idempotent، Tenant-scoped، فقط در DEBUG اجرا می‌شود."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--owner-username", required=True,
            help="یوزرنیمِ یک کاربرِ از‌قبل‌موجود که مالکِ StoreMembership این فروشگاهِ QA خواهد شد.",
        )
        parser.add_argument(
            "--reset", action="store_true",
            help=(
                "پیش از ساختنِ دوباره، این Storeِ QA (فقط با اسلاگِ "
                f"«{STORE_SLUG}») را کاملاً حذف می‌کند — هرگز Storeِ دیگری را لمس نمی‌کند."
            ),
        )
        parser.add_argument(
            "--preset", default=DEFAULT_LAYOUT_PRESET_KEY,
            help=f"کلیدِ Layout Presetی که در پایان منتشر می‌شود (پیش‌فرض: {DEFAULT_LAYOUT_PRESET_KEY}).",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "این دستور فقط در DEBUG=True قابل‌اجراست — یک دیتابیسِ Production هرگز "
                "نباید دادهٔ QA/Demo دریافت کند."
            )

        owner_username = options["owner_username"]
        try:
            owner = User.objects.get(username=owner_username)
        except User.DoesNotExist as exc:
            raise CommandError(
                f"کاربری با یوزرنیمِ «{owner_username}» یافت نشد. این دستور هرگز یک کاربرِ "
                "ناامنِ پیش‌فرض نمی‌سازد — ابتدا کاربر را با «python manage.py createsuperuser» "
                "یا مسیرِ ثبت‌نامِ عادیِ فروشگاه بسازید، سپس دوباره اجرا کنید."
            ) from exc

        preset_key = options["preset"]
        preset = layout_preset_registry.get_layout_preset(preset_key)
        if preset is None:
            valid = ", ".join(sorted(layout_preset_registry.LAYOUT_PRESET_REGISTRY.keys()))
            raise CommandError(f"Presetِ «{preset_key}» در Registry ثبت نشده. Presetهایِ معتبر: {valid}")

        if options["reset"]:
            self._reset(owner_username)

        with transaction.atomic():
            store = self._seed_store()
            self._seed_domain(store)
            self._seed_membership(store, owner)
            self._seed_shop_settings(store)
            self._seed_footer_settings(store)
            footer_media_stats = self._seed_footer_media(store)
            social_link_count = self._seed_social_links(store)
            vendor = self._seed_vendor(store)
            categories = self._seed_categories(store)
            category_image_count = self._seed_category_images(categories)
            brands = self._seed_brands(store)
            products = self._seed_products(store, vendor, categories, brands)
            variant_stats = self._seed_variants(products)
            image_stats = self._seed_product_images(products)
            collections = self._seed_collections(store, products)
            hero_count = self._seed_hero_slides(store)
            banner_count = self._seed_banners(store)
            story_count = self._seed_story_rail(store, categories, products, collections)
            menu_item_count = self._seed_navigation(store, categories, collections)
            footer_menu_count = self._seed_footer_menus(store, categories, collections)
            content_page_count = self._seed_content_pages(store)
            blog_post_count = self._seed_blog_posts(store)
            self._seed_builder(store, owner, preset)

        self.stdout.write(self.style.SUCCESS(
            "seed_rastisi_fashion_demo با موفقیت اجرا شد:\n"
            f"  Store: {store.slug} (admin_subdomain={store.admin_subdomain})\n"
            f"  دسته‌بندی: {Category.objects.filter(store=store).count()}\n"
            f"  برند: {Brand.objects.filter(store=store).count()}\n"
            f"  تصویر دسته‌بندی: {category_image_count}\n"
            f"  کالا: {Product.objects.filter(store=store).count()}\n"
            f"  تنوع: {variant_stats['total']} (روی {variant_stats['products_with_variants']} کالا؛ "
            f"{variant_stats['image_mapped']} تنوعِ تصویرمحور)\n"
            f"  تصویرِ کالا: {image_stats}\n"
            f"  کالکشن: {len(collections)}\n"
            f"  اسلایدِ هیرو: {hero_count}\n"
            f"  بنر تبلیغاتی: {banner_count}\n"
            f"  آیتمِ استوری: {story_count}\n"
            f"  آیتمِ منوی هدر: {menu_item_count}\n"
            f"  آیتمِ منوی فوتر: {footer_menu_count}\n"
            f"  نماد اعتماد/پرداخت: {footer_media_stats['trust']}/{footer_media_stats['payment']}\n"
            f"  شبکه‌های اجتماعی فوتر: {social_link_count}\n"
            f"  صفحهٔ محتوایی: {content_page_count}\n"
            f"  مطلب وبلاگ نمایشی: {blog_post_count}\n"
            f"  Presetِ منتشرشده: {preset.key}\n"
            "  ویدیویِ کالا: SKIPPED — نیازمندِ یک لینکِ خارجیِ واقعیِ یوتیوب/آپارات/"
            "اینستاگرام است (apps.catalog.models.ProductVideo.url)؛ هیچ گزینهٔ محلیِ "
            "کپی‌رایت-ایمن برایِ این مدل وجود ندارد، پس عمداً seed نشد."
        ))

    # ------------------------------------------------------------------ Reset

    @transaction.atomic
    def _reset(self, owner_username):
        """فقط Storeِ QA با همینِ اسلاگِ ثابت را حذف می‌کند — هرگز Storeِ
        دیگری (حتی اگر همان owner عضوش باشد) را لمس نمی‌کند. اتمیک: اگر حذف
        در میانه شکست بخورد، هیچ‌چیزی نصفه‌کاره حذف نمی‌شود.

        ``Store.delete()`` مستقیم به‌تنهایی کافی نیست: دو زنجیره‌یِ
        ``on_delete=PROTECT`` واقعاً روی گراف دادهٔ همین دستور وجود دارد —
        ``Product.category`` (PROTECT) و ``MenuItem.menu`` (PROTECT). وقتی
        Django سعی می‌کند از طریقِ CASCADEِ ``Category.store``/``Menu.store``
        این دو مدل را هم حذف کند، وجودِ Productها/MenuItemهایِ هنوز-موجود
        باعثِ ``ProtectedError`` می‌شود. راه‌حل: ابتدا خودِ Productها و
        MenuItemها (که آن دو PROTECT را نگه داشته‌اند) صریحاً و فقط برایِ
        همینِ Storeِ QA حذف می‌شوند — پس از آن، ``Store.delete()`` بقیه‌ی
        گراف (Category/Brand/Vendor/Menu/MerchantCollection/ContentPage/
        HeroSlide/PromotionalBanner/StoryRailItem/FooterSettings/
        ShopSettings/StoreMembership/StoreDomain/StorefrontLayout+نسخه‌ها+
        بخش‌ها) را کاملاً امن و بدونِ خطا از طریقِ CASCADEِ معمولی پاک می‌کند.
        هیچ مدلی از PROTECT به CASCADE تغییر داده نشده و هیچ راهِ حذفِ خام/
        بدونِ‌قید (raw SQL) استفاده نشده — فقط ترتیبِ حذف اصلاح شده است."""
        existing = Store.objects.filter(slug=STORE_SLUG).first()
        if existing is None:
            self.stdout.write("  --reset: Storeِ QA از قبل وجود نداشت — چیزی حذف نشد.")
            return
        self.stdout.write(f"  --reset: حذفِ کاملِ Storeِ QA «{existing.slug}» (pk={existing.pk})…")

        # قدمِ ۱ — Productهایِ همینِ Store را حذف کن تا PROTECTِ
        # Product.category آزاد شود (ProductVariant/ProductImage/
        # MerchantCollectionItem/... همه از طریقِ CASCADEِ خودِ Product پاک
        # می‌شوند). فیلترِ ``store=existing`` تضمین می‌کند هیچ کالایِ
        # فروشگاهِ دیگری لمس نشود.
        Product.objects.filter(store=existing).delete()

        # قدمِ ۲ — MenuItemهایِ منوهایِ همینِ Store را حذف کن تا PROTECTِ
        # MenuItem.menu آزاد شود. فیلترِ ``menu__store=existing`` تضمین
        # می‌کند هیچ آیتمِ منویِ فروشگاهِ دیگری لمس نشود.
        MenuItem.objects.filter(menu__store=existing).delete()

        # MediaAsset is Store-owned, while homepage placements reference it
        # through PROTECT. Remove only this QA Store's placements first so
        # Store.delete() can safely cascade through its MediaAsset rows.
        HeroSlide.objects.filter(store=existing).delete()
        PromotionalBanner.objects.filter(store=existing).delete()
        StoryRailItem.objects.filter(store=existing).delete()

        # قدمِ ۳ — اکنون Store.delete() بدونِ هیچ PROTECTِ باقی‌مانده، امن
        # است؛ بقیه‌ی گرافِ Store-owned از طریقِ CASCADEِ معمولیِ مدل‌ها پاک
        # می‌شود.
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
        self._log("Store", 1 if created else 0)
        return store

    def _seed_domain(self, store: Store) -> None:
        """میزبانِ عمومیِ توسعه — ``<admin_subdomain>.rastisi.localhost`` در
        DEBUG (``settings.RASTISI_ADMIN_DOMAIN_SUFFIX``) — با
        ``verification_status=VERIFIED``/``verified_at`` مقداردهی‌شده تا
        ``domain_is_eligible_for_routing`` واقعاً صادقانه اجازهٔ رندرِ
        عمومی/Publicِ فروشگاه را بدهد (نگاه کنید به
        ``apps.stores.resolution``)."""
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
        self._log("StoreDomain", 1 if created else 0)

    def _seed_membership(self, store: Store, owner) -> None:
        membership, created = StoreMembership.objects.get_or_create(
            store=store, user=owner,
            defaults={
                "role": StoreMembership.Role.OWNER,
                "status": StoreMembership.MembershipStatus.ACTIVE,
                "accepted_at": timezone.now(),
            },
        )
        if not created and membership.status != StoreMembership.MembershipStatus.ACTIVE:
            membership.role = StoreMembership.Role.OWNER
            membership.status = StoreMembership.MembershipStatus.ACTIVE
            membership.accepted_at = membership.accepted_at or timezone.now()
            membership.save(update_fields=["role", "status", "accepted_at", "updated_at"])
        self._log("StoreMembership", 1 if created else 0)

    def _seed_shop_settings(self, store: Store) -> None:
        shop = ShopSettings.provision_for(store)
        shop.name = "راستی استایل"
        shop.tagline = STORE_CONTACT["tagline"]
        shop.description = STORE_CONTACT["description"]
        shop.contact_phone = STORE_CONTACT["contact_phone"]
        shop.contact_email = STORE_CONTACT["contact_email"]
        shop.contact_address = STORE_CONTACT["contact_address"]
        # کادوپیچی (Toranj) — فعال با یک قیمتِ نمونهٔ منطقی (تومان).
        shop.gift_wrap_available = True
        shop.gift_wrap_price = GIFT_WRAP_PRICE
        shop.save()
        self._log("ShopSettings", 0, note="provision + به‌روزرسانیِ هویت/کادوپیچی")

    def _seed_footer_settings(self, store: Store) -> None:
        footer = FooterSettings.provision_for(store)
        footer.is_enabled = True
        footer.show_branding = True
        footer.description = STORE_CONTACT["description"]
        footer.show_contact = True
        footer.address = STORE_CONTACT["contact_address"]
        footer.phone = STORE_TELEPHONE
        footer.email = STORE_CONTACT["contact_email"]
        footer.working_hours = STORE_SUPPORT_HOURS
        footer.show_navigation = True
        footer.show_social_links = True
        footer.show_trust_badges = True
        footer.show_payment_logos = True
        footer.copyright_text = "© راستی استایل — همه حقوق محفوظ است"
        footer.save()
        self._log("FooterSettings", 0, note="provision + به‌روزرسانیِ هویت")

    def _seed_footer_media(self, store: Store) -> dict:
        trust_defs = [("نماد اعتماد", "TRUST", "#0F766E"), ("ضمانت خرید", "SAFE", "#1D4ED8"), ("اصالت کالا", "ORIG", "#7C3AED"), ("پشتیبانی", "HELP", "#B45309")]
        payment_defs = [("پرداخت امن", "PAY", "#16A34A"), ("کارت بانکی", "CARD", "#334155")]
        trust_created = 0; payment_created = 0
        for order, (title, text, color) in enumerate(trust_defs):
            if FooterTrustBadge.objects.filter(store=store, title=title).exists():
                continue
            badge = FooterTrustBadge(store=store, title=title, display_order=order, is_active=True)
            badge.image = _uploaded_footer_badge(filename=f"trust-{order}.jpg", text=text, bg_hex=color)
            badge.save(); trust_created += 1
        for order, (title, text, color) in enumerate(payment_defs):
            if FooterPaymentLogo.objects.filter(store=store, title=title).exists():
                continue
            logo = FooterPaymentLogo(store=store, title=title, display_order=order, is_active=True)
            logo.image = _uploaded_footer_badge(filename=f"payment-{order}.jpg", text=text, bg_hex=color)
            logo.save(); payment_created += 1
        self._log("FooterTrustBadge", trust_created)
        self._log("FooterPaymentLogo", payment_created)
        return {"trust": FooterTrustBadge.objects.filter(store=store).count(), "payment": FooterPaymentLogo.objects.filter(store=store).count()}


    def _seed_social_links(self, store: Store) -> int:
        """A small deterministic footer-social set for realistic shell QA."""
        entries = [
            (SocialLink.Platform.INSTAGRAM, "اینستاگرام", "https://www.instagram.com/"),
            (SocialLink.Platform.TELEGRAM, "تلگرام", "https://t.me/"),
            (SocialLink.Platform.X, "ایکس", "https://x.com/"),
        ]
        created_count = 0
        for order, (platform, title, url) in enumerate(entries):
            link, created = SocialLink.objects.get_or_create(
                store=store, platform=platform,
                defaults={
                    "title": title, "url": url, "display_order": order,
                    "is_active": True, "show_in_header": False, "show_in_footer": True,
                },
            )
            if not created:
                changed = False
                for field, value in (
                    ("title", title), ("url", url), ("display_order", order),
                    ("is_active", True), ("show_in_header", False), ("show_in_footer", True),
                ):
                    if getattr(link, field) != value:
                        setattr(link, field, value); changed = True
                if changed:
                    link.save()
            created_count += int(created)
        self._log("SocialLink", created_count)
        return SocialLink.objects.filter(store=store, is_active=True, show_in_footer=True).count()

    # ------------------------------------------------------------------ Vendor/Category/Brand

    def _seed_vendor(self, store: Store) -> Vendor:
        vendor, created = Vendor.objects.get_or_create(
            store=store, slug=VENDOR["slug"], defaults={"name": VENDOR["name"], "is_active": True},
        )
        self._log("Vendor", 1 if created else 0)
        return vendor

    def _seed_categories(self, store: Store) -> dict:
        by_slug = {}
        created_count = 0
        for order, top in enumerate(PRIMARY_CATEGORIES):
            parent, created = Category.objects.get_or_create(
                store=store, slug=top["slug"],
                defaults={"name": top["name"], "icon": top["icon"], "order": order, "is_active": True},
            )
            created_count += int(created)
            by_slug[top["slug"]] = parent
            for child_order, child in enumerate(top.get("children", [])):
                child_obj, child_created = Category.objects.get_or_create(
                    store=store, slug=child["slug"],
                    defaults={"name": child["name"], "parent": parent, "order": child_order, "is_active": True},
                )
                created_count += int(child_created)
                by_slug[child["slug"]] = child_obj
        self._log("Category", created_count)
        return by_slug

    def _seed_category_images(self, categories: dict) -> int:
        palette = ["#D9C7B5", "#B8C7D9", "#C9B8D9", "#BFD3C1", "#D8B7B7", "#B9C8C0", "#D4C5A7", "#B7C3D8", "#D8B7CB", "#C5B9A7"]
        created = 0
        for index, data in enumerate(PRIMARY_CATEGORIES):
            category = categories[data["slug"]]
            if category.image:
                continue
            category.image = _uploaded_image(
                filename=f"category-{data['slug']}.jpg", width=640, height=640,
                bg_hex=palette[index % len(palette)], label=data["name"],
            )
            category.save(update_fields=["image", "updated_at"])
            created += 1
        self._log("CategoryImage", created)
        return created

    def _seed_brands(self, store: Store) -> dict:
        by_slug = {}
        created_count = 0
        logo_colors = ["#111827", "#7C3AED", "#BE123C", "#0F766E", "#B45309", "#334155"]
        for index, data in enumerate(BRANDS):
            brand, created = Brand.objects.get_or_create(
                store=store, slug=data["slug"],
                defaults={
                    "name": data["name"], "name_en": data.get("name_en", ""),
                    "description": data.get("description", ""), "country": data.get("country", ""),
                    "sort_order": index, "is_active": True,
                },
            )
            if not brand.logo:
                brand.logo = _uploaded_brand_logo(
                    filename=f"brand-{data['slug']}.jpg", text=data.get("name_en") or data["slug"],
                    bg_hex=logo_colors[index % len(logo_colors)],
                )
                brand.save(update_fields=["logo", "updated_at"])
            created_count += int(created)
            by_slug[data["slug"]] = brand
        self._log("Brand", created_count)
        return by_slug

    # ------------------------------------------------------------------ Products

    def _seed_products(self, store: Store, vendor: Vendor, categories: dict, brands: dict) -> list:
        """دقیقاً ۱۰۰ کالا — ۱۰ به‌ازایِ هر یک از ۱۰ دستهٔ اصلی. توزیعِ
        قیمت/موجودی/وضعیت طبقِ الزامِ صریحِ کار: ~۷۵ موجودیِ نرمال، ~۱۵
        موجودیِ کم، ~۱۰ کاملاً ناموجود؛ اکثریتِ فعال، تعدادِ اندکی پیش‌نویس/
        غیرفعال برایِ تستِ صحیحِ فیلترِ نمایشِ عمومی."""
        products = []
        brand_slugs = list(brands.keys())
        sku_counter = 1
        product_index = 0
        created_count = 0

        for primary in PRIMARY_CATEGORIES:
            child_slugs = [c["slug"] for c in primary.get("children", [])]
            for i in range(10):
                child_slug = child_slugs[i % len(child_slugs)] if child_slugs else primary["slug"]
                category = categories[child_slug]
                pattern = NAME_PATTERNS.get(child_slug, "{name} — کالایِ تستی")
                first_name = FIRST_NAMES[product_index % len(FIRST_NAMES)]
                name = pattern.format(name=first_name)
                slug = f"{child_slug}-{first_name.lower()}-{i}".replace(" ", "-")
                sku = f"RFT-{sku_counter:04d}"
                sku_counter += 1

                # --- توزیعِ قیمت: کم/متوسط/زیاد + برخی تخفیف‌دار ---
                price_bucket = product_index % 3
                base_price = [Decimal("350000"), Decimal("890000"), Decimal("1850000")][price_bucket]
                price = base_price + Decimal(product_index % 5) * Decimal("15000")
                discount_percent = [0, 0, 15, 20, 30][product_index % 5]

                # --- توزیعِ موجودی: ~۷۵ نرمال / ~۱۵ کم / ~۱۰ صفر (از رویِ ۱۰۰) ---
                stock_bucket = product_index % 20
                if stock_bucket < 15:
                    stock = 20 + (product_index % 30)
                elif stock_bucket < 18:
                    stock = 1 + (product_index % 3)
                else:
                    stock = 0

                # --- توزیعِ وضعیت: اکثریتِ فعال، تعدادِ اندکِ Draft/Inactive ---
                if product_index % 33 == 0:
                    status = Product.Status.DRAFT
                elif product_index % 37 == 0:
                    status = Product.Status.INACTIVE
                else:
                    status = Product.Status.ACTIVE

                brand = brands[brand_slugs[product_index % len(brand_slugs)]] if brand_slugs else None

                product, created = Product.objects.get_or_create(
                    store=store, sku=sku,
                    defaults={
                        "vendor": vendor, "category": category, "brand": brand,
                        "name": name, "slug": slug,
                        "description": (
                            f"{name} با پارچهٔ باکیفیت و دوخت تمیز؛ مناسب استفادهٔ روزمره و استایل شهری. "
                            "راهنمای انتخاب سایز و رنگ در صفحهٔ محصول در دسترس است."
                        ),
                        "price": price, "discount_percent": discount_percent, "stock": stock,
                        "status": status, "unit": Product.Unit.PIECE,
                        "rating": Decimal(str(4 + ((product_index % 9) / 10))),
                        "reviews_count": 12 + (product_index * 7) % 180,
                        "sold_count": 18 + (product_index * 13) % 420,
                        "views_count": 120 + (product_index * 29) % 2400,
                        "tag": [Product.Tag.NEW, Product.Tag.HOT, Product.Tag.SALE, ""][product_index % 4],
                        "icon": primary["icon"],
                    },
                )
                created_count += int(created)
                products.append(product)
                product_index += 1

        self._log("Product", created_count)
        return products

    # ------------------------------------------------------------------ Variants

    def _seed_variants(self, products: list) -> dict:
        """توزیعِ واریانت طبقِ الزامِ صریحِ کار: بدونِ‌تنوع/فقط‌سایز/فقط‌رنگ/
        رنگ+سایز — حداقل ۳۰ کالایِ چندتنوعی، حداقل ۱۰ کالا با یک تنوعِ
        ناموجود در کنارِ بقیهٔ تنوع‌هایِ موجود، حداقل ۲۰ کالایِ تصویرمحور
        (که ``set_image_variant`` را واقعاً استفاده می‌کنند).

        ``variant_pattern = index % 5`` روی ۱۰۰ کالا دقیقاً ۲۰ تکرارِ هرکدام
        از ۰ تا ۴ می‌سازد:
          * ۰ و ۴ → بدونِ تنوع (۴۰ کالا)؛
          * ۱ → فقط سایز (۲۰ کالا)؛
          * ۲ → فقط رنگ + تصویرمحور (۲۰ کالا — دقیقاً الزامِ «حداقلِ ۲۰»)؛
          * ۳ → رنگ + سایز (۲۰ کالا).
        جمعِ کالاهایِ چندتنوعی = ۶۰ (پترنِ ۱/۲/۳)، بیشتر از الزامِ «حداقل ۳۰».
        """
        total = 0
        products_with_variants = 0
        image_mapped = 0
        zero_stock_alongside_available = 0

        for index, product in enumerate(products):
            variant_pattern = index % 5
            created_any = False

            if variant_pattern in (0, 4):
                # بدونِ تنوع — عمداً دست‌نخورده می‌ماند.
                continue

            # Idempotency: اگر این کالا از اجرایِ قبلی از قبل تنوع دارد، دوباره
            # ساخته نمی‌شود (create_variant رویِ مقدارِ فعالِ تکراری خطا
            # می‌دهد) — فقط در شمارشِ خلاصهٔ پایانی لحاظ می‌شود.
            existing_variants = list(product.variants.all())
            if existing_variants:
                total += len(existing_variants)
                mapped_here = product.images.filter(variant__isnull=False).count()
                image_mapped += mapped_here
                if any(v.stock == 0 for v in existing_variants) and any(v.stock > 0 for v in existing_variants):
                    zero_stock_alongside_available += 1
                products_with_variants += 1
                continue

            # هر دومینِ کالایِ چندتنوعی (index % 2 == 0)، تنوعِ اولش را عمداً
            # ناموجود می‌کند تا بقیهٔ تنوع‌ها همچنان موجود بمانند — این یکی
            # از راه‌هایِ رسیدن به الزامِ «حداقل ۱۰ کالا با یک تنوعِ ناموجود
            # در کنارِ بقیهٔ تنوع‌هایِ موجود» است (پترنِ ۱/۲/۳ جمعاً ۶۰ کالا،
            # نیمی از آن‌ها = ۳۰ کالا، خیلی بیشتر از حداقلِ ۱۰).
            first_variant_out_of_stock = index % 2 == 0

            if variant_pattern in (1, 3):
                # فقط سایز (یا سایز به‌همراهِ رنگِ زیر برایِ pattern==3).
                for size_index, size in enumerate(SIZES):
                    if first_variant_out_of_stock and size_index == 0:
                        size_stock = 0
                    else:
                        size_stock = 5 + size_index
                    create_variant(
                        product, attribute="سایز", value=size, stock=size_stock,
                        is_active=True,
                    )
                    total += 1
                created_any = True

            if variant_pattern in (2, 3):
                # فقط رنگ (یا رنگ اضافه‌شده به سایزِ بالا برایِ pattern==3 → رنگ+سایز).
                colors_for_product = COLORS[index % len(COLORS):] + COLORS[: index % len(COLORS)]
                colors_for_product = colors_for_product[:3] or COLORS[:3]
                # فقط pattern==2 (دقیقاً ۲۰ کالا از ۱۰۰) تصویرِ اختصاصیِ رنگ
                # می‌گیرد — الزامِ «حداقل ۲۰ کالایِ تصویرمحور» را دقیقاً برآورده می‌کند.
                should_map_image = variant_pattern == 2
                for color_index, (color_name, color_hex) in enumerate(colors_for_product):
                    if first_variant_out_of_stock and color_index == 0 and variant_pattern == 2:
                        # برایِ pattern==3، ناموجودسازیِ اولین‌تنوع از طریقِ سایز
                        # (بالا) کافی است — این‌جا فقط برایِ pattern==2 (که سایز
                        # ندارد) دوباره اعمال می‌شود تا آن گروه هم پوشش داده شود.
                        color_stock = 0
                    else:
                        color_stock = 4 + color_index * 2
                    variant = create_variant(
                        product, attribute="رنگ", value=color_name, value_hex=color_hex,
                        stock=color_stock, is_active=True,
                    )
                    total += 1
                    if should_map_image:
                        image = add_product_image(
                            product,
                            _uploaded_image(
                                filename=f"{product.slug}-{color_name}.jpg",
                                width=600, height=750, bg_hex=color_hex, label=f"{product.name} — {color_name}",
                            ),
                            alt=f"{product.name} — رنگ {color_name}",
                        )
                        set_image_variant(image, variant)
                        image_mapped += 1
                created_any = True

            if created_any:
                products_with_variants += 1
                if first_variant_out_of_stock:
                    zero_stock_alongside_available += 1
                product.product_type = Product.ProductType.VARIABLE
                product.save(update_fields=["product_type"])

        return {
            "total": total, "products_with_variants": products_with_variants,
            "image_mapped": image_mapped, "zero_stock_alongside_available": zero_stock_alongside_available,
        }

    # ------------------------------------------------------------------ Images

    def _seed_product_images(self, products: list) -> int:
        """حداقل ۲ تصویرِ عمومی به‌ازایِ هر کالایِ «معمولی» (بدونِ عکسِ
        تنوع‌محورِ قبلاً ساخته‌شده در ``_seed_variants``) — پالتِ رنگی طبقِ
        دستهٔ کالا، idempotent (کالایِ دارایِ تصویر رد می‌شود)."""
        created_count = 0
        category_palette = {}
        for i, primary in enumerate(PRIMARY_CATEGORIES):
            hue_hexes = ["#EDE9FE", "#FEF3C7", "#DCFCE7", "#FEE2E2", "#E0F2FE", "#FDE68A", "#F1F5F9", "#FCE7F3", "#E2E8F0", "#FFF7ED"]
            category_palette[primary["slug"]] = hue_hexes[i % len(hue_hexes)]

        for product in products:
            if product.images.exists():
                continue
            top_slug = product.category.parent.slug if product.category and product.category.parent else (
                product.category.slug if product.category else "misc"
            )
            bg = category_palette.get(top_slug, "#EDE9FE")
            for shot in range(2):
                add_product_image(
                    product,
                    _uploaded_image(
                        filename=f"{product.slug}-{shot}.jpg", width=600, height=750,
                        bg_hex=bg, label=product.name,
                    ),
                    alt=product.name,
                )
            created_count += 2
        return created_count

    # ------------------------------------------------------------------ Collections

    def _seed_collections(self, store: Store, products: list) -> list:
        collections = []
        visible_products = [p for p in products if p.status == Product.Status.ACTIVE]
        chunk_size = max(len(visible_products) // len(COLLECTIONS), 5) if visible_products else 0

        for c_index, data in enumerate(COLLECTIONS):
            collection, created = MerchantCollection.objects.get_or_create(
                store=store, slug=data["slug"], defaults={"name": data["name"], "is_active": True},
            )
            collections.append(collection)
            if not created:
                continue
            start = c_index * chunk_size
            end = start + min(chunk_size, 12)
            members = visible_products[start:end] or visible_products[:8]
            MerchantCollectionItem.objects.bulk_create([
                MerchantCollectionItem(collection=collection, product=product, order=order)
                for order, product in enumerate(members)
            ])
        self._log("MerchantCollection", MerchantCollection.objects.filter(store=store).count())
        return collections

    # ------------------------------------------------------------------ Hero / Banners / Story rail

    def _seed_hero_slides(self, store: Store) -> int:
        titles = [
            ("کالکشن تابستانی راستی سی", "جدیدترین‌های فصل را ببینید"),
            ("استایل روزمره", "لباس‌هایی برای هر روز شما"),
            ("تازه‌های این هفته", "محصولات تازه رسیده"),
            ("پیشنهادهای ویژه", "تخفیف‌های محدود، همین امروز"),
        ]
        created_count = 0
        colors = ["#111827", "#7C2D12", "#0F172A", "#78350F"]
        for order, (title, subtitle) in enumerate(titles):
            slide = HeroSlide.objects.filter(store=store, title=title).first()
            if slide is not None:
                slide.subtitle = subtitle
                slide.display_order = order
                slide.is_active = True
                slide.show_button = True
                slide.button_label = "خرید"
                slide.destination_type = DestinationType.SEARCH
                slide.save(update_fields=["subtitle", "display_order", "is_active", "show_button", "button_label", "destination_type", "updated_at"])
                continue
            slide = HeroSlide(
                store=store, title=title, subtitle=subtitle, display_order=order, is_active=True,
                show_button=True, button_label="خرید", destination_type=DestinationType.SEARCH,
            )
            slide.desktop_image = _uploaded_image(
                filename=f"hero-{order}.jpg", width=1600, height=700, bg_hex=colors[order % len(colors)], label=title,
            )
            slide.save()
            created_count += 1
        self._log("HeroSlide", created_count)
        return created_count

    def _seed_banners(self, store: Store) -> int:
        # Enough distinct Store-owned assets for the repeated Universal banner
        # blocks in the Golden composition.  The renderer selects slices via
        # offset/item_limit; no banner ID is ever hard-coded into the preset.
        titles = [
            "پرفروش‌های تابستان", "جدیدترین کلکسیون", "تخفیف ویژهٔ اعضا", "ارسال رایگان بالای ۵۰۰ هزار تومان",
            "انتخاب رسمی این هفته", "استایل روزمره", "پیشنهاد اعضای باشگاه", "ارسال رایگان امروز",
            "راهنمای انتخاب استایل", "کالکشن شهری", "پیشنهاد فصل", "منتخب راستی استایل",
            "راستی استایل کنار شما",
        ]
        created_count = 0
        colors = ["#334155", "#7C3AED", "#B45309", "#0E7490", "#9F1239", "#0F766E", "#4338CA", "#C2410C", "#475569", "#6D28D9", "#0369A1", "#A16207", "#0F766E"]
        for order, title in enumerate(titles):
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
                    banner.save(update_fields=["display_order", "is_active", "show_button", "destination_type", "updated_at"])
                continue
            banner = PromotionalBanner(
                store=store, title=title, display_order=order, is_active=True,
                show_button=False, destination_type=DestinationType.SEARCH,
            )
            banner.desktop_image = _uploaded_image(
                filename=f"banner-{order}.jpg", width=1200, height=500, bg_hex=colors[order % len(colors)], label=title,
            )
            banner.save()
            created_count += 1
        self._log("PromotionalBanner", created_count)
        return created_count

    def _seed_story_rail(self, store: Store, categories: dict, products: list, collections: list) -> int:
        """۱۰ آیتمِ استوری با ترکیبی از مقصدِ دسته‌بندی/محصول/کالکشن."""
        primary_categories = [categories[p["slug"]] for p in PRIMARY_CATEGORIES]
        visible_products = [p for p in products if p.status == Product.Status.ACTIVE][:4]
        created_count = 0
        colors = ["#DB2777", "#0891B2", "#CA8A04", "#16A34A", "#4F46E5", "#EA580C", "#0F766E", "#9333EA", "#DC2626", "#334155"]

        story_targets = []
        for category in primary_categories[:5]:
            story_targets.append(("category", category))
        for product in visible_products:
            story_targets.append(("product", product))
        for collection in collections[:1]:
            story_targets.append(("collection", collection))
        while len(story_targets) < 10 and primary_categories:
            story_targets.append(("category", primary_categories[len(story_targets) % len(primary_categories)]))
        story_targets = story_targets[:10]

        for order, (kind, target) in enumerate(story_targets):
            title = getattr(target, "name", "")[:20] or f"استوری {order + 1}"
            if StoryRailItem.objects.filter(store=store, title=title, display_order=order).exists():
                continue
            item = StoryRailItem(store=store, title=title, display_order=order, is_active=True)
            if kind == "category":
                item.destination_type = DestinationType.CATEGORY
                item.destination_category = target
            elif kind == "product":
                item.destination_type = DestinationType.PRODUCT
                item.destination_product = target
            else:
                item.destination_type = DestinationType.COLLECTION
                item.destination_collection = target
            item.image = _uploaded_image(
                filename=f"story-{order}.jpg", width=400, height=400, bg_hex=colors[order % len(colors)], label=title,
            )
            item.save()
            created_count += 1
        self._log("StoryRailItem", created_count)
        return created_count

    # ------------------------------------------------------------------ Navigation

    def _seed_navigation(self, store: Store, categories: dict, collections: list) -> int:
        menu, _ = Menu.objects.get_or_create(
            store=store, location=Menu.Location.HEADER, defaults={"title": "منوی اصلی", "is_active": True},
        )
        created_count = 0
        order = 0
        for primary in PRIMARY_CATEGORIES:
            category = categories[primary["slug"]]
            item, created = MenuItem.objects.get_or_create(
                menu=menu, title=primary["name"], parent=None,
                defaults={
                    "display_order": order, "is_active": True,
                    "destination_type": DestinationType.CATEGORY, "destination_category": category,
                },
            )
            created_count += int(created)
            order += 1

        collection_by_slug = {c.slug: c for c in collections}
        extra_links = [
            ("محصولات جدید", collection_by_slug.get("new-arrivals-rastisi")),
            ("پرفروش‌ها", collection_by_slug.get("bestsellers-rastisi")),
            ("تخفیف‌ها", collection_by_slug.get("special-discount-rastisi")),
        ]
        for title, collection in extra_links:
            if collection is None:
                continue
            item, created = MenuItem.objects.get_or_create(
                menu=menu, title=title, parent=None,
                defaults={
                    "display_order": order, "is_active": True,
                    "destination_type": DestinationType.COLLECTION, "destination_collection": collection,
                },
            )
            created_count += int(created)
            order += 1

        self._log("MenuItem", created_count)
        return created_count

    def _seed_footer_menus(self, store: Store, categories: dict, collections: list) -> int:
        """Seed the one reusable quick-link column consumed by the public footer.

        Category links are rendered from ``top_level_categories`` by the shared
        footer shell, so they stay automatically in sync with the Store catalog
        and do not need a second, duplicated menu dataset.
        """
        collection_by_slug = {c.slug: c for c in collections}
        entries = [
            ("جستجوی محصولات", DestinationType.SEARCH, None),
            ("سبد خرید", DestinationType.CART, None),
            ("تازه رسیده‌ها", DestinationType.COLLECTION, collection_by_slug.get("new-arrivals-rastisi")),
            ("تخفیف‌ها", DestinationType.COLLECTION, collection_by_slug.get("special-discount-rastisi")),
        ]
        menu, _ = Menu.objects.get_or_create(
            store=store, location=Menu.Location.FOOTER_1,
            defaults={"title": "راهنمای خرید", "is_active": True},
        )
        if menu.title != "راهنمای خرید" or not menu.is_active:
            menu.title = "راهنمای خرید"
            menu.is_active = True
            menu.save(update_fields=["title", "is_active", "updated_at"])

        created_count = 0
        for order, (item_title, destination_type, target) in enumerate(entries):
            if destination_type == DestinationType.COLLECTION and target is None:
                continue
            defaults = {
                "display_order": order, "is_active": True,
                "destination_type": destination_type,
            }
            if destination_type == DestinationType.COLLECTION:
                defaults["destination_collection"] = target
            item, created = MenuItem.objects.get_or_create(
                menu=menu, title=item_title, parent=None, defaults=defaults,
            )
            if not created:
                changed = False
                if item.display_order != order:
                    item.display_order = order; changed = True
                if not item.is_active:
                    item.is_active = True; changed = True
                if item.destination_type != destination_type:
                    item.destination_type = destination_type; changed = True
                if destination_type == DestinationType.COLLECTION and item.destination_collection_id != target.pk:
                    item.destination_collection = target; changed = True
                if changed:
                    item.save()
            created_count += int(created)
        self._log("FooterMenuItem", created_count)
        return created_count

    # ------------------------------------------------------------------ Content pages

    def _seed_content_pages(self, store: Store) -> int:
        created_count = 0
        now = timezone.now()
        for data in CONTENT_PAGES:
            page, created = ContentPage.objects.get_or_create(
                store=store, slug=data["slug"],
                defaults={
                    "title": data["title"], "body": data["body"],
                    "status": ContentPage.Status.PUBLISHED, "published_at": now,
                    "show_in_footer": True, "footer_column": data["footer_column"],
                },
            )
            created_count += int(created)
        self._log("ContentPage", created_count)
        return created_count

    # ------------------------------------------------------------------ Fashion blog (Store-scoped demo records)

    def _seed_blog_posts(self, store: Store) -> int:
        posts = [
            ("راهنمای ساخت کمد کپسولی برای هر فصل", "راهنمای استایل", "چطور با چند تکهٔ کاربردی، استایل‌های متنوع و هماهنگ بسازیم."),
            ("۵ ترکیب رنگی ساده برای استایل روزمره", "مد و رنگ", "ترکیب‌های مطمئن و قابل استفاده برای محیط کار، دانشگاه و آخر هفته."),
            ("راهنمای انتخاب سایز شلوار جین", "راهنمای خرید", "نکات اندازه‌گیری دور کمر، قد و فیت مناسب قبل از خرید اینترنتی."),
            ("چطور از لباس‌های نخی بهتر مراقبت کنیم؟", "مراقبت از لباس", "شست‌وشو، خشک‌کردن و نگهداری صحیح برای حفظ فرم و رنگ لباس."),
        ]
        colors = ["#E7DDD2", "#D9E5E2", "#E4DCE8", "#DEE4EC"]
        created = 0
        now = timezone.now()
        for index, (title, category, excerpt) in enumerate(posts):
            slug = f"rastisi-fashion-guide-{index+1}"
            if BlogPost.objects.filter(slug=slug).exists():
                continue
            post = BlogPost(
                store=store, title=title, slug=slug, category_label=category, excerpt=excerpt,
                body=excerpt + " این مطلب برای فروشگاه نمایشی راستی استایل تهیه شده است.",
                tint=colors[index], published_at=now - timedelta(days=index * 4),
            )
            post.cover_image = _uploaded_image(
                filename=f"blog-fashion-{index+1}.jpg", width=900, height=620,
                bg_hex=colors[index], label=title,
            )
            post.save(); created += 1
        self._log("BlogPost", created)
        return created

    # ------------------------------------------------------------------ Builder lifecycle

    def _seed_builder(self, store: Store, owner, preset) -> None:
        """چیدمانِ Builder را دقیقاً از طریقِ همان سرویس‌هایِ Production
        می‌سازد — هرگز StorefrontSection/StorefrontLayoutVersion را دستی
        نمی‌سازد.

        Idempotent و rate-limit-آگاه (تصمیمِ صریحِ این اصلاح): ``publish``
        و ``get_or_create_draft`` هرکدام پشتِ یک Rate Limitِ واقعیِ
        Production‌اند (به‌ترتیب ۲۰/۳۰ فراخوانی در هر ساعت، به‌ازایِ هر
        Store — ``apps.core.services.rate_limit``، تعریف‌شده در
        ``layout_service.py``). این محدودیت‌ها برایِ محافظت از سوءاستفادهٔ
        واقعی‌اند و اینجا هرگز دور زده/غیرفعال/بالا برده نمی‌شوند.

        به‌جایِ آن، این متد ابتدا وضعیتِ *فعلیِ* ``StorefrontLayout`` را
        می‌خواند (بدونِ فراخوانیِ هیچ سرویسِ Rate-Limitedی):
          * اگر از قبل یک نسخه‌ی منتشرشده وجود دارد که Presetِ آن دقیقاً
            برابرِ ``preset`` است و هیچ Draftِ باقی‌مانده‌ای ندارد — یعنی
            اجرایِ قبلیِ همینِ دستور دقیقاً همین حالت را ساخته — هیچ چیزی
            دوباره فراخوانی نمی‌شود (نه Draft جدید، نه publish جدید).
          * در غیرِ این صورت (اولین اجرا، یا Presetِ متفاوت، یا Draftِ
            نصفه‌کارهٔ باقی‌مانده)، دقیقاً همان مسیرِ Production طی می‌شود:
            ``get_or_create_draft`` → ``preset_service.apply_preset`` →
            ``publish``.
        این یعنی یک اجرایِ دومِ کاملاً یکسانِ همینِ دستور، هیچ عملیاتِ
        rate-limited اضافه‌ای مصرف نمی‌کند — دقیقاً همان الزامِ صریحِ کار."""
        layout = layout_service.get_or_create_layout(store)
        if layout.published_version_id and not layout.draft_version_id:
            current_config = layout.published_version.effective_appearance_config()
            if current_config.get("layout_preset_key") == preset.key:
                self._log(
                    "StorefrontLayoutVersion", 0,
                    note=(
                        f"از قبل با Preset «{preset.key}» منتشر شده — بدونِ فراخوانیِ "
                        "دوبارهٔ publish/new_draft (idempotent)"
                    ),
                )
                return

        draft = layout_service.get_or_create_draft(store, user=owner)
        preset_service.apply_preset(draft, preset)
        layout_service.publish(store, user=owner)
        self._log("StorefrontLayoutVersion", 0, note=f"Draft ساخته و با Preset «{preset.key}» منتشر شد")

    # ------------------------------------------------------------------ Logging

    def _log(self, label, created_count, note=""):
        if note:
            self.stdout.write(f"  {label}: {note}")
        else:
            self.stdout.write(f"  {label}: {created_count} رکورد جدید ساخته شد")
