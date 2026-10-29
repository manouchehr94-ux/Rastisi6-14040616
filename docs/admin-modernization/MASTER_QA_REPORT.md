# RastiSi — Admin Panel Modernization & Customer Order Experience — QA report

Branch `feature/admin-panel-modernization-20261029` (QA only; nothing merged, deployed, published or migrated on Production; no new migration in this pass).
QA server: port 8008, DB copy `db.sqlite3`; 8006/8007 untouched. QA notifications: `EMAIL_BACKEND=console`, every store's SMS backend = `console` (no real send).

## 1. Request status
| # | Request | Status | Where |
|---|---|---|---|
| §3 P0 | Customer order tracker (two independent tracks, real data only) | Done | `orders/services/order_tracker.py`, `customers/partials/order_tracker.html`, `order_tracker.css` |
| §3 | Rejection box (escaped reason) + «اصلاح و ثبت مجدد»; hidden after resubmit/approval | Done | same + view `account_order_detail` |
| §4 P0 | Card-transfer page: theme tokens, 4-4-4-4 LTR-isolated number, copy + fallback, states, a11y | Done | `orders/card_transfer.html`, `card_transfer.css` |
| §5 | C2C flow hardened/tested (submit→reject→resubmit→approve→double approve→after approval) | Done (existing engine already idempotent; tests added) | `test_order_tracker.CardTransferJourneyTests` |
| §6 | Shipping setup accordion, real `is_active` switch, active-first display, open-after-save | Done | `shipping_setup.html`, view `shipping_method_toggle` |
| §7 | Payment gateways accordion, per-field errors, server-confirmed switch | Done | `settings_gateway_card.html`, views save/toggle |
| §8 | Integrations accordion; connected == enabled (one real flag) | Done; toggle = disconnect / reconnect-with-saved-data (existing `connect` service) | `settings_integrations.html` |
| §9 | Finance page: tax summary last; tax editing only on tax page | Done (tax logic untouched, existing tax tests green) | `settings_finance.html` |
| §10 | Final-import button + confirmation modal with real counts; product name main column; wording; samples | Done except variant sample workbook | `import_detail.html`, `import_service.row_display_names` |
| §11 | Password eye: short accessible names, storefront customer auth covered | Done | `password_toggle.*`, `templates/base.html` |
| §12 | Unpaid-orders copy in plain Persian; SMS wiring verified | Done | `settings_unpaid_orders.html`, `test_order_expiry` |
| §13 | Limited polish | Partial: dialog centering bug fixed (affected the previous delivery too), shared au-acc/au-toggle; **not done**: settings search, extra breadcrumbs |
| §14 | Vision Studio untouched | Yes |

## 2. Audit (what was already right vs changed)
Already right: card-to-card engine (idempotent approve/reject, unique constraints, audit), unpaid-order expiry rules (COD / card-to-card never expire), import all-or-nothing + CAS execution, tax logic, shipping services.
Changed: UI and presentation, plus: `PaymentGatewayAdapter.field_errors` (per-field validation, `validate_credentials` for card-to-card now derives from it), gateway toggle auto-creates the config row (COD can be switched on first time), `integration_service.reconnect_with_saved`, `import_service.row_display_names` (+ `product_name` stored in the row summary JSON — no schema change).

## 3. Needs-new-backend / honest limits
- Integrations have a single real flag (`is_active`). «Connected» and «enabled» are the same thing; a separate "connected but disabled" state does not exist in the backend. The test button validates the stored identifiers' **format** only — no external call (existing design).
- Variant sample workbook: not generated (QA store has no product with options); variant import is covered by `test_import_variant`. The template can be downloaded from the UI.
- Pickup orders traverse the real `shipped` status; the tracker shows it as «آماده‌ی دریافت حضوری» (no invented step).
- Second-store theme check: the other QA stores' storefronts return 404 (not published), so a second palette and a dark palette were **emulated** by overriding the token variables in the browser; the first store was verified for real.

## 4. Changed files (main)
`apps/orders/services/order_tracker.py` (new), `apps/orders/gateways/{base,card_to_card}.py`, `apps/orders/templates/orders/card_transfer.html`, `apps/orders/static/css/card_transfer.css`, `apps/customers/{views.py,templates/customers/order_detail.html,partials/order_tracker.html,static/css/order_tracker.css}`, `apps/dashboard/{views.py,urls.py,services/import_service.py,services/import_xlsx.py,services/settings_admin_service.py}`, dashboard templates (`shipping_setup`, `import_detail`, `products`, partials `settings_gateway_card/payment_config/integrations/finance/unpaid_orders`), `admin_ui.{css,js}`, `apps/stores/services/integration_service.py`, `core/static/core/password_toggle.*`, `templates/base.html`.

## 5. Component architecture
`au-acc` (accordion: trigger button with `aria-expanded/aria-controls`, hidden panel, closed by default, opens only on error / user action / after save), `au-toggle` (`role=switch`, `aria-checked`, green/grey + word, changes only after the server re-rendered the row), `au-switch` (form checkbox), `au-modal` (centered dialog), `data-au-confirm`. Storefront pages use theme tokens only.

## 6. Tests
- New: order tracker 15, gateway accordion 7, integration accordion 6, shipping accordion 6, import modernization 9, expiry copy/wiring 3, finance order 1, password toggle 2 (+ real Chromium geometry run: 11 pass).
- Intentionally changed existing tests (copy/column positions): gateway save/toggle now return 200 HTML (was 204), expiry settings copy, import detail strings, error-report columns (name column inserted), button label «ورود گروهی کالاها», password-toggle accessible names, `StrictImportViewTests` success copy.
- Full suite (`manage.py test apps --parallel 6`) at the time of that report: 11 594 tests, 35 failures + 4 errors = 39 ids, none caused by this branch. Exact ids and the comparison with the Vision baseline (29 baseline ids still failing — they also fail on the untouched base `6d6258d3`; 3 baseline ids now pass; 8 environmental ids that fail alone on HEAD and on base; 2 ids that fail only in the parallel run and pass alone) are in `TEST_RECONCILIATION_20261029.md` (for the later HEAD: 34 FAIL + 5 ERROR = the same 39 ids). One failure introduced by this pass (`StrictImportViewTests.test_clean_preview_shows_success_copy_and_confirmation_warning`, old copy) was fixed and re-run green. The earlier wording "31 of the 32 baseline ids" in the conversation was wrong: it is 29 still failing + 3 passing.

## 7. Real-browser acceptance (Chromium, port 8008)
Order page (paid+processing, rejected, review, awaiting, shipped, canceled) at 1440 / 390; card-transfer page at 1100 / 390 (number order verified geometrically: first group left of last group; copy button gives the success message); gateways closed/open/error; integrations; shipping; finance; unpaid; import preview → approve all → final modal. No unexpected JS errors; only a pre-existing demo-media 404 (`media-assets/mobile_*.png`).

## 8. Risks
Existing JS caches: asset query strings were bumped (`?v=20261029-3`). Card-to-card orders waiting for review keep their stock until an admin decides (documented earlier). Persian copy was reviewed by me only.

## 9. Before any deployment
Run the full suite on the target, review the changed-test list above, no migration needed for this pass, restart app servers (template cache), do not push to legacy `origin`.
