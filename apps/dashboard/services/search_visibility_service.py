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


def provider_effect(code: str, *, connected: bool, store_live: bool, tracking_enabled: bool = True) -> dict:
    """The honest consequence of the saved identifier — drives the badge text of each integration row."""
    if code in LIVE_ON_PUBLIC_PAGES:
        if not connected:
            return {"state": "off", "text": "متصل‌نشده"}
        if store_live and not tracking_enabled:
            return {"state": "privacy", "text": "ذخیره شد — بارگذاری روی فروشگاه هنوز توسط مدیر پلتفرم (به‌خاطر حریم خصوصی و رضایت بازدیدکننده) فعال نشده است"}
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


# ---- the seller-facing structure of the integrations page (five plain-language groups) -------------------------------------------------
#: the readiness rows a seller can act on (everything else RastiSi does by itself and is shown folded under «جزئیات فنی»)
SELLER_FACING_ROWS = ("published", "public_host", "products")
AUTOMATIC_ROWS = ("robots_sitemap", "structured_data", "ai_search", "indexnow")
#: not-yet-built services, split by the group they will belong to (all are listed — never as connectable — under «امکانات آینده»)
SALES_TOOL_PROVIDERS = frozenset({"torob"})
TRUST_PROVIDERS = frozenset({"enamad"})


def _chip(state, text):
    return {"state": state, "text": text}


def integration_overview(seo_rows: list[dict], integration_rows: list[dict]) -> dict:
    """The summary + one status chip per group for the page. Pure presentation over data the page already has — it contacts nobody, enables
    nothing and never promises indexing, a ranking or an appearance in an AI answer."""
    by_key = {row["key"]: row for row in seo_rows}
    seller_rows = [by_key[key] for key in SELLER_FACING_ROWS if key in by_key]
    todo = [row for row in seller_rows if row["state"] == TODO]
    automatic = [by_key[key] for key in AUTOMATIC_ROWS if key in by_key]
    automatic_done = [row["title"] for row in automatic if row["state"] == OK]
    if todo:
        visibility_chip = _chip("todo", f"{len(todo)} کار باقی مانده")
        headline = "برای دیده‌شدن در جست‌وجو هنوز کاری لازم است"
        next_action = todo[0]["action"] or todo[0]["title"]
    else:
        visibility_chip = _chip("ok", "آماده برای جست‌وجو")
        headline = "فروشگاه شما از نظر فنی برای دیده‌شدن در جست‌وجو آماده است"
        next_action = ""

    def _rows(codes):
        return [row for row in integration_rows if row["provider"].code in codes]

    analytics = [row for row in integration_rows if row["group"] == "live"]
    connected_analytics = [row for row in analytics if row["is_connected"]]
    if not connected_analytics:
        stats_chip = _chip("off", "متصل‌نشده")
    elif any(row["effect"]["state"] == "live" for row in connected_analytics):
        stats_chip = _chip("ok", "فعال روی صفحه‌های عمومی")
    elif any(row["effect"]["state"] == "privacy" for row in connected_analytics):
        stats_chip = _chip("info", "شناسه ذخیره شد؛ بارگذاری هنوز فعال نشده")
    else:
        stats_chip = _chip("info", "شناسه ذخیره شد؛ پس از انتشار فعال می‌شود")
    sales_connected = [row for row in _rows(SALES_TOOL_PROVIDERS) if row["is_connected"]]
    trust_connected = [row for row in _rows(TRUST_PROVIDERS) if row["is_connected"]]
    return {
        "headline": headline,
        "next_action": next_action,
        "ready": not todo,
        "automatic_done": automatic_done,
        "needs_you": [row["title"] for row in todo],
        "seller_rows": seller_rows,
        "automatic_rows": automatic,
        "manual_rows": [row for row in seo_rows if row["key"] not in SELLER_FACING_ROWS + AUTOMATIC_ROWS],
        "sales_rows": _rows(SALES_TOOL_PROVIDERS),
        "trust_rows": _rows(TRUST_PROVIDERS),
        "analytics_rows": analytics,
        "chips": {
            "visibility": visibility_chip,
            "stats": stats_chip,
            "sales": _chip("info", "فقط شناسه ذخیره شده") if sales_connected else _chip("off", "متصل‌نشده"),
            "trust": _chip("info", "فقط شناسه ذخیره شده") if trust_connected else _chip("off", "متصل‌نشده"),
            "future": _chip("off", "به‌زودی"),
        },
        "not_available_count": len(NOT_AVAILABLE),
    }
