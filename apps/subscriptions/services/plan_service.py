"""سرویسِ مدیریتِ پلن و نسخه‌ی پلن — انتشار/بازنشستگی و اجرایِ تغییرناپذیریِ
نسخه‌ی منتشرشده (ADR-63). این عملیات platform-level هستند و از Django Admin
یا تست فراخوانی می‌شوند؛ هیچ مسیرِ Merchant به این‌جا نمی‌رسد."""

from django.db import transaction
from django.utils import timezone

from decimal import Decimal, InvalidOperation

from apps.subscriptions.models import EntitlementDefinition, PlanEntitlement, PlanVersion, PlanVersionPrice

# ``actor`` روی امضایِ توابع نگه داشته شده تا وقتی یک Audit Logِ پلتفرمی
# اضافه شد بدونِ تغییرِ فراخوان‌ها وصل شود؛ عملیاتِ platform-level فعلاً از
# طریقِ Django Admin's own LogEntry ردیابی می‌شوند.


class PlanServiceError(Exception):
    """خطای قابل‌نمایشِ عملیاتِ پلن — انتشارِ نامعتبر، ویرایشِ نسخه‌ی منتشرشده و... ."""


def _audit(actor, action, version, *, before=None, after=None, **meta):
    """ممیزیِ پلتفرم (کنشگر، زمان، قبل/بعد). actor=None برایِ فراخوانیِ سیستمی/تست مجاز است."""
    from apps.portal.services.platform_config_service import record_platform_audit_event

    record_platform_audit_event(
        actor=actor, action_code=f"platform_admin.{action}", object_type="PlanVersion", object_id=version.pk,
        object_label=f"{version.plan.code} v{version.version_number}", before=before, after=after, metadata=meta,
    )


def _entitlement_summary(version) -> dict:
    out = {}
    for pe in PlanEntitlement.objects.filter(plan_version=version).select_related("entitlement"):
        if not pe.is_enabled:
            value = "off"
        elif pe.is_unlimited:
            value = "unlimited"
        elif pe.integer_limit is not None:
            value = pe.integer_limit
        elif pe.decimal_limit is not None:
            value = str(pe.decimal_limit)
        else:
            value = "on"
        out[pe.entitlement.key] = value
    return out


@transaction.atomic
def create_plan_version(plan, **fields) -> PlanVersion:
    """نسخه‌ی پیش‌نویسِ تازه‌ای می‌سازد؛ ``version_number`` را خودکار (یکی
    بیشتر از بیشترین نسخه‌ی موجودِ همان پلن) تعیین می‌کند مگر صراحتاً داده
    شود."""
    if "version_number" not in fields:
        last = plan.versions.order_by("-version_number").values_list("version_number", flat=True).first()
        fields["version_number"] = (last or 0) + 1
    fields.setdefault("status", PlanVersion.Status.DRAFT)
    return PlanVersion.objects.create(plan=plan, **fields)


@transaction.atomic
def set_plan_entitlement(plan_version, entitlement_key, **values) -> PlanEntitlement:
    """یک ``PlanEntitlement`` را رویِ یک نسخه‌ی *پیش‌نویس* تنظیم/به‌روزرسانی
    می‌کند — نسخه‌ی منتشرشده تغییرناپذیر است (ADR-63). وضعیت همیشه تازه از
    دیتابیس خوانده می‌شود، نه از instanceِ احتمالاً کهنه‌ی حافظه."""
    current_status = PlanVersion.objects.filter(pk=plan_version.pk).values_list("status", flat=True).first()
    if current_status != PlanVersion.Status.DRAFT:
        raise PlanServiceError("فقط نسخه‌ی «پیش‌نویس» قابلِ ویرایشِ Entitlement است.")
    entitlement = EntitlementDefinition.objects.filter(key=entitlement_key).first()
    if entitlement is None:
        raise PlanServiceError(f"تعریفِ حق‌دسترسیِ «{entitlement_key}» وجود ندارد.")
    obj, _created = PlanEntitlement.objects.update_or_create(
        plan_version=plan_version, entitlement=entitlement, defaults=values,
    )
    obj.full_clean()
    obj.save()
    return obj


def _require_draft(plan_version):
    current_status = PlanVersion.objects.filter(pk=plan_version.pk).values_list("status", flat=True).first()
    if current_status != PlanVersion.Status.DRAFT:
        raise PlanServiceError("فقط نسخه‌ی «پیش‌نویس» قابلِ ویرایش است؛ برایِ تغییر نسخه‌ی تازه بسازید.")


def _money(value, field):
    try:
        amount = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        raise PlanServiceError(f"{field} معتبر نیست.")
    if amount < 0 or amount != amount.to_integral_value():
        raise PlanServiceError(f"{field} باید عددِ صحیحِ غیرمنفی باشد.")
    return amount


@transaction.atomic
def set_version_price(plan_version, billing_interval, *, price, compare_at_price=None, label="") -> PlanVersionPrice:
    """قیمتِ *اضافیِ* یک دوره را رویِ نسخه‌ی پیش‌نویس تنظیم می‌کند. دوره‌ی اصلیِ نسخه همان
    ``billing_interval/display_price`` است و اینجا ثبت نمی‌شود. نسخه‌ی منتشرشده تغییرناپذیر است (ADR-63)."""
    _require_draft(plan_version)
    if billing_interval not in PlanVersion.PAID_INTERVALS:
        raise PlanServiceError("دوره‌ی نامعتبر.")
    version = PlanVersion.objects.get(pk=plan_version.pk)
    amount = _money(price, "قیمت")
    if billing_interval == version.billing_interval and amount != Decimal(version.display_price):
        raise PlanServiceError("قیمتِ گزینه‌ی اصلی باید با قیمتِ خودِ نسخه برابر باشد.")
    compare = _money(compare_at_price, "قیمتِ قبل از تخفیف") if compare_at_price not in (None, "") else None
    from django.core.exceptions import ValidationError

    row = PlanVersionPrice.objects.filter(plan_version=version, billing_interval=billing_interval).first() or PlanVersionPrice(
        plan_version=version, billing_interval=billing_interval,
    )
    row.price, row.compare_at_price, row.label = amount, compare, (label or "")[:60]
    try:
        row.full_clean()
    except ValidationError as exc:
        raise PlanServiceError("؛ ".join(m for msgs in exc.message_dict.values() for m in msgs)) from exc
    row.save()
    return row


@transaction.atomic
def clear_version_price(plan_version, billing_interval) -> None:
    _require_draft(plan_version)
    PlanVersionPrice.objects.filter(plan_version_id=plan_version.pk, billing_interval=billing_interval).delete()


def validate_for_publication(plan_version) -> list:
    """خطاهایِ مانعِ انتشار (فهرستِ پیام). انتشار فقط وقتی مجاز است که همه‌ی قیمت‌ها منسجم باشند."""
    errors = []
    version = PlanVersion.objects.get(pk=plan_version.pk)
    options = version.price_options()
    for interval, option in options.items():
        compare = option.get("compare_at")
        if compare is not None and compare < option["price"]:
            errors.append(f"قیمتِ قبل از تخفیفِ دوره‌ی «{interval}» کمتر از قیمتِ فعلی است.")
    return errors


@transaction.atomic
def publish_plan_version(plan_version, *, actor=None) -> PlanVersion:
    """نسخه‌ی پیش‌نویس را منتشر می‌کند — پس از این، شرایطِ آن تغییرناپذیر
    می‌شود (ADR-63). idempotent: انتشارِ دوباره‌ی یک نسخه‌ی از پیش منتشرشده
    بی‌اثر است."""
    locked = PlanVersion.objects.select_for_update().get(pk=plan_version.pk)
    if locked.status == PlanVersion.Status.PUBLISHED:
        return locked
    if locked.status != PlanVersion.Status.DRAFT:
        raise PlanServiceError("فقط نسخه‌ی «پیش‌نویس» قابلِ انتشار است.")
    problems = validate_for_publication(locked)
    if problems:
        raise PlanServiceError("؛ ".join(problems))
    locked.status = PlanVersion.Status.PUBLISHED
    locked.published_at = timezone.now()
    if locked.effective_from is None:
        locked.effective_from = locked.published_at
    locked.save(update_fields=["status", "published_at", "effective_from", "updated_at"])
    _audit(actor, "plan_version_published", locked, before={"status": "draft"},
           after={"status": "published", "version": locked.version_number, "entitlements": _entitlement_summary(locked)})
    return locked


@transaction.atomic
def retire_plan_version(plan_version, *, actor=None) -> PlanVersion:
    """نسخه‌ی منتشرشده را بازنشسته می‌کند — اشتراک‌هایِ موجود روی این نسخه
    دست‌نخورده می‌مانند (ADR-63)؛ فقط اشتراکِ *تازه* دیگر نمی‌گیرد."""
    locked = PlanVersion.objects.select_for_update().get(pk=plan_version.pk)
    if locked.status == PlanVersion.Status.RETIRED:
        return locked
    if locked.status != PlanVersion.Status.PUBLISHED:
        raise PlanServiceError("فقط نسخه‌ی «منتشرشده» قابلِ بازنشستگی است.")
    locked.status = PlanVersion.Status.RETIRED
    locked.retired_at = timezone.now()
    locked.save(update_fields=["status", "retired_at", "updated_at"])
    _audit(actor, "plan_version_retired", locked, before={"status": "published"}, after={"status": "retired"})
    return locked


# ---------------------------------------------------------------------------------------------------- پیش‌نویس

_COPIED_FIELDS = ("currency", "billing_interval", "display_price", "trial_days", "trial_once_per_store", "grace_period_days",
                  "public_description_snapshot")
_EDITABLE_FIELDS = ("billing_interval", "display_price", "trial_days", "trial_once_per_store", "grace_period_days")


@transaction.atomic
def get_or_create_draft(plan, *, actor=None) -> PlanVersion:
    """پیش‌نویسِ پلن را برمی‌گرداند؛ اگر نبود، از آخرین نسخه (منتشرشده/بازنشسته) کپی می‌سازد — قیمت‌ها و *همه‌ی* حق‌دسترسی‌ها
    (از جمله قابلیت‌هایِ «به‌زودی») همراه می‌آیند تا نسخه‌ی تازه چیزی را بی‌صدا از دست ندهد. نسخه‌ی منتشرشده دست نمی‌خورد."""
    from apps.subscriptions.models import Plan

    Plan.objects.select_for_update().get(pk=plan.pk)
    draft = plan.versions.filter(status=PlanVersion.Status.DRAFT).order_by("-version_number").first()
    if draft is not None:
        return draft
    source = plan.versions.exclude(status=PlanVersion.Status.DRAFT).order_by("-version_number").first()
    fields = {name: getattr(source, name) for name in _COPIED_FIELDS} if source else {}
    draft = create_plan_version(plan, **fields)
    if source is not None:
        for row in PlanVersionPrice.objects.filter(plan_version=source):
            PlanVersionPrice.objects.create(plan_version=draft, billing_interval=row.billing_interval, price=row.price,
                                            compare_at_price=row.compare_at_price, label=row.label)
        for pe in PlanEntitlement.objects.filter(plan_version=source):
            PlanEntitlement.objects.create(
                plan_version=draft, entitlement=pe.entitlement, is_enabled=pe.is_enabled, is_unlimited=pe.is_unlimited,
                integer_limit=pe.integer_limit, decimal_limit=pe.decimal_limit, text_value=pe.text_value,
            )
    _audit(actor, "plan_draft_created", draft, after={"cloned_from": source.version_number if source else None,
                                                    "entitlements": _entitlement_summary(draft)})
    return draft


@transaction.atomic
def update_draft_version(plan_version, *, actor=None, **fields) -> PlanVersion:
    """مشخصاتِ نسخه‌ی **پیش‌نویس** را در جا ویرایش می‌کند (بدونِ ساختنِ نسخه‌ی اضافه). نسخه‌ی منتشرشده تغییرناپذیر است."""
    _require_draft(plan_version)
    version = PlanVersion.objects.select_for_update().get(pk=plan_version.pk)
    before = {name: str(getattr(version, name)) for name in fields if name in _EDITABLE_FIELDS}
    for name, value in fields.items():
        if name not in _EDITABLE_FIELDS:
            raise PlanServiceError(f"فیلدِ «{name}» قابلِ ویرایش نیست.")
        if name == "display_price":
            value = _money(value, "قیمت")
        elif name in ("trial_days", "grace_period_days"):
            try:
                value = int(value)
            except (TypeError, ValueError):
                raise PlanServiceError("عددِ روز معتبر نیست.")
            if value < 0:
                raise PlanServiceError("عددِ روز نمی‌تواند منفی باشد.")
        elif name == "billing_interval" and value not in PlanVersion.BillingInterval.values:
            raise PlanServiceError("دوره‌ی نامعتبر.")
        setattr(version, name, value)
    version.save()
    _audit(actor, "plan_draft_updated", version, before=before, after={name: str(getattr(version, name)) for name in before})
    return version


# ---------------------------------------------------------------------------------------------------- بایگانی

@transaction.atomic
def set_plan_archived(plan, *, archived, actor=None):
    """پلن را بایگانی/بازگردانی می‌کند. بایگانی فقط *فروشِ تازه* و نمایشِ عمومی را می‌بندد؛ اشتراک‌هایِ موجود، تمدید، صورت‌حساب و
    حق‌دسترسیِ مشترکان دست‌نخورده می‌ماند (آن‌ها به ``PlanVersion`` وصل‌اند، نه به وضعیتِ فعالِ پلن).
    پلنِ پیش‌فرضِ ثبت‌نام (``RASTISI_DEFAULT_PLAN_CODE``) بایگانی نمی‌شود تا فروشگاهِ تازه بی‌پلن نماند."""
    from django.conf import settings

    from apps.subscriptions.models import Plan, StoreSubscription

    locked = Plan.objects.select_for_update().get(pk=plan.pk)
    if archived and locked.code == (getattr(settings, "RASTISI_DEFAULT_PLAN_CODE", "") or None):
        raise PlanServiceError("این پلنِ پیش‌فرضِ ثبت‌نام است؛ ابتدا پلنِ پیش‌فرض را در تنظیمات عوض کنید.")
    before = {"is_active": locked.is_active}
    locked.is_active = not archived
    locked.save(update_fields=["is_active", "updated_at"])
    subscribers = StoreSubscription.objects.filter(plan_version__plan=locked, is_current=True).count()
    from apps.portal.services.platform_config_service import record_platform_audit_event

    record_platform_audit_event(
        actor=actor, action_code="platform_admin.plan_archived" if archived else "platform_admin.plan_unarchived",
        object_type="Plan", object_id=locked.pk, object_label=locked.name, before=before, after={"is_active": locked.is_active},
        metadata={"current_subscribers_unaffected": subscribers},
    )
    return locked


# ---------------------------------------------------------------------------------------------------- مهاجرتِ مشترکان

def plan_migration_preview(from_version, to_version):
    """پیش‌نمایشِ مهاجرتِ *صریح*: چه تعداد مشترک می‌روند و چه حق‌دسترسی‌هایی کم/زیاد می‌شود (هیچ تغییری اعمال نمی‌شود)."""
    from apps.subscriptions.models import StoreSubscription

    if from_version.plan_id != to_version.plan_id:
        raise PlanServiceError("مهاجرتِ صریح فقط بینِ نسخه‌هایِ یک پلن است.")
    old, new = _entitlement_summary(from_version), _entitlement_summary(to_version)
    lost = sorted(k for k, v in old.items() if v not in ("off",) and new.get(k, "off") == "off")
    gained = sorted(k for k, v in new.items() if v != "off" and old.get(k, "off") == "off")
    count = StoreSubscription.objects.filter(plan_version=from_version, is_current=True).count()
    return {"subscribers": count, "lost": lost, "gained": gained, "changed": sorted(k for k in old if k in new and old[k] != new[k])}


def migrate_subscribers(from_version, to_version, *, actor, reason, accept_losses=False):
    """مهاجرتِ صریح و حسابرسی‌شده‌ی مشترکانِ جاری از یک نسخه‌ی پلن به نسخه‌ی منتشرشده‌ی دیگرِ همان پلن.

    پیش‌فرضِ محصول *grandfathering* است (مشترکان روی نسخه‌ی خودشان می‌مانند)؛ این تابع فقط با دلیلِ ثبت‌شده اجرا می‌شود و اگر نسخه‌ی
    مقصد حق‌دسترسی‌ای را از مشترکان بگیرد، بدونِ تأییدِ صریحِ ``accept_losses`` رد می‌شود (حذفِ بی‌صدای دسترسیِ قراردادی ممنوع)."""
    from apps.subscriptions.models import StoreSubscription
    from apps.subscriptions.services import subscription_service

    reason = (reason or "").strip()
    if not reason:
        raise PlanServiceError("برایِ مهاجرتِ مشترکان ثبتِ دلیل الزامی است.")
    preview = plan_migration_preview(from_version, to_version)
    if to_version.status != PlanVersion.Status.PUBLISHED:
        raise PlanServiceError("نسخه‌ی مقصد باید منتشرشده باشد.")
    if preview["lost"] and not accept_losses:
        raise PlanServiceError("این مهاجرت دسترسی‌هایی را از مشترکان می‌گیرد: " + "، ".join(preview["lost"]) + " — تأییدِ صریح لازم است.")
    moved = 0
    for sub in StoreSubscription.objects.filter(plan_version=from_version, is_current=True).order_by("pk"):
        subscription_service.change_plan_version(sub, to_version, actor=actor, reason=reason, idempotency_key=f"migrate:{from_version.pk}:{to_version.pk}:{sub.pk}")
        moved += 1
    from apps.portal.services.platform_config_service import record_platform_audit_event

    record_platform_audit_event(
        actor=actor, action_code="platform_admin.subscribers_migrated", object_type="Plan", object_id=from_version.plan_id,
        object_label=from_version.plan.name, before={"version": from_version.version_number}, after={"version": to_version.version_number},
        metadata={"moved": moved, "lost": preview["lost"], "gained": preview["gained"], "reason": reason[:200]},
    )
    return moved
