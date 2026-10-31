# Pre-Push Gate (C) — final gate before asking for push authorization

Decisions applied (owner, 2026-10-31): reference repository = `manouchehr94-ux/Rastisi6-14040616` (`origin`), never `rastisi5`; tracking stays OFF by default; price-inquiry-aware ready-to-sell only on a real flow; no migration/queue; IndexNow off in Production; no external requests. **This is not a push authorization. Nothing was pushed, merged, deployed, migrated or backfilled; Windows QA and Production untouched.**

## 1. Git identity (the facts the gate asks for)

| Item | Value |
|---|---|
| Branch | `feature/admin-panel-modernization-20261029` |
| HEAD (tested code state) | `84f936cfbb7b5e8a1f5f8841049d63feddab1d78` — the commit that adds this file follows it (`git log -1`; docs only, no code) |
| Remote tracking SHA | `1e1d140b4d6a83b688b0570a6befaf7b47841718` (`origin/feature/admin-panel-modernization-20261029`; `git fetch --dry-run origin` printed nothing, i.e. no newer refs; no fetch/push executed) |
| Ahead / behind | **14 ahead / 0 behind** before this file (15 with it) |
| Remotes | only `origin` → `https://github.com/manouchehr94-ux/Rastisi6-14040616` (fetch + push). No remote added, changed or removed |
| Working tree | clean (`git status --short` → 0 lines) |
| Migrations | **none**: `git diff 1e1d140b..HEAD -- apps/*/migrations` empty; `makemigrations --check --dry-run` → "No changes detected"; nothing run, no backfill |
| Diff size vs remote | 46 files, +2746 / −346 (before this file) |

### Commits (oldest first)

| # | SHA | Subject |
|---|---|---|
| 1 | `4453880e` | Technical SEO: one indexability policy, canonical origin, safe JSON-LD from real data, AI-crawler policy |
| 2 | `c2688bc6` | Setup checklist: required vs optional, honest states, five goal groups, one primary action |
| 3 | `6d64e134` | feat(domain): connect a custom domain from the seller panel itself |
| 4 | `e90e72ed` | feat(visibility): honest integrations page, analytics snippets on public pages, IndexNow |
| 5 | `4f00c6d2` | fix: full-suite regressions from the search/checklist work |
| 6 | `79ff123c` | docs: search-readiness delivery report |
| 7 | `222a7793` | fix(seo): structured data and Open Graph prices in ISO 4217 (IRR, amount ×10) |
| 8 | `73fad160` | fix(privacy): analytics/ad trackers are OFF by default on the storefront |
| 9 | `60e66edd` | fix(checklist): ready-to-publish no longer needs a payment method; add ready-to-sell |
| 10 | `b678d6ce` | fix(indexnow): key file and submissions only for a VERIFIED, non-retired domain of the same store |
| 11 | `2c1543db` | test: remove two pre-existing parallel/order isolation defects (no product code) |
| 12 | `4200c75c` | docs: Pre-Push Gate B |
| 13 | `1d2bb973` | feat(checklist): no payment method needed for a shop whose active products are all price-inquiry |
| 14 | `84f936cf` | docs(CLAUDE.md): git remote for this cycle is origin (Rastisi6-14040616), not rastisi5 |
| 15 | *(this file)* | docs: Pre-Push Gate C |

## 2. `CLAUDE.md` (commit `84f936cf`, only file changed)

Before (line 8): ``- The canonical Git remote is `rastisi5`. Do not push to legacy `origin` unless explicitly requested.``
After (lines 8–9):
* ``- Git remote for the current development cycle: `origin` = `https://github.com/manouchehr94-ux/Rastisi6-14040616` (owner decision, 2026-10-31; the Windows QA builds are received from it). Do not use `rastisi5` (a separate, older repository).``
* `- Never add, change or remove Git remotes, and never push, merge, deploy, migrate or backfill, without explicit authorization from the owner for that specific action.`

Scope: this is the only place that gave the contradictory instruction. Other mentions of `rastisi5` are historical evidence documents (`docs/superpowers/**`, `docs/qa_evidence/**`, `docs/architecture_decisions/**`, one older implementation-audit note) and were deliberately **not** edited. `CLAUDE.md` in the other worktrees (`/home/user/Rastisi6-14040616` etc.) belongs to other branches and is unchanged. No remote or branch was added/changed.

## 3. Price-inquiry stores — is there a real flow?

**Yes, a real one** (read from code, `apps/catalog/services/pricing_mode_service.py`, cart, orders):
* a product (`price_mode_override`), a category (and its sub-categories) or an active collection can be «استعلام قیمت»; precedence is documented and tested; the effective flag `Product.is_price_inquiry` is written only by that service;
* the server refuses add-to-cart (`PriceInquiryOnlyError`) and re-checks at order creation; no price reaches the browser; the PDP shows an inquiry button to the store's page (`inquiry_destination_url`). It does **not** create a lead record — the page is informational.
* There is **no store-level "sale type"** — inquiry is per product/category/collection. I did not invent one.

**Rule implemented (`1d2bb973`, no hunch beyond the code):** the payment step is *required* when (a) no active product exists yet (we cannot know what the shop sells), or (b) at least one active, non-draft product is directly purchasable (`is_price_inquiry=False`) — i.e. the shop has a checkout. It is *optional* only when active products exist and **all** are price-inquiry; the step then says why, and still shows "done" if a method exists. Shipping and the base publish prerequisites were not touched.
Tests (5 new): all-inquiry → not required + `ready_to_sell` true + 9 required steps; one purchasable product brings it back; no product → required; draft / other store's products don't change it; optional-but-configured shows done. Combined with the earlier tests (COD, card-to-card, online gateway all count; inactive/other-store never count; public-without-payment = live but not ready to sell).
Residual risk: the inquiry page is informational (no lead capture) — "ready to sell" for an inquiry-only shop means "customers can see products and be pointed to your page", not "orders can arrive".

## 4. Trackers, IndexNow, domains (re-confirmed, unchanged by this round)

* `RASTISI_STOREFRONT_TRACKING_ENABLED` default **False** (asserted from project settings by a test); with it off nothing is rendered even for a connected, published, public store. **Enabling in Production is not allowed** without a valid Consent Management and a privacy review — the integrations page states this to the owner. No banner/CMP was built.
* `RASTISI_INDEXNOW_ENABLED` default **False** (asserted by a test); submissions need: switch on + indexable store + verified non-retired domain of the same store; every test used a fake transport; **no external request was sent**.
* The proposed migration/queue (per-store AI-crawler choice, persisted submission queue) remains **documentation only** (`SEARCH_READINESS_DELIVERY_20261031.md` §G); nothing created or run.

## 5. Isolation fixes — targeted re-verification

Fix (`2c1543db`, tests only): clear the cached platform-configuration key in the SMS mirror tests' `Base.setUp`; race-tolerant cleanup of the shared favicon/logo temp dir.
* Targeted modules `apps.dashboard.tests.test_settings_views apps.notifications.tests.test_legacy_sms_integration apps.sms` (301 tests), `--parallel 4`, **5 consecutive runs on the final code: 5 × OK** (1 skipped) — including the four previously failing ids.
* The cache-leak scenario (primer test caching a Kavenegar platform config, then the SMS mirror class) failed 3/3 on untouched base `1e1d140b` and passes on the fixed tree.
* Not proven: the favicon failure itself was never reproduced on base (timing); only the shared-directory cause was shown. A different order-dependent test may exist.

## 6. Full suite on the final code (`84f936cf`) vs baseline

`manage.py test --parallel 4 --noinput`, SQLite: **11 992 tests, 34 failures + 4 errors = 38 distinct ids, 237 skipped, 2 819 s.**
* The failing set is **identical** to the previous full run (diff of FAIL/ERROR lines: empty both ways) and **every id is in `TEST_RECONCILIATION_20261029.md`**: 29 × "A. in the Vision baseline list and still failing" (storefront_builder V2-family contract tests: dense_marketplace_beraito, editorial_jewelry_saremi, premium_leather_shokolati, warm_boutique_lalerokh, r4_settings_schema, r411_image_display_contract, architecture_consolidation, phase28/28c, arch02b gallery), 8 × "B. environmental" (portal onboarding gallery/fidelity ×5, `refresh_rasti_mode_demo_visuals` ×2, `notifications.test_email_transport` import error), 1 × "C. parallel-only" (`sms.test_gateway_live.LiveProtocolTests` setUpClass). The four ids reported in Gate B did **not** fail.
* **Limits stated plainly:** two full runs (identical results) on one machine, SQLite only, one worker count (4), no PostgreSQL concurrency suite, no Firefox; 237 tests are skipped by design. "No failure outside the baseline observed" ≠ "no regression is possible"; the baseline itself contains 38 failing ids that are not mine to fix in this branch.

## 7. Other facts the gate needs

* Currency: Google/Open Graph output is `IRR` with Rial amounts (stored Toman × 10, via the cart's price authority, AggregateOffer for differing variant prices); stored prices untouched; inconsistent `IRT`/`TOMAN` *labels* remain in non-Google code.
* Ready to Publish ≠ Ready to Sell: publish prerequisites = base five (no payment); sell = + payment (unless inquiry-only).
* Disclosure: one read-only network call was made to `origin` (`git fetch --dry-run`) to check for newer refs; it changed nothing. No other network call to a repository; the full suites' only outbound attempt was the (proxy-blocked) leak that Gate B explained and fixed.

## 8. Gate state

| Gate | State |
|---|---|
| Destination | `origin` / `Rastisi6-14040616`, as decided (no other target added) |
| Working tree | clean |
| Migration | none created, none run, `makemigrations --check` clean |
| Failures outside baseline | none in 2 consecutive full runs (limits in §6) |
| Trackers / IndexNow in Production | off; enabling not permitted |
| **Push** | **NOT authorized — waiting for your separate explicit permission** (and, after it, a separate one for transferring to Windows QA) |
