# Phase 4 family certification matrix

Tracks Phase-4 certification state for every section family and every global non-section family.
Updated by Task 6 (product-facing families) and Task 5 (CSS completeness). No row may remain
"unknown" at the Phase-4 final gate (Task 10).

**Pre-Task-10 FINAL remediation note (Gap 2 — CLOSED)**: the 15 `MIGRATE`
rows a previous session left `NOT YET CERTIFIED` (real Playwright browser-
automation work, deliberately not a rubber-stamp) are now all `CERTIFIED`,
via one new data/config-driven consolidated scenario
(`phase3-final-remediation-family-gate` in
`tools/storefront_builder_r4_qa/run.mjs`) reusing the EXISTING generalized
Task-4 harness mechanism (`task6FamilyFieldEditScenario`, unchanged, plus
two new small shared functions for the repeater and rich_text field types —
never 15 bespoke harnesses). Real executed evidence, run from a genuinely
fresh/pristine local DB in this session (`python manage.py migrate` +
the documented `phase3_qa_owner`/`akhlaghi` bootstrap), not assumed from
prior sessions' state.

While building and iterating this gate (`R4_QA_ONLY_SCENARIO`-filtered runs
per the browser-speed rule, then the complete harness once), two genuine
PRE-EXISTING defects were found and fixed as part of making the mechanism
itself trustworthy for this gate (neither is a Gap-1/Gap-2 family's own
fault):

1. `task6FamilyFieldEditScenario` used to open a section by an id the
   Python fixture captured ONCE before the browser session started
   (`openSectionById`). When this gate runs after scenario 10 (Publish) +
   12 (which clones a new Draft with new Section PKs —
   `layout_service._clone_version_content`), that id no longer belongs to
   the active Draft and the Inspector never opens. Fixed by switching to
   `openSectionViaPreview(sectionKey)` (the same dynamic-discovery
   mechanism the Brand/Collection gates already used) — a real fix, not a
   weakened assertion, and it benefits the existing 6-family gate too.
2. `waitSaved()` polls the `#r4SaveState` DOM text, whose resting and
   terminal values are identical text — in a dense back-to-back loop (this
   gate's own 11-family scalar edit sequence) that first poll can resolve
   on STALE text from the PREVIOUS edit, racing the current one's own save.
   Fixed by polling the actual `mutation_posts` array directly
   (`waitForMutationPostCount`) before `waitSaved()`.

**Pre-Task-10 CORRECTIVE closure note (this session)** — a prior session's
PASS report for the above was rejected: several of the 15 certifications
above were persistence-only (never proved the family's actual REAL render
contract), `multi_banner`/scenario 14's failures were left "documented,
not fixed", and the legacy editor shell still physically contained every
duplicate merchant-editing surface. All of that is now closed, with real
executed evidence, not a rubber stamp:

- **Real render proof, not persistence-only**: `hero_banner`/`image_slider`
  now back a real MediaAsset-linked `HeroSlide`; `discounted_products`/
  `amazing_offers` share one real discounted `Product`; `blog_posts` gets a
  real global `BlogPost`; `quick_links` gets a real `Menu`+`MenuItem`;
  `video_section` uses a real YouTube URL asserting a real `/embed/` iframe
  `src`; `newest_products`/`best_sellers`/`promo_cards` assert real `.pcard`/
  category DOM content. `phase3FinalRemediationFamilyGate()` also now runs
  ONE consolidated Publish → Public-reflects-it → Draft-only-edit →
  Public-remains-unchanged cycle (representative family: `quick_links`,
  the one named as the concrete rubber-stamp risk) plus a mobile-viewport
  no-overflow check on the published Home page.
- **`quick_links.menu_id` is now a genuine R4 merchant-facing field** — a
  new `menu_picker` SettingsField/Inspector control type (never a second
  Menu authority; the same Store-scoped `Menu.objects.filter(store=...,
  is_active=True)` query the legacy form's own `all_menus` context helper
  already used), closing the exact gap flagged as unacceptable to leave
  open. See `settings_schema.py`/`section_registry.py`/`r4_views.py`/
  `settings_field.html`, and `QuickLinksMenuPickerR4Tests` (Django-level:
  tenant-scoped menu choices, mutation persists, clearing persists `None`).
- **`multi_banner` and scenario 14's `brand_carousel` — now actually
  fixed**, not left documented: `multi_banner`'s QA fixture media now goes
  through the same canonical MediaAsset path (`_save_with_media_asset`,
  mirroring `media_views.py`'s real production upload flow) so it survives
  a Publish→Draft clone; scenario 14's Preview locator is now scoped to the
  specific `data-section-id` it opened, not the ambiguous bare
  `[data-section-key="brand_carousel"]` (which resolves to 3+ elements once
  `phase3-brand-gate`'s own 3-variant fixture is also on Home).
- **Two further genuine PRODUCTION bugs found and fixed** while driving the
  complete harness to green — not QA-fixture issues:
  - `story_rail` (already `CERTIFIED` from Task 6, apparently regressed
    silently since — this is the first time its real fixture was exercised
    against actual rendered output in the same run as the rest of the
    harness): `responsive_section_wrapper.html`'s single `{% include
    item.template_name with ... %}` whitelist — the one shared render path
    for BOTH editor Preview and the real public storefront — never forwarded
    `story_items` to `story_rail.html`. Every real `StoryRailItem` has been
    silently unrenderable, in Preview and on Public, until this session's
    fix (`story_items=item.context.story_items` added to the whitelist).
  - `best_sellers` deliberately ranks from real `OrderItem` history
    (`best_seller_service`, never `Product.sold_count` — see its own
    docstring), so "reuse existing catalog demo data" (correct for
    `newest_products`) was genuinely insufficient. The final-remediation
    fixture now creates one real `Order`+`OrderItem` against the real
    discounted `Product`.
- **Second legacy retirement pass — physically closed, not deferred**:
  `editor.html`'s full Alpine/R3-modal composition-settings-appearance body
  now renders only for a Store explicitly pinned back to the legacy editor
  (`r4_editor_enabled=False`, the documented rollback safety valve); the
  live R4 default renders a minimal compatibility surface exposing only
  the two capabilities with no R4 equivalent (restore/history browsing,
  industry-vertical layout preset). See `legacy_disposition.md` for the
  full row-by-row disposition.
- **Complete R4 `--phase3` browser harness — 20/20 PASS**, run from this
  corrective session's own local state, SQLite pre/post-run restore
  verified byte-identical. No unexpected FAIL scenarios; no stale FAILURE
  screenshots left in `docs/qa_evidence/storefront_builder/r4/phase1/`
  (all 13 numbered screenshots + the 2 new final-remediation/task7 ones are
  from this clean run).

Columns: disposition (from the plan's §0 recount) · CSS completeness (Task 5) · SettingsSchema ·
ResourceSource · browser certification (Task 4 harness) · status.

## Section families (36)

| key | disposition | CSS complete | SettingsSchema | ResourceSource | Browser cert | Status |
|---|---|---|---|---|---|---|
| `hero_banner` | MIGRATE | **yes (Task 5 Group A)** | yes (pre-existing) | no | **yes (Pre-Task-10 CORRECTIVE closure — `hero_style` choice edit against a real MediaAsset-backed HeroSlide; real `<h1>` DOM assertion in Preview scoped to whichever real structural variant renders (`overlay`/`split`/...), plus Publish→Public→Draft-only-unchanged proof)** | CERTIFIED |
| `fashion_lifestyle_hero` | HOME-ONLY | n/a (Home-only) | no | no | no | NO ACTION REQUIRED |
| `image_slider` | MIGRATE | **yes (Task 5 Group A)** | **yes (Task 6 Group A)** | no | **yes (Pre-Task-10 CORRECTIVE closure — `interval_ms` (advanced tab) edit against a real MediaAsset-backed HeroSlide; real `<h1>` DOM assertion in Preview)** | CERTIFIED |
| `single_banner` | MIGRATE | **yes (Task 5 Group B)** | **no — explicit FIXED/STATIC disposition (Task 6 Group C): no settings-driven field at all** | no | **yes (Task 6 A1 — presence/rendering; Task 7 Batch 3 — R4 Inspector now links to its media management screen instead of 404ing, since it has no schema)** | CERTIFIED |
| `multi_banner` | MIGRATE | **yes (Task 5 Group B)** | **yes (Task 6 Group C — real closed-enum validator + schema, replacing `_passthrough_dict`)** | no | **yes (Task 6 A1 — `layout_variant` edit + real `.promo-grid--promo-4` DOM assertion, backed by real fixture banners; Pre-Task-10 CORRECTIVE closure fixed the QA fixture's media creation to the canonical MediaAsset path so it survives a Publish→Draft clone — real bug in the fixture, not the family's own contract)** | CERTIFIED |
| `category_grid` | MIGRATE | **yes (Task 5 Group C, all 11 display_modes)** | **yes (Task 6 Group C)** | **yes (Task 6 — category kind wired into the shared Resource Picker)** | **yes (Task 6 A1 — `item_limit` edit, persisted-value proof)** | CERTIFIED |
| `featured_products` | MARKETING-ALIAS | n/a | no | no | no | DOCUMENTED AS ALIAS |
| `newest_products` | MIGRATE | already safe | **yes (Task 6 Group B — item_limit)** | no | **yes (Pre-Task-10 CORRECTIVE closure — item_limit edit; real `.pcard` DOM assertion in Preview against real catalog demo data)** | CERTIFIED |
| `best_sellers` | MIGRATE | already safe | **yes (Task 6 Group B — item_limit)** | no | **yes (Pre-Task-10 CORRECTIVE closure — item_limit edit; real `.pcard` DOM assertion against a real `Order`+`OrderItem` ranked live by `best_seller_service` — NOT `Product.sold_count`, which has no writer; "reuse existing catalog demo data" was genuinely insufficient here and was corrected)** | CERTIFIED |
| `discounted_products` | MIGRATE | already safe | **yes (Task 6 Group B — item_limit)** | no | **yes (Pre-Task-10 CORRECTIVE closure — item_limit edit; real discounted-Product name asserted in Preview text)** | CERTIFIED |
| `amazing_offers` | MIGRATE | **yes (Task 5 Group A)** | **yes (Task 6 Group D)** | no | **yes (Pre-Task-10 CORRECTIVE closure — item_limit edit; real discounted-Product name asserted in Preview text)** | CERTIFIED |
| `brand_carousel` | CERTIFY-ONLY | **yes (`beauty_tabs` gap closed, Task 5)** | yes | yes | **yes (Phase-3, 45/45)** | CERTIFIED (Phase 3) — regression sentinel |
| `collection_tiles` | CERTIFY-ONLY | already safe | yes | yes | **yes (Phase-3, 36/36)** | CERTIFIED (Phase 3) — regression sentinel |
| `promo_cards` | MIGRATE | **yes (Task 5 Group D — reuses Group C1 CSS)** | **yes (Task 6 Group B — item_limit)** | no | **yes (Pre-Task-10 CORRECTIVE closure — item_limit edit; real demo Category name asserted in Preview text)** | CERTIFIED |
| `rich_text` | MIGRATE | already safe (inline) | yes (legacy) | no | **yes (Pre-Task-10 final remediation, Gap 2 — the CKEditor5/`rich_text` field type's own dedicated scenario: real content typed into the live editor, persisted through the hidden source textarea, reflected verbatim in Preview)** | CERTIFIED |
| `image_text` | MIGRATE | **yes (Task 5 Group D)** | **yes (Task 6 Group C)** | no | **yes (Task 6 A1 — `image_position` edit + real `row-reverse` CSS assertion)** | CERTIFIED |
| `blog_posts` | MIGRATE | **yes (Task 5 Group D)** | **yes (Task 6 Group C)** | no | **yes (Pre-Task-10 CORRECTIVE closure — item_limit (advanced tab) edit against a real, global `BlogPost` row; real `.blog-card h4` title DOM assertion in Preview)** | CERTIFIED |
| `product_section` | MIGRATE | **yes (Task 5 Group A)** | yes | yes | **yes (Pre-Task-10 final remediation, Gap 2 — `title` edit + real `<h2>` DOM assertion in Preview, same pattern as `newsletter`)** | CERTIFIED |
| `catalog_product_wall` | HOME-ONLY | n/a | no | no | no | NO ACTION REQUIRED |
| `trust_features` | MIGRATE | **yes (Task 5 Group E)** | **yes (Task 6 Group D — first user of the new `repeater` field type; browser-verified end to end)** | no | **yes (Pre-Task-10 final remediation, Gap 2 — the shared repeater-family scenario: add row, fill subfields, real `.feat b` DOM assertion in Preview)** | CERTIFIED |
| `quick_links` | MIGRATE | already safe | **yes (Task 6 Group D `title`; Pre-Task-10 CORRECTIVE closure adds `menu_id` via a new `menu_picker` field type — never a second Menu authority, Store-scoped exactly like the legacy form's `all_menus` helper)** | no | **yes (Pre-Task-10 CORRECTIVE closure — `menu_id` selection against a real `Menu`+`MenuItem`; real resolved-MenuItem `<a>` text asserted in Preview; Publish→Public reflects it→Draft-only-clear→Public unchanged proof, this family is the corrective pass's representative case)** | CERTIFIED |
| `faq` | MIGRATE | **yes (Task 5 Group E)** | **yes (Task 6 Group D — `repeater` field type; browser-verified end to end)** | no | **yes (Pre-Task-10 final remediation, Gap 2 — the shared repeater-family scenario: add row, fill subfields, real `.faq-item summary` DOM assertion in Preview)** | CERTIFIED |
| `testimonials` | MIGRATE | **yes (Task 5 Group E)** | **yes (Task 6 Group D — `repeater` field type)** | no | **yes (Pre-Task-10 final remediation, Gap 2 — the shared repeater-family scenario: add row, fill subfields, real `.testimonial-card .quote` DOM assertion in Preview)** | CERTIFIED |
| `video_section` | MIGRATE | **yes (Task 5 Group E)** | **yes (Task 6 Group D)** | no | **yes (Pre-Task-10 CORRECTIVE closure — `video_url` edit with a REAL YouTube URL (not avoided); real `/embed/` iframe `src` asserted in Preview — `previewFrame()`'s no-nested-iframe invariant now explicitly allowlists real video-embed src patterns rather than dodging a real provider)** | CERTIFIED |
| `story_rail` | MIGRATE | already safe | **n/a — no section-level settings to schematize (media-only family, `_passthrough_dict`/`_empty_defaults`); real gap was the media-form/model rework (Task 6), now closed** | no | **yes (Task 6 A1 origin, real `StoryRailItem` fixture + `.story-item .story-label` text assertion; Task 7 Batch 3 — R4 Inspector links to its media management screen)** | **CERTIFIED — Pre-Task-10 CORRECTIVE closure found this had silently regressed since Task 6: `responsive_section_wrapper.html`'s shared `{% include item.template_name with ... %}` (the one render path for BOTH editor Preview and the real public storefront) never forwarded `story_items` to `story_rail.html` — every real StoryRailItem was unrenderable, in Preview and on Public, until fixed this session (real bug, not a QA-fixture issue). Reproduced live via the complete browser harness, fixed, and 20/20 harness re-verified green** |
| `newsletter` | MIGRATE | already safe (inline) | **yes (Task 6 Group D)** | no | **yes (Task 6 A1 — `title` edit + real `<h2>` text assertion)** | CERTIFIED |
| `announcement_bar` | LEGACY-RETIRE | n/a | no | no | no | RETIREMENT CANDIDATE (see legacy_disposition.md) |
| `product_main` | CONTEXT-AWARE-DOMAIN-OWNED | n/a | no | no | no | SAFE BY CONSTRUCTION |
| `product_description` | CONTEXT-AWARE-DOMAIN-OWNED | n/a | no | no | no | SAFE BY CONSTRUCTION |
| `product_video` | CONTEXT-AWARE-DOMAIN-OWNED | n/a | no | no | no | SAFE BY CONSTRUCTION |
| `related_products` | CONTEXT-AWARE-DOMAIN-OWNED | n/a | no | no | no | SAFE BY CONSTRUCTION |
| `product_listing` | CONTEXT-AWARE-DOMAIN-OWNED | n/a | no | no | no | **CERTIFIED (Task 6 Group E — route-context contract, Task 3E fragment fix confirmed closed; 15/15 targeted GREEN)** |
| `collection_header` | CONTEXT-AWARE-DOMAIN-OWNED | n/a | no | no | no | **CERTIFIED (Task 6 Group E — route-context contract, Task 3D boundary confirmed closed; 15/15 targeted GREEN)** |
| `collection_products` | CONTEXT-AWARE-DOMAIN-OWNED | n/a | no | no | no | **CERTIFIED (Task 6 Group E — route-context contract, Task 3D boundary confirmed closed; 15/15 targeted GREEN)** |
| `cart_items` | CONTEXT-AWARE-DOMAIN-OWNED | n/a | no | no | no | SAFE BY CONSTRUCTION |
| `cart_summary` | CONTEXT-AWARE-DOMAIN-OWNED | n/a | no | no | no | SAFE BY CONSTRUCTION |

## Global non-section families

| Family | Disposition | Status |
|---|---|---|
| Header | CERTIFY-ONLY | Canonical, converged — regression sentinel only |
| Footer | CERTIFY-ONLY | Canonical, converged — regression sentinel only |
| Mobile Bottom Navigation | CERTIFY-ONLY | Canonical, converged — regression sentinel only |
| Motion | CERTIFY-ONLY | Canonical, converged — regression sentinel only |
| `hero` (Store Appearance family) | TEMPORARY-ADAPTER | **CERTIFIED (Task 6 Group F — explicit-local-override-wins write/effective reconciliation confirmed via the real R4 mutation endpoint; no new selector UI, Ruling J)** |
| `product_view` | TEMPORARY-ADAPTER | **CERTIFIED (Task 6 Group F — same explicit-local-override contract confirmed for `product_section.display_mode`)** |
| `card` | TEMPORARY-ADAPTER | **CERTIFIED (Task 6 Group F — independent review found the first certification's "no local write path" claim false: the legacy card-settings form is a real write path that the manifest overlay was silently clobbering. Fixed with a `card_style_explicit` marker mirroring `variant_explicit`; explicit local wins, unmarked sections still inherit the Store default; full-suite re-verified with zero new regressions)** |
| `badge` | TEMPORARY-ADAPTER | **CERTIFIED (Task 6 Group F — `badge_treatment` genuinely has no local write path anywhere; manifest is unconditionally the sole write authority)** |
