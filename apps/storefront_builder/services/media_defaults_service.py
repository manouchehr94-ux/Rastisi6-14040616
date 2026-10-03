"""Store-wide *default* media (hero slides / banners / story items) — made visible
and adoptable from the R4 media manager.

Background
----------
A media Placement (``HeroSlide`` / ``PromotionalBanner`` / ``StoryRailItem``) is
either **section-scoped** (``section`` = one section of one layout version —
what the R4 media manager lists and edits) or **store-wide** (``section IS
NULL`` — the legacy, pre-Visual-Builder model; every demo seed command and the
legacy dashboard "homepage media" screen create these).

``render_service._scoped_hero_slides`` (and its banner / story twins) renders a
section's own ACTIVE items when it has any, and otherwise FALLS BACK to the
store's active store-wide items. The manager only ever lists the section's own
items, so before this service a store showing store-wide demo images presented
an empty "Manage slides" list, and adding the first slide silently switched the
renderer over and hid every default image.

This module does two things, and nothing else:

* :func:`default_media_state` — report, using exactly the renderer's own
  conditions, whether the fallback is currently in effect and which rows it is
  showing (read-only; never writes).
* :func:`adopt_store_defaults` — an explicit, merchant-triggered action that
  COPIES the in-effect store-wide rows into the section as ordinary scoped
  Placements. Originals are never modified, moved, deleted or de-activated
  (they are shared by the Published storefront, so editing them in place would
  bypass the Draft → Publish separation). Image files are not copied: each copy
  gets its own ``MediaAsset`` pointing at the same stored file (the existing
  ``_sync_asset_references`` convention; retention-first, nothing is ever
  physically deleted), which is also what lets publish clone the Placement
  (``layout_service._clone_section_scoped_media`` skips rows with no asset FK).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from django.db import transaction
from django.db.models import Max

from apps.content.models import MediaAsset

from ..section_media_contract import PLACEMENT_CONTENT_FIELDS


@dataclass
class DefaultMediaState:
    #: True when the renderer is CURRENTLY falling back to store-wide rows for
    #: this section (the section has no active item of its own AND the store
    #: has at least one active store-wide item).
    in_effect: bool = False
    #: The store-wide rows being shown (empty unless ``in_effect``).
    items: list = field(default_factory=list)
    #: The section owns items but every one is inactive (so the fallback is in
    #: effect only because nothing of its own is active).
    all_inactive: bool = False


@dataclass
class AdoptResult:
    created: int = 0
    #: Store-wide rows with no effective image at all (nothing to adopt).
    skipped: int = 0


def _store_id_of(section) -> int:
    # The section's own layout owns its store; never trust a caller-supplied one.
    return section.page.version.layout.store_id


def _store_default_rows(model, store_id):
    """EXACTLY the fallback query the renderer uses (see ``render_service``)."""
    return model.objects.filter(
        store_id=store_id, section__isnull=True, is_active=True,
    ).order_by("display_order", "id")


def default_media_state(section, model) -> DefaultMediaState:
    if section is None or section.pk is None:
        return DefaultMediaState()
    if model.objects.filter(section=section, is_active=True).exists():
        return DefaultMediaState()
    items = list(_store_default_rows(model, _store_id_of(section)))
    if not items:
        return DefaultMediaState()
    return DefaultMediaState(
        in_effect=True, items=items,
        all_inactive=model.objects.filter(section=section).exists(),
    )


def adopt_store_defaults(section, *, model, related_name: str, asset_fields: dict) -> AdoptResult:
    """Copy the in-effect store-wide rows into ``section`` as scoped Placements.

    Idempotent and safe against a double submit: the section row is locked, and
    the "fallback is in effect" condition is re-checked under the lock, so a
    second call finds the section already owns active items and does nothing.
    """
    from ..models import StorefrontSection

    with transaction.atomic():
        locked = StorefrontSection.objects.select_for_update().get(pk=section.pk)
        if model.objects.filter(section=locked, is_active=True).exists():
            return AdoptResult()
        store_id = _store_id_of(locked)
        defaults = list(_store_default_rows(model, store_id))
        if not defaults:
            return AdoptResult()

        last = model.objects.filter(section=locked).aggregate(m=Max("display_order"))["m"]
        base = 0 if last is None else last + 1

        clones, skipped = [], 0
        for index, row in enumerate(defaults):
            kwargs = {"store_id": store_id, "section": locked}
            for name in PLACEMENT_CONTENT_FIELDS[related_name]:
                kwargs[name] = getattr(row, name)
            kwargs["display_order"] = base + index  # keep the defaults' relative order, after any own items
            kwargs["is_active"] = True

            has_media = False
            for file_field, asset_field in asset_fields.items():
                asset_id = getattr(row, f"{asset_field}_id", None)
                if not asset_id:
                    stored = getattr(row, file_field)
                    if stored:
                        asset_id = MediaAsset.objects.create(store_id=store_id, image=stored.name).pk
                if asset_id:
                    kwargs[f"{asset_field}_id"] = asset_id
                    has_media = True
            if not has_media:
                skipped += 1
                continue
            clones.append(model(**kwargs))

        if clones:
            model.objects.bulk_create(clones)
        return AdoptResult(created=len(clones), skipped=skipped)
