# P5-W3 — Design Lab / Random Mix — Implementation Report

## Provenance
- **Certified starting checkpoint:** `e28b563ca614bd2eafea8ec102ad44cd8a56ae82`
  (the independently certified P5-W2 merge on `feature/phase5-design-expansion`).
- **Implementation branch:** `feature/phase5-w3-design-lab` (created from the checkpoint).
- **Final PR head:** `a5cdef0d5d1a5dce18e71e030ccf7ffc305748a4` (updated if later commits land).
- **Runtime:** Python 3.12.13, Django 5.2.17 (matches the certified checkpoint).

## Source inventory findings (see `00_source_inventory.md`)
Every canonical owner Design Lab must reuse was verified at the checkpoint:
`resolve_preset_candidate` / `resolve_store_appearance_manifest_state` (candidate
resolution, read-only), `StoreAppearanceManifest` + `validate_store_appearance_manifest`
(one manifest contract), `COMPONENT_FAMILIES`/`COMPONENT_REGISTRY` (one registry),
`appearance_authority_service` writers incl. W2 `apply_theme`/`clear_theme`,
`r4_mutation_service.apply_mutation` + `_persist_manifest_selection_updates` (one
atomic multi-family write path), `edit_history_service` (one history/undo),
`apps/stores/resolution.resolve_store_for_service` (tenant boundary), and
`views.storefront_preview` + `render_service.build_page_render_items` (one preview
route + renderer). One correction was recorded: `resolve_preset_candidate` requires
a *registered* preset key, so `candidate_to_preset` reuses the draft's own registered
template key for provenance while the DNA comes entirely from `store_appearance`;
appearance-only candidate preview resolves through the pure
`resolve_store_appearance_manifest_state` seam (the same resolver `resolve_preset_candidate`
itself calls for `store_appearance`).

## Candidate architecture
A Design Lab candidate is a **transient in-memory frozen dataclass**, never persisted:
```python
@dataclass(frozen=True)
class DesignLabCandidate:
    base_selections: Mapping[str, str]
    candidate_selections: Mapping[str, str]
    settings: Mapping
    locked_families: frozenset[str]
    seed: int | None
```
`candidate_to_preset(draft, candidate)` returns an unregistered in-memory
`LayoutPresetDefinition` (composition preserved via empty `pages`); its manifest is
resolved for preview through the canonical resolver. Nothing is registered or saved.

### Eligible randomized family keys
`DESIGN_LAB_RANDOMIZABLE_FAMILIES = {header, hero, product_view, card, footer, badge, bottom_nav}`.
These are the visually meaningful DNA families with registry alternatives. `theme` is
orthogonal (only changes on explicit randomize/Remove-Theme). `mega_menu` (single
option), `layout` (page composition) and `motion` (subtle token) are excluded so
Random Mix changes visible chrome/section DNA without touching composition or commerce.

### Lock semantics
Locks are **transient exploration locks** living only in
`DesignLabCandidate.locked_families` (and the client's transient set). No DB field, no
migration, no persistent lock table, no localStorage. Enforced **server-side** in
`generate_candidate` (a locked family is removed from the effective randomize set — lock
wins even if also requested) and in the `/design-lab/` endpoint.

### Deterministic generation seam
`generate_candidate(draft, *, randomize_families, locked_families, seed)` uses a local
`random.Random(seed)` over a deterministic family order and deterministic
`list_components(family)` order. Same (draft state, randomize set, locked set, seed) ⇒
same candidate. It prefers a component different from the current one when alternatives
exist (Random Mix is visibly meaningful) and leaves a family unchanged when it has no
alternative. The merchant never sees the seed.

### Compare-with-Base semantics
`compare_with_base(candidate)` is a server-authoritative family-by-family diff between
the committed-Draft base selections and the candidate, returning Persian merchant-facing
labels per changed family; unchanged/locked families never appear. JS only displays it.

### Return-to-Original-DNA semantics
`return_to_original_dna(draft, candidate)` returns the transient candidate to the Design
Lab's committed-Draft base (the state it was generated from) — **zero** Draft writes, and
it never restores a historic Ready-Template baseline over merchant customizations.

### Reset semantics
`reset_candidate(draft)` discards the experiment and returns a candidate equal to the
current committed Draft — no write, no history, no revision change. It is not Undo.

### Remove-Theme semantics
`remove_theme(candidate)` transiently sets `selections["theme"] = theme.none.v1` and drops
theme settings (no Draft write). On explicit Apply the removal flows through the canonical
W2 `clear_theme` owner; all non-theme state is preserved exactly.

## Canonical Preview path
The candidate is encoded as an opaque token for the **existing** `storefront_preview`
route (`?design_lab=<token>`). The view decodes it, **re-validates every component key
server-side** against the canonical registry (untrusted keys fail closed with HTTP 400),
resolves it via `resolve_candidate_appearance` → `resolve_store_appearance_manifest_state`,
and feeds the resulting `ResolvedStoreAppearance` to the same `build_page_render_items`
renderer. No second route, no second renderer, no candidate Draft, zero writes. Verified
live: candidate preview returns HTTP 200 through the existing route (browser QA scenario M).

## Canonical Apply path (atomic)
One merchant Apply → one `design_lab.apply_candidate` mutation through
`r4_mutation_service.apply_mutation`: one `base_revision`, one stale check, one tenant
boundary, one transaction, one history entry, one revision advance. The handler validates
every component against the registry **before any write** (invalid ⇒ full rollback, zero
partial writes), applies non-theme families via the single `_persist_manifest_selection_updates`
writer, and applies Theme via the W2 `apply_theme`/`clear_theme` owner. The client sends
only intent + draft id; the server materialises and re-validates the mutation.

## Write-time reconciliation
Added the generalized canonical writer `appearance_authority_service.apply_component_variant(
version, family, component_key)`, mirroring `apply_header_variant`/`apply_footer_variant`.
It writes `selections[family] = component_key` through the single
`persist_store_appearance_manifest` primitive — the canonical seam that reconciles the
render-time-overlay families (`hero`/`product_view`/`card`/`badge`) into persisted manifest
state, so after Apply the persisted manifest and the rendered component agree (verified by
tests) and no family is "changed only in the renderer".

## Stale protection / Tenant isolation / History
- **Stale:** applying a candidate with a base_revision older than the live Draft ⇒
  `R4StaleRevision` (HTTP 409), zero partial writes (tested).
- **Tenant:** Store A's candidate applied against Store B's draft id ⇒ `draft_not_found`
  (HTTP 400); both stores' manifests unchanged (tested).
- **Undo/Redo:** a Design Lab Apply participates in the existing history; Undo restores the
  pre-Apply appearance, Redo restores the applied appearance (tested).

## No-write-before-Apply proof
The transient flow (generate → candidate_to_preset → resolve → compare → reset →
return-to-DNA → preview) leaves `appearance_config`, `header_config`, `footer_config`,
`edit_revision`, `template_provenance`, `template_baseline_snapshot`, the manifest, page/
section counts, history count and registered-preset count **byte-for-byte unchanged**
(tested in `DesignLabNoWriteBeforeApplyTests`; the browser QA also confirms the real Draft
is unchanged until Apply).

## Browser QA (see `08_browser_qa_report.md`)
Existing Playwright harness conventions (bundled `playwright-core` + installed Chromium),
two materially different templates (`dark_digital`, `warm_boutique`), three viewports
(desktop 1440×900, tablet 768×1024, mobile 390×844), RTL. Scenarios A–H + candidate
preview HTTP 200 all PASS; 0 console errors, 0 failed requests, no horizontal overflow.

## Tests
- **Focused W3** (`test_w3_design_lab`): **37 tests — OK** (`02_green_focused.txt`).
- **TDD RED** first observed genuinely (`01_red_design_lab.txt`): 29× missing
  `design_lab_service`, 7× missing `apply_component_variant`; zero setup/fixture failures.

## Regression (see `06_regression.txt`, `06b_w1_cart_pricing.txt`)
- **W2 Theme suite:** 58 tests — OK (baseline preserved; W3 adds none to that module).
- **Targeted appearance/preset/preview/mutation/history:** 518 — OK (1 pre-existing skip).
- **Candidate preview** (`NonDestructiveTemplatePreviewTests`, task2/task3 preview): OK.
- **W1 cart/pricing:** 105 — OK.

## Full-suite status + base comparison (see `07*`)
`apps.storefront_builder.tests`: **3197 tests, 30 failures + 2 errors + 4 skipped.**
Compared against a **separate clean clone** of the certified base `e28b563` (3160 tests,
30 failures + 2 errors + 4 skipped): **W3-only failures = 0**, **base-only differences = 0**,
**changed pre-existing failure reasons = 0** (32 shared failing tests, identical reasons).
The W3 failure set reduces exactly to the pre-existing base set (all Ready-Template recipe/
version contract drift + pre-existing R4/editor UI expectations, none related to Design Lab).

## Gates (see `10_repo_gates.txt`)
- Django check: **0 issues**. `makemigrations --check --dry-run`: **No changes detected**.
- `git diff --check`: clean. No env artifacts tracked. **Migrations = 0.**

## Architecture duplication audit (see `09_architecture_duplication_audit.md`)
1 candidate engine (reused), 1 preview renderer, 1 preview route (reused), 1 draft model,
1 manifest, 1 registry, 1 mutation boundary, 1 history, 1 theme owner; 0 design-lab
models/tables/migrations, 0 candidate registration, 0 localStorage authority, 0 JS draft
writes, 0 per-template random engines. **Gate: PASS.**

## Commits (base → head)
```
5444b11 feat: reconcile appearance component writes (apply_component_variant)  [Green 1]
569481d feat: add transient Design Lab random mix (design_lab_service)         [Green 2]
8773aa3 feat: add Design Lab candidate preview integration (storefront_preview) [Green 3]
7d4c7e1 feat: add atomic Design Lab apply mutation (design_lab.apply_candidate) [Green 5]
b6edc82 feat: add Design Lab R4 controls (endpoint + panel + JS)               [Green 4]
1d41787 test: P5-W3 focused + regression evidence
39bdb6c fix: reconcile R4 JS guardrails with Design Lab endpoint (full-suite)
eb58fa9 test: P5-W3 Design Lab browser QA (Playwright)
a5cdef0 docs: architecture duplication audit + repo gates
```

## Known limitations / deferred items
- **Layout / motion / mega_menu are intentionally not randomized** by Random Mix (mega_menu
  has a single option; layout is page composition; motion is a subtle token). They remain
  valid canonical selections and are never fabricated; this keeps Random Mix focused on
  visible chrome/section DNA and page composition strictly preserved.
- **Pre-existing full-suite failures (30F + 2E) are unchanged** and are NOT addressed by W3
  (they belong to Ready-Template recipe/version contracts and pre-existing R4 UI
  expectations at the certified base). They are documented, not hidden.
- **P5-W4 not started** (frozen): no W4 branch, no W4 code, no W4 tests.



---

# Independent Architect review repair (PR #9)

Independent review of head `4c41f31` returned CRITICAL 0 / IMPORTANT 3 / MINOR 1,
verdict NOT READY FOR MERGE. The following state-machine defects were repaired on
the **same** branch/PR (no restart, no new module, no model, no migration). RED
tests were written first (`11_red_roundtrip_repair.txt`), then made GREEN
(`12_green_roundtrip_repair.txt`); all exercise the REAL `/design-lab/` HTTP
endpoint round-trips, not only direct Python calls.

## Candidate base-state preservation across HTTP
The transient `DesignLabCandidate` now carries BOTH the immutable **generation
base** and the evolving **working state**, so a real HTTP round-trip no longer
collapses them (the previous decode set `base = candidate`, causing self-compare):
- `base_selections`, `base_settings` — fixed original Base for Compare/Return.
- `candidate_selections`, `candidate_settings` — evolving working state.
- `locked_families`, `seed`.
- `base_revision`, `draft_id` — generation binding for stale/tenant checks.

## Candidate current working state
Chained operations evolve the CURRENT candidate (Architect IMPORTANT 2):
`generate_candidate(draft, *, current_candidate=None, ...)` starts randomization
from the current candidate's working selections when chaining (not the committed
Draft), so Randomize One changes only the requested family and Random Mix
re-randomizes only unlocked eligible families — all other candidate choices are
preserved. The original Base stays fixed for the whole experiment.

## Signed / integrity-protected transient token
The transport token is now produced by **`django.core.signing`** (HMAC over
`SECRET_KEY`, `salt="storefront_builder.design_lab.candidate.v1"`, `compress=True`,
bounded `max_age = 6h`) instead of plain editable Base64. `decode_candidate_token`
verifies the signature and validates shape/types; a tampered/expired token raises
`ValueError` → controlled 400. The token is a tamper-evident transport, never an
authority: selections/settings are still re-validated through the canonical
Store-Appearance validator on preview and apply.

## Candidate generation revision + draft identity
`reset_candidate`/`generate_candidate` stamp `base_revision = draft.edit_revision`
and `draft_id = draft.pk` at generation time; these survive the signed token.

## Real-flow stale rejection
`candidate_is_stale(draft, candidate)` returns True when the candidate's
`draft_id`/`base_revision` no longer match the active Draft. The `/design-lab/`
`apply_payload` action calls this as a **preflight** and returns HTTP 409
`stale_candidate` BEFORE producing any mutation — it never silently rebases the
old candidate. The canonical `apply_mutation` boundary remains the FINAL
transactional stale-write enforcement (a race after preflight still yields
`R4StaleRevision` 409). Proved through the real route sequence:
random_mix @N → real canonical edit → N+1 → `apply_payload` old token → 409, no
write, N+1 preserved (`test_real_flow_stale_candidate_apply_is_rejected`).

## Chained Randomize-One preservation & Lock-current-candidate semantics
`test_randomize_one_after_random_mix_preserves_other_candidate_families` and
`test_lock_after_randomize_preserves_current_candidate_value` (endpoint
round-trips) prove non-requested families are preserved from B and a locked
family holds its CURRENT candidate value H1 (never reverts to committed Draft H0).

## Real Compare diff / real Return-to-DNA proof
Compare now measures the candidate against the ORIGINAL Base and detects both
selection AND settings differences (e.g. Theme intensity — `test_compare_detects
_settings_difference`). Return-to-DNA yields Base A family-by-family across a real
round-trip (`test_return_to_dna_after_real_http_roundtrip_yields_base`).

## Broad exception swallowing removed (MINOR)
The Design Lab decode/validation paths no longer use bare `except Exception`.
Only `ValueError` (bad/tampered/expired token) and `InvalidStoreAppearanceContract`
(canonical contract) become controlled 400s; unexpected programming errors
propagate and fail loudly.

## Browser QA now asserts DATA (not visibility)
`w3_design_lab_qa.mjs` reads server-authoritative `candidate_selections`/
`base_selections`/`diffs` from the read-only endpoint: Compare asserts a real
changed family with `base_label != candidate_label`; Return asserts exact Base
restore family-by-family; chained Randomize asserts other families preserved +
footer changes; Lock asserts the CURRENT candidate value is held; a new stale
scenario asserts 409 `stale_candidate`; Apply asserts the Draft revision advances
0→1 only after the explicit Apply. Both templates × 3 viewports, RTL, OVERALL
PASS, 0 console errors, 0 failed requests.

## Post-repair verification
- W3 focused: **46 tests OK** (37 original + 9 endpoint round-trip).
- W2 Theme regression **58 OK**; targeted regression **619 OK** (adds
  `test_r4_foundation` + `test_r4_inspector` JS guardrails); W1 cart/pricing **105 OK**.
- Full `apps.storefront_builder.tests` on the final head `a41531f`: **3206 tests,
  30 failures + 2 errors** — identical failure identity+reason set to the certified
  base `e28b563`. **W3-only failures = 0; changed pre-existing reasons = 0.**
- Django check 0 issues; `makemigrations --check` = No changes detected;
  `git diff --check` clean; **migrations = 0**; no env artifacts tracked.

## Repair commits
```
40661a7 fix: candidate state-machine repair (signed token, base state, chaining, stale, precise except)
bca004d test: post-repair regression + full-suite base comparison
a41531f test: browser QA asserts DATA (+ endpoint candidate/base selections)
```
