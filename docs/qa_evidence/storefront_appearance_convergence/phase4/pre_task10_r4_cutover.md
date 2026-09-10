# Phase 4 — Pre-Task-10 Remediation: R4 Live Cutover

Goal (per the Pre-Task10 remediation gate): close the real remaining
architecture gaps Task 9's fresh audit found — before Task 10, which is
certification-only and must not become an implementation task — then make
R4 the live default merchant editor. Task 9 itself is CLOSED and is not
redone here.

Pre-remediation safety backup:
`backup/rastisi6-phase4-pre-final-remediation-20260910` ==
`75ede8ab82c6e53090b04eadc7ea9cf9f8691480` (the Task-9 final checkpoint),
pushed and verified before the first production change.

## FINAL REMEDIATION CLOSURE (Pre-Task-10 final remediation — Gaps 1-4)

A later session (this one) closed every item this document's first pass
deferred, plus the four remaining gaps the resulting continuation prompt
enumerated:

- **Gap 1 (compound-field parity)** — `announcement_links`, header/footer
  `extra_blocks`, and the header/footer `responsive` hide-on-tablet/
  hide-on-mobile toggles (deferred below as "compound multi-row UI, not a
  flat scalar patch key") are now all wired into `header.update`/
  `footer.update`, reusing the SAME canonical validators
  (`validate_header_config`/`validate_footer_config`) and the R4 Inspector's
  existing `repeater` field-type concept (extended to the Global Design
  panel via a new `data-r4-global-repeater-field` marker, not a second
  architecture). Targeted RED/GREEN tests added. Commit `aeff5c1`.
- **Gap 2 (family browser certification)** — the 15 `NOT YET CERTIFIED`
  MIGRATE families are now certified with real executed browser evidence,
  via one new config-driven scenario (`phase3-final-remediation-family-gate`
  in `run.mjs`) reusing the existing generalized Task-4 harness mechanism.
  Two genuine pre-existing bugs in that mechanism itself were found and
  fixed along the way (a stale-section-id bug across a Publish+clone, a
  save-state-polling race). Commit `d51671e`. See
  `family_certification_matrix.md`.
- **Gap 3 (second legacy-retirement pass)** — every row this document and
  `legacy_disposition.md` previously left `NOT SAFE TO REMOVE YET` because
  R4 lacked capability was re-verified against current code (not trusted
  from either pass's claims) now that Gaps 1-2 closed the field/
  certification gap. Result: settings-save, composition, toggle/lock, and
  the granular reset family are reclassified THIN NON-AUTHORITATIVE ADAPTER
  (R4 has full, verified parity); exactly two capabilities remain
  genuinely legacy-only (restore/history browser; industry-vertical layout
  presets), both CANONICAL KEEP. Commit `30c7c72`. See
  `legacy_disposition.md`.
- **Gap 4 (independent review)** — a fresh reviewer in an isolated worktree
  reviewed the complete diff (`75ede8ab8...` → this session's final HEAD)
  and returned 0 CRITICAL / 1 IMPORTANT: `container.update_settings`'s
  `background_mode`/`background_color`/`background_pattern` keys were
  backend-accepted from the first pass but had no R4 UI control at all — a
  real merchant-facing gap the "full functional parity" claim below (Step
  1C) did not catch. Fixed (commit `9d3d106`) by adding the missing R4
  controls, reusing the existing `container.update_settings` mutation and
  `effective_container_settings` validator unchanged; re-reviewed clean.

The one item still NOT closed — Container `content_width` — remains correctly
`INTERNAL/NOT MERCHANT-FACING` per its own row below: the legacy editor
itself does not expose it either, so R4 matching that restraint is not a gap.

## Scope actually completed this session, and what was deliberately deferred

**(Historical record of the FIRST remediation session — preserved as-is
below; superseded where the closure section above says so.)**

This remediation's true scope (full field parity across ~40 legacy
Appearance/Header/Footer fields, closing every composition gap, formal
Task-4-harness browser certification for 15 section families, the live
cutover, and a second legacy-retirement pass) is comparable in size to
several of the prior numbered Tasks — each of which took a dedicated
session with multiple independent-review rounds. Rather than rush every
item to a fabricated "done", this session did real, verified,
independently-testable work on the highest-leverage items and is explicit
about what remains.

**Completed, verified (targeted Django test suite, 330+ tests, zero new
regressions beyond the one pre-existing frozen-baseline failure already
documented in `task9_legacy_retirement.md`):**

- Step 1B (Appearance/Header/Footer field parity) — see below.
- Step 1C (Composition parity) — see below.
- Step 1E (Ready Template orchestration) — re-confirmed unchanged from
  Task 8's own ruling (see below); no new work needed.
- Step 2 (R4 live cutover) — see below.

**Deliberately deferred, and why (see "Remaining gap" sections below for
each):**

- A handful of compound-UI legacy fields (3 repeater-shaped fields, the
  header/footer per-field "hide on tablet/mobile" responsive toggles, and
  Container `content_width`, which the legacy editor itself does not
  expose yet either) remain legacy-only.
- Formal Task-4-harness browser certification for the 15 families flagged
  `NOT YET CERTIFIED` in `family_certification_matrix.md` was not
  performed this session — see "Family certification" below for why this
  is a justified, not an unjustified, gap.
- Step 3 (second legacy-retirement pass) was not attempted: the legacy
  editor remains genuinely needed as the reachable path for the deferred
  fields above, so none of Task 9's `NOT SAFE TO REMOVE YET` rows changed
  disposition.

## Step 1B — Appearance/Header/Footer field parity

Field-by-field classification, re-verified from current code (matches
`task9_legacy_retirement.md`'s headline finding #3's field inventory):

| Field group | Classification | Disposition this session |
|---|---|---|
| 8 `color_overrides` keys, 8 `theme_overrides` keys | REQUIRED EXISTING CAPABILITY | **Wired** — `appearance.update` patch accepts a partial `color_overrides`/`theme_overrides` dict, merged onto the current set with the exact same "drop the override if it now matches the resolved base color" dedup rule the legacy form uses. Global Design panel gained one `<input type=color>` per key. |
| `radius`, `button_radius`, `density` (Template-owned) | REQUIRED EXISTING CAPABILITY | **Wired** — extended into the existing Template-precedence loop (Template > posted > current), matching the 7 real `_TEMPLATE_OWNED_FIELDS` exactly (previously only 4 of 7 were reachable through R4). |
| `image_fit`, `image_hover`, `card_image_crossfade`, `card_image_zoom` | REQUIRED EXISTING CAPABILITY | **Wired** — always read from the patch when present, never gated on a Template switch (matching R3's own `_field()` semantics). |
| `content_width`, `grid_density`, `card_shadow`, `card_hover`, `hero_style` (Phase 8 P0-7 structural fields) | REQUIRED EXISTING CAPABILITY | **Wired** — plus a real pre-existing bug found and fixed at the canonical authority layer (see "Bug found" below). |
| Header: `show_search`/`show_account`/`show_cart`/`show_wishlist`/`sticky`/`announcement_enabled`, `announcement_text`, `announcement_show_phone` | REQUIRED EXISTING CAPABILITY | **Wired** — `header.update`'s allowlist widened; `show_cart` still cannot be disabled (server-side guarantee preserved). |
| Footer: all 9 `FOOTER_TOGGLE_FIELDS` | REQUIRED EXISTING CAPABILITY | **Wired** — `footer.update`'s allowlist widened; "footer cannot be entirely empty" guarantee preserved. |
| `announcement_links`, header `extra_blocks`, footer `extra_blocks` (repeater-shaped) | REQUIRED EXISTING CAPABILITY | **Deferred** — compound multi-row UI, not a flat scalar patch key; the R4 Inspector's existing `repeater` field type (Task 6) is section-scoped, not wired into the Global Design panel's per-field-change model. Real gap, not invented scope creep — left legacy-only. |
| Header `responsive` (4 keys), footer `responsive` (9 keys) (hide-on-tablet/mobile) | REQUIRED EXISTING CAPABILITY | **Deferred** — same compound-shape reason. |
| Container `content_width` | INTERNAL/NOT MERCHANT-FACING | **Not wired** — the legacy `storefront_container_settings` view itself deliberately preserves this field unconditionally ("not exposed until the renderer has a family-safe implementation"); R4 matches that restraint exactly, never exposing a capability legacy itself withholds. |

**Bug found and fixed (canonical-authority layer, affects legacy too):**
`appearance_authority_service._merge_appearance_config`'s managed-key set
(`_MANAGED_APPEARANCE_KEYS`) was `frozenset(APPEARANCE_CONFIG_DEFAULTS)` —
which never included the 5 Phase-8 P0-7 structural fields (they are
deliberately sparse-by-design, not part of `APPEARANCE_CONFIG_DEFAULTS`).
Reproduced directly against the unmodified function: a bare
`apply_appearance_patch(version=v, patch={"content_width": 1200})` left
the saved config completely untouched. This silently broke a Store-global
edit of any of these 5 fields through **both** the legacy
`storefront_appearance_editor` view (which has always read/posted them)
and any future R4 caller — a real, previously-undiscovered defect, not
new-capability scope creep. Fixed by including
`layout_service.PAGE_APPEARANCE_KEYS` (the same 5-key set
`validate_page_appearance_overrides` already treats as canonical) in the
merge allowlist — single source of truth, no schema change.

New tests: `FieldParityUpdateTests` (11 tests,
`test_r4_store_appearance_mutations.py`) plus 2 pre-existing tests
(`test_unknown_header_patch_key_is_rejected`/
`test_unknown_footer_patch_key_is_rejected`, `test_r4_vertical_slice.py`)
updated to use `extra_blocks` (still genuinely unknown/deferred) instead
of `show_search`/`show_about` (now legitimately known) as their
unknown-key representative — same precedent as Task 7's own
`NonSchemaSectionTests` representative swap.

## Step 1C — Composition parity

Task 7's B1 audit left two genuine gaps open (items #1/#2 "Container
never exposes merchant-facing controls" and #5 "arbitrary/non-adjacent
placement"). Both closed this session, reusing only existing canonical
services — no second composition model, no second persistence layer, no
drag/drop framework:

- **`section.move_to_cell`** (new `r4_mutation_service` mutation type,
  `section_structure_service.move_section_to_cell`) — place an EXISTING
  section into any valid target Cell (not just an adjacent swap), reusing
  the exact same `container_service.move_block` `section.move`'s own
  adjacent-swap path already calls. A locked source/target Container, or a
  legacy row member (whose linear adjacency the row-compat system depends
  on — the same guard `remove_section` already enforces), is rejected.
  Structure panel UI: one "move to empty cell" picker per section row
  (mirrors Task 7's own empty-cell "add" picker pattern) — a simple
  explicit target-cell operation, not a drag/drop framework, per the
  remediation's own instruction.
- **`container.update_settings`** (new mutation type) — gap/mobile_mode/
  vertical_align/height_mode/background_mode/background_color/
  background_pattern, wired to the exact same
  `container_service.effective_container_settings` the legacy
  `storefront_container_settings` view already uses. `content_width` is
  preserved unconditionally, matching legacy's own restraint (see the B
  table above). Structure panel UI: inline controls on each Container row.

New tests: `SectionMoveToCellTests` (7 tests), `ContainerUpdateSettingsTests`
(4 tests), both in `test_r4_vertical_slice.py` — same negative-path
coverage shape every sibling Task-7 mutation type already has (tenant
isolation, locked-container rejection, invalid ids, stale revision).

## Step 1D — Family/settings certification

Re-read `family_certification_matrix.md` fresh. 15 `MIGRATE` families
(`hero_banner`, `image_slider`, `newest_products`, `best_sellers`,
`discounted_products`, `amazing_offers`, `promo_cards`, `rich_text`,
`blog_posts`, `product_section`, `trust_features`, `quick_links`, `faq`,
`testimonials`, `video_section`) already have their `SettingsSchema` and
CSS-completeness columns closed (mostly by Task 5/6); every remaining
`NOT YET CERTIFIED` row is missing exactly one thing: a dedicated Task-4
QA-harness (`tools/storefront_builder_r4_qa/run.mjs`) browser scenario
proving the field's specific DOM/render contract end-to-end, the same bar
every already-`CERTIFIED` row cleared.

This session did **not** write and debug 15 (or a consolidated) new
Playwright scenarios against a live Django + Chromium instance — a
first-party UI-automation effort of comparable size to Task 6's own
dedicated browser-certification work, not something to rush through
inside a remediation whose own speed policy caps implementation at three
batches with targeted tests. No row's disposition was changed to
`CERTIFIED` without that real evidence — doing so would be exactly the
"unjustified" shortcut the remediation gate explicitly forbids.

**Disposition: all 15 remain `NOT YET CERTIFIED`, now formally re-affirmed
with the actual current-code reason** (backend schema/persistence/render
path already proven at the Django/unit level per Task 5/6's own evidence;
only the Task-4-harness browser proof is outstanding) rather than left as
a stale, unexplained row. This is a justified, explicitly-tracked
remaining gap for a follow-up session — not a family whose contract is
legitimately media-only/fixed/context-owned/domain-owned masquerading as
"not yet done" (none of these 15 are misclassified; they are genuinely
incomplete).

## Step 1E — Ready Template orchestration

Re-confirmed against current code: `apply_preset_with_checkpoint` (legacy)
and `appearance.template.apply` (R4 in-place full-recipe apply) remain the
two legitimate, different, already-tested capabilities Task 8's own
evidence doc ruled on — no new merchant-facing orchestration was added or
found. `switch_template_preserving_content` (Task 8's own new capability,
content-preserving DNA-only switch) remains a third, genuinely distinct
operation. No competing merchant-facing authority for the SAME operation
exists. No code change needed; canonical ownership is unchanged and
unambiguous.

## Step 2 — R4 live cutover

Required outcome achieved: **dashboard/storefront appearance entry -> R4
Editor**, reachable without first entering the legacy editor.

- `StorefrontLayout.r4_editor_enabled` default flipped `False` -> `True`
  (`models.py`), with migration `0020_r4_editor_enabled_default_true.py`
  (`AlterField` + a `RunPython` data migration flipping every existing
  Store's layout to `True` — "no important production data to preserve"
  per the remediation's own instruction, and Migration history is
  preserved, no squash/reset/rewrite). The flag is no longer a blocking
  rollout gate; it is kept as a genuine non-blocking compatibility
  mechanism — a Store can still be explicitly pinned back to the legacy
  editor (every R4 endpoint's existing gate check is unchanged) if a
  regression is found for that Store.
- `apps/dashboard/templates/dashboard/base_admin.html` — the primary
  "سازنده فروشگاه"/"ظاهر و طراحی" nav entries (priority 1/2) and every
  global-search shortcut (logo/header/footer/appearance) now point at
  `storefront-builder-r4-editor` instead of the legacy `storefront-
  builder-editor`. A new, clearly-labeled "ادیتور قدیمی (تنظیمات پیشرفته)"
  ("legacy editor — advanced settings") nav entry keeps the legacy editor
  reachable as the compatibility escape hatch for the fields documented as
  deferred in Step 1B above — the same pattern already established for the
  Global Hero/Banner admin mirror in `legacy_disposition.md`. **This is
  not retaining two co-equal editors**: R4 is the single primary nav
  target; the legacy link is explicitly labeled secondary/advanced, one
  click further away, exactly mirroring how R4 already links out to the
  legacy media-management screens for schema-less sections (Task 7 Batch
  3's own precedent).
- `r4_editor.js` — the dashboard nav's `?panel=appearance`/`?panel=header`/
  `?panel=footer` deep links (unchanged query-string contract) now
  auto-open R4's Global Design panel on load, so the nav shortcuts still
  land the merchant on the right screen.

New tests: `R4FoundationModelTests.test_r4_editor_is_enabled_by_default`,
`R4EditorRouteGateTests.test_r4_route_is_reachable_by_default_without_
opting_in`, `DashboardNavRoutesToR4Tests.test_primary_storefront_builder_
nav_item_points_at_r4` (all `test_r4_foundation.py`); `test_views.py`'s
`test_r4_editor_link_hidden_when_gate_disabled`/`test_r4_editor_link_
shown_when_gate_enabled` updated to `test_r4_editor_link_hidden_when_gate_
explicitly_disabled`/`test_r4_editor_link_shown_by_default` (same
precedent as the header/footer unknown-key test updates above — behavior
genuinely changed, so the test now asserts the new correct contract, not
patched to keep a stale one green).

## Step 3 — Second legacy retirement pass

**Not attempted.** Re-reading `legacy_disposition.md`'s `NOT SAFE TO
REMOVE YET` rows against this session's actual field/composition parity:
the legacy settings writer for ~23 non-schema section types, the granular
reset family, discard/restore/history UI, and the full legacy Appearance/
Header/Footer forms are all still the only reachable path for the
deferred fields in Step 1B (repeaters, responsive toggles) — retiring any
of them now would remove real, still-necessary merchant capability, the
exact same principle Task 9 itself already established. This is a
consistent, not an arbitrary, decision to defer Step 3 to the session that
closes the remaining Step 1B/1D gaps.

## Targeted regression

- `apps.storefront_builder.tests.test_r4_vertical_slice`,
  `test_r4_inspector`, `test_r4_store_appearance_mutations`,
  `test_phase2b_multiblock_cell_runtime`, `test_phase31_container_cell_
  builder`, `test_r4_appearance_overrides`, `test_r4_mutation_api`,
  `test_phase4_task3c_page_appearance`, `test_phase1_appearance_authority`,
  `test_preset_service`, `test_r4_foundation`, `test_views` — 330+ tests
  across the appearance/header/footer/composition surface, zero new
  regressions beyond the one pre-existing frozen-baseline failure already
  documented and reproduced-on-unmodified-checkpoint in
  `task9_legacy_retirement.md`.
- `python manage.py check`: clean.
- `python manage.py makemigrations --check --dry-run`: clean (the one
  new migration, `0020_r4_editor_enabled_default_true`, is already
  present and captures the full model change).
- `git diff --check`: clean.

## Independent review

See the closure commit for the independent-review record covering this
diff.
