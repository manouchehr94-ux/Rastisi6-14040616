# Pre-Launch Phase 5 — Final eNamad Platform + Merchant Completion

## 1. Objective

Complete the eNamad integration UX for both RastiSi and merchant Stores:
a coherent lifecycle covering the Phase 1 technical-verification meta and a
new, safely-rendered final badge, ready for real eNamad values later
without any source-code change.

## 2. Architecture before this phase

Phase 1's technical-verification meta (platform + merchant) was already
complete (see the Phase 1 report). The post-issuance "final badge" concept
existed only as a single free-text field, `enamad_code` (merchant side,
inside `StoreIntegrationConnection.encrypted_credentials`), capped at 4000
characters with no structural validation, and had **no rendering path
anywhere** (confirmed by the architecture inventory — no template
referenced it). The platform side had no final-badge concept at all.

## 3. Official eNamad badge format — source

eNamad's real trust-seal embed is a well-documented, widely-referenced
public pattern (confirmed via multiple independent sources describing
real merchant sites' actual embedded markup):

```html
<a referrerpolicy="origin" target="_blank" href="https://trustseal.enamad.ir/?id={ID}&Code={CODE}">
  <img referrerpolicy="origin" src="https://trustseal.enamad.ir/logo.aspx?id={ID}&Code={CODE}" alt="">
</a>
```

Two eNamad-issued identifiers drive it: a numeric site `id` and an
alphanumeric `Code`. This is the basis for Section 4's structured design.

## 4. Decisions

### 4.1 Structured identifiers, not a free-text fragment

Per the master prompt's explicit instruction ("prefer storing structured
identifiers/fields and generating trusted markup from known eNamad URLs
rather than accepting arbitrary HTML/JavaScript... never create a
general-purpose arbitrary footer HTML injection feature"), the final badge
is represented as exactly two validated fields, not a pasted HTML/script
fragment:

- `enamad_id`: digits only, 1–12 characters (`^[0-9]{1,12}$`).
- `enamad_auth_code` (merchant)/`enamad_auth_code` (platform): alphanumeric,
  1–64 characters (`^[A-Za-z0-9]{1,64}$`).

`apps/stores/services/enamad_verification_service.py` gained
`parse_enamad_badge_identifiers(id, code)`, returning an
`EnamadBadgeIdentifiers` dataclass with `.profile_url`/`.logo_url`
computed from the **fixed** `TRUSTSEAL_BASE_URL =
"https://trustseal.enamad.ir/"` constant — never a user/DB-controlled
origin. Both identifiers must be present together (partial state is
rejected as an error, not silently accepted); both blank means "not
configured yet" (not an error). Templates render only these two
Django-auto-escaped URLs inside a fixed `<a>`/`<img>` structure — there is
no code path that renders arbitrary HTML from admin/merchant input.

The legacy `enamad_code` free-text field is retired (replaced by
`enamad_id`/`enamad_auth_code` in the integration's field list). Since it
was never rendered anywhere, this is a clean cutover with no migration
risk — any old stored `enamad_code` value simply becomes an inert,
unread key inside the existing flexible `encrypted_credentials` JSON blob.

### 4.2 Meta and badge are independent lifecycle states

Both merchant-side states live as different keys in the same
`StoreIntegrationConnection.encrypted_credentials` blob
(`verification_meta_tag` vs. `enamad_id`/`enamad_auth_code`), so a Store
can have either, both, or neither at any time — matching the master
prompt's explicit requirement ("do not require final badge information
merely to save the technical-verification meta"). Symmetrically on the
platform side, `PlatformConfiguration.enamad_verification_meta_tag` and
`enamad_id`/`enamad_auth_code` are separate model fields.

### 4.3 Explicit enable/disable switch (platform)

`PlatformConfiguration.enamad_badge_enabled` (default `False`) gates
platform badge display independently of whether the identifiers are
populated — an admin can stage the identifiers before going live, or turn
the badge off without clearing them. The merchant side does not need a
separate switch: `StoreIntegrationConnection.is_active` already serves
that role (the same flag that gates the technical meta).

### 4.4 Rendering scope: sitewide, not home-only, still tenant/domain-scoped

The technical-verification meta stays home-page-only (Phase 1, unchanged).
The final badge — a normal trust-badge display — renders **sitewide** on
public pages (matching how eNamad badges are conventionally shown, e.g. in
a footer, and how this codebase's own pre-existing generic
`FOOTER_TRUST_BADGES` mechanism already works), but keeps the exact same
tenant/domain guard as the meta: merchant badge only on that Store's own
**verified custom domain** (never a trial/platform subdomain, never
another Store), platform badge only on `RASTISI_PLATFORM_HOSTS` (never a
merchant storefront or the admin host). A shared helper,
`_store_owns_verified_custom_domain()`, was factored out of the existing
meta-tag function so the meta and badge renderers can never drift apart on
this guard.

### 4.5 Fail-closed on corrupt/legacy values

`store_enamad_badge_for_request()` and the platform context processor both
catch `EnamadBadgeError` and return `None`/omit the context keys rather
than raising — a corrupt or partial stored value (e.g. only one of the two
identifiers surviving some future data issue) never renders, matching
Phase 1's established pattern.

## 5. Files changed

- `apps/stores/services/enamad_verification_service.py` — added
  `EnamadBadgeError`, `EnamadBadgeIdentifiers`, `TRUSTSEAL_BASE_URL`,
  `parse_enamad_badge_identifiers()`, `store_enamad_badge_for_request()`;
  factored `_store_owns_verified_custom_domain()` /
  `_store_enamad_connection()` out of the existing meta function; updated
  `validate_enamad_integration_values()` for independent meta/badge
  validation.
- `apps/stores/integrations/registry.py` — eNamad provider's `fields`
  replaced `enamad_code` with `enamad_id` + `enamad_auth_code`.
- `apps/core/context_processors.py` — `shop_settings` now also exposes
  `SHOP_ENAMAD_BADGE_PROFILE_URL`/`SHOP_ENAMAD_BADGE_LOGO_URL`.
- `templates/base.html` — renders the merchant badge in the footer
  (adjacent to the existing generic trust-badges block) when present.
- `apps/portal/models.py` — `PlatformConfiguration` gained `enamad_id`,
  `enamad_auth_code`, `enamad_badge_enabled`.
- `apps/portal/migrations/0009_platformconfiguration_enamad_auth_code_and_more.py`
  — new fields.
- `apps/portal/services/platform_config_service.py` —
  `update_platform_configuration()` validates the id/code pair together.
- `apps/portal/forms.py` — `PlatformConfigurationForm.clean()` validates
  the pair (mirrors the existing per-field `clean_enamad_verification_meta_tag`).
- `apps/portal/context_processors.py` — `platform_enamad_verification`
  extended (not replaced) to also expose the badge sitewide on platform
  hosts, independent of the home-only meta.
- `apps/portal/templates/portal/base_platform.html` — renders the platform
  badge in the footer.
- `apps/portal/templates/portal/platform_admin/configuration.html` —
  eNamad card now walks through the full lifecycle (meta → verify → badge
  identifiers → enable switch) with concise Persian help text.
- Tests: `apps/stores/tests/test_enamad_verification.py` (+17 tests),
  `apps/portal/tests/test_platform_enamad_verification.py` (+5 tests),
  `apps/portal/tests/test_platform_configuration.py` (+3 tests),
  `apps/dashboard/tests/test_integration_views.py` (updated 3 pre-existing
  tests off the retired `enamad_code` field, +1 new test).

## 6. Migrations

`apps/portal/migrations/0009_platformconfiguration_enamad_auth_code_and_more.py`
— adds `enamad_id`, `enamad_auth_code`, `enamad_badge_enabled` to
`PlatformConfiguration`. No merchant-side migration was needed —
`StoreIntegrationConnection.encrypted_credentials` is already a flexible
encrypted JSON blob, so changing which keys the eNamad provider reads/writes
inside it requires no schema change.

## 7. Models/services/views/templates/routes added or changed

See Section 5. No new views/URLs were needed on either side — the
merchant integrations page is already fully generic (driven by
`IntegrationProvider.fields`, Section 4.1), and the platform side reuses
the existing `/configuration/` view and form.

## 8. Security decisions

- No `mark_safe()`/raw-HTML rendering anywhere in the badge path — only
  two regex-validated identifiers ever reach a template, and only inside a
  fixed `<a href="{{ profile_url }}"><img src="{{ logo_url }}"></a>`
  structure pointed at a hardcoded `trustseal.enamad.ir` origin.
- Explicit rejection tests for script/HTML-injection attempts inside
  either identifier (`<script>`, `"><script>`, embedded spaces/angle
  brackets) — Section 9.
- Tenant isolation: one Store's badge identifiers can never render on
  another Store's domain or leak into another Store's page (tested).
- The platform badge can never render on a merchant storefront or the
  admin host, and a merchant badge can never render on the platform's own
  marketing site (tested) — both go through host-scoped context
  processors that return nothing outside their own domain.
- Fail-closed on corrupt/partial legacy values (tested).

## 9. Tests added

- `apps/stores/tests/test_enamad_verification.py`:
  `EnamadBadgeParserTests` (8) — valid pair, both-blank-not-an-error,
  id-only/code-only rejected, non-numeric id rejected, HTML-injection in
  id rejected, disallowed characters in code rejected, overlong code
  rejected. `MerchantEnamadBadgeRenderingTests` (9) — renders on verified
  custom domain, renders sitewide (not home-only), badge/meta independent
  in both directions, no badge on unverified domain, no badge on
  platform-owned subdomain, corrupt legacy value fails closed, no
  cross-tenant leakage.
- `apps/portal/tests/test_platform_enamad_verification.py::PlatformEnamadBadgeRenderingTests`
  (5) — renders when enabled+configured, renders sitewide, configured-but-disabled
  does not render, independent of meta state, never leaks onto a
  merchant/admin host.
- `apps/portal/tests/test_platform_configuration.py` (3 new) — save via the
  real Configuration view/form, partial identifiers rejected, badge and
  meta save independently.
- `apps/dashboard/tests/test_integration_views.py` — updated 3 pre-existing
  tests that posted the retired `enamad_code` field (would otherwise have
  broken, since the merchant integrations form is driven entirely by the
  provider's declared field list — Section 4.1); added
  `test_enamad_can_save_badge_identifiers_independently_of_meta`.

## 10. Exact commands run

```
python manage.py makemigrations portal
python manage.py test apps.stores.tests.test_enamad_verification \
  apps.portal.tests.test_platform_enamad_verification -v 2
python manage.py test apps.dashboard.tests.test_integration_views \
  apps.portal.tests.test_platform_configuration -v 1
python manage.py check
python manage.py makemigrations --check --dry-run
```

## 11. Exact test counts/results

- New/updated targeted tests (Gate A): 33/33 passed in
  `test_enamad_verification.py` + `test_platform_enamad_verification.py`
  combined (17 + 5 new, plus the pre-existing 11 from Phase 1, all green
  together).
- `apps.dashboard.tests.test_integration_views` +
  `apps.portal.tests.test_platform_configuration`: see the final audit
  report for the consolidated count (run in the background alongside this
  phase's work).
- `python manage.py check`: 0 issues. `makemigrations --check --dry-run`:
  clean.

## 12. Browser QA

Not performed in this pass (headless test environment only). The
Configuration page's eNamad card and the merchant integrations page both
reuse existing CSS classes with no new styling introduced.

## 13. Known limitations

- No real eNamad IDs were invented or used anywhere, per the master
  prompt's explicit instruction — all test identifiers are clearly
  synthetic (`998877`, `221617`/the public example code from eNamad's own
  documented format, etc.).
- The badge's `id`/`auth_code` regex bounds (12 digits, 64 alphanumeric
  characters) are generous estimates based on observed real eNamad values;
  if eNamad's real issued identifiers ever exceed these bounds, the regex
  in `enamad_verification_service.py` would need a one-line widening — no
  architectural change.

## 14. Commit SHA

Local commit (pending push — see the final audit report for the push-access
blocker status).

## 15. Remaining production-only prerequisites

Real eNamad verification meta tags and, later, real issued `id`/`Code`
badge identifiers for both `rastisi.ir` and each merchant Store's own
verified custom domain — entered via Platform Admin → Configuration and
Merchant Admin → Settings → Integrations → eNamad respectively, requiring
no source-code changes.
