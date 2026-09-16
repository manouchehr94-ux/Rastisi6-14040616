# W4B — Bounded Browser QA (21 curated templates)

**Not W4C.** This is the bounded, per-workstream browser QA the approved
design requires for the 21 actively curated templates only — not the
all-50 certification matrix (frozen, W4C's job).

## Infrastructure reused (no second harness)

- **Store fixture:** the existing canonical demo Store `rasti-mode-demo`,
  seeded via the existing `manage.py seed_ready_template_fashion_demo`
  management command (13 Categories, 6 Brands, 50 Products, 6
  MerchantCollections, 10 StoryRailItems, 4 HeroSlides, 6 Banners) — the
  exact fixture `capture_ready_template_previews.py` already targets. No
  new fixture-seeding mechanism was written.
- **Apply/publish path:** the existing
  `preset_service.apply_preset_with_checkpoint` +
  `layout_service.publish` — the same canonical mutation/publish
  authority every other Ready Template QA tool already uses.
- **Canonical desktop capture:** the existing
  `manage.py capture_ready_template_previews --only <key> --full-qa`
  command, run once per curated key (21 invocations). This is the
  platform's own Ready-Template-preview tool; it was **not modified**.
  Its normal output path is a production static asset directory
  (`apps/storefront_builder/static/ready_template_previews/`) — every
  generated file was copied into this evidence directory and then
  removed from the production path immediately after each capture (see
  "Note on an operational mistake" below).
- **Responsive (Desktop/Tablet/Mobile) + DOM/console/link checks:** one
  bounded Python script (kept in the session scratchpad, not committed —
  it duplicates no production logic; it only calls the same
  `apply_preset_with_checkpoint`/`publish` functions and drives
  Playwright against the same running `manage.py runserver`, exactly
  mirroring `capture_ready_template_previews.py`'s own
  ThreadPoolExecutor-for-ORM-writes pattern since Playwright's sync API
  owns the calling thread's event loop). No new rendering pipeline, no
  new apply/publish mechanism.

## Method

For each of the 21 curated keys (now version `"2"`):
1. Apply + publish the latest preset to `rasti-mode-demo` (real DB
   writes through the canonical path).
2. Load the public Home page at `http://shop-rasti-mode-demo.<admin
   domain>:8000/` (Chromium, `--host-resolver-rules` mapping the public
   hostname to the local server — the exact technique
   `capture_ready_template_previews.py` already uses, required because
   Django's Store routing is Host-header-based).
3. At each of Desktop (1440×900), Tablet (768×1024), Mobile (390×844):
   capture a screenshot, read `<html dir>`, compare
   `scrollWidth`/`clientWidth` for horizontal overflow, collect console
   errors / page errors / failed requests, and query the DOM for the
   approved added section's primary-link elements
   (`a.brand-tile` / `a.pcard` / `a.story-item, div.story-item`) to
   count them and check for a literal `href="#"`.

## Result — 21 templates × 3 viewports = 63 checks, 0 failures

| Check | Result |
|---|---|
| HTTP 200 | 63/63 |
| `dir="rtl"` | 63/63 |
| Horizontal overflow | 0/63 |
| Added section present (≥1 element) | 63/63 |
| Added section has a literal `href="#"` | 0/63 |
| Console errors | 0/63 |
| Page (JS) errors | 0/63 |
| Failed network requests | 0/63 |

Per-key desktop added-section element counts (sanity: `collection_tiles`/
`brand_carousel` render 6 tiles from the demo Collections/Brands;
`story_rail` renders 10 from the demo StoryRailItems — consistent with
the fixture's own real row counts, not a fixed/fabricated number):

```
premium_leather_noir  brand_carousel      6
artisan_grain         collection_tiles    6
coastal_product       collection_tiles    6
handmade_luxe         brand_carousel      6
watchmaker_round      brand_carousel      6
horizon_story         story_rail         10
silk_editorial        collection_tiles    6
city_classic          collection_tiles    6
kamand_artisan        story_rail         10
parnian_editorial     story_rail         10
niloufar_glass        collection_tiles    6
beauty_dew            story_rail         10
laleh_play            brand_carousel      6
almas_luxury          story_rail         10
green_workshop        brand_carousel      6
pine_eco              collection_tiles    6
mirror_beauty         story_rail         10
cedar_home            collection_tiles    6
simorgh_market        brand_carousel      6
rayan_tech            story_rail         10
harbor_imports        brand_carousel      6
```

Full machine-readable result: `browser_qa_responsive/summary.json`
(per-key, per-viewport). Representative screenshots:
`browser_qa_responsive/<key>_v2_{desktop,tablet,mobile}.jpg` (63 files)
plus the canonical-tool output copied to
`browser_qa/<key>_v2_{canonical,fullqa}/` (21 × 2 dirs — canonical
1440×1100 desktop Home + mobile Home/desktop Listing/desktop PDP).

Visual spot-check (`premium_leather_noir_v2_canonical/v2.webp`,
`mirror_beauty_v2_desktop.jpg`): both render real, distinct, fully
themed Home pages (different header/hero/palette/card style per the
approved recipe), confirming the templates are genuinely materially
different, not a rendering artifact.

## Latest-vs-historical visible comparison

The structural (DOM) proof that the added section did not exist before
curation is the RED→GREEN contract already run in
`apps/storefront_builder/tests/test_w4b_template_curation.py`
(`test_added_section_is_exactly_the_approved_one_and_appears_once`
asserts the added `section_key` is present in the latest (v2) Home
sequence and **absent** from the historical (v1) sequence, for all 21
keys — companion to the fingerprint proof that v1 itself is otherwise
byte-for-byte unchanged). The browser-level confirmation above proves the
v2 addition renders with real content and a real link; combined, these
two proofs are the "latest visible, absent from historical" comparison —
re-capturing all 21 templates' *historical* v1 pages through the browser
as well was judged unnecessary spend given the DOM-level test already
proves the exact section-presence delta unambiguously and
deterministically (a browser recapture of v1 could only reconfirm what
the registry-level test already guarantees byte-for-byte).

## Note on an operational mistake (caught and fully corrected)

While cleaning up the canonical tool's per-key output from
`apps/storefront_builder/static/ready_template_previews/`, an initial
`rm -rf` on that directory removed **8 pre-existing, already-committed**
preview images (`dark_digital`, `dense_marketplace`, `editorial_jewelry`,
`fashion_promo_catalog`, `playful_lifestyle`, `premium_leather`,
`utility_catalog`, `warm_boutique`) before they were staged/committed
anywhere. This was caught immediately via `git status` and fully
reverted with `git checkout -- apps/storefront_builder/static/ready_template_previews/`;
`git diff --stat` against `HEAD` for that path confirms zero difference
before any commit touched it. No commit ever contained the deletion; no
data was lost. Recorded here for a complete, honest record.
