# Pre-Push Gate (B) — launch checklist, domain, SEO/AI visibility

Branch `feature/admin-panel-modernization-20261029` · base `1e1d140b4d6a83b688b0570a6befaf7b47841718` · HEAD = the commit that carries this file (see `git log -1`) · **nothing pushed, merged, deployed, migrated or backfilled; no external request was sent; Windows QA / Production untouched.**

Supersedes the statements of `SEARCH_READINESS_DELIVERY_20261031.md` where they differ (currency `IRT`, trackers loading by default, payment inside "ready to publish", IndexNow host checks).

## Commits (12 local, oldest first)

| SHA | Subject |
|---|---|
| `4453880e` | Technical SEO: indexability policy, canonical origin, JSON-LD, AI-crawler policy |
| `c2688bc6` | Setup checklist: required vs optional, honest states |
| `6d64e134` | Custom domain actions inside the seller panel |
| `e90e72ed` | Honest integrations page, analytics snippets, IndexNow |
| `4f00c6d2` | Full-suite regressions caused by the above (lazy context processors, `data-goal-group`, contract test) |
| `79ff123c` | First delivery report |
| `222a7793` | **(3)** ISO 4217 currency in structured data / Open Graph |
| `73fad160` | **(4)** Trackers OFF by default (no consent mechanism exists) |
| `60e66edd` | **(5)** Ready-to-publish without payment; new ready-to-sell |
| `b678d6ce` | **(6)** IndexNow/key file only for a verified domain of the same store |
| `2c1543db` | **(2)** two pre-existing test-isolation defects fixed (tests only) |
| *(this file)* | Pre-Push Gate B |

---

## 1. Git — remote vs `CLAUDE.md`

**Exact text** (`CLAUDE.md` line 8, identical in this worktree and in `/home/user/Rastisi6-14040616`):
`- The canonical Git remote is `rastisi5`. Do not push to legacy `origin` unless explicitly requested.`

**Evidence (read-only, nothing changed):**
* `git remote -v` in every worktree: only `origin → https://github.com/manouchehr94-ux/Rastisi6-14040616` (fetch and push). **No remote named `rastisi5` exists** in this clone (`git config --get-regexp '^(remote|branch)\.'` lists only `origin`; no `url.*.insteadOf`).
* `rastisi5` is a **different GitHub repository**: `manouchehr94-ux/rastisi5` (public, last push 2026-09-07, `can_push: true`) — docs under `docs/superpowers/` call it "Repository: manouchehr94-ux/rastisi5". `CLAUDE.md` was last edited 2026-09-04 (`8d1e08b8`), i.e. before this repo (`Rastisi6-14040616`, last push 2026-10-31) became the working repository.
* Tracking: `feature/admin-panel-modernization-20261029` → `origin/feature/admin-panel-modernization-20261029` (remote head `1e1d140b`, local is ahead by 12). Every QA branch pushed so far went to `origin` = `manouchehr94-ux/Rastisi6-14040616` (e.g. `origin/feature/vision-studio-20261028`).
* Conclusion: the instruction in `CLAUDE.md` and the real QA destination contradict each other. **Not resolved by me** (no remote added, no branch changed, no `ls-remote`/fetch to `rastisi5`). Decision needed from the owner: (a) the destination for this push is `origin` = `Rastisi6-14040616` (what QA used) and `CLAUDE.md` is stale, or (b) it must go to the separate `rastisi5` repo, which requires adding that remote first. Until then the push gate stays closed.

## 2. The four failures outside the baseline — flaky or regression?

Full ids (from full-suite run #2 on `4f00c6d2`):
1. `apps.dashboard.tests.test_settings_views.FaviconUploadTests.test_simultaneous_upload_and_remove_replacement_wins` (ERROR in `tearDown`: `FileNotFoundError … /tmp/tmp84sjmauw/shop`)
2. `apps.notifications.tests.test_legacy_sms_integration.LegacyHistoryMirrorTests.test_failed_send_is_mirrored_as_dead_and_not_retried_by_outbox`
3. `apps.notifications.tests.test_legacy_sms_integration.LegacyHistoryMirrorTests.test_mirror_failure_never_breaks_sms`
4. `apps.notifications.tests.test_legacy_sms_integration.LegacyHistoryMirrorTests.test_one_mirror_row_with_links_and_no_second_delivery`

**Method:** frozen worktrees of `79ff123c` (HEAD at the time) and of the untouched base `1e1d140b`; same targeted module set (`apps.notifications apps.sms apps.dashboard.tests.test_settings_views`, 353 tests) run `--parallel 4` ×3 on each + sequential ×1 on each.

| Run | HEAD `79ff123c` | Base `1e1d140b` |
|---|---|---|
| parallel 1 / 2 / 3 | identical: 353 run, only `notifications.test_email_transport` import ERROR (pre-existing baseline) | identical |
| sequential | identical | identical |

The four tests **passed on both sides in all 8 runs**. So the failure is order/worker-dependent, not caused by a code difference. Mechanisms, with proof:
* **SMS trio (2–4):** `get_platform_configuration()` caches the PlatformConfiguration in the process-wide cache, which is not rolled back with the DB. If an earlier test in the same worker leaves a Kavenegar config there, `send_event_sms` selects `KavenegarBackend` instead of the patched `ConsoleBackend`; the log showed a real `HTTPSConnectionPool(host='api.kavenegar.com')` attempt (stopped by the sandbox proxy: 403). **Reproduced deterministically on the untouched base worktree** with a throw-away primer test (3/3 fail with the same assertions). The module is not touched by this work (`git diff 1e1d140b..HEAD -- apps/notifications apps/sms` was empty).
* **Favicon (1):** `_TEMP_MEDIA_DIR = tempfile.mkdtemp()` runs at import, before `--parallel` forks; **proved on base** that two workers print the same directory. `LogoUploadTests`/`FaviconUploadTests` tearDowns therefore race. I did *not* reproduce this particular failure on base (timing dependent) — it is classified as a pre-existing isolation defect, not as "proven flaky by repetition".

**Fix (tests only, commit `2c1543db`):** clear the platform-config cache key in the SMS `Base.setUp`; race-tolerant `_clear_temp_media_dir()`. Replaying the leak scenario now passes (it failed 3/3 before). **Residual risk:** the four ids are explained and fixed, but a different order-dependent test elsewhere could still exist; the shared temp dir across workers is still shared (only the cleanup became tolerant).

**Full suite on final HEAD (`2c1543db`, SQLite, `--parallel 4`):** 11 987 tests, 34 failures + 4 errors = **38 distinct ids, all in `TEST_RECONCILIATION_20261029.md`** (storefront_builder V2-family contracts, onboarding gallery, demo-refresh command, `notifications.test_email_transport` import error, `sms.test_gateway_live` setUpClass). None of the four above failed in this run. This is one run: I report "no failure outside the baseline observed in this run", not "zero regressions guaranteed".

## 3. Currency

**Findings (read from code):**
* Stored: `Product.price` etc. = `DecimalField(max_digits=12, decimal_places=0)`, verbose "قیمت (تومان)"; variants likewise; cart/checkout/orders use the same unit (`Order`/`ShippingRateRule.CURRENCY = "IRT"`; the card snapshot label `PaymentAttempt.currency` defaults to `"TOMAN"`, billing uses `"IRT"` — **labels are inconsistent but the unit is always Toman**).
* Displayed: UI uses the `toman` filter ("تومان").
* Charged: gateways multiply by `TOMAN_TO_RIAL = 10` (`apps/orders/gateways/zibal.py`, `apps/billing/providers/zibal.py`).
* **Bug found:** JSON-LD said `priceCurrency: "IRT"` and `og:product:price:currency = "IRT"` — not ISO 4217; Google would not understand it, and the amount was in Toman.
* Second finding: the Offer used `product.final_price`, ignoring independent **variant prices** that the cart/checkout use (`resolve_effective_price`).

**Fix (`222a7793`):** `apps/core/currency.py` (`IRT` storage convention, `IRR` ISO, factor 10, `toman_to_rial`). JSON-LD and Open Graph now emit `IRR` with Rial amounts from `resolve_effective_price` (discount and variant price included); variable products with different active variant prices → `AggregateOffer` (`lowPrice/highPrice/offerCount`, inactive/obsolete variants ignored); price-inquiry products emit nothing. **No stored price, model or migration changed.**
**Tests (`test_currency_structured_data.py`, 10 new tests + 2 updated assertions):** 250 000 Toman → `"2500000"` IRR; 1 000 000 with 10 % discount → `"9000000"`; Decimal/str inputs; stored price unchanged after render; page still shows "تومان"; variants 250 000/400 000 → low `2500000`, high `4000000`, count 2; equal variants → plain Offer; all out of stock → OutOfStock; inquiry → no price; factor tied to both gateway constants (single-truth guard).
**Residual risk:** inconsistent *labels* (`IRT`/`TOMAN`) in non-Google areas remain; Google Merchant Center does not serve Iran, so rich-result eligibility for IRR is not something I can verify offline.

## 4. Analytics and consent

**Finding:** the project has **no visitor consent mechanism for tracking**. The only consent system is `apps.customers.services.consent_service` (promotional SMS/e-mail of *registered customers*, a different purpose); there is no cookie banner/CMP anywhere (`templates/`, `apps/`). So there was nothing to reuse and, as shipped in `e90e72ed`, GA4/GTM/Meta pixel fired for every visitor immediately.
**Fix (`73fad160`) — fail-closed, no banner, no parallel system:** loading requires the explicit platform switch `RASTISI_STOREFRONT_TRACKING_ENABLED` (default **False**, env-controlled). With it off nothing is rendered even for a connected, public, published store; the integrations page says *why* ("saved, not loaded: platform owner must confirm the legal basis and visitor consent"). All earlier rules stay (own store only, strict id regex, no test/unpublished hosts, no seller HTML).
**Tests:** default-off with all three connected (no ids, no `googletagmanager.com`/`fbevents.js`), project default asserted from settings, switch-on renders only own ids, effect state `privacy` on the page.
**Open decision (needs you, not done):** a real consent mechanism (banner or CMP + storing the choice) is a product/legal decision; until then the switch should stay off in Production. With the switch ON trackers fire before any consent.

## 5. Publish rules — Ready to Publish vs Ready to Sell

**Finding (mine, now corrected):** in the first rewrite I had added "an active payment method" to the *publish step*. The base rule (`git show 1e1d140b`) was: store info + industry + industry template + one active product + one active shipping method; and the platform's real publish authority (`onboarding_publish_service.complete_onboarding`) needs only an applied template. So payment must not gate publishing; a showcase/inquiry shop may open first.
**Now (`60e66edd`):**
* `ready_to_publish` = base five prerequisites (no payment); publish step done = really public **and** those prerequisites (as before, plus the truthful "public" fact).
* `ready_to_sell` (new) = every required step except publish (this includes a payment method).
* A public shop with no payment: `is_live=True`, `ready_to_sell=False`, `all_complete=False`, summary text "منتشر شده اما هنوز آماده‌ی فروش نیست". Nothing is blocked in the UI.
* **Payment kinds:** online gateway, **cash on delivery** and **card-to-card** are the same `PaymentGatewayConfig` rows → any active one counts; inactive or another store's never counts.
**Tests (5 new + 1 updated):** ready-to-publish without payment; ready-to-sell needs payment; COD / CARD_TO_CARD / ZIBAL each make it sellable; inactive does not; other store's does not; public-without-payment is live but not ready to sell.
**Not changed (policy, needs your approval):** whether `payment_gateway` should remain a *required* step for "sell" progress; stores that sell only by **price inquiry** (no cart) still show a payment blocker — a business-rule question, left as is.

## 6. Domain and IndexNow

* Routing already resolves hosts only through **verified, non-retired** `StoreDomain` rows (`apps/stores/resolution.py`). I added an independent check (`b678d6ce`): `indexnow.is_verified_host(store, host)` (port ignored, store-scoped) is required by (a) the key file view, (b) `indexnow.submit()` (new status `host_not_verified`), and (c) the dry-run command, which now picks only a verified domain.
* Key = `HMAC(SECRET_KEY, "indexnow:<store.public_id>")[:32]` — unique per store; the key file of store B on A's host → 404.
* URLs: only the store's own host (`https://evil.<host>`, another store's host, `javascript:`/`ftp:` dropped), deduplicated, ≤ 10 000; sitemap entries come from `Store`-scoped queries.
* **Default OFF:** `RASTISI_INDEXNOW_ENABLED` default `False` (asserted from the project settings); even when on, nothing is sent for a non-indexable store or an unverified host. **No external request was made**: every submit test injects a fake transport (`assert_not_called` where applicable); the dry-run command test patches `_post`.
* Tests added: pending / verified-but-retired / other-store / unknown host never submitted; key file of one store not served on another store's verified host; `is_verified_host` ports and scoping; default-off.
* Residual: the domain model has no "verified host used for IndexNow" notion beyond the verified flag; a host verified but whose DNS later breaks is not re-checked at submit time.

## 7. Tests actually run (this round)

| Scope | Result |
|---|---|
| `test_currency_structured_data` + `test_seo_policy_and_structured_data` + `test_price_inquiry` | 49 OK |
| `test_tracking_indexnow_visibility`, `test_integrations_visibility_page`, `test_integration_views` | 25 + 6 + 20 OK |
| `test_setup_checklist` + `test_admin_v22_shell` | 75 OK |
| `test_legacy_sms_integration` + `test_settings_views` (isolation fix) | 138 OK |
| Targeted flaky comparison, HEAD vs base, 3× parallel + 1× sequential each | identical, 4 ids green (pre-existing `test_email_transport` error on both) |
| Throw-away repro on base (SMS leak; shared tmp dir probe) | SMS reproduced 3/3; shared dir proved; throw-away files removed, frozen worktrees removed |
| Full suite on final HEAD | 11 987 run, 38 distinct failing ids, all in baseline; skipped 237 |

Not run: PostgreSQL concurrency suite (no locking change), Firefox, browser screenshots for the *new* wording (text-only change on the integrations/checklist pages).

## 8. Items still needing your permission / decision (nothing executed)

1. Remote/destination: `origin` (`Rastisi6-14040616`) vs `rastisi5` (§1).
2. Consent mechanism for trackers and when to set `RASTISI_STOREFRONT_TRACKING_ENABLED` (§4).
3. Whether payment stays a required step for "ready to sell" / inquiry-only stores (§5).
4. The earlier proposed migration (per-store AI-crawler choice, persisted submission queue) — still **not** created.
5. Enabling `RASTISI_INDEXNOW_ENABLED` in Production — still **off**.

## Pre-Push Gate B

| Gate | State |
|---|---|
| Working tree clean, 12 local commits, no migration, `makemigrations --check` clean | ✔ |
| No push / merge / deploy / backfill / real external call | ✔ |
| Failures outside baseline in final full run | none observed (1 run) |
| Previously flaky four | explained, fixed, green |
| Currency in structured data | fixed, tested |
| Trackers | off by default; consent decision open |
| Remote destination | **OPEN — blocks push** |
