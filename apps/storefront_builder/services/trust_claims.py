"""FOLLOWUP-10 — «ردیف اعتماد و ویژگی‌ها» نباید در صفحهٔ عمومی وعده‌ای بدهد که وضعیتِ واقعیِ فروشگاه تأییدش نمی‌کند.

* ادعای عملیاتی (``payment`` / ``shipping`` / ``pickup``) فقط وقتی عمومی نمایش داده می‌شود که همان قابلیت *همین الان* در
  فروشگاه فعال باشد (همان منابعی که checkout استفاده می‌کند: درگاه فعال، روش ارسال فعال، روش «تحویل حضوری» فعال).
* بقیهٔ ادعاها (ضمانت اصالت، بهترین قیمت، …) فقط با تأییدِ صریحِ فروشنده (``verified``) عمومی می‌شوند.
* در Studio (پیش‌نمایش) همهٔ آیتم‌ها با برچسبِ علتِ پنهان‌بودن دیده می‌شوند؛ هیچ داده‌ای حذف یا بازنویسی نمی‌شود.
* ادعای قدیمی بدونِ فیلد ``claim`` از روی عنوان حدس زده می‌شود (فقط برایِ سه مفهومِ عملیاتیِ بالا)."""

from __future__ import annotations

CLAIM_PAYMENT, CLAIM_SHIPPING, CLAIM_PICKUP = "payment", "shipping", "pickup"
OPERATIONAL_CLAIMS = (CLAIM_PAYMENT, CLAIM_SHIPPING, CLAIM_PICKUP)
CLAIM_CHOICES = (
    ("", "خودکار از روی عنوان / متن آزاد"),
    (CLAIM_PAYMENT, "پرداخت (نیازمند درگاه فعال)"),
    (CLAIM_SHIPPING, "ارسال (نیازمند روش ارسال فعال)"),
    (CLAIM_PICKUP, "تحویل حضوری (نیازمند روش تحویل حضوری فعال)"),
)
_CLAIM_LABELS_FA = {
    CLAIM_PAYMENT: "درگاه پرداخت فعالی وجود ندارد",
    CLAIM_SHIPPING: "روش ارسال فعالی وجود ندارد",
    CLAIM_PICKUP: "روش «تحویل حضوری» فعالی وجود ندارد",
}
#: آیتم‌های پیش‌فرضِ قدیمیِ قالب وقتی هیچ آیتمی ذخیره نشده (همان چهار وعدهٔ قبلی)، حالا با ادعای صریح.
LEGACY_DEFAULT_ITEMS = (
    {"icon": "🚚", "title": "ارسال سریع", "subtitle": "به سراسر کشور", "claim": CLAIM_SHIPPING, "verified": False},
    {"icon": "🛡", "title": "ضمانت اصالت", "subtitle": "کالای اورجینال", "claim": "", "verified": False},
    {"icon": "💬", "title": "پشتیبانی ۲۴/۷", "subtitle": "پاسخگویی همه‌روزه", "claim": "", "verified": False},
    {"icon": "🏠", "title": "۷ روز ضمانت بازگشت", "subtitle": "بدون دردسر", "claim": "", "verified": False},
)


def infer_claim(item: dict) -> str:
    claim = (item.get("claim") or "").strip()
    if claim in OPERATIONAL_CLAIMS:
        return claim
    title = str(item.get("title") or "")
    if "تحویل حضوری" in title or "دریافت حضوری" in title or "تحویل در محل" in title:
        return CLAIM_PICKUP
    if "پرداخت" in title:
        return CLAIM_PAYMENT
    if "ارسال" in title:
        return CLAIM_SHIPPING
    return ""


def store_service_state(store) -> dict:
    """وضعیتِ واقعیِ قابلیت‌ها — فقط خواندن، store-scoped."""
    from apps.orders.models import PaymentGateway, ShippingMethod

    methods = ShippingMethod.objects.filter(store=store, is_active=True)
    return {
        CLAIM_PAYMENT: PaymentGateway.objects.filter(store=store, is_active=True).exists(),
        CLAIM_SHIPPING: methods.exists(),
        CLAIM_PICKUP: methods.filter(method_type=ShippingMethod.MethodType.LOCAL_PICKUP).exists(),
    }


def resolve_items(store, settings: dict) -> list[dict]:
    """هر آیتم را با ``claim``، ``public_visible`` و ``hidden_reason`` برمی‌گرداند (ترتیب حفظ می‌شود)."""
    raw_items = (settings or {}).get("items") or [dict(i) for i in LEGACY_DEFAULT_ITEMS]
    state = store_service_state(store)
    resolved = []
    for raw in raw_items:
        claim = infer_claim(raw)
        verified = bool(raw.get("verified"))
        if claim:
            visible = bool(state.get(claim))
            reason = "" if visible else _CLAIM_LABELS_FA[claim]
        else:
            visible = verified
            reason = "" if visible else "این ادعا هنوز توسط فروشنده تأیید نشده است"
        resolved.append({
            "icon": raw.get("icon") or "", "title": raw.get("title") or "", "subtitle": raw.get("subtitle") or "",
            "claim": claim, "verified": verified, "public_visible": visible, "hidden_reason": reason,
        })
    return resolved
