# editorial_jewelry v2 — reference-driven design contract

Reference kit: `zarrin-home-desktop.jpg` (design reference only; no third-party runtime assets are copied).

## Structural signature

- quiet, single-row editorial header with compact utilities and no permanent large search field
- warm ivory hero with an oversized headline and a three-image arch composition
- dense image-first category mosaic with strong over-image labels
- two large image-led promotional/story moments
- restrained four-column product grids with minimal commerce chrome
- a second paired editorial banner moment plus one full-width informational banner
- minimal legal-only footer
- centered 1320px site content width using the existing registered generic width option (not a renderer special case)

## Data / tenant safety

All visible commerce data must resolve from the current Store at render time.

- hero media/copy: current Store `HeroSlide` records
- category mosaic: current Store active top-level categories + representative media
- promotional imagery: current Store `PromotionalBanner` records using offset/limit, never IDs
- product rows: existing ID-free `newest` and `best_sellers` resolvers
- footer/header identity and navigation: shared current-Store context

The Ready Template must not embed Store/Product/Category/Banner IDs and generic renderers must not branch on `template_key`.

## Reusable registered additions

- palette: `atelier-ivory`
- header variant: `atelier_nav`
- hero variant: `atelier_triptych`
- category-grid variant: `atelier_mosaic`
- banner layout classes: `atelier-duo`, `atelier-wide`

These names describe general composition rather than the reference merchant and may be reused by future Stores/Templates.

## Deliberate non-copies

The reference contains merchant-specific brand marks, jewelry photography, FAQ copy, and a ring-size guide graphic. They are **not** copied or fabricated. If a merchant supplies equivalent content, generic banner/content sections can carry it; otherwise the Ready Template fails closed rather than inventing commercial claims/content.

## Responsive target

- desktop: 4-column category/product rhythm and 2-column editorial banners
- mobile: 2-column category/product rhythm, single-column banners, horizontally scrollable hero arches
- no horizontal page overflow; navigation collapses behind the existing burger pattern
