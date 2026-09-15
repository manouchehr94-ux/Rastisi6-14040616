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
