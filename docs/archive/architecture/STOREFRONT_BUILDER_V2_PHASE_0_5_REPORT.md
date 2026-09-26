# Storefront Builder V2 — Phase 0.5 (Correctness Lock) Implementation Report

**Branch:** `claude/family-visual-fidelity-fix`
**Base commit for this phase:** `6e0c496cab6852d53dc791695f517651b5e4f0a7`
**Status:** Implemented, **NOT executed against a live Django runtime** in this sandbox. Awaiting the owner's local test run before this phase is considered verified.

This phase implements only the "Correctness Lock" scope explicitly approved by the owner: stable section identity, a minimal `MediaAsset` model, evolving `HeroSlide`/`PromotionalBanner`/`StoryRailItem` into placements that reference it, a corrected version-clone algorithm, safe deletion, and regression tests. **Phase 1 (Universal Page Architecture / `StorefrontPage`) was explicitly NOT started**, per the owner's instruction.

---

## 0. Evidence-level note

Per the owner's evidence-language correction, this report uses `SOURCE_ONLY`, `SOURCE_WITH_TEST_COVERAGE`, `RUNTIME_VERIFIED`, `BROWSER_VERIFIED`. **Everything in this report is `SOURCE_ONLY` or `SOURCE_WITH_TEST_COVERAGE`** (code written and read carefully; tests written and read carefully, their assertions traced by hand against the implementation) — nothing was executed in this sandbox (still no Django install, still `network_mode=INTEGRATIONS_ONLY`, re-confirmed at the start of this session). The one exception, called out explicitly:

**The original media-clone bug itself is now `RUNTIME_VERIFIED`** — not by this session, but by the owner, who reproduced it against the real local database (`kianstock-qa`, Published v21 / Draft v22, `HeroSlide` id=12/13 both still pointing at `section_id=158` belonging to the archived v20). This report treats that specific finding as `RUNTIME_VERIFIED` on the owner's authority, exactly as instructed. **The fix implemented in this phase is NOT marked `RUNTIME_VERIFIED`** — it is `SOURCE_ONLY`/`SOURCE_WITH_TEST_COVERAGE` until the owner runs the tests below locally and reports the result.

---

## 1. Files changed

### Models
- `apps/storefront_builder/models.py` — added `StorefrontSection.stable_id` (UUIDField) + `UniqueConstraint(version, stable_id)`.
- `apps/content/models.py` — added `MediaAsset` model; added `desktop_asset`/`mobile_asset` FKs to `HeroSlide` and `PromotionalBanner`; added `image_asset` FK to `StoryRailItem`; added `_validate_asset_store_ownership()` cross-store rejection to `HeroSlide.clean()`/`PromotionalBanner.clean()`; added a `clean()` method to `StoryRailItem` with the same cross-store check (it had none before).

### Services
- `apps/storefront_builder/services/layout_service.py` — added `_clone_section_scoped_media()` (new function) and rewrote `_clone_version_content()` to (a) preserve `stable_id` on cloned sections, and (b) clone section-scoped media placements onto the new sections via the new function, without ever mutating the source rows. `get_or_create_draft`, `restore_version` (and transitively `apply_industry_layout`, which shares `_clone_version_content`) all inherit the fix automatically since they all call this one function.
- `apps/content/services.py` — added `delete_media_asset_if_unreferenced()`, the explicit (not signal-based) asset cleanup service.

### Views
- `apps/storefront_builder/views.py` — `storefront_section_duplicate` now also duplicates section-scoped media placements via `_clone_section_scoped_media`, and relies on `stable_id`'s default (`uuid.uuid4`) to give the duplicate a new logical identity (no code needed to force this — simply not overriding it is correct).
- `apps/storefront_builder/media_views.py` — `storefront_section_media_form` now creates/updates `MediaAsset` rows via a new `_sync_asset_references()` helper whenever a file field actually changes (not on every save); `storefront_section_media_delete` now calls `delete_media_asset_if_unreferenced()` instead of unconditionally deleting the physical file.

### Migrations
See §2 below for the full list and rationale.

### Tests (all new; see §10 for execution status)
- `apps/storefront_builder/tests/test_stable_section_identity.py`
- `apps/storefront_builder/tests/test_media_asset_lifecycle.py`
- `apps/storefront_builder/tests/test_media_write_path.py`

### Documentation
- This file (new).
- No other architecture document was modified in this phase — the five documents produced in the prior two checkpoints already correctly describe the target design this phase implements; nothing in them needed correcting as a result of writing the actual code.

---

## 2. Migrations added

Four migrations, deliberately kept small and single-purpose (owner's explicit instruction: "do not combine unrelated schema changes"):

| # | App | File | Purpose | Data touched |
|---|---|---|---|---|
| 1 | `content` | `0019_mediaasset.py` | `CreateModel(MediaAsset)` | None — new, empty table |
| 2 | `content` | `0020_placement_asset_fks.py` | `AddField` (nullable) — `desktop_asset`/`mobile_asset` on `HeroSlide`/`PromotionalBanner`, `image_asset` on `StoryRailItem`, all `on_delete=PROTECT` | None — every new field defaults to `NULL` |
| 3 | `content` | `0021_backfill_placement_assets.py` | Data migration (`RunPython`) — for every existing placement row with a stored legacy image but no asset FK yet, create a `MediaAsset` row pointing at the *same* storage path and set the FK | Creates new `MediaAsset` rows; does **not** touch any existing `desktop_image`/`mobile_image`/`image` field |
| 4 | `storefront_builder` | `0004_storefrontsection_stable_id.py` | `AddField` (temporarily nullable) → `RunPython` backfill (fresh UUID per existing row) → `AlterField` (not-null) → `AddConstraint` | Every existing `StorefrontSection` row gets a freshly generated, distinct `stable_id` |

**Migration dependency graph:** `0019 → 0020 → 0021` (content app, linear); `storefront_builder/0004` depends only on `storefront_builder/0003` (independent of the content-app chain, since `stable_id` doesn't touch media at all). No cross-app dependency was introduced between these two chains — they can be applied in either relative order.

**Reverse migrations:** every migration has a safe, data-preserving reverse. `0021`'s reverse clears FK fields but never deletes the `MediaAsset` rows it created (conservative — "prefer leaving an orphan asset over deleting a file that might still be referenced," per the owner's own Part 8 instruction, applied here too even though this is a migration, not a live delete path). `0004`'s reverse is intentionally a no-op for the backfill step (there is no safe/meaningful way to "un-backfill" a stable identity, and no forward-compatibility reason to ever need to).

**No legacy field was dropped.** `desktop_image`/`mobile_image`/`image` on the three placement models are completely untouched — still fully functional, still the field the render/write path falls back to whenever the corresponding asset FK is `NULL` (i.e., for any row that predates this phase and has never been re-saved through the updated write path).

---

## 3. Final MediaAsset schema

```python
class MediaAsset(TimeStampedModel):
    store = models.ForeignKey("stores.Store", on_delete=models.CASCADE, related_name="media_assets")
    image = models.ImageField(upload_to="media-assets/", validators=[validate_image_size, validate_image_content])

    def is_referenced(self) -> bool:
        # True if ANY placement (Hero desktop/mobile, Banner desktop/mobile,
        # StoryRail) across ANY version still points at this row.
```

Deliberately minimal, exactly as instructed ("do not add unnecessary metadata simply because it might be useful later"). `created_at`/`updated_at` come from `TimeStampedModel` (the same base every other content model uses) — no `created_by` field was added in the end (the original draft of this model had one; removed once it became clear nothing in this phase's scope needed it, and adding it back later is a trivial additive migration if a future phase does).

---

## 4. Final placement FK changes

| Model | New fields | `on_delete` | Legacy field kept? |
|---|---|---|---|
| `HeroSlide` | `desktop_asset`, `mobile_asset` → `MediaAsset` | `PROTECT` | Yes — `desktop_image`, `mobile_image` unchanged |
| `PromotionalBanner` | `desktop_asset`, `mobile_asset` → `MediaAsset` | `PROTECT` | Yes — `desktop_image`, `mobile_image` unchanged |
| `StoryRailItem` | `image_asset` → `MediaAsset` | `PROTECT` | Yes — `image` unchanged |

`on_delete=PROTECT` (not `SET_NULL`, not `CASCADE`) was chosen deliberately: a `MediaAsset` that is still referenced by at least one placement must be **structurally impossible** to delete via ORM cascade, not just procedurally discouraged. The only way to remove a `MediaAsset` row is the explicit `delete_media_asset_if_unreferenced()` service function, which checks `is_referenced()` first and does nothing if the check fails. This means a stray `MediaAsset.objects.filter(...).delete()` anywhere in future code would raise `ProtectedError` rather than silently destroying a file another version still needs — the safety is enforced at the schema level, not just the service level.

Cross-store reference safety: `HeroSlide.clean()`/`PromotionalBanner.clean()`/`StoryRailItem.clean()` all now reject (raise `ValidationError`) a placement whose `store` doesn't match its asset's `store` — mirroring the existing `MerchantCollectionItem.clean()` pattern for cross-store product rejection.

---

## 5. Stable_id implementation

```python
class StorefrontSection(TimeStampedModel):
    ...
    stable_id = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["version", "stable_id"], name="storefront_section_unique_stable_id_per_version"),
        ]
```

- **Scope:** `(version, stable_id)` — exactly as the owner specified ("Because StorefrontSection still belongs directly to StorefrontLayoutVersion during Phase 0.5, use the safest current-version-scoped uniqueness constraint"). Not global, not scoped to a nonexistent `page`. Phase 1 can migrate this constraint to `(page, stable_id)` once `StorefrontPage` exists, per the owner's own note that this is expected.
- **Clone preservation:** `_clone_version_content()` now passes `stable_id=s.stable_id` explicitly when constructing each cloned `StorefrontSection` — the same logical section keeps the same `stable_id` across Published → Draft (and Restore).
- **Duplicate divergence:** `storefront_section_duplicate` deliberately does **not** pass `stable_id` when creating the new row — the field's own `default=uuid.uuid4` generates a fresh one automatically. This is the one place clone and duplicate diverge, exactly as required.
- **Backfill:** migration `0004` assigns every pre-existing section row a fresh, distinct UUID (no attempt to infer historical correspondence across already-existing Draft/Published pairs — there is none to infer, since the field didn't exist before).

---

## 6. Clone algorithm — final behavior

`layout_service._clone_version_content(source, target)`:

1. Copies `header_config`/`footer_config`/`appearance_config` (unchanged from before).
2. Builds the list of cloned `StorefrontSection` rows, **now including `stable_id=s.stable_id`** for each.
3. `bulk_create()`s them.
4. Re-reads the newly created rows from the target version, builds a `{stable_id: section}` map (the only reliable correspondence key — not position, not `section_key`, since multiple sections of the same type can coexist).
5. For every source section, looks up its clone via that map and calls the new `_clone_section_scoped_media(source_section, target_section)`.

`_clone_section_scoped_media(source_section, target_section)`:

- For each of the three placement models (`HeroSlide`/`PromotionalBanner`/`StoryRailItem`), reads every row where `section == source_section`.
- For each such row, builds a **new** row (never updates the source row) copying every content field (title, subtitle/description, button label/visibility, destination, active state, display order) **and** the asset FK field(s) verbatim (same `MediaAsset` id — no new asset created, no file bytes copied).
- Rows that have **no** asset FK set at all (i.e., placements that predate this phase's write-path change and were never re-saved through it) are silently skipped during clone — they simply don't appear on the new version, exactly the same limitation that existed for *every* section-scoped placement before this fix (not a regression; see §11 "Known remaining limitations").
- `bulk_create()`s the clones.

This directly implements the exact 9-step algorithm the owner specified in Part 6 of the task, and the worked example (`MediaAsset #55` referenced independently by a Published placement and a Draft placement) is now literally what the code does — verified by hand-tracing the code against that example, not by execution.

**`discard_draft`, `restore_version`, `apply_industry_layout`:** none of these needed direct changes — `discard_draft` still just deletes the Draft version row (CASCADE to its own sections and *their* placements only, never touching a Published section's placements, since they were never moved into the Draft in the first place). `restore_version`/`apply_industry_layout` both call the same fixed `_clone_version_content`, so they inherit the fix automatically.

---

## 7. Duplicate-section behavior — final

`storefront_section_duplicate`:
1. Creates the new `StorefrontSection` row (new `stable_id`, via the field default).
2. Calls `_clone_section_scoped_media(section, new_section)` — the same function used by version-cloning, reused rather than reimplemented.
3. Result: the duplicate has its own placement rows, pointing at the **same** `MediaAsset`s as the original, with content fields copied independently. Editing the duplicate's placement afterward (title, destination, etc.) never touches the original's placement row — this was already true for `settings` before this phase (a pre-existing, tested guarantee) and is now equally true for section-scoped media.

---

## 8. Deletion / storage cleanup policy — final

- **Deleting a placement** (via `storefront_section_media_delete`): the placement row is deleted; for each asset it referenced, `delete_media_asset_if_unreferenced(asset)` is called — the asset (and its physical file, via the pre-existing `transaction.on_commit` + `storage.exists()` pattern) is only removed if `is_referenced()` returns `False` for it. For placements with no asset FK (legacy rows that predate this phase's write path), the exact previous behavior is preserved: the legacy file is deleted directly by name.
- **Deleting a Draft** (`discard_draft`): unchanged mechanism (delete the version row, CASCADE to its sections, CASCADE to *their* placements) — but now, because placements are never re-homed into the Draft in the first place (per the fix in §6), this CASCADE can never reach a Published placement, and the `MediaAsset` rows those Draft placements referenced survive (protected by `on_delete=PROTECT`) as long as *any* other placement — including the corresponding Published one — still needs them.
- **No Django signal was added.** Per the owner's explicit instruction ("avoid fragile Django signals that delete files blindly on row deletion; prefer an explicit asset cleanup service"), cleanup is only ever triggered by an explicit call to `delete_media_asset_if_unreferenced()` at each call site that deletes a placement — currently just `storefront_section_media_delete`. If a future call site deletes a placement without calling this function, the asset is simply never cleaned up (an orphan, not a broken reference) — this is the intentionally conservative failure mode: **"prefer leaving an orphan physical file temporarily over deleting a still-live file. Correctness > storage reclamation."** (documented here per the owner's explicit instruction to document this tradeoff).

---

## 9. Tests added

Full list (three new files, ~40 individual test methods total):

**`test_stable_section_identity.py`** (Part 11.A):
- `StableIdCloneTests` — stable_id survives Published→Draft clone, survives Restore, multiple sections keep distinct ids.
- `StableIdDuplicateTests` — duplicate gets a *different* stable_id.
- `StableIdUniquenessConstraintTests` — same stable_id allowed across two different versions; rejected twice within the same version (`IntegrityError`).

**`test_media_asset_lifecycle.py`** (Parts 11.B–K):
- `MediaAssetModelTests` — `is_referenced()` sanity.
- `PublishedDraftMediaIndependenceTests` — the core Owner Decision 4 guarantee (Part 11.B): Published placement untouched, Draft gets a separate row, both share the asset; editing Draft never mutates Published.
- `HeroSlideCloneTests` / `PromotionalBannerCloneTests` / `StoryRailItemCloneTests` (Parts 11.C/D/E) — direct reproduction of the exact bug class the owner found on `kianstock-qa`, now asserting the fixed behavior (both versions have the media, as separate rows, never the same PK).
- `DraftDiscardMediaSafetyTests` (Part 11.F) — discard deletes only the Draft placement; Published placement, asset, and rendered output are all still intact afterward (asserted at the render layer via `build_render_items`, not just the DB layer).
- `RestoreMediaCloneTests` (Part 11.G) — restoring an old version clones its media correctly and does not touch the version that was current at the time of restore.
- `ApplyIndustryLayoutMediaSafetyTests` (Part 11.H) — applying an industry layout over an existing Draft does not damage Published media.
- `CrossStoreMediaAssetSafetyTests` (Part 11.I) — a placement cannot `full_clean()` successfully if its asset belongs to a different store.
- `LegacyGlobalMediaFallbackTests` (Part 11.J) — `section=NULL` global slides still render exactly as before, completely independent of this phase's changes.
- `SectionDuplicateMediaTests` (Part 11.K) — duplicating a media-capable section duplicates its placements (new stable_id, separate rows, shared asset, independent edits).
- `DeleteMediaAssetIfUnreferencedServiceTests` — the cleanup service function itself, in isolation.

**`test_media_write_path.py`** (Part 5 + Part 8, from the merchant-facing form/view angle):
- `MediaWritePathAssetCreationTests` — adding a slide/banner through the real form creates a correctly store-scoped asset; editing only the title does not create a spurious new asset; replacing an image creates a new asset without deleting the old one if it's still referenced elsewhere.
- `MediaDeleteReferenceSafetyTests` — deleting a slide through the real view deletes its now-unreferenced asset, but not one still shared with another placement.

---

## 10. Tests actually executed vs. not executed

**None of the above tests, and none of the pre-existing 220-test baseline, were executed in this sandbox.** Confirmed at the start of this session (re-checked, unchanged from the prior two checkpoints): no Django installation exists, `pip install django` still fails with a `403 Forbidden` from the sandboxed PyPI proxy (`network_mode=INTEGRATIONS_ONLY`), and no cached Django wheel exists anywhere on disk.

Every test above was written carefully and then read back line-by-line against the actual implementation it exercises, to maximize confidence without execution — but this is explicitly **not** a substitute for running them, and this report does not claim it is. Per the owner's explicit instruction: **"do not claim tests passed; inspect/write them carefully; report them as NOT EXECUTED."** This is that report.

---

## 11. Known remaining limitations (documented, not silently left implicit)

1. **Legacy section-scoped placements with no asset FK are skipped during clone.** The clone code (`_clone_section_scoped_media`) explicitly skips any placement row with no asset FK set, rather than cloning it anyway with just its legacy image field. In practice, migration `0021` backfills an asset FK for every existing row that has a `store_id` set, so after that migration runs, essentially every real, currently-rendering placement should have an asset FK and clone correctly. The only rows that remain without one are `store_id IS NULL` rows (pre-store-scoping legacy rows that never render on any storefront anyway) — so this skip-path is a theoretical/edge-case safeguard, not a practical gap, but it is documented here for completeness since it is a real, deliberate limitation of the clone code as written.
2. **`story-items` (StoryRailItem) media cannot be created/edited through the generic media form at all** — this is a pre-existing limitation (the shared `storefront_section_media_form` hardcodes `desktop_image`/`mobile_image`, which `StoryRailItem` doesn't have) that predates Phase 0.5 and was not in scope to fix. The backfill migration still correctly gives existing `StoryRailItem` rows an `image_asset`, and the delete path (`storefront_section_media_delete`) correctly handles cleanup for it via `delete_asset_fields`, but there is no live *creation/edit* path that populates `image_asset` for new `StoryRailItem` rows yet (new rows created via the management-command seed scripts, or a future dedicated form, would need the same `_sync_asset_references`-style treatment).
3. **No storage-file byte-level test was written** — the tests confirm `MediaAsset`/placement row-level correctness and `storage.exists()`/`storage.delete()` call patterns are wired correctly (by tracing the code), but none of them upload a real file to a real storage backend and verify the byte content survives — this would require a runtime environment this sandbox doesn't have.
4. **`ProtectedError` is never explicitly caught anywhere** — if some future code path attempts a raw `MediaAsset.objects.filter(...).delete()` bypassing the service function, Django will raise `ProtectedError` (by design, per §4) rather than silently corrupting data — but no user-facing error message has been written for that scenario, since no code path in this phase can trigger it. This is intentional (fail loudly at the ORM level is the safety net, not a UX concern for Phase 0.5), but noted for Phase 1 planning.

---

## 12. Exact Phase 1 prerequisites — are they satisfied?

Reviewing the Implementation Plan's own list of what Phase 1 (Universal Page Architecture) needs:

- **Stable section identity** — ✅ implemented this phase, exactly as designed (`(version, stable_id)` scope, ready to be re-scoped to `(page, stable_id)` once `StorefrontPage` exists).
- **Draft/Published media independence** — ✅ implemented this phase.
- **Safe physical media ownership** — ✅ implemented this phase (`MediaAsset` + `PROTECT`).
- **Correct clone lifecycle** — ✅ implemented this phase (media now follows the section it belongs to, correctly, without ever touching the source).
- **Safe deletion lifecycle** — ✅ implemented this phase (explicit service function, reference-counted).
- **Shared storefront shell consistency** — ❌ **not started this phase** (out of scope for Phase 0.5 per the owner's own instruction: "Phase 0.5 is correctness infrastructure. Phase 1 is Universal Page Architecture." — the route/shell wiring work described in the Implementation Plan's Phase 1 scope remains entirely undone).
- **Runtime verification** — ❌ **not satisfied yet** — this entire phase's correctness rests on `SOURCE_ONLY`/`SOURCE_WITH_TEST_COVERAGE` evidence. The owner must run the tests in §9 locally (alongside the pre-existing 220-test baseline) before this phase can be considered verified, let alone before Phase 1 begins.

**Conclusion: Phase 1 prerequisites are partially satisfied** — the four correctness-lock objectives that were this phase's actual scope are implemented, but they are unverified pending the owner's local test run, and the shell-consistency prerequisite was correctly left untouched as explicitly out of scope for Phase 0.5.

---

## 13. Exact local commands the owner should run to validate this phase

```bash
python manage.py check

python manage.py makemigrations --check --dry-run
# ^ should report "No changes detected" — confirms the four migrations
#   written by hand above are the complete, correct set for the model
#   changes made in this phase (no missing migration).

python manage.py test \
  apps.storefront_builder.tests.test_layout_service \
  apps.storefront_builder.tests.test_render_service \
  apps.storefront_builder.tests.test_media_views \
  apps.storefront_builder.tests.test_page_shell \
  apps.storefront_builder.tests.test_public_homepage_integration \
  apps.storefront_builder.tests.test_views \
  --verbosity 2
# ^ the exact pre-existing baseline suite (220 pass / 1 skip / 0 fail / 0
#   error before this phase) — must remain fully green after this phase's
#   changes, with the same 220/1/0/0 shape (or better, if any previously
#   skipped test now runs).

python manage.py test \
  apps.storefront_builder.tests.test_stable_section_identity \
  apps.storefront_builder.tests.test_media_asset_lifecycle \
  apps.storefront_builder.tests.test_media_write_path \
  --verbosity 2
# ^ the new Phase 0.5 test suite. All should pass.

python manage.py test apps.content --verbosity 2
# ^ full content-app suite, to confirm the new MediaAsset model, the new
#   clean() validation on HeroSlide/PromotionalBanner/StoryRailItem, and
#   the migration graph did not regress any existing content-app test
#   (e.g. apps/content/tests/test_migration_graph.py, test_homepage_media.py).

python manage.py test apps.storefront_builder --verbosity 2
# ^ full storefront_builder-app suite (all pre-existing family/section/
#   bootstrap/appearance tests), to confirm nothing outside this phase's
#   direct scope regressed.
```

If the owner also wants to specifically re-reproduce and then re-verify the exact `kianstock-qa` scenario locally (Published v21 / Draft v22, `HeroSlide` id=12/13), the safest way is via a fresh test store in a throwaway shell session (not the production `kianstock-qa` data itself), following the same shape as `HeroSlideCloneTests.test_published_scoped_hero_slide_exists_in_both_versions_as_separate_rows` in `test_media_asset_lifecycle.py`.

---

## 13.5. Repair addendum — local validation failure and fix (post-initial-implementation)

The owner ran local validation on Django 5.2.16 + SQLite and found this phase's initial commit (`13f5adf`) did **not** pass. This addendum documents the failure and the fix, applied in-place to the existing migrations (no new `0005`/`0022` migration files were created).

### 13.5.1 What failed

`python manage.py migrate` failed on `storefront_builder.0004_storefrontsection_stable_id` with:

```
django.db.utils.IntegrityError: UNIQUE constraint failed:
new__storefront_builder_storefrontsection.version_id,
new__storefront_builder_storefrontsection.stable_id
```

`python manage.py makemigrations --check --dry-run` also reported drift, proposing two new migrations (`content/0022_alter_heroslide_desktop_asset.py`, `storefront_builder/0005_alter_storefrontsection_stable_id.py`) — these were correctly treated as diagnostic-only symptoms, not accepted as the fix.

### 13.5.2 Root cause of the `0004` `IntegrityError`

The original `0004` migration's `AddField` step declared `stable_id` as nullable **but still carrying `default=uuid.uuid4`**. On SQLite, Django implements `AddField` (and most other ALTERs) via a full table-rebuild strategy (`CREATE TABLE new__..., INSERT INTO new__... SELECT ... FROM old, DROP old, RENAME new__ TO old`). During that rebuild, a column's callable default can be evaluated and applied to every pre-existing row as part of the `INSERT ... SELECT`, rather than genuinely leaving them `NULL` for a later data migration to fill in per-row. In practice this meant every pre-existing `StorefrontSection` row ended up with the **same** (non-distinct) `stable_id` value immediately after `AddField`, not `NULL`.

The subsequent `RunPython` backfill step (`backfill_stable_ids`) was never itself wrong — its `.filter(stable_id__isnull=True)` genuinely assigns a fresh, distinct UUID to every row it matches. But because `AddField` had already given every row a non-null (collided) value, the filter matched **zero** rows, so nothing was corrected. The final `AddConstraint(UniqueConstraint(version, stable_id))` then failed for the first version that had more than one pre-existing section, because they all shared the one leaked-through value.

### 13.5.3 Fix applied to `0004` (in-place, no new migration)

`AddField`'s field declaration now has **no `default=` at all** (only `null=True`, matching the owner's required sequence exactly). This forces every pre-existing row to genuinely land on `NULL` after `AddField`, so the existing, already-correct `RunPython` backfill loop is the only thing that ever assigns a value to a pre-existing row — guaranteeing distinctness before `AlterField`/`AddConstraint` run. The final `AlterField`'s field declaration (which restores `default=uuid.uuid4` for future new rows and sets `null=False`) is otherwise unchanged in shape, only corrected to be byte-identical to the model (see 13.5.4).

Verified (`SOURCE_ONLY`, by direct code inspection — not executed): the operation sequence is now `AddField(no default, nullable) → RunPython(per-row backfill) → AlterField(default + not-null) → AddConstraint`, exactly the four-step sequence the owner specified.

### 13.5.4 Migration-state drift: `StorefrontSection.stable_id`

Separately from the `IntegrityError`, `makemigrations --check` found that `0004`'s final `AlterField`'s `help_text` did not exactly match the model's current `help_text` — the model's help_text had been extended (to also explain the section-scoped-media clone rationale) after `0004` was originally written, but the migration's recorded final state still had the shorter, earlier text. This is a pure migration-state/metadata drift (Django tracks the full field declaration, including `help_text`, as part of migration state for consistency checking — it does not correspond to any different column type or constraint). **Confirmed via direct byte-for-byte string comparison of the two help_text values** (543 characters each once corrected) that after this fix, the migration's final `AlterField` field declaration is identical to the model's live declaration.

### 13.5.5 Migration-state drift: `HeroSlide.desktop_asset`

`makemigrations --check` also found drift specifically on `HeroSlide.desktop_asset` (and no other field in `0020`). Root cause, confirmed by direct byte-for-byte comparison: the model's `help_text` wraps `on_delete=PROTECT` in RST-style double backticks (`` ``on_delete=PROTECT`` ``); the migration's recorded `help_text` for this one field had the same sentence **without** the backticks. Every other field added by `0020` (`HeroSlide.mobile_asset`, `PromotionalBanner.desktop_asset`/`mobile_asset`, `StoryRailItem.image_asset`) was checked the same way and found to already match exactly — confirmed there is no other drift in this migration.

**This is confirmed to be pure migration-state/docstring metadata, not a real database-schema difference** — it does not change the column type, nullability, `on_delete` behavior, or any constraint. Per the task's explicit instruction ("If you find a real schema difference, STOP and report it instead of silently rewriting an already-applied migration"): **no real schema difference was found.** `content.0020` is already applied on the owner's local database as of this repair; correcting only the `help_text` string in place does not require any different physical schema and is safe to apply directly to the already-migrated file, because Django's migration-state consistency check compares the full recorded field declaration (including `help_text`) against the live model, not the database schema itself — the database column is completely unaffected by this specific correction.

### 13.5.6 Encoding check

Per the task's explicit instruction, no Persian text was rewritten based on the PowerShell `Get-Content` mojibake report. Every file touched by this repair (and, for due diligence, every file touched by the original Phase 0.5 commit) was re-verified this session to decode successfully as UTF-8 with no errors — confirming the mojibake the owner observed is a Windows console/`Get-Content` display-encoding artifact, not a source-file corruption. No source file's actual bytes were altered for encoding reasons.

### 13.5.7 New test added for this repair

`apps/storefront_builder/tests/test_stable_id_migration.py` — two test classes:
- `MigrationOperationOrderTests` (`SimpleTestCase`, no DB) — a **static/structural** check that reads `Migration.operations` directly from the `0004` module and asserts: the first operation is `AddField` with no default (the exact regression point), the second is the `RunPython` backfill, the third is `AlterField` with a default and `null=False`, and the fourth (last) is `AddConstraint`. Also inspects the backfill function's source to confirm the `uuid.uuid4()` call happens inside the per-row loop, not once outside it. This is the test that would have caught the original bug without needing to execute a real migration.
- `StableIdConstraintBehaviorTests` (`TestCase`, full DB) — functional confirmation of the end state: new sections get distinct `uuid4` defaults, duplicate `stable_id` within the same version is rejected by the live `UniqueConstraint`, and the same `stable_id` is correctly allowed across two different versions.

A full end-to-end reproduction of the original SQLite table-rebuild bug (via genuinely running `python manage.py migrate` against a pre-`0004` database state) was **not** attempted in a Django `TestCase`, because Django's test framework always runs against the fully-migrated final schema — there is no way to construct the exact broken intermediate state (colliding non-null values before the fix, or genuine per-row NULLs before backfill) through the ORM once the final `NOT NULL` + `UniqueConstraint` are already live, without the database itself rejecting the setup for unrelated reasons. The static operation-order check in `MigrationOperationOrderTests` is the strongest test possible under this sandbox's constraints; **actually running `python manage.py migrate` against a fresh database is the only way to fully prove the fix**, and that is asked of the owner explicitly in §13.5.8 below.

### 13.5.8 Owner commands to re-validate this specific repair

```bash
python manage.py makemigrations --check --dry-run
# ^ must now report "No changes detected" for BOTH apps (content and
#   storefront_builder) — confirms the help_text drift on both
#   HeroSlide.desktop_asset and StorefrontSection.stable_id is fully
#   resolved, with no new migration file needed.

# From the owner's exact current local DB state (content 0019/0020/0021
# applied, storefront_builder 0004 unapplied/failed):
python manage.py migrate storefront_builder 0004
# ^ must now succeed cleanly — this is the definitive proof the
#   SQLite table-rebuild/default-leak bug is fixed. If the owner's local
#   database already has any partially-applied leftover state from the
#   failed attempt (e.g. a lingering new__storefront_builder_storefrontsection
#   table from SQLite's aborted rebuild), it may be necessary to inspect
#   that table manually or restore from a pre-migration backup before
#   retrying — this could not be predicted or repaired from this sandbox
#   since it depends on exactly what SQLite left behind after the failed
#   transaction rolled back (SQLite's ALTER-via-rebuild is normally
#   transactional and self-cleaning on failure, so a plain retry should
#   normally be sufficient, but this is flagged rather than assumed).

python manage.py migrate
# ^ confirm the rest of the migration graph still applies cleanly.

python manage.py test \
  apps.storefront_builder.tests.test_layout_service \
  apps.storefront_builder.tests.test_render_service \
  apps.storefront_builder.tests.test_media_views \
  apps.storefront_builder.tests.test_page_shell \
  apps.storefront_builder.tests.test_public_homepage_integration \
  apps.storefront_builder.tests.test_views \
  --verbosity 2
# ^ the original 220-test baseline — must remain green.

python manage.py test \
  apps.storefront_builder.tests.test_stable_section_identity \
  apps.storefront_builder.tests.test_media_asset_lifecycle \
  apps.storefront_builder.tests.test_media_write_path \
  apps.storefront_builder.tests.test_stable_id_migration \
  --verbosity 2
# ^ the full new Phase 0.5 suite, including this repair's new migration
#   regression test.
```

---

## 14. Summary — what was and was not done

**Done:** stable section identity (Part 1), minimal `MediaAsset` model (Part 2), placements evolved to reference it while keeping legacy fields (Part 3), backward-compatible backfill migration (Part 4), updated write path for create/edit (Part 5), corrected clone algorithm (Part 6), legacy global media left untouched (Part 7), safe explicit deletion service (Part 8), section-duplication now duplicates media correctly (Part 9), regression tests for all of the above (Part 11), migrations kept small and separate (Part 13), this report (Part 14).

**Not done, correctly out of scope:** `StorefrontPage` (Phase 1), the single-screen Builder UX (Phase 2), the Home Block Library refinement (Phase 3), Header/Footer Composer (Phase 4), commerce page composition (Phase 5), Presets (Phase 6), Legacy Migration (Phase 7). No Family was modified. No commerce logic was touched. No public route's shell wiring was changed.

**Implementation is complete for the approved Phase 0.5 scope. It has not been implemented or claimed as implemented for any phase beyond that. Awaiting the owner's local test execution before this phase is considered verified, and awaiting separate explicit approval before Phase 1 begins.**
