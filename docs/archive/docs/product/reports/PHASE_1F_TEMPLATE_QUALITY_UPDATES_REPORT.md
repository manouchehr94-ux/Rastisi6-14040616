# Phase 1F — Industry Template Quality Framework, Preview, and Safe Update Workflow Report

**Branch:** `claude/docs-prototypes-review-jxm6aw`
**Status of this report:** factual, scoped status update, following the
same discipline established in every prior phase report in this session
— every claim below is either verified by a passing test or named
explicitly as a limitation in §27, never asserted without evidence.

---

## 1. Executive Summary

Phase 1E shipped Industry Templates as a one-shot, unvalidated,
un-updatable installation mechanism. Phase 1F adds the missing quality
and lifecycle layer around that mechanism without disturbing it:

1. **A real quality framework** — `validate_industry_template` returns
   structured, coded errors/warnings/infos plus metrics and a
   non-vanity quality score; a template with any structural error can
   never reach `production_ready`, regardless of score.
2. **A complete pre-installation preview** — category hierarchy,
   grouped attributes, required/filterable/comparable/searchable flags,
   recommended options, and a Store-specific installation-impact plan
   derived from real Store state (never hardcoded counts).
3. **A safe, merchant-controlled update workflow** — when a newer
   `production_ready` version of an installed Store's Industry family
   exists, the merchant can preview a stable-code diff, apply safe
   additive changes with one confirmation, and see a full update
   history. Anything touching a customized or removed record is
   **never** applied automatically.
4. **Category Attribute Schema override controls** — the filterable/
   comparable/searchable tri-state overrides and storefront-visibility
   toggle named as a real gap in the Phase 1E report are now exposed in
   the dashboard UI.
5. **20 new Industry templates**, reaching **30 total**, all
   `production_ready`, all passing strict validation, all installing
   cleanly, seeded via a refactored, idempotent, per-file (not one giant
   dictionary) authoring structure.

**Two real, non-trivial bugs were found and fixed while writing this
phase's own tests — not hidden, both detailed in §8 and §23:**

* `install_industry_template` never set the new
  `AttributeValue.source_template_value` traceability FK, so every
  freshly-installed value looked indistinguishable from a merchant-added
  one to the new customization-detection logic.
* The update-application service's category lookup was keyed by
  `IndustryTemplateCategory` primary key, which differs between template
  versions for the *same* category — so any mapping or recommendation
  targeting a category that existed **before** the update being applied
  silently no-op'd instead of being applied. Fixed by keying on the
  stable `code` field throughout, matching ADR-27's own stated
  philosophy.

**One deliberate, named scope narrowing** (detailed in §27): only
`safe_additive` changes are ever auto-applied. `review_required` changes
(a rename/retype on an *uncustomized* record) are computed, classified,
and displayed, but the apply service explicitly refuses to apply them —
`apply_template_update` raises if a caller attempts to select a
review-required or blocked change-id. This is ADR-29's own documented
line, not an oversight.

## 2. Previous Phase Verification

Before writing any Phase 1F code, the session state was inspected and
found to have drifted: an earlier work session's Phase 1F implementation
had been built entirely in an ephemeral container's working tree and was
**never committed** before that session ended — a real loss, disclosed
here rather than glossed over. This session's local checkout was found
sitting at `715252a` ("Initial commit"), predating even Phase 1D/1E.
`git fetch` confirmed `origin/claude/docs-prototypes-review-jxm6aw` was
actually at `af0d71c` (Phase 1E, fully committed and pushed); a
fast-forward merge (`git merge --ff-only`) brought the local branch to
match. Phase 1E's own state was then re-verified directly rather than
assumed: `python manage.py check` clean, and a focused baseline
(`test_industry_template_service`, `test_category_schema_service`,
`test_industry_settings_views`, `test_category_schema_views`,
`test_seed_industry_templates` — 61 tests) passing before any Phase 1F
code was written.

Given the loss, this phase's own work was committed in nine incremental
checkpoints (models, services, 20 new templates, seed command wiring, UI,
five test batches) rather than one final commit, specifically to bound
any future repeat of this failure mode to, at most, the most recent
checkpoint.

## 3. Prototype Inventory

The prompt names `prototypes/merchant-panel-x25/` as the reference
prototype; as in every prior phase's report, no such directory exists in
this repository (`ls prototypes/` → does not exist; no file matching
`*merchant-panel-x25*` anywhere in the tree). There is therefore no
prototype UI for Industry template preview, version comparison, update
notifications, or conflict warnings to inventory against — this phase's
UI (template list, readiness badge, preview, category-tree expansion,
attribute groups, installation impact, update-available banner, version
diff, safe/review/blocked sections, update history) was designed from
this codebase's own existing dashboard design system (`.card`/`.btn`/
`.badge`/HTMX partial-swap conventions), consistent with every prior
phase.

| Capability | Prototype file | Status |
|---|---|---|
| Industry selection / template cards | none found | Not applicable |
| Template preview | none found | Not applicable — built fresh, Complete |
| Category-tree preview | none found | Not applicable — built fresh, Complete |
| Installation confirmation / impact summary | none found | Not applicable — built fresh, Complete |
| Update notification / version comparison | none found | Not applicable — built fresh, Complete |
| Selective update / conflict warnings | none found | Not applicable — built fresh, Complete |

## 4. Quality Framework

`apps.catalog.services.template_validation_service.validate_industry_template(template)`
checks, per ADR-26:

* **Identity** — non-empty name/slug (error), non-empty description/
  locale (warning).
* **Category** — at least one category and one root category (error),
  no circular hierarchy (error, cycle-detecting walk), no orphaned
  parent reference outside the template (error), excessive depth >4
  (warning), duplicate sibling names (warning).
* **Attribute** — valid/non-trivial label (error), a choice-type
  Attribute (SELECT/MULTISELECT/COLOR) with zero Values (error), a COLOR
  value missing `color_hex` (warning).
* **Category Schema (mapping)** — a required mapping whose Attribute is
  choice-type but has zero obtainable Values (error), more than 6
  required mappings on one Category (warning), a leaf Category with no
  direct mapping (warning — informational, since inheritance may still
  cover it).
* **Recommended Options** — a variant-axis recommendation with fewer
  than 2 Values (warning — cannot produce meaningful variants).
* **Merchant usefulness** — fewer than 2 Categories or 3 Attributes
  (warning), zero filterable mappings across the whole template
  (warning).
* **Installability** — the same category-graph shape check
  `install_industry_template` itself relies on (error if it would fail).

Severities are fixed: **any `error` unconditionally blocks
`production_ready`**, regardless of `quality_score`. The score
(`QUALITY_SCORE_WEIGHTS` = structure 25 / attribute completeness 20 /
schema quality 20 / variant recommendations 15 / merchant usefulness 10 /
installability 10, summing to 100) starts every dimension at its full
weight and subtracts a fixed 5 points per warning in that dimension,
floored at 0 — never below 0, never allowed to exceed 40 once any error
exists. This is a triage aid for platform operators comparing templates,
never an automated pass/fail gate on its own (ADR-26).

## 5. Validation Service

`validate_industry_template(template) -> TemplateValidationResult`
(pure, read-only) returns `errors`/`warnings`/`infos` (each a list of
`ValidationIssue(code, severity, message, model_type, identifier,
remediation)`), `metrics` (category/attribute/value/mapping/
recommendation counts + variant-axis/choice-attribute counts +
installability boolean), and `quality_score`. Determinism is verified by
test (`test_deterministic_result_across_calls`).

`validate_and_persist(template, *, strict=False)` is the mutating
wrapper: computes and caches `content_fingerprint`, upserts an
`IndustryTemplateValidationResult` row (one per template, keyed
`OneToOneField`), and updates `readiness` — but **only** while the
template is in one of the four auto-managed states (draft/
validation_failed/review_required/production_ready); a `deprecated`/
`archived` template is never silently promoted back
(`test_deprecated_template_never_auto_promoted`). `--strict` downgrades
a zero-error-but-some-warnings result to `review_required` instead of
`production_ready`.

Called identically by: the `validate_industry_templates` management
command (read-only unless `--apply`), the seed command (always applies,
setting each of the 30 templates' initial readiness), and every test —
one source of truth, per the prompt's own requirement.

## 6. Fingerprint Design

`compute_template_fingerprint(template)` builds a canonical dict from
`slug`/`name`/`description`/`icon`/`locale` plus every Category
(code/name/icon/parent-code/order), Attribute (code/label/data_type/
display_type/unit/is_variant_axis/order + sorted Values), Mapping
(category-code/attribute-code/group/order/required/filterable/
comparable/searchable/help/placeholder), and Recommendation
(category-code/attribute-code/order) — `json.dumps(sort_keys=True)` then
SHA-256. Explicitly **excludes** every primary key, `created_at`,
`updated_at`, and `version` itself — verified by
`test_independent_of_primary_keys` (two rows, same content, different
slug+version+PK, identical fingerprint) and
`test_does_not_depend_on_timestamps` (re-saving a child row bumps
`updated_at` via `auto_now` but the fingerprint is unchanged).
`test_changes_when_content_changes` confirms it's actually sensitive to
real content, not a no-op hash.

## 7. Readiness Lifecycle

`IndustryTemplate.Readiness`: `draft` → `validation_failed` /
`production_ready` (via `validate_and_persist`) → optionally
`review_required` (strict mode) → `deprecated`/`archived` (operator-only,
never auto-transitioned into or out of by validation). Only
`production_ready` (`is_offerable_for_new_installation` = `is_active AND
readiness == production_ready`) is ever shown to merchants
(`_latest_active_industry_templates`) or accepted by
`install_industry_template` — the latter enforces this itself now
(previously only `is_active`), so a draft/deprecated template can never
be installed even via a direct service call or a hand-crafted POST to the
install endpoint, not merely hidden from the merchant-facing list.
"Current recommended version for new installs" is never stored — it's
computed fresh on every read (`latest_production_version(slug)`), so
there is no risk of two rows both claiming to be "the" current version.

## 8. Template Version Architecture

No new version-family model was introduced (ADR-27) — `IndustryTemplate`'s
existing `(slug, version)` compound key already represents family
+ version identity fully; `readiness` and `content_fingerprint` are the
only two new fields on the model. This required zero migration risk to
Phase 1E's 10 existing templates or their installations beyond two new
nullable/defaulted columns. Migration `catalog.0013` is purely additive:
`IndustryTemplate.readiness`/`content_fingerprint`,
`AttributeValue.source_template_value`, and two new models
(`IndustryTemplateValidationResult`, `StoreTemplateUpdate`) —
`makemigrations --check --dry-run` confirms it exactly matches model
state, and running it against the Phase 1E database preserved every
existing template, installation, Category, and Attribute unchanged
(verified directly — the 10 Phase 1E templates and their fixtures still
pass every pre-existing test unmodified except for the two files needing
an explicit `readiness=PRODUCTION_READY` fixture update, see §21).

**A real bug found here:** `install_industry_template`'s `AttributeValue`
creation loop never set the new `source_template_value` FK in its
`get_or_create` defaults. Every value created through installation was
therefore indistinguishable from a merchant-added value under
`is_value_customized`'s "no source FK means owned" rule — meaning every
installed Store's values would have been permanently and incorrectly
treated as customized by the update workflow, blocking every future safe
value-addition. Fixed in the same file, verified by
`test_untouched_installed_value_is_not_customized`.

## 9. Preview and Installation Planning

`build_template_preview(template)` returns: readiness, counts
(categories/attributes/values/mappings/recommendations), a nested
category hierarchy (recursive `{code, name, icon, children}`), attributes
grouped per category with required/filterable/comparable/searchable
flags, recommended options per category, the validation result, and
static installation/customization policy text. Rendered as a dedicated
page (`industry_template_preview.html` + a self-recursive
`industry_preview_category_tree.html` partial) reachable via a
"پیش‌نمایش" link on every listed template card.

`plan_industry_template_installation(store, template)` is **Store-aware**
— `will_create_attributes`/`will_reuse_attributes` are computed from a
real query (`Attribute.objects.filter(store=store, code__in=[...])`),
never a static count (`test_plan_reflects_real_store_state_not_hardcoded`
proves an Attribute with a matching code in a *different* Store is not
miscounted as reusable here). `install_industry_template` **never**
trusts this plan or any client-submitted preview data — it independently
re-derives and re-validates everything inside its own atomic
transaction, exactly as Phase 1E already did; this phase's preview layer
is read-only and additive.

## 10. Version Comparison

`compare_template_versions(old, new)` raises `TemplateComparisonError`
for cross-family comparisons and otherwise returns a `TemplateDiff` with
`added`/`changed`/`removed` `DiffEntry` lists across categories,
attributes, values, mappings, and recommendations — identity is always
the stable `code` (or a `category_code:attribute_code` composite for
mapping/recommendation entries), **never** the display label
(`test_stable_code_identity_not_display_label` proves a pure rename is
classified as `changed`, never `removed`+`added`). `changed` entries
carry a `details` dict of only the fields that actually differ
(`{field: {old, new}}`). Ordering is fully deterministic
(`sorted()` on every dict before iteration) — verified by
`test_deterministic_ordering`. 15 tests cover every named change type
from the prompt's own checklist: added/removed/renamed Category, parent
change, added Attribute, data-type change, added/removed Value, mapping
required/filterable/comparable/searchable change, added/removed
Recommendation.

## 11. Customization Detection

Per ADR-28, no snapshot table exists — the *source template row itself*
(immutable per ADR-25) is compared directly against the live Store
record via its `source_template_*` FK: `is_category_customized`
(name/icon/parent-identity/active-state), `is_attribute_customized`
(label/data_type/display_type/unit/is_variant_axis/active-state),
`is_value_customized` (label/color_hex/active-state), and
`is_schema_entry_customized` (group/required/the three overrides/
help_text/placeholder/visibility). **Any record with no
`source_template_*` FK is unconditionally treated as customized** — this
covers both merchant-created records and Phase-1E-era installations that
predate the `AttributeValue.source_template_value` field added this
phase. `detect_installation_customizations(installation)` aggregates all
of the above into code-keyed sets for one Store's installation; verified
store-isolated (`test_other_store_isolation` — a second Store's
customization never leaks into the first Store's report).

## 12. Update Planning

`plan_template_update(installation, target_template)` first checks
eligibility (same family, `target.version > installed.version`, target
`is_offerable_for_new_installation`) before doing anything else — any
failure returns immediately with `eligible=False` and zero further
computation, never touching Store data. When eligible, it classifies
every diff entry:

* **`safe_additive`** — every `added` entry, *unless* it's a new
  Attribute whose `code` already exists in the Store with a
  **different** `data_type** (a real conflict, moved to `blocked` with an
  explicit reason instead of silently reusing or silently failing later).
* **`review_required`** — a `changed` entry on a record
  `template_customization_service` finds **not** customized.
* **`blocked`** — a `changed` entry on a customized record, or any
  `removed` entry (removal is never auto-applied in this phase, full
  stop).

`default_selected_change_ids` pre-selects only `safe_additive` — the
merchant must explicitly opt into nothing else, since `review_required`/
`blocked` entries are never selectable by the apply service regardless of
what a client submits (§13). 9 tests cover this classification plus
same-version/older-version/deprecated-target rejection and
"planning never mutates Store data."

## 13. Update Application

`apply_template_update(installation, target_template,
selected_change_ids, actor)`:

1. Idempotency check first — an already-`COMPLETED`
   `StoreTemplateUpdate` for this exact `(installation, target_template)`
   pair rejects immediately, before any other work.
2. **Always recomputes `plan_template_update` itself** — a stale or
   tampered client-submitted plan is never trusted; only `change_id`
   strings that appear in the **freshly computed** `safe_additive` set
   are ever eligible for selection. Selecting a `review_required` or
   `blocked` change_id (even one that was legitimately in an *older*
   plan) raises `TemplateUpdateError` before any mutation.
3. A `StoreTemplateUpdate` history row is created/updated to `PENDING`
   **before** the mutating transaction opens.
4. The actual mutation runs inside one `transaction.atomic()` block:
   categories (layer-by-layer, parent-before-child, keyed by stable
   `code` — see the bug fix below), attributes, values, mappings, then
   recommendations, in that dependency order; `installation.installed_version`
   is bumped only as the final step of the same transaction.
5. On success, the history row is marked `COMPLETED` with
   `applied_changes`/`skipped_changes` **inside the same transaction** —
   an all-or-nothing unit together with the actual data changes.
6. On any exception, the `except` block (outside the `with
   transaction.atomic()`) marks the history row `FAILED` with the
   exception's message, in a fresh transaction (since the failed one was
   already rolled back), then re-raises.

**The second real bug found while testing this**: `category_source_map`
(used to resolve which existing Store `Category` a mapping/recommendation
applies to) was keyed by `IndustryTemplateCategory.pk` — but a Category
installed from an *older* template version has
`source_template_category` pointing at that **old** version's row, whose
PK is naturally different from the *new* version's same-`code` row. Every
mapping/recommendation targeting a pre-existing category therefore
silently found nothing (`category is None → continue`) and was dropped
without error — a correctness bug that would have made every "add a new
optional Attribute mapping to an existing Category" scenario from the
prompt's own §19 worked example fail silently. Fixed by keying
`category_source_map` (and `_apply_category_additions`'s internal parent
resolution) by the stable `code` string throughout, matching how
`attribute_source_map` was already correctly keyed. Caught by
`test_atomic_rollback_on_failure` needing a `mock.patch` on
`CategoryRecommendedOption.objects.get_or_create` to force a failure —
the mock was never being reached until this fix, which is what surfaced
the bug.

12 tests cover apply-all, apply-subset (with correct skip tracking),
customization preservation, merchant-created-record preservation, update
history recording, duplicate-apply rejection, rejecting
review-required/blocked selection, atomic rollback on mid-transaction
failure (verified via `unittest.mock.patch`, confirming zero partial
writes survive), and cross-family target rejection.

## 14. Stale and Duplicate Request Handling

Duplicate submission: `already_completed` check at the top of
`apply_template_update` (§13.1). Stale plan: every apply recomputes the
plan itself rather than trusting anything passed in (§13.2) — the
dashboard view (`settings_industry_update_apply`) also recomputes
`plan_template_update` server-side before filtering the submitted
`change_id` list against the **freshly computed** `safe_ids` set, so a
tampered or outdated set of change-ids from the client can only ever
narrow what gets applied, never widen it
(`test_tampered_change_id_ignored_not_applied`).

## 15. Update History

`StoreTemplateUpdate`: `store`, `installation`, `from_template`,
`target_template`, `actor` (nullable, `SET_NULL`), `status`
(pending/completed/failed), `idempotency_key` (unique), `started_at`
(`auto_now_add`), `completed_at`, `selected_change_ids`/
`applied_changes`/`skipped_changes`/`conflicts` (all `JSONField` lists —
structured, not free text), `failure_reason`. `clean()` enforces the
installation belongs to the same Store, the target is the same family,
and target ≠ from (no self-update). Viewable per-Store
(`settings_industry_update_history`, `-started_at` ordering) — verified
Store-isolated (`test_other_store_history_not_visible`).

## 16. Schema Override UI

The Category Attribute Schema modal (`category_schema_list.html`) gained
three tri-state toggle buttons (filterable/comparable/searchable — each
cycling `None → True → False → None` via
`category_schema_toggle_override`, one shared endpoint keyed by a
`field` POST param) and one boolean toggle
(`is_visible_on_storefront`). Every button's label distinguishes
"inherited from Attribute default (currently X)" from an explicit
Store-level override — the merchant always sees which state they're in,
never an ambiguous checkbox. Both new endpoints are
`CATEGORY_MANAGE`-gated, Store-scoped (`get_object_or_404(...,
category=category)`), and covered by 7 new tests including cross-category
404 and Analyst-denied.

## 17. Platform Administration

Not extended this phase beyond what Phase 1E's admin registrations
already expose (`IndustryTemplate`/`*Category`/`*Attribute`/etc. via
Django admin, `StoreIndustryInstallation` read-only). `readiness` and
`content_fingerprint` are visible as ordinary model fields on the
existing `IndustryTemplateAdmin` list/detail view without further
customization needed; `IndustryTemplateValidationResult` and
`StoreTemplateUpdate` were **not** registered in Django admin this
phase — a named gap, see §27.

## 18. Industry Templates — 30 Total

The 10 Phase 1E founding templates are unchanged (`apps/catalog/seed_data/industry_templates.py`,
untouched). 20 new templates were added across 6 new logical-group files
under `apps/catalog/industry_templates/` (not one giant dictionary, per
the prompt's own §28 instruction), aggregated by `registry.py`:

| File | Industries |
|---|---|
| `fashion_extra.py` | watches, eyewear, bags-luggage |
| `family.py` | toys-children, baby-products, sports-fitness |
| `beauty_health.py` | health-personal-care, skincare, haircare, makeup |
| `auto_hardware.py` | automotive-parts, motorcycle-parts, tools-hardware, electrical-lighting |
| `home_living.py` | kitchenware, bedding-bath, pet-supplies |
| `lifestyle.py` | flowers-gifts, digital-products-software, musical-instruments |

All 30 (verified by a fresh `seed_industry_templates` run + `validate_industry_templates --strict`):

Exact metrics, from a real `validate_industry_templates --json` run
against the seeded database (not estimates):

| Slug | Categories | Attributes | Values | Mappings | Recommendations | Score |
|---|---|---|---|---|---|---|
| clothing-fashion | 8 | 9 | 31 | 15 | 6 | 75 |
| shoes | 4 | 6 | 26 | 12 | 8 | 95 |
| perfume-cosmetics | 5 | 12 | 29 | 50 | 10 | 95 |
| mobile-phones | 3 | 12 | 26 | 16 | 5 | 95 |
| computers-laptops | 4 | 9 | 16 | 12 | 5 | 95 |
| home-appliances | 4 | 7 | 10 | 24 | 4 | 95 |
| jewelry-accessories | 5 | 7 | 22 | 22 | 5 | 95 |
| books-stationery | 4 | 7 | 16 | 8 | 3 | 90 |
| food-grocery | 5 | 6 | 10 | 25 | 5 | 95 |
| furniture-decor | 5 | 6 | 15 | 25 | 5 | 95 |
| watches | 4 | 9 | 25 | 28 | 8 | 100 |
| eyewear | 4 | 7 | 22 | 14 | 2 | 100 |
| bags-luggage | 4 | 8 | 19 | 12 | 5 | 100 |
| toys-children | 5 | 6 | 12 | 25 | 3 | 100 |
| baby-products | 5 | 7 | 17 | 22 | 3 | 100 |
| sports-fitness | 5 | 7 | 24 | 11 | 3 | 100 |
| health-personal-care | 4 | 7 | 12 | 20 | 2 | 100 |
| skincare | 5 | 7 | 20 | 23 | 4 | 100 |
| haircare | 5 | 6 | 14 | 21 | 2 | 100 |
| makeup | 5 | 6 | 12 | 21 | 4 | 100 |
| automotive-parts | 5 | 6 | 13 | 18 | 1 | 100 |
| motorcycle-parts | 4 | 6 | 12 | 7 | 1 | 100 |
| tools-hardware | 5 | 6 | 8 | 10 | 0 | 100 |
| electrical-lighting | 5 | 7 | 15 | 10 | 2 | 100 |
| kitchenware | 5 | 7 | 13 | 17 | 3 | 100 |
| bedding-bath | 4 | 6 | 12 | 13 | 4 | 100 |
| pet-supplies | 4 | 6 | 20 | 14 | 1 | 100 |
| flowers-gifts | 4 | 5 | 14 | 13 | 2 | 100 |
| digital-products-software | 4 | 6 | 15 | 9 | 0 | 100 |
| musical-instruments | 5 | 6 | 11 | 16 | 2 | 100 |

**All 30 are `production_ready`, pass
strict validation with 0 errors, and installed successfully in a
dedicated automated test** (`test_every_seeded_industry_installs_cleanly`,
extended from Phase 1E's 10-template version to run against all 30).
`test_every_template_is_production_ready_after_seed` additionally asserts
every seeded template has a non-empty `content_fingerprint` after
seeding.

Every one of the 10 founding templates still shows the same
`USEFULNESS_NO_FILTERABLE` warning noted honestly in Phase 1E's own
mapping data (they predate this phase's filterable-flag quality bar) —
**deliberately not retroactively edited**, since `IndustryTemplate` rows
are immutable-by-convention once created (ADR-25/27); all 20 new
templates explicitly set `is_filterable=True` on their most useful
Attributes and score 100 as a result.

## 19. Models

**Modified:**
* `IndustryTemplate` — `+readiness` (`CharField`, choices, default
  `draft`), `+content_fingerprint` (`CharField(64)`, blank), `+is_offerable_for_new_installation` property.
* `AttributeValue` — `+source_template_value` (nullable FK to
  `IndustryTemplateAttributeValue`, `SET_NULL`).

**Created:**
* `IndustryTemplateValidationResult` — `OneToOneField` to
  `IndustryTemplate`; `fingerprint`, `validator_version`, `status`,
  `quality_score`, `errors`/`warnings`/`infos`/`metrics` (`JSONField`),
  `duration_ms`; `is_stale` property comparing its `fingerprint` against
  the live template's current `content_fingerprint`.
* `StoreTemplateUpdate` — see §15 for full field list; unique
  `idempotency_key`; `clean()` enforces same-Store installation,
  same-family target, no self-update.

## 20. Migrations

One migration: `apps/catalog/migrations/0013_attributevalue_source_template_value_and_more.py`
— purely additive (2 new fields + 2 new models), confirmed via
`makemigrations --check --dry-run` throughout the phase. Applied cleanly
against the Phase 1E database with all 10 existing templates, their
installations, and every dependent Category/Attribute/CategoryAttributeSchema
row intact and unmodified.

## 21. Services

| Service | Responsibility | Transactions |
|---|---|---|
| `template_validation_service` | Structural/semantic validation, fingerprinting, readiness persistence | `validate_and_persist` mutates via targeted `.update()` calls, no explicit atomic block needed (single-row updates) |
| `template_preview_service` | Merchant preview + Store-derived installation impact plan | Read-only |
| `template_comparison_service` | Stable-code diff between two template versions | Read-only |
| `template_customization_service` | Store-record vs. immutable-source drift detection | Read-only |
| `template_update_service` | Update plan classification + atomic, idempotent apply | `apply_template_update` wraps all mutation in one `transaction.atomic()`; history row created/failed outside it |
| `industry_template_service` (modified) | Deep-copy installation; now also enforces the readiness gate and sets `source_template_value` | `install_industry_template` (unchanged: `@transaction.atomic`) |

## 22. Routes and APIs

| Method | Path | Permission | Store scope | Notes |
|---|---|---|---|---|
| GET | `settings/industry/<id>/preview/` | `SETTINGS_MANAGE` | Store resolved server-side; template unscoped (platform-owned) | Preview + impact plan |
| GET | `settings/industry/update/` | `SETTINGS_MANAGE` | Installation resolved from `request`'s Store only | Redirects with a message if no installation or no update available |
| POST | `settings/industry/update/apply/` | `SETTINGS_MANAGE` | Same | Re-derives plan; filters submitted `change_id`s against fresh `safe_additive` |
| GET | `settings/industry/update/history/` | `SETTINGS_MANAGE` | `StoreTemplateUpdate.objects.filter(store=store)` | Store-isolated (tested) |
| POST | `categories/<id>/schema/<entry_id>/toggle-override/` | `CATEGORY_MANAGE` | `category=get_object_or_404(..., store=store)`, `entry` re-scoped to that category | Tri-state cycle |
| POST | `categories/<id>/schema/<entry_id>/toggle-visibility/` | `CATEGORY_MANAGE` | Same | Boolean toggle |

All POST endpoints are CSRF-protected via standard Django middleware (no
opt-outs); errors surface via the existing `messages`/`HX-Trigger` toast
patterns already used everywhere else in this codebase.

## 23. UI

Template preview page (full-page, not a modal, given content volume):
readiness/count badges, recursive category tree with per-node
attribute/recommendation annotations, a Store-specific impact section
(blocking-errors-or-counts), and static policy text. Update-plan page:
three sections (✅ safe additive with pre-checked checkboxes, 🔍
review-required with a field-level `old → new` change list, ⛔ blocked
with a reason string per entry) plus a single confirm-and-submit form.
Update-history page: a plain table (from/to version, status badge,
applied/skipped counts, start/end timestamps), an explicit empty state
("هنوز هیچ به‌روزرسانی‌ای انجام نشده است"). All templates reuse the
existing `.card`/`.btn`/`.badge`/table classes verbatim — no new CSS, no
new JS framework. Responsive behavior is inherited from the existing
`base_admin.html` layout, unchanged.

## 24. Permissions

No new permission keys (matching Phase 1D/1E's own discipline):
`SETTINGS_MANAGE` gates preview/update-plan/update-apply/update-history
(installing a Store's entire catalog foundation, or changing it, is an
owner/admin-tier action, same as Phase 1E's install endpoint);
`CATEGORY_MANAGE` gates the new schema-override toggles (already governs
the rest of the Category Attribute Schema surface). Verified per role:
Owner/Administrator allowed everywhere new; Catalog Manager denied on
update-apply (`test_catalog_manager_cannot_apply_update`) but allowed on
schema management (unchanged from Phase 1E); Analyst denied on schema
override toggles; anonymous denied (302 to login) on every new view.

## 25. Tenant Isolation

Every new endpoint resolves through `_resolve_dashboard_store(request)`
or a Store-scoped parent object — never a raw submitted ID. Audited and
tested: cross-Store update history is invisible
(`test_other_store_history_not_visible`), a cross-category schema-entry
ID 404s (`test_override_entry_from_other_category_404s`), a tampered/
foreign `change_id` in the update-apply POST is silently dropped rather
than trusted (`test_tampered_change_id_ignored_not_applied`), and
customization detection for one Store's installation never reflects
another Store's edits (`test_other_store_isolation`).
`IndustryTemplate`/`IndustryTemplateCategory`/etc. themselves remain
intentionally unscoped (platform-owned, readable by any authenticated
Store admin, per ADR-22) — the tenant boundary is enforced at the
Store-owned-record layer (Category/Attribute/Schema/Update), not by
hiding the shared template catalog.

## 26. Security

Authorization: `staff_required` + `permission_required` on every new
view, no exceptions. Host enforcement: inherited unchanged from the
existing admin-subdomain middleware. CSRF: standard Django middleware.
Plan tampering: never trusted — every apply recomputes server-side
(§13.2, §14). Stale update: same mechanism. Duplicate submission:
idempotency-key check. Remaining risk: none newly introduced that
adversarial testing surfaced; the same known, pre-existing limitations
from earlier phases (coarse-grained `SETTINGS_MANAGE`/`CATEGORY_MANAGE`
permission keys, no dedicated CSRF-specific test coverage anywhere in
this codebase) apply equally here, unchanged.

## 27. Known Limitations

Named precisely, per this session's standing practice:

* **`review_required` changes are never auto-applicable, even with
  explicit per-item merchant selection.** `apply_template_update` raises
  if asked to apply one. This is ADR-29's deliberate, documented scope
  line — safely applying a rename/retype on data that existing Products
  may already depend on is a harder problem than this phase's additive
  slice was scoped to solve. Named here, not hidden.
* **No update-application path for `removed` entries at all** — a
  Category/Attribute/Value/Mapping/Recommendation removed in a newer
  template version is always `blocked`, with no supported way to also
  remove it from an installed Store even if the merchant wants to. This
  matches the prompt's own "never automatically overwrite/delete"
  instruction taken to its logical conclusion, but it is a real,
  permanent gap in this phase's update coverage, not a temporary one.
* **`IndustryTemplateValidationResult` and `StoreTemplateUpdate` are not
  registered in Django admin.** Platform operators can inspect them via
  the ORM/shell or the `validate_industry_templates`/`--json` command
  output, but not through a dedicated admin list view yet.
* **A Store can still only ever install one Industry family, for its
  entire lifetime** (ADR-25, unchanged this phase) — the update workflow
  lets it move to a newer *version of the same family*, never switch
  families.
* **The 10 Phase 1E founding templates were not retroactively edited**
  to add `is_filterable` flags even though the new quality framework
  flags their absence as a warning — respecting template-row immutability
  over chasing a perfect score on pre-existing content (§18).
* **No quality-score trend/history over time** — each validation run
  overwrites the single cached `IndustryTemplateValidationResult` row;
  there is no historical record of how a template's score changed across
  re-validations (only across *versions*, which are separate rows).

## 28. Remaining Prototype Gaps

None beyond what §3 already states: no prototype exists for this phase's
scope, so there is nothing to compare against or reproduce faithfully.

## 29. Recommended Next Phase

In priority order:

1. **Storefront consumption** — still the single most-repeated
   recommendation across every phase report in this session
   (Phase 1D/1E/1F all name it); nothing in the admin-side engine this
   phase built has any shopper-facing consumption yet.
2. **`review_required` change application** — a dedicated design pass
   for safely applying a rename/retype/parent-change onto an
   uncustomized installed record, including what happens to any
   `ProductAttributeValue`/`Product` rows that depend on the old shape.
3. Django admin registration for `IndustryTemplateValidationResult` and
   `StoreTemplateUpdate` (§27) — a small, self-contained follow-up.
4. Then, per every prior phase's still-valid recommendation: wallet/
   cashback/referral, subscription/billing, staff invitation lifecycle,
   domain-management UI, inventory ledger, bulk import/export — none
   started, all still open.

## 30. Git Summary

* **Branch:** `claude/docs-prototypes-review-jxm6aw`
* **Commits this phase:** 9 incremental checkpoints (models/ADRs →
  services → 20 templates → seed wiring → UI → 4 test batches), each
  pushed immediately after a passing focused test run, specifically to
  bound any repeat of the session-loss failure disclosed in §2.
* **Migrations:** 1 new
  (`catalog.0013_attributevalue_source_template_value_and_more`), purely
  additive, `makemigrations --check --dry-run` clean.
* **Industry count:** 30 (10 unchanged from Phase 1E + 20 new), all
  `production_ready`, all passing `validate_industry_templates --strict`
  with 0 errors, all installing successfully in an automated test.
* **Tests:** 124 new this phase (22 validation-service + 11 command +
  9 preview + 15 comparison + 19 customization + 21 update-service + 18
  dashboard update-views + 7 schema-override + 1 readiness-gate + 1
  seed-production-ready) plus targeted fixture updates to 2 pre-existing
  Phase 1E test files for the new readiness gate.
* **Final full suite** (`python manage.py test`, run as the last step
  after every code change in this phase): **2242 tests, 0 failures, 0
  errors** (2118 from the end of Phase 1E + 124 new this phase — exact
  arithmetic match). `python manage.py check` and
  `makemigrations --check --dry-run` both clean immediately before this
  run. All ERROR/WARNING/Traceback lines visible in the raw suite output
  are expected —`logger.error`/`logger.warning` calls from tests that
  deliberately exercise failure paths (Zibal gateway errors, SMS
  template/provisioning errors, disallowed-host rejection) and assert on
  the resulting exception/response, the same pattern present in every
  prior phase's equivalent run.
