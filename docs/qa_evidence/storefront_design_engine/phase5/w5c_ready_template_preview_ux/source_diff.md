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
