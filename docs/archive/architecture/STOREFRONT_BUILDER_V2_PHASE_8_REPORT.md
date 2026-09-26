# Storefront Builder V2 — Phase 8 Final Report

Status: **IMPLEMENTATION_COMPLETE / TARGETED_RUNTIME_VERIFIED / BROWSER_VERIFIED
/ DESIGN_FREEDOM_PROVEN / OWNER_HEAVY_GATE_PENDING**

Phase 8 is **not** declared closed. The Owner Heavy Gate remains required
per the kickoff instructions.

Companion documents (read alongside this report):
`STOREFRONT_BUILDER_V2_PHASE_8_FIDELITY_AUDIT.md`,
`STOREFRONT_BUILDER_V2_PHASE_8_GAP_MATRIX.md`,
`STOREFRONT_BUILDER_V2_PHASE_8_IMPLEMENTATION_PLAN.md`,
`STOREFRONT_BUILDER_V2_PHASE_8_DESIGN_FREEDOM_PROOF.md`.

## The 15 required questions

**1. Can a non-programmer design a storefront without code?**
Yes, for the P0 scope this phase closed. A merchant can pick a palette, an
appearance preset, compose header/footer from a fixed block menu, add/
remove/reorder/duplicate/hide sections from a labeled library, edit each
section's content/data-source/card/layout/responsive settings through
selects/checkboxes/pickers, and publish — all through Persian-labeled forms
with no JSON, IDs, class names, or code shown anywhere in the merchant path.
The three demo stores in the design-freedom proof were built exactly this
way, by driving the real UI.

**2. Which design operations are available in the production UI?**
Palette selection (independent of everything else); appearance advanced
settings (font, radius, button radius/style, density, motion, type scale,
site content width, grid density, card shadow, card hover, hero style);
Layout Preset quick-start; header composition (6 toggles + up to 6 ordered
extra blocks: phone/social/CTA/spacer); footer composition (9 toggles + up
to 4 ordered extra blocks: custom-text/link/social); full section
library add/remove/reorder/duplicate/hide, now also reachable from an
inline canvas toolbar (P0-6), not only the sidebar; per-section settings
covering content, data source, card appearance (image ratio, brand/price/
badge/wishlist/quick-add visibility, border, quick-add reveal mode),
per-section layout (content width, height), and responsive device
visibility/columns where applicable; real tenant-scoped pickers for
product/category/brand/collection/menu references (P0-1 closed the last raw-
ID gap); Draft/Publish/Rollback.

**3. Does the production Builder match the prototype interaction model?**
Substantially, with one acknowledged structural gap. The canvas is the real
Draft rendered by the same engine as the public site (not a mock), sections
are directly clickable in-canvas with a visible selected state, and — new
this phase (P0-6) — sections now carry an inline floating toolbar (up/down/
duplicate/hide/delete) directly on the canvas element, matching the
prototype's "contextual section controls" intent. The one place the
production Builder still differs from the prototype's persistent 4-column
layout (bar/library/canvas/inspector all visible at once) is that the
Inspector remains a slide-over drawer rather than a permanently-docked 4th
column — a real, deliberate architectural difference (Gap Matrix row 1),
not fixed this phase because it is a larger layout-restructuring change
with no functional gap behind it (every Inspector control that exists is
fully reachable and usable; it just opens as an overlay instead of sitting
permanently docked).

**4. What remains different from the prototype and why?**
(a) Inspector-as-drawer vs. Inspector-as-permanent-column — see Q3.
(b) Page switching is a full navigation, not a live client-side swap — a
deliberate, documented choice from an earlier phase, not revisited this
phase since it carries no merchant-facing functional gap.
(c) Header/footer per-block styling (background/border/shadow/alignment/
width-mode) and independent mobile block arrangement were not built — the
kickoff's own block list was implemented (phone/social/CTA/spacer for
header; custom-text/link/social for footer), but the deeper per-block style
axes were judged P1/P2, not P0, and were not implemented this phase (see
Q13/Q14).

**5. Are Header/Footer genuinely composable?**
Yes, materially more than at Phase 8 start. Before this phase, header/
footer were flat toggle dictionaries with a fixed DOM order (Gap Matrix rows
23/27: `UI_MISSING`). P0-3/P0-4 added a real ordered block list — up to 6
header blocks (phone/social/CTA/spacer) and 4 footer blocks (custom-text/
link/social), reorderable, addable, removable, through a repeater UI, server-
validated (`ShellBlockError`, max counts, safe-URL validation on CTA/link
URLs). All three demo stores used materially different header/footer block
compositions (design-freedom proof table). What remains open: per-block
visual styling and independent mobile-only block arrangement (documented gap,
not built this phase — see Q13).

**6. Are all six pages visually configurable?**
Yes, unchanged from the Phase 8A audit's finding — this was already
`COMPLETE` for five of six pages (Home, Product Detail, Collection, Cart,
and Listing/Search sharing one composition by design, judged
`NOT_REQUIRED` to separate) before Phase 8 began, and nothing in Phase 8's
P0/P1 work regressed it. Phase 8's own new capabilities (card settings,
layout width/height, quick-add reveal) apply to whichever pages render
card-aware/layout-aware section types, so page composition freedom is, if
anything, now finer-grained than before.

**7. Is product-card presentation configurable enough?**
Yes, for the P0 scope. Before Phase 8, product-card fields were entirely
hardcoded (Gap Matrix rows 42-46: `NOT_IMPLEMENTED`/`PARTIAL`/dead code).
P0-2 added a real per-section `card` settings block (show/hide brand, price,
badge, wishlist, quick-add; border toggle; image ratio: square/portrait/
landscape) wired into 9 product-listing section types, plus expanded the
existing column-count control from 2 to 8 of those same types. P1 added a
working secondary-image crossfade (previously dead CSS/UI with zero effect —
found and fixed) and a 3-way quick-add reveal mode (hover-slide/hover-fade/
always). All of this was exercised differently across the three demo
stores. What remains open (documented, not blockers): per-section spacing
and a fully independent per-section overlay/shadow style beyond the current
site-wide card shadow/hover axes.

**8. Is responsive editing understandable?**
Yes for what exists, with one real gap found and fixed this phase, and one
pre-existing gap left open. The existing device-visibility model (hide-on-
tablet/hide-on-mobile checkboxes per component) uses plain Persian labels,
not breakpoint numbers. This phase's own new header/footer extra-blocks
feature, however, shipped with no mobile-width handling at all, and building
the real demo stores through the actual UI is what caught it: a header with
extra blocks plus the existing icon set genuinely overflowed the page at a
390px viewport. Fixed with a simple, understandable rule (phone/social/CTA
blocks hide below 480px; the primary cart/wishlist/account/menu icons never
do) and re-verified zero horizontal overflow on all three stores' mobile
homepages. Left open: independent mobile-only block *order* (not just
visibility) for header/footer, and per-device columns for the 6 product-
section types that still don't have it (Gap Matrix row 17, unchanged by
Phase 8 beyond the ratio-of-types P0-2 already improved elsewhere).

**9. What happened to the separate legacy Template concept?**
Retired from the merchant-facing UI (P0-7). The audit (Gap Matrix row 58)
found Template overlapping 6 of its 11 fields with controls the Advanced
panel already edited directly, with no independent identity of its own, and
capable of silently discarding a merchant's manual customization if applied
after the fact. The standalone "قالب فروشگاه" hub card and its whole
gallery/preview/apply flow were removed from `appearance_panel.html` and
`editor.html`. The 5 fields that were genuinely structural and not
duplicated elsewhere (content width, grid density, card shadow, card hover,
hero style) were promoted to direct, independent Advanced-panel controls.
`template_slug` itself still exists in the schema, purely as an internal
fallback source for stores that never set an explicit value for one of
those 5 fields (`config.get(key) or template.<field>`) — verified via two
new regression tests that an explicit merchant override always wins and a
store that never touches the field keeps its historical value; zero
migration was needed. The merchant's mental model is now exactly the three
concepts the kickoff asked for: Preset, Palette, Design/Appearance.

**10. Can three radically different stores be built using one engine?**
Yes — see `STOREFRONT_BUILDER_V2_PHASE_8_DESIGN_FREEDOM_PROOF.md` for the
full evidence. Three stores across three catalogs/verticals (fashion,
stock-clearance, generic marketplace) were built with materially different
palette, content width, grid density, card shadow/hover, hero style, header/
footer composition, card presentation, and home-page section count/rhythm
(6 vs. 27 vs. 7 sections) — all through one shared codebase, one shared
template set, one shared CSS bundle, zero store-specific branches.

**11. Were all design differences created via merchant-facing UI?**
Yes. Every palette/appearance/header/footer/section-settings change across
all three stores was a real Playwright-driven browser session performing
actual form fills, selects and submits against the production
`/admin-portal/storefront-builder/...` endpoints — the same URLs, forms and
CSRF-protected POSTs a human merchant would use. Shell access was used only
for infrastructure outside "design": seeding each store's product/category/
brand catalog data via existing seed commands
(`seed_rastisi_fashion_demo`, `seed_shop`), resetting two pre-existing test
accounts' passwords so they could be logged into, and adding one missing
`StoreDomain` row for a store that had no public route configured before
this phase. None of these touch `StorefrontSection.settings`,
`appearance_config`, `header_config`, or `footer_config` — full accounting
in the design-freedom proof's "Honest caveats" section.

**12. Were any new Families/renderers created? Answer must be NO.**
**No.** Phase 7 retired the Family architecture completely and Phase 8 did
not reintroduce it in any form — no new per-store template file, no
`family_slug`, no `if store == X` / `if preset_key == X` renderer branch, no
second builder implementation, no CSS keyed by store slug or preset key. All
three demo stores share every template, every CSS file, and every Python
code path; grep of the diff confirms zero store-specific or demo-specific
conditional logic anywhere in the changes made this phase.

**13. What visual gaps still remain?**
- Inspector is a slide-over drawer, not a permanently-docked 4th workspace
  column (Q3/Q4).
- Header/footer per-block visual styling (background/border/shadow/
  alignment/width-mode) and independent mobile-only block *order* were not
  built — only block *presence/type/order-on-all-devices* is composable.
- Footer still has no dedicated address/standalone-phone/standalone-email/
  second-menu block *types* — `custom_text`/`link`/`social` can approximate
  some of these (a merchant can hand-type an address into a custom-text
  block) but there is no purpose-built picker for them.
- Per-section spacing remains site-wide only (the `density` field), no
  per-section override.
- Per-device product-grid columns exist for the 8 product-listing types
  that got card settings in P0-2, but true per-device column *values*
  (distinct desktop/tablet/mobile counts) are still real+visual for only
  `product_section`/`multi_banner` and stored-but-inert for a few more
  (Gap Matrix row 17 — not touched by Phase 8's P0 slices, since none of
  P0-1 through P0-7 targeted that specific row).
- No mobile-specific alternate media (Gap Matrix row 50) — not touched.
- Sticky PDP purchase panel, mobile bottom navigation, hover/focus cart
  preview, PDP social share, PDP FAQ (P1 candidates 3-6) were not
  implemented this phase — time was allocated to the mandatory P0 closure
  and the three-store proof first, per the kickoff's explicit priority rule;
  only P1 candidates 1 (secondary-image crossfade) and 2 (quick-add reveal
  modes) were implemented.

**14. Which remaining gaps are P1/P2 rather than blockers?**
All of them. None of the items in Q13 block a merchant from designing and
publishing a materially different storefront today — every one of the three
demo stores was built successfully without needing any of them. They are
genuine backlog: per-block header/footer styling and independent-mobile-
order are natural P1 candidates (bounded, additive, same block-list
architecture P0-3/P0-4 already established); footer address/phone/email
block types and per-device grid columns for the remaining section types are
P1; a permanently-docked Inspector column, per-section spacing override, and
mobile-specific media are larger P2 investments the kickoff itself
classified as future work, not this phase's scope.

**15. Is the V2 product ready for a merchant usability/polish phase?**
Yes, with the above list as its input backlog. The core no-code design-
freedom claim is proven end-to-end — real merchant flows, real published
stores, zero fabricated evidence — and the remaining gaps are additive
refinements to an architecture that already supports them cleanly (the same
wrapper-composition pattern used for card/layout settings extends
naturally to the open header/footer/spacing items), not structural
rework.

## What changed this phase (commit-level summary)

Phase 8A (audit, no code): fidelity audit, gap matrix, implementation plan.

P0-1: real brand/collection pickers on the section media form (closing the
last raw-numeric-ID gap) + a second-layer tenant-ownership guard on
`DestinationMixin`.

P0-2: real per-section product-card settings block (9 section types),
column-count parity expansion (2→8 types), removal of confirmed-dead
`card_mode` field.

P0-5: per-section content-width/height layout controls (5 section types).

P0-3/P0-4: composable header (phone/social/CTA/spacer, ≤6 blocks) and
footer (custom-text/link/social, ≤4 blocks) extra-block system.

P1: product-card secondary-image crossfade (found and fixed dead wiring)
and quick-add reveal modes (hover-slide/hover-fade/always).

P0-7: legacy Template concept retired from the merchant UI; 5 genuinely
structural fields promoted to direct Advanced-panel controls; independently
discovered and fixed a bug where `card_image_crossfade`/`card_image_zoom`
were silently never persisted regardless of merchant input.

P0-6: inline canvas section toolbar (up/down/duplicate/hide/delete
directly on the rendered section). Building this surfaced and fixed a real,
previously-latent bug: `storefrontEditor()`'s `init()` method was being
invoked twice per page load (Alpine's automatic `init()` convention plus a
redundant explicit `x-init="init()"` on the same element) — harmless for
the pre-existing idempotent message handlers, but visibly wrong for the new
non-idempotent commands (double-POST duplicate, `htmx:swapError` console
error). Fixed by removing the redundant `x-init` attribute.

Design-freedom proof: three demo stores built via the real Builder UI;
discovered and fixed a genuine mobile header-overflow bug in the process
(header extra blocks + existing icon set at 390px).

## Tests run this phase

- `apps.storefront_builder` full suite: 824 tests, `OK (skipped=1)`
  (re-run clean after every P0/P1 slice and again after the final CSS fix).
- `apps.storefront_builder` + `apps.catalog` + `apps.cart` combined: 1704
  tests, `OK (skipped=1)` (final combined run after the last fix).
- `apps.catalog` + `apps.cart` alone: 877 tests, `OK`.
- Targeted new-test suites per slice (destination ownership, card settings,
  layout settings, header/footer extra blocks, appearance structural
  fields, canvas toolbar exposure/non-exposure): all passing, all newly
  added this phase, none weakening or removing existing coverage.
- `manage.py check`: 0 issues, run after every slice.
- `manage.py makemigrations --check --dry-run`: no changes detected —
  **zero migrations this phase**, confirmed after every slice.

## Tests not run

The full `apps.stores` suite was not re-run this phase — the kickoff
explicitly flagged its known pre-existing 18-failure baseline
(production-hardcoded `*.rastisi.ir` host expectations vs. local
`*.rastisi.localhost` DEBUG settings, already present at the pre-Phase-7 SHA)
as unrelated and not to be mixed into Phase 8 unless domain/host
infrastructure was touched. Phase 8 touched no domain/host code, so this
was correctly left to the owner's authoritative Heavy Gate run. The wider
platform-level 3000+ test suite (dashboard, portal, etc. beyond
storefront_builder/catalog/cart) was likewise not re-run this phase, per
the kickoff's explicit test-execution policy ("do not waste runtime on
repeated 3000+ test suites... a medium storefront_builder regression run is
appropriate after major Builder changes... the owner will perform the
authoritative final heavy gate").

## Browser QA evidence

- Builder: opened, selected Home, clicked sections directly in canvas
  (selection highlight confirmed), edited settings via the Inspector drawer
  and watched the canvas update, added/duplicated/reordered/hid/deleted
  sections via both the sidebar and the new inline canvas toolbar, edited
  Header and Footer (including the new block repeaters), applied a Layout
  Preset, changed Palette independently, made a manual Advanced-panel
  change after Preset application (verified it stuck), toggled Desktop/
  Mobile canvas modes, published, and verified the public site changed only
  after Publish (not before) — across all three demo stores, not just one
  QA sandbox.
- Public sites: full-page desktop screenshots and 390px mobile screenshots
  of all three published homepages, zero horizontal overflow (verified
  numerically via `document.documentElement.scrollWidth` vs. viewport
  width, not just visual inspection), zero genuine JavaScript console
  errors (the only console noise observed was pre-existing missing-media
  404s on one store's product thumbnails, unrelated to any Phase 8 code).

## Known remaining environment observations (not Phase 8 code defects)

- `kianstock-qa` has ~200 missing product-thumbnail media files on disk
  (pre-existing, likely ephemeral-storage loss from an earlier session).
- The `apps.stores` 18-failure baseline described above.

## Migrations

None. Every new field added this phase (`card` settings block, `layout`
settings block, header/footer `extra_blocks`, the 5 promoted structural
appearance fields, `quick_add_reveal`) lives inside existing JSON/JSONField
columns (`StorefrontSection.settings`, `appearance_config`, `header_config`,
`footer_config`) with validator-level defaults, confirmed via
`makemigrations --check --dry-run` after every slice.

## Owner-local authoritative Heavy Gate commands

```
git fetch origin claude/family-visual-fidelity-fix
git log --oneline origin/claude/family-visual-fidelity-fix -20
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test apps.storefront_builder --verbosity 1
python manage.py test apps.catalog apps.cart --verbosity 1
python manage.py test apps.stores --verbosity 1   # known pre-existing 18-failure baseline, see above
```

## Final handoff

Status: **IMPLEMENTATION_COMPLETE / TARGETED_RUNTIME_VERIFIED /
BROWSER_VERIFIED / DESIGN_FREEDOM_PROVEN / OWNER_HEAVY_GATE_PENDING**.
Phase 8 is not declared closed. A `git push` attempt and, on the expected
403, a verified git bundle follow this report as the last step of this
session's work.
