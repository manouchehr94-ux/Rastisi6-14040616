# Date and time pickers (UI-DATE-01) — 2026-11-06

Branch `ux/platform-merchant-remediation-20261106`. Local only.

## Inventory: one picker implementation
RastiSi has a single Jalali picker component, `apps/core/static/core/jalali_picker.{js,css}`, which upgrades every native `<input type="date|datetime-local">` (the submitted value stays
the Gregorian ISO string the server expects). It is loaded by the Merchant Admin and Platform Admin bases only. There is no Gregorian-only picker and no third-party library.

## Root cause
The popup was `position:absolute` inside the field. Any ancestor with `overflow:hidden|auto` — Platform Admin `.pa-card`, `.pa-fieldset`, the modal body — clipped it, and nothing kept it inside
the viewport, so near the bottom or an edge it ran off-screen. Secondary defect: **Escape did not close the popup while focus was in the text field** (only inside the popup).

## Fix (one component, no per-page patches)
While open, the popup is placed with viewport (`position:fixed`) coordinates computed from the field: it flips above when there is no room below, is clamped horizontally, gets an internal
scroll as a last resort, follows scroll/resize, releases its inline placement on close, and calibrates itself against a transformed ancestor. The phone (<=560px) bottom-sheet layout is kept.
z-index 1200 already sits above modals (100) and sticky bars (<=500). Cache-busters added to the two bases.

## Matrix (real Chromium, PostgreSQL, synthetic data; viewports 1440x900, 1024x600, 390x800)
"Reachable" = every sample point inside the popup (inset past its rounded corners) is the popup itself per `elementFromPoint` (not clipped, covered or off-screen).
After the fix every popup is 100% reachable **and** selecting a day updates the submitted ISO value.

| Page | Field | Kind | Before: min % of popup reachable (3 viewports) | Root cause | After | Status |
|---|---|---|---|---|---|---|
| Merchant Admin `/admin-portal/collections/1/campaign/` | `ends_at` | date | 71% | absolute popup not kept inside the viewport / covered by following content | 100% reachable, selection → ISO OK | FIXED_AND_VERIFIED |
| Merchant Admin `/admin-portal/collections/1/campaign/` | `starts_at` | date | 86% | absolute popup not kept inside the viewport / covered by following content | 100% reachable, selection → ISO OK | FIXED_AND_VERIFIED |
| Merchant Admin `/admin-portal/coupons/add/` | `expires_at` | date | 71% | absolute popup not kept inside the viewport / covered by following content | 100% reachable, selection → ISO OK | FIXED_AND_VERIFIED |
| Merchant Admin `/admin-portal/coupons/add/` | `starts_at` | date | 100% | n/a (was fully visible at these viewports) | 100% reachable, selection → ISO OK | ALREADY_FINE_VERIFIED |
| Merchant Admin `/admin-portal/products/1/edit/` | `discount_ends_at` | date | 57% | absolute popup not kept inside the viewport / covered by following content | 100% reachable, selection → ISO OK | FIXED_AND_VERIFIED |
| Merchant Admin `/admin-portal/products/1/edit/` | `discount_starts_at` | date | 57% | absolute popup not kept inside the viewport / covered by following content | 100% reachable, selection → ISO OK | FIXED_AND_VERIFIED |
| Merchant Admin `/admin-portal/products/1/edit/` | `publish_at` | date | 71% | absolute popup not kept inside the viewport / covered by following content | 100% reachable, selection → ISO OK | FIXED_AND_VERIFIED |
| Platform Admin `/features/add/` | `planned_release_on` | date | 71% | clipped by `fieldset.pa-fieldset` (overflow) | 100% reachable, selection → ISO OK | FIXED_AND_VERIFIED |
| Platform Admin `/stores/` | `date_from` | date | 57% | clipped by `form.pa-card` (overflow) | 100% reachable, selection → ISO OK | FIXED_AND_VERIFIED |
| Platform Admin `/stores/` | `date_to` | date | 57% | clipped by `form.pa-card` (overflow) | 100% reachable, selection → ISO OK | FIXED_AND_VERIFIED |
| Platform Admin `/stores/289ca6aa-cdbc-4995-86dc-e37c8fed64c6/` | `trial_end_at` | date | 29% | clipped by `div.pa-modalbody` (overflow) | 100% reachable, selection → ISO OK | FIXED_AND_VERIFIED |
| Merchant Admin `/admin-portal/billing/invoices/<id>/card-to-card/` | `transferred_at` | date-time | 71% | absolute popup not kept inside the viewport | 100% reachable, selection → ISO local datetime OK | FIXED_AND_VERIFIED |

**Totals: 12 pickers, 39 popups measured. Failing before: 18. Failing after: 0.**

A first pass of the probe reported 36/36 failures; that overstated the problem (it sampled the four extreme corners, which lie outside the popup's rounded corners, and flagged `position:fixed`
popups as "clipped" by a geometric heuristic). Both flaws were corrected and **both** states were re-measured with the identical corrected probe; the numbers above are from that run.

## Components checked and not applicable
| Where | Result |
|---|---|
| Storefront customer profile / checkout birth date | plain text inputs with a Jalali placeholder — no popup, nothing to clip (`N/A`) |
| Platform `/payments/transactions/` | has no date filter (search, type, status, gateway only) — nothing to test |
| Storefront Studio / R4 editor | no date picker (the "picker" in `r4_editor.js` is the template picker) |
| Platform `/features/` list, `/industries/`, `/domains/`, `/subscriptions/` | no date inputs |

## Tests
`apps/core/tests/test_jalali_picker_placement.py` — 4 source guards + 7 Chromium tests (opt-in: `SFB_BROWSER_TESTS=1`, optional `SFB_CHROMIUM_PATH`): inside an `overflow:hidden` box, flips above near the bottom,
clamped at both horizontal edges, a transformed ancestor, phone bottom sheet, follows scroll and releases on close, Escape from the text field + ISO value on selection.
Verified to fail on the old picker (4 of the 7 browser tests). Existing `test_jalali_utils` / `test_followup14_jalali` still pass (33 tests together).

## Not verified
Firefox and WebKit were not run (Chromium only). Touch gestures and screen-reader announcements were not exercised.
