# Storefront Builder V2 — Phase 4 (Header/Footer Composer) Final Report

**Branch:** `claude/family-visual-fidelity-fix`
**Audit doc:** `docs/architecture/STOREFRONT_BUILDER_V2_PHASE_4_AUDIT.md`
**Slice 1 commit:** `3b482f3b94068a466f04e86f41c7f85d7722d984`
**Closure commit:** see final commit SHA at the end of this report.

## 1. Objective

Give merchants a structured, validated Header/Footer composer that stays global
(owned by `StorefrontLayoutVersion.header_config`/`footer_config`, never a
page or `StorefrontSection`), and prove — with tests, not assumptions — that
the same Header/Footer from the same published version renders identically
across all six public page types. This is explicitly the class of bug the
legacy per-family template architecture was prone to.

## 2. Audit findings (recap)

The full read-only audit is in `STOREFRONT_BUILDER_V2_PHASE_4_AUDIT.md`.
Summary of what it found already correct vs. genuinely missing:

**Already correct (no gap, confirmed by reading code):**
- Header/footer config lives only on `StorefrontLayoutVersion` (Draft/Published),
  never on `Store` or `StorefrontPage`.
- All six public routes funnel through the same
  `build_universal_storefront_context()` → `storefront_shell.html` →
  `page_shell_header.html`/`page_shell_footer.html` — no per-view override.
- `Menu`, `SocialLink`, `FooterTrustBadge`, `FooterPaymentLogo` are all
  store-scoped **at render time**, not just at creation time.
- Authorization (`@staff_required` + `@permission_required(STOREFRONT_LAYOUT_MANAGE)`)
  and CSRF (global Django middleware, no `csrf_exempt` anywhere in this app)
  already apply uniformly to every editor endpoint including header/footer.

**Real gaps found and closed:**
1. **No per-component responsive visibility** for header/footer components —
   closed in Slice 1.
2. **No reusable schema-description pattern** for header/footer validation
   (ad-hoc dict-scrubbers) — strengthened additively in Slice 1.

**Real gap found, deliberately NOT closed this phase (documented boundary):**
3. **11 family-specific header/footer templates bypass the canonical shell.**
   Fixing this means refactoring 11 production templates — a large, separate
   undertaking disproportionate to "Header/Footer Composer," and the master
   prompt explicitly permits family-specific partials to remain temporarily
   as an isolated compatibility boundary, provided no new family-specific
   functionality is added to them. Nothing in Phase 4 touched any of the 11
   family template files.
4. **No multi-menu/ordering selection** — `Menu.UniqueConstraint(store, location)`
   means there is structurally only ever one menu per location; building
   real multi-instance selection is a materially larger schema change than
   this phase's scope, and risks the "generic page-builder-inside-the-header-
   builder" over-engineering the master prompt warns against.
5. **Newsletter's double-gate** (`footer_config.show_newsletter` AND legacy
   `FooterSettings.show_newsletter`) is inconsistent with badges/logos'
   single-gate pattern, but it predates this phase, gates a still-non-
   functional legacy placeholder, and changing it now risks altering
   behavior for stores already relying on the double-gate. Left as documented
   legacy behavior.

## 3. Existing systems reused (nothing rebuilt)

- The exact `hide_on_tablet`/`hide_on_mobile` + `data-hide-*` attribute + CSS
  media-query mechanism already established for section-level responsive
  visibility (`.rsec[data-hide-*]` in `apps/core/static/css/layout.css`) —
  extended with a parallel `[data-shell-hide-tablet]`/`[data-shell-hide-mobile]`
  rule pair for shell components, not a new mechanism.
- `header_editor.html`/`footer_editor.html` and their htmx panel partials
  (`header_panel.html`/`footer_panel.html`) were extended in place, not
  replaced.
- `SocialLink`, `Menu`/`MenuItem`, `FooterTrustBadge`, `FooterPaymentLogo`,
  `FooterSettings`, `Category` — all reused as-is; nothing duplicated.

## 4. Slice 1 — per-component responsive visibility (commit `3b482f3`)

- `HEADER_CONFIG_DEFAULTS`/`FOOTER_CONFIG_DEFAULTS` (`models.py`) gained an
  additive `responsive` sub-dict: an explicit allowlist of "responsive-aware"
  component keys (4 for header — `show_search`, `show_account`,
  `show_wishlist`, `announcement_enabled`; all 9 for footer), each holding
  `{hide_on_tablet, hide_on_mobile}` booleans. `show_cart` and `sticky` are
  deliberately excluded from the header allowlist (cart access must never be
  hideable — this matches the pre-existing `validate_header_config` rule
  that rejects `show_cart=False` outright; `sticky` is behavior, not a
  visible element).
- `layout_service._validate_shell_component_responsive()` cleans/whitelists
  the sub-dict inside `validate_header_config`/`validate_footer_config`.
- `views._extract_shell_responsive_raw()` reads the new
  `{key}__hide_on_tablet`/`{key}__hide_on_mobile` checkboxes from POST.
- New shared partial `shell_component_responsive_fields.html`, wired into
  both the dashboard editor templates and their htmx panel partials.
- `page_shell_header.html`/`page_shell_footer.html` emit
  `data-shell-hide-tablet`/`data-shell-hide-mobile` attributes per component,
  scoped to the canonical (non-family) shell only — consistent with the
  documented family boundary (finding 3 above).
- `layout.css`: new `[data-shell-hide-tablet]`/`[data-shell-hide-mobile]`
  media rules, plus a `.sfb-shell-inline{display:contents}` class for a
  search-form wrapper that previously had no box of its own — a **class**,
  not an inline `style`, so the more-specific media-query attribute selector
  can still override it (inline styles always win over stylesheet rules
  regardless of selector specificity, which would have silently broken the
  hide behavior).

## 5. Closure slice — test coverage for previously-code-only-verified claims

The audit's own §11 flagged three areas that were true by code inspection
but had no direct test asserting them. This slice adds that evidence,
without changing any production behavior:

- **`test_all_six_public_page_types_render_identical_header_footer`**
  (`test_page_shell.py`) — publishes one version with a header/footer marker
  and a responsive rule, then asserts the marker, the responsive attribute,
  and the footer all appear identically across Home, Product Detail,
  Listing, Collection, Search, and Cart.
- **`test_social_link_and_menu_never_leak_across_stores`**
  (`test_page_shell.py`) — two real stores, two hosts, distinct
  `SocialLink`/`Menu`/`MenuItem` rows; asserts Store A's public Home page
  never contains Store B's social URL or menu item text. This is the first
  test that exercises tenant scoping for these two models specifically
  through the canonical shell's actual render path (previously only
  confirmed by reading the `store=store` filter in code).
- **`test_header_editor_anonymous_denied`/`test_footer_editor_anonymous_denied`/
  `test_header_editor_without_storefront_permission_denied`**
  (`test_views.py::EditorAccessTests`) — the same `@staff_required` +
  `@permission_required(STOREFRONT_LAYOUT_MANAGE)` stack already proven for
  the main editor/preview endpoints, now asserted directly against the two
  Phase 4 endpoints.
- **`test_header_editor_without_csrf_token_rejected`/
  `test_footer_editor_without_csrf_token_rejected`**
  (`test_views.py::CsrfEnforcementTests`) — same global CSRF middleware,
  now asserted directly against the two Phase 4 POST endpoints, including
  that a rejected request leaves `draft.header_config`/`footer_config`
  unchanged.

## 6. Final Header architecture

- **Owner:** `StorefrontLayoutVersion.header_config` (JSONField), Draft/Published
  via the existing pointer-swap `publish()` — never mutated in place.
- **Components:** `show_search`, `show_account`, `show_cart` (always-on,
  cannot be hidden on any device), `show_wishlist`, `sticky` (behavior flag),
  `announcement_enabled` + `announcement_text`.
- **Responsive:** the 4 non-cart, non-behavior components carry an optional
  `hide_on_tablet`/`hide_on_mobile` pair; desktop is always the visibility
  baseline.
- **Navigation:** the category mega-menu (`nav_categories`) and the header
  `Menu` (`Menu.Location.HEADER`) are structural, not gated by a config
  toggle — consistent with how section-level navigation content is treated
  elsewhere in the builder.
- **Store identity:** `SHOP_NAME`/`SHOP_LOGO`/`SHOP_TAGLINE` come from the
  existing global context processors, not re-declared per shell.

## 7. Final Footer architecture

- **Owner:** `StorefrontLayoutVersion.footer_config` (JSONField), same
  Draft/Published lifecycle as header.
- **Components:** 9 boolean gates (`show_about`, `show_contact`,
  `show_quick_links`, `show_categories`, `show_social`, `show_trust_badges`,
  `show_payment_logos`, `show_newsletter`, `show_copyright`), all 9 now
  responsive-aware.
- **Content sources:** `footer_config` remains pure gating; actual content
  (about text, contact info, trust badges, payment logos, newsletter copy)
  continues to live in the separate, non-versioned `FooterSettings`/
  `FooterTrustBadge`/`FooterPaymentLogo` models, edited from their own
  dashboard screen outside the Draft/Publish cycle — unchanged this phase,
  and explicitly out of scope (these are live shop-identity data, not
  builder content, per the editor's own existing copy).

## 8. Draft/Published lifecycle (confirmed, not changed)

`header_config`/`footer_config` are written only to
`layout_service.get_or_create_draft(...)`'s result by both editor views.
`layout_service.publish()` is the only place `published_version` is
reassigned, and it is a pure pointer swap — draft content is never copied
into or mutated on the published row. Verified end-to-end by
`test_draft_header_changes_do_not_appear_publicly_before_publish` and
`test_published_header_changes_appear_publicly_after_publish`.

## 9. Responsive architecture

Reuses the exact `hide_on_tablet`/`hide_on_mobile` boolean pair and CSS
media-query breakpoints (1001px+ desktop, 681–1000px tablet, ≤680px mobile)
already established for section-level content. No new visibility system was
introduced. Applies only to the canonical (non-family) shell partials.

## 10. Tenant isolation

- `header_config`/`footer_config` live on a `StorefrontLayoutVersion`, which
  belongs to exactly one `Store` via `StorefrontLayout.store` — no
  cross-store reference is structurally possible.
- Every referenced content model (`Menu`/`MenuItem`, `SocialLink`,
  `FooterTrustBadge`, `FooterPaymentLogo`, `Category`) is filtered by
  `store=store`/`store_id=...` at render time, confirmed both by code
  reading (audit §8, §10) and now by a direct cross-store leak test
  (§5 above).
- Editor views resolve the store via the same `resolve_store_for_service`
  used across the whole app (host-based resolution), so there is no
  unscoped/client-supplied store ID anywhere in this surface.

## 11. Legacy compatibility boundary (documented, unchanged)

1. `uses_universal_shell=False` → `templates/base.html`'s own hardcoded
   header/nav/footer, reading `FooterSettings`/`Menu` directly.
   `header_config`/`footer_config` are not even in scope. This is also where
   `mobileNavOpen`/`catMenuOpen`/`loginOpen` are declared
   (`<body x-data="{ loginOpen: false, mobileNavOpen: true, catMenuOpen: false }">`)
   — shared by every page that extends this base template, including the
   canonical-shell pages, and predates this phase entirely; confirmed
   unaffected by Phase 4's changes during browser QA (§13).
2. `uses_universal_shell=True`, `family_slug=None` → canonical
   `page_shell_header.html`/`page_shell_footer.html`, the surface this
   phase changed.
3. `uses_universal_shell=True`, `family_slug` set → one of 11 family
   variants, untouched this phase, still gated by the same
   `header_config`/`footer_config` keys via bespoke markup.
4. Newsletter's legacy double-gate (§2, finding 5) — unchanged.

## 12. Family compatibility boundary — confirmed not touched

No file under
`apps/storefront_builder/templates/storefront_builder/partials/families/`
was modified this phase. `grep` over the diff confirms the only template
changes are `page_shell_header.html`, `page_shell_footer.html`, and the
dashboard editor templates/partials. The 11 family variants keep rendering
their own hand-maintained header/footer, independent of the new `responsive`
config key (they simply never read it, which is safe — an unread additive
key is a no-op for them).

## 13. Tests actually run this phase

Targeted, per the standing test policy (no 700+/2700+ suites run):

- `ValidateHeaderConfigTests`/`ValidateFooterConfigTests` (`test_layout_service.py`)
  — including new responsive round-trip/default/unknown-key cases.
- `HeaderFooterEditorTests` (`test_views.py`) — including new
  save/render/absent-by-default responsive cases.
- `EditorAccessTests`, `CsrfEnforcementTests` (`test_views.py`) — including
  new header/footer-specific anonymous-denied, permission-denied, and
  CSRF-rejected cases.
- `SharedPageShellTests` (`test_page_shell.py`) — including the new
  six-page-consistency and cross-store-isolation tests.
- `apps.content.tests.test_footer_config`,
  `apps.storefront_builder.tests.test_public_homepage_integration`,
  `apps.storefront_builder.tests.test_responsive_rendering` — 129 tests, OK
  (Slice 1 run).
- `apps.content.tests.test_navigation`, `apps.content.tests.test_social_links`
  — re-run this slice as directly-affected regression coverage for the new
  cross-store test's models.
- `manage.py check` — clean, both slices.
- `manage.py makemigrations --check --dry-run` — no drift, both slices
  (this phase never changed a model field, only Python-level default dicts
  and validators).

Not run (per policy): the ~700-test `storefront_builder` suite, the
~2700-test cross-app suite, the full project suite. Left for the owner's
local Heavy Gate.

## 14. Browser QA — exact evidence

Real gap: `kianstock-qa`, the standing QA store from Phases 2–3, has
`family_slug=sarv_stock` — meaning it renders through the family-specific
header/footer templates (§12), not the canonical shell this phase actually
changed. Testing Phase 4's new responsive controls there would have proven
nothing. A second, dedicated QA store was created for this phase:

- **Store:** `sfb-phase4-qa` (`family_slug=None`, canonical shell),
  host `sfb-phase4-qa.rastisi.localhost:8000`, owner `p4_qa_owner` /
  `Phase4QaPass1!`. One vendor, one parent+child category, one product, one
  collection, one header `Menu` with a category-destination item, one
  `SocialLink`, `FooterSettings` with newsletter/contact enabled,
  `ShopSettings` provisioned.
- **Published header/footer config used for QA:** `announcement_enabled`
  with `hide_on_tablet=True, hide_on_mobile=False`; `show_wishlist` with
  `hide_on_tablet=False, hide_on_mobile=True`; all other components on.

Verified with Playwright (pre-installed Chromium,
`/opt/pw-browsers/chromium-*/chrome-linux/chrome`, `--no-sandbox`) across
desktop (1440×900), tablet (800×1024), and mobile (375×812):

| Page type | URL | Desktop | Tablet | Mobile |
|---|---|---|---|---|
| Home | `/` | 200, all checks pass | 200 | 200 |
| Product Detail | `/products/p4-product-1/` | 200 | 200 | 200 |
| Listing | `/products/` | 200 | 200 | 200 |
| Collection | `/collections/<slug>/` | 200 | 200 | 200 |
| Search | `/products/?q=...` | 200 | 200 | 200 |
| Cart | `/cart/` | 200 | 200 | 200 |

Checked on every page/viewport combination: announcement marker text
present when expected, search form present, cart link present, account
control present, footer copyright/social/newsletter present, the
`data-shell-hide-tablet`/`data-shell-hide-mobile` attributes present, mobile
hamburger markup present, no family-variant markup leaked into the
canonical-shell store's pages. **Zero browser console errors or page errors**
across all 15 page/viewport combinations.

**Visual confirmation (screenshots) of the responsive feature itself, on
Home:**
- Desktop (1440px): announcement bar visible, wishlist heart icon visible.
- Tablet (800px): announcement bar **hidden** (as configured
  `hide_on_tablet=True`), wishlist heart icon visible.
- Mobile (375px): announcement bar visible, wishlist heart icon **hidden**
  (as configured `hide_on_mobile=True`).

This is an exact match to the configured per-component, per-breakpoint
visibility rules — the feature works as designed, confirmed visually, not
just via attribute presence in the HTML.

**Mobile menu:** clicking the header burger button on the mobile viewport
does toggle the `nav` element's `hidden` class (Alpine `mobileNavOpen`
state changes on click, confirmed via direct DOM inspection). The nav
starts in the "open" state by default on load (`mobileNavOpen: true`, set
in `templates/base.html`, shared by every page including the canonical
shell) — this is pre-existing, unrelated to Phase 4, identical across all
six page types, and outside this phase's scope (the audit explicitly
classified the mobile hamburger/drawer as "unconditional Alpine/CSS wiring,
not gated by any config key"). Not treated as a Phase 4 bug.

**Draft preview / Published isolation / publish transition:** already
covered by the existing `SharedPageShellTests` methods (draft-only visible
in preview, invisible publicly before publish, visible publicly after
publish) — re-verified passing this phase, not re-tested manually in the
browser (redundant with automated coverage).

QA fixture cleanup: the dev server used for this QA session was stopped
after testing; the `sfb-phase4-qa` store and its data were left in place
(harmless, additive, useful for future phases' canonical-shell browser QA
the same way `kianstock-qa` serves family-shell QA) rather than deleted.

## 15. Known limitations / deferred items

- Family-specific header/footer templates (11 variants) still bypass the
  canonical composer — documented accepted boundary, not a Phase 4 blocker
  per the master prompt's own explicit permission.
- No multi-menu selection/ordering by ID — `Menu`'s
  `UniqueConstraint(store, location)` makes this a materially larger future
  schema change, not attempted this phase.
- Newsletter's legacy double-gate against `FooterSettings.show_newsletter`
  — pre-existing, undisturbed.
- The `templates/base.html` legacy-fallback mobile nav's "open by default"
  behavior is pre-existing and outside this phase's scope; noted here for
  visibility, not filed as a Phase 4 defect.

## 16. Final commit SHA

Bundle handoff for the closure slice: `RastiSi4_PHASE_4_FINAL_HANDOFF.bundle`
(commit SHA recorded in the handoff report delivered alongside this file).

## 17. Phase 5 prerequisites

Phase 4 is closed. Header/Footer are structurally global, validated,
responsive-aware, tenant-isolated (now test-proven, not just code-read), and
identically rendered across all six public page types from a single
published version — the prerequisite Phase 5 ("Product / Listing /
Collection / Search / Cart Composition") needs from the shell layer. No
outstanding Phase 4 gap blocks Phase 5 from starting once the owner
confirms the Heavy Gate.
