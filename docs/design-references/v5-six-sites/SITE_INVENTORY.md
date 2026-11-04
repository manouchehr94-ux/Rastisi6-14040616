# Evidence inventory — all six reference sites

**Canonical location:** `docs/design-references/v5-six-sites/`. All references are read-only and NOT template assets for end customers.

All six archives were unpacked into `references/<site>/capture/` preserving the relative names of HTML/CSS/images/fonts, except four screenshots in each `Screenshot/ScreenShot` folder, which were renamed and stored **byte-for-byte** at `references/<site>/screenshots/original/`. Images with duplicate WP resolution suffixes are intentionally retained to preserve HTML srcsets and CSS links.

Each full-page original screenshot is also split into 2,800-pixel-high WebP parts under `screenshots/segments/` for convenient model inspection. Use original PNG for pixel-level comparison, noting capture pixel width is not guaranteed to equal CSS viewport width.

## Site inventory

| Site | Original files retained in capture | HTML files | CSS | Font files | Images | Original screenshots | WebP segments |
|---|---:|---:|---:|---:|---:|---:|---:|
| AsalBanoo | 639 | 1 | 41 | 4 | 593 | 4 | 15 |
| Dize | 233 | 1 | 64 | 44 | 123 | 4 | 9 |
| khanehshokolati | 252 | 1 | 3 | 16 | 232 | 4 | 16 |
| lilikacosmetics | 301 | 1 | 76 | 10 | 214 | 4 | 10 |
| lilium-gallery | 216 | 2 | 13 | 9 | 190 | 4 | 9 |
| zhimunplus | 586 | 3 | 2 | 10 | 571 | 4 | 19 |

## HTML pages (reported `<title>`, not proof of captured product HTML)

### {site}
- `references/AsalBanoo/capture/index.html` — title: فروشگاه خرید لوازم آرایشی، محصولات پوستی، مویی و عطر
- Screenshots (originals): `home-desktop.png`, `home-mobile.png`, `product-desktop.png`, `product-mobile.png` in `references/AsalBanoo/screenshots/original/`.

### {site}
- `references/Dize/capture/index.html` — title: خانه - دیزه
- Screenshots (originals): `home-desktop.png`, `home-mobile.png`, `product-desktop.png`, `product-mobile.png` in `references/Dize/screenshots/original/`.

### {site}
- `references/khanehshokolati/capture/index.html` — title: فروشگاه اینترنتی خانه شکلاتی
- Screenshots (originals): `home-desktop.png`, `home-mobile.png`, `product-desktop.png`, `product-mobile.png` in `references/khanehshokolati/screenshots/original/`.

### {site}
- `references/lilikacosmetics/capture/index.html` — title: فروشگاه لوازم آرایشی لیلیکا - انواع لوازم آرایشی برند
- Screenshots (originals): `home-desktop.png`, `home-mobile.png`, `product-desktop.png`, `product-mobile.png` in `references/lilikacosmetics/screenshots/original/`.

### {site}
- `references/lilium-gallery/capture/index.html` — title: فروشگاه اینترنتی لیلیوم گالری وارد کننده برترین برند ها - فروشگاه اینترنتی لیلیوم گالری
- `references/lilium-gallery/capture/index_1.html` — title: (not specified)
- Screenshots (originals): `home-desktop.png`, `home-mobile.png`, `product-desktop.png`, `product-mobile.png` in `references/lilium-gallery/screenshots/original/`.

### {site}
- `references/zhimunplus/capture/index.html` — title: ژیمون پلاس - خرید اکانت پریمیوم💎
- `references/zhimunplus/capture/index_1.html` — title: (not specified)
- `references/zhimunplus/capture/index_2.html` — title: LottieFiles animation
- Screenshots (originals): `home-desktop.png`, `home-mobile.png`, `product-desktop.png`, `product-mobile.png` in `references/zhimunplus/screenshots/original/`.

## Evidence strength

**Exact**: original HTML/CSS/file assets, screenshot PNG pixels, saved fonts. **Partial**: JavaScript behavior and product page computed styles. **Not verified**: true viewport, hover/active states, product variant mechanics, cross-browser parity.

An initial report is provided for orientation, not acceptance-grade implementation instructions. Claude should inspect actual assets, measure CSS, compare against R4, and issue a new evidence-backed comprehensive report.
