# P5-W4C Rendered Visual Distinctness Repair — Starting State

## Provenance

- Current branch (start): `feature/phase5-w4c-all50-certification`
- Starting HEAD: `0898c31bdca868f68f36a52021838201dfb2706f`
- Certified old campaign HEAD (704-cell result, unaffected by this round): `1e4efad80fbfc998cfd05d79658955193e1799d5`
- Pre-repair final source HEAD: `b3f2c43974ffd528a4374fb6a3c35af20314379c`
- Official base: `3a4fe9070584655548bae5a9bb574f3415bbf580` (unchanged)
- PR: #12, OPEN + UNMERGED

## Independent Architect verdict this round

704-cell browser campaign: APPROVED for its old source head.
Rendered visual distinctness: NEEDS REPAIR.
Open design findings: `pine_eco`/`green_workshop`, `playful_lifestyle`/`laleh_play`, `silk_editorial`/`parnian_editorial`.

## Repair strategy (binding)

Repair exactly one Template from each pair. Anchors (`pine_eco`,
`playful_lifestyle`, `silk_editorial`) are not modified. Targets
(`green_workshop`, `laleh_play`, `parnian_editorial`) are bumped to a new
version with a genuine above-the-fold structural change.

## Reporting precision correction (Section 3)

Independent GitHub blob verification: `pine_eco`/`green_workshop` Mobile
Home screenshots are byte-identical (same SHA256:
`78a873a262eb3c4e428299f7c58c1b5b8e23eda33f4f02da524fb815e8f579e5`).
Desktop Home screenshots are different JPEG blobs (`61308dc1...` vs
`574c36c2...`) that were judged visually indistinguishable above the
fold. Corrected in `visual_distinctness_matrix.json`/`.md`,
`execution_report.md` (commit `b4c8396f`) — does not change the
underlying finding or verdict.

## Source facts confirmed before any edit (Section 4)

Read directly from `apps/storefront_builder/a8_ready_templates.py`:

- `pine_eco` / `green_workshop` (v2 each): identical `header.compact_menu.v1`,
  `hero.editorial_split.v1`, `layout.three_column.v1`,
  `product_view.standard_grid.v1`, `bottom_nav.floating_dock.v1`, palette
  `sage`, font `Vazirmatn`, density `relaxed`, radius `16`. Differ only in
  `card` (`soft_capsule` vs `standard`) and `footer` (`centered` vs
  `brand_story`) — neither visible above the fold.
- `playful_lifestyle` / `laleh_play` (v2 each): identical
  `header.playful_canopy.v1`, `hero.image_collage.v1`,
  `layout.three_column.v1`, `product_view.standard_grid.v1`,
  `bottom_nav.five_item.v1`, font `Vazirmatn`, density `relaxed`, radius
  `22`. Differ only in `card` (`soft_capsule` vs `paper_frame`) and palette
  (`mint` vs `sunset`).
- `silk_editorial` / `parnian_editorial` (v2 each): identical
  `header.editorial_masthead.v1`, `hero.immersive.v1`,
  `layout.two_column.v1`, `product_view.editorial_grid.v1`,
  `bottom_nav.minimal_icons.v1`, font `Vazirmatn`, density `relaxed`,
  radius `0`. Differ only in `card` (`editorial_minimal` vs
  `shelf_editorial`) and palette (`atelier-ivory` vs `uupm-bakery-cream`).

Also confirmed the exact `_HERO_VARIANTS` mapping in `_home()`/`_appearance()`:
several *different* hero family names resolve to the *same* rendered
`hero_style` (e.g. `editorial_split`/`typographic`/`quiet`/`search_first`
all -> `"split"`; `image_collage`/`campaign_mosaic`/`social_gallery` all
-> `"atelier_triptych"`) — meaning a valid repair must change the
rendered hero_style, not just the raw hero key, or it silently
reproduces the same defect against a different key. This drove the
mid-round code-review correction documented in `code_review.md`.

Also confirmed the exact version-history preservation pattern
(`_HISTORICAL_SPECS` tuple, registered via the same `register_layout_preset`
authority, `get_layout_preset_version(key, version)` lookup) already used
for every prior version bump in this file — reused verbatim, no new
mechanism introduced.
