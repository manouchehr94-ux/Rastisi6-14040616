# 06 — Phase 1 Corrections (from Phase 2 validation)

Corrections applied to Phase 1 Architecture Knowledge System artifacts as a result of direct
Phase 2 code verification. History is **not** silently rewritten: each Phase 1 artifact is
annotated in place with a dated `[PHASE 2 CORRECTION]` note pointing here, and the original
wording/rationale is preserved.

Nothing below is a production-code change. Only `docs/architecture_knowledge_system/**` is edited.

---

## C1 — D3 `membership_service.transfer_ownership` is NOT dead (DISPROVED as dead)

- **Phase 1 said:** POSSIBLY/POTENTIALLY_DEAD relative to the OTP flow; "whether it has a live
  caller was not conclusively confirmed" (doc 13 D3; doc 12 M6; doc 14 A8, U-list).
- **Phase 2 evidence (VERIFIED):**
  - `apps/dashboard/urls.py:390` → `path("staff/<int:pk>/transfer-ownership/", views.staff_transfer_ownership, ...)`
  - `apps/dashboard/views.py:261` imports `transfer_ownership`; `:5882 def staff_transfer_ownership`;
    `:5896` calls `transfer_ownership(request.store, current_owner=..., new_owner=..., actor=...)`.
- **Correction:** `membership_service.transfer_ownership` is **LIVE** (merchant dashboard staff
  page). The "possibly dead" characterization is **DISPROVED**.
- **Consequence (UPGRADE, not removal):** there are now confirmed **two live** ownership-transfer
  paths — the dashboard direct path and the portal OTP path (`ownership_transfer_service`). This
  is a genuine **duplicate mutation path** for `StoreMembership` owner reassignment, which
  *strengthens* smell M6 / ambiguity A8 rather than removing it. Carried to Phase 4 as a
  decision-required item.
- **Artifacts corrected:** doc 13 (D3), doc 12 (M6), doc 14 (A8 + unknowns U-list),
  and the Phase 1 dead-count buckets (D3 moves out of "unconfirmed candidates").

## C2 — Post-C1 dead-count refinement

- STEP-0 recorded: 5 actual POTENTIALLY/POSSIBLY_DEAD candidates (D1, D3, D4, D6, D7), of which 2
  unconfirmed (D3, D6).
- **After Phase 2:** D3 is DISPROVED-as-dead (it is live). So:
  - Actual POTENTIALLY_DEAD candidates that remain = **4** (D1, D4, D6, D7).
  - Of these, **unconfirmed remaining = 1** (D6 only — no live caller found, but may be
    intentional API scaffolding; not deleted).
  - D1, D4, D7 are CONFIRMED as their limited kind of deadness (storefront-wiring / data /
    inert-constants respectively).
- **Artifact corrected:** doc 13 count-reconciliation table; doc 15 Part F / Part K item 17.

## C3 — Items explicitly CONFIRMED unchanged (no correction, recorded for completeness)

- H1, H2, H3: CONFIRMED (doc 01).
- Order.payment_status unguarded: CONFIRMED (doc 04).
- All other AMBIGUOUS_OWNERSHIP items A1–A7, A9: CONFIRMED (doc 03).
- Duplicate sources M1, M2, M11 and parallel impls M3, M4, M10, M12: CONFIRMED (doc 03).
- No-signal design, cycle-avoidance edges: CONFIRMED (doc 05).
- D1, D2, D4, D5, D7, D8: statuses unchanged (doc 01 table).

## C4 — No substantive architecture finding was DISPROVED

The only DISPROVED sub-claim was the *deadness* of D3. Its disproval does not weaken any
architecture-risk finding; it converts a hedged "maybe dead" into a confirmed "live duplicate
path," which is a stronger (not weaker) statement of the underlying duplication smell.

---

## Applied edits (traceability)

| Artifact | Edit |
|---|---|
| `phase1_code_discovery/13_POTENTIALLY_DEAD_OR_ORPHANED.md` | D3 annotated `[PHASE 2 CORRECTION]` → DISPROVED as dead (live caller); count table updated (candidates 5→4, unconfirmed 2→1) |
| `phase1_code_discovery/12_ARCHITECTURE_SMELLS.md` | M6 annotated → both transfer paths confirmed LIVE (duplication upgraded) |
| `phase1_code_discovery/14_AMBIGUITIES_AND_UNKNOWNS.md` | A8 annotated → both paths live; U-item "live caller of transfer_ownership" marked RESOLVED |
| `phase1_code_discovery/15_PHASE1_MASTER_ARCHITECTURE_REPORT.md` | Part F / Part K item 17 dead-count refined post-C1 |

All edits are annotations that preserve the original Phase 1 text; they do not delete Phase 1
conclusions.
