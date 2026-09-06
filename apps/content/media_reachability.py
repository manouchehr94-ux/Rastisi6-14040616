"""L07 / A05 — extended media-asset reachability scans (JSON background +
recovery snapshots).

``MediaAsset.is_referenced`` historically only ORed the five direct FK
placement reverse relations (Hero desktop/mobile, Banner desktop/mobile,
Story). That leaves it BLIND to two additional *live* reference classes from
the media-reference taxonomy (inventory §5):

  * Class #2 — JSON background:
    ``StorefrontSection.settings["background"]["media_asset_id"]``. An asset
    used only as a section background is still shown to visitors, yet the FK
    scan reports it unreferenced.
  * Class #4 — recovery snapshot: an asset id captured inside an edit-history
    entry (``StorefrontEditHistoryEntry.before_state``/``after_state``) or a
    version's ``template_baseline_snapshot``. Such an asset is still
    *recoverable* (Undo/Redo/restore/reset-to-baseline).

Because ``delete_media_asset_if_unreferenced`` trusts ``is_referenced`` as the
single deletion gate, an asset referenced ONLY via one of these classes could
be physically deleted — breaking a still-visible background or a recoverable
state. This module closes that gap.

Design invariants (approved spec §12–13):

* **Tenant-scoped.** Every query is bounded to the asset's OWN store
  (``asset.store``) via the ownership chain
  ``StorefrontSection → page → version → layout → store`` (and
  ``StorefrontEditHistoryEntry → draft_version → layout → store``). We NEVER
  full-table-scan across stores — an id colliding in ANOTHER store's JSON must
  not make this asset look referenced.
* **Fail-closed / conservative.** If any scan raises unexpectedly, we treat
  the asset as REFERENCED (return ``True``) — never risk deleting a live or
  recoverable asset because of a scan error/ambiguity.
* **Id-key matching (not "any integer anywhere").** We only treat the asset id
  as present when it appears under a KNOWN media-id key
  (``media_asset_id`` for backgrounds; ``desktop_asset_id`` /
  ``mobile_asset_id`` / ``image_asset_id`` for serialized placements). We walk
  the nested JSON and compare the value of those keys against the asset id —
  so an unrelated integer that merely equals the id elsewhere in the payload
  does not spuriously match.
* **Bounded.** Store-scoped querysets only; the (small) set of the store's
  section settings / history states / baseline snapshots is loaded and scanned
  in Python.
"""

from __future__ import annotations

#: Known JSON keys whose value is a ``MediaAsset`` primary key. Matching is
#: restricted to these keys so the scan cannot spuriously match an unrelated
#: integer that merely happens to equal the asset id.
MEDIA_ID_KEYS = (
    "media_asset_id",   # section background JSON (#2) + serialized backgrounds
    "desktop_asset_id",  # serialized Hero/Banner placement (#4 snapshots)
    "mobile_asset_id",   # serialized Hero/Banner placement (#4 snapshots)
    "image_asset_id",    # serialized Story placement (#4 snapshots)
)


def _matches_asset_id(value, asset_pk: int) -> bool:
    """Does ``value`` (the value stored under a known media-id key) equal
    ``asset_pk``? Tolerates ints and numeric strings; ignores anything else
    (``None``, non-numeric, nested containers under the key itself)."""
    if value is None:
        return False
    if isinstance(value, bool):
        # bools are ints in Python; a boolean is never a media id.
        return False
    if isinstance(value, int):
        return value == asset_pk
    if isinstance(value, str):
        try:
            return int(value.strip()) == asset_pk
        except (TypeError, ValueError):
            return False
    return False


def _payload_references_asset(payload, asset_pk: int) -> bool:
    """Recursively walk an arbitrary JSON-ish structure and return ``True``
    iff the asset id appears under one of :data:`MEDIA_ID_KEYS`.

    This deliberately checks the VALUE of known id keys rather than scanning
    for the integer anywhere, so it will not match an unrelated field that
    coincidentally equals the id (e.g. an ``order`` or ``product_id``)."""
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in MEDIA_ID_KEYS and _matches_asset_id(value, asset_pk):
                return True
            # Recurse into nested containers (values may be dicts/lists).
            if isinstance(value, (dict, list)) and _payload_references_asset(value, asset_pk):
                return True
        return False
    if isinstance(payload, (list, tuple)):
        for item in payload:
            if _payload_references_asset(item, asset_pk):
                return True
        return False
    return False


def _referenced_by_section_backgrounds(asset) -> bool:
    """Class #2 — any of the store's section ``settings["background"]
    ["media_asset_id"]`` (across Draft/Published/Archived versions) equals the
    asset id.

    Store-scoped via ``page__version__layout__store``. We scan the full
    ``settings`` payload with the id-key matcher so the check also survives
    minor shape drift, but the canonical location is
    ``settings.background.media_asset_id`` (written by
    ``views._extract_background_raw``)."""
    from apps.storefront_builder.models import StorefrontSection

    settings_qs = StorefrontSection.objects.filter(
        page__version__layout__store=asset.store,
    ).values_list("settings", flat=True)
    for settings in settings_qs.iterator():
        if _payload_references_asset(settings, asset.pk):
            return True
    return False


def _referenced_by_recovery_snapshots(asset) -> bool:
    """Class #4 — the asset id is captured in a recoverable snapshot for the
    store:

    * any ``StorefrontEditHistoryEntry.before_state`` / ``after_state`` on a
      draft of the store (scoped via ``draft_version__layout__store``), or
    * any version's ``template_baseline_snapshot`` for the store (scoped via
      ``layout__store``).

    Both payloads are scanned with the id-key matcher, so the asset id counts
    whether it appears as a background ``media_asset_id`` or as a serialized
    placement field (``desktop_asset_id`` / ``mobile_asset_id`` /
    ``image_asset_id``)."""
    from apps.storefront_builder.models import (
        StorefrontEditHistoryEntry,
        StorefrontLayoutVersion,
    )

    history_qs = StorefrontEditHistoryEntry.objects.filter(
        draft_version__layout__store=asset.store,
    ).values_list("before_state", "after_state")
    for before_state, after_state in history_qs.iterator():
        if _payload_references_asset(before_state, asset.pk):
            return True
        if _payload_references_asset(after_state, asset.pk):
            return True

    baseline_qs = StorefrontLayoutVersion.objects.filter(
        layout__store=asset.store,
    ).values_list("template_baseline_snapshot", flat=True)
    for snapshot in baseline_qs.iterator():
        if _payload_references_asset(snapshot, asset.pk):
            return True
    return False


def is_reachable_via_json_or_snapshots(asset) -> bool:
    """Return ``True`` if ``asset`` is referenced by a JSON background (#2) or
    a recovery snapshot (#4), scanning ONLY the asset's own store.

    FAIL-CLOSED: any unexpected error while scanning is treated as
    "referenced" (returns ``True``) so a scan failure can never green-light a
    physical deletion of a possibly-live/recoverable asset."""
    if asset is None or asset.pk is None:
        return False
    try:
        if _referenced_by_section_backgrounds(asset):
            return True
        if _referenced_by_recovery_snapshots(asset):
            return True
        return False
    except Exception:
        # Conservative: an error or ambiguity must NOT be read as
        # "unreferenced" — that would risk deleting a live/recoverable asset.
        return True
