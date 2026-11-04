# RastiSi Admin Experience Upgrade — QA delivery report

Branch `feature/admin-panel-modernization-20261029` (from `6d6258d3316acb4284d2fe4bd6c7c0778310da14`), QA only. Nothing merged, deployed,
published or migrated on Production.

## Environment
- Worktree: `/home/user/QA_ADMIN_PANEL_20261029` — own DB copy (`db.sqlite3`, git-ignored) and own Media (`/home/user/ADMIN_QA_DATA_20261029`).
- Server script: `/home/user/ADMIN_QA_DATA_20261029/run8008.sh` (port **8008**; 8006/8007 environments untouched).
- QA DB was migrated with `core 0022/0023` and `orders 0020`; QA demo data changed: card-to-card configured (test card 6037 9970 0000 0019),
  `QA-NB-*` sample products/5 brands imported from sample file 01, a few card-to-card demo orders, one shipping method activated.

## Commits (one per step)
| Step | Commit | Content |
|---|---|---|
| M0 | `33648394` | technical contract (`ADMIN_UPGRADE_CONTRACT.md`) |
| M1a | `c6f5d4d9` | shared password toggle (eye in a reserved gutter, RTL/LTR, ≥44px) |
| M1b | `67413d40` | shared admin design layer `au-*`; «مدیریت سفارش‌های پرداخت‌نشده» category |
| M2 | `7264a1d1` | one tax editor, new-store tax default (off, 10 % suggested), shipping single reference |
| M3 | `c472cc69` | advanced Excel import + approval queue, product-list button, samples |
| M4 | `9ab2810b`, `16770a98` | card-to-card on the real payment infrastructure |

## Migrations (additive, reversible)
- `core/0022_new_store_tax_defaults` — only changes the DEFAULT of `tax_enabled` / `tax_percent` (callables reading Django settings). No data
  change: existing stores keep their values (test proves it across the migration). On SQLite Django rebuilds the table copying rows; no-op on PostgreSQL.
- `core/0023_import_proposal` — new table `ImportProposal`.
- `orders/0020_card_transfer` — new table `CardTransferSubmission` (+2 unique partial constraints) and two choice additions
  (`PaymentGatewayConfig.gateway_code`, `Transaction.method`) — no data change.

## Tests
- New: password toggle 9 (incl. real Chromium geometry RTL/LTR/390px), tax upgrade 14, import proposals 16, card transfer 28, expiry UI 2.
- Intentionally changed existing tests (listed): import view template tests (new column order, sample sheet, soft dropdowns, summary keys),
  settings view tests (rate edited only on the tax page), order-expiry UI test (new category), navigation IA (+«بررسی کارت‌به‌کارت»),
  cart two-store pricing (tax enabled explicitly — new stores start without tax).
- Full suite (`manage.py test apps --parallel 6`): 11 545 tests; 38 non-passing, **all pre-existing or environmental**: 32 are the known
  baseline list; 8 more (portal ready-template gallery, rasti-mode demo refresh, email-transport import) fail identically on the untouched base commit;
  `sms.test_gateway_live` fails only in the parallel run (live-server port) and passes alone. No failure caused by this branch.
- Firefox/Windows was not testable in the cloud container (Chromium only).

## Scenarios proven in the real UI (Chromium on port 8008)
1. Password: portal login at 390 px / 1440 px — eye icon in its own gutter; toggles; resets on submit.
2. Import: product list → «ورود گروهی کالا با اکسل» → upload sample 01 → 6 proposals (5 brands + 1 subcategory), 2 rows ready, 6 «منتظر تأیید»;
   execute blocked → «تأییدِ همه» (confirm dialog) → exactly 5 brands + 1 subcategory → 8 products created → report links to product list;
   a re-import creates nothing (unit test `FiveNewBrandsScenario`).
3. Card-to-card: admin saves the destination card (Luhn-validated, stored encrypted) and activates → customer sees amount + card, submits last 4 + tracking →
   order shows «در انتظار بررسی پرداخت», still unpaid → admin approves (confirm dialog) → order paid + processing, one Transaction; second order rejected with a reason.

## Files for review
Sample workbooks: `docs/admin-upgrade/samples/*.xlsx` (+ generator). Before/after composites are delivered separately (not committed).

## Remaining risks / gaps
- Card-to-card orders waiting for review keep their stock reserved until an admin decides or cancels (never auto-expired through the online path;
  documented choice, an optional timeout can follow).
- Customer/admin notification on approve/reject relies on the existing payment-success events; no new SMS for «rejected».
- Import proposals: new attributes are created as TEXT; DATE attributes are rejected in bulk import; category proposals are limited to two levels.
- Scheduling of `expire_unpaid_orders` is documented only (no cron activated).
- The shared design layer is applied to the pages of this mission only; other pages migrate stepwise. Storefront customer login keeps its own control.
- Persian-only copy was reviewed by me only; a native-copy pass is advisable.
