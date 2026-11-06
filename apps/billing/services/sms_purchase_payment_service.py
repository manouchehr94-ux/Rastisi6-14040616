"""پرداختِ آنلاینِ خریدِ بسته‌ی پیامک از درگاهِ **پلتفرم** (نه درگاهِ Store).

زمینهٔ مالیِ صریح و جدا: ``SmsPackagePaymentAttempt`` ↔ ``SmsPackagePurchase`` ↔ ``SmsCreditLedger``.
- مبلغ/ارز از اسنپ‌شاتِ سمتِ سرورِ خرید می‌آید (نه مرورگر).
- موفقیت فقط از verify سرور-به-سرور (``payment_flow_service.verify_and_confirm``).
- اعتبار **دقیقاً یک‌بار** افزوده می‌شود: قفلِ تلاش و خرید + وضعیتِ pending + قیدِ یکتایِ دفتر.
- پولی که پس از لغو/تکمیل/بازپرداختِ خرید برسد، اعتبار نمی‌سازد؛ تلاش «نیازمندِ اقدام» می‌شود (تطبیق).
- اعتبارنامه‌یِ درگاه فقط از پلتفرم (``registry.get_provider`` → ``platform_gateway_service``)."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.billing.providers import registry
from apps.billing.providers.base import BillingProviderError
from apps.billing.services import payment_flow_service
from apps.billing.services.payment_flow_service import PaymentFlowError, callback_url_for, safe_return_to
from apps.core.services.audit_service import record_audit_event
from apps.sms.models import SmsPackagePaymentAttempt, SmsPackagePurchase
from apps.sms.services import balance_service

CURRENCY = "IRT"
TOKEN_PREFIX = "sms_"


class SmsPaymentConfirmationError(Exception):
    """مبلغ/ارزِ پرداخت با خرید نمی‌خواند."""


@dataclass(frozen=True)
class _PurchaseDescriptor:
    """جایگزینِ سبکِ «فاکتور» برای Providerها: فقط شماره و شرحِ پرداخت."""

    number: str
    payment_description: str
    cart_lines: tuple = ()


def _describe(purchase) -> _PurchaseDescriptor:
    # سبدِ BNPL از محتوای واقعیِ همین خرید: یک بسته‌ی پیامک با قیمتِ اسنپ‌شاتِ سمتِ سرور — هیچ محتوایی ساخته نمی‌شود.
    return _PurchaseDescriptor(
        number=f"SMS-{purchase.pk}",
        payment_description=f"خرید بسته پیامک راستیسی — {purchase.credit_amount} اعتبار",
        cart_lines=({"id": f"sms-package-{purchase.package_id}", "name": f"بسته پیامک {purchase.credit_amount} اعتبار"[:100],
                     "count": 1, "unit_amount": int(purchase.price), "line_amount": int(purchase.price)},),
    )


def _new_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(24)[:40]


@transaction.atomic
def _create_attempt(purchase, *, provider, idempotency_key, actor, now):
    locked = SmsPackagePurchase.objects.select_for_update().get(pk=purchase.pk)
    if locked.status != SmsPackagePurchase.Status.PENDING:
        raise PaymentFlowError("این خرید در وضعیتِ قابلِ‌پرداخت نیست.")
    if idempotency_key:
        existing = SmsPackagePaymentAttempt.objects.filter(idempotency_key=idempotency_key).first()
        if existing is not None:
            if existing.purchase_id != locked.pk or existing.store_id != locked.store_id:
                raise PaymentFlowError("کلید یکتای پرداخت با این خرید مطابقت ندارد.")
            return existing, False
    else:
        idempotency_key = f"smsattempt-{locked.pk}-{secrets.token_hex(8)}"
    provider_code = provider or registry.active_provider_code()
    number = SmsPackagePaymentAttempt.objects.filter(purchase=locked).count() + 1
    attempt = SmsPackagePaymentAttempt.objects.create(
        store=locked.store, purchase=locked, provider=provider_code,
        status=SmsPackagePaymentAttempt.Status.CREATED, amount=locked.price, currency=CURRENCY,
        public_token=_new_token(), idempotency_key=idempotency_key, attempt_number=number, started_at=now,
    )
    record_audit_event(
        store=locked.store, actor=actor, action_code="billing.sms_payment_attempt_created",
        object_type="SmsPackagePaymentAttempt", object_id=attempt.pk, object_label=attempt.public_token,
        after={"purchase": locked.pk, "amount": str(attempt.amount), "provider": provider_code},
    )
    return attempt, True


def start_payment(purchase, *, callback_base_url, return_to="", actor=None, provider=None,
                  idempotency_key="", now=None):
    """تلاشِ پرداختِ آنلاین برای یک خریدِ pending می‌سازد و جلسه‌یِ درگاهِ پلتفرم را باز می‌کند.
    ``(attempt, session)`` را برمی‌گرداند؛ شکستِ درگاه ⇒ تلاشِ FAILED (امن) + ``PaymentFlowError``."""
    now = now or timezone.now()
    attempt, created = _create_attempt(
        purchase, provider=provider, idempotency_key=idempotency_key, actor=actor, now=now,
    )
    if not created:
        return attempt, None
    failure = None
    session = None
    with transaction.atomic():
        attempt.return_to = safe_return_to(return_to)
        callback = callback_url_for(callback_base_url, attempt)
        try:
            provider_obj = registry.get_provider(attempt.provider)
            session = provider_obj.create_payment_session(
                attempt=attempt, invoice=_describe(attempt.purchase), return_url=callback,
            )
        except BillingProviderError as exc:
            attempt.status = SmsPackagePaymentAttempt.Status.FAILED
            attempt.failure_code = (exc.code or "provider_error")[:64]
            attempt.failure_message = "شروع پرداخت ناموفق بود."
            attempt.completed_at = now
            attempt.save(update_fields=["status", "failure_code", "failure_message", "completed_at", "return_to", "updated_at"])
            failure = exc
        else:
            attempt.provider_session_id = session.session_id
            attempt.provider_extra = payment_flow_service._storable_extra(session.extra)
            attempt.status = SmsPackagePaymentAttempt.Status.PENDING
            attempt.save(update_fields=["provider_session_id", "provider_extra", "status", "return_to", "updated_at"])
    if failure is not None:
        raise PaymentFlowError(
            "درگاه پرداخت در دسترس نیست یا پیکربندی نشده است؛ کمی بعد دوباره تلاش کنید "
            f"(کد: {failure.code or 'provider_error'})."
        )
    return attempt, session


@transaction.atomic
def confirm_payment(*, attempt, amount, currency, provider_payment_id="", actor=None, now=None):
    """پرداختِ تأییدشده‌یِ یک تلاش را اعمال می‌کند — idempotent، قفل‌دار، یک‌بار.

    ترتیبِ قفل: تلاش ← خرید ← موجودی (همیشه یکسان؛ بدونِ بن‌بست)."""
    now = now or timezone.now()
    S = SmsPackagePaymentAttempt.Status
    locked = SmsPackagePaymentAttempt.objects.select_for_update().get(pk=attempt.pk)
    if locked.status == S.SUCCEEDED:
        return locked
    if locked.status == S.REQUIRES_ACTION and locked.failure_code == "purchase_completed":
        return locked                                  # پرداختِ تکراریِ از قبل ثبت‌شده: تکرارِ callback حسابرسیِ دوباره نمی‌سازد
    purchase = SmsPackagePurchase.objects.select_for_update().get(pk=locked.purchase_id)

    amount = Decimal(amount)
    if currency != locked.currency or amount != locked.amount or locked.amount != purchase.price:
        raise SmsPaymentConfirmationError("مبلغ یا ارزِ پرداخت با خرید نمی‌خواند.")

    if purchase.status != SmsPackagePurchase.Status.PENDING:
        # پول رسیده ولی خرید دیگر قابلِ تکمیل نیست (لغو/تکمیلِ دستی/بازپرداخت): اعتبار ساخته نمی‌شود؛
        # تلاش برای تطبیقِ مدیر علامت می‌خورد، نه گم می‌شود و نه اعتبارِ تکراری می‌سازد.
        locked.status = S.REQUIRES_ACTION
        locked.failure_code = f"purchase_{purchase.status}"
        locked.failure_message = "پرداخت رسید امّا خرید دیگر در انتظار نیست؛ نیازمندِ بازپرداخت/بررسیِ مدیر."
        locked.completed_at = now
        if provider_payment_id:
            locked.provider_payment_id = provider_payment_id
        locked.save(update_fields=["status", "failure_code", "failure_message", "completed_at", "provider_payment_id", "updated_at"])
        record_audit_event(
            store=locked.store, actor=actor, action_code="billing.sms_payment_needs_reconciliation",
            object_type="SmsPackagePaymentAttempt", object_id=locked.pk, object_label=locked.public_token,
            after={"purchase": purchase.pk, "purchase_status": purchase.status},
        )
        return locked

    locked.status = S.SUCCEEDED
    if provider_payment_id:
        locked.provider_payment_id = provider_payment_id
    locked.completed_at = now
    locked.failure_code = ""
    locked.failure_message = ""
    locked.save(update_fields=["status", "provider_payment_id", "completed_at", "failure_code", "failure_message", "updated_at"])
    balance_service.complete_purchase(purchase=purchase, attempt=locked, actor=actor)
    record_audit_event(
        store=locked.store, actor=actor, action_code="billing.sms_payment_confirmed",
        object_type="SmsPackagePaymentAttempt", object_id=locked.pk, object_label=locked.public_token,
        after={"purchase": purchase.pk, "credits": purchase.credit_amount, "amount": str(amount)},
    )
    return locked


@transaction.atomic
def settle_free_purchase(purchase, *, actor=None):
    """خریدِ بسته‌ی **قیمت‌صفر** (اسنپ‌شاتِ سمتِ سرور) را بدونِ درگاه تکمیل می‌کند — دقیقاً یک‌بار، با ردیفِ دفتر و حسابرسی.
    هر خریدِ دارای قیمتِ بیشتر از صفر رد می‌شود (هیچ اعتبارِ رایگان برایِ بسته‌یِ پولی)."""
    locked = SmsPackagePurchase.objects.select_for_update().get(pk=purchase.pk)
    if locked.status == SmsPackagePurchase.Status.COMPLETED:
        return locked                                                  # idempotent
    if locked.status != SmsPackagePurchase.Status.PENDING:
        raise PaymentFlowError("این خرید در وضعیتِ قابلِ‌پرداخت نیست.")
    if locked.price != 0:
        raise PaymentFlowError("این خرید مبلغِ صفر ندارد و باید پرداخت شود.")
    completed = balance_service.complete_purchase(purchase=locked, actor=actor, note="بسته‌ی رایگان (مبلغِ صفر)")
    record_audit_event(
        store=locked.store, actor=actor, action_code="billing.sms_free_purchase_settled",
        object_type="SmsPackagePurchase", object_id=locked.pk, object_label=f"SMS-{locked.pk}",
        after={"credits": locked.credit_amount, "price": "0"},
    )
    return completed


def verify_and_fulfill(attempt, *, actor=None, now=None, callback_data=None):
    """verify سرور-به-سرور و (فقط در صورتِ موفقیتِ تأییدشده) تکمیلِ خرید و افزودنِ اعتبار."""
    return payment_flow_service.verify_and_confirm(
        attempt, confirm=confirm_payment, confirmation_error=SmsPaymentConfirmationError,
        actor=actor, now=now, callback_data=callback_data,
    )


class SmsRefundError(Exception):
    """بازپرداختِ خریدِ پیامک ممکن نیست."""


@transaction.atomic
def refund_purchase(purchase, *, actor=None, reason="", idempotency_key=""):
    """بازپرداختِ یک خریدِ پیامکِ **پرداخت‌شده‌یِ آنلاین**: اعتبارِ مصرف‌نشده از موجودی برگردانده می‌شود
    (ردیفِ دفترِ ``purchase_reversal``، دقیقاً یک‌بار) و بازپرداختِ پول از Providerِ همان پرداخت
    درخواست می‌شود. Providerی که بازپرداختِ خودکار ندارد «در انتظارِ پردازشِ دستی» می‌ماند (ثبت در
    حسابرسی). اگر اعتبار مصرف شده باشد خطا می‌دهد — سیاستِ بازپرداختِ جزئی نیازمندِ تأییدِ مالک است."""
    reason = (reason or "").strip()
    if not reason:
        raise SmsRefundError("دلیلِ بازپرداخت الزامی است.")
    attempt = (
        SmsPackagePaymentAttempt.objects.select_for_update()
        .filter(purchase=purchase, status=SmsPackagePaymentAttempt.Status.SUCCEEDED).order_by("-completed_at").first()
    )
    if attempt is None:
        raise SmsRefundError("این خرید پرداختِ آنلاینِ تأییدشده ندارد.")
    try:
        locked = balance_service.reverse_purchase_credits(purchase=purchase, actor=actor, note=f"بازپرداخت: {reason}")
    except balance_service.PurchaseRefundError as exc:
        raise SmsRefundError(str(exc)) from exc

    key = idempotency_key or f"smsrefund-{locked.pk}"
    try:
        result = registry.get_provider(attempt.provider).refund_payment(
            provider_payment_id=attempt.provider_payment_id or attempt.provider_session_id,
            amount=attempt.amount, currency=attempt.currency, idempotency_key=key,
        )
    except BillingProviderError as exc:
        raise SmsRefundError("درخواست بازپرداخت به درگاه انجام نشد؛ هیچ تغییری اعمال نشد.") from exc
    record_audit_event(
        store=locked.store, actor=actor, action_code="billing.sms_refund_requested",
        object_type="SmsPackagePurchase", object_id=locked.pk, object_label=str(locked.pk),
        after={
            "amount": str(attempt.amount), "credits_reversed": locked.credit_amount,
            "provider": attempt.provider, "provider_refund_id": result.provider_refund_id,
            "money_refund": "succeeded" if result.succeeded else "pending_manual",
        },
        metadata={"reason": reason},
    )
    return locked, result
