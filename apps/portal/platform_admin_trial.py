"""Platform Admin → «دوره‌ی آزمایشی»: the policy (enabled / default days), the internal Trial plan's limits and features, and the usage history.

Everything goes through the official engines (``trial_service``, ``plan_service``, ``platform_config_service``): validation, immutable plan versions,
platform audit entries. The page is superuser-only like the rest of Platform Admin. Nothing here changes a running trial's end date."""

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.subscriptions import capability_registry
from apps.subscriptions.models import EntitlementDefinition, PlanEntitlement, StoreSubscription
from apps.subscriptions.services import plan_service, trial_service

from .platform_admin_views import _is_platform_staff
from .services.platform_config_service import (
    PlatformConfigurationError,
    get_platform_configuration,
    record_platform_audit_event,
    update_platform_configuration,
)

_LOGIN = "portal_platform_admin:login"
_E = EntitlementDefinition.EntitlementType


def _editable_definitions():
    """Active entitlement definitions whose key the code really enforces (the registry is the single authority; planned features live in the matrix)."""
    keys = capability_registry.registered_keys()
    return [d for d in EntitlementDefinition.objects.filter(is_active=True).order_by("key") if d.key in keys]


def _limit_rows(version):
    current = {pe.entitlement_id: pe for pe in version.plan_entitlements.all()} if version else {}
    rows = []
    for definition in _editable_definitions():
        pe = current.get(definition.pk)
        rows.append({
            "key": definition.key, "name": definition.name, "numeric": definition.entitlement_type == _E.INTEGER_LIMIT,
            "boolean": definition.entitlement_type == _E.BOOLEAN,
            "enabled": pe.is_enabled if pe is not None else definition.default_enabled,
            "unlimited": bool(pe and pe.is_unlimited), "limit": pe.integer_limit if pe is not None else None,
            "defined": pe is not None,
        })
    return [r for r in rows if r["numeric"] or r["boolean"]]


def _parse_limit_form(post):
    """``{key: values}`` from the posted limits form; invalid numbers raise ``TrialPolicyError`` (nothing is saved)."""
    out = {}
    for definition in _editable_definitions():
        key = definition.key
        if definition.entitlement_type == _E.BOOLEAN:
            out[key] = {"is_enabled": post.get(f"ent_{key}_enabled") == "on"}
        elif definition.entitlement_type == _E.INTEGER_LIMIT:
            enabled = post.get(f"ent_{key}_enabled") == "on"
            unlimited = post.get(f"ent_{key}_unlimited") == "on"
            raw = (post.get(f"ent_{key}_limit") or "").strip()
            if unlimited:
                out[key] = {"is_enabled": enabled, "is_unlimited": True, "integer_limit": None}
                continue
            try:
                limit = int(raw)
            except ValueError:
                raise trial_service.TrialPolicyError(f"سقفِ «{definition.name}» باید یک عددِ صحیح باشد.") from None
            if limit < 0:
                raise trial_service.TrialPolicyError(f"سقفِ «{definition.name}» نمی‌تواند منفی باشد.")
            out[key] = {"is_enabled": enabled, "is_unlimited": False, "integer_limit": limit}
    return out


def _snapshot(version):
    if version is None:
        return {}
    return {pe.entitlement.key: (pe.is_enabled, pe.is_unlimited, pe.integer_limit)
            for pe in version.plan_entitlements.select_related("entitlement")}


def _apply_limits(plan, values, grace_days, *, actor):
    """Create a new immutable version only if something changed; returns ``(old_version, new_version or None)``."""
    old = trial_service.trial_plan_version()
    before = _snapshot(old)
    wanted = {k: (v.get("is_enabled", True), v.get("is_unlimited", False), v.get("integer_limit")) for k, v in values.items()}
    unchanged = (old is not None and old.grace_period_days == grace_days
                 and all(before.get(k) == w for k, w in wanted.items()))
    if unchanged:
        return old, None
    draft = plan_service.get_or_create_draft(plan, actor=actor)
    plan_service.update_draft_version(draft, actor=actor, grace_period_days=grace_days, trial_days=trial_service.current_policy().days)
    for key, vals in values.items():
        plan_service.set_plan_entitlement(draft, key, **vals)
    published = plan_service.publish_plan_version(draft, actor=actor)
    return old, published


def _history_rows(queryset):
    now = timezone.now()
    for sub in queryset:
        plan = sub.plan_version.plan
        converted = plan.code != trial_service.TRIAL_PLAN_CODE
        if converted:
            state, tone = "تبدیل‌شده به اشتراکِ پولی", "pa-ok"
        elif sub.status == StoreSubscription.Status.TRIALING:
            state, tone = "در جریان", "pa-info"
        else:
            state, tone = "پایان‌یافته", "pa-off"
        sub.history_state, sub.history_tone = state, tone
        sub.days_left = max(0, (sub.trial_end_at - now).days) if sub.status == StoreSubscription.Status.TRIALING and sub.trial_end_at else None
    return queryset


@user_passes_test(_is_platform_staff, login_url=_LOGIN)
def trial_settings(request):
    plan = trial_service.ensure_trial_plan(actor=request.user)           # idempotent; also enforces «internal, not purchasable»
    version = trial_service.trial_plan_version()
    config = get_platform_configuration()

    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "policy":
                days = trial_service.validate_days(request.POST.get("default_trial_days"))
                enabled = request.POST.get("trial_enabled") == "on"
                if enabled != config.trial_enabled or days != config.default_trial_days:
                    update_platform_configuration(actor=request.user, default_trial_days=days, trial_enabled=enabled)
                    messages.success(request, "سیاستِ دوره‌ی آزمایشی ذخیره شد. فقط فروشگاه‌هایِ تازه از این پس اثر می‌پذیرند؛ Trialهای در جریان تغییر نکردند.")
                else:
                    messages.info(request, "تغییری برایِ ذخیره وجود نداشت.")
            elif action == "limits":
                values = _parse_limit_form(request.POST)
                grace = request.POST.get("grace_period_days", "0")
                try:
                    grace_days = int(grace)
                except ValueError:
                    raise trial_service.TrialPolicyError("مهلتِ ارفاقی باید عددِ صحیح باشد.") from None
                if not (0 <= grace_days <= 60):
                    raise trial_service.TrialPolicyError("مهلتِ ارفاقی باید بین ۰ تا ۶۰ روز باشد.")
                apply_to_active = request.POST.get("apply_to_active") == "on"
                reason = (request.POST.get("reason") or "").strip()
                if apply_to_active and not reason:
                    raise trial_service.TrialPolicyError("برایِ اعمال روی Trialهای در جریان، ثبتِ دلیل الزامی است.")
                with transaction.atomic():
                    old, new = _apply_limits(plan, values, grace_days, actor=request.user)
                    if new is None:
                        messages.info(request, "تغییری در سقف‌ها و امکانات نبود.")
                    else:
                        record_platform_audit_event(
                            actor=request.user, action_code="platform_admin.trial_limits_updated", object_type="Plan", object_id=plan.pk,
                            object_label=plan.name, before=_snapshot(old), after=_snapshot(new),
                            metadata={"from_version": old.version_number if old else None, "to_version": new.version_number, "grace_days": grace_days},
                        )
                        moved = 0
                        if apply_to_active and old is not None:
                            moved = plan_service.migrate_subscribers(old, new, actor=request.user, reason=reason, accept_losses=True)
                        messages.success(request, f"نسخه‌ی {new.version_number} پلنِ آزمایشی منتشر شد."
                                                  + (f" روی {moved} Trialِ در جریان هم اعمال شد." if apply_to_active else
                                                     " Trialهای در جریان روی نسخه‌ی قبلیِ خود می‌مانند."))
            else:
                messages.error(request, "درخواست نامعتبر.")
        except (trial_service.TrialPolicyError, PlatformConfigurationError, plan_service.PlanServiceError) as exc:
            messages.error(request, str(exc))
        return redirect("portal_platform_admin:trial-settings")

    base = StoreSubscription.objects.filter(trial_start_at__isnull=False)
    now = timezone.now()
    stats = {
        "total": base.count(),
        "running": base.filter(status=StoreSubscription.Status.TRIALING, trial_end_at__gt=now).count(),
        "converted": base.exclude(plan_version__plan__code=trial_service.TRIAL_PLAN_CODE).count(),
        "ended": base.filter(plan_version__plan__code=trial_service.TRIAL_PLAN_CODE).exclude(status=StoreSubscription.Status.TRIALING).count(),
    }
    history = Paginator(
        base.select_related("store", "plan_version__plan").order_by("-trial_start_at", "-pk"), 25,
    ).get_page(request.GET.get("page"))
    _history_rows(history.object_list)
    active_on_old = (StoreSubscription.objects.filter(plan_version__plan=plan, is_current=True)
                     .exclude(plan_version=version).count() if version else 0)
    return render(request, "portal/platform_admin/trial_settings.html", {
        "plan": plan, "version": version, "config": config, "limit_rows": _limit_rows(version), "stats": stats, "page": history,
        "active_on_old_version": active_on_old, "active_nav": "trial-settings",
    })
