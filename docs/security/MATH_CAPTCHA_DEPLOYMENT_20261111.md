# Math CAPTCHA replaces Cloudflare Turnstile: deployment guide

Branch `kiro/math-captcha-20261111`, built on `6a6897b7`. Not deployed. Not merged. DNS, SSL and every other Cloudflare service are untouched.

## What changed

The sign-in (password and SMS code), sign-up, password-reset and contact forms no longer load `challenges.cloudflare.com` and no longer call Cloudflare
Siteverify. Each form shows a question such as «۳۵ + ۱۴ = ؟». See `apps/portal/services/captcha_service.py` for the exact rules:

* created on the server; the page carries only the two operands and a random token, never the sum;
* stored in the shared rate-limit Redis as an HMAC digest, bound to the visitor's session and to the form, valid for `RASTISI_CAPTCHA_TTL_SECONDS` (default 300);
* consumed by the first submission, right or wrong (atomic), so a solved question cannot be replayed;
* Persian, Arabic-Indic and ASCII digits are accepted;
* Redis down: the forms refuse with the standard "temporarily unavailable" message and nothing protected happens (fail closed);
* CSRF, per-IP login/OTP/reset/contact limits, per-phone OTP budget, per-identifier login throttle and the OTP flow are unchanged.

No database change. No migration. No new Python dependency.

## Environment

| Variable | Action |
|---|---|
| `RASTISI_CAPTCHA_ENABLED` | Optional. Defaults to true when `DJANGO_DEBUG=False`. Setting it false with `DJANGO_DEBUG=False` stops startup. |
| `RASTISI_CAPTCHA_TTL_SECONDS` | Optional, 30 to 900, default 300. |
| `TURNSTILE_*` | No longer read. **Leave them in the env file until the rollback window has closed** (the previous release refuses to start without them). Remove afterwards. |
| `RASTISI_RATE_LIMIT_CACHE_URL` | Already required. The CAPTCHA now also depends on this Redis. |
| `DJANGO_TRUSTED_PROXY_CIDRS` | Must list your real proxy hops. If it is wrong, every visitor shares one IP bucket. Check it before release (step 3). |

## Deployment (operator, staging first)

1. Back up as usual. Note the current release directory and commit.
2. Check out `kiro/math-captcha-20261111` into a **new** release directory with the existing virtualenv's requirements (`requirements.txt` is unchanged).
3. With the production environment loaded: `manage.py check --deploy` must show no errors. Confirm `DJANGO_TRUSTED_PROXY_CIDRS` is set for your proxy chain.
4. `manage.py verify_rate_limit_cache` must pass (Redis reachable).
5. No `migrate` is needed (`makemigrations --check` reports no changes). Do not run one for this change.
6. Switch the application servers to the new release and restart them. Cron jobs need no change.
7. Smoke test on the real host, from a phone and a desktop browser:
   * `/login/` (both tabs), `/register/`, `/reset-password/`, `/contact/` each show a question; the page source has no `cloudflare`/`turnstile`;
   * a wrong answer shows the Persian error and a new question; the right answer proceeds; the SMS code arrives and `/verify/` works;
   * reloading a submitted form (resubmitting the same token) is refused.
8. Watch the application log for a few minutes. Messages containing "CAPTCHA question could not be issued" or "CAPTCHA store failure" mean Redis problems.

## Rollback

1. Point the application servers back to the previous release directory and restart. Nothing else has changed (no schema, no data).
2. This works only while `TURNSTILE_*` are still in the env file, which is why they stay until the window closes.
3. Questions already issued sit in Redis under the prefix `captcha:v1:` and expire by themselves. No cleanup is needed.

## Known limits

* A math question stops naive scripts, not a bot that parses the page. The rate limits after it remain the real protection against SMS pumping and password guessing.
* The check depends on Redis. If Redis is down, nobody can sign in (this is the same dependence the rate limits already had).
* The legal/privacy drafts under `docs/legal` were adjusted to say the third-party widget is gone; a lawyer should confirm the wording before publication.
