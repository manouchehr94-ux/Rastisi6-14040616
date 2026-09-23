# content — Dependencies

```
domain_id: D10
code_baseline: 5883a140
```

## content depends ON
| Target | Type | What |
|---|---|---|
| `storefront_builder` | foreign-key (CASCADE) | placements FK into `StorefrontSection`; render via `render_service` (lazy import) |
| `catalog` | reads | destination resolution (Category/Product/Brand/MerchantCollection) |
| `core` | uses | `TimeStampedModel` base; `private_storage`/media |

## Depends ON content (who writes/reads content)
| Source | Type | What |
|---|---|---|
| `dashboard.views` | writes (DIRECT — H2) | ALL content CRUD |
| `storefront_builder` | writes (cross-domain) | placement media clone (`layout_service`, `media_views`) |
| storefront shell / render | reads | footer/menus/social via `context_processors`; page render |

## Cycle-avoidance
`content.page_detail` imports `storefront_builder` **lazily** (local import) to avoid a module-level
cycle with the render layer.

## Not a dependency
content does not depend on orders/cart/billing/subscriptions/sms.
