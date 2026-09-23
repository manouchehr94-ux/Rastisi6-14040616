# Phases 5–7 Master Report — Canonical Architecture Knowledge System

**System:** RastiSi — multi-tenant SaaS storefront platform (Django 5.2, Persian/RTL).
**Branch:** `docs/architecture-knowledge-system` (used exclusively; no switch/merge/rebase).
**Scope of this report:** STEP 0 (final bookkeeping repairs) + Phase 5 (canonical layer) +
Phase 6 (15 domain knowledge packs) + Phase 7 (change navigation) + documentation validation.

> This report is the completion record for building the **canonical Architecture Knowledge
> System**. Per instructions, work **STOPS** after this report. No archival, remediation, DR
> resolution, Domain Knowledge Pack creation beyond these, or production-code change was performed.

---

## 1. Frozen production baseline
```
audited_production_snapshot: 5883a1404a8b0f1f245f0d8ef17ac5c13e40a7cb
branch:                      docs/architecture-knowledge-system
```
Production code is **identical** to the frozen snapshot throughout:
`git diff --stat 5883a140 HEAD -- apps/ shop_core/ templates/ static/` is empty. Every canonical/
domain claim is grounded in Phase 1/2 code evidence at `5883a140`.

## 2. STEP 0 — final bookkeeping repairs (commit `6ec9194c`)
- **0A — DR counts made explicit.** Distinguished **6** claim-level `decision_required=YES` flags
  (in `phase4_reconciliation/01_CLAIM_RECONCILIATION_MATRIX.csv`) from the **8**-item DR register
  (DR-1…DR-8). Corrected Phase 4 execution record, doc 08 Part A, doc 11 master, and the Phases 2–4
  master report.
- **0B — domain-readiness totals corrected to sum to 15.** `D10 Content` reclassified from
  "POOR/MISSING" to **POOR**; the seven PARTIAL domains enumerated explicitly
  (D2 portal, D4 catalog, D6 orders, D7 subscriptions, D8 billing, D11 dashboard, D14 core).
  Totals: **READY 1 / PARTIAL 7 / POOR 4 / MISSING 2 / CONFLICTED 1 = 15.**

## 3. Phase 5 — Canonical Architecture Knowledge Layer (commit `34e38188`)
Created `docs/architecture_knowledge_system/canonical/` — the primary navigation + current-
architecture layer (21 files incl. graphs). Every file has verified content; no empty placeholders.

**Canonical files:** `README.md` (navigation — answers "what is RastiSi / domains / where to start /
which docs are current / where are unresolved decisions / how to find impact-radius/ownership/
mutation/tests"), `SYSTEM_CONTEXT.md`, `DOMAIN_MAP.md`, `DATA_OWNERSHIP.md`, `MUTATION_AUTHORITY.md`,
`DEPENDENCY_MAP.md`, `RUNTIME_FLOW_INDEX.md`, `STATE_MACHINE_INDEX.md`,
`TRANSACTION_AND_CONSISTENCY.md`, `EXTERNAL_INTEGRATIONS.md`, `SECURITY_AND_TRUST_BOUNDARIES.md`,
`TESTING_MAP.md`, `ARCHITECTURAL_DECISION_REGISTER.md`, `KNOWN_ARCHITECTURE_RISKS.md`,
`DOCUMENTATION_AUTHORITY.md`, `CHANGE_IMPACT_GUIDE.md`, `architecture_registry.yaml`, + `graphs/`.

Every canonical/domain document carries freshness metadata (`status: CANONICAL`, `code_baseline`,
`last_verified_against_code`, `source_phases`, `open_decisions`) and distinguishes **CURRENT CODE
REALITY / DOCUMENTED DESIGN INTENT / HISTORICAL / UNRESOLVED DECISION**.

### Phase 5A — machine-readable registry
`canonical/architecture_registry.yaml` — all **15 domains** with the full schema (id/name/app/
responsibility/status/code_roots/owned_models/owned_services/entry_points/reads/writes/upstream+
downstream dependencies/external_integrations/state_machines/critical_invariants/mutation_authorities/
cross_domain_writers/tests/canonical_docs/historical_docs/known_risks/unresolved_decisions) plus an
`open_decisions` block (DR-1…DR-8). Uses exact code paths/symbols; `UNKNOWN` where evidence is
genuinely missing. Validated: 15 domain IDs, 8 DR entries, no tabs.

### Phase 5B — documentation authority model
`canonical/DOCUMENTATION_AUTHORITY.md` — 5-level hierarchy (L1 code+tests at `5883a140`; L2 this
knowledge system; L3 ADR/design-intent; L4 supporting/QA evidence; L5 historical/superseded),
conflict-resolution rules, and the explicit statement: **a document named FINAL/MASTER/SPEC/AUDIT/
PLAN is not thereby authoritative** (with concrete examples).

### Phase 5C — architectural decision register
`canonical/ARCHITECTURAL_DECISION_REGISTER.md` — **DR-1…DR-8 carried forward, all OPEN**, each with
Problem / Current code reality / Existing design intent / Why needed / Affected domains /
Affected models-services / Risk if ignored / Options identified / Required evidence / Status: OPEN.
**No decision was resolved.**

## 4. Phase 6 — Domain Knowledge Packs (commits `66f65d45` … `2c78d104`)
`docs/architecture_knowledge_system/domains/` — one directory per domain, all **15** present, each
with a canonical `README.md` and applicable documents. Non-applicable categories are recorded in the
domain README rather than created as empty files. **No meaningless empty files** (validated).

| # | Domain (app) | Docs | Notes |
|---|---|---:|---|
| D6 | **orders** ★ gold-standard | 20 | Full doc set + CHANGE_GUIDE with all required payment recipes |
| D9 | storefront_builder | 17 | `GENERATIONS.md` de-conflicts R3/R4/A8 |
| D8 | billing | 16 | SaaS money; verified idempotent inbox |
| D1 | stores | 15 | tenant boundary (READY) |
| D10 | content | 15 | H2 documented; no fake service |
| D4 | catalog | 14 | 38 models / inventory ledger |
| D7 | subscriptions | 13 | canonical state machine |
| D2 | portal | 13 | platform control + identity |
| D3 | customers | 12 | global Customer + CRM |
| D11 | dashboard | 12 | controller (no models) |
| D12 | sms | 12 | send funnel + device gateway |
| D5 | cart | 11 | cart/pricing |
| D14 | core | 11 | cross-cutting |
| D13 | notifications | 9 | small outbox (proportionate) |
| D15 | blog | 1 | near-dead (proportionate) |

**Total domain-pack files: 191.**

### Domain-pack quality checks (the 18 mandatory questions)
Each substantial pack answers, without repository-wide rediscovery: what it owns / does NOT own /
models / canonical services / non-domain writers / callers / callees / entry points / state machines
/ invariants / transaction guarantees / external services / trust boundaries / tests / smells /
open DRs / historical docs / read-before-changing. Verified by construction across the packs;
`CHANGE_GUIDE.md` present for every substantial domain (task-oriented, non-boilerplate).

### Orders / payments gold-standard result
The `orders` pack (20 docs) covers every mandated item: Order, `Order.status`, **`Order.payment_status`
(3 writers, no guard — H1)**, PaymentAttempt, legacy Transaction, PaymentGateway, PaymentGatewayConfig,
gateway initiation, callback/verification, COD, simulation path, refund path, return flow, transition
ownership, idempotency, locking, `select_for_update`, conditional updates, cross-domain cart mutation,
SMS/payment side effects, tests, and **H1 / M4 / DR-1 / DR-5 / relevant DR-6**. Its `CHANGE_GUIDE.md`
includes all required recipes (add/change provider, change callback verification, change
`payment_status` semantics, add a payment state, change refund, change COD, change retry/idempotency,
change PaymentGatewayConfig, change checkout→payment handoff, retire simulation, retire legacy
Transaction). The current **3-writer `payment_status` reality is made impossible to overlook**
(README banner + MUTATION_AUTHORITY + STATE_MACHINES + CHANGE_GUIDE + INVARIANTS).

### Content special finding
The `content` pack documents **H2 explicitly**: `apps/content` has **no write service**; all CRUD is
in `apps/dashboard/views.py` (exact view functions + line ranges mapped in MUTATION_AUTHORITY). It
does **not** pretend a canonical content write service exists, and carries **DR-2 as OPEN**.

### Storefront de-confliction result
The `storefront_builder` pack's `GENERATIONS.md` gives a clear CURRENT vs LEGACY vs TEMPLATE/PRESET
map: **R4 = current** (`r4_editor_enabled` default True), **R3 = legacy, fail-closed**
(`_require_legacy_editor_active` → Http404 when R4 active), **A8 Ready Templates + layout presets** on
top. Documents H3, M1, M2, M10, M11, M12, DR-6, and the duplicate appearance/palette/theme sources.
A reader can immediately tell which path is current.

### Near-dead / small domains
`blog` documents exactly what exists (BlogPost model, admin-only, no urls/views, POTENTIALLY_DEAD
storefront wiring D1, no deletion decision) without manufacturing architecture. `notifications` is a
small, proportionate pack.

## 5. Phase 7 — Change-navigation system (commit `e4c180f7`)
`canonical/CHANGE_IMPACT_GUIDE.md` maps the required change families — **CF-1 payment verification,
CF-2 add Store status, CF-3 storefront appearance, CF-4 content pages, CF-5 subscription renewal,
CF-6 SMS sending, CF-7 owner authentication, CF-8 product inventory** — plus additional families,
each with domain / read-first / canonical models / canonical services / other writers / dependent
domains / runtime flows / state machines / tests / known risks / open decisions, and a
blocking-decision index (which DR blocks which change).

**Canonical graphs** (`canonical/graphs/`): a README that **links to the authoritative Phase 1 graph
sources** (system context, domain map, domain dependencies, model relationships, service
dependencies, mutation graph, major runtime flows) and adds 3 navigation graphs
(`change_impact_map.mmd`, `risk_and_decisions.mmd`, `domain_readiness.mmd`). Textual/diffable; the
Phase 1 sources are reused/linked (not copied) and their authority is explained.

## 6. Documentation validation (commit `f2000574`)
`tools/docs/validate_architecture_docs.py` (standard-library only; PyYAML unavailable). Validates:
broken internal links, domain IDs (15) + duplicates, required canonical files, domain READMEs +
expected set, invalid OPEN decision IDs (must be DR-1…DR-8), code-path references (`apps/….py`)
existence (with an allowlist of intentionally-absent files), canonical graph presence, and registry
parseability. **Result: PASS** (saved to `docs/architecture_knowledge_system/VALIDATION_RESULTS.txt`):
```
internal links checked: 434      (0 broken)
registry domain IDs: 15          (expected 15)
registry DR references: 8 distinct
domain dirs: 15                  (expected 15)
code-path references checked: 120 (2 intentionally-absent: apps/blog/urls.py, hypothetical new_gateway.py)
canonical graph sources: 3
warnings: 0    errors: 0    RESULT: PASS
```
**Internal-link failures:** none (9 initially-broken canonical→graph links were fixed to point to the
authoritative `../phase1_code_discovery/graphs/` sources). **Code-path reference failures:** none
(the 2 absent references are intentional: `apps/blog/urls.py` is cited precisely because it does not
exist — D1; `new_gateway.py` is a hypothetical example in the orders CHANGE_GUIDE). No application CI
was changed.

## 7. Open DR-1…DR-8 mapping (all OPEN — none resolved)
| DR | Title | Primary domain(s) | Finding |
|---|---|---|---|
| DR-1 | `Order.payment_status` canonical writer + guard | orders | H1 |
| DR-2 | content domain write boundary | content, dashboard | H2 |
| DR-3 | service-layer write discipline for settings/config | core, orders, dashboard | M5/X2 |
| DR-4 | ownership-transfer duplication (two live paths) | stores, portal, dashboard | M6/A8 |
| DR-5 | dual gateway representation | orders | M4 |
| DR-6 | legacy-path removal (simulation / Transaction / R3 editor) | orders, storefront_builder | H1/H3/DI-2 |
| DR-7 | Store vs `catalog.Vendor` ownership | catalog, stores | A1 |
| DR-8 | `require_resolved_store` disposition | stores | D6-dead |

## 8. Files created / modified
**Created (this task):**
- `canonical/` (21 files: README + 15 core docs + `architecture_registry.yaml` + `DOCUMENTATION_AUTHORITY.md`
  + `ARCHITECTURAL_DECISION_REGISTER.md` + `CHANGE_IMPACT_GUIDE.md` + `graphs/` [README + 3 .mmd]).
- `domains/` (191 files across 15 domain packs).
- `VALIDATION_RESULTS.txt`.
- `tools/docs/validate_architecture_docs.py`, `tools/docs/README.md`.
- `PHASES_5_TO_7_MASTER_REPORT.md` (this file).

**Modified (this task):**
- STEP 0: `phase4_reconciliation/{00,08,11}` + `PHASES_2_TO_4_MASTER_REPORT.md` (DR-count + readiness fixes).
- Phase-7 fix: 7 canonical docs' graph links repointed to the Phase 1 graph sources.

Total files under `docs/architecture_knowledge_system/`: **267**.

## 9. Exact commits pushed to `docs/architecture-knowledge-system`
```
6ec9194c  STEP 0 bookkeeping repairs
34e38188  Phase 5 canonical layer (+ registry, authority, DR register)
66f65d45  Phase 6 orders (gold-standard)
bf33def8  Phase 6 content + storefront_builder
48a99bf5  Phase 6 stores
875f5f1c  Phase 6 billing
51d638ff  Phase 6 subscriptions
1d5d795d  Phase 6 dashboard
cfa503cc  Phase 6 portal
0c7d470d  Phase 6 catalog
a7c74889  Phase 6 customers
98681a49  Phase 6 cart
3318ffae  Phase 6 sms
2c78d104  Phase 6 notifications + core + blog
e4c180f7  Phase 7 change-impact navigation + canonical graphs
f2000574  doc-validation tooling + canonical graph-link fixes
(this report adds one further commit on the same branch)
```

## 10. Confirmations
- **No production code changed:** CONFIRMED — `git diff --stat 5883a140 HEAD -- apps/ shop_core/
  templates/ static/` is empty. Tests and migrations untouched.
- **No historical doc changed / moved / deleted:** CONFIRMED — the only paths changed vs `5883a140`
  are under `docs/architecture_knowledge_system/**` and `tools/docs/**`
  (`git diff --name-only 5883a140 HEAD | grep -v` those two prefixes → empty). No old `docs/**` file
  was modified, moved, renamed, or archived; stale/historical docs are labelled from the new
  canonical system (in `HISTORICAL_CONTEXT.md` files + `DOCUMENTATION_AUTHORITY.md`), never edited.
- **Write scope:** only `docs/architecture_knowledge_system/**` and `tools/docs/**`.
- **No PR, no merge, no archive/delete/move, no DR resolution, no remediation.**

## 11. Limitations
- PyYAML is unavailable in this environment (no network); the registry is validated structurally
  (line-scanner) rather than by a full YAML parse. The registry is tab-free and structurally
  consistent (15 domains, 8 DRs).
- Some domain packs fold non-applicable document categories into the README rather than emitting
  every filename from the mandate's superset (recorded explicitly per pack) — deliberately avoiding
  meaningless empty files, as instructed.
- Code-path references in docs are validated for existence, not for line-number precision; a few
  cited line ranges are approximate (marked `~` where a file exceeded a single read in Phase 1).
- R4 client-side JS endpoint mapping remains INFERRED (unchanged from Phase 1/2).

## 12. Recommended next step
Independent review of the complete canonical knowledge system. If accepted, the natural next stages
(each **separately authorized**) are: (a) resolve DR-1…DR-8 with the Product Owner; (b) execute the
Phase 4 archive plan via `git mv` (never delete) with historical banners; (c) correct
`docs/README.md` (structural X1 contradiction); (d) then, and only then, architecture remediation
of the HIGH findings (H1/H2/H3). **None of these is started here.**

## 13. STOP
Phases 5–7 are complete and pushed. Per the task instructions, work **STOPS**. No archival, no
old-document deletion, no architecture remediation, no production-code change, no DR resolution, and
no Phase 8+ has been started.

The central distinction remains preserved:
> **WHAT THE CODE DOES** (Phase 1/2 + canonical) ≠ **WHAT DOCUMENTATION CLAIMS** (Phase 3/4) ≠
> **WHAT THE ORIGINAL DESIGN INTENDED** ≠ **WHAT THE FUTURE CANONICAL ARCHITECTURE SHOULD BE** (DRs, unresolved).
