# V5 six-site kit — font substitutions

Only fonts with a licence that allows redistribution are bundled (`apps/core/static/fonts/`, licence texts in `fonts/licenses/`).
The commercial fonts used by the reference sites are **not** bundled and **not** referenced: each template uses the closest licensed
face and the difference is stated here.

| Template | Reference font(s) (from the saved CSS) | Font used by the template | Licence | Visible difference |
|---|---|---|---|---|
| `decor_sand_boutique` (Dize) | IRANYekanX / Anjoman / Dana (stack of several; the active one cannot be proven from the CSS alone) | **Estedad** | OFL (bundled) | Estedad has slightly rounder terminals and a larger x-height than IRANYekan; line breaks can differ by a word on long titles. |
| `rose_beauty_store` (Lilika) | IRANYekan | **Estedad** | OFL (bundled) | Same as above; weight 700 headings read marginally heavier. |
| `pink_beauty_gallery` (Lilium) | Vazirmatn | **Vazirmatn** | OFL (bundled) | None — same family. |
| `campaign_beauty_hub` (AsalBanoo) | IRANSansWeb_FaNum | **Estedad** | OFL (bundled) | IRANSans has narrower digits; digits are formatted by the platform's own Persian-digit filter, so only their width differs. |
| `cocoa_gift_shop` (khanehshokolati) | IRANSansDN | **Estedad** | OFL (bundled) | As for AsalBanoo. |
| `neon_digital_store` (zhimunplus) | YekanBakh (body) + Rokh (display headings) | **Estedad** (body and headings); **Lalezar** is available as a display face a merchant can pick | OFL (bundled) | Rokh's heavy display forms are approximated by Estedad 800; no Latin display face is bundled. |

Fonts added to the engine for this kit (all OFL, two unicode-range subsets each so unused scripts are never downloaded):
Estedad, Noto Sans Arabic, Lalezar. A merchant can still choose any of the seven registered families per store.

If a merchant holds a licence for one of the reference fonts, the engine accepts it only through the normal font setting once the font
family is added to the registry together with its licence file — nothing in a template recipe names a commercial font.
