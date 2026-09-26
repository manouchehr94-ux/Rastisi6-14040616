# content — Data Model

```
domain_id: D10
code_baseline: 5883a140
source: apps/content/models.py (12 models + DestinationMixin)
known_risks: M2, M11
```

| Model | Key fields / lifecycle | Notes |
|---|---|---|
| **DestinationMixin** (abstract) | `destination_type` (none/category/product/brand/collection/search/cart/external) + FK dests (SET_NULL) + external URL | `clean()` enforces destination coherence + cross-store ownership |
| **ContentPage** | `status` (draft/published), `published_at/by`, `slug`, footer placement fields | `uniq(store, slug)`; CheckConstraint published-requires-timestamp; RESERVED_SLUGS. **2nd "page" concept (M3)** |
| **Menu** | `location` (header/footer_1/footer_2/footer_3/mobile) | `uniq(store, location)` |
| **MenuItem** | 2-level hierarchy (`parent` self-FK PROTECT); DestinationMixin | child must have a destination |
| **FooterSettings** | ~25 boolean/text toggles; OneToOne Store | **3rd footer representation (M2)** alongside layout `footer_config` + global_region footer variant |
| **FooterTrustBadge / FooterPaymentLogo** | Store-owned footer media | — |
| **HeroSlide / PromotionalBanner / StoryRailItem** | section-scoped placements; DestinationMixin | FK Store **and** FK `storefront_builder.StorefrontSection` (CASCADE). **Dual media (M11):** legacy `desktop_image`/`mobile_image` ImageField + newer `desktop_asset`/`mobile_asset` MediaAsset FK; resolved by `_resolve_placement_media_url` |
| **MediaAsset** | physical media file; `is_referenced()` fail-closed | Store-owned; decoupled from placements |
| **SocialLink** | platform enum + url + icon; header/footer flags | — |
| **NewsletterSubscriber** | email dedup per Store | `uniq(store, email)`; written by `subscribe_to_newsletter` |

## Cross-app coupling (VERIFIED)
`HeroSlide`/`PromotionalBanner`/`StoryRailItem` FK **into** `storefront_builder.StorefrontSection`
(CASCADE) — the tightest content↔builder coupling. Deleting a section cascades its placements.

## Ownership ambiguities documented here
- **M2 footer ×3:** `content.FooterSettings` vs `StorefrontLayoutVersion.footer_config` vs
  `global_region_registry` footer variant.
- **M3 page ×2:** `content.ContentPage` vs `storefront_builder.StorefrontPage`.
- **M11 dual media:** legacy ImageField + MediaAsset FK on placements.
