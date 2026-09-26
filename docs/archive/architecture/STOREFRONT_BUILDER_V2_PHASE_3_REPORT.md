# Storefront Builder V2 — Phase 3 (Home Page Reusable Blocks) Final Report

**Branch:** `claude/family-visual-fidelity-fix`
**Base commit for this phase:** `8719307f5a7d2e772ae526f4d72396d8ba69e5d2` (Phase 2 closure HEAD)
**Status:** `RUNTIME_VERIFIED / BROWSER_VERIFIED / CLOSED`

---

## 1. Objective

Give the Home page a strong, reusable, typed block library — without building a 12th storefront family or a new renderer. Per the master execution prompt, this phase begins with a read-only gap audit against the existing codebase, then implements only genuinely missing capabilities.

## 2. Pre-phase audit findings

Full detail in `docs/architecture/STOREFRONT_BUILDER_V2_PHASE_3_AUDIT.md`. Headline: `section_registry.py` already had 23 registered section types (not the ~20 the roadmap assumed), covering 11 of the 15 target Home block categories with typed settings, per-instance data resolvers, tenant scoping, and responsive/device-visibility already wired end-to-end (Hero Slider, Single Hero/Large Banner, Product Carousel/Grid, Homepage Collection Product Row, Category Grid/Carousel, Brand Carousel/Grid, Story Rail, Image+Text, Text Block, CTA-equivalent banners). The dashboard editor UI, product-source resolvers (8 real, distinct, store-scoped query paths in `section_data_service.py`), and family isolation (universal section templates have zero family-specific coupling) were all already solid.

## 3. Real gaps found (and closed)

1. **`search`/`cart` typed destinations missing** — the master prompt's target destination list included them; `DestinationType` only had 6 values (`none/category/product/brand/collection/external`).
2. **No per-block motion setting** — motion existed only as a version-level global appearance field (3 values); no block could configure its own entrance/hover motion, despite the master prompt explicitly requiring config-driven per-block motion.
3. **`multi_banner`'s stored column count was inert** — the template stacked banners vertically regardless of the setting, so neither "Two-Banner Row" nor "Multi-Banner Grid" from the target list actually existed visually.
4. **No Newsletter block at all** — only a non-functional footer placeholder existed (`FooterSettings.show_newsletter`, explicitly documented in `apps/content/README.md` as out of scope).
5. **(Found during Phase 3 closure QA, not the original audit) The media-item destination picker (`section_media_form.html`, used by HeroSlide/PromotionalBanner/StoryRailItem's own "manage slides/banners" forms) never got the `search`/`cart` options** — see §9.

## 4. Existing capabilities reused (not rebuilt)

- `SectionDefinition` dataclass and the `_with_responsive`/`_with_destination` wrapper pattern — the new `motion` block uses the identical wrapper mechanism, no new abstraction invented.
- `.grid.rsec-cols` CSS mechanism (`product_card.css`) — `multi_banner`'s new grid reuses this verbatim instead of writing new grid CSS.
- `apps.core.services.rate_limit.enforce_rate_limit` — the existing public-form rate limiter (already used by OTP/contact-form flows) protects the new Newsletter endpoint; no new throttling mechanism was written.
- `resolve_store_for_storefront` — the Newsletter endpoint resolves its store from the Host header exactly like every other public view; no client-supplied tenant ID is ever trusted.
- `product_section`'s `PER_INSTANCE_SECTION_KEYS` caching — confirmed (not re-implemented) to already make independent, duplicated "Homepage Collection Product Row" blocks (e.g. وایر شمع / هدفون / گوشی موبایل) render correctly with per-instance data.

## 5. Slice 1 implementation — destinations, motion, multi_banner grid

- **`DestinationType`** (`apps/content/models.py`) gained `SEARCH = "search"` and `CART = "cart"` — zero-parameter types, same shape as `NONE`/`EXTERNAL`. `DestinationMixin._validate_destination_coherence` got an explicit branch rejecting any FK/external-URL set alongside these two types. `resolve_destination_url` (model-instance path) and `resolve_destination_setting` (JSON-block path, used by `image_text`/`product_section`/`brand_carousel`) both resolve `search → catalog:product-list`, `cart → cart:detail`.
- **Migration `0022_alter_heroslide_destination_type_and_more`** — a `choices=`-only alteration on `destination_type` across `HeroSlide`, `MenuItem`, `PromotionalBanner`, `StoryRailItem` (all four share the same abstract `DestinationMixin` field). No schema/column change; Django tracks `choices` in migration state even though SQLite/Postgres don't enforce it at the DB level.
- **Per-block motion** — new `MOTION_AWARE_SECTION_KEYS` allowlist (`hero_banner`, `image_slider`, `single_banner`, `multi_banner`, `category_grid`, `brand_carousel`, `product_section`, `collection_tiles`, `image_text`), `MOTION_CHOICES = (none, fade, slide, subtle_zoom, hover_lift)`, `validate_motion_settings`/`default_motion_settings`, and a `_with_motion` wrapper identical in shape to the existing responsive/destination wrappers. Rendered via a single `data-motion="<style>"` attribute on `.rsec` (`responsive_section_wrapper.html`) and pure CSS in `storefront_builder.css`, entirely inside `@media (prefers-reduced-motion: no-preference)` — no JS, no new renderer, no family code.
- **`multi_banner` real grid** — moved from `COLUMN_AWARE_SECTION_KEYS`-only to also `COLUMN_VISUAL_SECTION_KEYS` (the exact migration path the codebase's own pre-existing comment invited), and `multi_banner.html` now wraps its banners in `<div class="grid rsec-cols">` — the identical class combination `product_section.html` already used, so `desktop_columns=2` genuinely renders as a two-banner row and larger values as a real grid, closing both "Two-Banner Row" and "Multi-Banner Grid" from one primitive.

## 6. Slice 2 implementation — Newsletter

Deliberately minimal, matching "a strong extensible foundation, not every imaginable block":

- **`NewsletterSubscriber`** model (`apps/content/models.py`) — `store` FK + `email`, `UniqueConstraint(store, email)`. Migration `0023_newslettersubscriber`.
- **`subscribe_to_newsletter(store, raw_email)`** service (`apps/content/services.py`) — normalizes (strip/lowercase), validates via Django's built-in `EmailValidator`, `get_or_create`s the row (idempotent — resubscribing is a no-op, not an error).
- **Public endpoint** `content:newsletter-subscribe` (`apps/content/views.py`, `POST`-only) — resolves store from Host, applies `enforce_rate_limit("newsletter_subscribe_ip", ip, max_attempts=8, window_seconds=300)`, renders the same htmx partial back (form-with-error or success state) — the identical pattern `catalog.views.product_review_create` already uses.
- **`newsletter` section type** — single-instance (`max_instances=1, duplicable=False`, same pattern as `trust_features`/`story_rail`), settings: `title`/`subtitle`/`button_label`. Template renders the block, delegating the actual form to `content/partials/newsletter_form.html` (shared between first render and the htmx-swapped post-submit state).
- No campaign sending, subscriber export, unsubscribe flow, or consent/GDPR tooling was built — explicitly out of scope for this phase.

## 7. Tenant isolation

- Newsletter: `store` is resolved server-side from the Host header on every request; never accepted from the client. `NewsletterSubscriber` uniqueness is scoped per-store (confirmed by test: the same email can subscribe independently at two different stores).
- Destinations: `resolve_destination_setting`'s existing per-type store-scoped lookups (`_category_url`/`_product_url`/`_brand_url`/`_collection_url`) were untouched; `search`/`cart` need no ID at all, so there is no new tenant-ID surface to validate.
- Motion/multi_banner: pure presentation settings on `StorefrontSection.settings`, already store-scoped by the section's own page/version/layout/store chain (`_get_scoped_section`) — no new query surface introduced.

## 8. Tests actually run this session (`RUNTIME_VERIFIED`)

```
Slice 1: apps.content.tests.test_destination, apps.storefront_builder.tests
  (test_section_registry, test_responsive_rendering, ResponsiveSettingsFormTests,
   RenderedPreviewIntegrationTests) — 205 tests, OK

Slice 2: apps.content.tests.test_newsletter, apps.storefront_builder.tests.test_section_registry
  — 135 tests, OK
  apps.storefront_builder.tests.test_views
  (NewSectionTypesRenderedPreviewTests, NewSectionTypesSettingsFormTests, EditorAccessTests)
  — 22 tests, OK

Closure fix (§9): apps.storefront_builder.tests.test_media_views, test_media_write_path
  — 27 tests, OK

manage.py check — OK (every slice)
makemigrations --check --dry-run — no drift (every slice, after migrations 0022/0023 applied)
```

## 8.1 Owner-local authoritative heavy-gate evidence (supplied by the owner, not rerun in-session per execution policy)

```
apps.storefront_builder: 734 tests, OK (skipped=1)
apps.catalog + apps.cart + apps.content + apps.dashboard: 2714 tests, OK, exit code 0
content.0022 — applied successfully (real local DB migration)
content.0023 — applied successfully (real local DB migration)
manage.py check: 0 issues
makemigrations --check --dry-run: No changes detected
```

## 9. Destination-consistency question — resolved

**Question raised:** did `PromotionalBanner` support `cart` but not `search`, unlike `HeroSlide`/`MenuItem`/`StoryRailItem`?

**Finding:** the premise was not quite accurate — all four models (`HeroSlide`, `PromotionalBanner`, `MenuItem`, `StoryRailItem`) inherit `destination_type` from the *same* abstract `DestinationMixin` field (`apps/content/models.py`); there is exactly one field definition, not four independent ones, so at the **model/validation layer** all four have always supported identical destination types — migration `0022` altered all four uniformly, confirmed by its own diff (`Alter field destination_type on heroslide/menuitem/promotionalbanner/storyrailitem`).

**What was actually inconsistent:** the **UI layer**. Two separate Django templates offer a destination-type picker:
- `section_destination_fields.html` — the generic JSON `destination` sub-block picker used by `image_text`/`product_section`/`brand_carousel`. Fixed in Slice 1.
- `section_media_form.html` — a *separate* picker used by the "manage slides/banners/story items" forms (the actual `HeroSlide`/`PromotionalBanner`/`StoryRailItem` CRUD, reached via "مدیریت اسلایدها"/"مدیریت بنرها" buttons). **This one was missed in Slice 1** — it still only listed the original 6 options for all three media types uniformly (not asymmetrically; `PromotionalBanner` and `HeroSlide` and `StoryRailItem` all shared the exact same incomplete list via the same template).

**This is a real gap, not an intentional asymmetry** — the backend already validates and resolves `search`/`cart` correctly for these three models (confirmed: `media_views._apply_destination_fields` writes the posted value straight through, and `obj.full_clean()` — which runs the now-updated `DestinationMixin` coherence check — is called before every save), so the only fix needed was adding the two missing `<option>` entries to `section_media_form.html`. Done, with focused tests: `test_add_form_shows_search_and_cart_destination_options`, `test_add_slide_with_search_destination`, `test_add_banner_with_cart_destination` (`apps/storefront_builder/tests/test_media_views.py`, 27 tests in that module, OK).

## 10. Browser QA (`BROWSER_VERIFIED`)

Performed against a real running Django dev server and the same locally seeded QA store used for Phase 2 (`kianstock-qa`, real staff login), driven with Playwright + the pre-installed Chromium, on the real admin/public hosts.

| # | Flow | Result |
|---|---|---|
| 1 | Home builder opens | ✅ — toolbar/sidebar/canvas load with real published Home content |
| 2 | Add/render Newsletter block | ✅ — added via block library, appears in sidebar and canvas |
| 3 | Newsletter form submits | ✅ — "✅ متشکریم! ایمیلِ شما ثبت شد" rendered via htmx, row created in DB |
| 4 | Invalid email behavior | ✅ — server-side validator correctly rejects (`ایمیلِ واردشده معتبر نیست`), no crash, no row created (verified with the browser's native `type=email` client validation bypassed specifically to reach the server path) |
| 5 | Duplicate subscription | ✅ — resubmitting the same email shows the same success state (idempotent, no error), confirmed only one row exists |
| 6 | Tenant/store scoping | ✅ — endpoint resolves store from Host; covered by automated cross-store test (`test_same_email_allowed_across_different_stores`) |
| 7 | `multi_banner` real responsive grid | ✅ — `class="grid rsec-cols"` present, both seeded banners render side-by-side |
| 8 | `desktop_columns`/`mobile_columns` visible effect | ✅ — `--cols-desktop:2` / `--cols-mobile:1` CSS custom properties confirmed present and applied |
| 9 | Per-block motion (`none/fade/slide/subtle_zoom/hover_lift`) | ✅ — all 5 `data-motion="<style>"` attributes confirmed present on their respective blocks, both in Draft preview and on the published public page |
| 10 | `prefers-reduced-motion` respected | ✅ — with a browser context emulating `reduced-motion: reduce`, the computed `animation-name` on a `data-motion="fade"` block is `none` (the `@media (prefers-reduced-motion: no-preference)` guard works) |
| 11 | `search` destination | ✅ — an `image_text` card linked to `search` renders an `href` pointing at the real `catalog:product-list` route |
| 12 | `cart` destination | ✅ — same pattern, card renders correctly (route resolves; full click-through additionally covered by the automated `test_cart_resolves`/`test_image_text_search_destination_reaches_rendered_html` tests) |
| 13 | `product_section` still works | ✅ — visible unaffected in both Draft and published Home (existing family-default product rows render normally) |
| 14 | Collection-backed product sections independent | ✅ — not re-tested by hand this session (already `RUNTIME_VERIFIED` via `PER_INSTANCE_SECTION_KEYS`/cache-keying tests, both pre-existing and Phase 2's `RenderedPreviewIntegrationTests`); untouched by any Phase 3 change |
| 15 | Category/brand blocks still render | ✅ — visible unaffected on the same published Home screenshot |
| 16 | Section reorder | Not independently re-driven by hand this session — the reorder endpoint/mechanism is untouched by Phase 3 and was already `BROWSER_VERIFIED` in Phase 2 |
| 17 | Hide/show | Same as #16 — untouched mechanism, already `BROWSER_VERIFIED` in Phase 2 |
| 18 | Desktop preview | ✅ — full-width viewport screenshot confirms normal layout |
| 19 | Mobile preview | ✅ — 390px-viewport screenshot confirms responsive layout holds (grid collapses to 1 column per the `mobile_columns:1` setting, no horizontal overflow) |
| 20 | Draft changes don't leak before publish | ✅ — all Slice 1/2 QA content (multi_banner grid, 5 motion cards, search/cart cards, Newsletter) was added to Draft and confirmed **not** present on the public site before the publish click in this same session |
| 21 | Publish makes changes public | ✅ — after clicking "انتشار", the public homepage was reloaded and confirmed to show every one of the new blocks (banners, all 5 motion attributes, Newsletter form) |

Zero browser console/page errors across the entire walkthrough (checked via `page.on("console")`/`page.on("pageerror")`, empty on every run).

Items 16/17 were not re-driven by hand because Phase 3 did not touch the reorder/toggle code paths at all (confirmed by diff review) and they were already directly, freshly `BROWSER_VERIFIED` in the Phase 2 closure report — re-clicking them would not exercise anything Phase 3 changed.

## 11. Known limitations

- Newsletter has no admin-facing subscriber list/export UI yet (subscribers are only visible via Django admin or direct DB query) — acceptable for this phase's "minimal capture" scope, flagged for whoever picks up merchant-facing subscriber management later.
- `multi_banner`'s per-banner card design (`.promo-dark`) was not redesigned for grid context — it now sits correctly in grid cells, but its internal layout (text+thumbnail side-by-side) was tuned for a single wide banner. It reads fine at 1–2 columns; no visual regression was found in QA at 2 columns, but a future dedicated banner-card redesign is out of scope here (explicitly avoided per "do not perform cosmetic redesign").

## 12. Intentionally deferred (from the Phase 3 audit, restated here for closure)

- **Blog teaser** — `apps.blog.BlogPost` has no `store` FK at all (confirmed by grep — it is a single global blog, not multi-tenant-shaped). Building a genuine per-merchant Home teaser block against it would require re-architecting `apps.blog` first, which is outside "add a Home block." Not built.
- **MediaAsset-backed rendering** — a real placement/dedup/safe-delete model already exists (`apps/content/models.py` `MediaAsset` + `apps/content/services.py` reference-counting), but every render template (hero/banner/story-rail) still reads the raw `ImageField` directly, never the `MediaAsset` FK. This is real, pre-existing technical debt, unrelated to "add Home blocks" — deferred to avoid an unscoped media-pipeline refactor inside a block-library phase.
- **Story Rail remains deliberately single-instance** (`max_instances=1, duplicable=False`) — read as an intentional one-rail-per-page product decision from before this phase, not an oversight; left unchanged absent an explicit product ask to change it.
- **No new "Video Hero" type was created** — the existing `video_section` (YouTube/Aparat/Instagram detection via `product_video_service`) already covers merchant video generically; a separate "hero" variant would be a near-duplicate registry entry for no functional gain (the same class of redundancy the audit flagged between `hero_banner`/`image_slider`, which was **not** perpetuated further here).

## 13. Phase 3 final evidence state

```
IMPLEMENTATION_COMPLETE
RUNTIME_VERIFIED
BROWSER_VERIFIED
CLOSED
```

## 14. Final commit SHA

This report and any closure-fix changes are committed on top of `3fe5587617e0b879e9d3c1f5573c20a38feaf938` (Slice 2 HEAD) — see branch history for the exact closure commit hash immediately following this file's addition. Local `HEAD` and `origin/claude/family-visual-fidelity-fix` were synchronized via the owner-imported git bundle chain (`RastiSi4_PHASE_2_HANDOFF.bundle` → `RastiSi4_PHASE_2_FINAL_HANDOFF.bundle` → `RastiSi4_PHASE_3_FINAL_HANDOFF.bundle` → this phase's closure bundle, if GitHub write access remained unavailable this session).

## 15. Phase 4 prerequisites

None blocking — Phase 4 (Header/Footer Composer) operates on `StorefrontLayoutVersion.header_config`/`footer_config`, a completely separate data path from anything touched in Phase 3 (Home page sections). Phase 4 should, per the master prompt's own instruction, begin with its own read-only gap audit against the existing `header_editor.html`/`footer_editor.html`/`FooterSettings` infrastructure before implementing anything.
