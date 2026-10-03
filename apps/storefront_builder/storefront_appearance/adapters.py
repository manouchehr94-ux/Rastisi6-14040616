"""Adapters from Store Appearance identities to existing R4 registries.

Persisted component keys are never renderer paths.  These adapters resolve a
platform-owned symbolic reference to the already-registered implementation.
"""

from __future__ import annotations

from collections.abc import Iterable

from .. import appearance_registry, global_region_registry, section_registry
from .. import theme_catalog
from ..services import container_service
from ..variant_contract import get_variant
from .contracts import ComponentDefinition, InvalidStoreAppearanceContract


_GLOBAL_REGIONS = {
    "header": global_region_registry.GLOBAL_HEADER_REGION,
    "footer": global_region_registry.GLOBAL_FOOTER_REGION,
    "mobile_bottom_nav": global_region_registry.GLOBAL_MOBILE_NAV_REGION,
}

_VIRTUAL_COMPONENTS = frozenset(
    {
        ("mega_menu", "none"),
        ("card", "legacy_default"),
        ("badge", "none"),
    }
)

_A8_HERO_ALIASES = (
    ("none", "overlay", "بدون هیروی تصویری"),
    ("immersive", "luxury_showcase", "فراگیر"),
    ("editorial_split", "split", "دوپاره نشریه‌ای"),
    ("promo_bento", "chocolate_carousel", "بنتوی کمپینی"),
    ("typographic", "split", "تایپوگرافیک"),
    ("product_focus", "beauty_editorial", "تمرکز محصول"),
    ("image_collage", "atelier_triptych", "کلاژ تصویری"),
    ("side_offer_slider", "chocolate_carousel", "اسلایدر با پیشنهاد جانبی"),
    ("media_feature", "overlay", "رسانه شاخص"),
    ("quiet", "split", "آرام"),
    ("search_first", "split", "جستجو-محور"),
    ("campaign_mosaic", "atelier_triptych", "موزاییک کمپین"),
    ("social_gallery", "atelier_triptych", "گالری اجتماعی"),
)

_A8_LAYOUT_ALIASES = (
    ("two_column", "half"),
    ("three_column", "thirds"),
    ("four_column", "quarters"),
    ("dense_five", "quarters"),
    ("horizontal_rail", "single"),
    ("catalog_list", "single"),
    ("bento_grid", "quarter_left"),
    ("featured_split", "third_right"),
    ("editorial_zigzag", "quarter_right"),
)

_A8_PRODUCT_VIEW_ALIASES = (
    ("standard_grid", "product_section", "grid"),
    ("carousel", "product_section", "carousel"),
    ("dense_grid", "catalog_product_wall", "group_columns"),
    ("editorial_grid", "product_section", "grid"),
    ("catalog_list", "catalog_product_wall", "rows"),
    ("bento", "catalog_product_wall", "featured_row"),
    ("featured_wall", "catalog_product_wall", "featured_row"),
)

#: Merchant-facing names of the A8 product-view aliases above (this registry
#: is their only definition, so their label lives here too).
_A8_PRODUCT_VIEW_LABELS_FA = {
    "standard_grid": "شبکهٔ استاندارد",
    "carousel": "کاروسل",
    "dense_grid": "شبکهٔ فشرده",
    "editorial_grid": "شبکهٔ تحریریه‌ای",
    "catalog_list": "فهرست کاتالوگی",
    "bento": "بنتو",
    "featured_wall": "دیوار ویژه",
}

_A8_CARD_STYLES = (
    "standard", "marketplace_price", "editorial_minimal", "retail_row",
    "luxury_dark", "soft_capsule", "beauty_glass", "paper_frame",
    "price_first", "portrait_round", "catalog_index", "shipping_label",
    "shelf_editorial", "technical_spec", "tech_neon", "bold_outline",
)

#: Merchant-facing names of the A8 card styles above.
_A8_CARD_STYLE_LABELS_FA = {
    "standard": "استاندارد",
    "marketplace_price": "قیمت‌محور بازارگاهی",
    "editorial_minimal": "مینیمال تحریریه‌ای",
    "retail_row": "ردیفی فروشگاهی",
    "luxury_dark": "لوکس تیره",
    "soft_capsule": "کپسولی نرم",
    "beauty_glass": "شیشه‌ای زیبایی",
    "paper_frame": "قاب کاغذی",
    "price_first": "قیمت در صدر",
    "portrait_round": "پرترهٔ گرد",
    "catalog_index": "فهرست کاتالوگی",
    "shipping_label": "برچسب ارسال",
    "shelf_editorial": "قفسهٔ تحریریه‌ای",
    "technical_spec": "مشخصات فنی",
    "tech_neon": "نئون دیجیتال",
    "bold_outline": "خط‌دور پررنگ",
}


def _component(
    *,
    key: str,
    family_key: str,
    label_fa: str,
    registry_reference: str,
    capabilities: Iterable[str] = ("responsive", "rtl"),
) -> ComponentDefinition:
    return ComponentDefinition(
        key=key,
        family_key=family_key,
        version=1,
        label_fa=label_fa,
        registry_reference=registry_reference,
        capabilities=capabilities,
    )


def _global_region_components(
    family_key: str,
    region: global_region_registry.GlobalRegionDefinition,
    *,
    default_identity: str,
) -> list[ComponentDefinition]:
    definitions = []
    for variant in global_region_registry.list_global_variants(region):
        identity = default_identity if variant.key == region.default_variant else variant.key
        definitions.append(
            _component(
                key=f"{family_key}.{identity}.v1",
                family_key=family_key,
                label_fa=variant.label_fa,
                registry_reference=f"global_region:{region.key}:{variant.key}",
                capabilities=("mobile", "rtl", "safe_area")
                if family_key == "bottom_nav"
                else ("responsive", "rtl"),
            )
        )
    return definitions


def _section_variant_components(
    family_key: str,
    section_key: str,
    *,
    default_identity: str,
    identity_prefix: str = "",
) -> list[ComponentDefinition]:
    section = section_registry.get_definition(section_key)
    definitions = []
    for variant in section.variants:
        identity = default_identity if variant.key == section.default_variant else f"{identity_prefix}{variant.key}"
        definitions.append(
            _component(
                key=f"{family_key}.{identity}.v1",
                family_key=family_key,
                label_fa=variant.label_fa,
                registry_reference=f"section_variant:{section_key}:{variant.key}",
                capabilities=variant.capabilities | frozenset({"responsive", "rtl"}),
            )
        )
    return definitions


def build_existing_component_definitions() -> tuple[ComponentDefinition, ...]:
    """Return deterministic adapters for the implementations present at R4 Phase 1."""

    definitions: list[ComponentDefinition] = []

    definitions.extend(
        _global_region_components(
            "header",
            global_region_registry.GLOBAL_HEADER_REGION,
            default_identity="legacy_default",
        )
    )
    definitions.append(
        _component(
            key="mega_menu.none.v1",
            family_key="mega_menu",
            label_fa="بدون مگامنو",
            registry_reference="virtual:mega_menu:none",
        )
    )
    definitions.extend(
        _section_variant_components(
            "hero", "hero_banner", default_identity="legacy_default"
        )
    )
    for identity, variant_key, label_fa in _A8_HERO_ALIASES:
        definitions.append(
            _component(
                key=f"hero.{identity}.v1",
                family_key="hero",
                label_fa=label_fa,
                registry_reference=f"section_variant:hero_banner:{variant_key}",
            )
        )

    for layout_key in container_service.LAYOUT_PRESETS:
        identity = "legacy_default" if layout_key == "single" else layout_key
        definitions.append(
            _component(
                key=f"layout.{identity}.v1",
                family_key="layout",
                label_fa=f"چیدمان {layout_key}",
                registry_reference=f"composition:{layout_key}",
            )
        )
    for identity, layout_key in _A8_LAYOUT_ALIASES:
        definitions.append(
            _component(
                key=f"layout.{identity}.v1",
                family_key="layout",
                label_fa=f"چیدمان {identity}",
                registry_reference=f"composition:{layout_key}",
            )
        )

    definitions.extend(
        _section_variant_components(
            "product_view", "product_section", default_identity="legacy_default"
        )
    )
    for identity, section_key, variant_key in _A8_PRODUCT_VIEW_ALIASES:
        definitions.append(
            _component(
                key=f"product_view.{identity}.v1",
                family_key="product_view",
                label_fa=f"نمای محصولات {_A8_PRODUCT_VIEW_LABELS_FA.get(identity, identity)}",
                registry_reference=f"section_variant:{section_key}:{variant_key}",
            )
        )
    definitions.extend(
        _section_variant_components(
            "product_view",
            "catalog_product_wall",
            default_identity="catalog_rows",
            identity_prefix="catalog_",
        )
    )

    definitions.append(
        _component(
            key="card.legacy_default.v1",
            family_key="card",
            label_fa="کارت فعلی / پیش‌فرض",
            registry_reference="virtual:card:legacy_default",
        )
    )
    for style in _A8_CARD_STYLES:
        definitions.append(
            _component(
                key=f"card.{style}.v1",
                family_key="card",
                label_fa=f"کارت {_A8_CARD_STYLE_LABELS_FA.get(style, style)}",
                registry_reference=f"card_style:{style}",
            )
        )
    definitions.append(
        _component(
            key="badge.none.v1",
            family_key="badge",
            label_fa="بدون نشان تزئینی",
            registry_reference="virtual:badge:none",
        )
    )
    definitions.append(
        _component(
            key="badge.sale.v1",
            family_key="badge",
            label_fa="تأکید فروش",
            registry_reference="badge_treatment:sale",
        )
    )

    for motion_key in appearance_registry.MOTION_CHOICES:
        definitions.append(
            _component(
                key=f"motion.{motion_key}.v1",
                family_key="motion",
                label_fa=f"حرکت {motion_key}",
                registry_reference=f"appearance_motion:{motion_key}",
                capabilities=("reduced_motion",),
            )
        )

    definitions.extend(
        _global_region_components(
            "footer",
            global_region_registry.GLOBAL_FOOTER_REGION,
            default_identity="legacy_default",
        )
    )
    definitions.extend(
        _global_region_components(
            "bottom_nav",
            global_region_registry.GLOBAL_MOBILE_NAV_REGION,
            default_identity="hidden",
        )
    )

    # P5-W2 — Theme (occasion/seasonal) components. The occasion identities,
    # labels and presentation metadata live ONLY in ``theme_catalog``; this
    # adapter merely projects each catalog entry into a ComponentDefinition
    # whose symbolic ``theme_overlay:<occasion-key>`` reference resolves back
    # against that same catalog. No occasion data is duplicated here.
    for occasion in theme_catalog.list_theme_occasions():
        definitions.append(
            _component(
                key=occasion.component_key,
                family_key="theme",
                label_fa=occasion.label_fa,
                registry_reference=occasion.registry_reference,
            )
        )
    return tuple(definitions)


def resolve_registry_reference(reference: str):
    """Resolve one trusted symbolic reference to its existing implementation."""

    parts = reference.split(":")
    resolved = None
    if len(parts) == 3 and parts[0] == "global_region":
        region = _GLOBAL_REGIONS.get(parts[1])
        if region is not None:
            resolved = global_region_registry.get_global_variant(region, parts[2])
    elif len(parts) == 3 and parts[0] == "section_variant":
        try:
            section = section_registry.get_definition(parts[1])
        except section_registry.UnknownSectionTypeError:
            section = None
        if section is not None:
            resolved = get_variant(section, parts[2])
    elif len(parts) == 2 and parts[0] == "composition":
        resolved = container_service.LAYOUT_PRESETS.get(parts[1])
    elif len(parts) == 2 and parts[0] == "appearance_motion":
        if parts[1] in appearance_registry.MOTION_CHOICES:
            resolved = parts[1]
    elif len(parts) == 2 and parts[0] == "card_style":
        if parts[1] in section_registry.CARD_STYLE_CHOICES:
            resolved = parts[1]
    elif len(parts) == 2 and parts[0] == "badge_treatment":
        if parts[1] in section_registry.BADGE_TREATMENT_CHOICES:
            resolved = parts[1]
    elif len(parts) == 2 and parts[0] == "theme_overlay":
        # Resolve the bounded symbolic Theme reference against the single
        # canonical ``theme_catalog``. Unknown occasion keys fail closed.
        if theme_catalog.has_occasion(parts[1]):
            resolved = theme_catalog.get_theme_occasion(parts[1])
    elif len(parts) == 3 and parts[0] == "virtual":
        token = (parts[1], parts[2])
        if token in _VIRTUAL_COMPONENTS:
            resolved = token

    if resolved is None:
        raise InvalidStoreAppearanceContract(
            f"unresolvable registry reference: {reference}"
        )
    return resolved


def resolve_component_implementation(component: ComponentDefinition):
    if not isinstance(component, ComponentDefinition):
        raise InvalidStoreAppearanceContract("component definition is required")
    return resolve_registry_reference(component.registry_reference)
