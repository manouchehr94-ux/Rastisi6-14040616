# P5-W3 final repair — architecture / duplication gate

Re-verified after the final Architect-review repair (commit `e9551ff`), on
top of the original W3 audit (`09_architecture_duplication_audit.md`), which
this repair did not invalidate — it only touched `design_lab_service.py`,
`r4_mutation_service.py`'s `_apply_design_lab_candidate`, `r4_views.py`'s
`/design-lab/` endpoint, `r4_editor.js`'s Design Lab panel, and the QA
runner/tests.

| Concept | Single owner | Verified |
|---|---|---|
| Design Lab candidate service | `apps/storefront_builder/services/design_lab_service.py` (the only module) | grep for a second `design_lab_service*.py` / resolver / registry: none |
| Signed candidate-token model | `design_lab_service.encode_candidate_token` / `decode_candidate_token` (one codec pair) | grep for a second `def encode_candidate_token`/`def decode_candidate_token`: none |
| Canonical mutation endpoint | `r4_mutation_service._dispatch_mutation`'s ONE `design_lab.apply_candidate` arm, calling `_apply_design_lab_candidate` | grep for a second `"design_lab.apply_candidate"` dispatch site: none (only the one `if` in `_dispatch_mutation`) |
| `apply_mutation` transaction | `r4_mutation_service.apply_mutation` (`@transaction.atomic`), unchanged — the new token decode/validate runs INSIDE it, not a second transaction | confirmed by reading the function: no new `@transaction.atomic` was added |
| Draft authority | `StorefrontLayoutVersion` via `layout_service` / `_lock_active_draft` (`select_for_update`) | `design_lab_service.py` contains zero `.save(`/`.objects.create(`/`.objects.update(` calls (verified) |
| Revision authority | `edit_history_service.record_change` (single `edit_revision` advance per `apply_mutation` call) | unchanged; the new candidate-revision check reads `draft.edit_revision`, never increments it directly |
| History authority | `edit_history_service` (`snapshot_draft` / `record_change`) | unchanged; no second history write path added |
| Store Appearance registry/resolver | `storefront_appearance.registry` / `rendering.resolve_store_appearance_manifest_state` | unchanged; `design_lab_service` only calls into it |
| Theme authority | `appearance_authority_service.apply_theme` / `clear_theme` (W2) | unchanged; `_apply_design_lab_candidate` still routes Theme through these two, now deriving `theme_intensity` from the signed candidate's own settings instead of a separate raw mutation field |
| Preview renderer | the existing `storefront_preview` route / `render_service` | untouched by this repair |

## Raw-selection Apply bypass — explicitly checked and removed

Before this repair, `_apply_design_lab_candidate` read `mutation["selections"]`
and `mutation["theme_intensity"]` directly from the client-supplied mutation
dict — an unsigned, client-editable bypass of the token's integrity guarantee
(Architect IMPORTANT 1). This repair removed that path entirely: the handler
now requires `mutation["candidate_token"]`, decodes it with
`design_lab_service.decode_candidate_token` (rejecting anything
missing/malformed/tampered/expired), and only ever derives `selections` /
`theme_intensity` from the **decoded, signature-verified** candidate. There is
no legacy fallback, no dual code path, and no way to submit raw selections —
confirmed by `grep -n "mutation.get(.selections.)\|mutation\[.selections.\]"
apps/storefront_builder/services/r4_mutation_service.py` returning nothing.

## Verdict: PASS — one owner per concept, zero duplicates, zero unsigned bypass.
