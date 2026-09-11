# RASTISI — Phase 5 Design Expansion Charter

**Document status:** APPROVED FOR PHASE 5 START  
**Product Owner:** Product Owner  
**Date:** 2026-09-11  
**Purpose:** Scope lock, architecture guardrails, execution boundary, and Definition of Done for Phase 5.

> **One-sentence closure rule:** If 50 materially different storefront templates, the required design components, Storefront Showcase, complete PDP/browse/cart/content surfaces, reversible themes, simple R4 controls, and full QA are implemented on the existing canonical architecture and approved by the Product Owner, Phase 5 is closed.

> **Critical boundary:** This document is not production code. External AI Design Factory outputs are references only and must never be imported directly as production authority.

## 1. Purpose

This charter locks the official Phase 5 — Design Expansion boundary: what must be built, what must not be built, how it must fit the real RastiSi architecture, and what conditions make `PHASE 5 CLOSED` valid.

## 2. Start gate

- Phase 5 starts only after an official Phase 4 checkpoint is accepted.
- Preserve the canonical flow: `R4 Editor -> Canonical Services -> One Draft Lifecycle / History -> One Shared Renderer -> Preview / Publish / Public Storefront`.
- Audit the repository before production changes so existing capabilities are reused instead of duplicated.
- Master Brief, Design Gallery, and AI outputs are reference inputs only.

## 3. Mandatory Phase 5 outcomes

1. **50 real storefront templates:** materially different composition, hierarchy, density, navigation, merchandising, responsive behavior and visual rhythm — not 50 recolors.
2. **Curated design component set:** implement only the production variants needed to support the templates and merchant experience. The `67 × 10 = 670` target belongs to reference generation, not production import.
3. **Storefront Showcase Section:** one reusable section that can show Categories, Products, Collections or Brands through multiple materially different layouts.
4. **Complete product detail experience:** Media Gallery, Buy Box, Variant Selector, Quantity/Add-to-Cart, Sticky Purchase, Product Details and Trust/Delivery.
5. **Listing/search/browse:** Filters, Sort, Pagination/Load More, Listing Header, Search Summary, Empty/Loading/Error states.
6. **Cart/conversion:** Cart Item, Summary, Coupon, Free-shipping Goal and Cross-sell.
7. **Editorial/content:** Rich Text, Blog, Testimonials, FAQ, Video, Story, Stats, Newsletter, Contact and Social.
8. **Reversible seasonal/event themes:** Nowruz, Yalda, Valentine, Ramadan, Eid, Iranian/Islamic occasions, Sale and Premium/Luxury overlays.
9. **RTL/responsive/accessibility/motion:** Persian-first, RTL-first, three target viewports, keyboard/focus, touch usability and reduced motion.
10. **Simple R4 merchant controls:** variant/theme/showcase choices should be visually understandable and not expose architectural complexity.
11. **Canonical architecture preserved:** no second renderer, persistence, lifecycle, media authority, template authority or source of truth.
12. **QA and evidence:** automated tests, browser QA, responsive/RTL/accessibility checks, visual distinctness review, evidence, and Product Owner approval.

## 4. Storefront Showcase Section

The Showcase is a single canonical merchandising section, complete in capability but simple to use.

| Setting | Required behavior |
|---|---|
| Content type | Categories / Products / Collections / Brands |
| Selection | Manual or supported canonical automatic source |
| Layout | Multiple visually distinct layout variants |
| Simple controls | Title, count, View All, content selection, layout, essential mobile behavior |
| Surfaces | Home, category page, brand page, campaign landing, sale page, seasonal landing |
| Shopper-visible | Yes — it is part of the public storefront |
| Data ownership | Existing Catalog/Product/Collection/Brand domains |

A template may compose showcase sections such as: `Hero -> Popular Categories -> Offers -> Selected Brands -> Featured Collection -> Best Sellers -> Trust/Story -> Footer`. The ten Gallery examples are choices, not ten sections that must appear together.

### Product detail responsibility split

- **PDPG — Product Media Gallery:** media only — main image, thumbnails, gallery/collage, zoom and media navigation.
- **PDPB — Product Information / Buy Box:** decision information — title, price, options, availability, short copy, trust context and CTA context.
- **ATC — Quantity + Add to Cart:** execution controls — quantity, add-to-cart and mobile purchase controls.

These three may compose one PDP, but must not collapse into three visually identical renderers.

## 5. Definition of 50 Template DNA

- A template is a composition of canonical capabilities, not a separate app or renderer.
- Even with the same palette and font, templates must remain materially distinguishable.
- Meaningful differences may come from navigation, hero composition, merchandising sections, grid geometry, card anatomy, footer, density and mobile transformation.
- Shared capabilities must be reused; per-template duplicated application logic is not acceptable.
- Themes overlay the DNA and must be reversible.
- Product Owner must be able to compare all 50 templates visually before final acceptance.

## 6. Meaning of 67 families and 670 variants

The Master Brief defines **67 reference families × 10 variants = 670 reference variants per AI** to maximize design exploration. This is **not** a production import requirement. Production selects and implements the strong, necessary variants that fit the canonical system.

Valid pipeline:

`External AI Reference -> Review / Shortlist -> Canonical Contract Mapping -> Claude Code / Engineering Implementation -> Tests -> Browser QA -> Product Owner Approval`

## 7. Non-negotiable architecture rules

> **One concept = one canonical owner.**

- R4 stays the main merchant editor.
- Canonical services remain the mutation/business-semantic owners.
- One Draft lifecycle/history remains authoritative.
- One shared renderer remains the rendering path for preview/publish/public.
- Catalog, pricing, inventory, cart, orders, auth, tenant and media remain domain-owned.
- No second renderer, second persistence, second lifecycle, duplicate authority/registry or parallel editor.
- Unknown repository details must be discovered, not invented.

## 8. R4 merchant UX

The merchant experience should be powerful but simple: add a section, choose a visual variant from previews, select content, set a small number of meaningful controls, and rely on strong defaults. Storefront Showcase should expose only content type, content selection/source, layout, title, count, View All and truly necessary responsive options.

## 9. UI quality targets

- **RTL/Persian:** RTL primary; logical CSS properties; correct directional icons/interactions; long Persian labels and prices must survive.
- **Responsive:** 1440×900, 768×1024 and 390×844; mobile is a deliberate transformation, not just desktop shrinkage; no unintended horizontal overflow.
- **Accessibility:** semantic controls, keyboard operation, visible focus, accessible names, state exposure, touch targets and sufficient contrast.
- **Motion:** `prefers-reduced-motion`; purposeful motion; no essential information dependent on animation.

## 10. Theme overlay model

Themes are reversible overlays: Neutral, Nowruz, Yalda, Valentine, Ramadan, Eid al-Fitr, Eid al-Ghadir/another Islamic celebration, Iranian cultural occasion, high-energy sale, and premium/luxury. They may change accents, motifs, decoration, campaign copy slots, ribbons, hero decoration and motion accents, but must not silently replace the underlying information architecture.

## 11. Recommended execution order

1. Repository discovery and Phase 4 baseline.
2. Production capability map against the 67 reference families.
3. High-impact primitives: header/navigation/hero/product cards/grids/rails/footer/mobile navigation.
4. Canonical Storefront Showcase.
5. Browse + PDP + cart/conversion.
6. Editorial + utility/system UI.
7. Theme overlays + motion systems.
8. Build 50 Template DNA compositions.
9. Expose simple R4 controls.
10. Full cross-template QA + curation.
11. Official Phase 5 closure checkpoint.

## 12. QA and evidence required

- Architecture audit: no parallel authority/render/persistence/lifecycle.
- Automated focused tests + relevant regression suite + system/migration checks where applicable.
- Browser QA on R4/preview/public paths.
- Responsive QA at 1440×900, 768×1024, 390×844.
- RTL primary QA + reasonable LTR sanity where components are bidirectional.
- Accessibility: keyboard, focus, semantics, state, dialog/drawer behavior, reduced motion.
- Visual distinctness review for the 50 templates and key variants.
- Evidence: screenshots, test reports, status/coverage, known limitations.

## 13. Phase 5 Definition of Done

Phase 5 may be declared closed only when **all** are true:

- [ ] ۵۰ Template production-ready وجود دارند و تفاوت آن‌ها صرفاً palette/font/radius نیست.
- [ ] Templateها از همان معماری canonical و Shared Renderer استفاده می‌کنند.
- [ ] Variantهای کلیدی Header/Mega Menu/Hero/Product Card/Grid/Rail/Footer/Mobile Nav و سایر اجزای لازم پیاده‌سازی شده‌اند.
- [ ] Storefront Showcase برای Categories / Products / Collections / Brands با چند Layout واقعی در R4 قابل تنظیم و در Public Storefront قابل مشاهده است.
- [ ] Product Media Gallery، Buy Box و Quantity/Add-to-Cart سه مسئولیت واضح و بصری متمایز دارند.
- [ ] Listing/Search/Filter/Sort/Pagination و empty/loading/error states کامل هستند.
- [ ] Product Detail flow کامل و responsive است.
- [ ] Cart/Conversion surfaces ضروری کامل هستند.
- [ ] Editorial/content sections موردنیاز merchant در دسترس‌اند.
- [ ] Theme Overlayهای تعیین‌شده برگشت‌پذیر و غیرمخرب هستند.
- [ ] RTL/Persian، Desktop/Tablet/Mobile، keyboard/focus و reduced-motion برای scope پذیرفته‌شده QA شده‌اند.
- [ ] R4 تجربه ساده‌ای برای انتخاب Template/Variant/Showcase/Theme فراهم می‌کند.
- [ ] هیچ source of truth، renderer، persistence، lifecycle، registry authority یا editor موازی ایجاد نشده است.
- [ ] تست‌های مرتبط و regression suite سبز هستند و migration/system checks مشکل ندارند.
- [ ] Browser QA و evidence برای خروجی نهایی ثبت شده است.
- [ ] Product Owner gallery/preview نهایی ۵۰ Template و قابلیت‌های اصلی را دیده و تأیید کرده است.
- [ ] Known limitations باقیمانده یا صفر هستند یا صریحاً خارج از Phase 5 پذیرفته شده‌اند.
- [ ] Checkpoint رسمی Phase 5 ساخته و نگهداری شده است.

> **Closure rule:** Only after every item above is green and the Product Owner gives final approval is `PHASE 5 CLOSED` valid.

## 14. Explicit non-goals

- Importing all 670 AI variants into production.
- Directly copying AI 101–108 code without review/adaptation.
- Creating a second storefront platform, editor, renderer or backend.
- Inventing database models/services/APIs to make a reference demo work.
- Reopening Phase 4 work without a proven regression.
- Building 50 independent applications instead of 50 shared-capability Template DNA compositions.
- Turning seasonal themes into permanent template forks.
- Endless polish outside acceptance criteria; post-closure improvements belong in maintenance/backlog unless scope is explicitly reopened.

## 15. After Phase 5 closes

If all requirements and acceptance criteria in this charter are implemented and approved, RastiSi's major Design Expansion is complete. Later polish, bug fixes, optimization or optional new variants may continue, but another major design phase is not required to achieve the scope defined here unless the Product Owner explicitly defines new scope.

## 16. Kickoff package to preserve

- `RASTISI_PHASE5_DESIGN_EXPANSION_CHARTER` — this document; official scope and closure authority.
- `RASTISI_MASTER_AI_DESIGN_GENERATION_BRIEF` — reference families and design quality requirements.
- `RASTISI_DESIGN_GALLERY_V2.html` — visual Product Owner reference.
- AI audit/reference packages — inspiration and curation only, never production authority.
- A repository-aware Claude Code implementation plan created at kickoff from the official Phase 4 checkpoint.

## Appendix A — 67 reference families

| # | Prefix | Family |
|---:|---|---|
| 1 | `HDR` | Header |
| 2 | `MM` | Mega Menu |
| 3 | `ANN` | Announcement Bar |
| 4 | `SRCH` | Search UI / Search Entry |
| 5 | `NAV` | Desktop Primary Navigation Pattern |
| 6 | `MDR` | Mobile Navigation Drawer |
| 7 | `BNAV` | Mobile Bottom Navigation |
| 8 | `BCR` | Breadcrumbs |
| 9 | `HERO` | Hero Section |
| 10 | `SLD` | Image / Content Slider |
| 11 | `PROMO` | Promo Banner / Promo Strip |
| 12 | `PCT` | Promo Cards / Campaign Tiles |
| 13 | `RIB` | Ribbon / Badge / Corner Label System |
| 14 | `CDN` | Countdown / Limited-Time Offer UI |
| 15 | `QLK` | Quick Links / Shortcut Navigation |
| 16 | `TRUST` | Trust / Service Features |
| 17 | `BRAND` | Brand / Logo Strip |
| 18 | `PC` | Product Card |
| 19 | `PGRID` | Product Grid / Product Listing Composition |
| 20 | `PRAIL` | Product Carousel / Horizontal Product Rail |
| 21 | `CATC` | Category Card |
| 22 | `COLC` | Collection Card |
| 23 | `COMP` | Product Comparison Entry/Card |
| 24 | `REC` | Recently Viewed / Recommendation Rail |
| 25 | `FLT` | Filter UI |
| 26 | `SORT` | Sort UI |
| 27 | `PAGE` | Pagination / Load More / Browse Continuation |
| 28 | `LPH` | Listing Page Header / Category Intro |
| 29 | `SRH` | Search Results Header / Query Summary |
| 30 | `EMPTY` | Empty / No-Result State |
| 31 | `PDPG` | Product Media Gallery |
| 32 | `PDPB` | Product Information / Buy Box |
| 33 | `VAR` | Variant / Option Selector |
| 34 | `ATC` | Quantity + Add-to-Cart Control Group |
| 35 | `SATC` | Sticky Add-to-Cart / Mobile Purchase Bar |
| 36 | `PDT` | Product Tabs / Accordion / Detail Sections |
| 37 | `PDTX` | Product Trust / Delivery / Guarantee Module |
| 38 | `RTE` | Rich Text / Editorial Section |
| 39 | `BLOG` | Blog / Editorial Card |
| 40 | `TEST` | Testimonials / Reviews Highlight |
| 41 | `FAQ` | FAQ |
| 42 | `VID` | Video Section |
| 43 | `STORY` | Image + Text Story Section |
| 44 | `STAT` | Stats / Social Proof Section |
| 45 | `CARTI` | Cart Item Row / Card |
| 46 | `CARTS` | Cart Summary / Totals Panel |
| 47 | `COUP` | Coupon / Promotion Entry |
| 48 | `GOAL` | Free-Shipping / Goal Progress Indicator |
| 49 | `XSELL` | Cross-Sell / Cart Recommendation Module |
| 50 | `FTR` | Footer |
| 51 | `NEWS` | Newsletter / Subscription Block |
| 52 | `CONTACT` | Contact / Store Information Block |
| 53 | `SOC` | Social Links / Community Block |
| 54 | `FLOAT` | Floating Action / Back-to-Top / Utility Control |
| 55 | `MODAL` | Modal / Dialog |
| 56 | `DRAW` | Drawer / Off-Canvas Panel |
| 57 | `TOAST` | Toast / Notification |
| 58 | `TIP` | Tooltip / Popover |
| 59 | `TAB` | Tabs |
| 60 | `ACC` | Accordion |
| 61 | `SKEL` | Skeleton / Loading State |
| 62 | `MOT` | Motion Recipe / Interaction System |
| 63 | `HOV` | Card Hover / Focus Interaction |
| 64 | `REV` | Section Reveal / Scroll Entrance |
| 65 | `MTRANS` | Menu / Drawer Transition |
| 66 | `STRANS` | Slider / Carousel Transition |
| 67 | `THEME` | Theme Accent / Decorative Overlay Kit |

## Appendix B — Claude Code kickoff instruction

> Read this Charter as the Phase 5 scope and Definition of Done. First audit the real repository and build a capability map. Do not directly import external AI code. Do not create a new model/service/renderer/registry before proving the need and identifying the existing canonical owner. Then produce a test-driven implementation plan for Phase 5 from the official Phase 4 checkpoint.

## Appendix C — Decision record

- **Status:** APPROVED / KEEP FOR PHASE 5 KICKOFF
- **Date:** 2026-09-11
- **Change rule:** Major scope changes require explicit Product Owner approval and a new version of this Charter.
