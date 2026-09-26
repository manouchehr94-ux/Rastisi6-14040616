# 07 — Phase 2 Validation Report

**Phase:** 2 — Independent validation of the Phase 1 code-derived architecture.
**Frozen production snapshot:** `5883a1404a8b0f1f245f0d8ef17ac5c13e40a7cb` (production code verified
identical to the working checkout via `git diff --stat 5883a140 HEAD -- apps/ shop_core/ templates/ static/` = empty).

---

## 1. What Phase 2 did
Re-verified the highest-impact Phase 1 findings **directly against the frozen code** (not via
sub-agent inference), and resolved the reachability questions Phase 1 left open. Every validated
item received one of: CONFIRMED / CONFIRMED_WITH_CORRECTION / DOWNGRADED / UPGRADED / NOT_PROVEN /
DISPROVED.

## 2. Results at a glance

| Area | Items validated | Result |
|---|---|---|
| HIGH findings (H1, H2, H3) | 3 | **3 CONFIRMED** (doc 01) |
| HIGH mutation entities (payment_status, content.*) | 2 | **2 CONFIRMED** (doc 02) |
| Other spot-checked entities | 5 | 4 CONFIRMED + 1 CONFIRMED_WITH_CORRECTION (StoreMembership) |
| AMBIGUOUS_OWNERSHIP (A1–A9) | 9 | 8 CONFIRMED + 1 UPGRADED (A8) (doc 03) |
| Duplicate sources of truth (M1, M2, M11) | 3 | 3 CONFIRMED (doc 03) |
| Parallel implementations (H1/H3, M3, M4, M6, M10, M12) | 6 | 5 CONFIRMED + 1 UPGRADED (M6) (doc 03) |
| Unguarded state machine (payment_status) | 1 | **CONFIRMED** (doc 04) |
| Guarded state machines | 4 tables + per-service set | CONFIRMED (doc 04) |
| Dependency edges + no-signal + cycle-avoidance | 11 | CONFIRMED (+1 new edge) (doc 05) |
| POTENTIALLY_DEAD resolvable (D1, D3, D4, D6, D7) | 5 | D1/D4/D7 CONFIRMED, D6 CONFIRMED-dead-candidate, **D3 DISPROVED-as-dead** (doc 01/06) |

## 3. Phase 1 findings confirmed
All three HIGH findings, both HIGH mutation entities, the single unguarded state machine, all
duplicate-source and parallel-implementation claims validated, the no-signal design, and the
cycle-avoidance edges. **No substantive architecture risk finding was weakened or disproved.**

## 4. Phase 1 findings corrected (transparent; see doc 06)
- **C1 — D3 DISPROVED as dead.** `membership_service.transfer_ownership` is live-called from the
  merchant dashboard (`staff/<pk>/transfer-ownership/`). This **upgrades** M6/A8: there are two
  **live** ownership-transfer paths — a genuine duplicate mutation path, not a maybe-dead one.
- **C2 — dead-count refined.** Post-Phase-2 actual POTENTIALLY_DEAD candidates = **4**
  (D1, D4, D6, D7); unconfirmed remaining = **1** (D6).
- Phase 1 artifacts (docs 12, 13, 14, 15) were annotated in place with dated
  `[PHASE 2 CORRECTION]` notes; no original conclusion was deleted.

## 5. Confidence upgrade
Phase 1's high-impact conclusions are no longer inference-dependent: the payment duplication,
content mutation authority, storefront generational layering, unguarded `payment_status`, and the
ownership-transfer duplication are all now backed by exact file/line/route citations against the
frozen snapshot.

## 6. Items still not fully resolvable by static analysis (carried forward)
- **A1** Store vs `catalog.Vendor` — genuine coexistence contract not fully expressed in code
  (UNKNOWN, not asserted either way).
- **D6** `require_resolved_store` — no live caller found; may be intentional API scaffolding
  (POTENTIALLY_DEAD, unconfirmed as intentional).
- R4 client-JS endpoint mapping — INFERRED (JS not read).
- These are recorded, not forced to a conclusion.

## 7. Boundaries respected
- No production code, tests, or migrations modified (`git diff 5883a140 HEAD -- apps/ ...` empty).
- Only `docs/architecture_knowledge_system/**` written.
- No merge/rebase; no other branch read. Analysis remains of `5883a140` only.

## 8. Gate
Phase 2 is complete. Existing repository documentation was **not** consulted during Phase 2
(that begins in Phase 3). Proceeding to Phase 3 (documentation inventory), where old docs become
**evidence/history, not authoritative runtime truth**.
