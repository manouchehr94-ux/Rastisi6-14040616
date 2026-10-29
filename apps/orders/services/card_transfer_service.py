"""کارت‌به‌کارت — ثبتِ اطلاعاتِ واریز توسطِ مشتری و تأیید/ردِ دستیِ مدیر.

* مشتری فقط ۴ رقمِ آخرِ کارتِ مبدأ و شماره‌ی پیگیری را وارد می‌کند؛ شماره‌ی کاملِ کارت، CVV2 و رمز هرگز دریافت یا ذخیره نمی‌شود
  (ورودیِ شبیهِ شماره‌کارت رد می‌شود). شماره‌ی پیگیری به‌تنهایی مدرکِ پرداخت نیست.
* ثبتِ اطلاعات سفارش را «پرداخت‌شده» نمی‌کند: ``Order.payment_status`` در ``pending`` می‌ماند (انقضا/COD/lifecycle دست‌نخورده) و «در انتظار
  بررسیِ پرداخت» از وضعیتِ ثبت‌ها مشتق می‌شود.
* تأیید *تنها* از مسیرِ موجودِ ``lifecycle.apply_payment_success`` انجام می‌شود (UPDATE شرطیِ ``pending→paid``، تراکنشِ OK، مصرفِ کد،
  رویدادِ اعلان، حرکت به PROCESSING) — مسیرِ موازی نداریم. هر تصمیم زیرِ قفلِ ردیفِ ثبت و سفارش، اتمیک، idempotent و حسابرسی‌شده است."""

from __future__ import annotations

import re
from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.services.audit_service import record_audit_event
from apps.core.utils import normalize_digits
from apps.orders.gateways.card_to_card import luhn_valid
from apps.orders.models import CardTransferSubmission, Order, PaymentAttempt, PaymentGatewayConfig, Transaction
from apps.orders.services.lifecycle import apply_payment_success

GATEWAY_CODE = "card_to_card"
MAX_SUBMISSIONS_PER_ORDER = 3

S = CardTransferSubmission.Status


class CardTransferError(ValueError):
    """ورودی/وضعیتِ نامعتبر — پیام برایِ نمایش به کاربر امن است."""


class AlreadyDecided(CardTransferError):
    """این ثبت قبلاً تصمیم‌گیری شده؛ تکرارِ تصمیم هیچ اثری ندارد (idempotent)."""


class DuplicateTracking(CardTransferError):
    """همین شماره‌ی پیگیری پیش‌تر برایِ سفارشِ دیگری تأیید شده است."""


@dataclass(frozen=True)
class Destination:
    card: str
    holder: str
    bank: str
    sheba: str

    @property
    def card_grouped(self) -> str:
        return " ".join(self.card[i:i + 4] for i in range(0, len(self.card), 4))

    @property
    def last4(self) -> str:
        return self.card[-4:]


# ───────────────────────────── پیکربندی و وضعیتِ سفارش ─────────────────────────────

def active_config(store) -> PaymentGatewayConfig | None:
    config = PaymentGatewayConfig.objects.filter(store=store, gateway_code=GATEWAY_CODE, is_active=True).first()
    return config if config is not None and config.can_activate else None


def destination_for(config: PaymentGatewayConfig) -> Destination:
    from apps.orders.gateways.card_to_card import clean_card_number

    creds = config.get_credentials()
    return Destination(
        card=clean_card_number(creds.get("destination_card")), holder=str(creds.get("holder_name") or "").strip(),
        bank=str(creds.get("bank_name") or "").strip(), sheba=re.sub(r"\s", "", str(creds.get("sheba") or "")).upper(),
    )


def is_card_transfer_order(order: Order) -> bool:
    return bool(order.payment_gateway_id) and order.payment_gateway.slug == GATEWAY_CODE


def review_state(order: Order) -> str:
    """وضعیتِ مشتق‌شده‌یِ سفارشِ کارت‌به‌کارت: ``""`` (سفارشِ دیگر)، ``awaiting_transfer`` (هنوز اطلاعاتی ثبت نشده)،
    ``under_review`` («در انتظار بررسی پرداخت»)، ``rejected`` (آخرین ثبت رد شد)، ``approved``."""
    if not is_card_transfer_order(order):
        return ""
    if order.payment_status == Order.PaymentStatus.PAID:
        return "approved"
    latest = order.card_transfers.order_by("-created_at", "-pk").first()
    if latest is None:
        return "awaiting_transfer"
    return {S.SUBMITTED: "under_review", S.REJECTED: "rejected", S.APPROVED: "approved"}[latest.status]


REVIEW_LABELS = {
    "awaiting_transfer": "در انتظار واریز و ثبت اطلاعات",
    "under_review": "در انتظار بررسی پرداخت",
    "rejected": "پرداخت رد شد — ثبت دوباره",
    "approved": "پرداخت تأیید شد",
}


# ───────────────────────────── اعتبارسنجیِ ورودیِ مشتری ─────────────────────────────

_TRACKING_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z\-_/]{3,39}$")


def clean_last4(raw) -> str:
    value = normalize_digits(str(raw or "")).strip()
    if len(re.sub(r"\D", "", value)) > 4 or not re.fullmatch(r"\d{4}", value):
        raise CardTransferError("فقط ۴ رقمِ آخرِ کارتِ مبدأ را وارد کنید (شماره‌ی کاملِ کارت را هرگز وارد نکنید).")
    return value


def clean_tracking(raw) -> str:
    value = normalize_digits(str(raw or "")).strip().replace(" ", "")
    if not _TRACKING_RE.match(value):
        raise CardTransferError("شماره‌ی پیگیری نامعتبر است (۴ تا ۴۰ حرف/عدد؛ بدونِ فاصله).")
    digits = re.sub(r"\D", "", value)
    if value.isdigit() and 13 <= len(digits) <= 19 and luhn_valid(digits):
        raise CardTransferError("این مقدار شبیهِ شماره‌ی کارت است. شماره‌ی کارت را وارد نکنید؛ فقط شماره‌ی پیگیریِ رسیدِ بانکی را بنویسید.")
    return value


# ───────────────────────────── ثبتِ اطلاعاتِ واریز ─────────────────────────────

def ensure_attempt(order: Order, config: PaymentGatewayConfig) -> PaymentAttempt:
    """تلاشِ بازِ این سفارش را برمی‌گرداند یا می‌سازد (``PENDING``؛ هرگز ``SUCCEEDED`` پیش از تأییدِ مدیر)."""
    attempt = order.payment_attempts.filter(gateway_config=config, status=PaymentAttempt.Status.PENDING).order_by("-pk").first()
    if attempt is None:
        attempt = PaymentAttempt.objects.create(
            store=order.store, order=order, gateway_config=config, amount=order.grand_total, currency="TOMAN",
            status=PaymentAttempt.Status.PENDING, gateway_track_id=f"c2c-{order.code}-{order.payment_attempts.count() + 1}",
            initiated_at=timezone.now(),
        )
    return attempt


@transaction.atomic
def submit(order_id: int, *, store, customer, source_last4, tracking_number) -> CardTransferSubmission:
    last4, tracking = clean_last4(source_last4), clean_tracking(tracking_number)
    order = Order.objects.select_for_update().select_related("payment_gateway").get(pk=order_id, store=store)
    if order.customer_id != customer.pk:
        raise CardTransferError("این سفارش متعلق به شما نیست.")
    if not is_card_transfer_order(order):
        raise CardTransferError("روشِ پرداختِ این سفارش کارت‌به‌کارت نیست.")
    if order.status == Order.Status.CANCELED:
        raise CardTransferError("این سفارش لغو شده و قابلِ پرداخت نیست.")
    if order.payment_status != Order.PaymentStatus.PENDING:
        raise CardTransferError("پرداختِ این سفارش قبلاً نهایی شده است.")
    config = active_config(store)
    if config is None:
        raise CardTransferError("پرداختِ کارت‌به‌کارت در حالِ حاضر برایِ این فروشگاه فعال نیست.")
    if order.card_transfers.filter(status=S.SUBMITTED).exists():
        raise CardTransferError("اطلاعاتِ واریزِ شما ثبت شده و در انتظارِ بررسی است.")
    if order.card_transfers.count() >= MAX_SUBMISSIONS_PER_ORDER:
        raise CardTransferError("سقفِ دفعاتِ ثبتِ اطلاعات برایِ این سفارش پر شده است؛ لطفاً با فروشگاه تماس بگیرید.")
    destination = destination_for(config)
    attempt = ensure_attempt(order, config)
    try:
        with transaction.atomic():
            submission = CardTransferSubmission.objects.create(
                store=store, order=order, attempt=attempt, amount=order.grand_total,
                destination_last4=destination.last4, destination_label=f"{destination.bank} — {destination.holder}".strip(" —"),
                source_last4=last4, tracking_number=tracking, submitted_by=customer,
            )
    except IntegrityError as exc:  # دو ثبتِ هم‌زمان: قیدِ یکتایی فقط یکی را می‌پذیرد
        raise CardTransferError("اطلاعاتِ واریزِ شما ثبت شده و در انتظارِ بررسی است.") from exc
    record_audit_event(
        store=store, actor=getattr(customer, "user", None), action_code="card_transfer.submitted",
        object_type="CardTransferSubmission", object_id=submission.pk, object_label=order.code,
        after={"amount": str(order.grand_total), "source_last4": last4, "tracking": tracking}, request_id=f"c2c-submit-{submission.pk}",
    )
    return submission


# ───────────────────────────── تصمیمِ مدیر ─────────────────────────────

def tracking_seen_elsewhere(submission: CardTransferSubmission) -> bool:
    return CardTransferSubmission.objects.filter(
        store=submission.store, tracking_number__iexact=submission.tracking_number, status=S.APPROVED,
    ).exclude(order_id=submission.order_id).exists()


@transaction.atomic
def approve(submission_id: int, *, store, actor, allow_duplicate_tracking: bool = False) -> CardTransferSubmission:
    submission = CardTransferSubmission.objects.select_for_update().select_related("order", "attempt").get(pk=submission_id, store=store)
    if submission.status != S.SUBMITTED:
        raise AlreadyDecided("این ثبت قبلاً تصمیم‌گیری شده است.")
    order = Order.objects.select_for_update().select_related("payment_gateway", "customer").get(pk=submission.order_id, store=store)
    if order.status == Order.Status.CANCELED:
        raise CardTransferError("سفارش لغو شده است؛ پرداختِ آن قابلِ تأیید نیست.")
    if order.payment_status != Order.PaymentStatus.PENDING:
        raise CardTransferError("پرداختِ این سفارش قبلاً نهایی شده است.")
    if order.grand_total != submission.amount:
        raise CardTransferError("مبلغِ سفارش پس از ثبتِ اطلاعات تغییر کرده است؛ ثبت را رد و از مشتری بخواهید دوباره ثبت کند.")
    if not allow_duplicate_tracking and tracking_seen_elsewhere(submission):
        raise DuplicateTracking("این شماره‌ی پیگیری پیش‌تر برایِ سفارشِ دیگری تأیید شده است. اگر مطمئن هستید، با تأییدِ صریح ادامه دهید.")
    tx = apply_payment_success(
        order, store=store, ref_id=submission.tracking_number, note="تأییدِ پرداختِ کارت‌به‌کارت توسطِ مدیر",
        from_statuses=(Order.PaymentStatus.PENDING,), gateway=order.payment_gateway, method=Transaction.Method.CARD_TRANSFER,
        confirmed_by=actor,
    )
    if tx is None:
        raise AlreadyDecided("پرداختِ این سفارش قبلاً تأیید شده است.")
    now = timezone.now()
    submission.status, submission.reviewed_by, submission.reviewed_at, submission.transaction = S.APPROVED, actor, now, tx
    submission.save(update_fields=["status", "reviewed_by", "reviewed_at", "transaction", "updated_at"])
    PaymentAttempt.objects.filter(pk=submission.attempt_id).update(
        status=PaymentAttempt.Status.SUCCEEDED, verified_at=now, gateway_ref_id=submission.tracking_number[:100], updated_at=now,
    )
    record_audit_event(
        store=store, actor=actor, action_code="card_transfer.approved", object_type="Order", object_id=order.pk, object_label=order.code,
        after={"amount": str(order.grand_total), "tracking": submission.tracking_number, "transaction": tx.code,
               "duplicate_tracking_override": bool(allow_duplicate_tracking)},
        request_id=f"c2c-approve-{submission.pk}",
    )
    return submission


@transaction.atomic
def reject(submission_id: int, *, store, actor, reason: str) -> CardTransferSubmission:
    reason = (reason or "").strip()
    if len(reason) < 3:
        raise CardTransferError("دلیلِ ردِ پرداخت را بنویسید (برایِ اطلاعِ مشتری).")
    submission = CardTransferSubmission.objects.select_for_update().select_related("order").get(pk=submission_id, store=store)
    if submission.status != S.SUBMITTED:
        raise AlreadyDecided("این ثبت قبلاً تصمیم‌گیری شده است.")
    submission.status, submission.reviewed_by, submission.reviewed_at = S.REJECTED, actor, timezone.now()
    submission.review_note = reason[:300]
    submission.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note", "updated_at"])
    record_audit_event(
        store=store, actor=actor, action_code="card_transfer.rejected", object_type="Order", object_id=submission.order_id,
        object_label=submission.order.code, after={"reason": submission.review_note, "tracking": submission.tracking_number},
        request_id=f"c2c-reject-{submission.pk}",
    )
    return submission
