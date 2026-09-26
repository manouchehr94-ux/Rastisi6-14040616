# Storefront Builder V2 — Phase 7 Read-Only Retirement Audit

**Base SHA**: `7ffc4ae805012f8545da454935555009c392e096` (canonical synchronized HEAD, confirmed)
**Status**: audit only — no implementation in this document. Companion document:
`docs/architecture/STOREFRONT_BUILDER_V2_LEGACY_RETIREMENT_MAP.md` (per-item classification
table). Visual extraction: `docs/architecture/STOREFRONT_BUILDER_V2_LEGACY_VISUAL_PATTERN_EXTRACTION.md`.

## 0. Scoping decision — Family vs. the separate legacy "Template" system

This codebase has **two independent legacy-era appearance mechanisms**, and only one is in
scope for this phase:

1. **Family** (`family_registry.py`, `preset_registry.py`, 11 families) — swaps entire Django
   template files per family (header/hero/category/footer/product-card/product-detail-page).
   **In scope for retirement**, per the master instruction's explicit title and content.
2. **Template** (`appearance_registry.TemplateDefinition`/`TEMPLATE_REGISTRY`, 10 entries:
   modern/marketplace/minimal/boutique/luxury/tech/editorial/compact/playful/glass) — never
   swaps a template file; only sets CSS custom properties (radius/density/motion/font/button
   style/hero style/card shadow) over the **one shared DOM**. Predates Family, is architecturally
   independent of it (`family_registry.py:9-19` and `preset_registry.py:10-13` both document
   this explicitly), and remains fully live for any store that hasn't selected a Family.

**Decision**: retire Family. Do **not** touch Template. Rationale: the master instruction is
titled "Legacy Family Migration/Retirement" and its Hard Cutover Strategy / Legacy Registry
Policy sections name `family_registry.py`/`preset_registry.py` specifically, while explicitly
warning "DO NOT delete shared appearance infrastructure merely because legacy presets use it."
Template's mechanism — CSS tokens over a shared DOM, no template-file swap — is structurally
the same *kind* of thing as a Phase 6 Layout Preset's `appearance` field, not the same kind of
thing as Family. Retiring it was not asked for and would be undocumented scope creep with its
own regression risk (10 templates, actively selectable today, with their own test coverage in
`test_appearance.py`, which contains **zero** `family_slug` references and is unaffected by
anything in this document).

## 1. Where legacy Family behavior is ACTIVE at canonical HEAD

### 1.1 Registries (ground truth, re-verified against the live code, not assumed)

- `apps/storefront_builder/family_registry.py` — `FAMILY_REGISTRY`, exactly 11 entries:
  `modern_fashion`, `artisan_editorial`, `nordic_living`, `heritage_premium`, `vibrant_catalog`,
  `atlas_catalog`, `ava_fashion`, `toranj_gifting`, `sarv_stock`, `sepidar_handmade`,
  `zarrin_jewelry`. Each carries 6 literal template paths
  (header/hero/category/footer/product_card/product_page variants) + `default_preset_slug` +
  `default_section_keys` (home-only) + `product_card_campaign_variant` (heritage_premium only).
- `apps/storefront_builder/preset_registry.py` — `PRESET_REGISTRY`, exactly 11 entries, each
  `family_slug`-locked 1:1 to one family.

### 1.2 The dispatch mechanism is broader than "Product Detail only"

A prior phase's working assumption — that only Product Detail has a family bypass — is **half
right**. It is right for *full page-body* replacement: only
`apps/catalog/templates/catalog/product_detail.html:24` does
`{% if SHOP_FAMILY %}{% include SHOP_FAMILY.product_page_variant %}{% else %}...render_items
loop...{% endif %}`; Listing/Collection/Search/Cart never swap their main body per family
(confirmed: no `SHOP_FAMILY` reference inside any of their content blocks).

But `SHOP_FAMILY` is injected **globally** by `apps/core/context_processors.py:163-188,259-260`
onto every request that resolves `ShopSettings` — not gated on Builder-adoption or page type.
As a result, family dispatch actually reaches **every** page through shared components:

| Component | File | Family branch |
|---|---|---|
| Header | `apps/storefront_builder/templates/storefront_builder/partials/page_shell_header.html:1` | `{% if SHOP_FAMILY %}{% include SHOP_FAMILY.header_variant %}{% else %}...{% endif %}` |
| Footer | `.../partials/page_shell_footer.html:1` | same pattern, `footer_variant` |
| Product card (every grid: listing/search/collection/home sections/related products) | `apps/catalog/templates/catalog/partials/product_card.html:2` | `{% if SHOP_FAMILY %}{% if card_mode == "campaign" and SHOP_FAMILY.product_card_campaign_variant %}...{% else %}{% include SHOP_FAMILY.product_card_variant %}{% endif %}{% else %}...{% endif %}` |
| Hero section | `apps/storefront_builder/templates/storefront_builder/sections/hero_banner.html:1` | `{% if SHOP_FAMILY %}{% include SHOP_FAMILY.hero_variant %}{% else %}...{% endif %}` |
| Category section | `.../sections/category_grid.html:1` | same pattern, `category_variant` |
| Global CSS | `templates/base.html:33-40` | `{% if SHOP_FAMILY %}<link ... href="css/families/{{ SHOP_FAMILY.slug }}.css">{% endif %}`, plus `data-sfb-family="..."` on `<html>` |
| Product Detail body | `apps/catalog/templates/catalog/product_detail.html:24` | full-body swap (see above) |
| Cart preview mode (business logic, not just markup) | `apps/cart/context_processors.py:29-31` | `if family_slug == "heritage_premium": cart_preview_mode = "mini_cart"` |

Pages reaching the header/footer family shell (via `templates/storefront_shell.html:33-45`'s
`{% if uses_universal_shell %}` block): Product Detail, Listing, Collection Detail, Collection
Index, Cart. Home (`home.html`/`home_visual.html`) includes the header/footer partials directly
rather than through `storefront_shell.html` (documented as intentional in that template's own
comment) but is still subject to the same `SHOP_FAMILY` global injection for its header/footer/
hero/category sections.

**Conclusion**: Family dispatch is not an isolated Product-Detail-only concern. A true hard
cutover must strip the `{% if SHOP_FAMILY %}` branch from all 7 locations above, not just
Product Detail's.

### 1.3 `apps/cart/context_processors.py` — a real business-logic dependency outside `storefront_builder`

`apps/cart/context_processors.py:29-31` hardcodes `cart_preview_mode = "mini_cart"` specifically
for `family_slug == "heritage_premium"`. This is the **one** place Family reaches actual
(non-template-selection) business/UX logic outside the builder app. Must be removed as part of
cutover — after retirement no store can newly select `heritage_premium`, and per the master
instruction's stale-value policy, existing stale values must not switch behavior.

### 1.4 Family switch UI/view flow (ACTIVE_RUNTIME_DEPENDENCY, merchant-facing)

- `apps/storefront_builder/views.py:822` `storefront_appearance_editor` — POST branch
  (`:833-970`): family/template mutual exclusivity, confirm-before-destructive-reset gate
  (`:851-857`), palette cascade, `layout_service.validate_appearance_config` call, and
  (`:963-967`) `bootstrap_service.apply_family_default_sections(draft, new_family)` — **only**
  call site of that function in the entire repo (besides its own definition).
- `apps/storefront_builder/templates/dashboard/storefront_builder/partials/appearance_panel.html` —
  family gallery (`:109-131`) with preview button (dispatches `preview-candidate-family`) and
  an apply form with a JS `confirm()` dialog.
- `apps/storefront_builder/templates/dashboard/storefront_builder/editor.html:201-204` —
  `#sfbApplyFamilyForm`, a hidden second-step submit form used by the candidate-preview flow
  (`:265-297`).

### 1.5 `apply_family_default_sections` / `default_section_keys`

`bootstrap_service.py:219-244` — operates on `version.home_page()` only, never touches other
pages. Draft-only **by caller discipline** (its one caller, `views.py:966`, always passes a
freshly-resolved Draft) — the function itself has no internal Draft/Published guard. No other
callers anywhere in the repo, including seed commands.

## 2. Family-specific source inventory

- **67 template files**: 44 structural partials (`.../partials/families/<slug>/{header,hero,category,footer}.html` × 11), 11 product-detail-page partials (`apps/catalog/templates/catalog/partials/product_pages/<slug>.html`), 12 product-card partials (`apps/catalog/templates/catalog/partials/product_cards/*.html` — heritage_premium has 2, for its campaign mode).
- **11 CSS files**: `apps/core/static/css/families/<slug>.css`, each keyed by `[data-sfb-family="..."]` selectors.
- **9 test files** exercising Family/legacy-Preset behavior directly (full list and classification in the retirement map): `test_family_registry.py`, `test_family_default_section_reset.py`, `test_eleven_families.py`, `test_preset_registry_import.py`, `test_six_families_tenant_isolation.py`, `test_family_artisan_editorial.py`, `test_family_heritage_premium.py`, `test_family_nordic_living.py`, `test_family_vibrant_catalog.py`.
- **1 test file with a mixed concern**: `test_shared_capabilities.py` — contains both unrelated infrastructure tests (category images, cart preview service, product metafields — must survive untouched) and family-specific assertions (`IndependentImageSettingsTests`, `StoryRailSectionTests`'s family-default cases, `AllElevenFamiliesRegisteredTests` — must be removed).

## 3. `family_slug`/`preset_slug` schema status

**Confirmed: pure JSON dict keys, zero schema/migration footprint.** No Django model named
`Family`/`Preset` exists; no migration file contains the literal strings `family_slug`/
`preset_slug`. They live only inside `StorefrontLayoutVersion.appearance_config` (a JSONField
added once, in `0003_storefrontlayoutversion_appearance_config.py`, and never touched again for
this purpose). Retirement requires **no schema migration** — only code changes to
`APPEARANCE_CONFIG_DEFAULTS` (`models.py:119-121`) and `validate_appearance_config`
(`layout_service.py:261-273`), plus a **data cleanup** for any store whose stored
`appearance_config` already has a non-null `family_slug`/`preset_slug` (dev/QA data only, per
the owner's confirmed "no production stores" decision — see §5).

## 4. Route cutover status (per master prompt's required table)

| Route | Full-body family swap today? | Family-influenced components today? | Uses `storefront_shell.html`/Universal header-footer? | Uses `StorefrontPage` composition? | After cutover |
|---|---|---|---|---|---|
| Home | No | hero_banner, category_grid sections, header/footer (via direct partial include) | N/A (direct include) | Yes (Phase 1A+) | Fully Universal, zero family branches |
| Product Detail | **Yes** (`SHOP_FAMILY.product_page_variant`) | header/footer, product_card (related products) | Yes | Yes (Phase 5) | Fully Universal |
| Listing | No | header/footer, product_card (grid) | Yes | Yes (Phase 5) | Fully Universal |
| Collection Index/Detail | No | header/footer, product_card | Yes | Yes (Phase 5, Detail only — Index has no "current collection" concept, confirmed unchanged in Phase 5) | Fully Universal |
| Search | No (reuses `product_list.html`) | header/footer, product_card | Yes | Yes (Phase 5) | Fully Universal |
| Cart | No | header/footer, `cart_preview_mode` business logic | Yes | Yes (Phase 5) | Fully Universal |

No Wishlist- or Content-Page-specific family logic was found anywhere in the audit (no matches
for family-related strings in `apps/content/` or wishlist views).

## 5. Development data policy applied

Per the owner's explicit confirmation (no production stores, no real merchants, destructive dev
cleanup acceptable): any dev/QA store's `appearance_config.family_slug`/`preset_slug` will be
normalized to `None` as part of implementation (a one-off management/shell data touch-up, not a
schema migration — see §3). No product/category/order/customer/content/collection data is
touched by this phase; those models have zero relationship to the Family system per the
Phase 6 and this phase's audits.

## 6. Test retirement classification (summary — full detail in the retirement map)

- **Obsolete product-contract tests** (assert "family X renders family template X" or "exactly
  11 families/presets exist") — retired outright: `test_eleven_families.py`,
  `test_preset_registry_import.py`, `test_family_artisan_editorial.py`,
  `test_family_heritage_premium.py`, `test_family_nordic_living.py`,
  `test_family_vibrant_catalog.py`.
- **Safety-pattern tests parameterized over families** — the underlying guarantee (Draft/
  Published isolation, tenant isolation, confirm-before-destructive-reset) must survive, but the
  *mechanism* it guards is retired. Since Phase 6's `test_preset_service.py` already proves the
  equivalent guarantee for the surviving mechanism (Layout Preset application — draft-only,
  transactional, tenant-isolated, confirmation-gated), these files are retired rather than
  ported: `test_family_registry.py`, `test_family_default_section_reset.py`,
  `test_six_families_tenant_isolation.py`.
- **Mixed file, surgical edit**: `test_shared_capabilities.py` — remove only the 3 family-tied
  test classes, keep the rest untouched.
- **Untouched**: `test_appearance.py` (zero family references — Template/Palette system, out of
  scope per §0).

## 7. What must NOT be touched

- `appearance_registry.py`'s Palette system (`PaletteDefinition`, `PALETTE_REGISTRY`,
  `resolve_colors`, 20 palettes) and structural token infrastructure (`DENSITY_CHOICES`,
  `MOTION_CHOICES`, `TYPE_SCALE_CHOICES`/`TYPE_SCALE_SIZES`, `FONT_CHOICES`,
  `BUTTON_STYLE_CHOICES`, `IMAGE_FIT_CHOICES`/`IMAGE_HOVER_CHOICES`) — genuinely shared V2
  infrastructure, consumed independently of Family by `layout_service`, the global context
  processor, and (Phase 6) `layout_preset_registry`/`preset_service`.
- `appearance_registry.py`'s `TemplateDefinition`/`TEMPLATE_REGISTRY` (10 legacy templates) —
  out of scope per §0.
- `layout_preset_registry.py`/`services/preset_service.py` (Phase 6) — the authoritative V2
  Preset mechanism; not merged with the retired legacy `preset_registry.py`, not given 1:1
  Family coupling.
- Everything in `apps/dashboard/views.py::product_preview` — confirmed to have **no** separate
  family-dispatch logic of its own; it already renders through the same universal
  `product_detail.html`/`build_universal_storefront_context` path as the public route, so it
  needs no direct code change (it inherits the header/footer/product_card fix automatically once
  those shared partials are cut over).
