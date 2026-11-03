"""TorobPay (تربپی) BNPL adapter — DOCUMENTATION_BLOCKED skeleton.

TorobPay is a BUY-NOW-PAY-LATER (BNPL) provider tied to the Torob
price-comparison platform, NOT an ordinary PSP. A complete BNPL integration has
a distinct lifecycle — eligibility, payment token/create, redirect, verify,
SETTLE, status inquiry, revert/cancel, order-update — where SETTLE is NOT the
same as VERIFY or REFUND, and itemized cart/discount/shipping data is passed on
create.

The only readily available integration evidence is a WordPress plugin
(https://wordpress.org/plugins/torobpay-for-woocommerce/), which is a COMMUNITY,
NON-authoritative source. During the FEAT-004 research pass (2026-11-03) no
official current TorobPay API documentation (endpoints, auth, currency unit,
error codes, eligibility/settlement rules, sandbox) was reachable. Per mission
rules we reverse-engineer NOTHING into a fabricated contract and add NO WordPress
dependency.

Because the documented BNPL contract is NOT verified, this adapter registers,
declares its real category (BNPL) and ``documentation_blocked = True`` so the
readiness derivation surfaces DOCUMENTATION_BLOCKED and it is NEVER selectable at
real (non-sandbox) checkout. It declares NO capabilities, raises
``GatewayUnsupportedOperationError`` from every money-moving method, and never
computes installment offers from guessed rates. SETTLE / CANCEL / eligibility
must each be implemented as DISTINCT capability-gated operations once the
official contract is verified.
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


class TorobPayAdapter(PaymentGatewayAdapter):
    """TorobPay BNPL adapter (documentation-blocked skeleton)."""

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
        return True

    @property
    def required_credentials(self) -> list[str]:
        # TorobPay merchants authenticate with an OAuth client id/secret. Field
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
            "قرارداد اعتبارسنجی اقساطی تربپی هنوز از مستندات رسمی تأیید نشده است.",
            code="bnpl_eligibility",
            details={"gateway": self.code, "documentation_blocked": True},
        )
