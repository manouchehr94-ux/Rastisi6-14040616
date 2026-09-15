"""The initial ordered family catalog for the central design engine."""

from .contracts import (
    ComponentFamilyDefinition,
    StoreAppearanceManifest,
    validate_family_catalog,
)


_FAMILY_DEFINITIONS = (
    ComponentFamilyDefinition(
        key="header",
        label_fa="هدر",
        storage_adapter_key="header_region",
        safe_default_component_key="header.legacy_default.v1",
        renderer_role="global_region",
        capabilities={"responsive", "rtl"},
    ),
    ComponentFamilyDefinition(
        key="mega_menu",
        label_fa="مگامنو",
        storage_adapter_key="mega_menu_region",
        safe_default_component_key="mega_menu.none.v1",
        renderer_role="global_region",
        optional=True,
        capabilities={"responsive", "rtl"},
    ),
    ComponentFamilyDefinition(
        key="hero",
        label_fa="هیرو و اسلایدر اول",
        storage_adapter_key="hero_section_variant",
        safe_default_component_key="hero.legacy_default.v1",
        renderer_role="section_variant",
        capabilities={"responsive", "rtl"},
    ),
    ComponentFamilyDefinition(
        key="layout",
        label_fa="چیدمان و ترکیب‌بندی",
        storage_adapter_key="layout_composition",
        safe_default_component_key="layout.legacy_default.v1",
        renderer_role="composition",
        capabilities={"responsive", "rtl"},
    ),
    ComponentFamilyDefinition(
        key="product_view",
        label_fa="نمایش محصولات",
        storage_adapter_key="product_view_section_variant",
        safe_default_component_key="product_view.legacy_default.v1",
        renderer_role="section_variant",
        capabilities={"responsive", "rtl"},
    ),
    ComponentFamilyDefinition(
        key="card",
        label_fa="کارت محصول",
        storage_adapter_key="product_card_variant",
        safe_default_component_key="card.legacy_default.v1",
        renderer_role="section_variant",
        capabilities={"responsive", "rtl"},
    ),
    ComponentFamilyDefinition(
        key="badge",
        label_fa="نشان و نمایش تخفیف",
        storage_adapter_key="badge_treatment",
        safe_default_component_key="badge.none.v1",
        renderer_role="section_variant",
        optional=True,
        capabilities={"responsive", "rtl"},
    ),
    ComponentFamilyDefinition(
        key="motion",
        label_fa="حرکت",
        storage_adapter_key="motion_profile",
        safe_default_component_key="motion.subtle.v1",
        renderer_role="appearance_token",
        capabilities={"reduced_motion"},
    ),
    ComponentFamilyDefinition(
        key="footer",
        label_fa="فوتر",
        storage_adapter_key="footer_region",
        safe_default_component_key="footer.legacy_default.v1",
        renderer_role="global_region",
        capabilities={"responsive", "rtl"},
    ),
    ComponentFamilyDefinition(
        key="bottom_nav",
        label_fa="ناوبری پایین موبایل",
        storage_adapter_key="mobile_bottom_nav_region",
        safe_default_component_key="bottom_nav.hidden.v1",
        renderer_role="global_region",
        optional=True,
        capabilities={"mobile", "rtl", "safe_area"},
    ),
    # P5-W2 — reversible occasion/seasonal Theme layer. An OPTIONAL
    # appearance-token family (like ``motion``): it tints/decorates the
    # storefront without owning any structural region/section/composition.
    # renderer_role MUST be ``appearance_token`` (an existing allowed role);
    # ``_RENDERER_ROLES`` is NOT expanded. The safe default ``theme.none.v1``
    # is a true visual no-op, so pre-W2 rendering is materially unchanged.
    ComponentFamilyDefinition(
        key="theme",
        label_fa="تم مناسبتی",
        storage_adapter_key="theme_overlay",
        safe_default_component_key="theme.none.v1",
        renderer_role="appearance_token",
        optional=True,
        capabilities={"responsive", "rtl"},
    ),
)

validate_family_catalog(_FAMILY_DEFINITIONS)

COMPONENT_FAMILIES = {definition.key: definition for definition in _FAMILY_DEFINITIONS}

DEFAULT_STORE_APPEARANCE_MANIFEST = StoreAppearanceManifest(
    schema_version=1,
    selections={
        definition.key: definition.safe_default_component_key
        for definition in _FAMILY_DEFINITIONS
    },
)
