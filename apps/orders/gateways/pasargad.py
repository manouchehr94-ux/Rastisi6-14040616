"""Pasargad (پاسارگاد / PEP) PSP adapter — DOCUMENTATION_BLOCKED skeleton.

Bank Pasargad electronic payment (commonly "PEP" / Pasargad e-Payment, also
marketed via the "Dorsa" IPG). This adapter is a deliberately INCOMPLETE
skeleton: as of the FEAT-004 research pass (2026-11-03) no official, current
Pasargad IPG API contract was reachable from this environment. The only
available integration evidence is COMMUNITY code (e.g. the Dorsa-IPG community
library at https://github.com/pep-ipg/Dorsa-IPG-pasargad), which is explicitly
NON-authoritative and must not be used to assert an official contract.

Because the real contract (RSA signing scheme, token acquisition vs purchase
creation, inquiry, VERIFY vs CONFIRM, reverse, transaction deadlines, terminal
configuration, endpoint URLs, currency unit, error codes, sandbox) is NOT
verified, this adapter:

- registers so the gateway code is known to the system,
- declares its real category (PSP) and ``documentation_blocked = True`` so the
  readiness derivation surfaces DOCUMENTATION_BLOCKED and the provider is NEVER
  selectable at real (non-sandbox) checkout,
- declares NO capabilities (it implements neither create nor verify), and
- raises ``GatewayUnsupportedOperationError`` from every money-moving method
  instead of inventing endpoints, signatures, auth, or error codes.

Nothing here performs a network call. ``required_credentials`` lists the
credential FIELD NAMES that Pasargad merchants are widely known to hold
(merchant/terminal codes and an RSA private key). Listing a credential name is
not the same as asserting the request/signature contract, which remains
unverified.
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


class PasargadAdapter(PaymentGatewayAdapter):
    """Bank Pasargad PSP adapter (documentation-blocked skeleton)."""

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
        # Official current contract not verifiable from this environment.
        return True

    @property
    def required_credentials(self) -> list[str]:
        # Field names only — NOT an assertion of the (unverified) signing/request
        # contract. Merchant & terminal codes plus the RSA private key used by
        # Pasargad merchants.
        return ["merchant_code", "terminal_code", "private_key"]

    @property
    def capabilities(self) -> frozenset[PaymentOperation]:
        # No operation is documentation-verified, so none is declared. Any
        # attempt to create/verify/inquire/etc. raises the unsupported-operation
        # error via the ABC defaults.
        return frozenset()

    def validate_credentials(self, credentials: dict[str, str]) -> list[str]:
        """Validate presence of the known credential fields (no contract claims).

        Error messages never include credential values.
        """
        errors = []
        if not (credentials.get("merchant_code") or "").strip():
            errors.append("کد پذیرنده الزامی است")
        if not (credentials.get("terminal_code") or "").strip():
            errors.append("کد پایانه الزامی است")
        if not (credentials.get("private_key") or "").strip():
            errors.append("کلید خصوصی (RSA) الزامی است")
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
