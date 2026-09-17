# P5-W4C — Harness + Matrix Inventory Gate

**Certified official base (branch created from):** `3a4fe9070584655548bae5a9bb574f3415bbf580`
**Branch:** `feature/phase5-w4c-all50-certification`
**Scope of this document:** source-backed inventory only. No production code, Django
test code, or QA harness code was changed to produce it.

---

## 1. Authoritative requirements (source: the plan documents)

### 1.1 `docs/superpowers/plans/2026-09-15-phase5-converged-completion-plan.md`

This is the AUTHORITATIVE plan ("Status: AUTHORITATIVE — replaces Tasks 9–18 of
the 2026-09-11 implementation plan").

**Global architecture constraints (apply to every workstream, W4C included):**
"ONE CONCEPT = ONE CANONICAL OWNER" — introducing a second renderer, second Ready
Template registry, second appearance manifest, second Draft/lifecycle, second
publish lifecycle, second edit-history system, second candidate-preview engine,
second R4 mutation boundary, second tenant resolver, second ResourceSource
authority, second ProductCard path, second cart/add-to-cart path, second Bottom
Navigation system, second overlay/modal/drawer mechanics, second search backend,
duplicate recommendation logic, per-template business logic, per-template SATC
fixes, or per-template mobile-nav engines is "an automatic STOP for architecture
review." Expected default: **ZERO MIGRATIONS**.

**Exact W4C section** ("P5-W4C — All-50 Browser Certification"), quoted:

> **Goal:** Real closure gate — automated browser matrix for ALL 50 Ready
> Templates. Representative QA does not count.
>
> **Matrix (per Template):** Desktop (1440×900), Tablet (768×1024), Mobile
> (390×844), RTL; horizontal-overflow check; presence/health of Header, Hero,
> Product Cards, Footer, Bottom Navigation; core page load; Listing; PDP; Cart;
> Theme interaction where applicable; accessibility-critical controls;
> console/page/request error capture. Reuse the existing harness
> `tools/storefront_builder_r4_qa/run.mjs` (and/or `tools/storefront_builder_qa/`)
> — do NOT build a second harness.
>
> **Evidence-volume discipline:** machine-readable JSON matrix for every
> Template/page/viewport; representative retained screenshots; mandatory
> home-template gallery assets for all 50 (for W5 review); failure screenshots
> only for failing non-home cases. Do not commit thousands of redundant
> screenshots.
>
> **Visual distinctness:** all 50 materially distinguishable across
> Header/Hero/layout/composition/Product Card/density/typography/Footer/Bottom
> Navigation — palette-only difference is insufficient. Structural test
> uniqueness (W4B) and rendered visual certification are different gates; both
> required.
>
> **Branch:** `feature/phase5-w4c-all50-certification`. **Evidence:**
> `docs/qa_evidence/storefront_design_engine/phase5/w4_certification/`.

**Sequencing:** `P5-W1 → P5-W2 → P5-W3 → P5-W4A → P5-W4B → P5-W4C → P5-W5`,
strictly sequential. W4 sub-ordering explicit: "Do NOT run all-50 certification
before W4A and W4B are complete... W4 certifies the final rendering state after
all rendering changes." W4A and W4B are merged and certified (this session), so
W4C is now unfrozen.

**Checkpoints:** "Each workstream begins from the latest merged official Phase-5
checkpoint... Record the exact SHA at every gate."

No numeric matrix beyond "ALL 50 Ready Templates" at the 3 named viewports is
stated explicitly; the base cardinality (50 × 4 page classes × 3 viewports) is
derived in §5 below from the enumerated per-Template surfaces (Home, Listing,
PDP, Cart) and is not a silent invention.

### 1.2 `docs/qa_evidence/storefront_design_engine/phase5/phase5_convergence_audit.md`

Pre-plan audit (checkpoint `804f734a...`). Capability-matrix row "50-template
browser certification": status PARTIAL — "Only representative/task-scoped QA...
Structural distinctness test-verified (`test_a8_template_diversity`)... NOT
done: a real all-50 × {1440×900, 768×1024, 390×844} × RTL browser matrix with
accessibility + visual-distinctness certification." Architectural-duplication-
risk table explicitly flags "Second QA harness | not reusing
`storefront_builder_r4_qa/run.mjs`" as IMPORTANT — direct precedent for the
"do not build a second harness" rule. Definition-of-Done item 4: "all 50
templates certified in the browser at 1440×900/768×1024/390×844, RTL, with
accessibility and visual-distinctness confirmation, reusing the existing
harness."

### 1.3 `docs/superpowers/specs/2026-09-11-phase5-design-expansion-charter.md`

Origin of the three fixed viewports, RTL primacy, and accessibility criteria
("semantic controls, keyboard operation, visible focus, accessible names,
state exposure, touch targets, sufficient contrast") that W4C's matrix
inherits. Explicit non-goal: "Creating a second storefront platform, editor,
renderer or backend."

### 1.4 W4B design doc status flag

`docs/superpowers/specs/2026-09-16-phase5-w4b-50-template-curation-design.md`
§15 marks `W4C | FROZEN` — a status flag only (W4B had to close first), no
scope content. W4B is now merged and certified, so this freeze is lifted.

### 1.5 W4A evidence structural precedent

`docs/qa_evidence/storefront_design_engine/phase5/w4a_public_shell_convergence/`
used a **per-template JSON result + per-template screenshots folder** pattern
(`browser_qa/<template>/w4a_browser_qa_result.json` + `screenshots/`), tractable
because only 2 templates were in scope. Not directly reusable at 50-template
scale (see §1.6).

### 1.6 W4B evidence JSON schema precedent (directly reusable shape)

`docs/qa_evidence/storefront_design_engine/phase5/w4b_template_curation/implementation/browser_qa_responsive_repair/summary.json`
uses a `{key, version, added_section, newsletter_terminal_key, viewports:
{desktop: {...}, tablet: {...}, mobile: {...}}}` shape, where each viewport
object carries `http_status, rtl, overflow, header_count, footer_count,
gmn_present, gmn_display, rsec_count, expected_rsec_count,
added_section_duplicate_block_count, added_section_element_count,
added_section_hrefs, added_section_has_dead_href,
newsletter_present_at_terminal_index, primary_link_check, console_errors,
page_errors, failed_requests, screenshot}`. This is the direct schema ancestor
for W4C's own JSON matrix (§7 of the plan) — extended with a `page_class` key
(home/listing/pdp/cart) and the additional Hero/Product-Card/accessibility
fields W4C requires that W4B's Home-only schema did not need.

---

## 2. Existing QA/browser-automation inventory (every Playwright-touching file in the repo)

Repo-wide search for `playwright`/`chromium` under `.mjs`/`.py` (excluding
`node_modules`) found exactly 14 files. Nothing else in the repository touches
browser automation.

| # | File | Role |
|---|---|---|
| 1 | `tools/storefront_builder_qa/run.mjs` (1175 lines) | Builder admin-editor UI QA |
| 2 | `tools/storefront_builder_qa/public_task5_qa.mjs` (411 lines) | Standalone public QuickView/Drawer/PDP-tabs QA |
| 3 | `tools/storefront_builder_qa/public_task7_qa.mjs` (219 lines) | Standalone public pagination/search QA |
| 4 | `tools/storefront_builder_qa/public_task8_qa.mjs` (275 lines) | Standalone public mobile-SATC QA |
| 5 | `tools/storefront_builder_qa/public_w1_qa.mjs` (140 lines) | Standalone public Free-Shipping-Goal QA |
| 6 | `tools/storefront_builder_r4_qa/run.mjs` (4172 lines) | R4 admin-editor mutation/history/publish QA (+ opt-in phase3/showcase public blocks) |
| 7 | `tools/storefront_builder_r4_qa/w3_design_lab_qa.mjs` | Design Lab feature QA |
| 8 | `tools/storefront_builder_r4_qa/w4a_public_shell_qa.mjs` (282 lines) | Public shell (Wishlist/CMS routes) QA — has Header/Footer/Bottom-Nav contract checks |
| 9 | `apps/storefront_builder/management/commands/qa_storefront_builder.py` (406 lines) | Django wrapper for #1 |
| 10 | `apps/storefront_builder/management/commands/qa_storefront_builder_r4.py` (1363 lines) | Django wrapper for #6 |
| 11 | `apps/storefront_builder/management/commands/capture_ready_template_previews.py` (335 lines) | **The only command that iterates the full 50-template registry** — screenshot-only, no assertions |
| 12 | `apps/storefront_builder/tests/test_ready_template_real_previews.py` | Asserts on committed screenshot artifacts; never launches a browser itself |
| 13 | `scripts/verify_product_entry_ui.py` | Ad hoc admin-form script, unrelated to Ready Templates |
| 14 | `scripts/verify_six_families_visual.py` | Ad hoc per-family Home/PDP screenshot script, unrelated to Ready Templates |

`tools/` has exactly two subdirectories: `storefront_builder_qa` (files 1–5,
plus `package.json`/`package-lock.json`, the ONLY declared Node dependency
being `playwright-core ^1.50.0`) and `storefront_builder_r4_qa` (files 6–8, no
package.json of its own — imports the sibling's `playwright-core` via
`createRequire`).

No committed orchestrator exists for an "all-50-template certification
matrix." The single closest prior-art precedent —
`docs/qa_evidence/storefront_design_engine/phase5/w4b_template_curation/implementation/06_bounded_browser_qa_summary.md`'s
21-template Playwright driver — was explicitly "kept in the session
scratchpad, not committed," per that document's own text.

### 2.1 `tools/storefront_builder_qa/run.mjs` — Builder admin-editor UI, NOT public storefront

Drives `/admin-portal/storefront-builder/` and its embedded preview iframe.
Single hardcoded viewport `{1650, 950}`. Staff-session cookie injection
(`Client().force_login` → raw session cookie → `context.addCookies`). Zero
Home/Listing/PDP/Cart route testing. JSON output `browser-result.json`.
Failure-only screenshots. No `--only`/subset flag — always tests the entire
section registry. Not relevant to W4C's public-storefront-per-template need
except as the sibling holding the shared `playwright-core` dependency.

### 2.2 `tools/storefront_builder_r4_qa/run.mjs` — R4 admin-editor mutation QA

15-scenario deterministic R4 mutation/undo/redo/publish smoke suite. Two
opt-in blocks (`manifest.phase3`, `manifest.showcase`) additionally hit public
Listing/PDP/Cart/Search routes, but **session-authenticated** (cookie
injected), for **one fixed Store's fixed fixture slugs**, never iterating the
Ready Template registry. `PHASE3_VIEWPORTS` reuses the same 3 viewports.
`--host-resolver-rules=MAP <host> 127.0.0.1` only used in `showcase` mode.
JSON output `r4-browser-result.json`. `R4_QA_ONLY_SCENARIO` env var does
scenario-name substring filtering (debug-only, explicitly documented as never
used in the real gate). No template-key concept anywhere in this file.

### 2.3 `tools/storefront_builder_r4_qa/w4a_public_shell_qa.mjs`

Public shell Header/Footer/Bottom-Nav contract checks — but scoped to exactly
2 non-template routes (`/account/wishlist/`, `/pages/<slug>/`), never to any
of the 50 Ready Templates' Home/Listing/PDP/Cart.

### 2.4 Standalone `public_task5/7/8_qa.mjs`, `public_w1_qa.mjs`

The only files that test the real, anonymous/unauthenticated public
storefront end-to-end (Home/PDP/Listing/Cart) with no admin session. Each
hardcoded to **one fixed fixture Store hostname**
(`rastisi-fashion-test.rastisi.localhost`), configured via `process.env.QA_*`,
invoked directly (`node public_taskN_qa.mjs`) — no shared package.json/CLI
wrapper, no shared JSON schema between the four files, no management-command
integration, no template-registry concept. `public_w1_qa.mjs` is the only file
that exercises the Free-Shipping-Goal widget (4 cart states: below-threshold
physical, above-threshold physical, all-digital, empty) via a genuinely
anonymous CSRF-cookie-only cart flow.

### 2.5 `apps/storefront_builder/management/commands/capture_ready_template_previews.py` — closest existing precedent

**This is the one file in the repository that already iterates the full
50-template registry through the canonical apply/publish path with real
public-host browser navigation.** Concretely, already proven:

- Already imports and uses the **Python `playwright` package**
  (`from playwright.sync_api import sync_playwright`, line 156) — this is an
  already-existing, already-committed production dependency of this exact
  management command, not something W4C would newly introduce. (It is not
  currently pinned in `requirements.txt` — a pre-existing gap, orthogonal to
  W4C.)
- `--only <key>` flag already implements exact per-template filtering; without
  it, iterates `lpr.list_ready_templates()` (confirmed = all 50, §4).
- Canonical mutation path: `preset_service.apply_preset_with_checkpoint` +
  `layout_service.publish`, idempotent (skips re-apply if already published).
- Correct public-host resolution already solved: navigates to
  `shop-{store.admin_subdomain}.{RASTISI_ADMIN_DOMAIN_SUFFIX}` via
  `--host-resolver-rules=MAP <public_host> 127.0.0.1`, with a documented,
  fixed bug precedent (raw-IP navigation previously produced byte-identical
  screenshots across templates) — the exact failure mode this pattern avoids.
- `ThreadPoolExecutor(max_workers=1)` isolates Django ORM writes from the
  thread `sync_playwright()` occupies (documented `SynchronousOnlyOperation`
  fix), the same pattern W4B's own (uncommitted) QA script mirrored.
- Fresh Chromium process per template (explicit anti-cache-leak precaution).
- `--full-qa` already captures Home desktop (1440×1100), Home mobile
  (390×844), Listing desktop (1440×1100, `/products/`), PDP desktop
  (1440×1100, first product via `a.pcard-hitarea`) — **but zero tablet
  viewport, zero Cart page, and zero assertions of any kind** (no
  console-error capture, no overflow check, no header/footer/bottom-nav
  check, no JSON pass/fail result — purely a screenshot generator for the
  Gallery UI's cached preview images).
- Invocation: operator starts `manage.py runserver 127.0.0.1:8000` separately,
  then `manage.py capture_ready_template_previews --base-url
  http://127.0.0.1:8000 [--full-qa] [--qa-output-dir <dir>] [--only <key>]`.

### 2.6 Cross-cutting gap (facts, not recommendations)

No file in the repository drives all 50 Ready Templates through a real
anonymous browser session with pass/fail assertions across a defined
page-class × viewport matrix. The assertion richness needed (RTL, overflow,
header/footer exactly-once, bottom-nav responsive contract, console/page/
request-failure zero-tolerance, PASS/FAIL JSON) exists split across three
mutually-incompatible schemas (`run.mjs`'s `browser-result.json`, `r4_qa/run.mjs`'s
`r4-browser-result.json`, `w4a_public_shell_qa.mjs`'s `w4a_browser_qa_result.json`),
none keyed by "template." The template-iteration + apply/publish + host-
resolution + threading pattern needed for W4C exists in exactly one place —
`capture_ready_template_previews.py` — and only for screenshots.

---

## 3. Harness classification

**B — bounded extension required.**

The plan's suggested files (`tools/storefront_builder_r4_qa/run.mjs`,
`tools/storefront_builder_qa/`) are, per source (§2.1–2.3), admin-editor-focused
Node/Playwright-core tools that do not iterate the Ready Template registry and
do not drive a genuinely anonymous public-storefront session per template. The
plan's instruction to "reuse" them is satisfied at the dependency/pattern
level (same `playwright-core` package family already declared in this repo,
same "Python management-command wrapper shells out to a Node/Playwright
script" architecture those two tools already establish), not by literally
running those files unmodified against 50 templates.

**Canonical extension target:**
`apps/storefront_builder/management/commands/capture_ready_template_previews.py`
— the one file that already does canonical registry iteration, canonical
apply/publish, canonical host-resolution, and the canonical ORM-thread-safety
pattern, using the Python `playwright` package this exact command already
depends on. The bounded extension (implementation round, not this round) adds:
Tablet viewport, Cart page class, assertion logic (RTL/overflow/header-and-
footer-exactly-once/bottom-nav-responsive-contract/dead-href/console-page-
request-error capture/accessibility-critical checks), a JSON result schema
(§1.6 shape, extended), and the bounded Theme sub-matrix (plan §9). No new
Playwright package, no new browser launcher, no new public-storefront
renderer, no parallel Apply/Publish authority, and no separate W4C-only route
system are introduced — every route/service call is one already exercised by
this file or by `w1_qa`/`task5/7/8_qa`'s already-proven anonymous-session
patterns.

**Second harness proposed: NO.**

---

## 4. Exact current 50-Template catalog (verified at HEAD `3a4fe907...`)

Verified programmatically:

```
$ /usr/bin/python3 -c "... from apps.storefront_builder.a8_ready_templates import A8_READY_TEMPLATES; from apps.storefront_builder import layout_preset_registry as lpr; print(len(A8_READY_TEMPLATES)); print(len(lpr.list_ready_templates())); print(sorted(p.key for p in A8_READY_TEMPLATES) == sorted(p.key for p in lpr.list_ready_templates()))"
50
50
True
```

`len(_SPECS) == 50`, `len(_HISTORICAL_SPECS) == 21` (W4B historical-only, never
feeding the latest catalog), `len(LAYOUT_PRESET_REGISTRY) == 55` (50 A8 latest
+ 5 pre-A8 legacy retained presets), `len(LAYOUT_PRESET_VERSION_REGISTRY) ==
84` (every registered version of every key). No `_HISTORICAL_SPECS` key/version
leaks into `list_ready_templates()`/`LAYOUT_PRESET_REGISTRY` as anything other
than its curated version "2" — confirmed programmatically for all 21 curated
keys.

Version distribution across the 50 (`Counter(s.version for s in _SPECS)`):
`{'3': 5, '2': 23, '1': 21, '8': 1}`. The 23 "2"s = the 21 W4B-curated keys
plus 2 keys that independently already carried version "2" before/outside
W4B (`playful_lifestyle`, `utility_catalog`).

Theme: `_RecipeSpec` has **no** `theme` field. `_manifest()` hardcodes
`"theme": "theme.none.v1"` identically for all 50 rows — Theme is a separate,
Store-level, merchant-selectable appearance family (confirmed in
`docs/qa_evidence/storefront_design_engine/phase5/w2_theme_overlay/00_source_inventory.md`
and `theme_catalog.py`), never varied per-Ready-Template in source.

Full 50-row table (key / version / label_fa / header / hero / layout /
product_view / card / badge / motion / footer / bottom_nav / palette / font /
density / width / radius / Home composition), in `_SPECS` source order:

| # | key | version | label_fa | header | hero | layout | product_view | card | badge | motion | footer | bottom_nav | palette | font | density | width | radius | composition |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | editorial_jewelry | 3 | آتلیه نوآر | editorial_row | immersive | three_column | editorial_grid | luxury_dark | none | none | minimal | minimal_icons | atelier-ivory | Vazirmatn | relaxed | 1200 | 0 | hero, indexed_categories, product_grid, brand_story, editorial_note |
| 2 | dense_marketplace | 3 | بازار مکس | marketplace_search | promo_bento | dense_five | dense_grid | marketplace_price | sale | dynamic | marketplace_columns | five_item | marketplace-spectrum | Vazirmatn | compact | 1500 | 8 | hero, circular_categories, sale_products, product_grid, service_strip, brands, testimonials |
| 3 | warm_boutique | 3 | کارگاه لاله | compact_menu | editorial_split | three_column | editorial_grid | paper_frame | none | subtle | brand_story | floating_dock | terracotta | Vazirmatn | relaxed | 1100 | 4 | hero, brand_story, product_grid, testimonials, newsletter |
| 4 | premium_leather | 3 | مونو | editorial_row | none | four_column | standard_grid | standard | none | none | minimal | minimal_icons | mono | Arial | normal | 1200 | 0 | ticker, chip_categories, product_grid, editorial_note |
| 5 | dark_digital | 3 | پالس نئون | floating_compact | media_feature | horizontal_rail | carousel | tech_neon | sale | dynamic | marketplace_columns | glass_dock | theme-purple-neon | Vazirmatn | normal | 1200 | 10 | hero, chip_categories, product_rail, sale_products, newsletter |
| 6 | cedar_home | 2 | سدر | centered_brand | editorial_split | four_column | standard_grid | standard | none | subtle | centered | four_item | forest | Vazirmatn | normal | 1200 | 12 | hero, tile_categories, product_grid, trust_features, collection_tiles |
| 7 | street_drop | 1 | خیابان | promo_bar | typographic | horizontal_rail | carousel | bold_outline | sale | dynamic | bold_columns | wide_cart | theme-graphite-orange | Vazirmatn | compact | 1320 | 0 | ticker, hero, chip_categories, product_rail, sale_products |
| 8 | premium_leather_noir | 2 | زر | centered_brand | immersive | two_column | editorial_grid | luxury_dark | none | none | editorial_wordmark | minimal_icons | theme-black-gold | Vazirmatn | relaxed | 1100 | 0 | hero, arch_categories, product_grid, brand_story, brands |
| 9 | search_market | 1 | میدان | marketplace_search | search_first | dense_five | dense_grid | price_first | sale | subtle | marketplace_columns | raised_cart | theme-cobalt-snow | Vazirmatn | compact | 1500 | 8 | hero, circular_categories, product_grid, trust_features |
| 10 | playful_lifestyle | 2 | غنچه | playful_canopy | image_collage | three_column | standard_grid | soft_capsule | none | dynamic | playful_wave | five_item | mint | Vazirmatn | relaxed | 1200 | 22 | hero, circular_categories, product_grid, testimonials, newsletter |
| 11 | utility_catalog | 2 | نسخه | marketplace_search | none | catalog_list | catalog_list | retail_row | none | none | centered | four_item | slate | Arial | compact | 1320 | 4 | tile_categories, product_list, service_strip |
| 12 | artisan_grain | 2 | دانه | editorial_masthead | typographic | two_column | editorial_grid | editorial_minimal | none | none | brand_story | floating_dock | olive | Vazirmatn | relaxed | 1100 | 0 | hero, indexed_categories, product_grid, brand_story, collection_tiles |
| 13 | pixel_play | 1 | پیکسل | category_tabs | promo_bento | bento_grid | bento | soft_capsule | sale | dynamic | minimal | raised_cart | violet-pop | Vazirmatn | normal | 1200 | 14 | hero, tile_categories, bento_products, newsletter |
| 14 | simorgh_market | 2 | سیمرغ | centered_brand | promo_bento | four_column | standard_grid | marketplace_price | sale | subtle | marketplace_columns | five_item | royal | Vazirmatn | normal | 1320 | 8 | hero, circular_categories, product_grid, trust_features, brands |
| 15 | coastal_product | 2 | موج | overlay_transparent | product_focus | four_column | standard_grid | standard | none | subtle | centered | wide_cart | ocean | Vazirmatn | normal | 1200 | 12 | hero, chip_categories, product_grid, brand_story, collection_tiles |
| 16 | literary_catalog | 1 | کتابخانه | editorial_masthead | quiet | catalog_list | catalog_list | retail_row | none | none | editorial_wordmark | minimal_icons | amber | Vazirmatn | relaxed | 1100 | 0 | hero, indexed_categories, product_list, editorial_note |
| 17 | gallery_minimal | 1 | گالری آب | editorial_row | immersive | catalog_list | catalog_list | editorial_minimal | none | none | minimal | minimal_icons | theme-ice-cyan | Vazirmatn | relaxed | 1100 | 0 | hero, indexed_categories, product_list, editorial_note |
| 18 | handmade_luxe | 2 | چرم دست | editorial_row | editorial_split | three_column | editorial_grid | luxury_dark | none | subtle | brand_story | floating_dock | theme-terracotta-cream | Vazirmatn | relaxed | 1100 | 10 | hero, indexed_categories, product_grid, brand_story, brands |
| 19 | niloufar_glass | 2 | نیلوفر | floating_compact | image_collage | three_column | standard_grid | beauty_glass | none | subtle | centered | raised_cart | rose | Vazirmatn | relaxed | 1200 | 18 | hero, circular_categories, product_grid, collection_tiles, newsletter |
| 20 | tool_finder | 1 | آچار | marketplace_search | none | four_column | standard_grid | technical_spec | none | none | marketplace_columns | four_item | navy | Arial | compact | 1320 | 4 | tile_categories, product_grid, trust_features |
| 21 | green_workshop | 2 | سبزه | compact_menu | editorial_split | three_column | standard_grid | standard | none | subtle | brand_story | floating_dock | sage | Vazirmatn | relaxed | 1100 | 16 | hero, tile_categories, product_grid, brand_story, brands, newsletter |
| 22 | tower_department | 1 | برج | marketplace_search | campaign_mosaic | four_column | standard_grid | marketplace_price | sale | dynamic | marketplace_columns | five_item | theme-crimson-charcoal | Vazirmatn | compact | 1500 | 8 | hero, tile_categories, product_grid, sale_products, trust_features |
| 23 | beauty_dew | 2 | شبنم | floating_compact | product_focus | horizontal_rail | carousel | beauty_glass | none | subtle | minimal | raised_cart | beauty-magenta | Vazirmatn | relaxed | 1200 | 18 | hero, circular_categories, product_rail, community_gallery, newsletter |
| 24 | fashion_promo_catalog | 8 | تندر | promo_bar | promo_bento | dense_five | dense_grid | price_first | sale | dynamic | marketplace_columns | raised_cart | magenta-pop | Vazirmatn | compact | 1500 | 8 | hero, chip_categories, sale_products, product_grid |
| 25 | horizon_story | 2 | افق | overlay_transparent | side_offer_slider | two_column | editorial_grid | standard | none | subtle | brand_story | four_item | peach | Vazirmatn | relaxed | 1100 | 14 | hero, chip_categories, product_grid, brand_story, community_gallery |
| 26 | mina_community | 1 | مینا | community_shortcuts | social_gallery | two_column | editorial_grid | soft_capsule | none | dynamic | app_download | floating_dock | uupm-social-rose | Vazirmatn | relaxed | 1100 | 20 | hero, circular_categories, product_grid, community_gallery |
| 27 | silk_editorial | 2 | ابریشم | editorial_masthead | immersive | two_column | editorial_grid | editorial_minimal | none | none | editorial_wordmark | minimal_icons | atelier-ivory | Vazirmatn | relaxed | 1100 | 0 | hero, indexed_categories, product_grid, brand_story, collection_tiles |
| 28 | tuska_bento | 1 | توسکا | compact_menu | promo_bento | bento_grid | bento | luxury_dark | sale | dynamic | minimal | four_item | plum | Vazirmatn | normal | 1200 | 12 | hero, tile_categories, bento_products, testimonials |
| 29 | rayan_tech | 2 | رایان | marketplace_search | product_focus | four_column | standard_grid | technical_spec | none | subtle | app_download | four_item | theme-midnight-electric | Vazirmatn | compact | 1320 | 6 | hero, tile_categories, product_grid, service_strip, community_gallery |
| 30 | laleh_play | 2 | لاله‌زار | playful_canopy | image_collage | three_column | standard_grid | paper_frame | none | dynamic | playful_wave | five_item | sunset | Vazirmatn | relaxed | 1200 | 22 | hero, chip_categories, product_grid, brands, newsletter |
| 31 | city_classic | 2 | شهر | centered_brand | editorial_split | four_column | standard_grid | standard | none | subtle | brand_story | four_item | uupm-professional-navy | Vazirmatn | normal | 1200 | 8 | hero, circular_categories, product_grid, brand_story, collection_tiles |
| 32 | collection_index | 1 | کلکسیون | compact_drawer | none | catalog_list | catalog_list | catalog_index | none | none | minimal | minimal_icons | catalog-colorful | Arial | compact | 1100 | 0 | indexed_categories, product_list, editorial_note |
| 33 | kamand_artisan | 2 | کمند | overlay_transparent | editorial_split | three_column | editorial_grid | editorial_minimal | none | subtle | brand_story | floating_dock | terracotta | Vazirmatn | relaxed | 1100 | 6 | hero, indexed_categories, product_grid, brand_story, community_gallery |
| 34 | almas_luxury | 2 | الماس | floating_compact | product_focus | three_column | editorial_grid | shelf_editorial | none | subtle | marketplace_columns | glass_dock | theme-ice-cyan | Vazirmatn | relaxed | 1200 | 18 | hero, circular_categories, product_grid, community_gallery, newsletter |
| 35 | roosta_zigzag | 1 | روستا | playful_canopy | image_collage | editorial_zigzag | featured_wall | marketplace_price | none | subtle | brand_story | four_item | forest | Vazirmatn | relaxed | 1200 | 16 | hero, circular_categories, featured_products, brand_story |
| 36 | mother_utility | 1 | مادر | compact_drawer | none | four_column | standard_grid | technical_spec | none | none | minimal | minimal_icons | slate | Arial | compact | 1200 | 4 | chip_categories, product_grid, trust_features |
| 37 | aftab_price | 1 | آفتاب | category_tabs | typographic | four_column | standard_grid | price_first | sale | dynamic | minimal | raised_cart | amber | Vazirmatn | compact | 1320 | 8 | hero, chip_categories, product_grid, sale_products |
| 38 | mist_quiet | 1 | مه | editorial_row | quiet | three_column | editorial_grid | standard | none | none | minimal | minimal_icons | mono | Vazirmatn | relaxed | 1100 | 14 | hero, chip_categories, product_grid, editorial_note |
| 39 | night_catalog | 1 | شبگرد | compact_drawer | quiet | two_column | editorial_grid | editorial_minimal | none | none | editorial_wordmark | minimal_icons | theme-black-gold | Vazirmatn | relaxed | 1100 | 0 | hero, indexed_categories, product_grid, editorial_note |
| 40 | watchmaker_round | 2 | ساعت‌ساز | centered_brand | product_focus | two_column | editorial_grid | portrait_round | none | subtle | centered | minimal_icons | uupm-gold-purple-tech | Vazirmatn | relaxed | 1100 | 12 | hero, indexed_categories, product_grid, brand_story, brands |
| 41 | kite_playful | 1 | بادبادک | playful_canopy | image_collage | four_column | standard_grid | soft_capsule | none | dynamic | playful_wave | five_item | uupm-playful-orange | Vazirmatn | relaxed | 1200 | 22 | hero, circular_categories, product_grid, testimonials |
| 42 | pine_eco | 2 | کاج | compact_menu | editorial_split | three_column | standard_grid | soft_capsule | none | subtle | centered | floating_dock | sage | Vazirmatn | relaxed | 1200 | 16 | hero, tile_categories, product_grid, brand_story, collection_tiles, newsletter |
| 43 | mirror_beauty | 2 | آینه | floating_compact | product_focus | three_column | standard_grid | beauty_glass | none | subtle | minimal | raised_cart | beauty-magenta | Vazirmatn | relaxed | 1200 | 18 | hero, circular_categories, product_grid, brand_story, community_gallery, newsletter |
| 44 | charcoal_grill | 1 | زغال | promo_bar | product_focus | four_column | standard_grid | bold_outline | sale | dynamic | bold_columns | wide_cart | theme-graphite-orange | Vazirmatn | compact | 1200 | 0 | hero, chip_categories, product_grid, sale_products |
| 45 | calligraphy_paper | 1 | خط | compact_drawer | immersive | catalog_list | catalog_list | editorial_minimal | none | none | editorial_wordmark | minimal_icons | mono | Vazirmatn | relaxed | 1100 | 0 | hero, indexed_categories, product_list, brand_story |
| 46 | harbor_imports | 2 | بندر | marketplace_search | campaign_mosaic | four_column | standard_grid | shipping_label | sale | subtle | marketplace_columns | four_item | navy | Vazirmatn | compact | 1320 | 6 | hero, tile_categories, product_grid, sale_products, trust_features, brands |
| 47 | parnian_editorial | 2 | پرنیان | editorial_masthead | immersive | two_column | editorial_grid | shelf_editorial | none | none | editorial_wordmark | minimal_icons | uupm-bakery-cream | Vazirmatn | relaxed | 1100 | 0 | hero, arch_categories, product_grid, brand_story, community_gallery |
| 48 | racer_tech | 1 | تک‌سوار | promo_bar | media_feature | horizontal_rail | carousel | technical_spec | sale | dynamic | marketplace_columns | wide_cart | uupm-gaming-neon | Vazirmatn | compact | 1320 | 6 | ticker, hero, chip_categories, product_rail, sale_products |
| 49 | ferdowsi_department | 1 | فردوسی | centered_brand | campaign_mosaic | featured_split | featured_wall | marketplace_price | sale | subtle | marketplace_columns | five_item | uupm-burgundy-gold | Vazirmatn | normal | 1320 | 8 | hero, tile_categories, featured_products, product_grid, brands, trust_features |
| 50 | anniversary_mosaic | 1 | پنجاه | editorial_row | promo_bento | bento_grid | bento | catalog_index | sale | dynamic | editorial_wordmark | floating_dock | uupm-creative-pink | Vazirmatn | normal | 1320 | 12 | ticker, hero, circular_categories, bento_products, testimonials, newsletter |

Bold-equivalent (version "2" AND in the W4B curated set) keys: cedar_home,
premium_leather_noir, artisan_grain, simorgh_market, coastal_product,
handmade_luxe, niloufar_glass, green_workshop, beauty_dew, horizon_story,
silk_editorial, rayan_tech, laleh_play, city_classic, kamand_artisan,
almas_luxury, watchmaker_round, pine_eco, mirror_beauty, harbor_imports,
parnian_editorial (21).

---

## 5. Base matrix cardinality — no reduction found

Every one of the 50 rows above sets its own `layout`, `product_view`, and
`card` fields, confirming Listing and PDP rendering are genuinely
Template-bound (not just Home) — `product_view`/`card` directly select the
Listing/PDP product-card presentation per Template. No architectural
impossibility was found that would require reducing the matrix below:

```
50 Templates × 4 public page classes (Home, Listing, PDP, Cart) × 3 viewports
= 600 base certification cells
```

---

## 6. Shared certification fixture

**Store:** `rasti-mode-demo` (the same Store `capture_ready_template_previews.py`
and W4B's browser QA already targeted).

**Seed authority:** `python manage.py seed_ready_template_fashion_demo`
(`apps/stores/management/commands/seed_ready_template_fashion_demo.py`).
Confirmed by reading the command's source: seeds Categories, Brands (via
`get_or_create`, idempotent), Products with real variants (`product_type`
SIMPLE/VARIABLE via `variant_engine_service.add_product_option` +
`generate_variants` — real size/color option axes and stock),
MerchantCollections, HeroSlides, PromotionalBanners, StoryRailItems — the
exact fixture already proven sufficient for every W4B curated-key browser
check (collection_tiles/brand_carousel/story_rail all rendered real content
from this fixture).

**Cart/shipping:** `Product.requires_shipping` defaults `True`; the fashion
demo fixture's products are all physical (shipping-required) — sufficient for
the Cart contract's "shipping-relevant item" and Free-Shipping-Goal checks
using physical items. An "all-digital cart" state (one of the four states
`public_w1_qa.mjs` already exercises against a *different*, dedicated fixture)
is out of scope for the per-Template W4C matrix: the master plan's own phrase
"Free-Shipping Goal from W1 where applicable" is conditional, and the
all-digital edge case is already certified once, by W1, independently of
which Ready Template is active (the widget's digital/physical logic lives in
`apps/cart/services/pricing.py`, not in any Ready Template).

**PDP variant fixture:** the seed command's `_seed_variants` step guarantees
at least one product with real Size/Color variant axes, satisfying "variant
controls when fixture/product supports variants" without per-template
special-casing — W4C picks one deterministic variant-bearing product from the
shared fixture (not a random pick) for every PDP cell.

No fixture IDs are placed in Ready Template DNA (no `_RecipeSpec` field
references a Product/Category/Store id); every Ready Template's sections
resolve merchant content generically (by Store scope), exactly as W4B's own
architecture audit already confirmed for the 21 curated keys.

---

## 7. Route inventory (confirmed via `urls.py`)

- Home: Store's public root (`/`), rendered by `catalog/views.py::home` /
  `home_visual.html` — same view every Ready Template's Home renders through.
- Listing: `catalog:product-list` → `/products/`.
- PDP: `catalog:product-detail` → `/products/<uslug:slug>/`.
- Cart: `cart:detail` → `/cart/` (`cart:add`, `cart:item-update`,
  `cart:item-remove` for the mutation checks).

---

## 8. Theme sub-matrix — source-derived, bounded (not guessed)

`docs/qa_evidence/storefront_design_engine/phase5/w2_theme_overlay/00_source_inventory.md`
+ `w2_implementation_report.md` (certified W2 evidence) establish: Theme is a
single, Store-level, orthogonal `appearance_token` family (`theme` selection +
`settings["theme"].intensity`), rendered ONLY as `data-occasion-theme` /
`data-occasion-tone` / `data-occasion-intensity` attributes + `--occasion-*`
CSS custom properties on the shared `<html>` shell (`templates/base.html`) —
never per-section, per-Template logic. `clear_theme()` resets to
`theme.none.v1` and "touches nothing else" (byte-for-byte preservation of
every other selection). W2 itself already certified the full occasion ×
intensity × viewport matrix — "3 occasions × 3 intensities × 3 viewports = 54
cases" — against 2 representative templates, with an explicit, PASSing
"Mourning tone safety" check (`muharram`: "structurally no festive/countdown/
sale flags; CSS restrained; visually confirmed").

Verified via `theme_catalog.list_theme_occasions()`: 8 occasions — `none`
(neutral, no-op), `nowruz`/`yalda`/`valentine` (festive), `ramadan`/
`eid_fitr`/`eid_qorban` (neutral observance), `muharram` (mourning).
`THEME_INTENSITY_CHOICES = ('subtle', 'balanced', 'strong')`, default
`balanced`.

Because Theme's mechanism is proven uniform/orthogonal (shell-level
attributes, not per-Template code), re-running W2's full occasion × intensity
matrix on all 50 Templates would not exercise any Template-specific code path
— the genuine, still-open question W4C must close is only: **does the
shell-level overlay mechanism visually/functionally survive every distinct
Header/Footer/Bottom-Nav combination present across the 50, and every one of
the 21 new W4B section families**, neither of which existed when W2 chose its
original 2 representative templates.

Computed via source (`_SPECS` header/footer/bottom_nav triples):

```
$ /usr/bin/python3 -c "... Counter of (header, footer, bottom_nav) across _SPECS ..."
distinct (header, footer, bottom_nav) triples: 33
```

**Theme representative set** = (one Template per distinct triple) ∪ (all 21
W4B-curated keys), deduplicated = **40 Templates** (33 triple-representatives,
of which 14 already are curated keys, plus the 7 curated keys not otherwise
selected as a triple's representative). Full 40-key list is deterministic and
reproducible from source (`_SPECS` iteration order ∪ curated-key set); it is
recorded in the plan document (§9) rather than duplicated here.

**Bounded Theme additional matrix (two tiers, both reusing only the existing
`apply_theme`/`clear_theme` authority-service calls — no new Theme
mechanism):**

- **Tier 1 (breadth):** 1 occasion per tone (`nowruz`=festive, `ramadan`=
  neutral, `muharram`=mourning) × `balanced` intensity (default) × Desktop
  viewport only (Theme's CSS-variable/attribute mechanism is not a responsive
  concern) × all 40 representative Templates → apply, verify
  `data-occasion-*` attributes present + zero console/page/overflow
  regressions + (muharram only) no festive/sale/countdown marker present →
  clear → verify reversion to the Template's own `theme.none.v1` baseline
  Home capture. **= 3 occasions × 40 Templates = 120 apply/clear cells.**
- **Tier 2 (depth, closes the W4B-curated gap):** reuses W2's own certified
  shape exactly — 3 occasions (one per tone) × 3 intensities × 3 viewports —
  applied to exactly 2 Templates: one of W2's own original certified
  Templates (continuity) and one W4B-curated Template with a new section
  family (gap closure). **= 2 Templates × 27 cases = 54 cells.**

**Total Theme additional matrix: 174 cells**, on top of the 600 base cells
(§5), for a grand total of **774 certification cells** this workstream
defines.

---

## 9. Conclusion

No architectural impossibility was found anywhere in this inventory. Every
requirement in the authoritative plan's W4C section is satisfiable by a
bounded, in-place extension of
`apps/storefront_builder/management/commands/capture_ready_template_previews.py`,
reusing: the Python `playwright` package it already depends on, the canonical
`preset_service`/`layout_service` apply/publish path, the canonical
`--host-resolver-rules` public-host resolution pattern, the canonical
`ThreadPoolExecutor` ORM-thread-safety pattern, the shared
`rasti-mode-demo`/`seed_ready_template_fashion_demo` fixture, the canonical
`catalog:product-list`/`catalog:product-detail`/`cart:detail` routes, and the
canonical `apply_theme`/`clear_theme` authority-service calls. No second
harness, no second Playwright package, no second browser launcher, no second
public-storefront renderer, no parallel Apply/Publish authority, and no
separate W4C-only route system are proposed. See the implementation plan
(`docs/superpowers/plans/2026-09-17-phase5-w4c-all50-browser-certification.md`)
for the full task breakdown, pass/fail contracts, evidence plan, and
resumability design.
