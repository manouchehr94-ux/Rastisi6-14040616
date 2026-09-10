# Phase 4 family certification matrix

Tracks Phase-4 certification state for every section family and every global non-section family.
Updated by Task 6 (product-facing families) and Task 5 (CSS completeness). No row may remain
"unknown" at the Phase-4 final gate (Task 10).

**Pre-Task-10 remediation note** (see
`pre_task10_r4_cutover.md`'s "Step 1D" section for the full record):
re-read fresh this session. The 15 `MIGRATE` rows still marked `NOT YET
CERTIFIED` each have `SettingsSchema`/CSS-completeness already closed
(Task 5/6) — the only outstanding item for each is a dedicated Task-4
QA-harness browser scenario, which this session did not write. This is a
justified, explicitly-tracked remaining gap (real Playwright browser-
automation work, not a rubber-stamp), not an unjustified or stale row —
none of these 15 are miscategorized as MIGRATE when they should be
media-only/fixed/context-owned/domain-owned.

Columns: disposition (from the plan's §0 recount) · CSS completeness (Task 5) · SettingsSchema ·
ResourceSource · browser certification (Task 4 harness) · status.

## Section families (36)

| key | disposition | CSS complete | SettingsSchema | ResourceSource | Browser cert | Status |
|---|---|---|---|---|---|---|
| `hero_banner` | MIGRATE | **yes (Task 5 Group A)** | yes (pre-existing) | no | no | NOT YET CERTIFIED |
| `fashion_lifestyle_hero` | HOME-ONLY | n/a (Home-only) | no | no | no | NO ACTION REQUIRED |
| `image_slider` | MIGRATE | **yes (Task 5 Group A)** | **yes (Task 6 Group A)** | no | no | NOT YET CERTIFIED |
| `single_banner` | MIGRATE | **yes (Task 5 Group B)** | **no — explicit FIXED/STATIC disposition (Task 6 Group C): no settings-driven field at all** | no | **yes (Task 6 A1 — presence/rendering; Task 7 Batch 3 — R4 Inspector now links to its media management screen instead of 404ing, since it has no schema)** | CERTIFIED |
| `multi_banner` | MIGRATE | **yes (Task 5 Group B)** | **yes (Task 6 Group C — real closed-enum validator + schema, replacing `_passthrough_dict`)** | no | **yes (Task 6 A1 — `layout_variant` edit + real `.promo-grid--promo-4` DOM assertion, backed by real fixture banners)** | CERTIFIED |
| `category_grid` | MIGRATE | **yes (Task 5 Group C, all 11 display_modes)** | **yes (Task 6 Group C)** | **yes (Task 6 — category kind wired into the shared Resource Picker)** | **yes (Task 6 A1 — `item_limit` edit, persisted-value proof)** | CERTIFIED |
| `featured_products` | MARKETING-ALIAS | n/a | no | no | no | DOCUMENTED AS ALIAS |
| `newest_products` | MIGRATE | already safe | **yes (Task 6 Group B — item_limit)** | no | no | NOT YET CERTIFIED |
| `best_sellers` | MIGRATE | already safe | **yes (Task 6 Group B — item_limit)** | no | no | NOT YET CERTIFIED |
| `discounted_products` | MIGRATE | already safe | **yes (Task 6 Group B — item_limit)** | no | no | NOT YET CERTIFIED |
| `amazing_offers` | MIGRATE | **yes (Task 5 Group A)** | **yes (Task 6 Group D)** | no | no | NOT YET CERTIFIED |
| `brand_carousel` | CERTIFY-ONLY | **yes (`beauty_tabs` gap closed, Task 5)** | yes | yes | **yes (Phase-3, 45/45)** | CERTIFIED (Phase 3) — regression sentinel |
| `collection_tiles` | CERTIFY-ONLY | already safe | yes | yes | **yes (Phase-3, 36/36)** | CERTIFIED (Phase 3) — regression sentinel |
| `promo_cards` | MIGRATE | **yes (Task 5 Group D — reuses Group C1 CSS)** | **yes (Task 6 Group B — item_limit)** | no | no | NOT YET CERTIFIED |
| `rich_text` | MIGRATE | already safe (inline) | yes (legacy) | no | no | NOT YET CERTIFIED |
| `image_text` | MIGRATE | **yes (Task 5 Group D)** | **yes (Task 6 Group C)** | no | **yes (Task 6 A1 — `image_position` edit + real `row-reverse` CSS assertion)** | CERTIFIED |
| `blog_posts` | MIGRATE | **yes (Task 5 Group D)** | **yes (Task 6 Group C)** | no | no | NOT YET CERTIFIED |
| `product_section` | MIGRATE | **yes (Task 5 Group A)** | yes | yes | no | NOT YET CERTIFIED |
| `catalog_product_wall` | HOME-ONLY | n/a | no | no | no | NO ACTION REQUIRED |
| `trust_features` | MIGRATE | **yes (Task 5 Group E)** | **yes (Task 6 Group D — first user of the new `repeater` field type; browser-verified end to end)** | no | no | NOT YET CERTIFIED |
| `quick_links` | MIGRATE | already safe | **yes (Task 6 Group D — title only; `menu_id` stays legacy-form-managed, no matching Inspector field type)** | no | no | NOT YET CERTIFIED |
| `faq` | MIGRATE | **yes (Task 5 Group E)** | **yes (Task 6 Group D — `repeater` field type; browser-verified end to end)** | no | no | NOT YET CERTIFIED |
| `testimonials` | MIGRATE | **yes (Task 5 Group E)** | **yes (Task 6 Group D — `repeater` field type)** | no | no | NOT YET CERTIFIED |
| `video_section` | MIGRATE | **yes (Task 5 Group E)** | **yes (Task 6 Group D)** | no | no | NOT YET CERTIFIED |
| `story_rail` | MIGRATE | already safe | **n/a — no section-level settings to schematize (media-only family, `_passthrough_dict`/`_empty_defaults`); real gap was the media-form/model rework (Task 6), now closed** | no | **yes (Task 6 A1 — real `StoryRailItem` fixture + `.story-item .story-label` text assertion; Task 7 Batch 3 — R4 Inspector now links to its media management screen instead of 404ing, since it has no schema)** | **CERTIFIED — media-form/model rework CLOSED (Task 6): real `AttributeError` on every story-item edit fixed, plus a duplicate-`title`-input data-loss bug and a missing-thumbnail bug found by independent review, also fixed; 56/56 targeted GREEN** |
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
