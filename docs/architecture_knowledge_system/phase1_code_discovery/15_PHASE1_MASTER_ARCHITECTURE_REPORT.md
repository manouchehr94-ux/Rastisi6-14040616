# 15 — Phase 1 Master Architecture Report

**System:** Rastisi — a multi-tenant SaaS storefront platform (Django 5.2, Persian/RTL).
**Phase:** 1 — Code-First Architecture Discovery (code only; existing docs excluded).
**Governing document:** `docs/architecture_knowledge_system/00_GOVERNING_RULES_AND_PHASE1.md`.

This report consolidates docs 00–14 and the seven Mermaid graphs. It records **what the current
code actually does**, with evidence classifications. It does **not** propose a future
architecture (governing rule §26) and does **not** reconcile against existing documentation
(that is a later phase).

---

## Part A — Freeze record (governing rule §27)

```
source_commit: 5883a1404a8b0f1f245f0d8ef17ac5c13e40a7cb   (production code audited)
branch: docs/architecture-knowledge-system
branch_start_HEAD: 1bc347404194067c529652c0a56a6c1210b4c092
branch_end_HEAD:   6e88c2c41448b2a7b6a73fb89bfb57e183b78147   (the single Phase 1 artifact commit)
discovery_completed_at: 2026-09-23 (session date)
existing_docs_used_for_architecture_discovery: NO
```

**Source-freeze note:** the branch HEAD differs from the audited production snapshot `5883a140`
by exactly one documentation-only commit (the governing document). `git diff 5883a140 HEAD`
returns only `docs/architecture_knowledge_system/00_GOVERNING_RULES_AND_PHASE1.md`. **No
production code differs**, so this report faithfully describes commit `5883a140`. No newer
production code was incorporated.

---

## Part B — System overview (VERIFIED)

One Django project (`shop_core`) serves **three Host-partitioned surfaces**, selected by
`apps.portal.middleware.PlatformHostRoutingMiddleware` setting `request.urlconf`:

1. **Per-Store storefront + Merchant Admin** — `shop_core.urls` (fallback ROOT_URLCONF).
2. **Marketing + Owner Portal** — `shop_core.urls_platform` (hosts in `RASTISI_PLATFORM_HOSTS`).
3. **Platform Admin** — `shop_core.urls_platform_admin` (hosts in `RASTISI_PLATFORM_ADMIN_HOSTS`).

The **tenant boundary** is `apps.stores.Store`. `request.store` is set on every request by
`StoreResolutionMiddleware` via `apps.stores.resolution.resolve_store_for_hostname` (the sole
authoritative Host→Store resolver); a separate resolver handles admin subdomains. Store
ownership is modeled exclusively via an active `StoreMembership` with `role=OWNER` (no `owner`
field). Two deliberately separate "money" systems exist: **storefront money** (cart→orders) and
**platform money** (subscriptions↔billing), with separate payment-attempt, provider, and refund
models.

Scale: 16 apps, ~213,934 production Python LOC (excl. migrations), 145 service files, 8,665 test
functions, 34 management commands, **0 Django signals** (deliberate explicit-coupling design;
side effects via service calls + `transaction.on_commit`).

---

## Part C — Discovered domains (governing rule §29.11)

| # | Domain | App | One-line responsibility |
|---|---|---|---|
| D1 | Tenancy & Store identity | `stores` | Store lifecycle, membership/roles, domains, Host→Store resolution, authorization |
| D2 | Platform control & owner identity | `portal` | Platform config singleton, owner/staff auth+OTP, host routing, provisioning, platform admin |
| D3 | Customer identity & CRM | `customers` | Global shopper account, per-Store CRM, segments, auth, cart merge |
| D4 | Catalog & inventory | `catalog` | Products/variants/categories/collections, ledgered inventory, industry templates |
| D5 | Cart & pricing | `cart` | Cart, coupons, gift wrap, checkout token |
| D6 | Orders, checkout, payments (storefront money) | `orders` | Order state machine, two payment implementations, refunds/returns, shipping/tax config |
| D7 | SaaS subscriptions (entitlements) | `subscriptions` | Canonical StoreSubscription state machine, plans, entitlements |
| D8 | SaaS billing (invoicing/payment) | `billing` | Invoices, billing payments, webhooks, dunning, renewals, refunds |
| D9 | Storefront presentation/builder | `storefront_builder` | Versioned draft/publish layout, R4 editor, A8 templates, appearance registries |
| D10 | Content & navigation | `content` | CMS pages, menus, footer, media, section-scoped placements |
| D11 | Merchant admin (controller) | `dashboard` | Auth-gated orchestration/CRUD over other domains (no models) |
| D12 | Messaging: SMS | `sms` | Templates/events, credits, backends, device gateway, OTP |
| D13 | Notifications | `notifications` | Persistent multi-channel outbox |
| D14 | Shared/cross-cutting | `core` | ShopSettings, base model, audit, export/import, SEO, utilities |
| D15 | Blog (near-dead) | `blog` | Admin-only BlogPost; no urls/views |

---

## Part D — Master ownership matrix (governing rule §25)

| Concept / Entity | Probable canonical owner | Other writers | Main readers | Main entry points | Risk |
|---|---|---|---|---|---|
| **Order.status** | `order_service.change_order_status` | (none direct; all funnel here) | dashboard, storefront | checkout, dashboard order_detail | LOW |
| **Order.payment_status** | `gateway_payment_service` (intended) | `payment_service.simulate_payment`, `refund_service` | dashboard, receipts | gateway callback, simulation callback, refund | **HIGH** (3 writers, no transition table) |
| **PaymentAttempt** | `gateway_payment_service` | — | dashboard | gateway callback | LOW |
| **Transaction (legacy)** | AMBIGUOUS | simulate + gateway back-compat | dashboard | both payment paths | MEDIUM |
| **CartItem / Cart** | `cart_service` | orders (reprice/delete), customers (merge) | storefront, checkout | cart/checkout views | MEDIUM (cross-domain) |
| **Coupon.used_count** | AMBIGUOUS (written by orders) | `order_service.create_order_from_cart` | pricing | checkout | LOW-MED |
| **StoreSubscription.status** | `subscription_service` | billing (funneled), plan_change override | dashboard banner, publication | webhook, cron, admin | MEDIUM (co-owned by billing) |
| **SubscriptionInvoice.status** | `invoice_service` | confirmation, dunning, refund, payment_flow | admin, portal | webhook, cron, admin | MEDIUM |
| **Product** | catalog services | dashboard views (direct), import, template install | storefront, dashboard | dashboard, import, provisioning | MEDIUM |
| **stock** | `catalog.inventory_service` (ledgered) | — | catalog, orders | orders, dashboard, import | LOW |
| **ShopSettings** | `core` (model) | dashboard views (direct), sms_service | pricing, context procs, checklist | dashboard settings, onboarding | MEDIUM |
| **content.* (pages/menus/footer/media)** | AMBIGUOUS (no content write service) | dashboard views (direct), storefront_builder (media clone) | storefront shell, render | dashboard content views | **HIGH** |
| **Shipping/Tax/GatewayConfig** | `orders` (model) | dashboard views (direct) | checkout, dashboard | dashboard settings | MEDIUM |
| **StorefrontLayoutVersion / Sections** | `layout_service` + `r4_mutation_service` | legacy views (fail-closed), preset_service | render_service, storefront | R4 editor, legacy editor | MEDIUM |
| **Store (status/onboarding/deletion)** | `store_status_service`/`deletion_service`/provisioning | platform_admin_views, Store.save fallbacks | resolution, publication | portal, platform admin, cron | MEDIUM |
| **StoreMembership** | `membership_service` | `ownership_transfer_service.accept`, provisioning | authorization, dashboard gate | portal, dashboard, provisioning | MEDIUM (2 transfer impls) |
| **StoreDomain (verification)** | `domain_verification_service` | handle_service, provisioning, platform admin | resolution, canonical redirect | portal domains, platform admin | MEDIUM |
| **Customer / auth User** | `customers.auth_service` / `owner_auth_service` | `membership_service.add_staff_member` | everywhere | portal, storefront, platform admin | MEDIUM (`is_staff` overloaded) |
| **SMS (SmsLog/credits/outbox)** | `sms_service._dispatch` | gateway_views (device poll/ack) | dashboard SMS | orders/customers on_commit, device | LOW |
| **NotificationOutbox** | `notification_service` | — | delivery command | stores services | LOW |

`AMBIGUOUS_OWNERSHIP` full list in doc 14 §1.

---

## Part E — Findings by severity (governing rule §29.16)

| Severity | Count | IDs (doc 12) |
|---|---:|---|
| CRITICAL | 0 | — (see H1 rationale) |
| HIGH | 3 | H1 (duplicate order-payment + unguarded payment_status), H2 (content has no write service), H3 (three storefront editor generations coexist) |
| MEDIUM | 15 | M1–M15 |
| LOW | 4 | L1–L4 |
| OBSERVATION | 4 | O1–O4 |

**Top risks to inspect before any change:**
1. `Order.payment_status` — 3 writers, no transition table (doc 06 §2, doc 09 §2, doc 12 H1).
2. `content.*` mutation lives entirely in `dashboard/views.py` (doc 12 H2).
3. Storefront editor generational layering R3/R4/A8 (doc 12 H3).

---

## Part F — Potentially dead / orphaned (governing rule §29.17)

- **D1 `apps/blog`** — POTENTIALLY_DEAD storefront wiring (admin-only model; no urls/views).
- **D3 `membership_service.transfer_ownership`** — POTENTIALLY_DEAD relative to OTP flow (unconfirmed).
- **D4 `ShopSettings` legacy SMS fields** — POTENTIALLY_DEAD data (superseded by PlatformConfiguration).
- **D5 removed `family_registry.py`/`preset_registry.py`** — confirmed absent; only doc/test references.
- **D6 `resolution.require_resolved_store`** — possibly unused scaffolding (unconfirmed).
- **D7 reserved authorization permission keys** — inert forward-design.
- **D8 content MED-001 media-cleanup functions** — live-but-inert no-ops.

Corrected non-dead items: PAYMENT_SUCCESS/FAILED SMS (live) and notification enqueue callers
(live in `stores` services). Full detail in doc 13.

---

## Part G — Ambiguous ownership & unknowns (governing rule §29.18–19)

Ambiguous ownership (doc 14 §1): Store vs Vendor; footer (×3); "page" (×2); order gateway (×2);
ShopSettings write authority; subscription lifecycle (subscriptions vs billing); storefront write
surface (R3 vs R4); ownership transfer (×2); section placement (×3).

Major unknowns (doc 14 §2): R4 editor JS endpoints; live caller of `membership.transfer_ownership`;
`require_resolved_store` consumers; several smaller service bodies (INFERRED responsibilities);
individual test assertions; external reliance on the simulation payment path; Vendor's live role.

---

## Part H — State machines summary (doc 09)

Guarded by explicit `ALLOWED_TRANSITIONS` table: **Order.status**, **ReturnRequest.status**,
**StoreSubscription.status**, **WarehouseTransfer**. Guarded per-service (no table):
SubscriptionInvoice.status, Store.status, StorefrontLayoutVersion.status, StoreDomain lifecycle
(also DB CheckConstraints), PaymentAttempt (is_final). **Unguarded: `Order.payment_status`**
(the key defect). Derived "store visibility" spans ≥5 signals across 3 apps and fails open.

---

## Part I — Transaction/consistency summary (doc 10)

Strong: order creation (membership-fence locks + idempotency), gateway callback (re-lock +
conditional update), all subscription transitions and billing services (`select_for_update` +
idempotency + webhook dedup + race-safe numbering), provisioning (single atomic across 4 apps).
Weak: `simulate_payment` (no Order lock, prod-gated), `refund_service` (no Order lock),
`content.*` writes (no service/transaction boundary). Read-only consistency-verification commands
exist for billing/subscriptions/inventory/domains.

---

## Part J — Test coverage (governing rule §29.20; doc 11)

8,665 test functions; heaviest suites in storefront_builder (~61k LOC) and dashboard (~17.5k LOC),
with strong recurring themes of **multi-tenant isolation** and **permission enforcement**. Apparent
gaps: no single `Order.payment_status` transition-legality test; no content-domain service test
suite (no such service); minimal blog tests; R4 client JS untested directly.

---

## Part K — Final Phase 1 report (governing rule §29)

1. **Branch name:** `docs/architecture-knowledge-system`
2. **Starting SHA:** `1bc347404194067c529652c0a56a6c1210b4c092`
3. **Ending SHA:** `6e88c2c41448b2a7b6a73fb89bfb57e183b78147` — a single commit adding only the
   Phase 1 artifacts under `docs/architecture_knowledge_system/phase1_code_discovery/`
   (this SHA-correction note itself is folded into a follow-up commit on the same branch).
4. **`git status --short` (before commit):** only `?? docs/architecture_knowledge_system/phase1_code_discovery/`
   (all new, untracked).
5. **`git diff --stat` (tracked files):** empty — no tracked file modified.
6. **`git diff --name-only` (tracked files):** empty.
7. **Files created:** the artifact set below (Part L).
8. **Files modified:** none (all created files are new; no pre-existing file changed).
9. **No production code changed:** CONFIRMED — `git status --short apps/ shop_core/ templates/ static/`
   is empty; migrations and tests untouched.
10. **Existing documentation not used as architecture source:** CONFIRMED — only the governing
    document was read; no other `docs/**` file was opened for discovery.
11. **Discovered domains:** 15 (Part C).
12. **Important models mapped:** ~70+ across 16 apps (doc 03 enumerates the significant ones).
13. **Mutation sites mapped:** 19 entity groups with per-writer classification (doc 06).
14. **Entry points mapped:** 3 URLconfs, 6 route groups + dashboard/portal/platform-admin route
    families, 4 webhook/device callbacks, 34 management commands, admin actions, 0 signals,
    6 on_commit hook sites (doc 05).
15. **Major runtime flows reconstructed:** 15 (doc 08, Flows 0–14).
16. **Architecture-smell findings by severity:** 0 CRITICAL / 3 HIGH / 15 MEDIUM / 4 LOW / 4 OBSERVATION (Part E).
17. **Potentially dead/orphaned findings:** 8 (Part F / doc 13).
18. **Ambiguous-ownership findings:** 9 (Part G / doc 14 §1).
19. **Major unknowns:** 9 (doc 14 §2).
20. **Test coverage gaps discovered:** payment_status transition legality; content-service tests;
    blog; R4 JS (Part J / doc 11 §7).
21. **Validation commands run:**
    - `git branch --show-current`, `git rev-parse HEAD`, `git status --short`,
      `git merge-base --is-ancestor 5883a140 HEAD`, `git diff --name-only 5883a140 HEAD`
    - `wc -l` / `find` for LOC + service/command counts; `grep -c "def test_"` (8,665)
    - `grep` verification of: `Order.payment_status` writers; `ALLOWED_TRANSITIONS` locations;
      `transaction.on_commit` senders; `@receiver`/signal usage (none); `send_event_sms`/PAYMENT
      SMS callers; management commands; admin actions; blog urls
22. **Limitations preventing full verification:** ~214k LOC not exhaustively read (high-risk paths
    read in depth, others characterized from signatures/callers); JS not read; RTL content defeated
    ripgrep in places; existing docs excluded by design. Full list in doc 14 §4.

---

## Part L — Phase 1 artifact set

```
docs/architecture_knowledge_system/phase1_code_discovery/
├── 00_PHASE1_EXECUTION_RECORD.md
├── 01_REPOSITORY_STRUCTURE.md
├── 02_DOMAIN_DISCOVERY.md
├── 03_MODEL_OWNERSHIP.md
├── 04_SERVICE_AND_CALL_MAP.md
├── 05_ENTRY_POINTS.md
├── 06_MUTATION_MAP.md
├── 07_DEPENDENCY_MAP.md
├── 08_RUNTIME_FLOWS.md
├── 09_STATE_MACHINES.md
├── 10_TRANSACTION_AND_CONSISTENCY.md
├── 11_TEST_MAP.md
├── 12_ARCHITECTURE_SMELLS.md
├── 13_POTENTIALLY_DEAD_OR_ORPHANED.md
├── 14_AMBIGUITIES_AND_UNKNOWNS.md
├── 15_PHASE1_MASTER_ARCHITECTURE_REPORT.md   (this file)
└── graphs/
    ├── system_context.mmd
    ├── domain_map.mmd
    ├── domain_dependencies.mmd
    ├── model_relationships.mmd
    ├── service_dependencies.mmd
    ├── mutation_graph.mmd
    └── major_runtime_flows.mmd
```

---

## Part M — STOP

Phase 1 is complete. Per governing rules §28–§32, this phase **STOPS here**. It does not begin
documentation reconciliation, remediation, or redesign, and does not start Phase 2 or any later
phase without explicit approval. The central distinction is preserved:

> **WHAT THE CODE DOES** (this report) ≠ **WHAT OLD DOCUMENTATION SAYS** ≠ **WHAT THE FUTURE
> ARCHITECTURE SHOULD BE**.
