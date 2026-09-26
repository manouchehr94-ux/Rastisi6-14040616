# Storefront Builder V2 — Phase 3 (Home Page Reusable Blocks) Read-Only Gap Audit

**Branch:** `claude/family-visual-fidelity-fix`
**Audited at commit:** `8719307f5a7d2e772ae526f4d72396d8ba69e5d2` (Phase 2 closure HEAD)
**Method:** Full reads of `apps/storefront_builder/section_registry.py`, `services/render_service.py`, `services/section_data_service.py`, `services/bootstrap_service.py`, `templates/storefront_builder/sections/*.html`, `templates/dashboard/storefront_builder/partials/*.html`, `apps/content/models.py`, `apps/content/services.py`, `apps/blog/models.py`, `apps/catalog/views.py`, and the 11 family-specific template subfolders.

---

## 1. Headline finding

`section_registry.py` already has **23** registered section types (not the ~20 the roadmap assumed), and they already cover **11 of the 15** target Home block categories from the master prompt, most with typed settings, per-instance data resolvers, tenant scoping, and responsive/device-visibility support already wired end-to-end. Phase 3 is a gap-closure phase, not a build-from-scratch phase.

## 2. Target block checklist

| # | Block | Status | Notes |
|---|---|---|---|
| 1 | Hero Slider | EXISTS | `hero_banner` (section_registry.py:775) — typed slider settings, HeroSlide-backed |
| 2 | Single Hero / Large Image Banner | EXISTS | `single_banner` (787) — `PromotionalBanner`-backed, already has title/description/button/destination |
| 3 | Two-Banner Row / Multi-Banner Grid | **PARTIAL** | `multi_banner` (793) has zero typed schema (`_passthrough_dict`) and its stored column count is *inert* — template stacks banners vertically regardless of the setting. Closed in this phase (§4.3). |
| 4 | Product Carousel | EXISTS | `product_section` (860), `display_mode="carousel"` |
| 5 | Product Grid | EXISTS | `product_section`, `display_mode="grid"` |
| 6 | Homepage Collection Product Row (independent, reorderable, per-instance) | EXISTS | `product_section` with `data_source="collection"` — confirmed genuinely independent per-instance via `PER_INSTANCE_SECTION_KEYS` cache keying (`render_service.py:324-327,406-410`); duplicating the section with a different collection `source_id` renders correctly independently. No gap. |
| 7 | Category Grid | EXISTS | `category_grid` (799) |
| 8 | Category Carousel | EXISTS | Same type, `display_mode="carousel"` |
| 9 | Brand Carousel / Grid | EXISTS | `brand_carousel` (835) |
| 10 | Story Rail | EXISTS (deliberately single-instance) | `max_instances=1, duplicable=False` is an intentional prior decision (one "discover" rail per page), not a bug — left unchanged |
| 11 | Image + Text | EXISTS | `image_text` (853) |
| 12 | Text Block / Rich Text | EXISTS | `rich_text` (847), sanitized at render |
| 13 | CTA Banner | Covered functionally by #2/#3 | `PromotionalBanner` already has title/description/button/destination; no separate "CTA banner" type needed |
| 14 | Newsletter | **MISSING** | No subscriber model/service/endpoint anywhere. Only a non-functional footer placeholder (`FooterSettings.show_newsletter`, explicitly documented as out of scope in `apps/content/README.md:673-676,716`). Closed in this phase (§4.4) with a deliberately minimal capture, not a marketing/CRM system. |
| 15 | Blog/editorial teaser | **OUT OF SCOPE** | `apps.blog.BlogPost` exists but has **no store FK** — it's a single global blog, not tenant-scoped. Building a per-merchant teaser block against it would require re-architecting `apps.blog` first, which is outside "add a Home block." Not built. |

## 3. Supporting architecture — confirmed solid, no changes needed

- **Product source resolvers** (`section_data_service.py`): all 8 `PRODUCT_SECTION_DATA_SOURCES` values (`collection/category/brand/manual/newest/discounted/best_sellers/most_viewed`) are real, distinct, store-scoped query paths — none is a stub.
- **Tenant scoping**: confirmed in the actual render-time queries (not just validators) for `category_grid`, `brand_carousel`, and `product_section`'s category/brand resolvers — all filter `store=store`.
- **Family isolation**: none of the 23 universal section templates have family-specific override subfolders. The 11 `templates/storefront_builder/partials/families/<family>/` directories only override header/footer/category-page/hero-variant (4 files each) — a separate, already-isolated subsystem. The Phase 3 block library is genuinely universal.
- **MediaAsset**: real placement/dedup/safe-delete model exists (`apps/content/models.py:313-360`, `services.py:174-205`) but is currently write-path/bookkeeping only — every render template still reads the raw `ImageField` directly, not the `MediaAsset` FK. Not a Phase 3 blocker (rendering already works correctly via the ImageFields); flagged as pre-existing debt, not touched here to avoid scope creep into an unrelated media-pipeline refactor.

## 4. Real gaps closed in this phase

### 4.1 Typed destinations: `search` and `cart`

`DestinationType` (`apps/content/models.py`) only had `NONE/CATEGORY/PRODUCT/BRAND/COLLECTION/EXTERNAL` — 6 values. The master prompt's target destination list explicitly includes `search` and `cart`, and neither existed. Added as two new zero-parameter destination types (no `destination_id` needed, matching `NONE`/`EXTERNAL`'s shape) resolving to `catalog:product-list` (existing listing/search route, same as Phase 1B's `search` page-type mapping) and `cart:cart-detail` respectively.

### 4.2 Per-block motion

Motion previously existed only as a **version-level** appearance setting (3 global values, `none/subtle/dynamic`) — no `SectionDefinition` anywhere exposed a per-block motion choice, despite the master prompt explicitly requiring "configuration-driven motion, not family code" at the block level (`none/fade/slide/subtle zoom/hover lift`). Added a shared `motion` settings block (mirroring the existing `_with_responsive`/`_with_destination` wrapper pattern exactly) applied to the section types where hover/entrance motion is visually meaningful (`hero_banner`, `image_slider`, `single_banner`, `multi_banner`, `category_grid`, `brand_carousel`, `product_section`, `collection_tiles`, `promo_cards`, `image_text`) — CSS-only, respects `prefers-reduced-motion`, no new renderer/family code.

### 4.3 `multi_banner` real grid/row layout

Moved `multi_banner` from "column count stored but inert" to `COLUMN_VISUAL_SECTION_KEYS` and implemented an actual CSS grid in `multi_banner.html` driven by the existing `desktop_columns`/`tablet_columns`/`mobile_columns` responsive fields — closes both "Multi-Banner Grid" (N columns) and "Two-Banner Row" (`desktop_columns=2`) from the same primitive, matching this codebase's own stated preference for reusing one configurable type over adding near-duplicate registry entries (see `section_registry.py`'s `image_slider`/`hero_banner` precedent, and the `COLUMN_VISUAL_SECTION_KEYS` docstring inviting exactly this migration).

### 4.4 Newsletter — minimal, real capture block

Added a genuinely functional but deliberately small `newsletter` section type: a new store-scoped `NewsletterSubscriber` model (email + store, unique per store), a subscribe service function reusing Django's built-in email validation, and a public POST endpoint (CSRF-protected, duplicate-safe — resubscribing is a no-op, not an error). No campaign/sending/export/unsubscribe UI was built — that would be a distinct, much larger product surface the master prompt does not ask for ("a strong extensible foundation, not every imaginable block").

## 4.5 Implementation evidence

**Slice 1** (destinations + motion + multi_banner grid): `apps.content.tests.test_destination`, `apps.storefront_builder.tests.test_section_registry`, `apps.storefront_builder.tests.test_responsive_rendering`, `ResponsiveSettingsFormTests`, `RenderedPreviewIntegrationTests` — 205 tests, OK. `manage.py check`: OK. `makemigrations --check --dry-run`: no drift (after migration `0022_alter_heroslide_destination_type_and_more`, a `choices=`-only change, no schema alteration).

**Slice 2** (Newsletter): new `NewsletterSubscriber` model + migration `0023_newslettersubscriber`, `subscribe_to_newsletter` service (reuses Django's `EmailValidator`, `apps.core.services.rate_limit.enforce_rate_limit` — the existing public-form rate limiter also used by OTP/contact-form flows), public `content:newsletter-subscribe` endpoint (POST-only, htmx-first, store-resolved from Host — never a client-supplied tenant ID), `newsletter` section type (single-instance, like `trust_features`/`story_rail`). `apps.content.tests.test_newsletter` + `apps.storefront_builder.tests.test_section_registry` — 135 tests, OK. `apps.storefront_builder.tests.test_views` (`NewSectionTypesRenderedPreviewTests`, `NewSectionTypesSettingsFormTests`, `EditorAccessTests`) — 22 tests, OK. `manage.py check`: OK. `makemigrations --check --dry-run`: no drift.

All test runs above are `RUNTIME_VERIFIED` (executed, not just written) — a working Django environment was available this session. No browser QA was performed for Phase 3 (not attempted this session; flagged as remaining work, same as it was for Phase 2's Slice 1 before that phase's dedicated browser-QA pass).

## 5. Explicitly not built (and why)

- **Blog teaser** — `apps.blog.BlogPost` isn't tenant-scoped; out of scope per §2.
- **Video Hero as a distinct type** — the existing `video_section` (897) already covers merchant-supplied video (YouTube/Aparat/Instagram detection via `product_video_service`) generically; a separate "hero" variant would be a near-duplicate registry entry for no functional gain, same reasoning as the audit's `hero_banner`/`image_slider` duplication finding (flagged as existing debt, not one to add to).
- **MediaAsset-backed rendering** — real gap, but unrelated to "add Home blocks"; deferred to avoid an unscoped media-pipeline refactor inside a block-library phase.
- **Story Rail multi-instance** — `max_instances=1` reads as a deliberate one-rail-per-page decision, not an oversight; left unchanged absent an explicit product ask to change it.
