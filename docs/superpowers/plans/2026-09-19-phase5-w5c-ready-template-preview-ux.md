# P5-W5C — Ready Template Preview UX

## Product goal

Improve the merchant's PRE-APPLY Ready Template browsing experience: turn
the Gallery's two existing "مشاهده..." links (which today force a new
browser tab) into an in-page, large Preview dialog with Desktop/Tablet/
Mobile presentation and a Merchant/Demo data-source toggle — without
creating any second preview route, renderer, or Apply path.

## Existing authority (source-verified, all pre-existing, unmodified by W5C)

1. **`storefront_template_gallery()`** (`apps/storefront_builder/views.py:2246`)
   — already resolves the merchant Store via `_resolve_store(request)` and
   already calls `layout_service.get_or_create_draft(store, user=...)`
   unconditionally before rendering. Every card already carries
   `preset`, `is_current`, `would_replace_existing_content`,
   `palette_swatch`, thumbnail fields, header/footer variant labels.
   Iterates `layout_preset_registry.list_ready_templates()` — confirmed by
   direct execution to return **50** presets (`is_ready_template=True`),
   not the "8" a stale in-repo comment/docstring from an earlier batch
   still says — the registry function itself, not that comment, is the
   authority W5C's tests derive the expected set from.
2. **`storefront_template_live_preview(request, key)`** (`views.py:2338`)
   — the ONE canonical live-preview route. `@staff_required
   @permission_required(STOREFRONT_LAYOUT_MANAGE)`. Default: the fixed
   `RASTI_MODE_DEMO_STORE_SLUG = "rasti-mode-demo"` Store (never
   request-controlled). `?data=merchant`: resolves the Store via the SAME
   `_resolve_store(request)` tenant authority as every other view — no
   store_id/tenant_id/slug ever read from query input. Merchant mode uses
   `layout_service.get_existing_draft(preview_store)` (not
   get-or-create) and fails closed (404) if no Draft exists yet — in
   practice a Draft always exists by the time a merchant reaches the
   Gallery, since the Gallery view itself already created one. Resolves a
   transient `preset_service.resolve_preset_candidate(...)` and renders it
   through the exact same shared renderer (`build_candidate_render_items`,
   `build_candidate_container_rows`, `store_appearance_global_renderer_template`
   for header/footer/mobile-bottom-nav) as every other candidate-rendering
   path in this codebase (R4 Design Lab, R4 restore/industry-apply
   preview). Nothing is persisted; no `preset_service.apply_preset()` call
   exists anywhere in this view.
3. **URL**: `path("storefront-builder/templates/<slug:key>/preview/", ...,
   name="storefront-builder-template-live-preview")`
   (`apps/dashboard/urls.py:286`). W5C reuses this exact URL name via
   `{% url %}` for both Demo (`?` no param) and Merchant (`?data=merchant`)
   modes — never a client-side-guessed URL pattern.
4. **`ready_template_live_preview.html`** — the canonical rendered preview
   document. Already renders a banner distinguishing the two data modes
   verbatim in Persian ("اطلاعات فروشگاه شما" for merchant,
   "داده‌های نمایشیِ Rasti Mode Demo" for demo) plus the template's own
   `label_fa` — this is the exact text W5C's browser QA asserts against
   for "which data mode is this iframe showing," with zero template
   changes needed.
5. **`template_gallery.html`** (current state) — each card already renders
   both preview links via `{% url 'dashboard:storefront-builder-template-live-preview' key=preset.key %}`
   (Demo) and the same URL `+ '?data=merchant'` (Merchant), both currently
   `target="_blank"`; the screenshot thumbnail is wrapped in a separate
   `<a target="_blank">` to the raw screenshot image URL (not the live
   preview); the Apply `<form>` posts to
   `{% url 'dashboard:storefront-builder-apply-preset' %}` with the
   existing `confirm()` dialog gated on `card.would_replace_existing_content`;
   the current-template state renders as a disabled "در حال استفاده"
   button plus a "قالبِ فعلی" badge.
6. **`template_preview_service.resolve_real_screenshot()` /
   `resolve_gallery_thumbnail()`** — the card thumbnail authority
   (real screenshot when valid, fresh zero-I/O SVG fallback when stale/
   missing). W5C does not touch this service, the capture pipeline
   (`capture_ready_template_previews`), or any Ready Template recipe.
7. **R4's device-switcher presentation contract** (`r4_editor.js` lines
   ~1680-1735, `r4/editor.html` lines ~212-221) — the established pattern
   this codebase already uses for "one iframe, presentation-only Desktop/
   Tablet/Mobile switching": fixed pixel widths via
   `data-desktop-viewport-width="1200"` / `data-tablet-viewport-width=
   "768"` / `data-mobile-viewport-width="390"` on the iframe element,
   `currentDevice` held in an in-memory closure variable only (never
   persisted), `setDevice()` sets the canvas's `data-r4-device` attribute
   and each button's `aria-pressed`, and `syncPreviewViewport()` sets the
   iframe's CSS `width`/`height`/`transform: scale(...)` — desktop is the
   iframe's natural full-width (no fixed width/scale at all).
   `ResizeObserver` re-syncs on canvas resize.
8. **Site-wide accessible-dialog convention** (`apps/dashboard/static/js/admin_v2.js`'s
   command palette, `#adminV2CommandPalette` in `base_admin.html`, which
   every admin page including the Gallery already extends/loads) — the
   established pattern for a dialog on an admin page: `role="dialog"
   aria-modal="true"`, an `open`/`aria-hidden` toggle, Escape closes,
   backdrop click closes, focus moves into the dialog on open, and focus
   is restored to the triggering element on close
   (`trigger.focus({preventScroll: true})`). W5C's Preview dialog follows
   this SAME behavioral contract (not the same DOM/JS — the command
   palette is single-instance, page-scoped, and search-specific; the
   Preview dialog needs per-card retargeting — see §11 below for why a
   dedicated small controller is used instead of literal code sharing).

## Confirmed current gap (source-verified)

1. **GAP 1**: both "مشاهده..." preview links are `target="_blank"` —
   every preview click leaves the Gallery in a new tab; there is no
   in-page preview experience at all.
2. **GAP 2**: no Desktop/Tablet/Mobile control exists anywhere in the
   Gallery's own preview flow (R4 has one; the Gallery does not).
3. **GAP 3**: switching between Demo and Merchant data today means
   opening a second, independent tab/link — there is no single surface
   that lets a merchant compare both without re-navigating.
4. **GAP 4**: the screenshot thumbnail's own click target is the raw
   screenshot image (in a new tab), not any preview at all.

## Exact vertical slice (minimal production changes)

1. `apps/storefront_builder/templates/dashboard/storefront_builder/template_gallery.html`:
   - Add one shared (single-instance, not per-card) dialog markup block,
     following the site's `role="dialog" aria-modal="true"` convention:
     title, a Merchant/Demo data-source toggle, a Desktop/Tablet/Mobile
     device toggle, ONE `<iframe>`, a Close button, and an optional
     "باز کردن در تب جدید" link that always mirrors the iframe's current
     `src`.
   - Replace each card's screenshot `<a target="_blank" href="<raw image>">`
     with an `<a>` carrying `data-tpl-preview-trigger`,
     `data-tpl-preview-url-demo="{% url ... key=preset.key %}"`,
     `data-tpl-preview-url-merchant="{% url ... key=preset.key %}?data=merchant"`,
     `data-tpl-preview-label="{{ preset.label_fa }}"`, with its plain
     `href` kept pointing at the canonical Demo live-preview URL (not the
     raw screenshot) as the no-JS graceful-degradation fallback.
   - Convert the two "مشاهده..." `<a>` elements into the same
     `data-tpl-preview-trigger` contract (Demo one defaults the dialog to
     Demo mode on open, Merchant one defaults it to Merchant mode), each
     still carrying a real `href` to its own canonical URL for the no-JS
     fallback case.
   - No change to the Apply `<form>`, the current-template badge/disabled
     button, the palette swatch, or the card meta.
2. `apps/storefront_builder/static/storefront_builder/template_gallery_preview.js`
   (new, small, dedicated controller — see §12 Scope): opens/closes the
   dialog (Escape, backdrop click, explicit Close button, focus-into/
   focus-restore), retargets the ONE iframe's `src` to the canonical URL
   for the current (template, data-source) pair, toggles the data-source
   control, and applies Desktop/Tablet/Mobile presentation to that same
   iframe using the exact same width-contract values (1200/768/390) and
   transform-scale approach as R4's device switcher — implemented
   independently (see §11) rather than by importing/refactoring
   `r4_editor.js`.
3. A small, scoped CSS block (co-located in `template_gallery.html`'s own
   `{% block extra_css %}`, matching how the Gallery's existing card
   styles are already inlined there — no new stylesheet file needed for
   this page-scoped UI).
4. **No `views.py` change.** `storefront_template_gallery()` and
   `storefront_template_live_preview()` are both reused exactly as they
   are — the Gallery view already supplies every data field the dialog's
   triggers need (`preset.key`, `preset.label_fa`), and the live-preview
   route already accepts everything the dialog needs to request
   (`?data=merchant` or nothing). No new query parameter, no new context
   variable.
5. **No model, migration, mutation type, or new route of any kind.**

## Single source of truth (reaffirmed)

```
layout_preset_registry.list_ready_templates()   (UNCHANGED, 50 presets)
    -> Gallery cards (UNCHANGED context/view)
    -> Preview trigger data attributes (NEW: 2 URLs + label per card,
       both built server-side via {% url %})
    -> ONE shared dialog + ONE iframe (NEW markup, NEW small JS controller)
    -> existing storefront_template_live_preview route (UNCHANGED)
    -> existing preset_service.resolve_preset_candidate (UNCHANGED)
    -> existing shared candidate renderer (UNCHANGED)
    -> existing ready_template_live_preview.html (UNCHANGED)
```

No parallel authority is introduced anywhere in this chain. The
Desktop/Tablet/Mobile presentation values (1200/768/390) are a *design
constant* shared by convention with R4's device switcher, not a shared
runtime authority — each owns its own in-memory state, on its own page,
scoped to its own iframe.

## §11 reuse-vs-duplication decision (required to be documented)

R4's device-switcher logic (`syncPreviewViewport`/`setDevice` in
`r4_editor.js`) is not a standalone, importable module — it is a set of
closures inside one large IIFE that also captures R4-specific DOM
references (`previewFrame`, `previewCanvas`, `deviceSwitcher`) resolved
by `getElementById`/`querySelector` at the top of that file, and it is
part of the just-merged, freshly-certified W5A/W5B R4 surface. Extracting
it into a shared module now would require either (a) touching
`r4_editor.js` itself — re-opening a file whose current behavior is
certified by the W5A exact-source regression and the W5B browser-evidence
repair, for a purely cosmetic/presentational reuse gain — or (b) a new
shared JS module both `r4_editor.js` and the Gallery would need to load
and agree on element-selection conventions for, which is its own,
non-trivial integration risk for a same-sized page.

Per the directive's own instruction ("do NOT force a broad risky R4
refactor merely to share a few presentation lines" / "use a minimal
Gallery presentation controller that follows the exact same data-attribute
contract"), W5C uses a **minimal, independent Gallery-local presentation
controller** in the new `template_gallery_preview.js`, replicating R4's
exact data-attribute names (`data-desktop-viewport-width`,
`data-tablet-viewport-width`, `data-mobile-viewport-width`), width values
(1200/768/390), and transform-scale technique byte-for-byte in spirit,
but as fully independent code with its own in-memory `currentDevice`
closure variable, on the Gallery's own iframe. This is UI-local
presentation state (never persisted, never sent through any mutation,
never touching Store/Draft/DB/browser storage) — not a second application
authority; there is exactly one Bottom-Nav-style "authority" here (the
Ready Template registry + the live-preview route + the shared renderer),
and this controller sits entirely outside it, on the read/display side.

## Data-source default (§9)

**Default: Merchant data.** Confirmed safe and deterministic: the Gallery
view itself already calls `layout_service.get_or_create_draft(store,
user=request.user)` unconditionally before rendering any card, so by the
time a merchant can click a Preview trigger, their Draft already exists —
`storefront_template_live_preview`'s merchant-mode 404 branch
(`layout_service.get_existing_draft(preview_store) is None`) cannot fire
for an authenticated merchant reaching this dialog from their own Gallery
page. No automatic fallback from Merchant to Demo is implemented if a
merchant-mode load ever failed for some other reason (e.g. a genuine
transient error) — surfacing that failure is correct per the directive;
silently substituting Demo would hide a real problem.

Each trigger still independently declares which mode it defaults the
dialog to when clicked (the Demo-labeled trigger opens in Demo mode, the
Merchant-labeled trigger and the screenshot both open in Merchant mode),
so a merchant who explicitly asked for "مشاهده با اطلاعات نمایشی" is not
redirected mid-click to Merchant data.

## Device presentation (§10)

Desktop 1200 / Tablet 768 / Mobile 390, exactly mirroring R4's own
contract. The dialog's iframe is the SAME element across every
device/data-source change — switching device never reloads the iframe
(pure CSS width/transform, per R4's own `syncPreviewViewport`); switching
data source (or retargeting to a different template) DOES change the
iframe's `src`, since that is a genuinely different document to load —
there is no way to change which Store's data (or which Ready Template) is
rendered without navigating the iframe to a new URL, and that URL must
stay the canonical route (never `srcdoc`, never a second renderer).

## Modal / lightbox behavior

Single shared dialog instance in the DOM (not re-created per card).
Opening a trigger: (1) sets the dialog's title text to the template's
`label_fa`, (2) builds both candidate URLs (Demo/Merchant) from the
trigger's own data attributes, (3) sets the iframe `src` to whichever
mode this trigger defaults to, (4) shows the dialog (`role="dialog"
aria-modal="true"`, unhidden), (5) moves focus into the dialog (the Close
button, matching the command palette's own "focus the primary interactive
element" pattern), (6) remembers the trigger element to restore focus to.
Closing (Escape, Close button, or backdrop click): hides the dialog and
restores focus to the remembered trigger. Retargeting to a second,
different template while the dialog is already open (browser QA step 31)
reuses the same dialog/iframe, replacing title + URLs + `src`, never
opening a second dialog/iframe.

## Accessibility behavior

`role="dialog" aria-modal="true" aria-labelledby="<title-id>"`. Device
buttons expose `aria-pressed`. The data-source toggle exposes a clear
`aria-pressed`/current-state contract of its own (radio-like two-button
group, `aria-pressed` per button, mirroring the device switcher's own
convention for consistency). Escape closes from anywhere while the dialog
is open (document-level keydown listener, gated on the dialog's own open
state — same idiom as the command palette). Focus is trapped to the
dialog's own interactive elements while open is achieved by moving focus
into the dialog on open and never programmatically re-focusing the
background; the dialog is the last child appended so native browser tab
order plus `aria-modal` communicate the same to assistive tech, consistent
with how `resource_picker.html`'s overlay is already structured in this
codebase (overlay wraps a `role="dialog"` child).

## No-mutation guarantee

`storefront_template_live_preview` is GET-only, calls no mutation
service, no `preset_service.apply_preset()`, no `layout_service` write
method, and constructs its render candidate via
`preset_service.resolve_preset_candidate()` (already, before W5C,
returns a transient in-memory candidate — never persisted). W5C makes
zero changes to this view. Opening the dialog, switching device, and
switching data source are all pure client-side/GET-only operations; W5C's
non-mutation test contracts (§6.H/I/J/K) assert this directly against the
Draft's PK/`edit_revision`/`template_provenance`/history-entry count
before and after each of these interactions.

## TDD plan

New focused module:
`apps/storefront_builder/tests/test_phase5_w5c_ready_template_preview_ux.py`.
Genuine RED observed against the 4 gaps above (no preview-trigger data
attributes exist yet, no dialog markup, links still `target="_blank"`),
then GREEN after the minimal fix. Contracts A-S per the repair directive:
all 50 Ready Templates still exposed (registry-derived, never a second
hand-written key list), every card has a preview trigger carrying both
canonical URLs + label, those URLs resolve to the existing
`dashboard:storefront-builder-template-live-preview` route (never a new
endpoint/`srcdoc`), Merchant mode uses `?data=merchant` with no
tenant-identifying query params, Demo mode uses the bare canonical URL,
exactly one iframe element exists in the dialog markup, device controls
expose the 1200/768/390 contract, opening/switching-device/switching-data
are all non-mutating (Draft PK/`edit_revision`/`template_provenance`/
history-count unchanged), previewing Template X never touches
`template_provenance`, the existing Apply form/action is untouched and
still present, the replace-content `confirm()` remains gated on
`would_replace_existing_content`, the current-template badge still
renders, the screenshot fallback authority (`resolve_real_screenshot`/
`resolve_gallery_thumbnail`) is untouched, tenant isolation (merchant mode
never resolves a foreign Store even if a query string tries), an invalid
template key still 404s, the dialog markup has a real accessible
contract, and zero migrations.

## Browser QA plan

Reuse `tools/storefront_builder_r4_qa/` conventions (no second harness):
new sibling script `w5c_ready_template_preview_ux_qa.mjs`. Real merchant
journey: login, open Gallery, count 50 cards/triggers, pick a
registry-derived representative Template, snapshot Draft facts
(PK/`edit_revision`/`template_provenance`), open its in-page Preview,
assert dialog visible with the correct title, assert exactly one iframe,
assert its URL is the canonical route, switch Merchant→assert
`?data=merchant` + banner text + Draft unchanged, cycle Desktop→Tablet
(assert real `window.innerWidth≈768` inside the iframe document)
→Mobile (assert `window.innerWidth≈390`, non-zero rendered body), switch
back to Demo (assert same iframe element reused, URL now canonical/no
param, banner text changes, Draft still unchanged), close with Escape
(assert focus returns to the trigger), open a SECOND different Template
(assert retargeting, not stale content), close with the Close button,
confirm the Apply control is still present/unmodified. Representative
Templates: one early, one middle, one late in registry order (deterministic
spread, matching the directive's guidance) — full Desktop/Tablet/Mobile +
both data sources exercised for the first; the other two only prove
successful retargeting + iframe load (no 50×3 matrix, matching §17's
explicit "do not duplicate W4C" instruction).

## Non-goals (explicit)

- No second preview route, renderer, `srcdoc` mini-renderer, or
  client-side fake storefront.
- No change to `storefront_template_live_preview`'s write semantics (it
  stays GET-only, non-mutating, unchanged in this diff unless proven
  otherwise necessary — and it is not: no backend change is needed at
  all).
- No new mutation type, no `preview.apply`/`modal.apply` endpoint. The
  existing Gallery Apply `<form>` remains the sole Apply path; W5C does
  not add a convenience "use this template" button inside the dialog
  (optional per the directive; out of scope here to avoid unnecessary
  diff surface).
- No Home/Product/Collection/Search page switcher inside the dialog — the
  live-preview route's existing single-page-type behavior is unchanged.
- No change to `capture_ready_template_previews`, Ready Template recipes,
  section renderers, global renderers, or the public storefront renderer.
- No industry filtering/gating/pagination of the Gallery — all 50 Ready
  Templates remain equally reachable.
- No touch to `r4_editor.js`/`r4_editor.css` (see §11 above).

## Architectural duplication check

Zero new authorities. The registry, the live-preview route, the shared
candidate renderer, the screenshot-fallback service, and the Apply form
are all reused byte-for-byte. The only new code is: two data attributes
per card (server-rendered from data the view already computes), one
shared dialog markup block, and one small, independent, presentation-only
JS controller whose width contract intentionally mirrors R4's own by
convention, not by shared runtime state.

## Evidence plan

`docs/qa_evidence/storefront_design_engine/phase5/w5c_ready_template_preview_ux/`:
`starting_state.md`, `implementation_plan_summary.md`, `tdd_red.txt`,
`tdd_green.txt`, `preview_authority_chain.md`, `non_mutation_proof.md`,
`accessibility_review.md`, `focused_tests.txt`, `browser_qa.md`,
`code_review.md`, `full_suite_identity_comparison.md`, `source_diff.md`,
`final_report.md`.
