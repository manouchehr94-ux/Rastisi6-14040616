# Phase 4 — Builder & Legacy Convergence — Implementation Plan

**Date:** 2026-09-08
**Repository:** `manouchehr94-ux/Rastisi6-14040616`
**Working branch:** `feature/phase4-builder-legacy-convergence`
**Created from:** `969a9b411ca712928c2bf31416bdde2ee8aaabb5` (Phase-4 architecture audit commit; parent
`185166a138e47c012b3af7f53ea6bcb94fb84bd0`, Phase-3 final)
**Start safety ref:** `backup/rastisi6-phase4-start-20260908` == `969a9b411ca712928c2bf31416bdde2ee8aaabb5`
**`main`:** must remain `973c1dc00bacb6f2f7d2604fa3880bb4d6250579` throughout — verified unchanged
at plan time.

**Status:** DRAFT — pending fresh review (SPEC COVERAGE PASS / ARCHITECTURE PASS / no unresolved
CRITICAL or IMPORTANT) before Task 1 begins.

**Governing documents (binding, in this order when in conflict):** the Master Execution Prompt's
Rulings A–N (restated in full in `phase4_architecture_audit.md`'s companion conversation and
summarized inline below wherever a task depends on one) > the 5-phase convergence spec
(`2026-09-05-storefront-appearance-convergence-5-phase-design.md`) > `phase4_architecture_audit.md`
> older specs/plans (context only, several explicitly superseded — see audit §5).

---

## 0. Recount of the section registry (re-derived fresh at this SHA, not trusted from the audit)

`apps/storefront_builder/section_registry.py` — grep for `SectionDefinition(` keys at module
scope confirms **exactly 36 registered section types**, matching the audit's §7 count (no drift
since the audit commit, as expected — same SHA lineage, no production edits between audit and
this plan). Every one of the 36 is classified below into exactly one Phase-4 disposition; none is
omitted.

Disposition legend:
- **MIGRATE** — real, cross-page-eligible, needs full Phase-4 vertical (CSS completeness where
  flagged, schema/ResourceSource where missing, browser certification).
- **CERTIFY-ONLY** — already migrated (Phase-3 Brand/Collection) or already canonical
  (Header/Footer/BottomNav/Motion) — Phase 4 re-certifies as a regression sentinel, no new work.
- **CONTEXT-AWARE-DOMAIN-OWNED** — mandatory, page-type-restricted, route-context is the
  authority; no independent ResourceSource/selector is invented for these.
- **HOME-ONLY** — restricted to `page_types=[HOME]` by design; low priority, no cross-page CSS
  risk.
- **MARKETING-ALIAS** — not a distinct implementation; documented as an alias, never counted as
  a separate family again.
- **TEMPORARY-ADAPTER** — a real compatibility bridge that must keep working but is not being
  converged further in Phase 4 (reserved for the four Store-Appearance selector families below;
  no section itself lands here).
- **LEGACY-RETIRE** — a superseded/hidden section kept only for backward compatibility; a Task-9
  retirement candidate.

| # | key | disposition | why | Phase-4 action |
|---|---|---|---|---|
| 1 | `hero_banner` | MIGRATE | REAL, 6 variants, all 6 page_types, has legacy write path; default `overlay` variant is 100% `home.css`-dependent | Task 5 CSS fix (Group A); Task 6 Group A full vertical (already SettingsSchema-enabled) |
| 2 | `fashion_lifestyle_hero` | HOME-ONLY | static-content, `page_types=[HOME]` | none required; documented as Home-only by design |
| 3 | `image_slider` | MIGRATE | shares `hero_banner`'s context/CSS root, all 6 page_types | Task 5 fix grouped with `hero_banner` (identical root cause); Task 6 Group A |
| 4 | `single_banner` | MIGRATE | REAL, all 6, `.promo-dark` Home-only CSS | Task 5 Group B; Task 6 |
| 5 | `multi_banner` | MIGRATE | REAL, all 6, `.promo-grid--*` Home-only CSS | Task 5 Group B; Task 6 |
| 6 | `category_grid` | MIGRATE | REAL, catalog-owned, 11 display_modes, 10/11 Home-only CSS (shared `.tile` core) | Task 5 Group C; Task 6 |
| 7 | `featured_products` | MARKETING-ALIAS | delegates entirely to `_newest_products_context`, no distinct field | document as alias; never re-counted as distinct |
| 8 | `newest_products` | MIGRATE | REAL, catalog | Task 6 Group B (simple auto-source) |
| 9 | `best_sellers` | MIGRATE | REAL, orders/catalog-derived | Task 6 Group B |
| 10 | `discounted_products` | MIGRATE | REAL, catalog | Task 6 Group B |
| 11 | `amazing_offers` | MIGRATE | REAL, no UI write path today, Home-only CSS | Task 5; needs a write path before Task 6 certification |
| 12 | `brand_carousel` | CERTIFY-ONLY | Phase-3 certified (schema+ResourceSource+browser) | Task 4/6 regression sentinel only; `beauty_tabs` cosmetic CSS gap fixed alongside Task 5 |
| 13 | `collection_tiles` | CERTIFY-ONLY | Phase-3 certified | Task 4/6 regression sentinel only |
| 14 | `promo_cards` | MIGRATE | REAL, catalog, Home-only CSS | Task 5 Group D; Task 6 |
| 15 | `rich_text` | MIGRATE | REAL, legacy schema exists, inline-styled (CSS-safe) | Task 6 (R4 schema + cert; no CSS fix needed) |
| 16 | `image_text` | MIGRATE | REAL, 2 variants, Home-only CSS | Task 5 Group D; Task 6 |
| 17 | `blog_posts` | MIGRATE | REAL, blog-owned, Home-only CSS | Task 5 Group D; Task 6 |
| 18 | `product_section` | MIGRATE | REAL, R4-schema+ResourceSource-enabled, `campaign_band`/spotlight modes Home-only CSS | Task 5 Group A; Task 6 Group A (strong candidate) |
| 19 | `catalog_product_wall` | HOME-ONLY | Ready-Template-oriented, `page_types=[HOME]` | none required |
| 20 | `trust_features` | MIGRATE | REAL, no UI write path, Home-only CSS | Task 5 Group E; Task 6 |
| 21 | `quick_links` | MIGRATE | REAL, content-owned (Menu), CSS-safe | Task 6 (no CSS fix needed) |
| 22 | `faq` | MIGRATE | REAL, no UI write path, Home-only CSS | Task 5 Group E; Task 6 |
| 23 | `testimonials` | MIGRATE | REAL, no UI write path, Home-only CSS | Task 5 Group E; Task 6 |
| 24 | `video_section` | MIGRATE | REAL, `.video-embed-wrap` Home-only CSS | Task 5 Group E; Task 6 |
| 25 | `story_rail` | MIGRATE | REAL, content-owned, CSS-safe (global `tokens.css`), no write path | Task 6 (add write path; no CSS fix needed) |
| 26 | `newsletter` | MIGRATE | REAL, inline-styled (CSS-safe), no context builder (falls to `_static_context`) | Task 6 |
| 27 | `announcement_bar` | LEGACY-RETIRE | `hidden_from_library`, superseded by header notification bar | Task 9 candidate: inventory callers/routes/templates/tests before any deletion decision |
| 28 | `product_main` | CONTEXT-AWARE-DOMAIN-OWNED | mandatory, product_detail only | Task 3B page-type generalization only; no ResourceSource invented |
| 29 | `product_description` | CONTEXT-AWARE-DOMAIN-OWNED | mandatory, product_detail only | same |
| 30 | `product_video` | CONTEXT-AWARE-DOMAIN-OWNED | product_detail only | same |
| 31 | `related_products` | CONTEXT-AWARE-DOMAIN-OWNED | product_detail only | same |
| 32 | `product_listing` | CONTEXT-AWARE-DOMAIN-OWNED | mandatory, listing+search | Task 3E HTMX fragment context-propagation fix |
| 33 | `collection_header` | CONTEXT-AWARE-DOMAIN-OWNED | collection detail only | Task 3D Collection Index/Detail boundary test |
| 34 | `collection_products` | CONTEXT-AWARE-DOMAIN-OWNED | mandatory, collection detail only | Task 3D |
| 35 | `cart_items` | CONTEXT-AWARE-DOMAIN-OWNED | mandatory, cart only | none beyond existing coverage |
| 36 | `cart_summary` | CONTEXT-AWARE-DOMAIN-OWNED | mandatory, cart only | none beyond existing coverage |

**Disposition totals:** MIGRATE = 21, CERTIFY-ONLY = 2, CONTEXT-AWARE-DOMAIN-OWNED = 9,
HOME-ONLY = 2, MARKETING-ALIAS = 1, LEGACY-RETIRE = 1, TEMPORARY-ADAPTER = 0 (no section itself is
an adapter). **21 + 2 + 9 + 2 + 1 + 1 = 36.** No row left unclassified.

### Global non-section families (inventoried per Task 0's instruction)

| Family | Disposition | Current state | Phase-4 action |
|---|---|---|---|
| Header | CERTIFY-ONLY | Canonical via `appearance_authority_service.apply_header_variant` ↔ `global_region_registry`; converged | Regression sentinel only |
| Footer | CERTIFY-ONLY | Canonical via `apply_footer_variant`; converged | Regression sentinel only |
| Mobile Bottom Navigation | CERTIFY-ONLY | Same pattern (`bottom_nav` family), converged | Regression sentinel only |
| Motion | CERTIFY-ONLY | Genuinely synchronized via `appearance_authority_service` | Regression sentinel only |
| `hero` (Store Appearance family) | TEMPORARY-ADAPTER | Render-time overlay only (`variant_explicit` guard), no write-time reconciliation, no merchant selector UI exists | Task 6 Group F: build write/effective-state reconciliation only; **no new selector UI** (Ruling J) |
| `product_view` | TEMPORARY-ADAPTER | Same pattern | Task 6 Group F, same constraint |
| `card` | TEMPORARY-ADAPTER | Same pattern | Task 6 Group F, same constraint |
| `badge` | TEMPORARY-ADAPTER | Same pattern | Task 6 Group F, same constraint |

---

## 1. Task list (checkboxes; execute in order; STOP conditions per task honored verbatim)

### Task 0 — Plan + baseline (this document + evidence files)
- [x] Verify branch/SHA/backup preconditions (done — see repo state above)
- [x] Recount section registry fresh (done — §0 above, 36/36 classified)
- [x] Create `phase4/baseline.md`, `phase4/execution_ledger.md`, `phase4/family_certification_matrix.md`, `phase4/legacy_disposition.md`
- [ ] Run exact Phase-3 baseline commands (Run A/B/C) verbatim — in progress
- [ ] Fresh-review this plan (SPEC COVERAGE PASS, ARCHITECTURE PASS, 0 unresolved CRITICAL/IMPORTANT)
- [ ] Commit `docs: plan phase4 builder and legacy convergence`; push

### Task 1 — Appearance + Ready-Template authority convergence
RED first: (1) non-Ready preset apply cannot erase `store_appearance` manifest; (2) Ready
Template transformation uses `apply_ready_template_appearance`; (3) unrelated appearance state
survives managed-field writes; (4) legacy+R4 Template Apply resolve through one orchestration;
(5) internal/seed use (`golden_reference_service`) cannot become a second merchant-facing
authority. Fix `preset_service.apply_preset`/`reset_appearance_setting_to_baseline` to delegate to
`appearance_authority_service`. Evidence: `phase4/task1_authority.md`. Commit:
`fix: converge storefront appearance and template authority`.

### Task 2 — ResourceSource read/write + tenant ownership convergence
RED for the `category_ids` ownership divergence (legacy validates it, R4 no-ops). Keep
`resource_source.py` DB-free. One shared DB-backed ownership boundary for legacy+R4. Evidence:
`phase4/task2_resource_source.md`. Commit: `fix: unify storefront resource source semantics and ownership`.

### Task 3 — Page Appearance + R4 non-Home + live entry (3A–3E, one wave)
- 3A: real dashboard entry point for R4, existing permissions only.
- 3B: generalize `section_structure_service`/`r4_views`/R4 editor away from Home-only; one
  validated PageType input; page switcher for Home/Listing/Search/Product Detail/Collection
  Detail/Cart.
- 3C: implement Page Appearance precedence tier (Template DNA→Store Global→Page→Section); minimal
  forward migration only if no existing canonical JSON surface can hold it cleanly (Ruling F).
- 3D: Collection PageType == Collection Detail only; Collection Index stays a domain-owned direct
  listing page with global Header/Footer/Appearance (Ruling L); explicit tests for the boundary.
- 3E: fix Listing/Search HTMX fragment context gap using the same canonical context builder.
Evidence: `phase4/task3_non_home_page_appearance.md`. Commits: `feat: generalize r4 builder across storefront pages`, `feat: add canonical page appearance inheritance`.

### Task 4 — Generalize the certified R4 QA harness (before broad family certification)
Extract the duplicated Brand/Collection browser assertion block in `run.mjs` into one shared
parameterized helper; must preserve Brand 45/45 and Collection 36/36. Evidence:
`phase4/task4_qa_harness.md`. Commit: `test: generalize storefront family browser certification harness`.

### Task 5 — Cross-page CSS completeness (grouped by shared CSS root)
- Group A: `hero_banner` default `overlay` + `image_slider` + `product_section` campaign/spotlight
- Group B: `single_banner` + `multi_banner`
- Group C: `category_grid` (10/11 modes)
- Group D: `promo_cards` + `image_text` + `blog_posts`
- Group E: `faq` + `testimonials` + `trust_features` + `video_section`
- Plus: `brand_carousel` `beauty_tabs` cosmetic gap
Each group: browser RED → exact missing computed style → smallest scoped fix in
`storefront_builder.css` → prove Home unchanged → prove non-Home envelopes → desktop/tablet/mobile
→ review → bounded commit. Evidence: `phase4/task5_cross_page_css.md`.

### Task 6 — Converge every required product-facing family (per Task 0 disposition)
Groups A–F per the Master Prompt's suggested order; Brand/Collection re-run as regression
sentinels throughout; group F is reconciliation-only, no new selector UI (Ruling J). Update
`phase4/family_certification_matrix.md` — no row left "unknown." Evidence:
`phase4/task6_family_convergence.md`. One commit per independently reviewable family/group.

### Task 7 — R4 composition/media/recovery parity
Container/Cell/Row/multi-column/arbitrary placement/multi-block Cells/container settings/
add-remove-duplicate-move/toggle-collapse-lock/discard/restore/history/granular baseline
reset/section-scoped media CRUD. Reuse `container_service`, `layout_service`,
`edit_history_service`, media models — no duplication. STOP (report, do not auto-migrate) if the
existing persisted model cannot represent required parity. Evidence: `phase4/task7_r4_parity.md`.
Commit family: `feat: complete r4 storefront composition and recovery parity`.

### Task 8 — Safe Template Switch + final lifecycle hardening (8A–8C)
- 8A: RED first, design fresh (not the stale 2026-09-03 plan) using `stable_id`,
  `template_slot_key`, `template_provenance`, `template_baseline_snapshot`; TEMPLATE-OWNED vs.
  MERCHANT-OWNED vs. BUSINESS-DOMAIN state contract.
- 8B: one merchant-facing Template orchestration for legacy+R4 (confirmation, checkpoint,
  base_revision, Draft-only, atomicity, history, rollback).
- 8C: close 3 lifecycle drift items — legacy structure/container lock parity; live legacy publish
  `base_revision` wiring; legacy mutation atomicity drift. Re-run Phase-2 safety suites.
Evidence: `phase4/task8_template_lifecycle.md`. Commits: `fix: preserve merchant state across storefront template switching`, `fix: close remaining storefront lifecycle parity gaps`.

### Task 9 — Evidence-based legacy retirement
Only after Tasks 1–8 PASS. Safety backup `backup/rastisi6-phase4-pre-legacy-retirement-20260908`
before first deletion commit. Candidates: duplicate settings writers, duplicate structure
mutation views, duplicate toggle/collapse/lock views, duplicate discard/restore/history paths,
duplicate granular reset paths, duplicate media CRUD UI paths, legacy merchant editor shell,
internal/industry layout-preset route if redundant (Ruling K), `announcement_bar` if caller
evidence proves safe. Update `phase4/legacy_disposition.md`. Evidence:
`phase4/task9_legacy_retirement.md`. Small bounded deletion commits only.

### Task 10 — Final Phase-4 certification
No fixes inside this task. Full 18-item audit, fresh Run A/B/C + all Phase-4 suites + Phase-2/3
regression suites, final browser certification (3 viewports, 6 page types), fresh independent
review (11 PASS line items, 0 CRITICAL/IMPORTANT), `phase4/final_gate.md`, final commit
`docs: close storefront builder and legacy convergence phase4`, `backup/rastisi6-phase4-final-20260908`, final response report.

---

## 2. Global constraints carried into every task

No second renderer/lifecycle/persistence model/ResourceSource system/Ready-Template authority/
merchant editor. `resource_source.py` stays DB-free. No Phase-5 visual/design expansion. No
historical-data migration. Migration history never rewritten — only normal forward migrations,
each requiring proof + RED test + minimal migration + rollback review + evidence, and only where
Ruling C/F explicitly authorizes one. Business domain ownership (Catalog/Cart/Orders/auth/tenant)
unchanged. STOP conditions per the Master Prompt are honored verbatim at every task, not just at
gates.
