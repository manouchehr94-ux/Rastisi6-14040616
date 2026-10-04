"""Zibal payment gateway adapter.

Zibal API documentation: https://docs.zibal.ir/

Currency conversion:
    The application stores amounts in Toman. Zibal's API accepts Rial.
    Conversion (Toman × 10 = Rial) happens ONLY inside this adapter.
    No other code in the system performs this conversion.

Flow:
    1. create_payment → POST /v1/request (server-to-server)
    2. build_redirect_url → redirect customer to https://gateway.zibal.ir/start/{trackId}
    3. Customer pays on Zibal page
    4. Zibal redirects to callback_url with trackId + success/status params
    5. verify_payment → POST /v1/verify (server-to-server)

Security:
    - All HTTP calls have explicit connect and read timeouts
    - Credentials (merchant ID) never appear in logs or error messages
    - Response parsing is strict — unexpected structure raises GatewayResponseError
    - Network failures are caught and wrapped in GatewayConnectionError
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

import requests

from .base import (
    GatewayConnectionError,
    GatewayCredentialError,
    GatewayPaymentError,
    GatewayResponseError,
    GatewayAmountMismatchError,
    GatewayVerificationError,
    PaymentCreationResult,
    PaymentGatewayAdapter,
    PaymentVerificationResult,
)

logger = logging.getLogger("payment")

# ---------------------------------------------------------------------------
# Zibal API constants
# ---------------------------------------------------------------------------

ZIBAL_API_BASE = "https://gateway.zibal.ir"
ZIBAL_REQUEST_URL = f"{ZIBAL_API_BASE}/v1/request"
ZIBAL_VERIFY_URL = f"{ZIBAL_API_BASE}/v1/verify"
ZIBAL_REDIRECT_URL = f"{ZIBAL_API_BASE}/start/"

# Sandbox uses a fixed merchant value per Zibal docs
ZIBAL_SANDBOX_MERCHANT = "zibal"

# Timeouts in seconds
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 30

# Zibal result codes
ZIBAL_RESULT_SUCCESS = 100  # Request accepted / Payment verified
ZIBAL_RESULT_ALREADY_VERIFIED = 201  # Already verified (idempotent)

# Zibal payment status codes (returned in verify response)
ZIBAL_STATUS_PAID = 1  # Paid and verified
ZIBAL_STATUS_ALREADY_VERIFIED = 2  # Already verified

# Toman to Rial multiplier
TOMAN_TO_RIAL = 10


class ZibalAdapter(PaymentGatewayAdapter):
    """Zibal online payment gateway adapter."""

    @property
    def code(self) -> str:
        return "zibal"

    @property
    def display_name(self) -> str:
        return "زیبال"

    @property
    def is_online(self) -> bool:
        return True

    @property
    def required_credentials(self) -> list[str]:
        return ["merchant"]

    def validate_credentials(self, credentials: dict[str, str]) -> list[str]:
        """Validate Zibal credentials (merchant ID required)."""
        errors = []
        merchant = (credentials.get("merchant") or "").strip()
        if not merchant:
            errors.append("شناسه‌ی مرچنت (merchant) الزامی است")
        return errors

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
        """Create a payment request with Zibal."""
        merchant = credentials.get("merchant", "").strip()
        if not merchant:
            raise GatewayCredentialError("Zibal merchant ID is not configured")

        # Use sandbox merchant if in sandbox mode
        effective_merchant = ZIBAL_SANDBOX_MERCHANT if sandbox else merchant

        # Convert Toman to Rial for Zibal API
        amount_rial = int(amount) * TOMAN_TO_RIAL

        payload = {
            "merchant": effective_merchant,
            "amount": amount_rial,
            "callbackUrl": callback_url,
            "orderId": order_code,
        }
        if description:
            payload["description"] = description[:255]

        logger.info(
            "Zibal create_payment: order=%s amount_rial=%d sandbox=%s",
            order_code, amount_rial, sandbox,
        )

        try:
            response = requests.post(
                ZIBAL_REQUEST_URL,
                json=payload,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
        except requests.ConnectionError as exc:
            logger.error("Zibal connection error during create_payment")
            raise GatewayConnectionError(
                "اتصال به درگاه زیبال برقرار نشد. لطفاً دوباره تلاش کنید.",
                code="connection_error",
            ) from exc
        except requests.Timeout as exc:
            logger.error("Zibal timeout during create_payment")
            raise GatewayConnectionError(
                "پاسخ درگاه زیبال در زمان مقرر دریافت نشد. لطفاً دوباره تلاش کنید.",
                code="timeout",
            ) from exc
        except requests.RequestException as exc:
            logger.error("Zibal request error during create_payment: %s", type(exc).__name__)
            raise GatewayConnectionError(
                "خطا در ارتباط با درگاه زیبال.",
                code="request_error",
            ) from exc

        # Parse response
        try:
            data = response.json()
        except (ValueError, TypeError) as exc:
            logger.error("Zibal returned non-JSON response: status=%d", response.status_code)
            raise GatewayResponseError(
                "پاسخ نامعتبر از درگاه زیبال دریافت شد.",
                code="invalid_json",
            ) from exc

        result_code = data.get("result")
        if result_code is None:
            logger.error("Zibal response missing 'result' field")
            raise GatewayResponseError(
                "ساختار پاسخ درگاه زیبال نامعتبر است.",
                code="missing_result",
            )

        if result_code != ZIBAL_RESULT_SUCCESS:
            message = data.get("message", "")
            logger.warning(
                "Zibal create_payment rejected: result=%s message=%s order=%s",
                result_code, message, order_code,
            )
            raise GatewayPaymentError(
                "درخواست پرداخت توسط درگاه زیبال رد شد.",
                code=f"zibal_{result_code}",
                details={"result": result_code, "message": message},
            )

        track_id = data.get("trackId")
        if not track_id:
            logger.error("Zibal response missing trackId despite result=100")
            raise GatewayResponseError(
                "شناسه‌ی پیگیری از درگاه زیبال دریافت نشد.",
                code="missing_track_id",
            )

        track_id_str = str(track_id)
        logger.info("Zibal create_payment success: order=%s trackId=%s", order_code, track_id_str)

        return PaymentCreationResult(
            track_id=track_id_str,
            gateway_url=self.build_redirect_url(track_id_str, sandbox=sandbox),
        )

    def build_redirect_url(self, track_id: str, *, sandbox: bool = False) -> str:
        """Build the Zibal payment page URL."""
        return f"{ZIBAL_REDIRECT_URL}{track_id}"

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
        """Verify a payment with Zibal after callback."""
        merchant = credentials.get("merchant", "").strip()
        if not merchant:
            raise GatewayCredentialError("Zibal merchant ID is not configured")

        effective_merchant = ZIBAL_SANDBOX_MERCHANT if sandbox else merchant

        payload = {
            "merchant": effective_merchant,
            "trackId": track_id,
        }

        logger.info("Zibal verify_payment: trackId=%s", track_id)

        try:
            response = requests.post(
                ZIBAL_VERIFY_URL,
                json=payload,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
        except requests.ConnectionError as exc:
            logger.error("Zibal connection error during verify_payment: trackId=%s", track_id)
            raise GatewayConnectionError(
                "اتصال به درگاه زیبال برای تأیید پرداخت برقرار نشد.",
                code="verify_connection_error",
            ) from exc
        except requests.Timeout as exc:
            logger.error("Zibal timeout during verify_payment: trackId=%s", track_id)
            raise GatewayConnectionError(
                "پاسخ تأیید از درگاه زیبال در زمان مقرر دریافت نشد.",
                code="verify_timeout",
            ) from exc
        except requests.RequestException as exc:
            logger.error("Zibal request error during verify: %s", type(exc).__name__)
            raise GatewayConnectionError(
                "خطا در ارتباط با درگاه زیبال برای تأیید.",
                code="verify_request_error",
            ) from exc

        # Parse response
        try:
            data = response.json()
        except (ValueError, TypeError) as exc:
            logger.error("Zibal verify returned non-JSON: status=%d trackId=%s", response.status_code, track_id)
            raise GatewayResponseError(
                "پاسخ نامعتبر از درگاه زیبال هنگام تأیید.",
                code="verify_invalid_json",
            ) from exc

        result_code = data.get("result")
        if result_code is None:
            logger.error("Zibal verify response missing 'result': trackId=%s", track_id)
            raise GatewayResponseError(
                "ساختار پاسخ تأیید درگاه زیبال نامعتبر است.",
                code="verify_missing_result",
            )

        # Check if verification was successful
        is_success = result_code in (ZIBAL_RESULT_SUCCESS, ZIBAL_RESULT_ALREADY_VERIFIED)

        # Amount verification — Zibal returns amount in Rial. A success result with a different or
        # unreadable amount must never be applied as a normal paid order; the evidence is carried in the
        # exception so the caller can persist it (money may have moved).
        if is_success:
            expected_rial = int(expected_amount) * TOMAN_TO_RIAL
            evidence = {
                "result_code": result_code,
                "ref_id": str(data.get("refNumber", ""))[:100],
                "card_number": str(data.get("cardNumber", ""))[:25],
                "status_code": data.get("status", 0),
                "expected_rial": expected_rial,
            }
            raw_amount = data.get("amount")
            try:
                returned_rial = int(raw_amount)
            except (TypeError, ValueError):
                logger.error("Zibal verify success without a usable amount: trackId=%s", track_id)
                raise GatewayResponseError(
                    "درگاه پرداخت را تأیید کرد اما مبلغ را اعلام نکرد.",
                    code="amount_unavailable",
                    details={"evidence": evidence},
                )
            evidence["returned_rial"] = returned_rial
            if returned_rial != expected_rial:
                logger.error(
                    "Zibal amount mismatch: expected=%d got=%d trackId=%s",
                    expected_rial, returned_rial, track_id,
                )
                raise GatewayAmountMismatchError(
                    "مبلغ تأییدشده با مبلغ سفارش مطابقت ندارد.",
                    code="amount_mismatch",
                    details={"expected_rial": expected_rial, "returned_rial": returned_rial, "evidence": evidence},
                )

        ref_id = str(data.get("refNumber", "")) if is_success else ""
        card_number = str(data.get("cardNumber", "")) if is_success else ""
        status_code = data.get("status", 0)
        message = data.get("message", "")

        if is_success:
            logger.info("Zibal verify success: trackId=%s refId=%s", track_id, ref_id)
        else:
            logger.warning(
                "Zibal verify failed: trackId=%s result=%s status=%s",
                track_id, result_code, status_code,
            )

        return PaymentVerificationResult(
            success=is_success,
            ref_id=ref_id,
            card_number=card_number,
            status_code=int(status_code) if status_code else 0,
            message=message,
        )
