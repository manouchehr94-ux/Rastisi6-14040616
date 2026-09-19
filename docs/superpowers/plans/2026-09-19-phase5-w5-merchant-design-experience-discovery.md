# P5-W5 — Merchant-Facing Storefront Design Experience: Discovery & Implementation Planning

Status: **DISCOVERY AND PLANNING ONLY — no W5 implementation has started.**
Official starting branch: `feature/phase5-design-expansion`
Official checkpoint HEAD: `81abb435c6421197117f8f570993b64ca485d4af` (W4C merge, PR #12, MERGED, APPROVED)
Discovery-documentation commit (evidence/planning only, 0 production files): `2c00b015421781e42eae6ad1e57884a5d464299f`

**Revision note**: this document was repaired following an Independent Architect review of the initial discovery. The Architect accepted the fact-finding but required (1) a correction to the process record below, (2) two binding architectural decisions be recorded rather than left open, (3) a corrected technical scope for the Bottom Navigation gap, (4) explicit dispositions for the inert `layout`/`mega_menu` families, (5) an explicit merchant-journey certification plan, and (6) a reordered workstream sequence that closes architectural risk before UI expansion. All are incorporated below. **No code has changed as a result of this repair round — this is a planning-document-only revision.**

**Final Architecture Correction note**: a second Architect pass found the repaired W5A plan still contained a real contradiction — it described "only one active mutation surface" while simultaneously treating the legacy Restore and Industry-Layout-Apply endpoints as an unconditional, unprotected exception to that policy. Direct re-reading of `layout_service.restore_version()` and `layout_service.apply_industry_layout()` confirmed both are genuinely mutating (each deletes the current Draft and creates a new one, with no stale-write check) and cannot be grouped with the truly read-only History browser. §5 and §8 (W5A) below are corrected to a three-class route model (A/B/C); §"Merchant Journey Certification Plan" cross-references in `merchant_journeys.md` are corrected for the Bottom-Nav journey's actual write path. **Still no code changed — planning-document-only.**

Supporting evidence (read alongside this document):
- `docs/qa_evidence/storefront_design_engine/phase5/w5_discovery/current_state_inventory.md`
- `docs/qa_evidence/storefront_design_engine/phase5/w5_discovery/gap_matrix.md`
- `docs/qa_evidence/storefront_design_engine/phase5/w5_discovery/authority_map.md`
- `docs/qa_evidence/storefront_design_engine/phase5/w5_discovery/merchant_journeys.md`

---

## 0. Process record — corrected

The initial discovery round's closing report stated "no new commits were created." **That statement is superseded and was accurate only at the moment it was written; it became false immediately afterward.** The corrected, truthful record is:

- One documentation/evidence-only commit, `2c00b015421781e42eae6ad1e57884a5d464299f`, was created **after** the initial no-commit report, at the explicit direction of this repository's stop-hook tooling (which requires untracked files to be committed and pushed before a turn ends) — not autonomously initiated ahead of that requirement.
- That commit contains **exactly the five discovery documents** listed above (four evidence files + this plan). `git show --stat 2c00b015` confirms: 5 files changed, all under `docs/`, 0 files under `apps/`, 0 migrations, 0 templates, 0 JS/CSS.
- **Production code changes introduced by that commit: 0.**
- No historical W4C evidence (`docs/qa_evidence/storefront_design_engine/phase5/w4_certification/...`) was altered, reset, or rewritten. The commit is purely additive.
- **No reset or history rewrite is required or has been performed.** The commit stands as an accurate, permanent record of the discovery round; this repair round adds a further commit-free revision on top of it (per the current binding instruction: do not commit, do not push, in this round).

This correction affects only §11 (git/process history) of this plan; no other discovery finding is invalidated by it.

---

## 1. What already exists (do not rebuild)

Full detail in `current_state_inventory.md` and `authority_map.md`. Unchanged from the initial discovery — the Architect's review accepted this fact-finding:

- **The R4 Builder is the live, authoritative merchant Storefront Builder** (`/admin-portal/storefront-builder/r4/`), default-enabled for every Store. A legacy "R3" surface remains wired in — see §3 below for the now-binding disposition of that surface.
- **The 50-Template Gallery already exists and is fully merchant-facing**: real page, real nav entry, all 50 templates, real static preview screenshots, real Apply-to-Draft flow with content preservation, provenance tracking, and Demo-vs-merchant-data preview modes.
- **The canonical Apply-to-Draft flow is a single, well-tested authority** (`preset_service.apply_preset()`), never copying catalog/business data.
- **Design Lab already exists and is fully implemented** (P5-W3, already merged): transient candidate state, compatibility-scoped Random Mix, per-family locks, Compare, Return-to-original-DNA, and a real Apply-to-Draft path.
- **Reversible Theme Overlay already exists** (P5-W2, already merged) and is the most thoroughly tested family in the system.
- **There is exactly one shared renderer** for Preview, Design Lab preview, non-destructive template preview, and the public storefront.
- **9 of 16 Store-Appearance families are COMPLETE vertical slices today**: Header, Motion, Footer, Palette, Typography, Density, Radius, Content Width, Theme.

## 2. What is built but not yet merchant-visible through the canonical editor

- **Mobile Bottom Navigation** has a real registry and a real renderer for both Preview and Public, but the canonical R4 editor cannot change it — see the corrected technical scope in §5 below (this is deeper than a missing allowlist entry).
- **Template provenance** is recorded on every Apply but never surfaced to the merchant in any UI (low-priority, not a workstream by itself).

## 3. Design-Lab-only by intentional product boundary — NOT a defect

Per the binding Builder-vs-Lab decision (§7 below), **Hero, Product View, Product Card (family-level), and Badge are correctly Design-Lab-only for W5.** These four families have full registries, renderers, and Design-Lab wiring; the merchant already has access to them through the already-implemented Advanced Design Lab. This is not a missing capability and must not be listed as a defect in the gap matrix. A future UX study may promote any of them to the Normal Builder; that is out of scope for W5.

## 4. Reserved/inert registry entries — binding disposition

- **The typed Store Appearance `layout` (composition) family**: registered with 9 variants, but zero render consumers exist anywhere in the codebase. A separate, real, fully working per-Container layout system (2/3/4-column rows) already covers the actual merchant need for page composition. **Binding disposition**: the typed `layout` family is **reserved/inert** for W5 — it must not be advertised to merchants as a functioning independent control, and W5 must **not** build a second store-wide composition renderer merely to activate it (that would be exactly the kind of duplication this initiative exists to prevent). Existing manifests/Ready-Template recipes that reference `layout` selections must continue to validate and load without error — nothing about existing persisted data changes. The real, canonical mechanism for composition remains the per-Container layout system.
- **The typed Store Appearance `mega_menu` family**: registry has exactly one component, `mega_menu.none.v1`. The real mega-menu presentation today is owned by specific **Header** variants, not by an independently switchable family. **Binding disposition**: `mega_menu` is **reserved/compatibility state** for W5 — not advertised as an independent merchant control, and W5 must not build a second navigation/menu authority just to populate this registry. If independent Mega Menu customization is authorized in a future phase, it must reuse the existing Header/navigation rendering architecture, declare Header capability compatibility, and avoid a second navigation authority — it is explicitly not a W5 deliverable.

Neither disposition requires removing the registry entries (removal risks breaking manifest/Ready-Template-recipe compatibility) — both are "leave registered, document as reserved, do not build around" decisions.

---

## 5. Binding architectural decision — R3/R4 single-active-write-surface policy (corrected)

This is now a **W5 architectural prerequisite**, not an end-of-W5 cleanup item. **Binding policy, final wording: when R4 is active for a Store, no R3-editor-specific unprotected write endpoint may mutate that Store's Draft.** A unique capability that previously existed only on a legacy page must either (a) be read-only, or (b) be converged onto a canonical R4-safe write boundary. The policy is **not** solved by keeping any unsafe mutating exception, however narrow.

- **R4 remains canonical and default.**
- R3's full write surface may remain available **only** for Stores explicitly pinned to `r4_editor_enabled = False` — the rollback mechanism, unweakened.

### Legacy route inventory and classification (corrected)

A prior, code-verified audit already exists and was re-read for this repair: `docs/qa_evidence/storefront_appearance_convergence/phase4/legacy_disposition.md`. Its findings, re-confirmed against the current W4C checkpoint source, classify every legacy surface. **This round corrected two rows** that a prior pass had wrongly merged: History and Restore are not one capability, and Industry-Layout-Apply is mutating with the same risk profile as Restore, not a read-only-adjacent item.

| Legacy surface | Classification | Current-code disposition |
|---|---|---|
| `storefront_discard` (bare discard) | MUTATING — HAS R4 EQUIVALENT | Already **RETIRED**: zero live UI callers, R4's `storefront-builder/r4/discard/` is the proven replacement |
| Settings save (all section types), Container/Cell/Row composition (add/settings/layout/move/remove), Section toggle/lock, Granular reset family (section/field/page/header/footer/storefront-to-baseline), Full Appearance/Header/Footer editor forms | MUTATING — HAS R4 EQUIVALENT | R4 has **full, re-verified functional parity** for every one of these; the legacy views/forms are functionally redundant. `editor.html` already stopped rendering their UI for any Store on the live R4 default — but the underlying URLs carry no server-side `r4_editor_enabled` gate. This is **Class A** below. |
| Undo / Redo / Publish | MUTATING — HAS R4 EQUIVALENT (already converged) | Already share the exact same `r4_mutation_service._run_history_command`/`layout_service.publish` — no separate legacy implementation exists to gate |
| Section collapse toggle | READ/UI-ONLY | Editor-session UI convenience, no persisted state — **CANONICAL KEEP** |
| **History browser** (`storefront-builder-history` / `storefront_history`) | **READ ONLY — CANONICAL KEEP (corrected)** | Confirmed by direct source read: no `@require_POST`, only calls `layout_service.list_versions()` and renders a list — never mutates the Draft. Safe unconditionally under R4. |
| **Restore Version** (`storefront-builder-restore` / `storefront_restore`) | **MUTATING — LEGACY-ONLY, REQUIRES CONVERGENCE (corrected)** | Confirmed by direct source read of `layout_service.restore_version()`: deletes the current Draft, creates a new one, reassigns `layout.draft_version` — a real Draft-identity replacement, with **no `base_revision`/stale-write check**. Cannot be an unconditional exception. **Class C below.** |
| **Industry-vertical layout preset installer** (`storefront_apply_industry_layout`) | **MUTATING — LEGACY-ONLY, REQUIRES CONVERGENCE (corrected)** | Confirmed by direct source read of `layout_service.apply_industry_layout()`: identical Draft-replacement pattern to `restore_version()` (its own docstring says "exactly like restore_version"), same absence of a stale-write check. **Class C below.** |
| Ready Template gallery / apply | MUTATING — dual, both canonical | `apply_preset_with_checkpoint` (legacy entry) and `appearance.template.apply` (R4 entry) converge on `preset_service.apply_preset()` — not a retirement candidate. Lives in `views.py` alongside Class A routes but **must not** be caught by a module-wide guard. **Class B below.** |
| Section-scoped media CRUD, Global Hero/Banner admin | MUTATING — shared/legitimate | Already single shared authority (a separate module, `media_views.py`) — **CANONICAL KEEP**, unaffected by any guard scoped to `views.py` |

### Corrected W5A architecture — three route/capability classes

**Class A — R3-editor-only redundant mutations** (settings save, container/row composition, toggle/lock, granular resets, appearance/header/footer forms). For `r4_editor_enabled=True`: fail closed via **one shared eligibility guard**. For `r4_editor_enabled=False`: remain available unchanged as the rollback editor.

**Class B — shared canonical non-R3 capabilities.** A route is not Class A merely because its view function lives in `apps/storefront_builder/views.py`. Ready Template Gallery/Apply and `storefront_preview` are concrete, confirmed examples — real, shared, canonical, and must never be disabled by a broad module-level assumption. The Class A guard must be an **explicit route allowlist/denylist**, never "everything in this module."

**Class C — legacy-only mutating capabilities requiring convergence** (Restore Version, Industry Layout Apply). Both are real, still-required, no-R4-equivalent capabilities — but neither may remain a permanently unprotected mutating exception once R4 is active, since that directly contradicts the single-active-write-surface policy. **Disposition**: for `r4_editor_enabled=True`, each must be reachable only through a new, thin **canonical R4-safe mutation/replacement boundary**, reusing the exact pattern R4's own existing "replace Draft identity" actions already use — `storefront_r4_reset_storefront` and `storefront_r4_switch_template` both already validate `layout.r4_editor_enabled`, parse a JSON body, and reject any `base_revision` that isn't a valid non-negative integer, *before* calling into the underlying replacement service. Concretely: new R4 endpoint/action → `base_revision`/active-Draft validation → tenant/store validation → **calls the existing, unmodified `layout_service.restore_version()` / `layout_service.apply_industry_layout()`** → new revision returned, client reloads (same contract shape as Reset Storefront/Switch Template). **No new restore or industry-layout business logic — the existing service functions are reused verbatim.** For `r4_editor_enabled=False`, the original legacy POST endpoints remain the rollback path, unchanged.

**No implementation happens in this round.** This corrected three-class model is recorded as the shape of the future W5A workstream (§8).

---

## 6. Binding terminology decision — "Ready Template" vs. "Style Pack"

The two merchant-facing concepts that were both being called "Template" (see `authority_map.md` Finding #2) are no longer to share that name.

| Concept | Canonical English term | Canonical Persian term | Underlying code (unchanged) |
|---|---|---|---|
| The 50 layout/design recipes (this initiative) | **Ready Template** | **قالب آماده** | `layout_preset_registry.py`, `a8_ready_templates.py` — no rename |
| The 10-item style-token bundle (font/radius/density/motion/etc.) | **Style Pack** | **بستهٔ سبک** | `appearance_registry.TEMPLATE_REGISTRY`, `template_slug` — no rename |

**Binding constraints**:
- Do **not** rename the persisted `template_slug` field or the `TEMPLATE_REGISTRY`/`TemplateDefinition` internal names in this phase merely for terminology — that would require a migration-adjacent internal rename for zero merchant-facing benefit and violates the "zero migrations" default.
- The rename applies to **merchant-facing labels, documentation, and new/updated tests only** — e.g. the R4 editor's `templates` choice list (fed from `appearance_registry.list_templates()`) should be labeled "بستهٔ سبک" / "Style Pack" in the UI, while the Ready Template Gallery and its 50 entries keep the "قالب آماده" / "Ready Template" label they already use.
- Internal compatibility naming (the field is still called `template_slug` in code, the registry is still `appearance_registry.TEMPLATE_REGISTRY`) must be documented clearly wherever this distinction matters (this document, `authority_map.md`, and future code comments introduced by any workstream touching this area) so a future engineer isn't confused by the code/label mismatch.

---

## 7. Binding decision — Normal Builder vs. Design Lab boundary

**Promote Mobile Bottom Navigation to the Normal Builder.** It is a high-value, mobile-storefront-critical control and has a real, closable R4 gap (§8, W5B).

**Do not promote Hero, Product View, Product Card, or Badge during W5.** They remain accessible through the already-implemented Advanced Design Lab. This is a deliberate product boundary, not a missing capability — see §3 above and the corrected gap matrix. A future UX study may revisit this; it is out of scope for W5.

This decision keeps the Normal Builder simple (per the R4 architecture's own §23 mandate: a merchant should be able to swap Header 08→14 "without seeing or understanding the entire combinatorial engine") while ensuring the one family with a genuine mobile-navigation stake gets a real fix.

---

## 8. Revised W5 workstream decomposition

Reordered so architectural convergence happens **before** additional merchant UI expansion, per the binding instruction. Workstreams for already-complete functionality are not reintroduced.

### W5A — Canonical Editor Safety / Architecture Closure (prerequisite — goes first, corrected)
- **Problem**: two structurally different mutation-safety guarantees (R4's stale-write-protected dispatcher vs. R3's unprotected direct-write views) currently coexist against the same Draft for any Store, and the legacy write endpoints remain server-reachable regardless of the per-Store editor flag — including two mutating capabilities (Restore Version, Industry Layout Apply) that a prior planning pass incorrectly treated as safe unconditional exceptions.
- **PO-visible outcome**: for a Store on the R4 default, no legacy endpoint can mutate its Draft unprotected — Class A redundant routes fail closed, Class C capabilities (Restore, Industry Layout Apply) work through a new R4-safe entry point with the same stale-write/tenant guarantees as every other R4 mutation, and Class B shared canonical routes (Ready Template Gallery/Apply, `storefront_preview`) are explicitly unaffected. A Store explicitly pinned to legacy keeps its full rollback capability, including Restore/Industry-Layout-Apply, unchanged. Merchant-facing labels distinguish "Ready Template" from "Style Pack." The `layout`/`mega_menu` families are documented as reserved, not silently left ambiguous.
- **Existing code reused**: 100% of the underlying services (container_service, row_service, section_data_service, appearance_authority_service, layout_service — including `restore_version()`/`apply_industry_layout()` **unmodified**, edit_history_service, preset_service) — no service is rewritten. The new Class C entry points reuse the exact `r4_editor_enabled` + JSON body + validated `base_revision` pattern already implemented in `storefront_r4_reset_storefront`/`storefront_r4_switch_template`.
- **Exact missing code**:
  - Class A: one shared server-side eligibility guard (single decorator/check) restricting an **explicit list** of Class A routes to `r4_editor_enabled=False` Stores.
  - Class B: no code change — an explicit exclusion list (or the guard's own allowlist design) ensures Ready Template Gallery/Apply and `storefront_preview` are never touched.
  - Class C: two new, thin R4 endpoints/actions (one for Restore, one for Industry Layout Apply) that validate `base_revision`/tenant scope exactly like `storefront_r4_reset_storefront` does, then call the existing `layout_service.restore_version()`/`apply_industry_layout()` verbatim.
  - Label-only changes for the Style Pack rename; a documentation/comment update marking `layout`/`mega_menu` as reserved in their registry definitions.
- **Architectural authorities used**: existing `StorefrontLayout.r4_editor_enabled` flag; existing `base_revision`/`edit_revision` stale-write mechanism; no new flag, no new model field, no new service.
- **Explicit non-goals**: no removal of any legacy view function; no removal of rollback capability for pinned-back Stores (Restore/Industry-Layout-Apply included); no new restore or industry-layout business logic (the existing service functions are reused verbatim, never duplicated); no registry-entry deletion for `layout`/`mega_menu`; no rename of `template_slug`; no module-wide (`views.py`-level) guard.
- **Dependencies**: none technical.
- **TDD strategy** (corrected, ten required cases):
  - A. For `r4_editor_enabled=True`: Class A redundant POST mutation routes fail closed.
  - B. For `r4_editor_enabled=False`: rollback Class A mutations remain functional, unchanged.
  - C. Class B shared canonical surfaces (Ready Template Gallery/Apply, `storefront_preview`) are **not** accidentally blocked merely because their view functions live in `views.py`.
  - D. History browser remains readable under R4 (never blocked — it's read-only).
  - E. Restore under R4 uses the new canonical stale-aware replacement entry point successfully.
  - F. A stale Restore attempt (wrong `base_revision`) cannot replace a newer Draft — rejected with a 409-shaped response, same as other R4 replace-identity actions.
  - G. Industry-Layout Apply under R4 uses the new canonical stale-aware replacement entry point successfully.
  - H. A stale Industry-Layout-Apply attempt cannot replace a newer Draft.
  - I. Cross-Store Restore and Industry-Layout-Apply attempts fail closed (tenant isolation), for both the legacy and the new R4 entry points.
  - J. No second Restore or Industry-Layout implementation is created — the new R4 endpoints assert they call the existing `layout_service` functions, not a reimplementation.
- **Browser QA strategy**: extend existing legacy-editor Playwright/QA coverage with the pinned-back-Store case (Class A) and a new R4-editor Restore/Industry-Layout-Apply smoke path (Class C); no new harness.
- **Security/tenant risks**: this workstream *reduces* risk (closes two genuinely unprotected mutating write paths, not just the previously-identified Class A ones) rather than introducing any.
- **Duplication risk**: none — one shared guard for Class A (never per-view logic), Class B is explicitly carved out by name, and Class C reuses existing services and the existing R4 replace-identity request pattern verbatim.
- **Definition of done**: single-active-write-surface policy holds with **no unprotected mutating exception of any kind**; History browser stays read-only and always reachable; Restore and Industry-Layout-Apply are R4-safe when R4 is active and unchanged as rollback-only when it isn't; Ready Template Gallery/Apply and `storefront_preview` are provably unaffected; Style Pack terminology recorded in UI copy; `layout`/`mega_menu` documented as reserved; zero migrations.

### W5B — Mobile Bottom Navigation R4 Parity
- **Problem**: corrected technical scope (see `gap_matrix.md` and `current_state_inventory.md` for full detail) — merely allow-listing `mobile_nav_variant` is insufficient; the value is never applied to the mutation candidate, and the R4 Global Design read projection has no `mobile_nav_variants` choice list.
- **PO-visible outcome**: merchant can change Mobile Bottom Navigation from the canonical R4 editor, exactly like Header/Footer today.
- **Existing code reused**: `appearance_authority_service.apply_footer_variant()` (already accepts `mobile_nav_variant` and already owns syncing both `footer` and `bottom_nav` typed-manifest families in one call); `global_region_registry.GLOBAL_MOBILE_NAV_REGION`/`list_global_variants()` (already exists, just not called from `_build_global_design_context()`); the existing generic `data-r4-global-field`/`data-r4-global-mutation="footer.update"` front-end mechanism (already used for `footer_variant` in the exact same panel).
- **Exact missing code** (six concrete points, corrected from the initial under-scoped proposal):
  - A. Add `mobile_nav_variant` to `_FOOTER_UPDATE_ALLOWED_PATCH_KEYS` in `r4_mutation_service.py`.
  - B. Inside `_apply_footer_update()`, explicitly apply the posted value — `if "mobile_nav_variant" in patch: candidate["mobile_nav_variant"] = patch["mobile_nav_variant"]` — **before** `validate_footer_config()` is called. (Confirmed by direct source read: today `candidate = dict(draft.effective_footer_config())` seeds the existing value, but no branch in the function ever overwrites it from `patch`, so a client-submitted change would currently be silently dropped even if the key were allow-listed.)
  - C. Add a `mobile_nav_variants` entry to `_build_global_design_context()` in `r4_views.py`, built the same way `header_variants`/`footer_variants` already are: `list_global_variants(global_region_registry.GLOBAL_MOBILE_NAV_REGION)` (this constant already exists in `global_region_registry.py`).
  - D. Add a `<select data-r4-global-field="mobile_nav_variant">` inside the existing `<section data-r4-global-mutation="footer.update">` block in `r4/editor.html`'s footer group — confirmed the existing generic JS change handler (which reads `data-r4-global-mutation`/`data-r4-global-field` and posts to the already-wired `footer.update` mutation) requires **no new JS sender**; this is the same mechanism `footer_variant`'s own selector already uses in the same section.
  - E. Extend the existing `footer.update` mutation test suite to assert `mobile_nav_variant` round-trips into both `StorefrontLayoutVersion.footer_config` and the typed `bottom_nav` manifest selection via `appearance_authority_service.apply_footer_variant()` (already the shared owner of both).
  - F. Prove, via existing test patterns (no new test infrastructure): stale-write protection (`base_revision` mismatch → 409), tenant isolation (cross-Store rejection), Undo restoring the prior Bottom Nav variant, Redo restoring the new one, Preview reflecting the change, Publish carrying it to Public, and correct mobile-viewport rendering.
- **Non-goals**: no new Bottom-Nav-specific JS mutation sender; no new mutation type; no change to the legacy footer editor (which already has this control and keeps working).
- **Dependencies**: none — self-contained, and safe to build on top of W5A (though not blocked by it at the code level).
- **Duplication risk**: none — reuses every existing authority exactly as Header/Footer already do.
- **Definition of done**: merchant changes Bottom Nav from the R4 editor; F's full list of guarantees holds; zero migrations.

### W5C — Ready Template Preview UX
- **Problem**: pre-apply Gallery preview has no in-page lightbox and no Desktop/Tablet/Mobile toggle.
- **PO-visible outcome**: merchant can enlarge a template preview in-page and toggle device sizes before applying.
- **Existing code reused**: `ready_template_live_preview.html`, `storefront_template_live_preview` view, `build_candidate_render_items` (already the shared, non-duplicated renderer for this path), and — critically — the **existing** device-preview presentation behavior already built for the in-editor Draft preview, extracted/reused rather than reimplemented as a second JS device-state mechanism.
- **Exact missing code**: a modal/lightbox wrapper around the existing preview link; port/extract the existing device-switcher markup and JS logic onto the Gallery preview page.
- **Non-goals**: no second preview renderer, no second preview route, no duplicated device-state authority — the Architect's explicit constraint.
- **Duplication risk**: none, provided the device-switcher logic is extracted and reused, not rewritten twice.
- **Definition of done**: Gallery preview supports in-page enlarge + 3-viewport toggle; zero migrations.

### W5D — Merchant Design IA Closure
- **Problem**: after W5A-C, the editor's navigation/labels/help text need a final pass so the terminology decision (§6) and boundary decision (§7) are consistently reflected.
- **PO-visible outcome**: consistent "Ready Template" vs. "Style Pack" labeling everywhere; Bottom Nav sits naturally alongside Header/Footer in the Global Design panel; Advanced Design Lab remains clearly the home for Hero/Product View/Card/Badge unless a future decision changes that.
- **Existing code reused**: the existing R4 editor shell and its existing panel structure — no second shell.
- **Non-goals**: no promotion of Hero/Product View/Card/Badge (§7); no new application shell.
- **Definition of done**: labels/nav/help text consistent; no functional change beyond copy and navigation grouping.

### W5E — Merchant Journey Browser Certification
- **Problem**: the existing W4C harness certifies storefront **rendering**, not Builder **UX**. W5's changes are Builder-UX changes and need their own certification exercising real admin journeys.
- **PO-visible outcome**: confidence that W5A-D work end-to-end for a real merchant, not just at the unit-test level.
- **Existing code reused**: `tools/storefront_builder_r4_qa/run.mjs` and `qa_storefront_builder_r4.py` — extended, not duplicated.
- **Non-goals**: no second certification harness.
- **Scope**: see the full merchant-journey certification plan in `merchant_journeys.md` §"W5 Merchant Journey Certification Plan" (journeys A-P, covering Builder access, Gallery browsing, pre-apply device preview, Template Apply, independent Bottom Nav mutation with sibling-isolation proof, Undo/Redo, Design-Lab-without-history-spam, Design-Lab Apply, device preview, Publish, Public reflection, stale-revision conflict behavior, and cross-tenant fail-closed behavior).
- **Whether to rerun the full 704-cell matrix**: not hard-coded into this plan. That decision should be made at W5E's own implementation time based on which actual rendering surfaces W5A-D touched — if no Ready-Template rendering path changed (likely, since W5A-D are Builder-UX/mutation-contract changes, not renderer changes), a full 704-cell rerun is probably unnecessary and a targeted regression subset suffices; this must be re-assessed against the actual diff, not assumed now.
- **Definition of done**: journeys A-P pass; regression scope matches what was actually touched.

---

## 8a. Self-review — the contradiction check (Final Architecture Correction round)

Before finalizing this correction, the plan was re-checked against the specific contradiction the Architect flagged:

- **"Only one active mutation surface" while allowing an unprotected legacy Restore/Industry-Layout mutator under R4?** No longer present. §5's corrected policy wording is unconditional: no R3-editor-specific unprotected write endpoint may mutate a Store's Draft when R4 is active. Restore and Industry Layout Apply are Class C — they converge onto a canonical R4-safe boundary rather than remaining exceptions. Only the truly read-only History browser is exempted, because it never mutates anything.
- **Can the Class A guard accidentally block legitimate shared merchant surfaces purely because they live in `views.py`?** No — §5's Class B is an explicit, named carve-out (Ready Template Gallery/Apply, `storefront_preview`), and the W5A TDD plan's item C is a dedicated test asserting exactly this never regresses. The guard is specified as an explicit route allowlist/denylist, never a module-wide check.

Both checks pass. No further correction identified in this pass.

---

## 9. Recommended first implementation workstream

**W5A — Canonical Editor Safety / Architecture Closure.**

This supersedes the initial discovery's recommendation of the Bottom Nav fix as the first slice. The Architect's binding instruction is explicit: the R3/R4 write-surface risk **must not be deferred to the end of W5** and **must close before ordinary W5 UI expansion**. W5A is architecture-safe (reuses every existing service, adds one shared guard rather than per-view checks), reversible (a flag-driven guard, not a deletion), and testable in isolation from W5B-E. W5B (Bottom Nav) remains the next logical step immediately after, since it is fully scoped and has no dependency on W5A at the code level, but W5A is the one that must not wait.

**This is not being implemented in this round.** No implementation branch has been created.

---

## 10. Persian summary for the Product Owner

### توضیح برای صاحب فروشگاه

**۱. امروز صاحب فروشگاه واقعاً چه امکانات طراحی‌ای دارد؟**

صاحب فروشگاه امروز می‌تواند: هر ۵۰ قالب آماده را مرور کند؛ یک قالب را روی طرح پیش‌نویس خودش اعمال کند بدون تغییر محصولات و قیمت‌ها؛ هدر، فوتر، رنگ‌بندی، فونت، تراکم، گردی گوشه‌ها، عرض محتوا، حرکت، و تم‌های مناسبتی را مستقل تغییر دهد؛ از آزمایشگاه طراحی برای امتحان هیرو/کارت محصول/نشان تبلیغاتی/نویگیشن پایین موبایل استفاده کند بدون آلوده‌شدن تاریخچهٔ فروشگاه؛ Undo/Redo کند؛ پیش‌نمایش بگیرد؛ و منتشر کند.

**۲. چه چیزهایی پشت صحنه ساخته شده ولی هنوز در اختیار صاحب فروشگاه نیست؟**

نویگیشن پایین صفحه در موبایل به‌طور کامل ساخته شده اما در ویرایشگر اصلی و پیش‌فرض قابل تغییر نیست. همچنین یک ریسک معماری کشف شد: دو ویرایشگر (جدید و قدیمی) هنوز هر دو می‌توانند هم‌زمان روی یک فروشگاه تغییر ایجاد کنند، که باید پیش از هر توسعهٔ دیگری بسته شود.

**۳. W5 قرار است دقیقاً چه چیزی به محصول اضافه کند؟**

اولویت اول W5 یک اصلاح معماری است، نه یک ویژگی جدید: اطمینان از این‌که برای هر فروشگاه فقط یک ویرایشگر می‌تواند تغییر واقعی ایجاد کند (ویرایشگر قدیمی فقط برای فروشگاه‌هایی که صراحتاً به آن بازگردانده شده‌اند باقی می‌ماند). پس از آن: نویگیشن پایین موبایل به ویرایشگر اصلی اضافه می‌شود؛ پیش‌نمایش قالب‌ها کمی بهتر می‌شود؛ و دو تصمیم اسمی نهایی می‌شود — «قالب آماده» برای ۵۰ قالب، و «بستهٔ سبک» برای مجموعهٔ قدیمی‌تر ۱۰ سبک ظاهری، تا این دو با هم اشتباه گرفته نشوند.

هیرو، طرح نمایش محصول، طرح کارت محصول، و نشان تبلیغاتی **در W5 به ویرایشگر اصلی اضافه نمی‌شوند** — این یک نقص نیست، بلکه تصمیمی آگاهانه است: صاحب فروشگاه از قبل از طریق «آزمایشگاه طراحی پیشرفته» به همهٔ آن‌ها دسترسی دارد، و نگه‌داشتن ویرایشگر اصلی ساده، یک اصل طراحی محصول است.

**۴. وقتی W5 تمام شود، صاحب فروشگاه چه کارهایی می‌تواند انجام دهد؟**

همهٔ امکانات فعلی، به‌علاوه تغییر مستقیم نویگیشن پایین موبایل از ویرایشگر اصلی، پیش‌نمایش بهتر قالب‌ها، و اطمینان معماری از این‌که هیچ تغییری از یک ویرایشگر «قدیمی و فراموش‌شده» به‌طور پنهانی روی فروشگاهش اثر نمی‌گذارد.

**۵. بعد از W5 چه بخش‌هایی از کل RastiSi هنوز باقی می‌ماند؟**

W5 فقط تجربهٔ طراحی فروشگاه را تکمیل می‌کند. سفارش، پرداخت، حمل‌ونقل، موجودی، گزارش‌ها و بازاریابی بخشی از این فاز نیستند. همچنین ارتقای احتمالی هیرو/کارت محصول/نشان تبلیغاتی به ویرایشگر اصلی، تصمیمی است که آگاهانه به آینده موکول شده و نیازمند یک مطالعهٔ تجربهٔ کاربری جداگانه است.

---

## 11. Change policy compliance (corrected)

**This repair round**: no production code, migrations, models, views, URLs, templates, JavaScript, CSS, services, registries, Ready Template definitions, renderer, mutation service, or Draft/Published behavior was modified. Only the five discovery/planning documents were revised. Per the explicit instruction for this round, **nothing was committed and nothing was pushed** — the working tree carries these edits as uncommitted changes pending Product Owner/Architect review.

**Corrected historical record for the prior round**: one documentation-only commit (`2c00b015`, 5 files, 0 production files) was created and pushed after the initial discovery's "no commits" report, at the direction of repository tooling that requires untracked files to be committed before a turn ends (see §0). This is now the accurate, permanent record.
