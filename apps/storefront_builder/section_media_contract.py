"""Neutral, dependency-light shared contract for section-scoped media
Placements (``HeroSlide``/``PromotionalBanner``/``StoryRailItem``).

Both ``services.layout_service`` (Published→Draft clone) and ``models``
(``StorefrontLayoutVersion.compute_fingerprint`` publication-content
fingerprinting, plus ``media_views``'s own before/after edit-semantics
check) need the exact same answer to "what does 'the same Placement,
unchanged' mean" — which related_names exist, which fields are copied
verbatim on clone / compared verbatim for dirty-detection, which FK
fields point at a shared ``MediaAsset``, and what a Placement's own
render-visible identity resolves to when it has no asset FK yet (a
legacy, pre-Phase-0.5 row).

This module is the ONE place that answer lives. It imports nothing from
``models`` or ``services.layout_service`` (no Django model classes, no
DB access — every function here operates on a generic ``row`` object via
plain ``getattr``), so both of those modules can import from here at
their own top level with no risk of a circular import in either
direction.

No DB writes. No renderer. No second media authority — this is read-only
semantic vocabulary, not a competing CRUD path to ``media_views``.
"""

from __future__ import annotations

#: related_name on StorefrontSection -> the three section-scoped media
#: families that exist. Order is not semantically meaningful.
SCOPED_MEDIA_MODELS = ("hero_slides", "banners", "story_items")

#: related_name -> tuple of MediaAsset FK id field names that Placement
#: model has. These are copied verbatim on clone (same asset_id — never a
#: freshly-created MediaAsset) and are part of a Placement's fingerprinted
#: identity, resolved through ``placement_semantic_payload`` below (never
#: as a bare id when the FK is unset).
ASSET_FK_FIELDS = {
    "hero_slides": ("desktop_asset_id", "mobile_asset_id"),
    "banners": ("desktop_asset_id", "mobile_asset_id"),
    "story_items": ("image_asset_id",),
}

#: related_name -> tuple of non-FK content fields copied verbatim on clone
#: / compared verbatim for dirty-detection. This is the render-visible
#: field set for each Placement kind: title/text, active state, display
#: order, button label/show-button, and every destination/link field.
PLACEMENT_CONTENT_FIELDS = {
    "hero_slides": (
        "title", "subtitle", "button_label", "show_button", "is_active", "display_order",
        "destination_type", "destination_category_id", "destination_product_id",
        "destination_brand_id", "destination_collection_id", "destination_external_url",
        "open_in_new_tab",
    ),
    "banners": (
        "title", "description", "button_label", "show_button", "is_active", "display_order",
        "destination_type", "destination_category_id", "destination_product_id",
        "destination_brand_id", "destination_collection_id", "destination_external_url",
        "open_in_new_tab",
    ),
    "story_items": (
        "title", "is_active", "display_order",
        "destination_type", "destination_category_id", "destination_product_id",
        "destination_brand_id", "destination_collection_id", "destination_external_url",
        "open_in_new_tab",
    ),
}

#: An asset FK id field name -> the legacy ``ImageField`` it falls back to
#: when unset, mirroring exactly the same precedence
#: ``apps.content.models._resolve_placement_media_url`` uses for
#: rendering (MediaAsset first, legacy file second). Only consulted for a
#: Placement that still has NO asset FK — a row
#: ``layout_service._clone_section_scoped_media`` never clones in the
#: first place (see its ``has_any_asset`` guard), so this fallback can
#: never disagree between an unchanged Published row and its own Draft
#: clone: there simply is no cloned counterpart to disagree with.
LEGACY_IMAGE_FIELD_FOR_ASSET_ID_FIELD = {
    "desktop_asset_id": "desktop_image",
    "mobile_asset_id": "mobile_image",
    "image_asset_id": "image",
}


def placement_semantic_payload(row, related_name: str) -> dict:
    """One section-scoped media Placement's canonical, PK-independent,
    render-visible publication-semantic identity.

    Never includes ``row.pk``/``row.id`` — Published and a cloned Draft
    are separate rows by construction (a clone always creates NEW rows),
    so two placements that are "the same Placement, unchanged" on either
    side of a clone must compare equal here despite having different
    primary keys.

    Used by two independent callers that must never define "the same
    Placement" two different ways: ``StorefrontLayoutVersion
    .compute_fingerprint`` (Published vs. Draft dirty-detection) and
    ``media_views``'s own before/after comparison (does an EDIT actually
    change anything semantic, or just re-save identical values — see
    ``storefront_section_media_form``).
    """
    data = {field: getattr(row, field) for field in PLACEMENT_CONTENT_FIELDS[related_name]}
    for asset_id_field in ASSET_FK_FIELDS[related_name]:
        asset_id = getattr(row, asset_id_field)
        if asset_id:
            data[asset_id_field] = asset_id
        else:
            legacy_field_name = LEGACY_IMAGE_FIELD_FOR_ASSET_ID_FIELD[asset_id_field]
            legacy_file = getattr(row, legacy_field_name)
            data[asset_id_field] = legacy_file.name if legacy_file else None
    return data
