# catalog — Dependencies

```
domain_id: D4
code_baseline: 5883a140
known_risks: M13
```

## catalog depends ON
| Target | Type | What |
|---|---|---|
| `stores` | foreign-key | Store FK on Product/Category/etc. |
| `storefront_builder` | renders (lazy import) | `catalog.views.home` → `render_service`; SECTION_REGISTRY validates industry template section keys |
| `core` | uses | TimeStampedModel, audit, private storage (import/export) |

## Depends ON catalog
| Source | Type | What |
|---|---|---|
| `orders` | writes | reserve/consume inventory (+StockMovement) |
| `cart` | reads | `pricing_service` effective price |
| `dashboard` | calls + writes | catalog services + direct Product/Category writes; import |
| `portal.provisioning_service` | writes | default Warehouse + industry template install |
| `storefront_builder` | reads | section data-sources (products/brands/categories/collections) |
| `content` | reads | destination resolution (Category/Product/Brand/Collection) |

## Cycle-avoidance (M13)
`catalog.IndustryTemplate.default_section_keys` is validated in `storefront_builder`'s
SECTION_REGISTRY, not in catalog — avoiding a catalog→storefront_builder module dependency.
catalog imports storefront_builder only lazily (home render).
