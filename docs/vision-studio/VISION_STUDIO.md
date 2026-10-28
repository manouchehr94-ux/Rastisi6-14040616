# RastiSi Vision Studio

A second **presentation** of the one R4 Design Studio session, shaped after the Vision Studio reference
(`assets/vision-studio-reference-20261028`, `docs/design-references/Promall_Frontend_Reference_v7_Faithful.html`). It owns no design data.

## Entry
* Admin sidebar → **«استودیو»** (its own section, permission `can_manage_storefront_layout`, route name `vision-studio`).
* URL: `/admin-portal/vision-studio/` (`?page=home|product_detail|listing|collection|search|cart`).
* The older routes (`storefront-builder-r4-editor`, «ظاهر و طراحی», «ساختار صفحه‌ها», `storefront-builder/`) are unchanged.

## Architecture (no second engine)
| Concern | Owner |
|---|---|
| Draft / Revision / Publish / History / Undo-Redo / Preview / Inspector / Global Design / Composer / Media picker | **R4** (`r4_editor.js`, `r4_mutation_service`, `layout_service`, …) – unchanged |
| UI state, dialogs (add section, templates, history, publish), toasts | `r4_studio.js` – unchanged |
| Layout of the panes, tab routing, element mode for header/footer, device bar read-out | **`vision/vision.js`** (presentation only, no request, no storage) |
| Look | `vision/vision.css` + generated `vision/vision-r4-dark.css` |

* `storefront_r4_editor(request, template_name=...)` renders the same context for both templates; the URL conf passes
  `dashboard/vision/studio.html` for `vision-studio`.
* `r4_editor.js` resolves its endpoints relative to the page (`new URL('mutate/', location.href)`). Vision therefore has **aliases** of the
  nine relative endpoints under `/admin-portal/vision-studio/…` (`apps/dashboard/urls.py`, `VISION_STUDIO_R4_ALIASES`) that point at the very
  same R4 views (permission decorators, Store resolution and Draft logic live on those views). `test_vision_studio.py` reads the relative paths
  out of `r4_editor.js` and fails if one has no alias.
* DOM contract kept by the template: `.rs-studio[data-r4-shell]`, `#r4Inspector`, `#r4PreviewFrame`, `#r4Structure`, `#r4GlobalDesign`,
  `#r4SaveState`, `#r4Undo/Redo/PublishButton`, `#r4PageSwitcherSelect`, `[data-r4-device-switcher]`, `.r4-preview-canvas`, `rsStudioData`, …
  (see `REQUIRED_IDS` / `REQUIRED_SELECTORS` in the test). Script order matters: `r4_editor` → `r4_color_picker` → `r4_studio` → `r4_resize` →
  `r4_composer` → `r4_announcement` → `vision`.
* The R4 components rendered inside Vision (section Inspector, Global Design, structure rows, dialogs) hard-code a light palette. A twin dark
  stylesheet is **generated** from the R4 CSS: `python tools/vision_studio/make_dark_overlay.py` (re-run after changing `r4_*.css`).

## Honest gaps (shown as «در دست توسعه», never as working controls)
Custom templates, store SEO score / Google preview / keywords, scroll-reveal motion, global icon style, separate heading font / text weight,
glass background / page background image, order-tracking and checkout pages. They need new engine or service work; see the feasibility report.

## QA
* Isolated DB/Media: a copy of the QA SQLite database (`db.sqlite3` in the worktree, git-ignored), media as a hard-link tree
  (`DJANGO_MEDIA_ROOT`, `DJANGO_PRIVATE_MEDIA_ROOT`); never the original QA database. Port **8007**.
* Tests: `python manage.py test apps.storefront_builder.tests.test_vision_studio apps.dashboard.tests.test_admin_navigation`;
  real browser (opt-in): `SFB_BROWSER_TESTS=1 DJANGO_SETTINGS_MODULE=shop_core.settings_browser_tests python manage.py test
  apps.storefront_builder.tests.test_vision_studio_browser` (also runs the Composer scenarios A–H against the Vision page).
