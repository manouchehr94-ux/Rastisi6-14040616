"""P5-W2 — the SINGLE canonical data authority for the reversible occasion Theme layer.

This is a bounded, immutable *data catalog* — deliberately NOT a second component
registry, NOT a second manifest, NOT a renderer, NOT a persistence layer. It owns
exactly one thing: the finite set of occasion identities and their bounded,
platform-owned presentation metadata (occasion key, component key, Persian label,
semantic tone, accent tokens, motif tokens).

Consumers:
* ``storefront_appearance.adapters`` reads this catalog to emit Theme
  ``ComponentDefinition``s (``theme_overlay:<occasion-key>``) into the central
  ``COMPONENT_REGISTRY`` — the adapter holds NO occasion data of its own.
* ``storefront_appearance.rendering.theme_overlay_state`` reads this catalog to
  resolve one active occasion into platform-owned CSS variables consumed by the
  storefront shell and page sections.

Architecture rule honored: ONE CONCEPT = ONE CANONICAL OWNER. Theme occasion
metadata lives here and only here.

Tone semantics (mandatory): every occasion carries a bounded semantic ``tone``
in {"festive", "neutral", "mourning"}. A ``mourning`` occasion
(Muharram/Ashura) must never enable celebratory motifs, countdown/sale pressure,
or celebratory sale badges — enforced structurally by this catalog: mourning
entries carry ``festive_motifs=False``, ``countdown_pressure=False``,
``sale_badge=False`` and this module refuses to construct any mourning entry
that violates that rule.
"""

from __future__ import annotations

import dataclasses
import re
from types import MappingProxyType


class InvalidThemeCatalogEntry(ValueError):
    """A Theme catalog entry violates its bounded platform-owned contract."""


_OCCASION_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_ALLOWED_TONES = frozenset({"festive", "neutral", "mourning"})

#: The bounded intensity vocabulary. Kept here alongside the catalog so the
#: single source of truth for the enum is the theme concept's own owner; the
#: manifest validator imports this rather than re-declaring the strings.
THEME_INTENSITY_CHOICES = ("subtle", "balanced", "strong")
DEFAULT_THEME_INTENSITY = "balanced"

#: Per-intensity multiplier applied to platform-owned motif opacity. Bounded,
#: not merchant-editable. subtle < balanced < strong.
_INTENSITY_MOTIF_OPACITY = {
    "subtle": "0.06",
    "balanced": "0.12",
    "strong": "0.20",
}
_INTENSITY_ACCENT_SOFT_MIX = {
    "subtle": "0.08",
    "balanced": "0.16",
    "strong": "0.28",
}


@dataclasses.dataclass(frozen=True)
class ThemeOccasion:
    """One bounded occasion definition. Immutable, platform-owned."""

    occasion_key: str
    label_fa: str
    tone: str
    accent: str
    accent_soft: str
    #: A short symbolic motif token (a CSS-class-safe identifier the shell CSS
    #: maps to a decorative treatment). Never raw CSS.
    motif: str
    festive_motifs: bool
    countdown_pressure: bool
    sale_badge: bool

    def __post_init__(self) -> None:
        if not isinstance(self.occasion_key, str) or not _OCCASION_KEY_RE.fullmatch(
            self.occasion_key
        ):
            raise InvalidThemeCatalogEntry(f"unsafe occasion key: {self.occasion_key!r}")
        if not isinstance(self.label_fa, str) or not self.label_fa.strip():
            raise InvalidThemeCatalogEntry("occasion label_fa must be a non-empty string")
        if self.tone not in _ALLOWED_TONES:
            raise InvalidThemeCatalogEntry(f"unknown tone: {self.tone!r}")
        if not _HEX_RE.fullmatch(self.accent):
            raise InvalidThemeCatalogEntry(f"accent must be a hex color: {self.accent!r}")
        if not _HEX_RE.fullmatch(self.accent_soft):
            raise InvalidThemeCatalogEntry(
                f"accent_soft must be a hex color: {self.accent_soft!r}"
            )
        if not isinstance(self.motif, str) or not re.fullmatch(
            r"^[a-z][a-z0-9_]*$", self.motif
        ):
            raise InvalidThemeCatalogEntry(f"unsafe motif token: {self.motif!r}")
        for flag_name in ("festive_motifs", "countdown_pressure", "sale_badge"):
            if not isinstance(getattr(self, flag_name), bool):
                raise InvalidThemeCatalogEntry(f"{flag_name} must be a boolean")
        # Structural tone-safety guarantee: a mourning occasion can never carry
        # any celebratory/pressure affordance.
        if self.tone == "mourning" and (
            self.festive_motifs or self.countdown_pressure or self.sale_badge
        ):
            raise InvalidThemeCatalogEntry(
                "a mourning occasion must not enable celebratory motifs, "
                "countdown pressure, or sale badges"
            )

    @property
    def component_key(self) -> str:
        return f"theme.{self.occasion_key}.v1"

    @property
    def registry_reference(self) -> str:
        return f"theme_overlay:{self.occasion_key}"

    @property
    def is_noop(self) -> bool:
        return self.occasion_key == "none"


def _festive(occasion_key, label_fa, accent, accent_soft, motif):
    return ThemeOccasion(
        occasion_key=occasion_key,
        label_fa=label_fa,
        tone="festive",
        accent=accent,
        accent_soft=accent_soft,
        motif=motif,
        festive_motifs=True,
        countdown_pressure=False,
        sale_badge=False,
    )


def _observance(occasion_key, label_fa, accent, accent_soft, motif):
    """A restrained religious observance (Ramadan / Eid): neutral tone, no
    festive particle motifs and no sale pressure by default — respectful."""
    return ThemeOccasion(
        occasion_key=occasion_key,
        label_fa=label_fa,
        tone="neutral",
        accent=accent,
        accent_soft=accent_soft,
        motif=motif,
        festive_motifs=False,
        countdown_pressure=False,
        sale_badge=False,
    )


def _mourning(occasion_key, label_fa, accent, accent_soft, motif):
    return ThemeOccasion(
        occasion_key=occasion_key,
        label_fa=label_fa,
        tone="mourning",
        accent=accent,
        accent_soft=accent_soft,
        motif=motif,
        festive_motifs=False,
        countdown_pressure=False,
        sale_badge=False,
    )


# The bounded initial occasion catalog. New Iranian/Islamic occasions are added
# HERE (and only here), automatically flowing into the registry via the adapter.
_THEME_OCCASIONS = (
    ThemeOccasion(
        occasion_key="none",
        label_fa="بدون تم مناسبتی",
        tone="neutral",
        accent="#000000",
        accent_soft="#000000",
        motif="none",
        festive_motifs=False,
        countdown_pressure=False,
        sale_badge=False,
    ),
    _festive("nowruz", "نوروز", "#1FA67A", "#D8F3E9", "spring_blossom"),
    _festive("yalda", "یلدا", "#B31E4B", "#F6D9E2", "pomegranate_night"),
    _festive("valentine", "ولنتاین", "#E23A6E", "#FBDDE7", "hearts"),
    _observance("ramadan", "رمضان", "#2C6E7F", "#D6E8EC", "crescent_lantern"),
    _observance("eid_fitr", "عید فطر", "#3C8C6A", "#DCEEE4", "crescent_star"),
    _observance("eid_qorban", "عید قربان", "#8A6A2F", "#EFE6D2", "geometric_gold"),
    _mourning("muharram", "محرم و عاشورا", "#2B2F36", "#DEE1E5", "muted_banner"),
)

_BY_OCCASION_KEY = MappingProxyType(
    {entry.occasion_key: entry for entry in _THEME_OCCASIONS}
)
_BY_COMPONENT_KEY = MappingProxyType(
    {entry.component_key: entry for entry in _THEME_OCCASIONS}
)

# Fail-fast integrity: unique keys.
if len(_BY_OCCASION_KEY) != len(_THEME_OCCASIONS):
    raise InvalidThemeCatalogEntry("duplicate occasion key in theme catalog")
if "none" not in _BY_OCCASION_KEY:
    raise InvalidThemeCatalogEntry("theme catalog must define the safe 'none' occasion")


def list_theme_occasions() -> tuple[ThemeOccasion, ...]:
    """Deterministic ordered tuple of every occasion (including ``none``)."""
    return _THEME_OCCASIONS


def get_theme_occasion(occasion_key: str) -> ThemeOccasion:
    entry = _BY_OCCASION_KEY.get(occasion_key)
    if entry is None:
        raise InvalidThemeCatalogEntry(f"unknown occasion key: {occasion_key!r}")
    return entry


def get_theme_occasion_by_component_key(component_key: str) -> ThemeOccasion:
    entry = _BY_COMPONENT_KEY.get(component_key)
    if entry is None:
        raise InvalidThemeCatalogEntry(f"unknown theme component key: {component_key!r}")
    return entry


def has_occasion(occasion_key: str) -> bool:
    return occasion_key in _BY_OCCASION_KEY


def is_valid_intensity(intensity: str) -> bool:
    return intensity in THEME_INTENSITY_CHOICES


def motif_opacity_for(intensity: str) -> str:
    return _INTENSITY_MOTIF_OPACITY.get(intensity, _INTENSITY_MOTIF_OPACITY[DEFAULT_THEME_INTENSITY])


def accent_soft_mix_for(intensity: str) -> str:
    return _INTENSITY_ACCENT_SOFT_MIX.get(
        intensity, _INTENSITY_ACCENT_SOFT_MIX[DEFAULT_THEME_INTENSITY]
    )
