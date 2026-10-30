# Hero Stage — Header + Hero composition engine (M0 audit + design contract)

Base: `b9562ccf` on `feature/admin-panel-modernization-20261029` (HEAD = remote at start, working tree clean).
Reference kit: `rasti-design-brief.zip` (7 HTML files, SHA-256 verified against `REFERENCE_SHA256.txt`; extracted outside Git).

## 1. The seven references (DOM/CSS evidence, not file names)

All seven are one `<section class="relative … min-h-[84vh] flex flex-col justify-between overflow-hidden text-white">` with a full-bleed
background (`<img absolute inset-0 object-cover>` or a two-column grid), a `bg-gradient-to-b from-black/.. via-black/.. to-black/..`
scrim, a `<header class="relative z-20">` **inside** the section, then content blocks (`relative z-20`).
They need Tailwind CDN + Google Fonts + Unsplash; `addToCart`, `setCategory`, `handleSearch`, `showToast`, `openProductModal`
are called from `onclick`/`oninput` but **defined in none of the files** → purely presentational, nothing to port as behaviour.
Structural comparison: refs 1 ≡ 7 and 2 ≡ 8 have **byte-identical hero structure** once text/image URLs are blanked
(only brand text and photo differ) → the kit contains **five** distinct compositions, not seven.

| Composition | Refs | Header | Hero body | Bindable (real data) | Presentation only |
|---|---|---|---|---|---|
| A centred stack | 1, 7 | 12-col grid: side note · centred brand over nav · search + cart | centred eyebrow/H1/white CTA | brand, nav, search, cart, CTA link | side note «کالکشن ۲۰۲۶ • ۱۵ اثر», toast |
| B single row + bottom-start text | 2, 8 | one row: brand · nav · search + cart | start-aligned eyebrow/H1/CTA, bottom | brand, nav, search, cart, CTA | handlers |
| C dual panel | 3 | bordered row with logo mark | 50/50 two-image background (`hidden md:block` 2nd panel), centred glass box (`bg-black/40 backdrop-blur-md border`) | brand, nav, search, cart, 2 images | box copy |
| D editorial | 4 | bordered row, brand + sub-brand | 8/4 grid: badge + H1 + CTA ▏ floating featured product card (`bg-white/10 backdrop-blur-xl`) | product (title/price/url/image), nav | «اثر برگزیده» label |
| E glass category bar | 6 | one row, pill cart | centred title/CTA + **glass category bar** at the bottom of the hero (`bg-black/45 backdrop-blur-xl rounded-2xl`) | categories + counts + routes | counts hard-coded «(۱۵)» |

## 2. Real engine (read from code, not from earlier reports)

| Capability | Status | Evidence | Note |
|---|---|---|---|
| Header lives in the same container as the hero | **unsupported** | `templates/storefront_shell.html:10` `{% block header %}` is rendered by `base.html` **before** `<main class="sfb-storefront-canvas">`; sections render in `partials/render_rows.html:35` → `responsive_section_wrapper.html:89` | header and hero are siblings, no shared stacking context/background |
| Variant named «شفاف روی تصویر» (`overlay_transparent`) | **partial (name only)** | `global_region_registry.py:315`; `partials/global_header/overlay_transparent.html:1` is `<div class="a8-global-silhouette a8-global-silhouette--overlay">` + `include atelier_nav.html`; no CSS/JS in the repo contains `silhouette` | DOM-identical to `atelier_nav`; used by 3 A8 templates (`a8_ready_templates.py:321/338/353`) — must not change |
| Header config persisted in the Draft/Published version | supported | `models.py:263` `header_config` JSON; `layout_service.py:286` `validate_header_config` (closed allowlist; sparse extensions such as `geometry`) | |
| Hero as a section with schema-driven Inspector | supported | `section_registry.py:3421` `hero_banner` (+`HERO_BANNER_SCHEMA`); `settings_schema.py:21` field types text/choice/integer/boolean/color/media/repeater/design/background | data comes from shared Store `HeroSlide` rows |
| Per-section Store-scoped media | supported | `render_service.py:576` `_image_text_context` → `content.services.resolve_background_media_url` (fail-closed) | |
| Per-section destination (real URL) | supported | `render_service.py:~590` `_resolved_destination_context` → `resolve_destination_setting` | |
| Dynamic products / categories | supported | `section_data_service.resolve_products`, `storefront_context_service._top_level_categories` | |
| Generic styling block (colour/border/radius/shadow/spacing/height/image fit) | supported | `design_block.py` (capabilities declared per section) | |
| Section registered in the Studio library, saved in Draft, copied on publish, undo/redo | supported (existing) | `section_registry.py` registry, `r4_mutation_service.py`, `edit_history_service.py` | new section type inherits all of it |
| Ready Template picker changes only the Draft | supported | `preset_service.apply_preset`; `ready_template_card_service.py` | |
| Gallery thumbnail for any registered template | supported (SVG, registry-derived) | `template_preview_service.py:93` `_ARCHETYPE_WEIGHTS` (unknown section → plain block); real screenshots only when a fresh sidecar exists (`:493`) — none committed | new section needs an archetype entry |
| Four header render call sites | supported | `storefront_shell.html:10`, `preview.html:14`, `ready_template_live_preview.html:29`, `views.py:242` / `:546` | embedding must be decided once and honoured by all four |
| Catalog count guard | supported | `tests/_catalog_count.py:4` `READY_TEMPLATE_COUNT = 59` (20 test modules) | becomes 63 |
| Free pixel drag/resize of arbitrary elements | **unsupported (by design)** | renderer is flow/grid based; Composer resizes Cells/Groups, not sub-elements | replaced by bounded slots + alignment + order + per-breakpoint overrides (below) |
| Video background | **not offered** | no approved video pipeline for sections | not faked |

Root cause: **renderer/shell topology** (header is a shell-level global region), not schema or editor — the editor/save/publish chain is
already generic. A compositional fix therefore needs (a) a model for the stage, (b) a shell decision "header embedded in the first stage",
(c) CSS for the embedded skin.

## 3. Design contract (what M1 implements)

**New section `hero_stage`** («بوم هدر و هیرو», category «تصاویر و تبلیغات», home page, max 1 instance) — a normal registered section, so
Draft/Published/history/Inspector/library/security all come from the existing pipeline. Settings (flat, all optional, closed allowlist,
server-validated, `design` block for colour/border/radius/shadow/spacing):

* `header_mode`: `independent | overlay | merged` (default `merged`).
  `independent` = shell header as today; `merged` = the global header is rendered **inside the stage** in normal flow over the shared
  background; `overlay` = same DOM, header floats absolutely over the top of the stage (stage content is padded).
* Panels: `panel_layout: single|dual`, `panel_a_media_asset_id`, `panel_b_media_asset_id` (Store media library), `panel_a/b_focal_x/y`
  (0–100), `image_fit: cover|contain`, `fallback_color`, `mobile_dual: stack|first_only`.
* Scrim: `scrim_style: none|top|bottom|both|full`, `scrim_strength` 0–90, `scrim_tone: dark|light`.
* Size: `height_desktop`, `height_tablet`, `height_mobile` (vh, 40–100).
* Slots (ordered repeater `slots`, each `eyebrow|title|subtitle|cta|categories|product_card`): order is the render order; per-slot hide per
  device via `hide_tablet`/`hide_mobile` flags. Text: `eyebrow`, `title`, `subtitle`, `cta_label` + `destination` (real URL via existing
  destination picker), `cta_style: solid|outline|glass`.
* Content frame: `content_align: start|center|end`, `content_valign: top|middle|bottom`, tablet/mobile overrides (`*_tablet`, `*_mobile`),
  `content_panel: none|glass|solid`, `panel_opacity`, `panel_blur`, `content_max_width`.
* Typography: `title_size: sm|md|lg|xl`, per-device `title_size_tablet/mobile`, `title_weight`, `text_tone: light|dark`.
* Modules: `category_limit` (real Store categories + product counts), `product_source: featured|newest|manual` + `product_id`
  (Store-scoped product; price/URL/image from the Product row).
* `v: 1` serialisation marker; absent keys = defaults (no migration; stores that never add the section are untouched).

**Shell integration**: one helper in `render_service` decides `header_embedded` from the page's render items (first top-level item is a
`hero_stage` whose `header_mode != independent`, page not in container layout); the four header call sites render the shell header only when
`not header_embedded`; the stage includes the same `header_variant_template` with the same `header_config`. Any other page (checkout, product,
account…) or a stage that is not first → header stays in the shell (safe fallback). Header variant stays an independent choice, so any
header variant from any template can be combined with any stage (cross-preset test).

**Backward compatibility**: `independent` shell path unchanged; `overlay_transparent` untouched; no migration; existing templates and stores
render byte-identically (tests assert shell output without a stage is unchanged).

**Security**: all text length-capped and auto-escaped; CTA only through `resolve_destination_setting`; media only through
`resolve_background_media_url` (Store-scoped, fail-closed); focal/size/opacity clamped integers; choices allowlisted; styling emitted only as
CSS custom properties built from validated ints/choices; no HTML/CSS/JS from the merchant.

**Out of scope (reported, not built)**: free pixel dragging, video backgrounds, containers-layout embedding (stage inside a Composer cell
degrades to `independent`), changing `overlay_transparent`, Cart/checkout/finance.
