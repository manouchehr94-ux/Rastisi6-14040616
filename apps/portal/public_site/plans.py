"""Public plan cards: always from the real, published Plan/PlanVersion records."""

from apps.core.utils import to_fa_digits
from apps.subscriptions.models import Plan, PlanVersion

MAX_FEATURES = 8


def _features(version) -> list:
    rows = []
    for pe in version.plan_entitlements.select_related("entitlement").order_by("entitlement__key"):
        ent = pe.entitlement
        if not ent.is_active or not pe.is_enabled:
            continue
        kind = ent.entitlement_type
        if kind == ent.EntitlementType.BOOLEAN:
            rows.append(ent.name)
        elif pe.is_unlimited:
            rows.append(f"{ent.name}: نامحدود")
        elif kind == ent.EntitlementType.INTEGER_LIMIT and pe.integer_limit is not None:
            rows.append(f"{ent.name}: {to_fa_digits(pe.integer_limit)}")
        elif kind == ent.EntitlementType.DECIMAL_LIMIT and pe.decimal_limit is not None:
            rows.append(f"{ent.name}: {to_fa_digits(pe.decimal_limit.normalize())}")
        elif kind == ent.EntitlementType.TEXT_VALUE and pe.text_value:
            rows.append(f"{ent.name}: {pe.text_value}")
    return rows[:MAX_FEATURES]


def public_plan_rows() -> list:
    rows = []
    plans = Plan.objects.filter(is_active=True, is_publicly_selectable=True).order_by("display_order", "code")
    for plan in plans:
        version = plan.versions.filter(status=PlanVersion.Status.PUBLISHED).order_by("-version_number").first()
        if version is not None:
            rows.append({"plan": plan, "version": version, "features": _features(version)})
    return rows
