# content — Code Map

```
domain_id: D10
code_baseline: 5883a140
```

```
apps/content/
├── models.py                 12 models + DestinationMixin
│                             · ContentPage ~:273, MediaAsset ~:385, HeroSlide ~:453,
│                               PromotionalBanner ~:536, SocialLink ~:655, Menu ~:737,
│                               MenuItem ~:772, FooterSettings ~:880, StoryRailItem ~:1025,
│                               NewsletterSubscriber ~:1080
├── services.py               READ/RESOLVE + newsletter + MED-001 no-ops (NO write CRUD — H2)
├── urls.py                   pages/<slug>/ (page_detail), pages/newsletter/subscribe/
├── views.py                  page_detail (read), newsletter_subscribe (write)
├── context_processors.py     footer/menus/social injection into the shell
├── templatetags/             render helpers
├── media_reachability.py     JSON/snapshot reachability for MediaAsset.is_referenced
├── migrations/
└── tests/

# CONTENT MUTATION LIVES HERE (H2):
apps/dashboard/views.py       page_form/delete/publish (~4705-4790), hero_* (~4826-4947),
                              banner_* (~4958-5075), social_link_* (~5085-5161),
                              menu_*/menu_item_* (~5171-5397), footer_* (~5397-5610)
apps/storefront_builder/services/layout_service.py   _clone_section_scoped_media (placement clone)
apps/storefront_builder/media_views.py               placement media add/edit/delete
```

## Where to look for a given concern
| Concern | File |
|---|---|
| Content model definitions | `apps/content/models.py` |
| Content **writes** (all CRUD) | `apps/dashboard/views.py` (H2) |
| Destination/URL resolution | `apps/content/services.py` |
| Footer (also see storefront_builder) | `content.FooterSettings` + `storefront_builder` footer_config/registry (M2) |
| Placement media clone | `storefront_builder.layout_service` / `media_views` |
| Media cleanup (no-op) | `apps/content/services.py` (MED-001, O2) |
