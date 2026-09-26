# Phase 1D — Attribute, Product Option, and Multi-Axis Variant Engine Report

**Branch:** `claude/docs-prototypes-review-jxm6aw`
**Status of this report:** factual, scoped status update. The originating
Phase 1D prompt's own "Definition of Complete" (§38) is a long checklist;
every item on it that is genuinely built and tested is claimed below, and
every item that is not is named explicitly in §20/§21 rather than glossed
over. The core Attribute/Option/Variant engine — the prompt's own §2
"Primary Objective" — is real, tested, and production-shaped. One
secondary item the prompt also required (descriptive-attribute assignment
*through the product form UI*) is service-complete but has no dashboard
page; this is the one concrete scope reduction, named up front, not buried.

---

## 1. Executive Summary

**Is the Variant Engine production-ready?** The core engine — Attribute
definitions, Product Options, Option Values, stable multi-axis variant
identity, Cartesian-product generation, idempotent reconciliation that
never loses SKU/price/inventory/images, default-variant management, and a
bulk-edit matrix — is real, persisted, tenant-isolated, permission-gated,
and covered by 127 new automated tests, all passing alongside the
project's full pre-existing suite (2017/2017, 0 failures). It is
production-ready for the scope it covers.

**Major limitations**, precise (full list in §20):

* No dashboard UI for assigning *descriptive* attributes to a product
  (`ProductAttributeValue`) — the model, migration, and service layer are
  complete and tested (31 tests), but there is no product-form section for
  it yet.
* No storefront consumption of the new variant data — this phase builds
  the admin-side engine only, matching the prompt's own explicit "This is
  not... Product form option editor... Attribute admin pages" framing of
  what's in scope; a shopper-facing variant switcher was never in scope for
  this phase or promised by it.
* Axis removal never auto-merges collapsed combinations (by design — see
  ADR-21); a merchant must manually review obsoleted rows.
* A maximum of 3 active option axes per product, chosen and documented
  (§11), not an accidental limit.

**A genuine, unrelated pre-existing bug was found and fixed** during full-
suite validation, not hidden: four data-migration reverse functions across
`orders`, `catalog`, `content`, and `core` were latently unsafe under
backward migration due to Django migration-state ordering fragility — see
§2 and §19.

## 2. Previous Phase Verification

Before any change: confirmed the session's local checkout was stale
(`715252a`, the initial commit) while `origin/claude/docs-prototypes-review-jxm6aw`
already had Phase 1B/1C's work through `40264b3` — fast-forwarded the
local branch to match origin exactly (`git merge --ff-only`), confirming a
clean working tree at `40264b3` before writing any code. Re-ran a focused
baseline (`apps.catalog`, `apps.dashboard.tests.test_product_views`,
`test_product_variant_views`, `test_product_image_views`) — 401 tests, all
passing, confirming Phase 1C's product-list/SEO/variant-image work was
intact before this phase began.

**Defect found during this phase's own full-suite validation (not part of
baseline verification, found only after implementation):** see §19 — four
migration reverse functions (`orders.0004`, `catalog.0007`,
`content.0012`, `core.0006`) had a latent state-consistency bug that this
phase's new `catalog.0011` migration happened to newly expose by changing
the shape of the overall migration dependency graph.

## 3. Prototype Inventory

The prompt names `prototypes/merchant-panel-x25/` as the reference
prototype; no such directory exists in this repository. The actual X25
variant-builder prototype lives at
`docs/docs/product/Final Result At Last/novinshop-video-rich-products/assets/x25-product-variants.js`
(referenced from `product-create.html`/`product-edit.html`), and is
explicitly catalogued as a 2-line file in the project's own prior
blueprint document (`Rastisi_Product_and_Technical_Blueprint_Volume_1.md`,
line 1283: `"X25 | x25-product-variants.js | 2 خط | —"`).

| Prototype capability | Prototype file | Previous state | Final state | Backend | Frontend | Tests | Remaining limitation |
|---|---|---|---|---|---|---|---|
| Add variant attribute (quick-pick + custom name) | `x25-product-variants.js` | Client-only mock, no persistence | Complete | `ProductOption`/`add_product_option` | `product_options_body.html` add-axis form | Yes | Quick-pick buttons (رنگ/سایز/جنس) not reproduced as one-click chips — plain text input instead |
| Add/edit values per attribute (comma-separated input) | same | Client-only mock | Complete | `ProductOptionValue`/`add_option_value` | inline add-value form per axis | Yes | — |
| Remove attribute | same | Client-only (`x25RemoveAttr`, in-memory splice) | Complete, but persisted and safety-checked | `remove_option_value`/`deactivate_product_option` | ✕ button per value chip, "غیرفعال‌سازی محور" button | Yes | Prototype removed instantly with no safety; this phase intentionally soft-deactivates instead (ADR-21) |
| Live combination-count preview | same (`count()` function) | Client-only, recalculated on every keystroke | Complete, but computed server-side per page load (not live-as-you-type) | `preview_combination_count` | shown on options page | Yes | Not live/AJAX-updated as values are typed — recalculated on next full page render, a deliberate simplification (§24 of the prompt explicitly says "do not regenerate on every keystroke") |
| Generate variant table (Cartesian product, per-row SKU/price/stock/image) | same (`table()` function) | Client-only mock table, values never saved, image preview via `URL.createObjectURL` (never uploaded) | Complete, persisted | `generate_variants` + bulk matrix editor | `product_options_body.html` variant matrix | Yes | Per-row image assignment reuses the existing Phase 1C image-variant `<select>` (on the images modal), not inline in the matrix — a deliberate reuse of existing UI rather than a third image-picker |
| Attribute definitions (Store-wide, reusable) | *(not in X25 prototype — only per-product ad hoc labels)* | Did not exist at all | Complete | `Attribute`/`AttributeValue` | `/admin-portal/attributes/` full CRUD | Yes | — |
| Descriptive (non-variant) product attributes | *(not in X25 prototype)* | Did not exist at all | Service-complete, no UI | `ProductAttributeValue`/`attribute_service` | ✕ (not built) | Yes (service layer) | **Named gap** — see §20 |

Per the prompt's blueprint document (`Rastisi_Product_and_Technical_Blueprint_Volume_1.md`,
"Variant Engine" section, lines 857–866), the target design explicitly
calls for: variant axes selectable from `AttributeDefinition`; server-side
generation with combinatorial-explosion control; SKU/barcode/price/compare
price/cost/stock/weight/image/status per variant; variant image mandatory
for color scenarios; duplicate-SKU/duplicate-variant/invalid-option
guards; a default sellable unit for non-variant products; bulk/matrix
editing; and a guarded/migration-aware Attribute deletion UX. Every one of
these is implemented and tested in this phase (mapped to the model/service
names above), confirming this phase's design matches the project's own
prior target specification, not just the prompt's literal wording.

## 4. Domain Model

See ADR-19/20/21 in `SAAS_DOMAIN_DECISIONS.md` for full reasoning; summary:

* **`Attribute`** (Store-owned): `code` (unique per Store), `label`,
  `description`, `data_type` (text/number/boolean/select/multiselect/
  color/date), `display_type` (validated against `data_type`), `unit`,
  `is_required`/`is_filterable`/`is_searchable`/`is_comparable`,
  `is_variant_axis` (eligibility, not commitment — ADR-19), optional
  `category` scoping, `display_order`, `is_active`.
* **`AttributeValue`**: `attribute` FK, `label`, `value` (internal code,
  auto-filled from label), `color_hex`, `display_order`, `is_active`,
  duplicate-label prevention scoped to active values per attribute.
* **`ProductAttributeValue`** (descriptive assignment): `product` +
  `attribute` + optional `value` FK, plus typed scalar fields
  (`text_value`/`number_value`/`boolean_value`) — one row per
  product+attribute for scalar/select types, multiple rows for
  multiselect.
* **`ProductOption`** (variant-generating axis, per-Product): `attribute`
  (optional link back to the Store's `Attribute` catalog), `label`,
  `position` (unique per Product), `is_active`. Max 3 active axes per
  Product (`MAX_OPTION_AXES`, §11).
* **`ProductOptionValue`**: `option` FK, `label`, `color_hex`,
  `display_order`, `is_active`, optional link to a catalog `AttributeValue`.
* **`VariantOptionValue`** (stable combination identity, ADR-20): one row
  per `(ProductVariant, ProductOption, ProductOptionValue)`.
* **`ProductVariant`** (existing model, extended): new fields
  `combination_key` (derived, sorted-value-ID join, empty for legacy
  single-axis variants), `compare_at_price`, `cost`, `barcode`,
  `low_stock_threshold`, `track_inventory`, `weight_grams`, `length_mm`/
  `width_mm`/`height_mm`, `is_default`, `is_obsolete`. Two new
  `UniqueConstraint`s: `(product, combination_key)` when non-blank, and
  `(product)` when `is_default=True`.

## 5. Variant Generation

`apps.catalog.services.variant_engine_service.generate_variants(product)`:

1. **Input**: the Product's active `ProductOption` axes, ordered by
   `position`, each with its active `ProductOptionValue`s.
2. **Cartesian product**: `itertools.product(*value_lists)` over the axes
   in position order.
3. **Identity**: each combination's `combination_key` is a sorted join of
   its `ProductOptionValue` primary keys (ADR-20) — independent of axis
   order or label text.
4. **Creation**: a combination present in *desired* but not *existing*
   gets a new `ProductVariant` + `VariantOptionValue` rows, an
   auto-generated SKU (reusing `variant_service.generate_variant_sku`),
   and generated `attribute`/`value` display strings (joined axis/value
   labels) for backward-compatible display.
5. **Idempotency**: verified by test — a second call with no option
   changes creates nothing, obsoletes nothing, reports every existing
   variant as "preserved."
6. **Ordering**: `display_order` is recomputed deterministically on every
   call from the Cartesian-product iteration order (axis position, then
   value `display_order`).
7. **Default variant**: `_ensure_default_variant` promotes the first
   eligible (active, non-obsolete) variant to `is_default=True` if none
   currently holds it — using the same "steal the flag" pattern as
   `product_image_service.set_cover_image`.

Verified with a 3-axis × 5-value-each case (125 combinations, prompt §31's
explicit example) — 125 variants created, zero duplicate `combination_key`
values, generation and idempotent rerun both correct
(`test_large_combination_set_125_variants`,
`test_idempotent_rerun_creates_nothing`).

## 6. Variant Reconciliation

All scenarios from the prompt's §13–§17 are implemented per ADR-21's
never-hard-delete policy, and each has a dedicated passing test:

| Scenario | Behavior | Test |
|---|---|---|
| Add a value | Only the new combinations are created; existing ones untouched | `test_add_value_creates_only_missing_variants` |
| Remove a value | Its combinations are marked `is_obsolete=True`, `is_active=False` — never deleted | `test_remove_value_marks_obsolete_not_deleted` |
| Rename a value's label | No `combination_key` change, same variant PK/SKU preserved | `test_rename_value_does_not_recreate_variant` |
| Rename an axis's label | No `combination_key` change, all variant PKs preserved | `test_rename_option_does_not_recreate_variants` |
| Reorder axes | Combination identity (sorted-key based) is order-independent; SKU/price/stock preserved | `test_reorder_options_preserves_variant_identity` |
| Remove an axis entirely | All combinations that included it are obsoleted; remaining axis's combinations regenerate at the reduced dimensionality | `test_removing_axis_obsoletes_all_its_combinations` |
| Re-add a previously removed value | The *original* variant row is restored (obsolete flag cleared), not duplicated | `test_re_adding_removed_value_restores_original_variant_not_a_duplicate` |
| Regeneration after manual edits | Merchant-set SKU/price/stock survive regeneration untouched | `test_preserves_price_inventory_and_images_on_regeneration` |
| Variant image across regeneration | `ProductImage.variant` assignment survives regeneration | `test_variant_image_survives_regeneration` |
| Default variant when its combination is obsoleted | A deterministic replacement is auto-promoted | `test_default_reassigned_when_current_default_becomes_obsolete` |

## 7. Models

**Created**: `Attribute`, `AttributeValue`, `ProductAttributeValue`,
`ProductOption`, `ProductOptionValue`, `VariantOptionValue` (all in
`apps/catalog/models.py`).

**Modified**: `ProductVariant` — 12 new fields (§4), 2 new
`UniqueConstraint`s, `display_image` property unchanged (still works for
both legacy and multi-axis variants since it operates on `self.images`,
independent of how the variant was created).

**Relationships**: `Attribute.store` → `stores.Store` (CASCADE);
`Attribute.category` → `catalog.Category` (SET_NULL, optional);
`AttributeValue.attribute` → `Attribute` (CASCADE);
`ProductAttributeValue.product`/`.attribute`/`.value` → CASCADE/PROTECT/
PROTECT (an `Attribute`/`AttributeValue` in use cannot be hard-deleted —
§9); `ProductOption.product` → CASCADE, `.attribute` → PROTECT, optional;
`ProductOptionValue.option` → CASCADE; `VariantOptionValue.variant` →
CASCADE, `.option` → CASCADE, `.option_value` → **PROTECT** (a value still
backing a variant's identity can never be hard-deleted, only
soft-deactivated — the DB itself enforces ADR-21's policy, not just the
service layer).

**Constraints**: `uniq_attribute_code_per_store`,
`uniq_active_attribute_value_label`, `uniq_product_attribute_value`,
`uniq_option_position_per_product`, `uniq_active_option_label_per_product`,
`uniq_active_option_value_label`, `uniq_variant_option_axis`,
`uniq_variant_option_value`, `uniq_variant_combination_key_per_product`,
`uniq_default_variant_per_product`.

## 8. Migrations

One migration: `apps/catalog/migrations/0011_attribute_option_variant_engine.py`
— purely additive (6 new models + 12 new nullable/blank/defaulted fields
on `ProductVariant` + constraints), no backfill needed, no data loss
possible, fully reversible (confirmed — see §19, where this migration's
addition to the dependency graph is precisely what exposed an *unrelated*
pre-existing reverse-migration bug, itself now fixed).
`makemigrations --check --dry-run` confirms it exactly matches model
state throughout the phase.

**Unplanned migration-safety fix** (§19 has full detail):
`apps/orders/migrations/0004_backfill_orders_store.py`,
`apps/catalog/migrations/0007_backfill_catalog_store.py`,
`apps/content/migrations/0012_backfill_footer_store.py`,
`apps/core/migrations/0006_backfill_shopsettings_store.py` — each restricts
its Akhlaghi-Store lookup query to `.only("pk")` and (for `orders.0004`)
gained an explicit `stores` dependency, fixing a genuine backward-migration
correctness bug this phase's new migration exposed.

## 9. Services

* **`apps.catalog.services.attribute_service`**: `create_attribute`/
  `update_attribute`/`archive_attribute`/`activate_attribute`/
  `can_delete_attribute`/`delete_attribute`, the equivalent set for
  `AttributeValue`, `reorder_attribute_values`, and
  `set_product_attribute_value`/`add_product_attribute_multiselect_value`/
  `remove_product_attribute_value` for descriptive assignments. Every
  mutating function wraps in `@transaction.atomic`; every cross-Store
  reference (`category`, in `set_product_attribute_value`'s `attribute`)
  is validated before write.
* **`apps.catalog.services.variant_engine_service`**: `add_product_option`/
  `add_option_value`/`remove_option_value`/`deactivate_product_option`/
  `activate_product_option`/`reorder_product_options`/
  `reorder_option_values`, `preview_combination_count`, `generate_variants`
  (the core engine, §5–§6), `set_default_variant`. `generate_variants` and
  `set_default_variant` are `@transaction.atomic`; `add_product_option`
  blocks the legacy/multi-axis mixed-mode case (ADR-20).

Views remain thin: `apps/dashboard/views.py`'s new view functions
(`attribute_*`, `product_option_*`, `product_variants_generate`,
`product_variants_bulk_update`) only resolve the Store-scoped object(s),
call a service function, and render — no Cartesian-product or
reconciliation logic lives in a view.

## 10. Routes and APIs

All routes below require `@staff_required` (admin-host + authenticated +
active membership) and a `@permission_required(...)` (`ATTRIBUTE_MANAGE`
for Attribute routes, `VARIANT_MANAGE` for Product Option/variant routes)
— both pre-existing decorators from Phase 1B/1C, reused unmodified.

| Method | Route | Permission | Store scoping |
|---|---|---|---|
| GET | `/admin-portal/attributes/` | `ATTRIBUTE_MANAGE` | `Attribute.objects.filter(store=store)` |
| GET | `/admin-portal/attributes/table/` | `ATTRIBUTE_MANAGE` | same (HTMX partial for search/filter) |
| GET/POST | `/admin-portal/attributes/add/` | `ATTRIBUTE_MANAGE` | new row scoped to `request.store` |
| GET/POST | `/admin-portal/attributes/<pk>/edit/` | `ATTRIBUTE_MANAGE` | `get_object_or_404(..., store=store)` |
| POST | `/admin-portal/attributes/<pk>/archive/` \| `/activate/` \| `/delete/` | `ATTRIBUTE_MANAGE` | same |
| GET | `/admin-portal/attributes/<pk>/values/` | `ATTRIBUTE_MANAGE` | same |
| POST | `/admin-portal/attributes/<pk>/values/add/` | `ATTRIBUTE_MANAGE` | same |
| POST | `/admin-portal/attributes/<pk>/values/<value_id>/archive/` \| `/delete/` | `ATTRIBUTE_MANAGE` | `AttributeValue` filtered through `attribute` (also store-scoped) |
| GET | `/admin-portal/products/<pk>/options/` | `VARIANT_MANAGE` | `_get_scoped_product` (store-scoped) |
| POST | `/admin-portal/products/<pk>/options/add/` | `VARIANT_MANAGE` | same |
| POST | `/admin-portal/products/<pk>/options/<option_id>/deactivate/` \| `/activate/` \| `/move/` | `VARIANT_MANAGE` | `ProductOption` filtered through `product` |
| POST | `/admin-portal/products/<pk>/options/reorder/` | `VARIANT_MANAGE` | `product.options.filter(pk__in=...)` — foreign IDs silently excluded |
| POST | `/admin-portal/products/<pk>/options/<option_id>/values/add/` | `VARIANT_MANAGE` | same |
| POST | `/admin-portal/products/<pk>/options/values/<value_id>/remove/` | `VARIANT_MANAGE` | `ProductOptionValue` filtered through `option__product` |
| POST | `/admin-portal/products/<pk>/options/generate/` | `VARIANT_MANAGE` | `generate_variants(product)` — product already store-scoped |
| POST | `/admin-portal/products/<pk>/options/variants/<variant_id>/default/` | `VARIANT_MANAGE` | `ProductVariant` filtered through `product` |
| POST | `/admin-portal/products/<pk>/options/bulk-update/` | `VARIANT_MANAGE` | `product.variants.filter(pk__in=variant_ids)` — foreign variant IDs silently excluded (tested, §13) |

All POST endpoints are CSRF-protected via Django's standard middleware
(no endpoint opts out); errors surface as an HTMX toast
(`HX-Trigger: {"toast": {...}}`) with the same pattern every other
dashboard view in this codebase already uses — no new error-response shape
introduced.

## 11. UI

* **Attribute pages** (`attributes.html` + partials): search/type-filter/
  status-filter list, add/edit modal (mirroring the existing
  `product-add` modal pattern), per-attribute values management modal
  (add/archive/delete, color swatch preview for `color` type).
* **Product Option editor** (`product_options.html` +
  `product_options_body.html`): axis cards with up/down reorder, per-axis
  activate/deactivate, inline add-value form, add-axis form with optional
  bulk initial values (reusing `parse_bulk_values` from the existing
  single-axis variant service); combination-count preview; a single
  "تولید / تطبیق تنوع‌ها" (generate/reconcile) button with an `hx-confirm`
  warning before the action runs (prompt §24's "show a warning before
  destructive reconciliation").
* **Variant matrix / bulk editor**: one form covering every active
  variant — SKU, barcode, extra_price, compare_at_price, cost, stock,
  active checkbox, default-variant button per row; a single submit saves
  the whole batch atomically (§13's tenant-isolation test proves a
  cross-Store variant ID smuggled into the same POST is silently ignored).
* **Obsolete-combinations table**: read-only, shown only when non-empty,
  so a merchant always sees what a reconciliation retired.
* **Legacy-mode banner**: if a Product still has legacy single-axis
  variants, the options page shows an explanatory banner and a link to the
  existing variant-management page instead of the new editor — never a
  silent no-op or a confusing empty state.
* Navigation: a new "ویژگی‌ها" sidebar entry, gated by
  `can_manage_attributes` in `apps.dashboard.context_processors.merchant_permissions`
  (same pattern as every existing nav entry).
* Responsive/accessible: reuses the existing design system's `.card`/
  `.btn`/`.inp`/`.badge`/`.chip` classes and form-group markup verbatim —
  no new CSS, no new JS framework, consistent with every other dashboard
  page in this codebase.

## 12. Permissions

No new permission keys — `ATTRIBUTE_MANAGE` already existed in
`apps.stores.authorization` since Phase 1B (defined, role-mapped, but
literally unused — no view existed to attach it to). This phase is the
first to actually attach it to a view. `VARIANT_MANAGE` (also pre-existing)
is reused for all Product Option/variant-generation routes, consistent
with it already covering the legacy variant-management views.

Role mapping (unchanged from Phase 1B, verified by test): OWNER and
ADMINISTRATOR get both keys via `ALL_PERMISSIONS`/`ALL_PERMISSIONS -
_OWNER_ONLY`; CATALOG_MANAGER gets both via `_CATALOG_READ_WRITE`;
ORDER_MANAGER, CONTENT_EDITOR, and ANALYST get neither. Tested per role in
both `test_attribute_views.py` and `test_product_options_views.py`
(Catalog Manager allowed, Analyst/Order Manager/Content Editor denied
with 403, no-membership and wrong-Store-membership denied with a redirect
to `catalog:home`, anonymous denied with a login redirect).

## 13. Tenant Isolation

Every new query resolves through `request.store` or a Store-scoped parent
— never a raw submitted ID. Verified with dedicated adversarial tests:

* Attribute from another Store assigned as a Product's category or option
  attribute → rejected (`AttributeError_`/`VariantEngineError`,
  `test_cross_store_attribute_rejected` in both service test files).
* `ProductOption`/`ProductOptionValue` for another Store's Product,
  addressed by ID → 404 (`test_other_product_option_404s`,
  `test_remove_value_from_other_product_404s`).
* Bulk variant-matrix update: a Store A request submitting Store B's
  variant ID alongside its own → Store B's row is provably untouched
  (`test_bulk_update_tenant_isolation`) — the exact "bulk-action foreign
  IDs" adversarial case the prompt's §27/§34.10 names explicitly.
* `Attribute`/`AttributeValue` addressed by ID from another Store → 404
  (`test_other_store_attribute_404s`, `test_value_from_other_store_attribute_404s`).
* A user with a valid membership in a *different* Store, or `is_staff=True`
  with *no* membership at all → redirected, never served the page
  (`test_wrong_store_membership_denied`, `test_staff_without_membership_denied`,
  present in both new view test files).

No issues found beyond what these tests were written to catch — every
adversarial case attempted was already correctly rejected by the
resolve-through-`request.store` discipline this codebase's decorators
(`staff_required`, `_get_scoped_product`) already enforce.

## 14. Security

* **Authorization**: `staff_required` + `permission_required` on every new
  view, no exceptions (§12).
* **Host enforcement**: inherited unchanged from Phase 1C's admin-host
  enforcement — every new view resolves through the same
  `resolve_store_for_admin_request`-backed `staff_required`.
* **CSRF**: standard Django middleware, no view opts out.
* **Input validation**: all numeric/monetary fields go through
  `normalize_digits` + explicit type conversion with try/except before
  reaching a model field (`product_variants_bulk_update`); all `full_clean()`
  calls on model instances before save; `ModelChoiceField`-style
  queryset-restriction pattern reused for the `category` field on
  `AttributeForm`.
* **Media validation**: unchanged — variant images continue to go through
  Phase 1C's `product_image_service` validated upload pipeline; this phase
  adds no new upload path.
* **Remaining risk**: none newly introduced that adversarial testing
  surfaced; the same known, pre-existing limitations from Phase 1B/1C
  (coarse-grained `MEDIA_MANAGE`/`VARIANT_MANAGE` permission keys, no
  dedicated CSRF-specific test coverage anywhere in this codebase) apply
  equally here, unchanged.

## 15. Performance

* `generate_variants` for the prompt's own named stress case (3 axes × 5
  values = 125 combinations) creates all 125 variants correctly with no
  duplicate `combination_key`s (`test_large_combination_set_125_variants`).
  Not formally profiled/benchmarked (no query-count assertions were added
  for this specific test) — the prompt's instruction to "not claim
  benchmark results unless actually measured" is honored by not claiming
  any specific number here.
* `generate_variants` uses `bulk_create` for `VariantOptionValue` rows (one
  bulk insert per new variant's axis values, not N individual `.save()`
  calls) and a single `bulk_update` pass for `display_order` recomputation
  across all preserved+created variants per call — not one UPDATE per row.
* The Product Options page prefetches `product.options.all().order_by(...)
  .prefetch_related("values")` and each variant's `option_values__option`/
  `option_values__option_value` — avoiding an N+1 per axis/value/variant
  row on page render (mirroring the exact N+1 fix pattern Phase 1C's own
  validation pass already established for the legacy variant page).
* No pagination added to the variant matrix — for a Product with a very
  large variant count (beyond the 125-combination test case) the bulk-edit
  form would render every active variant on one page. This is a known,
  named limitation (§20), not a claim of unlimited scalability.

## 16. Tests

127 new tests across 4 new files, all passing individually and as part of
the full 2017-test suite:

| File | Scope | Count |
|---|---|---|
| `apps/catalog/tests/test_variant_engine_service.py` | Option/value CRUD, generation, reconciliation (every scenario in §6), default-variant rules, image preservation, field-contract/validation | 46 |
| `apps/catalog/tests/test_attribute_service.py` | Attribute/value CRUD, archive/delete-guard, descriptive assignment for every data type, cross-Store rejection | 31 |
| `apps/dashboard/tests/test_attribute_views.py` | List/filter, add/edit/archive/delete, values sub-CRUD, permissions per role, tenant isolation | 24 |
| `apps/dashboard/tests/test_product_options_views.py` | Page rendering, option/value CRUD via HTTP, generate, default-variant, bulk-update (incl. tenant isolation + validation), permissions per role | 26 |

Exact commands executed and results (all real, all executed in this
session — none assumed or carried over):

```text
python manage.py check                              → System check identified no issues (0 silenced)  [run repeatedly through the phase]
python manage.py makemigrations --check --dry-run   → No changes detected  [run repeatedly through the phase]
python manage.py migrate                             → all pending migrations applied OK
```

| Batch | Tests | Result |
|---|---|---|
| Focused baseline before implementation (`apps.catalog` + 3 product/variant/image view files) | 401 | OK |
| `test_variant_engine_service.py` (iterative, caught 2 real bugs — §19) | 42→46 | OK (after fixes) |
| `test_attribute_service.py` | 31 | OK |
| `test_attribute_views.py` | 23→24 | OK (after 2 fixture bugs fixed) |
| `test_product_options_views.py` | 25→26 | OK |
| All four Phase 1D test files together | 127 | OK |
| **First full suite** (`python manage.py test`) | 2017 | **1 error** — migration-state bug, §19 |
| `apps.stores.tests.test_data_migration` (isolated, after first-line-item fix attempt) | 2 | **still failing** — fix was incomplete, root cause misdiagnosed on first attempt |
| Same, after the real fix (`.only("pk")` in all four affected migrations) | 2 | OK |
| `apps.stores.tests.test_data_migration` + `apps.catalog.tests` + `apps.content.tests` + `apps.core.tests` + `apps.orders.tests` (full regression around the fix) | 957 | OK |
| **Full suite, final** (`python manage.py test`) | 2017 | **OK — 0 failures, 0 errors** |

The migration bug (§19) is the one real defect this phase's own validation
caught — reported here, including the failed first fix attempt, not
hidden or smoothed over.

## 17. Files Created

* `apps/catalog/migrations/0011_attribute_option_variant_engine.py`
* `apps/catalog/services/attribute_service.py`
* `apps/catalog/services/variant_engine_service.py`
* `apps/catalog/tests/test_attribute_service.py`
* `apps/catalog/tests/test_variant_engine_service.py`
* `apps/dashboard/templates/dashboard/attributes.html`
* `apps/dashboard/templates/dashboard/product_options.html`
* `apps/dashboard/templates/dashboard/partials/attribute_form_modal.html`
* `apps/dashboard/templates/dashboard/partials/attribute_values_list.html`
* `apps/dashboard/templates/dashboard/partials/attribute_values_modal.html`
* `apps/dashboard/templates/dashboard/partials/attributes_table.html`
* `apps/dashboard/templates/dashboard/partials/product_options_body.html`
* `apps/dashboard/tests/test_attribute_views.py`
* `apps/dashboard/tests/test_product_options_views.py`
* `docs/docs/product/reports/PHASE_1D_ATTRIBUTE_VARIANT_ENGINE_REPORT.md` (this file)

## 18. Files Modified

* `apps/catalog/models.py` — 6 new models, `ProductVariant` extended (§7)
* `apps/dashboard/forms.py` — `AttributeForm`, `AttributeValueForm`,
  `ProductOptionForm`, `ProductOptionValueAddForm`
* `apps/dashboard/views.py` — ~40 new view functions (Attribute admin +
  Product Option/variant-engine sections)
* `apps/dashboard/urls.py` — 20 new routes
* `apps/dashboard/context_processors.py` — `can_manage_attributes`
* `apps/dashboard/templates/dashboard/base_admin.html` — nav entry
* `apps/dashboard/templates/dashboard/partials/products_table_inner.html` —
  "محورهای تنوع" link per variable product
* `apps/orders/migrations/0004_backfill_orders_store.py`,
  `apps/catalog/migrations/0007_backfill_catalog_store.py`,
  `apps/content/migrations/0012_backfill_footer_store.py`,
  `apps/core/migrations/0006_backfill_shopsettings_store.py` — migration
  safety fix (§19)
* `docs/docs/product/architecture/SAAS_DOMAIN_DECISIONS.md` — ADR-19,
  ADR-20, ADR-21, summary table
* `docs/docs/product/00_PROJECT_MASTER_REFERENCE.md` — §11.2 Catalog
  updated with the new engine's existing/missing capabilities

## 19. A Real Bug Found and Fixed: Cross-App Migration-State Ordering Fragility

While running the full test suite after all Phase 1D code was in place,
`apps.stores.tests.test_data_migration.AkhlaghiSeedMigrationExecutorTests`
— a pre-existing test that exercises Django's real `MigrationExecutor` to
unapply and reapply the `stores` app's migrations — failed with
`django.db.utils.OperationalError: no such column: stores_store.admin_subdomain`,
raised from inside `apps/orders/migrations/0004_backfill_orders_store.py`'s
reverse function.

**Root cause.** Four data-migration reverse functions
(`orders.0004`, `catalog.0007`, `content.0012`, `core.0006`) resolve the
seeded "Akhlaghi" Store via a plain `Store.objects.get(slug="akhlaghi")`,
using the *historical* `Store` model Django passes into a `RunPython`
reverse function's `apps` parameter — correctly avoiding the project's own
"never import runtime models in migrations" rule on its face. The problem
is one level deeper: Django's `MigrationExecutor._migrate_all_backwards`
builds the historical state passed to each migration being unapplied by
walking the *full forward plan* for the entire migration graph once, in
order, and snapshotting state at each point — and for two migrations with
no dependency edge between them (`orders.0004` never declared any
dependency on `stores`' later migrations), their relative position in that
walk is decided by graph-shape-dependent tie-breaking, not anything
`orders.0004`'s author actually specified. `orders.0004`'s
`Store.objects.get(...)` does an implicit `SELECT *`, so if the state walk
happens to place a *later* `stores` migration (one that adds
`admin_subdomain`) before `orders.0004` in that internal ordering, the
*historical model class* gains a field the *physical* database — being
unapplied in a separately-computed, dependency-respecting order — does not
yet have at the moment this specific `RunPython` actually executes. This
was **always** a latent bug in these four files (pre-dating Phase 1D
entirely); this phase's new `catalog.0011` migration (which correctly
depends on `stores.0005`) changed the shape of the overall migration graph
enough to flip that internal tie-break and expose it for the first time.

**First fix attempt (documented as unsuccessful, not hidden).** Adding an
explicit `("stores", "0002_create_akhlaghi_store")` dependency to
`orders.0004` — the semantically "correct" missing dependency — did *not*
fix the failure on its own (re-running `apps.stores.tests.test_data_migration`
in isolation still failed identically), because that edge does nothing to
prevent `stores.0003`–`0005` from independently floating to an earlier
position in the walk; it only pins `orders.0004` after `stores.0002`, not
before `stores.0003`+.

**Actual fix.** Changed all four `Store.objects.get(slug=...)` call sites
to `Store.objects.only("pk").get(slug=...)` — restricting the SQL `SELECT`
to only the column every one of these functions actually needs (the row's
identity), so the query is correct regardless of which historical fields
the state-walk-provided model class happens to declare. The explicit
`stores.0002` dependency on `orders.0004` was kept (it is still correct
documentation of a real semantic dependency, and does no harm), but the
`.only("pk")` change is what actually resolves the bug. Verified: the
specific failing test now passes in isolation, a 957-test regression pass
across every app whose migrations were touched (`stores`, `catalog`,
`content`, `core`, `orders`) is green, and the full 2017-test suite is
green.

**Why this matters beyond the one test.** This bug would only ever
manifest during an actual backward migration in a real deployment (e.g. a
rollback) — something this codebase's test suite is one of the only
places that ever exercises at all. It was not caused by anything wrong in
this phase's own new migration; `catalog.0011` is a normal, correctly-
dependency-declared, fully-additive migration. It is reported here as an
unplanned discovery, consistent with this session's practice in prior
phases (e.g. Phase 1B's cross-Store dashboard leak, Phase 1C's context-
processor 500) of surfacing real bugs found incidentally rather than
narrowly scoping validation to only the phase's own new code.

## 20. Known Limitations

Named precisely, per the prompt's own instruction not to hide unfinished
behavior:

* **No dashboard UI for descriptive attribute assignment.** `Attribute`/
  `AttributeValue`/`ProductAttributeValue` and the full
  `attribute_service` API (text/number/boolean/select/multiselect
  assignment, validation, removal) are built and have 31 passing tests —
  but there is no product-form section where a merchant can actually use
  this through the dashboard. The prompt's §9 explicitly asked for this to
  be "editable through the product form"; it is editable through the
  service/shell only. This is the single largest scope reduction this
  phase made, named here rather than silently dropped.
* **No storefront consumption of the new engine.** Everything built is
  admin-side. A shopper-facing variant selector that swaps price/image/
  stock based on selected option values does not exist — this was never
  claimed as in-scope (the prompt's own framing throughout §2–§34 is about
  the Merchant Admin Portal), but is worth stating precisely rather than
  leaving ambiguous.
* **Axis removal never auto-merges.** By design (ADR-21) — a merchant
  must review and manually act on obsoleted rows after removing an axis;
  no heuristic decides which of several now-collapsed rows' data "wins."
* **Maximum 3 active option axes per Product** (`MAX_OPTION_AXES`),
  chosen and documented (§11), matching the prototype's own Color/Size/
  Material triple and this project's prior blueprint's "control the
  combinatorial explosion" instruction — not arbitrary, but also not
  configurable per Store.
* **Variant matrix has no pagination.** For Products with variant counts
  well beyond the tested 125-combination case, the bulk-edit form renders
  every active variant in one page/one POST. Not a correctness issue at
  tested scale; a real scalability limit at larger scale, unaddressed.
* **No live/AJAX combination-count preview.** Recalculated on next full
  page render, not on every keystroke — a deliberate simplification the
  prompt's own §24 permits ("do not regenerate Variants automatically on
  every keystroke").
* **Legacy single-axis and multi-axis engines cannot coexist on one
  Product.** `add_product_option` refuses to create the first axis while
  any legacy (`combination_key=""`) variant still exists — documented in
  ADR-20 as a deliberate simplification, not an oversight.
* **No dedicated CSRF-specific tests** for the new endpoints — consistent
  with the rest of this codebase's existing test suite, which has none
  either; not a new gap this phase introduced.

## 21. Remaining Prototype Gaps

Beyond what's captured in §3's inventory table and §20:

* Quick-pick attribute buttons (رنگ/سایز/جنس one-click chips from the
  prototype's `add(name)` function) are not reproduced — a plain text
  input is used instead, since the underlying `Attribute` catalog already
  gives merchants a reusable, persisted alternative to quick-pick chips
  (pick an existing Store `Attribute` rather than retyping a common name).
* The prototype's per-row inline image-preview-before-upload
  (`URL.createObjectURL`) is not reproduced in the variant matrix; image
  assignment continues to go through the existing Phase 1C image-variant
  `<select>` in the separate images modal.
* No bulk import/export for Attributes or Options (unchanged gap from
  Phase 1C, still not addressed).

## 22. Recommended Next Phase

In priority order:

1. **Descriptive-attribute product-form UI** (§20's named gap) — the
   smallest, most self-contained remaining piece of this phase's own
   stated scope; the service layer is done and tested, only a template
   section + a couple of view wiring calls remain.
2. **Storefront variant consumption** — wire `ProductVariant.display_image`
   and the new Option/Value data into an actual shopper-facing variant
   switcher on the product detail page (Phase 1C already left this as a
   named gap for single images; it now applies to the full multi-axis
   engine too).
3. Then, per every prior phase's own still-valid recommendation: wallet/
   cashback/referral, subscription/billing, staff invitation lifecycle,
   domain-management UI, inventory ledger, bulk import/export — none
   started, all still open.

## 23. Git Summary

* **Branch:** `claude/docs-prototypes-review-jxm6aw`
* **Commit hash / push status:** recorded after this report is committed
  — see the commit that includes this file for the exact hash; pushed to
  `origin/claude/docs-prototypes-review-jxm6aw` in the same operation.
* **Files changed:** 27 (15 new, 12 modified) — see §17/§18.
* **Migrations:** 1 new (`catalog.0011_attribute_option_variant_engine`,
  purely additive), plus 4 pre-existing migration files corrected for a
  real backward-migration bug (§19) — no new schema in those four, only
  the query/dependency fix.
* **Tests:** 127 new (all passing); full suite 2017/2017 passing, 0
  failures, 0 errors, run as the final step after every code change in
  this phase.
