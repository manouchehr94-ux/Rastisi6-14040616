"""منطقِ سمتِ سرورِ رابطِ ساده‌ی ساختِ کمپین/مناسبت.

فروشنده فقط چند کارتِ ساده انتخاب می‌کند؛ این ماژول آن انتخاب‌ها را به همان
«درختِ قواعدِ» موتورِ فعلی (``rules.validate_tree``) و نامِ مناسبتِ پیام تبدیل
می‌کند. هیچ موتورِ موازی‌ای نیست: خروجی همیشه از ``validate_tree`` می‌گذرد."""

from __future__ import annotations

from apps.core.utils import format_toman, to_fa_digits
from apps.engagement.models import Campaign
from apps.engagement.services import rules

AUDIENCE_ALL, AUDIENCE_NEW, AUDIENCE_LOYAL, AUDIENCE_DORMANT, AUDIENCE_CUSTOM = "all", "new", "loyal", "dormant", "custom"
AUDIENCE_CHOICES = (AUDIENCE_ALL, AUDIENCE_NEW, AUDIENCE_LOYAL, AUDIENCE_DORMANT, AUDIENCE_CUSTOM)

NEW_CUSTOMER_DAYS = 30
LOYAL_MIN_ORDERS = 3
DORMANT_DAYS = 90

EXTRA_NONE, EXTRA_CITY, EXTRA_CATEGORY, EXTRA_TAG, EXTRA_SEGMENT = "", "city", "category", "tag", "segment"
EXTRA_CHOICES = (EXTRA_NONE, EXTRA_CITY, EXTRA_CATEGORY, EXTRA_TAG, EXTRA_SEGMENT)

_PRESET_LEAVES = {
    AUDIENCE_NEW: {"type": "registered", "mode": "within_days", "days": NEW_CUSTOMER_DAYS},
    AUDIENCE_LOYAL: {"type": "lifetime_orders", "op": "gte", "value": str(LOYAL_MIN_ORDERS)},
    AUDIENCE_DORMANT: {"type": "days_since_last_purchase", "op": "gte", "value": str(DORMANT_DAYS)},
}


class AudienceError(ValueError):
    """انتخابِ مخاطب نامعتبر است (پیام برایِ نمایش به مدیر مناسب است)."""


def _extra_leaf(kind: str, values: list) -> dict | None:
    if kind == EXTRA_NONE:
        return None
    if not values:
        raise AudienceError("برای «مخاطبِ خاص» حداقل یک مورد را انتخاب کنید.")
    if kind == EXTRA_CITY:
        return {"type": "customer_city", "values": [str(v) for v in values]}
    ids = [int(v) for v in values]
    if kind == EXTRA_CATEGORY:
        return {"type": "line_match", "category_ids": ids, "min_quantity": 1}
    if kind == EXTRA_TAG:
        return {"type": "customer_tag_ids", "ids": ids}
    if kind == EXTRA_SEGMENT:
        return {"type": "segment_ids", "ids": ids}
    raise AudienceError("نوعِ مخاطبِ خاص نامعتبر است.")


def build_audience_rules(kind: str, extra_kind: str, extra_values: list, store) -> dict:
    """انتخاب‌هایِ ساده → درختِ قواعدِ اعتبارسنجی‌شده (همیشه با ``store`` بررسی می‌شود)."""
    if kind not in AUDIENCE_CHOICES or kind == AUDIENCE_CUSTOM:
        raise AudienceError("مخاطب نامعتبر است.")
    try:
        children = []
        if kind != AUDIENCE_ALL:
            children.append(dict(_PRESET_LEAVES[kind]))
        extra = _extra_leaf(extra_kind, extra_values)
        if extra:
            children.append(extra)
        if not children:
            return {}
        tree = children[0] if len(children) == 1 else {"type": "group", "op": "and", "children": children}
        return rules.validate_tree(tree, store)
    except (rules.RuleError, ValueError) as exc:
        raise AudienceError(str(exc)) from exc


def detect_audience(tree, store) -> dict:
    """درختِ ذخیره‌شده → انتخاب‌هایِ ساده. اگر با هیچ ترکیبِ سادهٔ شناخته‌شده‌ای برابر نبود،
    ``custom`` برمی‌گردد (قواعدِ قبلی دست‌نخورده می‌ماند و از بین نمی‌رود)."""
    tree = tree or {}
    if not tree:
        return {"kind": AUDIENCE_ALL, "extra_kind": EXTRA_NONE, "extra_values": []}
    nodes = tree["children"] if tree.get("type") == "group" and tree.get("op") == "and" and not tree.get("negate") else [tree]
    if not (1 <= len(nodes) <= 2) or any(n.get("type") == "group" for n in nodes):
        return {"kind": AUDIENCE_CUSTOM, "extra_kind": EXTRA_NONE, "extra_values": []}
    kind, extra_kind, extra_values = AUDIENCE_ALL, EXTRA_NONE, []
    for node in nodes:
        matched_preset = next((k for k, leaf in _PRESET_LEAVES.items() if _same_leaf(node, leaf, store)), None)
        if matched_preset and kind == AUDIENCE_ALL:
            kind = matched_preset
        elif extra_kind == EXTRA_NONE and node.get("type") == "customer_city" and set(node) == {"type", "values"}:
            extra_kind, extra_values = EXTRA_CITY, list(node["values"])
        elif extra_kind == EXTRA_NONE and node.get("type") == "line_match" and set(node) == {"type", "category_ids", "min_quantity"} and node["min_quantity"] == 1:
            extra_kind, extra_values = EXTRA_CATEGORY, list(node["category_ids"])
        elif extra_kind == EXTRA_NONE and node.get("type") == "customer_tag_ids" and set(node) == {"type", "ids"}:
            extra_kind, extra_values = EXTRA_TAG, list(node["ids"])
        elif extra_kind == EXTRA_NONE and node.get("type") == "segment_ids" and set(node) == {"type", "ids"}:
            extra_kind, extra_values = EXTRA_SEGMENT, list(node["ids"])
        else:
            return {"kind": AUDIENCE_CUSTOM, "extra_kind": EXTRA_NONE, "extra_values": []}
    return {"kind": kind, "extra_kind": extra_kind, "extra_values": extra_values}


def _same_leaf(node: dict, preset: dict, store) -> bool:
    try:
        return rules.validate_tree(preset, store) == node
    except rules.RuleError:
        return False


# ----------------------------------------------------------------- نامِ مناسبت در پیام

#: «نامِ مناسبت» در پیام به‌صورتِ عبارتِ اسمی و داخلِ «» می‌آید؛ برایِ مناسبت‌هایِ دارایِ نامِ دلخواه
#: (روزِ ویژه/تاریخِ دلخواه) از نامِ همان پیشنهاد استفاده می‌شود.
_OCCASION_NOUNS = {
    Campaign.Occasion.BIRTHDAY: "تولد شما",
    Campaign.Occasion.REGISTRATION_ANNIVERSARY: "سالگرد عضویت شما",
    Campaign.Occasion.FIRST_PURCHASE_ANNIVERSARY: "سالگرد اولین خرید شما",
    Campaign.Occasion.REACTIVATION: "دیدار دوباره با شما",
}


def effective_occasion_name(campaign: Campaign) -> str:
    """نامی که جایگزینِ ``{occasion_name}`` می‌شود؛ نامِ ذخیره‌شده‌ی قبلی همیشه مقدم است."""
    if campaign.occasion_name:
        return campaign.occasion_name
    kind = campaign.occasion_kind
    params = campaign.occasion_params or {}
    if kind == Campaign.Occasion.ORDER_MILESTONE and params.get("n"):
        return f"خرید شماره {to_fa_digits(params['n'])} شما"
    if kind == Campaign.Occasion.SPENDING_MILESTONE and params.get("amount"):
        return f"رسیدن به مجموع خرید {format_toman(params['amount'], with_unit=False)} تومانی"
    return _OCCASION_NOUNS.get(kind) or campaign.name
