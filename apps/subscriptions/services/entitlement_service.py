"""سرویسِ مرکزیِ Entitlement — تنها منبعِ حقیقتِ «این Store به چه چیزی
دسترسی دارد؟» (ADR-64). هیچ ویو/سرویسی نباید ``plan.code == "pro"`` بنویسد؛
همه‌چیز از طریقِ کلیدِ Entitlement این‌جا عبور می‌کند.

قاعده‌ی fallback (ADR-64/65): اگر Store اشتراکِ جاری نداشته باشد، یا نسخه‌ی
پلن یک Entitlement را تعریف نکرده باشد، رفتار *fail-open* است (دسترسیِ
کامل/نامحدود) — تا فروشگاه‌هایِ موجود هرگز به‌طورِ ناگهانی محدود نشوند؛ اما
``get_subscription_access_state`` وضعیتِ واقعی را صادقانه گزارش می‌کند."""

from dataclasses import dataclass, field

from apps.subscriptions.models import EntitlementDefinition, PlanEntitlement, StoreSubscription


class EntitlementError(Exception):
    """پایه‌ی خطاهایِ دسترسی."""


class FeatureNotAvailable(EntitlementError):
    """قابلیتِ درخواست‌شده در پلنِ فعلیِ Store فعال نیست."""

    def __init__(self, key, message=None):
        self.key = key
        super().__init__(message or f"این قابلیت در پلنِ فعلیِ شما فعال نیست ({key}).")


class UsageLimitExceeded(EntitlementError):
    """ساختِ رکوردِ تازه از سقفِ پلنِ فعلی عبور می‌کند."""

    def __init__(self, key, *, limit=None, current=None, message=None):
        self.key = key
        self.limit = limit
        self.current = current
        super().__init__(message or f"به سقفِ پلنِ فعلیِ شما برایِ «{key}» رسیده‌اید.")


class SubscriptionRestricted(EntitlementError):
    """وضعیتِ اشتراک (معلق/منقضی) ساختِ رکوردِ تازه را می‌بندد."""

    def __init__(self, access_state, message=None):
        self.access_state = access_state
        super().__init__(message or access_state.message)


# --- وضعیت‌هایِ دسترسیِ کلان (state-level، جدا از سقفِ عددی) ---
class AccessState:
    FULL = "full"          # trialing/active/pending — دسترسیِ کامل
    GRACE = "grace"        # grace_period/past_due — کامل، با هشدار
    RESTRICTED = "restricted"  # suspended — ساختِ رکوردِ تازه بسته
    EXPIRED = "expired"    # expired/cancelled(نهایی) — رشد بسته، خواندن باز
    NONE = "none"          # بدونِ اشتراک — fail-open، اما پرچم‌دار


@dataclass
class AccessStateResult:
    state: str
    subscription_status: str = ""
    message: str = ""
    allows_growth: bool = True   # آیا ساختِ رکوردِ تازه (رشد) مجاز است؟
    warning: str = ""            # پیامِ بنرِ هشدار (خالی یعنی بدونِ هشدار)


# نگاشتِ وضعیتِ اشتراک → (AccessState، اجازه‌ی رشد، هشدار)
_STATE_POLICY = {
    StoreSubscription.Status.PENDING: (AccessState.FULL, True, ""),
    StoreSubscription.Status.TRIALING: (AccessState.FULL, True, ""),
    StoreSubscription.Status.ACTIVE: (AccessState.FULL, True, ""),
    StoreSubscription.Status.GRACE_PERIOD: (
        AccessState.GRACE, True, "اشتراکِ شما در مهلتِ ارفاقی است؛ لطفاً وضعیتِ اشتراک را بررسی کنید.",
    ),
    StoreSubscription.Status.PAST_DUE: (
        AccessState.GRACE, True, "پرداختِ اشتراکِ شما معوق است؛ لطفاً اشتراک را تمدید کنید.",
    ),
    StoreSubscription.Status.SUSPENDED: (
        AccessState.RESTRICTED, False, "اشتراکِ شما معلق شده است؛ ساختِ رکوردِ تازه تا رفعِ تعلیق مسدود است.",
    ),
    StoreSubscription.Status.CANCELLED: (
        AccessState.EXPIRED, False, "اشتراکِ شما لغو شده است.",
    ),
    StoreSubscription.Status.EXPIRED: (
        AccessState.EXPIRED, False, "اشتراکِ شما منقضی شده است؛ برایِ ادامه لطفاً یک پلن انتخاب کنید.",
    ),
}


# --- کشِ نقشه‌ی Entitlement به‌ازای هر نسخه‌ی پلن ---
# نسخه‌ی منتشرشده تغییرناپذیر است (ADR-63)، پس کش کردنِ نقشه به‌ازایِ
# ``plan_version_id`` امن است؛ برایِ نسخه‌هایِ draft/legacy هم ``updated_at``
# را می‌سنجیم تا اگر تغییر کردند نقشه بازساخته شود (invalidationِ امن).
_ENTITLEMENT_MAP_CACHE = {}


def _entitlement_map(plan_version):
    """دیکشنریِ ``key -> PlanEntitlement`` برایِ یک نسخه — با کشِ امن."""
    if plan_version is None:
        return {}
    cached = _ENTITLEMENT_MAP_CACHE.get(plan_version.pk)
    if cached is not None and cached[0] == plan_version.updated_at:
        return cached[1]
    mapping = {
        pe.entitlement.key: pe
        for pe in plan_version.plan_entitlements.select_related("entitlement").all()
    }
    _ENTITLEMENT_MAP_CACHE[plan_version.pk] = (plan_version.updated_at, mapping)
    return mapping


def clear_entitlement_cache():
    """کشِ نقشه‌ی Entitlement را پاک می‌کند — برایِ تست/پس از تغییرِ پلن."""
    _ENTITLEMENT_MAP_CACHE.clear()


# ================================================================== خواندنِ اشتراک

def get_current_subscription(store):
    """اشتراکِ جاریِ (غیرِ نهاییِ) Store یا ``None``."""
    return (
        StoreSubscription.objects.filter(store=store, is_current=True)
        .select_related("plan_version", "plan_version__plan")
        .first()
    )


def get_effective_plan_version(store):
    """نسخه‌ی پلنِ مؤثرِ Store (از اشتراکِ جاری) یا ``None``."""
    sub = get_current_subscription(store)
    return sub.plan_version if sub else None


# ================================================================== قابلیت (boolean)

#: کلیدهایِ اعمال‌شده‌یِ *تازه* که grandfathering دارند (``EntitlementDefinition.enforced_from``). برایِ بقیه‌ی کلیدها هیچ
#: پرس‌وجوی اضافه‌ای انجام نمی‌شود.
GRANDFATHERED_KEYS = frozenset({"domains.custom"})


def _is_grandfathered(plan_version, key) -> bool:
    """نسخه‌ی منتشرشده پیش از ``enforced_from`` (یا بدونِ ``published_at`` = قدیمی/دستی) رفتارِ قبلیِ fail-open را حفظ می‌کند."""
    if key not in GRANDFATHERED_KEYS or plan_version is None:
        return False
    effective = EntitlementDefinition.objects.filter(key=key).values_list("enforced_from", flat=True).first()
    if effective is None:
        return False
    return plan_version.published_at is None or plan_version.published_at < effective


def has_entitlement(store, key, *, plan_version=None) -> bool:
    """آیا قابلیتِ ``key`` برایِ Store فعال است؟ fail-open وقتی اشتراک/تعریف
    وجود نداشته باشد (ADR-64). کلیدهایِ دارایِ grandfathering برایِ نسخه‌هایِ منتشرشده‌ی پیش از تاریخِ اعمال همیشه True‌اند."""
    if plan_version is None:
        plan_version = get_effective_plan_version(store)
    if plan_version is None:
        return True  # بدونِ اشتراک → fail-open (نگاه کنید به docstring ماژول)
    if _is_grandfathered(plan_version, key):
        return True
    mapping = _entitlement_map(plan_version)
    pe = mapping.get(key)
    if pe is not None:
        return pe.is_enabled
    # تعریفِ پلن این کلید را ندارد → پیش‌فرضِ تعریف (یا fail-open اگر تعریف نبود).
    definition = EntitlementDefinition.objects.filter(key=key).first()
    return definition.default_enabled if definition else True


def check_entitlement(store, key, *, plan_version=None) -> None:
    """اگر قابلیت فعال نباشد ``FeatureNotAvailable`` می‌اندازد."""
    if not has_entitlement(store, key, plan_version=plan_version):
        raise FeatureNotAvailable(key)


# ================================================================== سقفِ عددی

def get_entitlement_limit(store, key, *, plan_version=None):
    """سقفِ عددیِ ``key`` را برمی‌گرداند: ``None`` یعنی «نامحدود»، وگرنه عددِ
    صحیح. اگر قابلیت خاموش باشد ``0`` برمی‌گرداند (هیچ ساختِ تازه‌ای مجاز
    نیست). fail-open (None) وقتی اشتراک/تعریف نبود."""
    if plan_version is None:
        plan_version = get_effective_plan_version(store)
    if plan_version is None:
        return None
    mapping = _entitlement_map(plan_version)
    pe = mapping.get(key)
    if pe is None:
        return None  # تعریف نشده → نامحدود (fail-open)
    if not pe.is_enabled:
        return 0
    return pe.resolved_limit()  # None = نامحدود


# ================================================================== وضعیتِ دسترسیِ کلان

def get_subscription_access_state(store) -> AccessStateResult:
    """وضعیتِ دسترسیِ کلانِ Store را برمی‌گرداند (state-level، جدا از سقف)."""
    sub = get_current_subscription(store)
    if sub is None:
        # آخرین اشتراکِ نهایی‌شده را هم در نظر بگیریم تا پیامِ درست بدهیم.
        last = (
            StoreSubscription.objects.filter(store=store)
            .order_by("-created_at").first()
        )
        if last is not None and last.status in _STATE_POLICY:
            state, allows_growth, warning = _STATE_POLICY[last.status]
            return AccessStateResult(
                state=state, subscription_status=last.status,
                message=warning or "", allows_growth=allows_growth, warning=warning,
            )
        return AccessStateResult(
            state=AccessState.NONE, subscription_status="",
            message="", allows_growth=True, warning="",
        )
    state, allows_growth, warning = _STATE_POLICY.get(
        sub.status, (AccessState.FULL, True, "")
    )
    return AccessStateResult(
        state=state, subscription_status=sub.status,
        message=warning or "", allows_growth=allows_growth, warning=warning,
    )


def require_growth_allowed(store) -> None:
    """اگر وضعیتِ اشتراک ساختِ رکوردِ تازه را می‌بندد، ``SubscriptionRestricted``
    می‌اندازد. این گیتِ *state-level* است — سقفِ عددی جداگانه بررسی می‌شود."""
    access = get_subscription_access_state(store)
    if not access.allows_growth:
        raise SubscriptionRestricted(access)


# ================================================================== خلاصه برایِ UI

def get_subscription_summary(store) -> dict:
    """خلاصه‌ی ساخت‌یافته‌ی اشتراک برایِ نمایش در Merchant Admin."""
    sub = get_current_subscription(store)
    access = get_subscription_access_state(store)
    if sub is None:
        return {
            "has_subscription": False,
            "access_state": access.state,
            "warning": access.warning,
            "status": "",
        }
    plan = sub.plan_version.plan
    return {
        "has_subscription": True,
        "subscription": sub,
        "plan": plan,
        "plan_version": sub.plan_version,
        "status": sub.status,
        "status_display": sub.get_status_display(),
        "access_state": access.state,
        "allows_growth": access.allows_growth,
        "warning": access.warning,
        "trial_end_at": sub.trial_end_at,
        "current_period_end": sub.current_period_end,
        "grace_period_end": sub.grace_period_end,
        "cancel_at_period_end": sub.cancel_at_period_end,
    }
