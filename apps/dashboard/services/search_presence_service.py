"""«دیده‌شدن در گوگل و جست‌وجوی هوشمند» — the facts behind section A of the integrations page.

Every state here is computed from the SAME sources the storefront itself obeys, never invented for the page:

* published?                → ``publication_service.is_publicly_visible`` (publication authority)
* the public address        → ``resolve_storefront_url_for_store`` (verified custom domain → claimed platform sub-domain → trial) and the
                              store's domain rows (``domain_settings_service.domain_overview`` for pending / error phases)
* indexable?                → ``seo_policy.is_non_public_host`` + published — the very rule robots.txt, the sitemap, ``<meta robots>``,
                              canonical URLs and JSON-LD read
* crawler policy            → ``seo_policy.AI_*_CRAWLERS`` / ``ai_training_blocked``
* IndexNow                  → ``indexnow.indexnow_enabled`` (platform setting) + ``indexnow.is_verified_host`` rules (verified custom domain only)

Nothing here contacts a search engine, saves anything or enables anything. Nothing promises indexing, a ranking, or an appearance in an AI
answer. A capability that is built but waiting is reported as WAITING (with what it waits for), never as «0 automatic jobs» and never as
«active»."""

from __future__ import annotations

from urllib.parse import urlsplit

from django.urls import reverse

from apps.catalog.services.product_publish_service import storefront_listing_products
from apps.core import indexnow, seo_policy
from apps.stores.models import StoreDomain
from apps.stores.resolution import resolve_storefront_url_for_store
from apps.stores.services.publication_service import is_publicly_visible

# ---- capability states (the only vocabulary the page uses) ----------------------------------------------------------------------
READY, ACTIVE, WAITING_ADDRESS, WAITING_PUBLISH = "ready", "active", "waiting_address", "waiting_publish"
PLATFORM_DISABLED, ERROR, UNAVAILABLE = "platform_disabled", "error", "unavailable"

STATE_LABELS = {
    READY: "آماده",
    ACTIVE: "فعال",
    WAITING_ADDRESS: "منتظر آدرس عمومی",
    WAITING_PUBLISH: "منتظر انتشار فروشگاه",
    PLATFORM_DISABLED: "غیرفعال توسط پلتفرم",
    ERROR: "خطا",
    UNAVAILABLE: "در دسترس نیست",
}
STATE_TONES = {READY: "ok", ACTIVE: "ok", WAITING_ADDRESS: "info", WAITING_PUBLISH: "info", PLATFORM_DISABLED: "off", ERROR: "danger", UNAVAILABLE: "off"}

# ---- the store address card ------------------------------------------------------------------------------------------------------
ADDRESS_TEST_ENV, ADDRESS_PUBLIC_READY, ADDRESS_DOMAIN_PENDING = "test_env", "public_ready", "domain_pending"
ADDRESS_DOMAIN_ACTIVE, ADDRESS_ERROR, ADDRESS_NONE = "domain_active", "error", "no_address"
ADDRESS_LABELS = {
    ADDRESS_TEST_ENV: ("محیط آزمایشی", "warn"),
    ADDRESS_PUBLIC_READY: ("آدرس عمومی آماده", "ok"),
    ADDRESS_DOMAIN_PENDING: ("دامنه در انتظار تأیید", "info"),
    ADDRESS_DOMAIN_ACTIVE: ("دامنه فعال", "ok"),
    ADDRESS_ERROR: ("خطای اتصال یا تنظیمات", "danger"),
    ADDRESS_NONE: ("آدرس عمومی ثبت نشده", "warn"),
}
TEST_ENV_MESSAGE = ("این فروشگاه در محیط آزمایشی است. پس از فعال‌شدن آدرس عمومی واقعی، امکانات معرفی فروشگاه به موتورهای جست‌وجو قابل استفاده خواهند بود.")

#: Google's own pages — links only, nothing is requested from them
SEARCH_CONSOLE_URL = "https://search.google.com/search-console"
SITEMAP_GUIDE_URL = "https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap"
GUIDE_LINKS = {"search_console": SEARCH_CONSOLE_URL, "sitemap_guide": SITEMAP_GUIDE_URL}


def _domain_url():
    return reverse("dashboard:settings") + "?section=domain"


def _cap(key, title, state, detail):
    return {"key": key, "title": title, "state": state, "label": STATE_LABELS[state], "tone": STATE_TONES[state], "detail": detail}


def _public_facts(store, request):
    """published / resolved address / indexable — computed once, from the policy modules."""
    published = is_publicly_visible(store)
    resolve_failed = False
    try:
        url = resolve_storefront_url_for_store(store, request) or ""
    except Exception:                                                           # noqa: BLE001 - a broken address must show as an error, not crash the page
        url, resolve_failed = "", True
    parts = urlsplit(url) if url else None
    host = parts.netloc if parts else ""
    public_host = bool(host) and not seo_policy.is_non_public_host(host)
    return {
        "published": published, "url": url, "host": host, "public_host": public_host, "resolve_failed": resolve_failed,
        "indexable": published and public_host,
        "origin": f"{parts.scheme}://{host}" if host else "",
        "products": storefront_listing_products(store).count() if published else 0,
        "verified_custom": store.domains.filter(
            domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN, verification_status=StoreDomain.VerificationStatus.VERIFIED,
            retired_at__isnull=True,
        ).exists(),
    }


def _address_state(facts, domain) -> str:
    custom = (domain or {}).get("custom_domains") or []
    if facts["resolve_failed"] or (any(row.get("phase") == "error" for row in custom) and not facts["public_host"]):
        return ADDRESS_ERROR
    if (domain or {}).get("storefront_is_local") or (facts["host"] and not facts["public_host"]):
        return ADDRESS_TEST_ENV
    if any(row.get("is_primary") for row in custom):
        return ADDRESS_DOMAIN_ACTIVE
    if any(not row.get("is_primary") for row in custom):
        return ADDRESS_DOMAIN_PENDING
    return ADDRESS_PUBLIC_READY if facts["public_host"] else ADDRESS_NONE


def _infrastructure(facts) -> list[dict]:
    """robots.txt, sitemap, canonical, JSON-LD, the indexability policy and IndexNow — each with its OWN state."""
    if facts["resolve_failed"]:
        wait = ERROR
        detail_wait = "تشخیص آدرس عمومی فروشگاه با خطا روبه‌رو شد؛ تنظیمات دامنه را بررسی کنید."
    elif not facts["published"]:
        wait, detail_wait = WAITING_PUBLISH, "تا فروشگاه منتشر نشود، صفحه‌ها برای موتورهای جست‌وجو بسته می‌مانند."
    else:
        wait, detail_wait = WAITING_ADDRESS, "این آدرس آزمایشی/محلی است؛ با آدرس عمومیِ واقعی خودکار فعال می‌شود."
    live = ACTIVE if facts["indexable"] else wait
    origin = facts["origin"]
    code = "indexable" if facts["indexable"] else ("store_not_public" if not facts["published"] else "test_host")
    caps = [
        _cap("robots", "robots.txt", live,
             "صفحه‌های عمومی مجاز و بخش‌های خصوصی (سبد، پرداخت، حساب کاربری، مدیریت) بسته‌اند." if facts["indexable"]
             else f"ساخته شده است و فعلاً همهٔ صفحه‌ها را می‌بندد. {detail_wait}"),
        _cap("sitemap", "نقشهٔ سایت (Sitemap)", live,
             (f"آدرس: {origin}/sitemap.xml — {facts['products']} کالای قابل‌نمایش." if facts["indexable"] else f"آماده‌ی انتشار است. {detail_wait}")),
        _cap("canonical", "آدرس مرجع (Canonical)", live,
             (f"همهٔ صفحه‌ها به {origin} اشاره می‌کنند؛ آدرس‌های دیگر، نسخهٔ تکراری حساب نمی‌شوند." if facts["indexable"]
              else f"از آدرس عمومیِ فروشگاه ساخته می‌شود. {detail_wait}")),
        _cap("jsonld", "داده‌های ساختاریافته (JSON-LD)", live,
             "نام فروشگاه، کالا، قیمت و موجودی از اطلاعات واقعیِ شما؛ امتیاز، نظر یا ارسال ساختگی اضافه نمی‌شود." if facts["indexable"]
             else f"از اطلاعات واقعیِ فروشگاه ساخته می‌شود. {detail_wait}"),
        _cap("indexability", "سیاست ایندکس‌پذیری", live, seo_policy.REASONS_FA[code]),
    ]
    if not indexnow.indexnow_enabled():
        caps.append(_cap("indexnow", "اطلاع‌رسانی IndexNow", PLATFORM_DISABLED, "هنوز توسط مدیر پلتفرم فعال نشده است؛ این برای ایندکس‌شدن لازم نیست."))
    elif not facts["indexable"]:
        caps.append(_cap("indexnow", "اطلاع‌رسانی IndexNow", wait, detail_wait))
    elif not facts["verified_custom"]:
        caps.append(_cap("indexnow", "اطلاع‌رسانی IndexNow", UNAVAILABLE, "فقط برای دامنهٔ اختصاصیِ تأییدشده کار می‌کند؛ آدرس رایگان راستی‌سی پوشش داده نمی‌شود."))
    else:
        caps.append(_cap("indexnow", "اطلاع‌رسانی IndexNow", READY, "با تغییر کالاها، آدرس‌های تغییرکرده به‌عنوان پیشنهاد برای موتورهای شرکت‌کننده ارسال می‌شود؛ ایندکس‌شدن را تضمین نمی‌کند."))
    return caps


def _next_action(facts, address_state, request, store):
    """ONE main action (or ``None`` when nothing is needed from the seller)."""
    if address_state == ADDRESS_ERROR:
        return {"key": "domain", "label": "بررسی تنظیمات دامنه", "href": _domain_url()}
    if address_state in (ADDRESS_TEST_ENV, ADDRESS_NONE, ADDRESS_DOMAIN_PENDING):
        return {"key": "domain", "label": "رفتن به تنظیمات دامنه", "href": _domain_url()}
    if not facts["published"]:
        from apps.dashboard.services.checklist_service import _platform_url

        return {"key": "publish", "label": "انتشار فروشگاه", "href": _platform_url(request, f"/app/stores/{store.public_id}/onboarding/review/")}
    if not facts["products"]:
        return {"key": "products", "label": "افزودن کالا", "href": reverse("dashboard:product-list")}
    return None


def _summary(facts, address_state, caps, action):
    active = sum(1 for c in caps if c["state"] == ACTIVE)
    ready = sum(1 for c in caps if c["state"] == READY)
    waiting = [c for c in caps if c["state"] in (WAITING_ADDRESS, WAITING_PUBLISH)]
    errors = [c for c in caps if c["state"] == ERROR]
    if errors:
        infra = {"state": ERROR, "text": "تشخیص آدرس با خطا روبه‌رو شد"}
    elif facts["indexable"]:
        infra = {"state": ACTIVE, "text": f"{active + ready} قابلیت فنی فعال یا آماده است"}
    else:
        infra = {"state": WAITING_ADDRESS if facts["published"] else WAITING_PUBLISH,
                 "text": f"{len(waiting)} قابلیت فنی ساخته شده و منتظر {'آدرس عمومی' if facts['published'] else 'انتشار فروشگاه'} است"}
    items = [
        {"key": "published", "label": "فروشگاه منتشر شده؟", "ok": facts["published"],
         "text": "بله، برای عموم باز است." if facts["published"] else "هنوز نه."},
        {"key": "address", "label": "آدرس عمومیِ معتبر و قابل‌ایندکس؟", "ok": facts["indexable"],
         "text": (f"بله: {facts['host']}" if facts["indexable"] else ADDRESS_LABELS[address_state][0])},
        {"key": "infra", "label": "زیرساخت فنی SEO آماده است؟", "ok": infra["state"] in (ACTIVE, READY), "text": infra["text"]},
    ]
    return items, infra


def _counters(caps) -> dict:
    """Counts + the plain sentence for the card chip. Never «0 …» while capabilities exist and merely wait; an error is said as an error."""
    count = lambda *states: sum(1 for c in caps if c["state"] in states)          # noqa: E731
    active, ready, waiting, errors = count(ACTIVE), count(READY), count(WAITING_ADDRESS, WAITING_PUBLISH), count(ERROR)
    if errors:
        text, tone = "خطا در تشخیص آدرس عمومی", "danger"
    elif waiting:
        text, tone = f"{waiting} قابلیت ساخته شده و منتظر است", "info"
    else:
        text, tone = f"{active + ready} قابلیت فعال یا آماده", "ok"
    return {"active": active, "ready": ready, "waiting": waiting, "errors": errors, "total": len(caps), "text": text, "tone": tone}


def presence(store, request, domain: dict | None = None) -> dict:
    """The whole of section A as plain data (JSON-safe, no model instances)."""
    facts = _public_facts(store, request)
    address_state = _address_state(facts, domain)
    caps = _infrastructure(facts)
    action = _next_action(facts, address_state, request, store)
    items, infra = _summary(facts, address_state, caps, action)
    label, tone = ADDRESS_LABELS[address_state]
    origin = facts["origin"]
    sitemap_url = f"{origin}/sitemap.xml" if facts["indexable"] else ""
    return {
        "published": facts["published"], "indexable": facts["indexable"], "host": facts["host"],
        "summary_items": items, "infra": infra,
        "next_action": action,
        "headline": ("این فروشگاه در محیط آزمایشی است" if address_state == ADDRESS_TEST_ENV
                     else "فروشگاه شما از نظر فنی برای معرفی به موتورهای جست‌وجو آماده است" if facts["indexable"] and not action
                     else "برای دیده‌شدن در جست‌وجو یک قدم باقی مانده است" if action else "زیرساخت آماده است و منتظر آدرس عمومی می‌ماند"),
        "test_env_message": TEST_ENV_MESSAGE if address_state == ADDRESS_TEST_ENV else "",
        "address": {"state": address_state, "label": label, "tone": tone, "host": facts["host"], "href": _domain_url(),
                    "primary": not (action and action["key"] == "domain"),
                    "text": {
                        ADDRESS_TEST_ENV: "آدرسی که اکنون با آن وارد شده‌اید (مثل localhost) فقط برای آزمایش است و موتورهای جست‌وجو آن را نمی‌بینند.",
                        ADDRESS_PUBLIC_READY: f"فروشگاه با آدرس {facts['host']} در دسترس عموم است.",
                        ADDRESS_DOMAIN_PENDING: "دامنهٔ اختصاصی ثبت شده ولی هنوز کامل نشده؛ تا آن زمان آدرس راستی‌سی کار می‌کند.",
                        ADDRESS_DOMAIN_ACTIVE: f"فروشگاه با دامنهٔ اختصاصی {facts['host']} آنلاین است.",
                        ADDRESS_ERROR: "در تشخیص آدرس یا اتصال دامنه خطایی دیده شد؛ جزئیات در تنظیمات دامنه است.",
                        ADDRESS_NONE: "هنوز آدرس عمومیِ قابل‌استفاده‌ای ثبت نشده است.",
                    }[address_state]},
        "capabilities": caps,
        "counters": _counters(caps),
        "search_console": {
            "title": "مدیریت حضور در گوگل",
            "auto_connect_available": False,
            "auto_connect_text": "اتصال خودکار هنوز در دسترس نیست؛ راستی‌سی به حساب Google شما وصل نمی‌شود و وضعیتی از گوگل نمی‌خواند.",
            "sitemap_url": sitemap_url,
            "links": GUIDE_LINKS,
            "waiting_text": "" if facts["indexable"] else "پس از فعال‌شدن آدرس عمومی، آدرس نقشهٔ سایت و راهنمای ثبت اینجا نمایش داده می‌شود.",
        },
        "crawlers": {
            "search": list(seo_policy.AI_SEARCH_CRAWLERS),
            "training": list(seo_policy.AI_TRAINING_CRAWLERS),
            "training_blocked": seo_policy.ai_training_blocked(),
        },
    }
