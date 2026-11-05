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
    return locked
