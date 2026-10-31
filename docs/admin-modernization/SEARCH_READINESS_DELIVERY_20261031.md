# RastiSi — Store launch, domain flow, Technical SEO and AI-search readiness (delivery report)

> **Superseded in part by `PRE_PUSH_GATE_20261031_B.md`** (currency, tracker default, ready-to-publish vs ready-to-sell, IndexNow host check, push destination).

Branch `feature/admin-panel-modernization-20261029` · base `1e1d140b4d6a83b688b0570a6befaf7b47841718` · **local commits only — nothing pushed, merged, deployed, migrated or backfilled.**

## A. Git status

| # | SHA | Subject |
|---|---|---|
| 1 | `4453880e` | Technical SEO: one indexability policy, canonical origin, safe JSON-LD from real data, AI-crawler policy |
| 2 | `c2688bc6` | Setup checklist: required vs optional, honest states, five goal groups, one primary action |
| 3 | `6d64e134` | Connect a custom domain from the seller panel itself |
| 4 | `e90e72ed` | Honest integrations page, analytics snippets on public pages, IndexNow |

* **Migrations: none created, none run.** No model changed (`makemigrations --check` is clean for this work). Nothing was backfilled.
* No push. The canonical remote named in CLAUDE.md is `rastisi5`; this clone only has `origin`, and the only push ever approved was an explicit one to `origin` earlier.
* Nothing in the Windows worktree, the QA database of port 8008, Production or RastiService was touched. The 8009 server used for screenshots reads the disposable copy in this worktree.

## B. Real-code audit (the QA report was not trusted) — gap table

| Area | What the code really did | Gap | Action |
|---|---|---|---|
| Setup checklist | 20 steps, optional/locked/skipped steps could render as «done»; progress counted everything | Dishonest | Rewritten: 21 steps, **10 required**; per-step state (done / ready / blocked / optional / needs_action / processing / needs_fix); 5 goal groups; one primary action; progress counts required only; «automatic» steps reported; sample data cannot satisfy a real-sale condition |
| Custom domain step | «done» when a domain row existed | Wrong | Done only when verified + DNS connected + HTTPS ready + active primary; in-progress states say who must act |
| Domain page | Read-only; sent the seller to the owner portal | Seller had to leave the panel | In-panel add / start verification / check TXT / check DNS+HTTPS, one primary action per state, copyable records, same domain service |
| robots / sitemap | robots allowed everything on any host; sitemap built on request host | Test hosts and unpublished stores were crawlable | One `seo_policy`: non-public host or unpublished store ⇒ `Disallow: /`, no sitemap (404), noindex meta |
| Canonical / og:url | Request host | Wrong after a domain change | Store's preferred public origin |
| Structured data | None | — | Store/WebSite/Organization, Product/Offer, BreadcrumbList from real data only; script-safe |
| AI crawlers | Not addressed | — | Search bots ≠ training bots; training bots disallowed by platform setting; no `llms.txt` dependency |
| Integrations page | Said «متصل و فعال» for GA4/GTM/pixel/Torob/eNamad but **nothing read those ids** | Fake «connected» | GA4/GTM/Meta pixel now really load on public pages; Torob and eNamad are labelled «only stored — not shown or sent yet» |
| Search Console / Bing / Merchant | Absent | Need accounts | Listed as «not available yet», manual Search Console guidance, IndexNow ready but off |

## C. Setup checklist

* Before: 20 steps, all counted, optional ones could show done. After: 21 steps, 10 required (`industry`, `industry_template`, `product_groups`, `product_categories`, `first_product`, `shipping`, `publish`, `product_publish`, `store_info`, `payment_gateway`).
* **Ready-to-sell criterion** = all required steps really done (`sell_blockers` lists what is left); `ready_to_publish` and `is_live` are separate facts.
* Optional steps (brands, attributes, images, variants, inventory, tax, logo, theme, contact, custom domain, search visibility) never count toward progress and are never shown «done» unless truly done.
* Idempotent: computed live from real data, nothing stored. Legacy keys (`completed_count`, `total_count`, `percent`) kept.

## D. Domain — who does what

| Who | Does |
|---|---|
| RastiSi (automatic) | Normalises/validates the hostname, creates the record, generates the TXT token, shows exact records, runs DNS/HTTPS checks, keeps audit, refuses duplicates |
| Seller | Types the domain; copies the TXT then the A/CNAME records into their registrar (the only thing no software can do for them); presses «check» |
| Seller, one confirmation | Final activation (Step-Up with fresh confirmation) in the owner portal — deliberately not moved into the panel |

Flows: (1) **free RastiSi address** — nothing to do, already live after publish; (2) **custom domain** — add → TXT → check → A/CNAME → DNS+HTTPS check → activate.
Security: one store per hostname (anti-hijack, unique constraint + service check); lookups scoped to the request's Store (another store's id ⇒ 404); `DOMAIN_MANAGE` permission; POST-only + CSRF; every action audited; **IP literals refused** (new, found by a test: an IP can never prove ownership and the routing/TLS probes must not be aimed at arbitrary addresses); RastiSi-owned names refused; DNS/TLS only inside the existing service (mocked in tests). No token for other stores is ever rendered.
**Domain-change SEO safety (M7):** canonical/sitemap/structured data use `resolve_storefront_url_for_store`, so they move to the new host only when it becomes the active primary; the permanent redirect from the RastiSi address only exists for a *verified primary* custom domain and activation requires DNS+HTTPS readiness — no 301 before readiness.

## E. SEO and AI-search details

* Indexability: public host + published store ⇒ indexable; otherwise robots `Disallow: /`, sitemap 404, `noindex,nofollow`. Private paths (`/cart/ /checkout/ /account/ /admin*`) always disallowed. Filtered/sorted listings are `noindex,follow`; category listing keeps `?category=` in the canonical.
* Sitemap: only public pages of that Store, on the canonical origin; no cross-store URLs.
* JSON-LD: no invented rating/review/stock/shipping. *Known business risk:* `priceCurrency` is currently `IRT` (not ISO 4217; `IRR` is the code and units differ) — unchanged, needs a business decision.
* AI: `OAI-SearchBot`, `ChatGPT-User`, `PerplexityBot` etc. are never named/blocked; `GPTBot`, `Google-Extended`, `CCBot`, `ClaudeBot`, `anthropic-ai`, `Applebot-Extended`, `Bytespider` disallowed unless `RASTISI_AI_TRAINING_CRAWLERS=allow`. It is a **platform** setting — a per-store toggle needs a field (migration, see §G). No wording promises ranking, indexing or AI citation.
* Analytics: GA4 / GTM / Meta pixel ids load only on indexable public pages of the owning store; ids re-validated by strict regex at render; no seller HTML/JS accepted.
* IndexNow (`apps/core/indexnow.py`, command `indexnow_submit`): key derived by HMAC (no storage, nothing secret), key file `/<key>.txt` served only on that store's public host, payload limited to the store's own host (≤10 000), bounded retry with backoff on 429/5xx, 403/422 final, injectable transport, dry-run default, disabled unless `RASTISI_INDEXNOW_ENABLED`. Google does not use IndexNow; no Sitemap-ping or Indexing-API misuse.
* Google Search Console: needs the seller's Google account → shown as manual guidance, not as a connection.

## F. Tests (see section "Results" below for the final numbers)

New: `test_seo_policy_and_structured_data` (19), checklist tests (updated + new), `test_domain_panel_actions` (17), `test_tracking_indexnow_visibility` (19), `test_integrations_visibility_page` (6). Updated intentionally: `test_domain_settings::test_page_has_no_write_form` → manager form / non-manager no form; `test_m4_domain_summary` banner test → one add-form only for managers.
Tenancy/security covered: permission matrix for all four actions, anonymous, GET 405, CSRF 403, other store's domain 404 with no service call, duplicate hostname refused, invalid/IP/platform hostnames refused, other store's analytics ids never rendered, tracking absent on local/unpublished hosts, malformed stored ids render nothing, key file only for the owning host, IndexNow disabled/not-public never calls the transport, secret-flagged field never echoed.

## G. Needs your permission / decision (nothing done)

1. **Proposed migration (not created):** `StoreSearchSettings` (OneToOne Store: `ai_training_allowed`, `indexnow_enabled`, `google_verification_token`, `bing_verification_token`) and `SearchSubmission` queue (store, engine, url_hash, status, attempts, next_attempt_at, last_http_status; unique pending per store+engine+url_hash). Purpose: per-store AI-crawler choice, durable post-publish retries, status shown to the seller. Today post-publish notification = the command run by a scheduler; publish never depends on it.
2. Enable `RASTISI_INDEXNOW_ENABLED` in Production (a platform-owner decision; QA stays off).
3. Decide the structured-data currency (`IRT` vs `IRR` with correct amount).
4. Torob feed, Merchant Center feed, eNamad badge per store, Search Console / Bing account connection are *not built*: they need either an official contract or the seller's credentials.
5. Remote: confirm `origin` vs `rastisi5` before any push.

## H. Windows QA scenario (after you approve delivery)

A. New store → dashboard shows required-only progress, «ready to sell» false with blockers listed. B. Add a custom domain from «دامنه و آدرس» → «شروع تأیید» → TXT with copy buttons → no real DNS needed to see the states (do **not** point real domains). C. Integrations: save a GA4 id → badge says «waits for publish» on the local host; Torob/eNamad say «only stored». D. `/robots.txt` and `/sitemap.xml` on the local host: closed / 404. E. Publish on a real host in staging: robots with sitemap, JSON-LD in page source (view-source). F. `python manage.py indexnow_submit --store <slug>` prints a dry-run only.

## Results (final HEAD, SQLite, `manage.py test --parallel 4`)

| Run | Tests | Failures | Errors | Skipped |
|---|---|---|---|---|
| Full suite #1 (before the fixes below) | 11 966 | 37 | 4 | 237 |
| Full suite #2 (HEAD `4f00c6d2`) | 11 966 | 37 | 5 | 237 |

* Run #1 exposed **three real regressions caused by this work**, all fixed in `4f00c6d2` and re-verified: (1) the SEO/tracking context processors ran queries on every admin page (settings page 28 > 26 queries) → made lazy; (2) the new checklist used `data-group=` which the sidebar test forbids → `data-goal-group`; (3) the dashboard contract test read markup that moved into the partial → test now asserts the honest model. Those 3 pass in run #2.
* Everything left in run #2 is in the pre-existing baseline of `TEST_RECONCILIATION_20261029.md` (storefront_builder V2 family contracts, onboarding gallery, demo-refresh command, `notifications.test_email_transport` import error, `sms.test_gateway_live` setUpClass — all environmental/pre-existing), **except four parallel-only flakes** (`test_simultaneous_upload_and_remove_replacement_wins` and three `test_legacy_sms_integration.LegacyHistoryMirrorTests`) that failed in only one of the two full runs and pass when run alone (33 tests OK) — same class as the known parallel-only `test_product_image_*` flake.
* Not run: PostgreSQL concurrency suite for this work (no new locking/concurrency code was added; domain creation keeps the existing unique constraint), Firefox (Chromium only for screenshots at 1440 and 390: no horizontal scroll, no console errors).
* Screenshots taken from the disposable 8009 server: domain page (empty/added/pending, desktop+mobile) and integrations page (desktop+mobile).
* One bug found by looking at the screenshot, not by a test, and fixed: the domain status line rendered a Python dict (`routing` key collision) → renamed to `routing_records`, regression test added.
