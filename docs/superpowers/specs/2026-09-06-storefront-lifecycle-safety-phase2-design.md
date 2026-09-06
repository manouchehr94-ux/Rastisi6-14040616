# RastiSi Storefront Appearance Convergence — Phase 2: Lifecycle & Safety (Architecture Specification)

**Date:** 2026-09-06
**Status:** Architecture specification — implementation-ready (no placeholders)
**Program spec:** `docs/superpowers/specs/2026-09-05-storefront-appearance-convergence-5-phase-design.md`
**Phase-2 baseline (merged Phase-1):** `515518227c09f888972fa6eda756867097358dfb`
**Phase-1 feature HEAD in that merge:** `8cea65e60d4afff40d43f8f14f3773ff5f071da2`
**Approved G2.3 ancestor:** `93c5afea2ee32bef67cfb5923ffdb13bb61d7930`
**Repository:** `manouchehr94-ux/rastisi5`
**Branch:** `feature/storefront-lifecycle-safety-phase2`

---

## 1. Purpose

Phase 1 established ONE canonical Appearance *write authority* (`appearance_authority_service`) and answered **"who owns the write?"**. Phase 2 answers the next question:

> **"Where and under what lifecycle/safety conditions may the canonical Appearance/Builder owner write?"**

Phase 2 converges the **lifecycle & safety contract** around those writes: tenant/authorization boundary, Draft/Published/Archived targeting, base-revision / stale-write protection, atomicity, publication, history, undo/redo/recovery, restore/discard, baseline/reset interactions, lifecycle-safe Template operations, Section/Container structure-lock semantics, and media reachability / retention / deletion safety.

Phase 2 hardens existing systems; it does not rebuild them. The R4 mutation boundary already provides the strong optimistic-concurrency contract — Phase 2 extends an equivalent, explicit lifecycle-safety guarantee to the remaining active Appearance/Builder write paths and closes the confirmed media-reachability gap (A05).

## 2. Phase-1 baseline dependency

Phase 2 assumes and MUST NOT reopen the Phase-1 outcomes (verified in `docs/qa_evidence/storefront_appearance_convergence/phase1/final_gate.md`):

- `appearance_authority_service` is the single Appearance state-transformation layer (`apply_appearance_patch`, `apply_header_variant`, `apply_footer_variant`, `apply_store_appearance_manifest`).
- Legacy views, R4 mutations, and Ready Template Apply already delegate Appearance transformation to it.
- Ready Template Apply persists the **complete** declared typed `store_appearance` manifest (A02 closed); `declared = persisted = effective`.
- Explicit local Section variant precedence (`appearance_overrides.variant_explicit`) is server-derived and historical-safe.

Phase 2 does **not** redesign this authority unless a direct Phase-2 lifecycle defect proves it necessary (in which case: STOP and escalate to Product Owner review).

## 3. Current lifecycle topology (as-is, evidence-based)

`apps/` paths. Line numbers per baseline `5155182`.

**Anchor:** `StorefrontLayout` (`models.py:181-241`) — per-store `OneToOneField`; pointers `draft_version` / `published_version` (SET_NULL); flags `uses_visual_storefront_layout` (gate: public renders visual layout only after first publish), `r4_editor_enabled`.

**Version:** `StorefrontLayoutVersion` (`models.py:244-599`) — `Status = {DRAFT="draft", PUBLISHED="published", ARCHIVED="archived"}`; `edit_revision` (monotonic optimistic-concurrency token, R4-only today); `template_provenance`, `template_baseline_snapshot`; `appearance_config`/`header_config`/`footer_config` (typed manifest lives inside `appearance_config`). Pages (`StorefrontPage`, 6 fixed types) → Sections → Containers/Cells.

**History:** `StorefrontEditHistoryEntry` (`models.py:882-944`) — per-Draft, `sequence`, `before_state`/`after_state`, `is_undone`; deleted on publish; capped at 30 (`edit_history_service._MAX_HISTORY_ENTRIES`).

**Transitions** (`services/layout_service.py`):
- `get_or_create_draft` (718-761, `@atomic`): existing draft returned; else first-ever → `bootstrap_service.apply_bootstrap_content`, otherwise `_clone_version_content(published, draft)` (589-715) — copies appearance/header/footer, provenance, baseline snapshot, sections (preserving `stable_id`/`template_slot_key`), section-scoped media as NEW rows sharing the SAME `MediaAsset` (`_clone_section_scoped_media` 589-634), and containers.
- `publish` (772-815, `@atomic`): ensure containers → delete draft edit history → previous published → ARCHIVED → draft → PUBLISHED, `draft_version=None`, `uses_visual_storefront_layout=True`.
- `discard_draft` (763-770, `@atomic`): null pointer + delete draft.
- `restore_version` (826-851, `@atomic`): clone ANY owned version (archived/published/older) into a NEW DRAFT (`Source.RESTORED`); `CrossStoreVersionError` on foreign version; never auto-publishes.
- `checkpoint_draft_before_replacement` (918-958, `@atomic`): archive the current draft (recoverable via `restore_version`) before destructive full replacement.

**Public vs Preview:** Public reads Published only (`services/page_resolution_service.py`: `_published_layout_queryset` requires `uses_visual_storefront_layout=True AND published_version` — never Draft). Preview reads the active Draft via `get_or_create_draft`.

## 4. Canonical lifecycle ownership

Phase 2 target — **one lifecycle contract, not necessarily one HTTP endpoint** (per program-spec Rule: converge ownership, do not force every path onto the R4 API):

| Concern | Canonical owner (target) |
|---|---|
| Active-Draft resolution + tenant scoping | `layout_service.get_or_create_draft` + the existing scoping helpers (`_lock_active_draft` for R4; `_get_scoped_section/_container/_cell` for legacy) |
| Optimistic concurrency (stale-write) | The `edit_revision` token on the Draft version, checked at the mutation boundary |
| Atomic mutation + revision increment + history | R4 `apply_mutation`; legacy paths gain an equivalent lifecycle-safe wrapper (see §5–§7) |
| Publish / archive transition | `layout_service.publish` (single implementation) |
| Restore / discard / checkpoint | `layout_service.restore_version` / `discard_draft` / `checkpoint_draft_before_replacement` |
| Undo / redo / snapshot | `edit_history_service` (single implementation) |
| Template apply / reset baseline | `preset_service` (single orchestration; already routes Appearance through the authority) |
| Structure lock enforcement | `Section.is_locked` / `Container.is_locked` checks in `section_structure_service` + `container_service` + views (single set of checks) |
| Physical media deletion safety | `content.services.delete_media_asset_if_unreferenced` gated by a **complete** reachability check |

## 5. Mutation safety contract

Every **Appearance/Builder-owned** mutation must satisfy, in this order:

1. **Tenant/authorization:** resolve the store from the request/session; require `staff_required` + `STOREFRONT_LAYOUT_MANAGE` (or R4 gate). Never accept a foreign store's version/section/asset id (already enforced; Phase 2 adds missing negative tests).
2. **Lifecycle target:** write only the **active Draft**. A Published or Archived version is never mutated by an editing path. Live business-domain data (Product/Brand/Collection, ShopSettings) is out of scope and remains domain-owned.
3. **Concurrency:** the mutation is checked against the Draft's current `edit_revision` (or an equivalent guard) so a stale client cannot silently overwrite newer Draft state.
4. **Atomicity:** the mutation runs in one DB transaction; a mid-mutation failure rolls back completely (no partial state).
5. **History/revision coherence:** a successful state-changing mutation records one history entry and advances `edit_revision` exactly once; a semantic no-op does neither.

Phase 2 classifies each existing path (§7) and hardens PARTIAL/MISSING paths toward this contract — **without forcing the R4 HTTP command envelope onto legacy routes** where an equivalent guard is simpler.

## 6. Draft / Published / Archived rules

- **DRAFT** is the only mutable state for Appearance/Builder writes.
- **PUBLISHED** is immutable by editing paths; only `publish` writes it (by pointer swap) and only `restore_version` reads it (to clone into a new Draft).
- **ARCHIVED** is immutable; readable only for recovery/clone via `restore_version`.
- **Transitions (verified, do not add transitions absent from code):**

```text
(no version) --get_or_create_draft(first)--> DRAFT (bootstrap)
PUBLISHED    --get_or_create_draft(clone)--> DRAFT (new, cloned from published)
DRAFT        --publish--------------------> PUBLISHED   (and previous PUBLISHED --> ARCHIVED)
DRAFT        --discard_draft--------------> (deleted)
ANY owned version --restore_version-------> DRAFT (new RESTORED clone; source unchanged)
DRAFT        --checkpoint_before_replace--> ARCHIVED (old) + DRAFT (new active)
```

- Preview reads DRAFT; Public reads PUBLISHED. This boundary is explicit and must be preserved.

## 7. Revision / stale-write policy

**Classification at baseline (evidence in `lifecycle_media_inventory.md`):**

- **STRONG:** R4 `apply_mutation`, `apply_history_command`, `publish_draft` — `select_for_update` lock + `base_revision` compare (`R4StaleRevision`) + atomic + single `edit_revision` increment.
- **PARTIAL:** legacy view mutations — Draft/store-scoped and history-recorded, but **no** `base_revision`/`edit_revision` (last-writer-wins between concurrent legacy tabs, or legacy-vs-R4 on the same Draft).
- **MISSING:** legacy `storefront_publish` (no base_revision, unlike R4 `publish_draft`), legacy `storefront_undo`/`storefront_redo` (direct `edit_history_service`, no guard), preset apply + all reset endpoints, media routes.

**Phase-2 policy — one lifecycle-safe boundary, minimally invasive:**

- The Draft's `edit_revision` is the single optimistic-concurrency token for all Appearance/Builder-owned mutations.
- Legacy state-changing mutations must, at minimum, **advance `edit_revision` on success inside their transaction** so that a concurrent R4 client (which holds a `base_revision`) detects the change and does not silently overwrite it. This is the primary convergence: make `edit_revision` a true Draft-wide monotonic token rather than an R4-only token.
- Where a legacy path can accept a client-supplied base revision without UI/product change, add an optional stale-write check; where it cannot (pure server-form POST with no revision in the form), the minimum guarantee is atomic + `edit_revision` advance + history, and the residual "two legacy tabs racing" risk is documented as an accepted, bounded limitation (it does not corrupt lifecycle state, only last-writer-wins on the Draft — the same class of risk that exists for any un-versioned form).
- Publish through any entry point must go through a single implementation that performs the archive transition atomically; legacy `storefront_publish` must reach the same lifecycle guarantee as R4 `publish_draft` (either by delegating to it or by adding the equivalent lock).

**Non-goal:** Phase 2 does NOT force every legacy route to become an R4 JSON command. The target is one lifecycle *contract* (revision token + atomicity + history), reachable through existing route shapes.

## 8. Transaction / atomicity policy

- Every state-changing Appearance/Builder mutation runs inside `@transaction.atomic` (directly or via its service).
- The transaction boundary is owned by the mutation/lifecycle layer (R4 `apply_mutation`, `layout_service.*`, `preset_service.*`), NOT by `appearance_authority_service` (which remains transaction-free per Phase 1).
- Multi-step operations (config write → manifest persist → snapshot; placement delete → asset reachability check) must be inside one transaction so a failure leaves no partial state.
- Media physical file deletion is deferred to `transaction.on_commit` (already the pattern in `content.services`) so a rolled-back transaction never deletes a file.

## 9. History / recovery semantics

- `edit_history_service` remains the single Undo/Redo authority. `snapshot_draft` already captures `appearance_config` (incl. typed manifest), `template_provenance`, `template_baseline_snapshot`, all sections (incl. media asset ids), and containers/cells — so recovery correctly restores Phase-1 canonical state.
- `record_change` filters no-ops and prunes to 30 entries; `undo`/`redo` flip `is_undone` and call `restore_draft_state`; R4 `apply_history_command` owns the `edit_revision` increment for undo/redo.
- **Phase-2 requirement:** legacy `storefront_undo`/`storefront_redo` must reach the same lifecycle guarantee (atomic + `edit_revision` advance) as R4 `apply_history_command`, so undo/redo through either entry point is revision-coherent.
- Recovery contracts (`edit_history`, `restore_version`, `reset_*_to_baseline`, `apply_baseline_snapshot`, `discard_draft`) are distinct mechanisms with distinct scopes — Phase 2 documents their boundaries and adds tests; it does not merge them.

## 10. Template operation lifecycle semantics

- `preset_service.apply_preset` and the `*_with_checkpoint` wrappers already: validate-then-write, persist the complete manifest via the authority, snapshot the baseline from the manifest-synced state, and (for the merchant-facing wrappers) `checkpoint_draft_before_replacement` first.
- **Phase-2 requirement:** Template Apply / reset entry points that mutate the Draft must be lifecycle-safe — atomic, Draft-only, `edit_revision`-coherent (advance on real change), and refuse to run against a locked page (already: `LockedSectionsPresentError`). No change to Apply *semantics* (replacement/reset), and NO content-preserving Switch (deferred to Phase 3+).

## 11. Structure lock semantics

Approved rule: **structure-lock protects STRUCTURAL operations only** — it is not a Store force-all Appearance lock, not a hidden precedence override, not a business-domain content lock.

Current fields: `StorefrontSection.is_locked` (`models.py:677`), `StorefrontContainer.is_locked` (`models.py:806`).

**Operation matrix (real existing operations only):**

| Operation | Locked section/container: allowed? | Enforcement site |
|---|---|---|
| Section move / reorder | NO | `section_structure_service` (218,238) / `views.storefront_section_move` (1849), `..._reorder` (1815) |
| Section remove | NO | `views.storefront_section_remove` (1564) |
| Block move / remove (within cell) | NO | `views` (1698,1762); `container_service` (830,847) |
| Container settings / layout / move / remove | NO (locked container) | `views` (424,510,537); `container_service` (711,1023) |
| Cell add-section / clear | NO (locked container) | `views` (580,647); `section_structure_service` (132,155) |
| Template apply / baseline reset over a page with a locked section | NO | `preset_service.apply_preset` / `apply_baseline_snapshot` → `LockedSectionsPresentError` |
| Section settings edit (content/appearance) | **YES** | not blocked — lock is structure-only |
| Toggle active / collapse / lock-toggle | **YES** | lock does not block visibility or the lock toggle itself |
| Section duplicate | YES (creates a NEW logical section) | `views.storefront_section_duplicate` (1633) |

**Phase-2 requirement:** verify the lock matrix is complete and consistent across BOTH R4 structure commands (`section_structure_service`) and legacy views, and add missing negative tests. Do not add new UI, new lock types, or content/appearance locking.

## 12. Media reference taxonomy

Primary physical-file model: `MediaAsset` (`apps/content/models.py:385-431`) — `store` FK (CASCADE), one `image` ImageField. Reference classes:

1. **Direct relational (FK):** `HeroSlide.desktop_asset`/`mobile_asset` (`hero_placements`/`hero_mobile_placements`), `PromotionalBanner.desktop_asset`/`mobile_asset` (`banner_desktop_placements`/`banner_mobile_placements`), `StoryRailItem.image_asset` (`story_placements`). Asset FK = `PROTECT`; `section` FK = `CASCADE`. **Seen** by `is_referenced()`.
2. **JSON:** `StorefrontSection.settings["background"]["media_asset_id"]` — written by `views._extract_background_raw` (1066-1084), rendered by `content.services.resolve_background_media_url` (131-156). **NOT seen** by `is_referenced()`.
3. **Version-state:** placements attach to versions via `section→page→version` (Draft/Published/Archived). FK placements in any status are counted; discarding a draft/archiving a version cascade-deletes placement ROWS but never the PROTECT-ed asset.
4. **Recovery:** `edit_history` `before_state`/`after_state` and `template_baseline_snapshot` capture placement `*_asset_id` values (`edit_history_service._serialize_media`). **NOT seen** by `is_referenced()`.
5. **Legacy file fields:** placement `desktop_image`/`mobile_image`/`image` ImageFields (pre-MediaAsset). Resolved as fallback; deleted by direct filename cleanup, not the asset service.
6. **Domain-owned:** catalog `Brand.logo`, `Category.image`, `ProductImage.image`, `MerchantCollection.image`, `Vendor.logo`, `ShopSettings.logo`/`favicon`. **Out of scope** — never touched by the MediaAsset lifecycle.
7. **Static/template-packaged:** Ready-template preview/slide filenames under `static/` and recipe constants. Not MediaAsset rows.

## 13. Media retention / deletion policy

**Approved safe policy (no arbitrary TTL):** *retain while referenced or recoverable; physically delete only when unreachable from every supported reference class AND deletion is explicitly authorized by the existing product flow.*

**Confirmed gap A05 (still present at `5155182`):** `MediaAsset.is_referenced()` (`content/models.py:418-431`) checks ONLY the five FK placement reverse relations. It is blind to reference classes **2 (JSON background), 4 (history/baseline snapshots)**. `delete_media_asset_if_unreferenced` (`content/services.py:211-243`) trusts this incomplete check, and `media_views.storefront_section_media_delete` (242-298) triggers it. **Concrete unsafe path:** an asset used only as a JSON background (or referenced only by a history/baseline snapshot) whose last FK placement is deleted will be physically deleted — breaking a still-visible background or a recoverable state.

**Phase-2 requirement:**
- Extend the reachability check so it also scans reference class 2 (JSON `settings.background.media_asset_id` across all of the store's Draft/Published/Archived section settings) and class 4 (edit-history `before_state`/`after_state` payloads and `template_baseline_snapshot`) before authorizing physical deletion.
- The extended check must be tenant-scoped and conservative (fail-closed: if in doubt, treat as referenced → do NOT delete).
- Deletion remains triggered only by the existing explicit product flow (`storefront_section_media_delete` / replacement). **No orphan-cleanup job/command/signal is created in Phase 2.** Physical file deletion stays on `transaction.on_commit`.
- No new retention TTL, no bulk deletion, no destructive migration.

## 14. Legacy migration role during Phase 2

- Legacy routes remain active compatibility paths. They are hardened to the lifecycle contract (revision-coherence, atomicity, history, lock enforcement), NOT deleted.
- Legacy retirement is Phase 4; Phase 2 must not delete any legacy route merely because R4 exists.
- Where a legacy path can delegate to an existing canonical lifecycle service (e.g. legacy publish → the same publish lifecycle contract as R4), it should; where it cannot without UI/product change, it is hardened in place.

## 15. Failure / rollback requirements

- Every hardened mutation must be provably atomic: a forced failure mid-mutation leaves appearance/config/manifest/composition/media unchanged (proven by injection tests, following the Phase-1 pattern of mocking a late step to raise).
- Media physical deletion must never occur inside a transaction that can roll back (stays on `transaction.on_commit`).
- Stale-write rejection must write nothing (no revision bump, no history entry, no partial state).
- Recovery operations (undo/redo/restore/reset) must be atomic and revision-coherent.

## 16. Test / evidence strategy

Evidence must match the risk changed (program-spec Rule 8):

- **Revision/stale-write:** concurrent/stale-revision tests proving a stale legacy or R4 write is rejected or safely ordered; `edit_revision` advances exactly once per real change and not on no-ops.
- **Draft/Published/Archived:** negative tests proving no editing path mutates a Published/Archived/foreign version (extend existing `test_layout_service`, `test_r4_mutation_api`, `test_media_views`).
- **Atomic rollback:** failure-injection tests per hardened path.
- **History/recovery:** undo/redo/restore/reset round-trip tests proving canonical Appearance (typed manifest) is preserved and revision-coherent.
- **Structure lock:** operation-matrix tests across R4 and legacy for both `Section.is_locked` and `Container.is_locked`.
- **Media reachability:** tests proving an asset referenced ONLY via JSON background, ONLY via a Draft/Archived version's JSON, and ONLY via a history/baseline snapshot is NOT physically deleted; and that a genuinely unreachable asset still is (existing FK behavior preserved).
- Reuse existing modules where they already cover an invariant (`test_media_asset_lifecycle`, `test_media_write_path`, `test_layout_service`, `test_r4_mutation_api`, `test_phase27_history_identity`, `test_u1a_preset_edit_history_characterization`, `test_phase5_composition_lifecycle`, `test_u7_ready_template_baseline`). Add new Phase-2 test modules only for genuinely new invariants.

## 17. Explicit non-goals

- No commerce/business-domain rewrite; no moving Product/Brand/Collection/ShopSettings into Builder version snapshots.
- No new component families, no new variants, no Template 51+.
- No visual/browser certification of the 50 templates.
- No CSS/JS redesign; no new renderer.
- No legacy route deletion (Phase 4).
- No Brand/Collection Phase-3 vertical slice.
- No Page Override; no Store force-all Appearance policy; no content-preserving Template Switch.
- No orphan-cleanup job/command; no media TTL; no bulk/destructive media deletion.
- No DB migration expected. If a hardening step appears to require a schema migration, STOP and escalate (the `edit_revision` field already exists; media reachability is a read-time check, not a schema change).

## 18. Phase-2 exit gate

Phase 2 PASSES only when:

1. Every Appearance/Builder-owned mutation has an explicit lifecycle target (active Draft) and cannot mutate Published/Archived/foreign versions — proven by negative tests.
2. Stale conflicting edits cannot silently overwrite newer Draft state through the canonical contract: `edit_revision` is a Draft-wide monotonic token advanced by every state-changing mutation (R4 and hardened legacy), and stale writes are rejected where a revision is available.
3. Publish/restore/discard/undo/redo/reset are atomic, Draft-lifecycle-correct, revision-coherent, and recover canonical Appearance (typed manifest) intact.
4. Structure-lock enforcement is complete and consistent across R4 and legacy for both Section and Container, with negative tests; lock remains structure-only.
5. Media physical deletion respects ALL supported reference classes (FK + JSON + history/baseline), fail-closed, tenant-scoped; A05 closed with tests; no unreachable-but-recoverable asset can be deleted.
6. Cross-store/tenant isolation remains intact (regression-tested).
7. No DB migration, no new renderer, no business-domain change, no legacy deletion, no new variants.
8. Fresh full Phase-2 regression matrix GREEN (0 failures/errors except documented pre-existing Phase-1 baseline exceptions), Django check clean, `makemigrations --check` clean.

## 19. Deferred Phase-3+ items

- Content-preserving Template Switch (Phase 3+ product decision).
- Legacy route retirement / deletion (Phase 4).
- Brand/Collection vertical-slice family convergence (Phase 3).
- Non-Home R4 editor expansion (Phase 4).
- Page Override / Store force-all Appearance policy (later, if approved).
- Orphan media-cleanup background job / retention TTL (later product decision; Phase 2 only makes deletion *safe*, not proactive).
- 50-template browser/mobile certification (Phase 5).
