# MASTER PROMPT — Implement the five lightweight RastiSi storefront references

You are working inside the real `RastiSi4` repository. The uploaded archive is intentionally lightweight because large ZIP files cannot be processed reliably in this session.

## Read first

Before changing code, read these files completely:

1. `README_FIRST_FA.md`
2. `IMPLEMENTATION_SPEC_FA.md`
3. `app.js`
4. `shared.css`
5. `index.html`
6. all ten HTML files under `pages/`

Open `index.html` locally and inspect every one of the ten routes at desktop and mobile widths. Use the “مشخصات دقیق این صفحه” control on every page.

## Critical interpretation rule

The emoji blocks are low-cost media placeholders, not the desired final imagery. Do not copy emoji into the production templates. For every emoji block, preserve its layout role, aspect ratio, crop/fit behavior, badge position, responsive behavior, and interaction, then connect it to real Builder media, products, variants, categories, or collections.

The lightweight pages are not five finished static websites. They are a visual and structural contract for five distinct template families:

1. `Vibrant Catalog` — based on the Beraito reference;
2. `Heritage Premium` — based on the Cactus Leather reference;
3. `Artisan Editorial` — based on the Deeyar reference;
4. `Modern Fashion` — based on the iBolak reference;
5. `Nordic Living` — based on the IkalaJam reference.

## Mission

Implement these five families inside the existing RastiSi4 site-builder architecture, including a homepage and a product-page presentation for every family. Preserve maximum design freedom: store owners must be able to hide, reorder, configure, and replace sections and media without breaking the template DNA.

Do not build five disconnected HTML sites. Do not create five color presets over one shared DOM. Do not replace the five references with generic approximations.

## Non-negotiable architecture

- Inspect and extend the current Builder, Template, Theme, Storefront, Product, Variant, Draft, Preview, Publish, and Rollback systems.
- Reuse the existing rendering pipeline. Preview and public storefront must render through the same components or templates.
- Preserve multi-tenancy and tenant isolation.
- Keep Palette, Typography, Motion, Component Style, and Density independently overrideable.
- Keep content separate from presentation. Never hard-code reference brand names, logos, addresses, phone numbers, discount claims, proprietary imagery, or industry data into a reusable template.
- Preserve all existing user changes and unrelated working features.
- Do not rewrite the Builder from scratch unless a verified architectural blocker makes extension impossible.

## Required renderer differences

Implement real component/partial/renderer branches for:

- `square_centered_commerce`
- `premium_portrait` with an optional `premium_campaign` mode
- `artisan_story_card`
- `fashion_portrait_gallery`
- `catalog_second_image`

The product card anatomy, image ratio, title alignment, price placement, action placement, and mobile fallback must follow `IMPLEMENTATION_SPEC_FA.md`. A single static markup structure with five CSS classes fails acceptance.

## Required section variants

At minimum support these variants through the existing section registry and section settings:

- Hero: `promo_dashboard`, `full_bleed_campaign`, `editorial_hero`, `fashion_carousel`, `neutral_living_hero`
- Category: `quick_icon_grid`, `portrait_category_row`, `editorial_category_tiles`, `banner_grid`
- Product collection: `dense_square_carousel`, `premium_portrait_grid`, `editorial_product_row`, `fashion_horizontal_rail`, `second_image_catalog_grid`
- Content/trust: Story rail, Service strip, About split, Workshop/blog cards, Social gallery, Campaign banners, Brand/logo row

Do not create a parallel homepage model if the existing section system can represent these as variants.

## Product pages

Add a template-specific product-page composition for all five families. Use the same Product and Variant data. Support:

- variant-aware image switching;
- color and size selectors when applicable;
- product video capability when present;
- related products using the selected template’s card renderer;
- touch-safe mobile CTA;
- Persian long-title, large-price, out-of-stock, discount, and no-discount states.

## Safe implementation workflow

### Phase 0 — Preflight

1. Show `git status` and preserve all current changes.
2. Identify the current branch and repository root.
3. Read repository instructions and relevant architecture documents.
4. Do not delete or overwrite migrations, templates, prototypes, media, or user files.

### Phase 1 — Repository-specific audit

Find and report the exact existing implementation for:

- Template/theme models and registry;
- Storefront sections and section settings;
- Product-card rendering;
- Header/footer rendering;
- product-detail rendering;
- Draft/Preview/Publish/Rollback;
- template gallery or preview routes;
- tenant resolution and isolation;
- existing tests.

Report the exact files, models, migrations, routes, templates/components, and tests that should change. Do not write code until this audit and an incremental plan are complete, unless the user explicitly tells you to proceed without a review gate.

### Phase 2 — Shared contracts

Implement or extend the minimum shared contracts first:

- template-family selection;
- section-variant selection;
- product-card renderer selection;
- product-page renderer/composition selection;
- media ratio/fit/mobile override;
- motion and touch fallback;
- safe defaults and migration behavior.

Backwards compatibility matters. Existing stores must retain their current rendering unless they select one of the new templates.

### Phase 3 — Implement one family at a time

Recommended sequence:

1. `Modern Fashion`
2. `Artisan Editorial`
3. `Nordic Living`
4. `Heritage Premium`
5. `Vibrant Catalog`

For each family:

1. implement Header, Hero, Category, Product Card, collections, Footer, and Product page;
2. connect every visible block to real Builder/store data;
3. verify desktop and mobile;
4. add focused tests;
5. create a stable commit before starting the next family.

If the user needs Template 1 first, change the sequence but keep the same one-family-at-a-time discipline.

### Phase 4 — Gallery and review flow

Create a development/admin review path:

`template gallery → selected template homepage → selected product page`

The review flow may use seeded demo content, but production storefronts must use tenant-owned data. The gallery must not become a second renderer.

### Phase 5 — Validation

Validate:

- all five homepages and all five product pages;
- desktop, tablet, and mobile;
- RTL and Persian typography;
- long product names and large prices;
- zero/one/many products;
- missing image and optional mobile image;
- variant image switching;
- out-of-stock and discounted states;
- touch and keyboard access;
- reduced motion;
- template switching without data loss;
- Draft/Preview/Publish/Rollback;
- Preview/Public parity;
- tenant isolation.

Use focused tests during development. Run the broader relevant suite only after the shared architecture or a complete family is stable.

## Visual acceptance gate

The implementation is accepted only if:

1. all five templates remain visibly different when given the same palette and demo products;
2. the product-card DOM/renderer differs where specified;
3. each family’s Header, Hero, density, image ratio, interaction, mobile fallback, and Footer match the lightweight reference;
4. no placeholder-only section is reported as complete;
5. every Builder control has a visible effect;
6. no critical action requires hover;
7. the final solution is extensible for future templates and industries.

## Session reporting

At the end of every session provide:

- completed work;
- exact changed files;
- migrations created;
- tests run and results;
- visual routes checked and viewport sizes;
- remaining families and blockers;
- current commit hash;
- exact instructions for the next session.

GitHub remains the official source of truth. Work on the correct RastiSi4 repository and branch, make incremental commits, and do not leave the laptop and GitHub histories divergent after the user approves pushing.
