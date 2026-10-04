# W4C Repair Round 1 — bounded browser smoke evidence (editorial_jewelry)

Section 11 of the repair directive: exactly ONE bounded real browser
smoke, `--only editorial_jewelry`, against a fresh, empty, dedicated
campaign root, expected 12 Base + 1 Tier-1 Theme = 13 cells, 2 Node
invocations. This is proof the repaired harness runs its real browser
assertions end-to-end -- it is explicitly NOT the final 704-cell
campaign evidence.

Command (same for every attempt below, campaign root wiped between
attempts with `rm -rf /tmp/w4c_smoke_campaign && mkdir -p
/tmp/w4c_smoke_campaign`):

```
/usr/bin/python3 manage.py qa_storefront_builder_r4 \
  --store-slug rasti-mode-demo --username w4c_qa_owner \
  --w4c-all50 --only editorial_jewelry \
  --report-dir /tmp/w4c_smoke_campaign --settings=shop_core.settings
```

## Attempt 1 — module-load crash (`15a_smoke_attempt1_module_load_crash.txt`)

Node's `run.mjs` threw at import time: `finalRemediationFixture()` is
called eagerly by a module-level array literal
(`FINAL_REMEDIATION_SCALAR_EDITS`) for every manifest shape, including
W4C manifests that never carry `manifest.phase3_fixture`. This is a
**pre-existing** defect (present at the certified base, already
documented in Implementation Round 1's `07_legacy_r4_non_interference.md`),
not introduced by this repair round, but it blocked the mandated smoke
entirely before any dispatch logic ran. Fixed with a one-line guard
(`if (!manifest.phase3_fixture) return {};`), safe because that array is
only ever consumed inside `phase3FinalRemediationFamilyGate`, itself only
invoked when `manifest.phase3` is true.

## Attempt 2 — 13/13 cells recorded, 10 genuine FAILs (`15b_smoke_attempt2_10_fails.txt`)

The harness now ran end-to-end: 12 base + 1 Tier-1 theme = 13 cells, 2
Node invocations, SQLite restore proof matched. 10/13 cells FAILed for 3
distinct, diagnosable root causes (Listing x3, PDP x3, Cart x3, and the
Theme cell -- Home x3 PASSed):

1. **Listing** (`cards=12 linkResolves=false href=/products/...`):
   `w4cRunListingCell`'s link-resolution request used the raw relative
   `href` with no origin prefix.
2. **PDP/Cart** (`stock="ناموجود"` / cart add failing): the fixture
   PDP product (`_build_w4c_fixture`) wasn't filtered for stock at all,
   so it could select (and did select) an out-of-stock VARIABLE product.
3. **Theme** (`rendered={"theme":"nowruz",...}
   expected={...,"componentKey":"theme.nowruz.v1"}`): `w4cRunThemeCell`'s
   identity check compared the rendered `data-occasion-theme` marker
   against a constructed `"theme.<occasion>.v1"` string, but
   `apps/core/context_processors.py` (`occasion_theme =
   _overlay.occasion_key`) renders the raw occasion key.

## Attempt 3 — 9 FAILs after fixes 1-3 (`15c_smoke_attempt3_9_fails.txt`)

Fixed all 3 above (listing origin-prefixing, fixture "has at least one
in-stock variant" filter, theme identity comparison against
`activeKey.occasion`). Fail count dropped 10 -> 9: Home and Theme now
PASS, but Listing (still `linkResolves=false`, same href) and PDP/Cart
(still `stock="ناموجود"`) did not improve.

Root-caused via a manual `manage.py shell` inspection of the DB and a
manual `runserver` + browser network trace: `manifest.origin` for W4C
cells is a fake customer-facing host
(`shop-<admin_subdomain>.<RASTISI_ADMIN_DOMAIN_SUFFIX>`) that resolves
*only* through Chromium's own `--host-resolver-rules` launch flag.
`targetPage.request`/`context.request` never goes through Chromium's
network stack for that mapping (confirmed empirically: the fix below
resolved it), so absolute-URL-prefixing alone could not fix the Listing
check, and the Cart cell's `context.request.post(...)` for add-to-cart
had the identical defect.

Separately, the fixture's "has at least one in-stock variant" predicate
was insufficient: `storefront_variant_service` picks the DEFAULT variant
as `is_default=True` else the first by `(display_order, id)` -- never
necessarily an in-stock one -- so a product with a mix of in-stock and
out-of-stock variants can still present an out-of-stock default variant
on the PDP.

## Attempt 4 — 3 FAILs after the listing/fixture fixes (`15d_smoke_attempt4_3_fails.txt`)

Fixed: (a) Listing's link check now runs `fetch()` inside
`targetPage.evaluate` (uses the browser's own resolver); (b) the fixture
predicate now requires *every* active, non-obsolete variant to be
in-stock, not just one. Fail count dropped 9 -> 3: Home, Listing, PDP,
and Theme all PASS. Only Cart (all 3 viewports) still failed
(`addStatus=null items=0 ...`) -- the identical
`context.request.post`-vs-Chromium-resolver defect, just in the Cart
cell's add-to-cart POST.

## Attempt 5 — final, 0 FAILs, 13/13 PASS (`15e_smoke_attempt5_final_0_fails.txt`)

Fixed: the Cart cell's add-to-cart POST now runs inside
`targetPage.evaluate` too (navigates to the PDP first so the
`csrftoken` cookie is set, reads it from `document.cookie`, POSTs with
`X-CSRFToken` + `HX-Request` headers and a `quantity` field -- mirroring
the real HTMX form, matching the production `cart_add` view's actual
contract).

```
W4C BATCH COMPLETE -- CAMPAIGN INCOMPLETE -- selected_keys=editorial_jewelry,
cells_recorded_this_run=13, cumulative_total_cells_recorded=13/704,
cumulative_missing=691, cumulative_fail_count=0, cumulative_blocked_count=0
Local database restored — pre=<sha256> post=<sha256> match=True
```

Full final matrix inspected in `14_repair_round1_smoke_final_matrix.json`:

- 12 base cells (Home/Listing/PDP/Cart x desktop/tablet/mobile): all
  `result: "PASS"`, all schema-complete (17 required fields), all
  carrying a distinct `run_token`.
- 1 Tier-1 theme cell (nowruz/balanced/desktop): `result: "PASS"`,
  `cleanup_verified: true`.
- `_meta.recovered_state_events`: populated with one genuine
  Template-drift-repair event (the fresh campaign root's first cell run
  found the Store's published Template state didn't match the preset,
  and the harness's own recovery path repaired and logged it -- not
  initialized-and-never-populated).
- `_meta.duplicate_cells`: empty.

**704-cell campaign was NOT run** (only this one template, 13 cells).
**No other Template was started.** **Static Gallery refresh was NOT run.**

## Regression coverage added for what the smoke found

Rather than leave these as one-off manual fixes, 5 new tests were added
to `test_w4c_all50_certification_harness.py` (source-grep regressions
for the listing/theme/cart fixes, plus 2 Python-level fixture-selection
tests including the mixed-stock edge case) -- see
`11_repair_round1_green.txt` for the 67/67 passing run that includes
them.
