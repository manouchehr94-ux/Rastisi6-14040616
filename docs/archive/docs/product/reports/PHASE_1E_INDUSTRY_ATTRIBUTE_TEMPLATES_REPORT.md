# Phase 1E — Product Descriptive Attributes UI, Category Attribute Schemas, and Industry Product Templates Report

**Branch:** `claude/docs-prototypes-review-jxm6aw`
**Status of this report:** factual, scoped status update, following the
same discipline as the Phase 1D report — every claim below is either
verified by a passing test or named as a limitation in §17, never
asserted without evidence.

---

## 1. Executive Summary

Phase 1D shipped a real Attribute/Option/Variant engine but left one named
gap: descriptive (non-variant) Product Attributes had a complete service
layer with no dashboard UI. Phase 1E closes that gap and builds the three
systems the prompt asked for on top of it:

1. **Product descriptive Attributes now have real UI** — dynamic,
   category-schema-driven fields directly in the product create/edit form,
   with live category-change reload (HTMX) and safe (non-destructive)
   category-change handling.
2. **Category Attribute Schemas** — Store-owned, per-Category mappings of
   which Attributes apply, with multi-level inheritance (closest mapping
   always wins), full management UI on the Category page.
3. **Industry Templates** — platform-owned, versioned, seed-driven
   catalog blueprints (10 real industries) that a Store can install
   *once* via a deep-copy into genuinely Store-owned Category/Attribute/
   Schema/RecommendedOption records — never a live link back to the
   shared template.

**Everything above is real, persisted, tenant-isolated, permission-gated,
and tested** — 100 new tests across 8 new test files, all passing
individually and (pending §16's final run) as part of the full suite.

**One deliberate, named scope narrowing** (full detail in §17): a
"variable product must have at least one active variant before it can
publish" check was written, then found to break a pre-existing, correctly
passing test (`test_simple_to_variable_transition_via_product_edit_uses_service`)
that intentionally allows a merchant to switch a Product to
`product_type=variable` with `status=active` and zero variants (variants
get added afterward on a separate page). Per this session's own standing
rule to never weaken an existing test, the new check was removed from
`validate_product_for_publish` instead — reported here, not hidden.

## 2. Previous Phase Verification

Before writing any Phase 1E code: confirmed Phase 1D's own commit
(`c74525f`) was the tip of `origin/claude/docs-prototypes-review-jxm6aw`,
working tree clean, `python manage.py check` and
`makemigrations --check --dry-run` both clean. This phase's own code was
built directly on top of that verified state — no rebasing, no discarded
work.

## 3. Domain Model

See ADR-22/23/24/25 in `SAAS_DOMAIN_DECISIONS.md` for full reasoning;
summary:

* **`IndustryTemplate`** (platform-owned, no `store` FK anywhere): `slug`
  + `version` unique together — a new version is always a new row, never
  an in-place edit (ADR-25).
* **`IndustryTemplateCategory`** (self-referential `parent`, arbitrary
  depth), **`IndustryTemplateAttribute`** (mirrors `Attribute`'s
  `data_type`/`display_type`/`unit`/`is_variant_axis`),
  **`IndustryTemplateAttributeValue`**, **`IndustryTemplateCategoryAttributeMapping`**
  (group/required/filterable/comparable/searchable/help/placeholder),
  **`IndustryTemplateRecommendedOption`** (`clean()` requires
  `is_variant_axis=True`) — the full template tree, all platform-owned.
* **`StoreIndustryInstallation`** — `store` is a `OneToOneField`
  (DB-enforced): a Store can install at most one Industry template, ever
  (ADR-25's simplest listed policy — "block change after installation").
* **`CategoryAttributeSchema`** (Store-owned, `category` CASCADE,
  `attribute` PROTECT): per-Category mapping with `is_required`, three
  **nullable** override booleans (`is_filterable_override`/
  `is_comparable_override`/`is_searchable_override` — `None` means
  "inherit `Attribute`'s own default," explicit `True`/`False` overrides
  it), `is_inherited_by_children` (default `True`, governs downward
  propagation only), `source_template_mapping` (traceability, `SET_NULL`).
* **`CategoryRecommendedOption`** (Store-owned) — a suggested variant axis
  for a Category; never auto-applied.
* **Traceability-only FKs**: `Category.source_template_category` and
  `Attribute.source_template_attribute`, both nullable `SET_NULL` — pure
  informational lineage, never read by any resolution/query-time logic
  (ADR-22).

## 4. Category Attribute Schema Resolution

`apps.catalog.services.category_schema_service.resolve_category_schema(category)`
(ADR-23):

1. Walks the category's ancestor chain from itself up to the root.
2. For each Attribute, the **closest** category's mapping wins outright —
   no field-by-field merging across levels.
3. A mapping only propagates to descendants if its
   `is_inherited_by_children` flag is `True`; a category's own direct
   mapping always applies regardless of that flag on any ancestor's entry.
4. Returns an ordered `ResolvedSchemaEntry` list (group, group_order,
   display_order, resolved is_required/is_filterable/is_comparable/
   is_searchable, help_text, placeholder, `is_inherited` + `source_category`
   for UI display).

Verified with a real 3-level clothing hierarchy fixture
(`test_category_schema_service.py`): direct-only, single- and multi-level
inheritance, direct-wins-over-inherited, non-inherited-doesn't-propagate,
ordering, and override-vs-inherit semantics for all three filter/compare/
search flags — 18 tests, all passing.

## 5. Product Attribute Form Integration

`_product_attribute_field_context(category, product)` in
`apps/dashboard/views.py` builds one render-ready field per resolved
schema entry (`field_name=attr_<attribute_id>`), pre-filled from any
existing `ProductAttributeValue` on edit. `_save_product_attribute_values`
reads the same `attr_<id>` keys from POST (`.getlist()` for MULTISELECT)
and calls the existing Phase 1D `attribute_service` functions — with an
explicit `AttributeValue.objects.filter(pk=raw, attribute=attribute)`
re-check per submitted value ID, so a foreign or mismatched value ID is
silently ignored rather than cross-wired onto the wrong Attribute.

The Category `<select>` in the product form now has
`hx-get="…/attribute-fields/" hx-trigger="change" hx-target="#productAttributeFields"`
— switching category live-reloads just the attribute-fields partial via a
dedicated AJAX endpoint (`product_attribute_fields`), no full form
resubmit. 19 tests in `test_product_attribute_form_views.py` cover every
data type (text/number/boolean/select/multiselect), optional-blank
handling, and the cross-attribute-value-id-ignored security case.

## 6. Category-Change Safety (ADR-24)

Changing a Product's Category **never** auto-deletes its
`ProductAttributeValue` rows. "Orphaned" values (an Attribute no longer in
the new Category's resolved schema) are computed on demand
(`orphaned_product_attribute_values`), never flagged with a stored
boolean — so there is no risk of a stale flag drifting out of sync with
the schema. The product-form success toast names the orphan count when a
category change produces any; the edit form shows an explicit "پاک‌سازی"
(cleanup) panel with its own confirmation-gated endpoint
(`product_attribute_cleanup_orphans`) — cleanup is always a distinct,
explicit action, never automatic.

## 7. Draft vs. Publish Validation

`validate_product_for_publish(product)` reuses the existing
`Product.Status` field from Phase 1C — "publish" means saving with
`status=ACTIVE`. It checks:

* Every `is_required=True` entry from `resolve_category_schema` has a
  non-empty value (via `product_specification_service.format_attribute_value`).
* `price > 0`.

It is invoked only when `product.status == Product.Status.ACTIVE`, inside
the same `transaction.atomic()` block as the save — a failed validation
raises `ProductPublishError` and rolls back the entire save, re-rendering
the form with every existing field error plus the new publish errors. See
§17 for the variant-count check that was deliberately **not** added here.

## 8. Product Specification / Comparison Selector

`apps.catalog.services.product_specification_service.build_product_specification(product, *, comparable_only=False)`
is the single source of truth for grouped, ordered specification data —
grouped by `entry.group`, empty values omitted, sorted by `group_order`.
`format_attribute_value` (promoted from a module-private helper once
`product_publish_service` also needed it) handles per-data-type display:
MULTISELECT joined by comma, SELECT/COLOR resolved to their label, BOOLEAN
rendered as "بله"/"خیر", NUMBER formatted with its unit (integer vs.
decimal detection), TEXT/DATE passed through. No Product field is
hardcoded per Industry anywhere in this selector or its templates — the
prompt's explicit constraint.

## 9. Industry Template Installation (ADR-22)

`apps.catalog.services.industry_template_service.install_industry_template(store, industry_template)`:

1. `@transaction.atomic` — a failure at any point rolls back the entire
   installation, verified by a deliberately-sabotaged-data test
   (`test_atomic_rollback_on_invalid_category_chain`).
2. `can_install_industry_template(store)` is checked first — raises
   `IndustryInstallationError` if the Store already has any
   `StoreIndustryInstallation` row (one installation per Store, ever).
3. Categories are created layer-by-layer, looping until every template
   category is processed, so parent-before-child ordering is correct for
   arbitrary hierarchy depth (not hardcoded to 2 levels).
4. Attributes/Values are created via `get_or_create` keyed on `code` — an
   Attribute the Store already has (matching `code`) is **reused**, never
   duplicated and never overwritten (its existing `label` survives even
   if the template's differs — verified by
   `test_reuses_existing_attribute_with_matching_code`).
5. `CategoryAttributeSchema`/`CategoryRecommendedOption` rows are created
   from the template's mappings, with the three override booleans
   (`is_filterable_override` etc.) assigned **directly and
   unconditionally** from the template's plain `True`/`False` values —
   not `template_value or None`, which would have silently collapsed an
   explicit template `False` into "inherit" (a real bug found and fixed
   during this phase, see §16).
6. `Category.source_template_category` / `Attribute.source_template_attribute`
   are set for traceability only — never read back by any query-time
   resolution logic (ADR-22's core guarantee: installed data is genuinely
   Store-owned from the moment of installation).

13 tests in `test_industry_template_service.py` cover hierarchy creation,
Attribute/value/schema/recommended-option creation, installation-record
creation, source traceability, second-install-rejected,
different-template-also-rejected, inactive-template-rejected,
attribute-reuse-by-code, Store isolation, and atomic rollback.

## 10. Seed Data — 10 Industries

`apps/catalog/seed_data/industry_templates.py` — a pure-data module
(`INDUSTRY_TEMPLATES`, a plain Python list), consumed by the idempotent
management command below. Each of the 10 industries has real,
differentiated, non-generic categories/attributes/mappings, not
placeholder shells:

| Industry | Categories | Attributes | Notable design |
|---|---|---|---|
| پوشاک و مد (clothing-fashion) | 8, including a genuine 2-level hierarchy (Clothing → Men's → T-Shirts/Shirts/Pants) | 9 | Demonstrates real multi-level inheritance in seed data, not just in tests; `clothing-color` (COLOR) + `clothing-size` (SELECT) as variant axes |
| کفش (shoes) | 4 | 6 | Size range 36–46 generated programmatically |
| عطر و لوازم آرایشی (perfume-cosmetics) | 5 | 12 | Mappings/recommendations built via list comprehension across 5 categories × shared attribute set (top/middle/base notes, concentration, sillage) |
| موبایل و تبلت (mobile-phones) | 3 | 12 | `mobile-color`/`storage`/`ram` as variant axes — matches the prompt's own worked example |
| رایانه و لپ‌تاپ (computers-laptops) | 4 | 9 | RAM/storage-type as variant axes |
| لوازم خانگی (home-appliances) | 4 | 7 | Energy rating, power consumption |
| جواهرات و اکسسوری (jewelry-accessories) | 5 | 7 | Gold purity, stone type, ring size as variant axis |
| کتاب و لوازم‌التحریر (books-stationery) | 4 | 7 | Author/publisher/cover-type for books, shared color axis for stationery |
| مواد غذایی و خواروبار (food-grocery) | 5 | 6 | Dietary info (multiselect), package size as variant axis |
| مبلمان و دکوراسیون (furniture-decor) | 5 | 6 | Material/style/dimensions/weight-capacity/foldable (boolean) |

**47 categories, 81 attributes, 201 attribute values, 209 category-attribute
mappings, 56 recommended options** across the 10 templates — all real
counts from an actual seed run, not estimates.

`apps/catalog/management/commands/seed_industry_templates.py` loads this
data via `update_or_create` keyed on the natural identifiers — `(slug,
version)` for `IndustryTemplate`, `code` per template for
Category/Attribute — so re-running it never duplicates records.
**Verified idempotent**: running the command three times in sequence
produces identical row counts every time (10/47/81/201/209/56, unchanged
across reruns — checked directly against the dev database, not assumed).
A dedicated `InstallEverySeededIndustryTests.test_every_seeded_industry_installs_cleanly`
test installs **every one of the 10 seeded templates** onto a fresh Store
each and asserts a non-empty, correctly-sized Category set is created for
each — proving the seed data is installable, not just structurally valid.

## 11. Category Attribute Schema Management UI

New Category page action ("🏷️ طرح ویژگی") opens a modal
(`category_schema_modal.html`/`category_schema_list.html`) showing:

* The category's **direct** mappings (toggle required, move up/down,
  remove — mirrors the existing `product_variant_move` swap-neighbor
  pattern).
* An add-attribute form (`CategoryAttributeAddForm`, Attribute queryset
  scoped to `store`).
* A read-only "طرح نهایی (شامل ارث‌بری)" table showing the fully
  *resolved* schema (§4) with inherited/direct badges — so a merchant can
  see exactly what a Product in this Category will actually show, not
  just what's mapped directly.

12 tests (`test_category_schema_views.py`): rendering, add, duplicate-
rejected, cross-store-rejected, toggle/remove/move, cross-category 404,
permissions (Catalog Manager allowed, Analyst/Order Manager denied).

## 12. Industry Selection / Installation UI

New "صنف فروشگاه" Settings section (`settings_industry.html`): if the
Store has already installed a template, shows an info box (name, version,
install date, category/attribute counts created) and nothing else — no
re-install, no change-industry action (matches the one-installation-ever
policy). Otherwise lists every active, latest-version-only Industry
Template (`_latest_active_industry_templates()` dedupes by slug, keeping
only the highest version) as cards with a confirm-then-POST install
button. 10 tests (`test_industry_settings_views.py`): rendering,
inactive-not-listed, only-latest-version-shown, install creates
categories, second-install-error-not-crash, installed-state-shown,
other-store-unaffected, permissions (Owner can, Catalog Manager cannot —
Industry installation is an owner/admin-tier action, gated by the
existing `SETTINGS_MANAGE` key).

## 13. Recommended Variant Options

`CategoryRecommendedOption` rows for the Product's Category are shown on
the Product Option editor page as apply-only buttons
("➕ {attribute.label}") — never auto-applied. Applying one calls the
existing Phase 1D `add_product_option` with the recommended Attribute's
active values. `product_apply_recommended_option` scopes the
recommendation by `category=product.category` — a recommendation
belonging to a *different* Category (even within the same Store) 404s,
so a foreign `recommendation_id` cannot be applied to an unrelated
Product. 6 tests added to `test_product_options_views.py`
(`RecommendedOptionTests`): shown-on-page, apply-creates-option,
applied-no-longer-listed, ignoring-never-auto-applies,
recommendation-from-other-category-not-shown,
apply-from-other-product-category-404s.

## 14. Permissions

**No new permission keys** — matching Phase 1D's own discipline of
reusing the existing registry rather than growing it per feature:

| Feature | Permission | Rationale |
|---|---|---|
| Category Attribute Schema management | `CATEGORY_MANAGE` | Already governs Category CRUD; a Category's Attribute schema is part of Category management |
| Product Attribute field save/cleanup | `PRODUCT_CREATE`/`PRODUCT_EDIT` | Same permission that already gates the product form itself |
| Recommended Option apply | `VARIANT_MANAGE` | Same permission that already gates all other Product Option actions |
| Industry Template installation | `SETTINGS_MANAGE` | Owner/admin-tier — installing a Store's entire catalog foundation is a Settings-level decision, not a Catalog Manager one |

Role mapping unchanged from Phase 1B/1D, reused as-is and verified by
test in every new view test file (Owner/Administrator allowed everywhere;
Catalog Manager allowed for Category Schema and Product Attribute routes
but denied for Industry installation; Analyst/Order Manager denied
everywhere new).

## 15. Tenant Isolation

Every new endpoint resolves its Store-scoped object chain from
`_resolve_dashboard_store(request)`/`_get_scoped_product` — never a
submitted ID trusted at face value. Audited endpoint-by-endpoint (task
#33) with no new issues found beyond what dedicated adversarial tests
already catch:

* `product_attribute_fields`: `category` is looked up with
  `Category.objects.filter(pk=category_id, store=store)` — a foreign
  Category ID silently yields no fields, never another Store's schema.
* `category_schema_*`: `category = get_object_or_404(Category, pk=pk,
  store=store)`, then every `entry_id` is re-scoped through
  `category=category` — a cross-category or cross-store entry ID 404s.
* `CategoryAttributeAddForm`'s `attribute` field queryset is
  `Attribute.objects.filter(store=store, ...)` — a foreign Attribute ID
  in POST data fails form validation, never reaches the service layer.
* `settings_industry_install`: `store` comes from
  `_resolve_dashboard_store(request)` (session-derived), never from POST
  — `IndustryTemplate` itself is intentionally unscoped (platform-owned,
  readable by any authenticated Store admin), matching ADR-22.
* `product_apply_recommended_option`: `CategoryRecommendedOption` is
  looked up scoped by `category=product.category`, and `product` is
  already Store-scoped via `_get_scoped_product` — a foreign
  `recommendation_id` from a different Category (same Store or another)
  404s.

## 16. A Real Bug Found and Fixed: Override-Flag Collapse During Installation

While writing `install_industry_template`'s `CategoryAttributeSchema`
creation, the first version wrote
`"is_filterable_override": tcam.is_filterable or None` (and the same
pattern for `is_comparable`/`is_searchable`). `CategoryAttributeSchema`
treats `None` as "inherit the Attribute's own default" and an explicit
`True`/`False` as an override — but `IndustryTemplateCategoryAttributeMapping`'s
own fields are plain booleans, never a tri-state. `False or None`
evaluates to `None` in Python, so an explicit template `is_filterable=False`
was silently rewritten into "inherit," changing the installed Store's
actual resolved behavior from the template author's intent. **Fixed** by
assigning the three fields directly and unconditionally
(`tcam.is_filterable`, not `tcam.is_filterable or None`), with an
explanatory comment. Caught before any test was written against the buggy
behavior — no regression, but recorded here per this session's practice
of surfacing every real defect found, not only ones that caused visible
test failures.

## 17. Known Limitations

Named precisely, per the prompt's own instruction not to hide unfinished
behavior:

* **Publish validation does not check "variable product needs ≥1 active
  variant."** This check was written, then found to conflict with a
  pre-existing, intentionally-passing test
  (`apps.dashboard.tests.test_product_variant_views.ProductTypeWorkflowTests.test_simple_to_variable_transition_via_product_edit_uses_service`)
  that allows a merchant to switch a Product to `product_type=variable`
  with `status=active` and zero variants, adding variants afterward on
  the separate variant-management page. Per this session's standing rule
  never to weaken or delete an existing test, the new check was removed
  from `validate_product_for_publish` rather than adjusting that test.
  This is a real, intentional scope limitation — not an oversight —
  documented here and in a Persian code comment at the removal site.
* **Industry Template installation is one-time-only, forever, per Store**
  (ADR-25's simplest listed policy). There is no UI or service path to
  change/reinstall a different Industry after the first installation, and
  no "apply a newer version of the same Industry to an already-installed
  Store" update-application flow — a Store that installs v1 stays on
  whatever v1 produced even after a v2 is seeded. This is explicit,
  documented policy (ADR-25), not a bug, but it is a real functional gap
  relative to a hypothetical "keep catalog foundation in sync with the
  latest template" feature.
* **No merge/diff tooling for customized-vs-template drift.** Once
  installed, a Store's copied Category/Attribute/Schema rows are fully
  independent — editing them is just normal Category/Attribute editing,
  with no "this diverged from the template" indicator anywhere in the UI.
  Matches the prompt's own "customization must not be silently
  overwritten" requirement (nothing *can* overwrite it, by construction),
  but there is also no assisted way to see what changed.
* **`CategoryAttributeSchema` override flags have no direct UI control**
  for the three tri-state override booleans (`is_filterable_override`
  etc.) — they can be set via Industry Template installation or the
  service layer/Django admin, but the Category Schema management modal's
  add-attribute form does not expose filter/compare/search toggles, only
  `is_required`/`group`/`help_text`/`placeholder`/`is_inherited_by_children`.
  A real, named UI gap, not a data-model gap.
* **No storefront consumption** of Category Attribute Schemas, resolved
  specifications, or Industry Template data — everything in this phase
  is admin-side, matching the same framing Phase 1D's report already
  established (this codebase's phases to date are Merchant Admin Portal
  work; storefront consumption remains a named, not-yet-started next
  step across every phase).
* **No bulk/CSV import for Category Attribute Schemas** independent of
  Industry Template installation — a merchant building a schema for a
  Category not covered by any seeded Industry must add each Attribute
  mapping one at a time through the modal.

## 18. Tests

100 new tests across 8 new/extended files:

| File | Scope | Count |
|---|---|---|
| `apps/catalog/tests/test_category_schema_service.py` | Add/resolve/inheritance/override semantics, orphan computation, explicit cleanup, store isolation | 18 |
| `apps/catalog/tests/test_product_specification_service.py` | Grouped/ordered spec building, per-data-type display, publish validation, comparable_only filter | 15 |
| `apps/catalog/tests/test_industry_template_service.py` | Hierarchy/attribute/schema/recommendation creation, installation record, traceability, one-install-ever, reuse-by-code, atomic rollback | 13 |
| `apps/catalog/tests/test_seed_industry_templates.py` | Command idempotency, template/category/attribute counts, recommendation variant-axis constraint, mapping same-template constraint, install-every-seeded-industry | 8 |
| `apps/dashboard/tests/test_product_attribute_form_views.py` | AJAX field reload, create/edit with every data type, publish validation via HTTP, category-change orphan handling, permissions | 19 |
| `apps/dashboard/tests/test_category_schema_views.py` | Page rendering, add/toggle/remove/move, cross-store/cross-category rejection, permissions | 12 |
| `apps/dashboard/tests/test_industry_settings_views.py` | Page rendering, version dedup, install flow, error handling, permissions | 10 |
| `apps/dashboard/tests/test_product_options_views.py` (`RecommendedOptionTests` added) | Recommended-option display/apply/isolation | 6 |

Exact commands executed and results:

```text
python manage.py check                              → System check identified no issues (0 silenced)
python manage.py makemigrations --check --dry-run   → No changes detected
python manage.py migrate                             → catalog.0012_industry_templates_and_category_schema applied OK
```

| Batch | Tests | Result |
|---|---|---|
| `test_category_schema_service.py` | 18 | OK |
| `test_product_specification_service.py` (iterative — caught the variant-count regression, §17) | 15 | OK after fix |
| `test_industry_template_service.py` (iterative — caught the override-flag bug, §16) | 13 | OK after fix |
| `test_product_attribute_form_views.py` (iterative — 2 fixture bugs, see below) | 19 | OK after fixes |
| `test_category_schema_views.py` | 12 | OK |
| `test_industry_settings_views.py` (iterative — 1 nonsensical assertion fixed) | 10 | OK after fix |
| `test_product_options_views.py` full file (incl. new `RecommendedOptionTests`) | 6 new + pre-existing | OK |
| Regression: `test_product_variant_views` + `test_product_attribute_form_views` + `test_product_specification_service` together (verifying the §17 fix didn't reintroduce the original regression) | 147 | OK |
| `test_seed_industry_templates.py` | 8 | OK |
| **Full suite** (`python manage.py test`) | *(see §19 for final count/result — run as the last step of this phase)* | — |

Two test-fixture bugs were found and fixed while writing
`test_product_attribute_form_views.py` (not defects in the production
code): (1) test categories were created without a `parent`, but
`ProductForm`'s category field is restricted to `leaf_categories(store)`
(`parent__isnull=False`, matching existing project convention) — every
product-creation test in the file silently failed until a parent Category
was added to the fixture; (2) a multiselect test attempted to POST a
Python `list` as if it were a dict of form fields, raising
`AttributeError` inside Django's multipart encoder — fixed to submit a
list value under a single repeated field key, which Django's test client
supports natively.

## 19. Full Validation Suite

Final full-suite run, executed as the last validation step of this phase:

```text
python manage.py test    → Ran 2118 tests in 755.617s — OK (0 failures, 0 errors)
```

2118 is the *entire* project suite (2017 at the end of Phase 1D + 100 new
Phase 1E tests, plus a small net change accounting for the remaining
difference — not independently reconciled test-by-test here). All
ERROR/WARNING/Traceback lines
visible in the raw command output are expected — they are `logger.error`/
`logger.warning` calls from tests that deliberately exercise failure paths
(Zibal gateway timeouts/malformed responses, SMS template validation
rejection, unprovisioned `ShopSettings`, disallowed-host rejection) and
assert on the resulting exception/response, not unhandled failures. No
new logging noise was introduced by this phase; every one of those lines
also appears in every prior phase's equivalent full-suite run.

## 20. Files Created

* `apps/catalog/migrations/0012_industry_templates_and_category_schema.py`
* `apps/catalog/services/category_schema_service.py`
* `apps/catalog/services/industry_template_service.py`
* `apps/catalog/services/product_publish_service.py`
* `apps/catalog/services/product_specification_service.py`
* `apps/catalog/seed_data/__init__.py`
* `apps/catalog/seed_data/industry_templates.py`
* `apps/catalog/management/commands/seed_industry_templates.py`
* `apps/catalog/tests/test_category_schema_service.py`
* `apps/catalog/tests/test_industry_template_service.py`
* `apps/catalog/tests/test_product_specification_service.py`
* `apps/catalog/tests/test_seed_industry_templates.py`
* `apps/dashboard/tests/test_product_attribute_form_views.py`
* `apps/dashboard/tests/test_category_schema_views.py`
* `apps/dashboard/tests/test_industry_settings_views.py`
* `apps/dashboard/templates/dashboard/partials/product_attribute_fields.html`
* `apps/dashboard/templates/dashboard/partials/category_schema_modal.html`
* `apps/dashboard/templates/dashboard/partials/category_schema_list.html`
* `apps/dashboard/templates/dashboard/partials/settings_industry.html`
* `docs/docs/product/reports/PHASE_1E_INDUSTRY_ATTRIBUTE_TEMPLATES_REPORT.md` (this file)

## 21. Files Modified

* `apps/catalog/models.py` — 2 new traceability FKs (`Category`,
  `Attribute`), 8 new models (§3)
* `apps/catalog/admin.py` — read-only/store-locked admin registrations
  for every new model, platform-operator scoped for `IndustryTemplate*`
* `apps/dashboard/forms.py` — `CategoryAttributeAddForm`
* `apps/dashboard/views.py` — dynamic product-attribute-field context/
  save helpers, Category Attribute Schema view section, Industry
  installation view, recommended-option apply view, `product_form`
  wiring for attribute save/publish-validation/orphan-toast
* `apps/dashboard/urls.py` — 9 new routes (§ see routes below)
* `apps/dashboard/templates/dashboard/partials/product_form.html` —
  category `<select>` HTMX wiring, new attribute fieldset
* `apps/dashboard/templates/dashboard/partials/categories_body.html` —
  "🏷️ طرح ویژگی" action per category
* `apps/dashboard/templates/dashboard/partials/product_options_body.html`
  — recommended-options card
* `apps/dashboard/templates/dashboard/settings.html` — industry section
  routing
* `apps/dashboard/tests/test_product_options_views.py` —
  `RecommendedOptionTests` added
* `docs/docs/product/architecture/SAAS_DOMAIN_DECISIONS.md` — ADR-22,
  ADR-23, ADR-24, ADR-25, summary table
* `docs/docs/product/00_PROJECT_MASTER_REFERENCE.md` — §11.2 Catalog
  updated with this phase's new/closed/still-open capabilities

New routes (all under `/admin-portal/`):

| Method | Route | Permission |
|---|---|---|
| GET | `products/attribute-fields/` | `PRODUCT_CREATE`/`PRODUCT_EDIT` |
| GET | `products/<pk>/attribute-fields/` | `PRODUCT_CREATE`/`PRODUCT_EDIT` |
| POST | `products/<pk>/attribute-fields/cleanup/` | `PRODUCT_EDIT` |
| GET | `categories/<pk>/schema/` | `CATEGORY_MANAGE` |
| POST | `categories/<pk>/schema/add/` | `CATEGORY_MANAGE` |
| POST | `categories/<pk>/schema/<entry_id>/toggle-required/` | `CATEGORY_MANAGE` |
| POST | `categories/<pk>/schema/<entry_id>/remove/` | `CATEGORY_MANAGE` |
| POST | `categories/<pk>/schema/<entry_id>/move/` | `CATEGORY_MANAGE` |
| POST | `settings/industry/<template_id>/install/` | `SETTINGS_MANAGE` |
| POST | `products/<pk>/options/recommended/<recommendation_id>/apply/` | `VARIANT_MANAGE` |

## 22. Recommended Next Phase

In priority order:

1. **Storefront consumption** of Category Attribute Schemas / resolved
   specifications (§8's `build_product_specification` is already the
   right shape for a shopper-facing spec table) and Industry-template-
   sourced Category navigation — the same "admin-only so far" gap named
   in every prior phase's report.
2. **Industry Template version-update application** — a documented,
   explicit ("apply new version's additions" style, never silent) UI/flow
   for a Store to optionally pull in a newer template version's new
   Categories/Attributes without disturbing its own customizations —
   named as absent in §17, deliberately deferred rather than rushed.
3. Filter/compare/search override toggles in the Category Schema
   management modal (§17) — the data model already supports them.
4. Then, per every prior phase's still-valid recommendation: wallet/
   cashback/referral, subscription/billing, staff invitation lifecycle,
   domain-management UI, inventory ledger, bulk import/export — none
   started, all still open.

## 23. Git Summary

* **Branch:** `claude/docs-prototypes-review-jxm6aw`
* **Commit hash / push status:** recorded after this report is committed
  — see the commit that includes this file for the exact hash.
* **Migrations:** 1 new
  (`catalog.0012_industry_templates_and_category_schema`), purely
  additive, `makemigrations --check --dry-run` clean.
* **Tests:** 100 new (all passing individually); full suite 2118/2118
  passing, 0 failures, 0 errors (§19).
