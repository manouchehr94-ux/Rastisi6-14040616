# Task 6 — Media Reachability / Retention / Deletion Guard (gap L07 — A05, P0)

Branch: `feature/storefront-lifecycle-safety-phase2` · baseline HEAD `237064b`
Python: `/projects/rastisi5_phase2_venv/bin/python` (3.12.13, Django 5.2.17)

## 1. The defect (A05, present at baseline)

`MediaAsset.is_referenced()` (`apps/content/models.py`) was the single truth
consumed by `content.services.delete_media_asset_if_unreferenced`
(`apps/content/services.py`) to decide whether a physical media file may be
deleted. At baseline it ORed **only** the five direct FK placement reverse
relations (`hero_placements`, `banner_desktop_placements`,
`banner_mobile_placements`, `hero_mobile_placements`, `story_placements`).

It was BLIND to two additional live reference classes from the media-reference
taxonomy (inventory §5):

- **Class #2 — JSON background:**
  `StorefrontSection.settings["background"]["media_asset_id"]` (written by
  `views._extract_background_raw`, rendered by
  `content.services.resolve_background_media_url`). An asset used only as a
  section background was reported unreferenced → deletable while still shown.
- **Class #4 — recovery snapshot:** an asset id captured inside
  `StorefrontEditHistoryEntry.before_state`/`after_state`, or a version's
  `StorefrontLayoutVersion.template_baseline_snapshot`. Such an asset is still
  recoverable (Undo/Redo/restore/reset-to-baseline) yet was reported
  unreferenced → deletable, breaking a recoverable state.

## 2. RED proof (baseline, before the fix)

`/projects/rastisi5_phase2_venv/bin/python manage.py test apps.content.tests.test_phase2_media_reachability -v2`

5 desired-invariant assertions FAILED for exactly the right reason
(`is_referenced()` / the deletion gate returning the unsafe value), while the
preservation guard passed:

```
FAIL: test_json_only_referenced_asset_on_draft_is_reachable
  AssertionError: False is not true            (asset.is_referenced())
FAIL: test_json_only_referenced_asset_on_published_is_reachable
  AssertionError: False is not true            (asset.is_referenced())
FAIL: test_edit_history_snapshot_only_referenced_asset_is_reachable
  AssertionError: False is not true            (asset.is_referenced())
FAIL: test_template_baseline_snapshot_only_referenced_asset_is_reachable
  AssertionError: False is not true            (asset.is_referenced())
FAIL: test_gate_must_not_delete_json_only_referenced_asset
  AssertionError: True is not false            (gate returned "deleted")
----------------------------------------------------------------------
Ran 6 tests in 0.210s
FAILED (failures=5)
```

`test_asset_with_no_references_is_not_reachable` (preservation guard) was GREEN
at baseline and stays GREEN after the fix.

## 3. The extended-check design

### What classes it now sees

`MediaAsset.is_referenced()` now considers an asset referenced if ANY of:

- **(a)** any of the 5 existing FK placement relations — **unchanged**, checked
  FIRST and short-circuits `True` (cheap, preserves existing behavior).
- **(b)** any `StorefrontSection.settings["background"]["media_asset_id"] ==
  asset.pk` across ALL of the store's Draft/Published/Archived version section
  settings (Class #2).
- **(c)** any `StorefrontEditHistoryEntry.before_state`/`after_state` (for the
  store's drafts) whose payload references the asset id (Class #4).
- **(d)** any version's `template_baseline_snapshot` (for the store)
  referencing the asset id (Class #4).

The FK check remains first and short-circuits, so the common path is unchanged
and the extra scans run only when no FK placement exists.

### Where the code lives

- `apps/content/models.py` — `MediaAsset.is_referenced` extended ONLY: FK check
  first (short-circuit `True`), then delegate to the helper. **No model field
  added or altered** — this is a read-time query change, not a schema change.
  `makemigrations --check` stays clean (see §6).
- `apps/content/media_reachability.py` — NEW small helper module holding the
  JSON/snapshot scans so `is_referenced` stays clean.
- `apps/content/services.py` — **unchanged.**
  `delete_media_asset_if_unreferenced` already is the single deletion gate that
  consumes `asset.is_referenced()` and performs physical file deletion on
  `transaction.on_commit`; it now transparently benefits from the extended
  check. No new orphan-cleanup job / command / signal / TTL was introduced —
  deletion stays triggered ONLY by the existing explicit product flow.

### Tenant-scoping (do NOT full-table-scan)

The ownership chain is `Store → StorefrontLayout (1:1) →
StorefrontLayoutVersion → StorefrontPage → StorefrontSection` (there is no
direct `store` FK on the version; store is reached via `version.layout.store`).
Every scan query is bounded to the asset's OWN store (`asset.store`):

- Backgrounds: `StorefrontSection.objects.filter(page__version__layout__store=asset.store)`
- Edit history: `StorefrontEditHistoryEntry.objects.filter(draft_version__layout__store=asset.store)`
- Baseline snapshots: `StorefrontLayoutVersion.objects.filter(layout__store=asset.store)`

No query scans across stores. Cross-store isolation is proven by tests (§5).

### Fail-closed / conservative

`is_reachable_via_json_or_snapshots` wraps the JSON/snapshot scans in
`try/except Exception` and returns `True` (REFERENCED) on any unexpected error
or ambiguity — an error must never be read as "unreferenced", because that
would risk deleting a live/recoverable asset.

### How the id is matched (not "any integer anywhere")

Matching is restricted to the KNOWN media-id key names, discovered from the
production write/serialize paths:

- `media_asset_id` — section background JSON (`views._extract_background_raw`,
  `section_registry`, `resolve_background_media_url`).
- `desktop_asset_id` / `mobile_asset_id` / `image_asset_id` — serialized
  Hero/Banner/Story placement fields (`layout_service._ASSET_FK_FIELDS`),
  which is exactly how these appear inside history/baseline snapshots.

`_payload_references_asset` recursively walks the JSON and only treats the
asset id as present when it is the VALUE under one of those keys (ints or
numeric strings; booleans excluded). An unrelated integer that merely equals
the id under a non-media key (e.g. `order`, `destination_product_id`) does NOT
match — proven by `test_matching_integer_under_unrelated_key_does_not_reference`.

### Performance bounded

Store-scoped querysets only; the store's section settings / history states /
baseline snapshots are streamed with `.iterator()` and scanned in Python,
bounded to the asset's store.

## 4. Cross-store isolation proof

Added `CrossStoreIsolationReachabilityTests`:

- `test_other_store_json_background_does_not_reference_this_asset` — store B's
  section background JSON reusing store A's asset id does NOT make store A's
  asset referenced.
- `test_other_store_recovery_snapshot_does_not_reference_this_asset` — same for
  store B's edit-history + baseline snapshot.
- `test_same_store_snapshot_still_references_after_isolation_setup` — control:
  within the OWN store the snapshot reference IS seen, proving the isolation is
  genuine tenant scoping, not a check that never matches.

## 5. GREEN proof (after the fix)

`apps.content.tests.test_phase2_media_reachability` — 10/10 GREEN:

```
Ran 10 tests in 0.325s
OK
```

Covering: the 5 previously-RED cases, the preservation guard
(`test_asset_with_no_references_is_not_reachable`), 3 cross-store isolation
cases, and the unrelated-integer over-reach guard.

Full verification suite (media modules):

`... test apps.storefront_builder.tests.test_media_asset_lifecycle
apps.storefront_builder.tests.test_media_write_path
apps.storefront_builder.tests.test_media_views
apps.storefront_builder.tests.test_g22_preview_media_render_consistency -v2`

```
Ran 55 tests in 16.730s
OK
```

(Note: `test_media_asset_lifecycle`, `test_media_write_path`, `test_media_views`
and `test_g22_...` physically live under `apps.storefront_builder.tests`, not
`apps.content.tests`.)

`test_media_asset_lifecycle.test_deletes_asset_with_zero_references` remains
GREEN — a genuinely unreachable asset (no FK, no JSON, no snapshot) is STILL
deletable. No over-reach.

## 6. `check` + `makemigrations --check` (critical)

```
$ manage.py check
System check identified no issues (0 silenced).

$ manage.py makemigrations --check --dry-run
No changes detected            (exit 0)
```

No schema change — A05 was closed as a read-time query change.

## 7. Diff surface

```
$ git diff --check
(no whitespace errors)

$ git diff --name-only
apps/content/models.py
apps/content/tests/test_phase2_media_reachability.py

(untracked, staged for this commit)
apps/content/media_reachability.py
docs/qa_evidence/storefront_appearance_convergence/phase2/task6_media_reachability.md
```

`apps/content/services.py` is unchanged. No forbidden file
(business-domain/renderer/appearance-authority) touched. `_sdd_ledger.md` is
deliberately NOT staged.
