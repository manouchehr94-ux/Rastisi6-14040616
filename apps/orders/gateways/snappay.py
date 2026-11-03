"""SnappPay (اسنپ‌پی) BNPL adapter — DOCUMENTATION_BLOCKED skeleton.

SnappPay is a BUY-NOW-PAY-LATER (BNPL) provider in the Snapp! ecosystem, NOT an
ordinary PSP. A complete BNPL integration has a distinct lifecycle —
eligibility, payment token/create, redirect, verify, SETTLE, status inquiry,
revert/cancel, order-update — where SETTLE is NOT the same as VERIFY or REFUND,
and where itemized cart/discount/shipping data is passed on create.

The official current API documentation (entry point
https://academy.snapppay.ir/self-cms/) was reachable only as an empty/listing
shell during the FEAT-004 research pass (2026-11-03); it exposes NO endpoint
URLs, OAuth/token auth scheme, eligibility API, installment terms, currency
unit, error codes, or sandbox. The documented BNPL contract is therefore NOT
verified.

Because of that, this adapter registers, declares its real category (BNPL) and
``documentation_blocked = True`` so the readiness derivation surfaces
DOCUMENTATION_BLOCKED and it is NEVER selectable at real (non-sandbox) checkout.
It declares NO capabilities, raises ``GatewayUnsupportedOperationError`` from
every money-moving method, and CRUCIALLY never computes installment offers from
guessed rates — installment/eligibility data must come from the provider once
its contract is verified. SETTLE / CANCEL / eligibility must each be implemented
as DISTINCT capability-gated operations at that point.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from .base import (
    GatewayCategory,
    GatewayUnsupportedOperationError,
    PaymentCreationResult,
    PaymentGatewayAdapter,
    PaymentOperation,
    PaymentVerificationResult,
)


class SnappPayAdapter(PaymentGatewayAdapter):
    """SnappPay BNPL adapter (documentation-blocked skeleton)."""

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
        return True

    @property
    def required_credentials(self) -> list[str]:
        # SnappPay merchants authenticate with an OAuth client id/secret. Field
        # names only; asserts nothing about the unverified token/eligibility API.
        return ["client_id", "client_secret"]

    @property
    def capabilities(self) -> frozenset[PaymentOperation]:
        return frozenset()

    def validate_credentials(self, credentials: dict[str, str]) -> list[str]:
        errors = []
        if not (credentials.get("client_id") or "").strip():
            errors.append("شناسه‌ی کلاینت (client_id) الزامی است")
        if not (credentials.get("client_secret") or "").strip():
            errors.append("رمز کلاینت (client_secret) الزامی است")
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
        raise self._unsupported(PaymentOperation.CREATE)

    def build_redirect_url(self, track_id: str, *, sandbox: bool = False) -> str:
        raise self._unsupported(PaymentOperation.CREATE)

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
        raise self._unsupported(PaymentOperation.VERIFY)

    def check_bnpl_eligibility(
        self,
        *,
        amount: Decimal,
        currency: str,
        credentials: dict[str, str],
        customer: dict[str, Any] | None = None,
        sandbox: bool = False,
    ) -> dict[str, Any]:
        # Eligibility/installment data must come from the provider. With no
        # verified contract, never fabricate installment offers.
        raise GatewayUnsupportedOperationError(
            "قرارداد اعتبارسنجی اقساطی اسنپ‌پی هنوز از مستندات رسمی تأیید نشده است.",
            code="bnpl_eligibility",
            details={"gateway": self.code, "documentation_blocked": True},
        )
