# P5-W4B — 50-Template Curation: Design / Inventory Gate

**Status:** DESIGN GATE ONLY. No production recipe has been edited by this
document or by this workstream so far. This is the required first step
before any implementation, per the Master Handoff's W4B kickoff instructions.

**Certified starting checkpoint:** `707dd631e851bdd13173bf3950489142f3e526b1`
(HEAD of `feature/phase5-design-expansion`, the merged+certified P5-W4A
checkpoint). Independently verified in this session: local clone was
fast-forwarded from a stale `e28b563` snapshot to `origin/feature/
phase5-design-expansion` and the resulting `HEAD` SHA matches exactly.

**Authoritative source for scope:** `docs/superpowers/plans/
2026-09-15-phase5-converged-completion-plan.md`, §P5-W4B (supersedes the
older A8/Task 9–18 documents wherever they conflict — no old scope revived
here). Cross-checked against `docs/qa_evidence/storefront_design_engine/
phase5/phase5_convergence_audit.md` §11/§13 (no additional requirement
found there beyond the converged plan).

**Companion evidence:** `docs/qa_evidence/storefront_design_engine/phase5/
w4b_template_curation/w4b_curation_inventory.md` — the full 50-row
source-measured inventory, section-usage tables, and cluster analysis this
proposal is built on. This document assumes that inventory and focuses on
the *decisions* and the *bounded proposal*.

---

## 1. Goal (restated from the authoritative plan, not reinterpreted)

> Reuse EXISTING section/component families to make the 50 Ready Templates
> materially and intentionally different from each other. This is NOT a new
> design engine, NOT a new editorial subsystem, NOT a request to create more
> than 50 Ready Templates, and NOT an excuse to insert every available
> component into every template.

Primary production scope: **data-level composition/recipe curation inside
`apps/storefront_builder/a8_ready_templates.py`.** No renderer, registry, or
persistence-architecture change is in scope, and none is proposed below.

## 2. What "material difference" means here (source-verified, not re-litigated)

`apps/storefront_builder/storefront_appearance/inventory.py::recipe_signature`
already ignores palette/font and hashes: the 10 component-family selections
(header/hero/layout/product_view/card/badge/motion/footer/bottom_nav —
`theme` is fixed at `theme.none.v1` for all 50 per P5-W2 and contributes
nothing to differentiation) **plus** the normalized Home section sequence
(section_key, settings, row placement). All 50 current recipes already
produce 50 pairwise-unique signatures (re-verified from source in the
companion inventory, §1) — **the diversity test is not at risk today.**

The Design Gate's job is a different, harder question the test cannot ask:
*which templates are so structurally close to each other that a merchant
comparing them would see the "same template with different colors,"* even
though their signatures technically differ. The inventory's cluster
analysis (§5–§6 of the companion doc) answers this by grouping templates on
their raw Home **skeleton** (the sequence of section *types*, ignoring
settings) — the axis the plan explicitly names as one of the "meaningful
axes" (§9 of the Master Handoff: "Home section types," "Home section
order").

## 3. The repetition finding

- 32 of 50 templates (64%) use exactly 4 Home sections.
- The dominant skeleton `hero_banner → category_grid → product_section` (or
  `catalog_product_wall`) `→ [one trailing section]` covers the overwhelming
  majority of the catalog.
- The single largest cluster (**C1**, 10 templates — 20% of the entire
  catalog) is *exactly* `hero_banner → category_grid → product_section →
  image_text`, with **no variation whatsoever** in section types or order:
  `premium_leather_noir`, `artisan_grain`, `coastal_product`,
  `handmade_luxe`, `horizon_story`, `silk_editorial`, `city_classic`,
  `kamand_artisan`, `watchmaker_round`, `parnian_editorial`.
- 10 more clusters of size 2–4 repeat the same pattern at a smaller scale
  (companion inventory §6, C2–C11 — 24 further templates).
- 16 templates already have a unique skeleton and need no structural change.

This — not the zero-usage sections list on its own — is the real curation
target. The zero-usage sections (`faq`, `video_section`, `blog_posts`,
`promo_cards`, `quick_links`, `collection_tiles`, `image_slider`,
re-confirmed still at 0 from current source, companion inventory §2) are the
**material** curation uses to break these clusters apart, but only where a
section genuinely fits a template's own identity — never mechanically, and
never to chase a coverage number (Master Handoff §11, explicit).

## 4. Proposed curation — Tier 1 (primary, do in W4B implementation)

For every template below, exactly **one** existing, already-registered,
merchant-content-driven section is added (or, where noted, swaps a section)
based on that template's own `label_fa`/header/hero/card identity — not
picked at random and not picked to hit a coverage target. Every listed
section already exists in `section_registry.py`, is merchant-editable with
neutral defaults, and carries no merchant/tenant ID (companion inventory
§2). Ordering and exact default copy/settings are implementation-phase TDD
detail, not fixed by this design doc.

### Cluster C1 (10 templates) — highest priority

| Key | Identity read from source | Proposed addition | Why it is a genuine fit, not filler |
|---|---|---|---|
| `premium_leather_noir` (زر) | luxury dark leather, immersive hero, `luxury_dark` card, black/gold palette | `video_section` | Luxury leather goods conventionally sell through a short brand/craft film; the template's own `luxury_dark`+`immersive` identity already leans cinematic. |
| `handmade_luxe` (چرم دست) | handcraft leather, editorial_split hero, `luxury_dark` card | `blog_posts` | "Handmade" identity — a maker's journal is the natural differentiator from `premium_leather_noir`'s film-led luxury. |
| `artisan_grain` (دانه) | grain/organic artisan, typographic hero, `editorial_minimal` card | `faq` | Artisan/organic goods carry real sourcing/care questions; `faq` is a direct, non-fabricated fit. |
| `watchmaker_round` (ساعت‌ساز) | watch precision, product_focus hero, `portrait_round` card | `faq` | Watches: warranty/water-resistance/movement questions are a standard real-world section for this vertical — reused deliberately (see note below). |
| `coastal_product` (موج) | coastal lifestyle, product_focus hero, `standard` card | `testimonials` | Lifestyle-goods identity leans on social proof more than the others in this cluster. |
| `horizon_story` (افق) | travel/sand editorial, side_offer_slider hero | `quick_links` | "Story"/destination-led identity fits quick destination/category shortcuts. |
| `silk_editorial` (ابریشم) | silk editorial luxury, immersive hero, `editorial_minimal` card | `collection_tiles` | Silk collections are naturally presented as a curated tile set, distinct from the plain product grid the whole cluster otherwise shares. |
| `city_classic` (شهر) | city/classic navy professional, editorial_split hero | `promo_cards` | Generalist city-retail identity is the most natural fit for seasonal promo cards in this cluster. |
| `kamand_artisan` (کمند) | artisan clay, editorial_split hero, `editorial_minimal` card | `image_slider` | Artisan-process imagery (distinct from the single static `image_text` block every C1 template already has) — a slider suits a process/gallery narrative. |
| `parnian_editorial` (پرنیان) | editorial cream, immersive hero, `shelf_editorial` card | `story_rail` | Editorial-cream identity suits a short highlight rail (currently used once, by `mina_community`) more than a second content block. |

Reuse note: `faq` is deliberately reused for both `artisan_grain` (sourcing)
and `watchmaker_round` (warranty) — two genuinely different real-world
reasons to show an FAQ, not the same reason applied twice. This is
curation, not coverage-gaming (Master Handoff §11): only 7 zero-usage
sections exist for a 10-template cluster, so some reuse across *different*
templates for *different* stated reasons is expected and acceptable; what
is forbidden is adding a section to a template for no stated reason.

### Cluster C2 (4 templates) — `... → newsletter`

| Key | Identity | Addition | Why |
|---|---|---|---|
| `niloufar_glass` (نیلوفر) | beauty glass, rose | `testimonials` (before newsletter) | Beauty verticals lean heavily on reviews. |
| `beauty_dew` (شبنم) | beauty dew, magenta | `video_section` | Beauty tutorial/demo video is a standard vertical fit. |
| `laleh_play` (لاله‌زار) | playful/floral | `collection_tiles` | Seasonal/floral collection showcase fits the playful identity. |
| `almas_luxury` (الماس) | diamond luxury, ice-cyan | `faq` | Jewelry care/certification FAQ — a strong, real fit (distinct reason from the C1 `faq` reuses above). |

### Cluster C3 (3 templates) — `... → image_text → newsletter`

| Key | Identity | Addition | Why |
|---|---|---|---|
| `green_workshop` (سبزه) | eco/green workshop | `testimonials` | Eco-brand social proof. |
| `pine_eco` (کاج) | eco (near-identical identity to `green_workshop` — flagged below) | `collection_tiles` | Differentiates from `green_workshop` via a collection showcase instead of reviews. |
| `mirror_beauty` (آینه) | beauty, magenta | `video_section` | Beauty tutorial fit (same genuine reason as `beauty_dew`, different template). |

**Identity-overlap note (not a version/architecture issue, a naming/content
observation for the implementer):** `green_workshop` and `pine_eco` are both
literally eco-themed (سبزه/"greenery" and کاج/"pine") with the same 5-section
skeleton and a similar palette family (`sage`/`olive`-adjacent). Distinct
card styles (`standard` vs `soft_capsule`) already separate them somewhat;
the additions above widen that gap. No key rename is proposed — Master
Handoff §8 forbids casual renames of existing semantic keys, and this is
squarely a "could be strengthened," not a "must fix," item.

### Cluster C4 (3 templates) — `... → trust_features`

| Key | Identity | Addition | Why |
|---|---|---|---|
| `cedar_home` (سدر) | home/furniture, forest | `blog_posts` | Home/decor journal content is a standard vertical fit. |
| `simorgh_market` (سیمرغ) | general marketplace | `promo_cards` | Marketplace seasonal-deal cards. |
| `rayan_tech` (رایان) | tech | `video_section` | Product-demo video is a standard tech-vertical fit. |

**Tier 1 total: 20 templates** (C1: 10, C2: 4, C3: 3, C4: 3).

## 5. Tier 2 (secondary, reviewed but recommended to defer within this W4B pass)

The seven remaining size-2 clusters (14 templates, companion inventory §6,
C5–C11) were individually reviewed. Recommendation: leave Tier 2 **out of
this W4B implementation pass** and revisit only if the Product Owner wants
W4B's scope widened, because several of these pairs are already
legitimately differentiated by something the skeleton-only view can't see
(a distinct `layout`/`product_view` combination, or a deliberately spare
identity where adding a section would work against the template's own
design intent):

| Cluster | Keys | Disposition | Why |
|---|---|---|---|
| C5 | `street_drop`, `racer_tech` | Optional CHANGE | `street_drop` (street/apparel drop) → `promo_cards` would fit; `racer_tech` (racing/tech) → `video_section` (race footage) would fit. Neither is load-bearing for W4B's bounded goal; safe to defer. |
| C6 | `tool_finder`, `mother_utility` | Optional CHANGE | `tool_finder` → `faq` (tool spec/usage questions) is a strong fit if pursued later. |
| C7 | `roosta_zigzag`, `calligraphy_paper` | **NO CHANGE recommended** | `roosta_zigzag` already carries a unique `layout.editorial_zigzag.v1` + `product_view.featured_wall.v1` combination (each used by only 1–2 other templates) — its skeleton match with `calligraphy_paper` is the weakest signal of "too close" in the whole list. |
| C8 | `literary_catalog`, `gallery_minimal` | **NO CHANGE recommended for `gallery_minimal`; optional for `literary_catalog`** | `literary_catalog` (کتابخانه = "library") → `blog_posts` would be an unusually strong nominal fit if pursued later. `gallery_minimal`'s minimalism is its stated identity — adding a section would undercut the very thing that template is for. |
| C9 | `aftab_price`, `charcoal_grill` | Optional CHANGE | Both are already sale/price-driven with `product_section` doubled; low priority. |
| C10 | `tower_department`, `harbor_imports` | **NO CHANGE recommended** | Both already carry a richer 5-section composition with distinct card styles (`marketplace_price` vs `shipping_label`) — the weakest "too close" candidates after C7. |
| C11 | `mist_quiet`, `night_catalog` | **NO CHANGE recommended** | Both are deliberately spare/quiet identities (`motion.none`, minimal footers) — same reasoning as `gallery_minimal`: padding a "quiet" template contradicts its own design intent. |

## 6. No change (16 templates, companion inventory §6 C12–C27)

`editorial_jewelry`, `dense_marketplace`, `warm_boutique`, `premium_leather`,
`dark_digital`, `search_market`, `playful_lifestyle`, `utility_catalog`,
`pixel_play`, `fashion_promo_catalog`, `mina_community`, `tuska_bento`,
`collection_index`, `kite_playful`, `ferdowsi_department`,
`anniversary_mosaic` — each already has a **unique** Home skeleton (no other
template shares it), so no structural change is proposed. This includes the
5 richest/most bespoke recipes already in the catalog (`dense_marketplace`,
`editorial_jewelry`, `ferdowsi_department`, `anniversary_mosaic`,
`fashion_promo_catalog`), which should stay untouched as the catalog's
existing high bar for distinctiveness.

## 7. Versioning strategy (decided from source, not a Product Owner question)

Full mechanism detail is in the companion inventory §7. Summary: **every
curated key gets a NEW `_RecipeSpec` row in `_SPECS` at the next integer
version; the existing row is left byte-for-byte unchanged.**
`register_layout_preset`'s existing max-version-wins comparison
automatically promotes the new row to `list_ready_templates()` /
`get_layout_preset(key)`, while `get_layout_preset_version(key, old_version)`
keeps resolving the untouched old row — exactly mirroring the existing,
already-proven pattern for the 8 pre-A8 legacy keys (hardcoded historical
blocks in `layout_preset_registry.py`). This requires zero new registry
code. `test_a8_ready_template_catalog.py::EXPECTED_LATEST_VERSIONS` (and any
other version-literal test fixture) is updated in the same commit — routine
maintenance, already done historically when A8 bumped 5 keys.

This resolves Master Handoff §8 in full from source; there is no unresolved
Product Owner decision here.

## 8. New-section rule compliance

No new section type is proposed. All 7 sections used above
(`faq`, `video_section`, `blog_posts`, `promo_cards`, `quick_links`,
`collection_tiles`, `image_slider`) already exist, registered, tested
(`test_section_registry.py` has dedicated settings tests for each), and
merchant-content-driven with neutral defaults. STAT and any other new
editorial primitive remain untouched/BACKLOG, per Master Handoff §12 — not
needed for any of the above.

## 9. Architecture / duplication / tenant impact

- **Files expected to change during implementation:**
  `apps/storefront_builder/a8_ready_templates.py` (new `_RecipeSpec` rows
  only — no function signature changes), plus the version-literal test
  fixtures in `apps/storefront_builder/tests/test_a8_ready_template_catalog.py`
  (`EXPECTED_LATEST_VERSIONS`) and any assertion in
  `test_a8_ready_template_contracts.py` / `test_a8_template_diversity.py` /
  `test_a8_component_coverage.py` that hardcodes a specific recipe's
  composition (none currently do, based on the read of those files — to be
  re-confirmed against the actual diff during implementation).
- **No renderer, registry, manifest, or persistence file changes.** No new
  canonical owner is introduced or duplicated (Master Handoff §6 list is
  fully respected — this workstream touches only `a8_ready_templates.py`
  data).
- **Migrations:** expected **zero** — recipes are pure Python data, never
  persisted as new model fields.
- **Tenant/Store scoping:** unaffected — Ready Template recipes are global,
  Store-agnostic Python data (no Store FK, no per-tenant branch); nothing
  proposed here reads or writes Store-scoped state.
- **Merchant data in Template DNA:** none of the proposed section additions
  reference a Product/Category/Collection/Brand ID — every default is the
  section type's own neutral `default_settings()` (companion inventory §2),
  consistent with Master Handoff §14.
- **W2/W3 non-interference:** `theme` selection stays `theme.none.v1` for
  every recipe (untouched); Random Mix/Design Lab and the Theme overlay are
  not touched by this workstream.

## 10. Test plan (for implementation phase — not run yet)

1. **RED:** for each Tier-1 curated key, a focused test asserting the new
   version's Home composition contains the proposed new section_key (and
   that the old version, unchanged, still resolves via
   `get_layout_preset_version(key, old_version)`).
2. **GREEN:** add the new `_RecipeSpec` rows; re-run.
3. **Regression — exact focused set:**
   `apps.storefront_builder.tests.test_a8_ready_template_catalog`,
   `test_a8_ready_template_contracts`, `test_a8_template_diversity`,
   `test_a8_component_coverage`, `test_u10_ready_template_catalog`,
   `test_layout_preset_registry`, `test_preset_service`.
4. **Diversity invariant:** `len(signatures) == 50` and
   `len(set(signatures)) == 50` must still hold after the version bumps
   (trivially true — the curated compositions are, by construction, more
   different from their old versions, and old versions stay out of
   `list_ready_templates()`).
5. **Full storefront_builder suite** compared against the certified W4A
   baseline evidence (`docs/qa_evidence/storefront_design_engine/phase5/
   w4a_public_shell_convergence/32_full_storefront_builder_exact_head.txt`
   and `33_full_suite_exact_head_base_comparison.md`) — any new
   failure/error identity is a blocker; the pre-existing 30 failures + 2
   errors must remain the same identities/reasons.
6. **`python manage.py check`**, **`makemigrations --check --dry-run`**
   (expect "No changes detected"), **`git diff --check`**.
7. **Bounded browser QA** (not the W4C all-50 matrix): the Tier-1 curated
   templates only, at the 3 standard viewports, RTL, confirming the new
   section renders correctly within each template's shell and that
   Header/Footer/Bottom-Nav duplication is still 0. Full all-50
   certification remains W4C's job, run only after W4B merges.

## 11. Open questions for the Product Owner

**None.** Every decision this Design Gate needed (versioning mechanism,
new-section approval, scope boundary, sequencing) was resolvable from source
and the authoritative plan, per the interaction rule in the Master Handoff.
If, during implementation, source reality contradicts something recorded
here (e.g. a hidden test hardcodes an exact old composition for a Tier-1
key), that is exactly the kind of discovery that would come back to the
Product Owner — none was found during this Design Gate.
