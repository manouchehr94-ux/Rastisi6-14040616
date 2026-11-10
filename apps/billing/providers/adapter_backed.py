"""Providerِ پرداختِ پلتفرم که یک آداپترِ موتورِ پرداخت (``apps.orders.gateways``) را بازاستفاده می‌کند — بدونِ ساختنِ سیستمِ پرداختِ دوم.

تفاوتِ حیاتی با پرداختِ سفارش: اعتبارنامه *فقط* از ``platform_gateway_service`` (پلتفرم) می‌آید؛ هرگز از
``orders.PaymentGatewayConfig`` و هرگز به‌عنوانِ fallback. مبلغ و ارز از رکوردِ سمتِ سرور (تلاشِ پرداخت) می‌آید، نه مرورگر.
موفقیت فقط از ``adapter.verify_payment`` (server-to-server) اعلام می‌شود و — اگر آداپتر مرحله‌ی SETTLE جدا اعلام کرده
(BNPL، ملت) — فقط پس از **موفقیتِ settle** هم. بازگشتِ مرورگر هرگز مدرک نیست.

چرخه‌ی verify→settle (آداپترهایِ دارایِ SETTLE):
  1. ``verify_payment`` موفق ⇒ «verified» (و مرجعِ یکتا) روی تلاش ثبت می‌شود؛ هنوز **فعال‌سازی نیست**.
  2. ``settle_payment`` موفق ⇒ تازه موفقیت گزارش می‌شود.
  3. خطا/ابهامِ settle ⇒ تلاش ``pending`` می‌ماند (هرگز ناموفقِ قطعی)؛ کارِ تطبیق بعداً ``inquire`` (اگر هست) و سپس settle
     (idempotent) را تکرار می‌کند؛ فقط پاسخِ «ناموفقِ قطعیِ ارائه‌دهنده» تلاش را ناموفق می‌کند.
"""

from __future__ import annotations

import copy
import logging
from decimal import Decimal

from apps.billing.providers.base import (
    BillingPaymentProvider,
    BillingProviderError,
    PaymentSessionResult,
    PaymentStatusResult,
    ProviderConnectionError,
    ProviderResponseError,
    RefundResult,
    WebhookVerificationError,
)
from apps.orders.gateways.base import (
    GatewayAmountMismatchError,
    GatewayCategory,
    GatewayConnectionError,
    GatewayCredentialError,
    GatewayError,
    GatewayResponseError,
    GatewayUnsupportedOperationError,
    GatewayVerificationError,
    PaymentOperation,
)
from apps.orders.gateways.registry import get_adapter

logger = logging.getLogger("billing")

#: ارزِ داخلیِ آداپترها (تومان). تبدیلِ ریال را خودِ آداپتر انجام می‌دهد (تنها مرز).
ADAPTER_CURRENCY = "TOMAN"
_TEST_ATTEMPT = "_ConfigTestAttempt"
_BNPL_LINE_TYPES = ("plan", "proration_charge")


class AdapterBackedBillingProvider(BillingPaymentProvider):
    supports_automatic_capture = True

    def __init__(self, code: str):
        self.code = code

    # -- helpers ---------------------------------------------------------------------------------
    def _adapter(self):
        from apps.portal.services.platform_gateway_service import ineligibility_reason

        reason = ineligibility_reason(self.code)
        if reason:
            raise BillingProviderError(reason, code="ineligible_gateway")
        return get_adapter(self.code)

    def _credentials(self, adapter):
        """``(adapter, credentials, sandbox)`` — adapter ممکن است برای ``api_base``ِ ارائه‌دهنده کپی شود (آداپترِ مشترک تغییر نمی‌کند)."""
        from apps.portal.services.platform_gateway_service import _safe_api_base, credentials_and_mode

        creds, sandbox, _source = credentials_and_mode(self.code)
        errors = adapter.validate_credentials(creds)
        if errors:
            raise BillingProviderError("درگاهِ پلتفرم پیکربندی نشده است.", code="not_configured")
        api_base = (creds.get("api_base") or "").strip()
        if api_base and hasattr(adapter, "api_base"):
            if not _safe_api_base(api_base):
                raise BillingProviderError("آدرسِ api_base نامعتبر است.", code="not_configured")
            adapter = copy.copy(adapter)
            adapter.api_base = api_base.rstrip("/")
        return adapter, creds, bool(sandbox)

    @staticmethod
    def _translate(exc: GatewayError, *, context: str) -> BillingProviderError:
        if isinstance(exc, GatewayConnectionError):
            return ProviderConnectionError("اتصال به درگاه برقرار نشد؛ دوباره تلاش کنید.", code=exc.code or "connection")
        if isinstance(exc, GatewayCredentialError):
            return BillingProviderError("اعتبارنامه‌یِ درگاهِ پلتفرم نامعتبر است.", code="not_configured")
        if isinstance(exc, GatewayAmountMismatchError):
            return BillingProviderError("درگاه پرداختی با مبلغِ متفاوت تأیید کرد.", code="amount_mismatch")
        return ProviderResponseError("پاسخِ درگاه نامعتبر یا رد شد.", code=exc.code or context)

    @staticmethod
    def _purchase_type(attempt) -> str:
        return "sms_package" if type(attempt).__name__ == "SmsPackagePaymentAttempt" else "subscription"

    def order_code(self, attempt) -> str:
        """شناسه‌ی سفارشی که به درگاه داده می‌شود: ``token`` (پیش‌فرض: توکنِ تلاش)، ``numeric`` (فقط رقم — پاسارگاد/ملت:
        ``1``+pk اشتراک، ``2``+pk پیامک، ``9``+pk تستِ پیکربندی) یا ``alnum`` (حرف+۹ رقم، ≤۱۰ نویسه — سپ/BNPL: B/S/T)."""
        from apps.portal.services import platform_gateway_matrix as matrix

        facts = matrix.facts_for(self.code)
        style = facts.order_code_style if facts is not None else "token"
        name = type(attempt).__name__
        if style == "numeric":
            kind = {"SmsPackagePaymentAttempt": "2", _TEST_ATTEMPT: "9"}.get(name, "1")
            return f"{kind}{int(attempt.pk):09d}"
        if style == "alnum":
            kind = {"SmsPackagePaymentAttempt": "S", _TEST_ATTEMPT: "T"}.get(name, "B")
            return f"{kind}{int(attempt.pk):09d}"
        return attempt.public_token

    def _callback_hints(self, attempt, callback_data) -> dict:
        """داده‌ی بازگشتِ مرورگر (فقط راهنما) + داده‌ی ذخیره‌شده‌ی سمتِ سرور. **داده‌ی سرور همیشه برنده است**:
        مرورگر نمی‌تواند ``urlId`` و مانندِ آن را جایگزین کند."""
        return {**dict(callback_data or {}), **dict(getattr(attempt, "provider_extra", None) or {})}

    def _assert_gate_open(self, attempt):
        """لایه‌ی دفاعیِ آخر: حتی اگر یک ویو اشتباه کند، Providerِ دارایِ گیت بدونِ گیت‌هایِ باز و نوعِ خریدِ مجاز، جلسه نمی‌سازد.
        (تستِ پیکربندی استثناست: فقط درخواستِ بدونِ پرداخت.)"""
        if type(attempt).__name__ == _TEST_ATTEMPT:
            return
        from apps.portal.services import platform_gateway_service as pgs

        if not pgs.usable_for(self.code, self._purchase_type(attempt), getattr(attempt, "store", None)):
            raise BillingProviderError(
                "این روشِ پرداخت برای این خرید مجاز/آماده نیست (گیتِ قرارداد یا نوعِ خرید).", code="gate_closed",
            )

    # -- BNPL cart (REAL purchase contents only) ----------------------------------------------------------------------------
    @staticmethod
    def _bnpl_cart(attempt, invoice):
        """سبدِ BNPL از **ردیف‌هایِ واقعیِ** همین فاکتور/خرید ساخته می‌شود — هیچ محتوایی ساخته نمی‌شود. فاکتورِ دارایِ ردیفِ
        تخفیف/مالیات/اعتبارِ مستقل یا پرداختِ جزئی پشتیبانی نمی‌شود (سبد باید دقیقاً با مبلغِ قابلِ پرداخت برابر باشد)."""
        lines = getattr(invoice, "cart_lines", None)
        items = []
        tax_total = 0
        if lines is not None:
            for line in lines:
                items.append({**line, "discount_allocation": 0, "total_tax": 0})
        else:
            model_lines = list(invoice.lines.all()) if hasattr(invoice, "lines") and hasattr(invoice.lines, "all") else []
            for line in model_lines:
                if line.line_type not in _BNPL_LINE_TYPES:
                    raise BillingProviderError("ساختارِ این فاکتور برای پرداختِ اقساطی پشتیبانی نمی‌شود.", code="cart_unsupported")
                if Decimal(line.quantity) != Decimal(line.quantity).to_integral_value() or int(line.quantity) < 1:
                    raise BillingProviderError("تعدادِ ردیف برای پرداختِ اقساطی معتبر نیست.", code="cart_unsupported")
                items.append({
                    "id": f"line-{line.pk}", "name": (line.description or "اشتراکِ راستیسی")[:100], "count": int(line.quantity),
                    "unit_amount": int(line.unit_amount), "line_amount": int(line.subtotal),
                    "discount_allocation": int(line.discount), "total_tax": int(line.tax),
                })
                tax_total += int(line.tax)
        if not items:
            raise BillingProviderError("فاکتور ردیفِ قابلِ ارسال به درگاهِ اقساطی ندارد.", code="cart_unsupported")
        net = sum(i["line_amount"] - i["discount_allocation"] for i in items)
        if net + tax_total != int(attempt.amount):
            raise BillingProviderError("سبدِ فاکتور با مبلغِ قابلِ پرداخت برابر نیست (پرداختِ جزئی/تعدیل).", code="cart_unsupported")
        totals = {"grand_total": int(attempt.amount), "shipping": 0, "shipping_tax": 0, "tax": tax_total, "gift_wrap": 0, "discount": 0}
        return items, totals

    # -- contract --------------------------------------------------------------------------------
    def create_payment_session(self, *, attempt, invoice, return_url: str) -> PaymentSessionResult:
        from apps.orders.services.gateway_payment_service import is_safe_gateway_redirect

        adapter = self._adapter()
        self._assert_gate_open(attempt)
        adapter, creds, sandbox = self._credentials(adapter)
        description = getattr(invoice, "payment_description", "") or (
            f"اشتراکِ راستیسی — فاکتورِ {invoice.number}" if getattr(invoice, "number", "") else "پرداخت راستیسی"
        )
        kwargs = {}
        if adapter.category == GatewayCategory.BNPL:
            kwargs["cart_items"], kwargs["cart_totals"] = self._bnpl_cart(attempt, invoice)
            try:
                payload = adapter.check_bnpl_eligibility(
                    amount=Decimal(attempt.amount), currency=ADAPTER_CURRENCY, credentials=creds, sandbox=sandbox,
                )
            except GatewayUnsupportedOperationError:
                payload = None
            except GatewayError as exc:
                raise self._translate(exc, context="eligibility") from exc
            response = (payload or {}).get("response") if isinstance(payload, dict) else None
            if isinstance(response, dict) and response.get("eligible") is False:
                raise BillingProviderError("ارائه‌دهنده این خرید را برای پرداختِ اقساطی واجدِ شرایط نمی‌داند.", code="bnpl_not_eligible")
        try:
            result = adapter.create_payment(
                amount=Decimal(attempt.amount), currency=ADAPTER_CURRENCY, callback_url=return_url,
                credentials=creds, order_code=self.order_code(attempt), description=description[:255], sandbox=sandbox, **kwargs,
            )
        except GatewayError as exc:
            raise self._translate(exc, context="create") from exc
        url = result.gateway_url or adapter.build_redirect_url(result.track_id, sandbox=sandbox)
        if not is_safe_gateway_redirect(url, adapter, sandbox=sandbox):
            raise ProviderResponseError("آدرسِ بازگشتیِ درگاه ایمن نیست؛ پرداخت شروع نشد.", code="unsafe_redirect")
        raw = dict(result.extra or {})
        extra = {k: v for k, v in raw.items() if isinstance(v, (str, int, bool)) and k != "paymentPageUrl"}
        extra["sandbox"] = sandbox
        if isinstance(raw.get("post_fields"), dict):
            extra["post_fields"] = {str(k): str(v) for k, v in raw["post_fields"].items()}       # فقط برای همین ریدایرکت؛ ذخیره نمی‌شود
        return PaymentSessionResult(session_id=str(result.track_id), redirect_url=url, extra=extra)

    # -- verify (+ settle) ---------------------------------------------------------------------------------------------
    def _status_ok(self, adapter, attempt, ref_id: str) -> PaymentStatusResult:
        unique = bool(getattr(adapter, "unique_payment_reference", False)) and ref_id
        return PaymentStatusResult(
            provider_payment_id=ref_id if unique else attempt.provider_session_id, succeeded=True,
            amount=Decimal(attempt.amount), currency=attempt.currency,
            raw_summary={"ref_id": ref_id},
        )

    def _pending(self, attempt, why: str) -> PaymentStatusResult:
        return PaymentStatusResult(provider_payment_id=attempt.provider_session_id, succeeded=False, raw_summary={"settlement": why})

    def _persist_extra(self, attempt, **updates):
        extra = dict(attempt.provider_extra or {})
        extra.update(updates)
        attempt.provider_extra = extra
        attempt.save(update_fields=["provider_extra", "updated_at"])

    def _settle(self, adapter, attempt, creds, sandbox, ref_id: str) -> PaymentStatusResult:
        try:
            settled = adapter.settle_payment(
                track_id=attempt.provider_session_id, amount=Decimal(attempt.amount), currency=ADAPTER_CURRENCY,
                credentials={**creds, "_saleReferenceId": ref_id}, sandbox=sandbox,
            )
        except GatewayError as exc:
            logger.warning("%s settle unconfirmed: %s", self.code, getattr(exc, "code", type(exc).__name__))
            return self._pending(attempt, "settle_error")
        if not settled.success:
            return self._pending(attempt, "settle_rejected")
        return self._status_ok(adapter, attempt, ref_id)

    def _after_verified(self, adapter, attempt, creds, sandbox, ref_id: str) -> PaymentStatusResult:
        """verify قبلاً موفق شده امّا settle تأیید نشده: اول استعلام (اگر هست)، سپس settle (idempotent) را تکرار کن."""
        if adapter.supports(PaymentOperation.INQUIRE):
            try:
                inquiry = adapter.inquire_payment(
                    track_id=attempt.provider_session_id, expected_amount=Decimal(attempt.amount), currency=ADAPTER_CURRENCY,
                    credentials={**creds, "_saleReferenceId": ref_id}, sandbox=sandbox,
                )
            except GatewayError as exc:
                raise self._translate(exc, context="inquire") from exc
            if inquiry.terminal_negative:
                raise BillingProviderError("ارائه‌دهنده اعلام کرد این تراکنش هرگز تکمیل نمی‌شود.", code="provider_terminal_failure")
            if inquiry.settled:
                return self._status_ok(adapter, attempt, ref_id)
        return self._settle(adapter, attempt, creds, sandbox, ref_id)

    def verify_attempt(self, *, attempt, callback_data=None) -> PaymentStatusResult:
        adapter = self._adapter()
        adapter, creds, sandbox = self._credentials(adapter)
        settle_capable = adapter.supports(PaymentOperation.SETTLE)
        extra = dict(attempt.provider_extra or {})
        if settle_capable and extra.get("verified"):
            return self._after_verified(adapter, attempt, creds, sandbox, str(extra.get("verified_ref", "")))
        try:
            result = adapter.verify_payment(
                track_id=attempt.provider_session_id, expected_amount=Decimal(attempt.amount),
                currency=ADAPTER_CURRENCY, credentials=creds, callback_data=self._callback_hints(attempt, callback_data), sandbox=sandbox,
            )
        except GatewayAmountMismatchError as exc:
            raise self._translate(exc, context="verify") from exc
        except GatewayVerificationError as exc:
            # صراحتاً «پرداخت تأیید نشد» — موفقیت نیست، اما خطای زیرساخت هم نیست.
            return PaymentStatusResult(
                provider_payment_id=attempt.provider_session_id, succeeded=False,
                raw_summary={"code": exc.code, "verified": False},
            )
        except GatewayError as exc:
            raise self._translate(exc, context="verify") from exc
        if not result.success:
            return PaymentStatusResult(
                provider_payment_id=attempt.provider_session_id, succeeded=False,
                raw_summary={"status_code": result.status_code, "message": result.message},
            )
        ref_id = str(result.ref_id or "")
        if settle_capable:
            # «verified» ثبت می‌شود تا شکستِ settle در تطبیقِ بعدی دوباره verify نشود؛ هنوز فعال‌سازی نیست.
            self._persist_extra(attempt, verified=True, verified_ref=ref_id)
            return self._settle(adapter, attempt, creds, sandbox, ref_id)
        return self._status_ok(adapter, attempt, ref_id)

    def callback_claims_failure(self, callback_data) -> bool:
        data = callback_data or {}
        if self.code == "pasargad":     # status = success | failed | unknown | cancel | expire (docs, 2026-11-05)
            return str(data.get("status", "")).strip().lower() in ("failed", "cancel", "expire")
        if self.code in ("snappay", "torobpay"):
            return str(data.get("state", data.get("status", ""))).strip().upper() in ("FAILED", "CANCEL", "CANCELED", "CANCELLED")
        if self.code == "saman":
            state = str(data.get("State", "")).strip().upper()
            return bool(state) and state != "OK"
        if self.code == "mellat":
            code = str(data.get("ResCode", "")).strip()
            return bool(code) and code != "0"
        return str(data.get("Status", data.get("status", ""))).strip().upper() == "NOK"

    def fetch_payment_status(self, *, provider_payment_id: str) -> PaymentStatusResult:
        raise ProviderResponseError(
            "تأیید برای این درگاه فقط از مسیرِ verify_attempt (با مبلغِ مورد انتظار) انجام می‌شود.", code="use_verify_attempt",
        )

    def verify_webhook(self, *, headers: dict, body: bytes, secret: str) -> bool:
        raise WebhookVerificationError("این درگاه Webhookِ فشاریِ امضاشده ندارد.", code="unsupported")

    def parse_webhook_event(self, *, body: bytes):
        raise ProviderResponseError("این درگاه Webhookِ فشاری ندارد.", code="unsupported")

    # -- refund ----------------------------------------------------------------------------------------------------------
    def refund_payment(self, *, provider_payment_id: str, amount: Decimal, currency: str,
                       idempotency_key: str) -> RefundResult:
        """بازپرداخت. فقط اگر قراردادِ آداپتر ``CANCEL`` (reverse در مهلت) را اعلام کرده، آداپتر BNPL نیست، و مبلغ کاملِ همان
        پرداخت است reverse تلاش می‌شود؛ در غیرِ این صورت یا اگر درگاه نپذیرفت (مهلت/تسویه‌شده) صادقانه «پردازشِ دستی»
        برمی‌گردد — هرگز خطای پرتاب‌شده یا موفقیتِ جعلی."""
        manual = RefundResult(
            provider_refund_id=f"{self.code}-manual-refund-{idempotency_key}", succeeded=False,
            raw_summary={"manual": True, "reason": "بازپرداختِ این درگاه نیازمندِ پردازشِ دستی در پنلِ درگاه است."},
        )
        try:
            adapter = self._adapter()
        except BillingProviderError:
            return manual
        if not adapter.supports(PaymentOperation.CANCEL) or adapter.category == GatewayCategory.BNPL:
            return manual
        attempt = self._attempt_for_payment(provider_payment_id)
        if attempt is None or Decimal(amount) != Decimal(attempt.amount):
            return manual
        extra = dict(attempt.provider_extra or {})
        reference = str(extra.get("verified_ref") or provider_payment_id or "")
        needed = {"pasargad": extra.get("urlId"), "saman": reference, "mellat": reference}.get(self.code)
        if not needed:
            return manual
        try:
            adapter, creds, sandbox = self._credentials(adapter)
        except (GatewayError, BillingProviderError) as exc:       # nothing was sent: a definite "not executed"
            logger.warning("%s reverse not attempted: %s", self.code, getattr(exc, "code", type(exc).__name__))
            return manual
        try:
            result = adapter.cancel_payment(
                track_id=attempt.provider_session_id,
                credentials={**creds, "_urlId": str(extra.get("urlId", "")), "_refNum": reference, "_saleReferenceId": reference},
                sandbox=sandbox,
            )
        except (GatewayConnectionError, GatewayResponseError) as exc:
            # The request may have reached the bank and been executed (timeout, dropped connection, unreadable reply). The
            # outcome is UNKNOWN: report it as such so the caller never retries blindly and finance reconciles with the bank.
            logger.warning("%s reverse outcome unknown: %s", self.code, getattr(exc, "code", type(exc).__name__))
            return RefundResult(
                provider_refund_id=f"{self.code}-unknown-refund-{idempotency_key}", succeeded=False,
                raw_summary={"manual": True, "unknown": True,
                             "reason": "نتیجهٔ reverse نزد درگاه نامشخص است؛ با بانک تطبیق دهید و دوباره درخواست نکنید."},
            )
        except GatewayError as exc:                              # the gateway explicitly refused
            logger.warning("%s reverse not accepted: %s", self.code, getattr(exc, "code", type(exc).__name__))
            return manual
        if not result.success:
            return RefundResult(
                provider_refund_id=f"{self.code}-manual-refund-{idempotency_key}", succeeded=False,
                raw_summary={"manual": True, "reason": "درگاه reverse را نپذیرفت (احتمالاً مهلت گذشته)؛ پردازشِ دستی.",
                             "status_code": result.status_code},
            )
        return RefundResult(
            provider_refund_id=f"{self.code}-reverse-{idempotency_key}", succeeded=True,
            raw_summary={"reversed": True, "status_code": result.status_code},
        )

    def _attempt_for_payment(self, provider_payment_id: str):
        from apps.billing.models import SubscriptionPaymentAttempt
        from apps.sms.models import SmsPackagePaymentAttempt

        if not provider_payment_id:
            return None
        for model in (SubscriptionPaymentAttempt, SmsPackagePaymentAttempt):
            attempt = model.objects.filter(provider=self.code, provider_payment_id=provider_payment_id).first()
            if attempt is not None:
                return attempt
        return None
