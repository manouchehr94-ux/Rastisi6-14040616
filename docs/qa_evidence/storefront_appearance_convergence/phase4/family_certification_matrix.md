# Phase 4 family certification matrix

Tracks Phase-4 certification state for every section family and every global non-section family.
Updated by Task 6 (product-facing families) and Task 5 (CSS completeness). No row may remain
"unknown" at the Phase-4 final gate (Task 10).

Columns: disposition (from the plan's §0 recount) · CSS completeness (Task 5) · SettingsSchema ·
ResourceSource · browser certification (Task 4 harness) · status.

## Section families (36)

| key | disposition | CSS complete | SettingsSchema | ResourceSource | Browser cert | Status |
|---|---|---|---|---|---|---|
| `hero_banner` | MIGRATE | **yes (Task 5 Group A)** | yes (pre-existing) | no | no | NOT YET CERTIFIED |
| `fashion_lifestyle_hero` | HOME-ONLY | n/a (Home-only) | no | no | no | NO ACTION REQUIRED |
| `image_slider` | MIGRATE | **yes (Task 5 Group A)** | **yes (Task 6 Group A)** | no | no | NOT YET CERTIFIED |
| `single_banner` | MIGRATE | **yes (Task 5 Group B)** | **no — explicit FIXED/STATIC disposition (Task 6 Group C): no settings-driven field at all** | no | no | NOT YET CERTIFIED |
| `multi_banner` | MIGRATE | **yes (Task 5 Group B)** | **yes (Task 6 Group C — real closed-enum validator + schema, replacing `_passthrough_dict`)** | no | no | NOT YET CERTIFIED |
| `category_grid` | MIGRATE | **yes (Task 5 Group C, all 11 display_modes)** | **yes (Task 6 Group C)** | **yes (Task 6 — category kind wired into the shared Resource Picker)** | no | NOT YET CERTIFIED |
| `featured_products` | MARKETING-ALIAS | n/a | no | no | no | DOCUMENTED AS ALIAS |
| `newest_products` | MIGRATE | already safe | **yes (Task 6 Group B — item_limit)** | no | no | NOT YET CERTIFIED |
| `best_sellers` | MIGRATE | already safe | **yes (Task 6 Group B — item_limit)** | no | no | NOT YET CERTIFIED |
| `discounted_products` | MIGRATE | already safe | **yes (Task 6 Group B — item_limit)** | no | no | NOT YET CERTIFIED |
| `amazing_offers` | MIGRATE | **yes (Task 5 Group A)** | **yes (Task 6 Group D)** | no | no | NOT YET CERTIFIED |
| `brand_carousel` | CERTIFY-ONLY | **yes (`beauty_tabs` gap closed, Task 5)** | yes | yes | **yes (Phase-3, 45/45)** | CERTIFIED (Phase 3) — regression sentinel |
| `collection_tiles` | CERTIFY-ONLY | already safe | yes | yes | **yes (Phase-3, 36/36)** | CERTIFIED (Phase 3) — regression sentinel |
| `promo_cards` | MIGRATE | **yes (Task 5 Group D — reuses Group C1 CSS)** | **yes (Task 6 Group B — item_limit)** | no | no | NOT YET CERTIFIED |
| `rich_text` | MIGRATE | already safe (inline) | yes (legacy) | no | no | NOT YET CERTIFIED |
| `image_text` | MIGRATE | **yes (Task 5 Group D)** | **yes (Task 6 Group C)** | no | no | NOT YET CERTIFIED |
| `blog_posts` | MIGRATE | **yes (Task 5 Group D)** | **yes (Task 6 Group C)** | no | no | NOT YET CERTIFIED |
| `product_section` | MIGRATE | **yes (Task 5 Group A)** | yes | yes | no | NOT YET CERTIFIED |
| `catalog_product_wall` | HOME-ONLY | n/a | no | no | no | NO ACTION REQUIRED |
| `trust_features` | MIGRATE | **yes (Task 5 Group E)** | **yes (Task 6 Group D — first user of the new `repeater` field type; browser-verified end to end)** | no | no | NOT YET CERTIFIED |
| `quick_links` | MIGRATE | already safe | **yes (Task 6 Group D — title only; `menu_id` stays legacy-form-managed, no matching Inspector field type)** | no | no | NOT YET CERTIFIED |
| `faq` | MIGRATE | **yes (Task 5 Group E)** | **yes (Task 6 Group D — `repeater` field type; browser-verified end to end)** | no | no | NOT YET CERTIFIED |
| `testimonials` | MIGRATE | **yes (Task 5 Group E)** | **yes (Task 6 Group D — `repeater` field type)** | no | no | NOT YET CERTIFIED |
| `video_section` | MIGRATE | **yes (Task 5 Group E)** | **yes (Task 6 Group D)** | no | no | NOT YET CERTIFIED |
| `story_rail` | MIGRATE | already safe | **no — pending (needs media-form/model rework, not just a schema; not yet started)** | no | no | NOT YET CERTIFIED |
| `newsletter` | MIGRATE | already safe (inline) | **yes (Task 6 Group D)** | no | no | NOT YET CERTIFIED |
| `announcement_bar` | LEGACY-RETIRE | n/a | no | no | no | RETIREMENT CANDIDATE (see legacy_disposition.md) |
| `product_main` | CONTEXT-AWARE-DOMAIN-OWNED | n/a | no | no | no | SAFE BY CONSTRUCTION |
| `product_description` | CONTEXT-AWARE-DOMAIN-OWNED | n/a | no | no | no | SAFE BY CONSTRUCTION |
| `product_video` | CONTEXT-AWARE-DOMAIN-OWNED | n/a | no | no | no | SAFE BY CONSTRUCTION |
| `related_products` | CONTEXT-AWARE-DOMAIN-OWNED | n/a | no | no | no | SAFE BY CONSTRUCTION |
| `product_listing` | CONTEXT-AWARE-DOMAIN-OWNED | n/a | no | no | no | PENDING Task 3E fragment fix |
| `collection_header` | CONTEXT-AWARE-DOMAIN-OWNED | n/a | no | no | no | PENDING Task 3D boundary test |
| `collection_products` | CONTEXT-AWARE-DOMAIN-OWNED | n/a | no | no | no | PENDING Task 3D boundary test |
| `cart_items` | CONTEXT-AWARE-DOMAIN-OWNED | n/a | no | no | no | SAFE BY CONSTRUCTION |
| `cart_summary` | CONTEXT-AWARE-DOMAIN-OWNED | n/a | no | no | no | SAFE BY CONSTRUCTION |

## Global non-section families

| Family | Disposition | Status |
|---|---|---|
| Header | CERTIFY-ONLY | Canonical, converged — regression sentinel only |
| Footer | CERTIFY-ONLY | Canonical, converged — regression sentinel only |
| Mobile Bottom Navigation | CERTIFY-ONLY | Canonical, converged — regression sentinel only |
| Motion | CERTIFY-ONLY | Canonical, converged — regression sentinel only |
| `hero` (Store Appearance family) | TEMPORARY-ADAPTER | PENDING Task 6 Group F write/effective reconciliation; no new selector UI (Ruling J) |
| `product_view` | TEMPORARY-ADAPTER | PENDING Task 6 Group F |
| `card` | TEMPORARY-ADAPTER | PENDING Task 6 Group F |
| `badge` | TEMPORARY-ADAPTER | PENDING Task 6 Group F |
