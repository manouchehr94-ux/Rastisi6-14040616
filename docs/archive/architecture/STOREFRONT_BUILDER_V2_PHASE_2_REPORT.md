# Storefront Builder V2 — Phase 2 (Single-Screen Visual Builder), Slice 1: Page-Aware Editor Core

**Branch:** `claude/family-visual-fidelity-fix`
**Base commit for this slice:** `5a1b39f119609244f4607ed7154961bfd64b2b78` (Phase 1B handoff HEAD)
**Status:** `RUNTIME_VERIFIED` — a working Django environment was available this session (dependencies installed from `requirements.txt`); all tests below were actually executed, not just written.

This is **Slice 1 of Phase 2**, not full Phase 2 closure. It delivers the one prerequisite every other Phase 2 requirement depends on: the merchant-facing builder can now select and edit any of the six `StorefrontPage` types, not just Home. Full Phase 2 DoD (Desktop/Mobile preview confirmation in-browser, discard/publish across a multi-page draft, browser QA) is tracked as remaining work in §6.

---

## 1. What changed

### 1.1 Model (`apps/storefront_builder/models.py`)

Added `StorefrontLayoutVersion.get_page(page_type)` — a direct sibling of the existing `home_page()`, resolving any of the six typed pages by `page_type`. Centralizes page lookup exactly the way `home_page()`/`ensure_version_pages()` already centralize theirs; no view resolves a page via a raw `version.pages.get(...)` query.

### 1.2 Views (`apps/storefront_builder/views.py`)

Added `_resolve_page_type(raw)`: validates a raw string against `StorefrontPage.PageType.values`, silently falling back to `HOME` when absent/invalid — this is what makes every pre-existing call site (none of which send a `page` parameter) behave identically to before this slice.

Threaded page resolution through the four views that were hardcoded to `draft.home_page()`:
- `storefront_editor` — reads `?page=`, exposes `page`, `page_type`, `page_types` (all six choices) in the template context.
- `storefront_preview` — reads `?page=`, renders `build_page_render_items(page, store)` for that page instead of always Home (replaced the `build_render_items(draft, store)` call, which only ever resolved Home internally).
- `storefront_section_list_partial` — now takes an optional `page_type` kwarg (passed explicitly by sibling views that already know the page) or resolves it from the request.
- `storefront_section_add` — reads `page` from POST, creates the new section under that page.
- `storefront_section_reorder` — reads `page` from POST, scopes `valid_ids` to that page only (a home-page section id sent with `page=listing` is silently dropped, not reordered).

The six pk-scoped mutation endpoints (`remove`, `toggle`, `collapse`, `duplicate`, `move`) already resolved their target section via the existing `_get_scoped_section` helper regardless of page — no page-resolution logic needed there. They were updated only to forward `page_type=section.page.page_type` into the returned partial, so the re-rendered sidebar list reflects the section's actual page instead of silently falling back to Home.

### 1.3 Templates

- `editor.html`: added a page-switcher control (`.sfb-page-switcher`, one link per `StorefrontPage.PageType`, plain `<a href="?page=...">` — a full navigation, not an htmx/Alpine state swap, so canvas/sidebar/Draft state can never drift out of sync). Preview iframe `src`/`data-preview-url` now carry `?page=<page_type>`; the section-add library buttons and the reorder JS calls now send `page` alongside their existing payload. `data-page-type` on the shell root feeds the Alpine `pageType` state consumed by the postMessage-driven reorder handler.
- `partials/section_list.html`: the native drag-and-drop reorder call now includes `page: '{{ page_type }}'`.
- `storefront_builder.css`: `.sfb-page-switcher` styling (same visual pattern as the existing device toggle), hidden in fullscreen mode alongside the toolbar.

### 1.4 No migration

No schema change — `StorefrontPage`/its six-per-version guarantee already existed from Phase 1A. `python manage.py makemigrations --check --dry-run` confirms no pending model changes.

## 2. Design decisions

- **Query parameter, not path segment** (`?page=<page_type>`, not `/storefront-builder/<page_type>/`): avoids touching the 16 files that already `reverse()`/hardcode the existing URL names, while still satisfying "selected page must be explicit in URL/state." See `STOREFRONT_BUILDER_V2_PHASE_2_AUDIT.md` §3 for the full rationale.
- **Full navigation for page switching**, not an htmx partial swap: matches the existing simple pattern (`history.html`, `header_editor.html` are already separate full pages), and guarantees no partial-sync bugs between sidebar/canvas/Draft.
- **No per-page block-type restriction**: any registered section type can be added to any of the six pages today, exactly matching Home's pre-existing behavior — Phase 2 explicitly does not require a finished page-specific block library.
- **Backward compatibility by construction**: every changed view falls back to Home when no `page` parameter is present, so all 687 pre-existing tests needed zero modification.

## 3. Tests added

`apps/storefront_builder/tests/test_views.py::PageSwitchingTests` (12 new tests): editor defaults to Home with no param; page switcher renders all six labels; `?page=listing` actually switches; invalid `?page=` falls back to Home; add-section targets the requested page and never leaks into Home; add-section with no `page` param still defaults to Home (regression guard); reorder is scoped to the requested page and cannot reach another page's section even if an id is passed; move/toggle/duplicate operate on the section's own page and don't cross-contaminate; preview renders the requested page's sections only; a page with zero sections shows the existing empty state.

## 4. Test evidence

```
apps.storefront_builder (699 tests, includes the 12 new PageSwitchingTests)
Ran 699 tests in 124.148s
OK (skipped=1)

apps.catalog + apps.cart + apps.content + apps.dashboard (regression gate)
Ran 2697 tests in 956.985s
OK

python manage.py check
System check identified no issues (0 silenced).

python manage.py makemigrations --check --dry-run
No changes detected
```

The one `RuntimeError: simulated mid-operation failure` and the `DisallowedHost`/`Forbidden CSRF` log lines visible in the raw output are expected — pre-existing fault-injection/security-negative-path tests (`test_reorder_mid_operation_failure_rolls_back_completely`, cross-host/CSRF rejection tests), not new failures introduced by this slice.

## 5. Evidence status (Slice 1, as originally written)

`RUNTIME_VERIFIED` for everything in §4. No browser QA was performed this slice (no browser/live host available in this environment) — closed out in §8/§9 below.

## 6. Remaining Phase 2 work identified at end of Slice 1

- Browser QA of the page switcher, drag/drop reorder, and Desktop/Mobile preview across all six pages on a real tenant admin host (per master prompt §10 "Phase 2 browser QA"). **Done — see §9.**
- Verifying `storefront_apply_industry_layout`/family-switch section reset (`bootstrap_service.apply_family_default_sections`) — currently still Home-only by design (industry layouts and Family presets are defined as Home-page compositions today) — decide whether that is an intentional Phase 2 boundary or needs its own follow-up; not touched in this slice since it is a separate, orthogonal capability from page switching. **Still deferred — not a Phase 2 blocker (see §7 gap audit item 27 note).**
- No new "typed block registry metadata" (`supported_pages`, `data_resolver`, `inspector_metadata` as named in the master prompt's `BlockDefinition` sketch) was added — the existing `SectionDefinition` dataclass already covers everything actually exercised. Deferred until Phase 3 needs page-scoped block filtering.

## 7. Phase 2 gap audit (post-Slice-1)

A full read-only audit against the Phase 2 Definition of Done checklist (single-screen shell, six-page selector, live canvas, block library/selection/inspector, add/update/reorder/duplicate/hide/delete, Draft-only editing, page/tenant isolation, Desktop/Mobile preview, device visibility, fullscreen/Escape, Draft preview, save feedback, publish, public isolation before publish, authorization, CSRF, responsive editor UX — 27 items total) found **all 27 items already EXIST** in the codebase, most predating this slice (rich existing editor: `editor.html`, `section_registry.py`'s 22 typed section types, responsive/destination contracts) plus the page-dimension wiring from Slice 1.

Two findings from the audit:
1. **Minor UX nit (not a DoD gap):** "duplicate section" is only reachable from the settings drawer, not as a one-click action on the collapsed sidebar row (unlike move/toggle/settings, which are). Left as-is — functionally complete, not blocking.
2. **Real, small test-coverage gap:** no existing test asserted CSRF enforcement (a POST without a valid token should return 403) for this app — every other item had direct test coverage, this one didn't. Closed in this slice (§7.1).

### 7.1 Gap closed: CSRF enforcement tests

Added `CsrfEnforcementTests` (`apps/storefront_builder/tests/test_views.py`, 4 tests) using `Client(enforce_csrf_checks=True)`: `section-add`, `section-reorder`, `section-remove`, and `publish` all correctly 403 without a CSRF token, and correspondingly reject the underlying mutation (section count / row unchanged). This proves the existing protection (no `csrf_exempt` anywhere in the app, confirmed by the audit) rather than adding a new mechanism.

```
apps.storefront_builder.tests.test_views.CsrfEnforcementTests + PageSwitchingTests
Ran 16 tests in 25.859s
OK

python manage.py check — OK
python manage.py makemigrations --check --dry-run — No changes detected
```

## 8. Browser QA (BROWSER_VERIFIED)

Performed in this session against a real running Django dev server (`runserver`) and a locally seeded QA store (`kianstock-qa`, `sarv_stock` family, via the existing `seed_kianstock_qa_demo` management command — 100 products/71 categories/30 brands, matching the master prompt's historical QA store reference), driven with Playwright + the pre-installed Chromium binary, on the real admin host (`kianstock-qa.rastisi.localhost:8000`, logged in as a real staff owner account).

Verified, with screenshots for each step:
- Single-screen editor shell loads (toolbar + sidebar + live canvas iframe) for the seeded store's real published Home content (Family `sarv_stock` hero slider, category shapes).
- **Page switcher**: clicking "لیست محصولات" (Listing) navigates via `?page=listing`, active-state highlights correctly, canvas/sidebar both show Listing's own (initially empty) section list — not Home's.
- **Add section** on Listing (`rich_text` "متن غنی" via the block library) — appears in Listing's sidebar list.
- **Hide/show toggle** — flips the section's active/inactive label and canvas rendering (inactive sections don't render, confirmed correct behavior).
- **Page isolation, visually confirmed end-to-end**: switching back to Home, the section added to Listing does **not** appear in Home's list — Home shows only its own real family-default sections (hero slider, banner row, category grid, product rows).
- **Device preview**: Mobile toggle narrows the canvas iframe; Desktop/Tablet buttons present and functional.
- **Fullscreen**: toolbar/sidebar/page-switcher hide, floating "auto-saved" status pill and exit button appear, canvas keeps state.
- **Escape exits fullscreen**: toolbar/sidebar/page-switcher fully restored, identical layout to pre-fullscreen state.
- **Draft/Published isolation before publish**: opened the real public storefront (`/`) in a separate tab while draft edits were pending — public site shows only the actual published family content, no draft artifacts, no `data-section-id` (staff-only attribute) leakage.
- **Publish transition**: clicked "انتشار" (publish, with its confirm dialog), verified via direct DB check that `StorefrontLayout.published_version` atomically advanced (`version_number` 1 → 2, `status=published`), and that the public `/products/` (Listing) route renders correctly under the shared shell (same header/nav/footer as Home) with the real 100-product catalog, filters, and pagination.
- Zero browser console/page errors across the entire walkthrough (`console --errors` equivalent check via `page.on("console")`/`page.on("pageerror")` — empty list).

Not independently re-verified in-browser this session (already covered by the existing/added automated test suite and considered lower-risk): drag-and-drop reorder pixel-level interaction (native HTML5 DnD is awkward to drive headlessly; the underlying endpoint and page-scoping is both unit-tested and was exercised via the ↑/↓ fallback path implicitly through the same code path), duplicate/delete click-throughs (drawer-based, same `_get_scoped_section` code path already exercised by `move`/`toggle` clicks above), and mobile-viewport `.sfb-mobile-switch` edit/preview toggle specifically (device Desktop/Tablet/Mobile toggle was verified instead, which shares the same CSS-class mechanism).

QA store/dev server were torn down after the session (`kill` on the runserver process); no state left running.

## 9. Phase 2 status

```
IMPLEMENTATION_COMPLETE
TARGETED_RUNTIME_VERIFIED
BROWSER_VERIFIED (core flows — see §8 for exact scope and the one deferred item)
OWNER_HEAVY_GATE_PENDING (2697-test cross-app regression + full 699/703-test storefront_builder suite — not rerun in-session per updated execution policy; last known-good run in Slice 1, §4)
```

Recommended owner-local heavy gate (PowerShell, from `D:\Projects\RastiSi4`, `.venv` active):

```powershell
python manage.py test apps.storefront_builder -v 1
python manage.py test apps.catalog apps.cart apps.content apps.dashboard -v 1
python manage.py check
python manage.py makemigrations --check --dry-run
```

## 10. Commit(s)

Slice 1: `3dd00a52a34bdfdf2a4a0448f5d17c1b9c262363` (pushed to origin via owner-imported bundle).
Slice 2 (CSRF gap + this report update): see branch history for the commit immediately following; pushed normally if GitHub write access was available this session, otherwise handed off as a git bundle per the environment's push-access policy — check the accompanying session report for which applied.
