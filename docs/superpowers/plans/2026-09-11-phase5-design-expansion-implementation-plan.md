# Phase 5 — Design Expansion Implementation Plan

Date: 2026-09-11
Status: DRAFT — created from the Task-0 kickoff audit (`docs/qa_evidence/storefront_design_engine/phase5/kickoff_capability_map.md`, `67_family_production_map.md`, `demo_store_inventory.md`). Not yet started; no production code changes have been made under this plan.
Starting point: `feature/phase5-design-expansion` branched from `chore/phase5-uiux-agent-foundation@9f71109`.

## How to read this plan

Every task below cites **real, currently-existing repository owners** discovered during Task 0 — no
model, service, registry, or file name is invented. Where a task requires new code, it names the
existing service/module it must extend or the existing pattern it must imitate, never a parallel one.
Each task is independently testable and ends with a commit checkpoint; do not start a task whose
"Depends on" list has an unfinished entry.

Every task carries the same seven gates, in order:
1. **TDD RED** — write the failing focused test(s) first.
2. **GREEN** — implement the minimum change to pass.
3. **Focused tests** — the tests from step 1, passing.
4. **Relevant regression** — the existing test modules named in "Regression scope", run and green.
5. **Browser evidence** — for any visual change: screenshots/interaction proof at 1440×900, 768×1024,
   390×844, RTL primary, per Charter §9/§12. Non-visual (pure service/data) tasks skip this gate.
6. **Architecture/duplication gate** — confirm no second renderer/persistence/lifecycle/authority was
   introduced (re-check against §4 of the kickoff capability map).
7. **Review gate + commit checkpoint** — a focused diff review, then one commit per task (this repo's
   convention: `feat(storefront_builder): ...` / `fix(...)` / `docs(...)` as appropriate), pushed to
   `feature/phase5-design-expansion`.

No task in this plan touches `main`, the Phase-4 branch, or the Phase-4 backup.

## Dependency graph (high level)

```
Task 1 (candidate preview primitive)
  ├─> Task 2 (onboarding demo gallery, live preview)
  ├─> Task 3 (merchant-data template preview)
  └─> Task 14 (Random Mix / Design Lab, needs a candidate/transient preview to explore against)

Task 4 (contextual editor repairs: device preview, media/background picker, scope labels, selection sync)
  -> feeds Task 6, Task 15 (every new section needs a working Inspector)

Task 5 (high-impact primitive expansion: Header un-orphan, Mobile Nav Drawer, PDT/PDTX repair, STRANS, Modal)
  -> feeds Task 6, 7, 8 (Showcase and browse/PDP work reuse these primitives)

Task 6 (Storefront Showcase canonical section) — depends on Task 4, Task 5
Task 7 (Browse/Search/Filter/Sort completion) — depends on Task 5
Task 8 (PDP completion) — depends on Task 5
Task 9 (Cart/conversion: Free-Shipping Goal, Cross-Sell) — independent, can run parallel to 6/7/8
Task 10 (Editorial/content activation) — independent, can run parallel to 6/7/8/9
Task 11 (System/utility primitives: Toast, Tooltip, Tabs, Skeleton, Drawer, Floating, Scroll-reveal, Menu-transition) — depends on Task 5 (Mobile Nav Drawer) for Drawer/Menu-transition specifically; the rest are independent

Task 12 (Theme Overlay system) — depends on Task 4 (Advanced-tier UI pattern), Product Owner decision on owner (see D-items)
Task 13 (Template-DNA component variant selections: write-time reconciliation for hero/product_view/card/badge) — depends on Task 4

Task 14 (Random Mix / Randomize One / Locks / Remove Theme / Compare-with-Base) — depends on Task 1, Task 12, Task 13
Task 15 (R4 merchant controls simplification pass) — depends on Task 4, Task 6, Task 12, Task 14

Task 16 (Cross-template QA: 50-template browser matrix, RTL, a11y, visual distinctness)
  — depends on everything above that touches rendering (6, 7, 8, 9, 10, 12, 13)

Task 17 (Product Owner gallery/review) — depends on Task 16
Task 18 (Final Phase-5 closure checkpoint) — depends on Task 17
```

Tasks 6-11 do not depend on each other and may be sequenced in any order (or parallelized across
separate work sessions) once Tasks 4-5 land, since each touches a disjoint set of sections/families.

---

## Task 1 — Candidate preview primitive ("resolve without writing")

**Goal:** a service-level entry point that resolves what a Ready Template (or, later, a Theme/Random-Mix
candidate) would render as, without writing to the real Draft. This is the single missing primitive
blocking Onboarding Charter items 2, 3, 4 (demo-data live preview, merchant-data preview, general
candidate preview).

**Real owners to build on:**
- `apps/storefront_builder/services/preset_service.apply_preset()` (`preset_service.py:274-528`) —
  already validates the full recipe before any write; the validation half of this function is the
  starting point for a non-writing variant.
- `apps/storefront_builder/services/render_service.py` (shared renderer) and
  `apps/storefront_builder/services/storefront_context_service.build_universal_storefront_context()` —
  reuse for rendering, do not fork.
- `apps/storefront_builder/templates/storefront_builder/preview.html` + `storefront_preview()`
  (`views.py:225-296`) — the existing Draft-only preview iframe; extend its context-resolution step to
  accept a non-Draft, in-memory candidate manifest instead of only the real Draft.
- **Proven precedent to imitate (different feature, same shape):**
  `apps/catalog/services/template_preview_service.py` — `build_template_preview()`,
  `plan_industry_template_installation()` — a real "plan/preview, then commit" pattern already in
  production for Catalog Industry Templates. Do not reuse this module directly (it's Catalog-specific);
  replicate its *architecture* for storefront Ready Templates.

**What NOT to build:** a second renderer, a second Draft model, a second persistence layer, or a
client-side-only mock preview. The candidate manifest is transient (request-scoped or short-TTL
server-side scratch state), never written to `StorefrontLayoutVersion` until an explicit Apply.

**TDD RED:** a test that requests a preview of Ready Template X against a given context (demo store or
merchant store) and asserts the rendered output reflects X's DNA, while asserting `StorefrontLayoutVersion`
row count/`edit_revision` for the real Draft is unchanged after the call.

**Regression scope:** `apps/storefront_builder/tests/test_a8_ready_template_contracts.py`,
`test_r4_appearance_overrides.py`, existing `preset_service` apply/reset tests (ensure the new read-only
path shares validation logic without breaking existing Apply behavior).

**Browser evidence:** not required for this task (service-layer only); required for Tasks 2/3 which
consume it.

**Commit checkpoint:** one commit, e.g. `feat(storefront_builder): add non-mutating template preview resolution`.

---

## Task 2 — Onboarding Demo Gallery (live preview, replacing static screenshots)

**Goal:** Charter's "50-template gallery" backed by live rendering against the canonical `rasti-mode-demo`
store instead of pre-captured `.webp` screenshots.

**Real owners to build on:**
- `storefront_template_gallery()` (`views.py:2137`), template `template_gallery.html`, already nav-linked
  at `dashboard:storefront-builder-templates` — extend, don't replace.
- `apps/storefront_builder/a8_ready_templates.py` (50 recipes) — data source, unchanged.
- `apps/stores/management/commands/seed_ready_template_fashion_demo.py` (`rasti-mode-demo`, slug fixed)
  — reuse as-is (see `demo_store_inventory.md`); do not build a second demo store.
- Task 1's candidate preview primitive, called with the demo store's context.

**Depends on:** Task 1.

**TDD RED:** a test asserting the gallery, when a live-preview feature flag/route is hit for a given
template key, renders through Task 1's primitive against `rasti-mode-demo` and shows visibly different
markup for two structurally distinct templates (e.g. differing Hero variant class/ID) — a materially
different assertion, not just "200 OK".

**Regression scope:** `test_a8_ready_template_catalog.py` (still exactly 50, unique keys),
`capture_ready_template_previews.py`'s own tests (ensure the offline screenshot path isn't broken —
it can remain as a fallback/thumbnail source even after live preview lands).

**Browser evidence:** required — gallery screenshots at 1440×900/768×1024/390×844, RTL, for at least 5
representative templates showing visibly distinct output.

**Commit checkpoint:** `feat(storefront_builder): live-render onboarding gallery previews against rasti-mode-demo`.

---

## Task 3 — Merchant-data Template Preview

**Goal:** Onboarding Charter's "see the same 50 templates with my own data" — preview a candidate
template against the merchant's real Store-scoped catalog/brand/category, with zero Draft mutation.

**Real owners to build on:**
- Task 1's primitive, called with `resolve_store_for_service()`-resolved merchant Store context
  (`apps/stores/resolution.py:277`) instead of the demo store.
- `apps/storefront_builder/resource_source.py` — already resolves real Store-scoped
  products/brands/categories; this is the substrate, unchanged.
- Tenant-safety: reuse `resolve_store_for_service()` exactly as every other Builder mutation view does
  — no new resolution path.

**Depends on:** Task 1.

**TDD RED:** a test that previews template Y against Merchant Store A's real products and asserts (a)
Store A's real product names/prices appear in the rendered output, (b) no cross-tenant data (Store B's
products) ever appears, (c) `StorefrontLayoutVersion` for Store A is unchanged after the call.

**Regression scope:** tenant-isolation tests already in the suite for `resolve_store_for_service`
call sites; re-run in full since this is a new caller of that resolver.

**Browser evidence:** required — one merchant store's real catalog rendered under 2-3 different
templates, at all three QA viewports.

**Commit checkpoint:** `feat(storefront_builder): merchant-data template preview without Draft mutation`.

---

## Task 4 — Contextual editor repairs (R4 gaps found in the audit)

**Goal:** close the four "EXISTS BUT NEEDS REPAIR" items from the Onboarding Charter capability map
(§5 items 2, 10, 13, 14 in `kickoff_capability_map.md`) that block a fully R4-native onboarding/editing
flow:
1. Global-vs-section scope labeling (item 10) — add an inline indicator per control.
2. Media/background editing per section, ported into R4 (item 13).
3. Device preview (desktop/tablet/mobile switcher), ported into R4 (item 14).
4. Selection-sync repair: sidebar-originated selection should re-highlight the iframe element (item 7's
   caveat — `sfb:setSelection` is never sent by `r4_editor.js`).

**Real owners to build on:**
- Scope labeling: `r4_editor.js:345,1130-1281` (Global Design panel) and `r4_editor.js:341-373`
  (`R4.openSection`) — add a label, no new architecture.
- Media/background: port `_background_picker_context()` (`views.py:1080-1081`) and the media library
  integration (`media_views.py:165+`) into a new `settings_field.html` field type, following the exact
  pattern already used for the resource picker and the typography override
  (`apps/storefront_builder/templates/dashboard/storefront_builder/r4/partials/settings_field.html`).
- Device preview: port `sfb-v3-device-switcher` markup/Alpine state from `editor.html:120,329` into
  `r4/editor.html`; it resizes the same shared `preview.html` iframe R4 already uses — no new preview
  mechanism.
- Selection sync: send `sfb:setSelection` from `r4_editor.js` (sidebar row click handler) into the
  iframe, mirroring the existing `sfb:selectSection` message the iframe already sends outward
  (`preview.html:87-100`, `r4_editor.js:1079-1097`).

**Depends on:** none (can start immediately; recommended before Task 6 since Showcase needs a working
media/background picker and device preview to be usable).

**TDD RED:** four focused tests, one per repair — e.g. a JS/contract test asserting a `sfb:setSelection`
message is posted when a sidebar row is clicked; a Python test asserting the R4 inspector for a
media-bearing section renders the new field type instead of the legacy-link stub.

**Regression scope:** `test_r4_inspector.py`, `test_r4_appearance_overrides.py`,
`test_r4_foundation.py`.

**Browser evidence:** required for all four — device-switcher interaction, background picker applied to
a real section, scope label visible, sidebar-click-then-iframe-highlight sequence, at all three
viewports.

**Commit checkpoint:** can be one commit or four small ones per this repo's existing granularity
convention — check recent `git log` for `storefront_builder` commits and match style (this plan does
not prescribe which).

---

## Task 5 — High-impact primitive expansion

**Goal:** close the 67-family "NEEDS REPAIR-EXPANSION" items that block multiple downstream Showcase/PDP
tasks:
- **HDR Header:** wire the 11 orphaned header partial files
  (`templates/storefront_builder/partials/global_header/*.html`: category_tabs, centered_brand,
  community_shortcuts, compact_drawer, compact_menu, editorial_masthead, editorial_row,
  floating_compact, marketplace_search, overlay_transparent, playful_canopy, promo_bar) into
  `GLOBAL_HEADER_REGION.variants` (`global_region_registry.py:184-259`) so they become merchant-selectable.
- **MDR Mobile Navigation Drawer:** build a real off-canvas primary-nav drawer (distinct from the
  already-built Bottom Nav, family #7) — genuinely missing, no existing markup to repair.
- **PDT Product Tabs/Accordion:** make `product_description`'s content (description/specs/reviews)
  actually tabbed/accordion-interactive rather than flat stacked content.
- **PDTX Product Trust/Delivery Module:** make the hardcoded Persian shipping/warranty/return strings in
  `product_main.html:165-174` merchant-editable (reuse the `trust_features` schema shape as a model,
  don't duplicate its registry entry).
- **MODAL:** establish a real public-storefront-facing modal/quick-view pattern (today only
  Builder-admin modals exist).
- **STRANS:** confirm/add an explicit carousel transition-style control distinct from the existing
  autoplay/interval/arrows/dots playback fields.

**Depends on:** none (independent of Tasks 1-4, but Task 6/7/8 depend on this).

**TDD RED per family:** e.g. for Header, a test asserting all 21 on-disk header partials are now
resolvable via `GLOBAL_HEADER_REGION`; for MDR, a test asserting a drawer open/close mutation and its
accessible-name/focus-trap behavior; for PDT, a test asserting tab-panel ARIA roles and keyboard
operability.

**Regression scope:** `global_region_registry` tests, `section_registry` tests, existing PDP template
tests.

**Browser evidence:** required for every sub-item — this is the family with the most direct visual
impact.

**Commit checkpoint:** one commit per family (Header, MDR, PDT, PDTX, Modal, STRANS) to keep review
scope tight — six checkpoints, not one.

---

## Task 6 — Storefront Showcase canonical section

**Goal:** the Design Expansion Charter's headline capability (§4): one reusable section showing
Categories/Products/Collections/Brands through multiple materially different layouts, with simple R4
controls (content type, selection/source, layout, title, count, View All, essential mobile behavior).

**Real owners to build on — do not create a new section-registry pattern:**
- `apps/storefront_builder/section_registry.py` — register a new section type following the exact shape
  of the existing schema-backed sections (`brand_carousel`, `category_grid`, `collection_tiles`,
  `product_section` — all already real, schema-backed, independently switchable content-type sources).
  The Showcase's "content type" selector is architecturally a thin dispatcher over these four already-real
  content domains — do not reimplement their data loaders; call `render_service`'s existing
  `_category_grid_context`, `_brand_carousel_context`, `_collection_tiles_context`,
  `_product_section_context` (or a shared internal helper that already wraps them) based on the
  selected content type.
- Layout variants: reuse the existing per-family layout variant counts already registered (category_grid
  11 modes, brand_carousel 3, collection_tiles 2, product_section 3) as the Showcase's layout options —
  do not invent a fifth incompatible layout taxonomy.
- R4 schema: model the Showcase's `SettingsSchema` on `PRODUCT_SECTION_SCHEMA`/`CATEGORY_GRID_SCHEMA`
  (`section_registry.py:404,1671`), with Basic tab = content type, source, layout, title, count, View
  All; Advanced tab = the same spacing/appearance-override/motion pattern established in Task 4's Global
  vs section scope work.

**Depends on:** Task 4 (Inspector/scope patterns), Task 5 (Header/Category/Product primitives it will
compose).

**TDD RED:** a test asserting a single Showcase section instance can be configured for each of the four
content types and renders the correct underlying data loader's output; a test asserting an invalid
content-type/layout combination is rejected with a typed error (per Onboarding Charter §19's
allowlisted-values requirement).

**Regression scope:** all four underlying section renderer tests (brand/category/collection/product),
`section_registry` validation tests.

**Browser evidence:** required — same Showcase section configured for each of the 4 content types × at
least 2 layouts each, at all three viewports, on Home/category/brand/campaign-landing surfaces per
Charter §4's "Surfaces" row.

**Commit checkpoint:** `feat(storefront_builder): add canonical Storefront Showcase section`.

---

## Task 7 — Browse/Search/Filter/Sort completion

**Goal:** close remaining gaps in the listing/search experience. Per the 67-family audit, Filter, Sort,
Pagination, Listing Header, Search Header, and Empty state are all already **EXISTS & REUSE** — this
task is about verifying/hardening, not building from scratch.

**Real owners:** `product_listing` section (`section_registry.py:2859`),
`catalog/templates/catalog/partials/listing_header.html`,
`catalog/templates/catalog/partials/product_list_results.html` (empty state).

**Scope of actual work:**
- Confirm Pagination/Load More (family #27, "not independently re-confirmed line-by-line" in the audit)
  behaves correctly — write the missing test coverage rather than assuming it from the shared
  `product_listing` pipeline.
- Address the visual-baseline finding: PLP pagination wraps awkwardly on mobile (390px) — a bounded CSS
  fix within the existing `product_listing.html` template, not a new component.
- Address the visual-baseline finding: no visible search entry point in the mobile header — confirm
  whether it's reachable via the hamburger menu (1-2 taps) and, if not, add one within the existing
  Header component (reuse family #1's search-bearing header variants, don't build a second search UI).

**Depends on:** Task 5 (Header work, for the mobile search entry point).

**TDD RED:** a Pagination test with fixture data producing >1 page; a CSS regression check (or Playwright
layout assertion) for the mobile pagination wrap.

**Regression scope:** existing `product_list`/`product_listing` view and template tests.

**Browser evidence:** required — PLP/Search at all three viewports, before/after for the pagination and
mobile-search fixes.

**Commit checkpoint:** `fix(catalog): pagination mobile wrap and mobile search entry point` (+ separate
test-coverage commit if needed).

---

## Task 8 — Product Detail (PDP) completion

**Goal:** close the PDP-specific gaps: Sticky Add-to-Cart (SATC, missing), PDT tabs interactivity
(Task 5), PDTX merchant-editable trust module (Task 5), and the visual-baseline finding that PDP content
tabs overflow/clip on mobile (390px) with no scroll affordance.

**Real owners:** `sections/product_main.html`, `sections/product_description.html`,
`apps/storefront_builder/section_registry.py` (`product_main` section).

**Scope of actual work:**
- **SATC (Sticky Add-to-Cart / mobile purchase bar):** genuinely missing, explicitly acknowledged as an
  un-built P1 candidate in `PHASE_8_REPORT.md`. Build as a new bounded UI element inside the existing
  `product_main` rendering path (mobile-only sticky bar mirroring the existing ATC quantity/CTA), not a
  new section type.
- **PDT/PDTX:** delivered by Task 5; this task consumes them on the PDP specifically.
- **Mobile tab overflow fix:** the visual-baseline audit found the third PDP tab ("نظرات کاربران") renders
  off-screen-left at 390px with no scroll affordance — fix once Task 5's PDT interactivity work lands
  (the accordion/tab redesign should resolve this as part of making tabs genuinely interactive, not as a
  separate patch).

**Depends on:** Task 5.

**TDD RED:** a test asserting the sticky ATC bar appears only below a mobile breakpoint and mirrors the
main ATC's live stock/purchasability state (no second source of truth for cart affordance); a layout
assertion that all PDP tabs are reachable (via visible scroll affordance or a non-overflowing layout) at
390px.

**Regression scope:** `product_detail` view/template tests, `VAR`/`ATC` existing Alpine-driven tests.

**Browser evidence:** required — PDP at 390px before/after, all three viewports for the completed tab
interaction.

**Commit checkpoint:** `feat(catalog): sticky add-to-cart and PDP tab accessibility fixes`.

---

## Task 9 — Cart/conversion completion

**Goal:** Free-Shipping Goal (GOAL) and Cross-Sell Module (XSELL) — the two genuinely missing
cart-specific families. Cart Item, Cart Summary, and Coupon are already EXISTS & REUSE.

**Real owners to build on:**
- `apps/cart/` app — `cart_detail.html`, `cart_summary` section (`section_registry.py:2893`),
  `coupon_service.py` (real threshold/coupon domain logic already exists — the existing
  `SHOP_FREE_SHIPPING_THRESHOLD` setting the Announcement Bar can already read as a static message is
  the correct data source for a real progress bar, not a new setting).
- PDP's existing `related_products` domain logic is the nearest pattern for Cross-Sell's data source,
  but Cross-Sell is cart-context-specific — reuse the underlying product-recommendation query approach,
  not a copy-paste of the PDP template.

**Depends on:** none (independent of Tasks 5-8).

**TDD RED:** a test asserting the Goal component computes remaining-to-threshold correctly from real
cart totals and the existing `SHOP_FREE_SHIPPING_THRESHOLD`; a test asserting Cross-Sell excludes items
already in the cart and respects Store-scoping.

**Regression scope:** `apps/cart/tests/` (coupon/threshold logic), `product_card_service` tests (if
Cross-Sell reuses `ProductCardData`).

**Browser evidence:** required — Cart with and without free-shipping threshold met, Cross-Sell rail
populated, at all three viewports.

**Commit checkpoint:** `feat(cart): free-shipping goal indicator and cross-sell module`.

---

## Task 10 — Editorial/content activation

**Goal:** most editorial families (RTE, Testimonials, FAQ, Video, Story, Newsletter) are already
EXISTS & REUSE and schema-backed — several sit at **zero Ready-recipe usage today** (SLD, PROMO, PCT,
QLK, BLOG, VID, FAQ, COLC). This task is about curating which of the 50 templates should actually
compose these already-built sections, plus building the one genuinely missing family: STAT
(Stats/Social Proof).

**Real owners:** `section_registry.py` schemas already listed in the 67-family map; `a8_ready_templates.py`
composition tuples (`_HERO_VARIANTS`/`_STATIC_SECTIONS`/`_product_entry`, `a8_ready_templates.py:30-159`)
determine which sections each recipe actually uses.

**Scope of actual work:**
- For each zero-usage family, decide (with Product Owner input on which of the 50 templates should
  showcase it) whether to add it to specific recipes' Home compositions — this is a **data change to
  `a8_ready_templates.py`'s composition tuples**, not new component code, for the seven families that
  are already schema-ready.
- Build STAT (Stats/Social Proof) as a new section following the same shape as `trust_features`
  (`TRUST_FEATURES_SCHEMA`, `section_registry.py:1739`) — the nearest existing pattern — since no
  dedicated stats/counter section exists today.

**Depends on:** none.

**TDD RED:** a test asserting each activated family renders correctly when added to a recipe's
composition; a schema/render test for the new STAT section.

**Regression scope:** `a8_ready_templates` composition validation tests, `test_a8_ready_template_catalog.py`.

**Browser evidence:** required for STAT (new); recipe-composition changes need visual confirmation only
for the specific templates modified.

**Commit checkpoint:** `feat(storefront_builder): activate editorial sections in Ready Template recipes; add Stats section`.

---

## Task 11 — System/utility UI primitives

**Goal:** the remaining genuinely-missing generic UI primitives: Floating Action/Back-to-Top, Off-Canvas
Drawer (shared plumbing with Task 5's Mobile Nav Drawer), Toast/Notification, Tooltip/Popover, generic
Tabs widget (distinct from Task 5's PDT-specific fix — this is the reusable primitive PDT and any future
family should consume), Skeleton/Loading State, Section Reveal/Scroll Entrance, Menu/Drawer Transition.

**Real owners:** none exist yet for any of these — confirmed absent by exhaustive grep in the audit. No
existing module to extend; these are genuinely new, bounded, presentation-only additions with no
business-data dependency (unlike GOAL/XSELL/STAT which needed real domain data).

**Depends on:** Task 5 for Drawer and Menu/Drawer Transition specifically (they compose with MDR); the
rest (Floating, Toast, Tooltip, generic Tabs, Skeleton, Scroll-Reveal) are independent.

**Scope guardrail:** these are Charter reference-family entries, not new commerce features — build the
minimal reusable primitive each family needs (e.g. one generic Toast component other features can call,
not a full notification-center system). Do not scope-creep into building a design-system package beyond
what the 50 templates actually need (Charter §6: 670 reference variants is not a production-import
requirement, and the same discipline applies to inventing elaborate variant matrices for these utility
primitives).

**TDD RED per primitive:** focused component/interaction tests (e.g. Toast auto-dismiss timing and ARIA
live-region behavior; generic Tabs keyboard arrow-key navigation and ARIA `tab`/`tabpanel` roles;
`prefers-reduced-motion` respected by Scroll-Reveal).

**Regression scope:** none pre-existing (net-new code) — establish the new test modules as the
regression baseline going forward.

**Browser evidence:** required for all — these are exactly the kind of primitive where visual/interaction
proof matters most.

**Commit checkpoint:** one commit per primitive (8 checkpoints) to keep each review scoped.

---

## Task 12 — Theme Overlay system

**Goal:** the 50-Template DNA Charter's Theme Overlay + Theme Intensity — genuinely missing, no owner
exists today (confirmed: no `campaign_overlay`/`occasion_overlay` symbol anywhere in
`apps/storefront_builder`).

**Before writing code:** this requires an explicit Product Owner decision on which existing service
should own it, per the Task-0 instruction not to invent a new registry. Recommended framing for that
decision (not a decision made by this plan): Theme Overlay should be modeled as an **additional,
independently-toggleable layer on top of the existing appearance manifest** —
`appearance_authority_service.py` is the natural extension point (it already owns
`apply_appearance_patch`/`apply_store_appearance_manifest`), and Theme selection/intensity would be new
typed fields validated the same way `palette_slug`/`font`/`density` are today, **not** a new persisted
JSON blob outside the existing `StoreAppearanceManifest` contract
(`storefront_appearance/contracts.py:149-165`).

**Non-negotiable constraints (from the 50-Template DNA Charter):**
- Reversible: applying a Theme must never destroy the underlying Template DNA; "Remove Theme" (Task 14)
  must cleanly return to the themeless state.
- Three intensity levels (subtle/balanced/full or the project's equivalent), not open-ended.
- Mourning occasions (Muharram/Ashura) must not receive aggressive sale messaging, countdowns, or
  discount emphasis — this is a content/tone constraint on the Theme catalog itself, not just a
  technical one; flag explicitly for Product Owner review of the initial Theme catalog copy.

**Depends on:** Task 4 (Advanced-tier UI pattern to expose Theme controls), a Product Owner decision on
ownership framing above.

**TDD RED:** a test asserting a Theme applied to a store changes only the designated overlay-affected
fields (accents/motifs/decoration/motion) and leaves the base Template DNA's structural
selections (header/hero/footer/etc.) byte-for-byte unchanged; a test asserting Theme removal restores
the exact pre-Theme appearance state.

**Regression scope:** full `appearance_authority_service` test suite (this is the module being
extended), `preset_service` apply/reset tests (ensure Theme doesn't interfere with Template apply/reset).

**Browser evidence:** required — at least 3 themes (one festive/Iranian, one Islamic, one neutral/sale)
at all three intensity levels, on 2-3 different base templates, at all three viewports.

**Commit checkpoint:** `feat(storefront_builder): add reversible Theme Overlay system`.

---

## Task 13 — Template-DNA component variant selections (write-time reconciliation)

**Goal:** close the "PARTIAL" item from the Template-DNA audit — hero/product_view/card/badge variant
selections currently only apply as a render-time overlay (`render_service._build_items_from_sections`),
with no merchant-facing write-time selector/reconciliation, unlike header/footer/bottom_nav/motion which
are already fully write-time reconciled via `appearance_authority_service.apply_header_variant`/
`apply_footer_variant`/`apply_appearance_patch`.

**Real owner to extend:** `appearance_authority_service.py` — add the equivalent
`apply_hero_variant`/`apply_product_view_variant`/`apply_card_variant`/`apply_badge_variant` functions
(or one generalized `apply_component_variant(family, value)` if that fits the existing code's style
better — a judgment call for whoever implements this, not prescribed here) following the exact pattern
already proven for header/footer.

**Depends on:** Task 4 (R4 Inspector pattern to expose the new write-time selectors).

**TDD RED:** a test asserting selecting a Hero variant through the new write-time path persists into
`StoreAppearanceManifest` and is reflected in both the R4 mutation response and a subsequent full page
render — not just the render-time overlay.

**Regression scope:** full `appearance_authority_service` and `render_service` test suites (this touches
the render-time overlay logic being replaced/complemented).

**Browser evidence:** required — before/after for each of the 4 families, confirming the write-time
selection matches the rendered output exactly.

**Commit checkpoint:** `feat(storefront_builder): write-time reconciliation for hero/product_view/card/badge variants`.

---

## Task 14 — Random Mix / Randomize One / Locks / Remove Theme / Compare-with-Base

**Goal:** the largest cluster of genuinely new Design-Lab capabilities. Per the 50-Template DNA Charter
§9, these must be **transient/candidate state until explicit Apply** — never a second persisted source
of truth.

**Real owners to build on:**
- Task 1's candidate preview primitive — Random Mix generates a candidate manifest and previews it
  through the exact same non-mutating path, then Apply commits it through the exact same
  `preset_service`/`appearance_authority_service` path Task 2/3/13 already use.
- `draft.template_baseline_snapshot` (already exists, referenced by
  `preset_service.reset_storefront_to_baseline()`) is the data Compare-with-Base needs — building the
  compare/diff UI is the actual new work, not new data storage.
- Locks: a **new, small, request/session-scoped concept** — explicitly not the same as the existing
  structural `is_locked` field on `StorefrontSection`/`StorefrontContainer` (`models.py:709,838`), which
  must not be repurposed for this (confirmed in the audit as a different concept with different
  semantics — reusing it would silently change structural-lock behavior).
- Remove Theme: a new, narrow operation in `appearance_authority_service.py` (built in Task 12) that
  clears Theme-layer fields specifically, distinct from `reset_storefront_to_baseline()` (which resets
  the whole DNA to a specific Template's recorded baseline, not to "themeless").

**Depends on:** Task 1, Task 12, Task 13.

**Explicit non-goals (Charter §16):** no Cartesian raw-random combination generation — Random Mix must
only produce compatible, QA-approved combinations (reuse the same validation `apply_preset()` already
performs before any write); no new persistence for "saved mixes"; no localStorage-as-authority.

**TDD RED:** a test asserting Random Mix never changes a locked family; a test asserting Random Mix
never produces a combination that fails the existing recipe validation; a test asserting Compare-with-Base
correctly diffs current vs. baseline for a store with local overrides.

**Regression scope:** everything touched by Tasks 1, 12, 13's test suites, run together (this is the
task most likely to surface interaction bugs between the appearance authority service, the candidate
preview primitive, and the Theme system).

**Browser evidence:** required — Random Mix (all-open and single-family), a Lock preventing a specific
family from changing across repeated randomizations, Compare-with-Base showing a real diff, Remove Theme
restoring the exact pre-Theme state, at all three viewports.

**Commit checkpoint:** likely multiple commits given scope — at minimum, separate checkpoints for
Random Mix + Locks, Compare-with-Base, and Remove Theme.

---

## Task 15 — R4 merchant controls simplification pass

**Goal:** Charter §8/§10's "powerful but simple" requirement — a cross-cutting pass over everything
built in Tasks 4-14 to ensure: Basic tab is always the default, Advanced is collapsed/secondary, no
JSON/registry-ID/model-name leaks into ordinary merchant UI, and every new control's scope (global vs
section) is labeled per Task 4's pattern.

**Depends on:** Task 4, Task 6, Task 12, Task 14 (this is a review/polish pass over their combined
output, not new architecture).

**Scope of actual work:** a UI/copy audit against the Onboarding Charter §11 table (Basic vs Advanced
examples) for every new control surface introduced in this plan; fix any control that leaks
implementation detail into the merchant-facing labels.

**TDD RED:** N/A for most of this (it's a UI/copy review) — add specific regression tests only where the
audit finds a control that's miscategorized between Basic/Advanced and needs a tab-placement fix.

**Regression scope:** `test_r4_inspector.py` (tab-placement assertions).

**Browser evidence:** required — a full pass through R4 for a representative store, confirming no raw
JSON/registry key is visible in normal merchant flows.

**Commit checkpoint:** `fix(storefront_builder): R4 merchant-control simplicity pass`.

---

## Task 16 — Cross-template QA

**Goal:** Charter §12/§13's QA gate — the one thing every prior audit (closure pack, Phase 8, the
convergence program) explicitly flagged as never yet done: a real browser/visual-distinctness
certification across all 50 templates.

**Depends on:** Tasks 6, 7, 8, 9, 10, 12, 13 (everything that changes rendered output).

**Scope of actual work:**
- Re-run the closure pack's declared-DNA fingerprint analysis (`final_closure_pack/04`) against the
  *final* Task-16-era `a8_ready_templates.py` to reconfirm 50 distinct fingerprints, 0 duplicate groups,
  0 palette-only-duplicate groups, after all Task 5-13 changes.
- Full browser matrix: all 50 templates × {1440×900, 768×1024, 390×844} × RTL, using the project's
  existing Playwright harness (`tools/storefront_builder_r4_qa/run.mjs`, already proven for the
  Storefront Appearance Convergence program's QA — reuse it, don't build a second harness).
- Accessibility pass: keyboard/focus/semantics/state per Charter §12, using the same harness's
  extension points if it has them, or a new focused Playwright+axe pass otherwise (this is where the
  audit's many "UNKNOWN" accessibility cells get resolved).
- `prefers-reduced-motion` verification for every Motion Recipe (family #62) and any new
  transition/reveal primitives from Task 11.

**Browser evidence:** this task's entire output IS the browser evidence — the primary Phase-5 closure
artifact.

**Commit checkpoint:** `docs(qa_evidence): phase5 cross-template browser/RTL/accessibility QA matrix`
(evidence-only commit, plus any bug-fix commits the pass surfaces).

---

## Task 17 — Product Owner gallery/review

**Goal:** Charter §12 step 10 — Product Owner visually reviews all 50 templates and the core new
capabilities (Showcase, Theme Overlay, Random Mix) before closure.

**Depends on:** Task 16.

**Scope of actual work:** package Task 16's evidence into a reviewable form (the existing onboarding
gallery from Task 2 IS this review surface — no separate review tool needed), walk the Product Owner
through it, and record explicit sign-off or a list of requested changes.

**Commit checkpoint:** `docs: record Product Owner Phase-5 gallery review outcome` (only after actual
review — this plan does not pre-author an approval).

---

## Task 18 — Final Phase-5 closure checkpoint

**Goal:** verify every item in the Design Expansion Charter §13 Definition of Done, produce the closure
evidence pack (mirroring this repo's existing pattern — see `docs/architecture_audits/final_closure_pack/`
and `docs/qa_evidence/storefront_appearance_convergence/phase4/final_gate.md` for the established
format), and create the official Phase-5 checkpoint (tag/branch, per this repo's existing convention for
Phase 4's certified checkpoint and backup branch).

**Depends on:** Task 17 (Product Owner approval).

**Commit checkpoint:** the closure documentation commit, plus whatever checkpoint/backup-branch
mechanism this repo's own convention specifies (mirror how `backup/rastisi6-phase4-final-20260911` and
the certified Phase-4 checkpoint SHA were established — do not invent a new checkpointing convention).

---

## What this plan deliberately excludes

Per the Design Expansion Charter §14 and the 50-Template DNA Charter §16, this plan does **not**
schedule: importing all 670 AI reference variants, a second storefront platform/editor/renderer, new
database models/services/APIs invented to make a reference demo work, reopening Phase 4, building 50
independent codebases instead of 50 shared-capability compositions, permanent seasonal-theme forks, or
open-ended polish beyond the acceptance criteria in the three Charters.

## Known residual risk carried into Phase 5 (not a blocking item, tracked for awareness)

The kickoff capability map (§3) found that R4's mutation endpoint is the only one with true client-side
stale-write rejection; the legacy editor's ~44 per-field routes advance the shared revision counter but
don't check it. This plan builds exclusively on R4, so it does not make this worse — but if any Phase-5
task discovers it must touch a legacy-editor-only route (e.g. before Task 4/5 ports it to R4), flag that
specific route for the same stale-write hardening `r4_mutation_service.apply_mutation` already has,
rather than treating it as out of scope.
