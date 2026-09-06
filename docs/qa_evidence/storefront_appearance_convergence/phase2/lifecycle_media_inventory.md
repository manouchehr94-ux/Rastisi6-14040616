# Phase 2 — Lifecycle & Media Inventory (evidence-driven)

Baseline `515518227c09f888972fa6eda756867097358dfb`. All `file:line` verified at this commit. Paths under `apps/`.

---

## 1. Mutation matrix (active Appearance/Builder-owned write paths)

Legend — **Lifecycle target:** always active DRAFT unless noted. **Auth:** `staff_required` + `permission_required(STOREFRONT_LAYOUT_MANAGE)` unless noted (R4 additionally feature-gated). **Stale-write class:** STRONG / PARTIAL / MISSING (see §3). **Phase-2 action:** KEEP / HARDEN / DELEGATE / CHARACTERIZE / DEFER.

| Path (command/route/service) | Source | Store resolution | Lifecycle target | Active Draft req'd | Explicit version id | base_revision | Stale class | Txn | History | edit_revision | No-op | Cross-store | Pub/Arch protected | Status | Phase-2 action |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R4 `apply_mutation` (all `section.*`, `appearance.*`, `header/footer.update`, `manifest/template/component`) | `r4_mutation_service.py:642` | `_lock_active_draft` select_for_update | Draft | yes | draft_id pin (appearance) | yes | STRONG | atomic | yes (snapshot/record) | +1/real change | no-op no churn | scoped | yes | R4 | KEEP |
| R4 `apply_history_command` (undo/redo) | `r4_mutation_service.py:676` | `_lock_active_draft` | Draft | yes | — | yes | STRONG | atomic | cursor only | +1 | controlled no-op | scoped | yes | R4 | KEEP |
| R4 `publish_draft` | `r4_mutation_service.py:685` | `_lock_active_draft` → `layout_service.publish` | Draft→Published | yes | — | yes | STRONG | atomic | clears history | — | — | scoped | yes | R4 | KEEP |
| Legacy `storefront_appearance_editor` | `views.py:2273` | `_resolve_store` + `get_or_create_draft` | Draft | yes | no | no | PARTIAL | via service | `@_record_edit_history` | none | history no-op filter | scoped | yes | LEGACY | HARDEN (T3) |
| Legacy `storefront_header_editor` / `footer_editor` | `views.py:2527/2574` | same | Draft | yes | no | no | PARTIAL | via service | decorator | none | filter | scoped | yes | LEGACY | HARDEN (T3) |
| Legacy `storefront_section_settings` | `views.py:787` | `_get_scoped_section` (Draft+store) | Draft | yes | no | no | PARTIAL | via service | decorator | none | filter | scoped | yes | LEGACY | HARDEN (T3) |
| Legacy structural: section add/remove/move/reorder/toggle/collapse/lock/duplicate | `views.py:683/1557/1843/1787/1593/1604/1618/1633` | `_get_scoped_section` | Draft | yes | no | no | PARTIAL | via service | decorator | none | filter | scoped | yes | LEGACY | HARDEN (T3), lock check T5 |
| Legacy block move/remove | `views.py:1689/1752` | `_get_scoped_section` | Draft | yes | no | no | PARTIAL | via service | decorator | none | filter | scoped | yes | LEGACY | HARDEN (T3), lock T5 |
| Legacy container add/settings/layout/move/remove | `views.py:396/421/487/505/534` | `_get_scoped_container` | Draft | yes | no | no | PARTIAL | via service | decorator | none | filter | scoped | yes | LEGACY | HARDEN (T3), lock T5 |
| Legacy cell add-section/clear | `views.py:555/631` | `_get_scoped_cell` | Draft | yes | no | no | PARTIAL | via service | decorator | none | filter | scoped | yes | LEGACY | HARDEN (T3), lock T5 |
| Legacy `storefront_apply_layout_preset` | `views.py:2033` → `preset_service.apply_preset_with_checkpoint` | `_resolve_store` | Draft (+checkpoint) | yes | no | no | PARTIAL | atomic + checkpoint | decorator | none | `_draft_already_matches_preset` short-circuit | scoped | yes | LEGACY | HARDEN (T5) |
| Legacy `storefront_apply_industry_layout` | `views.py:2234` → `layout_service.apply_industry_layout` | `_resolve_store` | new Draft | creates | no | no | PARTIAL | atomic | NOT decorated | — | force gate | scoped | yes | LEGACY | HARDEN (T5) |
| Legacy resets: section/field/appearance-field/header/footer/page/to-baseline | `views.py:2085/2109/2132/2153/2173/2191/2213` | `_get_scoped_section`/`_resolve_store` | Draft | yes | no | no | PARTIAL/MISSING | atomic (checkpoint for page/full) | decorator (granular) | none | — | scoped | yes | LEGACY | HARDEN (T5) |
| Legacy `storefront_undo` / `storefront_redo` | `views.py:1904/1916` → `edit_history_service.undo/redo` | `_resolve_store` | Draft | yes | no | no | MISSING | atomic (service) | cursor only | none | controlled no-op | scoped | yes | LEGACY | HARDEN (T4) |
| Legacy `storefront_publish` | `views.py:1928` → `layout_service.publish` | `_resolve_store` | Draft→Published | yes | no | **no** | MISSING | atomic | clears history | — | — | scoped | yes | LEGACY | HARDEN (T4) |
| Legacy `storefront_discard` | `views.py:2263` → `discard_draft` | `_resolve_store` | Draft delete | yes | no | no | N/A | atomic | — | — | — | scoped | yes | LEGACY | KEEP (T4 test) |
| Legacy `storefront_restore` | `views.py:2642` → `restore_version` | `_resolve_store` | any→new Draft | no | version_id | no | N/A | atomic | NOT decorated | — | — | CrossStoreVersionError | yes | LEGACY | KEEP (T4 test) |
| Media routes: list/form/delete/toggle/move/reorder | `media_views.py:109/165/242/304/316/338` | `_get_scoped_section` (Draft+store) | Draft placements | yes | no | no | MISSING | atomic | NOT decorated | none | — | scoped | yes | LEGACY | HARDEN media reachability T6 |

## 2. Lifecycle transition map (from real code)

```text
(no version)
   │ get_or_create_draft  (first-ever: bootstrap_service.apply_bootstrap_content, Source=LEGACY_BOOTSTRAP)
   ▼
 DRAFT ──────────────────────────────────────────────┐
   │ publish (layout_service.publish, @atomic):        │
   │   ensure containers; DELETE edit history;         │
   │   previous PUBLISHED → ARCHIVED;                  │
   │   this DRAFT → PUBLISHED; draft_version=None;     │
   │   uses_visual_storefront_layout=True              │
   ▼                                                    │
 PUBLISHED                                              │
   │ get_or_create_draft (not first-ever):             │
   │   _clone_version_content(published → new DRAFT)  ──┘  (copies appearance incl store_appearance,
   │                                                        provenance, baseline, sections w/ stable_id +
   │                                                        template_slot_key, section media as NEW rows
   │                                                        SHARING the same MediaAsset, containers)
   │
   │ (a newer publish) previous PUBLISHED ── ARCHIVED
   ▼
 ARCHIVED

 DRAFT ── discard_draft ──▶ (deleted; pointer nulled)

 ANY owned version (DRAFT/PUBLISHED/ARCHIVED)
   └ restore_version ──▶ new DRAFT (Source=RESTORED); source version unchanged; never auto-publishes
                         (CrossStoreVersionError if version not owned by store)

 DRAFT ── checkpoint_draft_before_replacement ──▶ old DRAFT → ARCHIVED (recoverable) + new active DRAFT
```

Public reads PUBLISHED only (`page_resolution_service._published_layout_queryset`: `uses_visual_storefront_layout=True AND published_version` — never Draft). Preview reads the active DRAFT (`get_or_create_draft`).

## 3. Stale-write / revision matrix

| Class | Paths | Rationale |
|---|---|---|
| **A. STRONG** (base_revision + atomic + revision-coherent) | R4 `apply_mutation`, `apply_history_command`, `publish_draft` | `_lock_active_draft` (`r4_mutation_service.py:610`) `select_for_update` on Layout + Version, compares `edit_revision != base_revision` → `R4StaleRevision`; atomic; single `edit_revision += 1` per real change (appearance component/manifest/template also pin `draft_id`). |
| **B. PARTIAL** (Draft/store-scoped + history, but no revision guard) | all legacy view mutations (appearance/header/footer/section-settings/structural/container/cell), legacy preset apply + granular resets | Scoped via `_get_scoped_section/_container/_cell` (`status=DRAFT`, store) so cannot cross store or hit Published/Archived, and captured in Undo/Redo via `@_record_edit_history`; but no `base_revision`, no `edit_revision` bump → last-writer-wins between two legacy tabs or legacy-vs-R4 on the same Draft. |
| **C. MISSING** (can silently overwrite newer Draft state) | legacy `storefront_publish` (no base_revision, cf R4 `publish_draft`), legacy `storefront_undo`/`storefront_redo` (direct `edit_history_service`, no guard, no revision bump), media routes (no revision) | No detection that the Draft's `edit_revision` advanced since the client loaded it. |
| **D. N/A** | `discard_draft` (deletes the draft), `restore_version` (creates a fresh Draft) | No newer state to overwrite; both atomic and store-scoped. |

**Phase-2 convergence target:** make `edit_revision` a Draft-wide monotonic token advanced by EVERY state-changing mutation (R4 + hardened legacy), so a concurrent client's stale `base_revision` is detected. Do NOT force the R4 JSON command envelope onto legacy routes (one lifecycle *contract*, not one endpoint).

## 4. Recovery inventory

| Mechanism | Source | Restores | Txn | Revision effect | History effect | Manifest-correct (post-Phase-1)? |
|---|---|---|---|---|---|---|
| `edit_history_service.snapshot_draft` / `record_change` | `edit_history_service.py:124/290` | full-draft snapshot (appearance_config incl typed manifest, provenance, baseline, sections+media asset ids, containers) | atomic | — | append + prune 30 | YES (manifest lives in appearance_config) |
| `undo` / `redo` → `restore_draft_state` | `edit_history_service.py` | before/after snapshot into Draft | atomic | R4 path +1; legacy path none (T4 hardens) | flips `is_undone` | YES |
| `preset_service.reset_storefront_to_baseline` → `apply_baseline_snapshot` | `preset_service.py:510/580` | `template_baseline_snapshot` (manifest-synced appearance + per-page composition) | atomic | none | none | YES (snapshot built from manifest-synced state, Phase-1 Task-5) |
| granular `reset_section/field/appearance-field/header/footer/page_to_baseline` | `preset_service.py:765+` | slice of baseline snapshot | atomic (page) | none | via caller decorator | YES |
| `*_with_checkpoint` wrappers | `preset_service.py:682/714/736` | checkpoint (archive prior) then apply | atomic | none | none | YES |
| `layout_service.restore_version` | `layout_service.py:826` | any owned version → new DRAFT | atomic | fresh draft | none | YES (clones appearance_config) |
| `layout_service.discard_draft` | `layout_service.py:763` | (deletes active draft) | atomic | — | — | N/A |

Overlap note: `edit_history` (short-lived per-Draft undo/redo), `reset-to-baseline` (return to the applied recipe), and `restore_version` (recover an archived/older version into a new Draft) are DISTINCT mechanisms with distinct owners/scopes — not duplicates. Phase 2 documents boundaries + adds tests; does not merge them.

## 5. Media-reference taxonomy

Primary model: `MediaAsset` (`apps/content/models.py:385-431`; `store` FK CASCADE + `image` ImageField). `is_referenced()` (`:418-431`) = OR of five FK reverse relations only.

| # | Class | Model / field | Written by | Rendered by | In snapshots? | Deletion behavior | Seen by `is_referenced`? | Risk if missed |
|---|---|---|---|---|---|---|---|---|
| 1 | Direct FK | HeroSlide `desktop_asset`/`mobile_asset`; PromotionalBanner `desktop_asset`/`mobile_asset`; StoryRailItem `image_asset` (asset FK PROTECT; section FK CASCADE) | media_views form | `_resolve_placement_media_url` | cloned as NEW rows sharing same asset (`_clone_section_scoped_media`) | placement row cascades w/ section; asset PROTECT | **YES** (all statuses) | — |
| 2 | JSON | `StorefrontSection.settings["background"]["media_asset_id"]` | `views._extract_background_raw:1066` | `content.services.resolve_background_media_url:131` | present in section settings snapshots | none direct | **NO** | **A05:** deletable while still shown |
| 3 | Version-state | placement/JSON via section→page→version (Draft/Published/Archived) | — | — | — | discard/archive cascades placement rows only | FK: yes; JSON: no | archived/draft JSON-only ref lost |
| 4 | Recovery | `edit_history` before/after + `template_baseline_snapshot` capture `*_asset_id` | `edit_history_service._serialize_media`, `preset_service` | on restore recreates placements at same asset | — | none | **NO** | **A05:** snapshot-only ref deletable |
| 5 | Legacy file | placement `desktop_image`/`mobile_image`/`image` ImageFields | legacy | fallback resolve | — | direct filename cleanup | N/A (not asset) | shared filename |
| 6 | Domain-owned | catalog `Brand.logo`/`Category.image`/`ProductImage.image`/`MerchantCollection.image`/`Vendor.logo`; `ShopSettings.logo`/`favicon` | domain editors | domain | — | domain-owned | N/A | out of scope |
| 7 | Static/template | Ready-template preview/slide filenames under `static/`, recipe constants | build/recipe | templates | — | none | N/A | out of scope |

## 6. Current media deletion / cleanup

- Single physical-deletion gate: `content.services.delete_media_asset_if_unreferenced` (`:211-243`) — returns False if `asset.is_referenced()`; else `asset.delete()` + `transaction.on_commit` file removal.
- Trigger: `media_views.storefront_section_media_delete` (`:242-298`) — deletes placement row, then calls the gate per asset field.
- Replacement: `_sync_asset_references` creates a new MediaAsset and deletes only the old raw upload bytes; does not delete a still-referenced old asset row.
- **No orphan/cleanup/prune management command, signal, or scheduled job exists** (grep confirms; the design explicitly avoided signals — `content/services.py:201-209`).

## 7. Structure-lock matrix (real operations only)

Fields: `StorefrontSection.is_locked` (`models.py:677`), `StorefrontContainer.is_locked` (`models.py:806`). Toggle: `views.storefront_section_lock_toggle` (`:1618`).

| Operation | Locked allowed? | Enforcement |
|---|---|---|
| Section move / reorder | NO | `section_structure_service.py:218/238`; `views.py:1815/1849` |
| Section remove | NO | `views.py:1564` |
| Block move / remove (in cell) | NO | `views.py:1698/1762`; `container_service.py:830/847` |
| Container settings / layout / move / remove | NO (locked container) | `views.py:424/510/537`; `container_service.py:711/1023` |
| Cell add-section / clear | NO (locked container) | `views.py:580/647`; `section_structure_service.py:132/155` |
| Template apply / baseline reset over a page with a locked section | NO | `preset_service.apply_preset` / `apply_baseline_snapshot` → `LockedSectionsPresentError` |
| Section settings (content/appearance) edit | YES | not blocked — structure-only |
| Toggle active / collapse / lock-toggle | YES | not blocked |
| Section duplicate | YES (new logical section) | `views.py:1633` |

Model docstring (`models.py:424`, `:677`) is explicit: lock affects structure only (move/delete), independent of `is_active` and of duplicable/removable — it is NOT an appearance or content lock. Phase-2 target = confirm this matrix is complete/consistent across R4 (`section_structure_service`) and legacy views for both Section and Container, add negative tests, add no new lock type.

## 8. L01+ gap register

| ID | Sev | Gap | Evidence | Required invariant | Task |
|---|---|---|---|---|---|
| L01 | P1 | Legacy mutations do not advance `edit_revision` | §3 class B | `edit_revision` is a Draft-wide monotonic token advanced by every real change | T3 |
| L02 | P1 | Legacy `storefront_publish` has no stale guard | `views.py:1928` vs R4 `publish_draft` | legacy publish reaches R4 publish lifecycle guarantee | T4 |
| L03 | P2 | Legacy undo/redo no revision guard/advance | `views.py:1904/1916` | undo/redo revision-coherent via either entry | T4 |
| L04 | P2 | Legacy preset apply/reset advance no `edit_revision` | `views.py:2033/2085…` | atomic + revision advance on real change | T5 |
| L05 | P2 | Missing negative tests: no editing path mutates Published/Archived/foreign | §1 all rows | proven by negative tests | T1(RED)+T2 |
| L06 | P2 | Lock matrix not proven complete/consistent (R4 vs legacy, Section+Container) | §7 | complete matrix, tested | T5 |
| L07 | **P0** | **A05** media reachability blind to JSON + snapshots | `content/models.py:418-431`, `services.py:211-243`, verified present | deletion respects ALL reference classes, fail-closed | T6 |
| L08 | P2 | No atomic-rollback test for legacy mutation/publish/reset | Phase-1 proved only preset/R4 | failure-injection rollback per hardened path | T1(RED)+relevant |
| L09 | P3 | Legacy routes co-active with R4 (retirement) | — | — | **DEFERRED → Phase 4** |
| L10 | P3 | No proactive orphan-media cleanup / TTL | §6 | — | **DEFERRED → later product decision** |

## 9. Deferred (non-Phase-2) findings

- L09 legacy route retirement/deletion → Phase 4.
- L10 proactive orphan-media cleanup job / retention TTL → later product decision (Phase 2 only makes deletion *safe*, not proactive).
- Content-preserving Template Switch → Phase 3+.
- Brand/Collection vertical-slice family convergence → Phase 3.
- Non-Home R4 editor expansion → Phase 4.
- Page Override / Store force-all Appearance policy → later, if approved.
- 50-template browser/mobile certification → Phase 5.
