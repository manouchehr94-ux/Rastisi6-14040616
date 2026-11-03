"""Saman / SEP (سامان / سپ) PSP adapter — DOCUMENTATION_BLOCKED skeleton.

Saman Electronic Payment ("سپ", Saman Electronic Payment). The SEP landing page
(https://www.sep.ir/) was reachable during the FEAT-004 research pass
(2026-11-03) but it is a MARKETING page: it describes the SEP internet payment
gateway product in prose and exposes NO technical contract — no token-request /
redirect / verification endpoint URLs, request/response schemas, currency unit,
error codes, or sandbox details. Legacy integration examples found elsewhere
cannot be assumed to match current terminals.

Because the real contract (token + redirect + verification, terminal config,
currency unit, error codes, sandbox) is NOT verified from an official current
source, this adapter registers, declares its real category (PSP) and
``documentation_blocked = True`` so the readiness derivation surfaces
DOCUMENTATION_BLOCKED and it is NEVER selectable at real (non-sandbox) checkout.
It declares NO capabilities and raises ``GatewayUnsupportedOperationError`` from
every money-moving method rather than invent an endpoint or signature.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from .base import (
    GatewayCategory,
    PaymentCreationResult,
    PaymentGatewayAdapter,
    PaymentOperation,
    PaymentVerificationResult,
)


class SamanAdapter(PaymentGatewayAdapter):
    """Saman / SEP PSP adapter (documentation-blocked skeleton)."""

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
        # Field name only — SEP merchants hold a terminal id ("TerminalId" /
        # merchant id). Listing it asserts nothing about the unverified contract.
        return ["terminal_id"]

    @property
    def capabilities(self) -> frozenset[PaymentOperation]:
        return frozenset()

    def validate_credentials(self, credentials: dict[str, str]) -> list[str]:
        errors = []
        if not (credentials.get("terminal_id") or "").strip():
            errors.append("شناسه‌ی پایانه (Terminal Id) الزامی است")
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
