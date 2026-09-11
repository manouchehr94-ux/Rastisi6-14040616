# Phase 5, Task 2 — Live Ready Template Preview: Browser QA Report
(RastiSi UI/UX Design Lead — read-only/observational visual QA)

Date: 2026-09-11
Role: reviewer/QA only. No production code, templates, CSS, or migrations were modified during this review. Setup-only mutations (documented below) were made to the local dev DB (a throwaway staff user + StoreMembership on the existing `akhlaghi` fixture Store, its `admin_subdomain` changed to `rastisiqa`, and the canonical `rasti-mode-demo` Demo Store seeded via the idempotent `apply_golden_reference_storefront` command) — no merchant-facing data, tenant isolation, or lifecycle/draft-publish behavior was touched.

## Setup performed

- Dev server: `.venv-baseline/bin/python manage.py runserver 0.0.0.0:8000` (no server was already running).
- Seed: `python manage.py apply_golden_reference_storefront` — succeeded, published Demo Store `rasti-mode-demo` (baseline provenance `fashion_promo_catalog`, header `marketplace_search_first`, 12-section Home).
- Staff access: reused existing `akhlaghi` Store fixture; set `admin_subdomain="rastisiqa"`; created throwaway staff user `rastisiqa_staff` + `StoreMembership` (OWNER, ACTIVE) — same pattern the feature's own test suite (`apps/storefront_builder/tests/test_task2_live_demo_template_preview.py`) uses.
- `/etc/hosts`: added `127.0.0.1 rastisiqa.rastisi.localhost` (admin host) and `127.0.0.1 rasti-mode-demo.rastisi.localhost` (public Demo Store host, used only for one comparison check, see Finding 1).
- Logged in through the real dashboard login form (`/admin-portal/login/`) via chrome-devtools, session-cookie auth — confirmed by reaching the real dashboard home and Gallery.

## A. Gallery (`/admin-portal/storefront-builder/templates/`)

Checked at Desktop 1440×900, Tablet 768×1024, Mobile 390×844.

- Loads without error at all three viewports. `document.documentElement.{scrollWidth,clientWidth}` equal at all three (1440/1440, 768/768, 390/390) — **no horizontal overflow at any viewport**.
- All 50 cards render with thumbnails (SVG-mock thumbnails, the pre-existing offline fallback path — `thumbnail_kind` in (`screenshot`,`svg`), unaffected by this task per the feature's own regression test).
- Every card has a **"مشاهده‌ی قالب (زنده)"** link, confirmed present on cards at all three viewports and confirmed via DOM query that its `href` matches `/admin-portal/storefront-builder/templates/<key>/preview/` and opens `target="_blank"`.
- RTL confirmed structurally, not mirrored-LTR: `document.documentElement.dir === "rtl"`, `lang === "fa"`; sidebar nav sits on the right, body content flows right-to-left, at desktop the collapsed-sidebar drops correctly on tablet/mobile to a right-side hamburger, consistent with real RTL app chrome (not a flipped LTR grid).
- Console: only one recurring DevTools accessibility hint at every viewport — `[issue] A form field element should have an id or name attribute (count: 1)` — present identically at all three viewports, from the shared header search input in `base.html`, pre-existing and unrelated to this feature. **No JS errors.**

Screenshots: `/tmp/claude-0/-home-user-Rastisi6-14040616/26842efd-9267-5a37-815f-95f7eacd7740/scratchpad/gallery_desktop_full.png` (full-page desktop; tablet/mobile viewport screenshots captured but not saved to disk — visually confirmed identical layout behavior, 2-col at tablet, 1-col at mobile, both overflow-free).

## B. Five representative templates × 3 viewports

For all five: page loaded 200 (no 404/500), demo-data banner **"این پیش‌نمایشِ زنده با داده‌های نمایشیِ Rasti Mode Demo ساخته شده — نه اطلاعاتِ واقعیِ فروشگاهِ شما."** present and correctly reads the previewed template's `label_fa`, no horizontal overflow at any of the 3 viewports (`scrollWidth === clientWidth` verified every time), zero broken images (`Array.from(document.images).filter(i => !i.complete || i.naturalWidth===0).length === 0` on every desktop check, `totalImages` ranging 16–110 depending on template), footer renders, mobile bottom nav present at 390×844 only (verified visually at all 5) and structurally distinct per template's declared `mobile_nav_variant`, and **no console errors** (only the same pre-existing DevTools accessibility hints — missing `autocomplete`/`id` attributes on form inputs — seen at every viewport of every template, identical class of issue as the Gallery, not new/feature-specific).

### 1. `editorial_jewelry` ("آتلیه نوآر")
- Header: `header_variant=editorial_row` (`gh--atelier` class) — left-aligned editorial nav row. Renders.
- Home composition (registry order): `hero_banner → category_grid → product_section → image_text → rich_text`.
- **hero_banner rendered EMPTY** (see Finding 1). `category_grid` (fashion_flat icon rail: کیف / پوشاک / کفش) and `product_section` (luxury_dark cards) rendered with real demo products (e.g. "کیف دوشی مشکی کلاسیک", brand "Demo Carry", "Demo Muse") and real prices. `image_text`/`rich_text` rows also empty (see note below Finding 1 — plausibly pre-existing "no content configured" behavior for these generic freeform section types, not confirmed feature-specific).
- Real seeded root category name "کفش" visible (required by the feature's own test `test_real_seeded_category_name_appears_in_rendered_output`).
- Mobile (390×844): floating pill bottom nav present (person/cart/grid/home icons).
- No overflow at any viewport.

### 2. `dense_marketplace` ("بازار مکس")
- Header: `header_variant=marketplace_search_first` — search-centric top bar, structurally different from #1.
- Home composition: `hero_banner → category_grid(circular) → product_section(discounted) → catalog_product_wall(group_columns) → trust_features → brand_carousel → testimonials`.
- **hero_banner rendered EMPTY** (Finding 1). `category_grid`, `product_section`, `catalog_product_wall` (a visibly denser, taller — ~12,267px — multi-column "wall" grid, matching the template's "dense" positioning) rendered with real content. `brand_carousel` rendered and **real seeded brand name "Demo Motion" confirmed present** in the rendered HTML (`document.body.innerText.includes('Demo Motion') === true`) — matches the feature's own test assertion. `trust_features`/`testimonials` rendered empty (no `TrustFeature`/`Testimonial` DB models exist in this codebase under that name — these section types appear to be settings-only/unconfigured-by-default, not a data-scoping regression).
- No overflow at any viewport (tallest page tested, still no horizontal overflow).

### 3. `playful_lifestyle` ("غنچه")
- Header: `header_variant=playful_canopy` — centered stacked logo with an icon row above it, genuinely different shape from both #1 (left row) and #2 (search-first). Footer: `footer_variant=playful_wave`, visually confirmed — a jagged/wave-cut top border on the (dark) footer, a real structural footer difference, not a recolor. Mobile nav: `five_item`, confirmed as a flat 5-icon bar at 390×844 (سبد خرید / حساب / جستجو / دسته‌بندی / خانه).
- Home composition: `hero_banner → category_grid(circular) → product_section(soft_capsule cards) → testimonials → newsletter`.
- **hero_banner rendered EMPTY** (Finding 1). `newsletter` section rendered correctly (visible "عضویت در خبرنامه" signup block). `testimonials` empty (see note above).
- No overflow at any viewport.

### 4. `dark_digital` ("پالس نئون")
- Header: `header_variant=floating_compact` — minimal dark topbar, visually distinct dark theme (not just a dark palette on the same layout — the category_grid itself changes shape, see below).
- Home composition: `hero_banner → category_grid(carousel) → product_section(newest, carousel, tech_neon cards) → product_section(discounted, grid, tech_neon cards) → newsletter`.
- `category_grid` renders as three large gradient CTA cards ("مشاهده محصولات کیف/پوشاک/کفش") in a horizontally-scrollable carousel — a genuinely different presentation from the icon-badge/circular styles used by the other four templates. Verified the carousel's horizontal scroll is internally contained (`scrollWidth 2344 > clientWidth 1164`, `overflow-x:auto` scoped to the carousel element) and does **not** cause page-level horizontal overflow.
- Two distinct `product_section` rows (carousel "newest" + grid "discounted") both rendered with real demo products, `tech_neon` cyan-accent pricing/badges visible.
- **hero_banner rendered EMPTY** (Finding 1).
- Mobile nav: `glass_dock`, confirmed — a dark glassmorphism floating bar, visibly different from `five_item`'s flat bar and mina_community's `floating_dock` (see #5).
- No overflow at any viewport, no crash despite the two internal carousels.

### 5. `mina_community` ("مینا")
- Header: `header_variant=community_shortcuts` — hot pink/red top bar with a highlighted circular account-shortcut icon, the most visually distinct header of the five.
- Home composition: `hero_banner → category_grid(circular) → product_section(newest, soft_capsule) → story_rail`.
- **This is the template the task flagged for the earlier story-rail crash fix.** Confirmed: page loads 200, no 500, no console error — the crash is fixed. However, **the story_rail section itself rendered EMPTY, same root cause as Finding 1** (its scoped-item fallback query never matches any of the Demo Store's real `StoryRailItem` rows, all of which are `section`-scoped, not global) — the fix prevents the crash but does not make the story rail show content in this specific live-preview path. This is real, direct evidence bearing on the task's explicit concern.
- `hero_banner` also rendered EMPTY (Finding 1).
- `category_grid`/`product_section` rendered correctly with real demo data.
- Footer: `footer_variant=app_download` — a visible trust-features icon strip (headphone/checkmark/card/truck) built into the footer chrome itself, plus app-download-style footer content — structurally different from #2's `marketplace_columns` and #3's `playful_wave`.
- Mobile nav: `floating_dock`, confirmed — pink-accented floating pill with a raised/highlighted home button, visibly different from `five_item` and `glass_dock`.
- No overflow at any viewport.

## Finding 1 (CRITICAL — blocks full acceptance): hero_banner / multi_banner / story_rail render EMPTY in every live preview, for every template tested

**Symptom:** In all 5 templates checked, the `hero_banner` section (and, for `dense_marketplace`, its `trust_features`-adjacent sections; and for `mina_community`, its `story_rail` section) renders as a completely empty `<div class="rsec">` — no heading, no image, no text, nothing — even though the task explicitly requires "Core body content renders: hero section... visible" for each template.

**Root cause (verified by reading `render_service.py` and querying the real DB, not guessed):**
- `_scoped_hero_slides`/`_scoped_banners`/`_story_rail_context` (`apps/storefront_builder/services/render_service.py`) each do: if the passed-in `section.pk is not None`, filter `HeroSlide`/`PromotionalBanner`/`StoryRailItem` by `section=<that exact section>`; **otherwise** (the Task-1 corrective's fallback, added specifically so an unsaved candidate section doesn't crash Django's "must be saved" FK-filter error) fall back to `filter(store=store, section__isnull=True, is_active=True)`.
- Every `resolve_preset_candidate()`-produced section (i.e. every section this new live-preview view ever renders) is unsaved, `pk=None` — so the fallback path is **always** taken, **for every template**.
- I queried the real `rasti-mode-demo` DB directly: **all 8 HeroSlides, all 12 PromotionalBanners, and all 20 StoryRailItems belonging to the Demo Store have a non-null `section_id`** (they are scoped to the specific, real, persisted `StorefrontSection` rows created when the Demo Store's actual baseline preset, `fashion_promo_catalog`, was applied and published) — **zero** of them have `section=None`.
- Net effect: the fallback query `section__isnull=True` matches **none** of the Demo Store's real content, for **any** candidate/any Ready Template, **every single time**. This is not specific to the 5 templates sampled — it is structural, and will reproduce for all 50.
- **Confirms it's specific to the new live-preview mechanism, not a general demo-data gap:** I separately opened the real, published Demo Store storefront (`http://rasti-mode-demo.rastisi.localhost:8000/`) and confirmed its hero/banner nav elements are **not** empty there — the Demo Store's own real (already-applied) template renders its hero correctly. Only the *candidate*-based live preview of a *different, not-yet-applied* template hits the empty fallback.

**Why this matters for acceptance:** the task's B checklist explicitly requires "hero section" to render as part of "core body content" for each of the 5 templates — it does not, for any of them. `mina_community`'s story_rail — called out by name as important evidence — also does not render its actual content (it renders safely, without crashing, which is good evidence the earlier crash fix held, but it is not evidence the story rail "renders correctly" in the sense of showing real story items).

**Severity/scope:** This is a data-context wiring gap in `storefront_template_live_preview()`'s render path, not a template/CSS/layout defect — architecture-adjacent (it touches `render_service.py`, a canonical shared-renderer file) and should go to an engineer, not be patched by a design/CSS change. I did not attempt a fix; per my role boundary this needs engineering sign-off, and I flag explicitly that I can't tell from here whether the correct fix is "give the candidate's fallback a wider query" or "the Demo Store's seed should also leave a set of globally-scoped (`section=None`) HeroSlides/Banners/StoryRailItems available for exactly this preview path" — that's a design decision for the render-service owner, not something I should silently redesign around.

## Finding 2 (IMPORTANT): header top-nav category strip shows "no categories" for every template, because it resolves the wrong Store

**Symptom:** Every live preview's header nav category strip/mega-menu shows the placeholder **"فعلاً دسته‌بندی‌ای ثبت نشده است"** ("no categories registered yet"), even though the Demo Store being previewed clearly has real categories (visibly rendered elsewhere on the same page via the `category_grid` section: کیف / پوشاک / کفش).

**Root cause:** `apps/catalog/context_processors.py`'s `nav_categories(request)` resolves its Store via `resolve_store_for_service(request)` — i.e. the **ambient, host-resolved Store for the current request** (on the admin dashboard host, that's the logged-in merchant's own Store — in my test, `akhlaghi`, which genuinely has 0 categories since no industry/template has been installed on it). It is completely independent of the `demo_store`/`preset` context this new view explicitly builds and passes to the template. The header partial (`category_link_row.html`/`category_mega_menu.html`) consumes this same global `nav_categories` context-processor value, not anything scoped to the Demo Store being previewed.

**Impact:** cosmetic/informational rather than blocking — the page still loads, still shows real demo category content elsewhere, and this only affects one header sub-widget — but it is a real correctness gap: for header variants that rely heavily on the category nav/mega-menu (e.g. `dense_marketplace`'s `marketplace_search_first`), this is a visible defect a merchant evaluating that Ready Template would notice immediately. Flagging as IMPORTANT, not CRITICAL, and — like Finding 1 — this is a data-wiring issue for an engineer, not a CSS/layout fix.

## Minor / non-blocking observations
- The header brand/logo text shows a shared fallback ("دیجی‌مارکت") on every preview — traced to neither the Demo Store nor the `akhlaghi` fixture having `ShopSettings.site_name` configured; this is a shared platform-wide fallback behavior, not something Task 2 introduced, and not something I'd block on.
- The same generic DevTools accessibility hints (missing `autocomplete`/`id` on a couple of form fields) recur on every page — pre-existing, shared chrome, unrelated to this feature.
- `prefers-reduced-motion` and keyboard/focus-state navigation were **not** specifically exercised in this pass — out of the explicit checklist given for this task; flagging as not-yet-verified rather than silently passing it.

## C. Visual distinctness assessment (explicit verdict)

**Verdict: yes — these five are meaningfully, structurally different from each other, not palette/color recolors of one fixed layout.** This preview mechanism is capable of surfacing real Ready Template DNA differences (modulo Finding 1's content gap).

Concrete structural evidence actually observed, not asserted:
- **Header shape** differs in kind, not just color, across all five: `editorial_jewelry`'s left-aligned nav row vs. `dense_marketplace`'s search-first bar vs. `playful_lifestyle`'s centered/stacked logo with an icon row above vs. `dark_digital`'s minimal dark topbar vs. `mina_community`'s pink bar with a highlighted circular account shortcut.
- **category_grid presentation** differs in kind: icon-rail (`editorial_jewelry`), circular badges (`dense_marketplace`, `playful_lifestyle`, `mina_community`), and large gradient horizontally-scrolling CTA cards (`dark_digital`) — three genuinely different widget types, not the same widget recolored.
- **Section composition/count** differs: `dark_digital` has two distinct `product_section` rows (a "newest" carousel and a "discounted" grid); `dense_marketplace` adds a `catalog_product_wall` + `brand_carousel` + `trust_features` + `testimonials` that none of the others have; `playful_lifestyle` adds a `newsletter` signup block; `mina_community` adds `story_rail`.
- **Card style** differs: `luxury_dark` (black cards, editorial_jewelry) vs. `marketplace_price` (dense_marketplace) vs. `soft_capsule` (playful_lifestyle, mina_community) vs. `tech_neon` (dark_digital, visible cyan accents on a dark card).
- **Footer structure** differs: plain dark (editorial_jewelry) vs. `marketplace_columns` (dense_marketplace) vs. `playful_wave`'s visible wave-cut top edge (playful_lifestyle) vs. `app_download`'s trust-icon strip + app-download content (mina_community).
- **Mobile bottom nav** differs visually and structurally at 390×844 in every case: flat 5-icon bar (playful_lifestyle) vs. dark glassmorphism (dark_digital) vs. pink floating dock with a raised home button (mina_community); confirmed absent at desktop/tablet in all cases (I did not observe any bottom-nav bar at 1440×900 or 768×1024 for any of the five).

Nothing here reads as "same layout, different accent color" — every one of the five changes the actual shape/composition of at least the header and the category-presentation widget, and most change card style, footer structure, and mobile-nav treatment as well. The one place this verdict is *not* fully testable is the hero section, which — per Finding 1 — never actually renders content in any of the five, so I cannot personally attest to hero-level visual distinctness from this pass; the Task-1 evidence's own earlier full-page screenshot (captured via a different, real-Apply-based mechanism, not this live-preview route) shows `editorial_jewelry`'s actual `luxury_showcase` hero rendering with real triptych arch imagery, which is at least existence-proof the hero DNA itself is real and distinct per template — it just isn't visible through this specific new preview route yet.

## Files/paths referenced
- Feature code: `/home/user/Rastisi6-14040616/apps/storefront_builder/views.py` (`storefront_template_live_preview`, line ~2251), `/home/user/Rastisi6-14040616/apps/storefront_builder/templates/storefront_builder/ready_template_live_preview.html`, `/home/user/Rastisi6-14040616/apps/storefront_builder/services/render_service.py` (`_scoped_hero_slides`, `_scoped_banners`, `_story_rail_context`), `/home/user/Rastisi6-14040616/apps/catalog/context_processors.py` (`nav_categories`).
- Feature's own test suite: `/home/user/Rastisi6-14040616/apps/storefront_builder/tests/test_task2_live_demo_template_preview.py`.
- Prior Task-1 evidence referenced for comparison: `/home/user/Rastisi6-14040616/docs/qa_evidence/storefront_design_engine/phase5/task1_candidate_preview_primitive.md`, `/home/user/Rastisi6-14040616/docs/qa_evidence/ready_template_previews/editorial_jewelry/fullpage/home_desktop_full.jpg`.
- Screenshots captured this session (scratchpad, not committed to the repo):
  `/tmp/claude-0/-home-user-Rastisi6-14040616/26842efd-9267-5a37-815f-95f7eacd7740/scratchpad/gallery_desktop_full.png`,
  `ej_desktop_full.png`, `ej_tablet_full.png`, `ej_mobile_full.png`,
  `dm_desktop_full.png`, `dm_mobile_viewport.png`,
  `pl_desktop_full.png`, `pl_mobile_viewport.png`,
  `dd_desktop_full.png`, `dd_mobile_viewport.png`,
  `mc_desktop_full.png`, `mc_mobile_viewport.png`.

## Explicit non-mutation statement
No production Django code, templates, CSS, JS, or migrations were modified during this review. The only writes made were local dev-environment QA fixtures (staff user, StoreMembership, `admin_subdomain` change on the pre-existing `akhlaghi` fixture Store, and the idempotent Demo Store seed command) plus two `/etc/hosts` lines — no merchant data, tenant isolation, Store scoping, permissions, or draft/publish lifecycle behavior was altered by this review.
