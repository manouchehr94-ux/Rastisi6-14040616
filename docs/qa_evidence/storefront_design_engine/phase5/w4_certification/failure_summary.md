# W4C Final Certification Campaign -- Failure Summary

CAMPAIGN_HEAD: `1e4efad80fbfc998cfd05d79658955193e1799d5`

FAIL: 0
BLOCKED: 0
NEEDS REPAIR: 6 (rendered visual distinctness closure round; see visual_distinctness_matrix.md)

No FAIL or BLOCKED browser cell was recorded across all 704 cells of the final certification campaign; that result is unchanged.

The rendered visual distinctness closure round (grounded in the actual Home Desktop+Mobile evidence, not configuration signatures alone) found 3 genuine NEEDS REPAIR pairs, 6 Templates total:

| Template | Cell | Reason | Evidence path | Recommended repair owner |
|---|---|---|---|---|
| `pine_eco` | Home (Desktop+Mobile) | Materially indistinguishable from `green_workshop` -- identical hero, promo-block section, header nav items, and Mobile bottom-nav rendering; only `card` and `footer` config differ, neither visible above the fold | `home_gallery/pine_eco_home_desktop.jpg`, `home_gallery/pine_eco_home_mobile.jpg` | Design/Template curation |
| `green_workshop` | Home (Desktop+Mobile) | Same pair as above | `home_gallery/green_workshop_home_desktop.jpg`, `home_gallery/green_workshop_home_mobile.jpg` | Design/Template curation |
| `playful_lifestyle` | Home (Desktop) | Materially indistinguishable from `laleh_play` -- identical arch-cutout hero composition/photos/headline/CTA/header nav; only background/accent palette (mint vs sunset) differs | `home_gallery/playful_lifestyle_home_desktop.jpg` | Design/Template curation |
| `laleh_play` | Home (Desktop) | Same pair as above | `home_gallery/laleh_play_home_desktop.jpg` | Design/Template curation |
| `silk_editorial` | Home (Desktop) | Materially indistinguishable from `parnian_editorial` -- identical hero panel (photo/headline/CTA); only header bar colour and page background tone differ | `home_gallery/silk_editorial_home_desktop.jpg` | Design/Template curation |
| `parnian_editorial` | Home (Desktop) | Same pair as above | `home_gallery/parnian_editorial_home_desktop.jpg` | Design/Template curation |

Per this round's binding rules, none of these Templates' production code/registries were modified this round.

