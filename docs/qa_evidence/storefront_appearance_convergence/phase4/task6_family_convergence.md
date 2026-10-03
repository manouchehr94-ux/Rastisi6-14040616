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
- **`badge`** genuinely has NO local write path anywhere in the codebase — confirmed by exhaustive
  search: no `SettingsSchema` field, no legacy section-settings form field, for `card.badge_treatment`
  on any section. The Store Appearance manifest is unconditionally the sole write/effective-state
  authority for it.
- **`card` — a real gap, found by independent review, now fixed.** The first draft of this
  certification claimed `card_style` had no local write path either. **That claim was false** — an
  independent isolated-worktree reviewer (dispatched as this task's final-gate review) found the
  legacy card-settings form (`section_card_fields.html`'s `card_style` `<select>`, rendered for
  every `CARD_AWARE_SECTION_KEYS` section, parsed by `views._extract_card_raw`) IS a real
  merchant-facing write path, and the render-time overlay
  (`storefront_appearance/rendering.py.card_settings_for`, wired into
  `render_service._build_items_from_sections`) was unconditionally clobbering it whenever the
  Store's `card` family selection was non-default — with no way for the merchant's own saved
  choice to ever take effect (CRITICAL finding, empirically reproduced by the reviewer over real
  HTTP). **Fixed** by extending the exact `variant_explicit` precedent (Phase 1 Task 6) to this
  independent axis: a new `card_style_explicit` marker (`settings_schema.py`), stamped by
  `views.storefront_section_settings` only on a genuine legacy-form change (same "presence is not
  intent" rule as the existing variant marker — the form submits `card_style` on every POST), and
  honored by `render_service.py` exactly like the variant axis (an explicit local `card_style` now
  wins over a later, conflicting Store-level `card` family selection; an unmarked section still
  inherits the Store default). The independent review's SAME investigation also surfaced two
  further real defects while verifying this claim (both now fixed, see "Independent Task-6 review"
  below): `amazing_offers`'s dedicated legacy-form branch was silently wiping the whole `card` block
  on every Save (no `card_*` controls rendered there, but `_extract_card_raw` ran unconditionally),
  and the story-item media form's two identically-named `title` inputs discarded the merchant's
  typed title.

  `ReadyTemplateCardFamilyConsistencyTests` remains valid and GREEN: every registered Ready
  Template's shared non-Home boilerplate sections (`product_listing`/`collection_products`/
  `related_products`) are never locally overridden (no Ready Template authors an explicit local
  `card_style` disagreeing with its own declared family selection there), so the manifest overlay
  correctly remains their effective authority — this test just never exercised the
  merchant-authored-disagreement case the CRITICAL finding was about, which is why the gap wasn't
  caught before independent review.
- New certification test file:
  `apps/storefront_builder/tests/test_phase4_task6_group_f_reconciliation.py` — 12 tests: explicit-
  local-override-wins for `hero`, `product_view`, and (after the fix) `card` (through the real R4/
  legacy-form HTTP endpoints, named specifically for each family); the "presence is not intent"
  no-mark-on-resubmission case for `card_style`; manifest-is-sole-authority + safe-default-restores-
  local-value for `card`/`badge`; and the full-registry Ready Template consistency check. All
  GREEN.
- `family_certification_matrix.md` updated: all four TEMPORARY-ADAPTER rows CERTIFIED — `hero`/
  `product_view`/`badge` on the first pass, `card` only after the fix above.

## story_rail media-form/model convergence (Group D, closed)

Investigated per the plan's instruction ("do not invent a second media model or second media
authority"). Found the real, live defect the plan anticipated:

- `storefront_section_media_form` (the ONE shared create/edit view for `hero-slides`/`banners`/
  `story-items`, in `media_views.py`) hardcoded `obj.desktop_image`/`obj.mobile_image` — but
  `StoryRailItem` has exactly one image field (`image`), not that pair. **Creating** a new story
  item happened to not crash only by accident (`obj.pk` is falsy for a new instance, so
  `obj.pk and obj.desktop_image` short-circuited before the missing-attribute access). **Editing**
  any existing story item crashed immediately with `AttributeError: 'StoryRailItem' object has no
  attribute 'desktop_image'` — a real 500 reachable by any merchant clicking "ویرایش" on a story
  rail item from the Storefront Builder's own media list page (confirmed with a RED test against
  the pre-fix code before touching anything). The GET-render path never crashed only because
  Django's template variable resolution silently swallows `AttributeError` on dotted lookups — but
  the rendered form was still wrong, showing "تصویر دسکتاپ"/"تصویر موبایل" fields that mean nothing
  for a single-image model.
- Fixed by making the form (and the `_MEDIA_KINDS` config it reads) genuinely model-agnostic: each
  kind now declares its own ordered `file_fields` (a desktop/mobile pair for
  `HeroSlide`/`PromotionalBanner`; one single `image` field for `StoryRailItem`), and
  `storefront_section_media_form` loops over that instead of hardcoding the pair. `asset_fields`
  (file field → `MediaAsset` FK) is now the single mapping shared by create/edit AND delete —
  `story-items` had a separate `delete_asset_fields` key before (used only by delete, because
  create/edit for this kind never worked at all); that's gone now, replaced by one `asset_fields`
  entry (`{"image": "image_asset"}`) that both paths share, exactly the same canonical-authority
  pattern the rest of this Phase enforces elsewhere (one write path, not two). No second media
  model, no second media authority — this reuses the exact existing `MediaAsset`/
  `_sync_asset_references`/`delete_media_asset_if_unreferenced` machinery `HeroSlide`/
  `PromotionalBanner` already use, now genuinely shared rather than assumed-shared.
  `section_media_form.html` updated the same way (loops over `config.file_fields`, using the
  existing `getattribute` filter already in use for the kind-specific text field).
- New test coverage: `StoryRailItemCrudTests` in `test_media_views.py` (9 tests — list/add/add
  without image rejected/edit title-only [the exact defect]/edit replacing the image and creating
  a new `MediaAsset`/delete/toggle/wrong-kind-404/form renders the single `image` field, not
  desktop/mobile). `test_media_views` full module: 29/29 GREEN (including the pre-existing
  `HeroSlideCrudTests`/`BannerCrudTests`/`MediaCrossStoreIsolationTests`, confirming zero
  regression on the two working kinds). Broader targeted regression across every module touching
  `media_views.py`/media CRUD/lifecycle safety (`test_admin_v22_live_builder`,
  `test_g22_on_g21_integration`, `test_g2_1_media_editability_roundtrip`, `test_media_views`,
  `test_media_write_path`, `test_phase2_lifecycle_safety`): 132/132 GREEN. `manage.py check`:
  clean. `makemigrations --check --dry-run`: no changes detected (no model change was needed or
  made — this was purely a view/template bug, exactly matching the plan's "media-form/model
  rework", not a schema addition). No merchant-facing media UI *shape* changed for
  `hero-slides`/`banners` (identical fields, identical behavior) — only `story-items` gained a
  correct, working form where none existed before, so no browser verification beyond the above
  Django test coverage was required for this batch (deferred to the Task-4 harness pass in Batch 3
  per the plan, alongside every other Task-6 family).

## Task 6 final gate (Batch 3)

### Full apps.storefront_builder suite (run once, per the speed policy)

Two runs were needed: the first attempt's own environment tampering (renaming the session's
Python virtualenv directory WHILE the 47-minute test process was still running against it)
corrupted PIL/bs4/dns imports and Django's own template lookup mid-run, producing 154 spurious
errors that were confirmed (by traceback: `ImportError: cannot import name 'ImageFile' from
'PIL'` pointing at the renamed path) to be 100% self-inflicted, not real regressions — that run's
result was discarded in full, not partially trusted. A second, genuinely clean run (no filesystem
changes of any kind while the suite executed) produced:

```
Ran 2785 tests in 2815.845s
FAILED (failures=30, errors=2, skipped=4)
```

**Exact match to the frozen baseline (30 failures / 2 errors / 4 skips) — zero new regressions.**
Verified by name, not just count: the 32 failing signatures are the already-documented
`FullscreenEditorTests` pair, `test_header_footer_variant_labels_shown_for_updated_preset`, and
`test_validate_appearance_config_is_the_validator_boundary` (all three named in
`phase4/baseline.md` and `phase4/task4_qa_harness.md`), plus a family of `test_*_v2`
"frozen Ready Template contract" tests across `test_warm_boutique_lalerokh_v2`,
`test_dark_digital_luxury_v2`, `test_dense_marketplace_beraito_v2`,
`test_editorial_jewelry_saremi_v2`, `test_premium_leather_shokolati_v2` — a stable, internally
consistent pre-existing category (version-frozen assertions predating this task; none of Batch
1/2's changes touch any of these five preset modules or their underlying sections/fixtures).
`manage.py check`: clean. `makemigrations --check --dry-run`: no changes detected.
`git diff --check`: clean. `git status`: clean (matches `origin/feature/phase4-builder-legacy-convergence`).

### Browser certification — scope decision

Per the plan: "run the generalized Task-4 browser harness ONCE across the Task-6 family
certification matrix... do not run a separate full browser campaign per family if the
parameterized harness can certify them in one run." Investigated the actual harness
(`tools/storefront_builder_r4_qa/run.mjs`, ~2570 lines) before running anything: Task 4 only
generalized the Brand/Collection TILE-matrix helper (`phase3FamilyPublicMatrix`) into one shared
parameterized function — it built no scenario code at all for the other ~20 Task-6 families
(banners/sliders/story_rail/repeater fields/item_limit pickers/etc.), which have entirely
different, non-tile DOM shapes. Building real per-family browser assertions for all of them would
be substantial new engineering (comparable in size to Task 4 itself), not a "run it once"
verification step. Put to the Product Owner explicitly rather than either silently skipping
browser certification or unilaterally undertaking that much new scope inside this gate; decision:
run the harness's existing generic coverage as-is and record the per-family DOM-assertion gap
honestly rather than claim coverage that was never built.

**Run**: `qa_storefront_builder_r4 --store-slug akhlaghi --username task6_qa_owner
--browser-channel auto --phase3` (dev DB freshly migrated + a throwaway staff/owner QA user
created for this session, since the container's `db.sqlite3` started empty).

- **16/16 scenarios PASS**: the 13 generic R4 workflow scenarios (initial load, Hero
  basic/advanced typography, product add/reorder/auto-source/manual-picker, Brand manual picker,
  undo/redo, real stale-conflict, publish, public parity, Draft-only change, public-unchanged) +
  `final-instrumentation-assertions` + `final-screenshot-verification` + `phase3-brand-gate`
  (Brand 45/45 + Collection 36/36 variant checks, 0 real errors, `known_red_findings: []` —
  identical to the Task-4 evidence's own recorded counts).
- Console "errors" recorded (30) are exclusively the harness's own deliberate
  `qa-broken-nonexistent.png` broken-image fixtures (the documented broken-image-classification
  exemption) — not real defects; the runner's own pass/fail gate already accounts for this
  (`Passed: 16 Failed: 0`).
- DB restore SHA256 verified byte-for-byte match on both invocations (base run and `--phase3` run).
- **Known, explicitly recorded gap** (not silently passed as "certified"): no browser-level DOM
  assertions exist for the ~20 other Task-6 MIGRATE/TEMPORARY-ADAPTER families (their own
  settings-schema fields, repeater UI, item_limit pickers, card/badge family selectors, etc.) —
  those remain certified only at the Django-test level (documented per-family throughout this
  document and in `family_certification_matrix.md`'s own "Browser cert" column, which stays "no"
  for every one of them). Building that coverage is a separately-scoped follow-up, not silently
  claimed here.

### Independent Task-6 review

A fresh, isolated-worktree reviewer with no prior context reviewed the cumulative Task 6 diff
(`a31da39..f98930b` — Task 5's close through the end of Batch 2), read the plan's Task 6 section
and this evidence document, and scrutinized the two not-yet-independently-reviewed commits
(`e524a35`/Group E+F certification, `f98930b`/story_rail fix) the hardest, including empirical
HTTP-level reproduction of its findings against a real venv. Verdict on the first pass:

```
CRITICAL: 1
IMPORTANT: 2
MINOR: 2
```

- **CRITICAL (C1)** — the `card` family's "no local write path" claim was false; the render-time
  overlay was silently discarding a real merchant `card_style` choice. Fixed as described in the
  "Group F" section above.
- **IMPORTANT (I1)** — `amazing_offers`'s legacy-form Save silently wiped its entire `card` block
  (no `card_*` controls in that dedicated branch, but `_extract_card_raw` ran unconditionally,
  defaulting every absent field to off/`"standard"`) — the exact class of destructive-Save bug
  Finding 2 (Group D checkpoint) was meant to close, reintroduced by that same fix's own new
  branch. Fixed: `_extract_card_raw` is now preserve-safe (mirrors `_extract_background_raw`) —
  absence of every one of its ten POST keys means this form never had the card block, so the
  stored block survives untouched. Regression test:
  `test_views.NewSectionTypesSettingsFormTests.test_amazing_offers_settings_form_does_not_wipe_card_block`.
- **IMPORTANT (I2)** — the story-item media form (`f98930b`) rendered two `<input name="title">`
  elements (the generic title block plus the kind-specific text-field block, since `story-items`'
  own `text_field` IS `"title"`); a browser posts duplicate keys as a list, and Django's
  `QueryDict.get()` returns the last one, silently discarding whatever the merchant typed into the
  first box. Fixed: the generic title block is skipped when `config.text_field == "title"`.
  Regression tests: `test_media_views.StoryRailItemCrudTests.test_add_form_renders_title_input_exactly_once`
  / `test_add_story_item_title_is_actually_saved`.
- **MINOR (M1)** — the media list partial read `item.desktop_image_url` unconditionally, which
  `StoryRailItem` doesn't have (its own property is `image_url`); Django's template engine
  swallows the `AttributeError`, so story items showed no thumbnail at all. Fixed via a per-kind
  `thumb_field` config entry (`media_views.py`), used generically by the list template. Regression
  test: `test_media_views.StoryRailItemCrudTests.test_media_list_shows_story_item_thumbnail`.
- **MINOR (M2)** — dead imports/an unused helper and an over-broad docstring claim in the new
  Group F test file. Cleaned up; docstrings corrected to match the actual (now-fixed) contract.

**Fix verification** (per "rerun only affected verification unless the fix changes a cross-cutting
contract" — the C1 fix DOES change a cross-cutting contract, the card/badge overlay precedence, so
the full gate was re-run, not just the touched modules):
- Targeted: `test_phase4_task6_group_f_reconciliation` (12/12), `test_media_views` (56/56, includes
  the new story-item regression tests), `test_views.NewSectionTypesSettingsFormTests` (12/12),
  `test_views` full module (221 tests, 1 failure + 1 error — the two known pre-existing
  `FullscreenEditorTests` signatures, nothing else), `test_render_service` +
  `test_g22_preview_media_render_consistency` + `test_u10_ready_template_catalog` +
  `test_a8_ready_template_contracts` + `test_section_registry` (418/418, 1 pre-existing skip) — all
  GREEN.
- **Full `apps.storefront_builder` suite re-run once more** (the fix touches `render_service.py`'s
  per-section overlay loop, a cross-cutting path): 2791 tests (6 more than the pre-fix run — the
  new regression tests), 30 failures / 2 errors / 4 skips. Diffed the full by-name failure/error
  list against the pre-fix run byte-for-byte: **identical set, zero new regressions.**
- `manage.py check` / `makemigrations --check --dry-run` / `git diff --check`: all clean, both
  before and after the fix.

No second review round was required for the FIRST reviewer's own findings — every finding was
concrete, reproducible, and fixed; no new finding surfaced during that fix verification. A SECOND,
separate independent reviewer was still dispatched afterward per the closure requirement's own
"re-review the final state" step (see below) — its findings are about the browser-harness commit
that came after the first reviewer's pass, not a reopening of the first reviewer's own findings.

### Second independent review (post browser-harness-extension commit `d8489c4`)

A second fresh, isolated-worktree reviewer (no prior context) reviewed `d8489c4` (the browser
harness extension giving 6 more Task-6 families genuine coverage) against two questions: (a) do
the FIRST reviewer's four fixes still hold, and (b) is the new harness commit itself sound. Verdict:

```
CRITICAL: 1
IMPORTANT: 2
MINOR: 3
```

- **CRITICAL (C1)** — the `card_style_explicit`/`variant_explicit` markers were durable across
  exactly ONE save (the first reviewer's own fix), then silently dropped again by the very next
  UNRELATED save: no `CARD_AWARE_SECTION_KEYS` member (nor `product_section`) was actually in
  `APPEARANCE_OVERRIDE_AWARE_SECTION_KEYS`, so `validate_settings` kept discarding the whole
  `appearance_overrides` block for those section types. Fixed by unioning
  `APPEARANCE_OVERRIDE_AWARE_SECTION_KEYS` with `CARD_AWARE_SECTION_KEYS` and generalizing the
  marker-preservation logic (`section_registry.py`'s `_with_appearance_overrides`) to a trusted-key
  tuple (`_TRUSTED_APPEARANCE_OVERRIDE_MARKER_KEYS`) instead of a single hardcoded key, plus
  widening the legacy form's `appearance_overrides` carry-forward (`views.py`) beyond
  `brand_carousel` to every section in the (now-widened) allowlist.
- **IMPORTANT (I1)** — same root cause, specifically breaking `product_section`'s `variant_explicit`
  marker — already fixed by the same C1 change (`product_section` is a member of
  `CARD_AWARE_SECTION_KEYS`).
- **IMPORTANT (I2)** — `story_rail`/`single_banner`/`multi_banner`'s browser-cert fixture placed
  sections with no backing media row, so their templates rendered nothing and the harness's
  visibility check passed on the empty-placeholder wrapper alone, not the family's own markup.
  Fixed: the fixture now creates a real `StoryRailItem`/`PromotionalBanner` row per section, and
  the harness asserts real family-specific DOM (`.story-item .story-label`, `.promo-dark h3`,
  `.promo-grid--promo-4`).
- **MINOR (M1)** — corrected a docstring that incorrectly claimed `rich_text` shares `image_text`'s
  browser-coverage mechanism (a shared validator SHAPE is not a shared Inspector CONTROL type —
  `rich_text` uses a genuinely different CKEditor5 widget); now recorded as a deliberate,
  unexercised coverage gap instead.
- **MINOR (M2)** — the harness threaded 6 fixture section ids through the manifest but never used
  them (every scenario re-discovered its section by CSS selector). Fixed: `run.mjs` now opens each
  Task-6-family section by its known fixture id (`openSectionById`), not by re-deriving it.
- **MINOR (M3)** — the new browser scenario ran after the one check that asserts zero unexpected
  console/page/network errors for the whole run, so an error it caused would never be caught. Fixed
  with a before/after instrumentation snapshot local to the scenario.

**Fix verification** (targeted + one full-suite re-run, matching the same "cross-cutting contract"
policy as the first round):
- Targeted: `test_phase4_task6_group_f_reconciliation` (15/15, including 3 new regression tests
  proving both markers survive an UNRELATED resave through both the legacy form and the R4
  mutation endpoint), `manage.py check` / `makemigrations --check --dry-run` / `git diff --check`:
  all clean.
- **Full `apps.storefront_builder` suite re-run once** (the fix touches the same cross-cutting
  `section_registry.py` validator wrapper every schema-enabled section goes through): 2807 tests
  (16 more than the prior 2791 — this session's new Task-7 Batch 1/2 tests, run for the first
  time), 30 failures / 2 errors / 4 skips — **exactly the same three counts as the frozen
  baseline**, despite ~16 more tests running and passing. Spot-verified two of the visible
  failures (`FullscreenEditorTests` pair, `test_validate_appearance_config_is_the_validator_boundary`)
  reproduce byte-for-byte identically on `git stash` (i.e. without any of this session's changes),
  confirming they are pre-existing and unrelated, not something this fix or the new Task-7 work
  introduced.

#### Third-party re-verification (re-review after the C1/I1/I2/M1/M2/M3 fix)

A THIRD independent reviewer (isolated worktree, no prior context) was dispatched to verify the six
findings above were genuinely fixed and to check the fix itself for new defects, per the closure
requirement's "re-review the final state" step. It confirmed C1/I1/I2/M1/M2/M3 all genuinely fixed
— including by deliberately REVERTING each half of the C1/I1 fix in isolation and re-running the
three new regression tests, confirming each one fails for exactly the right reason when its
corresponding code change is reverted (not vacuous), and by re-deriving the render-time card/badge
precedence and the "no third missed write-path" search independently. It found the M3 fix itself
introduced one new IMPORTANT-severity defect plus three MINOR ones:

```
CRITICAL: 0
IMPORTANT: 1
MINOR: 3
```

- **IMPORTANT** — the new instrumentation guard's `http_error_responses` snapshot was missing the
  same `isExpectedBrokenImageNoise`/`isExpectedStale409Response` filters its sibling arrays
  (console/request errors) already applied, so the Collection gate's own deliberately-broken-image
  collection tile (placed on Home, alongside this same gate, by an earlier Task-5 fixture) would
  make every page reload below record a "new" 404 and fail the gate spuriously — the opposite of
  the fix's own intent. Fixed: `http_error_responses` now filtered the same way, both before and
  after.
- **MINOR** — the guard's failure messages sliced the raw (unfiltered) arrays at filtered-count
  offsets, misaligning the diagnostic window. Fixed: the guard now snapshots the FILTERED arrays
  themselves (not just their lengths) before and after, and diffs those directly.
- **MINOR** — `_TRUSTED_APPEARANCE_OVERRIDE_MARKER_KEYS` was defined between two `from .x import y`
  statements (a stray module-level constant mid-import-block); moved below the imports.
- **MINOR** — the `#:` doc-comment explaining why `product_view`/`card` families joined the
  allowlist was placed AFTER the `APPEARANCE_OVERRIDE_AWARE_SECTION_KEYS = frozenset(...)`
  statement it was meant to document (Sphinx `#:` comments document the FOLLOWING attribute, so it
  would have been attributed to the next function instead); moved above the assignment, merged with
  the existing docstring-style comment already there, and one more line added documenting the
  `preserve_unmanaged=True` dependency the reviewer flagged as load-bearing-but-undocumented.

Also raised, as an observation rather than a code-level finding requiring a fix in this batch: now
that the explicit-override markers are durable (the whole point of the C1 fix), there is no
merchant-facing way to CLEAR one once set — `reset_section_setting_to_baseline(draft, section,
"card")` restores the card block's values to the Ready Template baseline but leaves
`card_style_explicit` (or `variant_explicit`) set, so the section stays permanently opted out of
future Store Appearance selections for that axis. This is pre-existing behavior (identical for
`variant_explicit` since Phase 1), not introduced by any commit in this task — the C1 fix only made
it durable enough to actually matter. Recorded here as a known product-level question for a future
task, not an in-scope Task 6 defect: whether resetting a component should also clear its own
explicit-override marker is a merchant-experience decision, not a bug fix.

**Re-verification after this third round's fixes**: `test_phase4_task6_group_f_reconciliation`
(15/15), `manage.py check` / `makemigrations --check --dry-run` / `git diff --check`: all clean.
`run.mjs`/`section_registry.py` both `node --check`/`py_compile` clean. The harness itself was not
re-run in this round (no browser/dev-server available in this environment) — the fix is verified
by static trace of the exact failure chain (the Collection gate's broken-image fixture -> HTTP 404
-> recorded into the SAME `result.http_error_responses` array the Task-6 gate's guard reads) and by
confirming the fixed filter predicates are byte-for-byte identical to `finalInstrumentationAssertions`'s
own, already-proven-correct predicates.

No further review round was required: CRITICAL 0 / IMPORTANT 0 after this round's fixes.
