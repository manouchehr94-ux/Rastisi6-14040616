"""دادهٔ صفحهٔ عمومیِ تعرفه — *فقط* از منبعِ حقیقتِ واقعی ساخته می‌شود:

* پلن‌ها/نسخه‌هایِ منتشرشده + قیمت‌هایِ دوره‌ای (``PlanVersion.price_options``)،
* مقدارِ هر ردیفِ ماتریس از ``PlanEntitlement`` همان نسخه از طریقِ همان توابعِ ``entitlement_service`` که محصول با آن‌ها
  دسترسی را اعمال می‌کند (نه یک کپیِ جدا)،
* ردیف‌ها از کاتالوگِ کانونی (``feature_catalog``) — قابلیتِ ``planned`` هرگز عمومی نمی‌شود.

هیچ عددِ فرضی ساخته نمی‌شود: کمبودِ داده یعنی «—» یا نبودِ ردیف، نه یک پیش‌فرضِ زیبا."""

import json

from apps.core.utils import to_fa_digits
from apps.subscriptions import feature_catalog as catalog
from apps.subscriptions.models import (
    EntitlementDefinition,
    OptionalService,
    Plan,
    PlanFaq,
    PlanOptionalService,
    PlanVersion,
    PricingFeature,
)
from apps.subscriptions.services import entitlement_service as ent

INTERVAL_LABELS = dict(PlanVersion.BillingInterval.choices)
INTERVAL_SHORT = {"monthly": "ماه", "quarterly": "سه ماه", "semiannual": "شش ماه", "yearly": "سال"}
CATEGORY_ORDER = [c for c, _ in PricingFeature.Category.choices]
MAX_HIGHLIGHTS = 4


def offered_plans():
    """(plan, published_version) برایِ پلن‌هایِ فعال و قابلِ‌انتخابِ عمومی که نسخه‌ی منتشرشده دارند، به ترتیبِ نمایش."""
    rows = []
    for plan in Plan.objects.filter(is_active=True, is_publicly_selectable=True).order_by("display_order", "code"):
        version = plan.versions.filter(status=PlanVersion.Status.PUBLISHED).order_by("-version_number").first()
        if version is not None:
            rows.append((plan, version))
    return rows


def resolve_selection(code, interval=""):
    """انتخابِ عمومی (کدِ پلن + دوره) را فقط وقتی برمی‌گرداند که همین الان واقعاً قابلِ‌عرضه باشد:
    ``(plan_version, interval)`` یا ``None``. ورودیِ کاربر هرگز مستقیم اعتماد نمی‌شود."""
    code = (code or "").strip()[:50]
    for plan, version in offered_plans():
        if plan.code != code:
            continue
        interval = (interval or "").strip()
        if interval and not version.offers_interval(interval):
            return None
        return version, (interval or version.billing_interval)
    return None


def _savings_percent(version, interval, price):
    """درصدِ صرفه‌جویی نسبت به ماهانه‌ی همان نسخه (فقط اگر ماهانه عرضه شود و واقعاً ارزان‌تر باشد)."""
    months = PlanVersion.INTERVAL_MONTHS.get(interval)
    monthly = version.price_options().get("monthly")
    if not months or months == 1 or not monthly or not monthly["price"]:
        return 0
    full = monthly["price"] * months
    if full <= 0 or price >= full:
        return 0
    return int(((full - price) / full * 100).to_integral_value())


def _period_options(version):
    out = []
    options = version.price_options()
    for interval in PlanVersion.PAID_INTERVALS:
        opt = options.get(interval)
        if opt is None:
            continue
        price = opt["price"]
        compare = opt["compare_at"]
        discount = int(((compare - price) / compare * 100).to_integral_value()) if compare and compare > price else 0
        out.append({
            "interval": interval, "label": INTERVAL_LABELS[interval], "short": INTERVAL_SHORT[interval],
            "price": price, "compare_at": compare if discount else None, "discount_percent": discount,
            "savings_percent": _savings_percent(version, interval, price), "custom_label": opt["label"],
            "monthly_equivalent": version.monthly_equivalent(interval),
        })
    return out


def _cell(feature, version):
    """مقدارِ یک ردیف برایِ یک نسخه: ``{"kind": check|none|unlimited|value|all, "text": str}``."""
    spec = catalog.BY_KEY.get(feature.key)
    key = spec.entitlement if spec else ""
    if not key:
        return {"kind": "all", "text": "همه‌ی پلن‌ها"}
    definition = EntitlementDefinition.objects.filter(key=key).first()
    if definition is None:
        return {"kind": "none", "text": "—"}
    if definition.entitlement_type == EntitlementDefinition.EntitlementType.BOOLEAN:
        on = ent.has_entitlement(None, key, plan_version=version)
        return {"kind": "check", "text": "✓"} if on else {"kind": "none", "text": "—"}
    if not ent.has_entitlement(None, key, plan_version=version):
        return {"kind": "none", "text": "—"}
    limit = ent.get_entitlement_limit(None, key, plan_version=version)
    if limit is None:
        return {"kind": "unlimited", "text": "نامحدود"}
    if limit == 0:
        return {"kind": "none", "text": "—"}
    unit = f" {feature.unit_label}" if feature.unit_label else ""
    return {"kind": "value", "text": f"{to_fa_digits(limit)}{unit}"}


def _matrix(plan_versions):
    features = [
        f for f in PricingFeature.objects.filter(is_visible=True).order_by("category", "display_order", "key")
        if f.is_publishable
    ]
    by_cat = {}
    for f in features:
        by_cat.setdefault(f.category, []).append(f)
    out = []
    labels = dict(PricingFeature.Category.choices)
    for cat in CATEGORY_ORDER:
        rows = []
        for f in by_cat.get(cat, []):
            rows.append({
                "feature": f, "title": f.title, "description": f.description, "note": f.note,
                "availability": f.availability, "availability_label": f.get_availability_display(),
                "cells": [_cell(f, v) for _plan, v in plan_versions],
            })
        if rows:
            out.append({"key": cat, "label": labels[cat], "rows": rows})
    return out


def _services(plans):
    services = list(OptionalService.objects.filter(is_active=True).order_by("display_order", "code"))
    if not services:
        return []
    modes = {(m.plan_id, m.service_id): m.mode for m in PlanOptionalService.objects.filter(plan__in=[p for p, _v in plans])}
    rows = []
    for service in services:
        cells = []
        for plan, _v in plans:
            mode = modes.get((plan.pk, service.pk), PlanOptionalService.Mode.UNAVAILABLE)
            text = {"included": "همراهِ پلن", "paid": "با هزینه‌ی جدا", "unavailable": "—"}[mode]
            cells.append({"kind": "check" if mode == "included" else ("paid" if mode == "paid" else "none"), "text": text})
        rows.append({"service": service, "cells": cells})
    return rows


def _highlights(plan_versions):
    """چند سقفِ عددیِ مهم برایِ کارتِ هر پلن — فقط از مقادیرِ واقعیِ نسخه."""
    wanted = ["products", "staff", "warehouses", "segments"]
    feats = {f.key: f for f in PricingFeature.objects.filter(key__in=wanted)}
    result = []
    for _plan, version in plan_versions:
        items = []
        for key in wanted:
            f = feats.get(key)
            if f is None or not f.is_visible:
                continue
            cell = _cell(f, version)
            if cell["kind"] in ("value", "unlimited"):
                items.append({"title": f.title, "text": cell["text"]})
        result.append(items[:MAX_HIGHLIGHTS])
    return result


def build_pricing_page() -> dict:
    """ساختارِ کاملِ صفحه: کارت‌ها، دوره‌ها، ماتریس، خدماتِ اختیاری و FAQ."""
    plan_versions = offered_plans()
    highlights = _highlights(plan_versions)
    cards = []
    for index, (plan, version) in enumerate(plan_versions):
        periods = _period_options(version)
        free = version.billing_interval == PlanVersion.BillingInterval.NONE and not periods
        default = next((p for p in periods if p["interval"] == version.billing_interval), periods[0] if periods else None)
        cards.append({
            "plan": plan, "version": version, "title": plan.public_title or plan.name, "tagline": plan.tagline,
            "description": plan.description, "is_recommended": plan.is_recommended,
            "badge": plan.badge_text or "پیشنهادی", "cta_label": plan.cta_label, "periods": periods,
            "default_interval": default["interval"] if default else "", "is_free": free,
            "trial_days": version.trial_days, "highlights": highlights[index],
            "purchasable": bool(periods) and any(p["price"] > 0 for p in periods),
            "offered": [p["interval"] for p in periods],
            "offered_json": json.dumps([p["interval"] for p in periods]),
            "default_label": default["label"] if default else "",
            "initial_interval": "",     # پس از محاسبه‌ی دوره‌ی پیش‌فرضِ صفحه پر می‌شود
        })
    available = []
    for interval in PlanVersion.PAID_INTERVALS:
        if any(any(p["interval"] == interval for p in c["periods"]) for c in cards):
            savings = [p["savings_percent"] or p["discount_percent"] for c in cards for p in c["periods"] if p["interval"] == interval]
            available.append({"interval": interval, "label": INTERVAL_LABELS[interval], "max_saving": max(savings or [0])})
    default_interval = "monthly" if any(a["interval"] == "monthly" for a in available) else (available[0]["interval"] if available else "")
    faqs = list(PlanFaq.objects.filter(is_published=True, plan__isnull=True).order_by("display_order", "id"))
    plan_faqs = list(PlanFaq.objects.filter(is_published=True, plan__in=[p for p, _v in plan_versions]).select_related("plan").order_by("display_order", "id"))
    for c in cards:
        c["initial_interval"] = default_interval if default_interval in c["offered"] else c["default_interval"]
    recommended = [c["is_recommended"] for c in cards]
    matrix = _matrix(plan_versions)
    for cat in matrix:
        for row in cat["rows"]:
            for cell, rec in zip(row["cells"], recommended):
                cell["rec"] = rec
    return {
        "cards": cards, "intervals": available, "default_interval": default_interval,
        "recommended_index": next((i for i, r in enumerate(recommended) if r), 0),
        "matrix": matrix, "services": _services(plan_versions), "faqs": faqs, "plan_faqs": plan_faqs,
    }


# ---------------------------------------------------------------- گزارشِ شکاف (مدیر)

def gap_report() -> list:
    """وضعیتِ هر ردیفِ کاتالوگ برایِ ممیزیِ مدیر: چه چیزی کنترل‌پذیر، همراهِ همه‌ی پلن‌ها یا پیاده‌نشده است."""
    rows = []
    for f in catalog.CATALOG:
        if f.availability == catalog.PLANNED:
            control = "پیاده نشده"
        elif f.entitlement:
            control = "قابلِ کنترل در پلن (اعمال می‌شود)"
        else:
            control = "همراهِ همه‌ی پلن‌ها"
        rows.append({"key": f.key, "category": f.category, "title": f.title, "availability": f.availability,
                     "control": control, "evidence": f.evidence, "note": f.note})
    return rows
