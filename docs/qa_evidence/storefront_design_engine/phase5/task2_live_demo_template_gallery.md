# Phase 5, Task 2 — Live Onboarding Demo Template Preview: Evidence

Status: **CLOSED**
Starting HEAD: `8f504639e8dd0ff3b8886863eedafaca9e4ef61c` (Task 1 corrective, closed)
Branch: `feature/phase5-design-expansion`

## 1. What was built

`storefront_template_live_preview(request, key)` — a new, staff-authenticated,
read-only Django view that renders a REAL, fully composed preview of any one
of the 50 curated Ready Templates, against the canonical `rasti-mode-demo`
Demo Store, on demand (never on Gallery page load).

- Route: `dashboard:storefront-builder-template-live-preview` →
  `/admin-portal/storefront-builder/templates/<key>/preview/` (`apps/dashboard/urls.py`).
- Gallery link: a "مشاهده‌ی قالب (زنده)" button added to every one of the 50
  template cards in `template_gallery.html`, opening the live preview in a
  new tab (`target="_blank"`) — the static SVG/screenshot thumbnail grid
  remains the fast-browse default; nothing renders live until clicked.
- Template: `storefront_builder/ready_template_live_preview.html` (new file)
  — a demo-data banner, then the candidate's own header/footer/mobile-nav
  variant includes and section rows, reusing `base.html` and the existing
  `render_rows.html`/`responsive_section_wrapper.html` partials.

## 2. Reused owners (no second anything)

| Concern | Owner reused | New code |
|---|---|---|
| Ready Template registry | `layout_preset_registry.get_layout_preset()` / `LayoutPresetDefinition.is_ready_template` | none |
| Demo Store | `Store.objects.get(slug="rasti-mode-demo")` (`RASTI_MODE_DEMO_STORE_SLUG` constant) | none — fixed constant, never request-derived |
| Candidate resolution | `preset_service.resolve_preset_candidate()` (Task 1) | none |
| Section rendering | `render_service.build_candidate_render_items()` (Task 1) | none |
| Row/container-settings composition | `render_service.group_items_into_rows()` (existing, pure) | `build_candidate_container_rows()` — thin zip adapter, no new grouping logic |
| Store Appearance resolution | `candidate.store_appearance` / `store_appearance_global_renderer_template()` | none |
| Global color/font CSS tokens | `apps.core.context_processors` (via `request.storefront_appearance_version`) | `_ReadyTemplateCandidateAppearanceVersion` — same idiom as the pre-existing `_CandidateAppearanceVersion` |
| Draft access | `layout_service.get_or_create_draft()` (idempotent, pre-existing) | none — read-only |
| Row rendering | `storefront_builder/partials/render_rows.html` (shared, `use_container_layout=False` path) | extended (backward-compatible, see §4) to actually apply `row.container_settings` when present |

No new renderer, no new Demo Store, no new candidate resolver, no candidate
persistence, no copying of Demo data into any other Store.

## 3. Non-mutation proof

`DemoDraftUnchangedTests` (in the new test file) snapshots every
Draft-identifying field (`edit_revision`, `appearance_config`,
`header_config`, `footer_config`, `template_provenance`,
`template_baseline_snapshot`, all `StorefrontSection` rows, Container count,
`StorefrontLayoutVersion` count, edit-history count, published-version id)
before and after:
- a single live-preview request, and
- a sequence of live-preview requests across 3 different templates
  (`editorial_jewelry`, `dense_marketplace`, `warm_boutique`).

Both assert byte-identical snapshots. `InvalidTemplateKeyTests` additionally
proves an unknown/invalid key is fully non-mutating (404 before any write
path is reachable).

## 4. Fixes applied during this task (both found by review/QA, both closed)

### 4.1 CRITICAL (browser QA) — hero/banner/story_rail rendered empty

**Root cause:** `_scoped_hero_slides` / `_scoped_banners` / `_story_rail_context`
(`render_service.py`) only matched content scoped to the exact (impossible,
for an unsaved candidate section) `pk`, or to genuinely store-wide
(`section=None`) content. The Demo Store's real seeded Hero/Banner/StoryRail
rows are ALL scoped to the one real section the currently-applied baseline
(`fashion_promo_catalog`) created — so previewing any *other* template found
nothing via either path.

**Fix:** added a third fallback tier (only reached when `section.pk is None`,
i.e. only for candidate previews — real saved-section rendering is
unchanged): match the store's own content for the SAME `section_key`,
scoped to that store's non-archived (`DRAFT`/`PUBLISHED`) layout versions.

**Proof:** `HeroBannerStoryRailContentIsNotEmptyTests` — a real seeded Hero
slide title (`"کالکشن پاییز و زمستان Rasti Mode"`) appears in
`dense_marketplace`'s live preview; `mina_community`'s resolved `story_rail`
section's `context["story_items"]` is non-empty (unit-level, via
`build_candidate_render_items` directly, immune to the "category name
appears elsewhere on the page too" ambiguity). Re-verified live in-browser
(see §6).

### 4.2 IMPORTANT (browser QA) — header category nav showed "no categories"

**Root cause:** `apps.catalog.context_processors.nav_categories` resolves
`resolve_store_for_service(request)` — the ambient admin-host Store (the
logged-in merchant's own store), never the Demo Store being previewed.

**Fix:** the view now computes `nav_categories` scoped to `demo_store` and
passes it explicitly in its own context dict — which overrides the
context-processor's same-keyed value for this render only (standard,
verified Django precedence: a view's own context wins over a context
processor for the same key; confirmed both by direct reproduction against
Django's real `render()`/`make_context()` path and by the passing test
below).

**Proof:** `NavCategoriesReflectDemoStoreNotAmbientAdminStoreTests` — logs in
as staff on a *different* store (`akhlaghi`) specifically to catch this bug;
asserts every category in `response.context["nav_categories"]` belongs to
`demo_store`, never to the ambient admin store. Re-verified live in-browser
(see §6).

### 4.3 CRITICAL (independent review) — container settings silently discarded

**Root cause:** `build_candidate_container_rows()` (Task 1/2) attached
`row["container_settings"]` to each row, but the shared
`render_rows.html` partial's `use_container_layout=False` branch — the path
this feature's template uses, since candidate sections are never persisted
as real `StorefrontContainer`/`Cell` rows — never read that key. Container
gap/background/alignment settings were computed but never reached the
rendered HTML, for any value.

**Fix:** `render_rows.html`'s non-container branch now reads
`row.container_settings` and, only when present and non-default, applies
gap/background-color/alignment as inline styles on the row wrapper
(`.rsec-row` for multi-item rows; a new `.rsec-row-single` wrapper for the
single-item rows every one of today's 50 Ready Templates actually produces,
since none of them use `row_key`/`row_span` grouping). A matching CSS rule
was added for the one registered background pattern (`commerce-doodle`),
mirroring the existing `.rcontainer[...]` rule. Guarded entirely behind
`row.container_settings` being present — `group_items_into_rows()` (every
other caller: real Draft/Published rendering, the htmx cart partial) never
sets this key, so all other callers are provably byte-identical to before
this change.

**Proof:** `ContainerSettingsReachRenderedOutputTests` (3 tests) — renders
the real `render_rows.html` partial with real candidate items and a
synthetic, deliberately non-default `container_settings` (`gap=37`,
`background_color="#1a2b3c"`, `vertical_align="center"`), asserting those
exact values appear in the rendered HTML, for both the multi-item and
single-item row shapes; a fourth test proves a row without the
`container_settings` key (the real shape every other caller produces)
renders with none of that markup — the fix is additive, not a behavior
change for existing callers.

### 4.4 IMPORTANT (independent review) — non-Ready preset key crashed instead of 404ing

**Root cause:** `layout_preset_registry.get_layout_preset(key)` resolves over
the ENTIRE preset registry (50 Ready Templates + ~5 other registered
presets, e.g. `clean_minimal`), not only the Ready Templates. A real,
registered-but-non-Ready key has `is_ready_template=False` and, after
`resolve_preset_candidate`, `store_appearance=None` — which crashed
`store_appearance_global_renderer_template` with an unhandled
`AttributeError` instead of failing closed.

**Fix:** the key-resolution check is now
`if preset is None or not preset.is_ready_template: raise Http404(...)` —
placed before any Draft/Store access, so it stays fail-closed with no
wasted queries.

**Proof:** `InvalidTemplateKeyTests.test_registered_but_non_ready_template_key_is_404_not_a_crash`
— confirms `clean_minimal.is_ready_template is False`, then asserts the
route now 404s (not crashes) and leaves the Demo Draft untouched.

## 5. Test results

### 5.1 Task 2's own suite

`apps.storefront_builder.tests.test_task2_live_demo_template_preview` —
**20/20 passed** (final run, after all fixes above).

Categories covered (per the task's required RED list): real rendered
output; two distinct templates produce different output (including a real
Store-Appearance-component-level divergence, `badge`); real Demo Store
context (category/brand names); non-mutation (single request + multi-
template sequence); invalid-key fail-closed (both unknown key and
registered-but-non-Ready key); Gallery still lists exactly 50 templates and
still links to the new route; existing static-thumbnail path untouched;
hero/banner/story-rail content non-empty; nav-categories reflect the Demo
Store; container settings reach the rendered output (multi-item, single-
item, and the no-op-for-other-callers negative control).

### 5.2 Required regression suites

Run together after all fixes (`test_preset_candidate_preview`,
`test_a8_ready_template_catalog`, `test_a8_ready_template_contracts`,
`test_u8_template_gallery`, `test_render_service`, `test_acceptance_batch3`,
`test_ready_template_real_previews`):

```
Ran 185 tests in 42.995s
FAILED (failures=1, skipped=4)
```

The single failure, `test_header_footer_variant_labels_shown_for_updated_preset`
(`test_u8_template_gallery.py`), is **pre-existing and unrelated to this
task's diff** — independently reproduced against an isolated `git worktree`
checked out at the starting SHA `8f504639e8dd0ff3b8886863eedafaca9e4ef61c`
(before any Task 2 code existed): it fails identically there. Re-confirmed a
second time by the independent reviewer running it directly against this
task's own working tree. Not a Task 2 regression.

### 5.3 Platform checks

- `python manage.py check` → "System check identified no issues (0 silenced)."
- `python manage.py makemigrations --check --dry-run` → "No changes detected"
- `git diff --check` → clean (no whitespace errors)

## 6. Browser QA

Performed by `rastisi-ui-ux-design-lead` (chrome-devtools MCP, real dev
server, real `apply_golden_reference_storefront` seed), in two passes.

### 6.1 First pass (full checklist)

- Gallery at 3 viewports (1440×900 / 768×1024 / 390×844): loads, all 50
  cards render, every card has the live-preview link, no horizontal
  overflow at any viewport, RTL structurally confirmed (not mirrored-LTR),
  no console errors beyond one pre-existing, unrelated accessibility hint.
- 5 representative Ready Templates chosen for material DNA difference —
  `editorial_jewelry`, `dense_marketplace`, `playful_lifestyle`,
  `dark_digital`, `mina_community` (the last specifically for its
  `story_rail` section, exercising the Task-1 fix) — each checked at all 3
  viewports: 200 status, demo-data banner present and correctly labeled, no
  horizontal overflow, zero broken images, footer renders, mobile bottom
  nav present only at 390×844 and structurally distinct per template, no
  console errors.
- **Visual distinctness verdict: yes** — header shape, category-grid
  presentation, section composition/count, card style, footer structure,
  and mobile bottom nav all differ in kind (not just palette) across the
  five templates. Concrete evidence in
  `docs/qa_evidence/storefront_design_engine/phase5/task2_live_preview_browser_qa.md`.
- This pass found the two CRITICAL/IMPORTANT findings fixed in §4.1/§4.2.

### 6.2 Second pass (focused re-verification of the two fixes)

- `dense_marketplace` hero_banner: real content renders — headline
  "کالکشن پاییز و زمستان Rasti Mode", subtext, CTA button, real product
  images, slider rotates through multiple real slides.
- `mina_community` story_rail: 10 distinct real story items with real
  images and labels (کتانی رانینگ، کفش زنانه، کیف دوشی، …), 200 status,
  zero console errors.
- `dense_marketplace` header mega-menu: real categories with real
  subcategories and working links, no "no categories registered" text
  anywhere.
- `editorial_jewelry` header nav: real category names present directly.
- Regression sanity: Gallery + all 3 re-checked preview pages still 200, no
  horizontal overflow, RTL intact, no new console errors.

**Both findings: PASS**, verified live in the rendered UI, not just at the
test/data level.

The independent code-review pass in §4.3/§4.4 found no visual/browser-level
consequence in the two later fixes for any of today's 50 real Ready
Templates (all use only default, all-default-value `container_settings`,
and the non-Ready-preset 404 fix has no reachable path from the Gallery UI)
— so a third browser QA round was judged unnecessary; the fixes were
instead proven directly against the real, shared production template file
via `django.template.loader.render_to_string` (§4.3) and the real view
(§4.4), both passing.

## 7. Architecture gate verdicts

| Gate | Verdict | Evidence |
|---|---|---|
| ONE READY TEMPLATE REGISTRY | PASS | `layout_preset_registry` is the only registry consulted; the IMPORTANT fix narrows resolution to `is_ready_template=True` entries of that same registry, introduces no second registry. |
| ONE DEMO STORE | PASS | `RASTI_MODE_DEMO_STORE_SLUG = "rasti-mode-demo"` is a fixed server-side constant, matching every other Demo Store consumer's own literal; never request-derived. |
| ONE CANDIDATE RESOLVER | PASS | Only `preset_service.resolve_preset_candidate()` (Task 1) is called; no new resolution logic. |
| ONE SHARED RENDERER | PASS | Only `render_service.build_candidate_render_items()`/`group_items_into_rows()`/`render_rows.html` are used; `build_candidate_container_rows()` is a thin adapter over the existing grouping function, not a new renderer. |
| ONE STORE APPEARANCE RESOLVER | PASS | `candidate.store_appearance` (Task 1) is used as-is; `store_appearance_global_renderer_template()` is the existing shared resolver. |
| NO CANDIDATE PERSISTENCE | PASS | No `.save()` on any candidate section/container; `DemoDraftUnchangedTests` snapshot-proves this across single and multi-request sequences. |
| NO DEMO DATA COPY | PASS | No writes to any other Store; the view only reads `demo_store`'s own data. |
| NO SECOND PREVIEW ENGINE | PASS | Reuses `render_rows.html` (extended, backward-compatibly, not forked) — the exact partial `preview.html` already falls back to for non-Container Drafts. |
| DEMO DRAFT UNCHANGED | PASS | §3, §5.1 (`DemoDraftUnchangedTests`). |
| STATIC THUMBNAILS ARE NON-AUTHORITATIVE | PASS | Gallery still renders all 50 cards via the pre-existing thumbnail mechanism, untouched (`ExistingStaticThumbnailPathStillUsableTests`); live preview is opt-in, on-click only, never rendered on Gallery page load. |

## 8. Independent review

Two rounds (a first full-diff review found the two findings in §4.3/§4.4; a
second, scoped review verified both fixes). Final verdict:
**CRITICAL=0, IMPORTANT=0** (2 MINOR/cosmetic notes only, both acknowledged,
neither requiring further action — a stylistic nit about one `{% if %}`'s
nesting position, harmless because Django resolves the guarded variable to
falsy anyway; and a cosmetic inline-style-vs-CSS-class inconsistency
matching the existing `.rcontainer` pattern's own established method for
that exact property).

## 9. Known limitations

- `content_width` (`standard`/`full`) in `container_settings` has no visual
  effect anywhere in the platform today — including in the REAL, persisted
  Container/Cell renderer (`render_containers.html`), not just this
  candidate path. Pre-existing gap, out of scope for this task.
- None of the 50 curated A8 Ready Templates currently set non-default
  `container_settings` or use `row_key`/`row_span` grouping — so the §4.3
  fix, while structurally necessary and now verified correct, has no
  visible effect on today's 50 templates' actual rendered output; it
  prevents a latent, silent bug for any future Ready Template (or
  `container_settings` value) that does set one.
- Task 3 (per the original directive) will address Merchant-scoped
  preview data separately — out of scope here by design.

## 10. Files changed

```
M  apps/dashboard/urls.py
M  apps/storefront_builder/services/render_service.py
M  apps/storefront_builder/static/css/storefront_builder.css
M  apps/storefront_builder/templates/dashboard/storefront_builder/template_gallery.html
M  apps/storefront_builder/templates/storefront_builder/partials/render_rows.html
M  apps/storefront_builder/views.py
?? apps/storefront_builder/templates/storefront_builder/ready_template_live_preview.html
?? apps/storefront_builder/tests/test_task2_live_demo_template_preview.py
?? docs/qa_evidence/storefront_design_engine/phase5/task2_live_preview_browser_qa.md
?? docs/qa_evidence/storefront_design_engine/phase5/task2_live_demo_template_gallery.md (this file)
```
