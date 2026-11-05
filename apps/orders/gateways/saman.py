"""Saman / SEP (سامان / سپ) PSP adapter — contract-testable implementation, **contract UNVERIFIED**.

STATUS (read this before changing anything): no official, current Saman Electronic Payment technical document was reachable
on 2026-11-05 (``sep.ir`` is marketing-only; ``sep.shaparak.ir`` and the documentation hosts do not resolve from the build
environment). The wire contract below is encoded from SECONDHAND sources only and may not match the provider's current API:

* ``pkg.go.dev/github.com/aliworkshop/samanpayment`` — the JSON "token" variant: token request
  ``{action, TerminalId, RedirectUrl, TxnRandomSessionKey, ResNum, Amount, CellNumber}`` → ``{status, errorCode, errorDesc, token}``;
  callback ``{MID, State, Status, RRN, RefNum, ResNum, TerminalId, TraceNo, Amount, Wage, SecurePan}``;
  ``VerifyTransaction`` / ``ReverseTransaction`` ``{RefNum, TerminalNumber, TxnRandomSessionKey}`` →
  ``{Success, ResultCode, ResultDescription, TransactionDetail{RRN, RefNum, MaskedPan, OrginalAmount, AffectiveAmount, ...}}``.
* ``shetabit/multipay`` Saman driver — the legacy SOAP variant (``RequestToken`` / ``VerifyTransaction`` / ``ReverseTransaction``)
  and the form POST ``Token`` + ``RedirectUrl``.
* WordPress / PyPI wrappers — server IP must be whitelisted with Saman; host ``sep.shaparak.ir``.

Which variant (JSON vs SOAP) and which exact URLs are CURRENT is **unverified**. Therefore:

* ``documentation_blocked`` stays ``True`` — the adapter is NEVER selectable for store checkout, and for platform billing it is
  held behind the ``contract_verification`` + ``live_verification`` gates (``platform_gateway_matrix``): the platform owner must
  compare these constants with the official document and record the reference before any live use.
* The endpoint constants below are the single place to correct if the official document differs.
* Fail-closed by construction: a payment is reported successful ONLY when ``VerifyTransaction`` answers success AND the returned
  original amount equals the server-side expected amount AND the returned ``RefNum`` equals the callback's; the callback itself
  (``State``/``Status``) is never proof.

Flow: ``create_payment`` (token) → browser **form POST** of ``Token`` to the payment page → callback POST → ``verify_payment``.
There is no separate settle step in this contract (verification finalises), no documented inquiry (a missed callback cannot be
reconciled without the ``RefNum``), and ``CANCEL`` is ``ReverseTransaction``. Amounts are RIAL (Toman × 10, exactly once, here).
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
    GatewayVerificationError,
    PaymentCancelResult,
    PaymentCreationResult,
    PaymentGatewayAdapter,
    PaymentOperation,
    PaymentVerificationResult,
)

logger = logging.getLogger("payment")

# --- UNVERIFIED endpoint constants (see module docstring) --------------------------------------------------------------
SEP_TOKEN_URL = "https://sep.shaparak.ir/onlinepg/onlinepg"
SEP_PAY_URL = "https://sep.shaparak.ir/OnlinePG/OnlinePG"
SEP_VERIFY_URL = "https://sep.shaparak.ir/verifyTxnRandomSessionkey/ipg/VerifyTransaction"
SEP_REVERSE_URL = "https://sep.shaparak.ir/verifyTxnRandomSessionkey/ipg/ReverseTransaction"

CONNECT_TIMEOUT = 10
READ_TIMEOUT = 30
TOMAN_TO_RIAL = 10

#: ResultCode values treated as "verified" (0 = success; 2 = already verified — per secondhand wrapper docs, UNVERIFIED).
_VERIFY_OK = (0, 2)


class SamanAdapter(PaymentGatewayAdapter):
    """Saman / SEP PSP adapter (contract-testable; live use gated on verification)."""

    unique_payment_reference = True          # RefNum is globally unique ⇒ a RefNum can fulfil at most one attempt

    @property
    def redirect_host_suffixes(self) -> tuple[str, ...]:
        return ("shaparak.ir",)

    @property
    def code(self) -> str:
        return "saman"

    @property
    def display_name(self) -> str:
        return "بانک سامان (سپ)"

    @property
    def is_online(self) -> bool:
        return True

    @property
    def category(self) -> GatewayCategory:
        return GatewayCategory.PSP

    @property
    def documentation_blocked(self) -> bool:
        return True

    @property
    def required_credentials(self) -> list[str]:
        return ["terminal_id"]

    @property
    def credential_labels(self) -> dict[str, str]:
        return {"terminal_id": "شناسه‌ی پایانه (Terminal Id)", "transaction_key": "کلیدِ تراکنش (TxnRandomSessionKey — اختیاری)"}

    @property
    def onboarding_help(self) -> str:
        return (
            "شناسه‌ی پایانه (و در صورتِ لزوم کلیدِ تراکنش) را از بانک سامان بگیرید و IP سرور را نزدِ سپ ثبت کنید. "
            "قراردادِ فنیِ این آداپتر از منابعِ ثانویه است و باید با مستندِ رسمیِ جاری تطبیق داده شود؛ تا آن زمان استفاده‌ی زنده مسدود است."
        )

    @property
    def capabilities(self) -> frozenset[PaymentOperation]:
        return frozenset({PaymentOperation.CREATE, PaymentOperation.VERIFY, PaymentOperation.CANCEL})

    def validate_credentials(self, credentials: dict[str, str]) -> list[str]:
        errors = []
        if not (credentials.get("terminal_id") or "").strip():
            errors.append("شناسه‌ی پایانه (Terminal Id) الزامی است")
        return errors

    # -- HTTP ----------------------------------------------------------------------------------------------------------
    @staticmethod
    def _post(url: str, payload: dict) -> dict:
        try:
            response = requests.post(url, json=payload, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
        except requests.Timeout as exc:
            raise GatewayConnectionError("پاسخِ سپ در زمانِ مقرر نرسید.", code="timeout") from exc
        except requests.RequestException as exc:
            logger.error("Saman request error: %s", type(exc).__name__)
            raise GatewayConnectionError("اتصال به سپ برقرار نشد.", code="connection_error") from exc
        try:
            body = response.json()
        except (ValueError, TypeError) as exc:
            raise GatewayResponseError("پاسخِ نامعتبر از سپ.", code="invalid_json") from exc
        if not isinstance(body, dict):
            raise GatewayResponseError("ساختارِ پاسخِ سپ نامعتبر است.", code="invalid_structure")
        return body

    @staticmethod
    def _terminal(credentials: dict[str, str]) -> str:
        terminal = (credentials.get("terminal_id") or "").strip()
        if not terminal:
            raise GatewayCredentialError("Saman terminal_id is not configured", code="not_configured")
        return terminal

    # -- create ----------------------------------------------------------------------------------------------------------
    def create_payment(
        self, *, amount: Decimal, currency: str, callback_url: str, credentials: dict[str, str],
        order_code: str, description: str = "", sandbox: bool = False,
    ) -> PaymentCreationResult:
        terminal = self._terminal(credentials)
        amount_rial = int(amount) * TOMAN_TO_RIAL
        payload = {"action": "token", "TerminalId": terminal, "Amount": amount_rial, "ResNum": str(order_code),
                   "RedirectUrl": callback_url}
        key = (credentials.get("transaction_key") or "").strip()
        if key:
            payload["TxnRandomSessionKey"] = key
        body = self._post(SEP_TOKEN_URL, payload)
        if body.get("status") != 1:
            logger.warning("Saman token rejected: errorCode=%s order=%s", body.get("errorCode"), order_code)
            raise GatewayPaymentError(
                "درخواستِ پرداخت توسطِ سپ رد شد.", code=f"saman_{body.get('errorCode', 'rejected')}",
                details={"errorCode": body.get("errorCode")},
            )
        token = str(body.get("token") or "")
        if not token:
            raise GatewayResponseError("توکنِ پرداخت از سپ دریافت نشد.", code="missing_token")
        return PaymentCreationResult(
            track_id=str(order_code), gateway_url=SEP_PAY_URL,
            extra={"post_fields": {"Token": token}, "ResNum": str(order_code)},
        )

    def build_redirect_url(self, track_id: str, *, sandbox: bool = False) -> str:
        return SEP_PAY_URL

    # -- verify ----------------------------------------------------------------------------------------------------------
    def verify_payment(
        self, *, track_id: str, expected_amount: Decimal, currency: str, credentials: dict[str, str],
        callback_data: dict[str, Any], sandbox: bool = False,
    ) -> PaymentVerificationResult:
        """Verify with ``VerifyTransaction``. The callback is only a hint: success needs the provider's own answer, the exact
        original amount, and the same ``RefNum``. A callback that does not name OUR ``ResNum`` is rejected."""
        data = callback_data or {}
        ref_num = str(data.get("RefNum") or "").strip()
        state = str(data.get("State") or "").strip().upper()
        if state and state != "OK":
            return PaymentVerificationResult(success=False, status_code=0, message="پرداخت در درگاه موفق نبود.")
        if not ref_num:
            return PaymentVerificationResult(success=False, status_code=0, message="شماره‌ی مرجع (RefNum) دریافت نشد.")
        if str(data.get("ResNum") or "") != str(track_id):
            raise GatewayVerificationError("شناسه‌ی سفارشِ بازگشتی با این تلاش نمی‌خواند.", code="resnum_mismatch")
        terminal = self._terminal(credentials)
        payload = {"RefNum": ref_num, "TerminalNumber": int(terminal) if terminal.isdigit() else terminal}
        key = (credentials.get("transaction_key") or "").strip()
        if key:
            payload["TxnRandomSessionKey"] = key
        body = self._post(SEP_VERIFY_URL, payload)
        if not (body.get("Success") is True and body.get("ResultCode") in _VERIFY_OK):
            raise GatewayVerificationError("تأییدِ تراکنش توسطِ سپ ناموفق بود.", code=f"saman_{body.get('ResultCode', 'failed')}")
        detail = body.get("TransactionDetail") if isinstance(body.get("TransactionDetail"), dict) else {}
        expected_rial = int(expected_amount) * TOMAN_TO_RIAL
        evidence = {"expected_rial": expected_rial, "ref_num": ref_num[:60], "masked_pan": str(detail.get("MaskedPan", ""))[:25]}
        try:
            original = int(detail.get("OrginalAmount"))
        except (TypeError, ValueError):
            raise GatewayResponseError("مبلغِ تأییدشده توسطِ سپ خوانا/موجود نیست.", code="amount_unavailable",
                                       details={"evidence": evidence})
        evidence["returned_rial"] = original
        if original != expected_rial:
            raise GatewayAmountMismatchError("مبلغِ تأییدشده با مبلغِ سفارش مطابقت ندارد.", code="amount_mismatch",
                                             details={"evidence": evidence})
        if detail.get("ResNum") not in (None, "") and str(detail.get("ResNum")) != str(track_id):
            raise GatewayAmountMismatchError("شناسه‌ی سفارشِ تأییدشده با این تلاش مطابقت ندارد.", code="resnum_mismatch",
                                             details={"evidence": evidence})
        if str(detail.get("RefNum") or ref_num) != ref_num:
            raise GatewayAmountMismatchError("شماره‌ی مرجعِ تأییدشده با بازگشت مطابقت ندارد.", code="refnum_mismatch",
                                             details={"evidence": evidence})
        return PaymentVerificationResult(success=True, ref_id=ref_num, card_number=str(detail.get("MaskedPan", "")),
                                         status_code=int(body.get("ResultCode", 0)), message="")

    # -- reverse (CANCEL) ------------------------------------------------------------------------------------------------
    def cancel_payment(self, *, track_id: str, credentials: dict[str, str], sandbox: bool = False) -> PaymentCancelResult:
        """``ReverseTransaction`` — needs the RefNum (passed by the caller as ``credentials["_refNum"]``)."""
        ref_num = str(credentials.get("_refNum") or "").strip()
        if not ref_num:
            return PaymentCancelResult(success=False, status_code=0, message="RefNum موجود نیست.")
        terminal = self._terminal(credentials)
        payload = {"RefNum": ref_num, "TerminalNumber": int(terminal) if terminal.isdigit() else terminal}
        key = (credentials.get("transaction_key") or "").strip()
        if key:
            payload["TxnRandomSessionKey"] = key
        body = self._post(SEP_REVERSE_URL, payload)
        ok = body.get("Success") is True and body.get("ResultCode") in _VERIFY_OK
        return PaymentCancelResult(success=ok, status_code=int(body.get("ResultCode", -1) or 0), message="")
