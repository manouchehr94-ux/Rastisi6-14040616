# Task 8 — final architecture/regression gate

## Result: PASS — Phase 3 vertical-slice CLOSED for the two pilot families (Brand, Collection)

## Authority and scope

- Repository: `manouchehr94-ux/Rastisi6-14040616`
- Branch: `feature/phase3-task7-task8`
- Task-7 starting SHA (repo migration point, carried forward from the old Rastisi5 workspace):
  `973c1dc00bacb6f2f7d2604fa3880bb4d6250579`
- Task-7 RED checkpoint (preserved, unamended): `b3e69147e3681980233cd4c7beac1790e184189d`
  (safety ref `backup/rastisi6-phase3-task7-red-20260907`, verified identical)
- Task-7 repair commit: `9fd27f8b089718fcaa338eec8aa1469814b71b79`
- Task-7 final certification commit: `578b3db5eb282e133949cf56ab13caca9be19e0a`
  (safety ref `backup/rastisi6-phase3-task7-final-20260907`, verified identical)
- Task-8 starting SHA: `578b3db5eb282e133949cf56ab13caca9be19e0a`
- Environment: same Claude Code Web sandbox as Task 7 (Python 3.11.15 venv, Django 5.2.17, no
  `DATABASE_URL`, local disposable SQLite).
- Task-8 production authorization: NONE. Task-8 test-code authorization: NONE. Nothing was fixed
  during this audit — see "MINOR findings" below, all deferred, none blocking.

Preconditions verified before starting: branch correct, HEAD == `578b3db5...`, worktree clean,
`e244619f395ebf0dbebc77d2033841e17f1cd099` and `c34a04e71cc62d191d6fe8238ef4e6735fb6642f` both
ancestors of HEAD, `origin/main` unchanged at `973c1dc00bacb6f2f7d2604fa3880bb4d6250579`.

## Baseline regression — Run A / B / C (exact commands from `baseline.md`)

No module list was reconstructed or substituted; the exact argument lists from `baseline.md` were
re-run verbatim. Counts have grown since the original Task-0 baseline (633/119/59) because Tasks
1–7 added real test methods inside these same modules — this is expected, not a discrepancy.

| Run | Command scope | Result | Known exceptions |
|---|---|---|---|
| A | 20 modules (render/domain/lifecycle/vertical-slice) | **734 tests, FAILED (failures=1, skipped=1)** | #1 `test_validate_appearance_config_is_the_validator_boundary` — `validate_appearance_config` called 2 times instead of once (exact same signature as baseline.md). Skip: `QuickLinksRenderTests.test_menu_from_another_store_never_leaks` — `"no second store fixture available"` (exact same signature). |
| B | 8 modules (capability/asset/QA/media) | **121 tests, FAILED (failures=2, errors=1)** | #2 `test_fullscreen_button_is_in_v3_topbar_with_device_and_zoom_controls` — `:aria-pressed="fullscreen"` absent (exact same signature). #3 `test_fullscreen_state_is_a_pure_css_toggle_not_a_new_route` — `StopIteration` (exact same signature). #4 `test_header_footer_variant_labels_shown_for_updated_preset` — Persian gallery label mismatch (exact same signature). |
| C | 3 modules (Cart/renderer) | **77 tests, OK** | none |

**Combined: 932 executions, 927 pass, 3 fail, 1 error, 1 skip.** All four failure/error
signatures and the one skip are byte-for-byte the same as the four pre-existing exceptions
`baseline.md` names and the one pre-existing skip it names. **No new regression exists anywhere
in the baseline matrix.**

## Additional final regression (methods not in baseline.md)

```
python manage.py test \
  apps.storefront_builder.tests.test_r4_inspector \
  apps.storefront_builder.tests.test_g23_builder_public_content_appearance \
  apps.storefront_builder.tests.test_page_shell \
  apps.storefront_builder.tests.test_views \
  --noinput -v2
```

**331 tests, FAILED (failures=1, errors=1).** Wider `test_views` (the full module, not just
`FullscreenEditorTests`) surfaced no additional pre-existing signature beyond the two already
named in Run B (#2, #3) — confirmed by name: only
`test_fullscreen_button_is_in_v3_topbar_with_device_and_zoom_controls` (FAIL) and
`test_fullscreen_state_is_a_pure_css_toggle_not_a_new_route` (ERROR) appear; `test_r4_inspector`,
`test_g23_builder_public_content_appearance`, and `test_page_shell` are fully green. No new
exemption was invented.

## Django check / migration check / diff check

```
python manage.py check                              → System check identified no issues (0 silenced)
python manage.py makemigrations --check --dry-run    → No changes detected
git diff --check                                     → clean
```

**No migration file exists anywhere in the cumulative Phase-3 diff** (confirmed via
`git diff --name-only e244619f395ebf0dbebc77d2033841e17f1cd099 HEAD | grep migrations` — empty).

## A06 / V02 / scope audit

### A06 final audit

Both pilot families now have direct browser proof for every allowed envelope (E1 Home, E2 Product
detail, E3 Listing/Search, E4 Collection detail, E5 Cart), certified in Task 7's final matrix
(`task7_browser_matrix.md`): Brand 45/45, Collection 36/36, both zero known-red findings, zero
console/page/network errors outside the two documented intentional exceptions (one stale-409, two
disposable broken-image fixtures). E6 Collection index remains a correctly-separate companion
(`sb_css: 0`, no pilot placement) — it does not substitute for E4, per spec. **A06 is CLOSED for
these two Phase-3 pilot families only.** No global/all-family A06 claim is made.

### V02 six-case exit

Independently re-verified against the actual test code (`test_r4_mutation_api.py`,
`BrandCarouselV01V02MutationTests`, lines 463–711) by the fresh whole-branch reviewer: real test
methods exist for all six cases —
(a) valid grid+destination enables View-all with the resolved anchor,
(b) absent/invalid destination rejects the enable,
(c) beauty_tabs rejects even with a valid destination,
(d) supporting→beauty_tabs preserves the dormant stored value,
(e) beauty_tabs→supporting restores the compatible effective value,
(f) spoofed capability/destination payload cannot grant authority —
each rejecting case asserting HTTP 400 plus unchanged `settings`/`edit_revision`/history count.
Browser-level control/anchor truth re-confirmed in Task 7's 45 V02 anchor records (unaffected by
the Task 7 repair, which touched only Collection CSS and Cart's stylesheet loading).

### V01–V10 final audit

| Gap | Status |
|---|---|
| V01 local variant intent preservation | **CLOSED** both families — `APPEARANCE_OVERRIDE_AWARE_SECTION_KEYS` contains both `brand_carousel` and `collection_tiles` (Task 2 + Task 6). One narrow legacy-path asymmetry noted as MINOR below (currently inert — see disposition). |
| V02 View-all variant+destination capability | **CLOSED** — six-case exit above; enforced at the R4 mutation/inspector boundary; legacy destination authoring preserved unchanged (no new destination editor). |
| V03 typed Collection source/schema/picker/ownership | **CLOSED** — Task 4; adapters map onto the existing `collection_ids`/`tile_style` settings keys, no second persisted source. |
| V04 count/query semantic distinction | **CHARACTERIZED, not changed** — total membership `Count("items")` vs visible-product count preserved and documented (Task 4/5); changing count meaning remains a separate, undecided product question, correctly not addressed here. |
| V05 Cart fragment context + isolated wrapper proof (A04, pilot) | **CLOSED for the two pilots** — `_render_cart_container` calls the existing `build_universal_storefront_context` (pre-existing service; Task 3 made Cart call it), Preview wrapper projection proven 3× stable. Global/Listing/Newsletter A04 remains explicitly deferred (V09). |
| V06 asset-envelope mismatch (A06) | **CLOSED for the two pilots** — Task 7 found the residual Collection CSS gap; repaired under separate bounded authorization (commit `9fd27f8`); re-verified 36/36 PASS. |
| V07 responsive/media/common-control truth | **CLOSED for the two pilots** — RTL, native scroll, keyboard focus, objectFit, no document overflow all asserted and PASS across all 3 viewports for both families (Task 7). |
| V08 browser reproducibility (QA platform) | **CLOSED** — harness now certifies both families, all viewports, DB restore proof on every run. |
| V09 remaining program-wide A04 (other families) | **DEFERRED to Phase 4**, as designed — no claim of closure beyond the two pilots. |
| V10 broad migration/closed Phase-2 nits | **DEFERRED**, unchanged — not reopened by this task. |

No P0/CRITICAL gap remains for the two Phase-3 pilot families.

## Cumulative diff / architecture audit

Audited both `e244619f395ebf0dbebc77d2033841e17f1cd099..HEAD` (official Phase-2 baseline) and
`c34a04e71cc62d191d6fe8238ef4e6735fb6642f..HEAD` (Phase-3 preparation baseline), independently, by
a fresh reviewer with no prior context in this task (see "Fresh whole-branch review" below).
Confirmed directly against the actual diff, not trusted from ledger prose:

- **Zero migration files** anywhere in either diff.
- **Zero files outside** `apps/cart/`, `apps/catalog/`, `apps/storefront_builder/`, `tools/`,
  `docs/` — no unrelated app (`orders`, `customers`, `core`, `stores`, `content`,
  `subscriptions`, `portal`, `sms`) touched.
- **Exactly 12 non-test, non-doc, non-migration production files** touched across all of Phase 3
  (Tasks 1–7 cumulative): `apps/cart/views.py`, `apps/cart/templates/cart/cart_detail.html`,
  `apps/storefront_builder/management/commands/qa_storefront_builder_r4.py`,
  `apps/storefront_builder/r4_views.py`, `apps/storefront_builder/resource_source.py`,
  `apps/storefront_builder/section_registry.py`,
  `apps/storefront_builder/services/r4_mutation_service.py`,
  `apps/storefront_builder/static/css/storefront_builder.css`,
  `apps/storefront_builder/static/storefront_builder/r4_editor.js`,
  `apps/storefront_builder/templates/dashboard/storefront_builder/partials/section_settings_form.html`,
  `apps/storefront_builder/views.py`, `tools/storefront_builder_r4_qa/run.mjs`.
- **`apps/storefront_builder/services/render_service.py` diff is literally empty** — the shared
  renderer needed zero changes across all of Phase 3, confirming "no second renderer" and "no
  renderer redesign" by direct inspection, not just by claim.
- **`layout_service.py` and `edit_history_service.py`: zero diff** — structure lock and
  lifecycle/history remain untouched, confirming "structure lock remains structure-only" and "no
  lifecycle redesign."
- **`appearance_authority_service.py`, `section_appearance_service.py`,
  `storefront_context_service.py`, `container_service.py`: zero diff** — confirming "common
  Appearance precedence remains unchanged."
- **No second `build_page_render_items`-shaped function, no second appearance-resolution
  service, no second place `brand_ids`/`collection_ids` gets written from** — exactly one of
  each; `collection_resource_source_to_legacy_patch` maps onto the pre-existing `collection_ids`
  settings key, never a new persisted field.
- **`apps/cart/views.py` diff confined to `_render_cart_container`'s presentation-context
  assembly** — `cart_add`/`cart_item_update`/`cart_item_remove`/`_cart_context`/
  `_header_counts_context` all untouched; real commerce semantics (pricing, stock, mutation)
  intact.
- **Tenant isolation**: Collection's R4 ownership check (`_validate_resource_source_ownership`)
  mirrors Brand's exactly (`filter(store=store, pk__in=...)`, count comparison, same rejection
  code); the legacy ownership validator already covered both `brand_ids`/`collection_ids`
  identically before Phase 3 (unchanged).
- **No Phase-4 scope**: exactly one new schema (`COLLECTION_TILES_SCHEMA`) added to the R4
  registry; no other family given typed-source/browser-certification treatment. Legacy settings
  paths for both Brand and Collection remain present alongside R4 (no retirement) — confirmed at
  `views.py:849` (Collection) and `:868` (Brand, per the reviewer's line numbers on the audited
  tree).
- **Task 7's escalation is real and correctly scoped**: the repair commit `9fd27f8b` touches
  exactly the two authorized files, nothing else; the RED checkpoint `b3e6914` precedes it
  unamended in `git log`.

## Fresh whole-branch review

Performed by a fresh-context agent with no prior involvement in this project, reviewing the
entire cumulative branch (not just Task 8's own documents) against the binding spec, the
implementation plan's per-task allowed-file lists, and the actual current code — independently
verifying every claim above rather than trusting prior evidence documents.

```
SPEC COMPLIANCE: PASS
CODE/TEST QUALITY: PASS
ARCHITECTURE: PASS
CRITICAL: 0
IMPORTANT: 0
MINOR: 3
```

### MINOR findings (recorded with disposition; none fixed — Task 8 has no production/test authorization)

1. **MINOR (DEFERRED):** `apps/storefront_builder/views.py`'s legacy (non-R4) settings-save path
   only stamps/preserves the trusted `variant_explicit` marker for `brand_carousel`
   (`if section.section_key == "brand_carousel"`), not `collection_tiles` — an asymmetry against
   Task 6's R4-path fix, which covers both. REASON currently inert: `storefront_appearance/
   adapters.py` registers `section_variant:` families only for `hero_banner`/`product_section`/
   `catalog_product_wall`, so `section_variant_for` resolves to `None` for BOTH pilots on this
   code path today — the marker isn't actually consumed there yet for either family. RISK IF
   WRONG: low today (no observable behavior difference); becomes a real Collection-specific gap
   only if a future change registers Collection into that adapter family without also updating
   this legacy-save guard. FUTURE TARGET: a bounded follow-up task, not blocking Phase-3 closure.
2. **MINOR (DEFERRED):** the V02 supporting-variant-AND-destination capability gate is enforced
   only at the R4 mutation boundary (`_validate_brand_view_all_enable`); the legacy form has no
   equivalent gate, so a crafted legacy POST could in principle persist `show_view_all=True` on
   `beauty_tabs` or with an unresolvable destination. REASON not a security issue: render-time
   resolution (`_brand_carousel_context`) still never emits the anchor for beauty_tabs or an
   unresolved destination, so the persisted state is merely dormant — exactly the state V02(d)
   already blesses as an acceptable roundtrip case. RISK IF WRONG: none observable; legacy
   destination authoring is explicitly out of this phase's scope per spec §13 ("do not add a
   broad R4 destination editor"). FUTURE TARGET: none required unless legacy Brand authoring is
   revisited.
3. **MINOR (DEFERRED):** `section_settings_form.html`'s `show_view_all_field_present` hidden
   marker is client-supplied rather than re-derived server-side from the already-known
   `display_mode`. REASON low risk: same-store authenticated staff action only, no privilege
   escalation, and the server already independently re-validates the resulting persisted state.
   RISK IF WRONG: cosmetic (a crafted legacy POST could suppress a genuine uncheck), not an
   authority or tenant-isolation issue. FUTURE TARGET: harden by re-deriving the marker from
   `display_mode` server-side if the legacy form is touched again for another reason.

None of the three findings is CRITICAL or IMPORTANT; none blocks Phase-3 closure per the
project's own gate criterion ("Any CRITICAL or unresolved IMPORTANT means STOP").

## Cumulative test/browser evidence summary

- Baseline Run A/B/C: 932 executions, 927 pass, 3 fail + 1 error (4 known signatures) + 1 skip
  (1 known signature) — no new regression.
- Additional regression (`test_r4_inspector`/`test_g23`/`test_page_shell`/`test_views` full
  module): 331 tests, 329 pass, the same 2 known fullscreen exceptions, no new signature.
- Task 7 browser matrix (final, post-repair): 16/16 scenarios PASS, Brand 45/45 + Collection
  36/36 variant checks PASS, 0 known-red findings, 0 unexpected errors, DB restore SHA256 match.
- `python manage.py check` / `makemigrations --check --dry-run` / `git diff --check`: clean at
  every checkpoint across Tasks 1–8.

## Phase-4-not-started assertion

No other component family received typed-source, schema, or browser-certification treatment; no
non-Home R4 UI rollout occurred; no legacy retirement occurred; no broad Page Override, Template
Switch, or 50-template work occurred; no media cleanup/TTL/deletion-system change occurred; no
Product/commerce redesign occurred. **Phase 4 was NOT started.**

## Allowed-file / scope audit (final)

Cumulative production files touched across all of Phase 3 (Tasks 1–7, the entire branch): exactly
the 12 files listed in "Cumulative diff / architecture audit" above. Cumulative test files
touched: extensions to existing test modules only (no new test module files invented). Cumulative
evidence: `docs/qa_evidence/storefront_appearance_convergence/phase3/` — spec, plan, baseline,
inventory, execution ledger, four per-family/shared gate documents (Task 3/5/6), the Task-7
browser matrix, and this document. Task 8 itself touched zero production files and zero test
files — audit/evidence only, as authorized.

## Final Phase-3 closure ruling

Both pilot families (Brand `brand_carousel`; Collection `collection_tiles`) have separately
passed: selection/order/domain ownership, typed source/schema, capability truth (V02 six-case
exit), variant preservation (V01), canonical mutation/lifecycle/identity, Preview/Public parity,
wrapper/fragment proof (V05, harness projection + real Cart HTMX, both individually and combined),
assets/JS/media (A06, now fully closed for both pilots after the Task-7-discovered,
separately-authorized Task-5-scope repair), desktop/mobile/tablet responsive behavior including
RTL/native-scroll/keyboard-focus, and tenant isolation. Shared conclusions cite evidence from both
families throughout (Task 6). The one genuine production regression this program encountered
(Collection's incomplete Task-5 CSS mirror) was found by Task 7's harness, correctly NOT
silently fixed within Task 7, escalated with full RED evidence, repaired only after explicit
separate authorization narrowly scoped to the exact two implicated files, and re-verified with
two more independent review rounds before being accepted as closed.

**Storefront vertical-slice Phase 3 is CLOSED for these two pilot families.** No global/all-family
convergence is claimed. Original other-family A04 (V09) and broad migration/legacy-nit cleanup
(V10) remain explicitly deferred to Phase 4 or a separately approved decision, per spec §26.

**Phase 4 does not start automatically.** This project now awaits Product Owner/Architect review
of Phase 3's completed closure before any Phase 4 scope is authorized.
