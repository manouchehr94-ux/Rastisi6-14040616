# Production Configuration Foundation

**Status:** Foundation only. This document covers making `shop_core.settings`
safely configurable for a real deployment — it does **not** mean the
platform is launch-ready. Real payment processing (Zibal), Enamad
readiness, the merchant/dashboard Store-boundary hardening, checkout
idempotency, and the actual server/hosting setup are separate, later pieces
of work. See `docs/00_PROJECT_MASTER_REFERENCE.md` for the full launch
picture and what remains.

This is written provider-neutral: no specific host (VPS vs. managed
platform) has been chosen yet. Adjust the process-manager/reverse-proxy
specifics to whatever you end up using.

## 1. Required environment variables

All variables are read by `shop_core/settings.py` via the helpers in
`shop_core/env_config.py`. None are required to run the app locally or to
run the test suite — every one has a default that reproduces the prior
hardcoded development behavior. See `.env.example` for the full annotated
list with placeholder values. Summary:

| Variable | Required in production? | Default (dev) | Notes |
|---|---|---|---|
| `DJANGO_SECRET_KEY` | Yes | dev-only literal key | Rejected if left as the dev key when `DJANGO_DEBUG=False` |
| `DJANGO_DEBUG` | Yes (`False`) | `True` | |
| `DJANGO_ALLOWED_HOSTS` | Yes | `[]` | Comma-separated, no wildcards |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Yes, once behind a real domain | `[]` | Comma-separated, full origin (`https://host`) |
| `DJANGO_SECURE_SSL_REDIRECT` | Recommended once HTTPS works | `False` | |
| `DJANGO_SESSION_COOKIE_SECURE` | Must be true | `True` when `DJANGO_DEBUG=False`, else `False` | `false` with `DJANGO_DEBUG=False` is a startup error (§7) |
| `DJANGO_CSRF_COOKIE_SECURE` | Must be true | `True` when `DJANGO_DEBUG=False`, else `False` | same |
| `RASTISI_RATE_LIMIT_CACHE_URL` | **Yes** — startup fails without it | unset (local LocMem; dev only) | `redis://` / `rediss://` URL of a Redis shared by all workers — §6.1 |
| `DJANGO_TRUSTED_PROXY_CIDRS` | Yes behind any proxy/CDN | empty (forwarded headers ignored) | Comma-separated IPv4/IPv6 CIDRs (+ optional `unix`) of your reverse proxies — §6.2 |
| `TURNSTILE_ENABLED` | **Yes** — must be true | `True` when `DJANGO_DEBUG=False`, else `False` | `false` with `DJANGO_DEBUG=False` is a startup error |
| `TURNSTILE_SITE_KEY` / `TURNSTILE_SECRET_KEY` | **Yes** | empty | Required in production |
| `TURNSTILE_EXPECTED_HOSTNAMES` | **Yes** | empty | Bare hostnames the widget runs on; verified against Siteverify |
| `TURNSTILE_VERIFY_TIMEOUT_SECONDS` | Optional | `5` | |
| `RASTISI_DEV_OTP_CODE` | **Must be unset/empty** | empty (off) | **DEVELOPMENT ONLY** local-QA OTP; non-empty with `DJANGO_DEBUG=False` is a startup error and `rastisi.E006` — see §6.3 |
| `DJANGO_SECURE_HSTS_SECONDS` | Staged — see §7 | `0` | |
| `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS` | Staged | `False` | |
| `DJANGO_SECURE_HSTS_PRELOAD` | Staged, last | `False` | |
| `DJANGO_SECURE_PROXY_SSL_HEADER` | Only behind a proxy that strips it | unset | Honoured only from `DJANGO_TRUSTED_PROXY_CIDRS` peers; requires them — §6 |
| `DATABASE_URL` | Recommended (PostgreSQL) | unset (SQLite) | `postgres://user:pass@host:port/dbname` |
| `DJANGO_STATIC_ROOT` | Recommended | `<repo>/staticfiles` | |
| `DJANGO_MEDIA_ROOT` | Recommended | `<repo>/media` | Must be persistent + backed up |
| `DJANGO_PRIVATE_MEDIA_ROOT` | Recommended | `<repo>/private_media` | Export/import files — never web-served directly; see §5a |
| `DJANGO_LOG_LEVEL` | Optional | `INFO` | One of DEBUG/INFO/WARNING/ERROR/CRITICAL |
| `RASTISI_ADMIN_DOMAIN_SUFFIX` | Recommended once real merchant admin subdomains are live | `rastisi.ir` | Suffix appended to `Store.admin_subdomain` to form the merchant admin host — see ADR-16 in `SAAS_DOMAIN_DECISIONS.md` |
| `RASTISI_DEFAULT_PLAN_CODE` | Optional (checkpoint 5A) | *(empty)* | `Plan.code` new stores are auto-subscribed to; empty = no auto-assignment (fail-open entitlements). Existing stores are unaffected — see §5a and ADR-65/72 |
| `RASTISI_DEFAULT_PLAN_START_TRIAL` | Optional (checkpoint 5A) | `true` | Whether a new store's default subscription starts in a trial (if the plan version defines `trial_days`) or goes straight to active |
| `RASTISI_BILLING_PROVIDER` | Optional (checkpoint 5B) | `manual` | Active SaaS payment provider. `manual` is an honest test/manual provider — wire a real gateway behind the same interface (ADR-75) |
| `RASTISI_BILLING_WEBHOOK_SECRET` | Required once a provider sends webhooks | *(empty)* | Secret used to verify webhook signatures (ADR-76). Never stored in the DB or code |
| `RASTISI_BILLING_MAX_WEBHOOK_BYTES` | Optional | `65536` | Max webhook body accepted before a 413 |
| `RASTISI_BILLING_WEBHOOK_TOLERANCE_SECONDS` | Optional | `300` | Signature timestamp tolerance |
| `RASTISI_BILLING_RENEWAL_LEAD_DAYS` | Optional | `3` | Days before period end that renewal invoices are generated (ADR-78) |
| `RASTISI_BILLING_DUNNING_SCHEDULE` | Optional | `0,3,7,14` | Days-after-due dunning retry schedule (ADR-79) |
| `RASTISI_BILLING_TAX_RATE` | Optional | `0` | Flat SaaS-billing tax rate; `0` = off. Not a legal VAT guarantee (ADR-82) |

Malformed values (an unparseable boolean, integer, or an invalid
`DATABASE_URL`) raise `ImproperlyConfigured` immediately at process startup
rather than falling back silently — you will see this as a crash on
`manage.py check`/`migrate`/`runserver`/gunicorn boot, with a clear message.

## 2. PostgreSQL preparation

1. Provision a PostgreSQL database and a role with a real password.
2. Install the driver: `psycopg[binary]` is already listed in
   `requirements.txt` (only actually needed once `DATABASE_URL` is set).
3. Set `DATABASE_URL=postgres://<user>:<password>@<host>:<port>/<dbname>`.
4. Run migrations against it (see §3) — this repository's migration history
   is engine-agnostic; no SQLite-specific operations are used.

This PR does not migrate your existing local SQLite data to PostgreSQL, and
does not rewrite migration history. A fresh PostgreSQL database is expected
to run every existing migration from scratch.

## 3. Migration command

```
python manage.py migrate
```

Run this on every deploy after pulling new code, before restarting the
application process.

### 3a. Industry Template catalog sync

`IndustryTemplate` rows (the merchant-onboarding "choose your industry"
catalog — categories, attributes, recommended options) are living,
version-controlled platform *content*
(`apps.catalog.industry_templates.registry`), not a one-time historical
fact — they are deliberately **not** created by a schema migration. A
migration is a frozen snapshot of a point in schema history; baking today's
registry into one would mean a fresh database, migrated years from now,
runs *today's* seed logic against whatever `IndustryTemplate`-family schema
existed back at that migration — silently breaking fresh installs the
moment a later migration changes one of those model fields.

Run this immediately after `migrate`, on every deploy:

```
python manage.py seed_industry_templates
python manage.py validate_industry_templates
```

Both are idempotent (`update_or_create` on stable natural keys) and safe to
run on every deploy, including ones that change nothing — re-running
`seed_industry_templates` creates no duplicate `IndustryTemplate`/category/
attribute rows. `validate_industry_templates` is read-only by default and
exits non-zero (failing the deploy, if your pipeline checks exit codes) the
moment any template fails validation — never skip or silence this step to
get a deploy through; fix the registry entry instead.

Skipping this step is exactly the production bug this section exists to
prevent: a fresh database that never runs `seed_industry_templates` silently
ends up with zero Industry Templates, and onboarding's industry-selection
step falls back to its (otherwise correct) empty state for every merchant.

## 4. Static files

```
python manage.py collectstatic --noinput
```

Serve the resulting `DJANGO_STATIC_ROOT` directory via your reverse proxy
(or a CDN in front of it) — Django itself does not serve static files when
`DEBUG=False`.

## 5. Persistent media

`DJANGO_MEDIA_ROOT` must point at storage that survives deploys/restarts
and is included in your backup routine (see §10) — product images, uploaded
logos, and homepage/footer media all live there. This PR keeps media on
local disk (per the existing architecture); it does not add cloud object
storage. If your hosting provider's disk is ephemeral (e.g. some
container/PaaS platforms), you must mount persistent storage there before
launch — that is a hosting decision, not something this codebase enforces.

## 5a. Private storage for export/import files, and its cleanup schedule

`DJANGO_PRIVATE_MEDIA_ROOT` must also point at persistent storage,
separate from `DJANGO_MEDIA_ROOT` — it holds generated Product/Variant/
Inventory/Customer/Order CSV exports (`ExportJob.file`), some of which
contain Customer PII or Order financial detail. Unlike `DJANGO_MEDIA_ROOT`,
nothing under this directory is ever served by a public URL — see ADR-52 in
`SAAS_DOMAIN_DECISIONS.md`; the only read path is the authenticated,
Store-scoped `dashboard:export-download` view.

This platform has no background task queue (ADR-49), so expired export
files are **not** reclaimed automatically — you must schedule
`python manage.py cleanup_expired_exports` yourself (cron or a systemd
timer), e.g. daily:

```
0 3 * * * cd /path/to/app && python manage.py cleanup_expired_exports
```

Without this, expired `ExportJob` rows still stop being downloadable
(the download view checks `status`/`expires_at`), but their files remain on
disk until the command actually runs.

Similarly, `python manage.py refresh_customer_segments` (ADR-53) must be
scheduled if you want dynamic Customer Segments' *materialized* membership
to stay current for future bulk actions — the segment detail page's live
preview does not depend on this schedule (it always re-evaluates), but the
materialized `CustomerSegmentMembership` rows only update when this command
(or the per-segment "Refresh Membership" button) runs:

```
0 4 * * * cd /path/to/app && python manage.py refresh_customer_segments
```

And `python manage.py cleanup_import_files` (ADR-62) deletes the private
source and error-report files of `ImportJob`s older than a 30-day retention
window (the `ImportJob` record and its per-row results are preserved). Like
the two commands above it needs external scheduling; the files it removes
are regeneratable/re-uploadable, never the sole copy of any data:

```
0 5 * * * cd /path/to/app && python manage.py cleanup_import_files
```

### Subscription state evaluation and consistency (checkpoint 5A)

The subscription domain (plans, entitlements, usage, trials, state machine)
has two cron-scheduled commands, again because this codebase has no background
task queue (ADR-49). `python manage.py evaluate_subscription_states` applies
due time-driven transitions — trial end → grace/expired, grace end →
suspended, elapsed billing period → grace, and a scheduled cancel firing at
period end (ADR-66/67). Run it at least daily; `--dry-run` reports what would
change without applying it:

```
0 6 * * * cd /path/to/app && python manage.py evaluate_subscription_states
```

`python manage.py verify_subscription_consistency --strict` is a **read-only**
health check (≤1 current subscription per store, no terminal-but-current row,
current version published, entitlement definitions present); with `--strict`
it exits non-zero on any problem, so it fits a CI/monitoring gate. It never
writes:

```
30 6 * * * cd /path/to/app && python manage.py verify_subscription_consistency --strict
```

`python manage.py provision_legacy_subscriptions` is idempotent and only
needed as a repair/backfill — the initial legacy grandfathering runs as a data
migration (ADR-65). Existing stores always get the unlimited Legacy plan;
they are never assigned a limited plan.

**Default plan for new stores.** `RASTISI_DEFAULT_PLAN_CODE` (empty by default
= no auto-assignment) names the `Plan.code` whose latest published version a
genuinely new store is placed on via `provision_default_subscription`;
`RASTISI_DEFAULT_PLAN_START_TRIAL` (default `true`) controls whether that
subscription starts in a trial. Leaving the code empty keeps new stores on
fail-open entitlements until a plan is chosen — turning it on is an explicit
deployment decision.

### SaaS billing: providers, webhooks, renewals, and dunning (checkpoint 5B)

SaaS subscription billing (`apps.billing`) is a domain separate from merchant
storefront order payments (ADR-73). It runs the honest `manual` provider by
default — no production payment is faked. Wire a real gateway behind
`apps.billing.providers` and set `RASTISI_BILLING_PROVIDER` +
`RASTISI_BILLING_WEBHOOK_SECRET`.

The provider **webhook endpoint** is `POST /billing/webhook/<provider>/` — the
only CSRF-exempt billing route; it authenticates by signature, not session
(ADR-76). Point the provider's webhook at that URL and share the secret.

Three billing commands need external scheduling (no task queue, ADR-49):

```
0 7 * * * cd /path/to/app && python manage.py generate_subscription_renewals
30 7 * * * cd /path/to/app && python manage.py process_subscription_dunning
45 7 * * * cd /path/to/app && python manage.py verify_billing_consistency --strict
```

`generate_subscription_renewals` creates one open renewal invoice per period,
`RASTISI_BILLING_RENEWAL_LEAD_DAYS` before period end (ADR-78).
`process_subscription_dunning` walks `RASTISI_BILLING_DUNNING_SCHEDULE`
(days-after-due), moving unpaid invoices past-due → grace → suspended (ADR-79).
`verify_billing_consistency --strict` is a **read-only** health check (paid
invoice without a successful attempt, overpaid invoice, duplicate renewal,
currency mismatch, refund over the paid amount, open invoice for a terminal
subscription, and so on) that exits non-zero on any problem.

**Tax and legal note (ADR-82):** SaaS billing tax defaults to zero
(`RASTISI_BILLING_TAX_RATE`); when enabled it is a single flat platform-wide
rate, not a jurisdiction-aware VAT engine. The platform makes no automatic
legal tax-compliance guarantee.

### CSV Import — columns, modes, and safety (checkpoint 4B)

Merchants import Products, Variants, and Inventory from CSV via the
**واردات داده‌ها** (Import) admin page. Every import is a two-step flow:
upload → automatic dry-run **preview** (nothing changes) → explicit
**execute** confirmation. The three modes are always chosen explicitly:
`create_only` (reject rows matching an existing record), `update_only`
(reject rows with no match), `upsert` (update matches, create the rest).

Records are matched by **stable, Store-scoped identity**: a platform
`product_id` first, then `sku` within the Store — never by name or slug.
Brand/Category/TaxClass/Warehouse are referenced by their **Store-scoped
code** (`brand_code`, `category_code`, `tax_class_code`, `warehouse_code`),
not display name; a missing or another-Store reference is a per-row error.
Downloadable CSV templates for each type are linked from the upload page.

Limits (documented, fixed — see `apps.core.services.csv_utils`): max upload
**10 MB**, max **20,000 rows**, max field length **2,000 chars**. Files are
UTF-8 (BOM-tolerant); Persian/Arabic digits are normalized automatically.
Inventory imports can never oversell — a reduction that would drop available
stock below active reservations is refused. Import source and error-report
files live under `DJANGO_PRIVATE_MEDIA_ROOT` and are only downloadable
through the authenticated, Store-scoped admin view (never a public URL).

### Storefront SEO endpoints (checkpoint 6)

The customer storefront serves a tenant-scoped `GET /sitemap.xml` and
`GET /robots.txt` (ADR-90): both resolve the Store from the request Host, so
each store's domain gets its own sitemap listing only that store's home,
product list, active categories, and published (never draft) products, plus
published CMS pages. `robots.txt` disallows `/cart/`, `/checkout/`, `/account/`,
and the admin paths and links the same-host sitemap. Canonical URLs, Open
Graph, and JSON-LD (Product/BreadcrumbList/Organization) are emitted per page
and reflect real price/availability. No cross-store URL or draft product is ever
exposed to crawlers. Because `django.contrib.sites` is not installed, these are
request-scoped views rather than the Sites-coupled sitemap framework — no
`SITE_ID` configuration is needed. See `STOREFRONT_AUDIT_REPORT.md`,
`STOREFRONT_SCREEN_INVENTORY.md`, and `STOREFRONT_MANUAL_QA_CHECKLIST.md` for
the full storefront coverage map and manual QA scenarios.

## 6. HTTPS / reverse-proxy assumptions

This application expects to sit either directly on the public internet with
its own TLS termination, or behind a reverse proxy that terminates TLS and
forwards plain HTTP internally. If you use the latter:

- Only set `DJANGO_SECURE_PROXY_SSL_HEADER` if your proxy is configured to
  **strip any client-supplied copy of that header** before setting its own. As a
  second line of defence the application drops that header from every request
  whose *direct* peer is not inside `DJANGO_TRUSTED_PROXY_CIDRS`
  (`apps.core.middleware.TrustedProxyHeaderMiddleware`, first in `MIDDLEWARE`,
  i.e. before `SecurityMiddleware`), so a client that reaches Django directly
  cannot spoof HTTPS detection. Setting the header without any trusted proxy
  is a startup error (it could never work). This setting is unset by default.
- `Store` resolution (`apps/stores/resolution.py`) uses Django's own
  `request.get_host()`, gated by `DJANGO_ALLOWED_HOSTS` — make sure your
  proxy passes through the real client-facing `Host` header unchanged. Client-IP
  trust is independent of host resolution; `USE_X_FORWARDED_HOST` must stay
  `False` (a system check enforces this in production).

### 6.1 Public-auth rate limits: shared cache, atomicity, outage policy

The anonymous auth/public endpoints (`/login/password/`, OTP request/resend,
`/reset-password/`, `/contact/`, platform-admin login, storefront customer OTP,
newsletter) are throttled by `apps/core/services/rate_limit.py`.

**Shared store (required).** The counters live in the cache alias `ratelimit`.
With `DJANGO_DEBUG=False`, `RASTISI_RATE_LIMIT_CACHE_URL` is mandatory and must be
a `redis://` or `rediss://` (TLS) URL; startup raises `ImproperlyConfigured` when
it is missing/malformed, and the `rastisi.E001` system check rejects any
non-Redis backend (LocMem, Dummy, file, database) for that alias. Django's
built-in `django.core.cache.backends.redis.RedisCache` is used — the only added
dependency is the `redis` client library. The URL carries the password: supply it
through your secret store; it is never echoed in errors/logs. Query strings are
rejected (redis-py would otherwise honour `ssl_cert_reqs=none`). Connect/socket
timeouts are 2 s so an unreachable Redis fails closed quickly instead of
hanging workers.

`default` stays a process-local LocMem on purpose: it holds non-security caches
(e.g. the platform-configuration row), so a Redis outage cannot take every page
down — only the throttled anonymous endpoints are affected.

**Algorithm.** Fixed window anchored on the first attempt, executed by one
server-side Lua script (`EVALSHA`, via the `redis` client the app already needs):

```lua
local count = redis.call('INCR', KEYS[1])
if count == 1 or redis.call('PTTL', KEYS[1]) < 0 then
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1]))
end
return count
```

Redis runs a script as one indivisible unit, so the increment and the first
expiry can never be separated: a counter cannot exist without its TTL even if the
client process is killed the instant after sending the command, and concurrent
workers cannot overshoot the budget. A request is rejected when the returned
count exceeds the budget. There is no read-modify-write, no `EXISTS`+`INCR`, and
no client-side `EXPIRE`. The TTL is the only window clock (not worker clocks);
later attempts never extend it; after it lapses the next attempt starts a fresh
window. The `PTTL < 0` branch also puts an expiry on any counter that was somehow
written without one. The connection (URL, TLS, 2 s timeouts) comes from
`CACHES["ratelimit"]`; the client is created lazily, so nothing connects at import
time. Keys are `rl:v1:<action>:<sha256(identifier)[:32]>` (no Django key prefix);
identifiers are always hashed, so no email, token or OTP appears in Redis. IPv6
clients are bucketed per /64. Redis ≥ 2.6 (Lua scripting) is required; any managed
Redis qualifies. A Redis *Cluster* is not needed (and each counter touches one key).

**Outage policy: fail closed.** If Redis is unreachable or errors, anonymous
password login, OTP SMS, password-reset mail, contact, newsletter, storefront
customer OTP and platform-admin login are *refused* with the Persian message
«سرویس موقتاً در دسترس نیست؛ لطفاً چند دقیقه‌ی دیگر دوباره تلاش کنید.» — never an
unhandled 500 and never unlimited attempts. The failure is logged (class name
only, no URL/secret). Already-authenticated dashboard use and public page
rendering do not depend on this store. The only deliberate exception is the
per-Store storefront-builder publish/restore/draft throttles, which are
authenticated anti-churn limits (not a security boundary) and fail open with an
error log.

**Pre-deploy / post-deploy verification**

```
python manage.py check                      # fails on missing/non-Redis cache, Turnstile, proxy, cookie errors
python manage.py check --deploy
python manage.py verify_rate_limit_cache    # LIVE probe of the atomic counter: create+TTL, incr, no TTL extension, expiry, delete (no secrets printed)
```

Run `verify_rate_limit_cache` from the same environment (network/secrets) as the
workers. Operators can unlock one bucket with `redis-cli DEL` on the exact key
(`rl:v1:<action>:<sha256(identifier)[:32]>`) or wait for the TTL.

### 6.2 Client IP and reverse proxies

All security code resolves the client through
`apps.core.services.client_ip.get_client_ip()` (never `REMOTE_ADDR`/headers
directly):

1. The direct peer (`REMOTE_ADDR`) is validated; an invalid/missing peer yields
   "unknown" and trusts nothing.
2. If the peer is **not** inside `DJANGO_TRUSTED_PROXY_CIDRS`, the peer *is* the
   client. `X-Forwarded-For`, `Forwarded`, `CF-Connecting-IP`, `True-Client-IP`
   and `X-Real-IP` are all ignored — a direct attacker cannot choose a bucket.
3. If the peer is trusted, `X-Forwarded-For` is read **right to left**; each hop
   that is itself a trusted network is a proxy of yours and is skipped; the
   first untrusted address is the client. Entries left of it are
   attacker-supplied and never examined. At most 16 hops are examined; a
   malformed hop, or a chain with no untrusted address, falls back to the
   direct peer. Ports/zone ids in hops are treated as malformed.
4. Only `X-Forwarded-For` is ever parsed. `Forwarded` and CDN headers are not.

Because a fallback bucket is shared, make sure the proxy always sets a clean
`X-Forwarded-For`. The same client-IP is sent to Turnstile as `remoteip`.

**A. Direct Django (no proxy).** Leave `DJANGO_TRUSTED_PROXY_CIDRS` empty and do not
set `DJANGO_SECURE_PROXY_SSL_HEADER` (TLS terminates on a server that sets
`REMOTE_ADDR` truthfully). All forwarded headers are ignored.

**B. One reverse proxy (e.g. Nginx on the same host or private network).**

```
DJANGO_TRUSTED_PROXY_CIDRS=127.0.0.1/32,::1/128        # or the proxy's private address/CIDR
DJANGO_SECURE_PROXY_SSL_HEADER=X-Forwarded-Proto:https
```

Nginx must *overwrite*, not forward, client-supplied values and Django must not
be reachable by any path that bypasses the proxy:

```
proxy_set_header Host $host;
proxy_set_header X-Forwarded-For $remote_addr;      # overwrite: Nginx is the first hop
proxy_set_header X-Forwarded-Proto $scheme;          # overwrite; never $http_x_forwarded_proto
```

A WSGI server bound to a unix socket typically reports an empty `REMOTE_ADDR`
(verify yours); in that case add the token `unix`
(`DJANGO_TRUSTED_PROXY_CIDRS=unix`) — only an *empty* peer is then trusted, garbage never is.

**C. CDN (e.g. Cloudflare) + reverse proxy — safest layout.** Do **not** put the
CDN's ranges into Django. Terminate CDN trust at the proxy with Nginx's
`realip` module (`set_real_ip_from <CDN ranges>; real_ip_header
CF-Connecting-IP;` — the CDN ranges are published by the CDN and must be
refreshed on a schedule you own, or enforced with authenticated origin pulls /
firewall rules), then overwrite the header for Django exactly as in B
(`X-Forwarded-For $remote_addr`, where `$remote_addr` is now the real client).
Django then trusts only Nginx. If instead Django must see a multi-hop
`X-Forwarded-For`, **every** hop in the chain must be deliberately listed in
`DJANGO_TRUSTED_PROXY_CIDRS`; any unlisted proxy IP is (correctly) treated as the
client, and a listed-but-uncontrolled network lets its users spoof their IP. The
repository does not hardcode any CDN range because no maintenance process for
them exists here.

**Turnstile (production).** With `DJANGO_DEBUG=False`, `TURNSTILE_ENABLED`,
`TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY` and `TURNSTILE_EXPECTED_HOSTNAMES`
are mandatory (startup fails otherwise; `rastisi.E002`). Verification is
server-side and authoritative: token, `action` and `hostname` must all match. Any
Siteverify timeout/network/parse error fails closed with the generic public error
before password authentication, SMS or mail happens. Runtime guards also refuse to
treat "Turnstile off" or empty hostnames as success while `DJANGO_DEBUG=False`.

### 6.3 Owner password recovery (mobile + SMS OTP) and the local-QA OTP

**Public recovery is mobile + SMS OTP.** `/reset-password/` asks for the owner's mobile
number, sends an OTP of purpose `reset` through the same hardened owner-OTP service
(per-phone budget, shared per-IP budget, attempt cap, single use, hashed at rest), then
`/verify/` -> `/reset-password/new/` lets the verified person choose a password
(an OTP-created owner with no password sets their first one here). It never logs anyone in,
never creates a User/OwnerProfile/Store, answers identically for known and unknown numbers
(the per-IP counters are charged for both), keeps Turnstile on the first request, and fails
closed when the shared rate-limit store is down. The 10-minute, single-use authorisation lives
only in the server-side session and is bound to the verified user. The legacy
`/reset-password/<uidb64>/<token>/` route (already-issued email links) still works;
`owner_auth_service.request_password_reset` is retained for that/internal use but no public
view calls it. Public recovery therefore needs a working platform SMS provider in production.

**Local-QA OTP (`RASTISI_DEV_OTP_CODE`) — development only.** On a laptop with no SMS
provider the console OTP backend is deliberately *not* treated as delivered, so register/login
OTP cannot be completed in a browser. For local QA only, set a 6-digit code:

```
# PowerShell
$env:RASTISI_DEV_OTP_CODE="123456"
python manage.py runserver
```

It applies only when `DJANGO_DEBUG=True` and the effective platform provider is `console`
(never over a real provider, never to non-OTP SMS), the code is stored hashed like any OTP and
is never logged. Unset it (restart `runserver`) to restore the default. Guards: non-6-digit
values fail startup; any value with `DJANGO_DEBUG=False` fails startup; system check
`rastisi.E006` repeats the production check (and refuses
`RASTISI_OWNER_SMS_ALLOW_CONSOLE_OTP=true` outside `manage.py test`); a runtime backstop ignores
it in production mode. **Never set it in a deployed environment.**

## 7. Secure cookies and staged HSTS rollout

Production (`DJANGO_DEBUG=False`) is HTTPS-only: `SESSION_COOKIE_SECURE` and
`CSRF_COOKIE_SECURE` default to true and an explicit `false` is a startup error
(`rastisi.E005` also checks `HttpOnly`, `SameSite` Lax/Strict and that
`SESSION_COOKIE_DOMAIN`/`CSRF_COOKIE_DOMAIN` stay unset — sessions are
intentionally host-only; Merchant Admin uses the one-time handoff ticket, never a
parent-domain cookie). `DJANGO_SECURE_SSL_REDIRECT` and HSTS remain staged: do not
enable them until you've confirmed HTTPS actually works for every hostname in
`DJANGO_ALLOWED_HOSTS`. HSTS is never enabled automatically. Suggested rollout:

1. Launch with HTTPS available but `DJANGO_SECURE_SSL_REDIRECT=False` and
   HSTS at `0`; confirm the site loads correctly over both `http://` and
   `https://`.
2. Set `DJANGO_SECURE_SSL_REDIRECT=True` (the secure cookies are already on).
   Confirm login/checkout still work.
3. Set `DJANGO_SECURE_HSTS_SECONDS=3600` (1 hour) for a day or two; watch for
   problems.
4. Raise to `86400` (1 day), then eventually `31536000` (1 year).
5. Only set `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=True` /
   `DJANGO_SECURE_HSTS_PRELOAD=True` once you are certain every subdomain
   you control also serves HTTPS correctly — these are effectively
   irreversible from the browser's perspective for the HSTS duration.

## 8. Health verification

After deploying, verify at minimum:

```
python manage.py check
python manage.py check --deploy
python manage.py verify_rate_limit_cache
```

Review every warning it prints — some may be intentionally deferred (e.g.
until a real domain/reverse-proxy is chosen); document which ones and why
rather than silencing them. Then confirm the application actually serves a
real page over the real domain/HTTPS before considering the deploy healthy.

## 9. Backup requirement

Before going live, you need a documented, **tested** restore procedure for:

- the PostgreSQL database (e.g. `pg_dump`/`pg_restore` on a schedule);
- the `DJANGO_MEDIA_ROOT` directory (product images, uploaded content).
- the `DJANGO_PRIVATE_MEDIA_ROOT` directory is deliberately **not** a backup
  candidate — every file in it today is a regeneratable CSV export (re-run
  the export from the admin panel), never the sole copy of any data. (A
  future CSV Import feature, not implemented as of this checkpoint — see
  ADR-54 — would also stage uploads here; that upload would likewise be a
  copy of data the merchant already has locally, not something this
  platform would need to be the only holder of.)

This PR does not implement or automate backups — that is deployment/hosting
work tracked separately (see `docs/00_PROJECT_MASTER_REFERENCE.md`). Do not
consider the platform launch-ready until a restore has actually been
exercised once against a throwaway copy, not merely scheduled.

## 10. Rollback preparation

Before a launch deploy, confirm you can:

- redeploy the previous known-good commit/build;
- reverse the most recent migration if it is safely reversible (check each
  migration's `reverse` behavior — several in this project intentionally
  only clear FK references rather than delete merchant data, precisely so
  rollback is safe);
- restore the database from the backup in §9 if a rollback requires it.

## 11. Commands to run before launch

```
python manage.py check
python manage.py check --deploy
python manage.py verify_rate_limit_cache
python manage.py makemigrations --check --dry-run
python manage.py showmigrations
python manage.py migrate
python manage.py seed_industry_templates
python manage.py validate_industry_templates
python manage.py provision_default_warehouses
python manage.py verify_inventory_consistency --strict
python manage.py collectstatic --noinput
python manage.py test
```

All of the above should be clean (no drift, no unexpected `check --deploy`
warnings left unexplained, full test suite green) before pointing a real
domain at the deployment.

## 12. Commerce & engagement operations (hardening phase)

Everything here extends the existing cron-based architecture (ADR-49): **no Celery, no queue, no scheduler framework.**
Status labels used below: *verified locally* (automated tests / staging PostgreSQL), *external verification pending*
(needs access this environment does not have). Nothing in this section has been deployed or run in production.

### 12.1 Background jobs — schedule, dependencies, safety

| Job (management command) | Frequency | Depends on | Idempotency / concurrency | Exit status |
|---|---|---|---|---|
| `process_notification_outbox --limit 200` | every 5 min | email backend / SMS provider configured | rows are claimed atomically (`SELECT … FOR UPDATE SKIP LOCKED`), stale `SENDING` claims are re-taken after 10 min, `dedupe_key` per message, backoff 1/5/30/120/360 min then `dead`; consent re-checked at send time | non-zero only if the *whole* batch failed (provider down) |
| `run_engagement_jobs --no-deliver` | hourly (or daily 08:15) | outbox job above | unique `CampaignIssuance(campaign, customer, cycle_key)`; per-customer errors isolated; a failing campaign does not stop delivery | non-zero if any campaign/issuance error occurred (after all work finished) |
| `expire_unpaid_orders` | every 10 min | per-store `unpaid_online_order_ttl_minutes` (**default 0 = no-op**) | order row lock → re-check → cancel through the lifecycle; one failing order does not stop the batch | non-zero if any order failed |
| `expire_inventory_reservations` | every 10 min | — | batch-safe conditional updates | 0 |
| `refresh_customer_segments` | daily 03:30 | — | per-segment errors isolated | non-zero if any segment failed |
| `cleanup_expired_exports` | daily 03:00 | — | — | 0 |
| `check_background_jobs` | every 15 min (monitoring) | — | read-only | 0 OK / 1 WARNING / 2 CRITICAL |

All commands that can overlap use a PostgreSQL advisory lock (`apps/core/job_lock.py`); a second concurrent run prints
`skipped: another … is still running` and exits 0. On SQLite (dev/tests) the lock is a no-op.

**Ready-to-apply configuration:** `deploy/cron/rastisi.crontab` (all six jobs, `CRON_TZ=Asia/Tehran`, `MAILTO`), `deploy/cron/run_job.sh` (per-job wrapper:
loads the environment file with `DATABASE_URL`/`DJANGO_SECRET_KEY`/`DJANGO_EMAIL_*`/provider settings from `/etc/rastisi/env`, activates the virtualenv, `cd`s to the app,
appends timestamped output to `/var/log/rastisi/<job>.log`, preserves the exit code, and runs `$RASTISI_ALERT_CMD "<subject>"` with the log tail on stdin when a job fails),
and `deploy/cron/validate_jobs.sh` (staging validation: DB/config check, delivery audit, expiry dry-run, reservations, segments, engagement queue-only twice, health).
Adapt `RASTISI_APP_DIR`, `RASTISI_VENV`, `RASTISI_ENV_FILE`, `RASTISI_LOG_DIR`, `MAILTO`, `RASTISI_ALERT_CMD` (e.g. `mail -s`), add log rotation (`logrotate` for `/var/log/rastisi/*.log`),
and route `check_background_jobs` exit codes 1/2 to your monitoring (the wrapper's alert already covers any non-zero exit).
Locally verified (against the staging PostgreSQL copy, **not** a real scheduler): the wrapper loads/activates/logs, preserves exit codes, fires the alert command on failure (this test found and fixed a bug where
the alert never ran), and `validate_jobs.sh` passes (the delivery audit exits 1 there because the staging platform gateway is console — expected and reported, not a hard failure).

**Validation on a real server (operator):** install the crontab for the app user (`crontab -u app deploy/cron/rastisi.crontab`), run `bash deploy/cron/validate_jobs.sh`, then check that
(a) `crontab -l` lists the entries; (b) within 5 minutes `/var/log/rastisi/outbox.log` shows a new `=== … end outbox rc=0`; (c) briefly stop the database on **staging** and confirm the alert fires and the
job exits non-zero; (d) start two copies of one job and confirm one prints `skipped: another … is still running`; (e) after the next hour `engagement.log` shows `end engagement rc=0`, and with an
active birthday/scheduled campaign the customer's reward appears in their account and the outbox rows become `sent` (or `skipped/no_promotional_consent`).

Time zone: the application uses `TIME_ZONE = "Asia/Tehran"` for Jalali periods/occasions and birthday cycles; the jobs themselves
are time-zone independent (they compare UTC timestamps). Set `CRON_TZ` (or the server TZ) consistently so "hourly/daily" means what
the owner expects. Missing configuration is never destructive: with every TTL at 0 the expiry job does nothing, and a store with
no SMS/e-mail configuration produces `failed`/`skipped` rows, not lost data.

`check_background_jobs` reports (from the data the jobs maintain): notification backlog age (WARNING > 30 min, CRITICAL > 2 h), claims stuck
in `SENDING`, `dead` deliveries in 24 h, campaign runs with errors in 24 h, overdue inventory reservations, unpaid orders past
TTL + grace (only for stores with expiry enabled), and open payment reconciliations (WARNING; CRITICAL if older than 24 h).
*Verified locally by tests; not verified on a real scheduler — see §12.7.*

### 12.2 Payment gateway (Zibal): what is and is not verified

Implemented and tested against the documented response contract with mocked HTTP (`apps/orders/tests/test_payment_discrepancy.py`):
verify result `100` (fresh) and `201` (already verified) are both treated as gateway-confirmed; amounts are exchanged in **Rial** (store
amounts are Toman × 10); a confirmed payment whose amount differs, or whose amount is missing/unreadable, is **never** applied as a
normal paid order — it becomes a `PaymentReconciliation` (confirmed mismatch, or *suspected* when the gateway result is ambiguous and
the customer returned claiming success), with staff e-mail and a Finance → تطبیق پرداخت‌ها entry.

**Not verified (official Zibal documentation and sandbox were unreachable from the build environment).** An operator with Zibal
account access must confirm before any order-expiry TTL is enabled:

1. How long a `trackId`/payment session stays payable (and whether the payment page link expires).
2. Whether Zibal retries the callback, and how many times / for how long.
3. What `verify` returns after the session expired (result code, `amount`, `status`) and for a payment completed after expiry.
4. Exact meaning of `result 201` and of callback `status`/`success` values in production vs. sandbox (`merchant=zibal`).
5. Whether production `verify` always returns `amount` (the adapter now treats a missing amount as ambiguous, not as success).
6. Whether partially paid/overpaid amounts are possible.

Until those answers are documented **keep `unpaid_online_order_ttl_minutes = 0`** for every store. The safe lower bound for a TTL
is *longer than the confirmed session lifetime + the grace period*; do not enable a speculative 60 minutes.

### 12.3 SMS / e-mail delivery

**Architecture (one system).** A store owner picks exactly ONE SMS delivery method in Settings → SMS: **Phone** (the owner's Android phone through the
SmsRasti app/gateway, `ShopSettings.sms_backend = smsrasti`) or **Platform** (RastiSi's central provider and credentials, configured only by the platform
administrator in `PlatformConfiguration`). Every eligible event — transactional (`send_event_sms`) and new-system/campaign (`NotificationOutbox` →
`send_raw_sms`) — is routed by `sms_service.get_backend` through the store's method automatically; there are no per-event providers and no per-store
provider credentials (the legacy `console/melipayamak/kavenegar` store values all mean "platform"). Rules enforced by tests
(`apps/sms/tests/test_delivery_routing.py`): no silent switch between methods (a store on Phone never falls back to paid platform delivery, a store on
Platform never uses the phone); changing the method affects only later messages (queued ones are never re-sent); **platform credit is consumed only by
platform delivery** and by OTP; Phone delivery consumes none; OTP/security SMS and platform-owner authentication always use the central gateway; legacy
transactional SMS stays synchronous and its events have no outbox SMS (no duplicate sends); an unconfigured platform "console" gateway fails loudly
(`درگاه پیامکِ مرکزی پیکربندی نشده`) instead of recording SENT + charging.
Customer-facing text speaks for the store (`{shop_name}`); only platform-owner OTP/test messages mention RastiSi (guarded by a test).

**SmsRasti device protocol** (`apps/sms/gateway_views.py`): pairing = per-store secret token; `poll` stamps `smsrasti_last_seen_at` (device "online" = polled within
5 min), hands out the oldest pending message once (`SENDING`, row lock + `skip_locked`), re-offers an unacknowledged message after 120 s at most 5 times and
then marks it `FAILED` (bounded, no endless duplicate sends); `ack` is idempotent (a SENT message is final), a failed ack marks the item and its `SmsLog`
FAILED, a later retry (dashboard → resets the claim counter) re-queues it and the history follows the real outcome. Offline device = messages stay queued in order.
`success` for Phone means "queued", not "delivered" — delivery is the device's acknowledgement.

**Status for the store admin** (Settings → SMS, `delivery_status_service`): selected method, health (ok/warning/error), credit (platform only), device
paired/online/last seen (phone only), queue (pending/sending/failed), failures in 24 h, and actionable errors (SMS disabled, device not paired/never connected/offline with N queued,
no credit, platform gateway problems — which only the platform admin can fix).

**Operator audit:** `python manage.py verify_delivery_channels [--store slug]` reports the same truth per store (method, device/credit state) and the platform gateway once
(provider real/NOT REAL, missing platform credentials — never printed), plus the e-mail backend (console/locmem/dummy = NOT REAL), SMTP settings, sender domain (SPF/DKIM/DMARC
must be checked at the DNS provider). Exit code 1 if anything is not production-ready.

**What is verified, and how.** Automated, mocked-HTTP/local-sink only: routing matrix, credit rules, provider failure/refund, device poll/ack/duplicate/timeout/retry,
parallel polling on PostgreSQL, e-mail through the real Django SMTP transport against a local in-process SMTP sink (envelope, multipart, backoff, single re-send,
invalid recipient, consent). **Not verified against any real service** (no credentials, no Android device, no mail account in the build environment).

**Operator verification steps (needs real access):**
1. Platform admin: configure the central provider (Platform Admin → SMS) and run `verify_delivery_channels` → must print `provider=… REAL`, no PLATFORM PROBLEM.
2. Platform method: with a store on Platform and credit > 0 run
   `python manage.py verify_delivery_channels --send-test-sms 09XXXXXXXXX --store <slug> --confirm-test-recipient` (a number you control) and confirm the handset received it.
   "SENT" only means the provider accepted the request.
3. Phone method: pair a real phone (generate the token in Settings → SMS, enter it in the SmsRasti app), confirm the dashboard shows "device connected", send the same test
   command, watch the queue item go pending → sending → sent on the phone's acknowledgement; switch the phone to airplane mode and confirm the device shows offline and messages stay queued.
4. E-mail: `verify_delivery_channels --send-test-email you@your-domain --confirm-test-recipient`; check inbox/spam, SPF/DKIM/DMARC headers.
Do not send tests to customers.

### 12.4 Promotional consent

Policy (single implementation: `apps/customers/services/consent_service.py`): unknown consent is **not granted**; SMS and e-mail are
independent; every change records source + time (+ audit event when a store context exists); consent is re-checked at queue time and
again at send time; transactional/security messages never depend on it. New customers default to no consent; signup/checkout checkboxes
are never pre-ticked; checkout can only *grant*, withdrawal is in account settings.

Migration `customers.0006` adds fields/defaults, `0007` backfills: every pre-existing `True` (which was the unverifiable column default)
becomes `False/legacy_unverified`; every `False` becomes `legacy_opt_out`. **Bulk promotional sends to existing customers therefore stop
until consent is recorded again.** Audit: `python manage.py promotional_consent report`. Where a store holds documented external evidence of
opt-in, import it: `promotional_consent import --file consent.csv --channel sms --evidence "<ref>" --store <slug> [--apply]` (dry-run by default).
Product/legal decisions needing external confirmation (not decided by tests): lawful basis and consent wording for Iran, whether consent is
per-store or per-account (currently per customer account across stores), retention of the consent evidence, and whether a one-click
unsubscribe link/short code is required in each promotional message.

### 12.5 Pricing and checkout confirmation

One mechanism (CAT-002, from `main`): `cart_service.reprice_cart_items` re-prices the cart snapshot (unit price and gift-wrap price) from the catalogue before order creation; `create_order_from_cart(require_confirmed_prices=True)` resolves final prices once under product/variant → cart → cart-item locks and raises `LivePriceChangedError` on any drift from what the customer confirmed — including a displayed total that no longer matches (`expected_total`, comparison only: shipping/coupon/tax/gift-wrap changes) — after which the cart is re-priced and the customer must re-confirm (`PriceChangeReviewRequired`). The persisted order total is what the payment attempt and the gateway receive (Toman → Rial in the adapter). Historical orders/refunds use order snapshots.

### 12.6 Migrations — production-like verification, ordering, rollback

Branch migrations (apply in dependency order; Django resolves it): `customers.0004–0007`, `cart.0008–0009`, `catalog.0039`, `core.0017–0018`,
`engagement.0001–0002`, `orders.0011–0019`, `notifications.0002–0003`.

Verified on a **synthetic populated PostgreSQL 16 database built at the base commit schema** (100,000 customers, 150,000 orders, 300,000 items,
89,736 transactions, 200,000 SMS logs; *not* a copy of production — none was available): forward migration of the whole sequence took ≈16 s total
(largest steps: `customers.0007` backfill 4.4 s, `orders.0016` coupon-redemption backfill 3.0 s, `notifications.0002` 2.1 s); order/transaction/SMS counts and
monetary sums identical before/after; no orphaned rows; every one of 29,970 coupon orders received a ledger row; backfills re-run idempotently;
`makemigrations --check` clean; `check` clean.
Locking risk: `customers.0006/0007` and `orders.0016` rewrite/update whole tables (row locks for seconds at this scale; run in a maintenance window or
low traffic); the other steps are additive (`ADD COLUMN` with constant default, new tables, indexes — `orders.0015` creates indexes without `CONCURRENTLY`).
Schema vs. data reversibility: reverse migrations exist and ran on the populated copy, **but** `customers.0005` cannot be reversed once an operator longer than 20
characters (e.g. `greater_than_or_equal`) is stored (`value too long for type character varying(20)`), and reversing `customers.0007` restores the old unverifiable
`True` consent. Treat the deploy as **roll-forward**: take a backup first, and recover by restoring the backup (or fixing forward), not by reversing.

Backup/restore drill executed on the staging copy: `pg_dump -Fc` (16 MB) → `pg_restore` into a fresh database → the 12 count/sum checks identical to the source → `check` clean → `promotional_consent report` identical → applying the one newer migration (`core.0019`, 0.07 s) left every count/sum unchanged. Procedure (operator, **do not run against production without explicit authorization**): `pg_dump -Fc` backup → restore into a staging DB and rehearse
`migrate` + `check` + `makemigrations --check` + `verify_coupon_consistency` + `promotional_consent report` → compare counts/sums → schedule window → `migrate` →
post-checks (same commands) → keep the backup until the first full business day passes.

### 12.7 What remains unverified (external access required)

Real Zibal session/callback behaviour (official docs and sandbox unreachable — re-checked in the follow-up phase, still unverifiable); real SMS (platform provider and the SmsRasti Android device) and e-mail delivery; a real cron scheduler (the crontab above is a template, not a deployed fact); a sanitized
production database copy for migration rehearsal; Firefox and WebKit runs of the browser suite — to run them elsewhere: `pip install playwright && playwright install firefox webkit`, `cd tools/engagement_e2e && npm i axe-core`, `E2E_PG_BASE=postgres://user:pw@host:5432 bash tools/engagement_e2e/reset.sh`, then `python tools/engagement_e2e/accessibility_e2e.py` (it launches Chromium, Firefox and WebKit in turn and prints `NOT RUN` for any missing runtime); (in this environment Playwright browser hosts, Mozilla and PPA hosts are blocked by the environment's egress proxy; Ubuntu's `firefox` package is a snap stub — cannot be installed here).

## What this PR does **not** do

- No real payment gateway (Zibal) — the checkout payment step is still
  simulated.
- No Order/dashboard Store-boundary hardening (a known, separate gap — see
  the launch audit).
- No checkout idempotency / inventory-locking fixes.
- No Enamad support.
- No hosting-provider selection or actual server provisioning.
- No secrets, merchant credentials, or real business information are
  included anywhere in this repository.
