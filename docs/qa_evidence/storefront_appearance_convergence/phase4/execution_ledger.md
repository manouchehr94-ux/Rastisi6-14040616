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
  fixed; no new finding surfaced during fix verification.

- **A1/A2 — genuine browser certification for 6 more Task-6 families** (continuation session,
  2026-09-10). The prior session's "Task 6 is now CLOSED" note above was this session's own
  starting state, not yet meeting the stricter closure bar this session's own instructions set (a
  second, harder round of browser certification plus one more independent review). Extended the
  EXISTING Task-4 harness (never a second harness): `category_grid`/`multi_banner`/`image_text`/
  `newsletter` each get one representative Inspector field edit with a real persisted-value and/or
  DOM assertion (one per remaining SettingsSchema field TYPE, not one registration per family);
  `story_rail`/`single_banner` get a presence-through-Preview proof matching their actual FIXED/
  STATIC or media-only disposition. 6 iterations of real debugging against actual template
  rendering behavior (advanced-tab activation, `change`-not-`input` event firing, real
  `ResourceSource` shape, empty-banner-pool rendering) — see `task6_family_convergence.md` for the
  full reasoning per family. Additive-only: `git show --stat` on the commit shows zero deleted
  lines. Committed and pushed as `d8489c4`.

- **A3 — second independent Task-6 review** (continuation session, 2026-09-10). A second fresh
  isolated-worktree reviewer, reviewing `d8489c4` for (a) whether the first reviewer's four fixes
  still hold and (b) whether the new harness commit is sound. Verdict: CRITICAL 1, IMPORTANT 2,
  MINOR 3 — the `card_style_explicit`/`variant_explicit` markers were durable across exactly ONE
  save, then silently dropped again by the next unrelated one (neither `CARD_AWARE_SECTION_KEYS`
  nor `product_section` were actually in `APPEARANCE_OVERRIDE_AWARE_SECTION_KEYS`); the
  `story_rail`/`single_banner`/`multi_banner` browser-cert fixture placed sections with no backing
  media row, so the harness's visibility check was passing on the generic empty-Section placeholder
  alone; plus three MINOR docs/coverage/instrumentation nits. All six fixed — see
  `task6_family_convergence.md`'s "Second independent review" section for the full record,
  including exact fix descriptions. Targeted re-verification: `test_phase4_task6_group_f_
  reconciliation` (15/15, 3 new marker-durability regression tests), `manage.py check`/
  `makemigrations --check --dry-run`/`git diff --check` clean. Full `apps.storefront_builder` suite
  re-run once (the fix touches the shared `section_registry.py` validator wrapper every
  schema-enabled section goes through): 2807 tests, 30 failures/2 errors/4 skips — the exact same
  three counts as the frozen baseline despite ~16 more tests running and passing; spot-verified two
  of the visible failures reproduce identically via `git stash` (pre-existing, unrelated).
  Committed and pushed as `77b0cf3`.

- **Batch 1/2 — R4 Task 7 composition + recovery parity** (continuation session, 2026-09-10, in
  parallel with the Task-6 re-review above). B1 gap audit classified all 20 required Task-7
  capabilities by reading the actual current implementation first (never assuming missing because
  the R4 UI doesn't obviously expose something) — 9 already complete, 2 not applicable (superseded/
  compat-only), 9 real gaps. Batch 1 (composition): `section.toggle_active`/`section.toggle_locked`
  (the Preview toolbar already sent these commands; R4 Task 8 had deliberately left them
  unhandled) and `container.change_layout` (multi-column reshape, reusing
  `container_service.change_container_layout` unchanged) wired as new R4 mutation types. Batch 2
  (recovery): the six `preset_service` baseline-reset granularities wired in (section/section-
  setting/appearance-setting/header/footer as in-place mutation types; page/storefront as dedicated
  endpoints since they replace the Draft's identity via a checkpoint, exactly like Publish); a
  dedicated Discard endpoint (the service existed but had no UI entry point in either editor). See
  `task7_r4_composition_media_parity.md` for the full per-capability record. Committed and pushed
  as `2bd3c77`.

- **Batch 2 bugfix + Batch 3 media reachability** (continuation session, 2026-09-10). Running the
  previously-untested Batch 2 test classes (deferred earlier while the full-suite run above was
  using the shared test DB) found two real bugs: the five in-place reset mutation types only caught
  `preset_service.BaselineResetError`, missing that `NoTemplateBaselineError` (a Draft with no
  Ready Template baseline — exactly the case these mutations must reject cleanly) is actually an
  `InvalidPresetError` subclass, so resetting anything on such a Draft raised an unhandled 500; and
  a new test class called a `_refresh_revision()` helper that only existed on a sibling base class.
  Both fixed; `test_r4_vertical_slice.py` re-run clean (135/135, only the one confirmed
  pre-existing failure). Batch 3 (media + cross-page parity): the R4 Inspector had no path to the
  existing media CRUD screens at all, and 404'd outright for schema-less media-only families
  (`story_rail`/`single_banner`) — a merchant could not even open an Inspector panel for them.
  Fixed with `media_views.media_kind_for_section_key` (reverse lookup, no new registry) threaded
  into the Inspector view: a link to the existing legacy media screen for schema-enabled
  media-owning sections, and a new minimal media-only Inspector partial (same
  `data-r4-section-inspector` contract) for schema-less ones — never a new media UI/authority.
  `test_r4_inspector.py` (55/55, including 4 new tests + 2 existing tests corrected to the new
  intended contract) and `test_media_views.py`+`test_r4_resource_picker.py` (100/100) both clean.
  Committed and pushed as `7347b8b`, evidence doc update as `b5a38c6`.

- **Third independent review (re-review after the second review's fix cycle)** (continuation
  session, 2026-09-10). Per the closure requirement's own "re-review the final state" step, a
  third fresh isolated-worktree reviewer verified the six C1/I1/I2/M1/M2/M3 findings above were
  genuinely fixed (including by deliberately reverting each half of the C1/I1 fix in isolation and
  confirming the corresponding regression test fails for exactly the right reason — proving the
  tests are not vacuous) and checked the fix itself for new defects. Verdict: CRITICAL 0, IMPORTANT
  1, MINOR 3. The IMPORTANT finding: the new M3 instrumentation guard's `http_error_responses`
  snapshot was missing the same broken-image/stale-409 filters its sibling arrays already applied,
  so the Collection gate's own deliberately-broken-image fixture (placed on Home, from an earlier
  Task-5 fixture) would make the Task-6 family gate fail spuriously on every page reload —
  precisely the opposite of what the M3 fix was meant to achieve. Fixed, along with three MINOR
  nits (misaligned diagnostic-message slicing, a stray module-level constant mid-import-block, a
  misplaced Sphinx doc-comment). Also raised as a non-blocking observation (pre-existing since
  Phase 1, not introduced by this task, and explicitly not treated as an in-scope defect): now that
  the override markers are durable, there is no merchant-facing way to clear one — recorded as a
  product-level question for a future task, not a Task 6 defect. Re-verification:
  `test_phase4_task6_group_f_reconciliation` (15/15), `manage.py check`/`makemigrations --check
  --dry-run`/`git diff --check` clean, `run.mjs`/`section_registry.py` both `node --check`/
  `py_compile` clean. **CRITICAL 0 / IMPORTANT 0 after this round's fixes — Task 6 is now CLOSED.**

- **Full `apps.storefront_builder` regression gate + browser certification campaign (Task 7 B4/B5)**
  (continuation session, 2026-09-10). Full suite (2833 tests) compared failure/error test names
  against the frozen baseline (30 failures/2 errors/4 skips) — exact match, zero new regressions.
  One consolidated browser scenario (`scenario14CompositionAndRecoveryGate` in
  `tools/storefront_builder_r4_qa/run.mjs`, registered as the absolute last scenario since Discard
  destroys the Draft's identity) built to exercise composition, multi-column placement,
  enable/disable, lock, granular-reset gating, media Inspector link, non-Home page switch, and
  Discard in one run against the shared `akhlaghi`/`task6_qa_owner` QA fixture — clean on first run.

- **Fourth independent review (Task 7)** (continuation session, 2026-09-10; agent
  `a753cb49608d991a6`, fresh isolated worktree against the full Task-7 diff since the Task-6
  baseline `559af59`). Verdict: CRITICAL 0, IMPORTANT 2, MINOR 8. IMPORTANT-1:
  `#r4ResetStorefrontButton`'s directly-bound click handler silently stopped firing after any other
  Global Design edit (its container's `innerHTML` gets replaced) — moved into the existing
  delegated click listener. IMPORTANT-2: `container.change_layout`'s grow branch could create a
  Cell no R4 mutation could ever fill — fixed with a new `section_structure_service.
  add_section_to_cell`/`_scoped_cell`, a new `cell.add_section` mutation type, and a new
  "empty cells" picker UI, mirroring the legacy `storefront_cell_add_section` view's own logic.
  4 of 8 MINORs fixed (stale-screenshot handling, triplicated test helper, a private-dict
  reach-across-module, raw-English layout-preset labels); 1 verified fixed as a side effect
  (an entirely empty container); 2 accepted as disclosed/defensible per the reviewer's own framing;
  1 (duplicated Draft-section-scoping across 3 call sites) also fixed, consolidated into one
  `_scoped_section` helper in `r4_mutation_service.py`. Also strengthened the browser scenario with
  a real click-through proving `cell.add_section` end-to-end. Re-verified: targeted suite (236
  tests, only the one frozen-baseline failure), full 16-scenario browser harness, sanity checks —
  all clean. Committed and pushed as `49929e1`. See `task7_r4_composition_media_parity.md`'s
  "Batch 4" section for the full per-finding record.

- **Fifth independent review (Task 7)** (continuation session, 2026-09-10; fresh isolated worktree,
  diff scoped to `559af59..49929e1`). Verdict: CRITICAL 0, IMPORTANT 1, MINOR 1. IMPORTANT-1: the
  brand-new `cell.add_section` mutation type — writing through a brand-new Draft-scoping helper —
  had zero Django-level regression tests for its negative paths, unlike every sibling Task-7
  mutation type; the browser scenario alone only proved the same-tenant happy path. Fixed with a
  new `CellAddSectionTests` class (10 tests: empty-cell success, occupied-cell success, locked-
  container/invalid-key/hidden-from-library/max-instances/nonexistent-cell/non-integer-cell/
  foreign-store-cell/stale-revision rejection). MINOR-1 (a docstring overstating byte-identical
  label reuse with the legacy layout picker) reworded for accuracy. Re-verified: new tests (10/10),
  full targeted re-run (246 tests, only the one frozen-baseline failure), sanity checks clean.
  Committed and pushed as `b6605d4`.

- **Sixth independent review (Task 7 — final)** (continuation session, 2026-09-10; fresh isolated
  worktree, full diff `559af59..b6605d4`, including actually running the new `CellAddSectionTests`
  and confirming by inspection that each guard is load-bearing). **Verdict: CRITICAL 0, IMPORTANT 0,
  MINOR 2 — required bar cleared.** MINOR-1: the `cell.add_section` browser assertion's DOM-presence
  selector referenced an admin-only Structure-panel attribute that never appears in Preview's own
  storefront-rendered markup, silently weakening the check to "does this section-key exist
  anywhere on the page" — fixed to use Preview's real per-section `data-container-id` attribute,
  genuinely scoping the check to the target Container. MINOR-2: `add_section_to_cell`'s docstring
  overstated "same validation order" as the legacy view (the checks match, plus one this function
  additionally enforces; only the order differs, and only because this entry point must resolve
  the Cell first) — reworded for accuracy. Both mechanical, non-functional fixes; re-verified via a
  full 16-scenario browser harness re-run (not a fourth review round, since neither fix touches
  mutation/scoping logic) plus `py_compile`/`node --check`/sanity checks — all clean. Committed and
  pushed as `ab22e3d`. **Task 7 is now CLOSED.**

- **Task 8 — Template Switch + lifecycle hardening, Batch 1+2** (continuation session,
  2026-09-10). Short gap audit (12 requirements, using the committed Phase-4 architecture audit plus
  direct code reads — no broad archaeology) found the real gap: `preset_service.apply_preset` always
  wipes/rebuilds page composition for every recipe-covered page, so switching a store's Ready
  Template has never been possible without losing merchant content; `appearance_authority_service.
  apply_ready_template_appearance` (a canonical, already-tested DNA-only primitive) had zero
  production callers. Batch 1: `preset_service.switch_template_preserving_content` (checkpoint-clone
  + DNA-only apply, reusing both canonical primitives unchanged); a new Draft-replacing
  `r4_mutation_service.switch_template` + `storefront_r4_switch_template` view/URL, same contract
  shape as Publish/Discard/Reset-page/Reset-storefront; kept deliberately separate from the
  pre-existing, already-tested `appearance.template.apply` full-recipe mutation type (two genuinely
  different operations); new Global Design panel picker UI. Batch 2 (three items from the earlier
  architecture audit, §5 conflict #6): legacy `storefront_section_remove`/`storefront_section_move`
  gained the container-lock check R4's own equivalents already had (reusing
  `section_structure_service.find_placement_cell`, made public for this); `container_service.
  move_block` gained a source-side container-lock check (a first attempt hit a real intra-request
  ORM-staleness bug, caught by a RED test before the fix); `@transaction.atomic` added to three
  legacy structure views; the legacy Publish form's missing `base_revision` field added. Targeted
  tests: 8 new `TemplateSwitchPreservingContentTests`, 4 new container-lock-parity tests, 1 new
  move_block source-lock test, 3 new publish-base_revision tests — all pass; full targeted
  regression across every touched module (606 tests) showed only the 3 already-documented
  pre-existing frozen-baseline failures. Committed and pushed as `542197b`.

- **Task 8 browser certification** (continuation session, 2026-09-10). `scenario15TemplateSwitch
  LifecycleGate` added to the R4 browser QA harness (registered after Task 7's own last scenario),
  exercising the full workflow end-to-end including a genuine before/after header-CSS-class diff
  (never a hardcoded class name — a Ready Template's `header` kwarg is a component key that can
  alias to a different rendered variant, discovered the hard way while iterating this scenario) and
  Draft/Public separation. A debug-only `R4_QA_ONLY_SCENARIO` env-var scenario selector was added to
  the harness to let a single scenario be iterated on directly instead of re-running the full ~15-
  scenario campaign on every assertion fix — confirmed unreferenced by the Python management command
  and a no-op when unset. Fixed while iterating to green: the merchant-content marker (hero_banner's
  structural variant needs real media data this fixture lacks; switched to a `product_section`
  title), ambiguous section discovery (multiple earlier scenarios already add their own
  `product_section`s to the same long-lived fixture page; scoped by this scenario's own sentinel
  text), an open Global Design panel intercepting Preview-targeted clicks, a "stale" `base_revision`
  that went negative for a fresh Draft starting at revision 0, and `#r4UndoButton`'s disabled
  attribute only being server-rendered at page-load time (never toggled client-side). Verified:
  scenario 15 green in isolation, full 17-scenario harness green in one complete run, sanity checks
  clean. Committed and pushed as `34278a6`.

- **Independent Task-8 review and closure fix** (continuation session, 2026-09-10). One fresh,
  isolated-worktree independent reviewer audited the full diff since the Task-7 baseline (`51df4a7`).
  Verdict: CRITICAL 1, IMPORTANT 0, MINOR 4. The CRITICAL finding: `switch_template_preserving_
  content` deliberately leaves `template_baseline_snapshot` describing the OLD Template after
  updating `template_provenance` to the new one (documented as intentional — rebuilding it would
  fabricate a historical baseline never actually applied) — but `reset_storefront_to_baseline` read
  that specific mismatch as indistinguishable from "no accurate snapshot at all" and silently fell
  into its legacy-compatibility fallback, fetching the new Template fresh from the live registry and
  wiping every covered page's composition, reachable via an ordinary two-click merchant workflow
  (switch template, then click the pre-existing Reset Storefront button). Fixed narrowly: a present-
  but-mismatched snapshot now raises `TemplateBaselineVersionChangedError` outright instead of
  falling through to the destructive fallback; confirmed this exact mismatch state is reachable only
  through the new switch function (every other `template_provenance` writer keeps both fields in
  lockstep), so a Draft with no snapshot at all (the genuine legacy case) is unaffected. The five
  granular reset paths were independently confirmed NOT to share this bug (they never reach the live
  registry). New regression test proves both the direct service-level rejection and the end-to-end
  R4 endpoint rejection, with the Draft's composition provably unchanged after the rejected attempt.
  Re-verified: 276 tests across every `preset_service`-touching module, only the one pre-existing
  failure; sanity checks clean. The four MINOR findings (a small, justified duplication to avoid a
  circular import; a missing no-op guard for a same-Template re-switch; a pre-existing header/footer
  merge skipping validation, first exposed to production traffic here rather than introduced by it;
  one missing trailing `return;` in JS) were accepted as disclosed, low-risk tradeoffs per the
  reviewer's own framing. Committed and pushed as `18bedd1`. **CRITICAL 0 / IMPORTANT 0 after this
  fix — Task 8 is now CLOSED.**

## Task 9 — Evidence-based legacy retirement

- **START** 2026-09-10. Startup guard verified: local HEAD == `origin/feature/phase4-builder-
  legacy-convergence` == `backup/rastisi6-phase4-task8-final-20260910` ==
  `34c1fba9fd1f3919a383c365cbb3e6893a310f3c`; `origin/main` unchanged
  (`973c1dc00bacb6f2f7d2604fa3880bb4d6250579`); working tree clean; exactly one writer session (no
  stale Task 7/8 waiters in the process table). Pre-deletion safety backup
  `backup/rastisi6-phase4-pre-legacy-retirement-20260910` created and pushed, pointing at
  `34c1fba9`, before the first deletion commit.
- Re-verified every `legacy_disposition.md` row against current code (three parallel `Explore`
  recon passes covering: settings/structure/toggle/history/reset; media CRUD/editor shell/industry
  presets/announcement_bar; Ready Template application and a full field-by-field Appearance/Header/
  Footer parity matrix). **Headline finding, re-confirmed by direct code inspection**:
  `StorefrontLayout.r4_editor_enabled` still defaults `False` and dashboard nav
  (`base_admin.html`) still routes every merchant to the legacy editor shell, never R4 — R4 remains
  reachable only via an opt-in link embedded inside the legacy editor itself. R4's
  Appearance/Header/Footer mutation surface also covers only a narrow field subset (template/
  palette/font/type_scale/motion/button_style, header_variant, footer_variant) — most legacy
  header/footer toggle fields and appearance color/structural fields have no R4 write path at all.
  Container/Cell arbitrary placement remains a documented gap even after Task 7. Ready Template
  gallery/apply was deliberately kept as a separate orchestration from R4 per Task 8's own evidence.
  Consequence: the legacy editor shell and every view still live-linked from it are **NOT SAFE TO
  REMOVE YET** — this matches the disposition ledger's own pre-existing "KEEP AS FINAL UNTIL R4 IS
  REACHABLE" ruling; deleting them now would remove real, currently-exercised merchant capability,
  not dead code. Making R4 the live default (new-capability/default-routing work) is out of Task
  9's deletion/convergence scope.
- **Batch 1** (route/view/UI retirement) — the one candidate that actually cleared the evidence
  bar: `storefront_discard` (`storefront-builder/discard/`) had zero live UI callers anywhere in
  the legacy editor templates and a fully proven, stricter R4 replacement
  (`storefront-builder/r4/discard/`, atomic + stale-revision gated, vs. the legacy view's bare
  `layout_service.discard_draft` call). Removed the view, its URL, and its two now-redundant direct
  tests (coverage retained via R4's own `DraftReplacingEndpointTests`). Targeted: 462 tests
  (`test_views`, `test_phase2_lifecycle_safety`, `test_r4_vertical_slice`) — only the 3
  already-known pre-existing failures (confirmed identical on unmodified `34c1fba9` via `git
  stash`). Committed and pushed as `5ed6486`.
- **Batch 2** (residual cleanup) — a real latent bug, not a section deletion: `announcement_bar` is
  `hidden_from_library` and the merchant-facing add path (`section_structure_service.add_section`/
  `duplicate_section`) already refuses to create new instances, but `preset_service.
  _build_sections_for_page` built preset/Ready-Template sections with no such check — a second,
  un-gated write authority. Four real A8 recipes (`premium_leather`/`street_drop`/`racer_tech`/
  `anniversary_mosaic`) carry a `"ticker"` token mapping to `announcement_bar`; applying any of them
  created a live instance double-rendering alongside the header's own notification bar (the exact
  defect `golden_reference_service.py` documents avoiding on the Golden Home composition). Fixed by
  filtering `hidden_from_library` entries once, where each page's preset entries are first bound —
  before either section-building or the parallel Container/row-grouping logic (both keyed off the
  same list) consume them, keeping `template_slot_key`/container-settings numbering consistent for
  the common case. New regression test applies all four recipes and asserts no `announcement_bar`
  section is built. `announcement_bar` itself is not deleted — existing instances still render.
  Targeted: 40 `test_preset_service` tests plus a 355-test sweep across A8/section-registry/Ready-
  Template modules — only the 1 already-known pre-existing failure (confirmed identical on
  unmodified `34c1fba9`). Committed and pushed as `61eff5b`.
- Consolidated Task-9 targeted regression (both batches, all 10 touched/related modules, 857
  tests): `failures=2, errors=2` — the exact same 4 pre-existing failures found in the narrower
  runs, zero new regressions. `python manage.py check`: clean. `python manage.py makemigrations
  --check --dry-run`: no changes detected. `git diff --check` (`34c1fba9..HEAD`): clean.
- **Independent review**, fresh reviewer, isolated `git worktree` (`/tmp/rastisi6-task9-review`,
  detached at `61eff5b`), no prior session context. Verified the discard removal's zero-caller claim
  via a full-worktree search (not scoped to one directory), read `preset_service.py` in full and
  confirmed the filter's ordering is correct with no other un-gated caller of `hidden_from_library`
  sections, independently re-ran all 10 targeted modules (857 tests, same 4 pre-existing failures by
  name), and independently re-derived the R4-reachability/field-parity restraint claims from current
  code. Verdict: **CRITICAL 0, IMPORTANT 1, MINOR 2.** IMPORTANT: commit `5ed6486`'s message claimed
  `legacy_disposition.md` was updated when it wasn't touched until this closure pass — fixed by
  actually updating every row now (see `legacy_disposition.md` and `task9_legacy_retirement.md`).
  MINOR (fixed): `golden_reference_service._rebuild_home_composition` forks the same row-build
  pattern `preset_service._build_sections_for_page` just gained a guard for, but lacked it itself —
  safe today only because its static Golden composition tuple hand-omits `announcement_bar`; added
  the same defensive assertion (54 golden-reference/media tests re-verified clean). MINOR (accepted,
  out of scope): no migration to clean up any *already-existing* `announcement_bar` instance created
  before this fix — consistent with the Product Owner ruling that no historical-data migration
  machinery is required. **CRITICAL 0 / IMPORTANT 0 after the fix — Task 9 is CLOSED.**
- Closure: `legacy_disposition.md` updated (every row re-verified, no `UNKNOWN` entries);
  `task9_legacy_retirement.md` created (full evidence, classification table, reviewer verdict);
  this ledger entry. `backup/rastisi6-phase4-task9-final-20260910` created pointing at the final
  Task-9 SHA. Task 10 (final Phase-4 certification, including the full `apps.storefront_builder`
  regression deferred from Task 8) explicitly **NOT STARTED** in this session.

## Pre-Task-10 Remediation — R4 live cutover + real remaining-gap closure

- **START** 2026-09-10. Preconditions verified: local HEAD == origin feature branch ==
  `origin/backup/rastisi6-phase4-task9-final-20260910` == `75ede8ab82c6e53090b04eadc7ea9cf9f8691480`;
  `origin/main` == `973c1dc00bacb6f2f7d2604fa3880bb4d6250579` (unchanged); working tree clean.
  `backup/rastisi6-phase4-pre-final-remediation-20260910` created pointing at the same SHA, pushed
  and verified before the first production change. Task 9 not redone; its evidence re-used as the
  factual starting point for this remediation's own short audit (Step 1A-E).
- Field-by-field Appearance/Header/Footer parity matrix built from current code (not from Task 9's
  prose alone — re-verified against `views.py`/`layout_service.py`/`models.py` directly). Wired the
  REQUIRED EXISTING CAPABILITY majority (~40 fields: all 8 color overrides, all 8 theme overrides,
  every structural appearance field, all 6 header toggles + announcement text/phone, all 9 footer
  toggles) into `r4_mutation_service.py`'s `appearance.update`/`header.update`/`footer.update`,
  reusing the exact same canonical validators (`layout_service.validate_appearance_config`/
  `validate_header_config`/`validate_footer_config`) the legacy forms already use — never a second
  validation authority. Found and fixed a genuine pre-existing bug in the canonical authority layer
  along the way: `appearance_authority_service._merge_appearance_config`'s managed-key set never
  included the 5 Phase-8 P0-7 structural fields, so a Store-global edit of any of them was silently
  discarded by both the legacy editor and any R4 caller — reproduced directly against the unmodified
  function before fixing. 3 repeater-shaped fields (announcement_links, header/footer extra_blocks)
  and the per-field responsive hide-on-tablet/mobile toggles deliberately deferred (compound
  multi-row/per-device UI, not a flat scalar patch key) — real, explicitly-tracked remaining gap, not
  scope creep. New Global Design panel UI for every wired field; `r4_editor.js`'s single-field
  change handler extended to handle checkboxes and the color/theme override's nested-dict patch
  shape. New tests: `FieldParityUpdateTests` (11 tests); 2 pre-existing tests updated to use a
  still-genuinely-unknown patch key (`extra_blocks`) instead of a now-legitimate one, same precedent
  as Task 7's own representative-test swaps.
- Composition parity: closed Task 7's B1 audit items #1/#2/#5 (Container-level settings, arbitrary
  non-adjacent placement) with two new mutation types — `section.move_to_cell`
  (`section_structure_service.move_section_to_cell`, reusing `container_service.move_block`) and
  `container.update_settings` (reusing `container_service.effective_container_settings`, matching
  the legacy view's own restraint of never exposing `content_width`). New Structure panel UI: a
  "move to empty cell" picker per section row, inline Container settings controls per Container row
  — a simple explicit target-cell operation, not a drag/drop framework. New tests:
  `SectionMoveToCellTests` (7), `ContainerUpdateSettingsTests` (4) — same negative-path coverage
  shape as every sibling Task-7 mutation type.
- Family certification (Step 1D): re-read `family_certification_matrix.md` fresh. The 15 remaining
  `NOT YET CERTIFIED` `MIGRATE` rows all have `SettingsSchema`/CSS already closed by Task 5/6 — the
  only outstanding item is a dedicated Task-4 QA-harness Playwright scenario per family, which this
  session did not write (real UI-automation effort comparable in size to Task 6's own dedicated
  browser-certification work; not something to rush inside a 3-batch-capped remediation). Left
  `NOT YET CERTIFIED` with the disposition formally re-affirmed against current code rather than
  silently carried over stale — a justified, not unjustified, remaining gap.
- Ready Template orchestration (Step 1E): re-confirmed unchanged from Task 8's own ruling — no new
  merchant-facing duplicate authority found or introduced. No code change needed.
- R4 live cutover (Step 2): `StorefrontLayout.r4_editor_enabled` default flipped `False` -> `True`
  (migration `0020_r4_editor_enabled_default_true`, `AlterField` + a `RunPython` data migration
  flipping every existing Store's layout — no important production data to preserve, per the
  remediation's own instruction; migration history preserved, no squash/reset/rewrite). Dashboard
  nav (`base_admin.html`) — every primary storefront-appearance nav entry and global-search shortcut
  now routes to `storefront-builder-r4-editor` instead of the legacy route; a new, clearly
  secondary-labeled "ادیتور قدیمی (تنظیمات پیشرفته)" entry keeps the legacy editor reachable as the
  compatibility escape hatch for the Step 1B field gap — one primary editor, not two co-equal ones.
  `r4_editor.js` extended so the nav's existing `?panel=appearance/header/footer` deep links still
  auto-open R4's Global Design panel. New tests: `R4FoundationModelTests.test_r4_editor_is_enabled_
  by_default`, `R4EditorRouteGateTests.test_r4_route_is_reachable_by_default_without_opting_in`,
  `DashboardNavRoutesToR4Tests`; 2 pre-existing tests in `test_views.py` updated (behavior genuinely
  changed, not patched to keep a stale contract green).
- Second legacy-retirement pass (Step 3): **not attempted.** The legacy editor remains genuinely
  needed as the reachable path for the Step 1B field gap and the still-open Task-9
  `NOT SAFE TO REMOVE YET` rows this remediation did not close (settings writer for ~23 non-schema
  section types, granular reset family, discard/restore/history UI) — retiring any of them now would
  remove real merchant capability, the same principle Task 9 itself established. Deferred, not
  skipped, to a future task once the remaining Step 1B/1D gaps close.
- Targeted regression: 330+ tests across `test_r4_vertical_slice`/`test_r4_inspector`/
  `test_r4_store_appearance_mutations`/`test_phase2b_multiblock_cell_runtime`/
  `test_phase31_container_cell_builder`/`test_r4_appearance_overrides`/`test_r4_mutation_api`/
  `test_phase4_task3c_page_appearance`/`test_phase1_appearance_authority`/`test_preset_service`/
  `test_r4_foundation`/`test_views` — zero new regressions beyond the one pre-existing
  frozen-baseline failure already documented in `task9_legacy_retirement.md` (re-confirmed
  reproducing identically on the unmodified `75ede8a` checkpoint via `git stash`). `manage.py check`,
  `makemigrations --check --dry-run`, `git diff --check` all clean.
- `legacy_disposition.md` and `family_certification_matrix.md` updated in place (not just this
  ledger) — every row this remediation actually touched re-verified and given its real current
  disposition; `pre_task10_r4_cutover.md` created with the full evidence record.
- Task 10 (full Phase-4 certification, including the 15 families' browser-harness certification and
  the second legacy-retirement pass deferred above) explicitly **NOT STARTED** in this session.
