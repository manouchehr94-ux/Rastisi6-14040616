"""Phase 1B — تفکیکِ متمرکزِ «کدام صفحه‌یِ منتشرشده باید برایِ این Store و
این نوعِ صفحه رندر شود؟».

هدفِ صریحِ این ماژول (طبقِ الزامِ کار: «Create one central, typed way to
resolve the current StorefrontPage... Do not scatter
``version.pages.get(page_type=...)`` across many unrelated views»): پیش از
این فاز، دقیقاً همین یک کوئری —
``StorefrontLayout.objects.filter(store=store, uses_visual_storefront_layout=True,
published_version__isnull=False).select_related("published_version").first()``
— به‌صورتِ کپی‌شده در دو جایِ مستقلِ کدبیس وجود داشت
(``apps.catalog.views.home()`` و
``apps.core.context_processors._global_identity_version``). این ماژول آن
تکرار را حذف می‌کند و تنها منبعِ حقیقتِ جدید برایِ «آیا این Store یک
Storefront V2 منتشرشده دارد؟» می‌شود — ``home()``/context processor هم در
همینِ کامیت به این تابع مهاجرت کرده‌اند (نگاه کنید به گزارشِ Phase 1B).

هرگز Draft را برنمی‌گرداند — طبقِ تصمیمِ همیشگیِ کاربر (Phase 0.5/1A):
«Public storefront must never read the editable draft». اگر Storeای هرگز
منتشر نکرده باشد (یا فلگِ ``uses_visual_storefront_layout`` را فعال نکرده
باشد)، ``None`` برمی‌گردد — نه یک fallback، نه یک نسخه‌ی ساختگی؛ فراخوان
مسئولِ رفتارِ fallback (رندرِ الگویِ قدیمی) است، دقیقاً همان مسئولیت‌بندیِ
موجودِ ``home()`` امروز."""

from __future__ import annotations

from typing import NamedTuple

from .. import models as sfb_models


class ResolvedStorefrontPage(NamedTuple):
    """نتیجه‌یِ حل‌شده‌یِ یک درخواستِ صفحه — یا هر دو مقدار پر است (Store یک
    Storefront V2 منتشرشده دارد و همان صفحه‌یِ خواسته‌شده وجود دارد — که
    همیشه باید وجود داشته باشد، چون ``StorefrontPage.ensure_version_pages``
    هر شش نوع را تضمین می‌کند)، یا هر دو ``None`` است (این Store هنوز
    Storefront V2 منتشر نکرده)."""

    version: "sfb_models.StorefrontLayoutVersion | None"
    page: "sfb_models.StorefrontPage | None"

    @property
    def is_resolved(self) -> bool:
        return self.version is not None


_UNRESOLVED = ResolvedStorefrontPage(version=None, page=None)


def _published_layout_queryset(**filter_kwargs):
    """کوئریِ مشترک — تنها جایِ نوشته‌شدنِ شرطِ ``published_version__isnull=False``
    در کلِ کدبیس (اشاره‌گرِ منتشرشده تنها منبعِ حقیقت است؛ پرچمِ منسوخِ
    ``uses_visual_storefront_layout`` دیگر خوانده نمی‌شود). Phase 1B: پیش از
    این، همین شرط به‌صورتِ کپی‌شده در دو جایِ مستقل نوشته شده بود
    (``apps.catalog.views.home()`` و
    ``apps.core.context_processors._global_identity_version``) — هر دو
    اکنون به این تابع (از طریقِ ``get_published_layout``/
    ``get_published_layout_for_store_id``) مهاجرت کرده‌اند."""
    return sfb_models.StorefrontLayout.objects.filter(
        published_version__isnull=False, **filter_kwargs,
    ).select_related("published_version")


def get_published_layout(store) -> "sfb_models.StorefrontLayout | None":
    """اگر این Store یک ``StorefrontLayout`` با فلگِ فعال و یک نسخه‌ی
    منتشرشده‌ی معتبر داشته باشد، همان ردیف را برمی‌گرداند — وگرنه
    ``None``. برایِ فراخوان‌هایی که یک آبجکتِ ``Store`` واقعی در دست دارند
    (اکثرِ ویوهایِ عمومی)."""
    return _published_layout_queryset(store=store).first()


def get_published_layout_for_store_id(store_id) -> "sfb_models.StorefrontLayout | None":
    """همان ``get_published_layout``، فقط برایِ فراخوان‌هایی که تنها
    ``store_id`` در دست دارند (مثلِ context processorهایی که عمداً از
    ``request.store`` استفاده نمی‌کنند — نگاه کنید به توضیحِ
    ``apps.core.context_processors._global_identity_version``) — بدونِ
    نیازِ آن‌ها به واکشیِ جداگانه‌یِ خودِ Store."""
    if store_id is None:
        return None
    return _published_layout_queryset(store_id=store_id).first()


def resolve_published_page(store, page_type: str) -> ResolvedStorefrontPage:
    """صفحه‌یِ منتشرشده‌یِ ``page_type`` برایِ ``store`` را حل می‌کند.

    ``page_type`` باید یکی از مقادیرِ ``StorefrontPage.PageType`` باشد
    (``home``/``product_detail``/``listing``/``collection``/``search``/
    ``cart``) — رشته‌یِ نامعتبر همان رفتارِ «حل‌نشده» را می‌گیرد (نه خطا)،
    چون تنها فراخوان‌کننده‌هایِ این تابع کدِ داخلیِ خودِ همین Storefront
    هستند که همیشه یکی از این شش مقدارِ ثابت را پاس می‌دهند — یک رشته‌ی
    اشتباهِ برنامه‌نویسی اینجا باید در تست دیده شود، نه در Productionِ
    زنده با یک ۵۰۰."""
    layout = get_published_layout(store)
    if layout is None:
        return _UNRESOLVED

    published = layout.published_version
    try:
        page = published.pages.get(page_type=page_type)
    except sfb_models.StorefrontPage.DoesNotExist:
        # نباید هرگز رخ دهد (``ensure_version_pages`` هر شش نوع را تضمین
        # می‌کند) — اما به‌جایِ کرش، defensive fallback به «حل‌نشده»،
        # دقیقاً همان الگویِ section_key ناشناخته در render_service.
        return _UNRESOLVED
    return ResolvedStorefrontPage(version=published, page=page)
