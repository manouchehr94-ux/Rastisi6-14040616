"""TorobPay (تربپی) BNPL adapter — real REST BNPL contract.

TorobPay is a BUY-NOW-PAY-LATER (BNPL) provider tied to the Torob
price-comparison platform and built on the Snapp-ecosystem BNPL stack, NOT an
ordinary PSP. The BNPL lifecycle is DISTINCT from a plain PSP: eligibility ->
payment token (create) -> redirect -> verify -> SETTLE -> status/cancel. SETTLE
is a separate, capability-gated finalize step, and itemized cart data is passed
on create.

The REST contract below was verified on 2026-11-03 from the provider-published
WooCommerce plugin source
(plugins.svn.wordpress.org/torobpay-for-woocommerce/trunk/class-torobpay-api.php).
It is implemented NATIVELY in Django — NO WordPress/PHP dependency is added; the
plugin source is used only as the published description of the HTTP contract.
Only facts from that source are encoded here; nothing is invented.

Authentication (OAuth password grant):
    POST api/online/v1/oauth/token with a form body
    {grant_type: 'password', scope: 'online-merchant', username: <client_username>,
    password: <client_password>} and a header
    ``Authorization: Basic base64(client_id:client_secret)`` plus
    ``Content-Type: application/x-www-form-urlencoded``. The response carries
    {access_token, expires_in (default ~3300s)}. On an HTTP 401 the adapter
    drops the token and re-authenticates exactly once. Subsequent calls send
    ``Authorization: Bearer <access_token>`` + ``application/json``. TorobPay
    requires the merchant server IP to be whitelisted and ``returnURL`` to match
    the whitelisted base; unknown-origin requests are rejected provider-side.

Endpoints (base host https://cpg.torobpay.com/ — the plugin's default):
    * POST api/online/v1/oauth/token           — OAuth password grant
    * GET  api/online/offer/v1/eligible         — eligibility
    * POST api/online/payment/v1/token          — get payment token (CREATE)
    * POST api/online/payment/v1/verify         — verify (does NOT finalize)
    * POST api/online/payment/v1/settle         — SETTLE (finalize)
    * POST api/online/payment/v1/cancel         — cancel
    * GET  api/online/payment/v1/status         — status (INQUIRE)
    (api/online/payment/v1/update is a multi-item follow-up and is NOT declared
    as a capability.)

Currency conversion (financial safety):
    RastiSi stores order amounts in TOMAN. The TorobPay contract expresses all
    amounts in RIAL (IRR). This adapter converts Toman -> Rial exactly once
    (Toman x 10) at this boundary; no other code performs the conversion so
    there is no double conversion. Amount-mismatch (verify/status amount vs the
    expected Rial) raises GatewayAmountMismatchError with evidence.

Readiness:
    ``documentation_blocked = False`` (the contract is verified and contract
    tested). ``is_active`` stays False by default — this adapter has NOT been
    exercised against a live or sandbox TorobPay environment here, so it ships
    disabled until a merchant configures credentials (and IP whitelisting) and
    verifies it.

Security:
    - All HTTP calls use explicit (connect=10, read=30) timeouts.
    - Credentials never appear in logs or errors.
    - Response parsing is strict; unexpected structure raises
      GatewayResponseError. Network failures become GatewayConnectionError.
"""

from __future__ import annotations

import base64
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
    PaymentCancelResult,
    PaymentCreationResult,
    PaymentGatewayAdapter,
    PaymentInquiryResult,
    PaymentOperation,
    PaymentSettleResult,
    PaymentVerificationResult,
)

logger = logging.getLogger("payment")

# ---------------------------------------------------------------------------
# TorobPay REST API constants (verified 2026-11-03 from the provider plugin)
# ---------------------------------------------------------------------------

# Default base host from the plugin's get_api_base_url(). Overridable so a
# merchant can point at an alternate host if TorobPay provisions one.
TOROBPAY_API_BASE = "https://cpg.torobpay.com"

TOROBPAY_TOKEN_PATH = "/api/online/v1/oauth/token"
TOROBPAY_ELIGIBLE_PATH = "/api/online/offer/v1/eligible"
TOROBPAY_PAYMENT_TOKEN_PATH = "/api/online/payment/v1/token"
TOROBPAY_VERIFY_PATH = "/api/online/payment/v1/verify"
TOROBPAY_SETTLE_PATH = "/api/online/payment/v1/settle"
TOROBPAY_CANCEL_PATH = "/api/online/payment/v1/cancel"
TOROBPAY_STATUS_PATH = "/api/online/payment/v1/status"

# Timeouts in seconds (match the gold-standard adapters).
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 30

# Toman -> Rial multiplier (TorobPay amounts are IRR/Rial).
TOMAN_TO_RIAL = 10

# Documented status tokens (shared Snapp-ecosystem lifecycle).
TOROBPAY_STATUS_SETTLE = "SETTLE"
TOROBPAY_STATUS_CANCEL = "CANCEL"
TOROBPAY_STATUS_VERIFY = "VERIFY"
TOROBPAY_STATUS_PENDING = "PENDING"
TOROBPAY_STATUS_REVERT = "REVERT"


class TorobPayAdapter(PaymentGatewayAdapter):
    """TorobPay BNPL adapter (real provider-plugin REST contract)."""

    # Overridable so a merchant can point at an alternate TorobPay host.
    api_base = TOROBPAY_API_BASE

    @property
    def code(self) -> str:
        return "torobpay"

    @property
    def display_name(self) -> str:
        return "تربپی"

    @property
    def is_online(self) -> bool:
        return True

    @property
    def category(self) -> GatewayCategory:
        return GatewayCategory.BNPL

    @property
    def documentation_blocked(self) -> bool:
        # The REST contract was verified from the provider-published plugin.
        return False

    @property
    def supports_sandbox(self) -> bool:
        return True

    @property
    def required_credentials(self) -> list[str]:
        # The plugin authenticates with Basic base64(client_id:client_secret)
        # for the token call AND a password grant using username/password.
        # Field names only; values are never logged.
        return ["client_id", "client_secret", "client_username", "client_password"]

    @property
    def credential_labels(self) -> dict[str, str]:
        return {
            "client_id": "شناسه‌ی کلاینت (Client ID)",
            "client_secret": "رمز کلاینت (Client Secret)",
            "client_username": "نام کاربری کلاینت (Client Username)",
            "client_password": "گذرواژه‌ی کلاینت (Client Password)",
        }

    @property
    def onboarding_help(self) -> str:
        return (
            "شناسه و رمز کلاینت (client_id / client_secret) به‌همراه نام کاربری و گذرواژه‌ی "
            "کلاینت را از تربپی دریافت کنید. احراز هویت با OAuth از نوع password grant انجام "
            "می‌شود (هدر Basic با client_id:client_secret و بدنه‌ی password grant). تربپی لازم "
            "دارد که IP سرور پذیرنده در فهرست سفید باشد و نشانی بازگشت (returnURL) با دامنه‌ی "
            "تأییدشده مطابقت کند؛ تا پیش از پیکربندی اعتبارنامه و بررسی، این درگاه غیرفعال است."
        )

    @property
    def capabilities(self) -> frozenset[PaymentOperation]:
        # BNPL lifecycle operations backed by documented endpoints:
        #   CREATE  -> payment/token
        #   VERIFY  -> payment/verify
        #   SETTLE  -> payment/settle (DISTINCT finalize step)
        #   CANCEL  -> payment/cancel
        #   INQUIRE -> payment/status
        # payment/update is intentionally NOT declared (multi-item follow-up).
        return frozenset(
            {
                PaymentOperation.CREATE,
                PaymentOperation.VERIFY,
                PaymentOperation.SETTLE,
                PaymentOperation.CANCEL,
                PaymentOperation.INQUIRE,
            }
        )

    # -- credential validation ---------------------------------------------

    def validate_credentials(self, credentials: dict[str, str]) -> list[str]:
        errors = []
        if not (credentials.get("client_id") or "").strip():
            errors.append("شناسه‌ی کلاینت (client_id) الزامی است")
        if not (credentials.get("client_secret") or "").strip():
            errors.append("رمز کلاینت (client_secret) الزامی است")
        if not (credentials.get("client_username") or "").strip():
            errors.append("نام کاربری کلاینت (client_username) الزامی است")
        if not (credentials.get("client_password") or "").strip():
            errors.append("گذرواژه‌ی کلاینت (client_password) الزامی است")
        return errors

    # -- transactionId helper ----------------------------------------------

    @staticmethod
    def _transaction_id(order_code: str) -> str:
        """Derive a unique transactionId from the order code.

        Same Snapp-ecosystem rule as SnappPay: a unique 5-10 character id where
        a letter is acceptable. RastiSi order codes contain letters, so the
        cleaned code already satisfies the rule; short codes are left-padded.
        """
        cleaned = "".join(ch for ch in str(order_code) if ch.isalnum())
        if not cleaned:
            cleaned = "0"
        if len(cleaned) < 5:
            cleaned = cleaned.rjust(5, "0")
        return cleaned[:10]

    # -- low-level HTTP helpers --------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        headers: dict,
        json_body: dict | None = None,
        data: dict | None = None,
        params: dict | None = None,
    ):
        url = f"{self.api_base.rstrip('/')}{path}"
        try:
            return requests.request(
                method,
                url,
                headers=headers,
                json=json_body,
                data=data,
                params=params,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
        except requests.ConnectionError as exc:
            logger.error("TorobPay connection error: path=%s", path)
            raise GatewayConnectionError(
                "اتصال به تربپی برقرار نشد. لطفاً دوباره تلاش کنید.",
                code="connection_error",
            ) from exc
        except requests.Timeout as exc:
            logger.error("TorobPay timeout: path=%s", path)
            raise GatewayConnectionError(
                "پاسخ تربپی در زمان مقرر دریافت نشد. لطفاً دوباره تلاش کنید.",
                code="timeout",
            ) from exc
        except requests.RequestException as exc:
            logger.error("TorobPay request error: %s", type(exc).__name__)
            raise GatewayConnectionError(
                "خطا در ارتباط با تربپی.",
                code="request_error",
            ) from exc

    @staticmethod
    def _parse_json(response) -> dict:
        try:
            body = response.json()
        except (ValueError, TypeError) as exc:
            logger.error(
                "TorobPay non-JSON response: status=%s",
                getattr(response, "status_code", "?"),
            )
            raise GatewayResponseError(
                "پاسخ نامعتبر از تربپی دریافت شد.",
                code="invalid_json",
            ) from exc
        if not isinstance(body, dict):
            raise GatewayResponseError(
                "ساختار پاسخ تربپی نامعتبر است.",
                code="invalid_structure",
            )
        return body

    def _get_token(self, credentials: dict[str, str]) -> str:
        """Obtain an access token via the OAuth password grant.

        Stateless: the token is returned to the caller and never cached on the
        instance (it expires after ~3300s server-side per expires_in).
        """
        client_id = (credentials.get("client_id") or "").strip()
        client_secret = credentials.get("client_secret") or ""
        username = (credentials.get("client_username") or "").strip()
        password = credentials.get("client_password") or ""
        if not (client_id and client_secret and username and password):
            raise GatewayCredentialError("TorobPay credentials are not fully configured")

        basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        response = self._request(
            "POST",
            TOROBPAY_TOKEN_PATH,
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "password",
                "scope": "online-merchant",
                "username": username,
                "password": password,
            },
        )
        if getattr(response, "status_code", 200) >= 400:
            logger.warning(
                "TorobPay oauth rejected: status=%s", getattr(response, "status_code", "?")
            )
            raise GatewayCredentialError(
                "احراز هویت تربپی ناموفق بود.",
                code="oauth_failed",
            )
        body = self._parse_json(response)
        token = body.get("access_token") or body.get("accessToken")
        if not token:
            logger.warning("TorobPay oauth response missing access_token")
            raise GatewayCredentialError(
                "توکن دسترسی تربپی دریافت نشد.",
                code="oauth_no_token",
            )
        return str(token)

    def _auth_headers(self, token: str) -> dict:
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _authed_request(
        self,
        method: str,
        path: str,
        *,
        credentials: dict[str, str],
        token: str,
        json_body: dict | None = None,
        params: dict | None = None,
    ):
        """Perform an authenticated request; on HTTP 401 drop the token and
        re-authenticate exactly once, then retry. Returns (response, token)."""
        response = self._request(
            method, path, headers=self._auth_headers(token), json_body=json_body, params=params
        )
        if getattr(response, "status_code", None) == 401:
            logger.info("TorobPay 401 — dropping token and re-authenticating once: path=%s", path)
            token = self._get_token(credentials)
            response = self._request(
                method, path, headers=self._auth_headers(token), json_body=json_body, params=params
            )
        return response, token

    @staticmethod
    def _unwrap(body: dict) -> dict:
        return body.get("response") if isinstance(body.get("response"), dict) else body

    @staticmethod
    def _extract_amount(data: dict) -> int | None:
        raw = data.get("amount")
        if raw is None:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    def _assert_amount(self, data: dict, *, expected_rial: int) -> None:
        returned_rial = self._extract_amount(data)
        if returned_rial is None:
            return
        if returned_rial != expected_rial:
            logger.error(
                "TorobPay amount mismatch: expected=%d got=%d", expected_rial, returned_rial
            )
            raise GatewayAmountMismatchError(
                "مبلغ تأییدشده با مبلغ سفارش مطابقت ندارد.",
                code="amount_mismatch",
                details={
                    "expected_rial": expected_rial,
                    "returned_rial": returned_rial,
                    "evidence": {
                        "expected_rial": expected_rial,
                        "returned_rial": returned_rial,
                    },
                },
            )

    # -- eligibility (BNPL) ------------------------------------------------

    def check_bnpl_eligibility(
        self,
        *,
        amount: Decimal,
        currency: str,
        credentials: dict[str, str],
        customer: dict[str, Any] | None = None,
        sandbox: bool = False,
    ) -> dict[str, Any]:
        """GET /offer/v1/eligible?amount=<IRR> — return the provider payload.

        Mirrors the plugin's is_merchant_eligible. Installment terms are always
        computed by TorobPay; this adapter never fabricates installment offers.
        The raw provider response is returned to the caller.
        """
        amount_rial = int(amount) * TOMAN_TO_RIAL
        token = self._get_token(credentials)
        response, _token = self._authed_request(
            "GET",
            TOROBPAY_ELIGIBLE_PATH,
            credentials=credentials,
            token=token,
            params={"amount": amount_rial},
        )
        body = self._parse_json(response)
        logger.info("TorobPay eligibility checked: amount_rial=%d", amount_rial)
        return body

    # -- create ------------------------------------------------------------

    @staticmethod
    def _build_cart_list(order_code: str, amount_rial: int) -> list[dict]:
        """Build a minimal valid single-cart cartList from order_code + amount.

        The RastiSi service boundary passes only amount + order_code at create,
        so a single synthetic cart with one cartItem is built here (the plugin's
        cartList item shape). Richer per-line itemization is a documented
        follow-up once the checkout boundary forwards the full basket.
        """
        return [
            {
                "cartId": str(order_code),
                "totalAmount": amount_rial,
                "taxAmount": 0,
                "shippingAmount": 0,
                "isShipmentIncluded": True,
                "isTaxIncluded": True,
                "cartItems": [
                    {
                        "id": str(order_code),
                        "name": f"سفارش {order_code}",
                        "count": 1,
                        "amount": amount_rial,
                        "category": "general",
                        "product_id": str(order_code),
                        "page_url": "",
                    }
                ],
            }
        ]

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
        """Get a TorobPay payment token (POST /payment/v1/token)."""
        amount_rial = int(amount) * TOMAN_TO_RIAL
        transaction_id = self._transaction_id(order_code)

        token = self._get_token(credentials)
        payload = {
            "amount": amount_rial,
            "paymentMethodTypeDto": "INSTALLMENT",
            "returnURL": callback_url,
            "transactionId": transaction_id,
            "discountAmount": 0,
            "cartList": self._build_cart_list(order_code, amount_rial),
        }

        logger.info(
            "TorobPay create_payment: order=%s txn=%s amount_rial=%d",
            order_code, transaction_id, amount_rial,
        )

        response, _token = self._authed_request(
            "POST",
            TOROBPAY_PAYMENT_TOKEN_PATH,
            credentials=credentials,
            token=token,
            json_body=payload,
        )
        body = self._parse_json(response)

        if body.get("successful") is False:
            logger.warning(
                "TorobPay payment token rejected: order=%s errorData=%s",
                order_code, body.get("errorData"),
            )
            raise GatewayPaymentError(
                "درخواست پرداخت توسط تربپی رد شد.",
                code="token_rejected",
                details={"errorData": body.get("errorData")},
            )

        data = self._unwrap(body)
        payment_page_url = data.get("paymentPageUrl") or data.get("paymentPageURL")
        payment_token = data.get("paymentToken") or data.get("token")

        if not payment_token:
            logger.error("TorobPay token success missing token: order=%s", order_code)
            raise GatewayResponseError(
                "توکن پرداخت از تربپی دریافت نشد.",
                code="missing_payment_token",
            )

        logger.info("TorobPay create_payment success: order=%s", order_code)

        return PaymentCreationResult(
            track_id=str(payment_token),
            gateway_url=str(payment_page_url) if payment_page_url else None,
            extra={
                "transactionId": transaction_id,
                "paymentToken": str(payment_token),
                "paymentPageUrl": str(payment_page_url) if payment_page_url else "",
            },
        )

    def build_redirect_url(self, track_id: str, *, sandbox: bool = False) -> str:
        """Return the TorobPay payment page URL.

        The authoritative redirect target is the ``paymentPageUrl`` captured at
        :meth:`create_payment` (stored in the creation result's ``extra`` and as
        the attempt's gateway URL). The URL always originates from create.
        """
        return track_id

    # -- verify ------------------------------------------------------------

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
        """Verify a TorobPay payment (POST /payment/v1/verify {paymentToken}).

        verify does NOT finalize (settle is a distinct step). Amount mismatch
        raises GatewayAmountMismatchError with evidence.
        """
        payment_token = str(track_id)
        expected_rial = int(expected_amount) * TOMAN_TO_RIAL
        token = self._get_token(credentials)

        response, _token = self._authed_request(
            "POST",
            TOROBPAY_VERIFY_PATH,
            credentials=credentials,
            token=token,
            json_body={"paymentToken": payment_token},
        )
        body = self._parse_json(response)

        if body.get("successful") is False:
            logger.warning("TorobPay verify unsuccessful: errorData=%s", body.get("errorData"))
            return PaymentVerificationResult(
                success=False,
                status_code=0,
                message="تأیید تربپی ناموفق بود.",
            )

        data = self._unwrap(body)
        self._assert_amount(data, expected_rial=expected_rial)

        transaction_id = str(data.get("transactionId", "") or "")
        logger.info("TorobPay verify success: txn=%s", transaction_id)
        return PaymentVerificationResult(
            success=True,
            ref_id=transaction_id,
            status_code=100,
            message="تأیید تربپی موفق بود (در انتظار تسویه).",
        )

    # -- settle (DISTINCT finalize step) -----------------------------------

    def settle_payment(
        self,
        *,
        track_id: str,
        amount: Decimal,
        currency: str,
        credentials: dict[str, str],
        sandbox: bool = False,
    ) -> PaymentSettleResult:
        """Finalize a verified payment (POST /payment/v1/settle {paymentToken}).

        This is a DISTINCT capability-gated step; the orchestrator's existing
        SETTLE gate only marks the order paid after this succeeds.
        """
        payment_token = str(track_id)
        token = self._get_token(credentials)
        response, _token = self._authed_request(
            "POST",
            TOROBPAY_SETTLE_PATH,
            credentials=credentials,
            token=token,
            json_body={"paymentToken": payment_token},
        )
        body = self._parse_json(response)
        success = body.get("successful") is not False

        if not success:
            logger.warning("TorobPay settle failed: errorData=%s", body.get("errorData"))
        else:
            logger.info("TorobPay settle success")

        data = self._unwrap(body)
        return PaymentSettleResult(
            success=bool(success),
            settle_ref=str(data.get("transactionId", "") or ""),
            status_code=100 if success else 0,
            message="تسویه‌ی تربپی موفق بود." if success else "تسویه‌ی تربپی ناموفق بود.",
        )

    # -- cancel ------------------------------------------------------------

    def cancel_payment(
        self,
        *,
        track_id: str,
        credentials: dict[str, str],
        sandbox: bool = False,
    ) -> PaymentCancelResult:
        """Cancel a payment (POST /payment/v1/cancel {paymentToken})."""
        payment_token = str(track_id)
        token = self._get_token(credentials)
        response, _token = self._authed_request(
            "POST",
            TOROBPAY_CANCEL_PATH,
            credentials=credentials,
            token=token,
            json_body={"paymentToken": payment_token},
        )
        body = self._parse_json(response)
        success = body.get("successful") is not False

        if not success:
            logger.warning("TorobPay cancel failed: errorData=%s", body.get("errorData"))
        else:
            logger.info("TorobPay cancel success")

        return PaymentCancelResult(
            success=bool(success),
            status_code=100 if success else 0,
            message="لغو تربپی موفق بود." if success else "لغو تربپی ناموفق بود.",
        )

    # -- inquire (status) --------------------------------------------------

    def inquire_payment(
        self,
        *,
        track_id: str,
        expected_amount: Decimal,
        currency: str,
        credentials: dict[str, str],
        sandbox: bool = False,
    ) -> PaymentInquiryResult:
        """Query authoritative status (GET /payment/v1/status {paymentToken}).

        States: SETTLE, CANCEL, VERIFY, PENDING, REVERT.
        """
        payment_token = str(track_id)
        expected_rial = int(expected_amount) * TOMAN_TO_RIAL
        token = self._get_token(credentials)
        response, _token = self._authed_request(
            "GET",
            TOROBPAY_STATUS_PATH,
            credentials=credentials,
            token=token,
            params={"paymentToken": payment_token},
        )
        body = self._parse_json(response)
        data = self._unwrap(body)

        status = str(data.get("status", "") or "")
        self._assert_amount(data, expected_rial=expected_rial)

        paid = status in (TOROBPAY_STATUS_VERIFY, TOROBPAY_STATUS_SETTLE)
        settled = status == TOROBPAY_STATUS_SETTLE
        return PaymentInquiryResult(
            paid=paid,
            settled=settled,
            ref_id=str(data.get("transactionId", "") or ""),
            status=status,
            status_code=100 if paid else 0,
            message=f"وضعیت تربپی: {status or 'نامشخص'}",
        )
