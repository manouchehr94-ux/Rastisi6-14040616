# P5-W4B — 50-Template Curation: Design / Inventory Gate

**Status:** DESIGN GATE ONLY, REPAIR ROUND 3 (FINAL). No production/test
code has been touched by this document, this repair, or this workstream
so far. Only the two design/inventory documents named in the repair
instruction were modified this round.

**Repair context:** Independent Architect review of design head
`e1071bbe6b4c2aeaef202fa34fdc36c11f55f155` returned CRITICAL:0 / IMPORTANT:3,
verdict REPAIR REQUIRED. The following are **accepted and not re-opened**:
exact-50 latest-catalog architecture; `_HISTORICAL_SPECS`
version-preservation mechanism; the full historical `LayoutPresetDefinition`
fingerprint contract; the explicit historical forbidden-payload scan; the
bounded composition-token compiler approach; the `blog_posts` rejection;
the `promo_cards` rejection; C10 activation with `harbor_imports` as its
curated side; no artificial even-distribution quota; 50 latest Ready
Templates; zero migrations; W4C frozen. This round fixes 2 new findings
plus a structural completeness requirement: (1) `image_slider` is
byte-identical to `hero_banner` and is redundant in every template that
already has a hero — removed from every assignment; (2) `trust_features`'s
default renders unverified merchant-business claims (nationwide shipping,
a specific authenticity guarantee, 24/7 support, a 7-day return policy) —
removed from every *new* W4B assignment (existing baseline usage is
untouched, out of scope); (3) a full exact-order implementation matrix is
now required and provided (§8/§9), removing all implementation-time
discretion about section position or version numbers.

**Certified starting checkpoint:** `707dd631e851bdd13173bf3950489142f3e526b1`
— re-verified unchanged at the start of this round.

**Companion evidence:** `docs/qa_evidence/storefront_design_engine/phase5/
w4b_template_curation/w4b_curation_inventory.md` §13–§15 hold the round-3
template-quality audit, the re-run 6-point eligibility check for the 3
surviving mechanisms, and the full exact-token implementation matrix this
document's §8 summarizes with identity rationale added.

---

## 1. Goal (unchanged)

Reuse EXISTING section/component families to make the 50 Ready Templates
materially and intentionally different from each other — data-level
composition curation inside `apps/storefront_builder/a8_ready_templates.py`
only.

## 2–3. Material difference / repetition finding (unchanged from rounds 1–2)

`recipe_signature()` already produces 50 pairwise-unique signatures; the
real curation target is Home-skeleton repetition. C1 (10 templates,
`hero_banner → category_grid → product_section → image_text`) remains the
largest cluster; C2 (4), C3 (3), C4 (3), and C10 (`tower_department`/
`harbor_imports`) round out the active curation scope, 21 templates total
(unchanged from round 2).

## 4. Revised material-curation principle (unchanged from round 2, restated)

Every actively curated template must satisfy: (1) coherent identity
rationale, (2) structural difference, (3) merchant-visible difference
under the shared fixture, (4) no dead primary interaction, (5) no fake
merchant content/ID, (6) no duplicated/redundant section serving a
function another section in the *same* recipe already serves. Round 3
adds no new principle — it applies principle (6) more strictly than round
2 did (see §5) and principle (5)'s spirit to a case round 2 hadn't
considered: a section whose *default* content is itself an unverified
business claim, not merely an ID.

## 5. Section eligibility — round-3 corrected (resolves IMPORTANT-1 and IMPORTANT-2)

Full source citations (both templates' complete file contents, byte for
byte) are in companion inventory §13–§14.

**`image_slider` — REJECTED (new finding).** `hero_banner.html` and
`image_slider.html` are **both, in their entirety**,
`{% include "storefront_builder/partials/hero_slider_body.html" %}` — the
identical rendered UI. Every template round 2 assigned `image_slider` to
(`premium_leather_noir`, `coastal_product`, `kamand_artisan`, `beauty_dew`,
`mirror_beauty`) already has `hero_banner`. Adding `image_slider` there is
a second instance of the exact same slider block under a different
`section_key` — disqualified as redundant, not merely "similarly behaved."
Removed from every assignment; not fixed, not redesigned, no new slider
created (per the review's explicit instruction).

**`trust_features` — REJECTED for new usage (new finding).**
`trust_features.html`'s neutral default renders 4 static, hardcoded
business claims (fast nationwide shipping; an authenticity guarantee;
24/7 support; a 7-day hassle-free return policy) — commitments a merchant
may not have actually made. Classification: VISIBLE BY DEFAULT: YES;
MERCHANT-NEUTRAL BY DEFAULT: **NO**; ELIGIBLE AS A **NEW** W4B PRIMARY
DIFFERENTIATOR: **NO**. Removed from every new assignment
(`city_classic`, `laleh_play`, `green_workshop`); the section itself is
**not** modified, and its 11 pre-existing baseline uses (`cedar_home`,
`simorgh_market`, `search_market`, `tool_finder`, `mother_utility`,
`rayan_tech`'s footer-derived `service_strip`, `tower_department`,
`harbor_imports`'s own pre-curation baseline, etc.) are untouched —
out of scope, those are certified, existing recipes.

**3 mechanisms survive, all independently re-verified against their
rendered template and the round-3 six-point test (companion inventory
§14, all pass unconditionally on checks 1–5):** `collection_tiles`,
`story_rail`, `brand_carousel`.

`faq`, `testimonials`, `video_section`, `quick_links` (round 1),
`blog_posts`, `promo_cards` (round 2), and now `image_slider`,
`trust_features`-as-new-usage (round 3) are all excluded from the final
proposal.

## 6. Distribution note (unchanged principle from round 2, restated for round 3's numbers)

No distribution quota exists or is targeted. The final mapping (§8) lands
at `collection_tiles`×7 / `brand_carousel`×7 / `story_rail`×7 across the 21
curated templates — this is the incidental result of 21 templates' own
identity-driven assignment once only 3 mechanisms remained eligible, not a
target anyone engineered. No template's assignment was chosen to balance
a count; §8 states each one's individual rationale.

## 7. Standard shared W4B QA visibility fixture — updated (drop HeroSlide/BlogPost, keep Collection/Brand/StoryRailItem)

| Fixture element | Used by | Belongs to |
|---|---|---|
| Existing demo Store's product/category set (unchanged) | `category_grid`, `product_section` baseline | QA fixture (already exists) |
| ≥1 active `MerchantCollection` | `collection_tiles` | QA fixture |
| ≥1 active `Brand` | `brand_carousel` | QA fixture |
| ≥1 active `StoryRailItem` | `story_rail` | QA fixture (same mechanism already proven for `mina_community`) |

The round-2 `HeroSlide`-for-`image_slider` fixture requirement and the
round-1 `BlogPost` requirement are both removed — neither section is used
anywhere in the final proposal, so no fixture content should exist "only
to make a bad section choice appear valid." Template DNA vs. QA fixture
split is unchanged: DNA only ever names a `section_key` + neutral default
settings (`collection_ids: []` / `brand_ids: []` = "show whatever the
Store has"); the fixture's actual Collection/Brand/StoryRailItem rows are
QA/setup data, never written into `a8_ready_templates.py`.

## 8. Final implementation matrix — resolves §3A/§3B (exact order, exact version map, per-template identity rationale)

**Placement rule:** every addition is **appended as the last entry** in
the Home composition — the same convention the catalog's own richest
existing recipes already use (`dense_marketplace` appends
`brand_carousel`→`testimonials` after its core; `ferdowsi_department`
appends `brand_carousel`→`trust_features`; `anniversary_mosaic` appends
`testimonials`→`newsletter`). No new ordering rule; no
implementation-time discretion — the exact resulting token tuple for
every key is in companion inventory §15's table. **Version map: all 21
keys are currently `"1"`; all 21 bump to `"2"`.**

| Key | Mechanism | Identity rationale | Non-redundant because | Merchant-neutral because | Interactive behavior |
|---|---|---|---|---|---|
| `premium_leather_noir` (زر) | `brand_carousel` | Luxury leather boutique showcasing the brands it carries — standard retail pattern for this vertical. | No `brand_carousel` anywhere in its current composition; distinct from `hero_banner`/`category_grid`/`product_section`/`image_text`. | Renders only the Store's own real `Brand` rows; no static copy. | Real link to `catalog:product-list?brand=slug`. |
| `artisan_grain` (دانه) | `collection_tiles` | Organic/artisan product-collection showcase. | No `collection_tiles` present; distinct rendered layout (`.pcard`/`grid g4`) from anything else in the recipe. | Renders only real `MerchantCollection` rows. | Real link to `catalog:collection-detail`. |
| `coastal_product` (موج) | `collection_tiles` | Coastal-lifestyle "resort/swim collection" showcase. | Same as above. | Same as above. | Same as above. |
| `handmade_luxe` (چرم دست) | `brand_carousel` | Handcraft-leather multi-brand boutique pattern. | Same reasoning as `premium_leather_noir`. | Same as above. | Same as above. |
| `watchmaker_round` (ساعت‌ساز) | `brand_carousel` | Multi-brand watch boutique — the standard retail pattern for this vertical. | Same reasoning. | Same as above. | Same as above. |
| `horizon_story` (افق) | `story_rail` | "Story"-named template gets a highlight rail — the strongest single nominal fit in the catalog. | No `story_rail` present; distinct circular-avatar-rail layout. | Renders only real `StoryRailItem` rows or nothing; no static copy. | `{% resolve_destination_item %}`; a safe non-link, never a placeholder, when a story has no destination. |
| `silk_editorial` (ابریشم) | `collection_tiles` | Silk collections presented as a curated tile set. | No `collection_tiles` present. | Same as artisan_grain. | Same as artisan_grain. |
| `city_classic` (شهر) | `collection_tiles` | Generalist "classic" retailer's seasonal collection showcase. | No `collection_tiles` present. | Same as above. | Same as above. |
| `kamand_artisan` (کمند) | `story_rail` | Artisan-process highlight rail. | No `story_rail` present. | Same as horizon_story. | Same as horizon_story. |
| `parnian_editorial` (پرنیان) | `story_rail` | Editorial highlight rail. | No `story_rail` present. | Same as above. | Same as above. |
| `niloufar_glass` (نیلوفر) | `collection_tiles` | Beauty product-line collection showcase. | No `collection_tiles` present. | Same as above. | Same as above. |
| `beauty_dew` (شبنم) | `story_rail` | Beauty "get the look" highlight rail. | No `story_rail` present. | Same as above. | Same as above. |
| `laleh_play` (لاله‌زار) | `brand_carousel` | Playful/floral multi-brand retailer pattern. | No `brand_carousel` present. | Same as premium_leather_noir. | Same as above. |
| `almas_luxury` (الماس) | `story_rail` | Short luxury highlight rail. | No `story_rail` present. | Same as above. | Same as above. |
| `green_workshop` (سبزه) | `brand_carousel` | Eco brand's own sustainable-partner-brand showcase; also widens the identity gap from `pine_eco` (both eco-themed — see round-1 overlap note). | No `brand_carousel` present. | Same as above. | Same as above. |
| `pine_eco` (کاج) | `collection_tiles` | Eco product-collection showcase — deliberately a *different* mechanism from `green_workshop`'s, per the overlap note. | No `collection_tiles` present. | Same as above. | Same as above. |
| `mirror_beauty` (آینه) | `story_rail` | Beauty "get the look" highlight rail. | No `story_rail` present. | Same as above. | Same as above. |
| `cedar_home` (سدر) | `collection_tiles` | Furniture/home retailers organize by "room collections" — standard pattern. | No `collection_tiles` present (existing `trust_features` at the tail is untouched/kept, per §5's scope limit). | Same as above. | Same as above. |
| `simorgh_market` (سیمرغ) | `brand_carousel` | Marketplaces conventionally feature a multi-brand carousel. | No `brand_carousel` present. | Same as above. | Same as above. |
| `rayan_tech` (رایان) | `story_rail` | Tech-highlights rail. | No `story_rail` present. | Same as above. | Same as above. |
| `harbor_imports` (بندر — "harbor/imports") | `brand_carousel` | The single strongest nominal fit in the catalog: imported goods are conventionally presented by the brands that make them. Also structurally separates C10 from `tower_department` (§9). | No `brand_carousel` present (existing `trust_features` at the tail is untouched/kept). | Same as above. | Same as above. |

## 9. C10 — kept active (resolves §6's requirement, unchanged decision from round 2)

`harbor_imports` keeps `brand_carousel`, re-verified against all 6 points
in §5/companion inventory §14: functional (real link), merchant-neutral
(no static claim), non-redundant (no `brand_carousel` in its own
composition), correctly Store-scoped, no merchant ID in DNA, and
identity-coherent (`بندر` = harbor/imports is the strongest single-section
fit in the whole catalog). `tower_department` remains unmodified. Their
Home compositions no longer share a skeleton at all (`harbor_imports`
gains a 6th section type `tower_department` doesn't have) — C10 is
materially separated.

## 10. Composition-token allowlist — final, minimal (resolves §8's "only used tokens" instruction)

**Exactly one genuinely new token is needed.** `story_rail`
(`"community_gallery"` → `"story_rail"`) and `brand_carousel`
(`"brands"` → `"brand_carousel"`) already exist in `_STATIC_SECTIONS` and
are reused directly — no new alias added for either. `image_slider` and
`trust_features` need no allowlist entry at all now (neither is used by
any new assignment; `trust_features`'s existing `"trust_features"`/
`"service_strip"` entries are untouched and unused by anything new).

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
    # W4B addition — the ONLY new token the final curation uses:
    "collection_tiles": "collection_tiles",
}
```

## 11. Versioning / historical preservation — UNCHANGED, ACCEPTED

`_SPECS` stays at exactly 50 rows (edited in place); the pre-curation row
for each of the 21 curated keys is copied verbatim into `_HISTORICAL_SPECS`
(21 frozen rows now, same count as round 2 — this round changed *which*
section each key gains, not *which* keys are curated); registered through
the same second loop, same `register_layout_preset`/
`LAYOUT_PRESET_REGISTRY`/`LAYOUT_PRESET_VERSION_REGISTRY`, `A8_READY_TEMPLATES`
built only from `_SPECS`. `layout_preset_registry.py` not touched. The
full historical `LayoutPresetDefinition` fingerprint contract
(`dataclasses.asdict` + deterministic recursive freeze + sha256, compared
against a `CERTIFIED_W4A_FINGERPRINT` recorded before any edit) and the
historical forbidden-payload safety scan (reusing
`test_recipes_contain_no_tenant_executable_or_prototype_payload`'s own walk
over the 21 `_HISTORICAL_SPECS` entries) are both unchanged from round 2 —
see that round's design text, restated in full in companion inventory §7
(fingerprint) and §12 (safety scan reference), still fully applicable
since neither depends on which section was chosen.

## 12. Post-curation closure matrix — unchanged counts from round 2

**Actively curated (21):** the 20 Tier-1 keys + `harbor_imports` — §8 (same
21 keys as round 2; only their assigned mechanism changed for 8 of them).

**Unique-skeleton, no change (16):** unchanged from round 1/2.

**`tower_department` (1):** unmodified, no longer paired with an
unresolved near-duplicate (§9).

**Shared-skeleton, left unchanged (12, 6 pairs — C5, C6, C7, C8, C9, C11):**
unchanged from round 2, ranked by real per-axis structural diff in
companion inventory §10.

Total: 21 + 16 + 1 + 12 = **50**.

## 13. New-section rule compliance (unchanged)

No new section type. The 3 sections used (`collection_tiles`,
`story_rail`, `brand_carousel`) already exist, registered, tested, and —
per the round-3 audit — confirmed non-redundant, merchant-neutral, and
functionally sound for every template they're assigned to.

## 14. Architecture / duplication / tenant impact (updated)

- **Files expected to change during implementation:**
  - `apps/storefront_builder/a8_ready_templates.py` — 21 `_RecipeSpec`
    rows edited in place (version `1`→`2`, one token appended each); a new
    `_HISTORICAL_SPECS` tuple (21 frozen rows) + one registration loop; 1
    new identity row in `_STATIC_SECTIONS` (§10).
  - `apps/storefront_builder/tests/test_a8_ready_template_catalog.py` —
    `EXPECTED_LATEST_VERSIONS` updated for the 21 keys; fingerprint +
    historical-safety-scan tests (§11).
  - `layout_preset_registry.py` **not** touched.
- **No renderer/registry/manifest/persistence change. Migrations: 0.**
- **Tenant/Store scoping:** unaffected; all 3 sections' context builders
  confirmed Store-scoped correctly.
- **Merchant data in Template DNA:** none — every default is neutral.
- **W2/W3 non-interference:** unchanged.

## 15. Architecture boundary (explicit)

| Item | Answer |
|---|---|
| Exactly 50 latest Ready Templates | YES |
| New renderer | NO |
| New Ready Template registry | NO |
| New section type | NO |
| New slider | NO |
| New Theme mechanism | NO |
| New Random Mix engine | NO |
| New tenant resolver | NO |
| New ProductCard authority | NO |
| New merchant policy subsystem | NO |
| New CMS/blog subsystem | NO |
| Merchant IDs in Template DNA | NO |
| Migrations | 0 |
| W4C | FROZEN |

## 16. Test plan (final, 21-point, matches the review's list)

1. `len(A8_READY_TEMPLATES) == 50`.
2. `len(lpr.list_ready_templates()) == 50`.
3. Explicit latest-version map for all 21 curated keys (§8: all `1`→`2`).
4. Full certified-base historical fingerprint equality for every outgoing
   curated version (companion inventory §7's contract, run and recorded).
5. Historical forbidden-payload safety scan over the 21
   `_HISTORICAL_SPECS` entries.
6. Bounded composition-token compilation — the 1 new `_STATIC_SECTIONS`
   row (§10).
7. All added sections registered and Home-allowed.
8. No merchant IDs/content in Ready Template DNA.
9. **No new false merchant business claims introduced** — explicit
   assertion that none of the 21 curated recipes' newly-appended section
   is `trust_features` (or any other static-claim section).
10. No new dead/placeholder interactions — for every curated template,
    assert the rendered primary link of its added section resolves to a
    real URL (`catalog:collection-detail` / `catalog:product-list?brand=...`
    / a resolved `story_rail` destination or a safe non-link), never `#`.
11. No newly introduced duplicate section serving the same function as an
    existing section in the same recipe — assert, per curated key, the
    appended `section_key` did not already appear in that key's
    pre-curation composition.
12. 50/50 pairwise-unique `recipe_signature()` — run and recorded.
13. Component coverage regression — no advertised component newly unused;
    none added to `A8_ADVERTISED_COMPONENTS_BY_FAMILY`.
14. All-50 candidate resolution/apply regression through canonical paths.
15. Bounded browser QA for all 21 actively curated latest versions, 3
    viewports, RTL, under the fixture (§7).
16. Latest-vs-historical visible comparison under identical fixture
    content, per curated template.
17. Exact final Home order verified against §8/companion inventory §15's
    matrix — the appended token is the *last* entry, nothing reordered.
18. Full `apps.storefront_builder.tests` regression vs. the certified W4A
    baseline (3216/30F/2E/4skip) — W4B-only failure/error identities = 0;
    changed historical failure reasons = 0.
19. `python manage.py check` — clean.
20. `python manage.py makemigrations --check --dry-run` — "No changes
    detected."
21. `git diff --check` — clean.

## 17. Open questions for the Product Owner

**None.** Both round-3 findings were settled by reading the actual
rendered `.html` files byte-for-byte; the resulting reassignment uses only
mechanisms already fully vetted in round 2 (`collection_tiles`,
`story_rail`, `brand_carousel`), and the exact-order/version-map
requirement is satisfied by the append-only placement rule and the
explicit 1→2 version map in §8/companion inventory §15.
