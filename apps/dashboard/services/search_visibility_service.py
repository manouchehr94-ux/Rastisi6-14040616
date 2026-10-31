"""Facts for the «visibility» part of the integrations page: what RastiSi already does for search engines on its own, what the seller
still has to do (if anything), and which services are NOT available yet.

Honesty rules (the page must never overstate):
* «ready» is not «connected»: a row is ``ok`` only when the thing really happens now (checked from real state), ``todo`` when the
  seller/store must act first, ``info`` for facts, ``off`` for something that is not available/enabled;
* nothing here promises indexing, a ranking, or an appearance in any AI answer;
* nothing contacts a search engine — every value comes from the database/settings."""

from __future__ import annotations

from urllib.parse import urlsplit

from django.conf import settings

from apps.catalog.services.product_publish_service import storefront_listing_products
from apps.core import indexnow, seo_policy
from apps.stores.resolution import resolve_storefront_url_for_store
from apps.stores.services.publication_service import is_publicly_visible

OK, TODO, INFO, OFF = "ok", "todo", "info", "off"

#: services that do NOT exist yet — shown separately so nobody mistakes them for connectable integrations
NOT_AVAILABLE = (
    {"key": "search_console", "title": "Google Search Console",
     "note": "ثبتِ سایت‌مپ و پایش از طریق API نیازمندِ حسابِ گوگلِ خودِ شماست و هنوز متصل نشده. تا آن زمان: خودتان در Search Console دامنه را اضافه و آدرسِ سایت‌مپ را ثبت کنید."},
    {"key": "bing_webmaster", "title": "Bing Webmaster Tools",
     "note": "اتصالِ حساب هنوز در دسترس نیست؛ ارسالِ خودکارِ تغییرات با IndexNow آماده‌ی فعال‌سازی توسطِ مدیرِ پلتفرم است."},
    {"key": "merchant_center", "title": "Google Merchant Center / فیدِ محصول",
     "note": "هنوز فیدی ساخته یا ارسال نمی‌شود."},
    {"key": "torob_feed", "title": "فیدِ ترب",
     "note": "شناسهٔ فروشنده ذخیره می‌شود ولی فیدی برای ترب ساخته نمی‌شود."},
)


def _row(key, state, title, detail, action=""):
    return {"key": key, "state": state, "title": title, "detail": detail, "action": action}


def seo_readiness(store, request) -> list[dict]:
    published = is_publicly_visible(store)
    try:
        url = resolve_storefront_url_for_store(store, request) or ""
    except Exception:                                                     # noqa: BLE001
        url = ""
    host = urlsplit(url).netloc if url else ""
    public_host = bool(host) and not seo_policy.is_non_public_host(host)
    indexable = published and public_host
    origin = f"{urlsplit(url).scheme}://{host}" if host else ""
    products = storefront_listing_products(store).count() if published else 0

    rows = [
        _row("published", OK if published else TODO, "فروشگاه منتشر شده",
             "فروشگاه برای عموم باز است." if published else "تا فروشگاه منتشر نشود، هیچ موتورِ جست‌وجویی اجازهٔ دیدنِ صفحه‌ها را ندارد.",
             "" if published else "ابتدا فروشگاه را منتشر کنید"),
        _row("public_host", OK if public_host else TODO, "آدرسِ عمومی",
             (f"صفحه‌ها با آدرسِ {host} معرفی می‌شوند." if public_host else
              "این آدرس آزمایشی/محلی است و ایندکس نمی‌شود. فروشگاهِ واقعی با آدرسِ راستی‌سی یا دامنهٔ اختصاصیِ تأییدشده معرفی می‌شود."),
             "" if public_host else "آدرسِ عمومی را در «دامنه و آدرس» ببینید"),
        _row("robots_sitemap", OK if indexable else INFO, "robots.txt و نقشهٔ سایت",
             (f"خودکار ساخته می‌شود: {origin}/sitemap.xml — فقط صفحه‌های عمومی (بدونِ سبد، پرداخت و حساب کاربری)." if indexable else
              "پس از انتشار روی آدرسِ عمومی خودکار فعال می‌شود؛ تا آن زمان همهٔ صفحه‌ها برای موتورهای جست‌وجو بسته‌اند."),),
        _row("products", OK if products else (TODO if published else INFO), "کالاهای قابل‌نمایش",
             f"{products} کالا در نقشهٔ سایت و دادهٔ ساختاریافته (قیمت و موجودیِ واقعی) قرار می‌گیرد." if products else
             "هنوز کالای منتشرشده‌ای نیست؛ بدونِ کالا چیزی برای نمایش در جست‌وجو نیست."),
        _row("structured_data", OK if indexable else INFO, "دادهٔ ساختاریافته (JSON-LD)",
             "نام فروشگاه، کالا، قیمت و موجودی از اطلاعاتِ واقعیِ خودتان ساخته می‌شود؛ امتیاز، نظر یا ارسالِ ساختگی اضافه نمی‌شود."),
        _row("ai_search", INFO, "جست‌وجوی هوشمند (ChatGPT، Perplexity و مشابه)",
             "ربات‌های «جست‌وجو» مجازند صفحه‌های عمومی را ببینند؛ ربات‌های «آموزشِ مدل» "
             + ("طبقِ سیاستِ پلتفرم مسدودند." if seo_policy.ai_training_blocked() else "طبقِ سیاستِ پلتفرم مجازند.")
             + " این تنظیم نمایش در پاسخِ هوش مصنوعی را تضمین نمی‌کند."),
        _row("indexnow", INFO if indexnow.indexnow_enabled() else OFF, "اطلاع‌رسانیِ خودکار به Bing (IndexNow)",
             "تغییرها به‌صورتِ پیشنهاد برای موتورهای شرکت‌کننده ارسال می‌شود؛ این به‌معنیِ ایندکس‌شدن نیست." if indexnow.indexnow_enabled()
             else "هنوز توسطِ مدیرِ پلتفرم فعال نشده است."),
        _row("search_console", TODO, "Google Search Console",
             "به حسابِ گوگلِ شما نیاز دارد و خودکار نیست: دامنه را در Search Console اضافه کنید و آدرسِ نقشهٔ سایت را ثبت کنید."
             + (f" آدرس: {origin}/sitemap.xml" if indexable else ""),
             "راهنمای گوگل"),
    ]
    return rows


# Provider code → what saving its identifier really does on the storefront today.
LIVE_ON_PUBLIC_PAGES = frozenset({"google_analytics", "google_tag_manager", "ad_pixel"})


def provider_effect(code: str, *, connected: bool, store_live: bool) -> dict:
    """The honest consequence of the saved identifier — drives the badge text of each integration row."""
    if code in LIVE_ON_PUBLIC_PAGES:
        if not connected:
            return {"state": "off", "text": "متصل‌نشده"}
        if store_live:
            return {"state": "live", "text": "فعال روی صفحه‌های عمومی"}
        return {"state": "waiting", "text": "ذخیره شد — پس از انتشارِ فروشگاه روی آدرسِ عمومی فعال می‌شود"}
    if connected:
        return {"state": "stored", "text": "فقط ذخیره شده — هنوز نمایش یا ارسالی انجام نمی‌شود"}
    return {"state": "off", "text": "متصل‌نشده"}


def store_live(store, request) -> bool:
    if not is_publicly_visible(store):
        return False
    try:
        url = resolve_storefront_url_for_store(store, request) or ""
    except Exception:                                                     # noqa: BLE001
        return False
    host = urlsplit(url).netloc
    return bool(host) and not seo_policy.is_non_public_host(host)
