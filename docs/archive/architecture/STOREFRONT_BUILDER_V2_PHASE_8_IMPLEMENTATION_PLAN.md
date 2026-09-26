# Phase 8 — Implementation Plan

Derived from `STOREFRONT_BUILDER_V2_PHASE_8_GAP_MATRIX.md`. Ordered P0 → P1 → P2. Each P0 item states the constrained architecture chosen (never "unlimited recursive layout," never a new Family/renderer) and the reason it was prioritized (materially increases achievable design difference; reusable across industries; understandable to non-programmers; fits the constrained visual-builder model; no second renderer; no duplicated infrastructure).

## P0 — required for no-code design freedom

### P0-1. Fix tenant-isolation gap in media-item destination form (security + no-code principle)
`section_media_form.html`'s Brand/Collection fields on Hero Slides and Banners are raw numeric-ID inputs with no server-side store-ownership check (`media_views.py:118-129`). Replace with the same real search/select pattern already used for Category/Product on the same form, and add a store-ownership check in the save path regardless (defense in depth — never trust that only the picker enforces scoping). Smallest, highest-value, most urgent item — both a UX and a security defect.

### P0-2. Product-card generic design settings
Add a small set of card-display settings resolvable per product-listing section (not a global-only axis, and not per-product — per *section*, so "Best Sellers" can look different from "New Arrivals"): show/hide brand, show/hide price, show/hide discount badge, show/hide wishlist icon, show/hide quick-add button, image ratio (square/portrait/landscape — closed enum, not raw CSS), border on/off. Implemented as a `card_settings` sub-dict validated in `section_registry.py` alongside existing `display_mode`/`item_limit` fields, threaded through to `product_card.html` via an explicit `with` include (no new global state, no per-product-row branching). Extend coverage from the current 2-of-8 product-listing section types to all 8 for both card settings and columns-per-device, since a merchant-visible "more products per row" control that only works on 2 of 8 rail types is confusing and looks like a bug. Repair the two dead settings found in the audit: either wire `card_image_crossfade` to real secondary-image markup (requires product image data supporting a second image — check `Product` model for an existing secondary-image field before adding one) or remove the dead toggle from the UI; remove or wire `card_mode`.

### P0-3. Header composability — bounded block model
Full recursive Rows→Blocks is explicitly out of scope ("no unlimited recursive layouts"). Chosen architecture: header keeps its existing fixed 3-zone structure (announcement bar / main row / nav row — this matches every real header archetype in the legacy visual-pattern extraction) but the **main row's action-icon cluster becomes an ordered list of blocks** instead of a fixed sequence, and the block *set* is extended beyond the current 4 toggleable actions. New `header_config["action_blocks"]` = ordered list of `{"type": <allowlisted key>, "hidden_on_tablet": bool, "hidden_on_mobile": bool}`, allowlisted types: `search`, `account`, `wishlist`, `cart` (always present, not removable), `phone`, `social`, `cta`, `spacer`. Order is drag/reorder in the header drawer, exactly like section reordering (reuse the same drag-handle pattern already proven in `section_list.html`). Add `header_config["alignment"]` (start/center/space-between — closed enum) for the main row, matching the legacy pattern extraction's documented archetypes (centered-logo, dense, minimal) without inventing new markup per archetype. Keep `sticky`/`announcement_*` as-is. This is additive to the existing toggle fields, not a breaking schema change — old drafts get a migration that derives an initial `action_blocks` list from their current toggle values in the existing fixed order.

### P0-4. Footer composability — bounded block model
Same constrained approach: footer becomes an **ordered list of column blocks** instead of a fixed 9-toggle sequence. `footer_config["columns"]` = ordered list of `{"type": <allowlisted key>, ...per-type settings}`, allowlisted types matching the audit's identified gaps: `about` (existing), `contact` (existing, split into `phone`/`email`/`address` sub-toggles since the audit found phone+email wrongly bundled and address entirely missing), `menu` (existing `quick_links`, extended to allow a second instance by picking a different Menu — this is the one "duplicate a block" case explicitly required by the spec's footer block list), `categories` (existing), `social` (existing), `trust_badges` (existing), `payment_logos` (existing), `newsletter` (existing), `custom_text` (new — free text block, sanitized like `rich_text` sections), `copyright` (existing, always last, not removable). Column order becomes drag/reorder in the footer drawer. Old drafts migrate their current 9 toggles into an initial `columns` list in today's fixed order, so no merchant-visible regression at migration time.

### P0-5. Inspector layout fields (content width, height)
Add `content_width` (narrow/standard/full) and `height` (compact/standard/tall) closed-enum selects to the sections where they have real visual meaning (`hero_banner`, `image_slider`, `image_text`, `single_banner`, `multi_banner`) — not added to sections where they'd have no effect (matching the existing precedent set by `supports_columns` gating). Rendered via a CSS class derived from the enum value, not raw pixel values.

### P0-6. Inline canvas section toolbar
Add the prototype's floating per-section toolbar (up/down/duplicate/hide/delete) directly on the hovered/selected element inside `preview.html`, dispatching to the exact same existing endpoints the sidebar already uses (`storefront-builder-section-move`/`-duplicate`/`-toggle`/`-remove` via `postMessage` to the parent, mirroring the existing `sfb:selectSection`/`sfb:reorderSections` pattern). No new backend surface — purely a canvas-side UI addition reusing proven endpoints.

### P0-7. Legacy Template consolidation
Absorb the 5 render-meaningful, currently Template-only fields (`content_width`, `grid_density`, `card_shadow`, `card_hover`, `hero_style`) into the Advanced/Design panel as new standalone controls. Retire the standalone "Template" gallery card and apply-flow from the merchant-facing appearance hub (collapsing 5 concept-cards to the target 3: Preset / Palette / Design). Keep `appearance_registry.TEMPLATE_REGISTRY` as an internal-only source of the *default combinations* used to seed Layout Presets and the new Design controls' option sets (satisfies "keep shared useful tokens," per the owner's explicit instruction) — it stops being merchant-facing, it doesn't get deleted. `template_slug` stays in the data model for backward read-compatibility of existing drafts but is no longer merchant-settable directly; a migration folds any stored `template_slug`'s unique 5 fields into the draft's explicit `appearance_config` so nothing visually changes for existing stores at migration time.

## P1 — high-value reusable visual variants (implement only where clean fit, after P0)

Priority per the owner's stated rule (visual difference, cross-industry reuse, non-programmer clarity, fits constrained builder, no second renderer, no duplication):
1. Product-card secondary-image crossfade — real implementation once P0-2 confirms whether `Product` has a natural secondary-image source; otherwise documented as a remaining gap rather than inventing new data model surface under time pressure.
2. Quick-add reveal modes (always/hover-fade/hover-slide) — a 3-way enum on the same `card_settings` dict from P0-2, pure CSS state, no new markup.
3. Sticky PDP purchase panel — a boolean on `product_main`'s section settings.
4. Mobile bottom navigation — a boolean on header_config, rendered as a fixed-position bar reusing the same `action_blocks` list from P0-3 (no new block-type concept, just an alternate render target on small screens).
5. Hover/focus cart preview — CSS/Alpine-only enhancement to the existing cart icon, no schema change.
6. PDP social share, PDP FAQ — new optional blocks on `product_detail`'s existing section-based composition (FAQ already exists as a general section; verify it's `page_types`-allowed on `product_detail` before adding a new section type).

Gift-wrap is explicitly out of scope per the kickoff.

## P2 — useful future enhancements (documented, not built this phase)

- Full recursive header/footer row system beyond the bounded block model above, if a future phase determines the bounded model is insufficient.
- Per-section card style beyond the closed-enum set in P0-2 (e.g. custom aspect ratios).
- A merchant-facing media-asset library browser (vs. today's per-item upload-only flow).
- Content-Page as a link destination type (currently absent from `DestinationType` entirely — a larger content-model change, not a Phase 8 P0).

## Execution order chosen for this phase

P0-1 (small, urgent) → P0-2 (product card — highest visual-difference leverage for the 3-store proof) → P0-5 (inspector width/height — small, unlocks visual variety needed for the 3-store proof) → P0-3 and P0-4 (header/footer — largest single gap, needed before demo stores can look structurally different) → P0-7 (Template consolidation — mental-model cleanup, do after the above so Design panel already has somewhere to put the absorbed fields) → P0-6 (inline canvas toolbar — pure UX polish, lowest risk to defer if time is short) → P1 items opportunistically → 3 demo storefronts via the finished Builder → design-freedom proof doc → full browser QA → final report.

Every step: implement → targeted tests for that slice → `manage.py check` + migration-drift check → commit. A medium `storefront_builder` app regression run after the header/footer and product-card slices (the two riskiest, most-shared-code changes) before moving on, per the kickoff's test-execution policy.
