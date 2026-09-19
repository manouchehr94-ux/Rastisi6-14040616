# P5-W5 Discovery — Product Gap Matrix

Status: DISCOVERY ONLY — no production code changed.
Source commit: `81abb435c6421197117f8f570993b64ca485d4af`.

Columns: Capability | Spec requirement | Current state | Merchant-facing? | Canonical owner | Source/evidence | Gap | Recommended W5 action | Risk

| Capability | Spec requirement | Current state | Merchant-facing? | Canonical owner | Source/evidence | Gap | Recommended W5 action | Risk |
|---|---|---|---|---|---|---|---|---|
| 50-template browser | §10, §20 | IMPLEMENTED | Yes | `layout_preset_registry.list_ready_templates()` | `views.py:2194`, `template_gallery.html` | None | None needed | — |
| Show all 50 | §10 | IMPLEMENTED | Yes | same | Gallery has no pagination/cap | None | None needed | — |
| Template filtering/recommendations | §10, §11 | NOT FOUND as a gating mechanism (industry does not hide templates) | N/A | — | grep found no restrict logic | None (compliant — spec forbids hiding) | Confirm no future regression adds hiding | Low |
| Static preview display | §13 (W4C) | IMPLEMENTED | Yes | `template_preview_service.py` | 50 `.webp` files on disk | None | None needed | — |
| Large Template preview | — | PARTIAL | Yes (degraded) | — | thumbnail `<a target="_blank">` opens raw image in new tab, no in-page lightbox | Small UX gap | W5B: add in-page lightbox/modal | Low |
| Desktop preview (pre-apply) | §12 | PARTIAL | Yes (only post-apply) | in-editor device switcher | `r4/editor.html:36-46` | Device switcher absent from `ready_template_live_preview.html` | W5B: extend device switcher to Gallery preview | Low |
| Tablet preview (pre-apply) | §12 | PARTIAL | same as above | same | same | same | same | Low |
| Mobile preview (pre-apply) | §12 | PARTIAL | same as above | same | same | same | same | Low |
| Template Apply to Draft | §14 | IMPLEMENTED | Yes | `preset_service.apply_preset()` | `views.py:2392`, `r4_mutation_service.py` | None | None needed | — |
| Template provenance | §9 | IMPLEMENTED | Backend only (not surfaced in UI) | `template_provenance`/`template_baseline_snapshot` fields | `models.py:286-316` | Provenance is recorded but not shown to the merchant anywhere in the UI | W5: consider a small "based on Template X" indicator in editor | Low |
| Return to original DNA | §12 | IMPLEMENTED (Design Lab only) | Yes | `design_lab_service.return_to_original_dna()` | `r4/editor.html:290` | None (works as designed within Design Lab) | None needed | — |
| Independent Header mutation | §8 | COMPLETE | Yes | `r4_mutation_service._apply_header_update` | `#r4GlobalHeaderVariant` | None | None needed | — |
| Mega Menu mutation | §8 | MISSING (registry has only 1 component; real UX is Header-variant-owned) | No | — | `inventory.py:26` (single `mega_menu.none.v1`) | No independently switchable mega-menu family exists | W5: clarify product intent — either retire the placeholder family or design real mega-menu variants | Medium (spec §6/§8 imply independent families should be independently switchable; this one structurally can't be) |
| Hero mutation | §8 | PARTIAL — registry+renderer complete, no persistent selector | Design-Lab/preset-only | `_apply_appearance_component_update` | `families.py:28-35` | No always-on Hero selector in Global Design panel | W5D: add a Hero selector to Normal Builder (see IA proposal) | Low-Medium |
| Layout mutation (typed family) | §8 | BACKEND ONLY — zero render consumers | No | `families.py:36-43` | grep: no `component("layout")` consumer found | Selecting a `layout.*` key has no visible effect; separate, real per-container layout system exists and covers the practical need | W5: decide whether to retire the unused typed `layout` family or wire it to a renderer; do NOT conflate with the working per-container layout system | Medium (dead registry entries a future dev could mistakenly build against) |
| Product View mutation | §8 | PARTIAL — same shape as Hero | Design-Lab/preset-only | same mechanism | `families.py:44-51` | No persistent selector | W5D: add selector if product decides it's Normal-Builder-worthy, else Advanced Lab only | Low-Medium |
| Product Card mutation | §8 | PARTIAL — family-level Design-Lab-only; adjacent style toggles ARE exposed | Partially (style toggles yes, full family no) | same mechanism | `families.py:52-59` | Merchant can be confused: style toggles (shadow/hover/crossfade/zoom) look complete but the full 19-variant card family isn't independently selectable outside Lab | W5: decide Normal Builder vs Advanced Lab placement, see §15 boundary proposal | Low |
| Badge mutation | §8 | PARTIAL — thin registry (2 options), Design-Lab-only | Design-Lab-only | same mechanism | `families.py:60-68` | No standalone control | W5: likely Advanced Lab only (thin registry doesn't justify Normal Builder real estate) | Low |
| Motion mutation | §8 | COMPLETE | Yes | `appearance.update` patch key `motion` | `#r4GlobalMotion` | None | None needed | — |
| Footer mutation | §8 | COMPLETE | Yes | `r4_mutation_service._apply_footer_update` | `#r4GlobalFooterVariant` | None | None needed | — |
| Bottom Nav mutation | §8 | PARTIAL — real gap: R4 mutation contract itself rejects the field | Legacy-editor-only, not R4 | `_apply_footer_update`'s allowed-patch-keys list excludes `mobile_nav_variant` | `r4_mutation_service.py:1009-1011` vs `footer_panel.html:29-32` (legacy) | Most merchants (on the R4-default editor) cannot change Bottom Nav directly at all — only via Design Lab or the legacy editor | **W5 priority fix**: add `mobile_nav_variant` to the R4 `footer.update` allowed keys + a selector in `r4/editor.html`'s footer group | **Medium-High** — a real, closable gap affecting a mobile-first storefront concern |
| Palette | §8 | COMPLETE | Yes | `appearance.update` patch key `palette_slug` | `#r4GlobalPalette` | None | None needed | — |
| Typography | §8 | COMPLETE | Yes | `font`/`type_scale` patch keys | `#r4GlobalFont`/`#r4GlobalTypeScale` | None | None needed | — |
| Density | §8 | COMPLETE | Yes | `density` patch key | `#r4GlobalDensity` | None | None needed | — |
| Radius | §8 | COMPLETE | Yes | `radius`/`button_radius` patch keys | `#r4GlobalRadius`/`#r4GlobalButtonRadius` | None | None needed | — |
| Content Width | §8 | COMPLETE (documented homepage-only scope) | Yes | `content_width` patch key | `#r4GlobalContentWidth` | None (scope limit is intentional) | None needed | — |
| Theme | §12(adjacent) W2 | COMPLETE — most thoroughly tested family | Yes | `theme.apply`/`theme.clear` mutations | `#r4ThemeOccasion`/`#r4ThemeIntensity` | None | None needed | — |
| Undo | R4 spec §Undo/Redo | YES | Yes | `edit_history_service.undo()` via shared `_run_history_command` | — | None | None needed | — |
| Redo | R4 spec §Undo/Redo | YES | Yes | `edit_history_service.redo()` | — | None | None needed | — |
| Publish | §14 | YES | Yes | `layout_service.publish()` | `r4_views.py:1298` | None | None needed | — |
| Design Lab | §12 | IMPLEMENTED | Yes | `design_lab_service.py` | `r4/editor.html:265-303` | None | None needed | — |
| Transient Lab state | §13 | YES | Yes | `DesignLabCandidate` (in-memory, signed token) | — | None | None needed | — |
| Random Mix | §12 | YES | Yes | `generate_candidate(randomize_families=...)` | scoped to 7 families | None (scope is intentional) | None needed | — |
| Locks | §12 | YES | Yes | `locked_families` (server-validated, transient) | — | None | None needed | — |
| Compare | §12 | YES | Yes | `compare_with_base()` | — | None | None needed | — |
| Apply Lab state | §14 | YES | Yes | `design_lab.apply_candidate` mutation | re-validated twice (TOCTOU-safe) | None | None needed | — |
| Tenant isolation | §26 | YES | — | `apps/stores/resolution.py` | single documented authority | None found | Re-verify under any W5 changes | Low |
| Stale-write protection | R4 §Stale writes | YES for R4 path; **absent for legacy R3 form POSTs** | — | `_lock_active_draft` / `edit_revision` | `r4_mutation_service.py:1137` | Legacy write endpoints remain POST-reachable without a revision check regardless of the `r4_editor_enabled` flag | W5: decide whether to close direct POST access to legacy write endpoints when R4 is active for a Store | Medium |
| Catalog preservation | §9, §15 | CONFIRMED | — | `preset_service.py` (no catalog-model refs) | — | None | None needed | — |
| Accessibility | §24 | Certified 0 FAIL at W4C (1800 checks) for the 704-cell matrix | — | W4C harness | `w4c_merge_checkpoint.md` | Certification covers Ready-Template rendering, not the Builder/Design-Lab admin UI itself | W5F: extend a11y QA scope to the Builder/Design-Lab admin surfaces if in scope | Low-Medium |
| Mobile Builder UX | R4 spec (no separate mobile builder) | Single responsive Builder shell, confirmed | Yes | `r4/editor.html` | — | None (compliant — no second mobile-only builder found) | None needed | — |

---

## Two structural duplication findings that affect multiple gap-matrix rows

See `authority_map.md` for full detail:

1. **R3/R4 dual mutation surface** — explains the "stale-write protection: absent for legacy" row above and the Bottom-Nav gap (legacy editor is currently the *only* full-featured surface for that one family).
2. **Two "Template" registries** (10-item style `appearance_registry` vs the 50-item Ready Template registry) — a naming collision that should be resolved before W5 exposes either concept more prominently in a new IA.
