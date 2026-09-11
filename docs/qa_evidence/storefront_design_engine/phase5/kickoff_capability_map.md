# Phase 5 — Task 0 Kickoff Capability Map

Date: 2026-09-11
Branch: `feature/phase5-design-expansion` (from `chore/phase5-uiux-agent-foundation@9f71109`)
Scope: Discovery/planning only. No production storefront code was changed to produce this document.

Method: narrow Graphify queries for orientation, then direct source/test verification (file:line). Six
parallel read-only audits were run against the real repository; findings below are synthesized from
those audits and, where flagged, independently re-verified by the orchestrating session. Evidence
convention: **FACT** = read directly from source/tests/migrations. **INFERENCE** = reasonable
conclusion, not itself independently observed. **DOC CLAIM** = a prior document's claim, confirmed or
marked stale against current source.

## 0. Corrections to the audit trail itself (read this first)

Two of the six sub-audits used mutually inconsistent baselines, and this section reconciles them
against directly re-verified current source (this is exactly the kind of internal conflict the kickoff
instructions require documenting rather than silently picking a side):

1. One sub-audit ran in an isolated git worktree that resolved to commit `973c1dc0` (2026‑09‑07) instead
   of the actual current branch tip, and concluded **"R4 is unreachable, the legacy editor is the real
   merchant path."** That conclusion is **STALE**. Directly re-verified against the real current
   working tree in this session:
   - `apps/storefront_builder/migrations/0020_r4_editor_enabled_default_true.py` flips
     `StorefrontLayout.r4_editor_enabled` to `default=True` **and** retroactively flips every existing
     Store via a data migration. The migration's own comment: *"Pre-Task-10 remediation — R4 is now the
     default canonical merchant editor (dashboard nav routes here) ... never to gate normal access."*
   - `apps/dashboard/templates/dashboard/base_admin.html:289,297,529-533` — the primary dashboard nav
     items for "سازنده فروشگاه" (Storefront Builder) and "ظاهر و طراحی" (Appearance & Design) link to
     `dashboard:storefront-builder-r4-editor`, **not** the legacy editor.
   - The legacy editor (`dashboard:storefront-builder-editor`) is still registered and still linked, but
     only as a secondary, de-emphasized link (`base_admin.html:301`, `font-size:.85em;opacity:.75`,
     labeled "ادامه در ویرایشگرِ پیشرفته" / "continue in the advanced editor") and as the explicit
     "back to editor" target from sub-pages that have not yet been ported to R4: header/footer full
     editor, section media management, and Draft history (`header_editor.html:98`,
     `footer_editor.html:107`, `section_media_list.html:9`, `history.html:37`).
   - **Corrected verdict:** R4 is the primary, nav-linked, default-enabled merchant editor today. The
     legacy editor is a real, intentionally-still-linked **adapter for capabilities not yet ported to
     R4** (header/footer full editor, media management, history UI), not a competing primary shell that
     merchants are actually using instead of R4. This is a **legitimate incremental-migration
     duplication**, not the dangerous kind — but see §3 "Draft mutation entrypoint" below for the real
     residual risk (unequal stale-write protection between the two shells).
2. The same stale-worktree audit also concluded "no R4 route calls `preset_service` at all." This is
   also corrected: `r4_mutation_service._apply_appearance_template()` (mutation type
   `appearance.template.apply`, dispatched at `r4_mutation_service.py:943`) calls
   `preset_service.apply_preset()` directly — independently confirmed by a second, current-HEAD sub-audit
   and by `docs/qa_evidence/storefront_appearance_convergence/phase4/task1_authority.md:74-78`
   (`test_legacy_and_r4_entry_paths_converge`). **Ready Template Apply is reachable from both shells
   through one canonical service`, not legacy-only.** (The Ready Template *gallery* itself,
   `dashboard:storefront-builder-templates`, is a separate nav-linked page, not part of either editor
   shell — see §2.)
3. Everything else in the stale-worktree audit (module ownership, the shared renderer, the appearance
   authority service, registries, tenant resolution) was independently corroborated by the two
   current-HEAD sub-audits and is retained below without qualification.

## 1. Canonical architecture flow (Charter §2: `R4 Editor → Canonical Services → Draft Lifecycle/History → Shared Renderer → Preview/Publish/Public`)

| Requirement | Current owner | Current implementation | Status | Evidence | Phase-5 action | Risk/dependency |
|---|---|---|---|---|---|---|
| R4 Editor (merchant shell) | `apps/storefront_builder/r4_views.py` | `storefront_r4_editor()` (shell), `storefront_r4_mutation()` (generic mutation), `storefront_r4_section_inspector()`, `storefront_r4_resource_picker()`, `storefront_r4_history_command()`, `storefront_r4_publish()` — 6 routes | EXISTS & REUSE | `r4_views.py:222-590`; nav links `base_admin.html:289,297,529-533`; migration `0020` | Build all new merchant-facing Phase-5 UI (Showcase, Theme, Random Mix, onboarding gallery) as R4 surfaces, not a new shell | None — this is the correct target, confirmed live |
| Legacy editor (secondary/adapter) | `apps/storefront_builder/views.py` | `storefront_editor()` + 44 mutation routes, still linked for header/footer/media/history | EXISTS BUT NEEDS REPAIR | `views.py:108-147`; nav `base_admin.html:301`; sub-page back-links (see §0) | Do not delete; port header/footer full editor, media picker, and history UI into R4 over time so the legacy shell can eventually retire | Legacy's ~44 field-mutation routes are **not** stale-write protected (see §3) — a real risk while both shells stay live |
| Canonical Services (mutation/business layer) | `apps/storefront_builder/services/` (17 modules, no single "the" service — responsibilities split by concern) | `layout_service.py` (Draft/Published lifecycle), `r4_mutation_service.py` (the one optimistic-concurrency mutation boundary + shared publish/undo-redo), `appearance_authority_service.py` (canonical appearance writer, used by both shells), `preset_service.py` (Ready Template apply/reset/switch), `edit_history_service.py`, `render_service.py` (shared renderer), `storefront_context_service.py` (public context builder) | EXISTS & REUSE | file:line citations in full architecture audit (scratchpad; see index) | Extend these services for Showcase/Theme/Random-Mix; do not create parallel services | None found — single-owner per concern |
| Draft Lifecycle / History | `StorefrontLayout`, `StorefrontLayoutVersion` (`models.py:188,232`, `edit_revision` field `:316`) + `edit_history_service.py` (`snapshot_draft:124`, `restore_draft_state:159`, `undo/redo:359,376`, `record_change:303`) | Draft/Published version pointers; Undo/Redo via monotonic `edit_revision` counter | EXISTS & REUSE | see architecture audit | Reuse as-is for all new mutation types (Theme apply, Random Mix apply, Showcase config) | See §3 — stale-write rejection is narrower than the revision counter itself |
| Shared Renderer | `apps/storefront_builder/services/render_service.py` (1066 lines) | `build_page_render_items`, `build_default_render_items`, `build_container_render_items`, `group_items_into_rows` | EXISTS & REUSE — **single implementation, no second renderer found** | `render_service.py:654,863,941,1020`; consumed by legacy preview, R4 shell, and 7 of 9 audited public routes via `storefront_context_service.build_universal_storefront_context` | Route every new Phase-5 surface (Showcase, Theme preview, Random Mix preview, onboarding gallery preview) through this same renderer | Wishlist (`apps/customers/views.py:25`) and Content/CMS pages (`apps/content/views.py:11`) are **not yet wired** to the shared renderer — still on hardcoded `base.html` chrome. Not a duplication, just an unclosed gap; fix before those pages need Phase-5 sections |
| Preview | `storefront_preview()` (`views.py:225-296`, route `storefront-builder/preview/`) | Draft-only iframe render via the shared renderer, staff-gated | EXISTS & REUSE | see architecture audit | Reuse for Design Lab / Theme preview once a non-mutating "candidate" path exists (§5, item 4) | Today it can only preview the **real Draft** — no candidate/what-if preview exists yet |
| Publish | `layout_service.publish()` (`:773`), atomic pointer swap | Called by both legacy `storefront_publish` and R4 `storefront_r4_publish` | EXISTS & REUSE — single owner | see architecture audit | Reuse unchanged | Legacy's plain-HTML publish form does not send `base_revision`, so it is not stale-checked in practice (see §3) |
| Public rendering | `build_universal_storefront_context()` (`storefront_context_service.py:56`) | Wired into Home, Product List/Search/Category, PDP, Collection Index/Detail, Cart, staff product-preview — **7 of 9 audited public routes** | EXISTS & REUSE (7/9); 2 gaps | `apps/catalog/views.py:66,375,523,590,609`; `apps/cart/views.py:68,93`; `apps/dashboard/views.py:1211` | Wire Wishlist and Content/CMS pages before Phase-5 needs Showcase/Theme sections there | Two legitimate, not-yet-closed gaps, not a competing renderer |
| Tenant/store scoping | `apps/stores/resolution.py` | `resolve_store_for_storefront()` (public, fail-closed), `resolve_store_for_service()` (dashboard/Builder mutation), `resolve_store_for_admin_request()`, `resolve_store_for_hostname()` | EXISTS & REUSE — single resolver family, no duplicate path | `resolution.py:218,277,300,398` | Reuse unchanged for every new Phase-5 route | None found |
| Media / ResourceSource authority | `apps/storefront_builder/resource_source.py` (typed contract) + `media_views.py` (section-scoped CRUD, legacy-editor-only, 7 routes) | `ResourceSource` dataclass + kind-scoped adapters (product/brand/collection) | EXISTS & REUSE, complementary (not competing) owners | `resource_source.py:262-367`; `media_views.py:109-338` | Port section media/background picker into R4 (see §5 item 13) before Contextual Editor work depends on it | R4 has no in-shell media/background picker yet — only a stub linking out to legacy |

## 2. Ready Template authority (Charter §6 "Meaning of 67 families", Charter §5 "50 Template DNA")

| Requirement | Current owner | Current implementation | Status | Evidence | Phase-5 action | Risk/dependency |
|---|---|---|---|---|---|---|
| Ready Template count | `apps/storefront_builder/a8_ready_templates.py` | Exactly **50** `_RecipeSpec` entries, registered via `layout_preset_registry.register_layout_preset()` | EXISTS & REUSE | `a8_ready_templates.py:221-272`; test `test_show_all_is_exactly_the_literal_fifty_key_catalog` (`tests/test_a8_ready_template_catalog.py:117-130`) | Reuse the 50 as Phase-5's starting set; do not rebuild | None |
| Template registry authority | `apps/storefront_builder/layout_preset_registry.py` | Single registry module; `LayoutPresetDefinition`, `register_layout_preset`, `list_ready_templates` | EXISTS & REUSE — single owner | `layout_preset_registry.py:87,187,214,218` | Reuse unchanged | None |
| Template DNA declaration | `_RecipeSpec` → `LayoutPresetDefinition.store_appearance`/`.appearance`/`.pages` | 10 Store-Appearance family selections (header/mega_menu/hero/layout/product_view/card/badge/motion/footer/bottom_nav) + bounded appearance overlay + per-page section composition | EXISTS & REUSE | `a8_ready_templates.py:9-27,86-218` | Reuse as the Template-DNA contract; extend fields only through this same manifest, never a parallel one | None |
| Distinctness of the 50 | — | 50 normalized declared-DNA fingerprints, 0 duplicate groups, 0 palette-only-duplicate groups (declared-recipe level, not rendered/visual certification); 27 distinct Home structural compositions; 12/8/7/6 distinct Header/Footer/BottomNav/Hero refs actually used | DOC CLAIM, structurally re-confirmed unchanged | `final_closure_pack/04-50-template-dna-reality-check.md` (2026-09-05), re-derived and confirmed "not stale" by `phase4_architecture_audit.md` (2026-09-11) | A full browser/visual-distinctness certification across all 50 is still needed before Phase-5 closure (Charter §13 QA gate) — this is a **declared-data** fact, not a rendered/browser-verified one | No browser screenshot pass across all 50 exists yet |
| Apply (does it fully consume the declared manifest?) | `preset_service.apply_preset()` (`:274-528`, `@transaction.atomic`) | **Fully consumes all 10 declared families** via `appearance_authority_service.apply_store_appearance_manifest()`, called last inside the same transaction, with explicit in-code comment "A02 closure" | EXISTS & REUSE — **the closure-pack's "A02: declared ≠ applied" P0 finding is CLOSED**, fixed by the 2026-09 "Storefront Appearance Convergence" program, Phase 1 Task 5 | `preset_service.py:428-484`; corroborating removal comment `r4_mutation_service.py:642-650`; test `task1_authority.md:74-78` | Reuse unchanged for Phase-5 Apply flows (including Theme apply if it reuses this same contract) | None — this used to be the single biggest closure-pack risk; it is now closed and independently re-verified in this session |
| Reset to baseline | `preset_service.reset_storefront_to_baseline()` (`:555`) | Resets to the originally-applied recipe's own recorded baseline | EXISTS & REUSE | see Template-DNA table §6 item 14 | Reuse for "Reset DNA" (Charter's Design Lab requirement) | Does not reset to an arbitrary in-progress Design-Lab candidate — that state doesn't exist yet (Random Mix is not built) |
| Content-preserving Template Switch | `preset_service.switch_template_preserving_content()` (`:794`), R4 mutation `switch_template` (`r4_mutation_service.py:1152-1190`) | Checkpoints current Draft, applies only the new Template's DNA (appearance + header/footer + manifest) via `appearance_authority_service.apply_ready_template_appearance()`, **never touches page composition** | EXISTS & REUSE — **new, landed today (2026-09-11) as Phase-4 Task 8** | `preset_service.py:794-921`; `docs/qa_evidence/storefront_appearance_convergence/phase4/task8_template_switch_lifecycle.md` | This is the correct primitive for Onboarding Charter §8's "Apply must not destroy merchant content" requirement — reuse it, do not build a second switch mechanism | A related regression (baseline-provenance mismatch silently wiping content) was found and fixed within the same Task 8 — re-run its regression test before building further on top |
| Full/replace Apply (distinct from Switch) | `preset_service.apply_preset()` via `apply_preset_with_checkpoint()` | **Deletes and rebuilds** all sections/containers on every covered page; safety net is only the pre-replacement checkpoint (Undo/Restore), not content preservation | EXISTS & REUSE, but **document the distinction clearly in any new UI** | `preset_service.py:511-528,762-790` | Onboarding gallery's "Apply Template" must clearly use the content-preserving Switch (item above), not this replace-only Apply, once a merchant already has real content — see §5 item 5 | Two operations, two different guarantees, reachable from different buttons; a UI that doesn't clearly distinguish them risks surprising a merchant with content loss |
| Template Preview (gallery thumbnails) | `template_preview_service.py` (offline capture: `capture_ready_template_previews` mgmt command) + `resolve_real_screenshot`/`resolve_gallery_thumbnail` | Pre-captured static `.webp` screenshots against `rasti-mode-demo`, with an SVG schematic fallback; **no live/interactive render, no Draft access at all** | EXISTS BUT NEEDS REPAIR | `template_preview_service.py:271-334,478-512`; `capture_ready_template_previews.py` | Needed for onboarding gallery: an on-demand render path (reusing the Preview iframe + render_service, not screenshots) — see §5 items 2-4 | Screenshots go stale between recaptures (guarded by a fingerprint hash, not auto-refreshed) |

## 3. R4 mutation contracts / stale-write protection (Charter §7 "no parallel authority")

| Requirement | Current owner | Current implementation | Status | Evidence | Phase-5 action | Risk/dependency |
|---|---|---|---|---|---|---|
| Client-side optimistic-concurrency rejection | `r4_mutation_service.apply_mutation()` | Rejects with HTTP 409 `stale_revision` if `base_revision` doesn't match `draft.edit_revision` | EXISTS & REUSE — **exactly 1 route enforces this unconditionally**: `storefront-builder/r4/mutate/` | `r4_views.py:309-311,325-329` (re-counted directly against current HEAD — do not reuse the closure-pack's stale "3 of 86" figure) | All new Phase-5 mutation types (Theme apply, Random Mix apply, Showcase config writes) must go through this one endpoint/contract | — |
| Shared monotonic revision counter | `edit_history_service.record_change()` | Advances `edit_revision` on every write (legacy and R4 alike), so both shells agree on "current revision" even though only R4's endpoint rejects stale writes | EXISTS & REUSE (real, useful convergence) | `edit_history_service.py:349-354` | Reuse — this is what makes it safe to keep both shells live during incremental R4 migration | — |
| Legacy per-field mutation routes | ~44 routes in `views.py` | Call `edit_history_service.record_change`, which advances the revision counter but does **not** accept/check a client `base_revision` | EXISTS BUT NEEDS REPAIR | spot-checked `storefront_section_settings` (`views.py:788-818`) — plain form POST, no revision field | Not blocking for Phase-5 if new work stays in R4, but do not add new Phase-5 mutation surfaces to the legacy shell | Real residual risk while legacy stays live: two merchants (or a merchant + a stale open tab) editing via legacy can silently overwrite each other; R4's endpoint alone is protected |
| Publish / Undo / Redo stale-write coverage | `r4_mutation_service.publish_draft`, `apply_history_command_current` | Publish is stale-checked **only if** the caller sends `base_revision`; legacy's plain HTML publish form does not send one in practice. Undo/Redo always advance the revision monotonically but don't themselves check an incoming `base_revision` | EXISTS BUT NEEDS REPAIR | `views.py:1929-1991` | Low priority for Phase-5 scope unless Theme/Random-Mix apply routes through Publish directly — worth a follow-up ticket, not a Phase-5 blocker | — |

## 4. Duplication / Authority gate (Charter §7, §10 audit step)

| Concept | Verdict | Owner(s) | Evidence |
|---|---|---|---|
| Renderer | **SINGLE OWNER** | `render_service.py` | No second implementation found; both editors' previews and 7 of 9 public routes funnel through it |
| Draft lifecycle (publish/version pointer) | **SINGLE OWNER** | `layout_service.publish()` | Both legacy and R4 call the same function (directly or via the stale-aware wrapper) |
| Draft mutation entrypoint / editor shell | **LEGITIMATE INCREMENTAL-MIGRATION DUPLICATION, with a real residual risk** | R4 (primary, nav-linked, revision-safe) + legacy (secondary, linked for un-ported capabilities, not stale-write safe) | See §0 correction and §3 — R4 is the shipped primary path; legacy remains a real adapter, not a second competing primary |
| Appearance persistence path (writer) | **SINGLE OWNER — CONVERGED** | `appearance_authority_service.py`, called by both shells and by `preset_service` | `appearance_authority_service.py:8-11` docstring + 3 confirmed call sites; this closes the closure-pack's A01 finding |
| Ready Template apply owner | **SINGLE OWNER, reachable from both shells** (corrected — see §0) | `preset_service.apply_preset()`, called by legacy's `apply_preset_with_checkpoint` and R4's `appearance.template.apply` mutation | `r4_mutation_service.py:620-650,943`; `task1_authority.md` convergence test |
| Ready Template declared-manifest application (A02) | **ADDRESSED** | `preset_service.py:428-484`, explicit "A02 closure" comment | See §2 Apply row |
| Template registry authority | **SINGLE OWNER** | `layout_preset_registry.py` | One registry, no second elsewhere |
| Media authority | **SINGLE OWNER (complementary split, not competing)** | `resource_source.py` (which resource) + `media_views.py` (uploaded files) | No second typed-resource contract or media-CRUD surface found |
| Preview rendering path | **SINGLE OWNER** | `storefront_preview()` using `render_service` | R4's shell reuses the same underlying render functions |
| Public rendering path | **SINGLE OWNER for 7/9 audited routes; 2 legitimate not-yet-wired gaps** | `build_universal_storefront_context` | Wishlist and Content/CMS pages not yet wired — a gap, not a second renderer |
| Design-state persistence (Draft JSON) | **SINGLE OWNER for the data; unequal write-surface safety (see §3)** | `StorefrontLayoutVersion` | One data model; the risk is in the write surface, not the data ownership |

**Overall verdict: no dangerous second renderer, persistence, lifecycle, or template authority exists.**
The one real architectural item Phase 5 planning must carry forward is the **unequal stale-write
protection** between the R4 (safe) and legacy (not safe) mutation surfaces while both remain live — see
§3. This is a residual-risk item to track, not a Phase-5 blocker, since Phase-5 work should build on R4.

## 5. Onboarding / Contextual Editor (Onboarding Charter, §6-§14)

| # | Requirement | Current owner | Status | Evidence | Phase-5 action |
|---|---|---|---|---|---|
| 1 | 50-template gallery | `storefront_template_gallery()` (`views.py:2137`), nav-linked at `dashboard:storefront-builder-templates` | EXISTS & REUSE | `a8_ready_templates.py`; test asserts exactly 50 unique keys | Reuse; extend cards with palette swatches / material-difference framing already present |
| 2 | Demo-data preview | `capture_ready_template_previews.py` (offline) + `resolve_real_screenshot`/`resolve_gallery_thumbnail` | EXISTS BUT NEEDS REPAIR | `template_preview_service.py:271-334,478-512` | Offline screenshots today, not live/interactive. Repair path: reuse the Draft Preview iframe + shared renderer against an isolated scratch context instead of Playwright screenshots |
| 3 | Merchant-data preview (real catalog, no Draft mutation) | none | MISSING & BUILD | confirmed absent by grep across `preset_service.py`/`views.py`/`r4_views.py` | Needs a service-level "resolve without writing" entry point parallel to `apply_preset()`. The rendering substrate (real Store-scoped products/brands/categories via `resource_source.py`) already exists and is reusable |
| 4 | Candidate preview without Draft mutation (general mechanism) | none | MISSING & BUILD | no `dry_run`/`preview_only`/`candidate` parameter anywhere in `preset_service.py` | A proven in-repo precedent exists for this exact shape in a **different** feature: `apps/catalog/services/template_preview_service.py` (`build_template_preview()`, `plan_industry_template_installation()` — full "what would happen" projection with zero writes). Reuse that architecture's pattern for storefront Ready Templates |
| 5 | Apply Template | `storefront_apply_layout_preset()` (`views.py:2218`) + `preset_service.apply_preset_with_checkpoint()`; R4 mutation `appearance.template.apply` | EXISTS & REUSE | see §2 | Reuse; UI must distinguish full-replace Apply from content-preserving Switch (§2) |
| 6 | Contextual click-to-edit | `selectSectionElement()` (`preview.html:87-100`) → `postMessage` → `r4_editor.js:1079-1097` → `R4.openSection()` (`r4_editor.js:341-373`) | EXISTS & REUSE | file:line above | Reuse unchanged for Showcase/new sections |
| 7 | Selected-section highlight | `applyBuilderSelection()` (`preview.html:52-76`) + `.sfb-rsec-selected` CSS (`storefront_builder.css:3345`) | EXISTS & REUSE, with a caveat | `r4_editor.js` never sends `sfb:setSelection` back into the iframe — a sidebar-originated selection may not re-highlight the iframe element | Verify/repair this specific sync path before onboarding flows depend on sidebar-driven selection |
| 8 | Inspector targeting | `R4.openSection()` fetches `sections/<id>/inspector/`, section-type-specific context builder (`views.py:1038-1082`) | EXISTS & REUSE | — | Reuse |
| 9 | Basic/Advanced control tiers | `section_inspector.html:17-18` (`data-r4-tab="basic"/"advanced"`), `activateTab()` (`r4_editor.js:186-193`) | EXISTS & REUSE | tested: `test_r4_inspector.py:260,356,401,416-466` | Reuse pattern for Showcase and all new Phase-5 section settings |
| 10 | Global vs section scope clarity | Structural split exists (Global Design panel vs per-section Inspector are mutually exclusive) but no inline "this is global/local" label on individual controls | EXISTS BUT NEEDS REPAIR | `r4_editor.js:345,1130-1281` | UI labeling pass, not a new architecture |
| 11 | Sparse local appearance override | `resolve_section_appearance()` (`section_appearance_service.py:15-30`) — overrides only `font`/`type_scale` today, inherits everything else | EXISTS & REUSE (typography-only today) | `settings_schema.py:333-392` | Extend the same sparse-override pattern to color/image/background per Onboarding Charter §12 — do not build a new override mechanism |
| 12 | Inherit/reset behavior | `enabled` flag on the override + `storefront_section_field_reset()`/`reset_section_to_baseline()` | EXISTS & REUSE | `views.py:2266-2293`; `preset_service.py:48-76` (typed errors) | Reuse |
| 13 | Media/background editing per section | Backend + legacy UI exist (`_background_picker_context`, `views.py:1080-1081`); R4 only links out to legacy media management | EXISTS BUT NEEDS REPAIR | `r4/partials/section_inspector_media_only.html:18-22` | Port the existing picker into an R4 `settings_field.html` field type, same pattern already used for the resource picker and typography override |
| 14 | Device preview (desktop/tablet/mobile) | Exists in legacy `editor.html:120` (`sfb-v3-device-switcher`); absent from R4 | EXISTS BUT NEEDS REPAIR | grepped, no matches in `r4/editor.html`/`r4_editor.js`/`r4_editor.css` | Port the existing switcher + CSS/Alpine wiring into R4; the underlying iframe it resizes is already shared |

**Summary: 8 EXISTS & REUSE, 4 EXISTS BUT NEEDS REPAIR, 2 MISSING & BUILD.** The two missing items
(merchant-data preview, general candidate-preview mechanism) are the load-bearing gap for the entire
Onboarding Charter "see first, then compare with your own data" flow — everything else it depends on
already exists.

## 6. Template-DNA / Design-Lab (50-Template DNA Charter §2-§11)

| # | Item | Status | Canonical owner if it exists |
|---|---|---|---|
| 1 | Template DNA definition | EXISTS & REUSE | `StoreAppearanceManifest` (`storefront_appearance/contracts.py:149-165`) + `LayoutPresetDefinition` |
| 2 | Component variant selections | PARTIAL | header/footer/bottom_nav/motion: write-time reconciled (`appearance_authority_service.py:171-227`). hero/product_view/card/badge: **render-time overlay only**, no merchant-facing write-time selector UI yet |
| 3 | Section recipes | EXISTS & REUSE | `LayoutPresetDefinition.pages`/`PresetSectionEntry` |
| 4 | Palette | EXISTS & REUSE | `appearance_registry.py` + `default_palette_slug`, merchant-editable via R4 |
| 5 | Typography | EXISTS & REUSE | `font`/`type_scale` fields, merchant-editable |
| 6 | Density | EXISTS & REUSE | `density` field, same mechanism |
| 7 | Content Width | EXISTS & REUSE | `content_width` field (structural, never Template-gated) |
| 8 | Radius | EXISTS & REUSE | `radius`/`button_radius` fields |
| 9 | Theme Overlay (seasonal/campaign) | **MISSING & BUILD** | No owner. Not to be confused with the existing plain palette-color-override layer — no `campaign_overlay`/`occasion_overlay` symbol exists anywhere |
| 10 | Theme Intensity | **MISSING & BUILD** | No owner, no symbol found |
| 11 | Random Mix | **MISSING & BUILD** | No owner; explicitly deferred by the A8 implementation plan and every convergence-program final gate to date |
| 12 | Randomize One | **MISSING & BUILD** | No owner |
| 13 | Locks (per-family DNA lock) | **MISSING & BUILD** | No owner — do not confuse with the existing **structural** `is_locked` field on `StorefrontSection`/`StorefrontContainer` (`models.py:709,838`), which blocks structural remove/move, not DNA randomization |
| 14 | Reset DNA | EXISTS & REUSE | `preset_service.reset_storefront_to_baseline()` — resets to the originally-applied recipe's own baseline |
| 15 | Remove Theme | **MISSING & BUILD** | No owner; distinct from Reset DNA (there's no "return to themeless" operation) |
| 16 | Compare with Base | **MISSING & BUILD** | No owner; the underlying data (`draft.template_baseline_snapshot`) already exists — only the compare/diff UI is missing |
| 17 | Desktop/Tablet/Mobile Preview (merchant-facing) | **MISSING & BUILD** | No owner in R4 (exists in legacy `editor.html:120` — see §5 item 14, same gap counted once); what exists is automated QA-only viewport coverage (`tools/storefront_builder_r4_qa/run.mjs`), not a merchant Builder feature |

**Summary: 9 EXISTS & REUSE (one partial), 7 MISSING & BUILD**, plus the merchant-facing device preview
already counted in §5. This is the largest concentration of genuinely new work in the whole Phase-5
scope — Theme Overlay, Random Mix, Locks, Compare-with-Base, Remove Theme all need real design/owner
decisions before implementation, per the charter's own instruction not to invent a new persistence
layer for them.

## 7. 67-family design capability inventory

See `docs/qa_evidence/storefront_design_engine/phase5/67_family_production_map.md` for the full
per-family table. Summary: **44 EXISTS & REUSE, 6 EXISTS BUT NEEDS REPAIR-EXPANSION, 17 MISSING &
BUILD** (of 67). The pre-Phase-4-closure "ALL 18 product-facing families FROZEN" verdict in
`final_closure_pack/07` is superseded for the specific capabilities Phase 7/8 of the storefront_builder
v2 program touched (R4 schema coverage grew from 4 to 18 of 36 section types; card/layout settings;
header/footer composability) — but that program's own status is `OWNER_HEAVY_GATE_PENDING`, not a final
production certification either.

## 8. Rasti Mode Demo store

See `docs/qa_evidence/storefront_design_engine/phase5/demo_store_inventory.md` for the full audit.
Summary: **EXISTS & REUSE** — mature, idempotent, tenant-isolated, test-covered. All nine Onboarding
Charter target counts (50 products / 10 categories / 6 brands / 150 images / 206 variants on 41
products / 6 collections / 4 hero / 6 banners / 10 story items) match exactly, verified by reading the
seed source directly. Two real gaps: no deliberate long-Persian-text stress fixture data, and no
deliberate missing-media/placeholder fixture state (both needed for Charter §20's empty/loading/failure
state requirements).

## 9. Read-only visual baseline

Full findings: scratchpad audit report (not committed — this is a summary; see §11 for why the raw
report isn't reproduced verbatim in the repo). Inspected Home/PLP/PDP/Cart at Desktop 1440×900,
Tablet 768×1024 (Home only — time-boxed), Mobile 390×844, against the project's own seeded QA fixture
(`rastisi-fashion-test`, via `seed_rastisi_fashion_demo` — a different, non-canonical QA store from
`rasti-mode-demo`, but rendered through the same shared renderer, so the findings below are valid
evidence of current production CSS/template behavior).

**Strongest reusable work:** PDP is the most complete, coherent template (gallery → buy box → trust
row → tabs → related products); the shared product-card component with a consistent badge/price
system; carousel controls have real accessible names (not icon-only); PLP's filter sidebar collapses
cleanly to a disclosure control on mobile; RTL execution is genuinely correct throughout (not a
mirrored LTR layout) — logo/nav/breadcrumbs/pagination all read right-to-left correctly.

**Visual debt (current-state observation, not a repair task):**
- Saturated, semantically-unmapped rainbow section borders on Home (red/green/orange/navy in sequence
  with no visible meaning).
- Inconsistent pink/blue card-background tinting that doesn't map to badge meaning.
- Blank/empty bands between sections at tablet/mobile widths — looks like a widget failing to render
  rather than being cleanly hidden; needs an engineer's look at the markup, not assumed to be pure CSS.
- **PDP content tabs overflow their container on mobile (390px)**, confirmed via computed layout: the
  third tab ("نظرات کاربران"/Reviews) renders off-screen-left with no scroll affordance.
- PLP pagination wraps awkwardly on mobile instead of collapsing to a condensed pattern.
- No visible search entry point in the mobile header (desktop has a persistent search bar).
- Footer trust/payment badges are literal text placeholders ("CARD"/"PAY"/etc.) — expected for demo
  data, the only part that reads as obviously unfinished.
- Focus rings exist (not suppressed) but are low-contrast against the green header — sampled one tab
  stop only.

**Coverage gaps in this baseline pass (explicitly not "clean" results):** Tablet PLP/PDP/Cart not
captured (time-boxed); populated-cart state not captured (mutation caution); LTR rendering not
separately verified.

## 10. Product Owner decision points carried forward from prior audits (not resolved by Task 0)

These are pre-existing, still-open decision points from `docs/architecture_audits/final_closure_pack/07-master-current-state-blueprint.md`
(D01-D12) that Phase-5 planning should be aware of but that Task 0 does not resolve — they require
Product Owner choice, not more code discovery:
- D01/D02 (precedence: Template → Store → Page → Section; local vs global override) — directly relevant
  to the Onboarding Charter's "sparse local override, clear scope" requirement (§5 items 10-11 above).
- D04 (should Page Override be a real capability) — relevant if Phase-5 Showcase needs page-scoped
  appearance.
- D07 (are MegaHeader/MegaMenu/MegaFooter real independent families) — directly relevant to 67-family
  item MM (Mega Menu), currently a no-op virtual variant only.

## 11. What this document deliberately does not contain

Full per-file evidence trails for every claim above live in the six sub-audit reports produced during
this session (not committed to the repository — they are scratch research artifacts). This document is
the synthesized, cross-checked record; anyone needing the raw file:line trail for a specific claim
should re-run the equivalent Graphify query / source read rather than expect a second copy of the same
evidence to be checked into `docs/qa_evidence/`.
