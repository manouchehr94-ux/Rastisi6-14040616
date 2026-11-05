"""Mellat / Behpardakht (ملت / به‌پرداخت) PSP adapter — contract-testable implementation, **contract UNVERIFIED**.

STATUS (read this before changing anything): no official, current Behpardakht technical document was reachable on 2026-11-05
(``behpardakht.com`` / ``api.mellatbank.ir`` do not resolve from the build environment). The SOAP contract below is encoded from
SECONDHAND sources and may differ from the provider's current API:

* ``shetabit/multipay`` Behpardakht driver (``raw.githubusercontent.com``, read 2026-11-05): operations ``bpPayRequest``,
  ``bpVerifyRequest``, ``bpSettleRequest``, ``bpReversalRequest``; purchase params ``terminalId, userName, userPassword, orderId,
  amount (rial), localDate (Ymd), localTime, additionalData, callBackUrl, payerId``; verify/settle/reversal params ``terminalId,
  userName, userPassword, orderId, saleOrderId, saleReferenceId``; purchase response ``"ResCode,RefId"``; browser **form POST**
  of ``RefId``; callback ``ResCode, RefId, SaleOrderId, SaleReferenceId, CardHolderPan``; verify result ``43`` = already
  verified; settle result ``45`` = already settled; reversal on a failed verify/settle.
* a third-party copy of the 2013 "Mellat PGW User Manual Rev 1.1" and the WSDL location ``bpm.shaparak.ir/pgwchannel/services/pgw?wsdl``.

Which of this is CURRENT is **unverified**. Therefore ``documentation_blocked`` stays ``True`` (never selectable for store checkout)
and platform billing holds it behind the ``contract_verification`` + ``live_verification`` gates. The endpoint/namespace constants
below are the single place to correct.

Safety rules that do NOT depend on the contract being right:
* A callback is never proof: fulfilment needs ``bpVerifyRequest`` success AND ``bpSettleRequest`` success (SETTLE is a DISTINCT
  capability — the platform bridge only reports success after both).
* ``48`` (reversed) is deliberately NOT treated as settled (a community driver accepts it; a reversed sale must never fulfil).
* Verification uses OUR order id and requires ``SaleOrderId`` to equal it; ``SaleReferenceId`` is unique per sale
  (``unique_payment_reference``) so it can fulfil at most one attempt.
* Amounts are RIAL (Toman × 10 exactly once, here). Mellat's verify has no amount echo — the amount is bound to the order at
  ``bpPayRequest`` by the bank; this is a documented limitation of the secondhand contract.
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal
from typing import Any
from xml.etree import ElementTree
from xml.sax.saxutils import escape

import requests

from .base import (
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
    PaymentSettleResult,
    PaymentVerificationResult,
)

logger = logging.getLogger("payment")

# --- UNVERIFIED endpoint constants (see module docstring) --------------------------------------------------------------
MELLAT_SERVICE_URL = "https://bpm.shaparak.ir/pgwchannel/services/pgw"
MELLAT_PAY_URL = "https://bpm.shaparak.ir/pgwchannel/startpay.mellat"
MELLAT_NAMESPACE = "http://interfaces.core.sw.bps.com/"

CONNECT_TIMEOUT = 10
READ_TIMEOUT = 30
TOMAN_TO_RIAL = 10
MAX_RESPONSE_BYTES = 64 * 1024

RES_OK = "0"
RES_VERIFIED_ALREADY = "43"
RES_SETTLED_ALREADY = "45"
RES_REVERSED = "48"
#: provider answers that prove the sale can never complete (used for reconciliation: ⇒ fail, never fulfil)
_TERMINAL_NEGATIVE = frozenset({"48", "49"})


def _tehran_now():
    from django.utils import timezone

    return timezone.localtime()


class MellatAdapter(PaymentGatewayAdapter):
    """Behpardakht Mellat PSP adapter (contract-testable; live use gated on verification)."""

    unique_payment_reference = True

    @property
    def redirect_host_suffixes(self) -> tuple[str, ...]:
        return ("shaparak.ir",)

    @property
    def code(self) -> str:
        return "mellat"

    @property
    def display_name(self) -> str:
        return "بانک ملت (به‌پرداخت)"

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
        return ["terminal_id", "username", "password"]

    @property
    def credential_labels(self) -> dict[str, str]:
        return {"terminal_id": "شناسه‌ی پایانه (Terminal Id)", "username": "نام کاربری", "password": "گذرواژه"}

    @property
    def onboarding_help(self) -> str:
        return (
            "شناسه‌ی پایانه، نام‌کاربری و گذرواژه را از به‌پرداخت ملت بگیرید و IP سرور را در بانک ثبت کنید. قراردادِ فنیِ این آداپتر "
            "(SOAP: pay/verify/settle/inquiry/reversal) از منابعِ ثانویه است و باید با مستندِ رسمیِ جاری تطبیق داده شود؛ تا آن زمان "
            "استفاده‌ی زنده مسدود است."
        )

    @property
    def capabilities(self) -> frozenset[PaymentOperation]:
        return frozenset({
            PaymentOperation.CREATE, PaymentOperation.VERIFY, PaymentOperation.SETTLE,
            PaymentOperation.INQUIRE, PaymentOperation.CANCEL,
        })

    def validate_credentials(self, credentials: dict[str, str]) -> list[str]:
        errors = []
        terminal = (credentials.get("terminal_id") or "").strip()
        if not terminal:
            errors.append("شناسه‌ی پایانه (Terminal Id) الزامی است")
        elif not terminal.isdigit():
            errors.append("شناسه‌ی پایانه باید عددی باشد")
        if not (credentials.get("username") or "").strip():
            errors.append("نام کاربری الزامی است")
        if not (credentials.get("password") or "").strip():
            errors.append("گذرواژه الزامی است")
        return errors

    # -- SOAP --------------------------------------------------------------------------------------------------------------
    def _auth(self, credentials: dict[str, str]) -> dict[str, str]:
        terminal = (credentials.get("terminal_id") or "").strip()
        username = (credentials.get("username") or "").strip()
        password = credentials.get("password") or ""
        if not (terminal and username and password):
            raise GatewayCredentialError("Mellat credentials are not configured", code="not_configured")
        return {"terminalId": terminal, "userName": username, "userPassword": password}

    @staticmethod
    def _envelope(operation: str, params: dict[str, Any]) -> bytes:
        inner = "".join(f"<{k}>{escape(str(v))}</{k}>" for k, v in params.items())
        return (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
            f'xmlns:int="{MELLAT_NAMESPACE}"><soapenv:Body><int:{operation}>{inner}</int:{operation}></soapenv:Body></soapenv:Envelope>'
        ).encode("utf-8")

    def _call(self, operation: str, params: dict[str, Any]) -> str:
        """Returns the SOAP ``return`` text (e.g. ``"0,RefId"`` or ``"43"``). Response size is capped; XML is parsed without
        entity expansion (ElementTree does not resolve external entities)."""
        try:
            response = requests.post(
                MELLAT_SERVICE_URL, data=self._envelope(operation, params), timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""},
            )
        except requests.Timeout as exc:
            raise GatewayConnectionError("پاسخِ به‌پرداخت در زمانِ مقرر نرسید.", code="timeout") from exc
        except requests.RequestException as exc:
            logger.error("Mellat request error: op=%s %s", operation, type(exc).__name__)
            raise GatewayConnectionError("اتصال به به‌پرداخت برقرار نشد.", code="connection_error") from exc
        content = getattr(response, "content", b"") or b""
        if len(content) > MAX_RESPONSE_BYTES:
            raise GatewayResponseError("پاسخِ به‌پرداخت بیش از حد بزرگ است.", code="response_too_large")
        if re.search(rb"<!DOCTYPE|<!ENTITY", content, flags=re.IGNORECASE):
            raise GatewayResponseError("پاسخِ به‌پرداخت شاملِ DTD است و رد شد.", code="unsafe_xml")
        try:
            root = ElementTree.fromstring(content)
        except ElementTree.ParseError as exc:
            raise GatewayResponseError("پاسخِ XMLِ نامعتبر از به‌پرداخت.", code="invalid_xml") from exc
        for node in root.iter():
            if node.tag.rsplit("}", 1)[-1] == "return":
                return (node.text or "").strip()
        raise GatewayResponseError("ساختارِ پاسخِ به‌پرداخت نامعتبر است.", code="missing_return")

    # -- create --------------------------------------------------------------------------------------------------------------
    def create_payment(
        self, *, amount: Decimal, currency: str, callback_url: str, credentials: dict[str, str],
        order_code: str, description: str = "", sandbox: bool = False,
    ) -> PaymentCreationResult:
        if not str(order_code).isdigit():
            raise GatewayPaymentError("شناسه‌ی سفارشِ ملت باید عددی باشد.", code="order_id_not_numeric")
        now = _tehran_now()
        params = {
            **self._auth(credentials), "orderId": str(order_code), "amount": int(amount) * TOMAN_TO_RIAL,
            "localDate": now.strftime("%Y%m%d"), "localTime": now.strftime("%H%M%S"),
            "additionalData": "", "callBackUrl": callback_url, "payerId": 0,
        }
        result = self._call("bpPayRequest", params)
        code, _, ref_id = result.partition(",")
        if code != RES_OK or not ref_id.strip():
            logger.warning("Mellat bpPayRequest rejected: code=%s order=%s", code, order_code)
            raise GatewayPaymentError("درخواستِ پرداخت توسطِ ملت رد شد.", code=f"mellat_{code or 'empty'}",
                                      details={"ResCode": code})
        ref_id = ref_id.strip()
        return PaymentCreationResult(
            track_id=str(order_code), gateway_url=MELLAT_PAY_URL,
            extra={"RefId": ref_id, "post_fields": {"RefId": ref_id}},
        )

    def build_redirect_url(self, track_id: str, *, sandbox: bool = False) -> str:
        return MELLAT_PAY_URL

    # -- verify --------------------------------------------------------------------------------------------------------------
    def _sale_params(self, credentials, order_id, sale_reference):
        return {**self._auth(credentials), "orderId": str(order_id), "saleOrderId": str(order_id), "saleReferenceId": str(sale_reference)}

    def verify_payment(
        self, *, track_id: str, expected_amount: Decimal, currency: str, credentials: dict[str, str],
        callback_data: dict[str, Any], sandbox: bool = False,
    ) -> PaymentVerificationResult:
        data = callback_data or {}
        res_code = str(data.get("ResCode") or "").strip()
        if res_code and res_code != RES_OK:
            return PaymentVerificationResult(success=False, status_code=int(res_code) if res_code.isdigit() else 0,
                                             message="پرداخت در درگاه موفق نبود.")
        sale_reference = str(data.get("SaleReferenceId") or "").strip()
        if not sale_reference:
            return PaymentVerificationResult(success=False, status_code=0, message="شماره‌ی مرجعِ فروش دریافت نشد.")
        if str(data.get("SaleOrderId") or "") != str(track_id):
            raise GatewayVerificationError("شناسه‌ی سفارشِ بازگشتی با این تلاش نمی‌خواند.", code="saleorder_mismatch")
        result = self._call("bpVerifyRequest", self._sale_params(credentials, track_id, sale_reference))
        if result not in (RES_OK, RES_VERIFIED_ALREADY):
            raise GatewayVerificationError("تأییدِ تراکنش توسطِ ملت ناموفق بود.", code=f"mellat_{result or 'empty'}")
        return PaymentVerificationResult(success=True, ref_id=sale_reference, card_number=str(data.get("CardHolderPan") or "")[:25],
                                         status_code=int(result), message="")

    # -- settle (DISTINCT capability) ----------------------------------------------------------------------------------------
    def settle_payment(self, *, track_id: str, amount: Decimal, currency: str, credentials: dict[str, str],
                       sandbox: bool = False) -> PaymentSettleResult:
        sale_reference = str(credentials.get("_saleReferenceId") or "").strip()
        if not sale_reference:
            return PaymentSettleResult(success=False, status_code=0, message="شماره‌ی مرجعِ فروش موجود نیست.")
        result = self._call("bpSettleRequest", self._sale_params(credentials, track_id, sale_reference))
        ok = result in (RES_OK, RES_SETTLED_ALREADY)
        return PaymentSettleResult(success=ok, settle_ref=sale_reference if ok else "", status_code=int(result) if result.isdigit() else 0,
                                   message="" if ok else "تسویه (settle) انجام نشد.")

    # -- inquiry / reversal ----------------------------------------------------------------------------------------------------
    def inquire_payment(self, *, track_id: str, expected_amount: Decimal, currency: str, credentials: dict[str, str],
                        sandbox: bool = False) -> PaymentInquiryResult:
        sale_reference = str(credentials.get("_saleReferenceId") or "").strip()
        if not sale_reference:
            return PaymentInquiryResult(paid=False, settled=False, status="no_reference", message="شماره‌ی مرجعِ فروش موجود نیست.")
        result = self._call("bpInquiryRequest", self._sale_params(credentials, track_id, sale_reference))
        # «paid» = بانک فروش را تأیید‌شده می‌داند؛ «settled» عمداً False: وضعیتِ settle از این پاسخ اثبات نمی‌شود ⇒ پل settle را (idempotent) دوباره می‌زند.
        return PaymentInquiryResult(
            paid=result in (RES_OK, RES_VERIFIED_ALREADY, RES_SETTLED_ALREADY), settled=False, ref_id=sale_reference,
            status=result, status_code=int(result) if result.isdigit() else 0, terminal_negative=result in _TERMINAL_NEGATIVE,
        )

    def cancel_payment(self, *, track_id: str, credentials: dict[str, str], sandbox: bool = False) -> PaymentCancelResult:
        sale_reference = str(credentials.get("_saleReferenceId") or "").strip()
        if not sale_reference:
            return PaymentCancelResult(success=False, status_code=0, message="شماره‌ی مرجعِ فروش موجود نیست.")
        result = self._call("bpReversalRequest", self._sale_params(credentials, track_id, sale_reference))
        return PaymentCancelResult(success=result == RES_OK, status_code=int(result) if result.isdigit() else 0)
