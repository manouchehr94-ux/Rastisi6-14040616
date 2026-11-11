# Owner OTP concurrency: `InFlightDeliveryConcurrencyTests` (resolved)

Date: 2026-11-11. Scope: three PostgreSQL-only test failures. No payment, refund, subscription, cron or migration code touched.

## Result

**OTP CONCURRENCY: PASS.** No application or security defect. The three tests asserted behaviour that was deliberately replaced on 2026-10-09.

## The failures

All three (`test_a_failed_in_flight_resend_leaves_the_previous_code_continuously_usable`, and both subtests of
`test_a_newer_failed_request_does_not_destroy_an_older_successful_code`) failed on the same expectation: after a provider failure the test expected the
failed request's challenge row to be gone (`count() == 1`); the database held 2 rows. The class is skipped on SQLite (it needs PostgreSQL advisory locks and
real threads), which is why the change went unnoticed. They failed identically on the unmodified baseline.

## Cause

Commit `f8c9c3d8` ("Anchor the OTP resend cooldown at request acceptance and keep it on provider failure") changed `owner_otp_service.request_otp`: a failed delivery,
a provider exception or an activation error no longer deletes the accepted request's row. The row stays as a marker with `expires_at = PENDING_EXPIRES_AT`.
Reason: deleting it silently reset the 120 s cooldown and the per-phone budget, so a failing provider could be hammered. That commit rewrote the equivalent
assertions in the non-concurrent tests but not these three.

## Evidence that the implementation is correct (PostgreSQL 16.2, real threads)

A throwaway probe (not committed) failed the newer of two in-flight requests and inspected the database:

| Observation | Value |
|---|---|
| Request result | `delivery` error (controlled, no 500) |
| Rows for the phone | 2: the earlier delivered code (active) and the failed request's marker (pending) |
| Marker `attempt_count` | 0, also after a correct-value `check_otp` against it |
| `check_otp` with the failed code | `INVALID` against the older active code; the marker is never selected, never counts attempts |
| Older delivered code afterwards | still verifies (`True`) |
| Per-phone budget used | 2 (the failed request still counts) |
| Resend cooldown after the failure | still positive (not reset) |

So: no duplicate delivery (one provider call per accepted request), no unintended state transition (the marker never becomes active; an older
success is not destroyed), cooldown and budget are held rather than reset, and an undelivered code can never authenticate. The admission order is serialised by
`pg_advisory_xact_lock` on (purpose, phone); activation takes the same lock.

## Test changes (only `apps/portal/tests/test_owner_registration_hardening.py`)

* Count expectations changed from 1 to 2, with the second row asserted to be the never-verifiable marker.
* Added assertions (stricter than before): marker state is `pending` with 0 attempts; the correct value of the undelivered code is rejected; the older code still
  verifies; the failed request still spends budget (`_recent_request_count == 2`); the 120 s cooldown is still held.
* The wait that relied on the row being deleted now waits for the failing request to finish, and asserts both requests are still `pending` at that point.
* No test was skipped, disabled or removed.

## Mutation check (the updated tests would catch a real regression)

On PostgreSQL, with only the two failing-path tests selected:

* Mutation A, delete the marker on failed delivery (the old behaviour): 3 failures.
* Mutation B, let `check_otp` see the pending marker (undelivered code becomes verifiable): 3 failures.

Both mutations were reverted; the service file is unchanged in the commit.

## Test results (PostgreSQL 16.2)

| Run | Result |
|---|---|
| `InFlightDeliveryConcurrencyTests` before | 9 run, 3 failures |
| `InFlightDeliveryConcurrencyTests` after | 9 run, OK |
| `test_dev_otp`, `test_owner_login_audit`, `test_owner_otp`, `test_owner_otp_resend_cooldown`, `test_owner_registration_hardening`, `test_owner_signup_credentials`, `test_password_reset_sms`, `test_phase_sms1_real_otp_delivery` (`--parallel 4`) | 411 run, OK, 0 skipped |

## Remaining OTP production risk (not verified here)

* A real SMS provider's behaviour (delay, duplicate delivery, out-of-order delivery) is not tested; the code decides order by admission (`pk`), not by arrival.
* The per-IP budget and Turnstile need the real shared Redis cache; fail-closed behaviour is tested only against fakes.
* A provider that is down for a long time makes a user wait 120 s per attempt and consumes the per-phone budget (3 per 10 minutes). This is the intended policy.
