"""Providerِ پرداختِ پلتفرم که یک آداپترِ **تأییدشده‌یِ موتورِ پرداخت** (``apps.orders.gateways``) را
بازاستفاده می‌کند — بدونِ ساختنِ سیستمِ پرداختِ دوم.

تفاوتِ حیاتی با پرداختِ سفارش: اعتبارنامه *فقط* از ``platform_gateway_service`` (پلتفرم) می‌آید؛
هرگز از ``orders.PaymentGatewayConfig``. مبلغ و ارز از رکوردِ سمتِ سرور (تلاشِ پرداخت) می‌آید، نه مرورگر.
موفقیت فقط از ``adapter.verify_payment`` (server-to-server) اعلام می‌شود؛ بازگشتِ مرورگر مدرک نیست."""

from __future__ import annotations

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
    GatewayConnectionError,
    GatewayCredentialError,
    GatewayError,
    GatewayVerificationError,
)
from apps.orders.gateways.registry import get_adapter

logger = logging.getLogger("billing")

#: ارزِ داخلیِ آداپترها (تومان). تبدیلِ ریال را خودِ آداپتر انجام می‌دهد (تنها مرز).
ADAPTER_CURRENCY = "TOMAN"


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
        from apps.portal.services.platform_gateway_service import credentials_and_mode

        creds, sandbox, _source = credentials_and_mode(self.code)
        errors = adapter.validate_credentials(creds)
        if errors:
            raise BillingProviderError("درگاهِ پلتفرم پیکربندی نشده است.", code="not_configured")
        return creds, bool(sandbox)

    @staticmethod
    def _translate(exc: GatewayError, *, context: str) -> BillingProviderError:
        if isinstance(exc, GatewayConnectionError):
            return ProviderConnectionError("اتصال به درگاه برقرار نشد؛ دوباره تلاش کنید.", code=exc.code or "connection")
        if isinstance(exc, GatewayCredentialError):
            return BillingProviderError("اعتبارنامه‌یِ درگاهِ پلتفرم نامعتبر است.", code="not_configured")
        if isinstance(exc, GatewayAmountMismatchError):
            return BillingProviderError("درگاه پرداختی با مبلغِ متفاوت تأیید کرد.", code="amount_mismatch")
        return ProviderResponseError("پاسخِ درگاه نامعتبر یا رد شد.", code=exc.code or context)

    # -- contract --------------------------------------------------------------------------------
    def create_payment_session(self, *, attempt, invoice, return_url: str) -> PaymentSessionResult:
        from apps.orders.services.gateway_payment_service import is_safe_gateway_redirect

        adapter = self._adapter()
        creds, sandbox = self._credentials(adapter)
        description = getattr(invoice, "payment_description", "") or (
            f"اشتراکِ راستیسی — فاکتورِ {invoice.number}" if getattr(invoice, "number", "") else "پرداخت راستیسی"
        )
        try:
            result = adapter.create_payment(
                amount=Decimal(attempt.amount), currency=ADAPTER_CURRENCY, callback_url=return_url,
                credentials=creds, order_code=attempt.public_token, description=description[:255], sandbox=sandbox,
            )
        except GatewayError as exc:
            raise self._translate(exc, context="create") from exc
        url = result.gateway_url or adapter.build_redirect_url(result.track_id, sandbox=sandbox)
        if not is_safe_gateway_redirect(url, adapter, sandbox=sandbox):
            raise ProviderResponseError("آدرسِ بازگشتیِ درگاه ایمن نیست؛ پرداخت شروع نشد.", code="unsafe_redirect")
        return PaymentSessionResult(session_id=str(result.track_id), redirect_url=url, extra={"sandbox": sandbox})

    def verify_attempt(self, *, attempt, callback_data=None) -> PaymentStatusResult:
        adapter = self._adapter()
        creds, sandbox = self._credentials(adapter)
        try:
            result = adapter.verify_payment(
                track_id=attempt.provider_session_id, expected_amount=Decimal(attempt.amount),
                currency=ADAPTER_CURRENCY, credentials=creds, callback_data=dict(callback_data or {}), sandbox=sandbox,
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
        # مبلغ را خودِ درگاه در verify با مبلغِ مورد انتظار سنجیده است (آداپتر در ناهماهنگی خطا می‌دهد).
        return PaymentStatusResult(
            provider_payment_id=attempt.provider_session_id, succeeded=True,
            amount=Decimal(attempt.amount), currency=attempt.currency,
            raw_summary={"ref_id": result.ref_id, "status_code": result.status_code},
        )

    def callback_claims_failure(self, callback_data) -> bool:
        data = callback_data or {}
        return str(data.get("Status", data.get("status", ""))).strip().upper() == "NOK"

    def fetch_payment_status(self, *, provider_payment_id: str) -> PaymentStatusResult:
        raise ProviderResponseError(
            "تأیید برای این درگاه فقط از مسیرِ verify_attempt (با مبلغِ مورد انتظار) انجام می‌شود.", code="use_verify_attempt",
        )

    def verify_webhook(self, *, headers: dict, body: bytes, secret: str) -> bool:
        raise WebhookVerificationError("این درگاه Webhookِ فشاریِ امضاشده ندارد.", code="unsupported")

    def parse_webhook_event(self, *, body: bytes):
        raise ProviderResponseError("این درگاه Webhookِ فشاری ندارد.", code="unsupported")

    def refund_payment(self, *, provider_payment_id: str, amount: Decimal, currency: str,
                       idempotency_key: str) -> RefundResult:
        # آداپترِ تأییدشده بازپرداختِ خودکار را اعلام نکرده ⇒ صادقانه «پردازشِ دستی».
        return RefundResult(
            provider_refund_id=f"{self.code}-manual-refund-{idempotency_key}", succeeded=False,
            raw_summary={"manual": True, "reason": "بازپرداختِ این درگاه نیازمندِ پردازشِ دستی در پنلِ درگاه است."},
        )
