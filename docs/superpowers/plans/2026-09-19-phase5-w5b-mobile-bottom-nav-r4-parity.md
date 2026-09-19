# P5-W5B — Mobile Bottom Navigation, R4 Parity

## Existing authority (source-verified, all pre-existing, unmodified by W5B)

1. **`apps/storefront_builder/global_region_registry.py`** — `GLOBAL_MOBILE_NAV_REGION`
   is a fully-defined third global chrome region (`key="mobile_bottom_nav"`,
   `variant_setting_key="mobile_nav_variant"`, `default_variant="hidden"`), with
   exactly **9 registered variants**: `hidden`, `luxury_floating_cart`, `four_item`,
   `five_item`, `raised_cart`, `floating_dock`, `glass_dock`, `minimal_icons`,
   `wide_cart`. Each carries a trusted `renderer` template path under
   `storefront_builder/partials/global_mobile_nav/`.
2. **`mobile_nav_variant` is already a field of the versioned `footer_config` JSON**
   (no schema/migration needed) — `layout_service.validate_footer_config()` already
   validates it against `GLOBAL_MOBILE_NAV_REGION` unconditionally (lines 333-335),
   alongside `footer_variant`.
3. **`appearance_authority_service.apply_footer_variant(version, footer_variant=None,
   mobile_nav_variant=None)`** already accepts both independently — passing only
   `mobile_nav_variant` updates typed `selections["bottom_nav"]` and leaves
   `selections["footer"]` untouched (confirmed by direct source read, lines 253-286).
4. **`_apply_footer_update()` (`r4_mutation_service.py`) already calls
   `apply_footer_variant(..., mobile_nav_variant=cleaned["mobile_nav_variant"])`
   on every `footer.update` mutation** (line 1051) — `mobile_nav_variant` is always
   present in `cleaned` (via `validate_footer_config`), so the typed-manifest sync
   already happens on every footer save; it just can never currently be CHANGED by a
   merchant through R4, because of Gaps 1/2 below.
5. **The public/preview renderers already render the resolved Mobile Bottom Nav
   variant** — `views.py` (`storefront_editor`/`storefront_public_home` and others)
   computes `mobile_bottom_nav_template` via `store_appearance_global_renderer_template`
   and both `preview.html`/`ready_template_live_preview.html` already
   `{% include mobile_bottom_nav_template %}` unconditionally.
6. **The legacy R3 footer editor ALREADY exposes a real, working merchant-facing
   selector for this exact field** —
   `templates/dashboard/storefront_builder/partials/footer_panel.html` (lines 29-33)
   renders a `<select name="mobile_nav_variant">` populated from
   `mobile_nav_variants` (itself `global_region_registry.list_global_variants(
   GLOBAL_MOBILE_NAV_REGION)`, `views.py` lines 3024/3048), labeled **"ناوبری پایین
   موبایل"** — this is the exact label W5B reuses for R4, and the exact registry-driven
   list-comprehension pattern to mirror.
7. **The R4 Global Design panel's generic field/mutation JS plumbing already supports
   this with zero new code**: `r4_editor.js`'s delegated `change` handler (lines
   1386-1423) does `field.closest('[data-r4-global-mutation]')` per individual field —
   a `<select data-r4-global-field="mobile_nav_variant">` nested inside ANY element
   carrying `data-r4-global-mutation="footer.update"` (a new sibling `<section>`, not
   necessarily the same one `footer_variant` lives in) will be captured and POSTed
   automatically, with no JS change.
8. **`preset_service.reset_footer_to_baseline()`** already replaces the *entire*
   `footer_config` (including `mobile_nav_variant`) with the Ready Template's baseline
   snapshot — Bottom Nav reset is already covered by the existing Footer reset; W5B
   adds no separate reset control.

## Confirmed current gap (source-verified)

1. **GAP 1**: `_FOOTER_UPDATE_ALLOWED_PATCH_KEYS` (r4_mutation_service.py:1013) does
   not include `"mobile_nav_variant"` — any patch containing that key is rejected
   outright with `invalid_footer_patch` (400), before reaching the candidate-merge
   step at all.
2. **GAP 2**: even if GAP 1 alone were fixed, `_apply_footer_update()`'s
   candidate-merge block (lines 1025-1034) never reads `patch["mobile_nav_variant"]`
   into `candidate["mobile_nav_variant"]` — the value would silently stay at
   whatever `effective_footer_config()` already had. **Both gaps must be fixed
   together**, or the second produces a silent no-op instead of the first's explicit
   400.
3. **GAP 3**: `_build_global_design_context()` (r4_views.py:362) provides
   `header_variants`/`footer_variants` but no `mobile_nav_variants` — the R4 Global
   Design panel's read projection has nothing to populate a selector from.
4. **GAP 4**: `r4/editor.html`'s Global Design panel renders a Footer-variant
   selector but no Mobile Bottom Navigation selector at all.

These four gaps are the entire vertical slice. Everything else in the authority
chain already exists and needs no change.

## Exact vertical slice (minimal production changes)

1. `apps/storefront_builder/services/r4_mutation_service.py`:
   - Add `"mobile_nav_variant"` to `_FOOTER_UPDATE_ALLOWED_PATCH_KEYS`.
   - Add `if "mobile_nav_variant" in patch: candidate["mobile_nav_variant"] =
     patch["mobile_nav_variant"]` to `_apply_footer_update()`'s candidate-merge block.
   - No change to `validate_footer_config`, `apply_footer_variant`, the mutation
     type (`footer.update` stays the single entry point), or any other function.
2. `apps/storefront_builder/r4_views.py`:
   - Add `"mobile_nav_variants": [{"key": v.key, "label_fa": v.label_fa} for v in
     global_region_registry.list_global_variants(global_region_registry.
     GLOBAL_MOBILE_NAV_REGION)]` to `_build_global_design_context()`, mirroring the
     existing `footer_variants`/`header_variants` entries exactly.
3. `apps/storefront_builder/templates/dashboard/storefront_builder/r4/editor.html`:
   - Add one new `<section class="r4-global-design-group"
     data-r4-global-mutation="footer.update">` sibling, immediately after the
     existing Footer section, titled **"ناوبری پایین موبایل"** (matching the legacy
     R3 label exactly), containing one `<select data-r4-global-field=
     "mobile_nav_variant">` populated from `global_design.mobile_nav_variants`,
     pre-selected from `global_design.footer.mobile_nav_variant`. A separate
     `<section>` (not folded into the Footer section) so it reads as its own
     product-level control, per the product goal — while still sharing the
     `footer.update` mutation group internally, matching the underlying
     `footer_config` storage exactly.
4. **No JavaScript file changes.** `r4_editor.js`'s existing generic `data-r4-global-
   field`/`data-r4-global-mutation` delegated handler already covers this
   automatically (source-verified above).
5. **No model change, no migration, no new renderer, no new registry entry, no new
   mutation type.**

## Single source of truth (reaffirmed, unchanged by this plan)

```
GLOBAL_MOBILE_NAV_REGION
    -> mobile_nav_variants read projection (_build_global_design_context, NEW)
    -> R4 selector (r4/editor.html, NEW)
    -> existing footer.update mutation (UNCHANGED type)
    -> _apply_footer_update() (EXTENDED: allowlist + candidate-merge only)
    -> layout_service.validate_footer_config() (UNCHANGED)
    -> appearance_authority_service.apply_footer_variant(mobile_nav_variant=...) (UNCHANGED, already called)
    -> typed bottom_nav selection + footer_config mirror (UNCHANGED)
    -> existing Preview/Public renderer (UNCHANGED)
```

No parallel authority is introduced anywhere in this chain.

## TDD plan

New focused module:
`apps/storefront_builder/tests/test_phase5_w5b_mobile_bottom_nav_r4_parity.py`.
Genuine RED observed against the four gaps above (patch rejected/silently dropped,
`mobile_nav_variants` absent from context, no selector rendered), then GREEN after
the minimal fix. Contracts A-S per the repair directive: registry-driven read
projection (no duplicated hardcoded list), selector markup/wiring, `footer.update`
acceptance, fail-closed on unknown key, sibling-state isolation (`footer_variant`,
`FOOTER_TOGGLE_FIELDS`, `extra_blocks`, `responsive`, unrelated Store Appearance
families), typed `bottom_nav`/`footer` selection isolation, stale `base_revision`
rejection, exactly-one revision advance, Undo/Redo round-trip, Draft Preview
resolution, Published-unchanged-until-Publish, Public-after-Publish, tenant
isolation, zero migrations, and coverage that every one of the 9 registered variants
appears in the projection / passes validation / resolves to its own trusted renderer
(derived from the registry, never a second hardcoded 9-item list in the test file).

## Browser QA plan

Reuse `tools/storefront_builder_r4_qa/` conventions (no second harness), extending
a workstream-scoped sibling script. Real mobile-viewport merchant journey: open R4
Builder -> Global Design -> find "ناوبری پایین موبایل" -> confirm registry-driven
options -> switch to a non-hidden variant -> confirm save/revision -> Preview
(mobile viewport) shows the new variant, Footer variant unchanged -> Undo restores
previous -> Redo restores changed -> Public unchanged pre-Publish -> Publish ->
Public now shows the new variant -> fresh Draft with `hidden` shows no nav in
Preview -> a stale mutation is rejected. Representative variants for the browser
run: `hidden`, one conventional multi-item variant (`four_item`), one structurally
distinct variant (`floating_dock` or `glass_dock`) — the remaining 6 get cheap
registry-driven Django-test coverage only (per the repair directive's guidance,
since the existing renderer/registry tests already certify each variant's own
rendering).

## Non-goals (explicit)

- No new Bottom Navigation variant, template, renderer path, registry, model, JSON
  field, DB column, or migration.
- No move of Hero/Product View/Product Card/Badge into the Normal Builder — they
  remain Design-Lab-oriented per the approved W5 Master Plan.
- No new JS mutation-sending function/branch.
- No independent "Reset Bottom Nav" control — the existing Footer reset already
  covers `mobile_nav_variant` as part of the whole `footer_config` baseline
  replacement (documented behavior above, unmodified).
- No change to the 704-cell Ready Template renderer certification, no touch to
  `global_mobile_nav` renderer templates or Ready Template recipes.

## Architectural duplication check

Zero new authorities. Every read, write, validation, sync, and render step in the
chain above already existed before W5B; the only new code is the read-projection
entry, the two-line write-path extension (allowlist + merge), and the template
markup — all following the exact existing Header/Footer pattern byte-for-byte.

## Rollback / stale-write implications

`footer.update` already goes through the standard R4 mutation boundary
(`_lock_active_draft`/`base_revision` check, single `edit_revision` advance, single
`edit_history_service` entry) — extending its allowed patch keys does not change
that boundary's semantics at all. A stale `base_revision` on a `footer.update` call
that happens to include `mobile_nav_variant` is rejected by the exact same existing
mechanism every other `footer.update` field already uses. Undo/Redo operate on the
whole Draft-history checkpoint (before/after full state), so a Bottom-Nav-only
change round-trips through Undo/Redo with zero special-casing.

## Preview / Publish verification plan

Both `preview.html` (Draft Preview) and `ready_template_live_preview.html`
(Ready-Template live preview) already resolve `mobile_bottom_nav_template` from the
version passed in, unconditionally. The public storefront path resolves it from
whichever version (`published_version` pre-Publish, the newly-promoted version
post-Publish) it is rendering — no code change needed to either path; W5B's own
tests exercise Draft Preview showing the change and Public staying on the old
variant until Publish, then reflecting the new one after.

## Evidence plan

`docs/qa_evidence/storefront_design_engine/phase5/w5b_mobile_bottom_nav_r4_parity/`:
`starting_state.md`, `implementation_plan_summary.md` (this file's summary),
`tdd_red.txt`, `tdd_green.txt`, `authority_chain.md`, `sibling_isolation.md`,
`focused_tests.txt`, `browser_qa.md`, `code_review.md`,
`full_suite_identity_comparison.md`, `source_diff.md`, `final_report.md`.
