"""Global Region/Variant Registry — U2A: Visual Global Header System,
extended in U2B to also cover the Footer global region.

``SECTION_REGISTRY`` (``section_registry.py``) resolves *page-section*
types (hero_banner, product_section, ...). It is deliberately NOT reused
for global chrome regions like Header/Navigation/Mobile shell — those are
not sections a merchant adds/removes/reorders on a page; they are exactly
one fixed region shared by all six page types, so forcing them into
``SectionDefinition`` (page_types/min_instances/duplicable/category_fa/
library visibility/... all meaningless here) would be a worse fit than a
small, dedicated registry.

This module reuses the exact U1 principle instead — the same one
``variant_contract.VariantDefinition`` already proved for section variants:

    persisted variant key (string, merchant-controlled)
            v
    trusted Python registry (this module)
            v
    trusted registered renderer path (Python code only, never merchant JSON)
            v
    shared storefront shell (``{% include header_variant_template %}``)

It is intentionally much smaller than ``SectionDefinition``/
``VariantDefinition``: a global variant has no ``validate_settings``/
``default_settings``/``capabilities``/``supported_settings``/
``required_data`` of its own (the *shape* of ``header_config`` is one
single schema, validated once by
``services.layout_service.validate_header_config`` — a variant only ever
selects which trusted renderer partial receives that same
``header_config`` dict), and there is no Pattern-A "same template as the
region" fallback (a region has no template_name of its own — the region
IS "a set of registered variants", and every variant, including the
backward-compatible default, always declares its own ``renderer``).

Read vs. write, exactly mirroring ``variant_contract``'s split:

- ``resolve_active_global_variant``/``resolve_header_variant_template``
  are the *read* (render-time) path — pure, zero-DB-query, never raise;
  an unknown/legacy/missing stored key fails safely to the region's
  ``default_variant``, never crashes the storefront, never falls back to
  an arbitrary/merchant-controlled path.
- ``validate_global_variant_selection`` is the *write* (editor POST) path
  — rejects a present-and-unknown key outright, exactly like
  ``variant_contract.validate_variant_selection``/
  ``UnknownVariantSelectionError`` does for section variants.

No branching on template-key identity, Store slug identity, or family-slug
identity exists or may be added anywhere that consumes this module — the
renderer is always the one fixed Python string already written on the
matching ``GlobalVariantDefinition``.
"""

from __future__ import annotations

import dataclasses
import re


class InvalidGlobalVariantDefinitionError(ValueError):
    """A ``GlobalVariantDefinition``/``GlobalRegionDefinition`` built in this
    module's own Python code (never merchant input) is malformed — raised at
    import time only, exactly like
    ``variant_contract.InvalidVariantDefinitionError``."""


@dataclasses.dataclass(frozen=True)
class GlobalVariantDefinition:
    """One registered, trusted rendering variant for a ``GlobalRegionDefinition``.

    ``key`` is the stable string persisted in merchant JSON config (e.g.
    ``header_config["header_variant"] = "marketplace_search_first"``) —
    never a template path. ``renderer`` is always a fixed Python string
    written in this module, validated against
    ``GLOBAL_RENDERER_NAMESPACE`` at import time (see
    ``_validate_global_variant_renderer`` below) — the same trusted-path
    invariant ``variant_contract`` already enforces for section variants,
    applied to a different (non-section) template namespace."""

    key: str
    label_fa: str
    renderer: str


@dataclasses.dataclass(frozen=True)
class GlobalRegionDefinition:
    """One fixed global chrome region (``"header"`` in U2A; a future phase
    may add ``"footer"``/``"mobile_shell"``) and its registered variants.

    Unlike ``SectionDefinition.variants`` (optional, defaults to ``()``), a
    ``GlobalRegionDefinition`` always has at least one variant — the
    backward-compatible default — and ``default_variant`` is always a real,
    resolvable key (never ``None``): a global region is not an optional
    per-instance feature a section may or may not have, it is the one
    thing every published Store already renders today, so "no variant
    registered yet" is not a valid state for it."""

    key: str
    label_fa: str
    variants: tuple[GlobalVariantDefinition, ...]
    default_variant: str
    #: Which key of the region's *existing* persisted config dict selects
    #: the active variant — exactly the same reason
    #: ``SectionDefinition.variant_setting_key`` exists: the header's own
    #: config already has many keys (``show_search``, ``sticky``, ...);
    #: this says which one is the variant selector, without renaming any
    #: of them.
    variant_setting_key: str


#: Namespace constraint for every ``GlobalVariantDefinition.renderer`` —
#: deliberately a *different* namespace from
#: ``variant_contract.SECTION_VARIANT_RENDERER_NAMESPACE`` (global regions
#: are not sections). Broad enough to include the pre-existing, unchanged
#: ``page_shell_header.html``/``page_shell_footer.html`` (registered below
#: as each region's ``legacy_default`` renderer, at their current, un-moved
#: paths) as well as the new ``global_header/``/``global_footer/`` variant
#: partials.
GLOBAL_RENDERER_NAMESPACE = "storefront_builder/partials/"

_WINDOWS_DRIVE_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")


def _validate_global_variant_renderer(renderer: str) -> None:
    """Same shape of check as ``variant_contract._validate_variant_renderer``
    — renderer safety here is a defense-in-depth layer, not the primary
    guarantee (the primary guarantee is that ``renderer`` is always a fixed
    Python string in this file, never read from merchant JSON/settings).
    Unlike the section-variant version, ``None`` is never valid here —
    every global variant, including the default, must declare its own
    renderer (see ``GlobalRegionDefinition`` docstring)."""
    if not isinstance(renderer, str) or not renderer.strip():
        raise InvalidGlobalVariantDefinitionError("renderer باید یک رشته‌ی غیرخالی باشد")
    if renderer != renderer.strip():
        raise InvalidGlobalVariantDefinitionError(f"renderer «{renderer}» نباید فاصله‌ی ابتدا/انتهایی داشته باشد")
    if "\\" in renderer:
        raise InvalidGlobalVariantDefinitionError(f"renderer «{renderer}» نباید شامل بک‌اسلش باشد")
    if renderer.startswith("/"):
        raise InvalidGlobalVariantDefinitionError(f"renderer «{renderer}» نباید مسیرِ مطلق باشد")
    if _WINDOWS_DRIVE_PATH_RE.match(renderer):
        raise InvalidGlobalVariantDefinitionError(f"renderer «{renderer}» نباید مسیرِ درایوِ ویندوزی باشد")
    if ".." in renderer:
        raise InvalidGlobalVariantDefinitionError(f"renderer «{renderer}» نباید شامل .. باشد")
    if not renderer.startswith(GLOBAL_RENDERER_NAMESPACE):
        raise InvalidGlobalVariantDefinitionError(
            f"renderer «{renderer}» باید در فضای نامِ «{GLOBAL_RENDERER_NAMESPACE}» باشد"
        )


def _validate_global_region(region: GlobalRegionDefinition) -> None:
    """Import-time validation for one ``GlobalRegionDefinition`` — never
    called for merchant input, only for the Python-code registry entries
    below (see ``_GLOBAL_REGIONS`` construction)."""
    if not isinstance(region.key, str) or not region.key.strip():
        raise InvalidGlobalVariantDefinitionError("کلیدِ Global Region نمی‌تواند خالی باشد")
    if not region.variants:
        raise InvalidGlobalVariantDefinitionError(f"Global Region «{region.key}» باید حداقل یک Variant داشته باشد")
    seen: set[str] = set()
    for variant in region.variants:
        if not isinstance(variant.key, str) or not variant.key.strip():
            raise InvalidGlobalVariantDefinitionError(f"کلیدِ Variantِ «{region.key}» نمی‌تواند خالی باشد")
        if not isinstance(variant.label_fa, str) or not variant.label_fa.strip():
            raise InvalidGlobalVariantDefinitionError(f"برچسبِ Variantِ «{variant.key}» نمی‌تواند خالی باشد")
        _validate_global_variant_renderer(variant.renderer)
        if variant.key in seen:
            raise InvalidGlobalVariantDefinitionError(f"کلیدِ Variantِ «{variant.key}» در «{region.key}» تکراری است")
        seen.add(variant.key)
    if region.default_variant not in seen:
        raise InvalidGlobalVariantDefinitionError(
            f"default_variant «{region.default_variant}» در «{region.key}» به هیچ Variantِ ثبت‌شده‌ای اشاره نمی‌کند"
        )


# ----------------------------------------------------------------- registry

#: U2A — backward-compatible default: the exact, unmoved, unmodified
#: partial every published-V2 Store renders today. Registering it as a
#: normal (not a special-cased) variant is what "Existing stores must not
#: visually change simply because U2A is merged" reduces to: a Store with
#: no ``header_variant`` in its persisted ``header_config`` resolves this
#: exact key via ``GlobalRegionDefinition.default_variant`` below —
#: same file, same DOM, same CSS classes as before U2A.
_LEGACY_DEFAULT_VARIANT = GlobalVariantDefinition(
    key="legacy_default",
    label_fa="فعلی / پیش‌فرض",
    renderer="storefront_builder/partials/page_shell_header.html",
)

_MARKETPLACE_SEARCH_FIRST_VARIANT = GlobalVariantDefinition(
    key="marketplace_search_first",
    label_fa="بازارگاهی (جستجو-محور)",
    renderer="storefront_builder/partials/global_header/marketplace_search_first.html",
)

_PREMIUM_THREE_COLUMN_VARIANT = GlobalVariantDefinition(
    key="premium_three_column",
    label_fa="پرمیوم سه‌ستونه",
    renderer="storefront_builder/partials/global_header/premium_three_column.html",
)

_BOUTIQUE_CENTERED_VARIANT = GlobalVariantDefinition(
    key="boutique_centered",
    label_fa="بوتیک (لوگوی مرکزی)",
    renderer="storefront_builder/partials/global_header/boutique_centered.html",
)

_DARK_TECH_VARIANT = GlobalVariantDefinition(
    key="dark_tech",
    label_fa="دیجیتال تیره",
    renderer="storefront_builder/partials/global_header/dark_tech.html",
)

#: Site-target-overhaul (ibolak reference) — a dominant campaign topbar
#: over a search-centered main row, with a second row combining real
#: social/contact chips (left) and category/nav links (right) in one
#: line. Distinct from ``marketplace_search_first`` (whose second row is
#: a single nav strip, no chip cluster) so that template stays untouched
#: while a fashion/campaign-style Ready Template can adopt this one.
_PROMO_SEARCH_NAV_VARIANT = GlobalVariantDefinition(
    key="promo_search_nav",
    label_fa="کمپینی (نوار پیشنهاد + جستجو)",
    renderer="storefront_builder/partials/global_header/promo_search_nav.html",
)

#: Beauty retail archetype (laleRokh reference family) — keeps the proven
#: search-centered three-zone topology from the campaign header, but removes
#: campaign-specific chrome and gives account/navigation their own quiet
#: utility row.  It is a generic registered option usable by any Store.
_BEAUTY_SEARCH_NAV_VARIANT = GlobalVariantDefinition(
    key="beauty_search_nav",
    label_fa="زیبایی (جستجو + ناوبری فروشگاهی)",
    renderer="storefront_builder/partials/global_header/beauty_search_nav.html",
)

#: Specialty/home-retail archetype (shokolati reference family): brown
#: primary row with prominent search at visual right, centered merchant brand,
#: shopper actions at visual left, then a separate white category/navigation
#: row.  It reuses shared controls and contains no Ready Template condition.
_CHOCOLATE_CENTERED_SEARCH_VARIANT = GlobalVariantDefinition(
    key="chocolate_centered_search",
    label_fa="شکلاتی (جستجو + لوگوی مرکزی)",
    renderer="storefront_builder/partials/global_header/chocolate_centered_search.html",
)

#: Editorial/atelier commerce header — one quiet row with merchant brand at
#: the RTL edge, real Store navigation in the center and compact shopper
#: utilities at the opposite edge. Search expands into a slim panel instead
#: of permanently occupying the header. Generic and reusable by any Store.
_ATELIER_NAV_VARIANT = GlobalVariantDefinition(
    key="atelier_nav",
    label_fa="آتلیه (ناوبری مینیمال)",
    renderer="storefront_builder/partials/global_header/atelier_nav.html",
)

#: Premium search-led commerce header.  Dark/gold is supplied by the active
#: palette; this variant only owns structure, so any future template may reuse
#: it without a template-key branch.
_LUXURY_SEARCH_VARIANT = GlobalVariantDefinition(
    key="luxury_search",
    label_fa="لوکس (جستجوی برجسته)",
    renderer="storefront_builder/partials/global_header/luxury_search.html",
)

#: Stationery / art-supply retail header: utility strip, wide pill search,
#: prominent account pill and a flat category + link navigation bar.
_STATIONERY_SEARCH_VARIANT = GlobalVariantDefinition(
    key="stationery_search",
    label_fa="لوازم تحریر (جستجوی عریض + نوار ناوبری)",
    renderer="storefront_builder/partials/global_header/stationery_search.html",
)

#: Soft stationery boutique header: two-tone announcement band, centred brand,
#: account pill and quiet icon actions, light grey navigation bar.
_KAWAII_CENTER_VARIANT = GlobalVariantDefinition(
    key="kawaii_center",
    label_fa="بوتیک ملایم (برند مرکزی + نوار اعلان دوگانه)",
    renderer="storefront_builder/partials/global_header/kawaii_center.html",
)

# A8 semantic header vocabulary.  Several identities deliberately reuse a
# proven renderer when the inventory found the same topology; the identity is
# still useful to recipes while renderer paths remain platform-owned.
_A8_HEADER_VARIANTS = tuple(
    GlobalVariantDefinition(key=key, label_fa=label, renderer=renderer)
    for key, label, renderer in (
        ("editorial_row", "ردیف نشریه‌ای", "storefront_builder/partials/global_header/editorial_row.html"),
        ("marketplace_search", "بازارگاهی جستجو-محور", "storefront_builder/partials/global_header/marketplace_search.html"),
        ("centered_brand", "برند مرکزی", "storefront_builder/partials/global_header/centered_brand.html"),
        ("floating_compact", "شناور فشرده", "storefront_builder/partials/global_header/floating_compact.html"),
        ("compact_drawer", "کشوی فشرده", "storefront_builder/partials/global_header/compact_drawer.html"),
        ("promo_bar", "نوار کمپینی", "storefront_builder/partials/global_header/promo_bar.html"),
        ("community_shortcuts", "میانبرهای اجتماعی", "storefront_builder/partials/global_header/community_shortcuts.html"),
        ("overlay_transparent", "شفاف روی تصویر", "storefront_builder/partials/global_header/overlay_transparent.html"),
        ("editorial_masthead", "سربرگ نشریه‌ای", "storefront_builder/partials/global_header/editorial_masthead.html"),
        ("compact_menu", "منوی فشرده", "storefront_builder/partials/global_header/compact_menu.html"),
        ("category_tabs", "زبانه‌های دسته‌بندی", "storefront_builder/partials/global_header/category_tabs.html"),
        ("playful_canopy", "سایه‌بان بازیگوش", "storefront_builder/partials/global_header/playful_canopy.html"),
    )
)

GLOBAL_HEADER_REGION = GlobalRegionDefinition(
    key="header",
    label_fa="هدر فروشگاه",
    variants=(
        _LEGACY_DEFAULT_VARIANT,
        _MARKETPLACE_SEARCH_FIRST_VARIANT,
        _PREMIUM_THREE_COLUMN_VARIANT,
        _BOUTIQUE_CENTERED_VARIANT,
        _DARK_TECH_VARIANT,
        _PROMO_SEARCH_NAV_VARIANT,
        _BEAUTY_SEARCH_NAV_VARIANT,
        _CHOCOLATE_CENTERED_SEARCH_VARIANT,
        _ATELIER_NAV_VARIANT,
        _LUXURY_SEARCH_VARIANT,
        _STATIONERY_SEARCH_VARIANT,
        _KAWAII_CENTER_VARIANT,
        *_A8_HEADER_VARIANTS,
    ),
    default_variant="legacy_default",
    variant_setting_key="header_variant",
)

#: U2B — backward-compatible default for the Footer region: the exact,
#: unmoved, unmodified partial every published-V2 Store renders today.
#: Same rationale as ``_LEGACY_DEFAULT_VARIANT`` above.
_FOOTER_LEGACY_DEFAULT_VARIANT = GlobalVariantDefinition(
    key="legacy_default",
    label_fa="فعلی / پیش‌فرض",
    renderer="storefront_builder/partials/page_shell_footer.html",
)

_FOOTER_MARKETPLACE_DENSE_VARIANT = GlobalVariantDefinition(
    key="marketplace_dense",
    label_fa="بازارگاهی (فشرده)",
    renderer="storefront_builder/partials/global_footer/marketplace_dense.html",
)

_FOOTER_PREMIUM_COLUMNS_VARIANT = GlobalVariantDefinition(
    key="premium_columns",
    label_fa="پرمیوم چندستونه",
    renderer="storefront_builder/partials/global_footer/premium_columns.html",
)

_FOOTER_BOUTIQUE_EDITORIAL_VARIANT = GlobalVariantDefinition(
    key="boutique_editorial",
    label_fa="بوتیک (نشریه‌ای)",
    renderer="storefront_builder/partials/global_footer/boutique_editorial.html",
)

_FOOTER_DARK_TECH_VARIANT = GlobalVariantDefinition(
    key="dark_tech",
    label_fa="دیجیتال تیره",
    renderer="storefront_builder/partials/global_footer/dark_tech.html",
)

#: Site-target-overhaul (ibolak reference) — a simple, contact-forward
#: 4-column footer with a compact trust/payment row, lighter and less
#: dense than ``marketplace_dense`` so ``dense_marketplace`` stays
#: untouched while a fashion/campaign-style Ready Template can adopt this.
_FOOTER_PROMO_COLUMNS_VARIANT = GlobalVariantDefinition(
    key="promo_columns",
    label_fa="کمپینی (چندستونه ساده)",
    renderer="storefront_builder/partials/global_footer/promo_columns.html",
)

#: Beauty retail footer — a guarantee strip followed by a light, information-
#: dense multi-column footer.  It deliberately reuses the same real merchant
#: data partials as every other footer variant and never embeds merchant IDs.
_FOOTER_BEAUTY_RETAIL_VARIANT = GlobalVariantDefinition(
    key="beauty_retail_columns",
    label_fa="زیبایی (اعتماد + چندستونه)",
    renderer="storefront_builder/partials/global_footer/beauty_retail_columns.html",
)

#: Dark specialty-retail footer for pale storefronts.  Reuses only shared
#: merchant/footer data partials; the decorative top edge is CSS, not copied
#: reference artwork.
_FOOTER_CHOCOLATE_DARK_VARIANT = GlobalVariantDefinition(
    key="chocolate_dark_columns",
    label_fa="شکلاتی (تیره چندستونه)",
    renderer="storefront_builder/partials/global_footer/chocolate_dark_columns.html",
)

#: Dense dark retail footer with a service strip (merchant custom-text block),
#: four information columns, store statement and credibility badges.
_FOOTER_STATIONERY_DARK_VARIANT = GlobalVariantDefinition(
    key="stationery_dark",
    label_fa="لوازم تحریر (تیره با نوار خدمات)",
    renderer="storefront_builder/partials/global_footer/stationery_dark.html",
)

#: Light link-strip footer: pale quick-link strip plus one quiet identity row.
_FOOTER_KAWAII_MINIMAL_VARIANT = GlobalVariantDefinition(
    key="kawaii_minimal",
    label_fa="بوتیک ملایم (نوار پیوند روشن)",
    renderer="storefront_builder/partials/global_footer/kawaii_minimal.html",
)

_A8_FOOTER_VARIANTS = tuple(
    GlobalVariantDefinition(key=key, label_fa=label, renderer=renderer)
    for key, label, renderer in (
        ("minimal", "مینیمال", "storefront_builder/partials/global_footer/minimal.html"),
        ("marketplace_columns", "ستون‌های بازارگاهی", "storefront_builder/partials/global_footer/marketplace_columns.html"),
        ("editorial_wordmark", "نشریه‌ای با نشان‌نوشت", "storefront_builder/partials/global_footer/editorial_wordmark.html"),
        ("brand_story", "روایت برند", "storefront_builder/partials/global_footer/brand_story.html"),
        ("bold_columns", "ستون‌های جسور", "storefront_builder/partials/global_footer/bold_columns.html"),
        ("centered", "فشرده و مرکزی", "storefront_builder/partials/global_footer/centered.html"),
        ("app_download", "پیوندهای همراه", "storefront_builder/partials/global_footer/app_download.html"),
        ("playful_wave", "موج بازیگوش", "storefront_builder/partials/global_footer/playful_wave.html"),
    )
)

GLOBAL_FOOTER_REGION = GlobalRegionDefinition(
    key="footer",
    label_fa="فوتر فروشگاه",
    variants=(
        _FOOTER_LEGACY_DEFAULT_VARIANT,
        _FOOTER_MARKETPLACE_DENSE_VARIANT,
        _FOOTER_PREMIUM_COLUMNS_VARIANT,
        _FOOTER_BOUTIQUE_EDITORIAL_VARIANT,
        _FOOTER_DARK_TECH_VARIANT,
        _FOOTER_PROMO_COLUMNS_VARIANT,
        _FOOTER_BEAUTY_RETAIL_VARIANT,
        _FOOTER_CHOCOLATE_DARK_VARIANT,
        _FOOTER_STATIONERY_DARK_VARIANT,
        _FOOTER_KAWAII_MINIMAL_VARIANT,
        *_A8_FOOTER_VARIANTS,
    ),
    default_variant="legacy_default",
    variant_setting_key="footer_variant",
)

#: Mobile bottom navigation is a third global chrome region.  Its selector is
#: intentionally persisted inside the already-versioned ``footer_config`` JSON
#: (``mobile_nav_variant``), so introducing the capability requires no schema
#: migration and old Stores resolve to ``hidden`` byte-for-byte.
_MOBILE_NAV_HIDDEN_VARIANT = GlobalVariantDefinition(
    key="hidden",
    label_fa="غیرفعال",
    renderer="storefront_builder/partials/global_mobile_nav/hidden.html",
)

_MOBILE_NAV_LUXURY_FLOATING_CART_VARIANT = GlobalVariantDefinition(
    key="luxury_floating_cart",
    label_fa="لوکس شناور (سبد برجسته)",
    renderer="storefront_builder/partials/global_mobile_nav/luxury_floating_cart.html",
)

_A8_MOBILE_NAV_VARIANTS = tuple(
    GlobalVariantDefinition(
        key=key,
        label_fa=label,
        renderer=f"storefront_builder/partials/global_mobile_nav/{key}.html",
    )
    for key, label in (
        ("four_item", "چهار مقصد"),
        ("five_item", "پنج مقصد"),
        ("raised_cart", "سبد برجسته"),
        ("floating_dock", "داک شناور"),
        ("glass_dock", "داک شیشه‌ای"),
        ("minimal_icons", "آیکن‌های مینیمال"),
        ("wide_cart", "سبد عریض"),
    )
)

GLOBAL_MOBILE_NAV_REGION = GlobalRegionDefinition(
    key="mobile_bottom_nav",
    label_fa="ناوبری پایین موبایل",
    variants=(
        _MOBILE_NAV_HIDDEN_VARIANT,
        _MOBILE_NAV_LUXURY_FLOATING_CART_VARIANT,
        *_A8_MOBILE_NAV_VARIANTS,
    ),
    default_variant="hidden",
    variant_setting_key="mobile_nav_variant",
)

#: Every global chrome region. Header/Footer retain their historical defaults;
#: the new mobile region defaults to a no-op renderer for complete backwards
#: compatibility.
_GLOBAL_REGIONS: tuple[GlobalRegionDefinition, ...] = (
    GLOBAL_HEADER_REGION, GLOBAL_FOOTER_REGION, GLOBAL_MOBILE_NAV_REGION,
)

for _region in _GLOBAL_REGIONS:
    _validate_global_region(_region)
del _region


# --------------------------------------------------------------- resolve

def list_global_variants(region: GlobalRegionDefinition) -> tuple[GlobalVariantDefinition, ...]:
    return region.variants


def get_global_variant(region: GlobalRegionDefinition, variant_key: str | None) -> GlobalVariantDefinition | None:
    """Lookup by key — ``None`` for a missing/unknown key (no exception;
    the caller decides the fallback), exactly ``variant_contract.get_variant``'s
    contract."""
    if not variant_key:
        return None
    for variant in region.variants:
        if variant.key == variant_key:
            return variant
    return None


def resolve_active_global_variant(region: GlobalRegionDefinition, config: dict | None) -> GlobalVariantDefinition:
    """Read-time resolution — pure, no DB query, never raises. An
    absent/blank/unknown (including retired-in-a-future-release) stored
    key always falls safely back to ``region.default_variant``, which
    ``_validate_global_region`` already guaranteed resolves to a real,
    registered variant at import time — so this function's return value is
    never ``None``, unlike ``variant_contract.resolve_active_variant``
    (which legitimately returns ``None`` for the common "no variants
    registered at all" section case; a ``GlobalRegionDefinition`` never has
    that empty case, see its docstring)."""
    config = config if isinstance(config, dict) else {}
    requested = config.get(region.variant_setting_key)
    match = get_global_variant(region, requested)
    if match is not None:
        return match
    default_match = get_global_variant(region, region.default_variant)
    assert default_match is not None, "GlobalRegionDefinition.default_variant validated at import time"
    return default_match


def resolve_global_renderer_template(region: GlobalRegionDefinition, config: dict | None) -> str:
    """The one function render code/templates should call — resolves the
    active variant and returns its trusted renderer path directly, so
    callers never need to touch a ``GlobalVariantDefinition`` themselves."""
    return resolve_active_global_variant(region, config).renderer


class UnknownGlobalVariantSelectionError(ValueError):
    """Write-time (editor POST) counterpart of
    ``variant_contract.UnknownVariantSelectionError`` — a merchant submitted
    a ``header_variant`` value that names no registered variant. Never
    raised at read time (see ``resolve_active_global_variant`` above)."""


def validate_global_variant_selection(region: GlobalRegionDefinition, value) -> str:
    """Write-time validation for the editor POST path. An absent/blank
    value is not an error — it resolves to ``region.default_variant``
    (mirrors every other ``HEADER_TOGGLE_FIELDS``-style field's
    ``config.get(field, <default>)`` pattern in
    ``layout_service.validate_header_config``). A present, non-empty value
    that names no registered variant is rejected outright — a tampered/
    stale POST must never be able to persist an arbitrary string into
    ``header_config[region.variant_setting_key]``."""
    if not value:
        return region.default_variant
    if not isinstance(value, str) or get_global_variant(region, value) is None:
        raise UnknownGlobalVariantSelectionError(
            f"مقدارِ «{value}» برایِ سبکِ «{region.label_fa}» به هیچ Variantِ ثبت‌شده‌ای اشاره نمی‌کند"
        )
    return value
