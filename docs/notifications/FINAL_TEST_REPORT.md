# Final automated test report — notifications email engine

Branch `kiro/notifications-email-engine-20261104`, commit `eb7834ad`. Integrated review branch `kiro/notifications-integrated-20261104`,
commit `643c9efc` (PR #38, draft, base = `integration/payment-engine-unified-20261104`).

Runner: `DJANGO_SETTINGS_MODULE=shop_core.settings python manage.py test <labels> --parallel <n>` on CPython 3.11, Django 5.2.19,
SQLite (the local/test default). **Fake e-mail provider throughout — no network, no AWS, no real e-mail, no real DNS.** `rm -f db.sqlite3`
before each run. "Baseline" = the same labels on a pristine `main` checkout at `7d311556` (`/projects/sandbox/_qa/src_main` in my environment).

## 1. Targeted groups (all green)
| group | command (labels) | result |
|---|---|---|
| Notifications (all) | `apps.notifications` | **309 passed** |
| SMS compatibility | `apps.sms` | **163 passed, 1 skipped** (the skip is `test_gateway_concurrency`, `@skipUnless(connection.vendor=='postgresql')` — needs Postgres row locks; cannot run on SQLite) |
| Sender identity / DNS / expiry / QA tooling | `apps.notifications.tests.test_sender_identity test_dns_provisioning test_expiry test_store_sms_overrides test_qa_tooling` + `apps.stores.tests.test_domain_verification_service` | **155 passed** |
| Template mgmt / RBAC / parity | `apps.dashboard.tests.test_notification_admin apps.portal.tests.test_platform_notification_admin apps.portal.tests.test_platform_team_login apps.notifications.tests.test_sms_email_parity` | **74 passed** |
| SNS / SES adapter / HTML sanitizer | `apps.notifications.tests.test_email_security test_ses_adapter test_ses_botocore_model test_html_sanitizer test_email_transport` | **94 passed** |

Notable sub-suites inside the above (counts verified individually in earlier runs): `test_email_security` 48 (SNS signature v1/v2, tampering,
foreign/unlisted topic, cert-URL host/scheme/port tricks never fetched, idempotent duplicate delivery, tenant attribution only from our own
outbox); `test_ses_botocore_model` 8 and `test_ses_adapter` 12 (real botocore `sesv2` service model + `Stubber`, request/response shapes
only); `test_expiry` 34; `test_sms_email_parity` 15; `test_qa_tooling` 14 (QA-mode guards, idempotent seed, cross-process fake state,
simulated provider events, SPF/DMARC advisory never-gating, SES smoke double opt-in, single-migration-leaf, repo secret-scan).

## 2. New tests added in the finalization pass
| file | what it locks down |
|---|---|
| `apps/notifications/tests/test_qa_tooling.py` (14) | QA commands refuse to run unless DEBUG + `RASTISI_QA_MODE=1` + `fake` provider; idempotent 4-tenant seed with the right sender states; fake-provider state shared across processes via the state file + mailbox dump; bounce → suppression + idempotent replay; domain verdict flows to the sender; SPF/DMARC advisory ok/missing/unknown/not_checked and **never** changes an ACTIVE sender; `ses_smoke_test` refuses non-ses provider, requires `--i-understand-this-sends-real-email`, `--check-only` fails on an unverified identity, leaks no secret; exactly one notifications migration leaf; no AWS key / private key committed under `apps/notifications`, `docs/notifications`, `tools/windows-qa`, `deploy`. |
| `apps/portal/tests/test_platform_team_login.py` (4) | a platform **team** member (staff + a granted notification permission, no store, no OwnerProfile) can sign in to the platform-admin host and lands on the catalog; wrong password / unknown / staff-without-permission / non-staff / inactive all refused; owner-portal eligibility is **not** widened; permission check is live (revoking closes the door). |
| `apps/dashboard/tests/test_notification_admin.py::HistoryProviderIdTests` (2) | store history shows the provider message id + delivery state; another store's provider ids are never listed. |

Both the login fix and the history columns were defects found by the real-HTTP acceptance walk-through (§4) that the earlier
`force_login`-based tests had missed.

## 3. Broad regression (3 chunks) — failures classified against the `main` baseline
| chunk | command | result | assessment |
|---|---|---|---|
| 1 | `apps.notifications apps.sms apps.dashboard apps.portal apps.core apps.engagement apps.customers --parallel 4` | 4109 tests, **5 failures + 1 error** (58 skipped) | **Not introduced by this work.** The 5 failures (`test_onboarding_ready_template` ×4, `test_onboarding_template_fidelity` ×1) reproduce **identically on pristine `main`** (18-test subset: 5 failed on both `main` and this branch, run serially). The 1 error (`test_public_site_v2.…test_a_new_ready_template_appears_without_any_code_change`) is a **parallel-isolation flake**: it errors under `--parallel` on `main`, `integ_base` and this branch alike, and **passes** when the file is run alone (`--parallel 1` → 40 passed). |
| 2 | `apps.orders apps.cart apps.catalog apps.content apps.blog apps.billing apps.subscriptions --parallel 4` | 2452 tests, **OK** (17 skipped) | Clean. Confirms the financial/commerce apps are unaffected. |
| 3 | `apps.stores apps.storefront_builder shop_core --parallel 4` | 4807 tests, **27 failures + 2 errors** (49 skipped) | **Not introduced by this work.** All 29 are storefront-builder / rasti-mode demo-visual contract tests; re-running the exact 29 labels on pristine `main` gives the **same 27 failures + 2 errors**. My diff touches no file under `apps/storefront_builder` or `apps/stores` demo visuals. |

Baseline method for every failure above: I re-ran the exact failing labels on the pristine `main` checkout and compared. No failure in
any chunk is unique to this branch.

## 4. Real-HTTP acceptance walk-through (scenarios A–N)
`tools/windows-qa/qa_http_acceptance.py`, driven by `Invoke-RastiSiAcceptanceCheck.ps1`, against a **running** QA server + worker (real
host-based routing, cookies, CSRF, central-login handoff; fake provider). Executed under PowerShell 7.4.6 on Linux in my environment:
**`SUMMARY: 55 passed, 0 failed, 3 manual-only`**. The 3 manual-only rows are, by design, the things a computer cannot judge: the
storefront browser click-through (L), the visual RTL review at desktop+mobile widths (M), and time-based expiry (N — covered instead by the
34 `test_expiry` unit tests). See `docs/notifications/ACCEPTANCE_MATRIX.md` for the per-check table.

> This was **not** run on Windows PowerShell 5.1 and **not** on a Windows machine. The scripts parse with 0 errors under both the PS5.1
> (`Desktop`) grammar and PS7, and every code path above ran under PS7 on Linux, but real Windows behaviour is unverified until you run it.

## 5. Migration integration
`docs/notifications/MIGRATION_INTEGRATION.md` (decision + rationale) and, on the integrated branch, `rehearse_states.sh` +
`verify_persistent_states.py`: three database histories (`payment_db`, `pr37_db`, `fresh_db`) all upgrade to the integrated head with data
and schema intact, a single leaf and no drift. Combined suite on the integrated tree: no failure beyond the pre-existing parallel flake in §3.

## 6. What is explicitly NOT covered by any automated test here
- Real deliverability: no message was sent through Amazon SES; no DNS zone was queried; no SNS push was received from AWS. `boto3` paths are
  exercised only against the botocore service model with `Stubber`. See `docs/notifications/AWS_ACTIVATION_RUNBOOK.md` for the live steps and
  their status labels.
- Windows / PowerShell 5.1 execution (see §4 note).
- The Postgres-only SMS row-lock concurrency test (skipped on SQLite).
