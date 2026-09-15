# P5-W2 Browser QA Report — Reversible Theme Overlay

Real, server-rendered public storefront (`manage.py runserver`, DEBUG),
demo Store `rasti-mode-demo` (Ready Template **dense_marketplace**, published V2),
public page `/products/` (a page that extends the universal
`storefront_shell.html` → `base.html`; the standalone `catalog/home.html` home
page is intentionally not shell-based).

Screenshots captured headless (Chromium via `agent-browser`) through a
localhost reverse proxy that injects the demo Store's Host header (works around
the headless-CDP forbidden-`Host`-header quirk; Django still resolves the Store
by Host exactly as in production). Occasion applied through the canonical
`appearance_authority_service.apply_theme` + real Draft publish each time.

## Logical matrix covered
| Occasion | Tone | Intensity | Viewports | Resolved DOM `data-occasion-*` | Horizontal overflow |
|---|---|---|---|---|---|
| Yalda (festive, Iranian) | festive | strong | 1440×900, 768×1024, 390×844 | `yalda / festive / strong` | none (-10px) |
| Ramadan (Islamic) | neutral | balanced | 1440×900, 390×844 | `ramadan / neutral / balanced` | none (-10px) |
| Muharram/Ashura (mourning) | mourning | subtle | 1440×900 | `muharram / mourning / subtle` | none (-10px) |
| None (clear/restore) | — | — | 1440×900 | attribute ABSENT (`null`) | none (-10px) |

Screenshots (in `.kiro/artifacts/screenshots/`):
- `yalda-strong-desktop-1440x900.png`, `yalda-strong-tablet-768x1024.png`, `yalda-strong-mobile-390x844.png`
- `ramadan-balanced-desktop-1440x900.png`, `ramadan-balanced-mobile-390x844.png`
- `muharram-subtle-desktop-1440x900.png`
- `none-restore-desktop-1440x900.png`

## Checks (all PASS)
- **No horizontal overflow**: `scrollWidth - innerWidth = -10px` at every viewport (desktop/tablet/mobile).
- **No console errors**: none captured on load.
- **Global chrome themed**: a platform-owned occasion accent band renders at the
  top of the shell (`body::before`, occasion accent color) — Yalda crimson
  `#B31E4B` clearly visible in the desktop/tablet/mobile shots; header remains
  fully readable, bottom-nav/footer edges pick up the same accent.
- **Section treatment**: the shared `responsive_section_wrapper` carries
  `data-occasion-theme`/`-tone` so page sections receive the soft occasion wash
  from the SAME resolved theme (one resolved theme drives chrome AND sections).
- **RTL preserved**: `dir="rtl"` layout intact; nav, breadcrumb, product grid all correct.
- **Reduced motion / mourning restraint**: Muharram (mourning, subtle) renders a
  faint neutral `#2B2F36` band at 0.06 motif-opacity — NO festive color, NO
  confetti/particles, NO countdown, NO sale badge. Visibly restrained and respectful.
- **Intensity difference**: motif-opacity scales 0.06 (subtle) < 0.12 (balanced)
  < 0.20 (strong) — server-resolved and confirmed in the served CSS variables.
- **Template independence**: identical occasion markers/behavior on the
  dense_marketplace template; the overlay is a single token layer with no
  per-template fork.
- **Theme none restores base appearance**: after Clear, `data-occasion-theme` is
  absent and the page is visually identical to the pre-theme baseline (no band).
- **Preview/Public parity**: the resolved overlay printed by the canonical
  resolver (`occasion/tone/intensity/vars`) exactly matches the served HTML
  attributes and CSS variables; automated test
  `ThemeRenderingTests.test_preview_public_parity_after_publish` asserts
  byte-identical resolved theme for draft-preview and published-public.
- **Contrast/readability**: header text, product titles, prices remain legible
  across all occasions/intensities (accent is a decorative edge/wash, never a
  text/background swap of merchant content).
- **Layout not corrupted**: product grid, filters, header, breadcrumbs unchanged.

## Server-rendered HTML marker verification (public /products/)
```
BASELINE (clear):   occasion attrs ABSENT; occasion_theme.css linked (inert)
YALDA strong:       data-occasion-theme="yalda" tone="festive" intensity="strong" --occasion-accent:#B31E4B
RAMADAN balanced:   data-occasion-theme="ramadan" tone="neutral" intensity="balanced" --occasion-accent:#2C6E7F
MUHARRAM subtle:    data-occasion-theme="muharram" tone="mourning" intensity="subtle" --occasion-accent:#2B2F36
```

Conclusion: Browser QA PASS across desktop/tablet/mobile for festive (Iranian),
Islamic, and mourning occasions and all three intensities; theme none restores
the base appearance; mourning tone is restrained and non-celebratory.
