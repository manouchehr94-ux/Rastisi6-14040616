# Task 7 — complete browser/full-fragment/asset/responsive matrix

## Result: PASS (after one authorized, bounded Task-5 repair round)

Task 7 itself carries **no production authorization**. Its first pass found a real, reproducible
defect in Collection's already-closed Task 5 CSS fix and correctly STOPPED without fixing
production code (per: "If Task 7 reveals a production defect: STOP. Record exact RED evidence and
owning scope. Do NOT silently fix production in Task 7."). That RED checkpoint was committed,
reviewed, and preserved. The Product Owner/Architect then explicitly authorized one narrowly
bounded repair round, scoped to exactly the two files implicated by the evidence. The repair was
applied, independently reviewed twice, and the full Task 7 matrix now passes 36/36 Collection
checks with zero regressions.

### RED checkpoint (preserved, not amended)

- **Commit:** `b3e69147e3681980233cd4c7beac1790e184189d` —
  `test: extend R4 QA harness for task7 matrix; surface collection tile CSS regression`
- **Safety ref:** branch `backup/rastisi6-phase3-task7-red-20260907` == `b3e69147e3681980233cd4c7beac1790e184189d`
  (verified identical, pushed to `origin`)
- This commit's own evidence (`git show b3e69147:docs/qa_evidence/storefront_appearance_convergence/phase3/task7_browser_matrix.md`)
  is the historical FAIL record: 18 `known_red_findings`, full root-cause analysis, two
  independent review rounds on the harness itself. It is **not rewritten** — this document
  supersedes it as the current state, but the RED checkpoint remains permanently readable at that
  SHA and that backup branch.

### Repair commit

- **Commit:** `9fd27f8b089718fcaa338eec8aa1469814b71b79` —
  `fix: restore collection tile layout across public envelopes`
- Production files changed (exactly the two authorized): `apps/storefront_builder/static/css/storefront_builder.css` (Collection-scoped rule only), `apps/cart/templates/cart/cart_detail.html` (one additional `<link>` to an existing, already-used-everywhere-else stylesheet).

### Final certification commit

This document, and the regenerated `browser/` evidence tree, are committed together in the commit
that follows this one in `git log` (subject: `test: certify pilot browser fragment assets and
responsive behavior`) — its SHA is in that commit's own metadata, not repeated here
self-referentially (matching this project's own established convention — see `baseline.md`).

## Authority and scope

- Branch: `feature/phase3-task7-task8`
- Repository: `manouchehr94-ux/Rastisi6-14040616`
- Starting HEAD for this repair round: `b3e69147e3681980233cd4c7beac1790e184189d` (the RED
  checkpoint) — verified as current HEAD, branch correct, worktree clean, `origin/main` still
  `973c1dc00bacb6f2f7d2604fa3880bb4d6250579`, before any repair edit was made.
- Environment: same Claude Code Web sandbox as the RED checkpoint (Python 3.11.15 venv, Django
  5.2.17, Node v22.22.2, Playwright Chromium at `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`)
  — already set up from the RED-checkpoint session, re-verified intact (venv present,
  `playwright-core` installed, `db.sqlite3` present) before the repair.

## Allowed-file audit

**Repair round** — exactly the two files the Architect's authorization named, nothing else:

| File | Change |
|---|---|
| `apps/storefront_builder/static/css/storefront_builder.css` | Added ONE new rule: `.collection-tiles-carousel.tiles-carousel{display:flex;gap:16px;overflow-x:auto;scroll-snap-type:x mandatory;padding-bottom:6px;-webkit-overflow-scrolling:touch}` — the missing PARENT container rule (Task 5's original fix mirrored only the child `.pcard` selector). Uses the exact same effective values as `home.css`'s `.tiles-carousel` base rule (the only other place this declaration set exists), so it is a byte-for-byte no-op on Home. Scoped to the compound selector already used for the child rule — never a bare `.tiles-carousel` override, which `category_grid.html` (an unrelated, non-pilot family) also uses for its own carousel display mode and must not be touched. |
| `apps/cart/templates/cart/cart_detail.html` | Added ONE `<link rel="stylesheet" href="{% static 'css/product_card.css' %}">` to the existing `{% block extra_css %}`, in the same position/order every other envelope's own template already uses (`product_card.css` → page CSS → `storefront_builder.css`). No new stylesheet was created; `product_card.css` already existed and was already loaded on every other public envelope — Cart was the sole exception. |

No renderer, section schema, mutation service, lifecycle, domain model/service, commerce logic,
fragment endpoint, media-ownership code, migration, Brand-family behavior, or Phase 4 code was
touched. `git diff --check` on both files: clean. `python manage.py makemigrations --check
--dry-run`: "No changes detected", run before and after the repair — no migration exists anywhere
in the diff.

**Harness round** (unchanged from the RED checkpoint, not re-described in full here — see commit
`b3e69147` for its own complete allowed-file audit): `apps/storefront_builder/management/commands/qa_storefront_builder_r4.py`, `tools/storefront_builder_r4_qa/run.mjs`, `apps/storefront_builder/tests/test_qa_harness_contract.py`.

## Root cause (as found at the RED checkpoint; now repaired)

1. **Carousel** (5 of 6 envelopes — product_detail, listing, search, collection, cart — ×3
   viewports = 15 of the 18 RED findings): `apps/catalog/static/css/home.css:143` was the ONLY
   place `.tiles-carousel{display:flex;gap:16px;overflow-x:auto;scroll-snap-type:x mandatory;
   padding-bottom:6px;-webkit-overflow-scrolling:touch}` existed. Task 5's original fix
   (`storefront_builder.css`) mirrored only the child `.collection-tiles-carousel.tiles-carousel
   .pcard{flex:0 0 220px;scroll-snap-align:start}` rule — never the PARENT container's
   `display:flex;overflow-x:auto`. `home.css` is deliberately not loaded on non-Home envelopes,
   and `collection_tiles.html` carries no inline fallback (unlike `brand_carousel.html`, which
   does). Net effect: the "carousel" tile_style rendered as a plain block list everywhere except
   Home.
2. **Grid on Cart only** (3 of 18 RED findings): `.grid{display:grid;gap:16px}` and
   `.g4{grid-template-columns:repeat(var(--sfb-grid-density,4),1fr)}` both live in
   `apps/catalog/static/css/product_card.css`, which every other public envelope's own template
   loads via `{% block extra_css %}` — Cart's `cart_detail.html` never did. Net effect: the
   "grid" tile_style also collapsed to a plain block list, but only on Cart.

Both are the same class of defect Task 3 found and fixed for Brand (V06/A06 asset-envelope
mismatch); Task 5's own fix for Collection correctly mirrored the *effective cascade value* for
the nested `.pcard` rule but missed that the *parent* container needed the same treatment, and
never noticed Cart's stylesheet omission because its computed-style assertions didn't exist yet
(Task 5 asserted container-class presence and tile count/order/image-decode, not `display`/
`overflowX` numerically — that gate is new in Task 7).

## Repair verification

Re-confirmed the exact RED (18 findings, same envelopes/viewports/variants as committed at
`b3e69147`) via a fresh harness run *before* touching any file, then applied both fixes above,
then re-ran the full harness against the actual committed evidence path
(`docs/qa_evidence/storefront_appearance_convergence/phase3/browser/`) three times across
iterations (including once immediately after a reviewer round correctly caught that an earlier
verification pass had targeted a scratchpad directory instead of this evidence path — see "Review
findings" below).

**Final run: 16/16 scenarios PASS, 0 known-red findings.**

```
R4 Task 12 result summary: Passed: 16  Failed: 0
```

DB restore: pre/post SHA256 both `7380719816273f29d29837b5085602013f28bb536956b1a37670302f44877ce7`, `match: true` (`browser/db-restore-proof.json`).

### Before → after (computed layout, from `metrics.json:collection.variant_checks`)

| Envelope | Variant | Before (RED) | After (GREEN) |
|---|---|---|---|
| Home | carousel | `display:"flex" overflowX:"auto" gap:"16px"` | **unchanged** — `display:"flex" overflowX:"auto" gap:"16px"` (byte-identical; confirms the CSS fix is a true no-op on Home) |
| Product detail | carousel | `display:"block" overflowX:"visible"` | `display:"flex" overflowX:"auto"` |
| Listing | carousel | `display:"block" overflowX:"visible"` | `display:"flex" overflowX:"auto"` |
| Search | carousel | `display:"block" overflowX:"visible"` | `display:"flex" overflowX:"auto"` |
| Collection detail | carousel | `display:"block" overflowX:"visible"` | `display:"flex" overflowX:"auto"` |
| Cart | carousel | `display:"block" overflowX:"visible"` | `display:"flex" overflowX:"auto"` |
| Cart | grid | `display:"block" gridTemplateColumns:"none"` | `display:"grid" gridTemplateColumns:"279px 279px 279px 279px"` (desktop; `224px×3` tablet, `160px×2` mobile) |

## A06 matrix — Brand (unaffected by the repair; unchanged from Task 3/RED-checkpoint)

All 45 variant checks (5 envelopes × 3 viewports × 3 variants), 15 asset-envelope records, 45 V02
anchor records, 1 wrapper-projection record, 3 real Cart-HTMX flows, 1 disposable broken-image
record — **identical to the RED checkpoint, confirmed byte-identical post-repair** (Brand's
templates carry their own inline layout fallback, so this repair — which only touched Collection
CSS and Cart's stylesheet loading — could not and did not affect Brand). PASS on every row.

## A06 matrix — Collection (repaired — **36/36 PASS**)

| Family | Page type | Route | Variant | Viewports | Result | Screenshot | Preview/Public |
|---|---|---|---|---|---|---|---|
| Collection | E1 Home | `/` | grid | 3 | PASS | `browser/collection/grid/{viewport}/home-public.png` | Public |
| Collection | E1 Home | `/` | carousel | 3 | PASS | `.../carousel/{viewport}/home-public.png` | Public |
| Collection | E2 Product detail | `/products/<slug>/` | grid | 3 | PASS | `.../grid/{viewport}/product_detail-public.png` | Public |
| Collection | E2 Product detail | `/products/<slug>/` | carousel | 3 | **PASS** (was FAIL) | `.../carousel/{viewport}/product_detail-public.png` | Public |
| Collection | E3 Listing | `/products/` | grid | 3 | PASS | `.../grid/{viewport}/listing-public.png` | Public |
| Collection | E3 Listing | `/products/` | carousel | 3 | **PASS** (was FAIL) | `.../carousel/{viewport}/listing-public.png` | Public |
| Collection | E3 Search | `/products/?q=کالا` | grid | 3 | PASS | `.../grid/{viewport}/search-public.png` | Public |
| Collection | E3 Search | `/products/?q=کالا` | carousel | 3 | **PASS** (was FAIL) | `.../carousel/{viewport}/search-public.png` | Public |
| Collection | E4 Collection detail | `/collections/p3-collection-2/` | grid | 3 | PASS | `.../grid/{viewport}/collection-public.png` | Public |
| Collection | E4 Collection detail | `/collections/p3-collection-2/` | carousel | 3 | **PASS** (was FAIL) | `.../carousel/{viewport}/collection-public.png` | Public |
| Collection | E5 Cart | `/cart/` | grid | 3 | **PASS** (was FAIL) | `.../grid/{viewport}/cart-public.png` | Public (real fragment) |
| Collection | E5 Cart | `/cart/` | carousel | 3 | **PASS** (was FAIL) | `.../carousel/{viewport}/cart-public.png` | Public (real fragment) |
| Collection | E6 Collection index (companion) | `/collections/` | n/a | 1 | PASS — `sb_css: 0`, no pilot placement; not a substitute for E4 | `browser/collection-index/index-companion.png` | Public (direct listing) |
| Collection | ?page=2 | `/collections/p3-collection-page2/?page=2` | n/a | 1 | PASS — 13-member fixture (12/page), 1 remaining product card, no HX branch | `browser/collection/page2/page2.png` | Public |

**A06 disposition: CLOSED for the two Phase-3 pilot families.** Every allowed pilot envelope for
both Brand and Collection now has direct browser proof. No global/all-family A06 claim is made —
only these two pilots, exactly as spec §25 permits.

## Real Cart HTMX proof (both families individually + combined — all PASS, unaffected by repair)

- **Brand alone**: 3 viewports, real add/update/remove, 15 tiles stable, OOB badge updates, `item_count_after_remove: 0`.
- **Collection alone**: tiles stable across swap, `page2`/index boundaries unaffected. Now also
  visually correct (grid columns / carousel rail render properly on the real Cart page, not just
  structurally present).
- **Combined**: both families on the SAME published Cart page, structurally distinct sections
  (`closest('section.section')` never overlaps), all 3 viewports: `brand_tiles_before/after_update/
  after_remove: 15/15/15`, `collection_tiles_before/after_update/after_remove: 8/8/8`,
  `distinct_sections: true`, `item_count_after_remove: 0`. Canonical screenshots:
  `browser/fragments/cart/{viewport}/{before,update,remove}.png`.

## Preview wrapper projection (harness-only; unaffected by repair)

3× replacement, `hrefs_identical: true`, `assets_stable: true` (10→10 asset tags unchanged).
Labeled explicitly as a harness projection, not a production fragment endpoint.

## Disposable broken-image fixtures (unaffected by repair; recorded separately per spec)

- **Brand**: isolated on the SEARCH envelope. `has_img_tag: true`, `img_complete: true`,
  `img_natural_width: 0`. Screenshot: `browser/brand/broken-image/search.png`.
- **Collection**: auto-selected onto all 6 envelopes × 2 variants × 3 viewports = 36 records in
  `metrics.json:collection.broken_image_records`, excluded from the decode/glyph assertions and
  the zero-error pools. No onerror fallback exists in either template — recorded as a known,
  out-of-scope gap for both Task 5 and Task 7, not fixed by this repair (the repair's authorized
  scope was the layout/display defect only, never image-fallback behavior).

## Computed / media / responsive assertions

`display`, `gridTemplateColumns` (now required to resolve to ≥2 real tracks for grid variants —
strengthened during harness review, see below), `gap`, `overflowX` (now required together with
`display` for carousel/beauty_tabs — same strengthening), image `objectFit` (`contain` Brand /
`cover` Collection), `dir` (`rtl` everywhere). `document.documentElement.scrollWidth <=
viewport.width + 1`: PASS on every envelope/viewport, no regression. Native horizontal scroll:
PASS on every carousel/beauty_tabs rail that overflows (scrolled to the far snap-aligned edge, both
scrollLeft conventions tried). Keyboard focus: PASS on all 81 variant/envelope/viewport records
(45 Brand + 36 Collection), `keyboard_focusable: true` throughout.

## Tenant / unauthorized negatives (unaffected by repair)

- Unauthorized Preview (Django test `Client`, unauthenticated, real permission stack): **302**,
  `rejected: true`. `browser/tenant_negatives.json`, now also embedded in `metrics.json.tenant_negatives`.
- Cross-host/foreign-store: no second Store fixture exists in this environment — same accepted
  baseline limitation (`QuickLinksRenderTests...` remains a visible SKIP, not a manufactured PASS).
- Foreign/missing-ID ownership rejection: covered by the required Python suite (all green).

## Console / page / network errors

Zero unexpected console errors, page errors, request failures, or HTTP-error responses across the
entire matrix, both before and after the repair. The one pre-existing stale-409 and the two
disposable broken-image fixtures remain the only tightly-scoped exceptions.

## Required Python tests (re-run after the repair)

```
python manage.py test \
  apps.storefront_builder.tests.test_qa_harness_contract \
  apps.storefront_builder.tests.test_g22_preview_media_render_consistency \
  apps.storefront_builder.tests.test_responsive_rendering \
  apps.storefront_builder.tests.test_r4_resource_picker \
  --noinput -v2
```
**Ran 91 tests, 0 failures/errors/skips — OK.**

```
python manage.py test \
  apps.storefront_builder.tests.test_render_service \
  apps.storefront_builder.tests.test_u4_component_variants \
  apps.storefront_builder.tests.test_g22_preview_media_render_consistency \
  apps.storefront_builder.tests.test_phase_1b_render_and_context \
  apps.storefront_builder.tests.test_responsive_rendering \
  apps.catalog.tests.test_collection_public_views \
  apps.catalog.tests.test_collection_integration \
  --noinput -v2
```
**Ran 186 tests, OK (1 pre-existing skip — QuickLinks second-store).**

```
python manage.py test \
  apps.cart.tests.test_cart_views \
  apps.cart.tests.test_cart_security \
  apps.storefront_builder.tests.test_phase2_universal_renderer \
  --noinput -v2
```
**Ran 77 tests, 0 failures/errors/skips — OK** (includes `test_cart_loads_shared_css`, confirming
the new `product_card.css` link doesn't disturb the existing shared-CSS assertion).

```
python manage.py check                              → System check identified no issues (0 silenced)
python manage.py makemigrations --check --dry-run    → No changes detected
git diff --check                                     → clean
```

## Review findings

### Harness round (at the RED checkpoint, commit `b3e69147`)

Two independent fresh-context review rounds already completed and recorded in that commit's own
evidence: round 1 found 1 IMPORTANT (computed-layout gate checked only one of two required
conditions per variant — fixed in the harness itself, confirmed not to change which real
envelopes were affected) and 3 MINOR (2 fixed, 1 accepted as consistent with existing test-file
precedent); round 2 confirmed CRITICAL 0 / IMPORTANT 0 unresolved.

### Repair round (this document)

**Round 1** (independent, fresh-context, reading the diff/CSS/templates/metrics.json directly):
```
SPEC COMPLIANCE: PASS
CODE/TEST QUALITY: FAIL
CRITICAL: 1
IMPORTANT: 2
```
- CRITICAL-1: the committed evidence path (`docs/qa_evidence/storefront_appearance_convergence/phase3/browser/metrics.json`) still showed the pre-repair RED state — the repair's verification runs had targeted scratchpad directories only, never the real evidence path. **Fixed:** re-ran the harness against the actual `docs/qa_evidence/.../browser/` path; evidence now genuinely reflects the repaired state.
- IMPORTANT-1: 10 unrelated PNGs under `docs/qa_evidence/storefront_builder/r4/phase1/` (the R3
  harness's own fixed-path screenshots, overwritten by every run of this shared command
  regardless of `--report-dir`) were left modified in the diff. **Fixed:** `git checkout --` on
  that path after every run, same practice as Task 3's own established ruling.
- IMPORTANT-2 (informational, correctly out of scope): `category_grid.html` has the same
  underlying bare-`.tiles-carousel` defect for an unrelated, non-pilot family. Not fixed here —
  fixing it would require touching a family outside this repair's authorization; noted for a
  separate, later decision.

**Round 2** (independent, fresh-context, re-verifying the same claims against the corrected
working tree): confirmed CRITICAL-1 and IMPORTANT-1 genuinely resolved (evidence file timestamps
and content match a fresh post-fix run; stray phase1 diff is gone), re-confirmed the production
diff is unchanged from round 1's assessment (minimal, correctly scoped, no collision risk with
Cart's own commerce UI — `product_card.css` has zero bare/global element selectors, and no class
name overlaps with Cart's own `.citem`/`.co-grid`/etc.).
```
SPEC COMPLIANCE: PASS
CODE/TEST QUALITY: PASS
CRITICAL: 0
IMPORTANT: 0
```

## Scope audit (final)

- Production files touched, total, across the harness-discovery pass and the repair: exactly two
  — `apps/storefront_builder/static/css/storefront_builder.css` (Collection-scoped rule),
  `apps/cart/templates/cart/cart_detail.html` (one existing-stylesheet `<link>`).
- No renderer, section schema, mutation service, lifecycle, domain model/service, commerce logic,
  fragment endpoint, media ownership, migration, Brand-family behavior, or Phase 4 code touched.
- No new harness, command, package, or endpoint created.
- `apps/storefront_builder/static/css/storefront_builder.css` gained no bare/global selector;
  `.collection-tiles-carousel.tiles-carousel` is the same compound selector Task 5 already used.
- `product_card.css` was not duplicated anywhere; it is loaded exactly once per envelope,
  matching the pattern every other template already used.

## Task-8 readiness: **READY**

Task 7 now fully PASSES: complete A06 closure for both Phase-3 pilot families, zero unresolved
CRITICAL/IMPORTANT findings across both review rounds (harness discovery + repair), zero
regressions, DB restore proof intact, all required Python suites green, no migration, no scope
expansion. Task 8 may proceed.
