# Public landing page v3 — Design Direction & Contract

Scope: the platform-host home page (`/`, `apps/portal/templates/portal/public/home.html`).
Other marketing pages, the Django stack, routes, auth and storefront themes are untouched.

## Problem

The previous hero showed a "Khane Aban" sample shop with three large product photos
(vases and bowls). Visitors read RastiSi as a shop that *sells* ceramics. RastiSi is a
**store-builder platform** (build, customise, manage an online store); it sells nothing.

## Direction — "the workbench"

The hero shows the *tool and its output*, never a product catalogue:
a dark builder panel (store name / template / brand colour) next to a live preview of an
**abstract** storefront (placeholder shapes, "محصول نمونه ۱…"). A short finite sequence
(≈10 s, skipped under `prefers-reduced-motion`) renames and recolours the preview — the
single orchestrated motion on the page.

Ideas taken from the references (not copied): v11 – interactive builder demo and
desktop/mobile toggle; v13 – one platform → several different stores; v14 – builder UI with
live preview as the hero. v12/v16 were reviewed; nothing was adopted from them.

## Tokens (all literal colours live in `:root`)

| Role | Value |
| --- | --- |
| Paper / ink / brand / accent | existing `--rs-*` tokens (brand continuity) |
| Workbench chrome | `--rs-brand-strong` (dark green) |
| Demo palettes | forest (`--rs-brand`), indigo, copper, graphite — `--rh-p-*` |

Type: Vazirmatn only (already shipped); hierarchy by size/weight; headline `text-wrap: balance`.
Radii/shadows reuse `--rs-radius-*`, `--rs-shadow-*`.

## Page structure

1. Hero — h1 «با راستی‌سی فروشگاه اینترنتی خودت را بساز و مدیریت کن», badge «فروشگاه‌ساز اینترنتی», CTAs «شروع ساخت فروشگاه» → `/register/` and «دموی زنده را امتحان کن» → `#demo`.
2. One platform, three different stores (only place photos appear; every card tagged «فروشگاه نمونه ساخته‌شده با راستی‌سی» + disclaimer).
3. Three real steps: ساخت فروشگاه → افزودن محصولات → مدیریت فروشگاه.
4. `#demo` — name, template, colour, desktop/mobile; explicit "no account is created, nothing is saved".
5. Admin panel tabs (محصولات / تصاویر / سفارش‌ها; order statuses mirror `Order.Status`).
6. Mobile.
7. Pointer to `/plans/` (no prices, trials or counts invented), FAQ (5), final CTA.

## Contract

- No invented claims: prices, trial, customer counts, 24/7 support, domain features. Enforced by `test_public_home_landing.py`.
- Sample content is always labelled sample/demo; photos stay managed through `public_photo` (admin overrides + alt text still work).
- No inline `style=` / `<style>` / hex in templates; literals only in `:root` (`test_public_site_theme_contract.py` + home CSS test).
- All new classes are `rh-*`; only `home.html` loads `public-home-v3.css/js` (via `block.super`), so other marketing pages are unaffected. Legacy `.rs-hero*`/`.rs-demo-*` rules in `public-site-v2.css` are left in place (shared with `/design/`).
- Tone on this page is informal second person («خودت … بساز»), following the brief; header/footer/other pages remain formal «شما». Flip in one pass if brand voice should be unified.

## Audit notes (improve-ui + web-design-guidelines)

Verified and fixed: miniature store text too small in the wide demo stage (container-query scale-up);
footnote spacing in the admin section; ragged card heights in the multi-store section;
duplicate store name in the demo chrome; missing `touch-action`, input `name`/`spellcheck`.
Not done (outside this page): site-wide skip link in `base_platform.html`; removal of dead legacy hero CSS.
