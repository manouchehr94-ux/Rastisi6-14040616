# Phase 5 — Rasti Mode Demo Store Inventory

Date: 2026-09-11. Read-only audit; no mutating commands were executed to produce this document (all
counts below come from reading fixture source code and existing regression-test assertions, not from
running the seed).

## 1. Does the canonical demo store exist?

**Yes.** `rasti-mode-demo` (Store name "Rasti Mode Demo") is a mature, idempotent, tenant-scoped fixture
— not a stub or partial build.

## 2. Owner

| Layer | Owner |
|---|---|
| Store/tenant + core catalog/content seed | `apps/stores/management/commands/seed_ready_template_fashion_demo.py` (1075 lines), `STORE_SLUG = "rasti-mode-demo"` |
| Apply+Publish orchestration ("Golden Reference") | `apps/stores/management/commands/apply_golden_reference_storefront.py` → `apps/storefront_builder/services/golden_reference_service.py` — applies the real registered `fashion_promo_catalog` baseline through the canonical preset/appearance/publish contracts, no parallel renderer |
| Curated visual refresh (real photography overlay, product images untouched) | `apps/stores/management/commands/refresh_rasti_mode_demo_visuals.py`, driven by `apps/stores/demo_assets/rasti_mode_demo/curated/manifest.json` |
| Demo asset pipeline (raw photo → processed webp) | `apps/stores/demo_assets/rasti_mode_demo/scripts/select_and_process_media.py`, `build_inventory.py` |

The fixture is idempotent and tenant-isolated (only ever touches the `rasti-mode-demo` store), and
never reads/serves `raw_user_catalog/` directly per its own module docstring.

## 3. Actual counts (verified by reading fixture source + existing tests, not by running the seed)

| Item | Actual count | Where verified |
|---|---|---|
| Products | 50 | `PRODUCT_MATRIX` has 50 rows, `assert len(PRODUCT_MATRIX) == 50` (`seed_ready_template_fashion_demo.py:186-251`); test asserts `Product.objects.count() == 50` |
| Categories | 10 leaf categories under 3 root groups | `CATEGORY_NAMES` (10 entries, `:125-136`); test `leaves.count() == 10`; 5 products per leaf |
| Brands | 6 | `BRAND_NAMES` (6 entries, `:109`) — deliberately fictional names, since raw source photos showed real unlicensed trademarks |
| Product images | 150 | 3 images × 50 products (`:802-814`); test `ProductImage.objects.count() == 150`; independently re-asserted by the media-pipeline test (`test_exactly_150_final_webp_files_all_physically_exist`) |
| Variants | 206, across 41 products | Computed from `PRODUCT_MATRIX`: 40 apparel/footwear products (color×size) + 1 multi-color bag `FSH-049` (color-only, takes the variant path even though bags are normally variant-free) = 41 products; Σ(colors×sizes) = 206. Test corroborates the per-product formula |
| Collections | 6 | `COLLECTIONS` list, 6 literal entries (`:153-160`) — "جدیدترین‌ها"، "پرفروش‌ها"، "تخفیف‌های منتخب"، "انتخاب فصل"، "کفش و کتانی"، "کیف و اکسسوری" |
| Hero items | 4 | `_seed_hero_slides`, 4 entries (`:878-907`); test `HeroSlide.objects.count() == 4` |
| Banners | 6 | `_seed_banners`, 6 entries (`:939-946`) |
| Story items | 10 | `_seed_story_rail`, one per category (10 entries, `:974-998`); test `items.count() == 10` |

## 4. Comparison against the Onboarding Charter's stated targets

Charter targets (`docs/superpowers/specs/2026-09-11-phase5-onboarding-demo-contextual-editor-charter.md`,
§5): 50 products, 10 categories, 6 brands, 150 product images, 206 variants across 41 products, 6
collections, 4 hero items, 6 banners, 10 story items.

**All nine targets MATCH exactly.** This is strong evidence the fixture was deliberately built to hit
these numbers — the numbers describe an already-implemented fixture, not an aspirational target (see
§6).

## 5. Origin of the charter's target numbers

Traced to `docs/superpowers/specs/2026-09-01-storefront-design-engine-50-templates-design.md`, §15
"Canonical Template Demo Store" (lines 288-309), which states the same counts as **fact about the
existing seed**, not as a design proposal. Every number holds up under direct source-code audit.

## 6. Representative states

| State | Covered? | Evidence |
|---|---|---|
| Sale pricing | **Yes** | 22 of 50 products have a `sale_price` (test asserts `discount_percent__gt=0` count == 22) |
| Out-of-stock | **Yes** | 10 products `OUT_OF_STOCK`, plus a distinct `PARTIAL_VARIANT_STOCK` state (10 more products, zeroing only a subset of variants) — a third, more nuanced state beyond binary in/out of stock |
| Long Persian text / names | **Not deliberately covered** — GAP | Product titles are uniform, moderate length (longest ~32 chars); `_description_for()` generates one formulaic templated sentence per product; no deliberate overflow/wrapping stress case |
| Missing-media / placeholder states | **Not covered** — GAP | Every product unconditionally gets exactly 3 processed images; no product/Hero/Banner/Story item is deliberately left without media. Directly relevant to Onboarding Charter §20's required "no image → standard placeholder" empty state, which this fixture does not itself demonstrate |

## 7. QA / real-environment evidence

- **Unit-test level**: several `TestCase` suites run the real seed commands against Django's test
  database, asserting exact row counts, idempotency (re-run produces no duplicates), image file
  integrity/hashes, and owner-login readiness. Strong code-level evidence, but not evidence of a
  persistent/staging/production deployment.
- **`docs/qa_evidence/` coverage**: only one hit across the entire tree —
  `docs/qa_evidence/storefront_appearance_convergence/phase4/phase4_architecture_audit.md:67`, which
  confirms the store/service exist and that the Golden Reference work landed on HEAD (via git ancestry),
  but is not a browser/screenshot QA artifact and does not itself re-derive the counts.
- **No browser/screenshot QA evidence exists** specifically confirming a real, running deployment of
  `rasti-mode-demo` (e.g. no visual regression captures, no manual sign-off doc). The separate Ready
  Template preview screenshots (`apps/storefront_builder/static/ready_template_previews/`) are captured
  *against* this store by `capture_ready_template_previews.py`, but that artifact is not itself
  qualitative QA evidence of the store's own health.

## 8. Overall readiness classification

**EXISTS & REUSE.** The `rasti-mode-demo` fixture is not a stub — it is a mature, idempotent,
tenant-isolated, test-covered pipeline (seed → Golden Reference Apply+Publish → curated visual refresh)
whose every numeric claim in the Onboarding Charter is verified correct by reading the actual source.
**Phase 5 should reuse this fixture as-is, not rebuild it.**

### Specific gaps to close (repair-expansion, not rebuild)

1. No deliberate long-Persian-text stress product/name/description.
2. No deliberate missing-media/placeholder-rendering product or content item — needed for Charter §20's
   empty-media UI state.
3. No dedicated real-environment QA evidence file for this store beyond one architecture-audit table
   row confirming code/git existence. If Phase 5 needs a signed-off "seeded and visually verified in a
   live/staging environment" artifact, one should be produced (responsive screenshots at
   1440×900/768×1024/390×844 per Charter §18).
4. Minor test-suite looseness: the seed command's own tests under-assert two counts it actually
   guarantees (`collections.count() >= 4` instead of `== 6`, `banners.count() > 0` instead of `== 6`) —
   worth tightening so a future regression (e.g. someone trimming banners) would be caught.

These are additive fixture enhancements, not a rebuild.
