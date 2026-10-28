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
| Layout of the panes, tab routing, design categories + palette cards, switch wording, device bar read-out | **`vision/vision.js`** (presentation only, no request, no storage) |
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

## Editing UX (UX correction phase)
* **Section settings = large modal.** The one R4 Inspector (`#r4Inspector`, same partials, same mutations) is shown in a centred dialog
  (800–1000 px on a desktop, ≤ 90 % of the height, near full-screen on a phone) with the element's name, a visible «بستن», the live
  save/error/Revision-conflict status (mirrored from `[data-rs-save-feedback]`) and an independent scroll. R4's own two-column card grid
  is used on a desktop (`.r4-ws-cols`; short fields additionally sit two per row). Escape / «بستن» / «انجام شد» close it through R4;
  focus returns to the navigator row that opened it. A failed or conflicting save keeps the dialog open and says why; a write still in
  flight is awaited first. The Composer's own *Group settings* keep their larger (1280 px) workspace.
* **«طراحی» tab = an ordered list of categories** (برند و رنگ‌ها، نوع نوشته و فونت‌ها، دکمه‌ها، شکل و تراکم، تصاویر و رسانه‌ها،
  سربرگ/پابرگ فروشگاه، ناوبری موبایل، تم مناسبتی) each with an icon, a one-line description and the **current value read from the real
  controls**. A click opens a dedicated large modal that shows only that category of the one `#r4GlobalDesign` panel (the flat R4
  markup is tagged by `vision.js`, `data-vs-cat`; nothing is copied, no second form). Saving stays R4's `appearance.update`,
  `header.update`, `footer.update`, `bottom_nav.update`.
* **Colours modal.** The registry's palettes (`appearance_registry`, the 73 palettes that carry the eight roles) as cards with six real
  colours + a tiny type/button mock, name, selected ring + check, hover/focus states, name search, and the real custom-colour rows
  (`color_overrides` / `theme_overrides`, R4 colour picker, «از پالت» reset). The server only adds the six swatches of each palette to the
  context (`vsPalettes`); the choice is the real `palette_slug` mutation.
* **Switches.** Every `input.r4-switch` / `button.switch` shows its value in words next to the control (on = coloured track + knob at the
  start side + «روشن»; off = neutral + knob opposite + «خاموش»; disabled = hatched + «غیرفعال»). The wording follows the field's meaning:
  «پنهان …» fields read «پنهان است» when ON, «نمایش …» fields «نمایش داده می‌شود»; only the label is added, the Boolean R4 stores is
  untouched.
* The generated dark overlay's `:is(.rs-studio,html)` selectors cannot match under `.vs`; the colour picker and the slider's «default
  slides» box are therefore themed explicitly in `vision.css`.

## Clarity phase: switches by real key, model galleries, plain wording
* **Switch meaning comes from the real stored key, never from label text** (`vision.js`, `vsUx` from `vision_ux.py`). Properties that are stored as
  «hidden» (`hide_on_tablet`, `hide_on_mobile`: the key starts with `hide_`) are shown inverted as «visible»: stored `false` ⇒ ON / green /
  «نمایش داده می‌شود», stored `true` ⇒ OFF / grey / «پنهان است». An inverted switch is a real `role="switch"` button (`aria-checked` = what is
  shown, keyboard + focus ring) layered over **R4's own checkbox, which stays the one source of truth**: a click on the proxy clicks that
  checkbox, so R4's ordinary change handler sends the same `header.update` / `footer.update` mutation (Revision, History, Undo/Redo). Positive
  keys (`show_*`, `sticky`, …) keep their native switch. Disabled is hatched / dashed + «غیرفعال» (distinct from OFF).
* **Header / footer model galleries.** The `<select>` of `r4GlobalHeaderVariant` / `r4GlobalFooterVariant` stays in the DOM (hidden) and is the
  only thing written; the gallery is built from `global_region_registry` (keys, Persian names) + `vision_ux.VARIANT_COPY` (one sentence per
  distinct look) + pre-rendered thumbnails. Choosing a card sets the select and fires its change event (⇒ the R4 mutation).
  * Thumbnails are photographs of the REAL renderer: `python manage.py capture_global_region_previews --base-url <demo store host> --user <staff>`
    opens the read-only `vision-studio/region-preview/?region=…&variant=…` (the Store's own shell with exactly one region swapped for the asked
    registry model; writes nothing, creates no Draft, 400 for unknown input) at 1280 px and 390 px and stores
    `static/storefront_builder/vision/region_previews/<region>/<key>.<device>.webp` + `manifest.json` (fingerprint of the renderer and the
    templates it includes, and `same_as` for models that render identically). A missing / stale picture is shown as «پیش‌نمایش موجود نیست»,
    never drawn by hand. `test_vision_studio` fails when a registry model has no fresh thumbnail or description.
  * «مشاهده بزرگ‌تر» opens that same preview live (the seller's own logo / menu / colours), desktop and phone width, without any mutation.
  * Models that render pixel-identically to another are grouped under «مدل‌های هم‌ظاهر» (`same_as`), not presented as distinct choices.
* **Wording** (`vision_ux.SETTING_COPY`, keyed by real field key): a plain Persian name + one sentence of effect under each control, a scope bar
  (اثر: کل فروشگاه · devices · «ذخیره در پیش‌نویس · منتشر نمی‌شود») in every design dialog, and a per-control saving → «✓ در پیش‌نویس ذخیره شد»
  badge. `test_vision_studio` fails when a control of the Global Design partial has no wording.

## Honest gaps (shown as «در دست توسعه», never as working controls)
Custom templates, store SEO score / Google preview / keywords, scroll-reveal motion, global icon style, separate heading font / text weight,
glass background / page background image, order-tracking and checkout pages. They need new engine or service work; see the feasibility report.

## QA
* Isolated DB/Media: a copy of the QA SQLite database (`db.sqlite3` in the worktree, git-ignored), media as a hard-link tree
  (`DJANGO_MEDIA_ROOT`, `DJANGO_PRIVATE_MEDIA_ROOT`); never the original QA database. Port **8007**.
* Tests: `python manage.py test apps.storefront_builder.tests.test_vision_studio apps.dashboard.tests.test_admin_navigation`;
  real browser (opt-in): `SFB_BROWSER_TESTS=1 DJANGO_SETTINGS_MODULE=shop_core.settings_browser_tests python manage.py test
  apps.storefront_builder.tests.test_vision_studio_browser` (also runs the Composer scenarios A–H against the Vision page).
