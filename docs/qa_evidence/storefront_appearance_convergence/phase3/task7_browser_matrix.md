# Task 7 — complete browser/full-fragment/asset/responsive matrix

## Result: FAIL (genuine pre-existing production regression found; NOT fixed in this task)

Task 7 itself carries **no production authorization**. It found a real, reproducible defect in
Collection's already-closed Task 5 CSS fix. Per the execution instruction's explicit rule
("If Task 7 reveals a production defect: STOP. Record exact RED evidence and owning scope. Do
NOT silently fix production in Task 7. Do NOT start Task 8."), this document records the RED
evidence and STOPS. **Task 8 was NOT started.**

## Authority and scope

- Starting SHA / current HEAD (unchanged by this task — no commit made yet): `973c1dc00bacb6f2f7d2604fa3880bb4d6250579`
- Branch: `feature/phase3-task7-task8`
- Repository: `manouchehr94-ux/Rastisi6-14040616`
- Environment: Claude Code Web sandbox (not the Product Owner's Windows workspace). Python
  3.11.15 (venv at `/tmp/.../scratchpad/phase3_venv`, `pip install -r requirements.txt`;
  Django 5.2.17 resolved — patch-version difference within `Django>=5.2,<6`, same class of
  adaptation already ruled in the execution ledger for Task 3/5). Node v22.22.2 / npm 10.9.7.
  Browser: pre-installed Playwright Chromium at `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`
  (the R4 runner's `launchSystemBrowser()` already lists this exact path as a Linux-sandbox
  fallback candidate — no runner change was needed for browser discovery).

### RULING (environment adaptations, Task 7)

1. RULING: Use a project-local venv (Python 3.11.15) with `pip install -r requirements.txt`
   (resolves Django 5.2.17) instead of the ledger's recorded Python 3.12.x / Django 5.2.16-17.
   REASON: this sandbox ships Python 3.11.15 system-wide; the project's own
   `Django>=5.2,<6` constraint is satisfied either way. RISK IF WRONG: negligible — no
   Django 5.2-major behavior differs between these patch/minor releases relevant to this work.
2. RULING: No local `db.sqlite3` existed at session start (fresh container). Ran
   `manage.py migrate --noinput` to create it (applies only existing migrations — confirmed
   zero new migration files via `makemigrations --check --dry-run` before and after), then
   backed up the freshly-migrated, still-empty-of-fixture-data database
   (`sha256=3db5497f6da577d2306e1babd1f4ebae7584abd4bf151b528e4f075966341fb9`) before creating the
   `phase3_qa_owner` user/membership per Task 1's documented bootstrap. This is exactly Task 1's
   documented bounded local QA bootstrap (POSIX translation of the PowerShell steps), not a new
   procedure. REASON: Task 7 requires a disposable local DB and the container starts with none.
   RISK IF WRONG: none — the seed migration `apps/stores/migrations/0002_create_akhlaghi_store.py`
   is what actually provisions the `akhlaghi` store; verified present after migrate.
3. RULING: `tools/storefront_builder_qa/node_modules/playwright-core` was installed via
   `npm install` inside that directory (the existing shared dependency both R3 and R4 runners
   reuse, exactly as `--install-node-deps` would do) — done once, out-of-band, because the
   command's own `--install-node-deps` path was also exercised and confirmed idempotent.
   RISK IF WRONG: none — this is the exact documented mechanism.

### Pre-flight verification (repeated per the plan's Task 7 preamble)

- `git rev-parse --show-toplevel` → `/home/user/Rastisi6-14040616`
- `git branch --show-current` → `feature/phase3-task7-task8`
- `git rev-parse HEAD` → `973c1dc00bacb6f2f7d2604fa3880bb4d6250579` (matches required starting HEAD)
- `git status --short` → clean at session start
- `git merge-base --is-ancestor e244619f395ebf0dbebc77d2033841e17f1cd099 HEAD` → true
- `git merge-base --is-ancestor c34a04e71cc62d191d6fe8238ef4e6735fb6642f HEAD` → true
- `origin/main` → `973c1dc00bacb6f2f7d2604fa3880bb4d6250579` (unchanged, verified via `git fetch origin main`)

All preconditions hold.

## Allowed-file audit

Only harness/evidence files were touched — **no production code changed**:

| File | Category | Change |
|---|---|---|
| `apps/storefront_builder/management/commands/qa_storefront_builder_r4.py` | Existing QA management command (Task-1-allowed) | Added Task 7 broken-image disposable fixtures (Brand on SEARCH page, isolated; Collection auto-selected everywhere), Task 7 tenant/unauthorized-Preview negative check (`_phase3_tenant_negatives`, Django test `Client`), wired both into `handle()`. |
| `tools/storefront_builder_r4_qa/run.mjs` | Existing R4 QA browser runner (Task-1-allowed) | Added computed-layout/RTL/keyboard-focus/native-scroll assertions to the existing per-variant loops; broken-image exclusion from the zero-error pools (`isExpectedBrokenImageNoise`, mirroring the existing stale-409 exception pattern); `phase3CollectionIndexCompanion` (E6 browser smoke); `phase3BrandBrokenImage`; `phase3CombinedCartHtmx` (dual-pilot Cart proof); the `known_red_findings` non-fatal recorder + end-of-gate assertion described below. |
| `apps/storefront_builder/tests/test_qa_harness_contract.py` | Test-harness-contract test (Task-7-allowed: "test harness contract tests only where required to certify the harness") | One new source-inspection test certifying the above harness additions exist (mirrors the existing `test_r4_runner_and_command_support_phase3_viewports` style). |

`git diff --check` on these three files: clean. No migration file created
(`makemigrations --check --dry-run`: "No changes detected", run both before and after all
edits). `python manage.py check`: clean throughout.

No other tracked file under `apps/`, `templates/`, `static/`, or any migrations directory was
modified. Evidence-only changes (screenshots, JSON, this document) are under
`docs/qa_evidence/storefront_appearance_convergence/phase3/`.

## Required Python tests

```
python manage.py test \
  apps.storefront_builder.tests.test_qa_harness_contract \
  apps.storefront_builder.tests.test_g22_preview_media_render_consistency \
  apps.storefront_builder.tests.test_responsive_rendering \
  apps.storefront_builder.tests.test_r4_resource_picker \
  --noinput -v2
```

**Ran 91 tests, 0 failures, 0 errors, 0 skips — OK.** (90 pre-existing + 1 new harness-contract
test.) Run three times across iterations of this task, always green.

```
python manage.py check                              → System check identified no issues (0 silenced)
python manage.py makemigrations --check --dry-run    → No changes detected
git diff --check                                     → clean
```

No migration file exists anywhere in the diff.

## DB safety

- DB backend: `django.db.backends.sqlite3`, local file, DEBUG=True, no `DATABASE_URL` — disposable.
- Pre-run SHA256 (each of 5 harness executions during this task): consistently
  `7380719816273f29d29837b5085602013f28bb536956b1a37670302f44877ce7`.
- Post-restore SHA256 (final, authoritative run): `7380719816273f29d29837b5085602013f28bb536956b1a37670302f44877ce7`.
- **`match: true`** — see `browser/db-restore-proof.json`. Verified on every run, including the
  three earlier RED iterations while debugging the new harness code (the command's `finally`
  restores regardless of exit code).
- Server/browser process shutdown: confirmed via the command's own `finally` (`_stop_process`),
  same mechanism Task 1–6 already certified.

## A06 matrix — Brand (unchanged from Task 3; re-verified, no regression)

All 45 variant checks (5 envelopes × 3 viewports × 3 variants), 15 asset-envelope records, 45 V02
anchor records, 1 wrapper-projection record, 3 real Cart-HTMX flows — **identical counts and PASS
status to Task 3's committed evidence**. New Task 7 fields now present on every record:
`computed_layout` (display/gridTemplateColumns/gap/overflowX/imgObjectFit/dir), `native_scroll`
(populated for carousel/beauty_tabs where the rail actually overflows; `null` for grid), and
`keyboard_focusable` (always `true`). Every envelope confirms `dir: "rtl"` (the whole storefront
renders RTL — `templates/base.html` sets `dir="rtl"` — so RTL is exercised on every single
existing and new assertion, not a separate code path). Brand's inline `style="display:flex;
overflow-x:auto"` / `style="display:grid;..."` fallback in `brand_carousel.html` means Brand has
**no** analogous defect to the one found below.

| Family | Page type | Route | Variants | Viewports | Automated result | Screenshot | Metrics | Preview/Public | PASS/FAIL |
|---|---|---|---|---|---|---|---|---|---|
| Brand | E1 Home | `/` | grid/carousel/beauty_tabs | 3 | PASS (45 checks total across E1–E5) | `browser/brand/{variant}/{viewport}/home-public.png` | `browser/metrics.json:variant_checks` | Public; Preview proven via wrapper projection + scenarios 10–13 | PASS |
| Brand | E2 Product detail | `/products/<slug>/` | same | 3 | PASS | `.../product_detail-public.png` | same | Public | PASS |
| Brand | E3 Listing/Search | `/products/` | same | 3 | PASS (Search dedup per Task 3's per-type equivalence proof) | `.../listing-public.png` | same | Public | PASS |
| Brand | E4 Collection detail | `/collections/p3-collection-1/` | same | 3 | PASS | `.../collection-public.png` | same | Public | PASS |
| Brand | E5 Cart | `/cart/` | same | 3 | PASS + real HTMX (see below) | `.../cart-public.png`, `browser/fragments/cart/{viewport}/*.png` | same | Public (real fragment) | PASS |
| Brand | E6 Collection index (companion) | `/collections/` | n/a | 1 | Companion only — Brand is not placed there; not a substitute for E4 | n/a (Collection's own E6 check covers this envelope) | n/a | n/a | N/A (by design) |

## A06 matrix — Collection (Task 5 re-verified + Task 7 additions — **2 findings, FAIL**)

36 variant checks (6 envelopes × 3 viewports × 2 tile variants) and 18 asset-envelope records —
identical counts to Task 5. **18 of the 36 variant checks now carry a recorded
`known_red_finding`** (Task 7's computed-layout assertions are new; Task 5 never asserted
`display`/`overflowX` numerically, only container-class presence and tile
count/order/image-decode, so this gap was invisible to it).

| Family | Page type | Route | Variant | Viewports | Automated result | Screenshot | Metrics | Preview/Public | PASS/FAIL |
|---|---|---|---|---|---|---|---|---|---|
| Collection | E1 Home | `/` | grid | 3 | PASS (`.grid{display:grid}` loads via `product_card.css`, present on Home) | `browser/collection/grid/{viewport}/home-public.png` | `metrics.json:collection.variant_checks` | Public | PASS |
| Collection | E1 Home | `/` | carousel | 3 | PASS (`.tiles-carousel{display:flex;overflow-x:auto}` loads via `home.css`, present on Home) | `.../carousel/{viewport}/home-public.png` | same | Public | PASS |
| Collection | E2 Product detail | `/products/<slug>/` | grid | 3 | PASS (`product_card.css` loaded here too) | `.../grid/{viewport}/product_detail-public.png` | same | Public | PASS |
| Collection | E2 Product detail | `/products/<slug>/` | carousel | 3 | **FAIL** — `display` computed `"block"` (not flex), `overflowX` computed `"visible"` | `.../carousel/{viewport}/product_detail-public.png` (a tight crop around the scrolled-to section — the vertical stacking is visible in the crop's proportions, not a labeled visual diff; the computed-style values are the authoritative evidence) | `metrics.json:collection.known_red_findings` | Public | **FAIL** |
| Collection | E3 Listing | `/products/` | grid | 3 | PASS | `.../grid/{viewport}/listing-public.png` | same | Public | PASS |
| Collection | E3 Listing | `/products/` | carousel | 3 | **FAIL** — same defect | `.../carousel/{viewport}/listing-public.png` | metrics | Public | **FAIL** |
| Collection | E3 Search | `/products/?q=کالا` | grid | 3 | PASS | `.../grid/{viewport}/search-public.png` | same | Public | PASS |
| Collection | E3 Search | `/products/?q=کالا` | carousel | 3 | **FAIL** — same defect | `.../carousel/{viewport}/search-public.png` | metrics | Public | **FAIL** |
| Collection | E4 Collection detail | `/collections/p3-collection-2/` | grid | 3 | PASS | `.../grid/{viewport}/collection-public.png` | same | Public | PASS |
| Collection | E4 Collection detail | `/collections/p3-collection-2/` | carousel | 3 | **FAIL** — same defect | `.../carousel/{viewport}/collection-public.png` | metrics | Public | **FAIL** |
| Collection | E5 Cart | `/cart/` | grid | 3 | **FAIL** — `display` computed `"block"`, expected `grid`\|`flex` (Cart is the one envelope that does NOT load `product_card.css` — see A06 asset table) | `.../grid/{viewport}/cart-public.png` | metrics | Public (real fragment; see Cart HTMX below) | **FAIL** |
| Collection | E5 Cart | `/cart/` | carousel | 3 | **FAIL** — same overflow defect as above, PLUS Cart also lacks `product_card.css` | `.../carousel/{viewport}/cart-public.png` | metrics | Public | **FAIL** |
| Collection | E6 Collection index (companion) | `/collections/` | n/a | 1 (desktop) | PASS — `sb_css: 0` confirmed (no pilot placement, direct listing only); does not substitute for E4 | `browser/collection-index/index-companion.png` | `metrics.json:collection.index_companion` | Public (direct listing, not Builder) | PASS (companion; N/A as certification) |
| Collection | ?page=2 | `/collections/p3-collection-page2/?page=2` | n/a | 1 (desktop) | PASS — 13-member fixture (12/page) renders its 1 remaining product card via the shared card partial, no HX branch even with `HX-Request` header (`metrics.json:collection.page2.product_card_count == 1`) | `browser/collection/page2/page2.png` | `metrics.json:collection.page2` | Public | PASS |

**A06 disposition: PARTIAL/OPEN for Collection.** Per spec §10/§25: "Any unproven allowed pilot
envelope leaves A06 PARTIAL/OPEN and blocks full family PASS." Collection's carousel variant is
unproven (fails) on 5 of 6 allowed envelopes; Collection's grid variant is unproven (fails) on
Cart. **Task 7 therefore FAILS**, and per its own rule, the fix belongs to CSS work already
inside Task 5's original allowed-file scope (`apps/storefront_builder/static/css/
storefront_builder.css`, Collection-scoped only) — not to Task 7, which has no production
authorization.

### Exact root cause (owning scope: Task 5's `storefront_builder.css`, Collection-scoped)

1. **Carousel overflow** (product_detail, listing, search, collection, cart × 3 viewports = 15
   findings): `apps/catalog/static/css/home.css:143` defines the ONLY base rule
   `.tiles-carousel{display:flex;gap:16px;overflow-x:auto;scroll-snap-type:x mandatory;
   padding-bottom:6px;-webkit-overflow-scrolling:touch}`. Task 5's CSS fix
   (`storefront_builder.css:4514`) mirrored only the child selector
   `.collection-tiles-carousel.tiles-carousel .pcard{flex:0 0 220px;scroll-snap-align:start}` —
   the PARENT container's `display:flex;overflow-x:auto` was never copied. `home.css` is
   deliberately not loaded on non-Home envelopes (by design, per the A06 asset table), and
   `collection_tiles.html` carries no inline fallback (unlike `brand_carousel.html`, which does
   have one). Net effect: on every non-Home page, the "carousel" tile_style renders as a plain
   block list (each `.pcard` stacks), not a horizontal scrolling rail.
2. **Grid display on Cart only** (3 findings): `.grid{display:grid;gap:16px}` lives in
   `apps/catalog/static/css/product_card.css:9`, which — per the A06 asset table — is loaded on
   every envelope EXCEPT Cart (`cart.css` + `storefront_builder.css` only). `collection_tiles.html`
   has no inline `display:grid` fallback either. Net effect: on Cart specifically, the "grid"
   tile_style also collapses to a plain block list.

Both are the same class of defect Task 3 found and fixed for Brand (V06/A06 asset-envelope
mismatch) — Task 5's own fix for Collection was incomplete (it correctly mirrored the *effective
cascade value* for the nested `.pcard` rule, exactly as Task 3's methodology required, but missed
that the *parent* container rule needed the same treatment).

## Real Cart HTMX proof (both families individually + combined — all PASS)

- **Brand alone** (reused/re-verified from Task 3): 3 viewports, real `/cart/add/`, real
  `hx-post` update/remove URLs read from the DOM (never hard-coded), 15 tiles stable across the
  swap, OOB `#cart-count` badge updates (۲→۳→۰), `item_count_after_remove: 0`.
- **Collection alone** (reused/re-verified from Task 5): tiles 6→6/8→8 stable, `page2`/index
  boundaries unaffected.
- **Combined (Task 7, new)**: both families placed on the SAME published Cart page (already
  true of the existing fixture — each `place_variant`/`place_tiles_variant` call creates its own
  single-cell container, so Brand's 3 variants and Collection's 2 variants already sit in 5
  independent containers/cells) — `phase3CombinedCartHtmx` adds a product, reads the real
  `hx-post` URLs, and asserts BOTH families' tiles survive quantity-update AND item-removal
  together, with **structural distinctness** proven via `closest('section.section')` (no editor
  container/cell hooks exist on Public by design — confirmed no Brand tile and Collection tile
  ever resolve to the same `<section>`). Result (all 3 viewports): `brand_tiles_before/after_update/
  after_remove: 15/15/15`, `collection_tiles_before/after_update/after_remove: 8/8/8`,
  `distinct_sections: true`, `brand_section_count: 3`, `collection_section_count: 2`,
  `item_count_after_remove: 0`. Screenshots (canonical Task 7 paths):
  `browser/fragments/cart/{viewport}/{before,update,remove}.png`.
- Real Cart HTMX and the harness-only Preview wrapper projection remain separately labeled (see
  below) — never conflated.

## Preview wrapper projection (harness-only; NOT a server fragment endpoint)

Reused/re-verified from Task 3: discover the live `data-section-id` in the R4 Preview iframe,
`fetch()` the same Preview URL, `DOMParser`-extract the matching wrapper, replace the live
wrapper 3× (scripts never executed from the fetched markup — assigned via `innerHTML` only).
Result: `hrefs_identical: true`, `assets_stable: true` (10→10 stylesheet/script tags, unchanged
across all 3 replacements). Labeled explicitly in code and here as a **harness projection**, not
a production fragment endpoint — no new route was added or required.

## Disposable broken-image fixtures (Task 7, new — recorded separately per spec, not asserted to succeed)

Per spec §16/Task 7: "record browser network failure; do not equate no-image with broken-image."

- **Brand**: one throwaway Brand (`t12-brand-broken`) with `logo` pointing at a file never
  written to storage, isolated on the SEARCH envelope (not one of Brand's 5 certified pages, so
  it cannot interfere with the certified matrix above). Result: `has_img_tag: true`,
  `img_complete: true`, `img_natural_width: 0`, `request_failed_observed: false` (a 404 is a
  completed HTTP response, not a Playwright network-level `requestfailed` event — the console
  error and the 404 HTTP-error-response are both correctly captured and excluded from the
  zero-error gates via the new `isExpectedBrokenImageNoise` exception, the same pattern already
  used for the one intentional stale-409). Screenshot: `browser/brand/broken-image/search.png`.
- **Collection**: one throwaway Collection (`p3-collection-broken`, ACTIVE, `created_at` two days
  before every other fixture collection so it can never become the deterministic "newest" tile)
  with `image` pointing at a file never written to storage. Because Collection's tile auto-mode
  selects "all active", this fixture is unavoidably picked up by every existing auto tile
  section — recorded at all 6 envelopes × 2 variants × 3 viewports = **36 records** in
  `metrics.json:collection.broken_image_records`, explicitly excluded from the existing
  decode/glyph-fallback assertions (which continue to require the OTHER tiles to decode or show
  the folder-glyph fallback, unmodified) and from the zero-error pools. No onerror fallback
  exists in either template (confirmed by source inspection, matching the inventory's own
  finding) — this is recorded as a known gap, not fixed (out of scope for both Task 5 and Task 7).

## Computed / media / responsive assertions (new)

Added to every existing per-variant/per-viewport check (Brand: 45 records; Collection: 36
records): `display`, `gridTemplateColumns`, `gap`, `overflowX`, image `objectFit` (`contain` for
Brand logos, `cover` for Collection covers — both asserted and PASS everywhere they render),
`dir` (`rtl` everywhere — the storefront always renders right-to-left, so this is exercised on
every single request, not a separate toggle). `document.documentElement.scrollWidth <=
viewport.width + 1` was already asserted by Task 3/5 and re-verified here with no regression on
any envelope/viewport. Native horizontal scroll: for carousel/beauty_tabs rails where
`scrollWidth > clientWidth`, scrolled the rail programmatically to its far edge (`scrollWidth`,
trying both the positive and the RTL "negative scrollLeft" convention Chromium uses for
right-to-left block content) and asserted the position actually changed — PASS everywhere Brand's
carousel/beauty_tabs rails render (they use `scroll-snap-type: x mandatory`, so an arbitrary small
delta legitimately snaps back to 0; scrolling to the far, snap-aligned edge avoids that false
negative). Keyboard focus: `element.focus()` + `document.activeElement === element` on the first
tile anchor of every variant/envelope/viewport — PASS everywhere (45 Brand + 36 Collection
records, all `keyboard_focusable: true`).

## Tenant / unauthorized negatives

- **Unauthorized Preview (Django test `Client`, unauthenticated, real permission stack — not the
  browser, not a skipped fixture)**: `GET /admin-portal/storefront-builder/preview/?page=home` →
  **302** (redirect to login), `rejected: true`. See `browser/tenant_negatives.json`.
- **Cross-host / foreign-store negative**: no second Store fixture exists in this environment
  (same accepted limitation the baseline already documents —
  `QuickLinksRenderTests.test_menu_from_another_store_never_leaks` remains a visible SKIP, not a
  PASS, exactly as `baseline.md` requires; Task 7 does not fabricate a second store to manufacture
  a PASS here). This is the same, already-accepted baseline exception — not a new Task 7 gap.
- Foreign/missing-ID ownership rejection for both Brand and Collection sources is already
  covered by the required Python suite (`test_r4_resource_picker`: `BrandManualOwnershipTests`,
  `CollectionManualOwnershipTests`, `StoreScopedSearchTests` — all green, re-run in this task).

## Console / page / network errors

Zero unexpected console errors, zero page errors, zero unexpected request failures, zero
unexpected HTTP-error responses across the entire matrix (`metrics.json: errors: []`,
`collection.errors: []`) — the ONE pre-existing intentional stale-409 (scenario 9) and the TWO
Task 7 disposable broken-image fixtures are the only excluded exceptions, both tightly scoped by
URL pattern (`isExpectedBrokenImageNoise`) or the existing URL+timestamp+status correlation
(`isExpectedStale409Response`/`isExpectedStaleConflictNoise`). No other exception exists anywhere
in the gates.

## Scope audit

- No production rendering/CSS/template/JS file was changed. `git diff --check` on
  `apps/storefront_builder/management/commands/qa_storefront_builder_r4.py`,
  `tools/storefront_builder_r4_qa/run.mjs`, and
  `apps/storefront_builder/tests/test_qa_harness_contract.py`: clean.
- No new harness, command, package, or endpoint was created — only the existing
  `qa_storefront_builder_r4.py` / `run.mjs` were extended, exactly as Task 7 requires.
- No Phase 4 scope entered (no other family, no non-Home R4 rollout, no legacy retirement).
- **Whether production code changed: NO.**

## Review findings

Independent fresh-context review performed by a separate agent with no prior context, reading
only this document, the actual code diff, the actual production CSS/template files, the actual
metrics.json/screenshots, and the vertical_slice_inventory.md A06 table.

**Round 1 verdict:**
```
SPEC COMPLIANCE: PASS
CODE/TEST/EVIDENCE QUALITY: PASS
CRITICAL: 0
IMPORTANT: 1
MINOR: 3
```

- Confirmed independently, against the real files (not just this document's claims): the
  root-cause claim (`.tiles-carousel{display:flex;overflow-x:auto}` exists only in home.css;
  `storefront_builder.css` mirrors only the child `.pcard` selector; `collection_tiles.html` has
  no inline fallback while `brand_carousel.html` does; `.grid{display:grid}` lives only in
  `product_card.css`, which Cart alone does not load); scope discipline (only the three allowed
  harness/test files touched, confirmed via `git diff HEAD`); and that the `known_red_findings`
  non-fatal-recording pattern genuinely still fails the overall run (`r4-browser-result.json`
  shows `{"passed":15,"failed":1}`, not a silent PASS).
- **IMPORTANT (resolved in this task, harness-only fix):** the computed-layout gate asserted
  only `overflowX` for carousel/beauty_tabs and only `display` for grid — a partial CSS fix
  (e.g. adding `overflow-x:auto` without `display:flex`) could have made the harness go green
  while the rail was still visually stacked. **Fix applied:** both `phase3PublicMatrix` (Brand)
  and `phase3CollectionPublicMatrix` (Collection) now require BOTH conditions together —
  non-grid variants require `display` to include `flex` AND `overflowX` to be `auto`/`scroll`;
  grid variants require `display` to include `grid`/`flex` AND `gridTemplateColumns` to resolve
  to >=2 actual tracks (not just a collapsed single-column grid). Re-run after the fix: still
  **18** known-red findings, same exact envelopes/viewports/variants as before (confirming the
  fix only tightened the assertion, it did not change which real pages are affected) — see
  `metrics.json:collection.known_red_findings`, now each carrying both the `display` and
  `overflowX`/`gridTemplateColumns` values in `actual`.
- **MINOR (resolved in this task):** `phase3.tenant_negatives` in `metrics.json` was declared
  but always left `null` — the real evidence lived only in the separately-written
  `tenant_negatives.json`. **Fix applied:** the runner now reads that file into
  `phase3.tenant_negatives` at the start of `phase3BrandGate()`, so `metrics.json` carries the
  same data as the standalone file (which remains the authoritative copy, unchanged).
- **MINOR (accepted, not changed):** the new `test_qa_harness_contract` test is source-substring
  inspection, not a behavioral test. REASON: this matches the file's own established, already-
  reviewed pattern (`test_r4_runner_and_command_support_phase3_viewports` does the same); the
  file's role per the plan is certifying the harness's own contract/wiring, not re-running the
  harness. RISK IF WRONG: low — a renamed identifier would need the test updated, but the actual
  behavior is exercised by the real browser run, not this test.
- **MINOR (resolved in this task):** two evidence-document phrasing overstatements were
  corrected: the E2 product_detail screenshot description ("shows tiles stacked, not a
  horizontal rail" — actually a tight crop, not a labeled visual diff; the computed-style values
  are the real evidence) and the Collection page-2 row ("13 visible members" — the fixture has
  13 total members across 2 pages at 12/page; the actual assertion and metrics value is 1
  remaining product card on page 2). Both corrected above in the A06 tables.

**Round 2 (informal, self-verified after applying the two fixes above):** re-ran the full
harness once more (see "DB safety" and counts throughout this document, which reflect the
POST-fix run) — same 18 known-red findings (now carrying both computed values), all other 15
scenarios still PASS, DB restore SHA256 still matches. No new regression introduced by the
harness-strengthening fix itself.

- CRITICAL: 0 (both before and after the round-1 fix — the finding is a genuine pre-existing CSS
  gap, not a harness defect, and was never silently hidden).
- IMPORTANT: 0 unresolved (the one round-1 IMPORTANT was fixed in the harness itself, as
  described above; **the underlying production CSS regression itself remains open** — see next
  section — but that is Task 7's correctly-reported FAIL disposition, not an unresolved review
  finding about the harness).
- MINOR: 1 accepted-as-is (source-inspection test style, consistent with existing precedent),
  2 fixed.

## Task-8 readiness: **NOT READY**

Per the master execution instruction: "TASK 7 MUST BE COMPLETED BEFORE TASK 8 STARTS" and "If
Task 7 reveals a production defect: STOP ... Do NOT start Task 8." Task 7 is FAIL. **Task 8 was
NOT started.**
