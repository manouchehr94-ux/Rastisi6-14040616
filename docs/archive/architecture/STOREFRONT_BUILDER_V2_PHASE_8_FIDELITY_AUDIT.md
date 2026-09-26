# Phase 8A — Spec + Prototype Fidelity Audit

**Scope**: read-only audit of the production Storefront Builder (`apps/storefront_builder`) at synchronized SHA `aa423b81f43f53e045d045ef926ad7a74dc596c8`, judged against `docs/architecture/UNIVERSAL_STOREFRONT_BUILDER_V2_SPEC.md` and `docs/prototypes/storefront-builder-v2/rastisi_builder_v2_prototype.html`, from the perspective of a non-programmer merchant.

**Method**: full reads of the canonical spec (2084 lines) and the prototype HTML (359 lines); four parallel source-level research passes covering (1) canvas/inspector fidelity, (2) header/footer composability, (3) product-card/responsive/page-composition coverage, (4) reference pickers + legacy Template redundancy — each returning file:line citations; direct verification reads of `editor.html`, `preview.html`, `section_list.html`, `section_settings_form.html`, `header_panel.html`, `footer_panel.html`, `models.py`, `views.py`, `section_registry.py`; one targeted Playwright pass against a real seeded store (`sfb-phase4-qa`) to browser-verify the claims this document marks as fully working. Evidence tiers used below: `SOURCE_ONLY`, `RUNTIME_VERIFIED` (traced through server logic, not merely read), `BROWSER_VERIFIED` (clicked through in a real browser this session).

No files were modified during this audit. No implementation has started.

---

## 1. Executive summary

The production Builder is materially more advanced than a naive reading of "Phase 7 closed, Family retired" would suggest. It already has a **genuine live-canvas renderer** (the same `build_page_render_items`/section-template pipeline used by the public site, not a mock second renderer), **click-to-select directly in the canvas** via `postMessage`, **drag-to-reorder** both in the canvas and the sidebar, a **6-page switcher**, a **tenant-scoped section library**, and **real search/select pickers** for products/categories/brands/collections/menus in the section inspector. This is a strong foundation and should not be rebuilt from scratch.

However, three areas fall clearly short of both the spec and the prototype's product intent, and these are the Phase 8 P0 targets:

1. **Header and Footer are not composable.** They are flat sets of show/hide booleans (6 fields for header, 9 for footer) with a template-hardcoded, unchangeable element order, no per-block styling, and no way to add, remove, or duplicate a block. This is the single largest gap versus the spec's "Rows → ordered Blocks" model (§10) and versus the owner's explicit Phase 8 requirement.
2. **Product cards have almost no merchant-facing design freedom.** Image ratio, border, and the visibility of brand/price/discount-badge/wishlist/quick-add are all hardcoded in one shared template with zero settings. The one style axis that IS configurable (image fit/hover/density/radius) is **site-wide**, not per-section — a merchant cannot make one product rail denser than another. Two existing settings (`card_image_crossfade`, `card_mode`) are dead — their UI toggle has no corresponding render-time effect.
3. **The Inspector is not a persistent panel and lacks several spec-required field types.** It is a hidden slide-over drawer rather than an always-visible third column, has no content-width or height controls, and per-section mutating actions (duplicate/delete/move) live only in the sidebar list or drawer, never inline on the canvas as the prototype shows.

A fourth, non-P0 but explicitly requested finding: the **legacy Template system is genuinely partially redundant** with Palette + Design/Appearance, and independently conflicts with Layout Presets with no reconciliation — detailed in §7.

Everything else — page composition across all 6 page types, section add/remove/reorder/duplicate/hide, per-section device-visibility, draft/publish/rollback, and reference pickers (with one specific exception) — is in materially good shape and mostly meets the spec.

---

## 2. Single-screen workspace (spec §6, prototype layout)

**Target**: one screen — top bar (page selector, undo/redo, draft status, preview, publish) — three-column body (block library / live canvas / settings panel) — floating add-section affordance.

**Reality** (`editor.html`, `preview.html`):

| Element | Status | Evidence |
|---|---|---|
| Top bar: draft status, publish, discard | Present | `editor.html:20-43` — status badges + publish/discard forms |
| Top bar: page selector | Present, but full navigation not a live switch | `editor.html:54-58` — `<a href="?page=...">` per page type; deliberately a full browser nav per the code's own comment (`editor.html:45-53`), not htmx/SPA |
| Top bar: undo/redo | **Absent** | grep of the whole app for `undo`/`redo` returns nothing |
| Top bar: preview | Present (desktop/tablet/mobile toggle resizing the live canvas in place) | `editor.html:69-73,98` — BROWSER_VERIFIED |
| Left column: block/section library | Present, grouped by category | `editor.html:113-134`, `section_registry.list_library_groups` |
| Center: live canvas = real Draft render | Present, genuinely the production renderer | `views.py:153-193` (`storefront_preview` calls the same `build_page_render_items` as public pages); `responsive_section_wrapper.html:40` includes the same per-section templates used live — RUNTIME_VERIFIED |
| Right column: persistent settings inspector | **Not persistent** — hidden overlay drawer | `editor.html:192-199` (`x-show="drawerOpen"`) — BROWSER_VERIFIED: drawer is empty/hidden until a section is explicitly selected, not an always-visible pane |
| Floating "+ Add Section" button / inline drop-zone | **Absent** | only an accordion (`<details>`) in the sidebar (`editor.html:113-116`); no floating button, no "+ add section here" zone between rendered sections |
| Add-section modal grid | **Absent** | add-section is inline in the sidebar accordion, not a modal |

**Assessment**: PARTIAL. The most important piece — a real, click-into live canvas — exists and works well. The container chrome (persistent 3rd column, floating add button, undo/redo) does not match the prototype and is a legitimate, scoped P0/P1 UI item, not a rebuild.

---

## 3. Section-level editing operations (spec §8)

| Operation | Status | Evidence |
|---|---|---|
| Add section (tenant-scoped, page-type-allowlisted) | Complete | `storefront_section_add` (`views.py:220-254`), server-enforced via `is_section_allowed_on_page` (`section_registry.py:1198-1206`, fail-closed on unknown keys) — RUNTIME_VERIFIED |
| Select section (from list AND directly in canvas) | Complete | sidebar: `section_list.html:45-48`; canvas: `preview.html:44-56` → `postMessage` → `editor.html:266-279` — BROWSER_VERIFIED (canvas click opened the drawer with a real form in this session's QA pass) |
| Reorder (drag in list, drag in canvas, up/down buttons) | Complete | `section_list.html:5-17` (list drag), `preview.html:58-107` (canvas drag), `section_list.html:34-41` (up/down buttons), persisted via `storefront_section_reorder` (`views.py:651-671`) |
| Duplicate | Complete, but sidebar/drawer-only (no inline canvas action) | `storefront_section_duplicate` (`views.py:607`); button only in settings-drawer danger zone (`section_settings_form.html:560-565`) |
| Hide/show | Complete, sidebar-only | `storefront_section_toggle` (`views.py:584`); button in `section_list.html:42-44` |
| Delete | Complete, drawer-only, with confirm | `storefront_section_remove` (`views.py:566`); `section_settings_form.html:566-582` |
| Inline per-section floating toolbar directly on the rendered canvas element (prototype's `.section-toolbar`) | **Absent** | canvas only exposes a small drag handle (`preview.html:71-107`); no floating up/down/duplicate/hide/delete cluster on the section itself |
| Device-visibility per section (desktop/tablet/mobile) | Complete, all 17 general section types | `section_registry.py:310-340` (`validate_responsive_settings`), UI `section_responsive_fields.html:7-18`, render `responsive_section_wrapper.html:34-36` + `layout.css:144-150` — RUNTIME_VERIFIED |
| Save | Complete, but full-page POST/redirect (not incremental) | every settings form uses `hx-boost="false"` and redirects to the full editor (`views.py:381`) |

**Assessment**: PARTIAL. All required merchant operations exist and are reachable and correctly tenant/page-scoped; the gap is purely about *where* the controls live (sidebar/drawer vs. inline-on-canvas per the prototype) and the lack of live incremental updates (every add/save/reorder triggers a forced full iframe reload or full page redirect, per `editor.html:217-221,256-265` and the settings-form `hx-boost="false"` pattern).

---

## 4. Inspector field coverage (spec §8, §20)

Content fields (title, rich text, media, product/category/brand/collection selection, FAQ/testimonial repeaters), destination/link fields, motion style, and device-visibility all exist and are wired per-section-type in `section_settings_form.html`'s 17 `{% elif %}` branches. Confirmed **missing** field types from the spec/prototype's inspector model:

- **Content width** (narrow/standard/full) — no such field anywhere in any section's settings form. BROWSER_VERIFIED absent.
- **Height** (short/medium/tall/full-screen) — no such field anywhere. BROWSER_VERIFIED absent.
- **"Save as Preset" from a single section** — does not exist (Presets are whole-layout only, via `layout_preset_registry`/`preset_service`, not a per-section save action).

**Assessment**: PARTIAL — strong content/data-source/responsive/motion/link coverage, but layout-shape controls (width/height) are entirely absent, which limits per-section visual variety even where the underlying template could support it.

---

## 5. Header composability (spec §10)

**Target**: Header → Rows → ordered Blocks (Logo, Store Name, Search bar, Search icon, Main nav, Category nav, Account, Wishlist, Cart, CTA, Phone, Social, Spacer), with row/block order, alignment, width mode, sticky, background, border/shadow, per-block desktop/mobile visibility, spacing, independent mobile arrangement.

**Reality**: `header_config` is a flat dict — RUNTIME_VERIFIED and BROWSER_VERIFIED (14 checkboxes counted in the live drawer, zero drag/reorder affordance, zero "add block" button):

```python
HEADER_TOGGLE_FIELDS = ["show_search", "show_account", "show_cart", "show_wishlist", "sticky", "announcement_enabled"]
HEADER_CONFIG_DEFAULTS = {f: True for f in HEADER_TOGGLE_FIELDS} | {"announcement_text": "", "responsive": {...}}
```
(`models.py:40-63`)

- **Order**: 100% fixed by hardcoded template sequence (`page_shell_header.html:45-115`); no order field exists in the schema or validator (`layout_service.py:98-164`).
- **Blocks that exist as toggles**: search, account, wishlist, cart (forced-on — validator rejects turning it off, `layout_service.py:130-134`), sticky, announcement bar + text.
- **Blocks that don't exist as configurable units at all**: logo (always on, unconditional), store name (always on), main navigation, category navigation, CTA button, phone, social icons, spacer, search-icon-only variant.
- **Add/remove/duplicate a block**: impossible — `validate_header_config` whitelists exactly the 6 toggle fields and silently drops anything else (`layout_service.py:114-119`).
- **Styling**: only `sticky` exists; no background, border, shadow, alignment, width-mode, or spacing control anywhere in header_config.
- **Independent mobile arrangement**: only hide-on-tablet/hide-on-mobile per field for 4 of 6 fields (`show_cart` and `sticky` explicitly excluded, `models.py:44-49`) — the mobile header is always the same DOM order as desktop, just with some elements optionally hidden. No mobile-specific block set or order.

**Assessment**: **UI_MISSING / BACKEND_ONLY at best** for the composable-block model the spec requires. What exists (visibility toggles + sticky + announcement text) is real and functions correctly for its narrow scope, but it is not "Header Builder" in the spec's sense at all — it cannot produce the visually distinct header archetypes (floating capsule, centered-logo, dense multi-row, minimal) called out as P1 legacy patterns worth preserving, because there is no mechanism to change structure, only to hide fixed elements.

---

## 6. Footer composability (spec §10)

**Target**: Footer → Rows/Columns → ordered Blocks (Logo, Store description, Menu, Contact info, Phone, Email, Address, Social links, Newsletter, Trust/badge region, Custom text, Internal/external link, Copyright).

**Reality**: Same pattern as header — RUNTIME_VERIFIED and BROWSER_VERIFIED (27 checkboxes counted in the live drawer, zero reorder/add-block controls):

```python
FOOTER_TOGGLE_FIELDS = ["show_about", "show_contact", "show_quick_links", "show_categories",
                         "show_social", "show_trust_badges", "show_payment_logos", "show_newsletter", "show_copyright"]
```
(`models.py:65-76`)

- 9 fixed toggle fields, fixed column order (`page_shell_footer.html:18-83`), no row/column concept, no order field.
- No separate blocks for: address, standalone phone-only, standalone email-only, custom free text, a second menu column, or a standalone internal/external link block — `show_contact` bundles phone+email into one toggle; `show_about` bundles the store description into one toggle; `show_quick_links` is a single fixed menu slot.
- No add/remove/duplicate — same whitelist-and-drop validator pattern (`layout_service.py:147-152`).
- No footer-level styling controls at all (no sticky-equivalent, no background/border/alignment/width-mode/spacing).
- Content (about text, contact details, social links, newsletter copy, trust badges, payment logos) is edited on entirely separate settings pages outside the Builder's draft/publish cycle — i.e. footer *content* changes take effect immediately on the live site, bypassing Draft/Preview/Publish, which is itself a Draft/Publish-safety inconsistency worth flagging even though it's not literally a design-freedom gap.

**Assessment**: **UI_MISSING / BACKEND_ONLY** for the same reasons as header. This is the second half of the single largest P0 item.

---

## 7. Product-card design freedom (spec §13, owner's explicit example area)

One shared template, `apps/catalog/templates/catalog/partials/product_card.html`, used by every product-listing section across every page type — confirmed clean of any `if preset_key ==`/`if template_slug ==`/`if SHOP_FAMILY` branching (the old Family-era branch was fully retired in Phase 7; verified by direct read).

| Setting | Status | Evidence |
|---|---|---|
| Image aspect ratio | **Absent** | hardcoded `aspect-ratio:1/1` (`product_card.css:23`) |
| Image fit (cover/contain) | Real, but **site-wide only** | `appearance_panel.html:250-255` → `context_processors.py` → `product_card.html:7`; not per-section |
| Image hover (zoom) | Real, **site-wide only** | `appearance_panel.html:256-261` |
| Card density (grid gap) | Real, **site-wide only**, and only affects grid gap not internal card padding | `appearance_panel.html:230-235` → `product_card.css:11-14` |
| Show/hide brand | **Absent** — always rendered | `product_card.html:31` |
| Show/hide price | **Absent** — always rendered | `product_card.html:37-42` |
| Show/hide compare-price / discount badge | **Absent as a merchant toggle** — automatically shown whenever a discount exists, no on/off control | `product_card.html:13,40` |
| Show/hide wishlist icon | **Absent** — always rendered | `product_card.html:11` |
| Show/hide quick-add button | **Absent** — always rendered | `product_card.html:22-28` |
| Corner radius | Real, **site-wide only** | `appearance_panel.html:216-219` → `product_card.css:21` |
| Border on/off | **Absent** — always on | `product_card.css:21` |
| Shadow style | Real, but only as a side effect of picking an entire Template, no standalone control | `appearance_registry.py:89,209-297` |
| Secondary-image hover-crossfade | **UI exists, is dead** — toggle has no matching markup anywhere (`.mf-card-img-2`/`.nl-card-img-2` targeted by CSS but never emitted by any template) | `appearance_panel.html:262-269`, `tokens.css:24-33` |
| `card_mode` (default/campaign) | **UI exists, is dead** — value stored but dropped before reaching the card include | `section_registry.py:202-204`, `product_section.html:12`, `product_grid.html:1-2` |
| Products per row (desktop/mobile) | **Real for only 2 of 8 product-listing section types** (`product_section`, `multi_banner`); hardcoded `g4`/`g3` CSS classes for the other 6 (`featured_products`, `newest_products`, `best_sellers`, `discounted_products`, `related_products`, `collection_products`/`product_listing`) | `section_registry.py:263-286,331-339` |

**Assessment**: **UI_MISSING** for genuine per-card/per-section design freedom, **BACKEND_ONLY/dead** for two settings that already have UI but no effect. What IS configurable (image fit/hover/density/radius/shadow) is real but site-wide, which is architecturally the wrong scope for "look different per rail/page" but is a legitimate axis for whole-store identity — it should be kept, not removed, while section/card-scoped controls are added on top.

---

## 8. Responsive editing (spec §21)

Per-section desktop/tablet/mobile visibility is complete and uniform across all 17 general section types (`section_registry.py:310-340`, `layout.css:144-150`) — RUNTIME_VERIFIED. Columns-per-device is real only for `product_section`/`multi_banner`; intentionally not exposed for `category_grid`/`promo_cards`/`brand_carousel` (documented as a deliberate choice since it would have no visual effect, `section_registry.py:256-262`) and entirely absent for the other 6 product-listing section types. No alternate mobile image/media field exists anywhere. No per-device spacing control exists (only one site-wide density value). Header/footer responsive control is narrower still (hide-on-tablet/mobile only, no hide-on-desktop, no columns concept at all).

**Assessment**: COMPLETE for section visibility; PARTIAL for columns-per-device; NOT_IMPLEMENTED for mobile-alternate-media and per-device spacing.

---

## 9. Page composition across all 6 page types (spec §14-18)

All 6 `StorefrontPage.PageType` values are switchable on the same screen/URL (`editor.html:54-58`, `views.py:37-45`), each with its own section list, add/remove/reorder, server-enforced page-type allowlist (`is_section_allowed_on_page`, fail-closed on unknown keys), and sensible non-empty seeded defaults (`bootstrap_service.py:35-150`) — BROWSER_VERIFIED (6 switcher links present and functional).

- **home**: fully free-form, any generally-scoped section allowed. Complete.
- **product_detail**: `product_main` (locked, max 1), `product_description`, `product_video`, `related_products` — genuinely distinct, reorderable composition. Complete.
- **collection**: `collection_header` (removable) + `collection_products` (locked, max 1) — genuinely distinct. Complete.
- **cart**: `cart_items` + `cart_summary`, both locked max-1 — genuinely distinct. Complete.
- **listing** and **search**: both use the *identical* `product_listing` section definition (`page_types={LISTING, SEARCH}`) — they are not compositionally distinct from one another; a merchant editing "Listing" and "Search" is really editing the same block on two different pages, not two different page designs. This matches the spec's description of these two page types as naturally similar (both are "product grid + filters"), so this is judged **NOT_REQUIRED to be more distinct** rather than a gap — flagged for owner awareness, not the implementation plan.

**Assessment**: COMPLETE for 5 of 6 page types' compositional distinctness; the listing/search overlap is intentional-and-acceptable, not a defect.

---

## 10. No-code reference pickers (spec's "no raw DB IDs" principle)

Section-level destination pickers (category/brand/collection/product, used by `image_text`/`product_section`/`brand_carousel`) are real search/select UI, tenant-scoped server-side (`views.py:482-501`, `views.py:548-560`). Section content pickers (`category_grid`/`brand_carousel`/`collection_tiles`/`quick_links`) are all real tenant-scoped multi-pickers (`views.py:408-454`).

**One confirmed exception, worth flagging as its own P0 item**: the **media-item (Hero Slide / Banner) destination form** (`section_media_form.html:80-87`) requires the merchant to **type a raw numeric Brand ID or Collection ID** into a plain number input labeled "شناسه‌ی برند" / "شناسه‌ی کالکشن" ("Brand ID" / "Collection ID") — this is a second, inconsistent picker implementation from the section-level one, and it is also a **tenant-isolation gap, not just a UX gap**: `media_views.py:118-129` reads and saves these IDs with no store-ownership check at all (confirmed by reading `apps/content/models.py:169-224`, which only validates "exactly one destination type is set," never that the referenced brand/collection belongs to the same store). A merchant (or a compromised/careless staff account) could type another tenant's brand/collection primary key and have it silently accepted and saved. Category and Product destinations on the same form ARE real, tenant-scoped pickers — only Brand and Collection are affected.

**Assessment**: PARTIAL for the no-code principle (one clear violation), and this specific violation is also a genuine security/tenant-isolation defect that should be fixed as part of Phase 8 P0 regardless of the design-freedom framing.

---

## 11. Legacy Template system vs. target merchant mental model (owner's explicit question)

Target: three concepts — Preset, Palette, Design/Appearance. Reality — BROWSER_VERIFIED via the live appearance hub, which shows **five** separate concept cards: Template, Palette, Colors (overrides), Advanced (Design), and Layout Preset (`appearance_panel.html:8-63`).

Traced what `template_slug` actually controls at render time (`apps/storefront_builder/views.py:802-911`, `apps/core/context_processors.py:159-238`, `appearance_registry.py:71-94`):

- **6 fields are fully redundant with the Advanced/Design panel**: `font`, `radius`, `button_radius`, `density`, `motion`, `type_scale`. Selecting a Template just bulk-writes these same six fields that the Advanced panel already edits directly and independently — after either path the persisted config is indistinguishable.
- **5 fields are genuinely unique to Template, with no other merchant-facing control anywhere**: `content_width`, `grid_density`, `card_shadow`, `card_hover`, `hero_style`. These do have real, distinct render-time effects (`--sfb-content-width`, `--sfb-grid-density`, `data-sfb-card-shadow`, `data-sfb-card-hover`, `data-sfb-hero-style` CSS hooks).
- The raw `template_slug` itself is emitted as a `data-sfb-template` DOM attribute but is never read by any CSS selector in the codebase — it is dead for styling; all visual effect flows through the 11 derived fields above.
- **Template and Layout Preset are fully independent axes that can silently conflict**: applying a Preset sets an appearance overlay (potentially including density/motion/etc.); separately applying a Template afterward unconditionally overwrites the same overlapping fields with the Template's fixed values, discarding the Preset's choices with no warning, no reconciliation, and no UI indication that this happened (`views.py:816-833`, `preset_service.py:108-163`).

**Conclusion for the implementation plan**: the Template concept is **not fully redundant** (it owns 5 real structural fields the Design/Appearance panel lacks) but its current **presentation as a separate fourth/fifth merchant concept, with a separate gallery and separate apply action that silently clobbers Preset choices, is a genuine UX defect** and should be resolved by absorbing the 5 unique structural fields into the Design/Appearance panel (giving it new "Layout width," "Grid density," "Card shadow," "Card hover," "Hero style" controls) and retiring the standalone Template selector UI, while keeping the 20-palette system and the underlying CSS-token machinery untouched. This becomes a P0/P1 item in the implementation plan.

---

## 12. What already fully meets the spec (do not rebuild)

- Draft/Preview/Publish/Rollback contract (`layout_service.py`) — untouched, correct, not in scope for redesign.
- Live canvas = real production renderer, not a second renderer.
- Click-to-select directly in canvas, drag-to-reorder in canvas and sidebar.
- Section add/remove/duplicate/hide/reorder, all tenant- and page-type-scoped server-side.
- Per-section desktop/tablet/mobile visibility for all general section types.
- Product/category/brand/collection/menu pickers at the section-content level (excluding the one media-form exception above).
- Page composition and defaults for all 6 page types.
- Layout Preset system (Phase 6) — independent, correct, should become the primary "starting point" concept post-Phase-8.
- Palette system (20 palettes) — clean, non-overlapping, correctly independent of everything else.

These are the parts of the Builder Phase 8 must build *on top of*, not replace.
