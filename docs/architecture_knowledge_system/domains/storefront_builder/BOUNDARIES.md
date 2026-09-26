# storefront_builder — Boundaries

```
domain_id: D9
code_baseline: 5883a140
known_risks: M1, M2, M11, M12
```

## Owns
- Versioned storefront layout (`StorefrontLayout`, `StorefrontLayoutVersion`, `StorefrontPage`,
  `StorefrontSection`, `StorefrontContainer`, `StorefrontCell`, `StorefrontEditHistoryEntry`).
- The R4 editor + R3 legacy editor; A8 Ready Templates; layout preset registry.
- Appearance/theme/palette registries + the typed `storefront_appearance` Design Engine.
- The render path (`render_service`) that turns a published version into render items.

## Does NOT own
- **CMS content** — `content` owns `ContentPage`/`Menu`/`FooterSettings`/placements. storefront_builder
  writes content **placement rows** during layout clone (cross-domain), but does not own them.
- **Catalog data** — `catalog` owns products/categories/collections referenced by sections.
- **Route registration / auth shell** — `dashboard` registers the builder routes and gates them.

## Cross-domain relationships
- **Writes content placement rows** (`layout_service._clone_section_scoped_media`, `media_views`).
- **Read by** `catalog.views.home` and `content.views.page_detail` (render, lazy import).
- **Consumes** catalog data-sources via `section_data_service` (with Store-ownership checks) and
  content menus.

## Overlaps / ambiguities (documented; see GENERATIONS)
- **M1** appearance/palette/theme spread across registries + mirrored into header/footer_config.
- **M2** footer represented 3 ways (also in content + a registry).
- **M11** dual placement media (content).
- **M12** three coexisting section-placement mechanisms (Cell.section / Section.cell / row_key/span).
