# RastiSi Product Entry — Final Implementation Plan

**Type:** Planning only. No application code, template, CSS, JavaScript, model, migration, form, view, service, URL, or test was changed to produce this document.
**Inputs:** the approved prototype (`rastisi-product-entry-prototype-final-v2.html`) and the accepted gap report (`docs/reports/PRODUCT_ENTRY_FINAL_PROTOTYPE_GAP_ANALYSIS.md`).
**Status:** Plan complete. Awaiting explicit user approval before any implementation stage begins.

---

## 1. Executive summary

This plan turns the 18 resolved product decisions in the approval message into ten small, independently reversible commits. Nothing here is architecturally risky in isolation: three of the four schema changes are additive optional fields, the fourth (`unit`) is an additive required field with a safe default-backfill, "second group" is resolved as a `purpose` discriminator on the existing `ProductTag` model rather than a new relation, SKU generation is a pure function copying an already-proven pattern (`attribute_service._unique_code`, `variant_service.generate_variant_sku`), and every richer capability the current app already has beyond the prototype (rich text, video validation, drag-reorder media, the multi-axis variant engine, publish scheduling) is explicitly preserved, not replaced. The only genuinely new backend surface is a `purpose` field on `ProductTag` and one new small SKU-generation service function; everything else is either a template reorganization or an additive nullable/defaulted column.

---

## 2. Approved decisions (restated for traceability)

| # | Decision | Resolution |
|---|---|---|
| 1 | Wizard shape | Exactly 5 steps, tabs above the form, same order on all breakpoints |
| 2 | Required/optional convention | Small red star for required; small neutral "اختیاری" pill for optional; one short legend at the top |
| 3 | "Second group" | Not a second category axis. Renamed **مجموعه‌های فروش** (merchandising collections). Reuses `ProductTag` with a new `purpose` discriminator |
| 4 | Unit of measurement | New `Product.unit` field, existing rows default to `عدد`, Django `choices` (Option A — see §6) |
| 5 | Model/technical code | New optional `Product.model_code`, distinct from SKU |
| 6 | Country of origin | New optional `Product.country_of_origin`, independent of `Brand.country` |
| 7 | SKU generation | Server-validated `PRD-XXXXXX` random-suffix generator, store-scoped uniqueness, bounded collision retry (Option 1 — see §7) |
| 8 | Category UX | Real 3-level tree (group → category → leaf) preserved exactly; prototype's 2-button visual language mapped honestly onto it (see §8) |
| 9 | Brand UX | Existing inline quick-add reused; relabeled as "+ افزودن برند"; no second modal system |
| 10 | Variants | Multi-axis engine (`variant_engine_service`) preserved fully; no prototype-only JS logic replaces it |
| 11 | Variant table/card | Both views on desktop (user-switchable); cards-primary, no page-wide horizontal scroll on mobile |
| 12 | Variant images | Existing 3-tier priority preserved and extended with a documented 2-tier fallback; existing gallery modal reused via a shortcut, not replaced |
| 13 | Media | All current advanced capabilities preserved (upload, cover, drag-reorder, alt/caption, video validation) |
| 14 | SEO/publication | All current capabilities preserved (status, visibility, publish_at, checklist) |
| 15–18 | Plan format, commit granularity, fragile-area protection, final report | Addressed throughout this document |

---

## 3. Final five-step UX

Tabs, in this exact order, rendered as a horizontal strip **above** the form body (not a right-side rail, on any breakpoint):

| # | Key | Label | Contents (source of truth: current templates, reorganized) |
|---|---|---|---|
| 1 | `basic` | اطلاعات پایه | name, SKU (+ "تولید" generator button), icon, brand (+ "+ افزودن برند"), status, tags (ordinary), description (CKEditor5) |
| 2 | `category` | دسته‌بندی | category tree picker (+ "افزودن گروه اصلی" / "افزودن زیرگروه"), مجموعه‌های فروش picker, unit, model_code, country_of_origin |
| 3 | `price` | قیمت و تنوع | simple/variable toggle, price/discount (via existing "Set Price" modal), stock, product-type-conditional attribute/variant manager (existing `product_options_body.html`), advanced/logistics `<details>` (tax class, barcode, weight, requires_shipping) |
| 4 | `media` | تصاویر و فیلم | images (dropzone, gallery, cover, drag-reorder, alt/caption), video (YouTube/Aparat validated) |
| 5 | `seo` | سئو و انتشار | SEO title, slug, meta description, preview box, visibility, publish_at, publish-readiness checklist |

This is a **template-only reorganization**: `product_form.html`'s `tabs` array becomes `[['basic','اطلاعات پایه'], ['category','دسته‌بندی'], ['price','قیمت و تنوع'], ['media','تصاویر و فیلم'], ['seo','سئو و انتشار']]`, and the `{% include "dashboard/partials/product_category_select.html" %}` block moves out of the current `tab === 'price'` section into a new `tab === 'category'` section. `_PRODUCT_WIZARD_FIELD_STEPS` in `views.py` (currently mapping `category` → `"price"`) is updated to map `category` → `"category"` — a one-line change, since the dict already separates `category` from `price`/`discount_percent`/etc. as independent keys (verified in the gap report, §2). No other field's step mapping changes.

**Required/optional convention** (Decision #2): a new `.required-star` (small red `*`, reusing the existing `--red` CSS variable already used for form errors) and `.opt-pill` (small neutral pill, reusing the existing `--surface2`/`--border`/`--muted` tokens already used for tag chips) replace the current per-field `?` tooltip-only convention. One `.field-legend` line ("* = ضروری، اختیاری = می‌توانید بعداً هم پر کنید" or equivalent) appears once, directly under the step strip, above step 1's content. The existing `?` tooltips are **kept** (they carry help text the star/pill do not), so this is additive, not a replacement of the current affordance.

---

## 4. Final data model changes

All in `apps/catalog/models.py`, class `Product`, all additive (nullable/defaulted, no field removed or renamed):

```python
class Product(TimeStampedModel):
    class Unit(models.TextChoices):
        PIECE = "piece", "عدد"
        PACK = "pack", "بسته"
        PAIR = "pair", "جفت"
        SET = "set", "ست"
        METER = "meter", "متر"
        SQUARE_METER = "sqm", "مترمربع"
        LITER = "liter", "لیتر"
        MILLILITER = "ml", "میلی‌لیتر"
        GRAM = "gram", "گرم"
        KILOGRAM = "kg", "کیلوگرم"
        STRAND = "strand", "شاخه"
        ROLL = "roll", "رول"
    ...
    unit = models.CharField("واحد شمارش", max_length=12, choices=Unit.choices, default=Unit.PIECE)
    model_code = models.CharField("مدل یا کد فنی", max_length=80, blank=True, default="")
    country_of_origin = models.CharField("کشور سازنده", max_length=80, blank=True, default="")
```

And in `ProductTag` (Decision #3 — see full design in §5):

```python
class ProductTag(TimeStampedModel):
    class Purpose(models.TextChoices):
        GENERAL = "general", "برچسبِ عادی"
        COLLECTION = "collection", "مجموعه‌ی فروش"
    ...
    purpose = models.CharField("کاربرد", max_length=12, choices=Purpose.choices, default=Purpose.GENERAL)
```

No changes to `ProductVariant`, `ProductOption`, `ProductOptionValue`, `VariantOptionValue`, `ProductImage`, `ProductVideo`, `Category`, `Brand`, or `Attribute`/`AttributeValue` — none are required by any of the 18 decisions.

**Migration:** one migration, e.g. `apps/catalog/migrations/0031_product_unit_model_code_country_of_origin_producttag_purpose.py` (next sequence number after the existing `0030_industrytemplate_default_section_keys.py`), containing four `AddField` operations. `unit` uses `default=Product.Unit.PIECE` at the migration level (Django writes this as a real default for existing rows, satisfying "existing products must safely default to عدد" with zero data migration/backfill script needed — a plain schema-level default is sufficient and is the same mechanism already used for `Product.status`/`Product.product_type`/`Product.visibility` in this exact model). `model_code`, `country_of_origin`, and `ProductTag.purpose` use empty-string/`GENERAL` defaults respectively — no backfill needed for any of the four fields.

---

## 5. Merchandising collection design ("second group" resolution)

**Storage semantics:** no new model, no new join table. `ProductTag.purpose` (new field, §4) discriminates the *same* `Product.tags` M2M relation into two logical uses:
- `purpose="general"` (default) — ordinary free-text tags, exactly today's behavior, unaffected by this change (existing rows get `purpose="general"` via the field default, so no ordinary tag silently becomes a collection).
- `purpose="collection"` — merchandising collections, seeded once (not user-arbitrary at first, see below) with: پیشنهاد ویژه, جدیدترین‌ها, پرفروش‌ها, تخفیف‌دارها, انتخاب سردبیر, مناسب هدیه. Seeding happens the same way `IndustryTemplate` content is seeded today — an idempotent management command or data migration, store-scoped, created once per store (a decision for the implementer: seed globally per-store at store-provisioning time, or lazily on first use of the collections picker; **this exact seeding trigger point is left as an open question in §20**, since it depends on onboarding-flow code not read as part of this plan).

**UI distinction between ordinary tags and collections:**
- Step 1 (اطلاعات پایه) "برچسب‌ها" section: **unchanged**, its `<input>`/chip UI/`tagSuggestions` datalist queries `ProductTag.objects.filter(store=store, purpose="general")` only (currently unfiltered — this is the one query-level change needed here).
- Step 2 (دسته‌بندی) gains a **new, visually distinct** "مجموعه‌های فروش" sub-section, placed directly under the category tree picker with its own sub-heading and a one-line explanatory caption ("این‌ها برای نمایش کالا در بخش‌های ویژه‌ی فروشگاه استفاده می‌شوند، نه دسته‌بندی — کالا هنوز دقیقاً یک دسته‌بندی نهایی دارد."), rendered as multi-select chips (checkbox-style, since a product may belong to multiple collections, unlike category which is singular) sourced from `ProductTag.objects.filter(store=store, purpose="collection")`, with a "+ افزودنِ مجموعه‌ی فروش" quick-add reusing the same small form pattern as `product_quick_add_brand` (a name-only form, `purpose` hardcoded server-side to `"collection"`).
- Both sections write to the same `Product.tags` M2M field on submit (the existing `ProductForm.tags` hidden-input/chip-join mechanism is reused for collections too, or — safer to avoid conflating two different Alpine chip-state arrays in one hidden field — a **second** hidden input/field, e.g. `collection_tags`, cleaned the same way `ProductForm.clean_tags()` already cleans `tags`, then merged server-side in the view before the M2M `.set()` call). This plan recommends the **second hidden field** approach to keep the two Alpine `x-data` chip arrays (`tags` vs `collectionTags`) independent and avoid one clearing the other on a partial re-render.

**Tenant isolation:** unchanged — `ProductTag` is already `store`-scoped with `UniqueConstraint(fields=["store", "code"])`; the `purpose` field carries no cross-store reference and needs no new `clean()` check.

**Filtering behavior:** any admin-side "filter products by tag" UI (if one exists — not verified in this investigation, flagged in §20) would need to filter its own tag-picker dropdown by `purpose="general"` to avoid surfacing collections as if they were ordinary tags, and vice-versa for a future "filter by collection" admin view.

**Storefront usage:** out of scope for this phase's *implementation* (the prototype and gap report only cover the admin entry form), but the design is forward-compatible: a future storefront "collection page" (e.g. `/products/?collection=pishnahad-vizhe`) would filter `Product.objects.filter(tags__purpose="collection", tags__code=...)`, the same query shape already implied by `storefront_listing_products()` in `product_publish_service.py`. **This plan does not implement any storefront-facing collection page** — only the admin-side field, picker, and storage.

---

## 6. Unit-field design

| Option | Description | Pros | Cons |
|---|---|---|---|
| A. Fixed Django `choices` | `CharField(choices=Unit.TextChoices)` on `Product`, exactly like the existing `status`/`product_type`/`visibility` fields on the same model | Zero new tables; matches an established, working pattern in this exact model; trivial safe default (`PIECE`); adding a new unit later is a one-line code change + no-op migration (no DB-level enum, so old rows with an old choice value remain valid) | Not merchant-customizable without a code deploy |
| B. Free text + suggested `<datalist>` | Plain `CharField`, no `choices`, with an HTML `<datalist>` of the same 12 suggested values (mirrors the existing tag-suggestion `<datalist>` pattern in `product_form.html`) | Fully flexible, zero schema constraint | Allows inconsistent values ("بسته" vs "بسته‌بندی" vs typos) with no server-side normalization — directly undermines any future "filter by unit" or storefront unit-aware logic |
| C. Store-scoped reusable `Unit` model | New model (`store` FK, `name`, `is_active`, `sort_order`), `Product.unit` becomes a FK, seeded with the 12 defaults per store like `Warehouse`'s `provision_default_warehouses` pattern | Fully merchant-customizable, sortable, most "correct" long-term | New model + migration + CRUD UI + seeding command + FK on `Product` + cross-store validation in `Product.clean()` — meaningfully larger scope than requested; overengineering for a field the user described as needing 12 fixed starting values, not merchant-authored ones |

**Recommendation: Option A.** It satisfies "existing products must safely default to عدد" with a plain migration default (no backfill script), matches the model's own established convention for exactly this kind of field, and remains "extensible" in the sense the instructions require — extensible by a maintainer adding a new choice, not by a merchant self-service form, which was not asked for. If merchant-customizable units become a real requirement later, Option C is a clean, non-breaking upgrade path (the `CharField` values could be migrated into a `Unit` table's `code` column 1:1).

---

## 7. SKU-generation design

| Option | Description | Pros | Cons |
|---|---|---|---|
| 1. Random alphanumeric suffix | `PRD-` + 6 random chars (excluding ambiguous `0/O/1/I`), generated via `django.utils.crypto.get_random_string` (already imported and used in `product_image_service.py` for gallery filenames — no new dependency), checked against `Product.objects.filter(store=store, sku=candidate).exists()`, regenerated on collision up to a bounded retry count (e.g. 10) | No shared mutable state, safe under concurrent requests without any locking, matches the user's requested format exactly, mirrors the already-proven `attribute_service._unique_code()` / `variant_service.generate_variant_sku()` "generate → check → retry" pattern already live in this codebase | Non-sequential, not human-meaningful (acceptable — the user's own example `PRD-A7K29Q` is explicitly non-sequential) |
| 2. Store-scoped counter | A `next_product_sequence` counter (new field, likely on `Store` or a new small counter model), incremented per product | Sequential, human-readable | Genuine race condition under concurrent product creation unless wrapped in `select_for_update()` row locking — a new locking pattern not currently used anywhere for this purpose in the codebase; exactly the "race-condition-prone" risk the instructions explicitly warn against |
| 3. Slug/name-derived code | Transliterate the product name into a Latin-ish code | No dependency on request timing | No reliable Persian→Latin transliteration exists in the codebase today; the SKU-generate button is meant to be usable *before* a name is necessarily finalized; produces inconsistent-length codes; doesn't match the requested fixed `PRD-XXXXXX` format |

**Recommendation: Option 1.** New function `generate_product_sku(store)` in a new small service module `apps/catalog/services/product_sku_service.py` (one function, mirrors the codebase's one-file-per-concern convention already visible across `apps/catalog/services/`), returning a candidate string; the "تولید" button in step 1 calls this via a new lightweight `hx-post` endpoint (`dashboard:product-sku-generate`) that returns just the generated value for the SKU `<input>` (not a full form re-render), since generation has no side effects worth round-tripping the whole form for. The merchant can edit the field afterward exactly like today (it is a plain `<input name="sku">`, generation only pre-fills it). **Variant SKUs already derive safely from the product SKU** — `variant_service.generate_variant_sku(product, value)` already builds `f"{product.sku}-{slugify(value)}"` with its own counter-suffix-on-collision (verified by direct read of `variant_service.py:55-68`) — so **no change is needed to variant SKU generation**; it automatically picks up whatever SKU the product ends up with, since it always reads `product.sku` live at variant-creation time, not a cached value.

---

## 8. Category/brand design

**Category — architecture preserved exactly as-is.** No change to `Category` (self-referencing tree), `ProductQuickCategoryForm`, `product_quick_add_category` view, `leaf_categories()`/`category_tree_context()`, or the cross-store `clean()` check in `Category.clean()`. The real hierarchy is **3 levels** (group → category → leaf subcategory), and the product only ever attaches to the leaf. This is represented **honestly**, not flattened to match the prototype's 2-field visual (گروه اصلی / زیرگروه) by hiding a level — instead, the existing tree-picker (which already lets a merchant navigate all 3 levels and select the leaf in one interaction) is kept as the primary selection UI, and the two requested buttons are mapped onto **specific entry points into the existing, already-tested 3-step quick-add modal** (`product_category_select.html`'s `#quickAddModal`) rather than becoming two independent flat dropdowns:

- **"افزودن گروه اصلی"** opens the existing quick-add modal at **step 1** (new top-level group name only) — functionally identical to what happens today when a merchant starts the quick-add flow with no group selected.
- **"افزودن زیرگروه"** opens the same modal **pre-advanced to step 2**, with the currently-selected group (if any) pre-filled, so the merchant is one step closer to creating just the missing category/leaf under an existing group instead of restarting the whole 3-step flow. This is a **new, small piece of Alpine state** (an optional `startAtStep` param passed when the button dispatches the modal-open event) — the only genuinely new interaction logic in this section; the underlying form, view, and validation are 100% reused.

This means: **the honest answer to "how will these buttons work" is that they are two different entry points into one existing, already-stable 3-step modal, not two new independent single-level creators.** No new endpoint, no new form, no new service function.

**Brand — reuse only.** "+ افزودن برند" replaces the current inline panel's toggle label; the underlying mechanism (`product_brand_select.html`'s inline quick-add, `product_quick_add_brand` view, `BrandForm`, `create_brand()` in `brand_service.py`) is unchanged. No modal is introduced for brand (kept as the current inline pattern, since the current app's inline pattern is functionally equivalent to the prototype's modal per the gap report's §6 classification — Classification A, cosmetic only) — a modal is *not required by the approval*, so this plan does not add one, avoiding an unrequested second brand-creation UI.

---

## 9. Variant architecture preservation

No changes to `apps/catalog/services/variant_engine_service.py`, `ProductOption`, `ProductOptionValue`, `VariantOptionValue`, or `ProductVariant`. Explicitly reused, unmodified: arbitrary per-product attributes via `add_product_option`, the store Attribute Library reuse path (`library_attributes` / `product-option-add-from-library`), free-text values, `generate_variants()`'s idempotent Cartesian generation with `combination_key`-based preservation (already proven more robust than the prototype's content-hash approach — see gap report §6), `MAX_OPTION_AXES` duplicate/explosion prevention, independent `sku`/`price`/`compare_at_price`/`discount` per variant, independent `stock`, `is_active`, `sales_limit`/`sales_limit_min`, `is_default` — all unchanged. The legacy single-axis system (`variant_service.py`, `/variants/` URLs) is untouched and remains reachable only for pre-existing legacy data, exactly as documented in the gap report §4.

**UI-only additions** (template/JS, `product_options_body.html`):
- A one-line, live-computed explanation above the attribute cards, e.g. `۳ طول × ۲ جنس = ۶ تنوع`, computed the same way `combination_preview` is already computed server-side (`preview_combination_count()` is already called and rendered as `{{ combination_preview }}` today — this is a **template-only formatting change**, not a new calculation, to spell out the multiplication instead of just showing the final count).
- Each attribute card gets a subtly different background (cycling through 3–4 pre-defined soft tint tokens by card index, pure CSS `nth-child`/inline `style` — no new state).
- The "+ افزودنِ ویژگی جدید" button moves to below the existing attribute-card list (currently it renders after the library-attribute chips but the toggle button itself is already positioned there — verify exact current DOM order at implementation time; if already below the list, this is a no-op).

---

## 10. Variant image design

**Priority chain preserved and clarified** (currently 3-tier in `storefront_variant_service.resolve_display_image()` and `ProductVariant.display_image`): 1) exact variant image (`ProductImage.variant`), 2) attribute-value image (`ProductImage.option_value`), 3) product cover image (`ProductImage.is_cover`). The approval's 5-step list additionally names "4. first gallery image" and "5. safe placeholder" — these are **already implicitly covered**: `Product.cover_image` (the property `resolve_display_image` falls back to) already falls back to `images[0]` when no image is flagged `is_cover` (verified in `models.py`'s `Product.cover_image` property, gap report §2), and the template layer already renders a plain `—`/muted placeholder span when `variant.display_image` is `None` (verified in `product_options_body.html`'s variant table `<td data-label="تصویر">`). So the "5-tier" language in the approval is **the existing 3-tier backend priority plus two already-existing template-level fallbacks** — no backend change is needed to satisfy it; this plan will document the full 5-step chain explicitly in code comments at implementation time so it reads as one deliberate chain rather than two separately-evolved layers.

**Shortcut from variant row/card to image assignment:** a new small button/icon in each variant row (`product_options_body.html`) and each future variant card (§11), next to the existing read-only thumbnail, that opens the **existing** gallery modal (`dashboard:product-images`, `product_images_modal.html`) — reused via the same `hx-get`/`modalOpen=true` pattern already used by the existing "🖼️ مدیریتِ تصاویر و اختصاصِ تصویر به تنوع" button at the bottom of the variant table — with a **new, small addition**: a URL query parameter (e.g. `?highlight_variant=<id>`) so `product_images_modal.html`/`product_images_list.html` can auto-scroll to and visually highlight the gallery image currently assigned to that variant (or show an empty-state hint if none is assigned yet), making the "shortcut" meaningfully faster than the existing bottom button without duplicating the assignment UI itself. **No new endpoint for assignment** — `product-image-variant`/`product-image-option-value` (existing, already validated for cross-product ownership in `product_image_service.set_image_variant`/`set_image_option_value`) are reused unchanged.

**Immediate table/card reflection:** since assignment happens via `hx-post` targeting `#productImagesList` with `hx-swap="outerHTML"` (existing), and the variant table itself is a **separate** `#productOptionsBody` fragment, the two are not currently wired to refresh each other. This plan adds a small `hx-trigger` custom event (`variant-image-changed`) fired by the gallery modal's image-variant/option-value select `hx-post` responses (via `HX-Trigger` response header, the same mechanism already used elsewhere in this app for toast/modal-close signaling — e.g. `product_form`'s `response["HX-Trigger"] = json.dumps(...)`), which the variant table listens for (`hx-trigger="variant-image-changed from:body"` on a hidden refresh element, or a targeted `hx-get` to re-render just the affected row) so the thumbnail updates without requiring the merchant to close the gallery modal and manually reopen the price/variant tab. This is the one genuinely new piece of client-server wiring in this whole plan (small, additive, uses only patterns already present elsewhere in the same codebase).

**Cross-store and cross-product validation:** already enforced (`ProductImage.clean()` checks `variant.product_id == product_id`; `set_image_variant`/`set_image_option_value` raise `ProductImageError` on mismatch) — no change needed.

**N+1 prevention:** already handled — `Product.cover_image`, `ProductVariant.display_image`, and `resolve_display_image()` all deliberately use `.all()` on already-prefetched relations rather than `.filter()` (verified, gap report §2/§13). The new highlight-shortcut adds no new query pattern (it reads the same already-loaded `image.variant_id`/`image.option_value_id` fields, just compares them against a query-string id client-side/template-side).

---

## 11. Responsive design

**Desktop:** both table and card views available, user-switchable via a toggle mirroring the prototype's `variant-view-switch`, persisted only in local Alpine state (not server-side) for the duration of the modal session — no new field needed.

**Mobile:** cards are the **primary** representation; no page-wide horizontal scroll, no dependency on a wide table.

**Reuse-vs-new-partial decision:** the current `.variant-table-responsive` CSS (verified in `admin.css:546-562`) already achieves a card-like stacked reflow below 768px **automatically**, without any explicit "card view" markup — each `<td data-label="...">` becomes a labeled stacked row via `content:attr(data-label)`. This already satisfies "no page-wide horizontal scrolling" and "cards as primary representation" **today**, confirmed by live Playwright verification in the gap-analysis phase (zero horizontal overflow at 390px). However, it does **not** give the desktop-only explicit table/card *toggle* the approval also requires — that is a genuinely new, separate view mode (a true card grid, not a CSS reflow of the table), matching the prototype's `#variantCardGrid`.

**Recommendation:** build one **new, separate card-grid partial** (e.g. `product_variant_cards.html`, rendered from the same `active_variants` queryset/context `product_options_body.html` already has — no new view, no new query) for the desktop-toggle "card view," and **keep** the existing `.variant-table-responsive` CSS reflow as the mobile behavior (i.e., on mobile, always render the table markup, which already visually presents as cards via CSS — do not force the new desktop card-grid partial onto mobile, since it was not built/tested for touch target sizing the way the existing reflow already was in the earlier session's mobile pass). This avoids maintaining two different card renderings for two different purposes, at the cost of the desktop "card view" and the mobile "card-like view" not being pixel-identical — an acceptable, explicitly-stated tradeoff, not a hidden inconsistency.

---

## 12. Implementation stages

Each stage is independently testable, independently revertible (its own commit, §17), and stages are ordered so nothing depends on a later stage. Dependencies are called out explicitly.

### Stage 1 — Five-step shell + required/optional visual convention
- **Depends on:** nothing.
- **Model/migration:** none.
- **Forms:** none.
- **Views:** `views.py` — `_PRODUCT_WIZARD_FIELD_STEPS` (`category` key's value changes from `"price"` to `"category"`).
- **Templates:** `product_form.html` — `tabs` array (5 entries), move the `product_category_select.html` include from the `price` section to a new `category` section, add `.required-star`/`.opt-pill`/`.field-legend` markup to every field label.
- **CSS:** `admin.css` — `.required-star`, `.opt-pill`, `.field-legend` (new, small rules using existing tokens).
- **JS/Alpine/htmx:** none beyond the existing `tab`/`tabIndex`/`goPrevTab`/`goNextTab` machinery, which is step-count-agnostic already.
- **Endpoints:** none new.
- **Tests:** update `test_product_form_wizard_steps.py` (step count/order/labels now 5, category tab key now `category`).
- **Rollback:** revert the single commit; no migration to reverse.

### Stage 2 — Brand/category action placement
- **Depends on:** Stage 1 (category now lives in its own tab).
- **Model/migration:** none.
- **Views:** none (reuses `product_quick_add_category`, `product_quick_add_brand` unchanged).
- **Templates:** `product_category_select.html` (two labeled buttons + `startAtStep` param), `product_brand_select.html` (relabel toggle to "+ افزودن برند").
- **JS/Alpine:** small `startAtStep` state addition in `product_category_select.html`'s quick-add modal Alpine component.
- **Endpoints:** none new.
- **Tests:** extend `test_product_quick_add.py` to cover opening the modal at step 2 pre-filled.
- **Rollback:** revert the single commit.

### Stage 3 — Unit / model_code / country_of_origin fields + migration
- **Depends on:** nothing (independent of Stages 1–2, but sequenced after them here to land schema changes after the shell is stable).
- **Model:** `Product.unit` (choices), `Product.model_code`, `Product.country_of_origin` (§4).
- **Migration:** one new migration, additive `AddField`s, schema-level defaults, no data migration/backfill script.
- **Forms:** `ProductForm` gains `unit` (ChoiceField), `model_code`, `country_of_origin` (CharFields, `required=False` for the latter two).
- **Views:** `_product_form_initial()` gains the three new keys (mirrors every other existing field in that function).
- **Templates:** `product_form.html` — three new fields in the `category` tab (per §3's placement).
- **Endpoints:** none new.
- **Tests:** extend `test_product_views.py` for create/edit round-trips of the three fields; a migration test is not needed (no data transformation to verify beyond Django's own tested `AddField` machinery).
- **Rollback:** revert the migration (`migrate catalog 0030`) then revert the commit; safe because no other code depends on these columns yet at this stage.

### Stage 4 — Product SKU generator
- **Depends on:** nothing structurally, sequenced after Stage 3 for narrative order only.
- **Model/migration:** none (`Product.sku` already exists).
- **Services:** new `apps/catalog/services/product_sku_service.py` — `generate_product_sku(store)` (§7).
- **Views:** new `product_sku_generate(request)` view (store-scoped, `staff_required` + `permission_required(PRODUCT_CREATE, PRODUCT_EDIT)`, mirrors the auth decorators already on every other product-entry view).
- **URLs:** new `products/sku/generate/` → `dashboard:product-sku-generate`.
- **Templates:** `product_form.html` — "تولید" button next to the SKU field, `hx-post` to the new endpoint, `hx-target` the SKU `<input>` itself (`hx-swap="outerHTML"` on a small wrapper, or `hx-swap="none"` + a tiny Alpine handler setting the field value — either is acceptable; recommend `hx-swap="none"` + `hx-on::htmx:after-request` reading the plain-text response into `x-model`, since the SKU field also participates in `maybeAutoContinueToVariants()`'s ref-based reads and a full swap would need to preserve `x-ref="skuField"` wiring).
- **Tests:** new focused test asserting format (`PRD-` + 6 chars), store-scoped uniqueness, and collision-retry behavior (simulate an existing colliding SKU and assert a different candidate is returned).
- **Rollback:** revert the single commit; the new URL/view/service are fully additive and nothing else calls them.

### Stage 5 — Merchandising collection semantics and UI
- **Depends on:** Stage 1 (category tab exists to host the picker), Stage 3 not required but reasonable to land after it.
- **Model:** `ProductTag.purpose` (§4/§5).
- **Migration:** additive `AddField`, default `"general"` (existing tags unaffected).
- **Forms:** `ProductForm` gains `collection_tags` (mirrors `clean_tags()`'s parsing, `required=False`); a new tiny `ProductCollectionQuickAddForm` (name-only, mirrors `ProductQuickAttributeForm`'s shape) for the "+ افزودنِ مجموعه‌ی فروش" action.
- **Views:** `views.py` — tag-suggestion query filtered by `purpose="general"`; a new `product_quick_add_collection` view (mirrors `product_quick_add_brand`'s shape almost exactly); `_save_product`'s tag-assignment step (wherever it currently calls `.tags.set(...)`, not read line-by-line in this plan — **must be located fresh at implementation time**, flagged honestly rather than assumed) extended to also `.set()`/`.add()` the collection tags from `collection_tags`.
- **URLs:** new `products/quick-add-collection/` (and a `pk`-scoped variant, mirroring the existing brand/category quick-add URL pairing).
- **Templates:** new "مجموعه‌های فروش" sub-section in the `category` tab (§5).
- **Seeding:** a small idempotent management command or data migration seeding the 6 suggested collection names per store — **exact trigger point (store creation time vs. lazy-on-first-use) is an open question, §20.**
- **Tests:** new `test_product_collections.py` covering: ordinary-tag query excludes collections and vice versa, tenant isolation (`purpose` carries no cross-store leakage risk but the picker's queryset must still be store-scoped), quick-add-collection creates a `purpose="collection"` tag.
- **Rollback:** revert the migration and commit; existing `ProductTag` rows keep working exactly as before (their new `purpose` column simply defaults to `"general"`).

### Stage 6 — Attribute-card visual separation and button placement
- **Depends on:** nothing (independent, cosmetic).
- **Templates:** `product_options_body.html` — per-card background tint by index, live "۳ طول × ۲ جنس = ۶ تنوع" phrasing, confirm/adjust "+ افزودنِ ویژگی جدید" position (§9).
- **CSS:** `admin.css` — 3–4 tint tokens.
- **Tests:** template-rendering assertion (new small test in `test_product_options_views.py`) that the multiplication phrasing appears when ≥2 axes exist.
- **Rollback:** revert the single commit.

### Stage 7 — Variant table/card switch
- **Depends on:** Stage 6 (shares the same template file, sequenced to avoid merge friction, not a hard dependency).
- **Templates:** new `product_variant_cards.html` partial (§11); `product_options_body.html` gains the view-toggle Alpine state and conditionally includes the new partial.
- **Tests:** extend `test_product_options_views.py` to assert both partials render the same variant set consistently (same ids, same fields) when requested.
- **Rollback:** revert the single commit; table view remains the only view if reverted (matches current behavior exactly).

### Stage 8 — Variant-image assignment shortcut
- **Depends on:** Stage 7 (needs the card partial to also carry the shortcut button, not just the table).
- **Views:** the existing `product_images_modal` view gains optional `?highlight_variant=` handling (context flag only, no new query — the variant id is already known, the modal just needs to pass it through to the template for a CSS/JS highlight).
- **Views:** `product_image_variant`/`product_image_option_value` views (existing, unchanged logic) gain an `HX-Trigger: variant-image-changed` response header addition (one line each).
- **Templates:** `product_options_body.html`/`product_variant_cards.html` gain the shortcut button + an `hx-trigger="variant-image-changed from:body"` listener on a small refresh target; `product_images_modal.html`/`product_images_list.html` gain the highlight styling.
- **Tests:** extend `test_product_image_views.py` to assert the `HX-Trigger` header is present on the relevant responses.
- **Rollback:** revert the single commit; the two touched views' extra header line is the only production-code change, trivially revertible.

### Stage 9 — Responsive/mobile fixes
- **Depends on:** Stage 7 (card partial must exist first).
- **Templates/CSS:** confirm/adjust the new card partial's mobile touch-target sizing and confirm the existing `.variant-table-responsive` reflow remains the mobile default (§11) — likely template/CSS-only, no logic changes.
- **Tests:** none new beyond what Stage 7 already covers; this stage is primarily browser-verification (§16), not new automated coverage.
- **Rollback:** revert the single commit.

### Stage 10 — Focused tests and browser fixes
- **Depends on:** all prior stages.
- **Content:** full regression pass, any fixes surfaced by cross-stage interaction (e.g., a Stage 5 collection chip accidentally breaking Stage 1's five-tab layout), full Playwright pass across all fragile areas (§17) and all four breakpoints.
- **Rollback:** this stage should contain no new production behavior, only test additions and micro-fixes — if a micro-fix in this stage turns out to be load-bearing, it should have been its own stage; the plan treats that as a signal to split the commit at implementation time, not a rule violation of "one commit per stage."

---

## 13. Exact file map (aggregated across stages)

| File | Stages touching it |
|---|---|
| `apps/catalog/models.py` | 3, 5 |
| `apps/catalog/migrations/003x_*.py` (new) | 3, 5 |
| `apps/catalog/services/product_sku_service.py` (new) | 4 |
| `apps/dashboard/forms.py` | 3, 5 |
| `apps/dashboard/views.py` | 1, 4, 5, 8 |
| `apps/dashboard/urls.py` | 4, 5 |
| `apps/dashboard/templates/dashboard/partials/product_form.html` | 1, 3, 4 |
| `apps/dashboard/templates/dashboard/partials/product_category_select.html` | 2, 5 |
| `apps/dashboard/templates/dashboard/partials/product_brand_select.html` | 2 |
| `apps/dashboard/templates/dashboard/partials/product_options_body.html` | 6, 7, 8 |
| `apps/dashboard/templates/dashboard/partials/product_variant_cards.html` (new) | 7, 8, 9 |
| `apps/dashboard/templates/dashboard/partials/product_images_modal.html` | 8 |
| `apps/dashboard/templates/dashboard/partials/product_images_list.html` | 8 |
| `apps/dashboard/static/css/admin.css` | 1, 6, 9 |
| `apps/dashboard/tests/test_product_form_wizard_steps.py` | 1 |
| `apps/dashboard/tests/test_product_quick_add.py` | 2 |
| `apps/dashboard/tests/test_product_views.py` | 3 |
| `apps/dashboard/tests/test_product_options_views.py` | 6, 7 |
| `apps/dashboard/tests/test_product_image_views.py` | 8 |
| `apps/dashboard/tests/test_product_collections.py` (new) | 5 |
| `apps/dashboard/tests/test_product_sku_generation.py` (new) | 4 |

Not touched by any stage in this plan: `apps/catalog/services/variant_engine_service.py`, `apps/catalog/services/variant_service.py`, `apps/catalog/services/storefront_variant_service.py`, `apps/catalog/services/product_image_service.py`, `apps/catalog/services/product_video_service.py`, `apps/catalog/services/product_publish_service.py`, `apps/catalog/services/attribute_service.py`, `apps/catalog/services/brand_service.py`, `apps/dashboard/templates/dashboard/partials/product_attribute_fields.html`, `apps/dashboard/templates/dashboard/partials/product_videos_list.html`, `apps/dashboard/templates/dashboard/partials/product_no_category_banner.html` — confirming Decisions #9, #10, #13, #14 (preserve, do not touch) are honored structurally, not just declared.

---

## 14. Migration plan

One migration in Stage 3 (`Product.unit`/`model_code`/`country_of_origin`) and one in Stage 5 (`ProductTag.purpose`) — kept **separate** (not combined into one migration file) so Stage 3 and Stage 5 remain independently revertible per the "small reversible commits" instruction, even though both are pure `AddField` operations that Django could technically bundle. Both migrations use schema-level defaults exclusively — no `RunPython` data migration, no backfill script, no batch `.update()` needed, because every new field is either optional (empty-string default) or has one universally-correct default value (`unit=PIECE`, `purpose="general"`) that is correct for 100% of existing rows without inspection. This is the safest possible migration shape for an additive change and was chosen specifically to avoid the two riskiest migration patterns (long-running data backfills on a large `Product`/`ProductTag` table, and defaults that require per-row business logic to compute).

---

## 15. Test plan

Beyond the per-stage tests listed in §12, the fragile-area guarantees (§17) are covered by **existing, unmodified** tests wherever a stage doesn't touch the relevant code path, and by **extended** versions of the same existing test files wherever a stage does touch it — no fragile area is left to a brand-new, first-time test written after the fact. Full test-file responsibility is enumerated in the table in §13.

---

## 16. Browser-verification plan

For every stage that touches a template or CSS file (all except none — every stage does), a live Playwright pass at exactly the four breakpoints already used in the gap-analysis phase (1440 / 1024 / 768 / 390px), checking:
- `document.documentElement.scrollWidth - clientWidth === 0` (no page-wide horizontal overflow) at every breakpoint, every stage — this is the single most important regression guard given the explicit "no horizontal scrolling" requirement and the fact that Stage 7–9 introduce genuinely new markup (the card partial) that has not been through the earlier session's mobile pass yet.
- Step-strip position (above the form, not right-aligned) at all three breakpoints, specifically re-checked in Stage 1 since it's the stage that changes the tab structure.
- Modal-still-teleported-and-htmx-processed spot check after Stage 2 (quick-add modal gains new `startAtStep` state) and Stage 8 (new `HX-Trigger` wiring) — the two stages most likely to accidentally reintroduce the teleport/htmx-process bugs, since both touch teleported-modal-adjacent code.
- Collection chip add/remove and category-quick-add-after Stage 2 and Stage 5, specifically re-testing the "newly created category/collection immediately appears" scenario the user has twice reported as buggy in earlier turns of this session.
- Variant table↔card consistency (Stage 7) and image-shortcut live-refresh (Stage 8) via direct interaction, not just static screenshot comparison.

---

## 17. Fragile areas — explicit protection

| Fragile area | Protected by | Stage(s) with elevated risk |
|---|---|---|
| `x-teleport` modal positioning | `test_product_modal_positioning.py` (existing, unmodified unless a stage adds a new teleported modal — none in this plan do; the quick-add modal already teleported is only extended with `startAtStep` state, not restructured) | 2 (touches the same modal's Alpine state) |
| `htmx.process` after teleport | Same file, same tests; no stage adds a new `hx-*`-bearing teleported element | 2, 8 |
| Orphaned modal instances | `test_product_modal_positioning.py::test_quick_add_category_submit_closes_modal_before_its_own_swap` (existing, unmodified) | 2 |
| Category quick-add submission | `test_product_quick_add.py` (extended in Stage 2) | 2 |
| Newly created category immediately appearing | Manual + Playwright re-verification (§16); no existing automated test asserts this end-to-end today per the gap report's honesty note (§7) — **this plan recommends adding one** as part of Stage 2's test extension, closing that gap | 2 |
| Save-and-continue state preservation | `_product_form_initial()` (unchanged in every stage except its dict gains 3 new keys in Stage 3 and 1 in Stage 5 — additive, same function, same call sites) | 3, 5 |
| Product-type auto-continue | `maybeAutoContinueToVariants()` (unchanged; Stage 4's SKU-generator must not break the `x-ref="skuField"` wiring this function reads — explicitly called out in Stage 4's template-change note) | 4 |
| Variant data preservation | `variant_engine_service.generate_variants()` (untouched, §9) + existing option/variant tests | — (no stage touches this) |
| Media upload for unsaved products | Untouched (§13's not-touched list); no stage modifies the staged-upload Alpine component | — |
| Variant image fallback | Untouched service logic (§10); only template/wiring additions | 8 |
| Mobile overflow | Playwright horizontal-overflow check (§16), every stage | 1, 7, 9 (highest risk — new markup) |

---

## 18. Commit plan

Exactly ten commits, one per stage in §12, in this order:

1. `product-entry: five-step wizard shell + required/optional visual convention`
2. `product-entry: brand/category quick-add button placement`
3. `catalog: add unit, model_code, country_of_origin fields to Product`
4. `product-entry: product-level SKU generator`
5. `catalog: merchandising collections (ProductTag.purpose) + UI`
6. `product-entry: attribute-card visual separation + button placement`
7. `product-entry: variant table/card view switch`
8. `product-entry: variant-image assignment shortcut`
9. `product-entry: responsive/mobile fixes for variant cards`
10. `product-entry: focused tests + browser-verification fixes`

No stage combines migration + unrelated template work beyond what's listed; no stage is a grab-bag.

---

## 19. Rollback plan

Per-stage rollback is stated in §12 for each stage individually. General principle applied throughout: every stage's commit is revertible with a plain `git revert` **in isolation** because (a) no stage's templates reference a model field or endpoint introduced by a *later* stage, and (b) both migrations (Stage 3, Stage 5) are pure additive `AddField`s with no downstream code depending on them until their own stage's forms/views/templates land in the *same* commit — so reverting Stage 3's commit removes the field, the form field, and the template field together, leaving no dangling reference. If a later stage is reverted but an earlier one is kept (e.g., Stage 8 reverted, Stage 7 kept), the only requirement is that Stage 8's `HX-Trigger` header additions and shortcut button are removed together, which they are (single commit, §18).

---

## 20. Risk matrix

| Item | Risk | Mitigation |
|---|---|---|
| Stage 1 (5-tab restructure) | LOW | Pure template/dict reorg, existing tab machinery is step-count-agnostic, guarded by existing wizard-step test file |
| Stage 2 (category button placement) | LOW | Reuses 100% existing form/view/service; only new surface is a `startAtStep` Alpine variable |
| Stage 3 (unit/model_code/country fields) | LOW | Additive schema, safe defaults, no backfill, no other code depends on the new columns yet |
| Stage 4 (SKU generator) | LOW | New pure function + one thin endpoint; must not disturb `x-ref="skuField"` (explicitly flagged) |
| Stage 5 (collections) | MEDIUM | Genuinely new UI surface (multi-select chip picker distinct from the tag picker) + a seeding-trigger decision still open (§21) — highest-scope stage in this plan |
| Stage 6 (attribute card styling) | LOW | Cosmetic only |
| Stage 7 (table/card switch) | MEDIUM | New template partial not yet browser-verified; must not regress the existing, already-verified `.variant-table-responsive` mobile behavior |
| Stage 8 (image shortcut) | LOW–MEDIUM | New `HX-Trigger` wiring touches two existing, already-load-bearing views — small diff, but must be verified not to break their existing response contract for other callers (if any exist beyond this modal — not verified in this plan, flag for implementation-time check) |
| Stage 9 (mobile fixes) | LOW | Expected to be template/CSS-only by the time it's reached, contingent on Stage 7's card partial being built correctly |
| Stage 10 (tests/fixes) | LOW | By design, should introduce no new production behavior |

---

## 21. Remaining unresolved questions

1. **Collection seeding trigger point** (§5, §12 Stage 5): seed the 6 default merchandising collections at store-provisioning time, or lazily on first use of the picker? Needs a decision before Stage 5 starts (does not block Stages 1–4).
2. **Storefront "browse by collection" pages**: explicitly out of scope for this plan (§5) — confirm this is acceptable, or should a minimal storefront listing be added in a Stage 5.5?
3. **`_save_product`'s exact tag-assignment call site** (§12 Stage 5): not read line-by-line in this plan; must be located fresh in `views.py` at Stage 5 implementation time rather than assumed from this document.
4. **Whether any admin-side "filter products by tag" view currently exists** (§5): not verified in this investigation; if one exists, it needs a `purpose="general"` filter added as part of Stage 5, not a separate follow-up.
5. **Whether any other view beyond `product_images_modal`/`product_image_variant`/`product_image_option_value` currently relies on those two views' exact current response shape** (§20's Stage 8 risk note): should be grepped for at Stage 8 implementation time before adding the new `HX-Trigger` header, to confirm no other caller would be surprised by it (an added response header is normally inert to existing callers, but this is called out for completeness, not because a conflict is expected).

None of these block Stages 1–4; all are scoped to Stage 5 or Stage 8 and can be resolved when those stages are actually approved for implementation.

---

## 22. Final go/no-go recommendation

**Go**, staged exactly as ordered in §12/§18, with Stage 5's two open questions (§21.1–21.2) resolved before Stage 5 specifically begins — every other stage can proceed independently once approved. No stage in this plan requires touching the multi-axis variant engine, the legacy variant system, the image-priority service logic, the video-validation logic, or the publish-scheduling logic — every one of the current app's capabilities that exceeds the prototype (per the accepted gap report) is preserved by construction, not by promise, because the file map in §13 shows those service files are never opened by any stage.

**No code was changed to produce this document. Awaiting explicit approval before Stage 1 (or any stage) begins.**
