"""Initial Trial policy — one place for «who gets a Trial, for how long, under which limits».

* The Trial is an **internal plan** (``Plan.code == "trial"``, never publicly selectable, never purchasable) run through the official
  Plan/PlanVersion/Entitlement engine: limits, features and grace are ordinary ``PlanEntitlement`` rows of its published version.
* **Duration** is read from ``PlatformConfiguration.default_trial_days`` *at the moment a store is provisioned* (straight from the database — it is an
  enforcement decision, not a display value) and frozen into that store's ``trial_end_at``. Changing the default therefore only affects stores created
  afterwards; running trials keep their own end date unless the platform owner explicitly extends them (``subscription_service.extend_trial``).
* **Once per store**: a store is eligible only if it has *never* had a subscription with ``trial_start_at`` set (any plan — a paid plan or a different
  trial version cannot hand out a second one). The store row is locked while deciding so concurrent provisioning cannot grant two.
* The Trial is independent of paid periods: paying converts the subscription (the unused trial days are not added to the paid period).
"""

from dataclasses import dataclass

from django.db import transaction

from apps.core.services.audit_service import record_audit_event
from apps.portal.models import PlatformConfiguration
from apps.subscriptions import entitlements as ekeys
from apps.subscriptions.models import Plan, PlanVersion, StoreSubscription
from apps.subscriptions.services import plan_service
from apps.subscriptions.services import subscription_service as sub_svc

TRIAL_PLAN_CODE = "trial"
MIN_TRIAL_DAYS = 1
MAX_TRIAL_DAYS = 365
DEFAULT_TRIAL_DAYS = 30

DOMAINS_CUSTOM = "domains.custom"
REPORTS_ADVANCED = "reports.advanced"

#: Defaults for a freshly created Trial version: (is_unlimited, limit) for numeric keys, bool for features. Only used when the Trial plan does not yet
#: exist — the platform owner edits the real values on the Trial page afterwards.
DEFAULT_TRIAL_LIMITS = {
    ekeys.CATALOG_PRODUCTS: (False, 20),
    ekeys.CATALOG_VARIANTS: (False, 60),
    ekeys.STAFF_MEMBERS: (False, 1),
    ekeys.INVENTORY_WAREHOUSES: (False, 1),
    ekeys.CUSTOMERS_SEGMENTS: (False, 1),
    ekeys.CATALOG_IMPORT_ROWS_MONTHLY: (False, 100),
    ekeys.CATALOG_EXPORTS_MONTHLY: (False, 5),
    DOMAINS_CUSTOM: False,
    REPORTS_ADVANCED: False,
    ekeys.CATALOG_IMPORT: False,
    ekeys.CATALOG_EXPORT: False,
}


class TrialPolicyError(Exception):
    """Invalid Trial setting (shown to the platform owner)."""


@dataclass(frozen=True)
class TrialPolicy:
    enabled: bool
    days: int


def current_policy() -> TrialPolicy:
    """Policy straight from the DB (never from the 5-minute configuration cache)."""
    row = PlatformConfiguration.objects.filter(pk=1).values("trial_enabled", "default_trial_days").first()
    if row is None:
        return TrialPolicy(enabled=True, days=DEFAULT_TRIAL_DAYS)
    return TrialPolicy(enabled=bool(row["trial_enabled"]), days=int(row["default_trial_days"]))


def validate_days(value) -> int:
    try:
        days = int(value)
    except (TypeError, ValueError):
        raise TrialPolicyError("مدتِ دوره‌ی آزمایشی باید یک عددِ صحیح باشد.") from None
    if not (MIN_TRIAL_DAYS <= days <= MAX_TRIAL_DAYS):
        raise TrialPolicyError(f"مدتِ دوره‌ی آزمایشی باید بین {MIN_TRIAL_DAYS} تا {MAX_TRIAL_DAYS} روز باشد.")
    return days


# ------------------------------------------------------------------------------------------------------------- the internal plan

def is_trial_plan(plan) -> bool:
    return plan is not None and plan.code == TRIAL_PLAN_CODE


@transaction.atomic
def ensure_trial_plan(*, actor=None) -> Plan:
    """The internal Trial plan with a published version, idempotent. An existing plan keeps its versions and limits; only its visibility is enforced
    (internal: not publicly selectable, active). A missing plan/version is created with ``DEFAULT_TRIAL_LIMITS``."""
    plan, created = Plan.objects.select_for_update().get_or_create(
        code=TRIAL_PLAN_CODE,
        defaults={"name": "آزمایشی", "public_title": "دوره‌ی آزمایشی", "description": "پلنِ داخلیِ دوره‌ی آزمایشیِ فروشگاه‌هایِ تازه (قابلِ خرید نیست).",
                  "is_active": True, "is_publicly_selectable": False, "display_order": 0},
    )
    changed = []
    if plan.is_publicly_selectable:
        plan.is_publicly_selectable = False
        changed.append("is_publicly_selectable")
    if not plan.is_active:
        plan.is_active = True
        changed.append("is_active")
    if changed:
        plan.save(update_fields=changed + ["updated_at"])
    if not plan.versions.filter(status=PlanVersion.Status.PUBLISHED).exists():
        from apps.subscriptions.entitlements import sync_entitlement_definitions

        sync_entitlement_definitions()
        version = plan_service.create_plan_version(
            plan, display_price=0, billing_interval=PlanVersion.BillingInterval.NONE, trial_days=current_policy().days,
            trial_once_per_store=True, grace_period_days=0,
        )
        for key, value in DEFAULT_TRIAL_LIMITS.items():
            if isinstance(value, tuple):
                plan_service.set_plan_entitlement(version, key, is_enabled=True, is_unlimited=value[0], integer_limit=value[1])
            else:
                plan_service.set_plan_entitlement(version, key, is_enabled=value)
        plan_service.publish_plan_version(version, actor=actor)
    return plan


def trial_plan_version():
    """Latest published version of the internal Trial plan (``None`` if it was never created)."""
    plan = Plan.objects.filter(code=TRIAL_PLAN_CODE, is_active=True).first()
    if plan is None:
        return None
    return plan.versions.filter(status=PlanVersion.Status.PUBLISHED).order_by("-version_number").first()


# --------------------------------------------------------------------------------------------------------------- eligibility / grant

def store_has_used_trial(store) -> bool:
    """True once ANY subscription of the store ever started a trial (terminal rows are kept as history, so this survives cancel/expiry)."""
    return StoreSubscription.objects.filter(store=store, trial_start_at__isnull=False).exists()


def is_eligible(store) -> bool:
    return current_policy().enabled and not store_has_used_trial(store)


@transaction.atomic
def grant_initial_trial(store, *, actor=None):
    """Give a brand-new store its one Trial. Returns the current subscription (the existing one if the store already has any — idempotent).

    * trial disabled → the store is created on the Trial plan but *never started*, and is restricted at once (non-terminal, so it can still buy a
      paid plan): read access stays, growth is closed, nothing is deleted;
    * already used → no second Trial (returns ``None`` unless a subscription exists);
    * otherwise → ``trialing`` for ``default_trial_days`` read now.
    """
    from apps.stores.models import Store

    Store.objects.select_for_update().get(pk=store.pk)                 # serialise concurrent provisioning of the SAME store
    existing = StoreSubscription.objects.filter(store=store, is_current=True).first()
    if existing is not None:
        return existing
    ensure_trial_plan(actor=actor)
    version = trial_plan_version()
    policy = current_policy()
    if store_has_used_trial(store):
        return None
    subscription = sub_svc.create_subscription(store, version, source=StoreSubscription.Source.DEFAULT, actor=actor)
    if not policy.enabled:
        record_audit_event(store=store, actor=actor, action_code="trial.not_granted_disabled", object_type="Store", object_id=str(store.pk),
                           object_label=store.slug, after={"reason": "trial_disabled"})
        return sub_svc.suspend_subscription(subscription, actor=actor, reason="دوره‌ی آزمایشی توسط پلتفرم غیرفعال است")
    started = sub_svc.start_trial(subscription, actor=actor, days=policy.days)
    record_audit_event(store=store, actor=actor, action_code="trial.granted", object_type="StoreSubscription", object_id=str(started.pk),
                       object_label=store.slug, after={"days": policy.days, "trial_end_at": str(started.trial_end_at)})
    return started


# ------------------------------------------------------------------------------------------------------------------- merchant view

def trial_info(store):
    """What the merchant panel shows about the store's Trial, from the store's OWN subscription rows only (tenant-scoped).

    ``state``: ``trialing`` (running), ``ended`` (Trial over, never bought), ``converted`` (bought a paid plan after the Trial), ``none`` (never had one).
    Returns ``days_left`` (whole days, ≥0), ``end_at``, the plan's limits with current usage while trialing, and ``can_buy_hint``."""
    from django.utils import timezone

    from apps.subscriptions.services import usage_service

    row = StoreSubscription.objects.filter(store=store, trial_start_at__isnull=False).select_related("plan_version__plan").order_by("-trial_start_at").first()
    current = StoreSubscription.objects.filter(store=store, is_current=True).select_related("plan_version__plan").first()
    if row is None:
        if current is not None and current.plan_version.plan.code == TRIAL_PLAN_CODE:        # Trial disabled when the store was created
            return {"state": "ended", "never_started": True, "trial_start_at": None, "trial_end_at": None, "days_left": 0, "limits": []}
        return {"state": "none"}
    now = timezone.now()
    on_trial_plan = current is not None and current.plan_version.plan.code == TRIAL_PLAN_CODE
    if current is not None and not on_trial_plan and current.status in (StoreSubscription.Status.ACTIVE, StoreSubscription.Status.GRACE_PERIOD,
                                                                       StoreSubscription.Status.PAST_DUE):
        return {"state": "converted", "trial_start_at": row.trial_start_at, "trial_end_at": row.trial_end_at}
    running = (current is not None and current.pk == row.pk and current.status == StoreSubscription.Status.TRIALING
               and current.trial_end_at is not None and current.trial_end_at > now)
    info = {"state": "trialing" if running else "ended", "trial_start_at": row.trial_start_at, "trial_end_at": row.trial_end_at,
            "days_left": 0, "limits": []}
    if running:
        seconds = (current.trial_end_at - now).total_seconds()
        info["days_left"] = max(0, int(-(-seconds // 86400)))                      # ceil: «۱ روز مانده» until the very end
        info["limits"] = [r for r in usage_service.get_usage_summary(store) if not r["unlimited"]]
    return info
