# portal — Entry Points

```
domain_id: D2
code_baseline: 5883a140
```

portal serves **two Host-partitioned surfaces** (chosen by `PlatformHostRoutingMiddleware`).

## Owner portal (`apps/portal/urls.py`, on `RASTISI_PLATFORM_HOSTS`, via `shop_core.urls_platform`)
Marketing (home/features/plans/contact/terms/privacy/robots/sitemap); owner auth
(register/login/login-password/verify-OTP/logout/register-email/login-email/reset-password); owner
app (app-home, store-create, onboarding[-identity/-industry/-branding/-review], store-created,
enter-admin); billing (plans/checkout/step-up/return); handle claim (+step-up); custom domains
(begin-verify/check/final-check/activate/+step-up); store deletion (+step-up/cancel); ownership
transfer (+step-up/cancel/accept-by-token); notifications.

## Platform admin (`apps/portal/platform_admin_urls.py` + `platform_admin_views.py`, on `RASTISI_PLATFORM_ADMIN_HOSTS`, via `shop_core.urls_platform_admin`)
Gated by `@user_passes_test(_is_platform_staff)` = authenticated AND `is_staff` AND `is_superuser`.
Groups: login, home KPIs, configuration, SMS (providers/templates/messages/credits/logs), stores
(search/detail/suspend/activate/support-login/extend-trial/change-plan/add-note), users, plans,
subscriptions, payments (incl. zibal), industries, domains (check/set-primary), audit-log.

## Middleware
`PlatformHostRoutingMiddleware` — sets `request.urlconf` to platform-admin / platform / (else
ROOT). Routing only; never touches `request.store`.

## Decorators (`apps/portal/decorators.py`)
`owner_required` (→ portal:login), `portal_action_allowed`/`portal_actions_allowed` (delegate to
`stores.authorization.user_has_permission`), `portal_permission_denied`.

## Signals / async
None.
