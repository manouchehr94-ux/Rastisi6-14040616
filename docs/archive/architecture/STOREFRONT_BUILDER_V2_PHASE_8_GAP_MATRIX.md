# Phase 8 — Capability Gap Matrix

Companion to `STOREFRONT_BUILDER_V2_PHASE_8_FIDELITY_AUDIT.md` (read that first for narrative detail and full citations). This document is the row-by-row classification required by the Phase 8 kickoff, covering the mandatory dimension list at minimum.

**Classification**: `COMPLETE` / `PARTIAL` / `BACKEND_ONLY` / `UI_MISSING` / `NOT_IMPLEMENTED` / `NOT_REQUIRED`
**Evidence tier**: `SOURCE_ONLY` / `RUNTIME_VERIFIED` (traced through server logic) / `BROWSER_VERIFIED` (clicked through this session) / `MERCHANT_UI_VERIFIED` (reserved for post-implementation, real merchant flow with no DB/shell shortcuts — none of Phase 8A's rows use this tier yet, since Phase 8A is read-only audit before implementation)

Nothing below is marked `COMPLETE` on `SOURCE_ONLY` evidence alone, per the explicit instruction.

| # | Dimension | Classification | Evidence | Notes |
|---|---|---|---|---|
| 1 | Single-screen workspace (bar+library+canvas+inspector together) | PARTIAL | BROWSER_VERIFIED | Inspector is a hidden slide-over drawer, not a persistent 4th column; everything else co-resides on one screen |
| 2 | Page selector (6 types, same workspace) | PARTIAL | BROWSER_VERIFIED | Works, but is a full browser navigation per click, not a live client-side switch (deliberate design choice, documented in code) |
| 3 | Live canvas = real Draft via Universal engine | COMPLETE | RUNTIME_VERIFIED | `storefront_preview` uses the same `build_page_render_items`/section-template pipeline as public pages |
| 4 | Direct section selection from canvas | COMPLETE | BROWSER_VERIFIED | Click-in-canvas → `postMessage` → drawer opens with real settings form |
| 5 | Selected-section highlight | COMPLETE | SOURCE_ONLY | CSS `.sfb-rsec-selected` outline; not independently re-verified in browser this pass but trivial and low-risk |
| 6 | Inline section controls (on-canvas toolbar) | UI_MISSING | BROWSER_VERIFIED | No floating up/down/duplicate/hide/delete cluster on the rendered section; those actions exist only in sidebar list / drawer |
| 7 | Block/section library | COMPLETE | BROWSER_VERIFIED | Grouped accordion, htmx add, page-type filtered |
| 8 | Add section | COMPLETE | RUNTIME_VERIFIED | Server-enforced via `is_section_allowed_on_page`, fail-closed |
| 9 | Delete section | COMPLETE | RUNTIME_VERIFIED | Confirm-gated, drawer danger zone |
| 10 | Duplicate section | COMPLETE | RUNTIME_VERIFIED | Drawer danger zone only, not inline-on-canvas |
| 11 | Hide/show section | COMPLETE | RUNTIME_VERIFIED | Sidebar toggle button |
| 12 | Reorder section | COMPLETE | RUNTIME_VERIFIED | Drag in sidebar, drag in canvas, up/down buttons — three redundant real mechanisms |
| 13 | Settings inspector — Content fields | COMPLETE | BROWSER_VERIFIED | 17 per-type branches; title/body/media/product-category-brand-collection selection all present |
| 14 | Settings inspector — Layout fields (width/alignment/columns/height) | PARTIAL | BROWSER_VERIFIED | Columns exist for 2/8 product sections; width and height fields entirely absent everywhere |
| 15 | Settings inspector — Style fields (card style/ratio/radius/overlay/button style) | UI_MISSING (section-scoped) / PARTIAL (site-wide) | RUNTIME_VERIFIED | Image fit/hover/density/radius exist but are site-wide only, not per-section; no per-section overlay/card-style control |
| 16 | Settings inspector — Responsive (device visibility) | COMPLETE | RUNTIME_VERIFIED | All 17 general section types |
| 17 | Settings inspector — Responsive (columns-per-device) | PARTIAL | RUNTIME_VERIFIED | Real+visual for `product_section`/`multi_banner` only; stored-but-inert for 3 more types; absent for 6 more |
| 18 | Settings inspector — Data source (product/category/collection/manual/newest/discounted) | COMPLETE | BROWSER_VERIFIED | `product_section` data_source select covers newest/discounted/best_sellers/most_viewed/collection/category/brand/manual |
| 19 | Desktop preview | COMPLETE | BROWSER_VERIFIED | In-place canvas resize |
| 20 | Tablet preview | COMPLETE | BROWSER_VERIFIED | Exceeds spec (3 device states, not 2) |
| 21 | Mobile preview | COMPLETE | BROWSER_VERIFIED | In-place canvas resize |
| 22 | Header editing — visibility toggles | COMPLETE | BROWSER_VERIFIED | 6 toggle fields functional |
| 23 | Header editing — composable rows/blocks | UI_MISSING | BROWSER_VERIFIED | Flat toggle dict; no order field; no add/remove block; confirmed no drag/reorder control in the live drawer |
| 24 | Header editing — per-block styling (bg/border/shadow/alignment/width mode/spacing) | NOT_IMPLEMENTED | RUNTIME_VERIFIED | Only `sticky` exists as a style axis |
| 25 | Header editing — independent mobile arrangement | NOT_IMPLEMENTED | RUNTIME_VERIFIED | Only hide-on-tablet/mobile per field (4 of 6 fields); same DOM order as desktop always |
| 26 | Footer editing — visibility toggles | COMPLETE | BROWSER_VERIFIED | 9 toggle fields functional |
| 27 | Footer editing — composable rows/columns/blocks | UI_MISSING | BROWSER_VERIFIED | Same flat-dict pattern as header; 27 checkboxes confirmed, zero reorder/add-block control |
| 28 | Footer editing — missing block types (address, standalone phone/email, custom text, standalone link, second menu) | NOT_IMPLEMENTED | SOURCE_ONLY | No schema field for any of these |
| 29 | Announcement bar editing | COMPLETE | BROWSER_VERIFIED | Toggle + text field, part of header_config |
| 30 | Navigation editing (main menu) | COMPLETE (via existing Menu app, not Builder-versioned) | SOURCE_ONLY | Explicitly routed to the separate live Menus feature, not Draft/Publish-scoped — acceptable per current architecture, documented as "live identity" |
| 31 | Draft status indicator | COMPLETE | BROWSER_VERIFIED | Top bar badges |
| 32 | Draft preview (no impact on public site until publish) | COMPLETE | RUNTIME_VERIFIED | Verified in Phase 4-7 test suites; not re-verified this pass but architecturally unchanged |
| 33 | Publish | COMPLETE | RUNTIME_VERIFIED | Atomic pointer-swap, verified in prior phases' test suites |
| 34 | Rollback | COMPLETE | RUNTIME_VERIFIED | `storefront_restore`, verified in prior phases |
| 35 | Preset selection | COMPLETE | RUNTIME_VERIFIED | Phase 6 system, independent and correct |
| 36 | Palette selection | COMPLETE | BROWSER_VERIFIED | Independent axis, 20 palettes, appearance hub confirmed |
| 37 | Global appearance (typography/spacing/radius/density/motion) | COMPLETE, but split across a redundant "Template" concept too | BROWSER_VERIFIED | Advanced panel has real, working controls; see row 44 |
| 38 | Typography | COMPLETE | SOURCE_ONLY | `font`/`type_scale` fields, functional |
| 39 | Spacing / density | PARTIAL | RUNTIME_VERIFIED | Site-wide only; no per-section spacing |
| 40 | Shape/radius | COMPLETE (site-wide) | RUNTIME_VERIFIED | Real slider control |
| 41 | Motion | COMPLETE | SOURCE_ONLY | Global `motion` field + per-section `motion_style` field both exist |
| 42 | Product-card configuration — visibility toggles (brand/price/badge/wishlist/quick-add) | NOT_IMPLEMENTED | RUNTIME_VERIFIED | All hardcoded-on in the single shared `product_card.html` |
| 43 | Product-card configuration — image ratio/fit/hover | PARTIAL | RUNTIME_VERIFIED | Fit/hover real but site-wide; ratio hardcoded everywhere |
| 44 | Product-card configuration — radius/border/shadow | PARTIAL | RUNTIME_VERIFIED | Radius+shadow real (site-wide, shadow via Template only); border has no toggle, always on |
| 45 | Product-card configuration — secondary-image behavior | BACKEND_ONLY (dead) | RUNTIME_VERIFIED | `card_image_crossfade` toggle exists in UI, matching CSS classes never emitted by any template — zero effect |
| 46 | Product-card configuration — products per row (desktop/mobile) | PARTIAL | RUNTIME_VERIFIED | Real for 2/8 section types, hardcoded for the other 6 |
| 47 | Media selection (reference picker) | PARTIAL | RUNTIME_VERIFIED | Real tenant-scoped picker for section-level product/category/brand/collection destinations; **raw numeric ID entry with no tenant check** for Brand/Collection specifically on the Hero-Slide/Banner media form |
| 48 | Internal destination picker | PARTIAL | RUNTIME_VERIFIED | Same split as row 47 — category/product real everywhere; brand/collection real at section level, raw-ID at media-item level |
| 49 | External URL controls | COMPLETE | SOURCE_ONLY | `destination_type=external` + URL field + new-tab checkbox present in `section_destination_fields.html` |
| 50 | Mobile-specific media (alternate image per device) | NOT_IMPLEMENTED | SOURCE_ONLY | No such field anywhere in `validate_responsive_settings` or any section schema |
| 51 | Device visibility (per-section) | COMPLETE | RUNTIME_VERIFIED | See row 16 |
| 52 | Page composition — Home | COMPLETE | RUNTIME_VERIFIED | Fully free-form |
| 53 | Page composition — Product Detail | COMPLETE | RUNTIME_VERIFIED | Distinct, reorderable, locked main block |
| 54 | Page composition — Listing | COMPLETE (shared block with Search, judged acceptable) | RUNTIME_VERIFIED | See row 55 |
| 55 | Page composition — Search | NOT_REQUIRED (to be more distinct from Listing) | RUNTIME_VERIFIED | Both page types intentionally share `product_listing`; this matches their near-identical real-world purpose — flagged for owner awareness only, not a defect |
| 56 | Page composition — Collection | COMPLETE | RUNTIME_VERIFIED | Distinct header + locked products block |
| 57 | Page composition — Cart | COMPLETE | RUNTIME_VERIFIED | Distinct items + summary, both locked |
| 58 | Legacy Template system — merchant mental model simplification | UI_MISSING (needs collapsing) | BROWSER_VERIFIED | 5 separate concept cards exist today (Template/Palette/Colors/Advanced/Preset) instead of the target 3 (Preset/Palette/Design); Template silently conflicts with Preset on shared fields |

---

## Summary counts

| Classification | Count |
|---|---|
| COMPLETE | 27 |
| PARTIAL | 13 |
| UI_MISSING | 5 |
| BACKEND_ONLY | 1 |
| NOT_IMPLEMENTED | 6 |
| NOT_REQUIRED | 1 |

## P0-relevant rows (feed directly into the implementation plan)

Rows 6, 14, 15, 23–28, 42–46, 47/48 (media-form tenant-ID gap), 58.
