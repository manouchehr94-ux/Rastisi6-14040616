"""FOLLOWUP-13 — مرجعِ واحدِ «مشخصاتِ تصویر» برایِ هر جایگاهِ آپلود.

هر جایگاه از *رندرِ واقعی* (انتخابگرِ CSS در ``renderer``) و از *ثابت‌هایِ اعتبارسنجیِ واقعیِ کد* استخراج شده است، نه یک عددِ فرضی. فیلدِ
``max_enforced`` مشخص می‌کند حدِ حجم واقعاً در سرور اعمال می‌شود یا فقط توصیه است. این ماژول فقط توضیح می‌دهد (و هشدارِ سمتِ مرورگر را
تغذیه می‌کند)؛ هیچ فایلی را تغییر یا بازنویسی نمی‌کند."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict

from apps.catalog.services.product_image_service import MAX_UPLOAD_SIZE_BYTES as PRODUCT_MAX_BYTES
from apps.content.models import HOMEPAGE_MEDIA_MAX_UPLOAD_BYTES
from apps.dashboard.forms import MAX_FAVICON_SIZE, MAX_LOGO_SIZE

MB = 1024 * 1024
FORMATS_RASTER = ("JPG", "PNG", "WebP")


@dataclass(frozen=True)
class ImageSpec:
    key: str
    label: str            # نامِ فارسیِ جایگاه
    usage: str            # کاربرد
    ratio: str            # نسبتِ پیشنهادی «عرض:ارتفاع»
    recommended: tuple    # (w, h) px
    minimum: tuple        # (w, h) px — زیرِ آن کیفیتِ تصویر افت می‌کند
    formats: tuple = FORMATS_RASTER
    max_bytes: int = 5 * MB
    max_enforced: bool = False      # آیا سرور همین حد را رد می‌کند؟
    max_pixels: int = 50_000_000    # سقفِ مگاپیکسلِ اعمال‌شده در سرور (apps.core.image_validation.MAX_PIXELS)
    transparent: bool = False       # شفافیت (PNG/WebP) توصیه می‌شود
    safe_area: str = "سوژهٔ اصلی را در ۸۰٪ مرکزِ تصویر نگه دارید."
    crop: str = "تصویر با حالتِ «پوشاندنِ کادر» نمایش داده می‌شود؛ اگر نسبت متفاوت باشد، لبه‌ها بریده می‌شوند."
    alt_hint: str = "متنِ جایگزین کوتاه و توصیفی بنویسید (مثلاً نامِ کالا)؛ برایِ تزیینی بودنِ تصویر خالی بگذارید."
    renderer: str = ""              # شاهد: انتخابگر/فایلِ رندرِ واقعی
    extra: str = ""
    form_names: tuple = field(default_factory=tuple)

    @property
    def max_mb(self) -> float:
        return round(self.max_bytes / MB, 2)

    def as_dict(self) -> dict:
        data = asdict(self)
        data["max_mb"] = self.max_mb
        return data


SPECS: dict[str, ImageSpec] = {s.key: s for s in (
    ImageSpec(
        "product_image", "تصویر کالا (کارت، فهرست و صفحهٔ کالا)",
        "تصویر اصلی و گالریِ کالا؛ همان تصویر در کارتِ کالا، نتایجِ جست‌وجو و صفحهٔ کالا استفاده می‌شود.",
        "1:1", (1200, 1200), (600, 600), max_bytes=PRODUCT_MAX_BYTES, max_enforced=True,
        crop="کارتِ کالا ۱:۱ است (در برخی سبک‌ها ۳:۴ یا ۴:۳ و در طرحِ «مد» صفحهٔ کالا ۳:۴). با پس‌زمینهٔ یکدست و کالا در مرکز، در همهٔ سبک‌ها درست دیده می‌شود.",
        alt_hint="نامِ کالا و ویژگیِ بارزِ آن (رنگ/مدل) را بنویسید.",
        renderer=".pcard .img{aspect-ratio:1/1} · .gallery .main{aspect-ratio:1/1}",
        extra="سرور برای نمایش، نسخه‌ای حداکثر ۲۰۰۰px و بندانگشتیِ ۴۰۰px می‌سازد؛ فایلِ اصلیِ شما بدونِ تغییر هم نگه داشته می‌شود. فایلِ بزرگ‌تر از ۲۰۰۰px برای نمایش بی‌فایده است.",
        form_names=("images",),
    ),
    ImageSpec(
        "category_image", "تصویر دسته‌بندی",
        "کاشیِ دسته‌بندی در صفحهٔ اصلی و منوها.", "1:1", (800, 800), (400, 400),
        crop="کاشی‌ها معمولاً ۱:۱ و گاهی دایره‌ای‌اند؛ سوژه را در مرکز نگه دارید.",
        alt_hint="نامِ دسته‌بندی.", renderer=".category-pastel-media / .category-grey-media / .category-fashion-media{aspect-ratio:1/1}",
        max_enforced=True,
        form_names=("image",),
    ),
    ImageSpec(
        "collection_image", "تصویر کالکشن",
        "کارتِ کالکشن در صفحهٔ اصلی و صفحهٔ کالکشن.", "4:3", (1200, 900), (600, 450),
        alt_hint="نامِ کالکشن.", renderer=".tiles-carousel .tile{flex:0 0 240px;min-height:180px}",
        max_enforced=True,
        form_names=("image",),
    ),
    ImageSpec(
        "brand_logo", "لوگوی برند",
        "نمایشِ برند در کاروسلِ برندها؛ حداکثر ارتفاعِ نمایش ۴۸px و با حالتِ «جاگیری کامل» (بدونِ برش).", "2:1", (800, 400), (200, 100),
        formats=("PNG", "WebP", "JPG"), transparent=True,
        safe_area="لوگو را با حاشیهٔ کوچک و پس‌زمینهٔ شفاف (PNG/WebP) بدهید؛ نسخهٔ افقی بهتر از مربعی دیده می‌شود.",
        crop="لوگو بریده نمی‌شود (contain)؛ فقط کوچک می‌شود. نسبت‌هایِ خیلی بلند/باریک ریز دیده می‌شوند.",
        alt_hint="نامِ برند.", renderer=".brand-tile img{max-height:48px;max-width:100%;object-fit:contain}",
        extra="فایلِ SVG پذیرفته نمی‌شود (برایِ امنیت)؛ از PNG یا WebP شفاف استفاده کنید.", max_enforced=True,
        form_names=("logo",),
    ),
    ImageSpec(
        "journal_cover", "کاورِ مقالهٔ مجله",
        "کارتِ مقاله در فهرستِ مجله و (در صورتِ وجود) بالایِ صفحهٔ مقاله.", "4:3", (1600, 1200), (800, 600),
        max_bytes=HOMEPAGE_MEDIA_MAX_UPLOAD_BYTES, max_enforced=True,
        crop="کارتِ مجله ۴:۳ است و تصویر بریده می‌شود؛ در صفحهٔ مقاله تصویر با نسبتِ اصلیِ خودش (تا عرضِ ۸۲۰px) دیده می‌شود.",
        alt_hint="موضوعِ مقاله را توصیف کنید.", renderer=".journal-cover{aspect-ratio:4/3} · .journal-article-cover img{height:auto}",
        form_names=("cover_image",),
    ),
    ImageSpec(
        "story_item", "آیتم استوری",
        "دایرهٔ استوری در نوار بالای صفحهٔ اصلی.", "1:1", (600, 600), (200, 200),
        max_bytes=HOMEPAGE_MEDIA_MAX_UPLOAD_BYTES, max_enforced=True,
        safe_area="تصویر به‌شکل دایره (۶۸ پیکسل) بریده می‌شود؛ چهره یا سوژه را دقیقاً در مرکز و درشت بگذارید.",
        crop="کادر دایره‌ای ثابت است و تصویر آن را می‌پوشاند؛ گوشه‌های تصویر دیده نمی‌شود.",
        alt_hint="عنوانِ استوری.", renderer=".story-avatar{width:68px;height:68px;border-radius:50%} img{object-fit:cover}",
        form_names=("image",),
    ),
    ImageSpec(
        "hero_desktop", "اسلایدِ اصلی — دسکتاپ",
        "تصویرِ بزرگِ بالایِ صفحهٔ اصلی در رایانه و تبلت.", "5:2", (1920, 766), (1200, 480),
        max_bytes=HOMEPAGE_MEDIA_MAX_UPLOAD_BYTES, max_enforced=True,
        safe_area="متن و دکمه روی تصویر می‌نشینند؛ ناحیهٔ ۳۰٪ کنارِ متن را خلوت بگذارید و اطلاعاتِ مهم را در ۸۰٪ مرکزی بیاورید.",
        crop="نسبتِ دسکتاپ ≈ ۱۰۵۳:۴۲۰ و در تبلت ۱۶:۷ است؛ لبه‌هایِ بالا/پایین ممکن است ببرند.",
        alt_hint="عنوانِ کمپین/اسلاید.", renderer=".hero-inner{aspect-ratio:1053/420} @media≤1000px{16/7}",
        form_names=("desktop_image",),
    ),
    ImageSpec(
        "hero_mobile", "اسلایدِ اصلی — موبایل",
        "نسخهٔ مستقلِ موبایل (اگر نگذارید همان تصویرِ دسکتاپ بریده نمایش داده می‌شود).", "5:6", (750, 900), (600, 720),
        max_bytes=HOMEPAGE_MEDIA_MAX_UPLOAD_BYTES, max_enforced=True,
        safe_area="در موبایل کادر حداقل ۳۰۰px ارتفاع دارد و متن روی تصویر است؛ سوژه را بالا/مرکز و ناحیهٔ پایینِ تصویر را برایِ متن خلوت بگذارید.",
        crop="ارتفاعِ کادر بر اساسِ محتوا تعیین می‌شود (حداقل ۳۰۰px)؛ تصویر پوشاننده است.",
        renderer=".hero-inner{aspect-ratio:auto;min-height:300px} @media≤560px", form_names=("mobile_image",),
    ),
    ImageSpec(
        "banner_desktop", "بنرِ تبلیغاتی — دسکتاپ",
        "بنرهایِ تکی/چندتاییِ صفحهٔ اصلی.", "4:3", (1200, 900), (600, 450),
        max_bytes=HOMEPAGE_MEDIA_MAX_UPLOAD_BYTES, max_enforced=True,
        crop="ارتفاعِ کارت بسته به چیدمانِ بنر (۱۱۸ تا ۲۶۰px) فرق می‌کند و تصویر پوشاننده است؛ برایِ بنرِ پهن (تکی) تصویرِ افقی‌تر (مثلاً ۳:۱) بدهید.",
        renderer=".promo-card{min-height:260px} · .promo-grid--wide-single{185px} · .promo-grid--mini-4{118px}", form_names=("desktop_image",),
    ),
    ImageSpec(
        "banner_mobile", "بنرِ تبلیغاتی — موبایل", "نسخهٔ موبایلِ بنر.", "1:1", (800, 800), (400, 400),
        max_bytes=HOMEPAGE_MEDIA_MAX_UPLOAD_BYTES, max_enforced=True, renderer=".promo-card (mobile)", form_names=("mobile_image",),
    ),
    ImageSpec(
        "shop_logo", "لوگوی فروشگاه",
        "هدر، فوتر و برخی صفحه‌ها؛ نسخهٔ افقی یا مربعی.", "3:1", (600, 200), (200, 60),
        formats=("PNG", "WebP", "JPG"), max_bytes=MAX_LOGO_SIZE, max_enforced=True, transparent=True,
        safe_area="لوگو را با حاشیهٔ کم و پس‌زمینهٔ شفاف بدهید؛ در هدر ارتفاعِ کوچکی دارد.",
        crop="لوگو بریده نمی‌شود؛ متناسب کوچک می‌شود.", alt_hint="نامِ فروشگاه.", renderer="header/footer logo (contain)",
        form_names=("logo",),
    ),
    ImageSpec(
        "favicon", "فاوآیکون",
        "آیکونِ برگهٔ مرورگر.", "1:1", (512, 512), (64, 64), formats=("PNG", "ICO"), max_bytes=MAX_FAVICON_SIZE, max_enforced=True,
        transparent=True, safe_area="طرح ساده و درشت؛ در ۱۶px هم باید خوانا بماند.", crop="مربع؛ بریده نمی‌شود.", renderer="<link rel=icon>",
        form_names=("favicon",),
    ),
    ImageSpec(
        "footer_badge", "نشان اعتماد / لوگوی پرداختِ فوتر",
        "فقط نشانِ رسمی و واقعی (اینماد و …) یا لوگوی درگاهِ واقعاً فعال.", "1:1", (256, 256), (96, 96),
        max_bytes=HOMEPAGE_MEDIA_MAX_UPLOAD_BYTES, max_enforced=True, transparent=True,
        safe_area="تصویرِ رسمی را بدونِ دستکاری و برش بارگذاری کنید.", crop="جاگیری کامل در کادرِ مربعی.",
        renderer="footer badge/payment slots", extra="نشانِ جعلی یا بدونِ مجوز نگذارید؛ سامانه هیچ نشانی را خودکار نمی‌سازد.",
        form_names=("image",),
    ),
    ImageSpec(
        "gift_wrap_image", "تصویرِ نمونهٔ کادوپیچی", "نمایش در سبد/تسویه.", "1:1", (600, 600), (300, 300),
        renderer="تصویرِ کوچکِ نمونه کنارِ گزینهٔ کادوپیچی در سبد/تسویه (object-fit:cover)", max_enforced=True,
        form_names=("gift_wrap_image",),
    ),
    ImageSpec(
        "swatch_image", "تصویرِ نمونهٔ رنگ/ویژگی", "دایرهٔ کوچکِ انتخابِ رنگ در صفحهٔ کالا (۳۴px).", "1:1", (200, 200), (64, 64),
        crop="به‌شکلِ دایره بریده می‌شود؛ بافت/رنگ را کاملاً پرِ کادر کنید.", renderer=".swatch{width:34px;height:34px;border-radius:50%}",
        max_enforced=True,
        form_names=("swatch_image",),
    ),
)}


def get_spec(key: str) -> ImageSpec:
    return SPECS[key]


def render_media_spec_markdown() -> str:
    """ماتریسِ «راهنمای تصاویر برایِ فروشنده» — از همین جدول تولید می‌شود تا هرگز با فرمِ آپلود اختلاف پیدا نکند."""
    from apps.core.utils import to_fa_digits as fa

    lines = [
        "# راهنمای تصاویر برای فروشنده (MEDIA_SPEC_FA)", "",
        "این جدول از همان تنظیماتی تولید شده که راهنمای کنار فرم‌های آپلود را می‌سازد؛ نسبت‌ها از رندرِ واقعیِ قالب‌ها و حدِ حجم‌ها از ثابت‌های اعتبارسنجیِ واقعیِ کد استخراج شده‌اند.",
        "«اعمال می‌شود» یعنی سرور فایلِ بزرگ‌تر را رد می‌کند؛ «توصیه» یعنی فقط برایِ سرعتِ سایت پیشنهاد می‌شود.", "",
        "| جایگاه | نسبت | ابعادِ پیشنهادی | حداقل | فرمت | حجم | شاهدِ رندر |", "|---|---|---|---|---|---|---|",
    ]
    for spec in SPECS.values():
        size = f"{fa(format(spec.max_mb, 'g'))} مگابایت ({'اعمال می‌شود' if spec.max_enforced else 'توصیه'})"
        lines.append(
            f"| {spec.label} | {fa(spec.ratio)} | {fa(spec.recommended[0])}×{fa(spec.recommended[1])} | {fa(spec.minimum[0])}×{fa(spec.minimum[1])} "
            f"| {'، '.join(spec.formats)} | {size} | `{spec.renderer}` |"
        )
    lines += ["", "## نکته‌هایِ هر جایگاه", ""]
    for spec in SPECS.values():
        lines += [f"### {spec.label}", f"- **کاربرد:** {spec.usage}", f"- **ناحیهٔ امن:** {spec.safe_area}", f"- **برش:** {spec.crop}", f"- **متنِ جایگزین (alt):** {spec.alt_hint}"]
        if spec.extra:
            lines.append(f"- **نکته:** {spec.extra}")
        lines.append("")
    lines += [
        "## رفتارِ فعلیِ سامانه",
        "- تصویرِ اصلیِ فروشنده هرگز بازنویسی/حذف نمی‌شود؛ جایگزینی فقط با آپلودِ تازه است.",
        "- کالا: سرور تصویر را تا ۲۰۰۰px کوچک می‌کند و بندانگشتی ۴۰۰px می‌سازد (بزرگ‌نمایی انجام نمی‌شود)؛ فایلِ اصلیِ شما بدونِ تغییر در products/originals نگه داشته می‌شود.",
        "- فایلِ غیرتصویری، خراب، SVG و HTML/JS پنهان‌شده در پسوندِ تصویر رد می‌شود (بازکردن و verify با Pillow).",
        "- هنگامِ انتخابِ فایل، مرورگر فرمتِ واقعی، حجم، ابعاد و نسبت را می‌سنجد و پیش‌نمایشِ «نمایش کامل» و «پر کردن قاب» را بر پایهٔ قابِ واقعیِ قالبِ شما نشان می‌دهد؛ سرور همان حد و فرمت‌ها را دوباره بررسی می‌کند.",
        "- دسته‌بندی در پنل (ایجاد و ویرایش دسته) تصویر مستقل دارد و با همین حد و فرمت بررسی می‌شود.", "",
    ]
    return "\n".join(lines)
