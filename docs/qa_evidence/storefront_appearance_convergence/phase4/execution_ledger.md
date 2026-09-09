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

## Task 3 — Page Appearance + R4 non-Home + live entry (3A/3B/3D/3E, then 3C)

- **START** 2026-09-08. Executed 3A (real R4 dashboard entry point, gated on the existing
  `r4_editor_enabled` per-store flag — deliberately not flipped globally since R4 lacks Task 7's
  composition/media parity yet), 3B (generalized `section_structure_service`/`r4_views`/`r4_editor.js`
  from Home-only to all 6 page types via one shared `StorefrontPage.resolve_page_type`), 3D (audited
  and confirmed-by-construction the Collection Index/Detail boundary per Ruling L, added the
  explicit documentation and end-to-end leak-proof test the ruling requires), and 3E (fixed the
  Listing/Search HTMX fragment context-propagation gap — both paths now call the same canonical
  context builder). Zero regression across 398 targeted tests and Phase-3 baseline Run A/B/C.
  Committed as a checkpoint (`baab587`), pushed, sent to a fresh independent reviewer.
- Reviewer verdict (3A/3B/3D/3E): PASS, 0 CRITICAL, 0 IMPORTANT, 1 MINOR (an operational incident
  during the review itself — see below — not a code defect).
- Implemented 3C (the Page Appearance tier, Ruling F) as a separate commit per the Master Prompt's
  explicit allowance: investigated for an existing canonical JSON surface (none — `StorefrontPage`
  had no field of its own), added a minimal forward migration
  (`0019_page_appearance_overrides.py`), chose the bounded 5-key allowlist from evidence (the
  pre-existing sparse-by-design structural fields, architecturally distinct from the core-identity
  tokens `_global_identity_version` requires stay Store-global), built the canonical write primitive
  and resolver, and wired them into the exact rendering path Preview and Public already share.
  Found and fixed a real latent bug during end-to-end testing: `_clone_version_content` never
  copied `page_appearance_overrides` when a Draft is spun off a Published version, so a published
  override would silently vanish on the next edit session — caught by this task's own
  Preview-vs-Public-after-publish test. Zero regression across 395 targeted tests. Committed
  (`5713b4b`), pushed, sent to a fresh independent reviewer.
- **Operational incident** (documented candidly in `phase4/task3c_page_appearance.md`'s closing
  note): while Task 3C was still in progress (uncommitted), a background reviewer working on the
  already-committed 3A/3B/3D/3E chunk performed a `git checkout <parent-commit> -- <file>` RED-
  verification step on the SAME shared working tree, which briefly reverted two of Task 3C's
  in-progress edits (`models.py`'s new field, `views.py`'s `storefront_preview` change) before
  restoring the tree to the last commit. Both edits were detected missing (via `git status`/grep)
  and re-applied; the real dev database's one corrupted scratch row (created during diagnosis) was
  cleaned up; the full test suite and `makemigrations --check` were re-verified clean before
  committing. No lasting damage to committed history. Noted here so a future session in this same
  environment knows background review agents and the primary session can collide on one shared
  working tree, and that RED-verification should use an isolated `git worktree` instead (the
  Task 3C reviewer was explicitly instructed to do this).
- Reviewer verdict (3C, performed in an isolated `git worktree` per the incident note above): PASS,
  0 CRITICAL, 0 IMPORTANT, 2 MINOR — (1) no `@transaction.atomic`/row-lock around
  `apply_page_appearance_patch`'s check-then-save, matching the pre-existing sibling
  `apply_appearance_patch`'s same shape, not a new weakness; (2) no merchant-facing UI/API endpoint
  yet for this tier, already explicitly disclosed as an intentional, in-scope-boundary limitation in
  `task3c_page_appearance.md`. Both informational, neither blocks the gate. Independently
  re-verified the `_clone_version_content` fix is load-bearing (isolated-worktree RED reproduction
  with only that fix removed) and the 5-key allowlist is genuinely enforced (live `manage.py shell`
  reproduction, not just documentation).
- **COMPLETE** 2026-09-08. Task 3 gate (3A/3B/3C/3D/3E all reviewed): 0 unresolved CRITICAL, 0
  unresolved IMPORTANT. Proceeding to Task 4.

## Task 4 — Generalize the certified R4 QA browser certification harness

- **START** 2026-09-08. Ran `--phase3` before any code change to derive the exact baseline
  the plan requires be preserved: `metrics.json` showed `variant_checks.length === 45`
  (Brand) and `collection.variant_checks.length === 36` (Collection), `known_red_findings`
  empty, 0 console/page/request errors, DB restore SHA256 match — saved as the pre-refactor
  baseline to diff against, explicitly distinguished from the coarser scenario-level
  "16/16 PASS" count.
- Extracted the duplicated Brand/Collection browser assertion block in `run.mjs` into one
  shared `phase3FamilyPublicMatrix(cfg)` covering every listed assertion category (asset
  envelope, document overflow, RTL, computed grid/flex layout, objectFit, native scroll,
  keyboard focus, error collection), with each family's distinct business logic (tile
  shape/order semantics, the Brand-throws-vs-Collection-records layout-mismatch policy,
  Brand's V02 view-all-anchor check) injected via config. Restructured `manifest.phase3`'s
  single boolean into a `PHASE3_FAMILIES` gate-registration loop. Backfilled a registry-wide
  schema-enable guard (`SchemaEnablementRegistryGuardTests`) covering all 36 registered
  section keys (previously only `image_slider`/`faq` were spot-checked).
- Re-ran `--phase3` post-refactor and diffed `metrics.json` against the saved baseline:
  Brand 45/45 and Collection 36/36 unchanged, 0 known-red findings, 0 errors, DB restore
  hash match, only one strictly-additive metrics field difference. One real bug (a
  Playwright `locator.evaluate()` call passed two positional arguments instead of one
  bundled object) was caught by this exact re-run (`FAIL phase3-brand-gate`) and fixed
  before commit.
- Official Phase-3 baseline Run A/B/C: 953 tests total, 3 failures + 1 error + 1 skip, all
  matching known-or-newly-classified pre-existing signatures. One failure
  (`test_header_footer_variant_labels_shown_for_updated_preset`) had not been previously
  documented; isolated, reproduced standalone, then reproduced identically against the
  clean parent commit (`9bacc80`) via `git stash` — confirmed pre-existing and unrelated to
  this task, not a new regression. Committed as a checkpoint (`130a876`), pushed, sent to a
  fresh independent reviewer with explicit instructions to use an isolated `git worktree`
  for any RED-verification (per the Task 3C incident) rather than the shared tree.
- Reviewer verdict: PASS, 0 CRITICAL, 0 IMPORTANT, 2 MINOR (a cosmetic assertion-message
  wording change with no functional effect or repo references; a docstring referencing a
  non-existent `EXPECTED_UNSCHEMATIZED` attribute name). The reviewer independently
  reproduced the pre-existing-failure classification via its own isolated worktree
  (`git worktree add`/`remove`, never touching the primary checkout) and confirmed it.
  The docstring MINOR was fixed (now correctly describes unschematized as implicit — any
  registered key not in `EXPECTED_SCHEMA_ENABLED`); re-verified 64/64 in
  `test_r4_settings_schema`.
- **COMPLETE** 2026-09-08. Task 4 gate: 0 unresolved CRITICAL, 0 unresolved IMPORTANT.
  Proceeding to Task 5.

## Task 5 — Cross-page CSS completeness

- **COMPLETE** 2026-09-08/09. All groups (A–E, plus the `brand_carousel` `beauty_tabs` gap)
  completed as one batch per the simplified execution model, one complete verification run, one
  independent isolated-worktree review (0 CRITICAL, 2 IMPORTANT — both real dead-CSS findings on
  Home, fixed by removal and RED/GREEN-verified via real-browser ground truth, not invented
  replacement values). Committed across `79c53c6`/`f09e5cf` (CSS work) and `89f34df` (family
  certification matrix CSS-completeness column). See `phase4/task5_cross_page_css.md` for the full
  per-group evidence. Proceeding to Task 6.

## Task 6 — Converge every required product-facing family

Full narrative evidence in `phase4/task6_family_convergence.md`; this entry is the chronological
commit-by-commit summary.

- **START** 2026-09-09. Gap-analysis investigation surfaced two pre-existing defects entangled
  with Group C/D scope (Finding 1: `category_grid` ResourceSource inert without a schema; Finding
  2: legacy-form Save destructively wiping `trust_features`/`amazing_offers`/`blog_posts`) — both
  fixed and pushed as `2664792` before group work began.
- Group A (`image_slider`'s own schema): `72e3cca`.
- Group C (`blog_posts`): `a956ad9`.
- Group D "easy batch" (`amazing_offers`, `quick_links`, `video_section`, `newsletter`): `13c0143`.
- Group C (`image_text`): `cd17eb7`.
- Group C (`multi_banner` real closed-enum validator + schema; `single_banner` explicit
  FIXED/STATIC disposition comment): `5a2169c`.
- Group B (`newest_products`/`best_sellers`/`discounted_products`/`promo_cards` `item_limit`):
  `49ffda5`.
- Group D (`trust_features`/`faq`/`testimonials` — the new `repeater` settings-schema field type,
  built end to end: `settings_schema.py` contract, `r4_views.py` allowlist, the Inspector
  template/JS/CSS, and the three families' schemas). Two real defects found only by real-browser
  verification (a duplicate-request race from an unguarded generic listener; an eagerly-saved,
  guaranteed-to-fail empty row on every "add" click) were fixed before this checkpoint — see
  `phase4/task6_family_convergence.md` for the full browser-proof record. **Checkpoint SHA and
  backup ref recorded once pushed below.**
- Zero regressions across the full `apps.storefront_builder` suite after every one of the commits
  above (each pushed only after a matching full-app run showed no new failures beyond the same
  pre-existing 30 failures/2 errors/4 skips — 2 of them, `FullscreenEditorTests`, confirmed
  pre-existing on clean HEAD independently; the other 28/1 confirmed identical to the Task-4-era
  baseline by exact test-name match). "Exactly one session may write/push this branch" discipline
  maintained throughout: `git fetch` + SHA comparison before every push, no concurrent-writer
  collision.
- **Group D checkpoint gate** (this document's own review, at the Product Owner's explicit
  request — not a full Task 6 gate; `story_rail`, Group E, Group F, and Task 7 remain open):
  browser proof PASS (see above), targeted + full-app regression PASS (same pre-existing
  signatures only), `manage.py check`/`makemigrations --check --dry-run`/`git diff --check` all
  clean. Proceeding only as far as this checkpoint; Task 6 itself is NOT complete.

- **Batch 1 — Group E certification + Group F reconciliation** (fast-continuation session,
  2026-09-09). Both groups investigated and certified AS-IS — no production code change in either
  group. See `phase4/task6_family_convergence.md` for the full investigation record. New
  certification test file: `apps/storefront_builder/tests/test_phase4_task6_group_f_reconciliation.py`
  (10 tests, all GREEN). Targeted regression across Group-F-adjacent modules
  (`test_phase4_task6_group_f_reconciliation`, `test_phase1_appearance_authority`,
  `test_r4_store_appearance_mutations`, `test_r4_mutation_api`, `test_section_registry`,
  `test_u10_ready_template_catalog`, `test_a8_ready_template_contracts`): 428/428 GREEN.
  `manage.py check`: clean. `makemigrations --check --dry-run`: no changes detected. Committed and
  pushed as `e524a35`. Proceeding to Batch 2 (`story_rail`).

- **Batch 2 — story_rail media-form/model convergence** (fast-continuation session, 2026-09-09).
  Investigated first per the plan's instruction; found a real, live defect (not just a missing
  schema): `storefront_section_media_form` hardcoded the `desktop_image`/`mobile_image` pair that
  `HeroSlide`/`PromotionalBanner` have, but `StoryRailItem` has one `image` field — editing (not
  creating) any existing story item raised `AttributeError` unconditionally, a real 500 reachable
  from the Storefront Builder's own "ویرایش" link. Fixed by making the shared form genuinely
  model-agnostic (`_MEDIA_KINDS[kind]["file_fields"]`, looped over in both the view and
  `section_media_form.html`), unifying `asset_fields` as the one mapping shared by create/edit AND
  delete (no second media model, no second media authority — reuses the existing `MediaAsset`/
  `_sync_asset_references`/`delete_media_asset_if_unreferenced` machinery). See
  `phase4/task6_family_convergence.md` for the full investigation and fix record. New test class
  `StoryRailItemCrudTests` in `test_media_views.py` (9 tests). Targeted regression: `test_media_views`
  alone 29/29 GREEN; broader media/lifecycle-safety sweep (`test_admin_v22_live_builder`,
  `test_g22_on_g21_integration`, `test_g2_1_media_editability_roundtrip`, `test_media_views`,
  `test_media_write_path`, `test_phase2_lifecycle_safety`) 132/132 GREEN. `manage.py check`: clean.
  `makemigrations --check --dry-run`: no changes detected (view/template-only fix, no model
  change). Committed and pushed as `f98930b`. All Task-6 implementation is now complete;
  proceeding to Batch 3 (Task-6 final gate).

- **Batch 3 — Task-6 final gate** (fast-continuation session, 2026-09-09). Full
  `apps.storefront_builder` suite run once, per the speed policy: first attempt corrupted by this
  session's own mid-run venv-directory rename (154 spurious errors, traced to a `PIL`/`bs4`/Django-
  template-lookup breakage at the renamed path — discarded in full, not partially trusted); a
  genuinely clean re-run produced 2785 tests, 30 failures/2 errors/4 skips, verified by exact
  failure/error NAME match (not just count) against the frozen baseline — zero new regressions.
  `manage.py check`/`makemigrations --check --dry-run`/`git diff --check` all clean. Browser
  certification: investigated the actual harness before running anything — Task 4 only generalized
  the Brand/Collection tile-matrix helper, never built scenario code for the other ~20 Task-6
  families; put the scope question to the Product Owner rather than silently claiming coverage
  that doesn't exist or unilaterally building a large new harness extension; decision: run the
  harness's existing generic scenarios (13 R4 workflow scenarios + `phase3-brand-gate`) as-is and
  record the gap honestly. Ran it (dev DB freshly migrated + a throwaway QA user, container started
  with an empty `db.sqlite3`): 16/16 scenarios PASS, Brand 45/45 + Collection 36/36 variant checks,
  0 real errors, DB restore SHA256 verified byte-for-byte on both invocations. Full record in
  `phase4/task6_family_convergence.md`'s "Task 6 final gate" section. Committed and pushed as
  `0cae527`.

- **Independent Task-6 review + fix cycle** (fast-continuation session, 2026-09-09). A fresh
  isolated-worktree reviewer with no prior context reviewed the cumulative Task 6 diff
  (`a31da39..f98930b`). Verdict: CRITICAL 1, IMPORTANT 2, MINOR 2 — all real, empirically
  reproduced findings (the `card` family's Group F certification rested on a false "no local write
  path" premise; a real merchant-facing `card_style` write path existed and was silently
  overridden by the render-time overlay; a destructive-Save regression in `amazing_offers`'s
  legacy form; a duplicate-`title`-input data-loss bug in the new story-item form; a missing
  story-item thumbnail; dead test code). All fixed — see `phase4/task6_family_convergence.md`'s
  "Independent Task-6 review" section for the full record. Full `apps.storefront_builder` suite
  re-run once more after the fix (the `card` fix touches `render_service.py`'s cross-cutting
  per-section overlay): 2791 tests, 30 failures/2 errors/4 skips, byte-for-byte identical
  failure/error names to the pre-fix run — zero new regressions. `manage.py check`/
  `makemigrations --check --dry-run`/`git diff --check` clean. Committed and pushed as `f7e71b9`.
  Matrix corrected: `card`'s CERTIFIED status now reflects the actual (fixed) contract rather than
  the disproven claim; `story_rail`'s CLOSED status now also covers the two defects the review
  found in that same commit. No second review round required — every finding was concrete and
  fixed; no new finding surfaced during fix verification. **Task 6 is now CLOSED.**
