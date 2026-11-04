"""Pasargad (پاسارگاد / PEP) PSP adapter — real Dorsa IPG REST contract.

Bank Pasargad electronic payment (PEP) exposes the "Dorsa" Internet Payment
Gateway (IPG). The REST contract implemented below was verified on 2026-11-03
from the official ``pep-ipg/Dorsa-IPG-pasargad`` documentation
(``api-reference.md``, ``usage-guides.md``, ``error-codes.md`` under
raw.githubusercontent.com/pep-ipg/Dorsa-IPG-pasargad/main/docs/). Only facts
from those documents are encoded here; nothing is invented.

Authentication (Bearer token, NOT RSA):
    The Dorsa REST contract authenticates with ``username``/``password`` and
    returns a short-lived (10-minute) Bearer token via ``POST /token/getToken``.
    Every subsequent call sends ``Authorization: Bearer <token>``. On HTTP 401
    the adapter re-authenticates once and retries. The adapter is STATELESS:
    a fresh token is fetched inside each create/verify/inquire/cancel call and
    is never cached on the instance.

Endpoints (base host https://pep.shaparak.ir/dorsa1/):
    * POST /token/getToken                   — obtain Bearer token
    * POST /api/payment/purchase             — create a payment (CREATE)
    * POST /api/payment/payment-inquiry      — authoritative status (INQUIRE)
    * POST /api/payment/verify-transactions  — finalize a purchase (VERIFY)
    * POST /api/payment/confirm-transactions — confirm (internal helper only)
    * POST /api/payment/reverse-transactions — reverse within deadline (CANCEL)

Flow:
    1. create_payment -> getToken -> POST purchase; returns data.url + urlId.
    2. build_redirect_url -> returns the data.url obtained at create. The
       customer's browser is redirected to pep.shaparak.ir/dorsa1/{urlId}. The
       provider requires the ``Referer`` header on that browser redirect to be
       the merchant domain; emitting that redirect is the VIEW's job — this
       adapter only returns the URL string.
    3. Provider redirects back to the callback URL with query params
       invoiceId, status, referenceNumber, trackId.
    4. verify_payment -> getToken -> payment-inquiry (read authoritative status
       + amount; assert amount == expected Rial) -> verify-transactions to
       finalize. ``verify`` (not ``confirm``) is the normal finalize step; if
       the merchant does not verify within the deadline (default 25 min) the
       transaction auto-reverts to the customer.

Currency conversion (financial safety):
    RastiSi stores order amounts in TOMAN. The Dorsa contract expresses amounts
    in RIAL. This adapter converts Toman -> Rial exactly once (Toman x 10) at
    this boundary, for both the purchase request and the amount-match check in
    verify. No other code performs the conversion, so there is no double
    conversion. Amounts are integer Rial end to end for this provider.

Security:
    - All HTTP calls use explicit (connect=10, read=30) timeouts.
    - Credentials (username/password/terminal) never appear in logs or errors.
    - Response parsing is strict; unexpected structure raises
      GatewayResponseError.
    - Network failures are wrapped in GatewayConnectionError.
"""

from __future__ import annotations

import datetime
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
    GatewayVerificationError,
    PaymentCancelResult,
    PaymentCreationResult,
    PaymentGatewayAdapter,
    PaymentInquiryResult,
    PaymentOperation,
    PaymentVerificationResult,
)

logger = logging.getLogger("payment")

# ---------------------------------------------------------------------------
# Dorsa IPG REST API constants (verified 2026-11-03 from pep-ipg docs)
# ---------------------------------------------------------------------------

PASARGAD_API_BASE = "https://pep.shaparak.ir/dorsa1"
PASARGAD_TOKEN_URL = f"{PASARGAD_API_BASE}/token/getToken"
PASARGAD_PURCHASE_URL = f"{PASARGAD_API_BASE}/api/payment/purchase"
PASARGAD_INQUIRY_URL = f"{PASARGAD_API_BASE}/api/payment/payment-inquiry"
PASARGAD_VERIFY_URL = f"{PASARGAD_API_BASE}/api/payment/verify-transactions"
PASARGAD_CONFIRM_URL = f"{PASARGAD_API_BASE}/api/payment/confirm-transactions"
PASARGAD_REVERSE_URL = f"{PASARGAD_API_BASE}/api/payment/reverse-transactions"

# Timeouts in seconds (match the zibal/zarinpal gold-standard adapters).
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 30

# Toman to Rial multiplier (Dorsa amounts are Rial).
TOMAN_TO_RIAL = 10

# serviceType for a standard online purchase, per api-reference.md.
PASARGAD_SERVICE_TYPE_PURCHASE = "PURCHASE"
# Default serviceCode documented for a purchase (configurable per merchant).
PASARGAD_DEFAULT_SERVICE_CODE = 8

# ---------------------------------------------------------------------------
# Dorsa result / status codes (from error-codes.md — do NOT invent codes)
# ---------------------------------------------------------------------------

PASARGAD_CODE_SUCCESS = 0           # موفق — success
PASARGAD_CODE_FAILURE = 1           # ناموفق — failure
PASARGAD_CODE_UNKNOWN = 2           # نامشخص — unknown
PASARGAD_CODE_NOT_AUTHORIZED = 401  # عدم احراز هویت — re-authenticate
PASARGAD_CODE_INVOICE_NOT_UNIQUE = 13003   # شماره فاکتور تکراری
PASARGAD_CODE_TOKEN_EXPIRED = 13008        # توکن منقضی شده
PASARGAD_CODE_TXN_NOT_FOUND = 13016        # تراکنش یافت نشد
PASARGAD_CODE_UNSUCCESSFUL = 13025         # ناموفق
PASARGAD_CODE_CALLBACK_DOMAIN_INVALID = 13028  # دامنه‌ی بازگشت نامعتبر
PASARGAD_CODE_CONFIRMED = 13029            # تأییدشده (موفق)
PASARGAD_CODE_REVERSED = 13033             # بازگشت‌خورده
PASARGAD_CODE_VERIFY_RECEIVED = 13034      # وریفای موفق دریافت شد (در زمان مهلت تأیید می‌شود)
PASARGAD_CODE_CARDHOLDER_CANCELED = 13045  # انصراف دارنده‌ی کارت
PASARGAD_CODE_ALREADY_SETTLED = 13046      # قبلاً تسویه شده
PASARGAD_CODE_AMOUNT_MISMATCH = 13071      # مبلغ با مبلغ نهایی مطابقت ندارد
PASARGAD_CODE_ALREADY_VERIFIED = 13428     # قبلاً وریفای شده

# Inquiry statuses that mean the payment is a paid success.
PASARGAD_PAID_STATUSES = frozenset(
    {
        PASARGAD_CODE_SUCCESS,          # 0
        PASARGAD_CODE_CONFIRMED,        # 13029
        PASARGAD_CODE_VERIFY_RECEIVED,  # 13034
    }
)

# Minimal human-readable map for the codes we reference (Persian).
_CODE_MESSAGES: dict[int, str] = {
    PASARGAD_CODE_SUCCESS: "موفق",
    PASARGAD_CODE_FAILURE: "ناموفق",
    PASARGAD_CODE_UNKNOWN: "نامشخص",
    PASARGAD_CODE_NOT_AUTHORIZED: "عدم احراز هویت",
    PASARGAD_CODE_INVOICE_NOT_UNIQUE: "شماره فاکتور تکراری است",
    PASARGAD_CODE_TOKEN_EXPIRED: "توکن منقضی شده است",
    PASARGAD_CODE_TXN_NOT_FOUND: "تراکنش یافت نشد",
    PASARGAD_CODE_UNSUCCESSFUL: "تراکنش ناموفق",
    PASARGAD_CODE_CALLBACK_DOMAIN_INVALID: "دامنه‌ی بازگشت نامعتبر است",
    PASARGAD_CODE_CONFIRMED: "تأییدشده",
    PASARGAD_CODE_REVERSED: "تراکنش بازگشت خورد",
    PASARGAD_CODE_VERIFY_RECEIVED: "وریفای موفق دریافت شد",
    PASARGAD_CODE_CARDHOLDER_CANCELED: "انصراف دارنده‌ی کارت",
    PASARGAD_CODE_ALREADY_SETTLED: "قبلاً تسویه شده است",
    PASARGAD_CODE_AMOUNT_MISMATCH: "مبلغ با مبلغ نهایی مطابقت ندارد",
    PASARGAD_CODE_ALREADY_VERIFIED: "قبلاً وریفای شده است",
}


def _code_message(code: int) -> str:
    """Return the documented Persian message for a Dorsa code (or a generic)."""
    return _CODE_MESSAGES.get(code, f"کد وضعیت {code}")


# ---------------------------------------------------------------------------
# Gregorian -> Jalali conversion (self-contained; no new dependency)
# ---------------------------------------------------------------------------


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    """Convert a Gregorian date to a Jalali (Solar Hijri) (year, month, day).

    Standard integer algorithm (Behrooz Abbasi / common public-domain form);
    kept dependency-free and testable. Returns a (jy, jm, jd) tuple.
    """
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy - 1600
    gm2 = gm - 1
    gd2 = gd - 1

    g_day_no = 365 * gy2 + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400
    g_day_no += g_d_m[gm2] + gd2
    # Leap-year correction for January/February of a Gregorian leap year.
    if gm2 > 1 and ((gy % 4 == 0 and gy % 100 != 0) or (gy % 400 == 0)):
        g_day_no += 1

    j_day_no = g_day_no - 79
    j_np = j_day_no // 12053
    j_day_no %= 12053

    jy = 979 + 33 * j_np + 4 * (j_day_no // 1461)
    j_day_no %= 1461

    if j_day_no >= 366:
        jy += (j_day_no - 1) // 365
        j_day_no = (j_day_no - 1) % 365

    if j_day_no < 186:
        jm = 1 + j_day_no // 31
        jd = 1 + (j_day_no % 31)
    else:
        jm = 7 + (j_day_no - 186) // 30
        jd = 1 + ((j_day_no - 186) % 30)

    return jy, jm, jd


def current_jalali_date_string(today: datetime.date | None = None) -> str:
    """Return the current Jalali date as a ``"YYYY-MM-DD"`` string.

    ``today`` is injectable for deterministic testing.
    """
    today = today or datetime.date.today()
    jy, jm, jd = gregorian_to_jalali(today.year, today.month, today.day)
    return f"{jy:04d}-{jm:02d}-{jd:02d}"


class PasargadAdapter(PaymentGatewayAdapter):
    """Bank Pasargad (Dorsa IPG) online PSP adapter."""

    @property
    def redirect_host_suffixes(self) -> tuple[str, ...]:
        return ("shaparak.ir",)

    @property
    def code(self) -> str:
        return "pasargad"

    @property
    def display_name(self) -> str:
        return "بانک پاسارگاد"

    @property
    def is_online(self) -> bool:
        return True

    @property
    def category(self) -> GatewayCategory:
        return GatewayCategory.PSP

    @property
    def documentation_blocked(self) -> bool:
        # The official Dorsa REST contract was verified from the pep-ipg docs.
        return False

    @property
    def supports_sandbox(self) -> bool:
        # The verified docs expose a single production host and no separate
        # sandbox base URL, so no unverified sandbox host is offered.
        return False

    @property
    def required_credentials(self) -> list[str]:
        # Dorsa REST uses username/password + terminal + serviceCode — NOT an
        # RSA private key. Field names only; values are never logged.
        return ["username", "password", "terminalNumber", "serviceCode"]

    @property
    def credential_labels(self) -> dict[str, str]:
        return {
            "username": "نام کاربری درگاه (Username)",
            "password": "گذرواژه‌ی درگاه (Password)",
            "terminalNumber": "شماره‌ی پایانه (Terminal Number)",
            "serviceCode": "کد سرویس (Service Code — پیش‌فرض ۸)",
        }

    @property
    def onboarding_help(self) -> str:
        return (
            "نام کاربری، گذرواژه و شماره‌ی پایانه‌ی درگاه درسا (پاسارگاد / PEP) را از "
            "پذیرنده‌ی بانک پاسارگاد دریافت کنید. کد سرویس به‌صورت پیش‌فرض ۸ است و در صورت "
            "نیاز قابل تغییر است. احراز هویت با توکن Bearer ده‌دقیقه‌ای انجام می‌شود و نیازی به "
            "کلید خصوصی RSA ندارد. قرارداد REST مطابق مستندات رسمی درسا پیاده‌سازی شده است؛ پیش از "
            "فعال‌سازیِ واقعی، درگاه را با یک تراکنش آزمایشیِ مجاز بررسی کنید."
        )

    @property
    def capabilities(self) -> frozenset[PaymentOperation]:
        # Operations backed by documented Dorsa endpoints:
        #   CREATE  -> purchase
        #   VERIFY  -> payment-inquiry + verify-transactions
        #   INQUIRE -> payment-inquiry
        #   CANCEL  -> reverse-transactions (reverse within deadline)
        # REFUND/SETTLE are NOT declared: the docs expose no post-settlement
        # refund or separate capture endpoint beyond reverse-within-deadline.
        return frozenset(
            {
                PaymentOperation.CREATE,
                PaymentOperation.VERIFY,
                PaymentOperation.INQUIRE,
                PaymentOperation.CANCEL,
            }
        )

    # -- credential validation ---------------------------------------------

    def validate_credentials(self, credentials: dict[str, str]) -> list[str]:
        """Validate presence/shape of Dorsa credentials (no values in errors)."""
        errors = []
        if not (credentials.get("username") or "").strip():
            errors.append("نام کاربری درگاه الزامی است")
        if not (credentials.get("password") or "").strip():
            errors.append("گذرواژه‌ی درگاه الزامی است")
        if not (credentials.get("terminalNumber") or "").strip():
            errors.append("شماره‌ی پایانه الزامی است")
        service_code = str(credentials.get("serviceCode") or "").strip()
        if not service_code:
            errors.append("کد سرویس الزامی است")
        elif not service_code.isdigit():
            errors.append("کد سرویس باید عددی باشد")
        return errors

    # -- low-level HTTP helpers --------------------------------------------

    def _post(self, url: str, *, json_body: dict, headers: dict | None = None):
        """POST with explicit timeouts; wrap network failures uniformly."""
        try:
            return requests.post(
                url,
                json=json_body,
                headers=headers or {},
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
        except requests.ConnectionError as exc:
            logger.error("Pasargad connection error: url=%s", url)
            raise GatewayConnectionError(
                "اتصال به درگاه پاسارگاد برقرار نشد. لطفاً دوباره تلاش کنید.",
                code="connection_error",
            ) from exc
        except requests.Timeout as exc:
            logger.error("Pasargad timeout: url=%s", url)
            raise GatewayConnectionError(
                "پاسخ درگاه پاسارگاد در زمان مقرر دریافت نشد. لطفاً دوباره تلاش کنید.",
                code="timeout",
            ) from exc
        except requests.RequestException as exc:
            logger.error("Pasargad request error: %s", type(exc).__name__)
            raise GatewayConnectionError(
                "خطا در ارتباط با درگاه پاسارگاد.",
                code="request_error",
            ) from exc

    @staticmethod
    def _parse_json(response) -> dict:
        try:
            body = response.json()
        except (ValueError, TypeError) as exc:
            logger.error(
                "Pasargad non-JSON response: status=%s",
                getattr(response, "status_code", "?"),
            )
            raise GatewayResponseError(
                "پاسخ نامعتبر از درگاه پاسارگاد دریافت شد.",
                code="invalid_json",
            ) from exc
        if not isinstance(body, dict):
            raise GatewayResponseError(
                "ساختار پاسخ درگاه پاسارگاد نامعتبر است.",
                code="invalid_structure",
            )
        return body

    def _get_token(self, credentials: dict[str, str]) -> str:
        """Acquire a fresh Bearer token via POST /token/getToken.

        Stateless: the token is returned to the caller and never cached on the
        instance (it expires after 10 minutes server-side).
        """
        username = (credentials.get("username") or "").strip()
        password = credentials.get("password") or ""
        if not username or not password:
            raise GatewayCredentialError("Pasargad username/password is not configured")

        response = self._post(
            PASARGAD_TOKEN_URL,
            json_body={"username": username, "password": password},
        )
        body = self._parse_json(response)
        result_code = body.get("resultCode")
        token = body.get("token")

        if result_code != PASARGAD_CODE_SUCCESS or not token:
            logger.warning("Pasargad getToken rejected: resultCode=%s", result_code)
            raise GatewayCredentialError(
                "احراز هویت درگاه پاسارگاد ناموفق بود.",
                code=f"pasargad_{result_code}",
                details={"resultCode": result_code},
            )
        return str(token)

    @staticmethod
    def _auth_headers(token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def _authed_post(
        self, url: str, *, json_body: dict, credentials: dict[str, str], token: str
    ):
        """POST with a Bearer token; on HTTP 401 re-authenticate once and retry.

        Returns a ``(response, token)`` tuple so the caller can reuse the
        (possibly refreshed) token.
        """
        response = self._post(url, json_body=json_body, headers=self._auth_headers(token))
        if getattr(response, "status_code", None) == 401:
            logger.info("Pasargad 401 — re-authenticating once and retrying: url=%s", url)
            token = self._get_token(credentials)
            response = self._post(
                url, json_body=json_body, headers=self._auth_headers(token)
            )
        return response, token

    # -- create ------------------------------------------------------------

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
        """Create a Dorsa purchase (POST /api/payment/purchase)."""
        terminal = (credentials.get("terminalNumber") or "").strip()
        if not terminal:
            raise GatewayCredentialError("Pasargad terminalNumber is not configured")
        service_code = int(
            str(credentials.get("serviceCode") or PASARGAD_DEFAULT_SERVICE_CODE)
        )

        # Toman -> Rial conversion happens exactly once here.
        amount_rial = int(amount) * TOMAN_TO_RIAL

        token = self._get_token(credentials)
        payload = {
            "amount": amount_rial,
            "invoice": order_code,
            "invoiceDate": current_jalali_date_string(),
            "serviceCode": service_code,
            "serviceType": PASARGAD_SERVICE_TYPE_PURCHASE,
            "callbackApi": callback_url,
            "terminalNumber": terminal,
        }

        logger.info(
            "Pasargad create_payment: order=%s amount_rial=%d", order_code, amount_rial
        )

        response, _token = self._authed_post(
            PASARGAD_PURCHASE_URL,
            json_body=payload,
            credentials=credentials,
            token=token,
        )
        body = self._parse_json(response)

        result_code = body.get("resultCode")
        if result_code != PASARGAD_CODE_SUCCESS:
            logger.warning(
                "Pasargad purchase rejected: resultCode=%s order=%s",
                result_code, order_code,
            )
            raise GatewayPaymentError(
                "درخواست پرداخت توسط درگاه پاسارگاد رد شد.",
                code=f"pasargad_{result_code}",
                details={
                    "resultCode": result_code,
                    "message": body.get("resultMsg") or _code_message(
                        result_code if isinstance(result_code, int) else -1
                    ),
                },
            )

        data = body.get("data")
        if not isinstance(data, dict):
            raise GatewayResponseError(
                "ساختار پاسخ درگاه پاسارگاد نامعتبر است.",
                code="missing_data",
            )
        url_id = data.get("urlId")
        gateway_url = data.get("url")
        if not gateway_url or not url_id:
            logger.error("Pasargad purchase success missing url/urlId: order=%s", order_code)
            raise GatewayResponseError(
                "نشانی پرداخت از درگاه پاسارگاد دریافت نشد.",
                code="missing_url",
            )

        logger.info("Pasargad create_payment success: order=%s urlId=%s", order_code, url_id)

        return PaymentCreationResult(
            track_id=str(order_code),
            gateway_url=str(gateway_url),
            extra={"urlId": str(url_id), "invoice": str(order_code)},
        )

    def build_redirect_url(self, track_id: str, *, sandbox: bool = False) -> str:
        """Return the Dorsa payment page URL.

        NOTE: ``track_id`` here is expected to be the full ``data.url`` captured
        from :meth:`create_payment` (persisted as the attempt's gateway URL).
        The provider requires that, when the browser is redirected to that URL,
        the ``Referer`` header equals the merchant domain — emitting that
        redirect (and the Referer) is the VIEW's responsibility; the adapter
        only returns the URL string.
        """
        return track_id

    # -- verify ------------------------------------------------------------

    def _inquiry(self, invoice: str, *, credentials: dict[str, str], token: str):
        """POST /api/payment/payment-inquiry — authoritative status read."""
        response, token = self._authed_post(
            PASARGAD_INQUIRY_URL,
            json_body={"invoiceId": invoice},
            credentials=credentials,
            token=token,
        )
        body = self._parse_json(response)
        data = body.get("data")
        if not isinstance(data, dict):
            raise GatewayResponseError(
                "ساختار پاسخ استعلام درگاه پاسارگاد نامعتبر است.",
                code="inquiry_missing_data",
            )
        return data, token

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
        """Verify + finalize a Dorsa purchase after the callback.

        Flow: getToken -> payment-inquiry (authoritative status + amount) ->
        assert amount matches expected Rial -> verify-transactions to finalize.
        ``track_id`` is the invoice (order_code). The ``urlId`` needed for
        verify-transactions is taken from ``callback_data`` (persisted from
        create) or from the inquiry response.
        """
        invoice = str(track_id)
        expected_rial = int(expected_amount) * TOMAN_TO_RIAL

        token = self._get_token(credentials)
        data, token = self._inquiry(invoice, credentials=credentials, token=token)

        status = data.get("status")
        try:
            status_code = int(status)
        except (TypeError, ValueError):
            logger.error("Pasargad inquiry returned non-numeric status: invoice=%s", invoice)
            raise GatewayResponseError(
                "وضعیت تراکنش از درگاه پاسارگاد نامعتبر است.",
                code="inquiry_bad_status",
            )

        ref_id = str(data.get("referenceNumber", "") or "")
        masked_card = str(data.get("cardNumber", "") or "")
        url_id = str(callback_data.get("urlId") or data.get("url") or "")

        is_paid = status_code in PASARGAD_PAID_STATUSES

        if not is_paid:
            logger.warning(
                "Pasargad inquiry not-paid: invoice=%s status=%s", invoice, status_code
            )
            return PaymentVerificationResult(
                success=False,
                ref_id=ref_id,
                card_number=masked_card,
                status_code=status_code,
                message=_code_message(status_code),
            )

        # Paid according to inquiry — assert the amount matches before finalize.
        raw_amount = data.get("amount")
        evidence = {
            "expected_rial": expected_rial,
            "ref_id": ref_id[:100],
            "card_number": masked_card[:25],
            "status": status_code,
        }
        if raw_amount is None:
            logger.error("Pasargad inquiry paid but amount missing: invoice=%s", invoice)
            raise GatewayResponseError(
                "درگاه پرداخت را تأیید کرد اما مبلغ را اعلام نکرد.",
                code="amount_unavailable",
                details={"evidence": evidence},
            )
        try:
            returned_rial = int(raw_amount)
        except (TypeError, ValueError):
            logger.error("Pasargad inquiry unreadable amount: invoice=%s", invoice)
            raise GatewayResponseError(
                "مبلغ اعلام‌شده توسط درگاه پاسارگاد خوانا نیست.",
                code="amount_unreadable",
                details={"evidence": evidence},
            )
        evidence["returned_rial"] = returned_rial
        if returned_rial != expected_rial:
            logger.error(
                "Pasargad amount mismatch: expected=%d got=%d invoice=%s",
                expected_rial, returned_rial, invoice,
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

        # Finalize with verify-transactions (the normal finalize step).
        response, token = self._authed_post(
            PASARGAD_VERIFY_URL,
            json_body={"invoice": invoice, "urlId": url_id},
            credentials=credentials,
            token=token,
        )
        verify_body = self._parse_json(response)
        verify_code = verify_body.get("resultCode")

        # Success codes for finalize: 0 (success) and 13428 (already verified,
        # idempotent).
        if verify_code not in (PASARGAD_CODE_SUCCESS, PASARGAD_CODE_ALREADY_VERIFIED):
            logger.warning(
                "Pasargad verify-transactions failed: invoice=%s resultCode=%s",
                invoice, verify_code,
            )
            raise GatewayVerificationError(
                "تأیید نهایی تراکنش توسط درگاه پاسارگاد ناموفق بود.",
                code=f"pasargad_{verify_code}",
                details={
                    "resultCode": verify_code,
                    "evidence": evidence,
                },
            )

        verify_data = verify_body.get("data")
        if isinstance(verify_data, dict):
            ref_id = str(verify_data.get("referenceNumber", ref_id) or ref_id)
            masked_card = str(verify_data.get("maskedCardNumber", masked_card) or masked_card)

        logger.info("Pasargad verify success: invoice=%s refId=%s", invoice, ref_id)

        return PaymentVerificationResult(
            success=True,
            ref_id=ref_id,
            card_number=masked_card,
            status_code=status_code,
            message=_code_message(status_code),
        )

    # -- inquire (capability) ----------------------------------------------

    def inquire_payment(
        self,
        *,
        track_id: str,
        expected_amount: Decimal,
        currency: str,
        credentials: dict[str, str],
        sandbox: bool = False,
    ) -> PaymentInquiryResult:
        """Query authoritative status via POST /api/payment/payment-inquiry."""
        invoice = str(track_id)
        token = self._get_token(credentials)
        data, _token = self._inquiry(invoice, credentials=credentials, token=token)

        status = data.get("status")
        try:
            status_code = int(status)
        except (TypeError, ValueError):
            raise GatewayResponseError(
                "وضعیت تراکنش از درگاه پاسارگاد نامعتبر است.",
                code="inquiry_bad_status",
            )

        paid = status_code in PASARGAD_PAID_STATUSES
        return PaymentInquiryResult(
            paid=paid,
            settled=status_code == PASARGAD_CODE_ALREADY_SETTLED or paid,
            ref_id=str(data.get("referenceNumber", "") or ""),
            status=str(status_code),
            status_code=status_code,
            message=_code_message(status_code),
        )

    # -- cancel / reverse (capability) -------------------------------------

    def cancel_payment(
        self,
        *,
        track_id: str,
        credentials: dict[str, str],
        sandbox: bool = False,
    ) -> PaymentCancelResult:
        """Reverse a purchase within the deadline via reverse-transactions.

        The reverse endpoint requires both the invoice and the urlId. The urlId
        is passed through ``credentials`` here as ``_urlId`` by the caller (the
        reverse is only meaningful for a known, verified-within-deadline
        transaction). Per the docs, reverse applies only to purchase/split and
        requires the transaction to have been verified.
        """
        invoice = str(track_id)
        url_id = str(credentials.get("_urlId") or credentials.get("urlId") or "")

        token = self._get_token(credentials)
        response, _token = self._authed_post(
            PASARGAD_REVERSE_URL,
            json_body={"invoice": invoice, "urlId": url_id},
            credentials=credentials,
            token=token,
        )
        body = self._parse_json(response)
        result_code = body.get("resultCode")
        success = result_code in (PASARGAD_CODE_SUCCESS, PASARGAD_CODE_REVERSED)

        if not success:
            logger.warning(
                "Pasargad reverse failed: invoice=%s resultCode=%s", invoice, result_code
            )
        else:
            logger.info("Pasargad reverse success: invoice=%s", invoice)

        return PaymentCancelResult(
            success=success,
            status_code=result_code if isinstance(result_code, int) else -1,
            message=_code_message(result_code if isinstance(result_code, int) else -1),
        )
