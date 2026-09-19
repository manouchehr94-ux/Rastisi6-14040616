# W5C — Source Diff Summary

Full diff: `git diff 3125a3250b1284ba216ac8c125257b7e48aaf0bf..HEAD`
(base = official W5B integration HEAD).

```
 apps/storefront_builder/static/storefront_builder/template_gallery_preview.js  | 199 +++++
 apps/storefront_builder/templates/.../template_gallery.html                    |  90 ++-
 apps/storefront_builder/tests/test_phase5_w5c_ready_template_preview_ux.py     | 411 +++
 apps/storefront_builder/tests/test_ready_template_real_previews.py             |  26 +-
 apps/storefront_builder/views.py                                               |   8 +
 (+ plan/evidence docs, ~1600 lines, docs-only)
 15 files changed, 2573 insertions(+), 8 deletions(-)
```

## Production code (3 files, non-test)

- **`apps/storefront_builder/templates/dashboard/storefront_builder/template_gallery.html`**
  (+90/-8): a new CSS block (page-scoped, inline, matching how the
  Gallery's existing card styles are already inlined here — no new
  stylesheet file); each card's screenshot `<a>` and both "مشاهده..."
  `<a>` elements gain `data-tpl-preview-trigger` +
  `data-tpl-preview-url-demo`/`-url-merchant` (both built via `{% url %}`)
  + `data-tpl-preview-label`, with their `href` kept as the no-JS
  fallback; one new shared dialog block (title, data-source toggle,
  device toggle, one `<iframe>`, close button, "open in new tab" link)
  appended once after the existing gallery-footer block; one new
  `{% block extra_js %}` loading the new controller script. No existing
  block/context/form/badge markup removed or altered.
- **`apps/storefront_builder/static/storefront_builder/template_gallery_preview.js`**
  (new file, 199 lines): open/close, focus management (incl. Tab focus
  trap), data-source toggle, and Desktop/Tablet/Mobile presentation for
  the ONE shared iframe. Zero `fetch`/`XMLHttpRequest`/form-submission
  calls anywhere in the file — it only ever reads data attributes already
  rendered by the template and sets `<iframe>.src` to one of the two
  server-supplied URLs.
- **`apps/storefront_builder/views.py`** (+8): `storefront_template_live_preview`
  gains exactly one decorator, `@xframe_options_sameorigin`, plus its
  docstring justification. No other line in this file changed —
  `storefront_template_gallery`, `_preset_would_replace_content`,
  `preset_service`, and every other view/helper are byte-for-byte
  unchanged.

## Zero JavaScript changes to R4

`git diff --stat -- 'apps/storefront_builder/static/storefront_builder/r4_editor.js' 'apps/storefront_builder/static/storefront_builder/r4_editor.css'`
between the base and this branch is empty — confirmed no touch to R4's
own device-switcher implementation, per the plan's §11 decision.

## Test code

- **`apps/storefront_builder/tests/test_phase5_w5c_ready_template_preview_ux.py`**
  (new file, +411, 24 tests across 5 classes): trigger/dialog markup,
  static accessibility markup, non-mutation (6 tests covering opening,
  retargeting, and data-source round-trips), Apply-path/badge/confirmation
  regression guards, and tenant isolation.
- **`apps/storefront_builder/tests/test_ready_template_real_previews.py`**
  (+26/-11 in one test): updates one pre-existing test whose assertion
  targeted the OLD "screenshot links to the raw static image" behavior,
  which this phase's own product requirement explicitly supersedes — see
  `implementation_plan_summary.md` for the full justification. No other
  test in this file changed.

## Non-production, not part of this diff summary's risk surface

- Plan + evidence documents under `docs/superpowers/plans/` and
  `docs/qa_evidence/.../w5c_ready_template_preview_ux/`.

## Zero migrations

No model field was added, removed, or altered.
`manage.py makemigrations --check --dry-run` reports "No changes
detected".

---

# Round 2 — Independent Architect repair diff

Diff: `git diff 2ebdc38ea868ceb5eae6a6696560cc4835fe6410..HEAD` (base =
the pre-repair PR head).

```
 apps/storefront_builder/static/storefront_builder/template_gallery_preview.js         |  27 +
 apps/storefront_builder/tests/test_phase5_w5c_ready_template_preview_ux.py            | 187 +++
 apps/storefront_builder/tests/test_task2_live_demo_template_preview.py                |  12 +
 apps/storefront_builder/views.py                                                       |  26 +-
 apps/stores/management/commands/apply_golden_reference_storefront.py                   |  15 +-
 (+ evidence docs, ~1200 lines, docs-only)
 18 files changed, 1462 insertions(+), 5 deletions(-)
```

## Production code (2 files, non-test, non-management-command)

- **`apps/storefront_builder/views.py`** (+26/-2): `storefront_template_
  live_preview` gains `@require_GET` and its Demo-mode candidate
  resolution changes from `get_or_create_draft` to `get_existing_draft`
  (with a new 404 branch matching Merchant mode's existing one), plus
  docstring justification. No other line changed.
- **`apps/storefront_builder/static/storefront_builder/template_gallery_preview.js`**
  (+27): one new `frame.addEventListener('load', ...)` block attaching
  an Escape handler to each newly-loaded iframe document. No other
  function changed.

## Production code (1 management command)

- **`apps/stores/management/commands/apply_golden_reference_storefront.py`**
  (+15/-1): one new step after publishing — `layout_service.
  get_or_create_draft(store)` — so the canonical Demo Store always has a
  usable Draft immediately after seeding, matching the Preview route's
  new no-bootstrap contract. Idempotent, consistent with the command's
  existing idempotency guarantee.

## Test code

- **`apps/storefront_builder/tests/test_phase5_w5c_ready_template_preview_ux.py`**
  (+187, 8 new tests across 4 new classes): `PreviewMethodContractTests`
  (POST → 405, both modes), `DemoPreviewNoBootstrapTests` (a Demo Store
  with no Draft still 404s and creates zero persistence — proven against
  the DB), `SeededDemoPreviewNonMutationTests` (a real seeded Demo Draft
  is never mutated, including repeated loads), and
  `MerchantPreviewNoBootstrapRegressionTests`.
- **`apps/storefront_builder/tests/test_task2_live_demo_template_preview.py`**
  (+12 in `setUpTestData`): the pre-existing, otherwise-unmodified shared
  fixture now explicitly creates a fresh Demo Draft after
  `apply_golden_reference_storefront` publishes — required once Demo
  mode correctly stopped silently bootstrapping one. See
  `non_mutation_proof.md`'s round-2 section for the full account
  (7 failures before this fixture fix, 20/20 after).

## Zero migrations (still)

`manage.py makemigrations --check --dry-run` reports "No changes
detected" at the final repaired HEAD.

## Zero new preview routes / renderers / mutation types (still)

The repair touches only the existing route's method restriction and
candidate-resolution call, the existing dialog's Escape handling, and
one seeding command's post-publish step — no new URL, template, or
mutation type anywhere in this diff.
