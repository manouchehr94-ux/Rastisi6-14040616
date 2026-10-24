# V5 six templates — final capture record (24 outputs) and remaining differences

Real Chromium, isolated media + throw-away test database, demo photography from the local reference folder only (never committed).
Every output is captured at the **same CSS viewport width as its reference picture** (1847 px desktop, 487 px mobile; measured exceptions:
zhimunplus desktop 1858 px, lilium-gallery mobile 503 px) with overlay scrollbars, so the layout width is identical.
`overflow` = page scroll width minus viewport width (0 = no horizontal overflow). `JS errors` = uncaught page errors. Heights are full-page pixels.

| Template | Output | Viewport | Our height | Reference height | overflow | JS errors |
|---|---|---|---|---|---|---|
| `decor_sand_boutique` (Dize) | home | desktop 1847 px | 4556 | 5852 | 0 | none |
| `decor_sand_boutique` (Dize) | home | mobile 487 px | 4150 | 5390 | 0 | none |
| `decor_sand_boutique` (Dize) | product | desktop 1847 px | 2579 | 3205 | 0 | none |
| `decor_sand_boutique` (Dize) | product | mobile 487 px | 2023 | 3015 | 0 | none |
| `rose_beauty_store` (lilikacosmetics) | home | desktop 1847 px | 5765 | 5668 | 0 | none |
| `rose_beauty_store` (lilikacosmetics) | home | mobile 487 px | 5469 | 7145 | 0 | none |
| `rose_beauty_store` (lilikacosmetics) | product | desktop 1847 px | 2089 | 3301 | 0 | none |
| `rose_beauty_store` (lilikacosmetics) | product | mobile 487 px | 2389 | 4677 | 0 | none |
| `pink_beauty_gallery` (lilium-gallery) | home | desktop 1847 px | 3726 | 5232 | 0 | none |
| `pink_beauty_gallery` (lilium-gallery) | home | mobile 503 px | 2859 | 3791 | 0 | none |
| `pink_beauty_gallery` (lilium-gallery) | product | desktop 1847 px | 2400 | 5285 | 0 | none |
| `pink_beauty_gallery` (lilium-gallery) | product | mobile 503 px | 2350 | 6646 | 0 | none |
| `campaign_beauty_hub` (AsalBanoo) | home | desktop 1847 px | 5267 | 8483 | 0 | none |
| `campaign_beauty_hub` (AsalBanoo) | home | mobile 487 px | 5189 | 10693 | 0 | none |
| `campaign_beauty_hub` (AsalBanoo) | product | desktop 1847 px | 2229 | 6578 | 0 | none |
| `campaign_beauty_hub` (AsalBanoo) | product | mobile 487 px | 2348 | 10585 | 0 | none |
| `cocoa_gift_shop` (khanehshokolati) | home | desktop 1847 px | 7676 | 11695 | 0 | none |
| `cocoa_gift_shop` (khanehshokolati) | home | mobile 487 px | 8314 | 15998 | 0 | none |
| `cocoa_gift_shop` (khanehshokolati) | product | desktop 1847 px | 2516 | 4263 | 0 | none |
| `cocoa_gift_shop` (khanehshokolati) | product | mobile 487 px | 2938 | 5998 | 0 | none |
| `neon_digital_store` (zhimunplus) | home | desktop 1858 px | 4094 | 7470 | 0 | none |
| `neon_digital_store` (zhimunplus) | home | mobile 487 px | 4303 | 8788 | 0 | none |
| `neon_digital_store` (zhimunplus) | product | desktop 1858 px | 2238 | 3573 | 0 | none |
| `neon_digital_store` (zhimunplus) | product | mobile 487 px | 2574 | 26022 | 0 | none |

## Why the heights still differ — content versus layout

Heights are **not** a quality score: each reference store holds its own catalogue, long merchant articles, review forms and FAQ entries, while the
demo Store used for capture holds a handful of generic products. The differences were therefore separated per cause.

### A. Content-driven height (not a layout defect; a merchant supplies this content)

* **Long product descriptions / SEO articles / FAQ answers** — AsalBanoo PDP (≈ 10 600 px mobile) carries a merchant-written article, a FAQ with four
  answers, the review form and seven written reviews; zhimunplus PDP mobile (26 022 px) carries a multi-section article with pictures and a
  buyer's guide. The template renders the *description*, *specification*, *brand* and *review* tabs from the product's real data; the demo
  product has two sentences. The AsalBanoo recipe now also ships an empty, merchant-authored **FAQ** section on the product page
  (`product.faq`): it renders nothing until the Store lists its own questions in the Inspector. A per-product FAQ would need a new Product field (Model
  change — not done without approval).
* **Number of products / banners / posts in a row** — the reference stores show 8–24 products per shelf, 5–19 banners and 3–6 posts; the demo Store seeds
  4–8 products, up to 19 banners (khanehshokolati) and 3 posts. The recipes use the same sections, limits and layouts; a Store with more content grows the same way.
* **Reference-only extra shelves that point at a specific category** (lilium-gallery "پک آرایشی") — a recipe cannot know a
  Store's category ids; the merchant adds the shelf and picks the category.

### B. Layout differences that were found and fixed in this round

| Finding (measured against the reference picture) | Fix (generic engine, no template key in code) |
|---|---|
| `duo-round`, `trio-round`, `people-4`, `mosaic-5`, `panel-4` banner rows rendered in 4 equal columns (the shared `.grid.rsec-cols` rule out-ranked the variant rule): the two round banners filled only half of the row | variant column rules now out-rank the shared rule (also tablet/mobile) — visible on lilium-gallery, khanehshokolati, lilikacosmetics, zhimunplus home |
| mobile PDP: our fixed add-to-cart bar floated mid-page in full-page captures and none of the references has it | `show_mobile_sticky_bar` switched off in all six recipes (the switch itself is unchanged for every other Store) |
| mobile PDP: description tabs collapsed into an accordion while the references show a horizontal tab row with the description under it | new `product_description.mobile_layout = tabs` (default `accordion`; written as `data-mobile="tabs"` only when chosen) enabled in five recipes |
| desktop sticky purchase bar (lilikacosmetics, zhimunplus references) was missing | new `product_main.show_desktop_sticky_bar` (default OFF): after the in-flow button scrolls out the bar shows the product's real picture, name, price and the same add-to-cart button — one form, one variant/stock/price owner; enabled for `rose_beauty_store` and `neon_digital_store` |
| PDP width: lilikacosmetics / lilium-gallery / AsalBanoo references use a narrower product container (≈ 80–84 % of the page) | `design.width_pct` 88 / 92 / 88 on the three PDP sections of those recipes |
| khanehshokolati home lacked the second and third banner groups, the "best sellers" shelf and the small four-banner strip (11 695 px reference) | five sections added to the recipe from existing primitives (`duo-round`, `mosaic-5`, `mini-4`, shelf) |
| capture harness: lilium-gallery mobile and zhimunplus desktop reference widths (503 / 1858 px) and scrollbar width were not matched; PDP of a discounted product was not captured where the reference shows a discount | harness now matches the measured widths, hides scrollbars and captures a discounted demo product for the four sites whose reference shows a discount |

### C. Remaining layout differences (real, documented, not faked)

* **Typography scale on product pages (AsalBanoo, zhimunplus mobile)**: the references use ≈ 19–22 px body/heading sizes on the mobile product page; ours follow the Store's type scale (title / price sizes are Inspector-editable but the description body is not scaled per page).
* **Mobile header** (AsalBanoo, zhimunplus): references show icons only with a search icon; ours keep the header search row.
* **Mobile PDP gallery** (AsalBanoo, zhimunplus): references use an edge-to-edge picture without a card; ours keep the card frame.
* **Four-tile promotion rows** (khanehshokolati "ماگ دیزنی | پنکه شارژی" style: text tile, photo, text tile, photo): our `duo-round` shows the two pictures only.
* **Trust strip / four-claim icon rows**: shown only for claims the Store really backs (payment, shipping, pickup); zhimunplus's four marketing claims are merchant copy and are not invented.
* **Header proportions**: lilium-gallery's reference menu bar is ≈ 20 px taller and its logo block larger than ours.

### D. Needs a licence, a third-party service, or a commercial / data-model decision (not built)

* Reference photographs, logos, copy, commercial fonts (see `FONT_SUBSTITUTIONS.md`) — never shipped.
* Instagram profile widget (khanehshokolati), AI live-chat bubble (lilium-gallery), app-store badges and download panel (AsalBanoo), eNAMAD / trust-seal images (lilikacosmetics, khanehshokolati) — third-party services or licensed seals.
* "N people are viewing this product now" (zhimunplus) — needs a real live-visitor service; showing a number without it would be fake.
* Second (red) call-to-action of khanehshokolati and per-product FAQ — need a business decision / a Product field.
* Product-attribute bullet list beside the buy button (AsalBanoo), validity period / delivery method / licence of digital goods (zhimunplus) — need structured catalogue fields; the platform shows the real description and specification tabs instead.

### E. Commercial features that already exist and are wired

* **Gift Wrap** (`ShopSettings.gift_wrap_*`, `Product.gift_wrap_enabled/price`): the product page renders the real checkbox, price, note and optional card message
  for **every** template whenever the merchant has switched the service on in settings; the choice flows through cart, checkout and order. This is the
  "packaging / gift extra" shown by the Dize and khanehshokolati references, so it is **not** a template recipe setting (a template must not change a Store's
  business settings). The capture harness switches it on for those two demo Stores.
* Low-stock alert, free-shipping notice, phone / WhatsApp consultation buttons, wishlist, gallery lightbox, mobile and desktop sticky purchase bar — all driven by real Store / product data.
