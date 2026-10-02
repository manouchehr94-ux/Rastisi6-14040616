"""چرخه‌ی عمر و اجرایِ کمپین‌ها: اعتبارسنجی، پیش‌نمایش، فعال‌سازی، اجرایِ
idempotent، صدورِ کدِ اختصاصی و اعلان.

اجرایِ دوباره‌ی هر job (دستی/زمان‌بندی/رویداد/مناسبت) هرگز پاداش یا پیامِ
تکراری نمی‌سازد: یکتاییِ ``CampaignIssuance(campaign, customer, cycle_key)`` در
دیتابیس، و ``dedupe_key`` اعلان (``issuance:<id>``) هر دو مانع‌اند."""

from __future__ import annotations

import datetime as dt
import logging
import secrets
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.cart.models import Coupon
from apps.customers.models import Customer
from apps.core.jalali_utils import (
    JalaliDateError, jalali_date_range_bounds, jalali_month_range_bounds, store_timezone,
)
from apps.core.services.audit_service import record_audit_event
from apps.engagement.models import Campaign, CampaignIssuance, CampaignRun
from apps.engagement.services import occasions, rule_data, rules
from apps.notifications import events as notif_events
from apps.notifications.services import context_builders, template_service
from apps.notifications.services.dispatcher import dispatch_event

logger = logging.getLogger(__name__)

CHUNK = 500
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # بدونِ نویسه‌هایِ مبهم (0/O، 1/I/L)
VALID_PAYMENT_STATUSES = ("pending", "paid", "failed", "refunded")


class CampaignError(Exception):
    """خطای قابلِ نمایش به مدیر."""


def store_now() -> dt.datetime:
    return timezone.now().astimezone(store_timezone())


# ------------------------------------------------------------------ بازه و اعتبارسنجی


def period_bounds(campaign: Campaign):
    """``[start, end)`` در منطقه‌ی زمانیِ فروشگاه یا ``(None, None)``."""
    tz = store_timezone()
    if campaign.period_mode == Campaign.PeriodMode.JALALI_MONTHS:
        return jalali_month_range_bounds(
            campaign.period_jalali_year, campaign.period_start_month, campaign.period_end_month, tz,
        )
    if campaign.period_mode == Campaign.PeriodMode.DATES:
        return jalali_date_range_bounds(campaign.period_start_date, campaign.period_end_date, tz)
    return None, None


def validate_campaign(campaign: Campaign) -> list[str]:
    """فهرستِ خطاهایِ پیکربندی؛ خالی = معتبر. یک کمپین فقط با پیکربندیِ
    معتبر فعال می‌شود (نمی‌تواند «فعال» باشد در حالی که ناقص است)."""
    errors: list[str] = []
    if not campaign.name.strip():
        errors.append("نامِ کمپین الزامی است.")

    try:
        campaign.rules = rules.validate_tree(campaign.rules, campaign.store)
    except rules.RuleError as exc:
        errors.append(f"قواعد: {exc}")

    statuses = campaign.valid_payment_statuses or []
    if any(s not in VALID_PAYMENT_STATUSES for s in statuses):
        errors.append("وضعیتِ پرداختِ معتبر نامعتبر است.")

    if campaign.period_mode == Campaign.PeriodMode.JALALI_MONTHS:
        if not (campaign.period_jalali_year and campaign.period_start_month and campaign.period_end_month):
            errors.append("سال و ماه‌هایِ شروع/پایانِ بازه الزامی است.")
        else:
            try:
                period_bounds(campaign)
            except JalaliDateError as exc:
                errors.append(f"بازه‌ی شمسی: {exc}")
    elif campaign.period_mode == Campaign.PeriodMode.DATES:
        if not (campaign.period_start_date and campaign.period_end_date):
            errors.append("تاریخِ شروع و پایانِ بازه الزامی است.")
        elif campaign.period_start_date > campaign.period_end_date:
            errors.append("تاریخِ شروعِ بازه نباید بعد از پایان باشد.")

    if campaign.reward_type == Campaign.Reward.COUPON:
        if campaign.coupon_type not in (Coupon.Type.PERCENT, Coupon.Type.FIXED, Coupon.Type.FREE_SHIP):
            errors.append("نوعِ تخفیف نامعتبر است.")
        elif campaign.coupon_type == Coupon.Type.PERCENT and not (0 < campaign.coupon_value <= 100):
            errors.append("درصدِ تخفیف باید بین ۱ تا ۱۰۰ باشد.")
        elif campaign.coupon_type == Coupon.Type.FIXED and campaign.coupon_value <= 0:
            errors.append("مبلغِ تخفیف باید مثبت باشد.")
        if campaign.coupon_max_discount is not None and campaign.coupon_max_discount <= 0:
            errors.append("سقفِ مبلغِ تخفیف باید مثبت باشد.")
        if campaign.code_starts_at and campaign.code_expires_at and campaign.code_expires_at <= campaign.code_starts_at:
            errors.append("انقضایِ کد باید بعد از فعال‌سازیِ آن باشد.")
        if not (campaign.code_expires_at or campaign.code_valid_days):
            errors.append("برایِ کد یک تاریخِ انقضا یا مدتِ اعتبار (روز) تعیین کنید.")
        if campaign.per_customer_period_days is not None and campaign.per_customer_period_days < 1:
            errors.append("پنجره‌ی سقفِ هر مشتری باید حداقل ۱ روز باشد.")
        if campaign.per_customer_period_days and not campaign.per_customer_limit:
            errors.append("برایِ پنجره‌ی زمانی، سقفِ استفاده برایِ هر مشتری را هم تعیین کنید.")
        if campaign.validity_from_delivery and not campaign.code_valid_days:
            errors.append("اعتبار از لحظه‌ی تحویل فقط با «مدتِ اعتبار (روز)» معنا دارد.")
        for field, label in (("total_redemption_limit", "سقفِ کلِ استفاده"), ("per_customer_limit", "سقفِ استفاده برایِ هر مشتری")):
            value = getattr(campaign, field)
            if value is not None and value < 1:
                errors.append(f"{label} باید حداقل ۱ باشد.")
    if campaign.max_issuances is not None and campaign.max_issuances < 1:
        errors.append("ظرفیتِ کمپین باید حداقل ۱ باشد.")
    if campaign.active_from and campaign.active_until and campaign.active_until <= campaign.active_from:
        errors.append("پایانِ فعالیتِ کمپین باید بعد از شروعِ آن باشد.")

    channels = campaign.channels or []
    if any(c not in notif_events.CHANNELS for c in channels):
        errors.append("کانالِ اطلاع‌رسانیِ نامعتبر.")

    if campaign.trigger_type == Campaign.Trigger.OCCASION:
        try:
            if not campaign.occasion_kind:
                raise occasions.OccasionError("نوعِ مناسبت را انتخاب کنید.")
            campaign.occasion_params = occasions.validate_params(campaign.occasion_kind, campaign.occasion_params)
        except occasions.OccasionError as exc:
            errors.append(str(exc))
        if not (-365 <= campaign.occasion_offset_days <= 365):
            errors.append("فاصله‌ی روز از مناسبت باید بین ۳۶۵- تا ۳۶۵ باشد.")
    elif campaign.trigger_type == Campaign.Trigger.EVENT and campaign.period_mode != Campaign.PeriodMode.NONE:
        pass  # بازه با رویداد سازگار است (قواعد تصمیم می‌گیرند)

    event_key = occasions.notification_event_key(campaign)
    for text, label in ((campaign.custom_sms_body, "پیامک"), (campaign.custom_email_body, "ایمیل"), (campaign.custom_email_subject, "موضوعِ ایمیل")):
        if text:
            try:
                template_service.validate_text(event_key, text, what=f"متنِ اختصاصیِ {label}")
            except template_service.TemplateError as exc:
                errors.append(str(exc))
    return errors


# ------------------------------------------------------------------ ارزیابی


def compute_eligible(campaign: Campaign, *, now=None, candidate_ids=None, valid_statuses=None):
    """مولدِ شناسه‌ی مشتریانِ مشمول — دسته‌ای (``CHUNK``) تا حافظه ثابت بماند."""
    now = now or store_now()
    store = campaign.store
    tree = campaign.rules or {}
    valid = valid_statuses or campaign.valid_payment_statuses or ["paid"]
    start, end = period_bounds(campaign)
    order_rules = rules.needs_orders(tree)

    if candidate_ids is None:
        candidates = rule_data.store_customer_ids(store)
    else:
        candidates = set(candidate_ids) & rule_data.store_customer_ids(store)  # هرگز مشتریِ Store دیگر
    if order_rules or start is not None:
        candidates &= rule_data.customers_with_valid_orders(store, valid, start, end)

    ordered = sorted(candidates)
    for i in range(0, len(ordered), CHUNK):
        chunk = ordered[i:i + CHUNK]
        facts = rule_data.load_facts(store, chunk, valid)
        valid_by, all_by = rule_data.load_orders(store, chunk, valid, start, end) if (order_rules or start is not None) else ({}, {})
        for cid in chunk:
            if cid not in facts:
                continue
            if rules.is_eligible(
                tree, scope=campaign.rule_scope, facts=facts[cid], orders=valid_by.get(cid, []),
                all_orders=all_by.get(cid, []), now=now, amount_basis=campaign.amount_basis,
            ):
                yield cid


def preview(campaign: Campaign, *, limit: int = 25, now=None, actor=None) -> dict:
    """تعدادِ مشمولان + نمونه (بدونِ صدورِ چیزی)."""
    from apps.customers.models import Customer

    now = now or store_now()
    if campaign.trigger_type == Campaign.Trigger.OCCASION:
        cycles = occasions.resolve_candidates(campaign, now.date())
        eligible = list(compute_eligible(campaign, now=now, candidate_ids=cycles.keys()))
    else:
        eligible = list(compute_eligible(campaign, now=now))
    existing = set(campaign.issuances.filter(customer_id__in=eligible[:5000]).values_list("customer_id", flat=True))
    sample = Customer.objects.filter(pk__in=eligible[:limit]).order_by("pk")
    run = CampaignRun.objects.create(
        campaign=campaign, trigger=CampaignRun.Trigger.PREVIEW, dry_run=True, started_at=now, finished_at=timezone.now(),
        evaluated=len(eligible), eligible=len(eligible),
    )
    return {
        "count": len(eligible),
        "already_issued": len(existing),
        "sample": [{"id": c.pk, "name": c.full_name, "phone": c.phone, "city": c.city} for c in sample],
        "run": run,
    }


# ------------------------------------------------------------------ کد تخفیف


def _generate_code(campaign: Campaign) -> str:
    prefix = (campaign.code_prefix or "GIFT").upper().strip("-")
    return f"{prefix}-" + "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))


def _coupon_expiry(campaign: Campaign, now):
    if campaign.code_expires_at:
        return campaign.code_expires_at
    if campaign.code_valid_days:
        # با «اعتبار از تحویل» این تاریخ موقت است (با ۷ روز مهلت)؛ با اولین تحویلِ موفق بازتنظیم می‌شود.
        grace = 7 if campaign.validity_from_delivery else 0
        return now + timedelta(days=campaign.code_valid_days + grace)
    return None


def _create_coupon(campaign: Campaign, customer, now) -> Coupon:
    for _ in range(10):
        try:
            with transaction.atomic():
                return Coupon.objects.create(
                    store=campaign.store, code=_generate_code(campaign), type=campaign.coupon_type,
                    value=campaign.coupon_value if campaign.coupon_type != Coupon.Type.FREE_SHIP else 0,
                    label=campaign.name[:150], min_order=campaign.coupon_min_order,
                    usage_limit=campaign.total_redemption_limit, per_customer_limit=campaign.per_customer_limit,
                    per_customer_period_days=campaign.per_customer_period_days,
                    starts_at=campaign.code_starts_at, expires_at=_coupon_expiry(campaign, now),
                    customer=customer, max_discount=campaign.coupon_max_discount,
                    applies_to_gift_wrap=campaign.coupon_applies_to_gift_wrap, is_active=True,
                )
        except IntegrityError:
            continue
    raise CampaignError("ساختِ کدِ یکتا ممکن نشد.")


def _coupon_for(campaign: Campaign, customer, now) -> Coupon:
    if campaign.personalized:
        return _create_coupon(campaign, customer, now)
    if campaign.shared_coupon_id is None:
        campaign.shared_coupon = _create_coupon(campaign, None, now)
        campaign.save(update_fields=["shared_coupon", "updated_at"])
    return campaign.shared_coupon


# ------------------------------------------------------------------ صدور و اعلان


def _notify(campaign: Campaign, customer, issuance: CampaignIssuance, coupon: Coupon | None) -> None:
    event_key = occasions.notification_event_key(campaign)
    ctx = {
        **context_builders.customer_context(campaign.store, customer),
        "campaign_name": campaign.name, "occasion_name": campaign.occasion_name or campaign.name,
        "discount_code": "", "discount_amount": "", "discount_max": "", "discount_expires_at": "",
        "reward_description": campaign.name,
    }
    if coupon is not None:
        ctx.update(context_builders.coupon_context(
            campaign.store, customer, coupon, campaign_name=campaign.name,
            occasion_name=campaign.occasion_name or campaign.name,
        ))
        ctx["reward_description"] = f"کد تخفیف {coupon.code} ({ctx['discount_amount']})"
    overrides = {}
    if campaign.custom_sms_body:
        overrides["sms"] = {"body": campaign.custom_sms_body}
    if campaign.custom_email_body:
        overrides["email"] = {"subject": campaign.custom_email_subject, "body": campaign.custom_email_body}
    rows = dispatch_event(
        event_key, store=campaign.store, customer=customer, context=ctx, dedupe_key=f"issuance:{issuance.pk}",
        channels=campaign.channels or None, overrides=overrides or None,
        metadata={
            "campaign_id": campaign.pk, "issuance_id": issuance.pk, "coupon_id": coupon.pk if coupon else None,
            # اعتبار از لحظه‌ی تحویل: پس از اولین ارسالِ موفق، انقضا مجدداً از همان لحظه محاسبه می‌شود
            "valid_days_from_delivery": (
                campaign.code_valid_days if campaign.validity_from_delivery and coupon and campaign.code_valid_days
                and not campaign.code_expires_at else None
            ),
        },
    )
    if rows:
        issuance.notified_at = timezone.now()
        issuance.save(update_fields=["notified_at", "updated_at"])


def issue_reward(campaign: Campaign, customer, cycle_key: str, *, now=None) -> str:
    """→ ``"issued"`` | ``"exists"`` | ``"capacity"``."""
    now = now or timezone.now()
    with transaction.atomic():
        locked = Campaign.objects.select_for_update(of=("self",)).select_related("store").get(pk=campaign.pk)
        if locked.max_issuances is not None and locked.issuances.count() >= locked.max_issuances:
            return "capacity"
        try:
            with transaction.atomic():
                issuance = CampaignIssuance.objects.create(campaign=locked, customer=customer, cycle_key=cycle_key)
        except IntegrityError:
            return "exists"
        coupon = _coupon_for(locked, customer, now) if locked.reward_type == Campaign.Reward.COUPON else None
        issuance.coupon = coupon
        issuance.save(update_fields=["coupon", "updated_at"])
        _notify(locked, customer, issuance, coupon)
        record_audit_event(
            store=locked.store, actor=None, action_code="campaign.reward_issued", object_type="Campaign",
            object_id=locked.pk, object_label=locked.name,
            after={"customer_id": customer.pk, "cycle": cycle_key, "coupon": coupon.code if coupon else ""},
        )
    return "issued"


# ------------------------------------------------------------------ اجرا


def sync_status(campaign: Campaign, now=None) -> Campaign:
    now = now or timezone.now()
    if campaign.status == Campaign.Status.ACTIVE and campaign.active_until and now > campaign.active_until:
        campaign.status = Campaign.Status.EXPIRED
        campaign.save(update_fields=["status", "updated_at"])
    return campaign


def execute_campaign(
    campaign: Campaign, *, trigger: str = CampaignRun.Trigger.MANUAL, now=None, candidate_ids=None,
    cycles: dict | None = None, dry_run: bool = False,
) -> CampaignRun:
    """اجرای یک کمپین. ``cycles``: ``{customer_id: cycle_key}`` برایِ مناسبت‌ها."""
    now = now or store_now()
    sync_status(campaign, now)
    run = CampaignRun.objects.create(campaign=campaign, trigger=trigger, dry_run=dry_run, started_at=timezone.now())

    def finish(error: str = ""):
        run.finished_at = timezone.now()
        run.error_text = error
        run.save()
        if not dry_run:
            campaign.last_run_at = run.finished_at
            campaign.save(update_fields=["last_run_at", "updated_at"])
        return run

    if not dry_run:
        if campaign.status != Campaign.Status.ACTIVE:
            return finish(f"کمپین در وضعیتِ «{campaign.get_status_display()}» قابلِ اجرا نیست.")
        if campaign.active_from and now < campaign.active_from:
            return finish("زمانِ شروعِ فعالیتِ کمپین هنوز فرا نرسیده است.")

    if cycles is not None:
        candidate_ids = list(cycles.keys())
    eligible_ids = list(compute_eligible(campaign, now=now, candidate_ids=candidate_ids))
    run.evaluated = run.eligible = len(eligible_ids)
    capacity_hit = False
    for i in range(0, 0 if dry_run else len(eligible_ids), CHUNK):
        chunk = eligible_ids[i:i + CHUNK]
        customers = Customer.objects.in_bulk(chunk)
        for cid in chunk:
            customer = customers.get(cid)
            if customer is None:
                continue
            cycle = (cycles or {}).get(cid, "once")
            try:
                outcome = issue_reward(campaign, customer, cycle, now=timezone.now())
            except Exception as exc:  # noqa: BLE001 — یک مشتری نباید کلِ اجرا را متوقف کند
                logger.exception("campaign %s issuance failed for customer %s", campaign.pk, cid)
                run.errors += 1
                run.error_text = (run.error_text + f"\nمشتری {cid}: {type(exc).__name__}")[:2000]
                continue
            if outcome == "issued":
                run.issued += 1
            elif outcome == "exists":
                run.skipped_existing += 1
            else:  # capacity
                campaign.status = Campaign.Status.COMPLETED
                campaign.save(update_fields=["status", "updated_at"])
                capacity_hit = True
                break
        if capacity_hit:
            break
    if not dry_run and campaign.max_issuances is not None and campaign.issuances.count() >= campaign.max_issuances:
        if campaign.status == Campaign.Status.ACTIVE:
            campaign.status = Campaign.Status.COMPLETED
            campaign.save(update_fields=["status", "updated_at"])
    return finish()


def run_occasion_campaign(campaign: Campaign, today: dt.date | None = None) -> CampaignRun:
    now = store_now()
    today = today or now.date()
    cycles = occasions.resolve_candidates(campaign, today)
    return execute_campaign(campaign, trigger=CampaignRun.Trigger.OCCASION, now=now, cycles=cycles)


def run_event_campaigns(store, customer, *, now=None) -> list[CampaignRun]:
    """پس از یک رویدادِ کسب‌وکار (پرداختِ موفق): کمپین‌هایِ ``EVENT`` را فقط برایِ
    همین مشتری ارزیابی می‌کند."""
    runs = []
    for campaign in Campaign.objects.filter(store=store, status=Campaign.Status.ACTIVE, trigger_type=Campaign.Trigger.EVENT):
        runs.append(execute_campaign(campaign, trigger=CampaignRun.Trigger.EVENT, now=now, candidate_ids=[customer.pk]))
    return runs


# ------------------------------------------------------------------ تغییر وضعیت


def activate(campaign: Campaign, *, actor=None) -> Campaign:
    if campaign.status not in (Campaign.Status.DRAFT, Campaign.Status.PAUSED):
        raise CampaignError("فقط کمپینِ پیش‌نویس یا متوقف قابلِ فعال‌سازی است.")
    errors = validate_campaign(campaign)
    if errors:
        raise CampaignError("؛ ".join(errors))
    if campaign.active_until and campaign.active_until <= timezone.now():
        raise CampaignError("زمانِ پایانِ فعالیتِ کمپین گذشته است.")
    campaign.status = Campaign.Status.ACTIVE
    campaign.activated_at = campaign.activated_at or timezone.now()
    campaign.save()
    record_audit_event(
        store=campaign.store, actor=actor, action_code="campaign.activated", object_type="Campaign",
        object_id=campaign.pk, object_label=campaign.name,
    )
    count = 0
    try:
        count = len(list(compute_eligible(campaign))) if campaign.trigger_type != Campaign.Trigger.OCCASION else 0
    except Exception:  # noqa: BLE001 — برآوردِ تعداد نباید فعال‌سازی را بشکند
        logger.exception("eligible count failed for campaign %s", campaign.pk)
    from apps.notifications.services.dispatcher import safe_dispatch

    safe_dispatch("campaign.activated", store=campaign.store, context={
        "campaign_name": campaign.name, "eligible_count": str(count), "store_name": campaign.store.name,
    }, dedupe_key=f"campaign:{campaign.pk}:{campaign.activated_at.isoformat()}")
    return campaign


def pause(campaign: Campaign, *, actor=None) -> Campaign:
    if campaign.status != Campaign.Status.ACTIVE:
        raise CampaignError("فقط کمپینِ فعال قابلِ توقف است.")
    campaign.status = Campaign.Status.PAUSED
    campaign.save(update_fields=["status", "updated_at"])
    record_audit_event(store=campaign.store, actor=actor, action_code="campaign.paused", object_type="Campaign",
                       object_id=campaign.pk, object_label=campaign.name)
    return campaign


def save_campaign(campaign: Campaign, *, actor=None) -> Campaign:
    """ذخیره با اعتبارسنجیِ ساختاریِ قواعد؛ کمپینِ فعال قابلِ ویرایش نیست (ابتدا متوقف کنید)."""
    if campaign.pk:
        current = Campaign.objects.get(pk=campaign.pk)
        if current.status == Campaign.Status.ACTIVE:
            raise CampaignError("کمپینِ فعال قابلِ ویرایش نیست؛ ابتدا آن را متوقف کنید.")
    try:
        campaign.rules = rules.validate_tree(campaign.rules, campaign.store)
    except rules.RuleError as exc:
        raise CampaignError(f"قواعد: {exc}") from exc
    is_new = campaign.pk is None
    campaign.save()
    record_audit_event(
        store=campaign.store, actor=actor, action_code="campaign.created" if is_new else "campaign.updated",
        object_type="Campaign", object_id=campaign.pk, object_label=campaign.name,
    )
    return campaign


# ------------------------------------------------------------------ یادآوریِ انقضا


def send_expiry_reminders(store=None, *, now=None) -> int:
    """برایِ کمپین‌هایِ دارایِ ``reminder_days_before_expiry``، کدهایِ مصرف‌نشده‌ای که
    دقیقاً در پنجره‌ی یادآوری قرار دارند را اعلان می‌کند (dedupe: یک‌بار به‌ازایِ کد)."""
    now = now or timezone.now()
    sent = 0
    qs = Campaign.objects.filter(status__in=(Campaign.Status.ACTIVE, Campaign.Status.COMPLETED), reminder_days_before_expiry__isnull=False)
    if store is not None:
        qs = qs.filter(store=store)
    for campaign in qs.select_related("store"):
        window_end = now + timedelta(days=campaign.reminder_days_before_expiry)
        issuances = campaign.issuances.filter(
            coupon__isnull=False, coupon__is_active=True, coupon__expires_at__gt=now, coupon__expires_at__lte=window_end,
        ).select_related("coupon", "customer")
        for issuance in issuances:
            coupon = issuance.coupon
            if coupon.used_count > 0:
                continue
            days_left = max(0, (coupon.expires_at - now).days)
            ctx = {**context_builders.coupon_context(campaign.store, issuance.customer, coupon, campaign_name=campaign.name),
                   "days_left": str(days_left)}
            rows = dispatch_event(
                "coupon.expiring", store=campaign.store, customer=issuance.customer, context=ctx,
                dedupe_key=f"expiring:{coupon.pk}", channels=campaign.channels or None,
                metadata={"campaign_id": campaign.pk, "issuance_id": issuance.pk},
            )
            sent += len(rows)
    return sent


# ------------------------------------------------------------------ زمان‌بند


def run_due_campaigns(now=None) -> dict:
    """نقطه‌ی ورودِ job دوره‌ای: کمپین‌هایِ ``SCHEDULED`` و ``OCCASION`` را اجرا می‌کند."""
    now = now or store_now()
    summary = {"campaigns": 0, "issued": 0, "errors": 0, "expired": 0}
    qs = Campaign.objects.filter(
        status=Campaign.Status.ACTIVE, trigger_type__in=(Campaign.Trigger.SCHEDULED, Campaign.Trigger.OCCASION),
    ).select_related("store")
    for campaign in qs:
        sync_status(campaign, now)
        if campaign.status != Campaign.Status.ACTIVE:
            summary["expired"] += 1
            continue
        try:
            if campaign.trigger_type == Campaign.Trigger.OCCASION:
                run = run_occasion_campaign(campaign, now.date())
            else:
                run = execute_campaign(campaign, trigger=CampaignRun.Trigger.SCHEDULED, now=now)
        except Exception:  # noqa: BLE001
            logger.exception("scheduled campaign %s failed", campaign.pk)
            summary["errors"] += 1
            continue
        summary["campaigns"] += 1
        summary["issued"] += run.issued
        summary["errors"] += run.errors
    summary["reminders"] = send_expiry_reminders(now=timezone.now())
    return summary


# ------------------------------------------------------------------ گزارش عملکرد


def performance(campaign: Campaign) -> dict:
    """شاخص‌هایِ عملکردِ یک کمپین: صدور، تحویل اعلان، استفاده (redemption)، نرخِ
    استفاده، مجموعِ تخفیف و فروشِ ناشی از کدها. همه فقط از دادهٔ همین کمپین."""
    from django.db.models import Count, Sum

    from apps.notifications.models import NotificationOutbox
    from apps.orders.models import CouponRedemption

    coupon_ids = list(campaign.issuances.exclude(coupon__isnull=True).values_list("coupon_id", flat=True).distinct())
    issued = campaign.issuances.count()
    redemptions = CouponRedemption.objects.filter(coupon_id__in=coupon_ids)
    by_status = dict(redemptions.values_list("status").annotate(n=Count("id")))
    counted = redemptions.filter(status__in=CouponRedemption.COUNTED_STATUSES)
    agg = counted.aggregate(discount=Sum("discount_amount"), revenue=Sum("order__grand_total"))
    redeemed_customers = counted.values("customer").distinct().count()
    notes = dict(
        NotificationOutbox.objects.filter(metadata__campaign_id=campaign.pk).values_list("status").annotate(n=Count("id"))
    )
    now = timezone.now()
    from apps.cart.models import Coupon

    expired = Coupon.objects.filter(pk__in=coupon_ids, expires_at__lte=now).count()
    return {
        "issued": issued,
        "coupons": len(coupon_ids),
        "redeemed": by_status.get("redeemed", 0) + by_status.get("refunded", 0),
        "reserved": by_status.get("reserved", 0),
        "released": by_status.get("released", 0),
        "redeemed_customers": redeemed_customers,
        "redemption_rate": round(100 * redeemed_customers / issued, 1) if issued else 0,
        "discount_total": agg["discount"] or 0,
        "revenue": agg["revenue"] or 0,
        "expired_coupons": expired,
        "notifications": notes,
        "notifications_sent": notes.get("sent", 0),
        "notifications_failed": notes.get("failed", 0) + notes.get("dead", 0),
        "notifications_skipped": notes.get("skipped", 0),
    }
