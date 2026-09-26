# storefront_builder — Dependencies

```
domain_id: D9
code_baseline: 5883a140
```

## Depends ON
| Target | Type | What |
|---|---|---|
| `catalog` | reads | section data-sources (products/brands/categories/collections) via `section_data_service`; industry-layout apply |
| `content` | writes (cross-domain) + reads | placement media clone (`layout_service`/`media_views` write Hero/Banner/Story); reads `Menu` |
| `stores` | reads | `request.store` |
| `core` | uses | `TimeStampedModel`; media/private storage |

## Depends ON storefront_builder
| Source | Type | What |
|---|---|---|
| `dashboard` | routes-to + calls | registers all builder routes (views/r4_views/media_views) |
| `catalog.views.home` | renders (lazy import) | `render_service.build_render_items` |
| `content.views.page_detail` | renders (lazy import) | `build_universal_storefront_context` |
| `content` models | foreign-key (CASCADE) | placements FK into `StorefrontSection` |

## Cycle-avoidance
- `catalog.home`/`content.page_detail` import storefront_builder **lazily**.
- `catalog.IndustryTemplate.default_section_keys` is validated **in** storefront_builder's
  SECTION_REGISTRY (not in catalog) to avoid a catalog→storefront_builder module dependency.

## Registry fan-in (M1)
`storefront_appearance.COMPONENT_REGISTRY` reads `appearance_registry` + `palette_pack_64` +
`theme_catalog` + `global_region_registry` at import — a fan-in that is the root of the M1
duplication concern.
