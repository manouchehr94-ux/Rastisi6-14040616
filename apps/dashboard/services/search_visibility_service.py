"""Facts for the integrations page, outside section A (see ``search_presence_service`` for «دیده‌شدن در جست‌وجو»): what saving an identifier
really does, which services are NOT available yet, and the summary + one status chip per group.

One vocabulary for every service (the page never mixes them up):

* **ذخیره‌شده** (saved)      — an identifier is stored for THIS store;
* **قالب معتبر** (validated) — the stored value matches the provider's strict pattern. This is a FORMAT check made here and now; it is
                               not a call to Google / Meta / Torob / eNamad and proves nothing about the account behind the value;
* **فعال** (enabled)         — the seller switched the identifier on (``StoreIntegrationConnection.is_active``);
* **ردیابی فعال است** (live) — a tracker really loads on public pages: enabled AND the platform allowed storefront tracking AND the store is
                               published on a real public address (``tracking_service``'s own rules).

«اتصال تأییدشده» (a connection confirmed by the other side) does not exist for any service: RastiSi has no API contract with any of them,
so no row ever says it. Nothing here contacts anyone, promises indexing, a ranking, or an appearance in an AI answer."""

from __future__ import annotations

from urllib.parse import urlsplit

from apps.core import seo_policy
from apps.stores.resolution import resolve_storefront_url_for_store
from apps.stores.services.publication_service import is_publicly_visible

#: services that do NOT exist yet — shown separately so nobody mistakes them for connectable integrations
NOT_AVAILABLE = (
    {"key": "bing_webmaster", "title": "Bing Webmaster Tools",
     "note": "اتصال حساب هنوز در دسترس نیست. اطلاع‌رسانی IndexNow (در بخش «دیده‌شدن در جست‌وجو») به اتصال حساب وابسته نیست."},
    {"key": "merchant_center", "title": "Google Merchant Center / فید محصول",
     "note": "پشتیبانی نمی‌شود: Google Merchant Center برای کسب‌وکارهای مستقر در ایران در دسترس نیست؛ فیدی ساخته یا ارسال نمی‌شود و راه دورزدن این محدودیت پیشنهاد نمی‌شود."},
    {"key": "torob_feed", "title": "فید ترب",
     "note": "فیدی برای ترب ساخته یا ارسال نمی‌شود؛ شناسهٔ فروشنده فقط ذخیره می‌شود."},
)

# Provider code → what saving its identifier really does on the storefront today.
LIVE_ON_PUBLIC_PAGES = frozenset({"google_analytics", "google_tag_manager", "ad_pixel"})
SALES_TOOL_PROVIDERS = frozenset({"torob"})
TRUST_PROVIDERS = frozenset({"enamad"})

#: «saved ≠ live» in plain words, shown once above the trackers
TRACKING_CONSENT_NOTE = (
    "ذخیره‌کردن شناسه، ردیابی را روشن نمی‌کند. ردیابی بازدیدکننده سه شرط دارد: مدیر پلتفرم آن را فعال کرده باشد (پایهٔ حقوقی)، فروشگاه روی آدرس عمومی منتشر شده باشد، "
    "و خودِ بازدیدکننده در بنر رضایتِ فروشگاه موافقت کرده باشد؛ تا آن زمان هیچ ابزار ردیابی‌ای بارگذاری نمی‌شود و شناسه فقط ذخیره می‌ماند."
)
DUPLICATE_TRACKING_NOTE = (
    "هم GA4 و هم GTM روشن است؛ این یک وضعیت پشتیبانی‌شده است، نه خطا. برای اینکه هر بازدید دوبار ثبت نشود، راستی‌سی فقط GTM را بارگذاری می‌کند و GA4 مستقیم را بارگذاری نمی‌کند. "
    "اگر آمار GA4 می‌خواهید، تگ GA4 را داخل کانتینر GTM بسازید."
)

#: views (horizontal category buttons) of the page — one place for the keys, labels and which service lives where
VIEWS = (
    ("overview", "نمای کلی"), ("seo", "جست‌وجو و سئو"), ("analytics", "آمار و تبلیغات"),
    ("torob", "ترب"), ("enamad", "اینماد"), ("future", "امکانات آینده"),
)
VIEW_KEYS = tuple(key for key, _ in VIEWS)
_PROVIDER_VIEW = {"google_analytics": "analytics", "google_tag_manager": "analytics", "ad_pixel": "analytics", "torob": "torob", "enamad": "enamad"}


def normalize_view(raw) -> str:
    raw = (raw or "").strip().lower()
    return raw if raw in VIEW_KEYS else "overview"


def view_for_provider(provider_code: str) -> str:
    """The view that holds this service — POST handlers send the seller back there, so a save never throws them to another tab."""
    return _PROVIDER_VIEW.get(provider_code, "overview")


def tracking_guidance(rows: list[dict]) -> dict | None:
    """Proportionate, non-alarming guidance for GA4 / GTM (QA-06). Never claims RastiSi can read a GTM container; never turns a supported
    combination into an error. ``None`` when neither is relevant (nothing saved)."""
    by_code = {row["provider"].code: row for row in rows}
    ga4, gtm = by_code.get("google_analytics"), by_code.get("google_tag_manager")
    ga4_on, gtm_on = bool(ga4 and ga4["is_connected"]), bool(gtm and gtm["is_connected"])
    ga4_saved, gtm_saved = bool(ga4 and ga4["has_saved_credentials"]), bool(gtm and gtm["has_saved_credentials"])
    if not (ga4_saved or gtm_saved):
        return None
    if ga4_on and gtm_on:
        state, title, points = "both", "GA4 و GTM هر دو روشن است — GTM اولویت دارد", [
            "این حالت مجاز است و خطا نیست؛ برای جلوگیری از ثبت دوبارهٔ هر بازدید، فقط GTM بارگذاری می‌شود و GA4 مستقیم بارگذاری نمی‌شود.",
            "اگر آمار GA4 می‌خواهید، تگ GA4 را داخل کانتینر GTM تنظیم کنید.",
            "راستی‌سی محتوای کانتینر GTM را نمی‌بیند و نمی‌تواند درستی تگ‌های داخل آن را بررسی کند.",
        ]
    elif gtm_on:
        state, title, points = "gtm", "از GTM استفاده می‌کنید", [
            "ذخیره‌کردن شناسهٔ GTM تنها، Google Analytics را روشن نمی‌کند: تگ GA4 باید داخل کانتینر GTM ساخته شود.",
            "راستی‌سی محتوای کانتینر GTM را نمی‌بیند و نمی‌تواند درستی تگ‌های داخل آن را تأیید کند.",
        ]
    elif ga4_on:
        state, title, points = "ga4", "GA4 مستقیم", [
            "اگر فقط آمار گوگل می‌خواهید، همین مسیر مستقیم کافی است و به GTM نیازی ندارید.",
            "اگر بعداً GTM را روشن کنید، GTM اولویت می‌گیرد و GA4 باید داخل کانتینر ساخته شود.",
        ]
    else:
        return None
    return {"state": state, "title": title, "points": points}


def provider_effect(code: str, *, connected: bool, store_live: bool, tracking_enabled: bool = True, has_saved: bool = False) -> dict:
    """The honest consequence of the saved identifier — drives the badge of each integration row.
    ``badge`` is the short word, ``text`` the full sentence; ``state`` is a stable key the tests and CSS read."""
    if code in LIVE_ON_PUBLIC_PAGES:
        if not connected:
            if has_saved:
                return {"state": "paused", "badge": "ذخیره‌شده — خاموش", "text": "شناسه ذخیره است ولی استفاده از آن خاموش است؛ ردیابی انجام نمی‌شود."}
            return {"state": "off", "badge": "ذخیره نشده", "text": "هنوز شناسه‌ای ذخیره نشده است."}
        if not tracking_enabled:
            return {"state": "privacy", "badge": "شناسه ذخیره شد", "text": "شناسه ذخیره شد، اما ردیابی روی فروشگاه روشن نیست: بارگذاری ردیاب‌ها هنوز توسط مدیر پلتفرم (به‌خاطر حریم خصوصی و رضایت بازدیدکننده) فعال نشده است."}
        if not store_live:
            return {"state": "waiting", "badge": "شناسه ذخیره شد", "text": "شناسه ذخیره شد؛ ردیابی پس از انتشار فروشگاه روی آدرس عمومی فعال می‌شود."}
        return {"state": "live", "badge": "ردیابی فعال است", "text": "ردیابی روی صفحه‌های عمومی فعال است."}
    if connected:
        return {"state": "stored", "badge": "شناسه ذخیره شد", "text": "فقط شناسه ذخیره شده است؛ اتصال عملیاتی یا ارسال داده‌ای انجام نمی‌شود."}
    if has_saved:
        return {"state": "paused", "badge": "ذخیره‌شده — خاموش", "text": "شناسه ذخیره است ولی استفاده از آن خاموش است."}
    return {"state": "off", "badge": "ذخیره نشده", "text": "هنوز شناسه‌ای ذخیره نشده است."}


def validation_of(provider, credentials: dict, *, has_saved: bool) -> dict:
    """A live FORMAT check of the stored value (no network, no external account). Replaces the vague «هنوز بررسی انجام نشده»."""
    if not has_saved:
        return {"state": "empty", "text": "چیزی برای بررسی ذخیره نشده است."}
    error = provider.validate(credentials)
    if error:
        return {"state": "invalid", "text": error}
    return {"state": "valid", "text": "قالب شناسه معتبر است. فقط قالب بررسی می‌شود؛ درستیِ حساب پشت آن توسط گوگل/متا/ترب/اینماد از اینجا بررسی نمی‌شود."}


def store_live(store, request) -> bool:
    if not is_publicly_visible(store):
        return False
    try:
        url = resolve_storefront_url_for_store(store, request) or ""
    except Exception:                                                     # noqa: BLE001
        return False
    host = urlsplit(url).netloc
    return bool(host) and not seo_policy.is_non_public_host(host)


def duplicate_tracking_warning(rows: list[dict]) -> str:
    codes = {row["provider"].code for row in rows if row["is_connected"]}
    return DUPLICATE_TRACKING_NOTE if {"google_analytics", "google_tag_manager"} <= codes else ""


# ---- the three questions every service answers --------------------------------------------------------------------------------------
STATUS_LABELS = {
    "needs_customer": ("نیازمند اقدام مشتری", "todo"), "waiting_platform": ("منتظر مدیر پلتفرم", "info"), "ready": ("آماده", "ok"), "checking": ("در حال بررسی", "info"),
    "active": ("فعال", "ok"), "error": ("خطا", "danger"), "unsupported": ("پشتیبانی نمی‌شود", "off"),
}
SERVICE_COPY = {
    "google_analytics": ("شناسهٔ GA4 را ذخیره می‌کند و فقط پس از رضایت بازدیدکننده، اگر پلتفرم ردیابی را فعال کرده باشد، آمار را بارگذاری می‌کند.", "شناسهٔ اندازه‌گیری (G-…) را از حساب Google Analytics خودتان وارد کنید."),
    "google_tag_manager": ("شناسهٔ GTM را ذخیره می‌کند و پس از رضایت بازدیدکننده (و فعال‌بودنِ پلتفرم) کانتینر را بارگذاری می‌کند.", "شناسهٔ کانتینر (GTM-…) را از حساب GTM خودتان وارد کنید."),
    "ad_pixel": ("شناسهٔ پیکسل را ذخیره می‌کند و فقط با رضایتِ دستهٔ تبلیغات بارگذاری می‌کند.", "شناسهٔ پیکسل را از Meta Events Manager خودتان وارد کنید."),
    "torob": ("شناسه را ذخیره می‌کند و آماده‌بودن اطلاعات کالاها را بررسی می‌کند؛ فید یا API ترب ساخته نمی‌شود.", "در ترب ثبت‌نام کنید و فروشگاه را آنجا تأیید کنید؛ شناسهٔ فروشنده را وارد کنید."),
    "enamad": ("متاتگ مجاز را در صفحهٔ اصلی و نمادِ صادرشده را در فوتر قرار می‌دهد (فقط روی دامنهٔ اختصاصیِ تأییدشدهٔ شما).", "در اینماد درخواست دهید؛ متاتگ و بعد از صدور، شناسه و کد تأیید را وارد کنید."),
}


def service_guide(row: dict) -> dict:
    """«What RastiSi does / what you do / status + next step» for one identifier service — computed from the row's real state, never from the mere presence of an id."""
    code = row["provider"].code
    does, you = SERVICE_COPY.get(code, ("", ""))
    effect, validation = row["effect"]["state"], row["validation"]["state"]
    if validation == "invalid":
        key, nxt = "error", "قالب شناسه معتبر نیست؛ آن را اصلاح کنید."
    elif not row["has_saved_credentials"]:
        key, nxt = "needs_customer", you
    elif effect == "paused":
        key, nxt = "needs_customer", "شناسه ذخیره است؛ اگر می‌خواهید استفاده شود، آن را روشن کنید."
    elif code in LIVE_ON_PUBLIC_PAGES:
        key, nxt = {"privacy": ("waiting_platform", "منتظر تصمیم مدیر پلتفرم برای فعال‌کردن ردیابی؛ کاری از شما لازم نیست."),
                    "waiting": ("ready", "فروشگاه را روی آدرس عمومی منتشر کنید؛ ردیابی پس از رضایت بازدیدکننده بارگذاری می‌شود."),
                    "live": ("active", "کاری لازم نیست؛ بازدیدکننده در بنر رضایت تصمیم می‌گیرد.")}.get(effect, ("ready", ""))
    elif code == "torob":
        key, nxt = "ready", "شناسه ذخیره شد. ثبت‌نام و تأیید در ترب با شماست؛ راستی‌سی فعلاً فید یا API برای ترب ندارد."
    elif code == "enamad":
        states = [stage["state"] for stage in (row.get("enamad") or {}).get("stages", [])]
        if "invalid" in states:
            key, nxt = "error", "یکی از اطلاعات اینماد معتبر نیست."
        elif "waiting_domain" in states:
            key, nxt = "needs_customer", "دامنهٔ اختصاصی خود را وصل و تأیید کنید؛ تا آن زمان نماد نمایش داده نمی‌شود."
        elif "ready" in states:
            key, nxt = "active", "متاتگ/نماد روی دامنهٔ اختصاصی شما نمایش داده می‌شود؛ وضعیت واقعی نماد را در پنل اینماد ببینید."
        else:
            key, nxt = "ready", ""
    else:
        key, nxt = "ready", ""
    label, tone = STATUS_LABELS[key]
    return {"does": does, "you": you, "status": key, "label": label, "tone": tone, "next": nxt}


def status_axes(row: dict, *, store_live: bool, tracking_enabled: bool) -> dict:
    """Four separate answers for one service (QA-05) — never collapsed into a vague «روشن است؟ بله»:

    1. ``saved``   — an identifier is stored for THIS store;
    2. ``enabled`` — the seller allowed the store to USE it (``is_active``);
    3. ``ready``   — the identifier is complete and format-valid, so nothing on the seller's side is missing;
    4. ``live``    — right now something really happens (a tracker may load after consent / the seal is rendered). Torob never is: nothing is sent.

    ``reason`` names the one thing that still stands between «ready» and «live». All of it is computed from backend facts."""
    code = row["provider"].code
    saved, enabled = bool(row["has_saved_credentials"]), bool(row["is_connected"])
    valid = row["validation"]["state"] == "valid"
    ready = saved and enabled and valid
    live, reason = False, ""
    if code in LIVE_ON_PUBLIC_PAGES:
        live = row["effect"]["state"] == "live"
        if not saved:
            reason = "هنوز شناسه‌ای ذخیره نشده است."
        elif not valid:
            reason = "قالب شناسهٔ ذخیره‌شده معتبر نیست."
        elif not enabled:
            reason = "استفاده از شناسه در تنظیمات فروشگاه خاموش است."
        elif not tracking_enabled:
            reason = "منتظر فعال‌سازی ردیابی توسط مدیر پلتفرم."
        elif not store_live:
            reason = "منتظر انتشار فروشگاه روی آدرس عمومی (روی آدرس آزمایشی/محلی هیچ ردیابی بارگذاری نمی‌شود)."
        else:
            reason = "فقط پس از موافقت بازدیدکننده در بنر رضایت بارگذاری می‌شود."
    elif code == "torob":
        ready = False                                    # there is no operational integration (feed/API) to be «ready»: a saved Torob ID is only a stored value
        reason = ("شناسه فقط ذخیره شده است؛ راستی‌سی فعلاً فید یا API برای ترب ندارد و چیزی به ترب ارسال نمی‌شود."
                  if saved else "هنوز شناسه‌ای ذخیره نشده است.")
    elif code == "enamad":
        states = [stage["state"] for stage in (row.get("enamad") or {}).get("stages", [])]
        live = "ready" in states
        if not saved:
            reason = "هنوز متاتگ یا شناسهٔ نماد ذخیره نشده است."
        elif "invalid" in states:
            reason = "یکی از اطلاعات ذخیره‌شده معتبر نیست."
        elif not enabled:
            reason = "استفاده از اطلاعات اینماد خاموش است."
        elif "waiting_domain" in states:
            ready = False
            reason = "دامنهٔ اختصاصیِ تأییدشده ندارید؛ تا آن زمان چیزی روی سایت قرار نمی‌گیرد."
        elif "hidden" in states and not live:
            ready = False
            reason = "نمایش نماد در فوتر را خودتان خاموش کرده‌اید."
        elif live:
            reason = "روی دامنهٔ اختصاصیِ شما نمایش داده می‌شود؛ تأییدِ رسمیِ نماد را فقط پنل اینماد می‌دهد."
    axes = [
        {"key": "saved", "short": "ذخیره‌شده", "label": "شناسه ذخیره شده؟", "on": saved},
        {"key": "enabled", "short": "استفاده روشن", "label": "استفاده از آن در تنظیمات فروشگاه فعال شده است؟", "on": enabled},
        {"key": "ready", "short": "اتصال عملیاتی" if code == "torob" else "آماده",
         "label": "اتصال عملیاتی (فید/API) وجود دارد؟" if code == "torob" else "سرویس آماده‌ی کار است؟", "on": ready},
        {"key": "live", "short": ("نمایش" if code == "enamad" else "ارسال" if code == "torob" else "ردیابی"), "label": ("همین حالا نمادی روی سایت نمایش داده می‌شود؟" if code == "enamad" else
                                  "همین حالا داده‌ای به ترب فرستاده می‌شود؟" if code == "torob" else
                                  "همین حالا ردیابی امکان‌پذیر است؟"), "on": live},
    ]
    return {"axes": axes, "reason": reason, "live": live}


def group_of(provider_code: str) -> str:
    """Which page group (B stats / C sales / D trust) holds this provider — so the page opens the group that contains the service just touched."""
    if provider_code in LIVE_ON_PUBLIC_PAGES:
        return "stats"
    if provider_code in SALES_TOOL_PROVIDERS:
        return "sales"
    if provider_code in TRUST_PROVIDERS:
        return "trust"
    return ""


def _chip(state, text):
    return {"state": state, "text": text}


def integration_overview(presence: dict, integration_rows: list[dict]) -> dict:
    """The summary + one chip per group. Pure presentation over data the page already has — contacts nobody, enables nothing."""
    action = presence["next_action"]
    counters = presence["counters"]
    if action:
        visibility_chip = _chip("todo", "یک قدم باقی مانده")
    elif presence["indexable"]:
        visibility_chip = _chip("ok", "فعال و آماده")
    else:
        visibility_chip = _chip("info", "منتظر آدرس عمومی")

    def _rows(codes):
        return [row for row in integration_rows if row["provider"].code in codes]

    analytics = [row for row in integration_rows if row["group"] == "live"]
    saved_analytics = [row for row in analytics if row["is_connected"]]
    if not saved_analytics:
        stats_chip = _chip("off", "شناسه‌ای ذخیره نشده")
    elif any(row["effect"]["state"] == "live" for row in saved_analytics):
        stats_chip = _chip("ok", "ردیابی فعال است")
    else:
        stats_chip = _chip("info", "شناسه ذخیره شد؛ ردیابی هنوز روشن نیست")
    sales_saved = [row for row in _rows(SALES_TOOL_PROVIDERS) if row["is_connected"]]
    trust_saved = [row for row in _rows(TRUST_PROVIDERS) if row["is_connected"]]
    return {
        "headline": presence["headline"],
        "next_action": action,
        "ready": not action,
        "infra_active": counters["active"] + counters["ready"],
        "infra_waiting": counters["waiting"],
        "all_rows": [row for row in integration_rows if row["provider"].code in _PROVIDER_VIEW],
        # services that need the seller (nothing saved yet / saved value invalid / saved but switched off)
        "attention": [row for row in integration_rows if row["guide"]["status"] in ("needs_customer", "error")],
        "sales_rows": _rows(SALES_TOOL_PROVIDERS),
        "trust_rows": _rows(TRUST_PROVIDERS),
        "analytics_rows": analytics,
        "duplicate_warning": duplicate_tracking_warning(analytics),
        "tracking_guidance": tracking_guidance(analytics),
        "chips": {
            "visibility": visibility_chip,
            "stats": stats_chip,
            "sales": _chip("info", "فقط شناسه ذخیره شده") if sales_saved else _chip("off", "شناسه‌ای ذخیره نشده"),
            "trust": _chip("info", "فقط شناسه ذخیره شده") if trust_saved else _chip("off", "شناسه‌ای ذخیره نشده"),
            "future": _chip("off", "به‌زودی"),
        },
        "not_available_count": len(NOT_AVAILABLE),
    }
