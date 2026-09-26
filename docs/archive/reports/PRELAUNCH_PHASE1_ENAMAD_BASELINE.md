# Pre-Launch Phase 1 — eNamad Technical-Verification Baseline

## 1. Objective

Close and prove the safe eNamad technical-domain-verification capability
(meta-tag method) for both the RastiSi platform (`rastisi.ir`) and every
merchant Store on its own verified custom domain, per the master prompt's
Phase 1 requirements.

## 2. Architecture before this phase

Commit `a07fe73` ("prelaunch: add safe enamad technical verification"),
already an ancestor of `main`, had already implemented the full feature:

- **Parser/validator**: `apps/stores/services/enamad_verification_service.py`
  — `parse_enamad_verification_meta_tag()` uses Python's `html.parser.HTMLParser`
  to accept exactly one `<meta name="..." content="...">` element and nothing
  else. It rejects: any tag other than `meta`, more than one element, end
  tags, non-whitespace text, comments, doctypes/processing instructions,
  `http-equiv`, `style`, `src`, event handlers, any attribute other than
  `name`/`content`, duplicate attributes, empty/overlong `content`
  (`> 1024` chars), and control characters. `name` must match
  `^[A-Za-z0-9_.:-]{1,128}$`. No `mark_safe()` is used anywhere — values are
  rendered through Django's normal auto-escaping.
- **Platform storage/rendering**: `PlatformConfiguration.enamad_verification_meta_tag`
  (`apps/portal/models.py`), edited via the Platform Admin configuration
  form (`PlatformConfigurationForm`, POST `/configuration/`, superuser-only).
  Rendered by `apps/portal/context_processors.py::platform_enamad_verification`,
  gated to `request.path == "/"` **and** `request.get_host()` in
  `settings.RASTISI_PLATFORM_HOSTS`, re-parsing/re-validating the stored
  value before exposing it to the template
  (`apps/portal/templates/portal/base_platform.html`).
- **Merchant storage/rendering**: stored as a `StoreIntegrationConnection`
  row (`provider_code="enamad"`), encrypted at rest via the shared Fernet
  utility (`apps/orders/encryption.py`), edited from Merchant Admin →
  Settings → Integrations → eNamad. Rendered by
  `apps/core/context_processors.py::shop_settings` calling
  `store_enamad_verification_meta_for_request()`, gated to the request path
  being `/` **and** an exact-match `StoreDomain` row for that Store with
  `domain_type=CUSTOM_DOMAIN`, `verification_status=VERIFIED`,
  `retired_at__isnull=True` (`apps/stores/services/enamad_verification_service.py`).
- Both rendering paths fail closed: a corrupt/legacy stored value that no
  longer parses returns `None` instead of raising into the template.

## 3. Gaps found

The implementation was already correct and complete against nearly every
item in the master prompt's Phase 1 checklist. Verifying against the
checklist line by line, two scenarios existed in production code but had
**no direct test coverage**:

1. An unverified custom domain must never render the merchant's meta tag
   (only `domain_type=CUSTOM_DOMAIN` + `verification_status=VERIFIED` may
   render it — a `pending`/`unverified`/`failed` domain must not).
2. One Store's meta tag must never leak onto a different Store's own
   verified custom-domain home page (cross-tenant isolation at the
   storefront-rendering layer, as opposed to the settings-page layer, which
   was already tested in `apps/dashboard/tests/test_integration_views.py`).

No production code defect was found; both gaps were purely test-coverage
gaps, and both scenarios already pass because the existing code correctly
scopes on `store_id` and `verification_status`.

## 4. Decisions

- Do not rewrite or refactor the existing implementation — it already
  matches the spec's security requirements (single safe meta tag, strict
  allowlist, reject script/`http-equiv`/event handlers/`style`/`src`,
  fail-closed on corrupt legacy values, no raw-HTML injection).
- Add the two missing test cases directly to the existing test file rather
  than create a parallel test module, to keep Phase 1 coverage in one place.

## 5. Files changed

- `apps/stores/tests/test_enamad_verification.py` — added
  `test_unverified_custom_domain_never_gets_verification_meta` and
  `test_other_stores_verified_domain_never_gets_this_stores_meta`.
- `.gitignore` — unrelated housekeeping (excludes local Claude Code agent
  worktree scaffolding from being tracked); not a Phase 1 change but
  committed alongside it.

## 6. Migrations

None. `portal.0007_platformconfiguration_enamad_verification_meta_tag`
(the baseline migration referenced by the master prompt) already exists on
`main` and required no changes.

## 7. Models/services/views/templates/routes added or changed

None — Phase 1 required no production-code changes. All infrastructure
listed in Section 2 already existed and was reused as-is.

## 8. Security decisions

- Confirmed no `mark_safe()` call exists anywhere in the eNamad code path;
  Django's default auto-escaping is relied on for both `name` and `content`.
- Confirmed the parser rejects every malicious-input class required by the
  master prompt: `<script>`, multiple tags, `http-equiv`, event-handler
  attributes, `style`, `src`, arbitrary attributes, malformed markup, and
  tag-closing/HTML-injection attempts (all covered by
  `EnamadMetaParserTests` in `apps/stores/tests/test_enamad_verification.py`).
- Confirmed corrupt/legacy stored values fail closed (return `None`, no
  exception surfaces to the template) on both the platform and merchant
  paths.

## 9. Tests added

- `apps/stores/tests/test_enamad_verification.py::MerchantEnamadMetaRenderingTests::test_unverified_custom_domain_never_gets_verification_meta`
- `apps/stores/tests/test_enamad_verification.py::MerchantEnamadMetaRenderingTests::test_other_stores_verified_domain_never_gets_this_stores_meta`

Full Phase 1 checklist coverage (file references):

| Requirement | Test |
|---|---|
| Valid platform tag save/render | `apps/portal/tests/test_platform_configuration.py::PlatformConfigurationViewTests::test_superuser_can_save_safe_enamad_verification_meta`, `apps/portal/tests/test_platform_enamad_verification.py::PlatformEnamadVerificationRenderingTests::test_platform_home_renders_safe_enamad_meta` |
| Platform tag only on platform home | `test_non_home_platform_page_does_not_render_verification_meta` |
| Invalid platform tag rejected | `test_platform_configuration_rejects_unsafe_enamad_html`, `UpdatePlatformConfigurationTests::test_invalid_enamad_meta_is_rejected_by_service` |
| Clear platform tag | covered by `update_platform_configuration` allowing an empty string; exercised indirectly via `PlatformConfigurationSingletonTests` |
| Valid merchant tag save | `apps/dashboard/tests/test_integration_views.py::test_enamad_can_connect_with_verification_meta_before_badge_is_issued` |
| Merchant tag renders on correct verified custom domain home | `test_context_exposes_parsed_meta_on_own_verified_custom_domain` |
| Does not render on platform subdomain | `test_platform_owned_store_subdomain_never_gets_merchant_enamad_meta` |
| Does not render on unverified custom domain | **new**: `test_unverified_custom_domain_never_gets_verification_meta` |
| Does not leak cross-tenant | `test_store_b_staff_sees_own_disconnected_state_not_akhlaghis` (settings page) + **new**: `test_other_stores_verified_domain_never_gets_this_stores_meta` (storefront rendering) |
| Invalid/malicious tag rejected | `EnamadMetaParserTests` (4 cases) + `test_enamad_rejects_script_instead_of_storing_raw_html` |
| Legacy corrupt stored value does not render | `test_corrupt_legacy_value_fails_closed_instead_of_rendering_html` |
| Authorization / CSRF / ownership | `test_ordinary_owner_cannot_reach_configuration_page`, `test_anonymous_denied` (Django's CSRF middleware is on by default for both POST endpoints; no `@csrf_exempt` present) |

## 10. Exact commands run

```
git status --short
git log -10 --oneline
python manage.py check
python manage.py makemigrations --check --dry-run
git merge-base --is-ancestor 50988e0 origin/main   # baseline check, YES
python manage.py test apps.stores.tests.test_enamad_verification \
  apps.portal.tests.test_platform_enamad_verification \
  apps.portal.tests.test_platform_configuration \
  apps.dashboard.tests.test_integration_views -v 2
python manage.py test apps.portal apps.stores apps.dashboard -v 1
```

## 11. Exact test counts/results

- Targeted eNamad suite (Gate A): 12 tests in
  `apps.stores.tests.test_enamad_verification` +
  `apps.portal.tests.test_platform_enamad_verification` — **12/12 passed**.
- Related-integration suite: the above two files plus
  `apps.portal.tests.test_platform_configuration` and
  `apps.dashboard.tests.test_integration_views` — **42/42 passed**.
- Gate B (full `apps.portal` + `apps.stores` + `apps.dashboard` suites):
  **2368/2368 passed** (3706s wall time), confirming no regression anywhere
  in the three most-related apps.

## 12. Browser QA

Not performed in this pass — Phase 1 required no UI changes (the existing
Platform Admin configuration screen and merchant Integrations settings
screen were unchanged). Browser QA for the eNamad settings screens is
covered under Phase 5, which does add new UI for the badge lifecycle.

## 13. Known limitations

- The post-issuance `enamad_code` field (the final badge/script fragment
  merchants would eventually paste in) is still a free-text field with only
  a length cap (`<= 4000` chars) and no structural allowlist/validation.
  This is intentionally left for Phase 5, which redesigns it into a
  structured, safely-rendered badge lifecycle rather than patching the
  legacy free-text field in place.
- `PlatformConfiguration.enamad_verification_meta_tag` has no database-level
  `CheckConstraint`; safety is enforced entirely at the service/form layer
  (`update_platform_configuration` calling
  `parse_enamad_verification_meta_tag`) plus fail-closed rendering. This
  matches the pattern used elsewhere in the codebase (e.g. `PlanVersion`
  immutability) and was judged acceptable rather than a gap to fix.

## 14. Commit SHA

Local commits (pending push — see Section 15):
- `256be51` — `chore: gitignore local Claude Code agent worktree scaffolding`
- `21e9dbb` — `prelaunch: close enamad verification baseline`

## 15. Remaining production-only prerequisites

- None specific to Phase 1's technical-verification capability. Real eNamad
  identity/badge values remain out of scope until Phase 5's final-badge
  lifecycle is issued by eNamad to the real platform and merchant domains.
- **Push blocker**: at the time of this report, this session's GitHub App
  installation does not have write access to
  `manouchehr94-ux/rastisi5` — both `git push` (plain 403 from GitHub, no
  credential challenge attempted) and the GitHub MCP `push_files` tool
  (`403 Resource not accessible by integration`) are denied. Work is
  proceeding with local commits; an org admin needs to grant this
  session/app write access before any commits reach the remote branch.
