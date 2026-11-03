"""Zarinpal payment gateway adapter.

Zarinpal API documentation: https://www.zarinpal.com/docs/paymentGateway/

Documentation verification note (2026-11-03):
    The REST v4 contract implemented below is confirmed from Zarinpal's
    official documentation (read on 2026-11-03):
      * connectToGateway:
        https://www.zarinpal.com/docs/paymentGateway/connectToGateway
      * currency:
        https://www.zarinpal.com/docs/paymentGateway/moreFeatures/currency
      * error list:
        https://www.zarinpal.com/docs/paymentGateway/errorList
    Confirmed from those pages:
      * Request fields: ``merchant_id`` (36-char), ``amount`` (Integer),
        ``currency`` (optional, ``IRR`` = Rial / ``IRT`` = Toman),
        ``description`` (<= 500 chars), ``callback_url``, optional ``metadata``
        (mobile/email/order_id), optional ``referrer_id``.
      * On success the request returns ``code`` and ``authority``; the buyer is
        redirected to StartPay/{authority}.
      * The callback carries a ``Status`` querystring of "OK"/"NOK"; verify is
        only meaningful when Status == "OK".
      * Verify request fields: ``merchant_id``, ``amount`` (Integer, in RIAL),
        ``authority``. Verify response: ``code``, ``ref_id`` (Integer),
        ``card_pan`` (masked), ``card_hash``, ``fee_type``, ``fee``.
      * ``code`` 100 = success (occurs exactly once for a transaction); a later
        verify of the SAME transaction returns 101 = already verified (also a
        successful state). ``-50`` = verify amount mismatch.
    ``documentation_blocked`` is therefore False (contract is officially
    documented). This does NOT assert sandbox/live test evidence; no new
    production activation is implied (``is_active`` still defaults False).

Currency conversion (financial safety):
    RastiSi stores order amounts in TOMAN (``Order.grand_total`` is a
    ``DecimalField(decimal_places=0)`` labeled تومان). Zarinpal's verify amount
    is specified in RIAL. To remove any Toman/Rial ambiguity this adapter:
      * converts the stored Toman amount to integer Rial exactly once
        (Toman x 10 = Rial) at this boundary, and
      * explicitly sends ``currency = "IRR"`` on create so Zarinpal interprets
        ``amount`` as Rial.
    No other code performs this conversion, so there is no risk of double
    conversion. Amounts are integer Rial end to end for this provider.

Flow:
    1. create_payment -> POST /pg/v4/payment/request.json (server-to-server)
    2. build_redirect_url -> redirect customer to
       https://payment.zarinpal.com/pg/StartPay/{Authority}
    3. Customer pays on Zarinpal page
    4. Zarinpal redirects to callback_url with Authority + Status params
    5. verify_payment -> POST /pg/v4/payment/verify.json (server-to-server)

Security:
    - All HTTP calls have explicit connect and read timeouts
    - Credentials (merchant_id) never appear in logs or error messages
    - Response parsing is strict - unexpected structure raises GatewayResponseError
    - Network failures are caught and wrapped in GatewayConnectionError
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

import requests

from .base import (
    GatewayAmountMismatchError,
    GatewayCategory,
    GatewayConnectionError,
    GatewayCredentialError,
    GatewayPaymentError,
    GatewayResponseError,
    PaymentCreationResult,
    PaymentGatewayAdapter,
    PaymentOperation,
    PaymentVerificationResult,
)

logger = logging.getLogger("payment")

# ---------------------------------------------------------------------------
# Zarinpal REST v4 API constants
# ---------------------------------------------------------------------------

ZARINPAL_API_BASE = "https://payment.zarinpal.com"
ZARINPAL_REQUEST_URL = f"{ZARINPAL_API_BASE}/pg/v4/payment/request.json"
ZARINPAL_VERIFY_URL = f"{ZARINPAL_API_BASE}/pg/v4/payment/verify.json"
ZARINPAL_STARTPAY_URL = f"{ZARINPAL_API_BASE}/pg/StartPay/"

# Sandbox base (Zarinpal historically exposed a sandbox host). The landing doc
# read here did NOT document a sandbox base URL, so sandbox is kept pointing at
# the documented production REST base; no unverified sandbox host is invented.
ZARINPAL_SANDBOX_API_BASE = ZARINPAL_API_BASE
ZARINPAL_SANDBOX_STARTPAY_URL = ZARINPAL_STARTPAY_URL

# Timeouts in seconds (match the zibal gold-standard adapter)
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 30

# Zarinpal result codes (Code field)
ZARINPAL_CODE_SUCCESS = 100          # Operation successful
ZARINPAL_CODE_ALREADY_VERIFIED = 101  # Already verified (idempotent)

# merchant_id is a 36-character code per the official documentation.
ZARINPAL_MERCHANT_ID_LENGTH = 36

# Toman to Rial multiplier
TOMAN_TO_RIAL = 10

# Currency token sent on create so Zarinpal interprets ``amount`` as Rial.
# IRR = Rial, IRT = Toman (per the official currency documentation).
ZARINPAL_CURRENCY_RIAL = "IRR"


class ZarinpalAdapter(PaymentGatewayAdapter):
    """Zarinpal online payment gateway adapter (REST v4)."""

    @property
    def code(self) -> str:
        return "zarinpal"

    @property
    def display_name(self) -> str:
        return "زرین‌پال"

    @property
    def is_online(self) -> bool:
        return True

    @property
    def required_credentials(self) -> list[str]:
        return ["merchant_id"]

    @property
    def credential_labels(self) -> dict[str, str]:
        return {"merchant_id": "کد پذیرنده (Merchant ID — ۳۶ کاراکتر)"}

    @property
    def onboarding_help(self) -> str:
        return (
            "کد پذیرنده‌ی ۳۶ کاراکتری را از پنل زرین‌پال دریافت و وارد کنید. "
            "قرارداد REST v4 مطابق مستندات رسمی پیاده‌سازی شده است؛ پیش از فعال‌سازیِ "
            "واقعی، درگاه را با یک تراکنش آزمایشیِ مجاز بررسی کنید."
        )

    @property
    def supports_sandbox(self) -> bool:
        # The landing doc read in this environment did NOT document a dedicated
        # sandbox host, so no unverified sandbox base is offered in the admin UI.
        return False

    @property
    def category(self) -> GatewayCategory:
        # Zarinpal is a payment facilitator/aggregator riding on Shaparak/Shetab.
        return GatewayCategory.FACILITATOR

    @property
    def capabilities(self) -> frozenset[PaymentOperation]:
        # Only the operations this adapter actually implements against the
        # documented request/verify endpoints. INQUIRE/CANCEL/REFUND/SETTLE are
        # NOT implemented here (the landing doc read in this environment does
        # not expose an authoritative inquiry/refund endpoint contract), so they
        # are not declared - the ABC defaults will raise on any attempt to use
        # them rather than silently emulating a financial operation.
        return frozenset({PaymentOperation.CREATE, PaymentOperation.VERIFY})

    def validate_credentials(self, credentials: dict[str, str]) -> list[str]:
        """Validate Zarinpal credentials (36-character merchant_id required)."""
        errors = []
        merchant_id = (credentials.get("merchant_id") or "").strip()
        if not merchant_id:
            errors.append("کد پذیرنده (merchant_id) الزامی است")
        elif len(merchant_id) != ZARINPAL_MERCHANT_ID_LENGTH:
            errors.append(
                "کد پذیرنده‌ی زرین‌پال باید دقیقاً ۳۶ کاراکتر باشد"
            )
        return errors

    def _api_base(self, sandbox: bool) -> str:
        return ZARINPAL_SANDBOX_API_BASE if sandbox else ZARINPAL_API_BASE

    def create_payment(
        self,
        *,
        amount: Decimal,
        currency: str,
        callback_url: str,
        credentials: dict[str, str],
        order_code: str,
        description: str = "",
        sandbox: bool = False,
    ) -> PaymentCreationResult:
        """Create a payment request with Zarinpal."""
        merchant_id = (credentials.get("merchant_id") or "").strip()
        if not merchant_id:
            raise GatewayCredentialError("Zarinpal merchant_id is not configured")

        # Convert Toman to Rial for the Zarinpal REST v4 API.
        amount_rial = int(amount) * TOMAN_TO_RIAL

        payload = {
            "merchant_id": merchant_id,
            # Amount is sent in Rial and ``currency`` is pinned to IRR so there
            # is no ambiguity about whether ``amount`` is Toman or Rial.
            "amount": amount_rial,
            "currency": ZARINPAL_CURRENCY_RIAL,
            "callback_url": callback_url,
            "description": (description or order_code)[:255],
            "metadata": {"order_id": order_code},
        }

        request_url = (
            ZARINPAL_REQUEST_URL
            if not sandbox
            else f"{self._api_base(sandbox)}/pg/v4/payment/request.json"
        )

        logger.info(
            "Zarinpal create_payment: order=%s amount_rial=%d sandbox=%s",
            order_code, amount_rial, sandbox,
        )

        try:
            response = requests.post(
                request_url,
                json=payload,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
        except requests.ConnectionError as exc:
            logger.error("Zarinpal connection error during create_payment")
            raise GatewayConnectionError(
                "اتصال به درگاه زرین‌پال برقرار نشد. لطفاً دوباره تلاش کنید.",
                code="connection_error",
            ) from exc
        except requests.Timeout as exc:
            logger.error("Zarinpal timeout during create_payment")
            raise GatewayConnectionError(
                "پاسخ درگاه زرین‌پال در زمان مقرر دریافت نشد. لطفاً دوباره تلاش کنید.",
                code="timeout",
            ) from exc
        except requests.RequestException as exc:
            logger.error(
                "Zarinpal request error during create_payment: %s", type(exc).__name__
            )
            raise GatewayConnectionError(
                "خطا در ارتباط با درگاه زرین‌پال.",
                code="request_error",
            ) from exc

        # Parse response
        try:
            body = response.json()
        except (ValueError, TypeError) as exc:
            logger.error(
                "Zarinpal returned non-JSON response: status=%d", response.status_code
            )
            raise GatewayResponseError(
                "پاسخ نامعتبر از درگاه زرین‌پال دریافت شد.",
                code="invalid_json",
            ) from exc

        # Zarinpal REST v4 wraps results in {"data": {...}, "errors": [...]|{...}}
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, dict):
            logger.error("Zarinpal response missing 'data' object")
            raise GatewayResponseError(
                "ساختار پاسخ درگاه زرین‌پال نامعتبر است.",
                code="missing_data",
            )

        code = data.get("code")
        if code is None:
            logger.error("Zarinpal response missing 'code' field")
            raise GatewayResponseError(
                "ساختار پاسخ درگاه زرین‌پال نامعتبر است.",
                code="missing_code",
            )

        if code != ZARINPAL_CODE_SUCCESS:
            message = data.get("message", "")
            logger.warning(
                "Zarinpal create_payment rejected: code=%s order=%s",
                code, order_code,
            )
            raise GatewayPaymentError(
                "درخواست پرداخت توسط درگاه زرین‌پال رد شد.",
                code=f"zarinpal_{code}",
                details={"code": code, "message": message},
            )

        authority = data.get("authority")
        if not authority:
            logger.error("Zarinpal response missing authority despite code=100")
            raise GatewayResponseError(
                "شناسه‌ی مرجع (Authority) از درگاه زرین‌پال دریافت نشد.",
                code="missing_authority",
            )

        authority_str = str(authority)
        logger.info(
            "Zarinpal create_payment success: order=%s authority=%s",
            order_code, authority_str,
        )

        return PaymentCreationResult(
            track_id=authority_str,
            gateway_url=self.build_redirect_url(authority_str, sandbox=sandbox),
        )

    def build_redirect_url(self, track_id: str, *, sandbox: bool = False) -> str:
        """Build the Zarinpal payment page URL (StartPay/{Authority})."""
        base = ZARINPAL_SANDBOX_STARTPAY_URL if sandbox else ZARINPAL_STARTPAY_URL
        return f"{base}{track_id}"

    def verify_payment(
        self,
        *,
        track_id: str,
        expected_amount: Decimal,
        currency: str,
        credentials: dict[str, str],
        callback_data: dict[str, Any],
        sandbox: bool = False,
    ) -> PaymentVerificationResult:
        """Verify a payment with Zarinpal after callback.

        ``track_id`` is the Authority returned by create_payment. Zarinpal's
        verify call requires the merchant_id, the Authority and the Amount
        (Rial). A browser callback parameter alone never proves success.
        """
        merchant_id = (credentials.get("merchant_id") or "").strip()
        if not merchant_id:
            raise GatewayCredentialError("Zarinpal merchant_id is not configured")

        expected_rial = int(expected_amount) * TOMAN_TO_RIAL

        payload = {
            "merchant_id": merchant_id,
            "authority": track_id,
            "amount": expected_rial,
        }

        verify_url = (
            ZARINPAL_VERIFY_URL
            if not sandbox
            else f"{self._api_base(sandbox)}/pg/v4/payment/verify.json"
        )

        logger.info("Zarinpal verify_payment: authority=%s", track_id)

        try:
            response = requests.post(
                verify_url,
                json=payload,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
        except requests.ConnectionError as exc:
            logger.error(
                "Zarinpal connection error during verify_payment: authority=%s", track_id
            )
            raise GatewayConnectionError(
                "اتصال به درگاه زرین‌پال برای تأیید پرداخت برقرار نشد.",
                code="verify_connection_error",
            ) from exc
        except requests.Timeout as exc:
            logger.error(
                "Zarinpal timeout during verify_payment: authority=%s", track_id
            )
            raise GatewayConnectionError(
                "پاسخ تأیید از درگاه زرین‌پال در زمان مقرر دریافت نشد.",
                code="verify_timeout",
            ) from exc
        except requests.RequestException as exc:
            logger.error(
                "Zarinpal request error during verify: %s", type(exc).__name__
            )
            raise GatewayConnectionError(
                "خطا در ارتباط با درگاه زرین‌پال برای تأیید.",
                code="verify_request_error",
            ) from exc

        # Parse response
        try:
            body = response.json()
        except (ValueError, TypeError) as exc:
            logger.error(
                "Zarinpal verify returned non-JSON: status=%d authority=%s",
                response.status_code, track_id,
            )
            raise GatewayResponseError(
                "پاسخ نامعتبر از درگاه زرین‌پال هنگام تأیید.",
                code="verify_invalid_json",
            ) from exc

        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, dict):
            logger.error(
                "Zarinpal verify response missing 'data': authority=%s", track_id
            )
            raise GatewayResponseError(
                "ساختار پاسخ تأیید درگاه زرین‌پال نامعتبر است.",
                code="verify_missing_data",
            )

        code = data.get("code")
        if code is None:
            logger.error(
                "Zarinpal verify response missing 'code': authority=%s", track_id
            )
            raise GatewayResponseError(
                "ساختار پاسخ تأیید درگاه زرین‌پال نامعتبر است.",
                code="verify_missing_code",
            )

        # Code 100 = success, 101 = already verified (idempotent). Any other
        # code means the payment was NOT successfully verified.
        is_success = code in (ZARINPAL_CODE_SUCCESS, ZARINPAL_CODE_ALREADY_VERIFIED)

        # Amount verification. Zarinpal verify is scoped to the Amount we send,
        # but we still defensively check any amount echoed back. A confirmed
        # payment whose returned amount differs from the order must never be
        # applied as a normal paid order; the evidence is carried in the
        # exception so the caller can persist it (money may have moved).
        if is_success:
            evidence = {
                "code": code,
                "ref_id": str(data.get("ref_id", ""))[:100],
                "card_pan": str(data.get("card_pan", ""))[:25],
                "expected_rial": expected_rial,
            }
            raw_amount = data.get("amount")
            if raw_amount is not None:
                try:
                    returned_rial = int(raw_amount)
                except (TypeError, ValueError):
                    logger.error(
                        "Zarinpal verify success with unreadable amount: authority=%s",
                        track_id,
                    )
                    raise GatewayResponseError(
                        "درگاه پرداخت را تأیید کرد اما مبلغ را اعلام نکرد.",
                        code="amount_unavailable",
                        details={"evidence": evidence},
                    )
                evidence["returned_rial"] = returned_rial
                if returned_rial != expected_rial:
                    logger.error(
                        "Zarinpal amount mismatch: expected=%d got=%d authority=%s",
                        expected_rial, returned_rial, track_id,
                    )
                    raise GatewayAmountMismatchError(
                        "مبلغ تأییدشده با مبلغ سفارش مطابقت ندارد.",
                        code="amount_mismatch",
                        details={
                            "expected_rial": expected_rial,
                            "returned_rial": returned_rial,
                            "evidence": evidence,
                        },
                    )

        ref_id = str(data.get("ref_id", "")) if is_success else ""
        card_number = str(data.get("card_pan", "")) if is_success else ""
        message = data.get("message", "")

        if is_success:
            logger.info(
                "Zarinpal verify success: authority=%s refId=%s", track_id, ref_id
            )
        else:
            logger.warning(
                "Zarinpal verify failed: authority=%s code=%s", track_id, code
            )

        return PaymentVerificationResult(
            success=is_success,
            ref_id=ref_id,
            card_number=card_number,
            status_code=int(code),
            message=message,
        )
