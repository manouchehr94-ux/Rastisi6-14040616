# P5-W4B — 50-Template Curation: Design / Inventory Gate

**Status:** DESIGN GATE ONLY, REPAIR ROUND 2. No production/test code has
been touched by this document, this repair, or this workstream so far.
Only the two design/inventory documents named in the repair instruction
were modified this round.

**Repair context:** Independent Architect re-review of design head
`b450722bd87916a9fcc8380c80762b220c52c308` returned CRITICAL:0 / IMPORTANT:4,
verdict REPAIR REQUIRED. Round 1's repairs (exact-50 versioning
architecture, bounded composition-token compilation, invisible-default
section classification, removing "trivially true") were **accepted
unchanged** and are kept below. This round fixes 4 new findings: (1)
`blog_posts` has a confirmed dead placeholder link and must not be used;
(2) the "even distribution" language must be removed and `promo_cards` is
confirmed functionally redundant with `category_grid`; (3) cluster C10
(`tower_department`/`harbor_imports`) must be actively curated, not
deferred; (4) the historical-preservation test must fingerprint the whole
`LayoutPresetDefinition`, not just the Home section-key sequence, plus a
historical forbidden-payload safety scan. Nothing here starts production
implementation or W4C.

**Certified starting checkpoint:** `707dd631e851bdd13173bf3950489142f3e526b1`
(HEAD of `feature/phase5-design-expansion`) — re-verified unchanged at the
start of this repair round.

**Authoritative source for scope:** `docs/superpowers/plans/
2026-09-15-phase5-converged-completion-plan.md`, §P5-W4B.

**Companion evidence:** `docs/qa_evidence/storefront_design_engine/phase5/
w4b_template_curation/w4b_curation_inventory.md` — full 50-row inventory,
cluster analysis, the versioning mechanism (§7), the round-1 section
classification (§9, partially superseded), the Tier-2 per-axis diff
evidence (§10), and the **round-2 template-quality audit + corrected
eligibility table (§11–§12)** this revision is built on.

---

## 1. Goal (unchanged, restated from the authoritative plan)

> Reuse EXISTING section/component families to make the 50 Ready Templates
> materially and intentionally different from each other. This is NOT a new
> design engine, NOT a new editorial subsystem, NOT a request to create more
> than 50 Ready Templates, and NOT an excuse to insert every available
> component into every template.

Primary production scope: **data-level composition/recipe curation inside
`apps/storefront_builder/a8_ready_templates.py`.** No renderer, registry, or
persistence-architecture change is proposed.

## 2. What "material difference" means here (unchanged)

`recipe_signature()` already produces 50 pairwise-unique signatures today.
The real curation target is repetition the signature test cannot see:
templates whose Home **skeleton** (section-type sequence, ignoring
settings) is identical to another's.

## 3. The repetition finding (unchanged)

- 32/50 templates use exactly 4 Home sections.
- The single largest cluster (**C1**, 10 templates) is *exactly*
  `hero_banner → category_grid → product_section → image_text`:
  `premium_leather_noir`, `artisan_grain`, `coastal_product`,
  `handmade_luxe`, `horizon_story`, `silk_editorial`, `city_classic`,
  `kamand_artisan`, `watchmaker_round`, `parnian_editorial`.
- 10 further clusters of size 2–4 repeat the pattern at smaller scale.
- 16 templates already have a unique skeleton.

## 4. Revised material-curation principle — resolves the review's "revised material-curation principle" section

"A new section exists in the recipe" is **not** equated with "the template
is materially better/different." Every actively curated template must
satisfy all six:

1. Coherent identity rationale (not picked at random, not picked to hit a
   coverage number — companion inventory §12 confirms zero-prior-usage was
   never itself a selection criterion).
2. Structural difference (`recipe_signature()` changes; the Home skeleton
   changes).
3. Merchant-visible difference under the shared fixture (§6) — the added
   content actually renders, not an empty DOM node.
4. **No dead primary interaction introduced** — a section whose primary
   link/action is a placeholder (`href="#"` or equivalent) is disqualified
   outright, regardless of how "visible" it otherwise is.
5. No fake merchant content, no ID in Template DNA.
6. **No duplicated/redundant section without a specific purpose** — adding
   a section that repeats what an existing section in the *same* recipe
   already does is not curation.

## 5. Section eligibility — round-2 corrected (resolves IMPORTANT-1 and IMPORTANT-2A/2B)

Full source citations, the rendered-template reads, and the complete
eligibility table (with the exact columns the review asked for: visible
with fixture / primary links functional / tenant scoping correct /
semantic data source / duplicates another section in the target recipe /
eligible as primary differentiator) are in companion inventory §11–§12.
Summary of the two corrections:

**`blog_posts` — REJECTED.** `blog_posts.html`'s own comment states the
post-detail route does not exist yet in the project, and every rendered
card is `<a class="blog-card" href="#">` — a confirmed dead placeholder
link. Classification:
- VISIBLE: YES, when `BlogPost` rows exist.
- INTERACTIONALLY COMPLETE: **NO**.
- ELIGIBLE AS W4B PRIMARY DIFFERENTIATOR: **NO**.
- Not fixed in W4B (no Blog detail subsystem, no Content/CMS widening,
  per the review's explicit instruction). Remains a valid, existing,
  registered section usable once its navigation contract is completed in
  a future workstream — out of scope here.

**`promo_cards` — REJECTED (different reason: redundancy, not
brokenness).** `promo_cards.html` renders a real, working link
(`catalog:product-list?category=slug`) — but its markup is functionally
and structurally near-identical to `category_grid.html`'s own default
`else` branch (same tile-cycling pattern, same "مشاهده محصولات {name}"
button, same destination URL), and `category_grid` is present in 49/50
templates including every Tier-1 candidate. Adding `promo_cards` anywhere
in this proposal would render a second, near-identical block of the same
Store's own Categories — disqualified as redundant, not as broken.

**5 sections remain eligible** (all pass every check in companion
inventory §12): `collection_tiles`, `image_slider`, `story_rail`,
`brand_carousel`, `trust_features`. `brand_carousel` and `trust_features`
are newly added to the candidate pool this round — both were always
existing, registered, working sections; round 1 simply hadn't needed them
yet. `trust_features` in particular needs **zero** Store data or fixture
content to render (a static, universal 4-badge default) — the strongest
visibility guarantee of any candidate.

`faq`, `testimonials`, `video_section`, `quick_links` remain rejected from
round 1 (empty by default, no auto-source) — unchanged from the prior
repair.

## 6. No artificial distribution target — resolves IMPORTANT-2

Round 1 stated the 5 (then different) Group-A sections were "intentionally
even" at 4 templates each. That target is **removed**. W4B is curation,
not quota balancing — an uneven distribution is fully acceptable, and the
repaired Tier-1 proposal below is deliberately uneven (§8: 5/5/4/3/3
across the 5 eligible sections), driven only by per-template identity fit.

## 7. Standard shared W4B QA visibility fixture — updated

| Fixture element | Used by | Belongs to |
|---|---|---|
| The existing demo Store's product/category set (unchanged, already reused by every other Ready Template QA pass) | `category_grid`, `product_section` (unchanged baseline) | QA fixture (already exists) |
| ≥1 active `MerchantCollection` | `collection_tiles` | QA fixture (new) |
| ≥1 active `Brand` | `brand_carousel` | QA fixture (new — replaces the round-1 `BlogPost` fixture requirement, now dropped along with `blog_posts`) |
| ≥1 `HeroSlide` scoped to the new `image_slider` section, per curated template | `image_slider` | QA fixture (same mechanism `ApplyAndRenderSmokeTests` already uses for `hero_banner`) |
| ≥1 active `StoryRailItem`, per curated template | `story_rail` | QA fixture (same mechanism already proven for `mina_community`) |
| *(none needed)* | `trust_features` | Renders its static universal default with zero fixture content |

The round-1 `BlogPost` fixture entry is removed — `blog_posts` is not used
anywhere in this proposal, so no fixture content should be created "only
to make a bad section choice appear valid" (explicit review instruction).
Template DNA vs QA fixture split is unchanged from round 1: Template DNA
only ever names a `section_key` + neutral default settings; the fixture's
actual Collection/Brand/HeroSlide/StoryRailItem rows are QA/setup data,
never written into `a8_ready_templates.py`.

## 8. Proposed curation — Tier 1 REPAIRED (20 templates) + C10 (1 template) = 21 active

Every addition is one of the 5 eligible sections (§5), chosen for identity
fit. Distribution is intentionally uneven (§6): `image_slider`×5,
`collection_tiles`×5, `story_rail`×4, `brand_carousel`×4,
`trust_features`×3 across 21 templates.

### Cluster C1 (10 templates)

| Key | Identity | Addition (round-2 final) | Why | Fixture dependency |
|---|---|---|---|---|
| `premium_leather_noir` (زر) | luxury dark leather, immersive hero | `image_slider` | Cinematic product-imagery slider, same precondition class as its own `hero_banner`. | 1 `HeroSlide` on the new section |
| `handmade_luxe` (چرم دست) | handcraft leather | `brand_carousel` *(changed from the rejected `blog_posts`)* | A handcraft-leather boutique showcasing the brands it carries is a standard retail pattern. | shared `Brand` fixture |
| `artisan_grain` (دانه) | grain/organic artisan | `collection_tiles` | Organic/artisan product-collection showcase. | shared `MerchantCollection` fixture |
| `watchmaker_round` (ساعت‌ساز) | watch precision, portrait_round card | `brand_carousel` *(changed from the rejected `promo_cards`)* | Multi-brand watch boutique is the standard retail pattern for this vertical. | shared `Brand` fixture |
| `coastal_product` (موج) | coastal lifestyle | `image_slider` | Coastal lifestyle imagery slider. | 1 `HeroSlide` on the new section |
| `horizon_story` (افق) | travel/sand editorial — "story" in the identity | `story_rail` | Strong nominal fit. | 1 `StoryRailItem` |
| `silk_editorial` (ابریشم) | silk editorial luxury | `collection_tiles` | Silk collections as a curated tile set. | shared `MerchantCollection` fixture |
| `city_classic` (شهر) | city/classic professional | `trust_features` *(changed from the rejected `promo_cards`)* | Generalist trust/authenticity strip fits a "classic" identity; zero fixture dependency. | none |
| `kamand_artisan` (کمند) | artisan clay | `image_slider` *(changed from the rejected `blog_posts`)* | Artisan-process imagery slider. | 1 `HeroSlide` on the new section |
| `parnian_editorial` (پرنیان) | editorial cream | `story_rail` | Editorial highlight rail. | 1 `StoryRailItem` |

C1 distribution: `image_slider`×3, `collection_tiles`×2, `brand_carousel`×2,
`story_rail`×2, `trust_features`×1.

### Cluster C2 (4 templates) — `... → newsletter`

| Key | Identity | Addition (round-2 final) | Why |
|---|---|---|---|
| `niloufar_glass` (نیلوفر) | beauty glass | `collection_tiles` | Beauty product-collection showcase. |
| `beauty_dew` (شبنم) | beauty dew | `image_slider` | Beauty imagery slider. |
| `laleh_play` (لاله‌زار) | playful/floral | `trust_features` *(changed from the rejected `promo_cards`)* | Generic reliability strip; genuinely distinct from the other 3 C2 picks, zero fixture dependency. |
| `almas_luxury` (الماس) | diamond luxury | `story_rail` | Short luxury highlight rail. |

### Cluster C3 (3 templates) — `... → image_text → newsletter`

| Key | Identity | Addition (round-2 final) | Why |
|---|---|---|---|
| `green_workshop` (سبزه) | eco/green workshop | `trust_features` *(changed from the rejected `blog_posts`)* | An eco brand's own certification/quality trust strip — strong identity fit, zero fixture dependency, and further widens the gap from `pine_eco` (see identity-overlap note below). |
| `pine_eco` (کاج) | eco (identity-overlap note) | `collection_tiles` | Eco product-collection showcase — a different mechanism from `green_workshop`'s `trust_features`. |
| `mirror_beauty` (آینه) | beauty | `image_slider` | Beauty imagery slider. |

**Identity-overlap note (unchanged observation, not a defect):**
`green_workshop` and `pine_eco` are both eco-themed; distinct card styles
(`standard` vs `soft_capsule`) plus now two structurally different
additions (`trust_features` vs `collection_tiles`) separate them clearly.
No key rename proposed.

### Cluster C4 (3 templates) — `... → trust_features`

All three already have `trust_features` in their baseline composition, so
none of them can add it again (would duplicate — companion inventory §12,
column 5). Additions:

| Key | Identity | Addition (round-2 final) | Why |
|---|---|---|---|
| `cedar_home` (سدر) | home/furniture | `collection_tiles` *(changed from the rejected `blog_posts`)* | Furniture/home retailers organize by "room collections" — a strong, standard retail pattern. |
| `simorgh_market` (سیمرغ) | general marketplace | `brand_carousel` *(changed from the rejected `promo_cards`)* | Marketplaces conventionally feature a multi-brand carousel. |
| `rayan_tech` (رایان) | tech | `story_rail` | Tech-highlights rail. |

### Cluster C10 (1 of 2 templates curated) — resolves IMPORTANT-3

`tower_department` and `harbor_imports` share header, hero, layout,
product_view, and footer, differing only in card style
(`marketplace_price` vs `shipping_label`) and bottom-nav variant — the
weakest-justified "unchanged" pair in the catalog (companion inventory
§10). Per the review's explicit instruction, this specific pair (and only
this pair) is promoted into active curation — no other Tier-2 pair is
touched.

| Key | Identity | Addition | Why | Structural effect |
|---|---|---|---|---|
| `harbor_imports` (بندر — literally "harbor/imports") | import/shipping marketplace, `shipping_label` card already reflects this | `brand_carousel` | An "imports" identity is the single strongest nominal fit of any candidate in the whole catalog for a multi-brand carousel — imported goods are conventionally presented by the brands that make them. | Home composition grows from 5 to 6 sections and gains a section type `tower_department` does not have — the two no longer share a skeleton at all (not just a settings difference). |

`tower_department` is **not** modified — per the review's own allowance
("21 curated templates is fine if only one C10 template needs change"),
changing one side of a near-duplicate pair is sufficient to break the
near-duplicate relationship, and `harbor_imports`'s own identity
(`بندر` = harbor) is the clearly stronger fit for `brand_carousel` than
`tower_department`'s (`برج` = tower, a generic department-store identity
with no comparably strong single-section fit). Cosmetic-only changes
(palette/font/motion) are explicitly insufficient per the review and are
not what is proposed here — this is a real added section with a new,
functioning, visible interaction.

**Tier-1 + C10 total: 21 actively curated templates.** The count is not
rounded to 20 or 22 on purpose — it is exactly how many templates the
source-backed rationale above supports.

## 9. Composition-token compilation fix — updated to the final token set (resolves IMPORTANT-2's "final token allowlist" instruction)

**Only 2 genuinely new tokens are needed.** `_home()`'s `_STATIC_SECTIONS`
dict already contains identity-mapping rows for `trust_features` (directly)
and for `story_rail`/`brand_carousel` under different token names
(`community_gallery` → `story_rail`; `brands` → `brand_carousel`) — the
repaired Tier-1 proposal reuses those **existing** tokens directly instead
of adding redundant new aliases:

- Templates gaining `story_rail` (`horizon_story`, `parnian_editorial`,
  `almas_luxury`, `rayan_tech`) use the existing composition token
  `"community_gallery"`.
- Templates gaining `brand_carousel` (`handmade_luxe`, `watchmaker_round`,
  `simorgh_market`, `harbor_imports`) use the existing composition token
  `"brands"`.
- Templates gaining `trust_features` (`city_classic`, `laleh_play`,
  `green_workshop`) use the existing composition token `"trust_features"`.

**Genuinely new tokens (2, both identity-mappings, same convention as the
existing `testimonials`/`newsletter` rows):**

```python
_STATIC_SECTIONS = {
    "ticker": "announcement_bar",
    "brand_story": "image_text",
    "editorial_note": "rich_text",
    "service_strip": "trust_features",
    "trust_features": "trust_features",
    "brands": "brand_carousel",
    "testimonials": "testimonials",
    "newsletter": "newsletter",
    "community_gallery": "story_rail",
    # W4B additions — only the 2 tokens the final curation actually uses:
    "collection_tiles": "collection_tiles",
    "image_slider": "image_slider",
}
```

`blog_posts`, `promo_cards`, `faq`, `video_section`, and `quick_links` are
**not** added — none is used anywhere in the final proposal, and adding an
unused alias would be exactly the speculative allowlist growth the review
forbade.

**Test contract (unchanged from round 1, restated for completeness):** for
every actively curated key, a focused test must prove its new composition
compiles through `_home()` without raising, produces only
`section_registry.is_valid_section_key`-accepted keys that are
`is_section_allowed_on_page(..., "home")`-permitted, and passes
`register_layout_preset`'s full import-time validation chain without
raising `InvalidLayoutPresetError`.

## 10. Versioning strategy — UNCHANGED, ACCEPTED

The round-1 `_HISTORICAL_SPECS` mechanism is accepted unmodified per the
review:

- `_SPECS` stays at exactly 50 rows; curating a key edits its row in
  place (version bump + new composition), never appends.
- The pre-curation row is copied verbatim into a second, append-only
  tuple, `_HISTORICAL_SPECS`, registered through a second loop that feeds
  `register_layout_preset` (via the same `_build()` compiler) but never
  feeds `A8_READY_TEMPLATES`.
- `A8_READY_TEMPLATES` (built only from `_SPECS`) stays exactly 50;
  `list_ready_templates()` stays exactly 50 (max-version-wins dedup, order
  independent).
- Both latest and historical versions register through the same canonical
  `register_layout_preset`/`LAYOUT_PRESET_REGISTRY`/
  `LAYOUT_PRESET_VERSION_REGISTRY` — no second registry.
- `layout_preset_registry.py` is not touched; the 8 pre-A8 legacy
  hardcoded blocks in it are untouched.

**Scope update for this round:** 21 keys are now curated (the 20 Tier-1
keys plus `harbor_imports`), so `_HISTORICAL_SPECS` holds 21 frozen rows,
and `test_a8_ready_template_catalog.py::EXPECTED_LATEST_VERSIONS` is
updated for 21 keys (was 20 in round 1).

## 11. Full historical fingerprint contract — resolves IMPORTANT-4A

Round 1's proposed historical-preservation test compared only
`tuple(e.section_key for e in historical.pages["home"])` — proving the
Home *skeleton* survived, not the full recipe. This is now replaced with a
whole-object fingerprint covering every field on `LayoutPresetDefinition`
(`key`, `label_fa`, `description_fa`, `version`, `is_ready_template`,
`store_appearance`, `appearance`, `default_palette_slug`, `header`,
`footer`, `pages` — including, per page, every `section_key`/`settings`/
`row_key`/`row_span`/`container_settings` — and `compatible_families`).

**Freeze/fingerprint function** (reuses the exact recursive-freeze pattern
`storefront_appearance/inventory.py::_freeze` already uses for
`recipe_signature`, and `dataclasses.asdict` so no field can be
accidentally omitted by hand-listing):

```python
import dataclasses
import hashlib


def _deep_freeze(value):
    if isinstance(value, dict):
        return tuple(sorted((k, _deep_freeze(v)) for k, v in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(v) for v in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted(_deep_freeze(v) for v in value))
    return value


def fingerprint(preset) -> str:
    frozen = _deep_freeze(dataclasses.asdict(preset))
    return hashlib.sha256(repr(frozen).encode()).hexdigest()
```

**Procedure (part of the TDD RED step, before any recipe is edited):**
1. At the certified W4A base (`707dd631e851bdd13173bf3950489142f3e526b1`),
   compute and record `CERTIFIED_W4A_FINGERPRINT[(key, version)]` for each
   of the 21 keys about to be curated, using their *current* (pre-curation)
   registered `LayoutPresetDefinition`.
2. Implement the curation (in-place `_SPECS` edit + `_HISTORICAL_SPECS`
   freeze, per §10).
3. Assert, for every curated key:
   ```python
   self.assertEqual(
       fingerprint(lpr.get_layout_preset_version(key, old_version)),
       CERTIFIED_W4A_FINGERPRINT[(key, old_version)],
   )
   ```
   This proves the frozen historical row is byte-for-byte identical to
   what was certified at W4A — not just its Home section-key sequence.

## 12. Historical safety scan — resolves IMPORTANT-4B

`test_a8_ready_template_catalog.py::test_recipes_contain_no_tenant_executable_or_prototype_payload`
iterates `lpr.list_ready_templates()` — the **latest** dict only — so it
never walks the new `_HISTORICAL_SPECS` entries. This is not because the
old recipes are suspected unsafe; it is a regression contract so the
historical-copy mechanism itself cannot silently introduce altered data.

**New test:** run the exact same walk/assertion the existing test already
performs (`_walk()` + `FORBIDDEN_DATA_KEYS` intersection + the
`<script`/`javascript:`/`{%`/`{{`/prototype-ID regex checks), but over
`[lpr.get_layout_preset_version(key, old_version) for key, old_version in
CURATED_KEYS_AND_OLD_VERSIONS]` instead of `list_ready_templates()`. No new
scanning logic — the existing test's own walk function is reused verbatim
against the 21 historical entries.

## 13. Post-curation closure matrix — updated counts

**Actively curated (21 templates):** C1 (10) + C2 (4) + C3 (3) + C4 (3) +
`harbor_imports` (1) — §8.

**Unique-skeleton, no shared cluster, no change (16 templates, unchanged
from round 1):** `editorial_jewelry`, `dense_marketplace`, `warm_boutique`,
`premium_leather`, `dark_digital`, `search_market`, `playful_lifestyle`,
`utility_catalog`, `pixel_play`, `fashion_promo_catalog`, `mina_community`,
`tuska_bento`, `collection_index`, `kite_playful`, `ferdowsi_department`,
`anniversary_mosaic`.

**`tower_department` (1 template) — unchanged, no longer paired with an
unresolved near-duplicate.** Its former cluster-mate `harbor_imports` is
now actively curated (§8), so `tower_department` is simply an unmodified,
unique-composition template going forward — not part of any remaining
shared-skeleton pair.

**Shared-skeleton, left unchanged this pass (12 templates, 6 pairs) — same
honest per-axis ranking as round 1, C10 removed (now curated above):**

| Cluster | Pair | Differing axes (count) | Closure judgment |
|---|---|---|---|
| C7 | `roosta_zigzag` / `calligraphy_paper` | 7/7 | Materially distinct already; unchanged is fully justified. |
| C9 | `aftab_price` / `charcoal_grill` | 5/7 | Materially distinct already; unchanged is justified. |
| C8 | `literary_catalog` / `gallery_minimal` | 4/7 | Distinct enough; `gallery_minimal`'s deliberate minimalism is itself a reason to leave it alone. |
| C11 | `mist_quiet` / `night_catalog` | 4/7 | Distinct enough; both deliberately spare/quiet identities. |
| C6 | `tool_finder` / `mother_utility` | 3/7 | Acceptable to leave unchanged; reasonable candidate if scope is later widened. |
| C5 | `street_drop` / `racer_tech` | 3/7 | Acceptable to leave unchanged; reasonable candidate if scope is later widened. |

Total accounted for: 21 (curated) + 16 (unique) + 1 (`tower_department`) +
12 (deferred pairs) = **50**.

## 14. New-section rule compliance (unchanged)

No new section type is proposed. The 5 sections used
(`collection_tiles`, `image_slider`, `story_rail`, `brand_carousel`,
`trust_features`) already exist, are registered, tested, and — per the
round-2 audit (companion inventory §11–§12) — confirmed functionally
sound (real working links where applicable, correct Store scoping, no
redundancy in their assigned target recipe). STAT and any other new
editorial primitive remain untouched/BACKLOG.

## 15. Architecture / duplication / tenant impact (updated)

- **Files expected to change during implementation:**
  - `apps/storefront_builder/a8_ready_templates.py` — (a) 21 `_RecipeSpec`
    rows edited in place; (b) a new `_HISTORICAL_SPECS` tuple (21 frozen
    rows) + one new registration loop; (c) 2 new identity rows in
    `_STATIC_SECTIONS` (§9).
  - `apps/storefront_builder/tests/test_a8_ready_template_catalog.py` —
    `EXPECTED_LATEST_VERSIONS` updated for the 21 bumped keys; new
    fingerprint + historical-safety-scan tests (§11–§12).
  - **`apps/storefront_builder/layout_preset_registry.py` is NOT changed.**
- **No renderer, registry, manifest, or persistence file changes.**
- **Migrations:** expected **zero**.
- **Tenant/Store scoping:** unaffected; all 5 newly-used sections' own
  context builders were confirmed Store-scoped correctly in companion
  inventory §12 (`collection_tiles`/`brand_carousel` filter by `store=store`;
  `image_slider`/`story_rail` reuse the existing scoped-with-fallback
  helpers already proven for `hero_banner`).
- **Merchant data in Template DNA:** none of the 5 sections' default
  settings reference a specific Collection/Brand/HeroSlide/StoryRailItem
  ID — every default is neutral (`collection_ids: []` = "show whatever the
  Store has," etc.).
- **W2/W3 non-interference:** unchanged, `theme` stays `theme.none.v1` for
  all 50.

## 16. Architecture boundary (explicit, per review request)

| Item | Answer |
|---|---|
| Exactly 50 latest Ready Templates | YES |
| New renderer | NO |
| New Ready Template registry | NO |
| New section type | NO |
| New Theme mechanism | NO |
| New Random Mix engine | NO |
| New tenant resolver | NO |
| New ProductCard authority | NO |
| New CMS/blog subsystem | NO |
| Merchant IDs inside Template DNA | NO |
| Migrations | 0 |
| W4C | FROZEN — not started |

## 17. Test plan (repaired — matches the review's 19-point list)

1. `len(A8_READY_TEMPLATES) == 50`.
2. `len(lpr.list_ready_templates()) == 50`.
3. Correct latest version for every one of the 21 curated keys
   (`get_layout_preset(key).version == new_version`).
4. **Full certified-base historical fingerprint equality** for every
   outgoing curated version (§11) — not section-keys-only.
5. **Explicit historical forbidden-payload safety scan** over the 21
   `_HISTORICAL_SPECS` entries (§12).
6. Bounded composition-token compilation — the 2 new `_STATIC_SECTIONS`
   rows (§9) compile without `KeyError` for every curated composition.
7. All added sections registered and Home-allowed
   (`is_valid_section_key`, `is_section_allowed_on_page(..., "home")`).
8. No merchant IDs/content in DNA — existing
   `test_recipes_contain_no_tenant_executable_or_prototype_payload`, run
   unmodified (it already walks `list_ready_templates()` generically) plus
   the new historical scan (item 5).
9. 50/50 pairwise-unique `recipe_signature()` — run and recorded, not
   predicted.
10. Component coverage regression — `test_a8_component_coverage` run; no
    advertised component newly unused, no component added to
    `A8_ADVERTISED_COMPONENTS_BY_FAMILY` (none is proposed — this workstream
    only edits Home composition).
11. All-50 candidate resolution/apply regression using existing canonical
    paths (`test_preset_service`, the `ApplyAndRenderSmokeTests` pattern) —
    confirm all 21 curated latest versions apply/preview without error.
12. Bounded browser QA for every actively curated template (21, not 20) —
    3 standard viewports, RTL, under the fixture (§7); confirm
    Header/Footer/Bottom-Nav duplication stays 0.
13. Latest-vs-historical visible comparison under the identical fixture —
    a screenshot/DOM-assertion pair per curated template proving the added
    section is actually visible, not just present in the manifest.
14. **No dead/placeholder primary interaction introduced** — for every
    actively curated template whose addition has a primary link
    (`collection_tiles`, `brand_carousel`; `image_slider`/`story_rail`
    where their resolved destination is present), assert the rendered
    `href` is not `#` and resolves to the intended application route
    (`catalog:collection-detail` / `catalog:product-list?brand=...` /
    whatever `resolve_destination_item` returns) — not merely that
    *something* rendered.
15. Post-curation closure matrix for all 50 (§13) — cross-checked against
    the actual diff during implementation, not just asserted in this doc.
16. Full `apps.storefront_builder.tests` comparison against the certified
    W4A baseline (3216 tests / 30F / 2E / 4skip) — W4B-only
    failure/error identities = 0; changed historical failure reasons = 0.
17. `python manage.py check` — clean.
18. `python manage.py makemigrations --check --dry-run` — "No changes
    detected."
19. `git diff --check` — clean.

## 18. Open questions for the Product Owner

**None that block proceeding.** All four round-2 findings were resolved
from source (two rendered-template reads settled `blog_posts`/`promo_cards`
definitively; the C10 curation and the fingerprint/safety-scan contracts
were direct instructions with a clear source-backed implementation path).
