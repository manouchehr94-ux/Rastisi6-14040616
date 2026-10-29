# Customer account — store isolation, UI and account security (local QA, not pushed)

Base: `171323461cf645ac5049ef98f0f6358ccebb2693`. No migration. QA ran on an isolated copy of the QA DB (`/home/user/ACCOUNT_QA_DATA_20261029`, port 8009); the earlier QA environment (8008 / `db.sqlite3`), `main` and Vision Studio were not touched.

## P0 — multi-store isolation
`Customer` is global by design (one identity, many stores). Before: the account page listed **every** store's orders and showed global `orders_count/total_spent`; `/account/orders/<code>/` and `/checkout/order/<code>/result|start|initiate|callback|card-transfer` opened another store's order (HTTP 200) for the same customer.
After (`apps/orders/views.py::_get_own_order`, `apps/customers/views.py`, `services/account_service.py`):
- every order lookup filters by customer **and** the current store (unknown host ⇒ 404); cross-store code ⇒ 404 on all of: detail, result, start, initiate, simulated callback, card-transfer GET/POST — nothing is created or changed;
- the order list and the counters are computed per store (paid, non-cancelled total; never the global counters); the level shows «ویژه» only from the store's own `CustomerProfile` (internal statuses such as «تحتِ نظر» are never shown);
- side effects fixed: cart badge counts only the current store's items; wishlist hearts only the store's products.
Tests: `apps/customers/tests/test_account_store_isolation.py` (9 tests, two stores + one shared customer). Run against the pre-fix code they fail 8/9 (6 failures + 2 errors).

### Finding that needs a decision (not changed)
`Cart` has no store field: a shared customer has ONE cart for all stores, so store B's cart lines can appear on store A's cart page and block checkout (order creation already refuses foreign items, so no cross-store order is possible). A proper fix is `Cart.store` (migration + data backfill + store-scoped `get_cart`). I did not add a migration without your approval; only the badge count was scoped.
Personal data: `Customer` (name/phone/email/city) and `Address` are person-level by design and shared across stores.

## P1 — account UI
Cause: `account.html` reused the product page's `pdp-tabs` component (`product_detail.css`), so every pane stayed visible and the tab strip collapsed (measured: 4 of 4 panes visible). Now: its own `acct-*` component in `account.css` (token-only colours/radius/button radius), `role=tablist/tab/tabpanel`, `aria-selected/controls/labelledby`, roving tabindex, arrow keys, URL hash (`#security`), server-rendered `hidden` panels (no flash). Panels: پروفایل، سفارش‌های من، آدرس‌ها، کدهای تخفیف من، امنیت حساب + link علاقه‌مندی‌ها. htmx saves/errors stay in their panel. Forms: 2 columns on desktop, 1 on mobile, 46 px fields; 390/768/1440 px: no horizontal scroll, no tab overlap. `product_detail.css` is no longer loaded on this page and was not edited.

## P1 — account security
New tab «امنیت حساب»: (1) change password with the current password; (2) for accounts created at checkout (password never seen by the customer) — set a new password after an SMS code to the account's own phone (existing `otp_service`: expiry, attempt limit, per-phone/IP limits; no phone input). Django password validators; confirmation + «must differ»; fixed-window rate limit on guesses; CSRF + login required (403); other sessions are closed, the current one stays; notification via the existing `account.sensitive_changed` event (email only, QA = console); passwords never echoed/logged. Tests: `test_account_security.py` (18) + `test_account_ui_structure.py` (4); the SMS function is mocked so no gateway is touched.
QA note: the platform SMS provider in QA is "console, real delivery not configured", so the code step shows that message; for the browser run only, the isolated 8009 server was started with `RASTISI_OWNER_SMS_ALLOW_CONSOLE_OTP=1` (console-only, refused when DEBUG is off) and the code hash in the isolated DB copy was replaced with a known one to stand in for the phone. Nothing was sent.

## Verification
Unit: new 31 tests + existing account/order/card-transfer/password-toggle tests green. Browser (Chromium 390/768/1440): tab switch (one panel visible each time), hash deep link, keyboard arrows, profile save, address validation, password error + rate limit, SMS-code flow, store B shows only B's orders/stats, eye button inside its gutter, dark palette emulated. Full suite: 11 625 tests, 34 failures + 5 errors = 39, all pre-existing/environmental (see report in the conversation); no failure comes from these changes.
