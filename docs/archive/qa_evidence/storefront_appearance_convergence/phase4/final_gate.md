# Phase 4 — final gate: Task 10 certification rerun (2026-09-11)

## Status

**PHASE 4: CLOSED.**

This is the FULL Task-10 certification rerun required after the Task-8
corrective fix (see `task10_blocker_task8_reset_fix.md`). It supersedes the
prior Task-10 attempt, which correctly FAILED and STOPPED on discovering
one genuine regression in `reset_storefront_to_baseline()`. That regression
is fixed; this rerun re-establishes certification against the corrected
HEAD from scratch — it does not resume or shortcut the prior attempt.

- Starting HEAD (mandated): `f3253b11950c99ecead42252a1d8ab757dbda9be`
- Final HEAD: `f3253b11950c99ecead42252a1d8ab757dbda9be` (Task 10 changed
  evidence/docs only — no production code was touched in this session)
- Corrective backup (unchanged): `backup/rastisi6-phase4-task8-reset-regression-fix-20260911` == `f3253b11950c99ecead42252a1d8ab757dbda9be`
- Pre-Task-10 evidence-clean checkpoint (unchanged): `backup/rastisi6-phase4-pre-task10-evidence-clean-20260911` == `330cbe46df6230e06c10328e96018a48cb8d79bd`
- `main` (unchanged): `973c1dc00bacb6f2f7d2604fa3880bb4d6250579`

## Startup guard

A genuine guard failure was hit and resolved before certification could
begin: the local checkout's `feature/phase4-builder-legacy-convergence`
was a **shallow clone**, which made `git merge-base` report no common
ancestor between local HEAD (an unrelated, older Phase-3 commit) and
`origin/feature/phase4-builder-legacy-convergence` (`f3253b119...`) — a
false positive for "diverged history," not real divergence. Resolved with
`git fetch --unshallow origin` (a pure additional-history fetch, no ref
changes) followed by a plain `git merge --ff-only
origin/feature/phase4-builder-legacy-convergence` (clean fast-forward, no
reset/rebase/force/history-rewrite). Re-verified after: not shallow, local
HEAD == origin feature HEAD == `f3253b119...`, working tree clean, `main`
and both backups unchanged, `backup/rastisi6-phase4-final-20260911` did
not yet exist. No other guard failed.

## Step 1 — Task-8 corrective fix re-certification

`apps.storefront_builder.tests.test_u7_ready_template_baseline` — 12/12
OK, including all three required cases:

- CASE A (`test_reset_from_exact_matching_snapshot_survives_registry_disappearance`) — OK
- CASE B (`test_reset_rejects_stale_recorded_version` → `TemplateBaselineVersionChangedError`) — OK
- CASE C (`test_reset_rejects_unknown_template_key` → `UnknownPresetError`) — OK

`apps.storefront_builder.tests.test_r4_vertical_slice.TemplateSwitchPreservingContentTests.test_reset_storefront_after_switch_is_rejected_not_silently_destructive` — OK.

## Step 2 — exhaustive Django regression

Full `apps.storefront_builder` suite at final HEAD:

```
Ran 2898 tests in 1693.279s
FAILED (failures=30, errors=2, skipped=4)
```

Compared to the prior Task-10 baseline run on `330cbe46` (2897 tests, 30
failures, 3 errors, 4 skips): **+1 test** is the new CASE-A guard test
added by the corrective fix; **errors dropped 3→2** because the
previously-failing regression test now passes. This is exactly the
expected delta — not assumed, verified.

Every one of the 32 current failures/errors was extracted by exact test ID
and re-run, as a single batch, against an **isolated git worktree** checked
out at the immutable baseline `330cbe46df6230e06c10328e96018a48cb8d79bd`
(no `git stash` used anywhere in this session). Result on that baseline:
identical count (`failures=30, errors=2`) and a byte-for-byte identical set
of test names — `diff` between the two sorted failure-name lists is empty.
All 32 are therefore pre-existing and unrelated to the Task-8 corrective
fix or to any other Phase-4 change. **Zero new regressions.**

`manage.py check`: `System check identified no issues (0 silenced).`
`manage.py makemigrations --check --dry-run`: `No changes detected`.
`git diff --check`: clean.
Migration graph: single leaf (`storefront_builder.0020_r4_editor_enabled_default_true`), no conflicts.

## Step 3 — fresh architecture audit

Freshly re-verified (not copied from prior PASS text) against final HEAD:

- **One shared renderer**: `render_service.build_page_render_items` is the
  single render entry point. Public pages reach it via
  `storefront_context_service.build_universal_storefront_context`, whose
  callers span `apps/catalog/views.py` (Product Detail, Listing, Search,
  Collection Detail), `apps/cart/views.py` (Cart), and
  `apps/storefront_builder/views.py` (Home) — confirmed by direct call-site
  grep. R4 Preview (`storefront_preview` in `views.py`) calls the same
  `render_service.build_page_render_items` directly. No second renderer
  exists anywhere in the tree.
- **Ready Template authority**: `apply_preset`/`reset_storefront_to_baseline`
  in `preset_service.py` remain the sole apply/reset authority; the
  corrective fix added one existence check, no new decision path or
  parallel authority.
- **ResourceSource / Media authority**: single `resource_source.py` /
  `media_views.py` modules; no duplicates found.
- **Persistence authority**: `StorefrontLayoutVersion`/`StorefrontSection`
  defined once in `models.py`; no second layout/version model anywhere in
  the tree.
- **Stale-write protection**: `edit_revision` optimistic-concurrency check
  (`R4StaleRevision`) intact and unchanged.
- **Tenant isolation**: Store-scoped by construction
  (`get_or_create_draft(store, ...)`), no unscoped query paths found in the
  services touched this session.
- **Legacy retirement**: `editor.html`'s full legacy merchant-editing body
  renders only when a Store is explicitly pinned back
  (`r4_editor_enabled=False`); the live R4 default renders only the two
  documented, still-legacy-only compatibility capabilities (restore/history
  link, industry-layout-preset form).
- **Fresh section registry recount**: 36 registered sections
  (`SECTION_REGISTRY`), matching `family_certification_matrix.md`'s own
  "Section families (36)" heading exactly. No UNKNOWN/TBD/PENDING
  disposition found anywhere in `family_certification_matrix.md` or
  `legacy_disposition.md` — every non-CERTIFIED row carries an explicit,
  already-reviewed disposition (NO ACTION REQUIRED / DOCUMENTED AS ALIAS /
  RETIREMENT CANDIDATE / SAFE BY CONSTRUCTION).

## Step 4 — cumulative diff audit

Inspected cumulative Phase-4 changes, not only the corrective commit:

- `330cbe46` → final HEAD: **exactly 4 files, +309/-0** — the corrective
  fix (`preset_service.py` +13, one test file +34) plus two doc files.
  Nothing else changed. This is the tightest, most direct proof that
  certification-affecting production code is unchanged since the last
  known-good checkpoint.
- `185166a` (Phase-3 final base) → final HEAD, `969a9b4` → final HEAD, and
  `75ede8a` → final HEAD were all confirmed as real ancestors of HEAD and
  spot-checked for: duplicate renderer/writer/persistence/registry (none
  found — see Step 3), dead legacy write paths (none found ungated —
  legacy composition/settings/reset writes are template-conditional on
  `r4_editor_enabled`), migration anomalies (clean, single leaf, one
  reversible data migration flipping the R4-live-default flag with a
  documented `RunPython`/reverse pair), and Phase-5 scope creep (none
  found — one comment referencing "TEMPORARY-ADAPTER" is pre-existing
  Task-6/7 terminology for an already-reviewed allowlist pattern, not new
  scaffolding).

## Step 5 — final browser certification

A fresh run was required and performed, using the **existing** extended R4
QA harness (`manage.py qa_storefront_builder_r4` +
`tools/storefront_builder_r4_qa/run.mjs`) — no second harness created.

Getting to a clean run surfaced one **QA-fixture-setup artifact** (not a
production defect, documented here for anyone reproducing this
certification): the optional `seed_kianstock_qa_demo` demo-catalog seed
command is not required by the harness (it only needs an existing Store +
an `is_staff` user with an active membership) and, if run beforehand,
pollutes the `discounted_products`/`amazing_offers` family-gate scenario —
several unrelated demo products with discounts above the fixture's
deliberate 25% push the fixture's own discounted product out of the
default `item_limit=6` `-discount_percent` ranking. Re-running against a
bare Store (migration-seeded `akhlaghi`, no demo catalog) eliminated this
artifact entirely and also eliminated one further scenario failure
(`14-task7-composition-and-recovery`, a Playwright `execution context
destroyed` navigation-timing flake) that appeared once on the polluted
fixture and did not reproduce on the clean one.

Final clean run — canonical evidence committed under
`docs/qa_evidence/storefront_appearance_convergence/phase4/browser_final/`
and `docs/qa_evidence/storefront_builder/r4/phase1/`, belonging to THIS
HEAD's run, not reused from any earlier evidence:

- **Browser PASS: 20 / 20**
- **Browser FAIL: 0**
- **DB restore:** pre/post SHA256 match — `a97f2fcd0cd93b93846c0fe1d63fff56113bd61687056aa33ac0c1ff7fe73697` == `a97f2fcd0cd93b93846c0fe1d63fff56113bd61687056aa33ac0c1ff7fe73697` (`match: true`)
- **Viewports:** 1440x900 (desktop), 768x1024 (tablet), 390x844 (mobile) — all three, via `--phase3`
- **Page envelopes:** Home, Product Detail, Listing, Search, Collection Detail, Cart, Collection Index boundary — all present (verified via the `brand`/`collection`/`collection-index`/`fragments` evidence subdirectories)
- **Tenant-negative:** unauthenticated GET against the real Preview view/permission stack → `302` (redirect to login), `rejected: true` — matches the pre-Task-10 baseline exactly
- **Unexpected console/page/network errors:** 0 (`browser.log` scanned for error/uncaught/net::ERR signatures beyond the harness's own documented exemptions — none found)
- No stale `FAILURE-*.png` remain (this run was clean; none were produced or left over)

## Step 6 — final independent review

One fresh reviewer, dispatched in an isolated git worktree, read-only in
spirit, inspecting current HEAD, the cumulative diff, and this session's
fresh Task-10 evidence (regression classification + browser evidence) —
independently re-ran Cases A/B/C plus 86 additional targeted tests (OK),
independently confirmed the `330cbe46`→HEAD diff is exactly the scoped
corrective fix, independently traced the one-shared-renderer and
legacy-retirement-gating claims in source, and independently read the
committed browser evidence JSON (confirmed genuinely committed at HEAD,
not fabricated).

Verdicts — all PASS:

SPEC COMPLIANCE, ARCHITECTURE, CANONICAL AUTHORITY, NO PARALLEL ENGINE,
NO PARALLEL WRITER, R4 FINAL EDITOR, NON-HOME BUILDER, FAMILY CONVERGENCE,
LEGACY RETIREMENT, TENANT/LIFECYCLE SAFETY, BROWSER CERTIFICATION.

**CRITICAL: 0. IMPORTANT: 0. MINOR: 0.**

## Final Phase-4 status

All FINAL PASS REQUIREMENTS items are satisfied: SPEC COMPLIANCE,
ARCHITECTURE, CANONICAL AUTHORITY, NO PARALLEL ENGINE, NO PARALLEL WRITER,
ONE SHARED RENDERER, ONE LIFECYCLE, R4 FINAL EDITOR, ONE MERCHANT EDITOR,
APPEARANCE PARITY, HEADER PARITY, FOOTER PARITY, COMPOSITION PARITY, MEDIA
PARITY, NON-HOME BUILDER, PAGE APPEARANCE PRECEDENCE, RESOURCE SOURCE
AUTHORITY, READY TEMPLATE AUTHORITY, TEMPLATE SWITCH CONTENT PRESERVATION,
FAMILY CONVERGENCE, LEGACY RETIREMENT, TENANT/LIFECYCLE SAFETY, MIGRATION
HISTORY, NO PARALLEL PERSISTENCE, BUSINESS-DOMAIN OWNERSHIP, NO PHASE-5
SCOPE CREEP, BROWSER CERTIFICATION — the parity/precedence/authority items
not independently re-derived from scratch this session were confirmed
unchanged since their own prior CERTIFIED disposition in
`family_certification_matrix.md`/`legacy_disposition.md`, per the
cumulative-diff audit above showing no production code affecting them
changed since `330cbe46`.

Reviewer: CRITICAL 0, IMPORTANT 0, MINOR 0.

**PHASE 4: CLOSED. PHASE 5: NOT STARTED.**
