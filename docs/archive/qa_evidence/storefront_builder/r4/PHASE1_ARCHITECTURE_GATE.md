# RastiSi R4 — Phase 1 Architecture Gate

## A. Gate Metadata

- Date: 2026-09-01
- Branch: `feature/storefront-builder-r4`
- Pre-report HEAD: `3c1ef0eb218d9dd5007b8542f4b9bc07ecddb2af`
- Architecture Spec commit: `70ac7f72c82a8c1858ec541d88d762ece91c36f6`
- Phase 0 / Phase 1 Plan commit: `2e5d510c58b0ad926770f6cc6f5c4bf42632401e`
- Task 11 baseline/final SHA: `fffbedf5f474e8c664be53a7348950034062ff17`
- Task 12 final SHA: `3c1ef0eb218d9dd5007b8542f4b9bc07ecddb2af`
- Task 13 scope: architecture verification and this report only.
- No production, test, migration, static, template, or QA-tool source was modified during Task 13.

## B. Phase 0 / Phase 1 Commit Chain

Chronological authoritative history:

- `70ac7f72c82a8c1858ec541d88d762ece91c36f6` — docs(storefront-builder): define R4 architecture
- `2e5d510c58b0ad926770f6cc6f5c4bf42632401e` — docs(storefront-builder): plan R4 phase 0 and phase 1
- `a8dda857e371b2e79a1014e18276e0dc595519d8` — feat(storefront-builder): add R4 foundation state
- `5e5b76a48d77050f7d5baadd9dcd2f0c1f91486d` — feat(storefront-builder): add gated R4 editor shell
- `acf7a485d8dc134654bad120a7fc1ea5af6e44e3` — feat(storefront-builder): add declarative settings schema
- `5b0bb2396606af759ac9321cf0a6bfc944230bed` — fix(storefront-builder): harden R4 settings schema
- `f28ff83ca0652dd5b1f00c5765b96918c65dadf3` — feat(storefront-builder): register first R4 section schemas
- `5190ff4244cc9fc674ed4ea18e0be2c3f8b732a0` — feat(storefront-builder): add optimistic R4 mutation API
- `c05d784399ca990daa9c163e0215aa06ca079dd2` — fix(storefront-builder): stabilize R4 mutation errors
- `f2f08c214e6d7ceb1eeae833c5e688d73d551413` — feat(storefront-builder): add schema-driven R4 inspector
- `9cbf4a4e1259b150e15eb164f6567f8dba3bb0ab` — fix(storefront-builder): polish R4 inspector workspace
- `149321c5682ab3eefcdf0aedbd412dd9a263d336` — feat(storefront-builder): add Hero typography overrides
- `8cf1462605bb6d4d2bbf378d3d268c2886353870` — feat(storefront-builder): add R4 structure mutations
- `427e4d224f359c272ff2eda18bed5939efc258cc` — fix(storefront-builder): preserve R4 section ordering
- `1b2f34ad7f86f4a81e57ef75d047f3c6aceb5099` — feat(storefront-builder): add shared ResourceSource contract
- `77f003077fc783bbf038cd3cfbaa5ef4dac288bb` — fix(storefront-builder): harden ResourceSource contract
- `16f938367564b6f0b2a551b02f4c35ed873f9ab6` — feat(storefront-builder): add shared R4 resource picker
- `795fc880681227dfc475971377f3b4498a18d5b6` — fix(storefront-builder): reject oversized R4 picker selection
- `fffbedf5f474e8c664be53a7348950034062ff17` — feat(storefront-builder): wire R4 global controls and publish

Task 12 browser QA chain:

- `b4a55943068927c41380366f2a84ccdf973f6924` — test(storefront-builder): prove R4 vertical slice in browser
- `40d377344e24eb40811fc70b486ede678d5f55c7` — test(storefront-builder): harden R4 browser QA evidence
- `6c667daf44e18ddfe00bfb3580e08ea654480fd1` — test(storefront-builder): close R4 browser QA safety gaps
- `3c1ef0eb218d9dd5007b8542f4b9bc07ecddb2af` — test(storefront-builder): persist R4 QA feature gate

Task 13 adds only this architecture-gate report after verification.

## C. Level 1 — Focused R4 Verification

Command:

`python manage.py test apps.storefront_builder.tests.test_r4_foundation apps.storefront_builder.tests.test_r4_settings_schema apps.storefront_builder.tests.test_r4_mutation_api apps.storefront_builder.tests.test_r4_inspector apps.storefront_builder.tests.test_r4_appearance_overrides apps.storefront_builder.tests.test_r4_resource_source apps.storefront_builder.tests.test_r4_resource_picker apps.storefront_builder.tests.test_r4_vertical_slice -v 1`

Evidence:

- Found: 356 tests
- Ran: 356 tests
- Duration: 348.362s
- Result: `OK`
- Django system check: no issues
- The logged `ImproperlyConfigured` response for unsupported Inspector `color/swatch` is an intentional negative-test contract and did not fail the suite.

## D. Level 2 — Neighboring Subsystems

Command covered:

- appearance
- history identity
- global header
- global footer
- layout service
- universal selection
- variant runtime wiring
- Ready Template real previews
- section registry
- acceptance batches 1–3
- Phase 30 container/cell foundation
- Phase 31 container/cell builder
- row service
- admin V22 live builder
- R3 simple live editor

Evidence:

- Found: 768 tests
- Ran: 768 tests
- Duration: 213.212s
- Result: `OK`
- Django system check: no issues

## E. Level 3 — Full Repository Suite

Command:

`python manage.py test -v 1`

Evidence:

- Found: 7025 tests
- Ran: 7025 tests
- Duration: 9158.973s
- Result: `FAILED (failures=1, errors=4, skipped=4)`

The five non-green cases were investigated rather than repaired opportunistically.

### Pre-existing / unrelated guest-cart fixture debt

Three errors:

- `SignupViewTests.test_signup_merges_guest_cart`
- `LoginViewTests.test_login_merges_guest_cart`
- `OtpLoginViewTests.test_otp_login_merges_guest_cart`

The tests create Products without positive stock while the current cart contract rejects zero-stock products. The failure is in legacy auth/cart fixture assumptions and is outside the R4 implementation surface. R4 did not modify the customer-auth/cart code responsible for this behavior.

### Pre-existing / unrelated R3 fullscreen assertion debt

Two cases under `FullscreenEditorTests`:

- `test_fullscreen_state_is_a_pure_css_toggle_not_a_new_route`
- `test_fullscreen_button_is_in_v3_topbar_with_device_and_zoom_controls`

These assertions target older R3 fullscreen markup/contracts already superseded before the R4 work. They are not R4 editor regressions.

No Task 13 repair was made for these unrelated failures.

Per the Phase-1 Plan, the Level-3 suite was executed once at the architecture checkpoint and was not repeatedly rerun for unrelated legacy-test debt.

## F. Playwright Browser Verification

Command:

`python manage.py qa_storefront_builder_r4 --store-slug akhlaghi --username r4_qa_admin --port 8798`

Fresh Task-13 evidence:

- Passed: 15
- Failed: 0
- All 13 required browser scenarios passed
- Final instrumentation assertions: PASS
- Final screenshot verification: PASS
- `unexpected_console_errors`: 0
- `expected_stale_409_console_events`: 1
- `expected_stale_409_http`: 1
- Expected stale URL: `/admin-portal/storefront-builder/r4/mutate/`
- `unexpected_http_errors`: 0
- `unexpected_request_failures`: 0
- `page_errors`: 0
- `expected_main_frame_navigations`: 11
- `unexpected_main_frame_navigations`: 0
- Product public-parity label hits: 2
- Brand public-parity label hits: 2

Database safety proof:

- Pre-run SHA256: `e82a81f2309fafb9125d1756f9db04bf87b6d51977559cdcbf28c26c30e9ea22`
- Post-restore SHA256: `e82a81f2309fafb9125d1756f9db04bf87b6d51977559cdcbf28c26c30e9ea22`
- Match: `true`

The fresh browser run regenerated runtime screenshot evidence. Those runtime-only image changes were reviewed and then restored to committed HEAD; the working tree returned clean.

## G. Phase-1 Screenshot Evidence

- `docs/qa_evidence/storefront_builder/r4/phase1/01_r4_initial.png`
- `docs/qa_evidence/storefront_builder/r4/phase1/02_hero_basic.png`
- `docs/qa_evidence/storefront_builder/r4/phase1/03_hero_advanced_typography_override.png`
- `docs/qa_evidence/storefront_builder/r4/phase1/04_product_added_reordered.png`
- `docs/qa_evidence/storefront_builder/r4/phase1/05_product_manual_picker.png`
- `docs/qa_evidence/storefront_builder/r4/phase1/06_brand_manual_picker.png`
- `docs/qa_evidence/storefront_builder/r4/phase1/07_conflict_detected.png`
- `docs/qa_evidence/storefront_builder/r4/phase1/08_publish_success.png`
- `docs/qa_evidence/storefront_builder/r4/phase1/09_public_storefront_after_publish.png`
- `docs/qa_evidence/storefront_builder/r4/phase1/10_draft_changed_public_unchanged.png`

## H. Mandatory Architecture Gate

| # | Criterion | Evidence | Result |
|---|---|---|---|
| 1 | R4 uses the existing Draft/Published and renderer infrastructure. | R4 resolves the existing StorefrontLayout active Draft and delegates publication/rendering to existing storefront-builder services; no duplicate Draft/Published domain was introduced. | PASS |
| 2 | One R4 shell only; R2/R3 markup is not embedded inside it. | Dedicated `r4/editor.html` shell, gated R4 route, and focused foundation/browser evidence. | PASS |
| 3 | Rich Text and Hero settings are schema-driven. | `settings_schema.py`, registered Section schemas, Inspector tests, and live Hero Basic/Advanced Playwright scenarios. | PASS |
| 4 | Normal settings save goes through one mutation endpoint/service. | R4 client uses one `mutate/` endpoint and `r4_mutation_service.apply_mutation`; Inspector controls dispatch through the same serialized queue. | PASS |
| 5 | Product and Brand use the same Resource Picker component/contract. | Shared `ResourceSource`, shared Picker template/JS lifecycle, and separate Product/Brand Playwright scenarios both pass. | PASS |
| 6 | Add/remove/duplicate/reorder use the same revisioned mutation boundary. | Structural actions dispatch `section.add/remove/duplicate/move` through the same R4 mutation service and revision queue. | PASS |
| 7 | Hero typography override is sparse and does not mutate global appearance or sibling sections. | Typed `appearance_override` validation plus focused isolation tests and live Advanced Hero persistence scenario. | PASS |
| 8 | Preview and public storefront still share the existing renderer. | R4 shell points at existing `storefront-builder-preview`; R4 did not introduce a second storefront renderer; public parity browser evidence passes. | PASS |
| 9 | Stale `base_revision` is rejected with 409; no silent overwrite. | Fresh browser QA recorded exactly one deliberate stale HTTP 409; attempted stale field mutation was rejected and recovery editing then succeeded. | PASS |
| 10 | Public storefront changes only on Publish. | Browser scenarios prove Publish changes Public and the subsequent Draft-only change does not; screenshots 09 and 10 preserve Public parity. | PASS |
| 11 | No normal R4 flow opens an admin iframe or second save lifecycle. | Inspector and generic Resource Picker are in-shell surfaces; browser QA checks the normal Inspector/Picker flow and no independent save lifecycle exists. Preview remains the single intended storefront preview iframe. | PASS |
| 12 | Focused Playwright smoke passes with evidence. | Fresh Task-13 browser run: 15 passed, 0 failed, exact expected 409 only, all unexpected instrumentation counters zero, DB restored byte-for-byte. | PASS |
| 13 | R3 routes still work for non-R4 stores. | Level-2 suite includes R3/live-builder compatibility modules and passed 768/768. R4 remains separately feature-gated. | PASS |
| 14 | `git diff --check`, `manage.py check`, and migration drift checks are clean. | Fresh Task-13 checks: `git diff --check` clean; Django check 0 issues; `makemigrations --check --dry-run` reports no changes. | PASS |

## I. Remaining Known Issues

### Architecture blockers

None identified for the R4 Phase-1 architecture gate.

### Non-blocking known issues

The Level-3 full suite contains legacy test debt unrelated to R4:

1. Three guest-cart auth tests use zero-stock Product fixtures while the current cart service requires available stock.
2. Two legacy R3 `FullscreenEditorTests` assert superseded fullscreen markup/contracts.

These were disclosed and intentionally not repaired during Task 13.

### Deferred Phase-2 work

Phase 1 proves the architecture and the first complete vertical slice. Broader editor capability, additional schema field/widget coverage, additional section/resource editing capabilities, and other planned R4 expansion remain Phase-2 scope and are not architecture defects.

## J. Final Static Checkpoint

Immediately before this report was created:

- `git status --short`: clean
- `git diff --check`: clean
- `python manage.py check`: `System check identified no issues (0 silenced).`
- `python manage.py makemigrations --check --dry-run`: `No changes detected`
- `git diff --name-status 3c1ef0eb218d9dd5007b8542f4b9bc07ecddb2af..HEAD`: empty

Task 13 therefore entered its report step with no production or test-source changes.

**Recommendation: PROCEED TO PHASE 2**
