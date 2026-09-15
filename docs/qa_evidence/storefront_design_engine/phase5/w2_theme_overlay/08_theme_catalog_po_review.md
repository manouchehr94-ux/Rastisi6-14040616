# P5-W2 Theme Catalog — Product Owner Tone Review

This artifact lists every initial occasion in the canonical single owner
`apps/storefront_builder/theme_catalog.py`, for Product Owner review BEFORE W2
merge. Theme presentation (below) and merchant campaign/promotional messaging
are deliberately separate concerns — no aggressive promotional copy is part of
the Theme layer.

**Mourning entries are flagged with ⚠️ and are structurally guaranteed to be
non-celebratory** (the catalog refuses to construct a mourning occasion that
carries `festive_motifs`, `countdown_pressure`, or `sale_badge`).

Intensity behavior is uniform across occasions: `subtle` / `balanced` /
`strong` scale the platform-owned motif opacity (0.06 / 0.12 / 0.20) and the
accent-soft mix (0.08 / 0.16 / 0.28). Accent is a decorative shell edge + soft
section wash — it never swaps merchant content text/background colors.

| key | Persian label | tone | primary accent idea | motif idea | intensity behavior |
|---|---|---|---|---|---|
| `none` | بدون تم مناسبتی | neutral | — (`#000000`, unused) | none | true no-op — no decoration at any intensity |
| `nowruz` | نوروز | festive | fresh spring green `#1FA67A` | spring blossom (`spring_blossom`) | brighter accent band + section wash as intensity rises |
| `yalda` | یلدا | festive | pomegranate crimson `#B31E4B` | pomegranate night (`pomegranate_night`) | deeper crimson wash as intensity rises |
| `valentine` | ولنتاین | festive | rose pink `#E23A6E` | hearts (`hearts`) | softer/heavier rose wash by intensity |
| `ramadan` | رمضان | neutral | calm teal `#2C6E7F` | crescent + lantern (`crescent_lantern`) | restrained; gentle accent, never festive particles |
| `eid_fitr` | عید فطر | neutral | soft green `#3C8C6A` | crescent + star (`crescent_star`) | restrained celebratory-neutral accent |
| `eid_qorban` | عید قربان | neutral | warm gold `#8A6A2F` | geometric gold (`geometric_gold`) | restrained warm accent |
| ⚠️ `muharram` | محرم و عاشورا | **mourning** | muted charcoal `#2B2F36` | muted banner (`muted_banner`) | **restrained only**: faint neutral band, no motion, no festive motif, no countdown, no sale badge — even at `strong` |

## Tone-safety guarantees (enforced in code + tested)
- ⚠️ `muharram` (mourning): `festive_motifs=False`, `countdown_pressure=False`,
  `sale_badge=False`. Enforced structurally in `ThemeOccasion.__post_init__`
  (a mourning entry with any of those set raises `InvalidThemeCatalogEntry`).
  CSS (`occasion_theme.css`) additionally disables animation and keeps the
  wash calm/normal-blend for `[data-occasion-tone="mourning"]`.
- Islamic observances (`ramadan`, `eid_fitr`, `eid_qorban`) are `neutral` and
  carry NO festive particle motifs and NO sale pressure by default — respectful.
- Automated tests assert: `muharram` tone == `mourning`
  (`test_muharram_tone_is_mourning`), and mourning carries no celebratory flags
  (`test_mourning_theme_does_not_enable_celebratory_flags`).

## PO decision points
1. Confirm the accent colors and Persian labels are acceptable per occasion.
2. Confirm mourning restraint for Muharram/Ashura is sufficient.
3. Additional Iranian/Islamic occasions can be added later through the SAME
   catalog mechanism (one entry each) with no architecture change.

_Awaiting Product Owner sign-off before W2 merge (PR is intentionally UNMERGED)._



---

## Actual rendered motif behavior (Repair B — implemented, not just "ideas")

Each occasion's `motif` token now drives a real, bounded, platform-owned CSS
decoration in the single shared `occasion_theme.css` (keyed off
`data-occasion-motif` on `<html>` and on page-section wrappers). No per-template
fork, no merchant CSS. Intensity scales the ornament opacity
(subtle 0.06 · balanced 0.12 · strong 0.20).

| occasion | motif token | rendered treatment |
|---|---|---|
| nowruz | `spring_blossom` | soft green radial "petals" cluster in the top corner |
| yalda | `pomegranate_night` | deep crimson orb + soft halo (pomegranate-night) top corner |
| valentine | `hearts` | overlapping soft heart-like blobs top corner |
| ramadan | `crescent_lantern` | restrained teal crescent ring (Islamic, no festive particles) |
| eid_fitr | `crescent_star` | crescent ring + small star dot |
| eid_qorban | `geometric_gold` | warm-gold geometric diagonal weave |
| ⚠️ muharram | `muted_banner` | a single calm, flat mourning band — **no** corner ornament, **no** glow, **no** festive shapes, **no** animation |

Verified in Browser QA on two materially different Ready Templates
(`dense_marketplace`, `editorial_jewelry`): a strong Yalda visibly reads as
Yalda (crimson band + pomegranate corner ornament), Nowruz differs from Yalda
(green blossom vs crimson orb), Ramadan is a restrained teal crescent, and
Muharram/Ashura remains a calm neutral band with no celebratory affordance.
See `07_browser_qa_report.md` and `screenshots/`.

_Still awaiting Product Owner sign-off before W2 merge (PR #8 intentionally UNMERGED)._
