# Phase 3 Execution Ledger (Kiro-native adapted protocol)

This ledger is the persistent, compaction-surviving execution record for the
Phase-3 storefront appearance convergence implementation. It is authorized by
the Architect as additional Phase-3 execution evidence and is committed with
the task commits. Do not rely on chat memory.

## Identity

- Plan: `docs/superpowers/plans/2026-09-06-storefront-vertical-slice-phase3-implementation-plan.md`
- Spec: `docs/superpowers/specs/2026-09-06-storefront-vertical-slice-phase3-design.md`
- Binding refs: 5-phase convergence design (2026-09-05), lifecycle-safety phase2 design (2026-09-06), phase2 final_gate.md
- Official Phase-2 merged baseline: `e244619f395ebf0dbebc77d2033841e17f1cd099`
- Phase-3 preparation HEAD (implementation start): `c34a04e71cc62d191d6fe8238ef4e6735fb6642f`
- Kiro workspace: `/projects/sandbox/rastisi5`
- Branch: `feature/storefront-vertical-slice-phase3`
- Initial Kiro HEAD: `c34a04e71cc62d191d6fe8238ef4e6735fb6642f`

## Adapted-protocol Architect ruling (verbatim substance)

RULING:
The official Superpowers runtime is unavailable in Kiro, but Kiro provides
isolated general-task-execution and semantic_reviewer subagents.
The Architect authorized Kiro-native implementer/reviewer isolation plus a
tracked persistent ledger and controller-owned authoritative verification.
This preserves the intent of independent implementation/review without
requiring unavailable framework scripts.

RISK IF WRONG:
Reviewer/implementer isolation may be weaker than the original Superpowers
runtime; this is mitigated by fresh subagent contexts, controller-run tests,
task-scoped diffs, persistent evidence, per-task independent reviews, and a
fresh final whole-branch reviewer.

## Preflight results

- Remote `origin/feature/storefront-vertical-slice-phase3` = `c34a04e71cc62d191d6fe8238ef4e6735fb6642f` âœ… (matches required)
- Remote `origin/docs/storefront-appearance-convergence` = `e244619f395ebf0dbebc77d2033841e17f1cd099` âœ… (matches required)
- Ancestry: phase2 head IS ancestor of phase3 head âœ…
- Worktree clean at `c34a04e7â€¦` âœ…
- Python: 3.12.13 (external venv `/projects/rastisi5_phase3_venv`)
- Django: 5.2.17
- Node: v22.23.2 ; npm 11.4.2
- Browser: Google Chrome for Testing 151.0.7922.10 at `/usr/local/bin/chrome`; playwright-core installed in `tools/storefront_builder_qa/node_modules` (gitignored); headless launch via executablePath verified OK.
- Database backend: `django.db.backends.sqlite3`, NAME `/projects/sandbox/rastisi5/db.sqlite3` (currently absent = empty baseline), DEBUG=True, no DATABASE_URL. Local/disposable âœ….

### Environment adaptation rulings

- RULING (env): Use external venv `/projects/rastisi5_phase3_venv` (Python 3.12.13) instead of laptop's 3.12.10; Django 5.2.17 instead of 5.2.16. REASON: patch-version differences within `requirements.txt` ranges; project constraints satisfied. RISK IF WRONG: negligible; both satisfy `Django>=5.2,<6`.
- RULING (env): The R4 runner's browser candidate list must include `/usr/local/bin/chrome` (Chrome for Testing) as a discovery path; `chrome`/`msedge` playwright channels are absent in this Linux sandbox. This is a bounded Task-1 harness adaptation preserving the same launch/backup/restore safety semantics (POSIX translation of the Windows plan). RISK IF WRONG: browser gate could use wrong binary; mitigated by asserting version and launch success.

## Baseline (fresh Kiro) â€” RESULT

- system check: Exit 0; "System check identified no issues (0 silenced)." âœ…
- makemigrations --check --dry-run: Exit 0; "No changes detected" âœ…
- Run A: Ran 633 tests; FAILED (failures=1, skipped=1). PASS 631, FAIL 1 (known #1 `test_validate_appearance_config_is_the_validator_boundary`: validate called 2 times), SKIP 1 (`QuickLinksRenderTests.test_menu_from_another_store_never_leaks`). âœ… matches preparation.
- Run B: Ran 119 tests; FAILED (failures=2, errors=1). Known #2 fullscreen button `:aria-pressed="fullscreen"` absent; #3 fullscreen StopIteration (error); #4 Persian gallery label. âœ… matches preparation.
- Run C: Ran 59 tests; OK. PASS 59. âœ… matches preparation.
- Combined: 811 executions, 806 pass, 3 fail, 1 error, 1 skip. âœ… EXACT match to preparation baseline.
- Unexpected new failures: NONE.

Baseline gate: PASS. Cleared to begin Task 1.

---

## TASK LOG


### Task 1: START
- BASE SHA: c34a04e71cc62d191d6fe8238ef4e6735fb6642f
- worktree: clean (verified)
- brief: Brand RED characterization + existing QA harness setup. Test-only. Allowed files (tests/harness only): B/tests/test_r4_settings_schema.py, B/tests/test_render_service.py, B/tests/test_g22_preview_media_render_consistency.py, B/tests/test_qa_harness_contract.py, B/management/commands/qa_storefront_builder_r4.py, tools/storefront_builder_r4_qa/run.mjs. NO production files.
- Expected end: characterization GREEN, only V01 desired RED remains (test-only RED may be committed in this task).


### Task 1: COMPLETE
- implementer: fresh general-task-execution subagent (test/harness-only)
- RED: V01 `test_variant_intent_survives_title_patch` fails at assertTrue line 523 `AssertionError: None is not true` (marker dropped after title-only patch). Intended, correct reason. This is the single planned RED crossing the task boundary; MUST close in Task 2.
- GREEN: characterization tests (brand order/foreign+inactive omission across 3 modes, sibling isolation, invalid-mode fallback, real 2nd-store tenant fixture) + wrapper/media consistency all GREEN (not forced).
- tests (controller-run): focused suite Ran 148; FAILED(failures=1 [V01], skipped=1 [pre-existing QuickLinks]). node --check run.mjs OK. git diff --check clean.
- browser: harness prepared (--phase3 arg + 3 viewports + /usr/local/bin/chrome fallback). No cert claimed in Task1.
- review: independent semantic_reviewer â†’ APPROVED. SPEC COMPLIANCE PASS, CODE/TEST QUALITY PASS. 0 CRITICAL, 0 IMPORTANT, 0 MINOR.
- fix rounds: 0
- commit: 597872c2edd2bd19c3d59b16812300aa64dd7a15  "test: characterize phase3 brand contracts and browser prerequisites"
- minor deferrals: none
- rulings: none new (env rulings already recorded above)


### Task 2: START
- BASE SHA: 597872c2edd2bd19c3d59b16812300aa64dd7a15
- worktree: clean
- brief: Brand canonical preservation (V01 close) + View-all capability truth (V02). Production task. Preserve trusted variant_explicit marker across brand_carousel non-variant edits; never from client payload. Declare Brand variant-specific supported settings; grid/carousel support show_view_all only when trusted current destination validates + resolves non-none; beauty_tabs never. Filter inspector; reject unsupported enable atomically (no settings/revision/history change); preserve dormant show_view_all/destination across switches.


### Task 2: COMPLETE
- implementer: fresh general-task-execution subagent (production, TDD REDâ†’GREEN)
- REDâ†’GREEN: V01 Task-1 test FAILâ†’ok (marker survives title patch). V02 (b)(c)(d) RED-first then GREEN; (a)(e)(f) verified. Every rejected mutation asserts settings+edit_revision+history unchanged.
- tests (controller-run): Phase3BrandPreservationTests Ran 6 OK; test_r4_mutation_api+test_render_service Ran 118 OK(skip=1); test_r4_settings_schema+test_r4_inspector+test_phase1_appearance_authority+test_shared_capabilities Ran 157 OK; test_views Ran 215 FAILED(1 fail+1 error = only known baseline #2/#3). No new failures.
- V01: CLOSED. V02: enforced (capability = supporting variant AND trusted resolved destination; atomic rejection; dormant preservation; read-only inspector filtering).
- browser: deferred to Task 3/7 per plan.
- review: independent semantic_reviewer â†’ SPEC COMPLIANCE PASS, CODE/TEST QUALITY PASS. 0 CRITICAL, 0 IMPORTANT. 2 MINOR (cosmetic).
  - MINOR-1 (DEFERRED): `_BRAND_VIEW_ALL_SUPPORTING_VARIANTS` constant duplicated in r4_mutation_service.py and r4_views.py (documented mirrors). REASON: both explicitly commented as mirrors, correct today; hoisting is a non-scoped refactor. RISK IF WRONG: future drift between mutation and inspector allowlists â€” low; covered by V02 inspector+mutation tests that would catch divergence. FUTURE TARGET: optional Task 6 shared-hardening if both pilots motivate it.
  - MINOR-2 (DEFERRED): `_brand_section` test helper duplicated across two test classes. REASON: cosmetic. RISK: none.
- Reviewer sandbox note: reviewer reported a bs4-missing limitation in ITS sandbox; controller-authoritative run (bs4 installed per requirements.txt) confirms test_views has only the 2 known fullscreen failures â€” reviewer limitation does not apply to the authoritative env.
- fix rounds: 0
- commit: 43cdd20c554cfb0ef0753164b4f7cb369bef99f5  "fix: preserve brand variant intent and supported controls" (amended)


### Task 3: START
- BASE SHA: 59dbbdd3fec5e9a99b6689d5d6868df3d4046bd7 (Task2 final = 43cdd20; ledger-sha-record = 59dbbdd)
- worktree: clean
- brief: Brand end-to-end renderer/asset/media proof = BRAND GATE. Six-page registry/dispatch/presence/asset/shell assertions for brand_carousel; V02 six cases in renderer+browser; real Cart HTMX fragment (V05/A04 pilot) via _render_cart_container presentation adapter (build_universal_storefront_context); wrapper projection proof; Draft/Published isolation + stable_id; scoped CSS fix if RED; browser matrix E1-E5 @ 1440/390/768.
- Allowed prod: render_service.py (_brand_carousel_context + item projection only), templates sections/brand_carousel.html, partials/responsive_section_wrapper.html (Brand only), static/css/storefront_builder.css (Brand-scoped only), preview.html; catalog templates home_visual/product_list/product_detail/collection_detail + cart_detail (load existing Builder styles if missing only); apps/cart/views.py _render_cart_container (presentation assembly only). QA command/runner from Task1.


- RULING (env, Task 3): Test-DB migration is very slow in this sandbox (individual SQLite migrations 12-36s; full migrate ~10min). Adopt `--keepdb` for controller test runs to reuse the migrated test DB. REASON: Section 24 says do not stop for long test runtime; --keepdb is a standard Django facility that does not alter test semantics (same migrations, same schema, tests still create/rollback their own rows in transactions). RISK IF WRONG: a stale test DB could mask a migration change â€” mitigated because Task 8 runs the fresh baseline (RunA/B/C) and `makemigrations --check` WITHOUT keepdb assumptions, and no migration is created in Phase 3. The keepdb DB is disposable and separate from the app db.sqlite3.
- RULING (Task 3 doc-nuance): The inventory/plan stated collection_index (E6) does NOT call build_universal_storefront_context. In THIS codebase it DOES (apps/catalog/views.py:590, PageType.COLLECTION). However the REAL A06 boundary still holds and was asserted: collection_index.html does not include render_rows.html and does not load storefront_builder.css, so NO pilot renders on /collections/ and E6 remains a non-pilot companion. Implementer correctly asserted the true boundary and did NOT assert the false premise. REASON: the certification-relevant fact (no pilot placement/assets on E6) is preserved; only the mechanism description in the inventory was imprecise. RISK IF WRONG: none for certification â€” E6 still hosts no pilot; the six pilot envelopes are unaffected.


## Task 3 â€” Brand gate browser certification (phase3 harness extension)

Authored REAL Brand browser-certification scenarios into the EXISTING R4 QA
harness (no second harness/runner). Files changed (harness only):

- `tools/storefront_builder_r4_qa/run.mjs` â€” replaced the placeholder
  `phase3ResponsiveCapture` with `phase3BrandGate()`, gated behind
  `if (manifest.phase3)`. Sub-groups:
  - `phase3PublicMatrix` â€” E1 home / E2 product_detail / E3 listing /
    E4 collection / E5 cart, أ— 3 viewports (1440أ—900, 390أ—844, 768أ—1024),
    أ— 3 variants (grid/carousel/beauty_tabs): brand-tile count/order,
    logo `<img>` decode (`complete && naturalWidth>0`) or `.brand-tile-name`
    fallback, asset envelope A06 (storefront_builder.css/htmx/alpine each
    exactly once, no duplicate asset URLs, no home.css off-home, bounded
    `.brand-tile img` height, `documentElement.scrollWidth <= vp.width+1`),
    and V02 view-all anchor truth (grid/carousel resolve to the collection
    destination; beauty_tabs has none).
  - `phase3WrapperProjection` â€” Preview iframe: discover brand
    `data-section-id`, `fetch()` Preview HTML, DOMParser-extract the matching
    wrapper, replace live wrapper 3أ—; assert brand hrefs identical and
    stylesheet/script count unchanged (no script execution from markup).
  - `phase3CartHtmx` â€” add product, read real `hx-post` URLs + item id from
    the DOM, POST quantity update + item removal, assert Brand section
    survives the swap, `#cart-count` OOB badge updates, totals/qty correct.
  - Metrics recorded to `result.phase3_brand` and `metrics.json`.
- `apps/storefront_builder/management/commands/qa_storefront_builder_r4.py` â€”
  `_prepare_r4_sandbox(..., phase3=False)`; new `_prepare_phase3_brand_gate`
  (guarded, phase3-only) places one brand_carousel per variant on all five
  envelope pages with the same ordered five brands (four PIL logos + one
  deliberate no-logo), a `p3-collection-1` MerchantCollection host + members,
  cart product stock, and a collection View-all destination. Fixture ids are
  threaded into the manifest via `_build_manifest(phase3_fixture=...)`.

Result (`--phase3` run): **Passed: 16  Failed: 0**; DB restore
`match=true` (pre==post SHA-256). Default (non-phase3) run behavior and
scenarios 01â€“13 unchanged (all additions are phase3-gated).


### Task 3: COMPLETE (BRAND GATE PASS)
- implementer: fresh general-task-execution (code/test) + fresh general-task-execution (browser harness authoring) + bounded fix subagent (CSS review fix)
- Production changed: apps/cart/views.py (_render_cart_container V05/A04 adapter), storefront_builder.css (Brand-scoped rules mirroring Home's EFFECTIVE cascade). Harness: run.mjs (phase3BrandGate) + qa command (_prepare_phase3_brand_gate). Tests: test_cart_views, test_g23, test_render_service, test_section_registry, test_page_shell, test_phase2_universal_renderer, test_stable_section_identity, test_g22.
- REDâ†’GREEN: cart context keys absentâ†’present (real HTMX fragment); CSS brand selectors absentâ†’present (dense/effective values).
- tests (controller-run --keepdb): cart suite 68 OK; six-page/shell 52 OK; main 139 OK (+1 pre-existing skip); test_g23 20 OK. No new failures.
- browser (controller-run, authoritative, TWICE incl. post-fix): 16/16 PASS incl phase3-brand-gate. 45 variant checks (E1-E5 أ— 3 viewports أ— 3 variants), 15 asset envelopes, 45 V02 anchor records, 3 cart HTMX flows, 1 wrapper projection. A06: non-home home_css=0/sb_css=1; brand-tile img 48px on Home AND non-home (Home UNCHANGED). No doc overflow. 0 console/page/request errors. DB restore SHA match=true.
- review: independent semantic_reviewer round 1 â†’ FAIL (1 CRITICAL: shared CSS overrode Home's dense block changing Home 48pxâ†’40px; 1 IMPORTANT: test ratified 40px; 1 MINOR: doc claim). Fix round 1: shared CSS rewritten to Home's effective dense values (48px etc.) â†’ override on Home is a no-op; test asserts 48px + Home-unchanged guard. Scoped re-review â†’ APPROVED, 0 CRITICAL, 0 IMPORTANT.
  - MINOR (resolved): doc claim corrected in task3_brand_gate.md.
- fix rounds: 1 (CRITICAL+IMPORTANT resolved within cap)
- A04 pilot (Brand portion) V05: cart fragment container projection + preview wrapper projection PROVEN. A06 pilot (Brand): all six envelopes proven (E1-E5 + E3 listing/search equiv; E6 companion). Global A04/A06 remain deferred.
- commit: (recorded on next task)
- RULING (Task 3, R3 evidence PNGs): the harness overwrites pre-existing R3 phase1 screenshots (docs/qa_evidence/storefront_builder/r4/phase1/*.png) on each run; these belong to a prior phase's evidence. Controller restored them (git checkout) so Phase 3 does not touch them. Transient runtime logs (runserver/browser/RECOVERY) excluded from committed evidence.


[Task 3 commit SHA: 4b0e092c7dc779d55e9cd41179469e449d0566c7 "fix: prove brand rendering across preview public and wrapper replacement"]

### Task 4: START
- BASE SHA: 4b0e092c7dc779d55e9cd41179469e449d0566c7
- worktree: clean; Brand gate PASS (precondition met)
- brief: Collection characterization + canonical adapter convergence (V03). Extend ResourceSource router to collection_tiles (collection_resource_source_from_settings/to_legacy_patch adapters mapping kind=collection manualâ†’collection_ids, auto all_activeâ†’[]). Add tile SettingsSchema (title/source/tile_style). Collection ownership check (MerchantCollection.objects.filter(store=store,pk__in=manual_ids)) rejecting foreign/missing before save (no settings/revision/history change). Collection picker search/selected by .name. Preserve total-membership-count meaning (Count items) vs visible-products; manual order + auto newest-first. Pilot variant-marker bridge. NO domain business behavior change, no new persisted source field, no migration.


### Task 4: COMPLETE
- implementer: fresh general-task-execution (production, TDD REDâ†’GREEN)
- Production: resource_source.py (collection adapters + _SECTION_ADAPTERS), section_registry.py (COLLECTION_TILES_SCHEMA + settings_schema + _RESOURCE_SOURCE_AWARE + error class), r4_mutation_service.py (collection ownership branch), r4_views.py (collection picker searcher/serializer/resolve/auto_rules). render_service/settings_schema/views/resource_picker.html/r4_editor.js unchanged (already generic).
- REDâ†’GREEN: adapter unsupportedâ†’roundtrip; R4 mutation section_not_schema_enabledâ†’200; inspector 404â†’resolves; ownership reject (foreign/missing â†’ 400, settings/revision/history unchanged).
- Semantics: total-membership Count("items") preserved (item_count=2 vs visible=1); manual + auto newest-first ordering preserved; collection dispatched explicitly (no name_en fallthrough); Brand not broken.
- tests (controller-run --keepdb): 358 OK (1 pre-existing skip). makemigrations --check clean. diff --check clean.
- review: independent semantic_reviewer â†’ SPEC COMPLIANCE PASS, CODE/TEST QUALITY PASS. 0 CRITICAL, 0 IMPORTANT. 2 MINOR (cosmetic).
  - MINOR-1 (DEFERRED): dangling category comment after the collection branch in r4_mutation_service.py. REASON: cosmetic; correct behavior. RISK: none.
  - MINOR-2 (DEFERRED): CollectionTilesNegativeMutationTests helper duplication in test_r4_mutation_api.py (actual ownership tests live in test_r4_resource_picker.py). REASON: organizational; no coverage gap. RISK: none.
- fix rounds: 0
- atomic schema+ownership: CONFIRMED (reviewer traced mutation path â€” no schema exposure without ownership check).
- commit: (recorded on next task)


[Task 4 commit SHA: d3e5c9967b55ea5db94cc25e65b68e5ab2151d25 "feat: converge collection tiles on typed source and r4 settings"]

### Task 5: START
- BASE SHA: d3e5c9967b55ea5db94cc25e65b68e5ab2151d25
- worktree: clean; Task 4 GREEN, Brand gate unchanged (preconditions met)
- brief: Collection end-to-end + page integration = COLLECTION GATE. Six-page registry/dispatch/presence/asset/shell for collection_tiles (like Task 3 Brand); both tile variants (grid/carousel) select/order; Draft/Published + stable_id; context-aware header/products get same collection/products/page_obj as domain view; /collections/<slug>/?page=2 domain membership + shared cards, no HX; E6 collection_index direct listing (no pilot render-items); real Cart HTMX for Collection tiles (presentation adapter from Task 3); scoped CSS if RED; browser matrix E1-E5 @ 3 viewports both tile variants. PRESERVE domain ownership, count meaning, pagination.
- Allowed prod: render_service.py (Collection builders only), templates sections/collection_tiles.html/collection_header.html/collection_products.html, partials/responsive_section_wrapper.html (Collection ctx only), static/css/storefront_builder.css (Collection-scoped only), catalog collection_detail.html/collection_index.html (pilot assets only), preview.html; + Task5 additional: test_section_registry/test_page_shell/test_g23 + catalog home_visual/product_list/product_detail + cart_detail (load Builder styles if new omission demonstrated). Reuse Task3 canonical stylesheet mechanism. QA command/runner. Forbidden: domain business rules, ProductCardData/card redesign, new pagination/fragment route, non-Home R4 UI.

### Task 6: START (Codex continuation)
- Starting HEAD: `064b81a78bd51e2f7ac826b5fe9d72e042ca18ce`; tree `ae96f051e5d366fc818903e018367985777a512e`; branch `feature/storefront-vertical-slice-phase3`; clean worktree verified.
- Task 5 is CLOSED/approved per current execution authorization and `task5_collection_gate.md`; no reopening of Tasks 1â€“5.
- Scope: two-family characterization plus combined published Cart update/remove proof. Proof-only by default; no manufactured RED or refactor. No Task 7.
- Workflow: fresh test implementer, controller verification, then independent spec/test-quality review; commit only after review.
- Workspace preference: retain explicitly required existing checkout and branch. Current user instruction permits only `backup/phase3-codex-task6-final-20260907` push after completion, overriding the historical general no-push rule for that ref alone.
- Preliminary controller checks: Django system check clean; migration dry run reports no changes (Python 3.12.10 / Django 5.2.16).
- Browser: reuse final Task-3/5 evidence if proof-only. No shared production rendering change; final family browser evidence remains applicable.

### Task 6: COMPLETE
- BASE SHA: 064b81a78bd51e2f7ac826b5fe9d72e042ca18ce
- executor: Codex continuation; bounded production recovery completed under Architect review after Codex token exhaustion.
- RED: Collection lost trusted appearance_overrides.variant_explicit after variant -> title -> source; Brand preserved it.
- root cause: collection_tiles absent from APPEARANCE_OVERRIDE_AWARE_SECTION_KEYS.
- production correction: section_registry.py only; collection_tiles added to existing trusted-marker preservation allowlist.
- focused GREEN: exact former RED 1/1 OK; Phase3SharedPilotPreservationTests 3/3 OK.
- controller regression Group 1: 301 OK, 1 pre-existing skip, 0 failures/errors.
- controller regression Group 2: 77/77 OK.
- Django check: PASS. Migration check: PASS, no changes detected. git diff --check: PASS.
- browser: Task-3/Task-5 evidence reused; no renderer/CSS/wrapper/Cart presentation change. Full browser certification remains Task 7.
- independent Architect review of snapshot 9f94fa8c5544720356e40e356d1ace6dcdd6775d: SPEC PASS; QUALITY PASS; 0 CRITICAL; 0 IMPORTANT; 0 MINOR.
- scope: no migration, renderer, fragment engine, lifecycle/authority/domain redesign, Product redesign, legacy retirement or Phase4.
- commit subject: fix: harden shared pilot contract
- Task 7: NOT STARTED.
