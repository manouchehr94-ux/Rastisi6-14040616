# Task 6 — Converge every required product-facing family

Evidence for Task 6 (per the plan's internal Group A–F order). This document is updated after
each group/checkpoint; see `phase4/execution_ledger.md` for the chronological commit-by-commit
record and `phase4/family_certification_matrix.md` for the per-family status table.

## Prior investigation carried into Task 6

Two gaps were found and fixed as part of the Task 6 gap-analysis before group work began:

- **Finding 1 — `category_grid` ResourceSource inert.** `resource_source.py` already had a full
  `category` kind adapter (`ALLOWED_KINDS`, `category_resource_source_from_settings`/
  `_to_legacy_patch`, `_SECTION_ADAPTERS["category_grid"]`), and `_RESOURCE_SOURCE_AWARE_SECTION_KEYS`
  already included `category_grid` — but `r4_mutation_service._apply_section_update_settings`
  refuses any `source` patch unless `definition.settings_schema is not None`, and `category_grid`
  had no schema yet. The wrapper was silently inert. Fixed by adding `CATEGORY_GRID_SCHEMA` and
  wiring `category` into the shared R4 Resource Picker (search/ownership validation/serialization),
  entangled with the Group C category_grid schema work rather than done as a separate step.
- **Finding 2 — destructive legacy-form Save for `trust_features`/`amazing_offers`/`blog_posts`.**
  `storefront_section_settings`'s POST handler had no dedicated branch for these three families
  (unlike `faq`/`testimonials`/`video_section`/`newsletter`), so pressing Save on the legacy form
  fell through to the destructive `else: raw = {}` fallback and silently wiped their real stored
  content back to defaults. Fixed with dedicated POST-parsing branches (mirroring the existing
  `faq`/`testimonials` Alpine.js repeater pattern for `trust_features`) and matching template
  fields, RED/GREEN-verified against the exact bug before committing.

## Group A (hero_banner, image_slider, product_section, rich_text)

Already the strongest families entering Task 6 (schema and/or ResourceSource from earlier phases).
`image_slider` was the one real gap: it shares `_validate_slider_settings`/`default_slider_settings`
with `hero_banner` but was deliberately left unschematized (no registered variants). Gave it
`IMAGE_SLIDER_SCHEMA` — identical fields minus `hero_style` (hero_banner-variant-only) and minus
`appearance_overrides` (Task 7 scoped that Inspector field to `hero_banner` only; the underlying
`_with_appearance_overrides` wrapper still applies universally regardless of Inspector exposure).

## Group B (newest_products, best_sellers, discounted_products, promo_cards)

All four previously hardcoded their slice limit (8/8/6/4 respectively) and never read
`section.settings` — "simple auto-source catalog families, no independent selector needed beyond
the existing implicit query" per the plan's own Group B disposition. Each now has a real
single-field validator/schema exposing `item_limit` (bounds 2–24 for the three product families,
matching `product_section`'s own; 2–12 for `promo_cards`, matching `category_grid`'s, since it
renders through the identical `.tiles`/`.tile` markup). Every default equals the family's prior
hardcoded value, so an untouched section renders byte-identically. `render_service.py`'s four
context builders now read the setting (falling back to the historical hardcoded value), and all
four keys were added to `PER_INSTANCE_SECTION_KEYS` since their output now genuinely depends on
the section instance, not just the Store — this is also why the pre-existing query-caching test
was repointed from `newest_products` (no longer a valid example) to `featured_products`, a
MARKETING-ALIAS with no settings surface of its own that remains the correct representative.

## Group C (single_banner, multi_banner, category_grid, image_text, blog_posts)

- `category_grid`: `CATEGORY_GRID_SCHEMA` (see Finding 1 above).
- `blog_posts`: minimal schema (title + item_limit) — it already had a real validator.
- `image_text`: schema covering title/body_html (rich_text)/image_position (choice, mirroring its
  already-registered left/right variants). `image_url` deliberately NOT declared — the Inspector
  has no "media" field-type widget yet, so it stays managed through the legacy form's existing
  image-URL input, preserved as an unmanaged key.
- `multi_banner`: the U1A/R1 §9 finding ("only four CSS classes exist… narrowing deferred") is now
  resolved with full evidence — a fresh full-codebase write-path re-enumeration (every
  `layout_preset_registry.py` preset, every fixture/migration/test; still no merchant-facing form
  control for this key) found exactly **six** values ever persisted for `layout_variant`, matching
  exactly the six `.promo-grid--*`/`.banner-section--*` CSS classes that actually exist (the old
  "four" count predates the `atelier-duo`/`atelier-wide` additions). Replaced `_passthrough_dict`/
  `_empty_defaults` with a real closed-enum validator/defaults pair mirroring
  `_multi_banner_context`'s own render-time clamps (`offset` 0–50, `item_limit` 1–24, an
  absent/empty `item_limit` still means "all banners" — preserved byte-for-byte), plus
  `MULTI_BANNER_SCHEMA`. `has_settings_form` stays unset (the legacy drawer remains unreachable
  exactly as before — enabling it would additionally need a real POST-parsing branch, since the
  destructive `else: raw = {}` fallback would otherwise wipe these fields on Save; the R4 Inspector
  path has no such dependency). Four pre-existing tests that explicitly guarded the old "still
  passthrough" behavior were updated to assert the new, deliberate closed-enum coercion.
- `single_banner`: investigated and confirmed it is genuinely FIXED/STATIC — its render context
  (`_single_banner_context`) ignores `section.settings` entirely (always shows the first active
  banner from the section-scoped `PromotionalBanner` pool, already fully served by existing media
  CRUD). No field exists for a schema to declare; `_passthrough_dict`/`_empty_defaults` stay
  exactly as they are, now as an explicit, verified disposition rather than an unclassified
  placeholder — and the pre-existing "representative unschematized section" guard test (which
  used `faq`, since retired from that role by Group D below) was repointed to `single_banner`.

## Group D (trust_features, faq, testimonials, video_section, story_rail, quick_links, newsletter, amazing_offers)

- `video_section`, `quick_links`, `newsletter`, `amazing_offers` ("easy batch" — already real
  validators): minimal schemas exposing every field the validator already has, except
  `quick_links`'s `menu_id` (an FK into the Menu/MenuItem navigation infrastructure, not a
  catalog ResourceSource kind and no matching Inspector field type — stays legacy-form-managed,
  preserved as an unmanaged key) and `video_section`'s URL field (declared as `"text"` — there is
  no dedicated `"url"` field type; the real provider/URL validation still runs in the legacy
  validator afterward, unchanged).
- **`trust_features`/`faq`/`testimonials` — the new `repeater` field type.** These three families'
  only real content is a list of items (icon/title/subtitle; question/answer; name/quote/role), and
  the R4 Inspector had no field type for that at all. Built one, end to end:
  - `settings_schema.py`: `"repeater"` added to `ALLOWED_FIELD_TYPES`; a new
    `SettingsField.repeater_item_fields` attribute (each item's own sub-fields, restricted to
    `REPEATER_ITEM_FIELD_TYPES = {text, integer, boolean, choice}` — no nested repeaters, no other
    compound types); `_clean_repeater_value` does shape/count/length cleaning only (item-count
    bounds via the field's own `min_value`/`max_value`, each item cleaned per its declared
    sub-field type) — the section's own legacy validator, run afterward by
    `clean_section_schema_patch` exactly as for every other field type, stays the sole authority
    for business rules ("title required", "drop an item missing question/answer", the per-family
    item-count cap). `serialize_schema` recurses into `repeater_item_fields`.
  - `r4_views.py`: `"repeater"` added to `_INSPECTOR_SUPPORTED_FIELD_TYPES`.
  - `settings_field.html`: a new compound-field branch, server-rendering the CURRENT rows directly
    (no Alpine reactive array — deliberately plain DOM, matching how `appearance_override` is
    already handled, so add/remove/reorder are ordinary DOM operations: clone a hidden
    `<template>` row, remove a row element, swap two adjacent row elements). No dependency on the
    legacy editor page's global `itemRepeaterForm()` — this partial is self-contained.
  - `r4_editor.js`: `collectRepeaterRows`/`patchRepeaterField`/`addRepeaterRow` helpers; a
    dedicated `change` listener re-collects and patches on any sub-field edit; the existing
    delegated click listener grew add/remove/move-up/move-down handling.
  - `r4_editor.css`: matching `.r4-repeater*` styling, mirroring the existing compound-field
    (`.r4-appearance-override`, `.r4-resource-source-summary`) visual language.
  - `TRUST_FEATURES_SCHEMA`/`FAQ_SCHEMA`/`TESTIMONIALS_SCHEMA` wired into their `SectionDefinition`s.
  - **Two real defects found and fixed during real-browser verification** (not caught by the 92
    backend unit tests, which only exercise the Python contract layer):
    1. The pre-existing generic scalar `change` listener's `.closest('[data-r4-field-key]')` also
       matched the repeater's own wrapper `<div>` (which carries `data-r4-field-key` too, for the
       dedicated repeater listener to use) — every edit inside a repeater row ALSO fired the
       generic listener, which resolved `control` to that wrapper, read its non-existent `.value`
       (→ `undefined`), and sent a second, bogus empty-patch request racing the real one. Fixed by
       excluding `fieldType === 'repeater'` there too (mirroring the existing `appearance_override`
       exclusion), with a comment explaining why `.closest()` reaches the wrapper even from a
       sub-input with no `data-r4-field-key` of its own.
    2. `addRepeaterRow` eagerly called `patchRepeaterField` immediately after inserting a brand-new
       *empty* row — for `trust_features` (whose legacy validator requires a non-empty title per
       item), this meant every single "add row" click produced an immediate, entirely predictable
       400 before the merchant had typed anything. Fixed by removing that eager patch: a blank
       template row has nothing meaningful to persist yet; it saves naturally once the merchant
       edits any of its fields (via the dedicated `change` listener), and if they never fill it in
       and navigate away, it is simply never persisted — the correct outcome for a blank row.

### Real-browser end-to-end proof (repeater field type)

Both defects above were found and the fix verified via a real Playwright/Chromium session against
the actual dev server (not the Django test client) — logged in as a real staff user, opened the R4
editor, and exercised the Inspector's repeater UI directly for two families to prove the field
type is generic, not FAQ-specific:

- **`faq`** (pk-scoped test section): existing 2 items rendered with correct values; added a row;
  edited its question/answer; moved it up one position; removed a different row; final DOM state
  and the `#r4SaveState` indicator ("ذخیره شد") both correct; **DB read directly after the browser
  session confirmed the persisted `settings.items` matches the final on-screen state exactly**
  (equivalent to a reload-persistence check); the Preview page (`storefront-builder/preview/`)
  rendered the updated content correctly, 200 OK, no page errors.
- **`trust_features`** (icon/title/subtitle — a different shape, no section-level `title` field at
  all): same add/edit/move/remove/persist/preview sequence, same result. Proves the field type
  composes correctly for a materially different item shape, not just FAQ's two-text-field case.
- After both fixes: exactly one remaining console-logged 400 across the whole two-family run — the
  transient "icon filled, title still empty" moment while a merchant is mid-way through typing a
  new `trust_features` row (the legacy validator correctly rejecting a genuinely incomplete row,
  same category of rejection any other required-field validator in this app can already produce).
  No data loss (the DOM keeps whatever was typed regardless of save success), no page errors, and
  the row saves successfully the moment it becomes valid. This is treated as expected,
  architecturally-inherent behavior (a list-shaped field's patch necessarily carries the whole
  list, unlike a scalar field's independent single-key patch), not a defect — recorded here rather
  than "fixed away" because there is no clean fix that would not require duplicating the legacy
  validator's business rules into the JS layer, which this app's architecture deliberately avoids.
- Browser session used a throwaway staff user + two throwaway `StorefrontSection` rows created
  directly against the dev `db.sqlite3` (backed up first: `db_backups/task6_group_d_repeater_baseline.sqlite3`,
  SHA256 `bde91d0a91caec058b229ff7a92be008df5cbc555af33875be817cff1e0e614e`). All fixtures + the dev
  server + the throwaway `/etc/hosts` entry were torn down afterward; the dev DB was restored from
  that same backup file and the restore verified byte-for-byte via the same SHA256 (matching the
  hash already on record from the prior session's `task5_c2_5_continuation_baseline.sqlite3`,
  confirming no drift since that checkpoint).

### Not yet done in Group D

- `story_rail` — needs a media-form/model rework (the legacy `storefront_section_media_form`
  hardcodes desktop/mobile image fields but `StoryRailItem` has one `image` field), not just a
  settings schema. Not started.

## Group E (product_listing, collection_header, collection_products) — certification only

Per the plan's own disposition, these three are context-aware page sections (route context, not a
merchant-facing selector, is the authority) — certification-tests only, no code change expected.
Investigated and confirmed already correct as-is:

- Task 3D/3E (an earlier Phase-4 task) already closed the two real defects that existed for this
  group (`task3_non_home_page_appearance.md`: 3D — Collection Index/Detail boundary; 3E — Listing/
  Search HTMX fragment `card_settings` propagation gap). The `family_certification_matrix.md` rows
  for these three families still read "PENDING Task 3D/3E" only because the matrix itself was never
  updated after those fixes landed — the underlying code has been correct since Task 3.
- Existing test coverage already certifies the full route-context contract end to end:
  `ProductListingContextAwareSectionTests`/`CollectionContextAwareSectionsTests`
  (`test_render_service.py` — context threading, fail-safe-without-collection, exact parity with
  the domain view's own query objects) and `ProductListingContextAwareSectionPreviewTests`/
  `CollectionContextAwareSectionsPreviewTests` (`test_views.py` — real rendered Preview HTML on
  both listing/search tabs and the collection page, plus the page-type exclusivity guards). Ran
  targeted: 15/15 GREEN.
  `CollectionIndexBoundaryTests`/`HtmxFragmentCardSettingsPropagationTests`
  (`apps/catalog/tests/test_collection_public_views.py` /
  `apps/catalog/tests/test_u5_listing_filter_search.py` — the Task 3D/3E fixes themselves) plus
  `test_g22_preview_media_render_consistency`'s wrapper-consistency suite: 26/26 GREEN. 41/41 total.
- No production code changed for Group E. `family_certification_matrix.md` updated to CERTIFIED.

## Group F (hero, product_view, card, badge — global Store-Appearance families) — reconciliation

Per the plan (Ruling J): write/effective-state reconciliation only, no new merchant-facing selector
UI. Investigated each family's actual write/read reconciliation contract:

- **`hero`/`product_view`** already have a full write-path reconciliation, built generically in an
  earlier phase (Phase 1 Task 6 — `docs/qa_evidence/storefront_appearance_convergence/phase1/task6_explicit_local_variant.md`):
  any section with a registered `variant_setting_key` (which covers both `hero_banner.hero_style`
  for the `hero` family and `product_section.display_mode` for the `product_view` family) stamps
  `appearance_overrides.variant_explicit=True` on a genuine local variant edit (R4 or legacy), and
  the renderer honors that marker over a conflicting Store Appearance manifest selection — exactly
  the `apply_header_variant`-style single-write-authority-with-local-override-precedence contract.
  This was already fully built and tested generically; Task 6 Group F's job for these two families
  is certification that the contract holds specifically named for `hero`/`product_view`, done via
  a new test file exercising the real R4 mutation HTTP endpoint end to end (not just direct service
  calls) — see below.
- **`card`/`badge`** have NO local write path anywhere in the codebase — confirmed by exhaustive
  search: no `SettingsSchema` field, no legacy section-settings form field, for `card.card_style`
  or `card.badge_treatment` on any section. The only place a local `card.card_style` value ever
  originates is a Ready Template's own authored `PresetSectionEntry.settings.card` — and every
  Ready Template in the live production registry (`layout_preset_registry.list_ready_templates()`)
  either sets that local value equal to its own declared `card` family selection, or leaves its
  shared non-Home boilerplate sections (`product_listing`/`collection_products`/`related_products`
  — the identical composition reused by `_u10_standard_non_home_pages()` across every recipe) at
  the inert `"standard"` value specifically so the Store Appearance manifest is free to be the
  single overlay authority for them. Verified directly, not by inspection alone: a new test
  (`ReadyTemplateCardFamilyConsistencyTests`) applies every registered Ready Template with a
  non-default `card` selection and asserts the effective render-time `card_style` on each of its
  shared boilerplate sections equals that template's own declared family value — GREEN across the
  entire live registry. This confirms the existing unconditional render-time overlay
  (`card_settings_for`/`badge_settings_for` in `storefront_appearance/rendering.py`, already wired
  into `render_service._build_items_from_sections`) is the correct, sole write/effective-state
  authority for these two families — not a defect, and nothing to change.
- New certification test file:
  `apps/storefront_builder/tests/test_phase4_task6_group_f_reconciliation.py` — 10 tests: explicit-
  local-override-wins for `hero` and `product_view` (through the real R4 HTTP mutation endpoint,
  named specifically for each family, not just the generic variant-key mechanism); manifest-is-
  sole-authority + safe-default-restores-local-value for `card` and `badge`; and the full-registry
  Ready Template consistency check. All GREEN; no production code changed.
- `family_certification_matrix.md` updated: all four TEMPORARY-ADAPTER rows moved from PENDING to
  CERTIFIED.

## Remaining Task 6 work (not started)

- `story_rail`'s media-form/model rework (Group D) — the one still-open item from the earlier
  Group D checkpoint.
- Task 4-harness browser certification has not yet been run against any family from this task (the
  "Browser cert" column in `family_certification_matrix.md` stays "no" for all of them); this
  document's browser proof above is a targeted, hand-driven verification of the new repeater field
  type specifically, not a Task-4-harness run. Scheduled once per the plan's Batch 3 (Task-6 final
  gate), after `story_rail` lands.
- One final Task-6 independent review (Batch 3), after the above.
