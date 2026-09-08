# Phase 4 execution ledger

Chronological record of Phase-4 task starts/completions, commits, and backup refs. Append-only.

## Task 0 — Plan + baseline

- **START** 2026-09-08. Preconditions verified: `origin/feature/phase4-architecture-audit` ==
  `969a9b411ca712928c2bf31416bdde2ee8aaabb5`; `origin/backup/rastisi6-phase4-architecture-audit-20260907`
  == same SHA; audit commit parent == `185166a138e47c012b3af7f53ea6bcb94fb84bd0` (Phase-3 final);
  `origin/main` == `973c1dc00bacb6f2f7d2604fa3880bb4d6250579` (unchanged); no pre-existing
  `feature/phase4-builder-legacy-convergence` or `backup/rastisi6-phase4-start-20260908` ref found.
- Created `feature/phase4-builder-legacy-convergence` from `969a9b4` and
  `backup/rastisi6-phase4-start-20260908` == `969a9b4`; both pushed and verified at that exact SHA.
- Section registry recounted fresh: 36/36 keys classified (see the plan document §0). Matches the
  audit's count exactly — no drift since the audit commit, as expected (same SHA lineage).
- Baseline Run A/B/C executed verbatim from `phase3/baseline.md`'s exact command lists (see
  `phase4/baseline.md` for full results).
- Plan committed as a checkpoint (`b55c37d`), pushed, then sent to a fresh independent reviewer.
  Verdict: SPEC COVERAGE PASS, ARCHITECTURE PASS, CRITICAL 0, IMPORTANT 5, MINOR 3. All 8 findings
  resolved by editing the plan (Task 2 SECURITY STOP condition restated; Task 3C's full Ruling-F
  contract spelled out; Task 4's 3 required QA-harness generalizations all listed; Task 5/6 group
  assignments for `amazing_offers` fixed and Task 6 Groups A–F concretely defined; Task 10's
  18-item audit and 11-line reviewer verdict spelled out in full; stale Task-0 checkbox and the
  `origin`-vs-`rastisi5` remote note resolved). Fix-up committed as a follow-up (not an amend).
- **COMPLETE** 2026-09-08. Task 0 gate: SPEC COVERAGE PASS, ARCHITECTURE PASS, 0 unresolved
  CRITICAL, 0 unresolved IMPORTANT. Proceeding to Task 1.

## Task 1 — Appearance + Ready-Template authority convergence

- **START** 2026-09-08. Empirically verified (not assumed from audit prose) that the real defect
  is narrower than "manifest erased": a non-Ready preset's header/footer overlay updates the
  legacy `header_config`/`footer_config` mirror but never the typed manifest, which is the actual
  render authority — so the merchant's explicit choice was silently ignored by the rendered
  storefront. RED tests added, fix applied to `preset_service.apply_preset` (route the overlay's
  `header_variant`/`footer_variant`/`mobile_nav_variant` through the existing
  `appearance_authority_service.apply_header_variant`/`apply_footer_variant` primitives). Zero
  regression across the full Phase-3 baseline Run A/B/C. Committed as a checkpoint (`5ae1ffc`),
  pushed, then sent to a fresh independent reviewer.
- Reviewer verdict: PASS, 0 CRITICAL, 0 IMPORTANT, 2 MINOR (untested `mobile_nav_variant` branch;
  evidence doc should note the deliberate deviation from the audit's suggested
  `apply_ready_template_appearance` routing). Both resolved: added
  `test_non_ready_preset_mobile_nav_variant_updates_manifest_not_just_mirror` (37/37 in the module
  now) and expanded `task1_authority.md`'s review section to explain the architecture choice.
- **COMPLETE** 2026-09-08. Task 1 gate: 0 unresolved CRITICAL, 0 unresolved IMPORTANT. Proceeding
  to Task 2.

## Task 2 — ResourceSource read/write + tenant ownership convergence

- **START** 2026-09-08. Characterized the real divergence: legacy never checked `product_section`'s
  single-reference auto `source_id`; R4's ownership check no-opped for `category` kind. Investigated
  the SECURITY STOP condition first — confirmed the render path independently re-scopes every
  `source_id` by Store, so the write-side gap was never an exploitable data leak (documented in
  `phase4/task2_resource_source.md`). Added a category `ResourceSource` adapter, one shared
  DB-backed ownership function in `section_data_service.py`, and made legacy + R4 both delegate to
  it. RED tests confirmed the gap empirically (stash/restore), zero regression across 207 targeted
  tests and Phase-3 baseline Run A/B/C. Committed as a checkpoint (`aaf9162`), pushed, sent to a
  fresh independent reviewer.
- Reviewer verdict: PASS, 0 CRITICAL, 1 IMPORTANT (the unification test only exercised R4's call
  site, not legacy's, under the shared mock), 1 MINOR (a resulting unused import). Both resolved:
  the test now exercises both call sites under the same patch and asserts `call_count == 2`.
- **COMPLETE** 2026-09-08. Task 2 gate: 0 unresolved CRITICAL, 0 unresolved IMPORTANT. Proceeding
  to Task 3.
