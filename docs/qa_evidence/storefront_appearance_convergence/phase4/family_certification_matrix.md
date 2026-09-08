# Phase 4 family certification matrix

Tracks Phase-4 certification state for every section family and every global non-section family.
Updated by Task 6 (product-facing families) and Task 5 (CSS completeness). No row may remain
"unknown" at the Phase-4 final gate (Task 10).

Columns: disposition (from the plan's §0 recount) · CSS completeness (Task 5) · SettingsSchema ·
ResourceSource · browser certification (Task 4 harness) · status.

## Section families (36)

| key | disposition | CSS complete | SettingsSchema | ResourceSource | Browser cert | Status |
|---|---|---|---|---|---|---|
| `hero_banner` | MIGRATE | pending (Task 5 Group A) | yes (pre-existing) | no | no | NOT YET CERTIFIED |
| `fashion_lifestyle_hero` | HOME-ONLY | n/a (Home-only) | no | no | no | NO ACTION REQUIRED |
| `image_slider` | MIGRATE | pending (Task 5 Group A) | no | no | no | NOT YET CERTIFIED |
| `single_banner` | MIGRATE | pending (Task 5 Group B) | no | no | no | NOT YET CERTIFIED |
| `multi_banner` | MIGRATE | pending (Task 5 Group B) | no | no | no | NOT YET CERTIFIED |
| `category_grid` | MIGRATE | pending (Task 5 Group C) | no | no | no | NOT YET CERTIFIED |
| `featured_products` | MARKETING-ALIAS | n/a | no | no | no | DOCUMENTED AS ALIAS |
| `newest_products` | MIGRATE | already safe | no | no | no | NOT YET CERTIFIED |
| `best_sellers` | MIGRATE | already safe | no | no | no | NOT YET CERTIFIED |
| `discounted_products` | MIGRATE | already safe | no | no | no | NOT YET CERTIFIED |
| `amazing_offers` | MIGRATE | pending (Task 5 Group A) | no | no | no | NOT YET CERTIFIED |
| `brand_carousel` | CERTIFY-ONLY | pending (`beauty_tabs` cosmetic gap) | yes | yes | **yes (Phase-3, 45/45)** | CERTIFIED (Phase 3) — regression sentinel |
| `collection_tiles` | CERTIFY-ONLY | already safe | yes | yes | **yes (Phase-3, 36/36)** | CERTIFIED (Phase 3) — regression sentinel |
| `promo_cards` | MIGRATE | pending (Task 5 Group D) | no | no | no | NOT YET CERTIFIED |
| `rich_text` | MIGRATE | already safe (inline) | yes (legacy) | no | no | NOT YET CERTIFIED |
| `image_text` | MIGRATE | pending (Task 5 Group D) | no | no | no | NOT YET CERTIFIED |
| `blog_posts` | MIGRATE | pending (Task 5 Group D) | no | no | no | NOT YET CERTIFIED |
| `product_section` | MIGRATE | pending (Task 5 Group A) | yes | yes | no | NOT YET CERTIFIED |
| `catalog_product_wall` | HOME-ONLY | n/a | no | no | no | NO ACTION REQUIRED |
| `trust_features` | MIGRATE | pending (Task 5 Group E) | no | no | no | NOT YET CERTIFIED |
| `quick_links` | MIGRATE | already safe | no | no | no | NOT YET CERTIFIED |
| `faq` | MIGRATE | pending (Task 5 Group E) | no | no | no | NOT YET CERTIFIED |
| `testimonials` | MIGRATE | pending (Task 5 Group E) | no | no | no | NOT YET CERTIFIED |
| `video_section` | MIGRATE | pending (Task 5 Group E) | no | no | no | NOT YET CERTIFIED |
| `story_rail` | MIGRATE | already safe | no | no | no | NOT YET CERTIFIED |
| `newsletter` | MIGRATE | already safe (inline) | no | no | no | NOT YET CERTIFIED |
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
