"""Gateway adapter registry — central dispatch for payment adapters.

New adapters are registered by adding them to _ADAPTERS below. No other
code in the system needs to know about specific adapter classes.

This module is the ONLY import point for adapter dispatch. Checkout views,
payment service, and admin code all go through ``get_adapter(code)`` —
they never import ZibalAdapter or CodAdapter directly.
"""

from __future__ import annotations

from .base import PaymentGatewayAdapter

# ---------------------------------------------------------------------------
# Lazy imports to avoid circular dependencies and keep the registry light
# ---------------------------------------------------------------------------


def _load_zibal():
    from .zibal import ZibalAdapter
    return ZibalAdapter()


def _load_cod():
    from .cod import CodAdapter
    return CodAdapter()


def _load_zarinpal():
    from .zarinpal import ZarinpalAdapter
    return ZarinpalAdapter()


def _load_card_to_card():
    from .card_to_card import CardToCardAdapter
    return CardToCardAdapter()


# --- M4+M5 online providers (PSPs + BNPL) -----------------------------------
# These adapters are documentation-blocked skeletons until each provider's
# official current contract is verified (see docs/payments/PROVIDER_RESEARCH_MATRIX.md).
# They register so the codes are known, but readiness derivation keeps them
# NOT selectable at real (non-sandbox) checkout.


def _load_pasargad():
    from .pasargad import PasargadAdapter
    return PasargadAdapter()


def _load_saman():
    from .saman import SamanAdapter
    return SamanAdapter()


def _load_parsian():
    from .parsian import ParsianAdapter
    return ParsianAdapter()


def _load_mellat():
    from .mellat import MellatAdapter
    return MellatAdapter()


def _load_sadad():
    from .sadad import SadadAdapter
    return SadadAdapter()


def _load_tejarat():
    from .tejarat import TejaratAdapter
    return TejaratAdapter()


def _load_snappay():
    from .snappay import SnappPayAdapter
    return SnappPayAdapter()


def _load_torobpay():
    from .torobpay import TorobPayAdapter
    return TorobPayAdapter()


# Registry: gateway_code → loader function
_ADAPTER_LOADERS: dict[str, callable] = {
    "zibal": _load_zibal,
    "cod": _load_cod,
    "zarinpal": _load_zarinpal,
    "card_to_card": _load_card_to_card,
    # M4 PSPs
    "pasargad": _load_pasargad,
    "saman": _load_saman,
    "parsian": _load_parsian,
    "mellat": _load_mellat,
    "sadad": _load_sadad,
    "tejarat": _load_tejarat,
    # M5 BNPL
    "snappay": _load_snappay,
    "torobpay": _load_torobpay,
}

# Cached adapter instances (stateless, safe to reuse)
_ADAPTER_CACHE: dict[str, PaymentGatewayAdapter] = {}

# Choices for Django model field
GATEWAY_CHOICES = [
    ("zibal", "زیبال"),
    ("cod", "پرداخت در محل"),
    ("zarinpal", "زرین‌پال"),
    ("card_to_card", "کارت به کارت"),
    # M4 PSPs
    ("pasargad", "بانک پاسارگاد"),
    ("saman", "بانک سامان (سپ)"),
    ("parsian", "بانک پارسیان"),
    ("mellat", "بانک ملت (به‌پرداخت)"),
    ("sadad", "بانک ملی (سداد)"),
    ("tejarat", "بانک تجارت"),
    # M5 BNPL
    ("snappay", "اسنپ‌پی"),
    ("torobpay", "تربپی"),
]


def get_adapter(gateway_code: str) -> PaymentGatewayAdapter:
    """Return the adapter instance for the given gateway code.

    Raises KeyError if the code is not registered.
    Adapter instances are cached (they are stateless).
    """
    if gateway_code not in _ADAPTER_LOADERS:
        raise KeyError(
            f"Unknown gateway code: {gateway_code!r}. "
            f"Registered codes: {list(_ADAPTER_LOADERS.keys())}"
        )

    if gateway_code not in _ADAPTER_CACHE:
        _ADAPTER_CACHE[gateway_code] = _ADAPTER_LOADERS[gateway_code]()

    return _ADAPTER_CACHE[gateway_code]


def registered_codes() -> list[str]:
    """Return all registered gateway codes."""
    return list(_ADAPTER_LOADERS.keys())


def is_online_gateway(gateway_code: str) -> bool:
    """Check if a gateway code represents an online payment method."""
    try:
        return get_adapter(gateway_code).is_online
    except KeyError:
        return False
