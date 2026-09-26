# Canonical Graphs

```
status: CANONICAL
code_baseline: 5883a140
source_phases: Phase 1 (graph sources) / this canonical layer
```

Textual, diffable Mermaid graphs. **Authority:** the Phase 1 graph sources
([`../../phase1_code_discovery/graphs/`](../../phase1_code_discovery/graphs/)) are the verified
code-derived originals; this canonical folder **links to them** and adds a small number of
navigation-oriented canonical graphs. Where a Phase 1 graph is sufficient, it is referenced rather
than copied.

## Phase 1 source graphs (authoritative, code-derived — link, do not duplicate)
| Graph | Source | Referenced by |
|---|---|---|
| System context | [`../../phase1_code_discovery/graphs/system_context.mmd`](../../phase1_code_discovery/graphs/system_context.mmd) | [`../SYSTEM_CONTEXT.md`](../SYSTEM_CONTEXT.md), [`../EXTERNAL_INTEGRATIONS.md`](../EXTERNAL_INTEGRATIONS.md) |
| Domain map | [`../../phase1_code_discovery/graphs/domain_map.mmd`](../../phase1_code_discovery/graphs/domain_map.mmd) | [`../DOMAIN_MAP.md`](../DOMAIN_MAP.md) |
| Domain dependencies | [`../../phase1_code_discovery/graphs/domain_dependencies.mmd`](../../phase1_code_discovery/graphs/domain_dependencies.mmd) | [`../DEPENDENCY_MAP.md`](../DEPENDENCY_MAP.md) |
| Model relationships | [`../../phase1_code_discovery/graphs/model_relationships.mmd`](../../phase1_code_discovery/graphs/model_relationships.mmd) | [`../DATA_OWNERSHIP.md`](../DATA_OWNERSHIP.md) |
| Service dependencies | [`../../phase1_code_discovery/graphs/service_dependencies.mmd`](../../phase1_code_discovery/graphs/service_dependencies.mmd) | [`../DEPENDENCY_MAP.md`](../DEPENDENCY_MAP.md) |
| Mutation graph | [`../../phase1_code_discovery/graphs/mutation_graph.mmd`](../../phase1_code_discovery/graphs/mutation_graph.mmd) | [`../MUTATION_AUTHORITY.md`](../MUTATION_AUTHORITY.md) |
| Major runtime flows | [`../../phase1_code_discovery/graphs/major_runtime_flows.mmd`](../../phase1_code_discovery/graphs/major_runtime_flows.mmd) | [`../RUNTIME_FLOW_INDEX.md`](../RUNTIME_FLOW_INDEX.md) |

## Canonical navigation graphs (added by this layer)
| Graph | Purpose |
|---|---|
| [`change_impact_map.mmd`](change_impact_map.mmd) | change family → domain → risk/decision (Phase 7 navigation) |
| [`risk_and_decisions.mmd`](risk_and_decisions.mmd) | HIGH/MEDIUM findings → DR-1…DR-8 → affected domains |
| [`domain_readiness.mmd`](domain_readiness.mmd) | documentation readiness per domain (READY/PARTIAL/POOR/MISSING/CONFLICTED) |

These canonical graphs are **derived from** Phase 1/2 evidence + the Phase 4 decision register; they
add navigation, not new architectural claims. All are textual/diffable.
