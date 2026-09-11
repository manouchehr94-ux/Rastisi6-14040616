# Phase 5 — 67 Reference Family Production Map

Date: 2026-09-11. Source: Phase-5 Design Expansion Charter, Appendix A. Read-only discovery; no
production code changed. Evidence tiers: **SOURCE-VERIFIED** = read directly this session (file:line).
Prior docs (`a8_component_*`, `STOREFRONT_BUILDER_V2_REUSE_MATRIX.md`, `final_closure_pack/03`/`07`) are
pre-Phase-4-closure/mid-Phase-4 evidence and are marked stale below wherever Phase 7/8 changed the
picture.

**Important:** the Charter's `67 × 10 = 670` figure is an external reference-generation target, **not**
a production-import requirement (Charter §6, §14). This table reports actual current repository state
only — it does not recommend building 670 variants, and several MISSING rows are arguably *correctly*
absent given the platform's explicit "no fabricated commerce truth" stance (see notes).

The living system today is `section_registry.py` (36 section types) + `global_region_registry.py`
(Header/Footer/Mobile-Nav global regions) + `appearance_config`/`header_config`/`footer_config` on
`StorefrontLayoutVersion`, with R4 (`settings_schema.py`/`r4_mutation_service.py`) as the
schema-validated merchant-editing layer. R4 `SettingsSchema` coverage grew from 4 section types
(pre-Phase-8) to **18 of 36** section types in Phase 7/8 (per-section card settings, layout settings,
composable header/footer extra blocks). Phase 8's own status line is `IMPLEMENTATION_COMPLETE /
BROWSER_VERIFIED / OWNER_HEAVY_GATE_PENDING` — an owner-run gate is still outstanding, so treat neither
"fully frozen" nor "fully certified" as accurate.

## Full 67-family table

| # | Family | Status | Registered variant count | Production usage today | R4/schema config | Responsive | RTL | Accessibility | Needed for 50-template target |
|---|---|---|---|---|---|---|---|---|---|
| 1 | HDR Header | EXISTS BUT NEEDS REPAIR-EXPANSION | 10 wired `GlobalVariantDefinition`s (`global_region_registry.py:184-259`); **11 more header partial `.html` files exist on disk but are orphaned** — not wired into `GLOBAL_HEADER_REGION.variants`, not merchant-selectable | Rendered on every route; 12/50 recipes use a Header ref | `header_config` composable: 6 toggles + up to 6 ordered extra blocks (`layout_service.py:113`, Phase 8 P0-3). Variant choice itself is a legacy config key, not an R4 section schema | VERIFIED GOOD (10 wired variants; mobile-overflow bug fixed in Phase 8) | VERIFIED GOOD (site-wide `dir="rtl"`) | LIKELY GAP — partial aria coverage, no confirmed keyboard-trap/focus proof | Yes — core, heavy use |
| 2 | MM Mega Menu | EXISTS BUT NEEDS REPAIR-EXPANSION | 1: `mega_menu.none.v1` only; a shared `category_mega_menu.html` partial exists but is not an independent family/data-contract | Whatever the header variant's dropdown renders | NO SCHEMA — no independent Mega-Menu family (unchanged by Phase 8) | UNKNOWN | VERIFIED GOOD | UNKNOWN | No — reference-only per charter; real dropdown covers the practical need |
| 3 | ANN Announcement Bar | EXISTS & REUSE | 1 default renderer, 0 explicit variants; also toggleable inside `header_config` | 4/50 recipes | NO SCHEMA (legacy only) | VERIFIED GOOD | VERIFIED GOOD | UNKNOWN | Yes |
| 4 | SRCH Search UI | EXISTS & REUSE (embedded in Header) | Not standalone — built into 4 of 10 header variants, wired to real `catalog:product-list?q=` | Live on any search-bearing header | NO SCHEMA as independent family | UNKNOWN | VERIFIED GOOD | UNKNOWN | Yes, via Header reuse |
| 5 | NAV Desktop Primary Navigation | EXISTS & REUSE | Real `Menu`/`MenuItem` domain model, store-scoped, 2-level nesting | Rendered inside header on every route | R4: NO — routed to the separate live Menu editor, not Draft/Publish-scoped | UNKNOWN | VERIFIED GOOD | UNKNOWN | Yes |
| 6 | MDR Mobile Navigation Drawer | MISSING & BUILD | 0 — no dedicated mobile-primary-nav hamburger/drawer markup found | UNKNOWN | NO SCHEMA | UNKNOWN | N/A | UNKNOWN | Yes — distinct from Bottom Nav (#7), which IS built |
| 7 | BNAV Mobile Bottom Navigation | EXISTS & REUSE | 9 variants (`global_region_registry.py:402-429`) — matches doc count exactly | 43/50 recipes (combined) | Legacy config key, no dedicated R4 schema | VERIFIED GOOD (safe-area/RTL/live cart-count wiring) | VERIFIED GOOD | LIKELY GOOD (highest aria density of any family checked) | Yes |
| 8 | BCR Breadcrumbs | EXISTS & REUSE | Not a registry entry — hardcoded page-shell pattern across 6+ templates | Live on every listing/PDP/collection/cart page | NO SCHEMA (structural) | UNKNOWN | VERIFIED GOOD | UNKNOWN | Yes (already ubiquitous) |
| 9 | HERO Hero Section | EXISTS & REUSE | `hero_banner`: 6 template paths, matches doc count exactly | 45/50 recipes | R4 YES — `HERO_BANNER_SCHEMA` | VERIFIED GOOD | VERIFIED GOOD | UNKNOWN | Yes |
| 10 | SLD Image/Content Slider | EXISTS BUT NEEDS REPAIR-EXPANSION | `image_slider`: 0 explicit variants, delegates to Hero's loader | 0/50 recipes | R4 YES (`IMAGE_SLIDER_SCHEMA`) but zero production use | VERIFIED GOOD | VERIFIED GOOD | UNKNOWN | Optional — schema exists, unused |
| 11 | PROMO Promo Banner/Strip | EXISTS & REUSE | `single_banner` + `multi_banner`, 0 explicit variants each | 0/50 each | R4 YES (both schema'd) | VERIFIED GOOD | VERIFIED GOOD | UNKNOWN | Reference-only; zero recipe use today |
| 12 | PCT Promo Cards/Campaign Tiles | EXISTS & REUSE | `promo_cards`: 0 explicit variants | 0/50 | R4 YES (`PROMO_CARDS_SCHEMA`) | VERIFIED GOOD | VERIFIED GOOD | UNKNOWN | Reference-only; zero recipe use |
| 13 | RIB Ribbon/Badge/Corner Label | EXISTS & REUSE | 2: `badge.none.v1`, `badge.sale.v1` | Part of the shared product-card partial | R4: badge visibility is part of Phase 8's per-section card settings, not a standalone schema | LIKELY GOOD | VERIFIED GOOD | UNKNOWN | Yes |
| 14 | CDN Countdown/Limited-Time Offer | MISSING & BUILD | 0 — explicitly excluded by design ("claims cannot be represented until commerce truth exists") | None | NO SCHEMA | N/A | N/A | N/A | No — deliberately excluded without real deadline data, not an oversight |
| 15 | QLK Quick Links | EXISTS & REUSE | `quick_links`: 0 explicit variants | 0/50 | R4 YES (`QUICK_LINKS_SCHEMA`) | VERIFIED GOOD | VERIFIED GOOD | UNKNOWN | Reference-only; zero recipe use |
| 16 | TRUST Trust/Service Features | EXISTS & REUSE | `trust_features`: 0 explicit variants | 11/50 | R4 YES (`TRUST_FEATURES_SCHEMA`) | VERIFIED GOOD | VERIFIED GOOD | UNKNOWN | Yes |
| 17 | BRAND Brand/Logo Strip | EXISTS & REUSE | `brand_carousel`: 3 variants | 2/50 | R4 YES (`BRAND_CAROUSEL_SCHEMA`) — platform's strongest schema-backed foundation | VERIFIED GOOD | VERIFIED GOOD | UNKNOWN | Yes |
| 18 | PC Product Card | EXISTS & REUSE | 16 presentation styles, one shared `product_card.html` dispatcher | Universal | R4 YES (Phase 8 P0-2): per-section card settings across 9 section types (brand/price/badge/wishlist/quick-add visibility, image ratio, columns 2-8) | VERIFIED GOOD | VERIFIED GOOD | UNKNOWN | Yes |
| 19 | PGRID Product Grid/Listing | EXISTS & REUSE | `product_listing` section, real filter form + sort + `hx-get` | 50/50 | R4: NO dedicated schema for the section itself (card/column settings apply via P0-2) | VERIFIED GOOD | VERIFIED GOOD | UNKNOWN | Yes |
| 20 | PRAIL Product Carousel/Rail | EXISTS & REUSE | `product_section`: 3 modes (carousel/grid/campaign_band) | 40/50 | R4 YES (`PRODUCT_SECTION_SCHEMA`) | VERIFIED GOOD | VERIFIED GOOD | UNKNOWN | Yes |
| 21 | CATC Category Card | EXISTS & REUSE | `category_grid`: 11 modes | 49/50 | R4 YES (`CATEGORY_GRID_SCHEMA`) | VERIFIED GOOD | VERIFIED GOOD | UNKNOWN | Yes |
| 22 | COLC Collection Card | EXISTS & REUSE | `collection_tiles`: 2 variants | 0/50 | R4 YES (`COLLECTION_TILES_SCHEMA`) | VERIFIED GOOD | VERIFIED GOOD | UNKNOWN | Reference-only; zero recipe use, real domain model backs it |
| 23 | COMP Product Comparison | MISSING & BUILD | 0 — confirmed absent | None | NO SCHEMA | N/A | N/A | N/A | No — genuinely new capability, not a reuse question |
| 24 | REC Recently Viewed/Recommendation Rail | MISSING & BUILD | 0 — no real tracking/recommendation service found | None | NO SCHEMA | N/A | N/A | N/A | No — `related_products` (PDP-only, domain-backed) is the nearest capability, not equivalent |
| 25 | FLT Filter UI | EXISTS & REUSE (embedded) | Real accordion + `hx-get` form inside `product_listing`, shared identically across Listing/Search | 50/50 | R4: NO dedicated schema | VERIFIED GOOD | VERIFIED GOOD | UNKNOWN | Yes |
| 26 | SORT Sort UI | EXISTS & REUSE (embedded) | Real `<select name="sort">` | 50/50 | R4: NO dedicated schema | VERIFIED GOOD | VERIFIED GOOD | UNKNOWN | Yes |
| 27 | PAGE Pagination/Load More | EXISTS & REUSE (embedded) | Shares the `product_listing` fragment pipeline | 50/50 (assumed, same section) | R4: NO dedicated schema | UNKNOWN | UNKNOWN | UNKNOWN | Yes |
| 28 | LPH Listing Page Header | EXISTS & REUSE | `listing_header.html`, includes breadcrumb | 50/50, shared with Search | NO SCHEMA (page-shell partial) | UNKNOWN | VERIFIED GOOD | UNKNOWN | Yes |
| 29 | SRH Search Results Header | EXISTS & REUSE (shared with Listing, by explicit design) | Same `product_listing`/`listing_header` pipeline | 50/50 | NO SCHEMA | UNKNOWN | VERIFIED GOOD | UNKNOWN | Deliberate reuse, documented decision, not a gap |
| 30 | EMPTY Empty/No-Result State | EXISTS & REUSE | Real `<div class="plp-empty">` | Live on 0-result queries | NO SCHEMA (not merchant-configurable copy) | UNKNOWN | VERIFIED GOOD | UNKNOWN | Yes |
| 31 | PDPG Product Media Gallery | EXISTS & REUSE | `product_main` section | 50/50 | R4: NO dedicated schema (domain-owned content) | VERIFIED GOOD | VERIFIED GOOD | UNKNOWN | Yes |
| 32 | PDPB Product Info/Buy Box | EXISTS & REUSE | Same `product_main` section | 50/50 | NO SCHEMA | VERIFIED GOOD | VERIFIED GOOD | UNKNOWN | Yes |
| 33 | VAR Variant/Option Selector | EXISTS & REUSE | Real Alpine swatch selector with availability logic, backed by real FKs | 50/50 | NO SCHEMA (domain-driven) | UNKNOWN | UNKNOWN | UNKNOWN | Yes |
| 34 | ATC Quantity+Add-to-Cart | EXISTS & REUSE | Real quantity input + submit with live stock/purchasability text | 50/50 | NO SCHEMA | UNKNOWN | UNKNOWN | UNKNOWN | Yes |
| 35 | SATC Sticky Add-to-Cart | MISSING & BUILD | 0 — explicitly acknowledged as an un-built P1 candidate in `PHASE_8_REPORT.md` Q13 | None | NO SCHEMA | N/A | N/A | N/A | Genuinely missing, explicit backlog item |
| 36 | PDT Product Tabs/Accordion | EXISTS BUT NEEDS REPAIR-EXPANSION | `product_description` section exists; no accordion/tab-role markup found — content renders flat/stacked | 50/50 (as `product_description`) | NO SCHEMA | UNKNOWN | UNKNOWN | UNKNOWN | Yes, but currently flat content, not the tabbed interaction the name implies |
| 37 | PDTX Product Trust/Delivery Module | EXISTS BUT NEEDS REPAIR-EXPANSION | Present but **hardcoded** Persian strings, not merchant-editable, duplicating `trust_features`' purpose PDP-specifically | 50/50 (part of `product_main`) | NO SCHEMA | UNKNOWN | VERIFIED GOOD | UNKNOWN | Yes, but hardcoded claims are a real content-truth risk |
| 38 | RTE Rich Text/Editorial | EXISTS & REUSE | `rich_text`: 0 explicit variants | 7/50 | R4 YES (`RICH_TEXT_SCHEMA`, sanitized body_html only, no merchant HTML/CSS/JS execution) | VERIFIED GOOD | VERIFIED GOOD | UNKNOWN | Yes |
| 39 | BLOG Blog/Editorial Card | EXISTS & REUSE | `blog_posts`: 0 explicit variants | 0/50 | R4: NO schema | VERIFIED GOOD | VERIFIED GOOD | UNKNOWN | Reference-only; zero recipe use |
| 40 | TEST Testimonials/Reviews | EXISTS & REUSE | `testimonials`: 0 explicit variants | 6/50 | R4 YES (`TESTIMONIALS_SCHEMA`) | VERIFIED GOOD | VERIFIED GOOD | UNKNOWN | Yes |
| 41 | FAQ FAQ | EXISTS & REUSE | `faq`: 0 explicit variants | 0/50 | R4 YES (`FAQ_SCHEMA`, real Q&A items, not hardcoded demo text) | VERIFIED GOOD | VERIFIED GOOD | UNKNOWN | Reference-only; zero recipe use despite being schema-ready |
| 42 | VID Video Section | EXISTS & REUSE | `video_section`: 0 explicit variants | 0/50 | R4 YES (`VIDEO_SECTION_SCHEMA`) | VERIFIED GOOD | VERIFIED GOOD | UNKNOWN | Reference-only; zero recipe use |
| 43 | STORY Image+Text Story | EXISTS & REUSE | `image_text` (2 variants) + `story_rail` (0 variants) | `image_text` 17/50; `story_rail` 1/50 | `image_text`: R4 YES. `story_rail`: NO schema, media-form gap (add/edit not a working single-image uploader) | VERIFIED GOOD | VERIFIED GOOD | UNKNOWN | Yes (image_text); story_rail usable with a known media-upload gap |
| 44 | STAT Stats/Social Proof | MISSING & BUILD | 0 — no dedicated stats/counter/social-proof section found | None | NO SCHEMA | N/A | N/A | N/A | Nearest capability is `trust_features`, a different presentation |
| 45 | CARTI Cart Item Row | EXISTS & REUSE | `cart_items` section | 50/50 | NO SCHEMA (domain content) | VERIFIED GOOD | VERIFIED GOOD | UNKNOWN | Yes |
| 46 | CARTS Cart Summary/Totals | EXISTS & REUSE | `cart_summary` section | 50/50 | NO SCHEMA | VERIFIED GOOD | VERIFIED GOOD | UNKNOWN | Yes |
| 47 | COUP Coupon/Promotion Entry | EXISTS & REUSE (cart domain feature, not a Builder section) | Real `coupon_service.py`, coupon fields on `Cart` model | Live on the real cart flow | NO SCHEMA — correctly kept out of the section registry (commerce logic, not presentation) | UNKNOWN | UNKNOWN | UNKNOWN | Yes, correctly a domain feature |
| 48 | GOAL Free-Shipping Goal | MISSING & BUILD | 0 — no progress-bar/threshold component found in cart | Announcement bar can show a static free-shipping message, not a progress/goal component | NO SCHEMA | N/A | N/A | N/A | Genuinely missing as a cart-page component |
| 49 | XSELL Cross-Sell Module | MISSING & BUILD | 0 — no related/cross-sell/upsell markup in cart templates | None in cart flow (PDP has `related_products`, different purpose) | NO SCHEMA | N/A | N/A | N/A | Genuinely missing specifically in the cart context |
| 50 | FTR Footer | EXISTS & REUSE | 8 variants, matches doc count exactly | 8/50 refs | `footer_config`: 9 toggles + up to 4 ordered extra blocks (Phase 8 P0-4) | VERIFIED GOOD | VERIFIED GOOD | UNKNOWN | Yes |
| 51 | NEWS Newsletter Block | EXISTS & REUSE | `newsletter`: 0 explicit variants | 12/50 | R4 YES (`NEWSLETTER_SCHEMA`) | VERIFIED GOOD | VERIFIED GOOD | UNKNOWN | Yes |
| 52 | CONTACT Contact/Store Info | EXISTS & REUSE (footer-embedded) | No dedicated section; lives inside footer content/live store identity | Wherever footer renders it | NO SCHEMA as standalone | UNKNOWN | VERIFIED GOOD | UNKNOWN | Reasonable reuse via Footer, not a hard gap |
| 53 | SOC Social Links | EXISTS & REUSE | `footer_config` `show_social` toggle + social extra-block reading live identity source | Wherever footer renders it | R4 YES (Phase 8 P0-4) | VERIFIED GOOD | VERIFIED GOOD | UNKNOWN | Yes |
| 54 | FLOAT Floating Action/Back-to-Top | MISSING & BUILD | 0 — no back-to-top/floating-action markup found | None | NO SCHEMA | N/A | N/A | N/A | Genuinely missing |
| 55 | MODAL Modal/Dialog | EXISTS BUT NEEDS REPAIR-EXPANSION | Only Builder-admin modals found (not public-storefront-facing) | Merchant-editing UI only | NO SCHEMA | UNKNOWN | UNKNOWN | UNKNOWN | No public-facing modal/quick-view pattern confirmed — treat as effectively missing for storefront use |
| 56 | DRAW Drawer/Off-Canvas Panel | MISSING & BUILD | Same finding as MDR (#6) — no off-canvas markup located | UNKNOWN | NO SCHEMA | N/A | N/A | N/A | Not located |
| 57 | TOAST Toast/Notification | MISSING & BUILD | 0 | None | NO SCHEMA | N/A | N/A | N/A | Not located |
| 58 | TIP Tooltip/Popover | MISSING & BUILD | 0 | None | NO SCHEMA | N/A | N/A | N/A | Not located |
| 59 | TAB Tabs (generic) | MISSING & BUILD | See #36 — one orphaned `category_tabs.html` file only, not a general-purpose widget | Orphaned template only | NO SCHEMA | UNKNOWN | UNKNOWN | UNKNOWN | Nearest asset is dead code |
| 60 | ACC Accordion (generic) | EXISTS & REUSE (one real instance, not generalized) | Native `<details class="plp-filters">` disclosure | 50/50 (filter panel) | NO SCHEMA | VERIFIED GOOD | VERIFIED GOOD | LIKELY GOOD (native disclosure carries built-in AT support) | Yes for filter use-case; not generalized to PDT (#36) |
| 61 | SKEL Skeleton/Loading State | MISSING & BUILD | 0 | None | NO SCHEMA | N/A | N/A | N/A | Not located |
| 62 | MOT Motion Recipe | EXISTS & REUSE | 3 registered values (`motion.none/.subtle/.dynamic`) as global field, plus per-section `motion_style` | Global, platform-wide | R4 YES (global Advanced-panel control, Phase 8 P0-7) | N/A | N/A | UNKNOWN (reduced-motion respect not independently verified) | Yes |
| 63 | HOV Card Hover/Focus | EXISTS & REUSE | Site-wide `card_hover` control | Global | R4 YES (site-wide, not yet per-section) | N/A | N/A | UNKNOWN | Yes, though not per-section-overridable yet |
| 64 | REV Section Reveal/Scroll Entrance | MISSING & BUILD | 0 — no IntersectionObserver/scroll-reveal implementation found | None | NO SCHEMA | N/A | N/A | N/A | Not located |
| 65 | MTRANS Menu/Drawer Transition | MISSING & BUILD | 0 — blocked on MDR/DRAW being built first | None | NO SCHEMA | N/A | N/A | N/A | Blocked on #6/#56 |
| 66 | STRANS Slider/Carousel Transition | EXISTS BUT NEEDS REPAIR-EXPANSION | Hero/product_section/brand_carousel have real autoplay/interval/arrows/dots controls, but no explicit CSS transition-style axis confirmed as a separate control | Wherever those sections render (widely used) | R4 fields exist for playback mechanics, not transition style specifically | UNKNOWN | UNKNOWN | UNKNOWN | Playback exists; the charter's specific "transition" axis is unconfirmed as separate |
| 67 | THEME Theme Accent/Decorative Overlay Kit | MISSING & BUILD (as a distinct configurable kit) | 0 — no generic decorative-overlay kit found; Hero's own `overlay` variant name is a different, single-purpose thing | Only as one specific Hero variant name | NO SCHEMA | N/A | N/A | N/A | The real appearance system (palette/radius/density/motion/type-scale) is the nearest capability but is not itself a decorative-overlay kit |

## Summary counts

| Status | Count | Families |
|---|---:|---|
| EXISTS & REUSE | 44 | ANN, SRCH, NAV, BNAV, BCR, HERO, SLD, PROMO, PCT, RIB, QLK, TRUST, BRAND, PC, PGRID, PRAIL, CATC, COLC, FLT, SORT, PAGE, LPH, SRH, EMPTY, PDPG, PDPB, VAR, ATC, RTE, BLOG, TEST, FAQ, VID, STORY, CARTI, CARTS, COUP, FTR, NEWS, CONTACT, SOC, ACC, MOT, HOV |
| EXISTS BUT NEEDS REPAIR-EXPANSION | 6 | HDR, MM, PDT, PDTX, MODAL, STRANS |
| MISSING & BUILD | 17 | MDR, CDN, COMP, REC, SATC, STAT, GOAL, XSELL, FLOAT, DRAW, TOAST, TIP, TAB, SKEL, REV, MTRANS, THEME |

44 + 6 + 17 = 67.

Several EXISTS & REUSE rows carry a real caveat: SLD, PROMO, PCT, QLK, BLOG, VID, FAQ, COLC are all
schema-ready but sit at **0 Ready-recipe usage today** (reference-only in practice); CONTACT and SRH
are reuse *by deliberate documented design decision* (sharing Footer/Listing rather than a standalone
build), not because a dedicated implementation exists under those names.

Several MISSING rows are arguably *correctly* absent given the platform's explicit "no fabricated
commerce truth" stance (CDN countdown, STAT, GOAL, XSELL) rather than oversights — do not treat every
MISSING row as an unconditional build target.

Accessibility evidence is thin platform-wide: no dedicated a11y audit or automated check was found in
this pass; every UNKNOWN in that column is a real verification gap, not a claim of failure. RTL is the
one dimension with strong, uniform evidence: `dir="rtl" lang="fa"` is set once, globally, in
`templates/base.html:2`, so every family inherits real RTL layout direction by default — that is not
the same as confirming every family's icons/animations/asymmetric layout are individually RTL-correct.
