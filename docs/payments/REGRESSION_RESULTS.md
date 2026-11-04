> **OUTDATED (2026-11-04):** this document describes the payment-engine work before its integration into the main development line (canonical card-transfer workflow, settlement-uncertainty handling, reconciled migrations). The current record is `docs/payments/INTEGRATION_UNIFIED_20261104.md`.

# Regression Results — Payment Engine Mission (FEAT-006 close-out)

All commands were run inside the isolated worktree
`/projects/sandbox/rastisi-payment-kiro-20261103` on branch
`feature/kiro-payment-engine-20261103`, after `. .venv/bin/activate`. The test
database is **SQLite** (the only database available in this sandbox). All
provider HTTP is mocked; no real provider endpoint was contacted and no
real-money transaction was performed.

## Exact commands and results (FEAT-006 "after")

| Command | Ran | Passed | Skipped | Failed | Result |
|---------|-----|--------|---------|--------|--------|
| `python manage.py test apps.orders` | 713 | 697 | 16 | 0 | OK |
| `python manage.py test apps.billing` | 147 | 146 | 1 | 0 | OK |
| `python manage.py test apps.dashboard` | 1840 | 1833 | 7 | 0 | OK |
| `python manage.py makemigrations --check --dry-run` | — | — | — | — | `No changes detected` |

New FEAT-006 test modules (also included in the `apps.orders` run above), run
explicitly:

```
python manage.py test \
  apps.orders.tests.test_payment_security \
  apps.orders.tests.test_payment_currency \
  apps.orders.tests.test_payment_migration_compat
```

Result: **43 tests, 43 passed, 0 skipped, 0 failed (OK).**

Breakdown of the new modules:
- `test_payment_security.py` — credential encryption + secret leakage,
  cross-tenant isolation, forged/replayed callbacks, duplicate finalization,
  amount tampering, expired/final attempts, unauthorized/blocked config, unsafe
  redirects, concurrency logic (SQLite-only caveat marked inline).
- `test_payment_currency.py` — Toman→Rial (×10) conversion exactly once, no
  float, no 10x/0.1x error, recorded submitted amount (Zibal + Zarinpal).
- `test_payment_migration_compat.py` — migrations 0020/0021/0022 are additive,
  legacy {zibal, cod} config still loads/behaves, fresh-SQLite migrate, and
  `makemigrations --check` is clean.

## Baseline vs after comparison

The mission baseline recorded in `context.json` was captured on the base SHA
before any payment-engine code change:

| Suite | Baseline (passed / skipped) | After FEAT-006 (passed / skipped) | Delta |
|-------|------------------------------|-----------------------------------|-------|
| `apps.orders` | 527 / 16 | 697 / 16 | +170 passed (adapters + services + FEAT-006 tests), skips unchanged |
| `apps.billing` | 147 / 1 | 146 / 1 | untouched subsystem; `Ran 147` includes 1 skip (146 pass + 1 skip) |
| `apps.dashboard` | not in original baseline | 1833 / 7 | finance-admin additions kept green |

Notes on the counts:
- The orchestrator briefing reported a post-FEAT-005 figure of
  `apps.orders = 654 passed / 16 skipped`. FEAT-006 adds 43 new tests, giving
  `697 passed / 16 skipped` (654 + 43 = 697). The `context.json` baseline of
  `527 / 16` is the pre-mission figure; the growth is from the adapter/service
  work across FEAT-002..005 plus the FEAT-006 test pass.
- `apps.billing` is a SEPARATE SaaS-billing subsystem and was intentionally not
  modified; it stays green (`Ran 147`, 1 skipped). It is reported in the table
  as `146 passed / 1 skipped` to make the skip explicit.
- No regressions were introduced. No test that passed on the baseline fails
  after FEAT-006.

## Concurrency status — NOT verified on SQLite

Postgres is **NOT installed** in this sandbox (no `psql` / `pg_ctl` / `postgres`
binaries; neither `psycopg2` nor `psycopg` importable). The default and only
available test database is SQLite.

The payment orchestrator relies on `SELECT ... FOR UPDATE` **row-level locking**
(order row first, then attempt row) to serialize concurrent callbacks and a
cancel racing a payment. SQLite does **NOT** implement row-level locking, so:

- The concurrency tests
  (`test_payment_security.py::ConcurrentVerificationLogicTests` and
  `test_payment_concurrency.py`) verify the **idempotency LOGIC only** — the
  conditional status transition and the already-`SUCCEEDED` guard. Each
  SQLite-only assertion is marked `NOT VERIFIED ON SQLITE` inline.
- Real row-level-locking concurrency is therefore **NOT verified** in this
  environment. It must be validated against Postgres before being relied upon
  in production.

How to run against Postgres (when available): provision a Postgres instance,
set `DATABASE_URL=postgres://...` (the settings require a `postgres://` /
`postgresql://` scheme), run migrations, then re-run the concurrency modules
with real parallel callbacks (threads/processes) to exercise the row locks.

## Fresh-database migrate

- Every test run builds a fresh SQLite test database and applies **all**
  migrations (through 0022) cleanly — this is the fresh-DB migrate proof
  exercised on each suite above.
- `python manage.py migrate orders` additionally applied `0021` and `0022`
  cleanly on the dev SQLite database.

## Browser QA status — environment-limited

Attempted via the Playwright MCP against the finance settings page and checkout
at 1440 / 768 / 390 / 320 px.

- A Django dev server was started on the host (`127.0.0.1:8099`) and served
  `HTTP 200` to a host-side `curl`.
- The Playwright browser backend runs in a separate, isolated network namespace
  and could **not** reach the host-bound server: both
  `http://127.0.0.1:8099/` and `http://localhost:8099/` returned
  `net::ERR_CONNECTION_REFUSED` from the browser.
- Therefore **browser QA is environment-limited** and was NOT performed; no
  browser runs are fabricated.

Static/template checks performed instead (documented honestly as a substitute,
not a replacement for real responsive QA):
- `apps/dashboard/templates/dashboard/partials/settings_payment_config.html`
  and `settings_finance.html` — use responsive utility classes
  (`grid`/`flex`/`sm:`/`md:`/`lg:`) and render **zero** occurrences of
  `encrypted_credentials` (no secret leakage into the finance UI).
- `apps/orders/templates/orders/partials/checkout_body.html` — uses responsive
  layout utilities.
- The full `apps.dashboard` suite (1833 passed) exercises the finance admin
  views/permission gating server-side.

Recommended follow-up when a reachable browser target is available: run the
finance settings page and checkout at 1440/768/390/320 px, confirm the gateway
cards, readiness badges, credential forms, and the checkout payment-method list
render correctly in RTL and that no secret is ever shown.
