"""دفترِ استفاده از کدِ تخفیف: رزرو، مصرف، آزادسازی.

* ``reserve_redemption`` — در تراکنشِ ثبتِ سفارش. سقفِ کل با یک
  compare-and-set اتمیک (``UPDATE ... WHERE used_count < usage_limit``) اعمال
  می‌شود؛ پس حتی دو سفارشِ همزمان هرگز سقف را رد نمی‌کنند — بازنده خطا
  می‌گیرد و سفارشش ساخته نمی‌شود. سقفِ هر مشتری زیرِ قفلِ ردیفِ کد
  (``select_for_update``) در ``lock_coupon`` بررسی می‌شود.
* ``mark_redeemed`` — پرداختِ موفق.
* ``release_redemption`` — لغوِ سفارش / پرداختِ ناموفق: ظرفیت برمی‌گردد.
* ``mark_refunded`` — استردادِ کاملِ سفارشِ پرداخت‌شده: ظرفیت برنمی‌گردد.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.cart.models import Coupon
from apps.orders.models import CouponRedemption

logger = logging.getLogger(__name__)
R = CouponRedemption.Status


class CouponUnavailableError(ValueError):
    """کد دیگر قابل‌استفاده نیست (مثلاً ظرفیتش همزمان تکمیل شد)."""


def lock_coupon(coupon_id: int) -> Coupon:
    """ردیفِ کد را قفل و تازه می‌خواند (روی SQLite بی‌اثر؛ روی Postgres
    سفارش‌هایِ همزمانِ همین کد را سریال می‌کند)."""
    return Coupon.objects.select_for_update().get(pk=coupon_id)


def _increment_used(coupon: Coupon) -> bool:
    qs = Coupon.objects.filter(pk=coupon.pk)
    if coupon.usage_limit is not None:
        qs = qs.filter(used_count__lt=F("usage_limit"))
    return qs.update(used_count=F("used_count") + 1) == 1


def _decrement_used(coupon_id: int) -> None:
    Coupon.objects.filter(pk=coupon_id, used_count__gt=0).update(used_count=F("used_count") - 1)


@transaction.atomic
def reserve_redemption(*, coupon: Coupon, order, customer, discount_amount) -> CouponRedemption:
    existing = CouponRedemption.objects.filter(order=order).first()
    if existing is not None:
        return existing
    if not _increment_used(coupon):
        raise CouponUnavailableError("ظرفیت استفاده از این کد تخفیف تکمیل شده است.")
    return CouponRedemption.objects.create(
        coupon=coupon, order=order, customer=customer, discount_amount=discount_amount, status=R.RESERVED,
    )


def _get(order) -> CouponRedemption | None:
    return CouponRedemption.objects.select_for_update(of=("self",)).filter(order=order).select_related("coupon").first()


@transaction.atomic
def mark_redeemed(order) -> CouponRedemption | None:
    redemption = _get(order)
    if redemption is None or redemption.status in (R.REDEEMED, R.REFUNDED):
        return redemption
    if redemption.status == R.RELEASED:
        # پرداختِ موفق پس از یک پرداختِ ناموفقِ قبلی: ظرفیت را (در صورتِ امکان) دوباره می‌گیریم.
        if not _increment_used(redemption.coupon):
            logger.warning("Coupon %s capacity exhausted while re-redeeming order %s", redemption.coupon.code, order.code)
    redemption.status = R.REDEEMED
    redemption.redeemed_at = timezone.now()
    redemption.released_at = None
    redemption.release_reason = ""
    redemption.save(update_fields=["status", "redeemed_at", "released_at", "release_reason", "updated_at"])
    from apps.notifications.services import business_events
    business_events.coupon_redeemed(order, redemption.coupon, redemption.discount_amount)
    return redemption


@transaction.atomic
def release_redemption(order, *, reason: str) -> CouponRedemption | None:
    redemption = _get(order)
    if redemption is None or redemption.status in (R.RELEASED, R.REFUNDED):
        return redemption
    redemption.status = R.RELEASED
    redemption.released_at = timezone.now()
    redemption.release_reason = reason
    redemption.save(update_fields=["status", "released_at", "release_reason", "updated_at"])
    _decrement_used(redemption.coupon_id)
    return redemption


@transaction.atomic
def mark_refunded(order) -> CouponRedemption | None:
    redemption = _get(order)
    if redemption is None or redemption.status != R.REDEEMED:
        return redemption
    redemption.status = R.REFUNDED
    redemption.save(update_fields=["status", "updated_at"])
    return redemption
