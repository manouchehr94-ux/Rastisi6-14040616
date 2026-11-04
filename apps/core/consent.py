"""Visitor consent for the storefront's analytics / advertising tags — the server half.

Policy (conservative, ONE policy; region variants need a legal review and are NOT invented here):

* **opt-in, nothing before a choice.** No tag of any provider is printed into the page. The page carries only a validated JSON config and ``consent.js``; the script loads a
  provider's tag *after* the visitor accepted the matching category, never before, never by default, never pre-ticked;
* categories: ``necessary`` (always on — RastiSi itself sets no tracking cookie, so there is nothing to ask), ``analytics`` (GA4, GTM), ``marketing`` (Meta pixel).
  GTM is classed with analytics for LOADING and receives the Consent Mode v2 signals, so tags inside the container only fire for what was granted;
* Google Consent Mode v2: the four signals ``ad_storage``, ``analytics_storage``, ``ad_user_data``, ``ad_personalization`` (+ functionality / personalization) default to
  ``denied`` before any Google tag exists, and are updated from the visitor's choice (``security_storage`` is the only one granted by default: it protects the visitor);
* no double counting: when a GTM container is active the direct GA4 tag is NOT loaded (GTM is the one loader; the GA4 tag, if wanted, lives inside the container);
* the choice is a first-party cookie (``rs_consent``: version, analytics, marketing, time) the visitor can reopen and change at any time; a policy-version bump asks again;
  the global privacy control signal (``navigator.globalPrivacyControl``) keeps marketing denied.

Nothing here decides whether tracking is ON: that remains ``RASTISI_STOREFRONT_TRACKING_ENABLED`` (default OFF) + a live public store (``tracking_service``). When there are no
tracker ids, no config, no banner and no script are rendered at all."""

from __future__ import annotations

from django.conf import settings

COOKIE_NAME = "rs_consent"
COOKIE_MAX_AGE = 180 * 24 * 3600

CATEGORIES = (
    ("necessary", "ضروری", "برای کارکرد فروشگاه لازم است و ردیابی نیست؛ همیشه فعال است.", True),
    ("analytics", "آمار بازدید", "به فروشگاه کمک می‌کند بفهمد کدام صفحه‌ها دیده می‌شوند (Google Analytics / Google Tag Manager).", False),
    ("marketing", "تبلیغات", "برای سنجش و بهینه‌سازی تبلیغات (پیکسل Meta).", False),
)
TEXTS = {
    "title": "حریم خصوصی شما",
    "body": "این فروشگاه برای سنجش بازدید و تبلیغات، در صورت موافقت شما، ابزارهای ردیابی بارگذاری می‌کند. تا انتخاب شما هیچ ابزار ردیابی‌ای فعال نیست. هر زمان می‌توانید انتخابتان را عوض کنید.",
    "accept_all": "پذیرش همه",
    "reject_all": "رد همه",
    "customize": "انتخاب دسته‌ها",
    "save": "ذخیره انتخاب",
    "reopen": "تنظیمات حریم خصوصی",
    "gpc": "سیگنال «عدم فروش/اشتراک اطلاعات» مرورگر شما دیده شد؛ دستهٔ تبلیغات خاموش می‌ماند.",
}
CONSENT_SIGNALS = {
    "analytics": ("analytics_storage",),
    "marketing": ("ad_storage", "ad_user_data", "ad_personalization"),
}
#: signals that default to denied (a signal is granted by default only if it protects the visitor)
DEFAULT_DENIED = ("ad_storage", "analytics_storage", "ad_user_data", "ad_personalization", "functionality_storage", "personalization_storage")
DEFAULT_GRANTED = ("security_storage",)


def policy_version() -> int:
    try:
        return max(1, int(getattr(settings, "RASTISI_CONSENT_POLICY_VERSION", 1)))
    except (TypeError, ValueError):
        return 1


def server_decision(request) -> dict:
    """The visitor's CURRENT choice as the server can verify it on this request: the first-party ``rs_consent`` cookie (current policy
    version, ``a``/``m`` flags) and the ``Sec-GPC`` header (GPC overrides a stored marketing grant). Missing / unreadable / stale → both False."""
    import json
    from urllib.parse import unquote

    analytics = marketing = False
    raw = request.COOKIES.get(COOKIE_NAME)
    if raw:
        try:
            data = json.loads(unquote(raw))
            if isinstance(data, dict) and data.get("v") == policy_version() and data.get("a") in (0, 1) and data.get("m") in (0, 1):
                analytics, marketing = bool(data["a"]), bool(data["m"])
        except (ValueError, TypeError):
            pass
    if str(request.META.get("HTTP_SEC_GPC", "")).strip() == "1":
        marketing = False
    return {"analytics": analytics, "marketing": marketing}


def would_dispatch(tracking_ids: dict, decision: dict) -> bool:
    """True when consent.js would actually dispatch to at least one loaded tag under this decision (same ``needs`` rules as the browser)."""
    config = build_config(tracking_ids)
    if not config:
        return False
    for item in config.get("load", []):
        needs = item.get("needs")
        ok = decision["analytics"] if needs == "analytics" else decision["marketing"] if needs == "marketing" else (decision["analytics"] or decision["marketing"])
        if ok:
            return True
    return False


def build_config(tracking_ids: dict) -> dict | None:
    """The JSON-safe config for the page, or ``None`` when there is nothing to ask about (no tracker → no banner). Only validated ids are passed in."""
    ids = {k: v for k, v in (tracking_ids or {}).items() if k in ("ga4", "gtm", "meta_pixel") and v}
    if not ids:
        return None
    load = []
    if "gtm" in ids:
        load.append({"tracker": "gtm", "needs": "analytics_or_marketing"})
    elif "ga4" in ids:
        load.append({"tracker": "ga4", "needs": "analytics"})
    if "meta_pixel" in ids:
        load.append({"tracker": "meta_pixel", "needs": "marketing"})
    return {
        "policy": "opt_in",
        "version": policy_version(),
        "cookie": COOKIE_NAME,
        "max_age": COOKIE_MAX_AGE,
        "ids": ids,
        "load": load,
        "ga4_via_gtm": "gtm" in ids and "ga4" in ids,
        "categories": [{"key": k, "label": label, "desc": desc, "required": required} for k, label, desc, required in CATEGORIES],
        "signals": {"analytics": list(CONSENT_SIGNALS["analytics"]), "marketing": list(CONSENT_SIGNALS["marketing"]),
                    "default_denied": list(DEFAULT_DENIED), "default_granted": list(DEFAULT_GRANTED)},
        "texts": TEXTS,
    }
