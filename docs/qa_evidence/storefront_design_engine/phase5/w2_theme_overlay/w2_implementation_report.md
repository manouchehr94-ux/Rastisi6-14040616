# P5-W2 — Reversible Theme Overlay — Implementation Report

## Identity
- **Certified base SHA:** `b7d8ac281389870877553f5a308af3e77dcdd7f0`
- **Implementation branch:** `feature/phase5-w2-theme-overlay` (branched exactly from the certified base)
- **PR target (unmerged):** `feature/phase5-design-expansion`
- **Scope executed:** P5-W2 only. P5-W3 NOT started, no W3 branch created.

## What was built
A reversible occasion/seasonal Theme layer implemented as a NEW OPTIONAL
Store-Appearance family (`theme`, `renderer_role="appearance_token"` — an
existing allowed role; `_RENDERER_ROLES` was NOT expanded). Theme visually
alters the storefront (accent band on global chrome + soft section wash) while
preserving the underlying Ready-Template DNA. It owns ONLY `selections["theme"]`
and `settings["theme"]`.

Initial occasions (single owner `theme_catalog.py`): `none` (no-op), `nowruz`,
`yalda`, `valentine` (festive), `ramadan`, `eid_fitr`, `eid_qorban` (neutral
observance), `muharram` (mourning). Future occasions add one catalog entry each.

## Production files changed
- `apps/storefront_builder/theme_catalog.py` **(new)** — single occasion data authority + intensity vocab.
- `apps/storefront_builder/storefront_appearance/families.py` — `theme` optional appearance-token family.
- `apps/storefront_builder/storefront_appearance/adapters.py` — emit Theme ComponentDefinitions from catalog; `theme_overlay:<key>` resolution (fail-closed).
- `apps/storefront_builder/storefront_appearance/validation.py` — `ALLOWED_SETTINGS_BY_FAMILY["theme"]={"intensity"}` + typed enum check.
- `apps/storefront_builder/storefront_appearance/rendering.py` — `ThemeOverlayState` + `theme_overlay_state()` canonical accessor.
- `apps/storefront_builder/storefront_appearance/inventory.py` — advertise only `theme.none.v1` (Ready Templates auto-assign no occasion).
- `apps/storefront_builder/services/render_service.py` — re-export `store_appearance_theme_overlay_state`.
- `apps/storefront_builder/services/appearance_authority_service.py` — `apply_theme()` / `clear_theme()` (theme-owned state only; NO baseline snapshot).
- `apps/storefront_builder/services/r4_mutation_service.py` — `theme.apply` / `theme.clear` mutations through the existing single mutation boundary.
- `apps/storefront_builder/a8_ready_templates.py` — `theme.none.v1` in every generated manifest (all 50).
- `apps/storefront_builder/layout_preset_registry.py` — `theme.none.v1` in retained recipe manifests.
- `apps/core/context_processors.py` — `SHOP_OCCASION_*` projection from the single global identity version (Preview/Public parity).
- `templates/base.html` — `data-occasion-*` attributes + `--occasion-*` CSS vars on `<html>`; link `occasion_theme.css`.
- `apps/core/static/css/occasion_theme.css` **(new)** — one bounded overlay token layer (no per-template fork; RTL/reduced-motion/mourning-safe).
- `apps/storefront_builder/templates/storefront_builder/partials/responsive_section_wrapper.html` — section occasion marker (same resolved theme).
- `apps/storefront_builder/r4_views.py` — `_build_theme_design_context` + wire into Global Design panel.
- `apps/storefront_builder/templates/dashboard/storefront_builder/r4/editor.html` — Theme controls (occasion/intensity/apply/clear) + `data-r4-draft-id` on shell.
- `apps/storefront_builder/static/storefront_builder/r4_editor.js` — Theme apply/clear handlers via `R4.enqueueMutation`.

## Test files changed
- `apps/storefront_builder/tests/test_w2_theme_overlay.py` **(new, 41 tests)**.
- `apps/storefront_builder/tests/test_r4_store_appearance_contracts.py` — family ordering now includes `theme`.
- `apps/storefront_builder/tests/test_a8_component_coverage.py` — advertised counts include `theme: 1`.
- `apps/storefront_builder/tests/test_a8_component_library.py` — registry counts `theme: 8`, total `127`, advertised set +`theme.none.v1`.

## Evidence files (`docs/qa_evidence/storefront_design_engine/phase5/w2_theme_overlay/`)
`00_source_inventory.md`, `01_red_summary.txt`, `02_green_focused.txt`,
`03_targeted_regression.txt`, `04_full_storefront_builder_suite.txt`,
`05_preexisting_failures_repro.md`, `06_repo_gates.txt`,
`07_browser_qa_report.md`, `08_theme_catalog_po_review.md`,
`09_architecture_duplication_audit.md`, `screenshots/` (7 PNGs), this report.

## Exact test counts
- W2 focused suite: **41 passed / 41** (`OK`).
- Targeted regression (rendering, registry, contracts, render_service, preset_service): **186 passed** (1 skipped).
- Full Storefront Builder suite: **3143 tests — 30 failures + 2 errors + 4 skipped**.

## Exact known failures
- **30 failures + 2 errors** in the full suite are **PRE-EXISTING** at the
  certified base — independently reproduced by reverting the worktree to
  `b7d8ac28` (git stash -u) and re-running the same modules: identical 30+2
  (see `05_preexisting_failures_repro.md`). They are Ready-Template reference
  contract / mobile-nav / fullscreen-topbar / template-gallery / validator-
  boundary tests that assert frozen preset versions & reference silhouettes;
  none touch the Theme family or the appearance engine W2 modifies.
- **W2 introduces ZERO new failures.**

## Result summary
- **Migrations = 0** (`makemigrations --check --dry-run` → "No changes detected").
- **Django check:** PASS (0 issues).
- **git diff --check:** clean.
- **Theme catalog entries:** 8 (`none`, `nowruz`, `yalda`, `valentine`, `ramadan`, `eid_fitr`, `eid_qorban`, `muharram`).
- **Preview/Public parity:** PASS (single resolver via global identity version; asserted byte-identical resolved theme; Browser QA confirmed).
- **All-50 compatibility:** PASS (all 50 manifests valid `require_complete=True`, all default `theme.none.v1`; all 50 candidate previews resolve; all 50 applies succeed).
- **Reversibility:** PASS (State A→B→C→D scenario: post-clear non-theme state equals post-customization/pre-theme state exactly; no `template_baseline_snapshot`).
- **Tenant isolation:** PASS (Store A cannot mutate Store B theme; no global theme state).
- **Stale-write:** PASS (valid revision applies; stale rejected via existing `R4StaleRevision`).
- **Mourning tone safety:** PASS (`muharram` tone=`mourning`; structurally no festive/countdown/sale flags; CSS restrained; visually confirmed).

## Architecture
Single owner for every concern (family, catalog, registry path, resolver,
persistence, Draft lifecycle, mutation boundary, preview, public renderer) —
see `09_architecture_duplication_audit.md`. No new model, no migration, no
second registry/resolver/persistence layer.



---

## PR #8 Architect-repair addendum (6 IMPORTANT + minor)

Runtime for all repair verification: **Python 3.12.13, Django 5.2.17**.
New PR head after repairs supersedes `0c29fb5…`.

- **Repair A — single request-scoped resolved appearance.** Added
  `render_service.resolved_store_appearance_for_request(request, version)` — a
  request-scoped memoization (attribute `request.storefront_resolved_appearance`,
  keyed by `version.pk`) around the single canonical
  `resolve_store_appearance_render_state`. `build_universal_storefront_context`
  and the `shop_settings` context processor now consume this ONE resolved state
  per request instead of resolving the same Version twice. The broad
  `except Exception:` was removed — a malformed NEW manifest now raises loudly
  (never silently becomes `theme.none`). No second resolver.
- **Repair B — real motif.** `ThemeOverlayState` gained a bounded `motif`
  identity from the catalog; `SHOP_OCCASION_MOTIF` is projected; `<html>` and
  `.rsec` section wrappers emit `data-occasion-motif`; the one shared
  `occasion_theme.css` maps every non-noop motif token to a distinct bounded
  decoration (per-occasion corner ornament + section corner accent). Mourning
  (`muted_banner`) renders only a calm flat band and suppresses the ornament.
  No per-template CSS, no merchant CSS, no motif registry, no DNA change.
- **Repair C — Undo AND Redo.** The mutation history test now proves apply →
  undo → redo restores the exact occasion + intensity; a Clear-Theme history
  test was added.
- **Repair D — actual rendered Preview/Public parity.** New integration test
  renders the real Preview and real public routes and asserts identical rendered
  Theme projection (occasion/tone/intensity/motif/accent + shell + section).
- **Repair E — full Browser QA matrix.** 2 materially different Ready Templates
  (`dense_marketplace`, `editorial_jewelry`) × 3 themes (Yalda/Ramadan/Muharram)
  × 3 intensities × 3 viewports = 54 cases; representative screenshots for both
  templates; no overflow, no console errors, RTL intact, motif rendered,
  mourning restrained, none-restoration. See `07_browser_qa_report.md` +
  `10_browser_qa_matrix_raw.txt` + `screenshots/A-*`,`screenshots/B-*`.
- **Minor — No Theme == Clear.** `apply_theme("theme.none.v1", …)` routes to
  `clear_theme()` (no dead intensity retained); the R4 UI routes "بدون تم
  مناسبتی" to `theme.clear` and disables the intensity control for No Theme.

### Public-home shell limitation — deferred to P5-W4A
W2 Theme is certified on the current universal-shell surfaces (every page that
extends `storefront_shell.html`/`base.html`, e.g. the product list). The
standalone `catalog/home.html` public home does not yet use the universal
shell; that public-shell convergence is deferred to **P5-W4A**. W2 does NOT
claim complete all-public-page Theme coverage before W4A.

### Repair test counts (Python 3.12.13, Django 5.2.17)
- Focused `test_w2_theme_overlay`: **57 passed / 57**.
- Candidate-preview regression: task2 (13) + `NonDestructiveTemplatePreviewTests` (11) = 24 PASS; task3 (11) PASS.
- Targeted regression: 186 PASS (1 skip).
- Full Storefront Builder suite: 3159 tests — 30 failures + 2 errors + 4 skipped,
  **identical (empty diff) to the clean certified-base failure set** on Python
  3.12 (reproduced via a clean clone, no stash). Zero W2 regressions.

### Task-6 historical guard correction
The Task-6 additive guard `test_ready_template_recipe_files_are_untouched_by_task6`
had an open-ended diff range (`c0ca174…...HEAD`) that incorrectly flagged
authorized post-Task-6 work. It was corrected to the FIXED historical Task-6
range `c0ca174475bf19dd5c3ecac3857da479623e1e7d...a75711473b791c2add0389913707503bc0024cc0`
(the guard's real purpose: prove Task 6 ITSELF did not touch canonical
authorities). The forbidden set is UNCHANGED and NO W2 exemptions were added —
this is a maintenance correction to a historical guard, not a W2 exception.

### Additional production files changed by the repair
- `apps/storefront_builder/services/render_service.py` — `resolved_store_appearance_for_request`.
- `apps/storefront_builder/services/storefront_context_service.py` — consume the request-scoped resolved appearance.
- `apps/core/context_processors.py` — consume resolved state; remove broad except; project `SHOP_OCCASION_MOTIF`.
- `apps/storefront_builder/storefront_appearance/rendering.py` — `ThemeOverlayState.motif`.
- `apps/storefront_builder/services/appearance_authority_service.py` — `apply_theme` no-op normalization to `clear_theme`.
- `apps/core/static/css/occasion_theme.css` — per-motif bounded decorations.
- `templates/base.html`, `.../responsive_section_wrapper.html` — `data-occasion-motif`.
- `.../static/storefront_builder/r4_editor.js` — No-Theme → clear + intensity disable.
