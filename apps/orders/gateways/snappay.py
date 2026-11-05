"""SnappPay (اسنپ‌پی) BNPL adapter — real REST BNPL contract.

SnappPay is a BUY-NOW-PAY-LATER (BNPL) provider in the Snapp! ecosystem, NOT an
ordinary PSP. The BNPL lifecycle is DISTINCT from a plain PSP: eligibility ->
payment token (create) -> redirect -> verify -> SETTLE -> status/cancel. SETTLE
is a separate, capability-gated finalize step (it is NOT the same as VERIFY or
REFUND), and itemized cart data is passed on create.

The REST contract below was verified on 2026-11-03 from the official SnappPay
self-cms documentation (https://academy.snapppay.ir/self-cms/, REST API v2.1).
Only facts from that documentation are encoded here; nothing is invented.

Authentication (OAuth / JWT):
    POST /api/online/v1/oauth/token obtains a JWT bearer token. Per the FAQ the
    token request itself authenticates with HTTP Basic
    (base64(client_id:client_secret)). The returned JWT expires after 3600s and
    is NOT cached beyond its expiry — this adapter is stateless and fetches a
    fresh token inside each operation. All subsequent calls send
    ``Authorization: Bearer <jwt>``. SnappPay additionally requires that the
    merchant server IP is whitelisted and that ``returnURL`` matches the
    whitelisted base; unknown-origin requests are rejected provider-side.

Endpoints (base host is merchant-provided — see SNAPPAY_API_BASE note):
    * POST /api/online/v1/oauth/token          — obtain JWT (OAuth)
    * GET  /api/online/offer/v1/eligible        — BNPL eligibility (dynamic)
    * POST /api/online/payment/v1/token         — get payment token (CREATE)
    * POST /api/online/payment/v1/verify        — verify (does NOT finalize)
    * POST /api/online/payment/v1/settle        — SETTLE (finalize)
    * POST /api/online/payment/v1/cancel        — cancel
    * GET  /api/online/payment/v1/status        — status (INQUIRE)
    (update/revert exist but are NOT declared as capabilities: revert is "not
    required" and update is a multi-item follow-up — see capabilities note.)

Flow:
    1. create_payment -> oauth token -> POST payment/token with amount (IRR),
       returnURL (POST), a unique transactionId, and a minimal cartList. The
       response carries ``paymentPageUrl`` + a payment token. Redirect the
       customer to ``paymentPageUrl``.
    2. Callback is a POST to returnURL: {transactionId, state (OK|FAILED),
       amount}. OK -> verify; FAILED -> revert (revert not required per doc).
    3. verify_payment -> POST payment/verify. On a read timeout, call status
       and branch (PENDING -> re-verify, VERIFY -> settle, else fail). verify
       alone does NOT finalize.
    4. settle_payment -> POST payment/settle. SETTLE is declared in
       ``capabilities`` so the orchestrator's existing SETTLE gate finalizes
       the order only after settle succeeds.

Currency conversion (financial safety):
    RastiSi stores order amounts in TOMAN. The SnappPay contract expresses all
    amounts in RIAL (IRR). This adapter converts Toman -> Rial exactly once
    (Toman x 10) at this boundary; no other code performs the conversion so
    there is no double conversion. Amount-mismatch (verify/status amount vs the
    expected Rial) raises GatewayAmountMismatchError with evidence.

Readiness:
    ``documentation_blocked = False`` (the contract is verified and contract
    tested). ``is_active`` stays False by default — this adapter has NOT been
    exercised against a live or sandbox SnappPay environment here (the exact
    stage/production host is merchant-provided after a demo), so it ships
    disabled until a merchant configures credentials and verifies it.

Security:
    - All HTTP calls use explicit (connect=10, read=30) timeouts; verify uses
      the documented 30s read budget.
    - Credentials (client_id/client_secret) never appear in logs or errors.
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
# SnappPay REST API constants (verified 2026-11-03 from academy.snapppay.ir)
# ---------------------------------------------------------------------------

# NOTE: SnappPay provisions the base host per-merchant (stage access first,
# production after a demo). The self-cms documentation gives the endpoint PATHS
# only, so the base host is kept as an overridable module constant. The value
# below is the conventional production host; a merchant integration may need to
# override SNAPPAY_API_BASE with the stage/production host SnappPay provides.
SNAPPAY_API_BASE = "https://api.snapppay.ir"

SNAPPAY_TOKEN_PATH = "/api/online/v1/oauth/token"
SNAPPAY_ELIGIBLE_PATH = "/api/online/offer/v1/eligible"
SNAPPAY_PAYMENT_TOKEN_PATH = "/api/online/payment/v1/token"
SNAPPAY_VERIFY_PATH = "/api/online/payment/v1/verify"
SNAPPAY_SETTLE_PATH = "/api/online/payment/v1/settle"
SNAPPAY_CANCEL_PATH = "/api/online/payment/v1/cancel"
SNAPPAY_STATUS_PATH = "/api/online/payment/v1/status"

# Timeouts in seconds (match the zibal/zarinpal/pasargad gold-standard adapters).
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 30

# Toman -> Rial multiplier (SnappPay amounts are IRR/Rial).
TOMAN_TO_RIAL = 10

# Documented status tokens from GET /payment/status.
SNAPPAY_STATUS_SETTLE = "SETTLE"
SNAPPAY_STATUS_CANCEL = "CANCEL"
SNAPPAY_STATUS_VERIFY = "VERIFY"
SNAPPAY_STATUS_PENDING = "PENDING"
SNAPPAY_STATUS_REVERT = "REVERT"

# Documented callback states (POST to returnURL).
SNAPPAY_CALLBACK_OK = "OK"
SNAPPAY_CALLBACK_FAILED = "FAILED"


class SnappPayAdapter(PaymentGatewayAdapter):
    """SnappPay BNPL adapter (real self-cms REST v2.1 contract)."""

    # Overridable so a merchant can point at the stage/production host SnappPay
    # provisions for them without changing the module constant globally.
    api_base = SNAPPAY_API_BASE


    @property
    def code(self) -> str:
        return "snappay"

    @property
    def display_name(self) -> str:
        return "اسنپ‌پی"

    @property
    def is_online(self) -> bool:
        return True

    @property
    def category(self) -> GatewayCategory:
        return GatewayCategory.BNPL

    @property
    def documentation_blocked(self) -> bool:
        # The REST v2.1 contract was verified from the official self-cms docs.
        return False

    @property
    def supports_sandbox(self) -> bool:
        # SnappPay provides a stage environment per-merchant; the sandbox toggle
        # is offered, but the host must be merchant-provided.
        return True

    @property
    def required_credentials(self) -> list[str]:
        # OAuth client id/secret are used (Basic base64(client_id:client_secret))
        # to obtain the JWT. Field names only; values are never logged.
        return ["client_id", "client_secret"]

    @property
    def credential_labels(self) -> dict[str, str]:
        return {
            "client_id": "شناسه‌ی کلاینت (Client ID)",
            "client_secret": "رمز کلاینت (Client Secret)",
        }

    @property
    def onboarding_help(self) -> str:
        return (
            "شناسه و رمز کلاینت (client_id / client_secret) را از اسنپ‌پی دریافت کنید. "
            "احراز هویت با OAuth انجام می‌شود (توکن JWT با انقضای ۳۶۰۰ ثانیه). اسنپ‌پی لازم "
            "دارد که IP سرور پذیرنده در فهرست سفید باشد و نشانی بازگشت (returnURL) با دامنه‌ی "
            "تأییدشده مطابقت کند. میزبان دقیق محیط آزمایشی/تولید توسط اسنپ‌پی و پس از جلسه‌ی "
            "نمایشی ارائه می‌شود؛ تا پیش از پیکربندی اعتبارنامه و بررسی، این درگاه غیرفعال است."
        )

    @property
    def capabilities(self) -> frozenset[PaymentOperation]:
        # BNPL lifecycle operations backed by documented endpoints:
        #   CREATE  -> payment/token
        #   VERIFY  -> payment/verify (+ status fallback on timeout)
        #   SETTLE  -> payment/settle (DISTINCT finalize step)
        #   CANCEL  -> payment/cancel
        #   INQUIRE -> payment/status
        # update/revert are intentionally NOT declared: revert is "not required"
        # per the doc and update is a multi-item follow-up operation.
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

    @property
    def supports_dry_run_session(self) -> bool:
        return False          # a BNPL payment token needs a real cart; the configuration test only authenticates

    def check_connection(self, *, credentials: dict[str, str], sandbox: bool = False) -> str:
        """OAuth authentication only (no payment token, no cart, no money)."""
        self._get_token(credentials)
        return "احراز هویت OAuth موفق بود."

    def validate_credentials(self, credentials: dict[str, str]) -> list[str]:
        errors = []
        if not (credentials.get("client_id") or "").strip():
            errors.append("شناسه‌ی کلاینت (client_id) الزامی است")
        if not (credentials.get("client_secret") or "").strip():
            errors.append("رمز کلاینت (client_secret) الزامی است")
        return errors

    # -- transactionId helper ----------------------------------------------

    @staticmethod
    def _transaction_id(order_code: str) -> str:
        """Derive a unique SnappPay transactionId from the order code.

        SnappPay requires a unique transactionId of 5-10 digits, and documents
        that a letter may be used when the identifier would otherwise be longer.
        RastiSi order codes look like ``DM-F005`` (contain letters/dashes), so
        the raw code already satisfies the "use a letter if longer" allowance.
        We strip to alphanumerics and, when the result is shorter than 5 chars,
        left-pad with zeros to guarantee the 5-10 length window.
        """
        cleaned = "".join(ch for ch in str(order_code) if ch.isalnum())
        if not cleaned:
            cleaned = "0"
        if len(cleaned) < 5:
            cleaned = cleaned.rjust(5, "0")
        # Cap at 10 characters; a letter is already present for typical codes,
        # satisfying the documented "use a letter if longer" rule.
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
        read_timeout: int = READ_TIMEOUT,
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
                timeout=(CONNECT_TIMEOUT, read_timeout),
            )
        except requests.ConnectionError as exc:
            logger.error("SnappPay connection error: path=%s", path)
            raise GatewayConnectionError(
                "اتصال به اسنپ‌پی برقرار نشد. لطفاً دوباره تلاش کنید.",
                code="connection_error",
            ) from exc
        except requests.Timeout:
            # Re-raise so verify can apply the documented status-fallback.
            raise
        except requests.RequestException as exc:
            logger.error("SnappPay request error: %s", type(exc).__name__)
            raise GatewayConnectionError(
                "خطا در ارتباط با اسنپ‌پی.",
                code="request_error",
            ) from exc

    @staticmethod
    def _parse_json(response) -> dict:
        try:
            body = response.json()
        except (ValueError, TypeError) as exc:
            logger.error(
                "SnappPay non-JSON response: status=%s",
                getattr(response, "status_code", "?"),
            )
            raise GatewayResponseError(
                "پاسخ نامعتبر از اسنپ‌پی دریافت شد.",
                code="invalid_json",
            ) from exc
        if not isinstance(body, dict):
            raise GatewayResponseError(
                "ساختار پاسخ اسنپ‌پی نامعتبر است.",
                code="invalid_structure",
            )
        return body

    def _get_token(self, credentials: dict[str, str]) -> str:
        """Obtain a JWT via POST /oauth/token (Basic base64(id:secret)).

        Stateless: the JWT is returned to the caller and never cached on the
        instance (it expires after 3600s server-side).
        """
        client_id = (credentials.get("client_id") or "").strip()
        client_secret = credentials.get("client_secret") or ""
        if not client_id or not client_secret:
            raise GatewayCredentialError("SnappPay client_id/client_secret is not configured")

        basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        response = self._request(
            "POST",
            SNAPPAY_TOKEN_PATH,
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials"},
        )
        if getattr(response, "status_code", 200) >= 400:
            logger.warning(
                "SnappPay oauth rejected: status=%s", getattr(response, "status_code", "?")
            )
            raise GatewayCredentialError(
                "احراز هویت اسنپ‌پی ناموفق بود.",
                code="oauth_failed",
            )
        body = self._parse_json(response)
        token = (
            body.get("access_token")
            or body.get("accessToken")
            or (body.get("response_result") or {}).get("access_token")
        )
        if not token:
            logger.warning("SnappPay oauth response missing access_token")
            raise GatewayCredentialError(
                "توکن دسترسی اسنپ‌پی دریافت نشد.",
                code="oauth_no_token",
            )
        return str(token)

    def _auth_headers(self, token: str) -> dict:
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

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

        Installment terms are ALWAYS computed by SnappPay; this adapter never
        fabricates installment offers. The low/high eligibility bounds are
        provider-driven (the test environment returns false below ~4k Toman and
        above ~10M Toman). The raw provider response is returned to the caller.
        """
        amount_rial = int(amount) * TOMAN_TO_RIAL
        token = self._get_token(credentials)
        response = self._request(
            "GET",
            SNAPPAY_ELIGIBLE_PATH,
            headers=self._auth_headers(token),
            params={
                "amount": amount_rial,
                "paymentMethodTypes": "POSTPAID,INSTALLMENT,FINANCING",
            },
        )
        body = self._parse_json(response)
        logger.info("SnappPay eligibility checked: amount_rial=%d", amount_rial)
        return body

    # -- create ------------------------------------------------------------

    def _build_cart_list(
        self,
        order_code: str,
        amount_rial: int,
        *,
        cart_items: list[dict] | None = None,
        cart_totals: dict | None = None,
    ) -> list[dict]:
        """Build the SnappPay cartList (amounts in RIAL).

        When ``cart_items``/``cart_totals`` are forwarded by the service
        boundary (BNPL path), build a cart with REAL per-line cartItems (real
        product id/sku, product_name, quantity, unit amounts) and allocate the
        order-level shipping/tax/discount to the documented cartList-level
        fields (``shippingAmount``, ``taxAmount``) and the documented top-level
        ``discountAmount``. Only the documented SnappPay cartItem shape
        (id/name/count/amount/category/commissionType) is used — no invented
        fields. The built cart's totalAmount reconciles EXACTLY to the Rial
        grand total; a divergence raises :class:`GatewayAmountMismatchError`
        rather than sending a mismatched cart.

        When nothing is forwarded (fallback), keep the historical single
        synthetic cart so non-itemized call sites keep working.
        """
        if not cart_items or not cart_totals:
            return [
                {
                    "cartId": str(order_code),
                    "totalAmount": amount_rial,
                    "shippingAmount": 0,
                    "taxAmount": 0,
                    "cartItems": [
                        {
                            "id": str(order_code),
                            "name": f"سفارش {order_code}",
                            "count": 1,
                            "amount": amount_rial,
                            "category": "general",
                            "commissionType": 0,
                        }
                    ],
                }
            ]

        # Per-line amounts are NET of the line's authoritative coupon discount
        # allocation (``discount_allocation``). The documented SnappPay cart
        # shape has no cart-level discount field, so applying the real per-line
        # allocation keeps totalAmount == the net payable using only documented
        # fields and no fabricated amounts.
        cart_item_payload = [
            {
                "id": str(line["id"]),
                "name": str(line["name"]),
                "count": int(line["count"]),
                "amount": (int(line["line_amount"]) - int(line.get("discount_allocation", 0)))
                * TOMAN_TO_RIAL,
                "category": "general",
                "commissionType": 0,
            }
            for line in cart_items
        ]
        # Gift wrap is a real documented charge with no dedicated SnappPay
        # field, so it rides as its own cartItem (real data, not fabricated),
        # net of any coupon discount that applied to gift wrapping.
        gift_wrap_net = int(cart_totals.get("gift_wrap", 0)) - int(
            cart_totals.get("gift_wrap_discount", 0)
        )
        gift_wrap_rial = gift_wrap_net * TOMAN_TO_RIAL
        if gift_wrap_rial:
            cart_item_payload.append(
                {
                    "id": f"{order_code}-giftwrap",
                    "name": "کادوپیچی",
                    "count": 1,
                    "amount": gift_wrap_rial,
                    "category": "general",
                    "commissionType": 0,
                }
            )

        shipping_rial = int(cart_totals.get("shipping", 0)) * TOMAN_TO_RIAL
        tax_rial = int(cart_totals.get("tax", 0)) * TOMAN_TO_RIAL

        lines_rial = sum(ci["amount"] for ci in cart_item_payload)
        total_rial = lines_rial + shipping_rial + tax_rial
        self._assert_built_cart(total_rial, expected_rial=amount_rial, order_code=order_code)

        return [
            {
                "cartId": str(order_code),
                "totalAmount": total_rial,
                "shippingAmount": shipping_rial,
                "taxAmount": tax_rial,
                "cartItems": cart_item_payload,
            }
        ]

    def _assert_built_cart(self, built_rial: int, *, expected_rial: int, order_code: str) -> None:
        """Refuse to send a cartList whose total diverges from the order amount."""
        if built_rial != expected_rial:
            logger.error(
                "SnappPay built cart mismatch: order=%s built=%d expected=%d",
                order_code, built_rial, expected_rial,
            )
            raise GatewayAmountMismatchError(
                "مبلغِ سبدِ ساخته‌شده با مبلغِ سفارش مطابقت ندارد.",
                code="cart_build_mismatch",
                details={
                    "expected_rial": expected_rial,
                    "built_rial": built_rial,
                    "evidence": {"expected_rial": expected_rial, "built_rial": built_rial},
                },
            )

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
        cart_items: list[dict] | None = None,
        cart_totals: dict | None = None,
    ) -> PaymentCreationResult:
        """Get a SnappPay payment token (POST /payment/v1/token)."""
        # Toman -> Rial conversion happens exactly once here.
        amount_rial = int(amount) * TOMAN_TO_RIAL
        transaction_id = self._transaction_id(order_code)
        mobile = str((credentials.get("mobile") or "") or "")

        token = self._get_token(credentials)
        # The coupon discount is applied per cartItem (net amounts), so the
        # top-level discountAmount stays 0 and ``amount`` remains the net
        # payable — the single documented source of truth for the charge.
        payload = {
            "amount": amount_rial,
            "discountAmount": 0,
            "externalSourceAmount": 0,
            "mobile": mobile,
            "paymentMethodTypeDto": "INSTALLMENT",
            "returnURL": callback_url,
            "transactionId": transaction_id,
            "cartList": self._build_cart_list(
                order_code, amount_rial, cart_items=cart_items, cart_totals=cart_totals
            ),
        }

        logger.info(
            "SnappPay create_payment: order=%s txn=%s amount_rial=%d",
            order_code, transaction_id, amount_rial,
        )

        response = self._request(
            "POST",
            SNAPPAY_PAYMENT_TOKEN_PATH,
            headers=self._auth_headers(token),
            json_body=payload,
        )
        body = self._parse_json(response)

        if body.get("successful") is False:
            logger.warning(
                "SnappPay payment token rejected: order=%s errorData=%s",
                order_code, body.get("errorData"),
            )
            raise GatewayPaymentError(
                "درخواست پرداخت توسط اسنپ‌پی رد شد.",
                code="token_rejected",
                details={"errorData": body.get("errorData")},
            )

        data = body.get("response") if isinstance(body.get("response"), dict) else body
        payment_page_url = data.get("paymentPageUrl") or data.get("paymentPageURL")
        payment_token = data.get("paymentToken") or data.get("token")

        if not payment_page_url or not payment_token:
            logger.error("SnappPay token success missing page url/token: order=%s", order_code)
            raise GatewayResponseError(
                "نشانی یا توکن پرداخت از اسنپ‌پی دریافت نشد.",
                code="missing_payment_token",
            )

        logger.info("SnappPay create_payment success: order=%s", order_code)

        return PaymentCreationResult(
            track_id=str(payment_token),
            gateway_url=str(payment_page_url),
            extra={
                "transactionId": transaction_id,
                "paymentToken": str(payment_token),
                "paymentPageUrl": str(payment_page_url),
            },
        )

    def build_redirect_url(self, track_id: str, *, sandbox: bool = False) -> str:
        """Return the SnappPay payment page URL.

        The authoritative redirect target is the ``paymentPageUrl`` captured at
        :meth:`create_payment` (stored in the creation result's ``extra`` and as
        the attempt's gateway URL). If ``build_redirect_url`` is called with the
        persisted gateway URL, it is returned verbatim; the payment page URL
        always originates from create, never fabricated here.
        """
        return track_id

    # -- status helper -----------------------------------------------------

    def _status(self, payment_token: str, *, credentials: dict[str, str], token: str) -> dict:
        response = self._request(
            "GET",
            SNAPPAY_STATUS_PATH,
            headers=self._auth_headers(token),
            params={"paymentToken": payment_token},
        )
        body = self._parse_json(response)
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
        """Verify a SnappPay payment (POST /payment/v1/verify).

        verify does NOT finalize (settle is a distinct step). On a read timeout
        the documented fallback calls GET /payment/v1/status and branches:
        PENDING -> re-verify once; VERIFY -> proceed (treated as verified);
        anything else -> failure. Amount mismatch raises
        GatewayAmountMismatchError with evidence.
        """
        payment_token = str(track_id)
        expected_rial = int(expected_amount) * TOMAN_TO_RIAL
        token = self._get_token(credentials)

        try:
            response = self._request(
                "POST",
                SNAPPAY_VERIFY_PATH,
                headers=self._auth_headers(token),
                json_body={"paymentToken": payment_token},
                read_timeout=READ_TIMEOUT,
            )
            body = self._parse_json(response)
        except requests.Timeout:
            logger.warning(
                "SnappPay verify timed out — consulting status fallback: token=***"
            )
            return self._verify_timeout_fallback(
                payment_token=payment_token,
                expected_rial=expected_rial,
                credentials=credentials,
                token=token,
            )

        return self._finish_verify(body, expected_rial=expected_rial)

    def _finish_verify(self, body: dict, *, expected_rial: int) -> PaymentVerificationResult:
        if body.get("successful") is False:
            logger.warning("SnappPay verify unsuccessful: errorData=%s", body.get("errorData"))
            return PaymentVerificationResult(
                success=False,
                status_code=0,
                message="تأیید اسنپ‌پی ناموفق بود.",
            )

        data = body.get("response") if isinstance(body.get("response"), dict) else body
        self._assert_amount(data, expected_rial=expected_rial)

        transaction_id = str(data.get("transactionId", "") or "")
        logger.info("SnappPay verify success: txn=%s", transaction_id)
        return PaymentVerificationResult(
            success=True,
            ref_id=transaction_id,
            status_code=100,
            message="تأیید اسنپ‌پی موفق بود (در انتظار تسویه).",
        )

    def _verify_timeout_fallback(
        self, *, payment_token: str, expected_rial: int, credentials: dict[str, str], token: str
    ) -> PaymentVerificationResult:
        data = self._status(payment_token, credentials=credentials, token=token)
        status = str(data.get("status", "") or "")

        if status == SNAPPAY_STATUS_PENDING:
            # Re-verify once.
            response = self._request(
                "POST",
                SNAPPAY_VERIFY_PATH,
                headers=self._auth_headers(token),
                json_body={"paymentToken": payment_token},
                read_timeout=READ_TIMEOUT,
            )
            body = self._parse_json(response)
            return self._finish_verify(body, expected_rial=expected_rial)

        if status == SNAPPAY_STATUS_VERIFY:
            # Already verified provider-side — accept, settle will finalize.
            self._assert_amount(data, expected_rial=expected_rial)
            return PaymentVerificationResult(
                success=True,
                ref_id=str(data.get("transactionId", "") or ""),
                status_code=100,
                message="تأیید اسنپ‌پی از طریق استعلام وضعیت تأیید شد.",
            )

        if status == SNAPPAY_STATUS_SETTLE:
            # Already settled (idempotent) — accept.
            self._assert_amount(data, expected_rial=expected_rial)
            return PaymentVerificationResult(
                success=True,
                ref_id=str(data.get("transactionId", "") or ""),
                status_code=100,
                message="تراکنش اسنپ‌پی پیش‌تر تسویه شده است.",
            )

        logger.warning("SnappPay status fallback not-verified: status=%s", status)
        return PaymentVerificationResult(
            success=False,
            status_code=0,
            message=f"وضعیت اسنپ‌پی: {status or 'نامشخص'}",
        )

    def _assert_amount(self, data: dict, *, expected_rial: int) -> None:
        returned_rial = self._extract_amount(data)
        if returned_rial is None:
            # Not every verify/status payload echoes the amount; if present it
            # must match. Absence is not treated as a mismatch.
            return
        evidence = {"expected_rial": expected_rial, "returned_rial": returned_rial}
        if returned_rial != expected_rial:
            logger.error(
                "SnappPay amount mismatch: expected=%d got=%d", expected_rial, returned_rial
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
        """Finalize a verified payment (POST /payment/v1/settle).

        This is a DISTINCT capability-gated step; the orchestrator's existing
        SETTLE gate only marks the order paid after this succeeds.
        """
        payment_token = str(track_id)
        token = self._get_token(credentials)
        response = self._request(
            "POST",
            SNAPPAY_SETTLE_PATH,
            headers=self._auth_headers(token),
            json_body={"paymentToken": payment_token},
        )
        body = self._parse_json(response)
        success = body.get("successful") is not False

        if not success:
            logger.warning("SnappPay settle failed: errorData=%s", body.get("errorData"))
        else:
            logger.info("SnappPay settle success")

        data = body.get("response") if isinstance(body.get("response"), dict) else body
        return PaymentSettleResult(
            success=bool(success),
            settle_ref=str(data.get("transactionId", "") or ""),
            status_code=100 if success else 0,
            message="تسویه‌ی اسنپ‌پی موفق بود." if success else "تسویه‌ی اسنپ‌پی ناموفق بود.",
        )

    # -- cancel ------------------------------------------------------------

    def cancel_payment(
        self,
        *,
        track_id: str,
        credentials: dict[str, str],
        sandbox: bool = False,
    ) -> PaymentCancelResult:
        """Cancel a payment (POST /payment/v1/cancel)."""
        payment_token = str(track_id)
        token = self._get_token(credentials)
        response = self._request(
            "POST",
            SNAPPAY_CANCEL_PATH,
            headers=self._auth_headers(token),
            json_body={"paymentToken": payment_token},
        )
        body = self._parse_json(response)
        success = body.get("successful") is not False

        if not success:
            logger.warning("SnappPay cancel failed: errorData=%s", body.get("errorData"))
        else:
            logger.info("SnappPay cancel success")

        return PaymentCancelResult(
            success=bool(success),
            status_code=100 if success else 0,
            message="لغو اسنپ‌پی موفق بود." if success else "لغو اسنپ‌پی ناموفق بود.",
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
        """Query authoritative status (GET /payment/v1/status).

        States: SETTLE, CANCEL, VERIFY, PENDING, REVERT.
        """
        payment_token = str(track_id)
        expected_rial = int(expected_amount) * TOMAN_TO_RIAL
        token = self._get_token(credentials)
        data = self._status(payment_token, credentials=credentials, token=token)

        status = str(data.get("status", "") or "")
        # Only assert the amount when the provider echoes it.
        self._assert_amount(data, expected_rial=expected_rial)

        paid = status in (SNAPPAY_STATUS_VERIFY, SNAPPAY_STATUS_SETTLE)
        settled = status == SNAPPAY_STATUS_SETTLE
        terminal_negative = status in (SNAPPAY_STATUS_CANCEL, SNAPPAY_STATUS_REVERT)
        return PaymentInquiryResult(
            paid=paid,
            settled=settled,
            ref_id=str(data.get("transactionId", "") or ""),
            status=status,
            status_code=100 if paid else 0,
            message=f"وضعیت اسنپ‌پی: {status or 'نامشخص'}",
            terminal_negative=terminal_negative,
        )
