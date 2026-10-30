# Hero Stage design engine — delivery report (2026-10-30)

Base SHA `b9562ccfa1ab890008e14c3217c5a9a3f9fc234a` (= remote branch head). Everything below is **local, unpushed**.
Reference audit, real-engine matrix (path:line) and the design contract live in `HERO_STAGE_ENGINE_CONTRACT_20261030.md`.

## 1. Engine (generic, no template keys)
* New section `hero_stage` (home-only, max 1) = header + hero in one canvas: modes `merged | overlay | independent`, single/dual background panels
  with split ratios and per-panel focal point, scrim style/strength, content frame (border/shadow/opacity/blur/radius), ordered slots
  (eyebrow, title, subtitle, cta, categories, product_card) with per-device hide, per-breakpoint size/alignment, Store-bound categories and product card,
  versioned settings (`SETTINGS_VERSION`), allowlisted vocabulary, clamped numbers, semantic colours only, Store-scoped media (fail-closed).
* One shell-level decision (`header_embedded_for`) shared by live page, Draft preview, builder preview and gallery live preview; safe fallback to the
  shell header (stage not first, hidden on a device, independent mode, framed/nested container).
* Files: `apps/storefront_builder/hero_stage.py`, `section_registry.py`, `services/render_service.py`, `services/storefront_context_service.py`, `views.py`,
  templates `sections/hero_stage.html`, `partials/hero_stage_header.html`, CSS block in `storefront_builder.css`.

## 2. Templates (official registry `apps/storefront_builder/a11_stage_templates.py`, imported by `layout_preset_registry.py`)
| id | Persian title | structure |
|---|---|---|
| `dual_atelier` | کتان آتلیه | two-panel hero, merged header |
| `editorial_noir` | سیاه و زر | dark single panel, overlay header, framed copy |
| `glass_commerce` | اقیانوس شیشه‌ای | glass content frame, categories + product card |
| `asymmetric_canvas` | بوم تراکوتا | asymmetric split, large type, independent rhythm |
Thumbnails are registry-derived SVG (`template_preview_service.py`). Templates ship without stock photos (fallback colour until the Store supplies media).

## 3. Acceptance chain (isolated DB/Store only)
Per template: Registry → gallery selection → real Studio editor → ≥6 real controls (header mode, panels, scrim, vertical position, title size, CTA; backend chain adds slot order + Store media) →
Save Draft → reload → Undo/Redo → Preview → Publish (temp store) → Storefront.
* Backend: `tests/test_hero_stage_templates.py::test_the_full_chain_for_every_template` (+ two-store isolation, foreign media refusal, malformed payloads, XSS, permission, stale revision, cross-preset edits, legacy templates unchanged).
* Chromium (opt-in `SFB_BROWSER_TESTS=1`, throw-away PostgreSQL): `tests/test_hero_stage_browser.py::test_every_template_from_the_gallery_to_the_published_storefront` (4 sub-tests, widths 320/390/768/1440).
* PostgreSQL concurrency: `tests/test_studio_open_concurrency.py` (two pre-existing races fixed: `ensure_page_containers`, `get_or_create_draft`).
Firefox could not be run in this environment — Windows scenario below.

## 4. Test results
* Full suite after `46b97c71`: Ran 11834, 35 failures + 5 errors, 230 skipped. Not claimed green. Two ids were not in the baseline:
  W4C `test_13_hero_none_templates_computed_live_not_hardcoded` (fixed in `626aef16`) and
  `test_product_image_service…test_mid_operation_failure_rolls_back_completely` (temp-dir flake under parallel run; passes alone — 177 tests OK with the W4C module).
* After M4: `apps.dashboard apps.portal apps.stores` (parallel 4): Ran 3781, failures 6, errors 1, skipped 35 — **all 7 are listed in `TEST_RECONCILIATION_20261029.md`** (portal onboarding gallery ×5, refresh_rasti_mode_demo_visuals ×2); no new failures.
* New/changed targeted suites OK: M4 finance/search/domain + tax/gift-wrap/settings/navigation/shell (203 + 150 + 22 + 14 tests).

## 5. M4 panel UX (separate commits)
* C `f1505757` settings search: scope label «فقط صفحه‌های تنظیمات», hint to the global Ctrl+K search, aligned with the content column (also the screen chips). Same index/permission filter/`?section=`.
* B `e57140fa` finance: accordion cards; real green/gray switches only for Boolean settings (gift-wrap enable, card message). Tax stays a read-only summary (editor `/admin-portal/tax/settings/`, 9 % untouched). Switches save with the explicit form button (no autosubmit, so other fields are never dropped); «remove image» stays a checkbox (an action).
* A `2ec65757` domain page: development/QA host (`*.localhost`, loopback) is labelled «نشانیِ فعلیِ محیط آزمایشی» with a warning instead of «آدرسی که مشتریان می‌بینند». Backend/guide/Step-Up/audit untouched.
* D: Cart.store / audit_cart_scope / Excel dynamic dropdown / RastiService — risks only, nothing implemented.

## 6. Limits and risks
No free pixel drag/resize or video background; slots can't be reordered per device (hide/align only); «featured» product = newest; the stage embeds the header only as first stand-alone top-level block;
`get_or_create_draft` now takes a layout row lock; no real screenshot sidecars for the new templates; no schema change, no migration proposed or applied.

## 7. Windows QA (read-only fetch)
Fetch the local commits from the cloud bundle/branch handed over by the user (not pushed). In a disposable Store: Studio → قالب‌های آماده → pick each of the four → Inspector «بخش قهرمان»
change header mode / panels / overlay / position / title size / CTA → Undo/Redo → Preview → publish on the test store → check 390 and 1440 in Firefox and Chromium.

---
## Addendum — Final Pre-Push Gate (2026-10-30)

Code HEAD for the final test runs: `bc2ae4f0f669b01378712af2969f1bbe85054548` (the commit after it is documentation only).

### Findings and fixes made during the gate
1. **PostgreSQL deadlock (real, introduced by the first concurrency fix) — fixed.** `ensure_page_containers` locked the *page* row; R4 mutations lock *layout → draft → section(+page)*. A heal racing a mutation produced `deadlock detected` (≈1 in 3 stress runs). The heal now locks the Store's *layout* row first (`077c4ba1…`). New PG-only test `test_a_heal_and_an_r4_mutation_never_deadlock` fails 3/3 on the page lock and passes on the layout lock; 6 post-fix stress runs (heal × heal × mutation × draft-open × structure edit × publish; 175 requests + 50 stale-revision refusals each) had no error and PostgreSQL logged no deadlock after the fix.
2. **Finance badge could look "saved" after a rejected save — fixed** (`86fdbf54…`): the badge now shows the stored value; a rejected form shows an explicit "not saved" note.
3. **Test-harness race — fixed** (`bc2ae4f0…`): the browser chain grabbed the Preview frame while the Studio reloaded after a template apply.

### Verified with real evidence (disposable DB/Store, Chromium)
* merged mode: one `<header>` in the document, inside `.hs-stage`; stage is `isolation:isolate` (own stacking context); header box lies inside the shared background layer; the topmost element at the header position is the header; embedded header HTML is identical to the shell header on `/products/` (normalised) — same menu, search form (`/products/`), cart (`/cart/`), wishlist/account (login dialog) and category links; all 14 sampled links return 200.
* overlay: header wrapper `position:absolute` at the stage top, body padded by header height + 12px; independent: shell header, none in the stage; stage hidden on a device → shell header for every width (never a page without a header). No horizontal scroll at 1440/768/390.
* structure of the four templates differs in header mode, panel layout/split, alignment, vertical position, frame, slot set/order, product card vs category bar, and section sequence on the home page (not only colour/name). Closest pair: `editorial_noir` and `glass_commerce` (both merged + single panel; they differ in alignment, position, slots and following sections).

### Documented limits
* No free pixel drag/resize: composition is flow/grid + ordered slots + alignment + per-breakpoint size/alignment/hide. Slot **order is one global order** — per-device you can hide a slot and change alignment, not reorder it.
* There is no "featured product" flag in the catalogue. The product-card slot lists "جدیدترین / پرفروش‌ترین / دارای تخفیف"; the UI never calls it "featured".
* The stage embeds the header only as the first stand-alone top-level block of the home page; otherwise the shell header is used.

### Test results (final)
* Full suite (SQLite, parallel 4) on `bc2ae4f0`: Ran 11849, failures 34, errors 4, skipped 231 (passed 11580). All 38 failing ids are in `TEST_RECONCILIATION_20261029.md` (29 storefront_builder Vision-baseline + 8 environmental in portal/stores/sms…); **0 new**. One baseline id did not fail this run (`…test_product_image_views…test_reorders_by_posted_sequence`, a parallel-only flake). Not green.
* PostgreSQL: hero stage 20 ok, stage templates 19 ok, concurrency 3 ok (×3 runs), stress module 4 ok (×6 runs).
* Chromium on PostgreSQL: template chain / hide-per-device / existing-template regression 3 ok (×2 runs). The other 10 browser failures in `test_hero_stage_browser` are inherited from `test_engine_parity_browser`; the same module on the untouched base `b9562ccf` shows the same 2 failures + 8 errors (pre-existing, opt-in, not in the default suite).
