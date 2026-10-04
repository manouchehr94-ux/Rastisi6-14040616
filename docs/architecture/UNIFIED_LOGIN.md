# Unified login contracts (merchant, customer and platform administration)

The **canonical merchant/owner password login** is the platform portal at
`/login/` (POST `/login/password/`). The identifier accepts **mobile number,
username or email**, always with the account's Django password. The existing
phone/OTP flow is an additional option, not an alternative authorization path.

## Deliberately separate security contexts

| Surface | Login location | Identity lookup | Authorization |
|---|---|---|---|
| Owner and merchant employees | `rastisi.localhost:8000/login/` in local development; production platform host | `owner_auth_service.authenticate_owner_by_identifier` (email / `OwnerProfile.phone` / legacy username) | Exact Store's **ACTIVE StoreMembership**, enforced by the signed admin handoff and dashboard decorators; no global `is_staff` shortcut |
| Storefront customers | Storefront's existing account/login modal (`/account/login/` POST) | `authenticate_customer_by_identifier` (Customer.email / Customer.phone / Customer.user.username) | A matching Customer record; no merchant or platform privileges |
| Platform administrators | Separate, host-isolated platform-admin login | Same owner identifier/password service, via `OwnerLoginForm` | **Both** global `is_staff` and `is_superuser`; no OTP shortcut |

For every password flow, invalid credentials and ambiguous case-insensitive
identifiers fail closed. Django's `authenticate()` enforces the existing
password hash and inactive-user checks. Existing throttling, remember-me,
CSRF, OTP, login-audit and signed short-lived admin-return mechanisms remain.
An account with an unusable password never authenticates through any of the
three password flows.
The platform-admin form still accepts the old `email` POST field as a
compatibility alias without rendering a second password form.

## Legacy merchant-login URL and local development

`/admin-portal/login/` is **not** another password handler. On a valid
merchant admin host it redirects to the platform's canonical login with a
signed `admin_return` value bound to that exact store and a validated admin
destination. Already-authenticated members enter their own dashboard, and an owner who is
already signed in at the central portal and arrives with a signed
`admin_return` continues to that store's handoff (ACTIVE membership is still
required to receive a ticket).

The plain `127.0.0.1` / `localhost` host is **ambiguous** on a multi-store
database. When `DEBUG=True`, visiting the legacy merchant-login URL there
redirects to the canonical platform login without guessing a store. Select
your store from **My Stores** and enter via its actual admin host:

`http://<store.admin_subdomain>.rastisi.localhost:8000/admin-portal/`

Unrecognized merchant hosts, inactive stores and public storefront domains
still return 404 at the merchant-admin entry point. There is no production
fallback from an unknown host to an arbitrary Store.

## Local verification on Windows

From `D:\\Projects\\Rastisi6_14040616` with an activated project virtualenv,
run the focused regression suites **against a disposable test database**:

```powershell
.\\.venv\\Scripts\\python.exe manage.py check
.\\.venv\\Scripts\\python.exe manage.py makemigrations --check --dry-run
.\\.venv\\Scripts\\python.exe manage.py test apps.portal.tests.test_three_identifier_login apps.portal.tests.test_unified_login apps.portal.tests.test_owner_auth apps.portal.tests.test_platform_admin apps.portal.tests.test_central_admin_login apps.dashboard.tests.test_admin_login apps.dashboard.tests.test_decorators apps.customers.tests.test_three_identifier_login apps.customers.tests.test_auth_service apps.customers.tests.test_auth_views apps.portal.tests.test_unified_login_hardening
```

Then verify both the canonical login and a real store's admin-host handoff in
the browser. If `*.rastisi.localhost` cannot be resolved by the local
browser/OS, configure loopback host resolution on the developer workstation;
**do not** remove tenant-host checks or change production `ALLOWED_HOSTS`.

These login changes do **not** require a database migration, password reset,
new login backend or changes to real SMS/email provider settings.

## Verification record (PR #21 completion)

Run on the branch after the review fixes, base `origin/main` @ `9325a4a1`:

- `manage.py check`: no issues. `makemigrations --check --dry-run`: no changes. No migration is added.
- Focused suites listed above plus `test_unified_login_hardening` and the
  cross-store modules `catalog.test_store_isolation`,
  `catalog.test_product_tax_class_isolation`, `catalog.test_tenant_routing_seo`,
  `billing.test_consistency_isolation`, `subscriptions.test_management_and_isolation`:
  219 tests, all OK.
- Broad regression `apps.portal apps.customers apps.dashboard apps.stores`
  (2,832 tests): 4 failures + 1 error. Three of those (the two
  `test_refresh_rasti_mode_demo_visuals_command` tests and
  `test_platform_host_routing.test_marketing_host_serves_portal_home`) fail
  identically on a clean export of `origin/main` and are not related to login.
  The other two (`stores` tests that asserted the retired local login page
  renders) were updated to assert the new redirect contract and pass.
- Browser (Chromium, scratch database with three stores, `*.rastisi.localhost`
  host resolution): 38/38 scripted checks, covering three-identifier login for
  owner, customer and platform admin, legacy-login redirect with a store-bound
  signed handoff, owner A refused into store B, ambiguous `localhost` /
  `127.0.0.1` in DEBUG, unknown and public-storefront hosts returning 404,
  unusable-password and customer-only accounts rejected, and staff-only /
  non-superuser platform-admin attempts rejected.
