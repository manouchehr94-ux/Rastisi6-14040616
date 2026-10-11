# Background / colour contract — Amazing Offers + all background-aware sections

Owner report: *Design → Background → Custom colour* on «پیشنهادهای شگفت‌انگیز» showed no visible change.

## 1. Reproduction (real Studio UI, Rasti Mode Demo, sandbox copy)

Value at every stage when the custom colour `#0066ff` is chosen (trace: `ui_qa_trace.txt` for the final contract run):

| Stage | Value |
|---|---|
| native `input[type=color]` event | `#0066ff` (input phase → coalesced, 110 ms) |
| `section.update_settings` patch | `{"background":{"mode":"color","color":"#0066ff",…}}` |
| persisted `StorefrontSection.settings["background"]` | `{"mode":"color","color":"#0066ff","media_asset_id":null,"pattern_slug":"","palette_role":""}` |
| effective settings | identical (schema normalisation keeps the colour) |
| returned fragment wrapper | `data-bg-mode="color"` · `style="background-color:#0066ff;--sfb-section-bg-color:#0066ff;--sfb-section-fg:#FFFFFF;…"` |
| computed `.rsec` background (main + mini) | `rgb(0, 102, 255)` — **correct** |
| what the merchant saw | white panel |

The pipeline was correct end to end; the colour was **covered**, and the edit additionally took the *full-iframe-reload* path.

## 2. Exact element that hid the colour

`div.special-wrap` — a single panel that covers **94.1 %** of the section (measured on a 12 px sample grid, outermost painter below the wrapper), leaving a 14 px / 12 px frame. Computed background before: `rgb(255, 255, 255)`. Stylesheet winner (all rules matching the element that carry a background):

| Sheet | Rule | Fill | Priority |
|---|---|---|---|
| `home.css` | `.special-wrap{background:#fff}` (×2) | `#fff` | normal |
| `storefront_builder.css` | `.special-wrap{…background:#fff…}` | `#fff` | normal |
| **`theme_palette.css`** | `.catstrip-inner,.tabs,.blog-card,.feat,.promo-card,.special-wrap,.brand-tile,.product-spotlight-*…{background:var(--theme-card-bg,var(--theme-surface))!important}` | `rgb(255,255,255)` | **`!important` — the computed-style winner** |

On top of it: `.special-list` `#f7f8fa`, `.special-panels` `linear-gradient(135deg,#fff,#fbfbfc)`, list buttons `#fff`, `.special-image` `#fff`.
Second finding: the fragment contained a `<script>` (the countdown `Alpine.data`) and the Studio **rejects** such a fragment, so every Amazing Offers edit fell back to the full twin-iframe reload.

Computed style **after**: `.special-wrap` `rgba(0, 0, 0, 0)` (transparent, contract rule wins by specificity + `!important`), `.rsec` `rgb(0, 87, 255)`, panel text `rgb(255,255,255)` (`--sfb-section-fg:#FFFFFF`), `.special-list` a 4 % text tint, buttons keep `--brand-surface`.

## 3. The generic solution — primary-surface contract

No template key, no section key, no section-specific Inspector (`storefront_builder.css`, block *PRIMARY-SURFACE CONTRACT*):

* A component whose main visual surface **is** the section marks it `data-sfb-section-surface` (`="ink"` additionally takes the fill's foreground).
* Explicit fill (`color`, `palette`, `pattern`, `palette_pattern`): the marked surface is transparent (`!important`, to out-rank the palette sheet's `!important` card rule) and exposes `--ssf-fg / --ssf-accent / --ssf-price / --ssf-muted` derived from `--sfb-section-fg` (server-side `contrast_fg`).
* Picture fill (`image`, with fit / position / overlay / bleed): the surface becomes a translucent scrim (`color-mix(brand-surface 84 %, transparent)` + 3 px blur) so the picture stays visible and text stays readable.
* No explicit fill (`theme`, `surface`): the component keeps its own default surface (tokens).
* An explicit design «رنگ سطح» (`data-d~=surface`) still wins over the fill.
* Inner cards, list buttons and product-media tiles are **not** marked — independent semantic surfaces.

Marked surfaces: Amazing Offers `.special-wrap`; hero / image slider `.hero-inner`; product-section spotlight (section, slider, head, track); trust features `.feat` ×5.
The countdown became an inline Alpine component (no `<script>`), so Amazing Offers edits are partial refreshes.

## 4. Hard-coded colours changed (Amazing Offers) and their class

| Colour(s) | Where | Class | Now |
|---|---|---|---|
| `#fff` | `.special-wrap` | surface | `var(--brand-surface)` default; transparent under an explicit fill |
| `#e0e3e8`, `#e5e7eb`, `#e2e5e9`, `#e7e9ed` | wrap / list / title borders | border | `--brand-border` / `color-mix(currentColor 12–14 %)` |
| `#f7f8fa`, `#fafafa` | `.special-list` | surface (tint) | `color-mix(--brand-text 3–4 %, transparent)` |
| `#fff → #fbfbfc` gradient | `.special-panels` | surface | removed (the wrap/fill owns the surface) |
| `#fff`, `#4b4f56`, `#d9dde3`, `#fecaca`, `#b91c1c`, `#ef4444` | list buttons (default/hover/active) | card surface / text / border / accent | `--brand-surface`, `--brand-text`, `--d-accent` mixes |
| `#24272c`, `#222` | list title, `h3` | text | `inherit` (follows the fill's foreground) |
| `#6a6f77`, `#6b6f74` | brand, old price, list price | muted | `--ssf-muted` / `--brand-muted` |
| `#c93939` | kicker, countdown | accent | `--ssf-accent` / `--d-accent` |
| `#127e50` | price | price (success) | `--ssf-price` / `--brand-success` |
| `#34383f`, `#fff`, `#292d33` | buy button (+ hover) | button | `--brand-text` / `--brand-surface` |
| `#fff`, `#f8f8f7` | `.special-image` | **product-media neutral** | `--brand-surface` (kept as a tile) |
| `#c5cad0` | placeholder glyph | muted | `color-mix` of text/surface |
| `#d53d3d` + white | `.special-discount` badge | **danger / sale accent** | intentionally unchanged (≥ 4.5 : 1) |

Legacy `home.css` surfaces for the same widget (`.special-wrap` ×2, `.special-list` ×2, `.special-panels` gradient, `.amazing-offers-section .special-list{#f7f8fa}` + button override) were converted at source as well, so no stylesheet repaints them.
Other sections: `.hero-inner`, `.product-spotlight-slider/-head/-track`, `.feat` defaults `#fff`/`#e2e5ea` → `--brand-surface` / `--brand-border`; `.feat small` muted ink follows the fill.

## 5. The 20-section audit (white `#FFFFFF` → `#0057FF`, painted result on the owning element)

Method (`qa/background_contract.py`): sample grid per section → outermost element below the wrapper that paints each pixel → share painted by the fill, dominant inner painter, outer-frame ring.

| section | before | after |
|---|---|---|
| amazing_offers | **HIDDEN BY INNER SURFACE** (`.special-wrap` 94.1 %) | PASS |
| hero_banner | **HIDDEN BY INNER SURFACE** (`.hero-inner` 97.7 %) | PASS |
| image_slider | **HIDDEN BY INNER SURFACE** (`.hero-inner` 93.8 %) | PASS |
| trust_features | **PARTIAL ONLY** (`.feat` cards) | PASS |
| product_section · spotlight (autoplay carousel) | **HIDDEN BY INNER SURFACE** (section/slider 96.3 %) | PASS (card tiles: one product card is the content) |
| multi_banner | PARTIAL ONLY (image tiles reach the edges) | PASS (CARD / MEDIA TILES) — the fill frames the tiles and shows in the gaps/padding |
| product_section · campaign band ×2 | "NO CONSUMER" (audit artefact) | PASS — the band **is** the owner of the fill (it paints `--sfb-section-bg-color`); the first metric mis-read its all-transparent overlay layer as an image |
| product_section ×7 (grids/carousels), newest/best/discounted, brand_carousel, category_grid, collection_tiles, promo_cards, rich_text, image_text, quick_links, faq, testimonials, video_section, newsletter | PASS | PASS |

Verdict vocabulary: PASS · HIDDEN BY INNER SURFACE · NO CONSUMER · OVERRIDDEN BY CSS · PARTIAL ONLY (· PASS (CARD / MEDIA TILES) when the dominant inner element is a product card / image tile — a component surface by design).
**Inspector honesty:** after the fixes every section that shows «پس‌زمینه این بخش» visibly consumes it in all modes; no section needed a hidden/disabled mode. Residual by-design note: sections whose content is edge-to-edge media (multi_banner) show the fill in gaps/padding only — their padding / gap settings control how much.

## 6. Live colour input

* `input` → 110 ms coalescing → one `section.update_settings` → canonical fragment → `swapFragmentIn` for **both** the main Preview and the workspace mini-frame (same fragment).
* Path: `fragment` for 5/5 edits (no full iframe reload); a 12-event drag produced **1** write; last colour wins.
* Latency (browser, sandbox: Django dev server, DEBUG, SQLite, 31 sections on the page): input → both frames median **≈ 400–430 ms** (289–496 ms); the mutation request's server time is 275–500 ms in that environment (≈ 155–220 ms in-process with DEBUG off). The **≤ 200 ms median target is NOT met in this sandbox**: the cost is the shared mutation + fragment pipeline (115 queries, draft history snapshot, whole-page structure build) which is identical for every section (a `rich_text` background edit costs the same, 143–237 ms server in-process) and was not changed here. The edit no longer pays for a full reload, and the opt-in latency test keeps its existing CI headroom (≤ 450 ms simple median).

## 7. Browser QA (A–G) — `A_original_theme.jpg … G_revert_theme.jpg`

Each screenshot shows the Settings Workspace (Design tab) with the live mini preview. Computed values per step are in `ui_qa_trace.txt` (main and mini identical in every step).

| Step | Mode | Result |
|---|---|---|
| A | original (theme) | white panel, tokens |
| B | custom `#0057FF` | wrapper `rgb(0,87,255)`, `.special-wrap` transparent, ink white; main = mini |
| C | custom `#101828` | wrapper `rgb(16,24,40)`, ink white; main = mini |
| D | palette tone-3 | wrapper `rgb(186,102,0)`, ink black (AA); main = mini |
| E | image | picture on the wrapper, panel is the translucent scrim (`rgba(255,255,255,.84)`) |
| F | image + overlay 45 % | overlay layer present (`data-bg-overlay`), scrim intact |
| G | revert → theme | original white panel restored |

Also proven: the value survives close/reopen and a page reload (`#101828`), no horizontal overflow (`overflowX 0`) in every step. Section close-ups with `#0057FF`: `section_*_custom_blue.jpg`. Published parity is asserted in a test fixture only (no real store was published).

## 8. Tests

* `tests/test_background_contract.py` (14, always on): contract CSS is generic (no template/section key), out-ranks the palette sheet's `!important`, markers in all templates, no `<script>` in the Amazing Offers fragment, no fixed surface literals left in either sheet, inks follow tokens, classifier verdicts; Amazing Offers colour round trip (schema → persisted → wrapper → script-free fragment), fragment == full Preview, every background mode reaches the wrapper with a consumer, AA contrast of the fg token over 7 fills, Preview == Published wrapper; **every** background-offering section renders the custom colour on its wrapper.
* `tests/test_background_contract_browser.py` (4, opt-in `SFB_BROWSER_TESTS=1`): Amazing Offers colour / dark / bleed / pattern / palette / image / image+overlay computed styles and Preview == Published; painted-share check (`ring 100 %`, dominant < 50 %); **the 20-section white→blue audit**; live colour input = coalesced script-free partial refresh, main + mini identical, reopen + reload persistence.
* Intentionally updated: `test_phase4_task5_cross_page_css` (pins of the converted rule literals — surfaces are now tokens).

Not touched: Templates 52/53. Not pushed, no PR, no merge, no deploy.

## 9. Verification run

Focused suites (802 tests: background contract, cross-page CSS, reference templates 51–53, renderer, schema, registry, presets, designability, campaign panel, settings workspace …): all pass after updating the two files that pin changed rule literals (`test_phase4_task5_cross_page_css`, `test_interaction_performance_campaign_panel`). Opt-in browser suite `test_background_contract_browser` (4 tests): pass. `manage.py check`: no issues; `makemigrations --check`: no changes; `git diff --check`: clean. The full suite was not run.
