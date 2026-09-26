# 08 — Target Architecture and File Plan (Design Only — No Implementation)

Reading guide, matching the convention already established in this repository's own sibling planning documents (`docs/reports/STOREFRONT_TEMPLATE_AND_BUILDER_ARCHITECTURE_PLAN.md`): 🔍 **FACT** (verified in current code), 💡 **RECOMMENDATION** (this document's proposal), ❓ **OPEN DECISION** (needs the owner, tracked with a `Q-XX` reference into `09_QUESTIONS_FOR_OWNER_FA.md`).

**No code, migration, template, or test changes have been made as part of this document.** This is Gate-1 output only.

---

## 1. Template-family manifest/registry

💡 **Recommendation: a new, separate, code-defined registry — `apps/storefront_builder/family_registry.py` — following the exact existing pattern of `section_registry.py` and `appearance_registry.py` (both platform-owned Python dictionaries, not database tables, per those files' own documented rationale: family definitions are reviewed platform content, versioned via git/code-review, not merchant-authored data).**

Proposed shape (dataclass, mirroring `SectionDefinition`/`TemplateDefinition`'s existing style):

```python
@dataclasses.dataclass(frozen=True)
class FamilyDefinition:
    slug: str                     # "vibrant_catalog" | "heritage_premium" | "artisan_editorial" | "modern_fashion" | "nordic_living"
    name_fa: str
    description_fa: str
    header_variant: str           # header/nav renderer identifier — see §4
    hero_variant: str
    category_variant: str
    footer_variant: str
    product_card_variant: str     # "square_centered_commerce" | "premium_portrait" | ... (see §4)
    product_page_variant: str
    default_appearance_template_slug: str   # which of the EXISTING 10 appearance_registry templates this family defaults to for radius/density/motion baseline (see §3 — the two systems compose, they do not merge)
    schema_version: int
    readiness: str                # draft | production_ready | deprecated — reusing the exact enum vocabulary already established by IndustryTemplate (apps/catalog/models.py:1339-1349) rather than inventing a new one
```

Per-store selection: a `family_slug` key added to `StorefrontLayoutVersion.appearance_config` (the same JSONField that already carries `template_slug`/`palette_slug`, `models.py:151-158`) — **not a new model, not a new versioned field** — because `appearance_config` is already Draft/Publish/Rollback-aware exactly like this new selection needs to be. `effective_appearance_config()` (`models.py:193-201`) gains one more default key (`"family_slug": None`), following the identical pattern already used for every other appearance key.

❓ **OPEN DECISION (the central one of this whole task, `Q-01`/`Q-02` in the questions doc).** Does `family_slug` coexist with the existing `template_slug` (10 CSS-token templates) as two independent axes — e.g. a store picks `modern_fashion` (DOM anatomy) *and independently* `boutique` (radius/motion/card-shadow flavor) — or does selecting a family fix/override the appearance template entirely? 💡 This document's recommendation: **coexist, with the family supplying only a *default* `template_slug` that the merchant can still override**, exactly mirroring how `TemplateDefinition` already supplies default `font`/`radius`/`density` that a merchant can override via `color_overrides`/direct fields (`appearance_registry.py:67-70`, "این‌ها فقط پیش‌فرضِ اعمال‌شده هنگامِ انتخابِ Template‌اند"). This preserves the master prompt's explicit requirement that "Palette, Typography, Motion, Component Style, and Density independently overrideable" survive family selection.

## 2. Section-instance contract

🔍 **FACT.** The existing `StorefrontSection` contract (`section_key`, `order`, `is_active`, `settings` JSONField, `collapsed_in_editor`) and the existing `SECTION_REGISTRY` (22 types, `section_registry.py`) already satisfy essentially everything the master prompt asks for at this level: enabled/hidden/order, titles/links/content references (`product_section`'s `title`/`subtitle`/`cta_link` fields), collection/category/product selection+ordering (`PRODUCT_SECTION_DATA_SOURCES`, §2.2 of doc 01), layout settings (columns via responsive settings), desktop/mobile media, validation+defaults+schema versioning (each section's `validate_settings` callable).

💡 **Recommendation: no new section-instance contract fields are needed.** What each family needs is a small, additive `render_variant` setting (optional, defaults to `None` = the section's platform-generic rendering) on the *few* section types whose rendering must differ by family — concretely: `hero_banner` (promo-dashboard / full-bleed-campaign / editorial / carousel / neutral-circular), `category_grid` (quick-icon / portrait-row / banner-overlay / editorial-tiles / none-by-default), and `product_section` (which card renderer it uses). This is exactly the `render_variant` mechanism the (stale but still architecturally sound on this specific point) `STOREFRONT_TEMPLATE_AND_BUILDER_ARCHITECTURE_PLAN.md` §5.1 already proposed for a similar reason — reuse that idea, not the rest of that document's now-superseded status claims.

❓ **OPEN DECISION (`Q-05`).** Should `render_variant`'s default value be *derived automatically* from the active `family_slug` (so a merchant adding a `hero_banner` section to a `nordic_living` store gets the circular-hero variant with zero extra clicks), with an explicit override control shown only if the owner wants merchants to be able to mix variants across families? 💡 Recommendation: derive automatically by default, expose the override control — consistent with "every configurable visible element must map to a real control," but the *default* should require no merchant action, exactly like every other family-default value in this system already works.

## 3. Design-token contract

🔍 **FACT.** Already fully built and does not need new work: `apps/storefront_builder/appearance_registry.py` (palette: 20 entries, 8 colors each; typography: `FONT_CHOICES`, `TYPE_SCALE_SIZES`; spacing/density: `DENSITY_CHOICES`; radius: `radius`/`button_radius`; border: derived from `--border` token; shadow: `card_shadow` enum; motion: `MOTION_CHOICES` + global `prefers-reduced-motion` respect independent of the active template's own motion value, per commit `d08b762`; component-state tokens: `button_style`, `image_fit`, `image_hover`).

💡 **Recommendation: reuse this system entirely, unchanged, for palette/typography/motion/density within a family** (§1's `default_appearance_template_slug` mechanism). Do not fork or duplicate `appearance_registry.py` — the five families' *own* signature values (e.g. `heritage_premium`'s default radius/density) should be expressed as one more `TemplateDefinition` entry each (or as `default_appearance_template_slug` pointing at the closest existing entry, e.g. `heritage_premium` → existing `luxury` or `boutique` template, `modern_fashion` → existing `playful` or a new one) rather than inventing a second, parallel color/font/radius system.

❓ **OPEN DECISION (`Q-06`).** Should each of the five families get one *brand-new* `TemplateDefinition` entry added to the existing `TEMPLATE_REGISTRY` (10 → 15), reusing the exact declared radius/density/motion/hero_style/card_shadow/card_hover values already present in the lightweight package's `SPECS` object (which conveniently already expresses most of these as literal numbers — e.g. Beraito radius=10, Cactus radius=8, iBolak radius=16, Nordic radius=4), or should each family simply default to the closest *existing* entry without adding new ones? 💡 Recommendation: add five new entries — the package's own declared values map almost one-to-one onto `TemplateDefinition`'s existing fields, so this is very low new-surface-area work and keeps the family's signature "recommended" look self-describing in the registry, without touching `hero_style`'s existing enum (`"wide"|"tall"|"split"`) which will need exactly one new value (`"circular"`, for `nordic_living`) or reuse of `"tall"` — a small, explicitly-scoped extension, not a rewrite.

## 4. Renderer contracts

🔍 **FACT — current reality (doc 01 §2.2, re-stated for this plan's precision).** Exactly one shared header partial (`storefront_builder/partials/page_shell_header.html`), one shared footer partial (`page_shell_footer.html`), one shared product-card partial (`catalog/partials/product_card.html`), one shared product-detail template/view (`catalog/product_detail.html` / `catalog/views.py:346`).

💡 **Recommendation — the concrete file-level shape of the new capability**, following the existing `{% include %}`-based section-template pattern already used for all 22 section types (each is its own `.html` file selected by `SectionDefinition.template_name`, never a giant `{% if %}` chain in one file):

| Renderer contract | New file(s) (proposed) | Selection mechanism |
|---|---|---|
| Header/nav (5 variants + existing default) | `storefront_builder/partials/headers/header_{{ family_slug }}.html` (one file per family; existing `page_shell_header.html` becomes the "no family selected" default, unchanged) | `family_registry.FamilyDefinition.header_variant` → template-name lookup, mirroring `SECTION_REGISTRY`'s existing `template_name` field pattern |
| Hero variant | New `render_variant` values consumed *inside* the existing `sections/hero_banner.html` via `{% include %}` sub-partials (`hero_banner_promo_dashboard.html`, `_full_bleed_campaign.html`, `_editorial.html`, `_carousel.html`, `_neutral_circular.html`) | `StorefrontSection.settings.render_variant`, resolved through `section_data_service.py`'s existing settings-resolution pattern |
| Category variant | Same sub-partial pattern inside `sections/category_grid.html` | same as hero |
| Product-card renderer (5 variants) | `catalog/partials/product_cards/{{ variant }}.html` (`square_centered_commerce.html`, `premium_portrait.html`, `premium_campaign.html`, `artisan_story_card.html`, `fashion_portrait_gallery.html`, `catalog_second_image.html` — 6 files for 5 families since Cactus needs 2 modes); existing `catalog/partials/product_card.html` stays as the literal default for stores with no family selected | `product_section.html` and `product_grid.html` (both existing) resolve which card partial to `{% include %}` based on the active family's `product_card_variant`, threaded down from the same context both already receive |
| Product-page composition (5 variants) | `catalog/partials/product_pages/{{ family_slug }}.html` included from a lightly-refactored `catalog/product_detail.html` (which becomes a thin shell that includes the family-specific composition, exactly the same shell/partial split already proven for header/footer) | `apps/catalog/views.py:346 product_detail()` resolves the active family the same way it already resolves `store` |
| Footer variant | Same file-per-family pattern as header, `footers/footer_{{ family_slug }}.html` | same mechanism as header |

❓ **OPEN DECISION (`Q-07`).** Should the product-card variant be selectable **independently per `product_section` instance** (so a merchant could mix `square_centered_commerce` on one row and `catalog_second_image` on another, as the master prompt's "product-card mode where the family supports more than one" line literally allows for Cactus's two modes) or **fixed platform-wide by the active family** (simpler, matches "five genuinely distinct families" framing more literally, prevents accidental Frankenstein pages)? 💡 Recommendation: fixed by family **except** for Cactus's two declared modes (`premium_portrait`/`premium_campaign`), which are a per-*section*-instance choice specifically because the master prompt calls that out explicitly for this one family only — everything else stays family-fixed.

## 5. Rendering pipeline

🔍 **FACT.** `render_service.build_render_items(version, store)` (`services/render_service.py`) is already the single function consumed by both `storefront_preview` (Draft) and `catalog/views.py:home()` (Published) — this is the master prompt's "Preview and Public must use the same rendering pipeline" requirement, **already satisfied, unconditionally**, and nothing in this plan should create a second render path. The same must hold for the new product-detail composition split in §4 — `product_detail()` must resolve the active family and pass it into the *same* template-resolution call regardless of whether it's being viewed by a customer or previewed by staff (there is currently no separate "preview product page" route at all — confirmed absent — so this is a straightforward extension, not a divergence risk).

💡 Cache-key implication (if storefront caching is ever added — currently absent, `01_...GAPS.md` §1): any future cache key must include `family_slug` alongside the existing `content_fingerprint`, since `compute_fingerprint()` (`models.py:203-216`) already hashes the full `appearance_config` dict — adding `family_slug` to that dict means the fingerprint automatically changes when the family changes, with zero additional code. No action needed now; noted for completeness only.

## 6. Builder controls

💡 **Recommendation, mapped against the master prompt's own checklist:**

- **Family picker** — a new gallery view, modeled directly on the existing appearance-template picker UI (`templates/dashboard/storefront_builder/partials/appearance_panel.html`), reusing its existing "swatch card + پیش‌نمایش button + `preview-candidate-template` Alpine event" interaction pattern verbatim for a `preview-candidate-family` event instead.
- **Section add/remove/hide/reorder, variant, title/CTA/link, collection/product source, columns, media, spacing/background, responsive, palette/typography/density/radius/motion, reset-to-default** — 🔍 **FACT: every one of these already exists and needs zero new Builder chrome** (doc 01 §2.1); only the new `render_variant`/family-picker controls from §§1-2 above are genuinely new UI.
- **Validation/reset-to-family-default** — reuse the existing `_passthrough_dict`/typed-validator pattern (`section_registry.py:58-62` and the `product_section` validators) for the new `render_variant` key; "reset to family default" is simply clearing the key (falls back to the family's default per §2's derivation rule).

## 7. Multi-tenancy and security

🔍 **FACT, reused unchanged:** `resolve_store_for_storefront`, `storefront_visible_products`/`storefront_listing_products`, `STOREFRONT_LAYOUT_MANAGE` permission, the existing HTML sanitizer for any rich-text content inside family-specific sections (e.g. Deeyar's About-split copy), the existing validated video-provider allowlist (YouTube/Aparat/Instagram) for the optional product-video capability.

💡 New surface to test, following the exact existing adversarial-test pattern (`SECRET-STORE-A-TEXT`-style markers, per doc 01's testing note): a `family_slug`/`render_variant` value must never let one Store's Draft leak into another Store's Preview or Public render — but since both live inside the *already tenant-scoped* `StorefrontLayoutVersion.appearance_config`/`StorefrontSection.settings`, this is a natural, low-risk extension of an existing, already-adversarially-tested boundary, not a new isolation surface.

❓ **OPEN DECISION (`Q-08`).** No new database model is proposed anywhere in this plan (family selection lives in existing JSONFields; new registries are code, like their two siblings). If the owner's answer to `Q-06`/`Q-07` above ends up requiring a genuinely new *merchant-editable* field (e.g. a real maker/region field for `artisan_editorial`, or real installment/campaign data for `heritage_premium` — both flagged as data gaps in doc 01 §3.1), that is the one place this plan would need an actual migration — tracked explicitly as its own question rather than assumed.

## 8. Accessibility, RTL, and localization

🔍 **FACT, reused unchanged:** platform-wide `dir="rtl"`, curated RTL-safe font allowlist, global `prefers-reduced-motion` enforcement independent of any template's own motion setting, existing touch-target/keyboard patterns already required platform-wide (no critical action may depend on hover — already true today for the existing wishlist/add-to-cart interactions per doc 01 §3).

💡 New requirement specific to this plan: every new family-specific hover-revealed element (Nordic's action-rail, Cactus's side-action, iBolak's thumbnail-reveal) must ship with the exact same kind of `@media(max-width:720px)`-gated static/touch fallback the lightweight package itself already encodes for each (docs 02-06 §13/§5) — this is a design *constraint* carried into implementation, not new infrastructure.

## 9. SEO and performance

🔍 **FACT:** JSON-LD already present on `home.html`/`product_detail.html` (doc 01 §5); no per-family change to *what* structured data is emitted is implied by anything in this plan — family only changes presentation, never the underlying `Product`/`Offer` data driving the JSON-LD, so existing SEO correctness should be unaffected by construction (to be verified with a regression test per family in Gate 3, not re-litigated as an open question now).

💡 Performance comparison: since no new database queries are proposed (family/variant selection is read once per request from the already-loaded `StorefrontLayoutVersion`, exactly like `appearance_config` is today), the expected query-count delta versus the current baseline is zero for the family mechanism itself — the only genuinely new per-request cost is template *selection* (a dict lookup, not a query) and possibly one or two additional `{% include %}` resolutions, which Django's template loader caches. Actual measurement is a Gate-3 validation step (`Phase 14`), not something to claim now without running it.

## 10. Test strategy

💡 Following the exact structure already established for `storefront_builder`/`collections` (model / service / view+permission / end-to-end / regression, per doc 01 §5 and the — otherwise stale — `..._IMPLEMENTATION_ROADMAP.md` §6 methodology, which remains valid as *methodology*):

- `family_registry` validation tests, mirroring `test_section_registry.py`'s `EXPECTED_KEYS` change-detector pattern.
- Defaults/backward-compatibility: a store with no `family_slug` set must render byte-for-byte identically to today (the same guarantee `appearance_config`'s own defaults already provide for `template_slug=None`).
- All 5×(header+hero+category+card+footer+product-page) renderer branches — one assertion per family that its distinguishing DOM element is present (e.g. Nordic's `.nordic-facts` 3-cell strip, iBolak's `.wishlist` button) with **identical fixture palette/products across all five**, directly testing this document's Matrix-C conclusion (doc 07).
- Preview/Public parity for the new product-detail split (§4) — extend the existing `test_public_homepage_integration.py`-style pattern to product pages, which do not currently have an equivalent Draft-preview route to test against (confirmed absent) — flagged as new test *infrastructure*, not just new test *cases*, if product-page family previewing is approved in scope.
- Tenant isolation — reuse the existing `SECRET-STORE-A-TEXT`-marker pattern for the two new JSONField keys.
- The specific edge-cases each per-family audit doc's own §20 checklist already enumerates (long titles, zero/one/many products, missing image, discount/no-discount, out-of-stock, variant-image switching, reduced motion).

## 11. File plan

| File | Reason | Symbol | Migration impact | Compatibility impact | Test file | Risk / rollback |
|---|---|---|---|---|---|---|
| `apps/storefront_builder/family_registry.py` (new) | Family manifest, mirrors `section_registry.py`/`appearance_registry.py` | `FamilyDefinition`, `FAMILY_REGISTRY`, `register_family`, `get_family` | none (pure Python) | additive only | `test_family_registry.py` (new) | Low — pure addition, revertable by deleting the file + its one import site |
| `apps/storefront_builder/appearance_registry.py` (edit) | Add ≤5 new `TemplateDefinition` entries (§3) + possibly one new `hero_style` value | `register_template(...)` calls | none | additive; existing 10 entries untouched | extend `test_appearance.py` | Low |
| `apps/storefront_builder/models.py` (edit) | Add `"family_slug": None` to `APPEARANCE_CONFIG_DEFAULTS`; add `"render_variant": None` default helper for the 2-3 affected section settings validators | `APPEARANCE_CONFIG_DEFAULTS`, `effective_appearance_config` | none — JSONField default dict key addition only, no schema migration | fully backward-compatible (missing key = existing default) | extend `test_models.py` | Low |
| `apps/storefront_builder/section_registry.py` (edit) | Add optional `render_variant` to `hero_banner`/`category_grid`/`product_section` validators | `validate_settings` callables for those 3 keys | none | additive, default `None` = current behavior | extend `test_section_registry.py` | Low-medium — validator changes touch a widely-used file; keep changes additive-only |
| `apps/storefront_builder/templates/storefront_builder/partials/headers/*.html` (new, 5 files) | Per-family header DOM | — | none | new files only | browser/visual checks per doc 02-06 §20 | Medium — real new markup, needs the most careful visual QA |
| `apps/storefront_builder/templates/storefront_builder/partials/footers/*.html` (new, 5 files) | Per-family footer DOM | — | none | new files only | same as above | Medium |
| `apps/storefront_builder/templates/storefront_builder/sections/hero_banner_*.html`, `category_grid_*.html` (new, ~10 files) | Per-family hero/category sub-variants | — | none | new files only | same as above | Medium |
| `apps/catalog/templates/catalog/partials/product_cards/*.html` (new, 6 files) | Per-family/per-mode card renderers | — | none | existing `product_card.html` stays as-is for the no-family default | new `test_product_card_renderers.py` | Medium-high — this is the single most acceptance-critical set of files per the master prompt's own "single DOM fails" criterion |
| `apps/catalog/templates/catalog/product_detail.html` (edit → thin shell) + `.../partials/product_pages/*.html` (new, 5 files) | Per-family product-page composition | `product_detail()` view unchanged in signature | none | must be a pure refactor for the no-family-selected path (byte-identical output) before any new family content is added | extend existing product-detail tests + new per-family ones | Medium-high — refactor-then-extend, in that order, with a regression test locking the "before" output first |
| `apps/storefront_builder/templates/dashboard/storefront_builder/partials/family_panel.html` (new) | Merchant-facing family picker, modeled on `appearance_panel.html` | — | none | new UI only | extend `apps/storefront_builder/tests/test_views.py` | Low — additive dashboard UI |
| `apps/storefront_builder/views.py` (edit) | Wire the new family-picker panel + its "apply candidate family" preview event handler | new view function(s), mirroring the existing appearance-template-preview handler | none | additive endpoint(s), same permission gate (`STOREFRONT_LAYOUT_MANAGE`) | extend `test_views.py` | Low-medium |

**No new database model and no new migration for a schema *table* is proposed anywhere in this plan** — every model-layer change above is either a pure-Python registry addition or a JSONField default-dict key addition (no `AlterField`, no new column). The one place a real migration could become necessary is contingent on `Q-08` (a genuinely new merchant-editable field for maker/region or installment/campaign data) — not decided by this document.
