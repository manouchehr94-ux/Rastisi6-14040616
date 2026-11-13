# Local verification — 2026-11-13

Base: `fa416ddbf1ff31652dd7accb9576097fbab0405a`. Branch: `codex/altcha-local-20261113`.

Environment: Linux x86_64, Python 3.12.14, Django 5.2.19, official altcha 2.3.0 / altcha-django 1.1.0, Redis 7.0.15, PostgreSQL 16 in disposable local containers. No customer data, real SMS, payment, external verification or production access.

## Results

| Run | Result | Runtime reported by Django |
|---|---|---|
| SQLite auth/security/config + real Redis | 553 tests, 552 passed; 1 existing PostgreSQL-only OTP race skipped on SQLite | 225.957 s |
| PostgreSQL CAPTCHA/security/auth infrastructure/cooldown/config + real Redis | 213 passed, **zero skipped**; includes that OTP race | 52.000 s |
| Isolated preview settings safety guards | 4 passed, zero skipped | 0.239 s |
| Dependency consistency | `pip check`: no broken requirements | — |
| Browser v2 | 30 measured real proofs, five actions, real Django contact POST and replay rejection | see JSON |
| Browser legacy | 10 measured real proofs, five actions, real Django contact POST and replay rejection | see JSON |

The 54 ALTCHA regressions cover five sensitive forms, invalid/missing/checkbox-only/test-mode/old-math responses, exact issued-parameter binding, signatures, strict decoding, expiration, cross-session/action rejection, invalid-proof consumption, valid/invalid concurrent consumers, Redis TTL, unreachable Redis, cache/counter errors without leaked credentials, recovery, CSRF, OTP/identifier/IP budgets, login and the whole OTP journey. Sixteen threads race over a single proof in repeated rounds; four independent Python interpreters also race using separate Redis connection pools. Only one valid consumer passes. The PostgreSQL test uses eight threads and confirms exactly one OTP send and seven cooldown responses.

Production tests include startup with CAPTCHA disabled, cache and trusted-proxy restrictions, development OTP rejection in production, secret/cookie settings, new work parameter bounds and runtime defence in depth. Preview tests reject inherited DSN/secret, non-local Redis and production mode before normal settings import. Historical arithmetic/digit-specific assertions were replaced with actual PoW/payload regressions. Existing login UI assertions now check the ALTCHA widget and on-click issuance; they were not removed. An initial command used a nonexistent rate-limit test label; the final run uses `test_rate_limit_service` and `test_rate_limit_redis`. Initial failures of old markup/issuance assertions were corrected with equivalent new behaviour coverage. No test/known-failure exclusion was added to make results green.

Targeted suites, not the entire repository test suite, were run. The SQLite conditional skip is not a failure and was explicitly covered by the PostgreSQL run.

## Speed (milliseconds, median / p95)

Chromium 143.0.7499.4 via Playwright; localhost Django development server and real Redis; ten samples per profile. Desktop 1440×1000, mobile 390×844 with touch/device scale factor 2. Routing blocks all non-local requests and disables the HTTP cache, so every sample reloads assets. No external requests were attempted and no page JavaScript errors occurred. Native checkbox dimensions (22px) and RTL are asserted to catch site-CSS interference. Checkmark animation waits are excluded from measured times.

| Profile | Navigation → checkbox visible | Click → PoW verified in widget |
|---|---:|---:|
| desktop | 217 / 381 | 115 / 154 |
| mobile | 177 / 249 | 104 / 120 |
| mobile-cdp-6x | 515 / 914 | 190 / 242 |

These are local observations, not internet/production SLA measurements. Page-ready timing includes Django navigation and module load. Click-to-verified includes local challenge fetch, worker startup and solve, but not a sensitive form POST. The real browser-produced payload was separately accepted by the Django contact form; replay was rejected.

For weak-device assessment, defaults use one worker, no artificial minimum-duration delay, and bounded 65–128 PBKDF2 derivations × 1000 rounds. CDP's 6× CPU profile is a UI/browser approximation: WebCrypto/native worker throttling differs by browser and it does **not** certify a physical low-end phone. Physical low-end Android, iOS/Safari and Windows/PowerShell execution remain owner/staging acceptance items. No accessibility arithmetic bypass is enabled; JavaScript/WebCrypto must be available. The test machine was shared with test processes; repeat on the owner's hardware before tuning work.

## Commands used

With an isolated venv containing `requirements.txt`, `RASTISI_TEST_REDIS_URL` pointing at the disposable Redis DB 15:

```text
python manage.py test apps.portal.tests.test_math_captcha shop_core.tests apps.portal.tests.test_owner_otp apps.portal.tests.test_owner_otp_resend_cooldown apps.portal.tests.test_owner_auth apps.portal.tests.test_unified_login apps.portal.tests.test_unified_login_hardening apps.portal.tests.test_three_identifier_login apps.portal.tests.test_password_reset_sms apps.portal.tests.test_auth_infra_integration apps.portal.tests.test_owner_login_audit apps.portal.tests.test_dev_otp apps.portal.tests.test_phase_sms1_real_otp_delivery apps.core.tests.test_rate_limit_service apps.core.tests.test_rate_limit_redis apps.core.tests.test_client_ip --noinput
```

PostgreSQL subset (same disposable Redis; `DATABASE_URL` to a local disposable test database):

```text
python manage.py test apps.portal.tests.test_math_captcha apps.portal.tests.test_owner_otp_resend_cooldown apps.portal.tests.test_auth_infra_integration shop_core.tests --noinput
python manage.py test tools.altcha_qa.test_settings --noinput
python -m pip check
```

Browser: `node tools/altcha_qa/browser-check.cjs`; legacy server used `RASTISI_PUBLIC_SITE_DESIGN=legacy`, a separate loopback port and the same isolated preview database. Browser evidence stores timings and blank/fabricated form screenshots only, never cookies, CSRF tokens or proof payloads.

CI/CD files, workflows and financial logic are unchanged. GitHub CI status must be reported separately after push; local results do not imply GitHub CI success. No merge or deployment is part of this task.
