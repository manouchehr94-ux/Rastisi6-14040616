# V5 six reference templates — build status, evidence and limits

Scope: Ready Templates 54-59, built as pure recipe data over the one R4 engine (`apps/storefront_builder/a10_reference_templates.py`).
No renderer, partial or CSS selector knows a template key. Every visual difference is a registered section variant, card style,
header/footer variant, appearance token or palette that any Store can use and the Inspector can edit.

| # | Key | Reference | Palette | Header | Footer |
|---|---|---|---|---|---|
| 54 | `decor_sand_boutique` | Dize | `sand-olive` | `floating_card` | `centered_contact` |
| 55 | `rose_beauty_store` | lilikacosmetics | `rose-cream` | `beauty_search_nav` (+ category-menu block, dark bar) | `marketplace_dense` |
| 56 | `pink_beauty_gallery` | lilium-gallery | `fuchsia-gallery` | `beauty_search_nav` (fuchsia bar) | `marketplace_dense` |
| 57 | `campaign_beauty_hub` | AsalBanoo | `honey-orange` | `promo_search_nav` | `marketplace_dense` |
| 58 | `cocoa_gift_shop` | khanehshokolati | `cocoa-gold` | `chocolate_centered_search` | `chocolate_dark_columns` |
| 59 | `neon_digital_store` | zhimunplus | `neon-navy` | `marketplace_search_first` | `dark_tech` |

## Generic engine primitives added (all sparse / default-off: an existing Store renders exactly as before)

Fonts (Estedad, Noto Sans Arabic, Lalezar — see `FONT_SUBSTITUTIONS.md`), wider content width (1800), global heading style, announcement
strip geometry + colours + picture, floating WhatsApp / phone / back-to-top, floating-card header, centred-contact footer,
category display modes `label_tiles` / `icon_rail` / `ring_circles` / `photo_cards` and category source `subcategories`, hero
`clean_slider` / `duo_carousel` with independent desktop / mobile ratio and an edge-to-edge width, product-row **tabs** (real categories, sub-categories or
sort orders; pills or underline), row glow, heading styles `plain_link` / `icon_chip`, "view all" below the items, call-to-action strip
(button + two-colour fill), blog `editorial_cards` (date badge), image-text feature rows (registered icons), multi-banner layouts
`duo-round` / `trio-round` / `people-4` (consultant cards) / `mosaic-5` / `panel-4` and an optional heading, several videos in one row,
three product cards (`gallery_pink`, `campaign_round`, `cocoa_gift`) plus `lifestyle_cart` / `outline_plain`, header geometry for the
beauty header, a header `category_menu` block, and product-page controls: low-stock alert, free-shipping notice, phone / WhatsApp
buttons (all from the Store's real data), add-to-cart colour role, title / price size, gallery lightbox + swipe.

Fixed engine defects found on the way: two unsaved candidate sections of one key shared one cached context in the gallery live preview;
an unsaved `linked_image` crashed the candidate preview.

## What was compared with the reference pictures

All 24 outputs (6 templates × Home/PDP × desktop 1847 px / mobile 487 px) are rendered in real Chromium with the isolated-media harness
(`apps/storefront_builder/qa/reference_capture.py`, opt-in test `test_v5_reference_capture`) on a throw-away Store whose demo
photography comes only from the local reference folder (never copied into the repository or a recipe), and none shows a horizontal
overflow or a JavaScript error. Each was compared **visually, side by side with the reference screenshot** (structure, order, colours,
widths, spacing, card anatomy, header/footer shape); this is not a numeric pixel diff, because the reference photographs, logos and
copy are intentionally not shipped.

## Real remaining differences (honest list)

* **Photography / logo / copy**: reference pictures, logos and marketing text are never shipped; a merchant supplies their own. A template
  therefore looks structurally like its reference but not photographically identical.
* **Fonts**: commercial reference fonts are substituted (`FONT_SUBSTITUTIONS.md`).
* **Dize**: announcement is one colour (reference has two); the "extra" checkbox (packaging fee) is not built — it needs a commercial add-on
  price model.
* **lilikacosmetics**: the story block's picture is the section's external image URL (no media-library picker on `image_text`); no desktop
  sticky bar (a mobile sticky bar exists); review form is the platform's own.
* **lilium-gallery**: the trust strip shows only claims the Store really backs (payment / shipping / pickup) so it is empty on a Store without
  them; nav links are right-aligned (reference centred); live-chat "AI support" bubble is a third-party service and is not built (WhatsApp
  / phone floating widgets are).
* **AsalBanoo**: no swirl artwork on the orange bands, no product attribute bullet list beside the buy button, no FAQ block on the product
  page, branch / app-store badge footer is not reproduced, circular category rail uses the generic ring style.
* **khanehshokolati**: the gold-bordered buy panel uses the generic outlined panel; optional gift / packaging extras and the second (red)
  call-to-action are not built (commercial model). The hero is the generic two-up peeking slider (`duo_carousel`); the footer wave is the
  existing `chocolate_dark_columns` wave.
* **zhimunplus**: digital-goods facts (validity period, delivery method, licence) need catalogue / cart fields and are **not** faked; the
  illustration hero depends on the merchant's picture; testimonials are merchant-entered text (no avatar image).
* **Evidence limit**: the saved reference HTML does not contain a usable product-page document for any site; product-page facts come from the
  screenshots only, so no exact PDP pixel value is claimed.
