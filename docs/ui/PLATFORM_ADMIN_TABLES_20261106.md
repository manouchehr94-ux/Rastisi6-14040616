# Platform Admin tables, filter bars and transactions — 2026-11-06

Branch `ux/platform-merchant-remediation-20261106` (from the pushed Checkout commit `8ad4b687`). Local only.

## UI-ADMIN-01 `/industries/` — root cause
`.pa-ltr{display:inline-block}` (a utility for inline LTR text) was applied directly to `<td class="pa-ltr">` (the slug column). It overrides `display:table-cell`, so that cell
left the table's row layout: 47.8px tall instead of the row's 63px, a different top (385.3 vs 384.8), and its bottom border no longer lined up with the row's — exactly the
"fragmented separator / slightly moving row" in the screenshot. Fixed once, in the shared stylesheet: `td.pa-ltr,th.pa-ltr{display:table-cell}`.

## UI-ADMIN-03 — the same defect class elsewhere
A browser crawl (31 Platform Admin pages x 5 widths 1440/1024/768/390/320; 155 tables, 1330 rows, 80 filter bars; real Chromium, PostgreSQL, synthetic data) measured every row:
all cells must be `display:table-cell` with one shared top and height; filter controls in a row must share one top; no horizontal overflow; no console errors.

| | pages affected | problems |
|---|---|---|
| Before (Checkout `8ad4b687`) | `/industries/`, `/domains/`, `/subscriptions/`, `/payments/`, `/users/`, `/audit-log/` | 62 |
| After | none | **0** |

Second cause found by the crawl: `<td class="pa-row">` (`display:flex`) on `/domains/` and `/subscriptions/`. A table cell must not be the flex container; the content now sits in a
`<div class="pa-row pa-nowrap">` inside `<td class="pa-actcol">` (the existing action-column convention).
A static guard (`TableCellLayoutGuardTests`) now fails whenever a class that sets a non-table-cell `display` is used on a `<td>/<th>` without a `td.<class>` override
(verified to fail on both original defects).

## UI-ADMIN-02 `/payments/transactions/`
* Filter bar (shared by 16 pages): `.pa-filters` was `align-items:end`, so any field with help text ("فروشگاه، شماره‌یِ فاکتور یا توکن") pushed its control above the others and orphaned
  neighbouring fields. Now top-aligned with an explicit label line-height, and the actions take their own full-width row (no wrapping inside a narrow track).
* The empty state "تراکنشی یافت نشد" is **correct** for the QA database: it genuinely has no platform transactions. No fake data was created for the page.
* Real functional defect found while verifying: `_attempt_rows` cut each kind to 300 rows *before* pagination, so older financial records were silently unreachable. Replaced with a lazy
  merged sequence (`len` = COUNTs, slices read only what the page needs): 310 attempts → 13 pages, all reachable.
* Tests (`apps/portal/tests/test_platform_admin_tables.py`, 13): permissions (anonymous / non-staff), empty state, both kinds listed, search hit/miss, kind/status/provider filters and reset,
  unknown filter value, pagination keeps filters, >300-row history.
* The global header search is labelled "جستجو در فروشگاه‌ها…" and does search stores; it was kept.
