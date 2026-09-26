# RastiSi Architecture Knowledge System
## Governing Rules and Phase 1 — Code-First Architecture Discovery

**Document status:** CANONICAL GOVERNING DOCUMENT  
**Purpose:** Define the rules, evidence standard, workflow, safety boundaries, output structure, and Phase 1 execution method for rebuilding RastiSi architecture documentation from the actual codebase.  
**Intended operator:** Kiro or another coding/documentation agent  
**Repository scope:** RastiSi  
**Initial phase:** Phase 1 — Code-First Architecture Discovery  
**Critical principle:** Existing documentation MUST NOT influence Phase 1 discovery.

---

# 1. Why this initiative exists

RastiSi contains a large body of documentation created across many phases of development.

Some documents may be:

- current;
- historical;
- partially current;
- duplicated;
- superseded;
- inconsistent with the current implementation;
- implementation reports rather than architecture documentation;
- useful design intent that no longer matches runtime behavior;
- important but effectively lost inside a large documentation corpus.

The purpose of this initiative is **not** merely to reorganize Markdown files.

The purpose is to create a durable **Architecture Knowledge System** that allows a developer or coding agent to answer questions such as:

> What does this subsystem actually do?

> Which models belong to it?

> Which services mutate those models?

> What calls those services?

> What depends on this subsystem?

> Which runtime flows pass through it?

> What invariants must not be broken?

> Which tests prove the behavior?

> What is the impact radius of a proposed change?

> Are multiple implementations or sources of truth present?

> Is there legacy or orphaned code?

> What must be inspected before modifying a feature?

The final system must be based primarily on **verified implementation evidence**, not assumptions or inherited descriptions.

---

# 2. Fundamental rule: CODE FIRST, DOCUMENTATION LATER

Phase 1 is an independent architecture discovery exercise.

During Phase 1:

> **DO NOT READ EXISTING ARCHITECTURE, PLAN, DESIGN, QA, TASK, REPORT, OR HISTORICAL DOCUMENTATION TO LEARN HOW THE SYSTEM WORKS.**

This restriction is intentional.

Existing documents can anchor the investigation around old assumptions and may cause the auditor to confirm a previous design instead of discovering the current implementation.

Phase 1 must answer only:

> **WHAT DOES THE CURRENT CODE ACTUALLY DO?**

Only after Phase 1 has been completed, written to disk, validated, and explicitly frozen may a later phase inspect existing documentation.

The future documentation-reconciliation phase will answer separately:

1. What the current code actually does.
2. What historical/current documents claim.
3. Where those two disagree.
4. What the canonical architecture should become.

These must never be silently conflated.

---

# 3. Independent branch and worktree policy

This initiative MUST be performed on an isolated branch.

Recommended branch name:

```text
docs/architecture-knowledge-system
```

A more phase-specific branch is also acceptable:

```text
docs/architecture-discovery-phase1
```

If another coding agent such as Claude Code is actively working in the primary worktree, Kiro MUST NOT reuse or disturb that worktree.

Preferred approach:

- create a new branch from the exact approved repository checkpoint;
- create a separate Git worktree for this documentation initiative;
- perform all discovery artifacts there.

Before doing anything else, record:

```bash
git branch --show-current
git rev-parse HEAD
git status --short
```

The worktree must initially be clean.

Kiro MUST NOT:

- reset another branch;
- clean another worktree;
- stash another agent's changes;
- checkout over another agent's files;
- amend another agent's commits;
- modify another agent's uncommitted work.

If the starting repository state is not safe, STOP and report the condition.

---

# 4. Allowed write scope

During Phase 1, authored files should be limited to a new documentation subtree.

Recommended root:

```text
docs/architecture_knowledge_system/
```

This governing document should become the first canonical file in that subtree:

```text
docs/architecture_knowledge_system/00_GOVERNING_RULES_AND_PHASE1.md
```

Recommended Phase 1 output directory:

```text
docs/architecture_knowledge_system/phase1_code_discovery/
```

Optional documentation-only helper tooling may later be written under:

```text
tools/docs/
```

but only if explicitly necessary.

---

# 5. Forbidden write scope

During Phase 1, Kiro MUST NOT modify application behavior.

Do not modify:

```text
apps/**
templates/**
static/**
migrations/**
production settings
runtime configuration
database schema
application tests
application services
models
views
URLs
forms
serializers
signals
commands
tasks
provider implementations
```

The codebase is being observed, not repaired.

If architecture defects are found:

> DOCUMENT THEM. DO NOT FIX THEM.

Discovery and remediation are separate phases.

---

# 6. Existing documentation access policy

During Phase 1, the following sources are prohibited as architecture-learning inputs:

- existing files under `docs/**`, except this governing file;
- previous architecture specifications;
- implementation plans;
- QA reports;
- task reports;
- migration plans;
- old design reports;
- old system maps;
- previous architecture reviews;
- historical Markdown files;
- old generated diagrams.

The prohibition exists to prevent anchoring bias.

Exception:

A documentation file may be read only if it is technically required to execute the application or understand a machine-readable runtime contract and there is no equivalent source in code/configuration.

If such an exception occurs, record:

- exact file;
- why it was necessary;
- what information was used;
- why code alone was insufficient.

Do not use the document's architectural conclusions as evidence.

---

# 7. Permitted discovery sources

Phase 1 SHOULD inspect the current implementation, including where relevant:

```text
project/package structure
Django apps
models
model managers
querysets
services
domain services
application services
views/controllers
URLs/routes
forms
serializers
signals
tasks/jobs
management commands
middleware
adapters
provider integrations
repositories/data access helpers
feature flags
settings/configuration
templates when they affect runtime architecture
JavaScript when it performs domain-relevant mutations or API calls
migrations
tests
fixtures
factories
admin actions
shared/common modules
utility modules
transaction boundaries
event or signal flows
external APIs
```

Tests are especially important because they often reveal intended invariants and supported behavior.

However:

> Tests are evidence of intended/verified behavior, not proof that all production paths conform.

Always inspect the implementation path as well.

---

# 8. Evidence classifications

Every major architectural claim must be assigned one of these evidence classifications:

## VERIFIED

Directly supported by current code, schema, configuration, routing, or tests.

Example:

```text
VERIFIED:
apps/payments/services/payment_service.py::confirm_payment()
updates Payment.status.
```

## INFERRED

Strongly suggested by code structure, but not fully proven.

Example:

```text
INFERRED:
PaymentService appears to be intended as the primary mutation boundary,
but direct writes exist elsewhere.
```

## UNKNOWN

Cannot be established safely from available implementation evidence.

Example:

```text
UNKNOWN:
Whether this unused provider is still required by an external deployment.
```

## POTENTIALLY_DEAD

No live caller, route, signal, command, registration, or other entry point has yet been found.

This classification does NOT authorize deletion.

## AMBIGUOUS_OWNERSHIP

More than one domain or implementation appears to own the same concept.

---

# 9. Evidence citation standard

Architecture reports must avoid unsupported generic prose.

Bad:

```text
The payment system probably uses PaymentService.
```

Good:

```text
VERIFIED:
POST /payments/start/ routes through
apps/payments/urls.py
→ apps/payments/views.py::start_payment
→ apps/payments/services/payment_service.py::create_payment
```

For important findings, cite as many of the following as applicable:

- exact file path;
- class;
- function/method;
- model;
- route;
- signal;
- setting;
- test;
- migration;
- template;
- command;
- call site.

When practical, include line ranges or symbols.

---

# 10. Core architectural questions

The Phase 1 audit must answer these questions for the repository.

## 10.1 What are the real application domains?

Do not assume the domain list in advance.

Discover candidate domains from actual ownership and behavior.

Examples may include concepts such as:

- accounts;
- stores;
- catalog;
- storefront;
- orders;
- payments;
- fulfillment;
- content;
- design/builder;
- media;
- authentication;
- analytics.

These are only examples.

Kiro must derive the real domain map from the code.

For each candidate domain identify:

- responsibility;
- owned data;
- owned services;
- entry points;
- dependencies;
- consumers;
- boundary ambiguities.

---

# 11. Model ownership discovery

For every important model determine:

- defining file;
- owning app;
- likely owning domain;
- important fields;
- foreign keys;
- many-to-many relations;
- unique constraints;
- database constraints;
- lifecycle/status fields;
- creator(s);
- updater(s);
- readers;
- deletion behavior;
- related services;
- related tests.

The audit must explicitly identify:

> **WHO MUTATES WHAT**

This is a mandatory output.

A model being physically located in one app does not automatically prove that the app owns all mutation authority.

---

# 12. Mutation analysis

Build a repository-wide mutation map.

For important persisted entities identify every meaningful writer.

Example format:

```text
Payment.status

Writers:
- PaymentService.confirm()
- WebhookHandler.process()
- OrderService.settle()
- Admin payment action

Risk:
Multiple mutation paths
```

Required classifications:

- CANONICAL_WRITER
- SECONDARY_WRITER
- DIRECT_MODEL_WRITE
- CROSS_DOMAIN_WRITE
- UNKNOWN_WRITE_PATH

Look especially for:

- direct `.save()`;
- `.update()`;
- bulk updates;
- manager methods;
- signal-side mutation;
- admin actions;
- background tasks;
- callbacks;
- webhooks;
- raw SQL;
- mutation through shared helpers.

---

# 13. Service and call graph discovery

For important services/functions record:

```text
symbol
file
responsibility
called_by
calls
reads
writes
transaction_boundary
external_side_effects
exceptions
tests
```

Build a call/dependency map sufficient to understand:

```text
entry point
    ↓
controller/view
    ↓
service
    ↓
domain/service logic
    ↓
model/database
    ↓
external provider or side effect
```

Do not create a graph merely for appearance.

Each graph edge must represent a real relationship.

---

# 14. Entry-point inventory

Discover all important system entry points, including as applicable:

- HTTP routes;
- APIs;
- admin actions;
- webhooks;
- callbacks;
- scheduled jobs;
- workers;
- management commands;
- signals;
- CLI tools;
- async tasks;
- internal service entry points;
- template-triggered actions;
- JavaScript API calls.

For each entry point identify its downstream path.

---

# 15. Runtime-flow reconstruction

Reconstruct major runtime flows from code.

Examples:

```text
user action
→ route
→ view
→ service
→ model mutation
→ external call
→ state transition
→ response
```

Each major flow should document:

- trigger;
- entry point;
- call path;
- reads;
- writes;
- transaction boundaries;
- side effects;
- state transitions;
- failure paths;
- retry behavior;
- idempotency behavior;
- tests.

Do not assume happy-path-only behavior.

---

# 16. Dependency discovery

Relationships should be typed.

Use types such as:

```text
imports
calls
owns
reads
writes
foreign-key
routes-to
renders
publishes
consumes
configured-by
validated-by
tested-by
external-call
cross-domain-mutation
```

The output must distinguish between:

- code/import dependency;
- runtime call dependency;
- database dependency;
- data ownership dependency;
- UI dependency;
- event/signal dependency;
- external integration dependency.

---

# 17. Architecture-smell audit

Phase 1 must actively search for architecture problems.

At minimum inspect for:

## Duplicate source of truth

The same concept is represented or governed in multiple places.

## Parallel implementation

Two different service paths implement the same business capability.

## Cross-domain mutation

One domain directly mutates another domain's owned state without a clear contract.

## Circular dependency

Modules/domains depend on each other cyclically.

## Hidden side effect

A function appears local but unexpectedly mutates other state or triggers external behavior.

## Business logic in presentation/controller layer

Important domain rules are implemented directly in views, templates, serializers, forms, or admin actions.

## Multiple state machines

The same state/lifecycle is enforced differently in multiple code paths.

## Legacy parallel path

Old and new architectures are both still reachable.

## Unowned model/concept

No clear service/domain appears responsible.

## Configuration duplication

The same configuration concept exists in multiple registries/settings.

## Inconsistent transaction boundary

A multi-step business operation lacks clear atomicity or uses inconsistent transaction behavior.

## Untested critical path

Important mutation or integration behavior has no clearly located test coverage.

## Potentially dead/orphaned code

No live caller or runtime registration is found.

## Implicit coupling

One area relies on undocumented state or behavior of another.

---

# 18. Severity standard for findings

Architecture findings must use these severity levels:

## CRITICAL

Likely to create severe correctness, financial, security, data-integrity, or systemic architecture risk.

## HIGH

Important structural defect with meaningful change-risk, duplication, ownership, or consistency impact.

## MEDIUM

Architecture weakness that increases complexity or maintenance risk but is not currently catastrophic.

## LOW

Localized or limited structural issue.

## OBSERVATION

Not necessarily a defect, but important context for future design.

Severity must be justified with evidence.

Do not inflate severity.

---

# 19. Dead/orphan discovery rules

A component may be marked `POTENTIALLY_DEAD` only after checking appropriate entry mechanisms.

For example:

```text
called by code: none found
route: none found
signal registration: none found
task registration: none found
command: none found
admin action: none found
configuration reference: none found
test-only reference: yes/no
dynamic import possibility: checked/not checked
```

Never label code definitively dead unless evidence is conclusive.

Never delete it during Phase 1.

---

# 20. State-machine discovery

Where models contain lifecycle/status/state concepts:

- enumerate states;
- find all mutation sites;
- determine allowed transitions;
- identify terminal states;
- identify guards;
- identify illegal transitions;
- identify state changes triggered by other domains;
- identify tests covering transitions.

If different paths enforce different transitions, record an architecture smell.

---

# 21. Transaction and consistency discovery

For important multi-model operations inspect:

- `transaction.atomic`;
- explicit locks;
- `select_for_update`;
- idempotency protections;
- unique constraints;
- optimistic/pessimistic concurrency behavior;
- retry behavior;
- external calls inside/outside transactions;
- partial failure risks.

Record unclear boundaries.

Do not redesign them during Phase 1.

---

# 22. Test map

Build a map between important behavior and tests.

Example:

```text
Behavior:
Payment confirmation

Implementation:
apps/payments/services/payment_service.py::confirm_payment

Tests:
apps/payments/tests/test_payment_confirmation.py::...
```

Identify:

- unit coverage;
- integration coverage;
- API coverage;
- lifecycle coverage;
- browser coverage where relevant;
- regression tests;
- apparent gaps.

Do not modify application tests during this phase.

---

# 23. Mandatory Phase 1 output structure

Create:

```text
docs/
└── architecture_knowledge_system/
    ├── 00_GOVERNING_RULES_AND_PHASE1.md
    └── phase1_code_discovery/
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
        ├── 15_PHASE1_MASTER_ARCHITECTURE_REPORT.md
        └── graphs/
            ├── system_context.mmd
            ├── domain_map.mmd
            ├── domain_dependencies.mmd
            ├── model_relationships.mmd
            ├── service_dependencies.mmd
            ├── mutation_graph.mmd
            └── major_runtime_flows.mmd
```

Additional files may be created when justified.

Do not create empty placeholder documents.

---

# 24. Graph requirements

Use text-based graph sources.

Preferred format:

```text
Mermaid (.mmd)
```

Do not rely only on PNG/SVG diagrams.

Graphs must be:

- version-control friendly;
- searchable;
- diffable;
- readable by coding agents;
- traceable to implementation evidence.

Required graph families:

1. System context
2. Domain map
3. Domain dependencies
4. Data/model relationships
5. Service dependencies
6. Mutation graph
7. Major runtime flows

The mutation graph is especially important.

It should make visible:

```text
which code paths mutate which persisted entities
```

---

# 25. Master ownership matrix

The Phase 1 master report must include a matrix conceptually equivalent to:

| Concept / Entity | Probable Canonical Owner | Other Writers | Readers | Main Entry Points | Risk |
|---|---|---|---|---|---|

Do not force ownership where evidence is ambiguous.

Use:

```text
AMBIGUOUS_OWNERSHIP
```

when appropriate.

---

# 26. No premature canonical architecture decisions

Phase 1 discovers reality.

It does NOT decide what the future architecture should be.

Examples:

If code has:

```text
PaymentService
PaymentManager
Webhook mutation
Admin direct mutation
```

do not arbitrarily choose one and rewrite the rest.

Instead record:

```text
CURRENT REALITY:
four mutation paths exist.

ARCHITECTURE RISK:
multiple writers / unclear canonical mutation boundary.

FUTURE DECISION REQUIRED:
yes.
```

Future remediation requires a separate approved task.

---

# 27. Phase 1 freeze rule

At the end of Phase 1, before reading existing documentation, the entire code-derived architecture discovery must be written to disk.

The Phase 1 master report must record:

```text
source_commit: <exact git SHA>
branch: <branch>
discovery_completed_at: <timestamp if available>
existing_docs_used_for_architecture_discovery: NO
```

This creates an independent architecture snapshot.

After this point, Phase 1 findings must not be silently rewritten merely because an old document claims something different.

Later reconciliation should record the disagreement explicitly.

---

# 28. Phase 1 completion gate

Phase 1 is complete only when all of the following are true:

- repository state and source SHA are recorded;
- major domains have been discovered;
- important models have ownership analysis;
- important mutation paths are mapped;
- important services are mapped;
- major entry points are mapped;
- major dependencies are typed;
- major runtime flows are reconstructed;
- state machines are documented where applicable;
- transaction/concurrency boundaries are inspected where important;
- tests are mapped to critical behavior;
- architecture smells are reported;
- potentially dead/orphaned components are reported;
- ambiguities are explicitly listed;
- required Mermaid graphs exist;
- a master Phase 1 report exists;
- no production code has been modified;
- existing documentation has not been used to shape the architecture discovery.

---

# 29. Mandatory final Phase 1 report

At the end of Phase 1, report:

1. branch name;
2. starting SHA;
3. ending SHA;
4. `git status --short`;
5. `git diff --stat`;
6. `git diff --name-only`;
7. all files created;
8. all files modified;
9. confirmation that no production code changed;
10. confirmation that existing documentation was not used as an architecture source;
11. discovered domains;
12. number of important models mapped;
13. number of mutation sites mapped;
14. number of entry points mapped;
15. number of major runtime flows reconstructed;
16. number of architecture-smell findings by severity;
17. potentially dead/orphaned code findings;
18. ambiguous ownership findings;
19. major unknowns;
20. test coverage gaps discovered;
21. exact validation commands run;
22. any limitations that prevented full verification.

Do not commit or push unless explicitly authorized.

---

# 30. What happens after Phase 1

DO NOT begin these later phases unless explicitly instructed.

The planned later workflow is:

```text
PHASE 1
Code-only architecture discovery

        ↓

PHASE 2
Freeze and validate code-derived architecture

        ↓

PHASE 3
Inventory historical/current documentation

        ↓

PHASE 4
Compare documentation claims against code-derived reality

        ↓

PHASE 5
Classify documents:
MATCHES_CODE
STALE
CONTRADICTS_CODE
HISTORICAL
DESIGN_INTENT_ONLY
SUPERSEDED
DUPLICATE
UNVERIFIABLE

        ↓

PHASE 6
Define canonical Architecture Knowledge System

        ↓

PHASE 7
Create domain knowledge packs

        ↓

PHASE 8
Create deep change guides and dependency maps

        ↓

PHASE 9
Archive plan for obsolete/superseded documents

        ↓

PHASE 10
Separate remediation tasks for architecture defects
```

The central distinction must remain:

```text
WHAT THE CODE DOES
≠
WHAT OLD DOCUMENTATION SAYS
≠
WHAT THE FUTURE ARCHITECTURE SHOULD BE
```

---

# 31. Operating principle

The quality objective is not the number of Markdown files.

The quality objective is:

> A future engineer or coding agent can understand the real RastiSi system, trace a feature to exact implementation and tests, identify its dependencies and mutation paths, determine the likely impact radius of a change, and detect conflicting or duplicated architecture without blindly searching the entire repository.

When evidence is uncertain:

> Record uncertainty.

When architecture is duplicated:

> Record duplication.

When ownership is unclear:

> Record ambiguity.

When code appears wrong:

> Record the defect.

Do not hide uncertainty behind confident prose.

Do not repair architecture while auditing architecture.

---

# 32. Initial execution instruction for Kiro

After placing this file at:

```text
docs/architecture_knowledge_system/00_GOVERNING_RULES_AND_PHASE1.md
```

begin **Phase 1 only**.

First perform and report the Git safety gate.

Then inspect the repository codebase independently.

Do not inspect prior documentation for architectural guidance.

Create the Phase 1 discovery outputs incrementally under:

```text
docs/architecture_knowledge_system/phase1_code_discovery/
```

At the end, produce the mandatory Phase 1 master report and STOP.

Wait for explicit approval before beginning documentation reconciliation or any architecture remediation.
