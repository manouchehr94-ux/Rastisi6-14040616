# RastiSi — Canonical Architecture Knowledge System

```
status: CANONICAL
code_baseline: 5883a1404a8b0f1f245f0d8ef17ac5c13e40a7cb
last_verified_against_code: 5883a1404a8b0f1f245f0d8ef17ac5c13e40a7cb
source_phases: Phase 1 (code discovery) / Phase 2 (validation) / Phase 3 (doc inventory) / Phase 4 (reconciliation)
open_decisions: DR-1..DR-8 (see ARCHITECTURAL_DECISION_REGISTER.md)
```

> **Start here.** This is the primary navigation and current-architecture layer for RastiSi. A
> future engineer or coding agent should begin in this folder rather than searching the ~3,180
> files of historical documentation. Every claim here is grounded in verified code evidence from
> the frozen snapshot `5883a140` (Phase 1/2), with documented design intent and history kept
> explicitly separate.

---

## What is RastiSi?

RastiSi is a **multi-tenant SaaS storefront platform** built on Django 5.2 (Persian/RTL). One
Django project (`shop_core`) serves **three Host-partitioned surfaces**:

1. **Per-Store storefront + Merchant Admin** — `shop_core.urls` (default ROOT_URLCONF); the public
   storefront and the merchant dashboard at `/admin-portal/`.
2. **Marketing + Owner Portal** — `shop_core.urls_platform` (hosts in `RASTISI_PLATFORM_HOSTS`).
3. **Platform Admin** — `shop_core.urls_platform_admin` (hosts in `RASTISI_PLATFORM_ADMIN_HOSTS`).

The surface is chosen by `apps.portal.middleware.PlatformHostRoutingMiddleware`. The **tenant
boundary** is `apps.stores.Store`; `request.store` is resolved from the HTTP Host by
`apps.stores.resolution.resolve_store_for_hostname`. See [`SYSTEM_CONTEXT.md`](SYSTEM_CONTEXT.md).

Two deliberately separate "money" systems exist: **storefront money** (customer buys products:
`cart` → `orders`) and **platform money** (merchant pays RastiSi: `subscriptions` ↔ `billing`).

## What are its domains?

15 code-derived domains. Full map: [`DOMAIN_MAP.md`](DOMAIN_MAP.md). Per-domain deep packs:
[`../domains/`](../domains/).

15 code-derived domains. All 15 now have a **CANONICAL** Domain Knowledge Pack (Phase 6). The
"Phase-4 pre-pack readiness" column below is a **historical** finding recorded *before* those packs
existed — it does **not** describe the current documentation state. The "Current canonical pack"
column is the state now.

| ID | Domain | App | Phase-4 pre-pack readiness¹ | Current canonical pack² |
|---|---|---|---|---|
| D1 | Tenancy & Store identity | `stores` | READY | CANONICAL |
| D2 | Platform control & owner identity | `portal` | PARTIAL | CANONICAL |
| D3 | Customer identity & CRM | `customers` | POOR | CANONICAL |
| D4 | Catalog & inventory | `catalog` | PARTIAL | CANONICAL |
| D5 | Cart & pricing | `cart` | POOR | CANONICAL |
| D6 | Orders, checkout, payments (storefront money) | `orders` | PARTIAL | CANONICAL |
| D7 | SaaS subscriptions | `subscriptions` | PARTIAL | CANONICAL |
| D8 | SaaS billing | `billing` | PARTIAL | CANONICAL |
| D9 | Storefront presentation / builder | `storefront_builder` | CONFLICTED | CANONICAL |
| D10 | Content & navigation | `content` | POOR | CANONICAL |
| D11 | Merchant admin (controller) | `dashboard` | PARTIAL | CANONICAL |
| D12 | Messaging: SMS | `sms` | POOR | CANONICAL |
| D13 | Notifications | `notifications` | MISSING | CANONICAL |
| D14 | Shared / cross-cutting | `core` | PARTIAL | CANONICAL |
| D15 | Blog (near-dead) | `blog` | MISSING | CANONICAL |

¹ **Phase-4 pre-pack readiness** = the historical Phase-4 assessment of *documentation* readiness
measured **before** the Phase-6 canonical packs were authored (not code quality; not current state).
Preserved for the record. Totals (unchanged): READY 1 / PARTIAL 7 / POOR 4 / MISSING 2 /
CONFLICTED 1 = 15. Source:
[`../phase4_reconciliation/08_ARCHITECTURAL_DECISIONS_REQUIRED.md`](../phase4_reconciliation/08_ARCHITECTURAL_DECISIONS_REQUIRED.md) Part C.

² **Current canonical pack** = the present state of the domain's Architecture Knowledge System pack.
All 15 are **CANONICAL** (a Phase-6 pack exists at [`../domains/<app>/`](../domains/)). This is
**independent of code freshness** — every pack remains verified against baseline `5883a140` and may
still require a future delta audit against newer production code. A `MISSING`/`POOR`/`CONFLICTED`
value in column ¹ therefore does **not** mean documentation is missing today.

## Where do I start? (navigation)

| I want to… | Read |
|---|---|
| Understand the whole system at a glance | [`SYSTEM_CONTEXT.md`](SYSTEM_CONTEXT.md), [`DOMAIN_MAP.md`](DOMAIN_MAP.md) |
| Know which app owns a model | [`DATA_OWNERSHIP.md`](DATA_OWNERSHIP.md) |
| Know **who is allowed to mutate** an entity | [`MUTATION_AUTHORITY.md`](MUTATION_AUTHORITY.md) |
| See domain dependencies | [`DEPENDENCY_MAP.md`](DEPENDENCY_MAP.md) |
| Trace a runtime flow | [`RUNTIME_FLOW_INDEX.md`](RUNTIME_FLOW_INDEX.md) |
| Find a lifecycle/state machine | [`STATE_MACHINE_INDEX.md`](STATE_MACHINE_INDEX.md) |
| Understand transactions/locking/idempotency | [`TRANSACTION_AND_CONSISTENCY.md`](TRANSACTION_AND_CONSISTENCY.md) |
| See external providers (payment/SMS/DNS) | [`EXTERNAL_INTEGRATIONS.md`](EXTERNAL_INTEGRATIONS.md) |
| Understand trust/tenant boundaries | [`SECURITY_AND_TRUST_BOUNDARIES.md`](SECURITY_AND_TRUST_BOUNDARIES.md) |
| Find the tests for a behavior | [`TESTING_MAP.md`](TESTING_MAP.md) |
| **Change something and see what breaks** | [`CHANGE_IMPACT_GUIDE.md`](CHANGE_IMPACT_GUIDE.md) |
| Deep-dive one domain | [`../domains/<domain>/README.md`](../domains/) |
| Machine-readable domain data | [`architecture_registry.yaml`](architecture_registry.yaml) |

## Where do I go before changing a specific subsystem?

Every substantial domain has a `CHANGE_GUIDE.md` in its pack (e.g.
[`../domains/orders/CHANGE_GUIDE.md`](../domains/orders/CHANGE_GUIDE.md)). The cross-domain
entry point is [`CHANGE_IMPACT_GUIDE.md`](CHANGE_IMPACT_GUIDE.md).

## Which documents are current? Which are historical?

Authority is defined in [`DOCUMENTATION_AUTHORITY.md`](DOCUMENTATION_AUTHORITY.md). In short:
- **Current runtime truth** = the Phase 1/2 code-derived artifacts + this canonical layer.
- **Design intent / history** = the older `docs/**` corpus (mostly foundation-era 2026-07-28 and
  the storefront V2/R4 generations). It explains *why*, but **never overrides current code**.
- A document being named `FINAL`, `MASTER`, `SPEC`, `AUDIT`, or `PLAN` does **not** make it
  authoritative.

## Where are unresolved architecture decisions?

[`ARCHITECTURAL_DECISION_REGISTER.md`](ARCHITECTURAL_DECISION_REGISTER.md) — **DR-1…DR-8**, all
currently **OPEN**. They must not be resolved without explicit Product-Owner authorization.

## How do I find impact radius / model ownership / mutation authority / tests?

- Impact radius → [`CHANGE_IMPACT_GUIDE.md`](CHANGE_IMPACT_GUIDE.md) + the domain `CHANGE_GUIDE.md`.
- Model ownership → [`DATA_OWNERSHIP.md`](DATA_OWNERSHIP.md) + domain `DATA_MODEL.md`.
- Mutation authority → [`MUTATION_AUTHORITY.md`](MUTATION_AUTHORITY.md) + domain `MUTATION_AUTHORITY.md`.
- Tests → [`TESTING_MAP.md`](TESTING_MAP.md) + domain `TESTING.md`.

## Known architecture risks

[`KNOWN_ARCHITECTURE_RISKS.md`](KNOWN_ARCHITECTURE_RISKS.md) consolidates the Phase 1/2 findings:
HIGH (H1 duplicate order-payment + unguarded `payment_status`; H2 content mutation authority; H3
storefront generational layering), plus MEDIUM/LOW/OBSERVATION and the dead-code register.

## Highest-risk area to read first

**Orders/payments (`orders`)** is the gold-standard pack and the highest-risk domain. Read
[`../domains/orders/README.md`](../domains/orders/README.md) and its
[`CHANGE_GUIDE.md`](../domains/orders/CHANGE_GUIDE.md) before touching anything payment-related.
The single most important fact: **`Order.payment_status` has three writers and no transition
guard** (finding H1, decision DR-1).

---

## Canonical folder contents
```
canonical/
├── README.md                          ← this file
├── SYSTEM_CONTEXT.md                  ← the three surfaces, host routing, tenant boundary
├── DOMAIN_MAP.md                      ← 15 domains, clusters, ownership
├── DATA_OWNERSHIP.md                  ← model → owning domain
├── MUTATION_AUTHORITY.md              ← WHO MUTATES WHAT (canonical/secondary/direct/cross-domain)
├── DEPENDENCY_MAP.md                  ← typed cross-domain dependencies
├── RUNTIME_FLOW_INDEX.md              ← index of 15 reconstructed flows
├── STATE_MACHINE_INDEX.md             ← every lifecycle/status machine + guard status
├── TRANSACTION_AND_CONSISTENCY.md     ← atomicity/locking/idempotency
├── EXTERNAL_INTEGRATIONS.md           ← payment/SMS/DNS/email/turnstile
├── SECURITY_AND_TRUST_BOUNDARIES.md   ← tenancy isolation, auth surfaces, is_staff overloading
├── TESTING_MAP.md                     ← behavior → tests
├── ARCHITECTURAL_DECISION_REGISTER.md ← DR-1..DR-8 (OPEN)
├── KNOWN_ARCHITECTURE_RISKS.md        ← H/M/L/OBS findings + dead-code register
├── DOCUMENTATION_AUTHORITY.md         ← the 5-level authority hierarchy
├── CHANGE_IMPACT_GUIDE.md             ← change-oriented navigation (Phase 7)
├── architecture_registry.yaml         ← machine-readable domain registry
└── graphs/                            ← canonical Mermaid graphs
```

## Freshness & authority note
This canonical layer is verified against code baseline `5883a140`. If the production code advances
past that commit, a delta re-verification is required before treating these documents as current.
The `code_baseline` / `last_verified_against_code` metadata at the top of each canonical and
domain document records this explicitly.
