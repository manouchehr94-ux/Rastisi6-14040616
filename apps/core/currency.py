"""The ONE place that says how RastiSi money maps to the ISO 4217 codes search engines and ad platforms require.

Storage and display: every price/amount in the database, the storefront UI, the cart and the checkout is in **Toman** (``IRT``,
a whole-number ``DecimalField(decimal_places=0)`` — see ``Product.price``, ``Order.currency = "IRT"``). ``IRT`` is a RastiSi
convention, NOT an ISO 4217 code. The ISO code of the Iranian currency is ``IRR`` (Rial) and 1 Toman = 10 Rial — the same factor the
payment gateways already apply (``apps.orders.gateways.zibal.TOMAN_TO_RIAL``).

So anything leaving the platform for Google / Meta / schema.org must be converted here (``priceCurrency: IRR``, amount × 10). Nothing
stored is ever changed."""

from decimal import Decimal

STORAGE_CURRENCY = "IRT"       # platform convention: Toman
ISO_CURRENCY = "IRR"           # ISO 4217: Rial
TOMAN_TO_RIAL = 10


def toman_to_rial(amount) -> int:
    """Whole Rials for an amount stored in Toman (exact: Toman amounts are integers, so no rounding is involved)."""
    return int(Decimal(amount) * TOMAN_TO_RIAL)
