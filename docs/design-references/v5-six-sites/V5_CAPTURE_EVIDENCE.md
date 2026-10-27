# V5 six templates — capture record (24 outputs) and remaining differences

Real Chromium, isolated media + throw-away test database. Demo photography comes only from the local reference folder and is **never committed**
(the QA harness reads it at run time). Every output is captured at the **same CSS viewport width as its reference picture** (1847 px desktop, 487 px
mobile; measured exceptions: zhimunplus desktop 1858 px, lilium-gallery mobile 503 px) with overlay scrollbars.
`overflow` = page scroll width minus viewport width; `JS errors` = uncaught page errors. This is a visual comparison, **not** a pixel diff.

| Template | Output | Viewport | Our height | Reference height | overflow | JS errors |
|---|---|---|---|---|---|---|
| `decor_sand_boutique` (Dize) | home | desktop 1847 px | 4556 | 5852 | 0 | none |
| `decor_sand_boutique` (Dize) | home | mobile 487 px | 4150 | 5390 | 0 | none |
| `decor_sand_boutique` (Dize) | product | desktop 1847 px | 3176 | 3205 | 0 | none |
| `decor_sand_boutique` (Dize) | product | mobile 487 px | 3266 | 3015 | 0 | none |
| `rose_beauty_store` (lilikacosmetics) | home | desktop 1847 px | 5887 | 5668 | 0 | none |
| `rose_beauty_store` (lilikacosmetics) | home | mobile 487 px | 5604 | 7145 | 0 | none |
| `rose_beauty_store` (lilikacosmetics) | product | desktop 1847 px | 3285 | 3301 | 0 | none |
| `rose_beauty_store` (lilikacosmetics) | product | mobile 487 px | 4389 | 4677 | 0 | none |
| `pink_beauty_gallery` (lilium-gallery) | home | desktop 1847 px | 4507 | 5232 | 0 | none |
| `pink_beauty_gallery` (lilium-gallery) | home | mobile 503 px | 3207 | 3791 | 0 | none |
| `pink_beauty_gallery` (lilium-gallery) | product | desktop 1847 px | 4224 | 5285 | 0 | none |
| `pink_beauty_gallery` (lilium-gallery) | product | mobile 503 px | 5223 | 6646 | 0 | none |
| `campaign_beauty_hub` (AsalBanoo) | home | desktop 1847 px | 6110 | 8483 | 0 | none |
| `campaign_beauty_hub` (AsalBanoo) | home | mobile 487 px | 6068 | 10693 | 0 | none |
| `campaign_beauty_hub` (AsalBanoo) | product | desktop 1847 px | 5051 | 6578 | 0 | none |
| `campaign_beauty_hub` (AsalBanoo) | product | mobile 487 px | 7371 | 10585 | 0 | none |
| `cocoa_gift_shop` (khanehshokolati) | home | desktop 1847 px | 7760 | 11695 | 0 | none |
| `cocoa_gift_shop` (khanehshokolati) | home | mobile 487 px | 8776 | 15998 | 0 | none |
| `cocoa_gift_shop` (khanehshokolati) | product | desktop 1847 px | 4216 | 4263 | 0 | none |
| `cocoa_gift_shop` (khanehshokolati) | product | mobile 487 px | 5707 | 5998 | 0 | none |
| `neon_digital_store` (zhimunplus) | home | desktop 1858 px | 4878 | 7470 | 0 | none |
| `neon_digital_store` (zhimunplus) | home | mobile 487 px | 5962 | 8788 | 0 | none |
| `neon_digital_store` (zhimunplus) | product | desktop 1858 px | 5749 | 3573 | 0 | none |
| `neon_digital_store` (zhimunplus) | product | mobile 487 px | 7867 | 26022 | 0 | none |

## Fidelity round (audit of commit `ece7599`) — what was found and how each item was classified

Every missing / empty part was first classified as one of three states, because each needs a different fix:
**(1)** the section is not in the recipe, **(2)** the section is in the recipe but the QA Store had no data / media, **(3)** the section has data but the
renderer / Inspector / CSS did not draw it correctly. QA problems were fixed by feeding the QA Store real, store-owned fixtures (never by hiding anything with CSS).

| Finding | State | Fix |
|---|---|---|
| khanehshokolati PDP: gallery and buy panel swapped | recipe setting (`gallery_position: end` was wrong) | removed — the gallery sits at the start (right in RTL) like the reference |
| khanehshokolati: 4-destination bottom nav | recipe setting | `five_item` (home, categories, search, account, cart — all real destinations) |
| khanehshokolati buy panel: brown outline, small chips | engine gap | `info_panel = outlined_tone` (brand secondary colour, larger radius), `option_size = large`, real specification list (`show_spec_summary`) |
| zhimunplus panels white / empty | **renderer defect (3)**: the shared palette card rule painted every banner card with `!important` | panel-4 excluded; media on the correct side; stacked layout on phones |
| zhimunplus hero light, tiny text, no button | engine gap + QA data (hero button had no destination) | new generic hero variant `split_open`; QA slides now have real category destinations and a transparent-mascot picture |
| zhimunplus testimonials empty | **data (2)** + engine gap | `card_row` style, optional star rating; QA fixture text |
| Dize PDP picture letter-boxed in a frame | recipe + engine | `gallery_frame = flush`, `design.image_fit = cover`, larger title |
| AsalBanoo / zhimunplus mobile header search row | engine gap | header geometry `mobile_search_icon` (search opens from an icon); mobile gallery frame `flush`; description `body_size` large / xlarge |
| AsalBanoo about block, videos, 4th trust claim, FAQ cards | about: **(1)**; videos / claims / FAQ: **(2)** | `image_text` about block in the recipe; QA fixtures for videos, merchant-verified claim, FAQ items; FAQ `cards` style |
| lilium-gallery wide banner and benefits row empty | **(2)**: `linked_image` needs its own picture row; claims need real shipping / payment settings | QA Store now has a section picture, active gateway, shipping and pick-up methods, one merchant-verified claim |
| lilikacosmetics story picture empty | **engine gap (3)**: `image_text` accepted only an external URL | picture now chosen from the Store's own media library (Store-scoped, fail-closed) |
| footers short and dense in 5 templates | engine gap | footer geometry `pad_y` / `text_size` for every footer variant (sparse) |
| product pages far shorter than the references | **(2)**: demo catalogue had 12–16 products, two-sentence descriptions, no reviews / specs / variants | reference-sized catalogues (24–32 products), neutral long articles, specifications, approved reviews, colour variants, FAQ items — all QA-only |

## Remaining layout differences (real, documented, not faked)

* **Footer composition**: references place about text, link columns, contact, trust seal and social icons in their own arrangement; ours use the registered
  footer variants with larger spacing / text (geometry) but not the same grid.
* **Four-tile promotion rows** (text tile, photo, text tile, photo) of khanehshokolati: our `duo-round` shows two pictures.
* **Trust seals, QR / Instagram widget, app-store badges**: licensed images or third-party services (see below).
* **Videos**: the video section embeds the provider's player; in the isolated QA browser (no network) the frames are empty rectangles.
* **Related products**: the engine shows at most four products of the same category.
* **Typography**: reference product pages use larger sizes than the store scale; the new `body_size` / `title_size` / `price_size` controls close most of it.

## Needs a licence, a third-party service, or a commercial / data-model decision (not built)

* Reference photographs, logos, copy, commercial fonts (`FONT_SUBSTITUTIONS.md`) — never shipped.
* Instagram profile widget, AI live-chat bubble, app-store badges, eNAMAD / trust seals, live "N people are viewing" counter.
* Second (red) call-to-action of khanehshokolati; a second hero button (the hero slide has one button field); per-product FAQ (needs a Product field);
  structured product attributes beside the buy button beyond the real Specification rows; validity / delivery / licence of digital goods.

## Commercial features already wired

* **Gift Wrap** (`ShopSettings.gift_wrap_*`, `Product.gift_wrap_*`): rendered on the product page of every template once the merchant enables the service;
  the choice flows through cart, checkout and order. It is not a recipe setting (a template must not change a Store's business settings).
* Low-stock alert, free-shipping notice, phone / WhatsApp buttons, wishlist, gallery lightbox, mobile and desktop sticky purchase bar, real specification
  list — all driven by real Store / product data.
