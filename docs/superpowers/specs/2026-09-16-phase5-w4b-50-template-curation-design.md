# P5-W4B — 50-Template Curation: Design / Inventory Gate

**Status:** DESIGN GATE ONLY, REPAIR ROUND 1. No production/test code has
been touched by this document, this repair, or this workstream so far.
Only the two design/inventory documents named in the repair instruction
were modified this round.

**Repair context:** Independent Architect review of design head
`58c2dbc0248cc82a79cb53f3d51a82839cf6ed4e` returned CRITICAL:0 / IMPORTANT:3
/ MINOR:1, verdict REPAIR REQUIRED. This revision resolves all four
findings from source — see the per-section notes below (each repaired
section states which finding it resolves). Nothing here starts production
implementation or W4C.

**Certified starting checkpoint:** `707dd631e851bdd13173bf3950489142f3e526b1`
(HEAD of `feature/phase5-design-expansion`, the merged+certified P5-W4A
checkpoint) — re-verified unchanged at the start of this repair round.

**Authoritative source for scope:** `docs/superpowers/plans/
2026-09-15-phase5-converged-completion-plan.md`, §P5-W4B (supersedes older
A8/Task 9–18 documents wherever they conflict).

**Companion evidence:** `docs/qa_evidence/storefront_design_engine/phase5/
w4b_template_curation/w4b_curation_inventory.md` — full 50-row inventory,
cluster analysis, the corrected versioning mechanism (§7), the section
render-precondition classification (§9), and the Tier-2 per-axis diff
evidence (§10). This document assumes that inventory.

---

## 1. Goal (unchanged, restated from the authoritative plan)

> Reuse EXISTING section/component families to make the 50 Ready Templates
> materially and intentionally different from each other. This is NOT a new
> design engine, NOT a new editorial subsystem, NOT a request to create more
> than 50 Ready Templates, and NOT an excuse to insert every available
> component into every template.

Primary production scope: **data-level composition/recipe curation inside
`apps/storefront_builder/a8_ready_templates.py`.** No renderer, registry, or
persistence-architecture change is proposed anywhere below.

## 2. What "material difference" means here (unchanged, source-verified)

`recipe_signature()` (`storefront_appearance/inventory.py`) hashes the 10
component-family selections (`theme` is fixed at `theme.none.v1` for all 50)
plus the normalized Home section sequence. All 50 current recipes already
produce 50 pairwise-unique signatures — the diversity test is not at risk
today. The harder, real question is repetition the signature test cannot
see: templates whose Home **skeleton** (section-type sequence, ignoring
settings) is identical to another's.

## 3. The repetition finding (unchanged)

- 32/50 templates use exactly 4 Home sections.
- The single largest cluster (**C1**, 10 templates) is *exactly*
  `hero_banner → category_grid → product_section → image_text`, with zero
  variation in section types or order: `premium_leather_noir`,
  `artisan_grain`, `coastal_product`, `handmade_luxe`, `horizon_story`,
  `silk_editorial`, `city_classic`, `kamand_artisan`, `watchmaker_round`,
  `parnian_editorial`.
- 10 further clusters of size 2–4 repeat the same pattern at smaller scale
  (companion inventory §6, C2–C11).
- 16 templates already have a unique skeleton.

## 4. Section render-precondition classification — resolves IMPORTANT-3(A)

Full source citations and the per-section table are in the companion
inventory §9. Summary: of the 9 sections available for curation, 4
(`faq`, `testimonials`, `video_section`, `quick_links` — "**Group B**")
render nothing under neutral default settings — each requires the merchant
to manually author content (Q&A pairs, quotes, a video URL, or picking an
existing Menu) before anything appears. The other 5 (`blog_posts`,
`promo_cards`, `collection_tiles`, `image_slider`, `story_rail` —
"**Group A**") are auto-sourced from real Store/platform data (the global
blog feed, the Store's own Categories/Collections, or existing
`HeroSlide`/`StoryRailItem` media records) and become visible under a
standard populated Store with **no manual per-section settings edit** —
exactly the same precondition class the catalog already accepts for
`hero_banner`/`category_grid`/`product_section` today.

## 5. Primary-differentiator rule — resolves IMPORTANT-3(B)

**A Group-B section must never be the sole reason a Ready Template is
called materially curated**, and Template DNA must stay merchant-ID-free —
so fabricating FAQ answers, testimonial quotes, a video URL, or a Menu
selection inside a Ready Template recipe to force Group-B sections
"visible" is explicitly forbidden (companion inventory §14 constraint,
Master Handoff §14).

**Consequence:** the design-gate-round-1 Tier-1 proposal used a Group-B
section as the *sole* addition for 11 of its 20 templates
(`premium_leather_noir`, `artisan_grain`, `coastal_product`, `horizon_story`,
`watchmaker_round`, `niloufar_glass`, `beauty_dew`, `almas_luxury`,
`green_workshop`, `mirror_beauty`, `rayan_tech`). **§8 below replaces every
one of those 11 assignments with a Group-A section instead** — no template
in the repaired Tier-1 relies on a Group-B section as its material
differentiator. Group-B sections are not used anywhere in this repaired
proposal; they remain available to individual merchants through the normal
R4 Inspector after Apply, same as for any of the other 41 non-curated
templates today — nothing here removes that option, curation simply does
not rely on it.

## 6. Standard shared W4B QA visibility fixture — resolves IMPORTANT-3(C)

One shared, controlled fixture — reused for every Tier-1 curated template's
before/after comparison, so the comparison is fair and nothing is
per-template special-cased:

| Fixture element | Used by | Belongs to |
|---|---|---|
| The existing demo Store's product/category set (already used by every other Ready Template QA pass — no new products/categories) | `category_grid`, `product_section` (unchanged baseline) | QA fixture (already exists) |
| ≥1 active `MerchantCollection` | `collection_tiles` | QA fixture (new — one, reused by every template that adds `collection_tiles`) |
| ≥1 published `BlogPost` (global platform feed, not Store-scoped) | `blog_posts` | QA fixture (new — the platform blog feed, reused by every template that adds `blog_posts`) |
| ≥1 `HeroSlide` scoped to the new `image_slider` section, per curated template | `image_slider` | QA fixture (same mechanism `ApplyAndRenderSmokeTests` already uses for `hero_banner` — not new infrastructure) |
| ≥1 active `StoryRailItem`, per curated template | `story_rail` | QA fixture (same mechanism already proven for `mina_community`) |

**Template DNA vs QA fixture, explicit line:** Template DNA (the
`_RecipeSpec`/`_manifest()`/`_home()` output) only ever names a
**section_key** plus neutral default settings (`collection_ids: []` =
"show whatever the Store has," `item_limit: N` = a bounded count — never a
specific Collection/Product/BlogPost ID). The fixture's actual Collection,
BlogPost, HeroSlide, and StoryRailItem *rows* are QA/setup data created for
the browser-QA pass, never written into `a8_ready_templates.py`. This
mirrors exactly how the existing catalog already treats `hero_banner`
(recipe names the section; the demo Store's own `HeroSlide` rows make it
visible) and `category_grid`/`product_section` (recipe names the section;
the demo Store's own Categories/Products make it visible).

## 7. Material-curation acceptance criterion — resolves IMPORTANT-3(D)

For every Tier-1 curated template, implementation must prove **both**:

1. **Structural recipe change** — the new version's Home composition
   differs from the old version's in intended, bounded structural DNA
   (the added `section_key` is present; `recipe_signature()` differs).
2. **Visible change** — under the standard fixture (§6), the newly curated
   latest version renders a merchant-visible structural difference from its
   own old version (the added section actually appears with real content,
   not an empty DOM node).

A section that satisfies #1 but not #2 (any Group-B section used alone)
does **not** satisfy this criterion — this is why §8 uses Group-A sections
exclusively.

## 8. Proposed curation — Tier 1, REPAIRED (20 templates, Group-A only)

Every addition below is a Group-A (auto-sourced, visible-under-fixture)
section, chosen for identity fit — not for coverage. Distribution across
the 5 Group-A sections is intentionally even (4 templates each) so no
single section type is overused; several picks differ from the original
(rejected) round specifically because the original pick was Group-B.

### Cluster C1 (10 templates)

| Key | Identity | Addition (repaired) | Why | Fixture dependency |
|---|---|---|---|---|
| `premium_leather_noir` (زر) | luxury dark leather, immersive hero | `image_slider` | Luxury/immersive identity suits a cinematic product-imagery slider (same precondition class as its own `hero_banner`). | 1 `HeroSlide` on the new section |
| `handmade_luxe` (چرم دست) | handcraft leather, editorial_split hero | `blog_posts` | "Handmade" identity → a maker's journal. | shared `BlogPost` fixture |
| `artisan_grain` (دانه) | grain/organic artisan | `collection_tiles` | Organic/artisan product collections showcase. | shared `MerchantCollection` fixture |
| `watchmaker_round` (ساعت‌ساز) | watch precision, portrait_round card | `promo_cards` | Limited-edition/collection promo cards fit a precision-watch retailer. | Store's own active Categories (already required by `category_grid`) |
| `coastal_product` (موج) | coastal lifestyle | `image_slider` | Coastal lifestyle imagery slider. | 1 `HeroSlide` on the new section |
| `horizon_story` (افق) | travel/sand editorial — "story" in the identity | `story_rail` | Strong nominal fit: a "story"-named template gets a highlight rail. | 1 `StoryRailItem` |
| `silk_editorial` (ابریشم) | silk editorial luxury | `collection_tiles` | Silk collections as a curated tile set. | shared `MerchantCollection` fixture |
| `city_classic` (شهر) | city/classic professional | `promo_cards` | Generalist city-retail seasonal promos. | Store's own active Categories |
| `kamand_artisan` (کمند) | artisan clay | `blog_posts` | Artisan process journal. | shared `BlogPost` fixture |
| `parnian_editorial` (پرنیان) | editorial cream | `story_rail` | Editorial highlight rail. | 1 `StoryRailItem` |

Group-A distribution in C1: `image_slider`×2, `blog_posts`×2,
`collection_tiles`×2, `promo_cards`×2, `story_rail`×2 — even, not
mechanical (each pick still keyed to that template's own identity).

### Cluster C2 (4 templates) — `... → newsletter`

| Key | Identity | Addition (repaired) | Why |
|---|---|---|---|
| `niloufar_glass` (نیلوفر) | beauty glass | `collection_tiles` | Beauty product-collection showcase. |
| `beauty_dew` (شبنم) | beauty dew | `image_slider` | Beauty imagery slider (tutorial-style stills). |
| `laleh_play` (لاله‌زار) | playful/floral | `promo_cards` | Seasonal/floral promo cards. |
| `almas_luxury` (الماس) | diamond luxury | `story_rail` | Short luxury highlight rail. |

### Cluster C3 (3 templates) — `... → image_text → newsletter`

| Key | Identity | Addition (repaired) | Why |
|---|---|---|---|
| `green_workshop` (سبزه) | eco/green workshop | `blog_posts` | Eco brand journal. |
| `pine_eco` (کاج) | eco (identity-overlap note below) | `collection_tiles` | Eco product-collection showcase — deliberately a *different* Group-A type from `green_workshop`, widening the gap between these two already-similar eco-identity templates. |
| `mirror_beauty` (آینه) | beauty | `image_slider` | Beauty imagery slider. |

**Identity-overlap note (unchanged from round 1, still just an
observation, not a defect):** `green_workshop` and `pine_eco` are both
literally eco-themed; distinct card styles (`standard` vs `soft_capsule`)
already separate them somewhat, and the two different Group-A additions
above widen that gap further. No key rename proposed (Master Handoff §8).

### Cluster C4 (3 templates) — `... → trust_features`

| Key | Identity | Addition (repaired) | Why |
|---|---|---|---|
| `cedar_home` (سدر) | home/furniture | `blog_posts` | Home/decor journal. |
| `simorgh_market` (سیمرغ) | general marketplace | `promo_cards` | Marketplace seasonal-deal cards. |
| `rayan_tech` (رایان) | tech | `story_rail` | Tech-highlights rail (repaired from the rejected `video_section` pick). |

**Tier 1 total: 20 templates**, C1:10 + C2:4 + C3:3 + C4:3. Final Group-A
distribution across all 20: `image_slider`×4, `blog_posts`×4,
`collection_tiles`×4, `promo_cards`×4, `story_rail`×4.

## 9. Composition-token compilation fix — resolves IMPORTANT-2

**Finding confirmed from source:** `_home()`'s only fallback for a
composition token is `_STATIC_SECTIONS[token]` (a plain dict lookup); none
of the 5 Group-A tokens above (`blog_posts`, `promo_cards`,
`collection_tiles`, `image_slider`, `story_rail` — the token literal is
identical to the target `section_key`, same convention `_STATIC_SECTIONS`
already uses for `testimonials`/`newsletter`) currently exist in
`_STATIC_SECTIONS`. Placing any of them in a new `_RecipeSpec.composition`
tuple today raises `KeyError` at import time. Round-1's design silently
assumed this compiled; it does not.

**Repair — the smallest possible extension, inside the existing canonical
recipe-compilation path, no new compiler, no per-template branching:** add
exactly the 5 identity entries this proposal actually uses to the existing
`_STATIC_SECTIONS` dict in `a8_ready_templates.py`:

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
    # W4B additions — identity mapping, same convention as the 8 rows above:
    "blog_posts": "blog_posts",
    "promo_cards": "promo_cards",
    "collection_tiles": "collection_tiles",
    "image_slider": "image_slider",
    "story_rail": "story_rail",
}
```

This is a **bounded allowlist addition**, not an open mapping: only the 5
section keys this specific proposal uses are added, exactly as the
architect's own example (`"faq" -> "faq"`) prescribed, mirroring the
pre-existing `testimonials`/`newsletter` identity-mapping rows already in
the same dict. No change to `_home()`'s dispatch logic, `_product_entry()`,
`section_registry.py`, or any other file. `faq`, `video_section`, and
`quick_links` are deliberately **not** added — they are not used anywhere
in the repaired Tier-1 proposal (§8), so extending the allowlist for them
now would be scope creep the architecture-boundary rule (§14) forbids.

**Test contract for this fix** (addresses IMPORTANT-2B): for every Tier-1
curated key, a focused test must prove that its new composition:
- compiles through `_home()` without raising (`KeyError` or otherwise);
- produces only section keys `section_registry.is_valid_section_key()`
  accepts, on a page type each is `section_registry.is_section_allowed_on_page()`-permitted
  for (`home`);
- passes `register_layout_preset`'s full import-time validation chain
  (`_validate_page_composition_shape` → per-section `validate_settings`/
  `default_settings()` → `row_service.validate_page_row_layout` →
  `_validate_ready_template_store_appearance` → `validate_store_appearance_manifest(..., require_complete=True)`)
  without raising `InvalidLayoutPresetError`;
- introduces no key in `test_a8_ready_template_catalog.py::FORBIDDEN_DATA_KEYS`
  anywhere in its compiled `LayoutPresetDefinition` (no merchant/tenant ID).

## 10. Versioning strategy, REPAIRED — resolves IMPORTANT-1

Full derivation and the exact code shape are in the companion inventory §7
(new `_HISTORICAL_SPECS` tuple + a second registration loop, both confined
to `a8_ready_templates.py`). Summary of why round 1 was wrong and what
replaces it:

**Round-1 error:** `A8_READY_TEMPLATES = tuple(_build(spec) for spec in
_SPECS)` maps `_SPECS` 1:1 with no dedup. Appending a new version row per
curated key while leaving the old row in `_SPECS` would grow `_SPECS` (and
`A8_READY_TEMPLATES`) to 70 rows for 20 curated keys — `test_a8_ready_template_catalog.py`'s
`len(A8_READY_TEMPLATES) == 50` assertion would correctly fail. `list_ready_templates()`'s
dedup-by-key does not help, because the test asserts on the raw
`A8_READY_TEMPLATES` tuple itself, not on `list_ready_templates()`.

**Repaired mechanism:** `_SPECS` stays at exactly 50 rows forever — curating
a key **edits its existing row in place** (new version number, new
composition), it never adds a row. The row's exact pre-curation field
values are copied, unedited, into a second, append-only tuple —
`_HISTORICAL_SPECS` — registered through a second loop that feeds
`register_layout_preset` (via the same `_build()` compiler) but never
feeds `A8_READY_TEMPLATES`:

```python
_HISTORICAL_SPECS = (
    # one frozen row per curated key's outgoing version — copied verbatim
    # from its old _SPECS row at curation time, never edited again.
)

for _historical_spec in _HISTORICAL_SPECS:
    register_layout_preset(_build(_historical_spec))
```

Why every constraint from the review is satisfied:

| # | Constraint | How it's satisfied |
|---|---|---|
| 1 | `A8_READY_TEMPLATES` stays exactly 50 | It is built only from `_SPECS`, which is edited-in-place, never appended, for curation. |
| 2 | `list_ready_templates()` stays exactly 50 | Same reason, plus the pre-existing max-version-wins dedup by key. |
| 3 | Every curated key gets a new numeric latest version | The in-place `_SPECS` edit bumps the version string. |
| 4 | Old exact version stays resolvable via `get_layout_preset_version` | `_HISTORICAL_SPECS`'s frozen row is registered through the same canonical call. |
| 5 | Historical versions never appear as extra catalog entries | `_HISTORICAL_SPECS` never touches `A8_READY_TEMPLATES`; its lower version number can never win `LAYOUT_PRESET_REGISTRY[key]` regardless of registration order (`register_layout_preset`'s own numeric comparison). |
| 6 | No second Ready Template registry | Same `LAYOUT_PRESET_REGISTRY`/`LAYOUT_PRESET_VERSION_REGISTRY`. |
| 7 | Canonical `register_layout_preset`/registry used | Yes, unchanged. |
| 8 | Existing historical versions preserved | The 8 pre-A8 hardcoded blocks in `layout_preset_registry.py` are untouched; this mechanism doesn't interact with them at all. |

This is a **smaller** change than literally mirroring the 8 legacy keys'
pattern in `layout_preset_registry.py` would have been (that would require
hand-transcribing each curated key's fully-compiled `PresetSectionEntry`
tuple instead of reusing `_build()`), and it stays inside the one file
named as W4B's primary production scope. `layout_preset_registry.py` is
**not** touched by this design.

**RED/GREEN contract per curated key (addresses IMPORTANT-1B):**

```python
def test_<key>_curation_preserves_history_and_promotes_latest(self):
    latest = lpr.get_layout_preset(key)
    historical = lpr.get_layout_preset_version(key, old_version)

    self.assertEqual(latest.version, new_version)
    self.assertEqual(historical.version, old_version)
    self.assertIsNot(latest, historical)
    # the old recipe's Home composition is byte-for-byte the certified
    # pre-W4B structure:
    self.assertEqual(
        tuple(e.section_key for e in historical.pages["home"]),
        <certified pre-W4B skeleton for this key, from companion inventory §5>,
    )

def test_a8_read_template_catalog_still_exactly_fifty(self):
    self.assertEqual(len(A8_READY_TEMPLATES), 50)
    self.assertEqual(len(lpr.list_ready_templates()), 50)
```

## 11. Post-curation closure matrix — resolves the Tier-2/remaining-cluster-closure requirement

No cluster below is automatically added to this W4B pass. This matrix
exists so "deferred" is an honest, measured statement, not an unmeasured
scope escape.

**Curated (20 templates, §8):** C1 (10) + C2 (4) + C3 (3) + C4 (3) — see §8
for the exact addition and rationale per template.

**Unique-skeleton, no shared cluster, no change (16 templates):**
`editorial_jewelry`, `dense_marketplace`, `warm_boutique`, `premium_leather`,
`dark_digital`, `search_market`, `playful_lifestyle`, `utility_catalog`,
`pixel_play`, `fashion_promo_catalog`, `mina_community`, `tuska_bento`,
`collection_index`, `kite_playful`, `ferdowsi_department`,
`anniversary_mosaic`. Justification: each already has a Home skeleton no
other template shares (companion inventory §6, C12–C27) — the strongest
possible non-palette/non-font distinctness this catalog can express.

**Shared-skeleton, left unchanged this pass (14 templates, 7 pairs) — ranked
honestly by how many of the 7 non-palette structural axes (header, hero,
layout, product_view, card, footer, bottom_nav) actually differ (full
per-axis breakdown: companion inventory §10):**

| Cluster | Pair | Differing axes (count) | Closure judgment |
|---|---|---|---|
| C7 | `roosta_zigzag` / `calligraphy_paper` | 7/7 — every family axis differs, plus a layout/product_view combination (`editorial_zigzag`+`featured_wall`) no other template uses at all | Materially distinct already; leaving unchanged is fully justified. |
| C9 | `aftab_price` / `charcoal_grill` | 5/7 (header, hero, card, footer, bottom_nav) | Materially distinct already; leaving unchanged is justified. |
| C8 | `literary_catalog` / `gallery_minimal` | 4/7 (header, hero, card, footer) | Distinct enough to justify no change; `gallery_minimal`'s deliberate minimalism would be undercut by adding a section, which is itself a reason to leave it alone. |
| C11 | `mist_quiet` / `night_catalog` | 4/7 (header, layout, card, footer) | Distinct enough; both are deliberately spare/quiet identities (`motion.none`) — padding either would work against its own design intent. |
| C6 | `tool_finder` / `mother_utility` | 3/7 (header, footer, bottom_nav) | Weaker but still a full chrome difference (header pattern + footer + bottom-nav all differ); acceptable to leave unchanged this pass, reasonable Tier-2 candidate if scope is later widened. |
| C5 | `street_drop` / `racer_tech` | 3/7 (hero, card, footer) | Same strength as C6; acceptable to leave unchanged this pass, reasonable Tier-2 candidate if scope is later widened. |
| **C10** | **`tower_department` / `harbor_imports`** | **2/7 (card, bottom_nav only)** | **Weakest justification in the catalog — flagged, not hidden.** These two share header, hero, layout, product_view, and footer exactly. Recommendation: this is the single strongest candidate if the Product Owner or Architect wants W4B's scope widened beyond Tier 1; this design does **not** widen scope unilaterally (the review's own instruction: "do NOT automatically expand W4B to all remaining repeated-skeleton pairs"), so it stays unchanged for this pass, honestly labeled as the weakest "unchanged" case rather than asserted as adequately distinct. |

Total accounted for: 20 (curated) + 16 (unique) + 14 (deferred pairs) = 50.

## 12. New-section rule compliance (unchanged)

No new section type is proposed. The 5 sections used in the repaired Tier 1
(`blog_posts`, `promo_cards`, `collection_tiles`, `image_slider`,
`story_rail`) already exist, are registered, tested
(`test_section_registry.py`), and auto-sourced from real Store/platform
data with no merchant/tenant ID in Template DNA. STAT and any other new
editorial primitive remain untouched/BACKLOG (Master Handoff §12).

## 13. Architecture / duplication / tenant impact (updated file list)

- **Files expected to change during implementation:**
  - `apps/storefront_builder/a8_ready_templates.py` — (a) 20 `_RecipeSpec`
    rows edited in place (version bump + new composition); (b) a new
    `_HISTORICAL_SPECS` tuple (20 frozen rows) + one new registration loop;
    (c) 5 new identity rows in `_STATIC_SECTIONS` (§9). No function
    signature changes to `_build`/`_home`/`_manifest`/`_appearance`.
  - `apps/storefront_builder/tests/test_a8_ready_template_catalog.py` —
    `EXPECTED_LATEST_VERSIONS` updated for the 20 bumped keys; new
    RED/GREEN tests per §10.
  - New focused test module (or an addition to an existing one) for the
    per-key historical-preservation + compilation contracts in §9/§10.
  - **`apps/storefront_builder/layout_preset_registry.py` is NOT changed**
    (round-1's implicit assumption that no file besides `a8_ready_templates.py`
    would need touching is now correct in substance, though the historical
    hardcoded-block idea it gestured at would have required touching this
    file — the repaired `_HISTORICAL_SPECS` mechanism does not).
- **No renderer, registry, manifest, or persistence file changes.** No new
  canonical owner introduced or duplicated (Master Handoff §6 fully
  respected).
- **Migrations:** expected **zero**.
- **Tenant/Store scoping:** unaffected — Ready Template recipes remain
  global, Store-agnostic Python data.
- **Merchant data in Template DNA:** none of the 5 Group-A sections'
  default settings reference a Product/Category/Collection/Brand/BlogPost
  ID (companion inventory §9) — consistent with Master Handoff §14.
- **W2/W3 non-interference:** `theme` stays `theme.none.v1` for all 50;
  Random Mix/Design Lab/Theme overlay untouched.

## 14. Architecture boundary (explicit, per review request)

| Item | Answer |
|---|---|
| Exactly 50 latest Ready Templates | YES (§10 proof) |
| New renderer | NO |
| New Ready Template registry | NO |
| New section type | NO |
| New Store Appearance family | NO |
| New Theme mechanism | NO |
| New Random Mix engine | NO |
| New tenant resolver | NO |
| New ProductCard path | NO |
| New merchant-data persistence inside Template DNA | NO |
| Migrations | 0 |
| W4C | FROZEN — not started |

## 15. Test plan (repaired — no predicted results, only commands to run)

1. **Exact-50 latest-catalog contract:** `len(A8_READY_TEMPLATES) == 50` and
   `len(lpr.list_ready_templates()) == 50`, run and recorded as evidence
   after the `_SPECS`/`_HISTORICAL_SPECS` change — not assumed.
2. **Historical exact-version preservation** for all 20 curated keys (§10
   RED/GREEN contract) — `get_layout_preset_version(key, old_version)` is
   not `None`, is not the same object as `get_layout_preset(key)`, and its
   Home skeleton matches the certified pre-W4B skeleton recorded in
   companion inventory §5, byte-for-byte.
3. **Composition-token compilation** for the 5 newly-used section keys
   (§9 test contract) — no `KeyError`, valid registered section keys,
   passes the full `register_layout_preset` validation chain.
4. **Registered-section / page-type validation** — `section_registry.is_valid_section_key`
   and `is_section_allowed_on_page(..., "home")` true for every added
   section.
5. **Merchant-ID-free DNA** — `test_a8_ready_template_catalog.py`'s existing
   `test_recipes_contain_no_tenant_executable_or_prototype_payload` re-run
   against the 20 curated + 20 historical entries; must stay green
   unmodified (this test already walks all of `lpr.list_ready_templates()`
   generically, no test-code change needed for it to cover the new rows).
6. **50 pairwise-unique structural signatures** —
   `apps.storefront_builder.tests.test_a8_template_diversity` run and its
   actual `len(signatures) == 50` / `len(set(signatures)) == 50` output
   recorded — **not** asserted in advance as "trivially true."
7. **Component coverage regression without coverage-gaming** —
   `test_a8_component_coverage` run; confirm no advertised component key
   becomes newly unused, and that no new component was added to
   `A8_ADVERTISED_COMPONENTS_BY_FAMILY` purely to chase a coverage number
   (none is proposed — §8 only edits Home composition, no family selection
   changes).
8. **Candidate resolution / Ready Template apply regression for all 50** —
   run whichever existing tests already cover `resolve_preset_candidate`/
   `apply_preset` against the full `list_ready_templates()` set (e.g.
   `test_preset_service`, `test_u10_ready_template_catalog::ApplyAndRenderSmokeTests`
   pattern) — confirm the 20 curated latest versions apply/preview without
   error.
9. **Bounded browser QA, Tier-1 curated templates only** (not the W4C
   all-50 matrix): 3 standard viewports, RTL, under the standard fixture
   (§6) — confirm the new section renders with real content (not an empty
   DOM node) and Header/Footer/Bottom-Nav duplication stays at 0.
10. **Visible latest-vs-historical comparison** under the *same* fixture
    (§7's acceptance criterion #2) — a screenshot or DOM assertion pair per
    curated template, old version vs new version, proving the added
    section is actually visible, not just present in the manifest.
11. **Full `storefront_builder` regression** compared against the certified
    W4A baseline evidence (`.../w4a_public_shell_convergence/
    32_full_storefront_builder_exact_head.txt` and
    `33_full_suite_exact_head_base_comparison.md`, 3216 tests / 30F / 2E /
    4skip) — any new failure/error identity is a blocker; the 30
    pre-existing failures + 2 errors must remain the same identities and
    reasons.
12. **`python manage.py check`** — clean.
13. **`python manage.py makemigrations --check --dry-run`** — "No changes
    detected."
14. **`git diff --check`** — clean.

## 16. Open questions for the Product Owner

**None that block proceeding.** All four review findings were resolved
from source in this repair. One item is surfaced for transparency, not as
a blocking question: companion inventory §10 shows `tower_department`/
`harbor_imports` (C10) is the weakest-justified "leave unchanged" pair in
the whole catalog (only 2 of 7 structural axes differ). Per the review's
own instruction not to auto-expand W4B's scope, this design leaves C10
unchanged for this pass and simply states that fact plainly rather than
asserting it is "already materially distinct" without qualification. If a
future reviewer wants C10 folded into Tier 1, that is a one-line addition
to §8 using the same Group-A methodology — not a design change.
