# content — Boundaries

```
domain_id: D10
code_baseline: 5883a140
known_risks: H2, M2, M3, M11
```

## Owns (data)
CMS pages (`ContentPage`), navigation (`Menu`/`MenuItem`), footer settings + media
(`FooterSettings`/`FooterTrustBadge`/`FooterPaymentLogo`), section-scoped placements
(`HeroSlide`/`PromotionalBanner`/`StoryRailItem`), `SocialLink`, `MediaAsset`, `NewsletterSubscriber`.

## Does NOT own
- **Its own write path** — `dashboard.views` performs all content CRUD (H2). content owns the models,
  not the mutation authority.
- **Storefront layout sections** — `HeroSlide`/`PromotionalBanner`/`StoryRailItem` FK **into**
  `storefront_builder.StorefrontSection`; that section model belongs to `storefront_builder`.
- **The render shell / layout** — `storefront_builder.render_service` + the storefront shell own
  rendering; content provides footer/menus/social via `context_processors`.
- **Catalog entities** referenced by destinations (Category/Product/Brand/Collection) — owned by `catalog`.

## Overlaps (ambiguous ownership — documented, not resolved)
- **Footer (M2):** three representations across content + storefront_builder + a registry.
- **"Page" (M3):** `ContentPage` (CMS) vs `StorefrontPage` (layout slot).

## Cross-domain relationships
- **In (writes into content):** `dashboard.views` (all CRUD — H2); `storefront_builder`
  (placement media clone during layout publish/restore).
- **Out (content reads/renders):** `catalog` (destination resolution), `storefront_builder`
  (section settings resolution + FK), storefront shell (context processors).
