# content — State Machines

```
domain_id: D10
code_baseline: 5883a140
```

## ContentPage.status
```
draft → published   (sets published_at; CheckConstraint: published requires published_at)
published → draft    (unpublish)
```
- Enforced by a DB `CheckConstraint` (published requires timestamp) + `ContentPage.clean()`.
- **Writer:** `dashboard.views.page_publish` / `page_form` (direct — H2). No content service guards it.

## Other content models
No other content model has a status/lifecycle state machine. `HeroSlide`/`PromotionalBanner`/
`StoryRailItem`/`SocialLink`/`MenuItem` have `is_active`/ordering flags but no multi-state machine.

## Note
Because content mutation lives in dashboard views (H2), the only "state machine" enforcement is the
`ContentPage` DB constraint + model `clean()`. There is no content-service transition layer.
