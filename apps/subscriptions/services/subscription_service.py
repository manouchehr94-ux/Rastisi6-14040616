"""ماشینِ حالتِ اشتراک — تنها مسیرِ مجازِ تغییرِ وضعیتِ ``StoreSubscription``.
نگاه کنید به ADR-66 (ماشینِ حالت)، ADR-67 (تریال/grace)، ADR-71 (رخدادها).

هر انتقال: ``transaction.atomic`` + ``select_for_update`` رویِ اشتراک، فقط
انتقالِ قانونی (جدولِ ``ALLOWED_TRANSITIONS``)، idempotent، ثبتِ actor،
ساختِ ``SubscriptionEvent`` و رخدادِ Audit Log. هیچ ویو‌ای نباید مستقیماً
``subscription.status = ...`` بنویسد."""

from django.db import transaction
from django.utils import timezone

from apps.core.services.audit_service import record_audit_event
from apps.subscriptions.models import Plan, PlanVersion, StoreSubscription, SubscriptionEvent

S = StoreSubscription.Status
ET = SubscriptionEvent.EventType


class SubscriptionError(Exception):
    """خطای قابل‌نمایشِ عملیاتِ اشتراک — انتقالِ غیرمجاز، نسخه‌ی نامعتبر و... ."""


class IllegalTransitionError(SubscriptionError):
    """انتقالِ درخواست‌شده از وضعیتِ فعلی مجاز نیست."""


#: جدولِ انتقال‌هایِ قانونی — از هر وضعیت به کدام وضعیت‌ها می‌توان رفت
#: (نگاه کنید به ADR-66). انتقال‌هایِ غیرِ فهرست‌شده رد می‌شوند. مثال‌هایِ
#: صریحاً غیرمجاز: expired→active (بدونِ اشتراکِ تازه)، cancelled→trialing،
#: suspended→trialing.
ALLOWED_TRANSITIONS = {
    # PENDING→SUSPENDED: created but never started (the platform disabled the initial Trial) — restricted until the store buys.
    S.PENDING: {S.TRIALING, S.ACTIVE, S.CANCELLED, S.SUSPENDED},
    # TRIALING→SUSPENDED: the internal Trial ended with no grace. NON-terminal on purpose: the store keeps a current subscription, so it can
    # still buy (a terminal row would leave it with no subscription to upgrade from).
    S.TRIALING: {S.ACTIVE, S.GRACE_PERIOD, S.SUSPENDED, S.EXPIRED, S.CANCELLED},
    S.ACTIVE: {S.GRACE_PERIOD, S.PAST_DUE, S.SUSPENDED, S.CANCELLED, S.EXPIRED},
    S.GRACE_PERIOD: {S.ACTIVE, S.PAST_DUE, S.SUSPENDED, S.EXPIRED, S.CANCELLED},
    S.PAST_DUE: {S.ACTIVE, S.GRACE_PERIOD, S.SUSPENDED, S.EXPIRED, S.CANCELLED},
    S.SUSPENDED: {S.ACTIVE, S.EXPIRED, S.CANCELLED},
    S.CANCELLED: set(),
    S.EXPIRED: set(),
}


def _record_event(subscription, *, event_type, from_status, to_status, actor, reason,
                  from_plan_version=None, to_plan_version=None, idempotency_key="", metadata=None):
    SubscriptionEvent.objects.create(
        subscription=subscription, store=subscription.store, event_type=event_type,
        from_status=from_status or "", to_status=to_status or "",
        from_plan_version=from_plan_version, to_plan_version=to_plan_version,
        actor=actor, reason=reason or "", idempotency_key=idempotency_key or "",
        metadata=metadata or {},
    )
    record_audit_event(
        store=subscription.store, actor=actor, action_code=f"subscription.{event_type}",
        object_type="StoreSubscription", object_id=str(subscription.pk),
        object_label=f"{subscription.plan_version.plan.code} → {to_status or from_status}",
        before={"status": from_status} if from_status else None,
        after={"status": to_status} if to_status else None,
        metadata=metadata or {},
        request_id=idempotency_key or "",
    )


def _transition(subscription, *, to_status, event_type, actor, reason, idempotency_key="",
                extra_fields=None, metadata=None):
    """هسته‌ی مشترکِ همه‌ی انتقال‌ها — قفل، بررسیِ قانونی‌بودن، به‌روزرسانیِ
    فیلدها، ثبتِ رخداد. idempotent: اگر اشتراک از قبل در ``to_status`` باشد
    و همان ``idempotency_key`` قبلاً رخداد ساخته باشد، بی‌اثر برمی‌گردد."""
    locked = StoreSubscription.objects.select_for_update().get(pk=subscription.pk)
    from_status = locked.status

    if from_status == to_status:
        # idempotent no-op — اگر رخدادِ همین کلید قبلاً ثبت شده باشد.
        if idempotency_key and locked.events.filter(idempotency_key=idempotency_key).exists():
            return locked
        # وضعیت از قبل درست است؛ فیلدهایِ اضافی را (در صورتِ تفاوت) اعمال
        # نمی‌کنیم تا رفتار قابل‌پیش‌بینی بماند — فقط برمی‌گردیم.
        return locked

    if to_status not in ALLOWED_TRANSITIONS.get(from_status, set()):
        raise IllegalTransitionError(
            f"انتقال از «{from_status}» به «{to_status}» مجاز نیست."
        )

    locked.status = to_status
    if to_status in StoreSubscription.TERMINAL_STATUSES:
        locked.is_current = False
    for field, value in (extra_fields or {}).items():
        setattr(locked, field, value)
    locked.save()

    _record_event(
        locked, event_type=event_type, from_status=from_status, to_status=to_status,
        actor=actor, reason=reason, idempotency_key=idempotency_key, metadata=metadata,
    )
    return locked


# ================================================================== ساختِ اشتراک

@transaction.atomic
def create_subscription(store, plan_version, *, source=StoreSubscription.Source.ADMIN, actor=None) -> StoreSubscription:
    """یک اشتراکِ ``pending`` تازه می‌سازد. اگر Store از قبل اشتراکِ جاری
    داشته باشد خطا می‌دهد (قیدِ یک‌اشتراکِ‌جاری). نسخه باید منتشرشده باشد."""
    if StoreSubscription.objects.filter(store=store, is_current=True).exists():
        raise SubscriptionError("این فروشگاه از قبل یک اشتراکِ جاری دارد.")
    if plan_version.status != PlanVersion.Status.PUBLISHED:
        raise SubscriptionError("فقط نسخه‌ی «منتشرشده»ی پلن قابلِ اشتراک است.")
    subscription = StoreSubscription.objects.create(
        store=store, plan_version=plan_version, status=S.PENDING, is_current=True, source=source,
    )
    _record_event(subscription, event_type=ET.CREATED, from_status="", to_status=S.PENDING,
                  actor=actor, reason="", to_plan_version=plan_version)
    return subscription


# ================================================================== انتقال‌ها

@transaction.atomic
def start_trial(subscription, *, actor=None, idempotency_key="", days=None) -> StoreSubscription:
    """اشتراک را به ``trialing`` می‌برد و بازه‌ی تریال را محاسبه می‌کند (ADR-67): ``days`` صریح (سیاستِ پلتفرم برایِ Trialِ
    اولیه، ``trial_service``) یا ``trial_days``ِ نسخه. تغییرِ پلن مدتِ تریال را ریست نمی‌کند."""
    now = timezone.now()
    days = subscription.plan_version.trial_days if days is None else days
    end = now + timezone.timedelta(days=days) if days else now
    return _transition(
        subscription, to_status=S.TRIALING, event_type=ET.TRIAL_STARTED, actor=actor,
        reason="", idempotency_key=idempotency_key,
        extra_fields={"trial_start_at": now, "trial_end_at": end, "start_at": subscription.start_at or now},
    )


@transaction.atomic
def activate_subscription(subscription, *, actor=None, period_end=None, idempotency_key="") -> StoreSubscription:
    """اشتراک را فعال می‌کند. دوره‌ی جاری را تنظیم می‌کند. در 5A پول واقعی
    دریافت نمی‌شود (ADR-72) — فعال‌سازی یک اقدامِ اداری/سرویسی است."""
    now = timezone.now()
    return _transition(
        subscription, to_status=S.ACTIVE, event_type=ET.ACTIVATED, actor=actor,
        reason="", idempotency_key=idempotency_key,
        extra_fields={
            "start_at": subscription.start_at or now,
            "current_period_start": subscription.current_period_start or now,
            "current_period_end": period_end,
        },
    )


def _status_of(subscription):
    """وضعیتِ فعلی با قفلِ ردیف — فقط درونِ تراکنشِ فراخوان (همان قفلی که ``_transition`` می‌گیرد)؛ دو اجرای هم‌زمان یک گذار را دو بار گزارش نمی‌کنند."""
    return StoreSubscription.objects.select_for_update().filter(pk=subscription.pk).values_list("status", flat=True).first()


@transaction.atomic
def enter_grace_period(subscription, *, actor=None, grace_end=None, idempotency_key="") -> StoreSubscription:
    now = timezone.now()
    if grace_end is None:
        days = subscription.plan_version.grace_period_days
        grace_end = now + timezone.timedelta(days=days) if days else now
    before = _status_of(subscription)
    result = _transition(
        subscription, to_status=S.GRACE_PERIOD, event_type=ET.GRACE_STARTED, actor=actor,
        reason="", idempotency_key=idempotency_key, extra_fields={"grace_period_end": grace_end},
    )
    if before != S.GRACE_PERIOD:                       # فقط گذارِ واقعی؛ اجرای تکراریِ dunning/ارزیابی (از قبل در مهلت) اعلانِ دوم نمی‌سازد
        from apps.notifications.services import admin_events

        admin_events.subscription_state(result, "grace")
    return result


@transaction.atomic
def mark_past_due(subscription, *, actor=None, idempotency_key="") -> StoreSubscription:
    before = _status_of(subscription)
    result = _transition(
        subscription, to_status=S.PAST_DUE, event_type=ET.PAST_DUE, actor=actor,
        reason="", idempotency_key=idempotency_key,
    )
    if before != S.PAST_DUE:
        from apps.notifications.services import admin_events

        admin_events.subscription_state(result, "past_due")
    return result


@transaction.atomic
def suspend_subscription(subscription, *, actor=None, reason="", idempotency_key="") -> StoreSubscription:
    before = _status_of(subscription)
    result = _transition(
        subscription, to_status=S.SUSPENDED, event_type=ET.SUSPENDED, actor=actor,
        reason=reason, idempotency_key=idempotency_key,
        extra_fields={"suspended_at": timezone.now()},
    )
    if before != S.SUSPENDED:
        from apps.notifications.services import admin_events

        admin_events.subscription_state(result, "suspended")
    return result


@transaction.atomic
def resume_subscription(subscription, *, actor=None, idempotency_key="") -> StoreSubscription:
    """اشتراکِ معلق/معوق/grace را دوباره فعال می‌کند (ADR-66) — هرگز به
    ``trialing`` برنمی‌گردد."""
    return _transition(
        subscription, to_status=S.ACTIVE, event_type=ET.RESUMED, actor=actor,
        reason="", idempotency_key=idempotency_key, extra_fields={"suspended_at": None},
    )


@transaction.atomic
def cancel_at_period_end(subscription, *, actor=None, idempotency_key="") -> StoreSubscription:
    """لغو را در پایانِ دوره زمان‌بندی می‌کند — اشتراک تا آن زمان فعال می‌ماند
    (وضعیت تغییر نمی‌کند، فقط پرچمِ ``cancel_at_period_end``). idempotent."""
    locked = StoreSubscription.objects.select_for_update().get(pk=subscription.pk)
    if locked.status in StoreSubscription.TERMINAL_STATUSES:
        raise IllegalTransitionError("اشتراکِ نهایی‌شده را نمی‌توان زمان‌بندیِ لغو کرد.")
    if locked.cancel_at_period_end:
        return locked
    locked.cancel_at_period_end = True
    locked.save(update_fields=["cancel_at_period_end", "updated_at"])
    _record_event(locked, event_type=ET.CANCEL_SCHEDULED, from_status=locked.status,
                  to_status=locked.status, actor=actor, reason="", idempotency_key=idempotency_key)
    return locked


@transaction.atomic
def cancel_immediately(subscription, *, actor=None, reason="", idempotency_key="") -> StoreSubscription:
    return _transition(
        subscription, to_status=S.CANCELLED, event_type=ET.CANCELLED, actor=actor,
        reason=reason, idempotency_key=idempotency_key,
        extra_fields={"cancelled_at": timezone.now(), "cancel_at_period_end": False},
    )


@transaction.atomic
def expire_subscription(subscription, *, actor=None, idempotency_key="") -> StoreSubscription:
    return _transition(
        subscription, to_status=S.EXPIRED, event_type=ET.EXPIRED, actor=actor,
        reason="", idempotency_key=idempotency_key, extra_fields={"expired_at": timezone.now()},
    )


@transaction.atomic
def renew_subscription(subscription, *, period_start, period_end, actor=None, idempotency_key="") -> StoreSubscription:
    """اشتراک را برایِ دوره‌ی تازه تمدید می‌کند (پس از پرداختِ موفقِ فاکتورِ
    تمدید — ADR-78). دوره‌ی جاری را جلو می‌برد، وضعیتِ grace/past_due را (در
    صورتِ قانونی‌بودن) به active برمی‌گرداند، و رخدادِ ``renewed`` ثبت می‌کند.
    idempotent روی ``idempotency_key``. اشتراکِ نهایی‌شده تمدید نمی‌شود."""
    locked = StoreSubscription.objects.select_for_update().get(pk=subscription.pk)
    if locked.status in StoreSubscription.TERMINAL_STATUSES:
        raise IllegalTransitionError("اشتراکِ نهایی‌شده را نمی‌توان تمدید کرد.")
    if idempotency_key and locked.events.filter(idempotency_key=idempotency_key).exists():
        return locked
    from_status = locked.status
    locked.current_period_start = period_start
    locked.current_period_end = period_end
    locked.grace_period_end = None
    # پرداختِ موفق، دوره‌ی معوق/ارفاقی را پاک می‌کند و اشتراک را فعال می‌کند.
    if locked.status != S.ACTIVE:
        locked.status = S.ACTIVE
    locked.save(update_fields=[
        "current_period_start", "current_period_end", "grace_period_end", "status", "updated_at",
    ])
    _record_event(
        locked, event_type=ET.RENEWED, from_status=from_status, to_status=locked.status,
        actor=actor, reason="", idempotency_key=idempotency_key,
        metadata={"period_start": str(period_start), "period_end": str(period_end)},
    )
    return locked


@transaction.atomic
def change_plan_version(subscription, target_version, *, actor=None, reason="", idempotency_key="") -> StoreSubscription:
    """نسخه‌ی پلنِ اشتراک را عوض می‌کند (ارتقا/تنزل) — وضعیت را تغییر نمی‌دهد،
    فقط ``plan_version`` و رخدادِ ``plan_changed`` (ADR-70). مدتِ تریال ریست
    نمی‌شود (ADR-67). نسخه‌ی هدف باید منتشرشده باشد.

    در 5A فقط Entitlement‌ها را تغییر می‌دهد؛ هیچ پول واقعی/پروریشنی رخ
    نمی‌دهد (ADR-72)."""
    locked = StoreSubscription.objects.select_for_update().get(pk=subscription.pk)
    if locked.status in StoreSubscription.TERMINAL_STATUSES:
        raise IllegalTransitionError("اشتراکِ نهایی‌شده را نمی‌توان تغییرِ پلن داد.")
    if target_version.status != PlanVersion.Status.PUBLISHED:
        raise SubscriptionError("فقط نسخه‌ی «منتشرشده» قابلِ انتخاب است.")
    if idempotency_key and locked.events.filter(idempotency_key=idempotency_key).exists():
        return locked
    from_version = locked.plan_version
    if from_version.pk == target_version.pk:
        return locked
    locked.plan_version = target_version
    locked.save(update_fields=["plan_version", "updated_at"])
    _record_event(
        locked, event_type=ET.PLAN_CHANGED, from_status=locked.status, to_status=locked.status,
        actor=actor, reason=reason, from_plan_version=from_version, to_plan_version=target_version,
        idempotency_key=idempotency_key,
        metadata={"from_version": from_version.pk, "to_version": target_version.pk},
    )
    return locked


# ================================================================== کنترل‌هایِ دستیِ تریال (مدیرِ پلتفرم)

def _require_reason(reason: str) -> str:
    reason = (reason or "").strip()
    if not reason:
        raise SubscriptionError("برایِ این تغییرِ دستی، ثبتِ دلیل الزامی است.")
    return reason


@transaction.atomic
def extend_trial(subscription, *, days: int, actor, reason: str, idempotency_key="") -> StoreSubscription:
    """دوره‌ی آزمایشیِ در حالِ اجرا را به‌مدتِ ``days`` روز تمدید می‌کند
    (بخشِ ۴.۲ — کنترل‌هایِ دستیِ تریال). فقط رویِ اشتراکِ ``trialing`` مجاز
    است؛ دلیل الزامی است و رخدادِ ``trial_extended`` با پایانِ قبلی/تازه
    ثبت می‌شود."""
    reason = _require_reason(reason)
    if not isinstance(days, int) or days <= 0:
        raise SubscriptionError("تعدادِ روزهایِ افزوده باید یک عددِ صحیحِ مثبت باشد.")
    locked = StoreSubscription.objects.select_for_update().get(pk=subscription.pk)
    if locked.status != S.TRIALING:
        raise IllegalTransitionError("این فروشگاه در وضعیتِ آزمایشی نیست.")
    if idempotency_key and locked.events.filter(idempotency_key=idempotency_key).exists():
        return locked
    before = locked.trial_end_at
    base = before or timezone.now()
    after = base + timezone.timedelta(days=days)
    locked.trial_end_at = after
    locked.save(update_fields=["trial_end_at", "updated_at"])
    _record_event(
        locked, event_type=ET.TRIAL_EXTENDED, from_status=locked.status, to_status=locked.status,
        actor=actor, reason=reason, idempotency_key=idempotency_key,
        metadata={"days_added": days, "previous_trial_end_at": str(before) if before else None,
                  "new_trial_end_at": str(after)},
    )
    return locked


@transaction.atomic
def set_trial_end(subscription, *, end_at, actor, reason: str, idempotency_key="") -> StoreSubscription:
    """پایانِ دقیقِ تریال را به یک تاریخ/زمانِ صریح تنظیم می‌کند. فقط رویِ
    اشتراکِ ``trialing`` مجاز است؛ دلیل الزامی است."""
    reason = _require_reason(reason)
    if end_at is None or timezone.is_naive(end_at):
        raise SubscriptionError("پایانِ تریال باید یک زمانِ معتبر و timezone-aware باشد.")
    locked = StoreSubscription.objects.select_for_update().get(pk=subscription.pk)
    if locked.status != S.TRIALING:
        raise IllegalTransitionError("این فروشگاه در وضعیتِ آزمایشی نیست.")
    if idempotency_key and locked.events.filter(idempotency_key=idempotency_key).exists():
        return locked
    before = locked.trial_end_at
    locked.trial_end_at = end_at
    locked.save(update_fields=["trial_end_at", "updated_at"])
    _record_event(
        locked, event_type=ET.TRIAL_END_SET, from_status=locked.status, to_status=locked.status,
        actor=actor, reason=reason, idempotency_key=idempotency_key,
        metadata={"previous_trial_end_at": str(before) if before else None, "new_trial_end_at": str(end_at)},
    )
    return locked


@transaction.atomic
def end_trial_now(subscription, *, actor, reason: str, idempotency_key="") -> StoreSubscription:
    """دورهٔ آزمایشی را همین حالا پایان می‌دهد — دقیقاً همان انتقالی که
    ارزیاب زمان‌بندی‌شده (``evaluate_subscription_states``) در سررسیدِ
    طبیعی اعمال می‌کرد (به مهلتِ ارفاقی یا مستقیماً انقضا، بر اساسِ
    ``grace_period_days`` نسخه‌ی پلن)، امّا هم‌اکنون و با دلیلِ دستی.
    دیتای فروشگاه پاک نمی‌شود؛ مالک همچنان می‌تواند وارد شود و
    خرید/تمدید/تغییرِ پلن انجام دهد."""
    reason = _require_reason(reason)
    locked = StoreSubscription.objects.select_for_update().get(pk=subscription.pk)
    if locked.status != S.TRIALING:
        raise IllegalTransitionError("این فروشگاه در وضعیتِ آزمایشی نیست.")
    if idempotency_key and locked.events.filter(idempotency_key=idempotency_key).exists():
        return locked
    before = locked.trial_end_at
    now = timezone.now()
    to_status = S.GRACE_PERIOD if locked.plan_version.grace_period_days else S.EXPIRED
    extra_fields = {"trial_end_at": now}
    if to_status == S.GRACE_PERIOD:
        extra_fields["grace_period_end"] = now + timezone.timedelta(days=locked.plan_version.grace_period_days)
    else:
        extra_fields["expired_at"] = now
    result = _transition(
        locked, to_status=to_status, event_type=ET.TRIAL_ENDED_MANUALLY, actor=actor,
        reason=reason, idempotency_key=idempotency_key, extra_fields=extra_fields,
        metadata={"previous_trial_end_at": str(before) if before else None, "new_trial_end_at": str(now)},
    )
    return result


# ================================================================== پلنِ پیش‌فرض

def resolve_default_plan_version():
    """جدیدترین نسخه‌ی منتشرشده‌ی پلنِ پیش‌فرض (``RASTISI_DEFAULT_PLAN_CODE``)
    یا ``None`` اگر پیکربندی نشده / پلن نبود / نسخه‌ی منتشرشده نداشت. هرگز
    استثنا نمی‌اندازد — نبودِ پلنِ پیش‌فرض یک پیکربندیِ معتبر است (fail-open)."""
    from django.conf import settings

    code = getattr(settings, "RASTISI_DEFAULT_PLAN_CODE", "") or ""
    if not code:
        return None
    plan = Plan.objects.filter(code=code, is_active=True).first()
    if plan is None:
        return None
    return (
        PlanVersion.objects.filter(plan=plan, status=PlanVersion.Status.PUBLISHED)
        .order_by("-version_number").first()
    )


def trial_eligible(store, plan_version) -> bool:
    """آیا این فروشگاه می‌تواند تریالِ این نسخه را بگیرد؟ نسخه باید تریال داشته باشد؛ و اگر ``trial_once_per_store``
    روشن است، فروشگاهی که قبلاً تریالِ *همین پلن* (هر نسخه‌ای) را شروع کرده واجد نیست."""
    if plan_version is None or not plan_version.trial_days:
        return False
    if not plan_version.trial_once_per_store:
        return True
    return not StoreSubscription.objects.filter(
        store=store, plan_version__plan=plan_version.plan_id, trial_start_at__isnull=False,
    ).exists()


@transaction.atomic
def provision_default_subscription(store, *, actor=None, with_trial=None, plan_version=None):
    """اشتراکِ پیش‌فرض را برایِ یک Storeِ تازه می‌سازد. idempotent: اگر Store از قبل اشتراکِ جاری دارد همان برمی‌گردد.

    * پیش‌فرض (و رفتارِ محصولیِ نهایی): **Trialِ اولیه** از پلنِ داخلیِ «trial» با مدتِ ``PlatformConfiguration.default_trial_days``
      (``trial_service.grant_initial_trial``) — برایِ هر فروشگاه حداکثر یک‌بار. ``plan_version`` (پلنِ پولیِ انتخاب‌شده در سایتِ عمومی)
      **هیچ Trial دومی نمی‌دهد** و هیچ اشتراکِ پولی بدونِ پرداخت ساخته نمی‌شود؛ انتخاب فقط در نشست برایِ هدایتِ خرید یادآوری می‌شود.
    * استثنا (سازگاریِ عملیاتی): اگر اپراتور صراحتاً ``RASTISI_DEFAULT_PLAN_CODE`` را روی پلنی جز «trial» تنظیم کرده باشد، همان پلن مثلِ قبل
      داده می‌شود (فعال، یا با Trial اگر ``with_trial`` و نسخه ``trial_days`` داشته باشد).

    اگر هیچ پلنی ساخته نشود ``None`` برمی‌گرداند و ساختِ Store هرگز شکست نمی‌خورد (fail-open، ADR-65). فروشگاه‌هایِ *موجود* از این مسیر عبور
    نمی‌کنند — آن‌ها پلنِ نامحدودِ Legacy را از مهاجرت/فرمان می‌گیرند."""
    from django.conf import settings

    existing = StoreSubscription.objects.filter(store=store, is_current=True).first()
    if existing is not None:
        return existing
    configured = getattr(settings, "RASTISI_DEFAULT_PLAN_CODE", "") or ""
    if configured in ("", "trial"):
        from apps.subscriptions.services import trial_service

        return trial_service.grant_initial_trial(store, actor=actor)
    version = resolve_default_plan_version()
    if version is None:
        return None
    if with_trial is None:
        with_trial = getattr(settings, "RASTISI_DEFAULT_PLAN_START_TRIAL", True)
    subscription = create_subscription(store, version, source=StoreSubscription.Source.DEFAULT, actor=actor)
    if with_trial and version.trial_days and trial_eligible(store, version):
        return start_trial(subscription, actor=actor)
    return activate_subscription(subscription, actor=actor)


# ================================================================== ارزیابیِ زمانی

def _due_action(sub, now):
    """کارِ سررسیدشده‌ی این اشتراک بر اساسِ زمان، یا ``None``. ترتیبِ اولویت:
    لغوِ زمان‌بندی‌شده > پایانِ تریال > پایانِ مهلتِ ارفاقی > پایانِ دوره."""
    if sub.cancel_at_period_end and sub.current_period_end and sub.current_period_end <= now:
        return "cancelled"
    if sub.status == S.TRIALING and sub.trial_end_at and sub.trial_end_at <= now:
        if sub.plan_version.grace_period_days:
            return "grace"
        # the internal Trial ends into the restricted (non-terminal) state so the store can still buy; other plans keep the old «expired»
        return "suspended" if sub.plan_version.plan.code == "trial" else "expired"
    if sub.status == S.GRACE_PERIOD and sub.grace_period_end and sub.grace_period_end <= now:
        return "suspended"
    if sub.status in (S.ACTIVE, S.PAST_DUE) and sub.current_period_end and sub.current_period_end <= now:
        return "grace"
    return None


def _apply_due_action(sub, action, *, actor=None):
    if action == "cancelled":
        cancel_immediately(sub, actor=actor, reason="لغوِ زمان‌بندی‌شده در پایانِ دوره")
    elif action == "grace":
        enter_grace_period(sub, actor=actor)
    elif action == "suspended":
        suspend_subscription(sub, actor=actor, reason="پایانِ دوره‌ی آزمایشی" if sub.status == S.TRIALING else "پایانِ مهلتِ ارفاقی")
    elif action == "expired":
        expire_subscription(sub, actor=actor)


def evaluate_subscription_states(*, now=None, dry_run=False, actor=None) -> dict:
    """اشتراک‌هایِ جاریِ غیرِ نهایی را می‌گردد و انتقال‌هایِ زمانیِ سررسیدشده را
    اعمال می‌کند (تریال→ارفاق/انقضا، ارفاق→تعلیق، دوره‌ی گذشته→ارفاق، لغوِ
    زمان‌بندی‌شده→لغو). ``dry_run`` فقط می‌شمارد و چیزی تغییر نمی‌دهد.

    این باید از یک زمان‌بندِ خارجی (cron) اجرا شود — این کدبیس صفِ کارِ
    پس‌زمینه‌ای ندارد (ADR-49)."""
    now = now or timezone.now()
    results = {"scanned": 0, "cancelled": 0, "grace": 0, "suspended": 0, "expired": 0}
    qs = (
        StoreSubscription.objects.filter(is_current=True)
        .exclude(status__in=StoreSubscription.TERMINAL_STATUSES)
        .select_related("plan_version")
    )
    for sub in qs.iterator(chunk_size=200):
        results["scanned"] += 1
        action = _due_action(sub, now)
        if action is None:
            continue
        if not dry_run:
            _apply_due_action(sub, action, actor=actor)
        results[action] += 1
    return results


# ================================================================== بررسیِ سازگاری

def check_subscription_consistency() -> list:
    """ناسازگاری‌هایِ اشتراک را فقط *می‌خواند* و فهرستِ مشکلات را برمی‌گرداند
    (هرگز چیزی نمی‌نویسد). هر مورد: dict با ``severity`` (error/warning) و
    ``message``. برایِ ``verify_subscription_consistency``."""
    from django.db.models import Count

    from apps.subscriptions.entitlements import ENTITLEMENT_DEFINITIONS
    from apps.subscriptions.models import EntitlementDefinition

    issues = []

    # ۱) بیش از یک اشتراکِ جاری برایِ یک Store (قیدِ DB باید جلویش را بگیرد).
    dupes = (
        StoreSubscription.objects.filter(is_current=True)
        .values("store_id").annotate(n=Count("id")).filter(n__gt=1)
    )
    for row in dupes:
        issues.append({"severity": "error",
                       "message": f"فروشگاه {row['store_id']} بیش از یک اشتراکِ جاری دارد ({row['n']})."})

    # ۲) وضعیتِ نهایی امّا is_current=True (باید هنگامِ نهایی‌شدن خاموش شود).
    for sub in StoreSubscription.objects.filter(
        is_current=True, status__in=StoreSubscription.TERMINAL_STATUSES,
    ).iterator(chunk_size=200):
        issues.append({"severity": "error",
                       "message": f"اشتراک {sub.pk} (فروشگاه {sub.store_id}) وضعیتِ نهاییِ «{sub.status}» دارد اما هنوز is_current است."})

    # ۳) اشتراکِ جاری رویِ نسخه‌ی غیرِ منتشرشده.
    for sub in StoreSubscription.objects.filter(is_current=True).select_related("plan_version").iterator(chunk_size=200):
        if sub.plan_version.status != PlanVersion.Status.PUBLISHED:
            issues.append({"severity": "error",
                           "message": f"اشتراکِ جاری {sub.pk} رویِ نسخه‌ی غیرِ منتشرشده ({sub.plan_version.status}) است."})

    # ۴) تعریفِ Entitlementِ استاندارد گم‌شده.
    existing_keys = set(EntitlementDefinition.objects.values_list("key", flat=True))
    for key, _n, _t, _d in ENTITLEMENT_DEFINITIONS:
        if key not in existing_keys:
            issues.append({"severity": "warning", "message": f"تعریفِ Entitlement «{key}» در پایگاه‌داده نیست."})

    return issues
