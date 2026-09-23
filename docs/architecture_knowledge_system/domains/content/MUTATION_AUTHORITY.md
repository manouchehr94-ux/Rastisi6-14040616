# content — Mutation Authority (H2)

```
domain_id: D10
code_baseline: 5883a140
open_decisions: DR-2
known_risks: H2
```

> **The defining fact of this domain (H2):** there is **no content write service**. Every
> content-model mutation is a **DIRECT / CROSS-DOMAIN** write performed by `apps/dashboard/views.py`.
> The content model layer owns the data; the dashboard view layer is its de-facto (unowned) service.

## Direct mutation sites in `apps/dashboard/views.py` (VERIFIED)
| Model | View functions | Approx lines |
|---|---|---|
| `ContentPage` | `page_form`, `page_delete`, `page_publish` | 4705, 4763, 4775 |
| `HeroSlide` | `hero_form`, `hero_delete`, `hero_toggle` | 4826, 4910, 4935 |
| `PromotionalBanner` | `banner_form`, `banner_delete`, `banner_toggle` | 4958, 5034, 5056 |
| `SocialLink` | `social_link_form`, `social_link_delete`, `social_link_toggle` | 5085, 5123, 5142 |
| `Menu` | `menu_form`, `menu_delete`, `menu_toggle` | 5171, 5217, 5244 |
| `MenuItem` | `menu_item_form`, `menu_item_delete`, `menu_item_toggle` | 5283, 5346, 5368 |
| `FooterSettings` | `footer_settings_page` | 5397 |
| `FooterTrustBadge` | `footer_trust_badge_form/delete/toggle` | 5467, 5516, 5545 |
| `FooterPaymentLogo` | `footer_payment_logo_form/…` | 5567 |
| `StoryRailItem` | (via homepage/story views in dashboard) | dashboard views |

Each uses raw `instance.full_clean()` + `instance.save()` (or `.delete()`) directly in the view.
The only model-level guard is each model's `clean()` (e.g. `DestinationMixin` coherence +
cross-store ownership checks, `ContentPage` published-requires-timestamp).

## The single content-service write (VERIFIED)
- `content.services.subscribe_to_newsletter(store, raw_email)` — creates `NewsletterSubscriber`.
  This is the **only** write in `content/services.py`.

## Cross-domain writes from `storefront_builder` (VERIFIED)
- `storefront_builder.layout_service._clone_section_scoped_media` and `media_views` write content
  placement rows (HeroSlide/PromotionalBanner/StoryRailItem) when cloning/publishing a layout
  version (placements FK into `StorefrontSection`).

## What this means for change safety
- There is **no single content service** to route a change through and **no content transaction
  boundary**. A multi-object content edit (e.g. reordering menu items) relies on the view's own
  (often implicit) handling.
- Adding a content write path today means adding another dashboard view, unless DR-2 introduces a
  service layer.

## Decision
**DR-2 — content domain write boundary — OPEN.** Options: (a) extract a content service; (b)
formally sanction dashboard-as-content-service and document; (c) partial extraction. Do not decide.
