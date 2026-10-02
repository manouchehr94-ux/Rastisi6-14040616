"""مدیریت کد تخفیف — Store-owned (ADR-32).

هر عملیات این ماژول صریحاً روی ``store`` مشخص عمل می‌کند؛ هیچ کوئری‌ای
بدون فیلتر ``store`` روی ``Coupon`` اجرا نمی‌شود — این تنها لایه‌ای است که
دیدِ پنل مدیریت به کدهای تخفیف را می‌سازد.
"""

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.cart.models import Coupon
from apps.core.services.audit_service import record_audit_event


class CouponError(Exception):
    """خطای قابل‌نمایش هنگام مدیریت کد تخفیف."""


def list_coupons(store):
    return Coupon.objects.filter(store=store).order_by("-created_at")


def _validate_semantics(coupon: Coupon) -> None:
    """قواعدِ کسب‌وکارِ فراتر از ``full_clean`` (درصد، بازه‌ها، محدودیت‌ها)."""
    from apps.cart.services.coupon_rules import CouponRestrictionError, validate_restrictions

    if coupon.type == Coupon.Type.PERCENT and not (0 < coupon.value <= 100):
        raise CouponError("درصدِ تخفیف باید بین ۱ تا ۱۰۰ باشد.")
    if coupon.type == Coupon.Type.FIXED and coupon.value <= 0:
        raise CouponError("مبلغِ تخفیف باید مثبت باشد.")
    if coupon.max_discount is not None and coupon.max_discount <= 0:
        raise CouponError("سقفِ تخفیف باید مثبت باشد.")
    if coupon.starts_at and coupon.expires_at and coupon.expires_at <= coupon.starts_at:
        raise CouponError("انقضا باید بعد از تاریخِ فعال‌سازی باشد.")
    if coupon.max_order is not None and coupon.max_order < coupon.min_order:
        raise CouponError("حداکثرِ مبلغِ سبد نباید کمتر از حداقل باشد.")
    if coupon.min_items and coupon.max_items and coupon.max_items < coupon.min_items:
        raise CouponError("حداکثرِ تعدادِ اقلام نباید کمتر از حداقل باشد.")
    try:
        coupon.restrictions = validate_restrictions(coupon.restrictions)
    except CouponRestrictionError as exc:
        raise CouponError(str(exc)) from exc


@transaction.atomic
def create_coupon(store, *, actor=None, **fields) -> Coupon:
    coupon = Coupon(store=store, **fields)
    try:
        coupon.full_clean()
    except ValidationError as exc:
        raise CouponError("؛ ".join(sum(exc.message_dict.values(), []))) from exc
    _validate_semantics(coupon)
    coupon.save()
    record_audit_event(
        store=store, actor=actor, action_code="coupon.created",
        object_type="Coupon", object_id=coupon.pk, object_label=coupon.code,
        after={"type": coupon.type, "value": str(coupon.value)},
    )
    return coupon


@transaction.atomic
def update_coupon(coupon: Coupon, *, actor=None, **fields) -> Coupon:
    before = {"type": coupon.type, "value": str(coupon.value), "is_active": coupon.is_active}
    for key, value in fields.items():
        setattr(coupon, key, value)
    try:
        coupon.full_clean()
    except ValidationError as exc:
        raise CouponError("؛ ".join(sum(exc.message_dict.values(), []))) from exc
    _validate_semantics(coupon)
    coupon.save()
    record_audit_event(
        store=coupon.store, actor=actor, action_code="coupon.updated",
        object_type="Coupon", object_id=coupon.pk, object_label=coupon.code,
        before=before, after={"type": coupon.type, "value": str(coupon.value), "is_active": coupon.is_active},
    )
    return coupon


def toggle_coupon_active(coupon: Coupon, *, actor=None) -> Coupon:
    coupon.is_active = not coupon.is_active
    coupon.save(update_fields=["is_active", "updated_at"])
    record_audit_event(
        store=coupon.store, actor=actor, action_code="coupon.toggled",
        object_type="Coupon", object_id=coupon.pk, object_label=coupon.code,
        after={"is_active": coupon.is_active},
    )
    return coupon


def delete_coupon(coupon: Coupon, *, actor=None) -> None:
    store, code, pk = coupon.store, coupon.code, coupon.pk
    coupon.delete()
    record_audit_event(
        store=store, actor=actor, action_code="coupon.archived",
        object_type="Coupon", object_id=pk, object_label=code,
    )


def customer_coupons(store, customer):
    """کدهای اختصاصیِ یک مشتری در همین Store (برایِ «حسابِ من») با وضعیتِ
    محاسبه‌شده. کدِ مشتریِ دیگر یا Storeِ دیگر هرگز برنمی‌گردد."""
    from django.utils import timezone

    from apps.cart.services.pricing import coupon_is_applicable  # noqa: F401 — هم‌خانواده با منطقِ اعتبار
    from apps.notifications.services.context_builders import discount_amount_label

    now = timezone.now()
    rows = []
    for coupon in Coupon.objects.filter(store=store, customer=customer).order_by("-created_at"):
        if not coupon.is_active:
            state = "inactive"
        elif coupon.expires_at and coupon.expires_at <= now:
            state = "expired"
        elif coupon.starts_at and coupon.starts_at > now:
            state = "upcoming"
        elif coupon.usage_limit is not None and coupon.used_count >= coupon.usage_limit:
            state = "used"
        else:
            state = "active"
        rows.append({"coupon": coupon, "state": state, "label": discount_amount_label(coupon)})
    return rows
