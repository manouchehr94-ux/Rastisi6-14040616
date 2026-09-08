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
- [x] Run exact Phase-3 baseline commands (Run A/B/C) verbatim — done, see `phase4/baseline.md`
  (932 combined executions, 927 pass, 3 fail + 1 error + 1 skip, identical signatures to Phase-3's
  final gate — no regression)
- [x] Fresh-review this plan (SPEC COVERAGE PASS, ARCHITECTURE PASS, 0 unresolved CRITICAL; 5
  IMPORTANT found and resolved in this revision — see the review note at the end of this document)
- [ ] Commit fix-up `docs: plan phase4 builder and legacy convergence` (follow-up commit
  incorporating the review's fixes); push

**Remote note (resolves a review MINOR):** this repository has only one configured remote,
`origin` (`git remote -v` confirms no `rastisi5` remote exists here — that name is legacy-workspace
guidance from a different repo). Every Phase 1–4 master prompt in this program has explicitly
named `origin/feature/...` push targets by exact branch name, which is the "explicitly requested"
override CLAUDE.md's own `origin` caution allows. All Phase-4 pushes continue that established,
explicitly-authorized pattern.

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
`resource_source.py` DB-free. One shared DB-backed ownership boundary for legacy+R4, covering
manual Product/Brand/Collection/Category ownership, product by_category/by_brand/by_collection,
automatic ID-free rules, foreign Store, missing ID, inactive/visibility semantics, and
unrelated-field-edit-must-not-fail-on-dormant-old-resource-state. Evidence:
`phase4/task2_resource_source.md`. Commit: `fix: unify storefront resource source semantics and ownership`.

**SECURITY STOP CONDITION (carried forward explicitly from the divergence itself, per CLAUDE.md's
"preserve tenant isolation" instruction and Ruling M):** if unifying the two ownership-check
implementations reveals that legacy's `category_ids` validation was masking a real,
currently-exploitable cross-tenant exposure in R4 (i.e., R4's `category` no-op lets a merchant
reference another Store's Category today, not just a theoretical gap) — STOP immediately, do not
fold this into the routine unification fix, and record it as a SECURITY RED finding for
Architect/Product-Owner review before writing the fix, per the Master Prompt's global STOP
conditions ("cross-tenant exposure discovered").

### Task 3 — Page Appearance + R4 non-Home + live entry (3A–3E, one wave)
- 3A: real dashboard entry point for R4, existing permissions only.
- 3B: generalize `section_structure_service`/`r4_views`/R4 editor away from Home-only; one
  validated PageType input; page switcher for Home/Listing/Search/Product Detail/Collection
  Detail/Cart.
- 3C: implement the Page Appearance tier per Ruling F's full contract, not just its precedence
  order — precedence Template DNA→Store Global→Page→**Section/Component** (stronger than Store
  Global, weaker than Section/Component); bounded, typed, sparse override only (**no arbitrary CSS
  editing**); Draft/Published-lifecycle-aware; tenant-safe; canonical (single write contract, no
  second appearance/lifecycle engine); reusable identically by **both** Preview and Public. First
  investigate whether an existing versioned canonical JSON/state surface (e.g. the
  `StorefrontLayoutVersion` JSON-config idiom the audit's §14 identifies) can hold it cleanly; only
  if none can, a minimal forward migration is authorized for this specific approved requirement —
  record the storage decision and why in the task's evidence file.
- 3D: Collection PageType == Collection Detail only; Collection Index stays a domain-owned direct
  listing page with global Header/Footer/Appearance (Ruling L); explicit tests for the boundary.
- 3E: fix Listing/Search HTMX fragment context gap using the same canonical context builder.
Evidence: `phase4/task3_non_home_page_appearance.md`. Commits: `feat: generalize r4 builder across storefront pages`, `feat: add canonical page appearance inheritance`.

### Task 4 — Generalize the certified R4 QA harness (before broad family certification)
Three required generalizations (all three, not just the first — the audit's §21 requires all
before certifying a third family, and Task 6 depends on this harness for ~19 more families):
1. Extract the duplicated Brand/Collection browser assertion block in `run.mjs` into one shared
   parameterized helper covering every listed assertion category (computed display,
   gridTemplateColumns, gap, overflowX, background, padding, typography, objectFit, image decode,
   fallback, RTL, keyboard focus, native scrolling, document overflow, asset duplication,
   Preview/Public, fragment, network/console/page errors, DB restore).
2. Restructure `manifest.phase3`'s single boolean into a real per-family gate-registration loop so
   new families register their own gate instead of piggybacking on the Brand/Collection flag.
3. Backfill the R4-schema-enable guard test across all non-schema-enabled families (today only
   `brand_carousel`/`collection_tiles` — 2 of 31 non-context-aware MIGRATE families — are asserted;
   every MIGRATE family gaining a schema in Task 6 needs this guard from the start).
Must preserve Brand 45/45 and Collection 36/36; must not weaken assertions to make new families
pass. Evidence: `phase4/task4_qa_harness.md`. Commit: `test: generalize storefront family browser certification harness`.

### Task 5 — Cross-page CSS completeness (grouped by shared CSS root)
- Group A: `hero_banner` default `overlay` + `image_slider` + `product_section` campaign/spotlight
  + `amazing_offers` (shares the same promo-card CSS root as `product_section`'s spotlight mode —
  re-verify this grouping against the actual computed styles at implementation time; split out if
  the root causes turn out unrelated)
- Group B: `single_banner` + `multi_banner`
- Group C: `category_grid` (10/11 modes)
- Group D: `promo_cards` + `image_text` + `blog_posts`
- Group E: `faq` + `testimonials` + `trust_features` + `video_section`
- Plus: `brand_carousel` `beauty_tabs` cosmetic gap
Each group: browser RED → exact missing computed style → smallest scoped fix in
`storefront_builder.css` → prove Home unchanged → prove non-Home envelopes → desktop/tablet/mobile
→ review → bounded commit. Evidence: `phase4/task5_cross_page_css.md`.

### Task 6 — Converge every required product-facing family (per Task 0 disposition)
Not "add SettingsSchema to all 36 blindly" — each family proves the full vertical (Business
Domain→canonical Data/Resource contract→typed content/settings→common Appearance capabilities→
component-specific capabilities→variant→canonical mutation→Draft/Published→shared renderer→full
page→fragment where applicable→CSS/JS/media→Preview/Public→desktop/tablet/mobile) according to its
own Task-0 disposition — a family may legitimately end up typed-SettingsSchema-editable,
ResourceSource-driven, context-aware/domain-owned with no independent source selector, or
fixed/static with an explicit capability contract, but none may remain unclassified. Brand
(`brand_carousel`) and Collection (`collection_tiles`) are re-run as regression sentinels
throughout every group below, not migrated again.

Internal order (defined here concretely — the 21 MIGRATE families plus the 4 global
Store-Appearance selector families, none omitted or double-scheduled):
- **Group A** (already strongest — has schema and/or ResourceSource today): `hero_banner`,
  `image_slider` (shares `hero_banner`'s context, migrated alongside it), `product_section`,
  `rich_text`.
- **Group B** (simple auto-source catalog families, no independent selector needed beyond the
  existing implicit query): `newest_products`, `best_sellers`, `discounted_products`,
  `promo_cards`.
- **Group C** (layout/banner families needing schema + resource contract built fresh):
  `single_banner`, `multi_banner`, `category_grid`, `image_text`, `blog_posts`.
- **Group D** (currently no UI write path at all — add a settings write path, typically
  legacy-form + R4-schema together, before certifying): `trust_features`, `faq`, `testimonials`,
  `video_section`, `story_rail`, `quick_links`, `newsletter`, `amazing_offers`.
- **Group E** (context-aware page sections — route context, not a merchant-facing selector, is the
  authority; certify the route-context contract instead of inventing a ResourceSource):
  `product_listing`, `collection_header`, `collection_products` (the always-mandatory,
  already-safe-by-construction context-aware sections — `product_main`, `product_description`,
  `product_video`, `related_products`, `cart_items`, `cart_summary` — need no further Group-E work
  beyond the boundary/fragment fixes already scheduled in Task 3D/3E).
- **Group F** (global regions/Store Appearance — reconciliation only, per Ruling J **no new
  merchant-facing selector UI**): write/effective-state reconciliation for the `hero`,
  `product_view`, `card`, `badge` families, mirroring the existing `apply_header_variant`-style
  pattern.
- **Excluded from Group work by disposition** (documented, not migrated): `fashion_lifestyle_hero`,
  `catalog_product_wall` (HOME-ONLY); `featured_products` (MARKETING-ALIAS); `announcement_bar`
  (LEGACY-RETIRE, handled in Task 9).

Update `phase4/family_certification_matrix.md` after each group — no row left "unknown" at the
Phase-4 final gate. Evidence: `phase4/task6_family_convergence.md`. One commit per independently
reviewable family/group — no mega-commit.

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
No production/test fix allowed inside this task — a defect found here returns to its owning task
with RED evidence, it is not patched in place.

**The 18-item final audit** (each item re-derived from current code/tests at Task-10 time, not
carried forward from earlier task claims):
1. Recount the section registry fresh; confirm the count matches what Task 10 certifies.
2. Every one of the 36 (or newly recounted) sections has a final Task-0-style disposition — none
   left unclassified.
3. Every MIGRATE family uses the approved canonical contracts (schema/ResourceSource/appearance)
   with no bespoke one-off mechanism.
4. Non-Home Builder pages (Listing, Search, Product Detail, Collection Detail, Cart) use the same
   canonical R4 architecture as Home — no Home-only special case remains in
   `section_structure_service`/`r4_views`/the R4 editor JS.
5. Page Appearance precedence (Template DNA→Store Global→Page→Section/Component) is proven end to
   end on at least one non-trivial override at each tier.
6. Header/Footer/Bottom-Nav/Motion manifest and legacy-JSON mirrors remain canonical and
   single-writer.
7. `resource_source.py` is the single source of both read and write ResourceSource semantics; no
   read path re-derives it independently.
8. Ready Template application has exactly one merchant-facing orchestration; legacy and R4 both
   delegate to it.
9. Template Switch preserves merchant-owned content/media/domain-selection state per the Task-8A
   contract; TEMPLATE-OWNED vs. MERCHANT-OWNED vs. BUSINESS-DOMAIN is explicit and tested.
10. R4 has Container/Cell/Row composition, media CRUD, and recovery (discard/restore/history/
    granular reset) parity with legacy.
11. Every legacy duplicate write authority identified in `legacy_disposition.md` is either retired
    or reduced to a thin, non-independent-write adapter with a documented removal owner.
12. Exactly one renderer (`render_service.build_page_render_items`) and one lifecycle
    (`layout_service`/`edit_history_service`) remain in use anywhere in the domain.
13. No duplicate persistence model exists for any converged concept (Appearance, ResourceSource,
    Ready Template, Page Appearance, Container/Cell/Row).
14. Business domain ownership (Catalog/Cart/Orders/auth/tenant) is unchanged except for the
    explicitly approved Page-Appearance/Ready-Template-orchestration adapters.
15. No Phase-5 visual/design expansion occurred (no new campaigns, seasonal themes, mass
    beautification, or variant-count growth for diversity's own sake).
16. No historical-data migration was added anywhere (consistent with Ruling B).
17. Django migration history was never rewritten/squashed/reset — only normal forward migrations,
    each with its own recorded proof/RED-test/rollback-review evidence, if any were added at all.
18. Cumulative diff from both `185166a138e47c012b3af7f53ea6bcb94fb84bd0` (Phase-3 final) and
    `969a9b411ca712928c2bf31416bdde2ee8aaabb5` (Phase-4 audit) is inspected in full, including any
    migration files, before the final verdict is written.

Run fresh: exact Phase-3 baseline Run A/B/C; all Phase-4 task test modules; Phase-2 safety suites;
Phase-3 Brand/Collection suites; every new family certification suite; Cart suites; page-shell/view
tests; R4 mutation/security tests; Ready Template tests; media reachability tests;
`python manage.py check`; `python manage.py makemigrations --check --dry-run`; `git diff --check`.

**Final browser certification**: the extended R4 QA harness (post-Task-4 generalization), 3
viewports (1440x900 / 768x1024 / 390x844), Home/Product Detail/Listing/Search/Collection
Detail/Cart + the Collection Index companion boundary check; for every migrated family: Draft
Preview→publish→Public→Draft-only change→Public unchanged→restore; computed layout; assets; media;
no-image fallback; broken-image classified separately; RTL; keyboard; native scroll where
relevant; no document overflow; no duplicate CSS/JS; no unexpected console/page/network errors;
real HTMX paths; DB pre/post restore hash match.

**Final independent review** — fresh whole-branch reviewer with no prior task context, against the
5-phase spec, the Phase-4 audit, this plan, actual code, and the cumulative diff. Required verdict
format (all 11 lines must read PASS):
```
SPEC COMPLIANCE: PASS
ARCHITECTURE: PASS
CANONICAL AUTHORITY: PASS
NO PARALLEL ENGINE: PASS
NO PARALLEL WRITER: PASS
R4 FINAL EDITOR: PASS
NON-HOME BUILDER: PASS
FAMILY CONVERGENCE: PASS
LEGACY RETIREMENT: PASS
TENANT/LIFECYCLE SAFETY: PASS
BROWSER CERTIFICATION: PASS
CRITICAL: 0
IMPORTANT: 0
MINOR: <n, only if explicitly non-blocking with a named future owner/reason>
```
Any unresolved CRITICAL or IMPORTANT means PHASE 4 FAILS — no false PASS is written.

Evidence: `docs/qa_evidence/storefront_appearance_convergence/phase4/final_gate.md` (starting/final
SHA, every task commit, backup refs, registry count, family matrix disposition, legacy disposition,
migrations, exact test counts, historical known exceptions, browser counts, DB restore proof, final
architecture map, parallel-authority verdict, reviewer verdict, Phase-5 boundary). Final commit only
after every gate PASSes: `docs: close storefront builder and legacy convergence phase4`; push only
`origin/feature/phase4-builder-legacy-convergence`; create
`backup/rastisi6-phase4-final-20260908`; verify feature branch SHA == final backup SHA; verify the
architecture-audit backup remains `969a9b411ca712928c2bf31416bdde2ee8aaabb5`; verify the Phase-3
backup unchanged; verify `main` remains `973c1dc00bacb6f2f7d2604fa3880bb4d6250579`. No merge, no PR,
Phase 5 not started.

---

## 2. Global constraints carried into every task

No second renderer/lifecycle/persistence model/ResourceSource system/Ready-Template authority/
merchant editor. `resource_source.py` stays DB-free. No Phase-5 visual/design expansion. No
historical-data migration. Migration history never rewritten — only normal forward migrations,
each requiring proof + RED test + minimal migration + rollback review + evidence, and only where
Ruling C/F explicitly authorizes one. Business domain ownership (Catalog/Cart/Orders/auth/tenant)
unchanged. STOP conditions per the Master Prompt are honored verbatim at every task, not just at
gates.
