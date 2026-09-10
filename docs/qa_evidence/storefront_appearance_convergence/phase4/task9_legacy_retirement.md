# Phase 4 — Task 9: Evidence-Based Legacy Retirement

Goal (per the Master Prompt): remove redundant legacy merchant-facing paths
now that R4 has proven parity, while preserving canonical services and
legitimate compatibility adapters. Deletion/convergence only — no
replacement systems built in this task.

Pre-deletion safety backup: `backup/rastisi6-phase4-pre-legacy-retirement-20260910`
== `34c1fba9fd1f3919a383c365cbb3e6893a310f3c` (Task-8 final), pushed and
verified before the first deletion commit.

## Headline finding: the retirement precondition is only partially met

`docs/.../phase4/legacy_disposition.md` (seeded at Task 0, from the Phase-4
architecture audit) itself states: *"every 'NEEDS EVIDENCE' row... cannot be
honestly evidenced until R4 has a real dashboard entry point"* and the
legacy editor shell is *"KEEP AS FINAL UNTIL R4 IS REACHABLE."* Re-verifying
against current code (commit `34c1fba9`, the Task-8 final checkpoint) at
Task-9 time:

1. **`StorefrontLayout.r4_editor_enabled` still defaults `False`**
   (`apps/storefront_builder/models.py:211`) and is a per-Store opt-in flag,
   never flipped globally. Every R4 write endpoint in `r4_views.py` gates on
   it (`if not layout.r4_editor_enabled: ...`).
2. **Dashboard nav still routes to the legacy editor, not R4.**
   `apps/dashboard/templates/dashboard/base_admin.html` links
   `dashboard:storefront-builder-editor` (legacy) from every appearance-related
   nav entry. The only path to R4 is an opt-in link embedded inside the
   legacy editor's own page (`editor.html`). There is no independent nav
   entry point to R4.
3. **R4's field-level capability is a narrow subset of the legacy
   Appearance/Header/Footer forms.** `r4_mutation_service.py`'s
   `appearance.update`/`header.update`/`footer.update` mutations accept only
   `{template_slug, palette_slug, font, type_scale, motion, button_style}` /
   `{header_variant}` / `{footer_variant}` respectively. The legacy forms
   additionally expose (with no R4 equivalent today): 8 appearance
   `color_overrides` keys, 8 `theme_overrides` keys, `radius`/`button_radius`/
   `density`/`image_fit`/`image_hover`/`card_image_crossfade`/
   `card_image_zoom`/`content_width`/`grid_density`/`card_shadow`/
   `card_hover`/`hero_style`; 6 header toggles
   (`show_search`/`show_account`/`show_cart`/`show_wishlist`/`sticky`/
   `announcement_enabled`) plus `announcement_text`/`announcement_links`/
   `announcement_show_phone`, `responsive` hide-on-tablet/mobile, and
   `extra_blocks`; 9 footer toggles
   (`show_about`/`show_contact`/`show_quick_links`/`show_categories`/
   `show_social`/`show_trust_badges`/`show_payment_logos`/`show_newsletter`/
   `show_copyright`) plus footer `responsive`/`extra_blocks`.
4. **Container/Cell composition still has a real, documented R4 gap**
   (arbitrary/non-adjacent placement; Container/Cell-level settings editing)
   even after Task 7's parity work for `container.change_layout`/
   `cell.add_section`.
5. **Ready Template gallery/apply is deliberately NOT one orchestration
   with R4**, per Task 8's own evidence doc (`task8_template_switch_lifecycle.md`
   item #2): legacy `apply_preset_with_checkpoint` and R4
   `appearance.template.apply` are two legitimate, different, already-tested
   capabilities, not a duplicate pair.

**Consequence:** the legacy editor shell remains the sole live, reachable
merchant path today, and everything still live-linked from it (structure
mutation, settings writer for non-schema section types, toggle/collapse/lock,
granular reset, discard-via-restore/history UI, media admin reachable from
it, Template gallery/apply, the industry-layout preset form) is
**NOT SAFE TO REMOVE YET** — deleting any of it now would remove real,
currently-exercised merchant capability, not dead legacy cruft. This directly
matches the disposition ledger's own pre-existing "KEEP AS FINAL UNTIL R4 IS
REACHABLE" ruling and the Master Prompt's explicit instruction that
"NOT SAFE TO REMOVE YET" is a legitimate, expected classification — not a
shortfall to force past.

Per the Master Prompt: *"Do NOT create replacement systems during Task 9"* —
so flipping `r4_editor_enabled`'s default or rewiring dashboard nav to make
R4 the live default (which would itself require first closing the field-parity
and composition gaps above, i.e. new capability work) is out of scope here.
That precondition work belongs to a future task, not Task 9.

## What Task 9 actually retired (two small, bounded, evidenced deletions)

### Batch 1 — `storefront_discard` (orphaned duplicate write authority)

- **Evidence:** `storefront-builder/discard/` → `storefront_discard`
  (`apps/storefront_builder/views.py`) had **zero live UI callers** — no
  template in `apps/storefront_builder/templates` links to it (the legacy
  editor's live discard-equivalent flow goes through
  `storefront_restore`/`storefront_history`). It was reachable only by direct
  POST and by two tests that called it directly.
- **R4 replacement, proven:** `storefront-builder/r4/discard/` →
  `r4_mutation_service` wraps the exact same `layout_service.discard_draft`,
  with its own tested atomicity/staleness-rejection coverage
  (`DraftReplacingEndpointTests` in `test_r4_vertical_slice.py`).
- **Action:** deleted the view, its URL route, and the two now-redundant
  direct tests (`test_discard_redirects`,
  `test_discard_is_atomic_and_removes_only_the_draft`) — coverage of the
  underlying atomicity contract is retained via R4's own tests.
- **Disposition:** RETIRED.
- Commit `5ed6486`.

### Batch 2 — `announcement_bar` preset-application gate (bug fix, not a section deletion)

- **Evidence:** `announcement_bar` is `hidden_from_library=True`
  (`section_registry.py`), superseded by the header's own notification-bar
  capability. `section_structure_service.add_section`/`duplicate_section`
  already refuse to create new instances of a hidden section. But
  `preset_service._build_sections_for_page` built `StorefrontSection` rows
  straight from preset/Ready-Template entries with **no such check** — a
  second, un-gated write authority for the same "add a section" concept.
  Four real A8 Ready Template recipes (`premium_leather`, `street_drop`,
  `racer_tech`, `anniversary_mosaic`) carry a `"ticker"` component token that
  maps to `announcement_bar`; applying any of them created a live
  `announcement_bar` instance alongside the header's own notification bar —
  the exact double-render defect `golden_reference_service.py` documents
  avoiding on the Golden Home composition. No test previously covered this
  path.
- **Action:** filtered `hidden_from_library` entries out once, where each
  page's preset entries are bound — before either section-building or the
  parallel Container/row-grouping logic (both keyed off the same `entries`
  list) consume them, so both stay in sync. New regression test
  (`HiddenFromLibrarySectionsNeverBuiltByPresetTests`) applies all four
  ticker-bearing recipes and asserts no `announcement_bar` section is built.
- **`announcement_bar` itself is NOT deleted** — existing/future legitimate
  instances (however created historically) still render via
  `render_service.py`'s `"announcement_bar": _static_context` mapping; this
  was a "reduce the active caller" fix per the Master Prompt's own guidance
  ("if an active caller still exists: reduce/migrate that caller first
  rather than leaving two authorities"), not a full section retirement,
  since the header notification-bar replacement path for any *existing*
  merchant who already added one was out of scope for this bounded fix.
- **Disposition:** THIN ADAPTER CLOSED (single gate now covers both callers);
  section registry entry itself remains CANONICAL KEEP (hidden, rendering
  preserved for compatibility).
- Commit `61eff5b`.

## Full retirement-candidate classification (re-verified against current code)

| Candidate | Disposition | Evidence |
|---|---|---|
| `storefront_discard` | **RETIRED** | Zero live callers; proven R4 replacement. Batch 1. |
| `announcement_bar` preset-application gap | **FIXED (thin adapter closed)** | Batch 2. |
| `announcement_bar` section (registry entry / renderer) | **CANONICAL KEEP** | Still legitimately rendered for any existing instance; hidden from all merchant-facing add paths (now including presets). No live add path remains. |
| Legacy settings writer (`storefront_section_settings`) | **NOT SAFE TO REMOVE YET** | Live-linked from `editor.html`; ~23 non-schema section types have no R4 settings-schema path yet (unchanged since Task 6). |
| Structure mutation views (container/cell/row add/settings/layout/move/remove, cell add-section/clear) | **NOT SAFE TO REMOVE YET** | Live-linked from `editor.html`; R4 has partial parity only (`container.change_layout`, `cell.add_section`) — arbitrary placement and Container/Cell-level settings editing remain a genuine gap. |
| Toggle / lock (`storefront_section_toggle`/`_lock_toggle`) | **NOT SAFE TO REMOVE YET** | R4 has proven equivalents (`section.toggle_active`/`toggle_locked`), but both remain live-linked from `editor.html`, the only reachable editor — deleting now removes working merchant UI, not dead code. |
| Collapse (`storefront_section_collapse_toggle`) | **NOT SAFE TO REMOVE YET** | Editor-only UI convenience, no persisted R4 concept by design (not a capability gap) — still live, functioning UI in the only reachable editor. |
| Discard/Restore/History UI (`storefront_restore`, `storefront_history`) | **NOT SAFE TO REMOVE YET** | Live-linked from `editor.html`/`history.html`/`r3_toolbar.html`. R4 has a proven discard equivalent; restore/history browser has no R4 UI equivalent yet. |
| Undo/Redo | **KEEP AS FINAL** (unchanged) | Already converged — legacy and R4 share `apply_history_command_current` bare. |
| Granular reset family (section/field/page/header/footer/storefront-to-baseline) | **NOT SAFE TO REMOVE YET** | R4 has proven mutation-type equivalents for all six, but all six legacy routes remain live-linked from `editor.html`/panel templates. |
| Media CRUD (`media_views.py` canonical) vs. legacy per-section forms in `editor.html` | **CANONICAL KEEP** (`media_views.py`) | `media_views.py` is the single shared authority for both legacy and R4 (Task 7 confirmed); no separate legacy duplicate exists at this layer. |
| Global Hero/Banner admin (`apps/dashboard/views.py` `hero_*`/`banner_*`) | **KEEP — legitimate compatibility mirror** | Full field parity with canonical `media_views.py` confirmed (superset, even), BUT this remains the primary "homepage" dashboard nav entry and the sole content-management path for any store not using the visual storefront layout (`storefront_builder_active` flag gates only a guidance message, not access) — has its own full test suite (`apps/content/tests/test_homepage_media.py`). Not a pure duplicate; canonical owner for storefront-builder stores is `media_views.py`, but this is still required for non-builder stores. |
| Legacy merchant editor shell (`editor.html`) | **NOT SAFE TO REMOVE YET** | Sole live, reachable merchant path (see headline finding above). Matches the disposition ledger's own pre-existing ruling. |
| Ready Template gallery/apply (`storefront_template_gallery`/`storefront_apply_layout_preset`) | **CANONICAL KEEP** | Deliberately kept separate from R4's template mutations per Task 8's own evidence — not a duplicate. |
| `storefront_apply_industry_layout` | **NOT SAFE TO REMOVE YET** | No R4 equivalent; a distinct concept (installs industry-suggested layout into a fresh Draft, not a Template-DNA switch); embedded as a plain form inside `editor.html` — retirement is coupled to the editor shell's own retirement, not an independent duplication problem. |
| Full legacy Appearance/Header/Footer forms | **KEEP AS CANONICAL** | Field-by-field parity check (this session) found the majority of fields — not "one or two" — have no R4 UI write path (see headline finding #3). Per the Master Prompt: only delete when *all* required capabilities have a valid replacement; a narrow subset qualifying is not grounds to delete the whole form. |

No `UNKNOWN` entries remain — every candidate has a final, evidenced
disposition.

## Targeted verification

- Batch 1: `test_views`, `test_phase2_lifecycle_safety`, `test_r4_vertical_slice`
  (462 tests) — pass, only 3 pre-existing failures (reproduced identically on
  unmodified `34c1fba9`, confirmed via `git stash`).
- Batch 2: `test_preset_service` (40 tests, including the new regression
  test) — all pass. Broader sweep across `test_a8_ready_template_catalog`,
  `test_a8_ready_template_contracts`, `test_section_registry`,
  `test_u7_ready_template_baseline`, `test_u10_ready_template_catalog`,
  `test_ready_template_real_previews` (355 tests) — 1 pre-existing failure
  (`test_reset_rejects_unknown_template_key`, reproduced identically on
  unmodified `34c1fba9`), unrelated to this change.
- Consolidated Task-9 regression (both batches together, 857 tests across
  all ten touched/related modules): `FAILED (failures=2, errors=2, skipped=3)`
  — the exact same 4 pre-existing failures found in the narrower runs above,
  zero new regressions.
- `python manage.py check`: clean.
- `python manage.py makemigrations --check --dry-run`: no changes detected
  (no migration needed — no model/field changes in this task).
- `git diff --check` (`34c1fba9..HEAD`): clean.

## Independent review

One fresh reviewer, dispatched to an isolated `git worktree`
(`/tmp/rastisi6-task9-review`, detached at commit `61eff5b` — Batches 1+2),
with no prior session context. Verified: `storefront_discard`'s zero-caller
claim (full-worktree search, not just `apps/storefront_builder/templates`)
and that R4's `storefront_r4_discard` fully subsumes the deleted tests'
coverage (and is in fact stricter — atomic + stale-revision gated, unlike
the legacy view it replaced); read `preset_service.py` in full and confirmed
the `hidden_from_library` filter's ordering is correct (applied once,
upstream of every downstream consumer keyed off the same `entries` list) and
that no other preset/baseline write path re-derives rows from an unfiltered
source; ran all 10 targeted modules independently (857 tests) and got the
exact same 4 pre-existing failures, by name; confirmed no canonical shared
service was touched; independently re-derived the R4-reachability and
field-parity restraint claims from current code.

**Verdict: CRITICAL 0, IMPORTANT 1, MINOR 2.**

- **IMPORTANT (fixed):** commit `5ed6486`'s message claimed
  `legacy_disposition.md` was updated; it wasn't touched until this closure
  pass. Fixed by actually updating it now (see the table above/in the ledger
  itself) — every row re-verified and given its real current disposition,
  including the two rows this task's commits actually changed. No re-review
  was re-dispatched for this alone (it is a documentation-accuracy fix with
  no code-behavior surface); the corrected ledger is part of this closure
  commit.
- **MINOR (fixed):** `golden_reference_service._rebuild_home_composition`
  intentionally forks `preset_service._build_sections_for_page`'s row-build
  loop (Golden sections are merchant-authored, not template slots) but
  didn't carry the same `hidden_from_library` guard — safe today only
  because the static `_golden_home_composition()` tuple hand-omits
  `announcement_bar`, with no structural guard against a future edit
  reintroducing it. Added the same defensive assertion (fail loudly, matching
  the function's existing style for its `container_settings` invariant)
  rather than a silent skip, since Golden's composition is a fixed, reviewed
  tuple, not merchant input.
- **MINOR (accepted, out of scope):** no remediation/audit query was added
  for any *already-existing* `announcement_bar` section instance created by
  one of the 4 ticker recipes before this fix. The fix prevents new
  occurrences; per the Product Owner ruling ("no historical-data migration
  machinery is required... fresh deterministic test data is acceptable"),
  cleaning up any such pre-existing rows is left to whoever seeds/owns that
  data, not a Task 9 migration.
