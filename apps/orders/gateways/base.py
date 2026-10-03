"""Abstract gateway adapter contract.

Every payment gateway adapter must implement this interface. The contract is
deliberately minimal and focused on the payment lifecycle:

1. validate_credentials — can this config initiate payments?
2. create_payment      — server-to-server request to create a payment session
3. build_redirect_url  — where to send the customer's browser
4. verify_payment      — server-to-server verification after callback

Adapters must:
- Never log credentials or sensitive customer data
- Always use explicit timeouts for external HTTP calls
- Return structured results (dataclasses below), never raw dicts/responses
- Raise GatewayError subclasses for all failure modes
- Never modify Order/PaymentAttempt state directly (caller's responsibility)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PaymentCreationResult:
    """Result of a successful create_payment call."""

    track_id: str  # Gateway's tracking/session identifier
    gateway_url: str | None = None  # If gateway returns redirect URL directly
    extra: dict | None = None  # Any additional gateway-specific data


@dataclass(frozen=True)
class PaymentVerificationResult:
    """Result of a successful verify_payment call."""

    success: bool
    ref_id: str = ""  # Bank reference number (for successful payments)
    card_number: str = ""  # Masked card number (if provided by gateway)
    status_code: int = 0  # Gateway-specific status code
    message: str = ""  # Human-readable status message


# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


class GatewayError(Exception):
    """Base exception for all gateway adapter errors.

    IMPORTANT: Never include credentials, full card numbers, or customer PII
    in error messages. These exceptions may be logged and their messages may
    appear in admin UI (though never in customer-facing pages).
    """

    def __init__(self, message: str, code: str = "", details: dict | None = None):
        super().__init__(message)
        self.code = code  # Machine-readable error code
        self.details = details or {}  # Safe-to-log additional context


class GatewayConnectionError(GatewayError):
    """Network-level failure (timeout, DNS, connection refused)."""


class GatewayResponseError(GatewayError):
    """Gateway returned an unexpected or malformed response."""


class GatewayPaymentError(GatewayError):
    """Gateway explicitly rejected the payment request."""


class GatewayVerificationError(GatewayError):
    """Verification failed — payment should NOT be marked successful."""


class GatewayAmountMismatchError(GatewayVerificationError):
    """The gateway CONFIRMED a payment, but for a different amount than the order expects.

    Money has moved (the gateway said so), so this is not an ordinary verification failure: the
    caller must preserve ``details["evidence"]`` (reported/expected Rial, ref id, masked card) in a
    ``PaymentReconciliation`` and must NOT mark the order paid."""


class GatewayCredentialError(GatewayError):
    """Credentials are invalid, expired, or missing."""


# ---------------------------------------------------------------------------
# Abstract adapter
# ---------------------------------------------------------------------------


class PaymentGatewayAdapter(ABC):
    """Abstract base class for payment gateway adapters.

    Each adapter instance is stateless and can be reused across requests.
    Configuration (merchant ID, etc.) is passed per-call from the
    PaymentGatewayConfig model, never stored on the adapter instance.
    """

    @property
    @abstractmethod
    def code(self) -> str:
        """Unique gateway code matching GATEWAY_CHOICES and PaymentGatewayConfig.gateway_code."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Persian display name for admin/checkout UI."""

    @property
    @abstractmethod
    def is_online(self) -> bool:
        """True for online payment gateways, False for offline (COD)."""

    @property
    def required_credentials(self) -> list[str]:
        """List of credential field names required for this gateway.

        Used by admin UI to validate configuration completeness.
        Default: empty (no credentials needed, e.g., COD).
        """
        return []

    @abstractmethod
    def validate_credentials(self, credentials: dict[str, str]) -> list[str]:
        """Validate that credentials are sufficient for this gateway.

        Args:
            credentials: Decrypted credential dict from PaymentGatewayConfig.

        Returns:
            List of validation error messages (empty = valid).
            Never includes the actual credential values in error messages.
        """

    @abstractmethod
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
        """Create a payment session with the gateway.

        Args:
            amount: Payment amount in the currency unit stored in the database.
            currency: Currency code (e.g., "TOMAN").
            callback_url: Full URL the gateway should redirect to after payment.
            credentials: Decrypted credential dict.
            order_code: Order identifier for the gateway's records.
            description: Optional payment description.
            sandbox: Whether to use sandbox/test mode.

        Returns:
            PaymentCreationResult with track_id and optional redirect URL.

        Raises:
            GatewayConnectionError: Network failure.
            GatewayResponseError: Malformed/unexpected response.
            GatewayPaymentError: Gateway rejected the request.
            GatewayCredentialError: Invalid credentials.
        """

    @abstractmethod
    def build_redirect_url(
        self,
        track_id: str,
        *,
        sandbox: bool = False,
    ) -> str:
        """Build the URL to redirect the customer's browser to.

        Args:
            track_id: The tracking identifier from create_payment result.
            sandbox: Whether to use sandbox/test mode URL.

        Returns:
            Full URL string for browser redirect.
        """

    @abstractmethod
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
        """Verify a payment after callback.

        This is the authoritative server-to-server verification. A browser
        callback parameter alone NEVER proves payment success.

        Args:
            track_id: The tracking identifier from the payment attempt.
            expected_amount: The amount we expect (from our database, not browser).
            currency: Currency code.
            credentials: Decrypted credential dict.
            callback_data: Data received in the callback (query params, etc.).
            sandbox: Whether sandbox mode.

        Returns:
            PaymentVerificationResult indicating success/failure.

        Raises:
            GatewayConnectionError: Network failure during verification.
            GatewayResponseError: Malformed verification response.
            GatewayVerificationError: Verification explicitly failed.
        """
