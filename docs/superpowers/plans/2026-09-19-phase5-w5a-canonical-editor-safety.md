# P5-W5A — Canonical Editor Safety / Architecture Closure — Implementation Plan

Status: IMPLEMENTATION PLAN (pre-code). Approved Master Plan base: `e88ebac0dc333251e7be0d98f5c0d9fb6cad4efe` (`docs(phase5): finalize W5 discovery master plan`).
Feature branch: `feature/phase5-w5a-canonical-editor-safety`.

This plan maps the binding Class A/B/C classification from the approved master plan (`docs/superpowers/plans/2026-09-19-phase5-w5-merchant-design-experience-discovery.md` §5/§8, `authority_map.md` §2/§2a/§2c) to an exact, source-verified route inventory, before any production code changes.

---

## 1. Exact route inventory (source-verified against `apps/dashboard/urls.py` + `apps/storefront_builder/views.py`)

All routes below are registered in `apps/dashboard/urls.py` under `storefront-builder/...` (mounted at `admin-portal/`). "Owner" = the view function in `apps/storefront_builder/views.py` unless noted.

### Class A — R3-editor-only redundant mutation routes (fail closed when `r4_editor_enabled=True`)

| URL name | View | HTTP | Current mutation owner | R4 equivalent | W5A disposition |
|---|---|---|---|---|---|
| `storefront-builder-container-add` | `storefront_container_add` | POST | `container_service` (direct) | `section.add`-family R4 mutations / container mutations via `r4_mutation_service` | Guarded |
| `storefront-builder-container-settings` | `storefront_container_settings` | GET+POST | `container_service` (direct) | `container.update_settings` | Guarded |
| `storefront-builder-container-layout` | `storefront_container_layout` | POST | `container_service` (direct) | `container.change_layout`-family | Guarded |
| `storefront-builder-container-move` | `storefront_container_move` | POST | `container_service` (direct) | R4 container move mutation | Guarded |
| `storefront-builder-container-remove` | `storefront_container_remove` | POST | `container_service` (direct) | R4 container remove mutation | Guarded |
| `storefront-builder-cell-add-section` | `storefront_cell_add_section` | POST | `section_structure_service` (direct) | `section.add` | Guarded |
| `storefront-builder-cell-clear` | `storefront_cell_clear` | POST | `section_structure_service` (direct) | R4 equivalent | Guarded |
| `storefront-builder-section-add` | `storefront_section_add` | POST | `section_structure_service` (direct) | `section.add` | Guarded |
| `storefront-builder-section-reorder` | `storefront_section_reorder` | POST | `section_structure_service` (direct) | R4 equivalent | Guarded |
| `storefront-builder-block-move` | `storefront_block_move` | POST | `section_data_service` (direct) | R4 equivalent | Guarded |
| `storefront-builder-block-remove` | `storefront_block_remove` | POST | `section_data_service` (direct) | R4 equivalent | Guarded |
| `storefront-builder-section-settings` | `storefront_section_settings` | GET+POST | `section_data_service`/`clean_section_schema_patch` (direct) | `section.update_settings` | Guarded |
| `storefront-builder-section-row-layout` | `storefront_section_row_layout` | POST | `section_data_service` (direct) | R4 equivalent | Guarded |
| `storefront-builder-section-remove` | `storefront_section_remove` | POST | `section_structure_service` (direct) | R4 equivalent | Guarded |
| `storefront-builder-section-toggle` | `storefront_section_toggle` | POST | direct | `section.toggle_active` | Guarded |
| `storefront-builder-section-lock` | `storefront_section_lock_toggle` | POST | direct | `section.toggle_locked` | Guarded |
| `storefront-builder-section-duplicate` | `storefront_section_duplicate` | POST | `section_structure_service` (direct) | R4 equivalent | Guarded |
| `storefront-builder-section-move` | `storefront_section_move` | POST | `section_structure_service` (direct) | R4 equivalent | Guarded |
| `storefront-builder-appearance` | `storefront_appearance_editor` | GET+POST | `appearance_authority_service` (direct) | `appearance.update` | Guarded |
| `storefront-builder-section-reset` | `storefront_section_reset` | POST | `preset_service` (direct) | R4 granular reset | Guarded |
| `storefront-builder-section-field-reset` | `storefront_section_field_reset` | POST | `preset_service` (direct) | R4 granular reset | Guarded |
| `storefront-builder-appearance-field-reset` | `storefront_appearance_field_reset` | POST | `preset_service` (direct) | R4 granular reset | Guarded |
| `storefront-builder-header-reset` | `storefront_header_reset` | POST | `preset_service` (direct) | `header.reset_to_baseline` | Guarded |
| `storefront-builder-footer-reset` | `storefront_footer_reset` | POST | `preset_service` (direct) | `footer.reset_to_baseline` | Guarded |
| `storefront-builder-page-reset` | `storefront_page_reset` | POST | `preset_service.reset_page_with_checkpoint` | `storefront-builder/r4/reset-page/` | Guarded |
| `storefront-builder-reset-to-baseline` | `storefront_reset_to_baseline` | POST | `preset_service.reset_storefront_with_checkpoint` | `storefront-builder/r4/reset-storefront/` | Guarded |
| `storefront-builder-header` | `storefront_header_editor` | GET+POST | `appearance_authority_service.apply_header_variant` (direct) | `header.update` | Guarded |
| `storefront-builder-footer` | `storefront_footer_editor` | GET+POST | `appearance_authority_service.apply_footer_variant` (direct) | `footer.update` | Guarded |
| `storefront-builder-undo` | `storefront_undo` | POST | `r4_mutation_service.apply_history_command_current` (already shared) | `storefront-builder/r4/history/` | Guarded (redundant entry point; explicitly named as a Class A example in the master plan) |
| `storefront-builder-redo` | `storefront_redo` | POST | same | same | Guarded |
| `storefront-builder-publish` | `storefront_publish` | POST | `layout_service.publish` (already shared) | `storefront-builder/r4/publish/` | Guarded |

**Not guarded, despite being POST/mutating** (explicit, source-justified exclusions, matching the binding master plan):

| URL name | View | Reason excluded from the Class A guard |
|---|---|---|
| `storefront-builder-section-collapse` | `storefront_section_collapse_toggle` | Confirmed by source read: writes only `collapsed_in_editor` — a purely cosmetic, editor-local UI-state field with zero effect on Preview/Public render output. Master plan §5 legacy-route table explicitly classifies this as "READ/UI-ONLY... CANONICAL KEEP, not part of the write-surface risk." Binding — not re-litigated here. |

### Class B — shared canonical capabilities (must remain unblocked, verified NOT gated)

| URL name | View | Why Class B |
|---|---|---|
| `storefront-builder-templates` | `storefront_template_gallery` | Ready Template Gallery — real merchant-facing browsing surface for all 50 templates, shared by both editors |
| `storefront-builder-apply-preset` | `storefront_apply_layout_preset` | Ready Template Apply — converges on `preset_service.apply_preset()`, the same canonical authority `appearance.template.apply` (R4) uses. Explicitly "not a retirement candidate" per Phase-4 audit and the approved master plan |
| `storefront-builder-template-live-preview` | `storefront_template_live_preview` | Non-destructive Ready Template preview (Demo/merchant data) — zero DB writes |
| `storefront-builder-preview` | `storefront_preview` | Shared Draft preview route — used directly by the R4 editor's own iframe and by Design Lab (`?design_lab=` / `?preview_template=`) |
| `storefront-builder-section-list` | `storefront_section_list_partial` | Read-only partial (no `@require_POST`, no mutation) |
| `storefront-builder-container-state` | `storefront_container_state_partial` | Read-only partial |
| `storefront-builder-section-product-search` | `storefront_section_product_search` | Read-only (product-search autocomplete for the legacy edit forms) |
| `storefront-builder-edit-history-state` | `storefront_edit_history_state` | Read-only (legacy Undo/Redo button state) |
| Section-scoped media CRUD (`storefront-builder-section-media-*`) | `apps/storefront_builder/media_views.py` | A separate module, already the single shared authority for both editor shells (Phase-4 audit finding, re-confirmed) |
| `storefront-builder-editor` | `storefront_editor` (the R3 page shell itself) | Already template-conditional (renders full legacy body only for `r4_editor_enabled=False`, a minimal compatibility surface otherwise) — pre-existing behavior, not part of this workstream's route guard |

**History browser** — its own bucket, not Class A or Class B, matching the master plan's explicit separate treatment:

| URL name | View | Classification |
|---|---|---|
| `storefront-builder-history` | `storefront_history` | READ ONLY — `@staff_required`/`@permission_required` only, no `@require_POST`; calls only `layout_service.list_versions()`/`get_or_create_layout()` and renders a list. Confirmed zero Draft mutation. Remains unconditionally reachable under both `r4_editor_enabled=True` and `False`. |

### Class C — legacy-only mutating capabilities requiring R4-safe convergence

| URL name | View | HTTP | Current mutation owner | R4 equivalent today | W5A disposition |
|---|---|---|---|---|---|
| `storefront-builder-restore` | `storefront_restore` | POST | `layout_service.restore_version()` (direct, no stale-write check) | None | Legacy endpoint gated closed when `r4_editor_enabled=True` (same guard mechanism as Class A); **new** R4-safe endpoint added, delegating to the same unmodified `layout_service.restore_version()` |
| `storefront-builder-apply-industry-layout` | `storefront_apply_industry_layout` | POST | `layout_service.apply_industry_layout()` (direct, no stale-write check) | None | Same pattern: legacy gated closed under R4; new R4-safe endpoint delegates to the same unmodified `layout_service.apply_industry_layout()` |

**Confirmed by direct source read** (see `authority_map.md` §2a): both `restore_version()` and `apply_industry_layout()` delete the current Draft (if any) and create a new one, reassigning `layout.draft_version` — identical Draft-identity-replacement shape, neither takes a `base_revision`, neither is safe to leave as an unconditional exception once R4 is active.

---

## 2. New R4-safe Class C endpoints — design

Two new endpoints, mirroring the exact existing contract shape of `storefront_r4_reset_storefront`/`storefront_r4_switch_template`:

```
POST storefront-builder/r4/restore/<int:pk>/
POST storefront-builder/r4/apply-industry-layout/
```

Both:
- `@require_POST @staff_required @permission_required(STOREFRONT_LAYOUT_MANAGE)`.
- `store = resolve_store_for_service(request)`; `layout = layout_service.get_or_create_layout(store)`; `if not layout.r4_editor_enabled: raise Http404` (exact existing R4 convention).
- Parse JSON body; read `base_revision` — accepted values: a non-negative int (client expects an active Draft with exactly that `edit_revision`), or JSON `null` (client expects **no** active Draft). Any other shape → `400 {"code": "invalid_base_revision"}`.
- Call a new `r4_mutation_service` orchestration function (see §3) inside one `@transaction.atomic` block.
- `R4StaleRevision` → `409 {"ok": False, "code": "stale_revision", "current_revision": exc.current_revision}` (matches existing convention; `current_revision` may be `null` when the conflict is "a Draft now exists where none was expected" is inverted — see §3 for the exact semantics).
- `R4MutationError` (any other) → `400 {"ok": False, "code": str(exc)}`.
- Success → `200 {"ok": True}` (client reloads, same as Reset Storefront/Switch Template — this is a whole-Draft-identity-replacing operation, not an in-place edit).

## 3. New `r4_mutation_service` orchestration — concurrency contract

See `docs/qa_evidence/storefront_design_engine/phase5/w5a_canonical_editor_safety/concurrency_contract.md` for the full wire contract. Summary:

- A new locking helper, `_lock_layout_for_identity_replacement(*, store, expected_base_revision)`, distinct from `_lock_active_draft` (which unconditionally requires an existing Draft and is therefore unsuitable for Restore/Industry-Layout-Apply, both of which are legitimately reachable with no active Draft).
- `expected_base_revision is None` → client expects no active Draft. Under `select_for_update()` on `StorefrontLayout`: if a Draft now exists, raise `R4StaleRevision(current_revision_of_that_draft)`; otherwise proceed.
- `expected_base_revision` is a non-negative int → client expects an active Draft with exactly that `edit_revision`. Under the same lock: if no Draft exists, or its `edit_revision` doesn't match, raise `R4StaleRevision(...)`; otherwise proceed.
- The row lock is held for the entire `@transaction.atomic` block, including the call into the existing `layout_service.restore_version()`/`apply_industry_layout()` — no release-then-call gap (the exact TOCTOU the master plan forbids).
- Two new thin wrapper functions, `restore_version_safe(*, store, actor, base_revision, version_id)` and `apply_industry_layout_safe(*, store, actor, base_revision, force=False)`, each: lock → call the existing service function unmodified → return its result. **No restore or industry-layout business logic is duplicated** — both wrappers are pure orchestration.

## 4. Response/eligibility policy consistency

Matches existing repository convention exactly: `if not layout.r4_editor_enabled: raise Http404` is already used by `storefront_r4_reset_storefront`, `storefront_r4_switch_template`, `storefront_r4_design_lab`, etc. The new **Class A shared guard** (applied to the explicit Class A list in §1, plus the two legacy Class C endpoints) uses the same status code for the same reason (wrong editor mode / unavailable surface), applied in the inverse direction (`if layout.r4_editor_enabled: raise Http404` for legacy views). One shared decorator, `_require_legacy_editor_active`, defined once in `apps/storefront_builder/views.py` and applied to the explicit Class A route list — never a module-wide check.

## 5. Style Pack terminology

Source-search scope: `apps/storefront_builder/templates/dashboard/storefront_builder/r4/editor.html` (the `templates` choice list fed from `appearance_registry.list_templates()`) and any other merchant-facing label referring to the 10-item `appearance_registry.TEMPLATE_REGISTRY` concept. The Ready Template Gallery's own labels ("قالب‌های آماده", "استفاده از این قالب", etc.) are already correctly "Ready Template" and must not change. No change to `template_slug`, `TEMPLATE_REGISTRY`, `TemplateDefinition`, or any persisted field — labels only.

## 6. Reserved family documentation

Add a non-behavioral code comment to the `layout` and `mega_menu` entries in `apps/storefront_builder/storefront_appearance/families.py` recording their reserved/inert and reserved/compatibility disposition (per the approved master plan), so a future engineer does not mistake either for an active, independently-switchable merchant control. No renderer, no selector, no new registry variant.

## 7. Forbidden scope (explicit, per master plan §19)

Not touched: Ready Template recipes/registry membership, public renderer, section renderer, Theme architecture, Cart, Product Card renderer, Bottom Navigation implementation (W5B), Design Lab mutation semantics, Store Appearance persisted contract, database schema, migrations.

## 8. Files expected to change

- `apps/storefront_builder/views.py` — add `_require_legacy_editor_active` decorator; apply to the explicit Class A list (§1) and to `storefront_restore`/`storefront_apply_industry_layout`.
- `apps/storefront_builder/services/r4_mutation_service.py` — add `_lock_layout_for_identity_replacement`, `restore_version_safe`, `apply_industry_layout_safe`.
- `apps/storefront_builder/r4_views.py` — add `storefront_r4_restore`, `storefront_r4_apply_industry_layout` thin views.
- `apps/dashboard/urls.py` — register the two new R4 routes.
- `apps/storefront_builder/templates/dashboard/storefront_builder/history.html` (or equivalent) — Restore button's form action conditional on `layout.r4_editor_enabled`, reusing the existing template, no new screen.
- Industry-layout-apply UI (embedded in `editor.html`'s minimal R4-active compatibility surface, per the Phase-4 audit) — same conditional-action treatment, no new screen.
- `apps/storefront_builder/storefront_appearance/families.py` — non-behavioral reserved-disposition comments for `layout`/`mega_menu`.
- Merchant-facing Style Pack label text.
- New test module: `apps/storefront_builder/tests/test_phase5_w5a_canonical_editor_safety.py`.
- Evidence docs under `docs/qa_evidence/storefront_design_engine/phase5/w5a_canonical_editor_safety/`.

Zero migrations expected — no model/field changes.
