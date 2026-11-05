"""کارت‌به‌کارتِ **پلتفرم** — گردشِ کارِ ادعا ← بررسیِ مالیِ مستقل ← اعمالِ یک‌باره.

اصولِ امنیتی (قفل‌شده با تست و قیدِ پایگاه‌داده):
- رسید/شماره‌ی پیگیری مدرکِ پرداخت نیست؛ ثبتِ ادعا هرگز اشتراک را فعال یا اعتبارِ پیامک را اضافه نمی‌کند.
- فقط یک مدیرِ مالیِ مجاز (superuser + دسترسیِ ``billing.approve_manual_platform_payment``)، **غیر از ثبت‌کننده** و بدونِ عضویتِ
  فعال در همان فروشگاه، می‌تواند تأیید/رد کند؛ تأیید نیازمندِ ارجاعِ صورتحسابِ بانکیِ مستقل و مبلغِ **دقیقاً برابر** است
  (بدونِ پرداختِ کمتر/بیشتر، بدونِ تأییدِ جزئی).
- اعمال از همان ``confirm_payment`` (اشتراک) / ``sms_purchase_payment_service.confirm_payment`` + ``SmsCreditLedger`` عبور می‌کند ⇒
  دقیقاً یک‌بار، قفل‌دار، idempotent.
- شماره‌ی پیگیری و ارجاعِ صورتحسابِ بانکی با قیدِ یکتایِ پایگاه‌داده از بازپخش (replay) و تأییدِ دوباره محافظت می‌شوند؛ تلاشِ
  تکراری و ادعاهایِ مکررِ ردشده نشانه‌گذاری و حسابرسی می‌شود.
- شواهد در ذخیره‌سازیِ خصوصی (نه media عمومی) و تاریخچه‌ی فقط‌افزودنی نگهداری می‌شود."""

from __future__ import annotations

import hashlib
import re
import secrets
import unicodedata
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.billing.models import (
    PlatformManualPaymentClaim,
    PlatformManualPaymentClaimEvent,
    SubscriptionInvoice,
    SubscriptionPaymentAttempt,
)
from apps.billing.providers.manual_card import CODE as PROVIDER_CODE
from apps.billing.services import attempt_service, confirmation_service
from apps.billing.services.sms_purchase_payment_service import SmsPaymentConfirmationError
from apps.core.services.audit_service import record_audit_event
from apps.portal.services import platform_gateway_matrix as matrix
from apps.portal.services import platform_gateway_service as pgs
from apps.portal.services.platform_config_service import record_platform_audit_event
from apps.sms.models import SmsPackagePaymentAttempt, SmsPackagePurchase

Status = PlatformManualPaymentClaim.Status
REVIEW_WINDOW_DAYS = 7
MAX_RECEIPT_BYTES = 5 * 1024 * 1024
MAX_PENDING_PER_STORE_PER_DAY = 5
REPEATED_REJECTION_THRESHOLD = 3
MAX_TRANSFER_AGE_DAYS = 14
APPROVE_PERMISSION = "billing.approve_manual_platform_payment"
_MIN_REFERENCE_LEN = 6
_PERSIAN = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


class ClaimError(Exception):
    """خطای قابل‌نمایش در گردشِ کارِ کارت‌به‌کارت (بدونِ جزئیاتِ حساس)."""


class DuplicateReferenceError(ClaimError):
    """شماره‌ی پیگیریِ تکراری/ادعایِ فعالِ موجود — تلاش ثبت و نشانه‌گذاری می‌شود."""


# ----------------------------------------------------------------------------- helpers

def normalize_reference(raw: str) -> str:
    """شماره‌ی پیگیری را به کلیدِ یکتا تبدیل می‌کند: ارقامِ فارسی/عربی ⇒ ASCII، حذفِ فاصله/خط‌تیره/نویسه‌های نامرئی، حروفِ کوچک."""
    text = unicodedata.normalize("NFKC", str(raw or "")).translate(_PERSIAN)
    return re.sub(r"[^0-9a-z]", "", text.lower())


_RECEIPT_MAGIC = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"%PDF-", "application/pdf"),
)


def sniff_receipt(data: bytes) -> str:
    """نوعِ رسید از روی محتوا (نه نام/Content-Type کاربر)؛ فقط JPEG/PNG/WEBP/PDF."""
    for magic, kind in _RECEIPT_MAGIC:
        if data.startswith(magic):
            return kind
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return ""


def can_review(user) -> bool:
    """مدیرِ مالیِ مجاز: کاربرِ فعال، staff و superuser با دسترسیِ صریح. (لایه‌ی دوم: ویوها هم superuser می‌خواهند.)"""
    return bool(user is not None and user.is_authenticated and user.is_active and user.is_staff and user.is_superuser
                and user.has_perm(APPROVE_PERMISSION))


def _event(claim, action, *, actor=None, **detail):
    PlatformManualPaymentClaimEvent.objects.create(claim=claim, actor=actor, action=action, detail={k: v for k, v in detail.items() if v not in (None, "")})


def _audit(claim, action_code, *, actor, after=None):
    record_audit_event(
        store=claim.store, actor=actor, action_code=action_code, object_type="PlatformManualPaymentClaim",
        object_id=claim.pk, object_label=claim.target_label, after=after or {"status": claim.status},
    )
    record_platform_audit_event(
        actor=actor, action_code=action_code, object_type="PlatformManualPaymentClaim", object_id=claim.pk,
        object_label=claim.target_label, after=after or {"status": claim.status},
    )


# ----------------------------------------------------------------------------- owner side

def claimable_target(*, invoice=None, sms_purchase=None):
    """بررسیِ اینکه هدف قابلِ پرداخت است و کارت‌به‌کارت برایش مجاز؛ ``(purchase_type, amount, store)`` یا ClaimError."""
    if (invoice is None) == (sms_purchase is None):
        raise ClaimError("دقیقاً یک هدفِ پرداخت لازم است.")
    if invoice is not None:
        if not invoice.is_payable:
            raise ClaimError("این فاکتور در وضعیتِ قابلِ‌پرداخت نیست.")
        return matrix.PURCHASE_SUBSCRIPTION, Decimal(invoice.amount_due), invoice.store
    if sms_purchase.status != SmsPackagePurchase.Status.PENDING:
        raise ClaimError("این خرید در وضعیتِ در انتظارِ پرداخت نیست.")
    return matrix.PURCHASE_SMS, Decimal(sms_purchase.price), sms_purchase.store


def submit_claim(*, user, store, reference, transferred_at, payer_card_last4="", receipt=None,
                 invoice=None, sms_purchase=None, now=None):
    """ادعای پرداخت را ثبت می‌کند (هیچ اثرِ مالی ندارد). مبلغ همیشه از رکوردِ سمتِ سرور می‌آید، نه فرم.
    تلاشِ تکراری **بعد از rollbackِ تراکنش** حسابرسی می‌شود تا ردپایش از بین نرود."""
    now = now or timezone.now()
    try:
        return _submit_claim_atomic(
            user=user, store=store, reference=reference, transferred_at=transferred_at, payer_card_last4=payer_card_last4,
            receipt=receipt, invoice=invoice, sms_purchase=sms_purchase, now=now,
        )
    except DuplicateReferenceError:
        _record_duplicate_attempt(store=store, user=user, key=normalize_reference(reference), now=now)
        raise


@transaction.atomic
def _submit_claim_atomic(*, user, store, reference, transferred_at, payer_card_last4, receipt, invoice, sms_purchase, now):
    purchase_type, amount, owner_store = claimable_target(invoice=invoice, sms_purchase=sms_purchase)
    if owner_store.pk != store.pk:
        raise ClaimError("این هدفِ پرداخت متعلق به فروشگاهِ شما نیست.")
    state = pgs.gateway_state(pgs.PLATFORM_CARD)
    if not state.ready or purchase_type not in state.allowed_types:
        raise ClaimError("کارت‌به‌کارت برای این نوعِ خرید فعال نیست.")

    key = normalize_reference(reference)
    if len(key) < _MIN_REFERENCE_LEN:
        raise ClaimError("شماره‌ی پیگیری معتبر نیست (حداقل ۶ رقم/نویسه).")
    last4 = re.sub(r"\D", "", unicodedata.normalize("NFKC", str(payer_card_last4 or "")).translate(_PERSIAN))
    if last4 and len(last4) != 4:
        raise ClaimError("چهار رقمِ آخرِ کارت باید دقیقاً ۴ رقم باشد.")
    if transferred_at > now + timedelta(minutes=5):
        raise ClaimError("زمانِ انتقال در آینده است.")
    flags = []
    if transferred_at < now - timedelta(days=MAX_TRANSFER_AGE_DAYS):
        flags.append("old_transfer")

    recent = PlatformManualPaymentClaim.objects.filter(store=store, created_at__gte=now - timedelta(days=1))
    if recent.filter(status=Status.PENDING_REVIEW).count() >= MAX_PENDING_PER_STORE_PER_DAY:
        raise ClaimError("تعدادِ ادعاهایِ در انتظارِ این فروشگاه از حدِ مجاز بیشتر است؛ بعداً تلاش کنید.")
    if recent.filter(status=Status.REJECTED).count() >= REPEATED_REJECTION_THRESHOLD:
        flags.append("repeated_rejected_claims")

    data = b""
    content_type = ""
    digest = ""
    if receipt is not None:
        data = receipt.read()
        if len(data) > MAX_RECEIPT_BYTES:
            raise ClaimError("حجمِ رسید بیش از ۵ مگابایت است.")
        content_type = sniff_receipt(data)
        if not content_type:
            raise ClaimError("رسید باید تصویرِ JPEG/PNG/WEBP یا PDF باشد.")
        digest = hashlib.sha256(data).hexdigest()
        if PlatformManualPaymentClaim.objects.filter(receipt_sha256=digest, status__in=PlatformManualPaymentClaim.ACTIVE_STATUSES).exists():
            flags.append("duplicate_receipt_file")

    if PlatformManualPaymentClaim.objects.filter(reference_key=key, status__in=PlatformManualPaymentClaim.ACTIVE_STATUSES).exists():
        raise DuplicateReferenceError("این شماره‌ی پیگیری پیش‌تر ثبت شده است؛ اگر اشتباه می‌دانید با پشتیبانی تماس بگیرید.")

    # قفلِ هدف و ساختِ تلاشِ پرداختِ موجود (اشتراک/پیامک) — بدونِ ساختنِ سیستمِ جدید.
    if invoice is not None:
        locked = SubscriptionInvoice.objects.select_for_update().get(pk=invoice.pk)
        if not locked.is_payable or Decimal(locked.amount_due) != amount:
            raise ClaimError("فاکتور تغییر کرده است؛ صفحه را دوباره باز کنید.")
        attempt = attempt_service.create_attempt(
            locked, provider=PROVIDER_CODE, idempotency_key=f"manualclaim-inv-{locked.pk}-{secrets.token_hex(6)}", actor=user, now=now,
        )
        target = {"invoice": locked, "subscription_attempt": attempt}
    else:
        from apps.billing.services import sms_purchase_payment_service as sms_svc
        from apps.billing.services.payment_flow_service import PaymentFlowError

        locked = SmsPackagePurchase.objects.select_for_update().get(pk=sms_purchase.pk)
        try:
            attempt, _created = sms_svc._create_attempt(
                locked, provider=PROVIDER_CODE, idempotency_key=f"manualclaim-sms-{locked.pk}-{secrets.token_hex(6)}", actor=user, now=now,
            )
        except PaymentFlowError as exc:
            raise ClaimError(str(exc)) from exc
        target = {"sms_purchase": locked, "sms_attempt": attempt}
    attempt.provider_session_id = f"claim-{key}"[:120]
    attempt.status = type(attempt).Status.PENDING
    attempt.save(update_fields=["provider_session_id", "status", "updated_at"])

    try:
        with transaction.atomic():
            claim = PlatformManualPaymentClaim.objects.create(
                store=store, submitted_by=user, expected_amount=amount, currency="IRT", reference_raw=str(reference)[:80],
                reference_key=key, transferred_at=transferred_at, payer_card_last4=last4, receipt_sha256=digest,
                receipt_content_type=content_type, expires_at=now + timedelta(days=REVIEW_WINDOW_DAYS), flags=flags, **target,
            )
    except IntegrityError as exc:                      # رقابتِ هم‌زمان: قیدِ یکتا یک‌بار برنده می‌شود
        raise DuplicateReferenceError("برای این پرداخت قبلاً یک ادعای فعال ثبت شده یا این شماره‌ی پیگیری تکراری است.") from exc
    if data:
        from django.core.files.base import ContentFile

        claim.receipt.save(f"receipt{_ext(content_type)}", ContentFile(data), save=True)
    if target.get("invoice") and target["invoice"].status in (SubscriptionInvoice.Status.OPEN, SubscriptionInvoice.Status.PAST_DUE):
        target["invoice"].status = SubscriptionInvoice.Status.PAYMENT_PENDING
        target["invoice"].save(update_fields=["status", "updated_at"])
    _event(claim, "submitted", actor=user, flags=flags, has_receipt=bool(data), amount=str(amount))
    _audit(claim, "billing.manual_claim_submitted", actor=user, after={"status": claim.status, "amount": str(amount), "flags": flags})
    return claim


def _ext(content_type):
    return {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "application/pdf": ".pdf"}.get(content_type, "")


def _record_duplicate_attempt(*, store, user, key, now):
    """تلاشِ ثبتِ شماره‌ی پیگیریِ تکراری را برای رسیدگی ثبت می‌کند (بدونِ ساختِ ادعا). مستقل از تراکنشِ فراخواننده."""
    record_audit_event(
        store=store, actor=user, action_code="billing.manual_claim_duplicate_reference", object_type="PlatformManualPaymentClaim",
        object_label=key[:40], after={"reference_key_suffix": key[-4:]},
    )
    record_platform_audit_event(
        actor=user, action_code="billing.manual_claim_duplicate_reference", object_type="PlatformManualPaymentClaim",
        object_label=f"store:{store.pk}", after={"reference_key_suffix": key[-4:]},
    )


@transaction.atomic
def cancel_claim(claim, *, user, now=None):
    """مالکِ ثبت‌کننده یک ادعای در انتظار را لغو می‌کند؛ تلاش لغو می‌شود، فاکتور/خرید همچنان قابلِ پرداخت است."""
    now = now or timezone.now()
    locked = PlatformManualPaymentClaim.objects.select_for_update().get(pk=claim.pk)
    if locked.store_id != claim.store_id or locked.submitted_by_id != getattr(user, "pk", None):
        raise ClaimError("فقط ثبت‌کننده‌ی ادعا می‌تواند آن را لغو کند.")
    if locked.status != Status.PENDING_REVIEW:
        raise ClaimError("این ادعا دیگر قابلِ لغو نیست.")
    _close(locked, Status.CANCELLED, attempt_status="cancelled", code="claim_cancelled", actor=user, now=now)
    _event(locked, "cancelled", actor=user)
    _audit(locked, "billing.manual_claim_cancelled", actor=user)
    return locked


def _attempt_of(claim):
    return claim.subscription_attempt or claim.sms_attempt


def _close(claim, status, *, attempt_status, code, actor, now, note=""):
    claim.status = status
    claim.reviewed_by = actor if status in (Status.REJECTED,) else claim.reviewed_by
    claim.reviewed_at = now if status in (Status.REJECTED, Status.EXPIRED, Status.CANCELLED) else claim.reviewed_at
    if note:
        claim.review_note = note[:500]
    claim.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note", "updated_at"])
    attempt = _attempt_of(claim)
    if attempt is not None and attempt.status not in (type(attempt).Status.SUCCEEDED,):
        attempt.status = getattr(type(attempt).Status, attempt_status.upper())
        attempt.failure_code = code
        attempt.completed_at = now
        attempt.save(update_fields=["status", "failure_code", "completed_at", "updated_at"])


# ----------------------------------------------------------------------------- finance side

def _check_reviewer(reviewer, claim):
    if not can_review(reviewer):
        raise ClaimError("فقط مدیرِ مالیِ مجاز می‌تواند ادعاهایِ کارت‌به‌کارت را بررسی کند.")
    if claim.submitted_by_id and claim.submitted_by_id == reviewer.pk:
        raise ClaimError("تأیید/ردِ ادعایِ خودتان مجاز نیست (تضادِ منافع).")
    from apps.stores.models import StoreMembership

    if StoreMembership.objects.filter(store_id=claim.store_id, user=reviewer, status=StoreMembership.MembershipStatus.ACTIVE).exists():
        raise ClaimError("شما عضوِ فعالِ همین فروشگاه هستید؛ بررسیِ ادعایِ آن مجاز نیست (تضادِ منافع).")


@transaction.atomic
def approve_claim(claim, *, reviewer, bank_confirmation_reference, confirmed_amount, note="", now=None):
    """تأییدِ مالی: فقط با ارجاعِ صورتحسابِ بانکیِ مستقل و مبلغِ دقیقاً برابر. سپس از همان مسیرِ کانونیکِ تأییدِ پرداخت
    (قفل، یک‌بار، دفتر) فعال‌سازی/افزودنِ اعتبار انجام می‌شود. idempotent: ادعایِ تأییدشده دوباره اعمال نمی‌شود."""
    now = now or timezone.now()
    locked = PlatformManualPaymentClaim.objects.select_for_update(of=("self",)).select_related("invoice", "sms_purchase", "store").get(pk=claim.pk)   # of=self: PostgreSQL refuses FOR UPDATE on nullable outer joins
    _check_reviewer(reviewer, locked)
    if locked.status == Status.APPROVED:
        return locked
    if locked.status != Status.PENDING_REVIEW:
        raise ClaimError("این ادعا در وضعیتِ قابلِ تأیید نیست.")
    if locked.expires_at <= now:
        raise ClaimError("مهلتِ بررسیِ این ادعا گذشته است؛ مالک باید دوباره ثبت کند.")
    ref = (bank_confirmation_reference or "").strip()
    if len(ref) < _MIN_REFERENCE_LEN:
        raise ClaimError("ارجاعِ صورتحسابِ بانکیِ مستقل (حداقل ۶ نویسه) الزامی است؛ رسیدِ مالک مدرک نیست.")
    try:
        confirmed = Decimal(str(confirmed_amount))
    except Exception as exc:  # noqa: BLE001
        raise ClaimError("مبلغِ تأییدشده معتبر نیست.") from exc
    if confirmed != Decimal(locked.expected_amount):
        raise ClaimError(
            f"مبلغِ صورتحسابِ بانکی ({confirmed:,.0f}) با مبلغِ مورد انتظار ({locked.expected_amount:,.0f}) برابر نیست؛ "
            "پرداختِ کمتر/بیشتر تأیید نمی‌شود — ادعا را رد کنید یا برای اصلاح به مالک برگردانید."
        )
    if PlatformManualPaymentClaim.objects.filter(bank_confirmation_reference=ref, status=Status.APPROVED).exclude(pk=locked.pk).exists():
        raise ClaimError("این ارجاعِ صورتحسابِ بانکی پیش‌تر برای تأییدِ پرداختِ دیگری استفاده شده است.")

    attempt = _attempt_of(locked)
    provider_payment_id = f"card-{locked.reference_key}"[:120]
    try:
        if locked.invoice_id:
            result = confirmation_service.confirm_payment(
                attempt=attempt, amount=locked.expected_amount, currency=locked.currency,
                provider_payment_id=provider_payment_id, actor=reviewer, now=now,
            )
        else:
            from apps.billing.services import sms_purchase_payment_service as sms_svc

            result = sms_svc.confirm_payment(
                attempt=attempt, amount=locked.expected_amount, currency=locked.currency,
                provider_payment_id=provider_payment_id, actor=reviewer, now=now,
            )
    except (confirmation_service.ConfirmationError, SmsPaymentConfirmationError, IntegrityError) as exc:
        raise ClaimError(f"اعمالِ پرداخت ممکن نشد: {exc}") from exc       # ⇒ rollback؛ ادعا بدونِ اثر می‌ماند

    locked.reviewed_by = reviewer
    locked.reviewed_at = now
    locked.review_note = (note or "")[:500]
    locked.bank_confirmation_reference = ref[:120]
    locked.confirmed_amount = confirmed
    if result.status == type(result).Status.SUCCEEDED:
        locked.status = Status.APPROVED
    else:
        # پول تأیید شد امّا اثر اعمال نشد (مثلاً فاکتور/خرید دیگر قابلِ‌پرداخت نبود): برای بازپرداخت/رسیدگی علامت می‌خورد.
        locked.status = Status.NEEDS_ACTION
        locked.flags = list({*locked.flags, "paid_elsewhere_or_closed"})
    locked.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note", "bank_confirmation_reference",
                               "confirmed_amount", "flags", "updated_at"])
    _event(locked, "approved" if locked.status == Status.APPROVED else "needs_action", actor=reviewer,
           bank_confirmation_reference=ref[:120], confirmed_amount=str(confirmed), note=note[:200],
           attempt_status=result.status)
    _audit(locked, "billing.manual_claim_approved" if locked.status == Status.APPROVED else "billing.manual_claim_needs_action",
           actor=reviewer, after={"status": locked.status, "amount": str(confirmed), "attempt": result.status})
    return locked


@transaction.atomic
def reject_claim(claim, *, reviewer, reason, now=None):
    """ردِ ادعا با دلیلِ الزامی (شاملِ «نیازمندِ اصلاح»): تلاش ناموفق می‌شود، شماره‌ی پیگیری آزاد می‌شود تا مالک بتواند
    ادعایِ اصلاح‌شده ثبت کند، و فاکتور/خرید همچنان قابلِ پرداخت است."""
    now = now or timezone.now()
    locked = PlatformManualPaymentClaim.objects.select_for_update(of=("self",)).select_related("store").get(pk=claim.pk)
    _check_reviewer(reviewer, locked)
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise ClaimError("دلیلِ رد (حداقل ۵ نویسه) الزامی است.")
    if locked.status == Status.REJECTED:
        return locked
    if locked.status != Status.PENDING_REVIEW:
        raise ClaimError("این ادعا در وضعیتِ قابلِ رد نیست.")
    _close(locked, Status.REJECTED, attempt_status="failed", code="claim_rejected", actor=reviewer, now=now, note=reason)
    _event(locked, "rejected", actor=reviewer, reason=reason[:300])
    _audit(locked, "billing.manual_claim_rejected", actor=reviewer, after={"status": locked.status, "reason": reason[:200]})
    return locked


def expire_stale_claims(*, now=None) -> int:
    """ادعاهایِ رسیدگی‌نشده پس از مهلت منقضی می‌شوند (بدونِ هیچ اثرِ مالی)؛ شماره‌ی پیگیری آزاد می‌شود."""
    now = now or timezone.now()
    count = 0
    for pk in list(PlatformManualPaymentClaim.objects.filter(status=Status.PENDING_REVIEW, expires_at__lte=now).values_list("pk", flat=True)):
        with transaction.atomic():
            claim = PlatformManualPaymentClaim.objects.select_for_update().get(pk=pk)
            if claim.status != Status.PENDING_REVIEW:
                continue
            _close(claim, Status.EXPIRED, attempt_status="expired", code="claim_expired", actor=None, now=now)
            _event(claim, "expired")
            _audit(claim, "billing.manual_claim_expired", actor=None)
            count += 1
    return count


def history(claim):
    return claim.events.select_related("actor").all()
