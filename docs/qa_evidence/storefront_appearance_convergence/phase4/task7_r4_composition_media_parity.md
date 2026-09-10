# Phase 4 — Task 7: R4 Composition/Media/Recovery Parity

Goal: make R4 the functionally complete merchant editor for the approved
composition/media/recovery capabilities before the legacy (R3) editor is
retired. Architecture constraint (unchanged from Task 6): R4 Editor ->
canonical mutation/composition/media services -> Draft lifecycle/history ->
shared renderer. No second persistence authority, no second renderer, no
second lifecycle, no second media ownership model.

## B1 — Gap audit (done BEFORE any production code, per instruction)

Method: read the actual current implementation (`r4_mutation_service.py`,
`section_structure_service.py`, `r4_views.py`, `r4_editor.js`,
`responsive_section_wrapper.html`, `container_service.py`, `preset_service.py`,
`views.py` legacy endpoints, `media_views.py`, R4 Inspector templates) rather
than assuming a capability is missing because the R4 UI does not obviously
expose it.

| # | Capability | Classification | Evidence |
|---|---|---|---|
| 1 | Container | PARTIAL | `StorefrontContainer`/`container_service` are already load-bearing for R4: `section_structure_service.add_section/remove_section/duplicate_section/move_section` all call `container_service.ensure_page_containers`/`get_cell_blocks`/`move_block` (`section_structure_service.py:106,137,160,231`). But R4 never exposes container-level merchant controls (layout switch, container settings) — no mutation type touches `container_service.change_container_layout` or `effective_container_settings`. |
| 2 | Cell | PARTIAL | Same as Container — Cell is read/written internally by `section_structure_service` for every add/remove/duplicate/move, but has no direct merchant-facing R4 control. |
| 3 | Row | NOT APPLICABLE (compat-only) | `row_service.validate_page_row_layout` is respected defensively by `move_section` (`section_structure_service.py:271-278`) so a move can never silently break a legacy row. Row (`row_key`/`row_span`) is a legacy compatibility concept superseded by Container/Cell — Task 7 does not need to add new merchant-facing Row UI, only continue not breaking it (already true). |
| 4 | multi-column composition | MISSING | `add_section` always calls `container_service.create_empty_container(page, "single")` (`section_structure_service.py:112`) — R4 has no mutation type equivalent to legacy `storefront_apply_layout_preset`/`change_container_layout` (`views.py:2182`, `container_service.change_container_layout`). A merchant cannot create or change a 2-up/3-up row via R4 today. |
| 5 | arbitrary valid section placement | PARTIAL | `move_section` only swaps a section with the ADJACENT slot in the container/cell projection (`section_structure_service.py:222-291`) — a real reorder, but not "place section X into cell Y at index Z" for an arbitrary non-adjacent target. |
| 6 | add section | ALREADY COMPLETE | `r4_mutation_service` type `section.add` -> `section_structure_service.add_section`; wired in the Structure panel (`r4_editor.js:563-578`) and the Preview toolbar bridge. |
| 7 | remove section | ALREADY COMPLETE | `section.remove` -> `remove_section`; wired both in the Structure panel (`r4_editor.js:552-561`) and the Preview toolbar bridge (`r4_editor.js:939-953`). |
| 8 | duplicate section | ALREADY COMPLETE | `section.duplicate` -> `duplicate_section`; wired in both surfaces (`r4_editor.js:542-550,937-938`). |
| 9 | move/reorder section | ALREADY COMPLETE | `section.move` -> `move_section`; wired in both surfaces (`r4_editor.js:530-540,947-950`). |
| 10 | section enable/disable | LEGACY-ONLY (MISSING in R4) | Model field `StorefrontSection.is_active` + legacy view `storefront_section_toggle` (`views.py:1683-1688`, `@_record_edit_history`) already exist. The Preview toolbar button (`data-cmd="toggle"`, `responsive_section_wrapper.html:71-72`) already renders and `preview.html`'s `interceptBuilderEditClick` already posts `sfb:sectionCommand`/command `toggle` to the parent — but `r4_editor.js`'s message listener explicitly drops it: *"toggle, lock, cellCommand and containerCommand are deliberately left unhandled"* (`r4_editor.js:918-922`). No `section.toggle_active` (or equivalent) mutation type exists in `r4_mutation_service.py`. |
| 11 | collapse | NOT APPLICABLE (superseded UX paradigm) | The field is real — `StorefrontSection.collapsed_in_editor` + legacy view `storefront_section_collapse_toggle` (`views.py:1693-1704`) exist, and its own docstring says exactly what it is for: *"جمع‌کردن/بازکردن کارت یک بخش داخل ادیتور — فقط UI، مستقل از is_active"* (collapse/expand one section's inline settings CARD inside the legacy list-based editor — cosmetic only, independent of `is_active`). R3's editor renders every section as an always-present, independently-expandable inline settings card in one long scrolling list; `collapsed_in_editor` is which of those cards is currently expanded. R4 does not have that surface at all: R4 shows at most one section's settings at a time, in the single shared Inspector panel opened via `R4.openSection()`, and the Structure panel's own rows never carry inline settings to begin with (`editor.html:48-58` — label + icon buttons only). There is no R4 surface this flag could control, so there is nothing to wire — not a gap, an obsoleted concept. |
| 12 | lock | LEGACY-ONLY (MISSING in R4) | Same shape as #10: model field `is_locked` (`models.py:703-711`, spec §37), legacy view (`views.py:~1710-1717`), Preview toolbar button (`data-cmd="lock"`), `preview.html` posts it — but `r4_editor.js` deliberately drops `lock` too (same comment, `r4_editor.js:918-922`). No mutation type. |
| 13 | discard Draft changes | LEGACY-ONLY (MISSING in R4) | `layout_service.discard_draft(store)` is a real, already-used one-line service call, wired only to the legacy view `storefront_discard` (`views.py:2417-2424`). No R4 endpoint/mutation type and no button in `editor.html`'s topbar. |
| 14 | restore/recovery | ALREADY COMPLETE (undo/redo granularity) | `storefront_r4_history_command` (`r4_views.py:565-610`) -> `r4_mutation_service.apply_history_command`, base-revision-checked, wired to the Undo/Redo buttons already rendered in `editor.html:33-40`. (Granular reset-to-baseline, a *different* recovery granularity, is tracked separately as #16.) |
| 15 | history | ALREADY COMPLETE | `edit_history_service.history_state(draft)` feeds `history.can_undo`/`can_redo` into `editor.html` (`r4_views.py:316`); every mutation is recorded through the same service (module docstring, `r4_mutation_service.py:1-9`). |
| 16 | granular reset | LEGACY-ONLY (MISSING in R4) | Six distinct, already-hardened granularities exist only as legacy views, all POST-redirect, all using `preset_service`, several with checkpoint-before-destructive-reset semantics: `storefront_section_reset` (`views.py:2234`), `storefront_section_field_reset` (`views.py:2258`), `storefront_appearance_field_reset` (`views.py:2281`), `storefront_header_reset` (`views.py:2302`), `storefront_footer_reset` (`views.py:2322`), `storefront_page_reset` (`views.py:2340`), `storefront_reset_to_baseline` (`views.py:2370`). None have an R4 mutation-type equivalent. |
| 17 | section media CRUD | MISSING (from R4's reachable UI) | The generic media CRUD system (`media_views.py`, `_MEDIA_KINDS`, fixed for story_rail in Task 6) is real, shared, and already canonical — but a grep of every R4 template (`templates/dashboard/storefront_builder/r4/**`) for `media` returns zero matches. A merchant editing a `story_rail`/`hero_banner`/`image_slider`/`multi_banner` section in R4 has no link anywhere in the R4 Inspector to the shared media management screens; they would have to already know the legacy URL. |
| 18 | correct behavior on all approved page types | ALREADY COMPLETE | `editor.html` already renders a full page switcher (`#r4PageSwitcherSelect`, `editor.html:21-28`) over `StorefrontPage.PageType.choices`; `storefront_r4_editor` resolves `page_type` the same validated way the legacy editor does (`r4_views.py:254`, Task 3B); every `section_structure_service` mutation (add/remove/duplicate/move) is page-agnostic by construction — `remove_section`/`duplicate_section`/`move_section` infer their page from the resolved section, never assume Home (`section_structure_service.py:8-18`). |
| 19 | tenant isolation | ALREADY COMPLETE | `storefront_r4_mutation`/`storefront_r4_history_command`/`storefront_r4_publish` all resolve the store via `resolve_store_for_service(request)` (`r4_views.py:329,570,620`) before doing anything; every section lookup inside the mutation boundary goes through `_scoped_section(draft, section_id)`, filtered by `page__version=draft` — "a crafted section_id belonging to another Store... is indistinguishable from does not exist" (`section_structure_service.py:36-52`). |
| 20 | stale-write protection | ALREADY COMPLETE | `base_revision` is required and validated on every R4 write endpoint (mutate/history/publish); a mismatch raises `R4StaleRevision`, surfaced as HTTP 409 with `current_revision` (`r4_views.py:358-362,595-599,641-645`); already regression-tested by the existing browser harness (`scenario09`, "real-stale-conflict"). |

### Summary

- **Already complete, no work needed**: #6 add, #7 remove, #8 duplicate,
  #9 move/reorder, #14 restore (undo/redo), #15 history, #18 non-Home page
  parity, #19 tenant isolation, #20 stale-write protection. (9 of 20)
- **Not applicable / nothing to build**: #3 Row (compat-only, already
  respected defensively), #11 collapse (no persisted concept exists to wire).
  (2 of 20)
- **Real gaps requiring implementation** (9 of 20), grouped into the three
  batches below:
  - Composition (Batch 1): #1 Container (merchant-facing layout control),
    #2 Cell (same), #4 multi-column composition, #5 arbitrary placement,
    #10 enable/disable, #12 lock.
  - Recovery (Batch 2): #13 discard, #16 granular reset (all six
    granularities).
  - Media + cross-page (Batch 3): #17 section media CRUD reachability from
    R4. (#18/#19/#20 already certified above — Batch 3 only needs a
    regression sentinel, not new code.)

## B2 — Implementation strategy

Every new capability is wired as: a new allowlisted `r4_mutation_service`
mutation `type` (or, for discard, a small dedicated R4 endpoint mirroring
`storefront_r4_publish`'s shape) that calls the EXACT SAME canonical service
function the legacy view already calls (`container_service`, `preset_service`,
`layout_service.discard_draft`, the `is_active`/`is_locked` flip already used
by the legacy toggle/lock views) — never a new persistence path. R4-side UI
work is additive: new buttons/controls in the Structure panel, Inspector, and
topbar, plus finally routing the two already-emitted-but-dropped Preview
toolbar commands (`toggle`, `lock`) instead of leaving them unhandled.

See `execution_ledger.md` for the batch-by-batch implementation log.

## Batch 1 — Composition (done)

New R4 mutation types, all wired through `section_structure_service.py`
(never a new persistence path), all reusing the exact canonical service the
legacy view already used for the same flag/operation:

- `section.toggle_active` -> `StorefrontSection.is_active` flip (same field
  the legacy `storefront_section_toggle` view already flips).
- `section.toggle_locked` -> `is_locked` flip (same field the legacy
  `storefront_section_lock_toggle` view already flips).
- `container.change_layout` -> `container_service.change_container_layout`
  (the same content-preserving grow/shrink function the legacy layout-preset
  picker already calls).

UI: the Structure panel gained toggle/lock icons per section row and one
layout-preset `<select>` per Container (rendered once per distinct
`container_id` via `{% ifchanged %}`). The shared Preview toolbar's
`toggle`/`lock` buttons — which already existed and already posted
`sfb:sectionCommand` messages that Task 8 deliberately left unhandled — are
now routed to the same two mutation types, so a merchant using either
surface (Structure panel or Preview) gets the same real effect.

`section.move`'s existing container/cell-aware adjacent-swap and
`section.add`'s existing single-column-only placement are UNCHANGED — Batch
1 adds the ability to reshape an existing row into 2/3/4 columns, not a
new arbitrary drag-to-any-cell placement primitive (still adjacent-swap
only; a true "drop into any cell at any index" gesture remains a future
increment if the merchant workflow needs more than reshape+adjacent-move).

Targeted tests: `ToggleSectionActiveTests`, `ToggleSectionLockedTests`,
`ChangeContainerLayoutTests` (13 tests, `test_r4_vertical_slice.py`) — all
GREEN, plus the full `test_r4_vertical_slice.py` module re-run clean (one
pre-existing, unrelated failure confirmed via `git stash` to reproduce
identically without this batch's changes — see Batch 2 note below).

## Batch 2 — Recovery (done)

New R4 mutation types (in-place, no Draft-identity change — wired into the
normal `_dispatch_mutation` allowlist exactly like Batch 1's):

- `section.reset_to_baseline` -> `preset_service.reset_section_to_baseline`
- `section.reset_setting_to_baseline` -> `preset_service.reset_section_setting_to_baseline`
- `appearance.reset_setting_to_baseline` -> `preset_service.reset_appearance_setting_to_baseline`
- `header.reset_to_baseline` -> `preset_service.reset_header_to_baseline`
- `footer.reset_to_baseline` -> `preset_service.reset_footer_to_baseline`

New DEDICATED R4 endpoints (NOT mutation types — each replaces the Draft's
identity, exactly the same reason Publish is its own endpoint rather than a
mutation type): `storefront_r4_discard` / `storefront_r4_reset_page` /
`storefront_r4_reset_storefront`, each mirroring `storefront_r4_publish`'s
exact contract shape (`base_revision`-gated via the SAME `_lock_active_draft`
boundary, `R4StaleRevision` -> HTTP 409), delegating to
`layout_service.discard_draft` / `preset_service.reset_page_with_checkpoint`
/ `preset_service.reset_storefront_with_checkpoint` — never a second
implementation of checkpoint/baseline logic.

UI: a "Discard Draft" button in the topbar (same shape as Publish); a
"Reset this page to Template" button in the Structure panel (gated on
`page_has_baseline`, same condition the legacy editor's own equivalent
button already uses: `draft.template_baseline_snapshot.pages[page_type]`);
a "Reset entire storefront to Template" button in the Global Design panel
(gated on `storefront_has_baseline`); a "↺" reset icon per Structure-panel
section row (gated on `has_baseline` = `bool(section.template_slot_key)` —
a manually-added section has no baseline, exactly like the legacy editor's
own per-section reset control); one "↺" reset icon per appearance field and
one whole-group reset button each for header/footer inside the Global
Design panel.

Targeted tests: `BaselineResetMutationTests`, `BaselineResetWithoutTemplateTests`,
`DraftReplacingEndpointTests` (`test_r4_vertical_slice.py`) covering success,
tenant isolation, stale-revision, no-baseline rejection, and (for
discard/reset-page/reset-storefront) that the Published version is never
touched.

Note: while implementing this batch, the final Task-6 independent reviewer
(dispatched per A3) returned CRITICAL 1 / IMPORTANT 2 / MINOR 3 — all six
findings were fixed in the same working session (see
`task6_family_convergence.md`'s "Second independent review" section for the
full record) before Task-6 closure and before this batch's own full-suite
re-verification.
