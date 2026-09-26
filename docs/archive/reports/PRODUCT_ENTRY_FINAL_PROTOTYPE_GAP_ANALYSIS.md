# RastiSi Product Entry — Gap Analysis (Final Prototype v2)

**Type:** Analysis only. No application code, template, CSS, JS, model, migration, view, form, or service was changed to produce this report.
**Authoritative reference:** `rastisi-product-entry-prototype-final-v2.html` (uploaded by the user, read in full). All older product-entry prototypes, screenshots, and prior interpretations are explicitly excluded from this comparison.
**Status:** Analysis complete. Awaiting explicit user approval before any implementation begins.

---

## 1. Executive summary

The current Django Product Create/Edit flow (`apps/dashboard/templates/dashboard/partials/product_form.html` and its includes) is architecturally **more advanced** than the approved prototype in several areas (rich-text description via CKEditor5, tag chips, video-embed validation, drag-reorder image gallery, a three-tier variant-image priority system, publish scheduling, visibility control, a multi-axis variant engine with bulk actions) but **structurally diverges** from the prototype's approved 5-step wizard shape and is **missing a small number of fields the prototype shows** (unit of measurement, product model/technical code, country of manufacture, and a "second group" merchandising field).

The single most consequential finding is architectural, not cosmetic: **the current `Product` model has exactly one `category` ForeignKey (`on_delete=PROTECT`)** — a product belongs to exactly one leaf category, full stop. The prototype's "گروه دوم" (second group) field, which in the HTML is populated with merchandising-collection values like "پیشنهاد ویژه" / "جدیدترین‌ها" rather than taxonomy nodes, has **no corresponding backend concept at all** — not a second FK, not an M2M, not a tag system aimed at that purpose (the existing `ProductTag` M2M is general-purpose, not scoped to "second group" semantics). This is flagged in §11 as an **unresolved decision** per the user's explicit instruction; it must not be implemented in this phase.

The current UI's tab grouping (4 tabs: اطلاعات پایه → نوعِ کالا → تصاویر و ویدیو → سئو و انتشار) differs from the prototype's 5-tab grouping (اطلاعات پایه → دسته‌بندی → قیمت و تنوع → تصاویر و فیلم → سئو و انتشار) in one structural way: **the current UI merges "category" and "price & variants" into a single step**, while the prototype keeps them as two separate steps. This is a reversible, UI-only layout change (Classification B) with no backend implication — see §16 for a staged, low-risk way to split it if the user wants literal 5-step parity.

No horizontal page overflow was observed in live browser verification at 1440/1024/768/390px on the current wizard (§ "Responsive/mobile").

---

## 2. Current repository state

| Item | Value |
|---|---|
| Branch | `claude/rastisi-audit-fixes-av8eao` |
| HEAD commit | `ae153b9` — "مودال‌های تودرتو: رفعِ باگِ واقعیِ «دکمه‌ی افزودن کار نمی‌کند» + جلوگیریِ از رگرسیونِ خودِ رفعِ قبلی" |
| `git status --short` | empty (clean) |
| `git diff --stat HEAD` | empty (clean) |

Recent history on this branch (for context, most recent first):
```
ae153b9 مودال‌های تودرتو: رفعِ باگِ واقعیِ «دکمه‌ی افزودن کار نمی‌کند» + جلوگیریِ از رگرسیونِ خودِ رفعِ قبلی
f33faba مودالِ ساختِ دسته‌بندی: رفعِ باگِ «دکمه‌ی افزودن کار نمی‌کند»
07b09fe فرم افزودن کالا: تبدیل به ویزارد مرحله‌ای در اندازه‌ی موبایل + رفع باگ breadcrumb
ddeb7ab فرم افزودن کالا: رفع باگ موقعیت مودال‌های تودرتو هنگام اسکرول
ba1b4cd فرم افزودن کالا: تنظیم ویژگی/تنوع بدون پیام «ابتدا ذخیره کنید»
```

### Exact current Product Create/Edit URLs

From `apps/dashboard/urls.py` (verbatim, product-entry-relevant subset):

```
products/add/                                      dashboard:product-add            → views.product_form
products/<int:pk>/edit/                             dashboard:product-edit           → views.product_form
products/<int:pk>/preview/                          dashboard:product-preview        → views.product_preview
products/attribute-fields/                          dashboard:product-attribute-fields       → views.product_attribute_fields
products/<int:pk>/attribute-fields/                 dashboard:product-attribute-fields-edit  → views.product_attribute_fields
products/quick-add-brand/                           dashboard:product-quick-add-brand        → views.product_quick_add_brand
products/quick-add-category/                        dashboard:product-quick-add-category     → views.product_quick_add_category
products/<int:pk>/quick-add-category/               dashboard:product-quick-add-category-edit → views.product_quick_add_category
products/<int:pk>/images/                           dashboard:product-images          → views.product_images_modal (gallery modal)
products/<int:pk>/images/upload/                    dashboard:product-image-upload
products/<int:pk>/images/<int:image_id>/alt/        dashboard:product-image-alt
products/<int:pk>/images/<int:image_id>/caption/    dashboard:product-image-caption
products/<int:pk>/images/<int:image_id>/variant/    dashboard:product-image-variant
products/<int:pk>/images/<int:image_id>/option-value/ dashboard:product-image-option-value
products/<int:pk>/images/<int:image_id>/move/       dashboard:product-image-move
products/<int:pk>/images/<int:image_id>/set-cover/  dashboard:product-image-set-cover
products/<int:pk>/images/<int:image_id>/delete/     dashboard:product-image-delete
products/<int:pk>/images/reorder/                   dashboard:product-image-reorder
products/<int:pk>/videos/add/                       dashboard:product-video-add
products/<int:pk>/videos/<int:video_id>/delete/     dashboard:product-video-delete
products/<int:pk>/variants/...                      dashboard:product-variants*       — LEGACY single-axis variant system (see §4)
products/<int:pk>/options/...                       dashboard:product-option*, product-variant* — multi-axis engine (see §4), wired into the wizard's "نوعِ کالا" tab
```

`product_variants` (legacy, single-axis, `apps.catalog.services.variant_service`) and `product_options`/`product_variants_generate` (multi-axis engine, `apps.catalog.services.variant_engine_service`) **both exist and are both routable**, but they are **mutually exclusive per product at the data level**, not parallel systems a merchant can pick between freely:
- `variant_engine_service.add_product_option()` refuses to create the first `ProductOption` axis on a product while any legacy variant (`combination_key=""`) still exists on it.
- `product_options_body.html` (embedded in the wizard) detects `has_legacy_variants` and, if true, shows only a link to the **separate** legacy `/variants/` management page instead of the attribute/variant UI — i.e. the wizard's "نوعِ کالا" tab does not manage legacy variants at all.
- In practice, **every product created through the current wizard uses the multi-axis engine only**; the legacy system is reachable only for pre-existing data that predates the engine (or was created via direct API/admin use of the old path).

This is a **pre-existing dual-system fact**, not something introduced by this analysis, and not something this phase touches.

### Exact current templates (product-entry flow)

All under `apps/dashboard/templates/dashboard/partials/`:
- `product_form.html` — root modal, wizard shell, tabs `basic`/`price`/`media`/`seo`
- `product_category_select.html` — leaf-category tree picker + 3-step quick-add-category modal
- `product_category_tree_node.html` — recursive tree node partial
- `product_brand_select.html` — inline brand `<select>` + quick-add panel
- `product_attribute_fields.html` — category-scoped **descriptive** attribute fields (non-variant, `ProductAttributeValue`)
- `product_options_body.html` — multi-axis attribute/variant management (embedded in wizard's "price" tab for existing variable products)
- `product_images_modal.html` — standalone gallery+video modal (`dashboard:product-images`)
- `product_images_list.html` — image gallery grid, drag-reorder, per-image variant/option-value assignment dropdowns
- `product_videos_list.html` — video list partial
- `product_no_category_banner.html` — "no leaf categories yet" banner
- `products_table_inner.html` — product list table (out-of-band swap target after save)

### Exact current views/forms/services

**Views** (`apps/dashboard/views.py`):
- `product_form(request, pk=None)` (line 878) — single view for both add and edit, dispatches on `pk`
- `_product_form_initial(product)` (line 806) — builds initial dict for `ProductForm` (a plain `forms.Form`, not `ModelForm`)
- `_product_form_extra_context(store, product, ...)` (line 829) — shared context: checklist, completion %, tags, category tree, variant/attribute context
- `_PRODUCT_WIZARD_FIELD_STEPS` (line 790) — maps `ProductForm` field names → wizard tab key, used by `_product_wizard_error_step()` to route server-side validation errors back to the correct tab
- `product_quick_add_category(request, pk=None)` (line 1060)
- `product_quick_add_brand(request)` (line 1033)
- `product_attribute_fields(request, pk=None)` (line 1018)
- Plus ~30 further views for images/video/options/variants (see URL list above)

**Forms** (`apps/dashboard/forms.py`):
- `ProductForm` — plain `forms.Form` (not `ModelForm`); fields: `name, sku, category, brand, price, discount_percent, stock, status, icon, description, product_type, barcode, weight_grams, requires_shipping, tax_class, seo_title, seo_description, slug, visibility, publish_at, tags`
- `ProductQuickCategoryForm` — 3-level quick-add (group/category/sub_name, each existing-or-new)
- `ProductOptionForm` — attribute-axis add form; **no `input_type` field is ever shown to the user** — color vs. text is auto-detected from whether `color_values_json` has entries
- `ProductOptionValueAddForm`, `AttributeValueForm`, `BrandForm`, `AttributeForm`, `ProductImageUploadForm`, `ProductImageAltForm`, `VariantBulkAddForm`, `VariantEditForm` (legacy single-axis)

**Services** (`apps/catalog/services/`):
- `variant_engine_service.py` — multi-axis engine: `add_product_option`, `add_option_value`, `generate_variants` (idempotent Cartesian product, preserves existing variants by `combination_key`, obsoletes rather than deletes removed combinations), `add_manual_variant`, `set_default_variant`. Hard cap `MAX_OPTION_AXES = 3`.
- `variant_service.py` — legacy single-axis engine (not read in full for this report; out of scope for the wizard as established above)
- `product_image_service.py` — upload/validate (jpg/png/webp, ≤5MB, real-content verification via Pillow), auto-resize (max 2000px, 400px thumb), cover-image "steal the flag" pattern, `set_image_variant`, `set_image_option_value`
- `product_video_service.py` — YouTube/Aparat URL detection via regex, `embed_url()` computation; **no other providers supported, no direct file upload**
- `product_publish_service.py` — `validate_product_for_publish()` (required category-schema attributes + price > 0), `storefront_visible_products()`, `storefront_listing_products()` (visibility-aware)
- `storefront_variant_service.py` — `resolve_display_image()` (3-tier priority: exact variant image → image-driving option-value image → product cover), `build_variant_selector_context()` (independent per-axis selectors for multi-axis products)
- `attribute_service.py` — Attribute/AttributeValue CRUD + `ProductAttributeValue` (descriptive, non-variant) assignment
- `brand_service.py`, `category_schema_service.py` — not read line-by-line for this report; referenced only for the facts already cited (leaf-category enforcement, required-attribute schema)

### Exact current models

All in `apps/catalog/models.py`. Field lists are verbatim from the model source (verified by direct read, not inferred):

**`Product`** (line 118): `store, vendor, category (FK→Category, PROTECT, single, not-null), brand (FK→Brand, SET_NULL, nullable), name, slug, sku, description, price, discount_percent, stock, status (active/inactive/draft), product_type (simple/variable), visibility (public/link), publish_at, rating, reviews_count, sold_count, views_count, tag (single legacy marketing tag: new/hot/sale), icon, tint, barcode, weight_grams, requires_shipping, tax_class, seo_title, seo_description, tags (M2M→ProductTag)`.
**There is no `unit`/`واحد شمارش` field, no `model_code`/`مدل یا کد فنی` field, and no `country_of_origin`/`کشور سازنده` field on `Product`.** (`Brand.country` exists, but that is the brand's country, not the product's manufacturing country — a materially different field.)

**`Category`** (line 46): `store, name, slug, icon, parent (FK→self, nullable, CASCADE), order, is_active, source_template_category`. Self-referencing tree, no depth limit in the model itself (depth-3 is enforced only by `SubSubCategoryForm`'s queryset restriction in the forms layer, not a DB constraint).

**`Brand`** (line 92): `store, name, name_en, slug, logo, description, website, country, sort_order, is_active`.

**`ProductImage`** (line 258): `product, variant (FK→ProductVariant, SET_NULL, nullable — exact-variant image), option_value (FK→ProductOptionValue, SET_NULL, nullable — attribute-value-driven image), image, thumbnail, alt, caption, order, is_cover, is_360` (data-only flag; no 360° viewer implemented).

**`ProductVideo`** (line 304): `product, provider (youtube/aparat), url, title, display_order`. `embed_url` is a computed property, not stored.

**`ProductVariant`** (line 412): `product, store, attribute (str), value (str), normalized_attribute, normalized_value, value_hex, sku, barcode, stock, extra_price, is_active, display_order, compare_at_price, cost, price (independent absolute price, nullable), wholesale_price, sales_limit_min, sales_limit, tax_class, track_inventory, low_stock_threshold, weight_grams/length_mm/width_mm/height_mm, combination_key (multi-axis identity, empty for legacy), is_default, is_obsolete`.

**`Attribute`** (line 935, store-level reusable library): `store, code, label, description, data_type (text/number/boolean/select/multiselect/color/date), display_type, unit, is_required, is_filterable, is_searchable, is_comparable, is_variant_axis, is_image_driving, category, display_order, is_active`.

**`AttributeValue`** (line 1031): `attribute, label, value, normalized_label, color_hex, swatch_image, display_order, is_active`.

**`ProductAttributeValue`** (line 1082) — descriptive (non-variant-creating) assignment of an `Attribute`/`AttributeValue` to a `Product`.

**`ProductOption`** (line 1147, per-product variant axis): `product, attribute (optional link back to library Attribute), label, normalized_label, input_type (text/color/number), position, is_active`.

**`ProductOptionValue`** (line 1202): `option, attribute_value (optional link), label, normalized_label, color_hex, display_order, is_active`.

**`VariantOptionValue`** (line 1242) — join table giving each generated `ProductVariant` a stable identity per axis (`PROTECT` on `option_value`, per ADR-20).

**`ProductTag`** (line 1122) — store-owned free tag, M2M via `Product.tags`.

**SEO fields**: `Product.seo_title`, `Product.seo_description` (both on `Product` itself, not a separate model). **Publication state**: `Product.status` (active/inactive/draft) + `Product.visibility` (public/link-only) + `Product.publish_at` (optional schedule) — three independent axes, richer than the prototype's single `select`.

---

## 3. Approved prototype inventory (exact reference)

Source: `rastisi-product-entry-prototype-final-v2.html`, read in full (312 lines). This is the literal structure — nothing summarized loosely.

**Shell:** 5-step horizontal pill bar (`.step[data-step="0..4"]`), each with a numbered circle (`.num`) and Persian label. A `.progress-mini` bar tracks overall progress. **Note on the file's own internal inconsistency**: an early `<style>` block implies a sidebar-collapsing-to-horizontal-icons responsive pattern, but a second, later `<style>` block (lines 66–113) overrides it and forces the step bar to be horizontal at all widths (`.shell{display:block}`, `.sidebar{grid-template-columns:repeat(5,...)}`), and re-enables `.step-label{display:inline}` below 700px — contradicting the first block. The later rule wins in CSS cascade, so the prototype's actual behavior is: **always-horizontal 5-pill bar**, not sidebar-then-collapse. This is reported as a fact about the reference file, not treated as ambiguous.

**Required/optional convention:** a `<span class="required-star">*</span>` red star next to required labels; a `<span class="opt">اختیاری</span>` pill next to optional ones; a `.legend` bar at the top explains both once.

**Step 1 — اطلاعات پایه:**
| Field | Required? | Widget |
|---|---|---|
| نام کالا | * | text |
| کد کالا | * | text + "تولید" auto-generate button |
| برند | optional | select + "+ افزودن برند" → generic `simpleModal` |
| واحد شمارش | * | select (عدد/متر/کیلوگرم/شاخه) |
| مدل یا کد فنی | optional | text |
| برچسب‌ها | optional | **single free-text input** (not a chip UI) |
| توضیحات کالا | optional | rich text with toolbar: Bold/Italic/Underline/Heading/List/Link/Table |

**Step 2 — دسته‌بندی:**
| Field | Required? | Widget |
|---|---|---|
| گروه اصلی | * | select + "+ افزودن گروه اصلی" |
| زیرگروه | * | select + "+ افزودن زیرگروه" |
| گروه دوم | optional | select + "+ افزودن گروه دوم" — populated with merchandising-style values ("پیشنهاد ویژه", "جدیدترین‌ها"), **not** a third taxonomy level |
| کشور سازنده | optional | text, default "ایران" |

**Step 3 — قیمت و تنوع:**
- `.segment` toggle: کالای ساده / کالای دارای تنوع.
- Simple: قیمت* / تخفیف%(opt) / موجودی* — **no SKU field visible for simple products in this prototype.**
- Variable: info banner explaining Cartesian combinations; "ویژگی‌های تنوع‌ساز" card (name-only attribute cards, no color/type selection shown to user — same auto-detect philosophy the current app already implements); "+ افزودنِ ویژگی جدید" → `#attrModal` (name only); "تنوع‌های ساخته‌شده" card with a table/card view toggle (`variant-view-switch`), "ساخت ترکیب‌ها" button (`generateVariants()` — preserves existing variant data by matching `JSON.stringify(v.values)` against prior combos, i.e. a **content-hash** preservation strategy, not an id-based one); `.variant-summary` (count / total stock / price range); table view (`min-width:980px`, scrolls internally via `.table-wrap{overflow:auto}` above 700px, page itself does not scroll) and a card-grid view for <700px; each row/card has a 58×58px inline `.variant-image-box` (click-to-upload, `FileReader`/`toDataURL`, **exact-variant only — no attribute-value-level image concept in the prototype at all**); "ویرایش" opens `#variantModal` (price/stock/sku/discount only — no active/inactive toggle inside the modal, though the table shows an on/off pill separately).

**Step 4 — تصاویر و فیلم:** one multi-file `.dropzone` (no visible size/format restriction text); `.gallery` grid, each `.thumb` with "تصویر اصلی/اصلی کن" (cover toggle) and "حذف"; one video-link field + one video-title field, **no embed preview or provider validation** (plain text inputs, no regex, no YouTube/Aparat detection).

**Step 5 — سئو و انتشار:** عنوان سئو (opt), آدرس صفحه/slug (opt, pre-filled), وضعیت انتشار* (single select: پیش‌نویس/فعال/غیرفعال — no separate visibility axis, no scheduling field), توضیحات متا (opt textarea), a Google-style SEO preview box (partially static, not fully live-bound).

**Footer:** sticky bar, "مرحله قبل" (hidden on step 0) / "ذخیره پیش‌نویس" + "مرحله بعد" (becomes "ثبت کالا" on step 4).

**Modals:** `#attrModal` (attribute name), `#variantModal` (variant price/stock/sku/discount), `#jsonModal` (raw JSON preview — `finalSave()` only validates name+code non-empty then calls `previewJSON()`; **there is no real submission endpoint in the prototype, it is a static client-side demo**), `#simpleModal` (one generic modal reused for brand/group/subgroup/secondGroup quick-add, driven by `state.simpleModalType`).

**Data shape** (`state` object, useful as the prototype's implied contract): `{step, type, variantView, simpleModalType, attributes:[{name, values:[]}], variants:[{values, sku, stock, price, discount, active, image}], images:[], editIndex}`.

---

## 4. Current Product Entry architecture (narrative)

The current flow is a single Alpine.js component (`product_form.html`) rendered inside a shared admin modal shell (`base_admin.html`'s `#admin-modal-content`), submitted via one `hx-post` (`multipart/form-data`) to `product-add` or `product-edit`, both routed to the same `product_form` view. Four `x-show`-toggled tabs (not `x-if`, deliberately, per the earlier breadcrumb-ref-destruction bug fixed this session) share one `<form>` and one submit button; there is no per-step network round-trip except for: (a) htmx-driven category/attribute-field refresh when category changes, (b) the "keep_open" auto-continue mechanism that saves a brand-new product early (as soon as name+sku+category are filled and "variable" is chosen) so the real `product_options_body.html` variant panel — the *same* panel used for existing products — can render against a real `product.pk`, avoiding a parallel "unsaved-product" variant UI.

Category, product-type, price entry (via a "Set Price" modal, not raw fields), and — for existing variable products — the full attribute/variant manager are all inside the single "نوعِ کالا" (price) tab, unlike the prototype's separation of category (step 2) from price/variants (step 3).

Media (images, drag-reorder, cover toggle, video with embed preview) is its own tab for edit mode; for a brand-new (unsaved) product, images are staged client-side (Alpine file list + hidden `cover_index` input) and only actually uploaded via `product_image_service.add_product_image` after the product itself is created in the same POST — video for new products is a plain `video_url`/`video_title` field pair validated the same way as the edit-mode version (regex-detected provider, live iframe preview), submitted with the rest of the form rather than via a separate `hx-post`.

SEO/publication is its own tab, richer than the prototype (adds `visibility` and `publish_at`, plus a live publish-readiness checklist for existing products, sourced from `product_publish_service.validate_product_for_publish` + `apps.catalog.services.product_completion_service`).

---

## 5. Exact relevant files

Already enumerated with full paths in §2 ("Exact current templates/views/forms/services/models"). No additional files were found to be part of the live product-entry flow beyond those listed. `apps/dashboard/services/` does not exist as a separate package for this feature — all business logic lives in `apps/catalog/services/`, consistent with "views must stay thin" per the docstring in `variant_engine_service.py`.

---

## 6. Per-area comparison matrix

Status legend: **MATCH** / **PARTIAL** / **MISSING** / **DIFFERENT** / **BUG** / **UNSAFE TO CHANGE WITHOUT BACKEND WORK**.
Classification legend: **A** visual-only · **B** template/UI logic only · **C** existing backend capability, missing UI · **D** backend work required · **E** unsafe/architecture conflict.

| Area | Prototype behavior | Current Django behavior | Status | Exact gap | Backend support exists? | UI-only? | Backend change? | Risk | Files likely involved | Class |
|---|---|---|---|---|---|---|---|---|---|---|
| Overall wizard shape | 5 steps, category and price/variant separated | 4 tabs, category folded into the "price" tab | DIFFERENT | Splitting into 5 steps is a template/JS reorganization only | Yes (all fields already exist) | Yes | No | LOW | `product_form.html` | B |
| Step order labels | اطلاعات پایه→دسته‌بندی→قیمت و تنوع→تصاویر و فیلم→سئو | اطلاعات پایه→نوعِ کالا→تصاویر و ویدیو→سئو و انتشار | DIFFERENT | Label/order only | — | Yes | No | LOW | `product_form.html`, `views.py::_PRODUCT_WIZARD_FIELD_STEPS` | B |
| نام کالا | required text | required text (`ProductForm.name`) | MATCH | — | — | — | — | — | — | — |
| کد کالا (SKU) | required text + auto-generate button | required text, no auto-generate button, uniqueness-validated server-side | PARTIAL | Missing "تولید" (auto-generate SKU) convenience button | Partial — no SKU-generation helper exists anywhere in the codebase (only `variant_engine_service.generate_variant_sku`, which is variant-scoped, not product-scoped) | No | Needs a small product-level SKU generator function | LOW | `forms.py`, `views.py`, `product_form.html` | C/D (mixed: UI needs a new small service function, not a model change) |
| برند | select + modal quick-add | inline select + inline quick-add panel (not a modal) | PARTIAL | Interaction pattern differs (inline vs. modal); functionally equivalent | Yes | Yes | No | LOW | `product_brand_select.html` | A |
| واحد شمارش (unit) | required select (عدد/متر/کیلوگرم/شاخه) | **field does not exist anywhere** | MISSING | No `Product.unit` field, no form field, no UI | No | No | **Yes** — new `Product` field + migration + form + UI | MEDIUM | `models.py`, migration, `forms.py`, `product_form.html`, likely storefront display templates | D |
| مدل یا کد فنی (model/technical code) | optional text | **field does not exist** | MISSING | Same as above | No | No | **Yes** — new field | LOW–MEDIUM | same as above | D |
| برچسب‌ها (tags) | single free-text input | full Alpine chip UI (add/remove pills), backed by `ProductTag` M2M + suggestions | DIFFERENT (current exceeds prototype) | Current UI/data model is *more* capable; matching the prototype literally would be a regression | Yes (already implemented) | N/A | N/A | — (do-not-implement candidate) | `product_form.html` | — |
| توضیحات کالا (description) | rich text (Bold/Italic/Underline/Heading/List/Link/Table) | CKEditor5 (`heading, bold, italic, bulletedList, numberedList, outdent, indent, link, insertTable, blockQuote, uploadImage, mediaEmbed, undo, redo`) + server-side sanitizer | MATCH (current is a superset) | None — current toolbar covers every prototype item and more | — | — | — | — | — | — |
| وضعیتِ نمایش (status) | (spec: 3-button row active/inactive/draft, already implemented per earlier session) | 3-button segmented row (`فعال/غیرفعال/پیش‌نویس`) | MATCH | — | — | — | — | — | — | — |
| گروه اصلی / زیرگروه (category) | 2 required selects, each with its own "+ افزودن" | single tree-picker button + 3-step quick-add modal (group→category→leaf) covering both levels at once | PARTIAL | Interaction pattern differs (2 separate dropdowns vs. 1 tree picker); prototype's 2-field UI maps onto the current 3-level tree's first two levels; functionally the current implementation is a **more general** version (supports arbitrary depth-3 trees, not just group+subgroup) | Yes | Yes | No | LOW | `product_category_select.html` | A/B |
| گروه دوم (second group) | optional select + quick-add, populated with **merchandising labels**, not taxonomy nodes | **no equivalent concept anywhere** | MISSING | See dedicated analysis in §11 — **do not implement without an explicit decision** | No | No | **Undetermined — requires a decision, not just code** | **HIGH** (data-model ambiguity risk) | TBD per §11 | E |
| کشور سازنده (country of manufacture) | optional text, default "ایران" | **no `Product.country_of_origin` field** (only `Brand.country`, a different concept) | MISSING | New optional `Product` field | No | No | **Yes** — new field | LOW | `models.py`, migration, `forms.py`, `product_form.html` | D |
| Simple/Variable toggle | 2-button segment | 2-button segmented radio row | MATCH | — | — | — | — | — | — | — |
| Simple product fields | قیمت*/تخفیف%(opt)/موجودی*, no SKU shown | price+discount via "Set Price" modal (not inline fields); stock is inline but tucked inside a collapsed `<details>` ("تنظیماتِ تکمیلی") | DIFFERENT | Current buries stock in an advanced/collapsed section; prototype shows it inline and required at top level | Yes | Yes | No | LOW | `product_form.html` | B |
| Variable-product attribute cards | name-only cards, no color/type shown to user | name + auto-detected color-value section (already hides `input_type` from the user, matching prototype's philosophy) | MATCH | — | — | — | — | — | — | — |
| Variant generation | `generateVariants()` preserves by `JSON.stringify(values)` content match | `variant_engine_service.generate_variants()` preserves by `combination_key` (sorted option-value ids), obsoletes (not deletes) removed combos, atomic, entitlement-gated | MATCH in outcome (idempotent preserve/regenerate), DIFFERENT in preservation mechanism (id-based key vs. content hash) — current is more robust (survives value **relabeling**, prototype's approach would not) | None functionally relevant; current is strictly better | — | — | — | — | — | — |
| Variant view mode | table/card toggle (`variant-view-switch`) + a legacy `.mobile-variants` grid for <700px | single responsive table (`variant-table-responsive`) that CSS-reflows into stacked cards below 768px via `data-label` attributes — **no user-facing toggle**, the reflow is automatic | PARTIAL | No manual table/card switch; current instead auto-switches by viewport, which is arguably better UX but is a different interaction model than the prototype's explicit toggle | Yes (reflow already works) | Yes (only if a manual toggle is specifically wanted) | No | LOW | `product_options_body.html`, `admin.css` | B |
| Variant image | 58×58 inline click-to-upload, **exact-variant only**, `FileReader`/`toDataURL`, no server round-trip modeled | read-only thumbnail in the table (driven by `variant.display_image`, 3-tier priority: exact-variant → image-driving option-value → cover); actual assignment happens in the **separate** "مدیریتِ تصاویر و اختصاصِ تصویر به تنوع" gallery modal via per-image `<select>` dropdowns (`product_image_variant`, `product_image_option_value`) | DIFFERENT | See dedicated deep-dive below. Current model is materially more capable (3-tier fallback + attribute-value-driven switching that the prototype's model cannot express at all) but the *interaction* is 2 clicks away (open gallery modal → pick dropdown) instead of 1 (click the thumbnail in the variant row) | Yes (fully implemented, richer than prototype) | Partial — an inline "assign image" shortcut *button* next to the table thumbnail (deep-linking into the existing gallery modal, or a lightweight inline picker) is UI-only | No | LOW | `product_options_body.html`, `product_images_list.html` | B |
| Variant edit modal | price/stock/sku/discount only, no active toggle inside modal | separate small modals per field group: one for price+discount, one for sales-limit(min/max); active toggle inline in table row (checkbox), not in either modal; sku/stock inline in table row, not in a modal | DIFFERENT | Interaction pattern differs (2 focused modals + inline row edits vs. 1 combined modal); prototype groups more into one modal | Yes | Yes | No | LOW | `product_options_body.html` | A/B |
| Bulk actions on variants | not present in prototype | bulk stock fill, bulk activate/deactivate, bulk sales-limit, bulk delete, per-row duplicate, "set default variant" | DIFFERENT (current exceeds prototype) | Current is a strict superset | — | — | — | — | — | — |
| Media dropzone | single dropzone, no visible restriction text | dropzone with visible "jpg/png/webp, ≤5MB" text, both for new and existing products | MATCH (current exceeds prototype in disclosure) | — | — | — | — | — | — | — |
| Media gallery | thumb grid, cover toggle, delete | drag-reorder grid, cover toggle, delete, per-image alt text, caption, variant/option-value assignment, move up/down buttons (both drag and buttons — dual affordance) | MATCH (current exceeds prototype) | — | — | — | — | — | — | — |
| Video | plain URL+title fields, no validation/preview | regex-validated (YouTube watch/shorts/`youtu.be`/embed + Aparat `v/`/embed) with live iframe preview before submit | MATCH (current exceeds prototype) | — | — | — | — | — | — | — |
| 360° images | not present in prototype | data-only flag (`ProductImage.is_360`) exists, no UI, no viewer | N/A | Out of scope for this comparison (prototype has no equivalent to gap against) | — | — | — | — | — | — |
| SEO fields | عنوان سئو, slug, توضیحات متا, preview box | same 3 fields + same preview box concept, live-bound via `document.querySelector` reads (not full two-way binding, but reactive to input) | MATCH | — | — | — | — | — | — | — |
| Publication state | single select (پیش‌نویس/فعال/غیرفعال) | `status` (3-way, same values) **+** `visibility` (public/link-only) **+** `publish_at` (optional schedule) **+** live pre-publish checklist | DIFFERENT (current exceeds prototype) | Prototype has no equivalent to `visibility`/`publish_at`/checklist — not a gap against the prototype, a current-app capability the prototype simply doesn't show | — | — | — | — | — | — |
| Required/optional markers | red star + "اختیاری" pill + one-time legend | inline `?` help-icon tooltips per field, `*` in label text for required fields, no dedicated "اختیاری" pill, no top-of-form legend | PARTIAL | Visual convention differs; current relies on `*` text + tooltips instead of star icon + pill + legend | Yes | Yes | No | LOW | `product_form.html`, `admin.css` | A |
| Final submit / raw preview | `#jsonModal` static JSON preview, **no real backend** | real `hx-post` submission with full server-side validation (`ProductForm`, `full_clean()` on every touched model, `ProductPublishError`, category-schema required-attribute check) | N/A | Prototype's submit path is a non-functional demo; current is the production path — nothing to "match," current is strictly the real implementation the prototype was mocking | — | — | — | — | — | — |

---

## 7. Existing bugs / fragile areas (audit only — not fixed here)

Per the user's explicit list of previously-fixed-but-worth-re-auditing areas, current state as of HEAD `ae153b9`:

- **Teleported Alpine modals** (category picker, quick-add-category, price modal, per-variant price/sales-limit modals, bulk sales-limit modal): all confirmed still wrapped in `<template x-teleport="body">` (verified by direct template read in §2/§6, not assumed) and covered by regression tests in `test_product_modal_positioning.py` (5 tests, all asserting the teleport wrapper is present in server-rendered HTML). **Stable.**
- **htmx processing after teleport**: the 3 teleported overlays that contain `hx-*` attributes (quick-add-category modal, per-variant price modal, per-variant sales-limit modal) all still carry `x-init="htmx.process($el)"` (verified in §6 template reads). **Stable.**
- **Orphaned modals**: the quick-add-category submit button still uses `hx-on::htmx:before-request="quickAddOpen = false"` rather than a racing `@click`, per the fix documented in `test_product_modal_positioning.py::test_quick_add_category_submit_closes_modal_before_its_own_swap`. **Stable.**
- **Category quick-add / category selection after creation**: `confirmSelection()` dispatches `category-selected`, which triggers `maybeAutoContinueToVariants()`, and the quick-add modal's success path re-swaps `#categoryField` via `hx-swap="outerHTML"`, which re-renders the picker with the newly created category present in `category_tree_rows` (server-side, from `_product_form_extra_context`) — this was the bug reported by the user in an earlier turn of this session ("ثبت شد ولی دیگر نمایش داده نمی‌شود"), and no code changes were made in *this* gap-analysis session, so its current live behavior was not re-verified end-to-end here (only the template wiring was inspected). **Flagged for live re-verification, not re-confirmed as fixed in this pass** — this is an honesty note, not a claim of regression.
- **Modal position while scrolled**: covered by the same teleport tests above. **Stable per template inspection.**
- **Save-and-continue state preservation / variant data preservation**: `_product_form_initial()` is explicitly documented (in its own docstring) as existing specifically to prevent silent field-reset bugs on the `keep_open` path; both the initial GET and the `keep_open` re-render call the same function. **Stable per code inspection.**
- **Product-type auto-continue**: `maybeAutoContinueToVariants()` still gates on `isNewProduct && productType==='variable' && !autoContinuing` plus non-empty name/sku/category, and still fires a hidden submit button rather than duplicating the real submit path. **Stable per code inspection.**

No new bugs were introduced or discovered in the current architecture during this read-only investigation.

---

## 8. UI-only gaps (Classification A/B — safe, reversible, no backend change)

1. Split the "نوعِ کالا" tab into two tabs (category / price+variants) to match the prototype's 5-step shape exactly — pure `product_form.html` + `_PRODUCT_WIZARD_FIELD_STEPS` change.
2. Reorder/relabel tabs to prototype's exact Persian labels and step numbers (۱..۵).
3. Add a `*`/`اختیاری` visual convention (red star + pill + one-time legend) matching the prototype instead of the current `?`-tooltip convention.
4. Add an inline "assign image to this variant" shortcut affordance next to the read-only thumbnail in the variant table (deep-link to the existing gallery modal, pre-filtered to that variant) — purely template/JS, no new backend endpoint (the endpoints already exist: `product-image-variant`, `product-image-option-value`).
5. Move "موجودی" (simple-product stock) out of the collapsed "تنظیماتِ تکمیلی" section into the top-level simple-product box, matching the prototype's visibility.
6. Optionally add a manual table/card view toggle for the variant list (current already reflows responsively without one; this would only be for literal UI parity, not a functional gap).

## 9. Backend-required gaps (Classification D)

1. **`Product.unit`** (واحد شمارش) — new required `CharField`/`choices` field + migration + form field + template field + (likely) storefront display update.
2. **`Product.model_code`** (مدل یا کد فنی) — new optional `CharField` + migration + form field + template field.
3. **`Product.country_of_origin`** (کشور سازنده) — new optional `CharField` + migration + form field + template field.
4. **Product-level SKU auto-generation** ("تولید" button) — no such helper exists today (only variant-level `generate_variant_sku`); needs a new small service function plus an `hx-post` (or pure client-side scheme, but the current SKU-uniqueness constraint is server-side, so a server round-trip is the safe choice) and a button in `product_form.html`.

None of these four are architecturally risky in isolation — each is an additive nullable/defaulted field or a small pure function. Risk is rated per §15.

## 10. Architecture conflicts (Classification E)

Only one true conflict was identified, and it is the "second group" field — analyzed in full in §11. No other prototype element conflicts with the current architecture; every other difference is either additive (new optional field) or a reversible UI reorganization.

---

## 11. "Second group" (گروه دوم) — unresolved architecture decision

**This section is analysis only. Nothing here should be implemented without an explicit follow-up decision from the user.**

### What the current architecture actually supports

`Product.category` (models.py:141) is a single `ForeignKey(Category, on_delete=models.PROTECT)` — **not nullable, not M2M, not multi-valued in any way**. `ProductForm.clean_category()` further enforces that the selected category must be a leaf (`leaf_categories(store)` queryset, per `catalog_admin_service`), and `product_category_select.html`'s own help text states this explicitly to the user ("فقط زیرگروهِ نهایی... قابلِ انتخاب است"). There is no secondary category relation anywhere in `apps/catalog/models.py` — confirmed by a full line-by-line read of the model file, not inferred from naming conventions.

**A product currently has exactly one final category. Full stop. There is no architectural ambiguity in the current system — the ambiguity would only be introduced if "second group" were implemented naively.**

### What the prototype's "second group" actually is

Critically, the prototype's `گروه دوم` field is **not a second taxonomy level** — its example option values in the HTML ("پیشنهاد ویژه" / "جدیدترین‌ها" — "Special Offer" / "Newest") are **merchandising-collection labels**, semantically closer to the existing `ProductTag` / `Product.tag` (marketing tag: new/hot/sale) concept than to `Category`. This distinction matters enormously for the safest implementation path, because it changes the entire recommendation:

- If "second group" means **"a second, independent taxonomy path"** (e.g., a product classified simultaneously under "Electronics" *and* "Gifts"), that is a genuine data-model change: it would require either an M2M `Product.categories` (deprecating the single `category` FK, a breaking change touching every query, template, and service that currently assumes `product.category` is singular — dozens of call sites across `catalog`, `dashboard`, `storefront`, `storefront_builder`) or a new, clearly-scoped second FK (e.g., `Product.secondary_category`, additive, non-breaking, but semantically confusing next to a real multi-level tree).
- If "second group" means **"a merchandising collection/badge"** (which the prototype's actual example values suggest), the **safest and lowest-risk implementation is to extend the existing `ProductTag` mechanism** (or add a second, purpose-scoped tag dimension, e.g. `Product.merchandising_tags`) rather than touching `Category` or `Product.category` at all. This requires no changes to the category tree, no changes to any query that filters by `product.category`, and no risk to tenant-isolation or storefront-listing logic that currently assumes one category per product.

### Safest recommendation (not an implementation — a recommendation only)

Do not add a second `Category` relationship to `Product`. If "second group" is confirmed by the user to mean a merchandising/collection concept, model it as an extension of the existing tag system, not the category system — this reuses `ProductTag`'s existing store-scoped uniqueness, its safe-archive-not-hard-delete pattern, and requires zero changes to any of the ~dozens of places `product.category` is currently treated as singular. If the user confirms it must instead be a true second independent taxonomy axis, that is a substantially larger, higher-risk project (Classification E, estimated HIGH-VERY HIGH risk — see §15) that should be scoped and approved as its own initiative, separate from the rest of this gap-fill work, precisely because of its blast radius across query code, tenant-isolation checks (`Category.clean()`'s store-ownership check would need to be duplicated for a second relation), and the storefront category-browsing UI.

**This item remains an unresolved decision, exactly as instructed. No field, migration, form change, or template change for "second group" is included in this report's implementation recommendations.**

---

## 12. Security / tenant-isolation impact

None of the identified UI-only gaps (§8) touch any query boundary. All four backend-required gaps (§9) are new scalar fields on `Product`, which is already store-scoped (`Product.store` FK) and already validated in `Product.clean()` for cross-store FK leakage on `vendor`/`category`/`brand`/`tax_class` — a new plain `CharField` (unit, model_code, country_of_origin) carries no FK, so it introduces **no new tenant-isolation surface**. The SKU-generation helper must reuse the existing store-scoped uniqueness check pattern already present in `ProductForm.clean_sku()` (`Product.objects.filter(store=self.store, sku=sku)`) rather than a global uniqueness check — this is a design constraint for whoever implements item §9.4, not a currently-existing risk.

The one item with genuine tenant-isolation risk *if implemented carelessly* is "second group" (§11), specifically if implemented as a second `Category` FK: it would need the exact same `store_id` cross-check that `Product.clean()` already does for `category` (line 227-228 of `models.py`), and if implemented as an M2M it would need equivalent validation on every add/remove path, not just `full_clean()`. This is called out explicitly because M2M-through validation is easy to under-implement (Django does not run `clean()` automatically on M2M changes the way it does on `save()`).

---

## 13. Performance / query impact

- UI-only gaps (§8): zero query impact — pure template/JS reorganization.
- New scalar fields (§9.1–9.3): zero query impact — same row, no new joins.
- SKU auto-generation (§9.4): one additional `SELECT` (uniqueness probe) per generation click, store-scoped and indexed via the existing `uniq_product_sku_per_store` constraint — negligible.
- The existing variant-image resolution path (`ProductVariant.display_image` → `storefront_variant_service.resolve_display_image`) already guards against N+1 by using `self.images.all()`/`self.option_values.all()` (not `.filter()`) so it relies on prefetch — this is pre-existing, already-correct behavior (confirmed by the docstring and code in `models.py:529-548`), not something this analysis needs to flag as a gap.
- "Second group," **if** ever implemented as an M2M, would introduce a real N+1 risk on any listing page that renders per-product category chips unless `prefetch_related` is added everywhere `Product.objects` is listed — this is one more reason it is flagged HIGH risk in §15 rather than being treated as a simple additive change.

---

## 14. Test coverage impact

Current product-entry test files (`apps/dashboard/tests/`, all present, none touched by this report):
`test_product_views.py`, `test_product_variant_views.py`, `test_product_options_views.py`, `test_product_options_library_and_sales_limit.py`, `test_product_image_views.py`, `test_product_attribute_form_views.py`, `test_product_quick_add.py`, `test_product_list_bulk_actions.py`, `test_product_form_wizard_steps.py`, `test_product_modal_positioning.py`.

Every UI-only gap in §8 and every backend gap in §9 would need new/updated tests in this existing suite (no new test file categories required — they fit the existing breakdown). The "second group" item, if it ever proceeds, would need an entirely new test file given its cross-cutting nature (`test_product_multi_category_views.py` or similar) plus updates to any existing test that asserts `product.category` singularity.

---

## 15. Risk matrix

| Change | Risk | Rationale |
|---|---|---|
| Split "نوعِ کالا" tab into 2 tabs (category / price+variant) | LOW | Pure template reorg; `_PRODUCT_WIZARD_FIELD_STEPS` already separates `category` from `price/discount_percent/...` at the dict level, so error-routing needs only a label change, not new logic |
| Required/optional visual convention (star/pill/legend) | LOW | CSS + template only |
| Inline variant-image assign shortcut | LOW | Reuses existing endpoints (`product-image-variant`, `product-image-option-value`); no new backend surface |
| Move simple-product stock out of collapsed section | LOW | Template-only reposition |
| `Product.unit` field | MEDIUM | New required field needs a sane default/migration strategy for existing rows (existing products have no unit value); must decide whether to make it required-for-new-only or backfill a default for all existing rows |
| `Product.model_code` field | LOW | Optional field, trivially additive |
| `Product.country_of_origin` field | LOW | Optional field, trivially additive |
| Product-level SKU auto-generation | LOW | New pure function + one endpoint; no schema change |
| "Second group" as tag/collection extension | MEDIUM | Additive, but needs care not to conflate with existing `Product.tag`/`ProductTag` semantics; needs a product decision on relationship to existing tag system before scoping |
| "Second group" as true second category axis (M2M or 2nd FK) | **VERY HIGH** | Breaks the single-category assumption baked into dozens of call sites (storefront listing, category-browsing, breadcrumbs, category-schema attribute resolution, tenant-isolation checks in `Product.clean()`), requires new N+1-safe query patterns everywhere, and changes the meaning of "a product's category" platform-wide — this is a new initiative, not a gap-fill |

---

## 16. Recommended staged implementation order (if/when approved)

Each stage is independently testable and revertible on its own; none depends on "second group" being resolved.

1. **Stage A (UI-only, no migration):** required/optional visual convention + move simple-product stock to top level + inline variant-image assign shortcut. Fully reversible by template revert alone.
2. **Stage B (UI-only, no migration):** split "نوعِ کالا" into 2 tabs to reach literal 5-step parity; update `_PRODUCT_WIZARD_FIELD_STEPS` labels only (no key changes needed since `category` already routes independently of `price`/`discount_percent`/etc.).
3. **Stage C (additive migration):** add `Product.model_code` and `Product.country_of_origin` as optional fields — lowest-risk schema change, no default-value dilemma since both are optional with empty-string defaults.
4. **Stage D (additive migration, needs a product decision on default):** add `Product.unit` — requires the user/product owner to decide the migration default for existing rows (e.g., default to "عدد" for all pre-existing products) before this stage starts.
5. **Stage E (small new service + endpoint):** product-level SKU auto-generation button.
6. **Stage F (blocked on §11 decision):** "second group" — cannot be staged until the user confirms which of the two interpretations in §11 applies; if confirmed as a tag/collection extension, it would be its own small stage; if confirmed as a true second taxonomy axis, it needs a separate scoping/planning pass before any staging is possible.

---

## 17. Exact files likely to change (by stage, forward-looking only — none touched in this report)

- Stage A/B: `apps/dashboard/templates/dashboard/partials/product_form.html`, `apps/dashboard/templates/dashboard/partials/product_options_body.html`, `apps/dashboard/static/css/admin.css`, `apps/dashboard/views.py` (`_PRODUCT_WIZARD_FIELD_STEPS` labels only)
- Stage C/D: `apps/catalog/models.py`, a new migration under `apps/catalog/migrations/`, `apps/dashboard/forms.py` (`ProductForm`), `apps/dashboard/views.py` (`_product_form_initial`, `_save_product` — not read line-by-line in this report but implied by symmetry with existing fields), `product_form.html`, possibly `apps/catalog/templates/catalog/product_detail.html` (storefront display) — **not verified in this report; must be located fresh at implementation time, not assumed**
- Stage E: `apps/catalog/services/` (new function, likely alongside `variant_engine_service.generate_variant_sku` or as a new product-scoped sibling), `apps/dashboard/views.py`, `apps/dashboard/urls.py`, `product_form.html`
- Stage F: entirely dependent on the §11 decision; not enumerable yet

---

## 18. Proposed commit breakdown (forward-looking only)

1. `docs: analyze final product-entry prototype gaps` — this report (the only commit this phase produces)
2. *(future, on approval)* `product-entry: required/optional visual convention + inline variant-image shortcut`
3. *(future, on approval)* `product-entry: split category and price/variant into separate wizard steps`
4. *(future, on approval)* `catalog: add optional model_code and country_of_origin fields to Product`
5. *(future, on approval)* `catalog: add unit field to Product` (with explicit migration default decision recorded in the commit message)
6. *(future, on approval)* `product-entry: product-level SKU auto-generation`
7. *(future, on approval, blocked on §11)* second-group implementation, scope TBD

---

## 19. Open decisions requiring user approval

1. **"Second group" semantics** (§11): merchandising-collection extension of the tag system, vs. a true second independent category axis? This determines whether it is a MEDIUM-risk small stage or a VERY-HIGH-risk new initiative.
2. **`Product.unit` migration default** for existing rows: backfill a default value (which one?) vs. leave blank/optional for pre-existing products and required only going forward?
3. **Literal 5-step parity vs. current 4-tab grouping**: does the user want the wizard's step *count* to exactly match the prototype (Stage B), or is the current category-inside-price-tab grouping acceptable as an intentional simplification?
4. **SKU auto-generation scheme**: what generation strategy is wanted (e.g., prefix + incrementing counter, prefix + random suffix, slugified-name-based)? The existing variant-level `generate_variant_sku` is not directly reusable as-is (it is scoped to a variant's value labels, not a bare product).
5. **Required/optional visual convention**: adopt the prototype's star+pill+legend literally, or keep the current tooltip-based convention (which already conveys the same information, just differently)?

---

## 20. Final recommendation

The current Product Entry flow is not "behind" the approved prototype in capability — in nearly every area that both surfaces cover, the current implementation is equal to or more capable than the prototype (rich text, tags, video validation, media management, variant engine robustness, publication controls). The genuine, actionable gaps are narrow and mostly additive: three missing scalar fields (`unit`, `model_code`, `country_of_origin`), one missing convenience action (SKU auto-generate), and a handful of low-risk visual/structural reorganizations to reach literal step-for-step parity with the prototype's 5-tab shape. All of these can be staged safely per §16 with no architectural risk.

The one item that must not be implemented without further explicit direction is "second group" (§11): its correct implementation path is entirely contingent on a product decision this report cannot make on the codebase's behalf, and choosing the wrong one (a second `Category` relation instead of a tag/collection extension) would be a expensive-to-reverse architectural mistake given how many places in the codebase currently assume `product.category` is singular.

**No code was changed to produce this report. Awaiting explicit approval before any implementation stage begins.**
