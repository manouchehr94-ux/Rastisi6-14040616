# P5-W5 Discovery — Five Real Merchant Journeys

Status: DISCOVERY ONLY — no production code changed.
Source commit: `81abb435c6421197117f8f570993b64ca485d4af`.

**Revision note (Architect repair round)**: added a "W5 Merchant Journey Certification Plan" section at the end of this document, recording the binding requirement that W5's final certification exercise real admin Builder journeys (not just re-run the W4C rendering-certification harness).

**Revision note (Final Architecture Correction round, minor)**: Journey G's evidence owner was corrected. Bottom Navigation's future write path is `footer.update` → `_apply_footer_update()` → `appearance_authority_service.apply_footer_variant()` (per the W5B corrected technical scope), not `_apply_appearance_component_update` (which is the generic single-component-family mutation path used by Hero/Product View/Card/Badge, an unrelated family group). The journey table below is corrected accordingly.

Each journey is traced from the current UI through backend and persistence, using the authorities documented in `authority_map.md` and `current_state_inventory.md`.

---

## Journey A — A new merchant wants to browse all 50 Templates

**CURRENTLY POSSIBLE: YES**

Trace:
1. Merchant clicks "قالب‌های آماده" in the dashboard nav (`base_admin.html:293-296`), or the template-switch dropdown inside the R4 editor.
2. → `GET storefront-builder/templates/` → `views.py:2194 storefront_template_gallery`.
3. View calls `layout_preset_registry.list_ready_templates()`, which filters the full 50-entry registry (`a8_ready_templates.py::_SPECS`) on `is_ready_template=True` — no slicing, no cap.
4. Template `template_gallery.html` renders all 50 as cards with real `.webp` screenshots (from `apps/storefront_builder/static/ready_template_previews/<key>/`), each with "مشاهده با اطلاعات نمایشی" (preview w/ Demo data), "مشاهده با اطلاعات فروشگاه من" (preview w/ merchant's own data), and "استفاده از این قالب" (Apply).

**Missing link**: none for the "browse all 50" journey itself. Two smaller gaps sit downstream of browsing (not blocking it): (1) the preview thumbnail opens in a new browser tab rather than an in-page lightbox; (2) the pre-apply preview page has no in-page Desktop/Tablet/Mobile switcher (see Journey E).

---

## Journey B — An existing merchant chooses Template X and applies it to Draft

**CURRENTLY POSSIBLE: YES**

Trace:
`UI (Gallery "استفاده از این قالب" form)` → `POST storefront-builder/apply-preset/` → `views.py:2392 storefront_apply_layout_preset` (confirm-overwrite gate if the Draft already has content) → `preset_service.py:921 apply_preset_with_checkpoint` (checkpoints the pre-apply Draft into version history first) → `preset_service.py:436 apply_preset(draft, preset)` (writes Sections/Containers/appearance_config/header_config/footer_config/template_provenance/template_baseline_snapshot) → `@_record_edit_history` wraps the whole view, adding an Undo-able entry → merchant is routed to Preview.

The equivalent in-editor path (`r4_mutation_service.py::_apply_appearance_template`, mutation type `appearance.template.apply`) reaches the same `apply_preset()` and additionally goes through the R4 stale-write (`base_revision`) check.

**Merchant product/catalog data preserved — CONFIRMED.** `preset_service.py` contains zero references to Product/Category/Brand/Collection models; every Ready-Template section expresses its content as `mode="auto"` resource-source rules resolved live against whichever Store the Draft belongs to.

---

## Journey C — Merchant applies Template X, then changes ONLY Header

**Expected invariant**: Header changes; Hero/Card/Footer/Palette/etc. remain untouched.

**CURRENTLY POSSIBLE: YES**

Trace: merchant changes the Header selector in the editor's Global Design panel (`#r4GlobalHeaderVariant`) → `header.update` mutation → `r4_mutation_service.py::_apply_header_update` → validates via `layout_service.validate_header_config`, persists only `StorefrontLayoutVersion.header_config`, then syncs the typed manifest via `appearance_authority_service.apply_header_variant`. The generic isolation path `_apply_appearance_component_update` additionally guards family-key mismatches and preserves sibling selections (`preserve_live_legacy_siblings=True`) for any component-family mutation. `AppearanceMutationIsolationTests` covers this invariant directly at the test level.

**No gap found** for Header specifically — Header is a COMPLETE vertical slice (see current_state_inventory.md §5). Note: the equivalent "change only X" journey is **not currently possible from a persistent, always-on UI control** for Hero, Product View, Product Card (family-level), Badge, or Mobile Bottom Nav in the canonical R4 editor — those families are PARTIAL (Design-Lab/preset-only, or in Bottom Nav's case, legacy-editor-only). The isolation *mechanism* itself is sound and shared for all families; what's missing for those families is a merchant-facing entry point to trigger it outside Design Lab.

---

## Journey D — Merchant experiments with multiple Header/Hero/Card/Palette combinations without filling Draft history, then applies once

**This is the Design Lab transient-state journey.**

**CURRENTLY POSSIBLE: YES**

Trace: merchant opens the Design Lab panel in the R4 editor → clicks "Random Mix" or per-family "randomize only this," optionally locking families they want to keep fixed → `storefront_r4_design_lab` (read-only endpoint, never writes: no `draft.save()`, no history entry, no revision change) returns a signed, opaque `candidate_token` representing an in-memory `DesignLabCandidate` → the in-editor preview iframe loads `?design_lab=<token>` against the **same** `storefront_preview` route used for normal Draft preview → merchant can Compare the candidate against the committed Draft, or Return-to-original-DNA, any number of times with **zero Draft history entries created**. Only when the merchant clicks Apply does `design_lab.apply_candidate` go through the normal `apply_mutation` boundary — re-validated for staleness, producing exactly **one** atomic Draft mutation + one history entry, regardless of how many experiments preceded it.

**No gap found.** This matches the spec's §13 mandate ("a hundred Lab experiments should not become a hundred Draft history mutations") exactly.

---

## Journey E — Merchant previews the result in Desktop/Mobile, then Publishes

**CURRENTLY POSSIBLE: YES, with one caveat**

Trace:
`Draft` → in-editor Preview iframe with a real Desktop/Tablet/Mobile device switcher (UI-only, "never persisted to Store/Draft/database") → merchant clicks Publish → `POST storefront-builder/r4/publish/` → `r4_views.py:1298 storefront_r4_publish` → `r4_mutation_service.py:1281 publish_draft` (locks + revision-checks) → `layout_service.py:852 publish()` — atomic pointer-swap: `draft.status=PUBLISHED`, archive previous published version, `layout.published_version=draft`, `layout.draft_version=None` → `Published` → public storefront renders through `build_universal_storefront_context()`, the same shared renderer Preview used, so what the merchant saw in Desktop/Mobile preview is what goes live.

**Caveat (not a blocker, but worth naming for W5 IA work)**: the Desktop/Tablet/Mobile device switcher exists in the **in-editor Draft preview**, which is what a merchant uses after they've started building/applying a template. It does **not** exist on the **pre-apply Ready-Template Gallery preview page** (`ready_template_live_preview.html`) — so a merchant comparing templates before choosing one cannot yet device-toggle that specific preview; they can only device-toggle after they've applied a template and are looking at their own Draft. This is the same gap noted in Journey A.

---

## Cross-journey summary

| Journey | Status | Blocking gap |
|---|---|---|
| A — Browse all 50 | YES | none (minor: no lightbox, no device-toggle on pre-apply preview) |
| B — Apply Template X | YES | none |
| C — Apply then change only Header | YES | none (Header specifically is COMPLETE; Hero/Product View/Card/Badge are Design-Lab-only by binding product decision, not a gap — see the main plan §7) |
| D — Design Lab experimentation | YES | none |
| E — Preview Desktop/Mobile then Publish | YES | device switcher not available on the pre-apply Gallery preview (same as A) |

---

## W5 Merchant Journey Certification Plan

**Binding requirement (Independent Architect, W5 repair round)**: the W4C harness certifies **storefront rendering** (the 704-cell Ready-Template matrix). It does not exercise the merchant's actual **Builder UX** click-path. W5's final certification (workstream W5E) must be merchant-UX-aware and exercise real browser journeys, reusing the existing R4 QA/browser infrastructure (`tools/storefront_builder_r4_qa/run.mjs`, `qa_storefront_builder_r4.py`) — **no second certification harness**.

The following journeys (A-P) are the required scope for W5E, to be automated as an extension of the existing harness:

| # | Journey | Depends on |
|---|---|---|
| A | Merchant opens the canonical R4 Builder | existing R4 editor |
| B | Merchant browses all 50 Ready Templates | existing Gallery (already certified as merchant-facing in this discovery) |
| C | Merchant opens a Ready Template preview | existing `storefront_template_live_preview` |
| D | Merchant uses pre-apply device preview | **W5C** (new capability — this journey step doesn't exist to certify until W5C ships) |
| E | Merchant applies a Ready Template to Draft | existing `apply_preset()` path |
| F | Merchant changes Bottom Navigation independently | **W5B** (new capability) |
| G | Bottom Nav changes independently: `mobile_nav_variant` changes; unrelated `footer_config` fields remain unchanged; the typed `bottom_nav` manifest selection is synchronized; unrelated Store Appearance selections (Header, Palette, etc.) remain unchanged; the `footer_variant` selection is not accidentally changed when only Bottom Nav is changed | `footer.update` → `_apply_footer_update()` → `appearance_authority_service.apply_footer_variant()` (corrected owner — **not** `_apply_appearance_component_update`, which is the unrelated generic single-family mutation path used by Hero/Product View/Card/Badge) |
| H | Undo restores the prior Bottom Nav variant | existing shared `_run_history_command`, newly exercised for this family |
| I | Redo restores the new Bottom Nav variant | same |
| J | Merchant runs a Design Lab experiment without creating Draft history spam | existing Design Lab (already certified as history-clean in this discovery) |
| K | Merchant applies one Design Lab candidate | existing `design_lab.apply_candidate` |
| L | Merchant previews Desktop/Mobile | existing device switcher |
| M | Merchant Publishes | existing `layout_service.publish()` |
| N | Public storefront reflects the Published state | existing `build_universal_storefront_context()` |
| O | A stale revision receives the expected 409 conflict behavior | existing `R4StaleRevision`/`_lock_active_draft`, newly exercised for the Bottom-Nav mutation specifically |
| P | Cross-Store/tenant attempts fail closed | existing `resolve_store_for_service`/tenant-scoped queries, newly exercised for the Bottom-Nav mutation specifically |

**Regression scope decision (not hard-coded)**: whether the full 704-cell matrix must be rerun at W5 closure depends on which actual rendering surfaces W5A-D touch. W5A (server-side eligibility guard) and W5B/C (mutation-contract + UI additions reusing existing renderers) are not expected to change any Ready-Template rendering path, so a full rerun is likely unnecessary — but this must be confirmed against the actual W5 diff at W5E's implementation time, not assumed here. A targeted regression subset (the families/routes actually touched) is the expected default; escalate to a full rerun only if the diff review at that time shows a rendering-path change.
