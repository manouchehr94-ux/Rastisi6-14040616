"""Delivery validity policy: WHEN a queued notification may still be delivered, per event category and per event.

Two independent rules are checked immediately before ANY send (worker, manual retry, revival after a sender recovers):

1. **Hard TTL** (``ttl_hours``, from the row's creation): after it the message is never delivered. The row is kept
   as ``EXPIRED`` (visible in history and in the platform "needs attention" list) — it is never deleted, and an
   expired row cannot be retried or revived. Retrying would otherwise deliver stale content.
2. **Contextual validity** (read-only checks against the *current* business state): a message whose premise no longer
   holds is not sent and is kept as ``SKIPPED`` with ``stale:<reason>`` (e.g. "your payment failed" after the order was
   paid; "your coupon expires soon" after it expired; a "shipped" notice after the order was cancelled).

``hold_hours`` is a separate, shorter window: how long a message waits for an inactive sender / rate limit before it
becomes a visible failed (``DEAD``) row that an operator can retry — retry is only possible while the TTL allows it.

OTPs are not part of this engine at all (phone-possession codes use the dedicated OTP path with their own few-minute
validity); ``test_expiry`` asserts that no event here carries a code/token/reset-link variable.

The validators only READ order/coupon state. They never write, and they never touch payment, refund or settlement
logic — they consume ``Order.status`` / ``Order.payment_status`` and ``Coupon`` validity fields as plain data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.notifications import events as ev


@dataclass(frozen=True)
class Policy:
    ttl_hours: int
    hold_hours: int
    validator: str = ""


@dataclass(frozen=True)
class Verdict:
    ok: bool
    kind: str = ""      # "expired" (hard TTL) | "stale" (context no longer valid)
    reason: str = ""    # machine reason; stored as last_error / skip_reason


OK = Verdict(True)


def _hold_default() -> int:
    return int(getattr(settings, "RASTISI_EMAIL_HOLD_MAX_HOURS", 72))


def _hold_promotional() -> int:
    return int(getattr(settings, "RASTISI_EMAIL_HOLD_MAX_HOURS_PROMOTIONAL", 24))


#: per-event overrides (everything else uses its category default, see ``policy_for``)
EVENT_POLICIES = {
    # --- order lifecycle: a status notice is only useful while it is still the current status ---
    "order.created": (168, "order_not_canceled"),
    "order.processing": (72, "order_not_superseded"),
    "order.shipped": (168, "order_shipped_still_current"),
    "order.delivered": (168, "order_not_canceled"),
    "order.canceled": (168, ""),
    # --- payment results (read-only consumers of the financial engine's state) ---
    "payment.succeeded": (168, ""),
    "payment.failed": (72, "payment_still_unresolved"),
    "refund.completed": (168, ""),
    "return.requested": (168, ""), "return.approved": (168, ""), "return.rejected": (168, ""),
    "coupon.redeemed": (72, ""),
    # --- staff alerts ---
    "staff.order_created": (72, ""), "staff.review_created": (72, ""),
    "staff.return_requested": (168, ""), "staff.late_payment": (168, ""), "campaign.activated": (72, ""),
    # --- platform -> store admin: only meaningful while the sender is still in the state being reported ---
    "platform.email_sender_active": (72, "sender_still_active"),
    "platform.email_sender_problem": (72, "sender_still_problem"),
    # --- security: short; the content is an alert about a past change, not an actionable link ---
    "account.sensitive_changed": (48, ""),
}

#: promotional events that carry a coupon: valid only while that coupon can still be used
COUPON_BOUND_PREFIXES = ("coupon.issued", "coupon.expiring", "campaign.offer_", "occasion.", "reward.")


def policy_for(event_key: str) -> Policy:
    event = ev.EVENTS.get(event_key)
    category = event.category if event else ev.TRANSACTIONAL
    if event_key in EVENT_POLICIES:
        ttl, validator = EVENT_POLICIES[event_key]
        hold = {ev.SECURITY: 24}.get(category, _hold_default())
        return Policy(ttl, min(hold, ttl), validator)
    if category == ev.PROMOTIONAL:
        validator = "coupon_still_usable" if event_key.startswith(COUPON_BOUND_PREFIXES) else ""
        return Policy(24, _hold_promotional(), validator)
    if category == ev.SECURITY:
        return Policy(48, 24)
    return Policy(168, _hold_default())


# ----------------------------------------------------------------------------------------------------- validators
def _order(n):
    return n.order if n.order_id else None


def _order_not_canceled(n, now):
    order = _order(n)
    return "order_canceled" if order is not None and order.status == "canceled" else ""


def _order_not_superseded(n, now):
    order = _order(n)
    if order is None:
        return ""
    return f"order_{order.status}" if order.status in ("shipped", "delivered", "canceled") else ""


def _order_shipped_still_current(n, now):
    order = _order(n)
    if order is None:
        return ""
    return f"order_{order.status}" if order.status in ("delivered", "canceled") else ""


def _payment_still_unresolved(n, now):
    order = _order(n)
    if order is None:
        return ""
    if order.status == "canceled":
        return "order_canceled"
    return "payment_resolved" if order.payment_status in ("paid", "refunded") else ""


def _coupon_for(n):
    from apps.cart.models import Coupon

    meta = n.metadata or {}
    coupon_id = meta.get("coupon_id")
    if not coupon_id and meta.get("issuance_id"):
        from apps.engagement.models import CampaignIssuance

        coupon_id = CampaignIssuance.objects.filter(pk=meta["issuance_id"]).values_list("coupon_id", flat=True).first()
    return Coupon.objects.filter(pk=coupon_id, store_id=n.store_id).first() if coupon_id else None


def _coupon_still_usable(n, now):
    coupon = _coupon_for(n)
    if coupon is None:
        return ""  # greeting / announcement without a code: only the TTL applies
    if not coupon.is_active:
        return "coupon_inactive"
    if coupon.expires_at is not None and coupon.expires_at <= now:
        return "coupon_expired"
    if coupon.usage_limit is not None and coupon.used_count >= coupon.usage_limit:
        return "coupon_used_up"
    return ""


def _sender_state(n):
    from apps.notifications.models import EmailSenderIdentity

    identity = EmailSenderIdentity.objects.filter(store_id=n.store_id).first()
    return identity.status if identity else ""


def _sender_still_active(n, now):
    return "" if _sender_state(n) == "active" else "sender_no_longer_active"


def _sender_still_problem(n, now):
    return "" if _sender_state(n) != "active" else "sender_recovered"


VALIDATORS = {
    "order_not_canceled": _order_not_canceled,
    "order_not_superseded": _order_not_superseded,
    "order_shipped_still_current": _order_shipped_still_current,
    "payment_still_unresolved": _payment_still_unresolved,
    "coupon_still_usable": _coupon_still_usable,
    "sender_still_active": _sender_still_active,
    "sender_still_problem": _sender_still_problem,
}


def evaluate(notification, now=None) -> Verdict:
    """Is it still legitimate to deliver this row right now? Pure read; safe to call repeatedly."""
    if not notification.event_key:
        return OK  # generic enqueue() rows (in-app security notices etc.) keep their pre-existing behaviour
    now = now or timezone.now()
    policy = policy_for(notification.event_key)
    if notification.created_at and now - notification.created_at > timedelta(hours=policy.ttl_hours):
        return Verdict(False, "expired", "ttl_exceeded")
    if notification.is_test:
        return OK
    validator = VALIDATORS.get(policy.validator)
    if validator is not None:
        reason = validator(notification, now)
        if reason:
            return Verdict(False, "stale", reason)
    return OK


REASON_TEXT = {
    "ttl_exceeded": "مهلتِ اعتبارِ این پیام گذشته است و دیگر ارسال نمی‌شود.",
    "order_canceled": "سفارش لغو شده است.",
    "order_shipped": "وضعیتِ سفارش جلوتر رفته است (ارسال شده).",
    "order_delivered": "وضعیتِ سفارش جلوتر رفته است (تحویل شده).",
    "payment_resolved": "پرداختِ سفارش در این فاصله تعیین تکلیف شده است.",
    "coupon_expired": "کدِ تخفیف منقضی شده است.",
    "coupon_inactive": "کدِ تخفیف غیرفعال شده است.",
    "coupon_used_up": "سقفِ استفاده از کدِ تخفیف تکمیل شده است.",
    "sender_no_longer_active": "فرستنده‌ی ایمیل دیگر فعال نیست.",
    "sender_recovered": "مشکلِ فرستنده‌ی ایمیل برطرف شده است.",
}


def reason_text(reason: str) -> str:
    return REASON_TEXT.get((reason or "").removeprefix("stale:"), "این پیام دیگر معتبر نیست.")


VALIDATOR_TEXT = {
    "": "—",
    "order_not_canceled": "سفارش لغو نشده باشد",
    "order_not_superseded": "سفارش هنوز «در حال پردازش» باشد",
    "order_shipped_still_current": "سفارش لغو/تحویل نشده باشد",
    "payment_still_unresolved": "پرداخت هنوز تعیین‌تکلیف نشده و سفارش لغو نشده باشد",
    "coupon_still_usable": "کد تخفیف فعال، منقضی‌نشده و دارای سقفِ باقی‌مانده باشد",
    "sender_still_active": "فرستنده‌ی ایمیل هنوز فعال باشد",
    "sender_still_problem": "مشکلِ فرستنده هنوز برطرف نشده باشد",
}


def to_markdown() -> str:
    """The per-event delivery-validity table, computed from the policy code (docs cannot drift)."""
    out = ["| رویداد | دسته | مهلتِ اعتبار (TTL) | مهلتِ نگه‌داری (hold) | شرطِ اعتبارِ بافتاری |", "|---|---|---|---|---|"]
    for key, event in ev.EVENTS.items():
        p = policy_for(key)
        out.append(f"| `{key}` | {ev.CATEGORY_LABELS[event.category]} | {p.ttl_hours} ساعت | {p.hold_hours} ساعت | "
                   f"{VALIDATOR_TEXT.get(p.validator, p.validator)} |")
    return "\n".join(out)
