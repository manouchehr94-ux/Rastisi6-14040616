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


def _load_card_to_card():
    from .card_to_card import CardToCardAdapter
    return CardToCardAdapter()


# Registry: gateway_code → loader function
_ADAPTER_LOADERS: dict[str, callable] = {
    "zibal": _load_zibal,
    "cod": _load_cod,
    "card_to_card": _load_card_to_card,
}

# Cached adapter instances (stateless, safe to reuse)
_ADAPTER_CACHE: dict[str, PaymentGatewayAdapter] = {}

# Choices for Django model field
GATEWAY_CHOICES = [
    ("zibal", "زیبال"),
    ("cod", "پرداخت در محل"),
    ("card_to_card", "کارت‌به‌کارت"),
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
