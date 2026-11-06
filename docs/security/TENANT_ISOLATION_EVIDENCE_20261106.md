# Tenant-isolation evidence — the three historical external-audit scenarios (FV3, 2026-11-06)

Companion to `TENANT_ISOLATION_20261106.md`. Local branch only; nothing pushed. Synthetic fixtures on PostgreSQL 16; no production data, no real gateway.

The audit harness's own test ids are not in this repository, so each scenario was **rebuilt from its description** and recorded by
`apps/orders/tests/test_strix_scenario_evidence.py` (a recording variant of `test_tenant_isolation_regression.py`; same contracts). Raw machine-readable evidence:
`docs/security/evidence/strix_evidence_postgresql_{fixed,prefix,mutation_unscoped_lookup}.json` (regenerate with `STRIX_EVIDENCE_DIR=<dir> STRIX_LABEL=<label>`).

## How "the tests reproduce the historical scenario" was demonstrated

| Run | Code under test | Purpose |
|---|---|---|
| `fixed` | integrated branch (refund key per store) | the contract holds |
| `prefix` | integrated branch with ONLY the refund-key fix reverted (`orders/models.py`, `refund_service.py` at `8ad4b687`, migration `0022` removed) | the test must FAIL on the historical code |
| `mutation_unscoped_lookup` | `prefix` + the store filter removed from `_get_own_order` | proves the HTTP test could detect a cross-store disclosure if one existed |

## Scenario results

### 1. `http_payment_result_other_store_same_user` — NOT reproducible in any code state tried
Fixture: ONE global Customer/User owns order `TI-A-1` (Store A, grand total 7,654,321) and `TI-B-1` (Store B); each store has its own verified host.

| Request (all as the shared user unless stated) | HTTP | Order code / amount / name in body |
|---|---|---|
| GET `payment-result` TI-A-1 on **Store B host** | **404** (generic «صفحه پیدا نشد») | none |
| GET `payment-start` TI-A-1 on Store B host | **404** | none |
| GET `payment-initiate` TI-A-1 on Store B host | **404** | none |
| other user, Store A host | 404 | none |
| anonymous, Store A host | 404 (no login redirect → no existence oracle) | none |
| *positive control* owner on own host | 200 | order shown (expected) |

Side effects: Order rows (status, payment status, totals) identical before/after; session keys unchanged by the foreign request.
Result is identical on `fixed` and `prefix` (the finding never existed here). **Mutation check:** with the store filter removed, the same request returns **200 and the body contains the order code and amount** → the test fails (`200 != 404`). So the test is sensitive to exactly this class of bug.

### 2. `refund_idempotency_cross_tenant` — REPRODUCED on the historical code, fixed
Fixture: Store A and Store B each have a paid order; staff user; client key `strix-shared-key-0001` used by A, then by B.

| | `prefix` (historical) | `fixed` |
|---|---|---|
| DB constraint | `uniq_refund_idempotency_key_when_set (idempotency_key)` global | `uniq_refund_idempotency_key_per_store (store_id, idempotency_key)` |
| Store B reuses A's key | **`RefundError`** «کلید یکتای درخواست استرداد با این سفارش مطابقت ندارد» — collision + one-bit existence oracle | independent refund (pk 2, store 3) |
| Refund rows A / B | 1 / **0** (B blocked) | 1 / 1 |
| Store A's refund after B's attempt | unchanged | unchanged |
| Same-store retry / same key different request | idempotent / refused | idempotent / refused |

The recording test **fails on `prefix`** (`unexpectedly None … cross-tenant collision / existence oracle`) and passes on `fixed`.
What the historical code did NOT do: it never returned or modified Store A's refund and the message did not describe it — the weakness was the global namespace (collision/oracle), as rated low/medium in the earlier report.

### 3. PostgreSQL concurrency (real connections)
Workers released together by a barrier; each worker's `pg_backend_pid()` recorded (distinct pids prove separate connections/transactions).

| Race | `prefix` | `fixed` |
|---|---|---|
| 2 stores, same key, simultaneously | one worker gets `refund_error`, the other `ok`; only ONE store ends up with a refund (which one depends on timing) — test FAILS | both `ok`, 2 distinct backends, 1 refund per store |
| 1 store × 3, same key | unchanged: exactly 1 refund, all three get the same one (not a cross-tenant property) | exactly 1 refund, all three workers return the same refund, 3 distinct backends |

## What this does and does not prove
* Proves, on these fixtures and this code: the three scenarios behave as tabulated; the refund test reproduces the historical defect; the HTTP test catches an unscoped lookup.
* Does **not** prove: there is no other cross-tenant path; behaviour with other host/proxy setups or custom domains beyond those fixtured; behaviour on production data; real gateway callbacks.
* The original harness ids/payloads were unavailable; the scenarios are reconstructions from their descriptions.
* Concurrency evidence is a few runs of a barrier-synchronised race, not an exhaustive interleaving proof (the DB unique constraint + the `IntegrityError` retry path is what actually guarantees the outcome).
