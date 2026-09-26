# 05 — Entry-Point Inventory

All discovered runtime entry points, grouped by mechanism. Evidence class legend as in doc 01.

---

## 1. Host-based URLconf routing (VERIFIED)

`apps.portal.middleware.PlatformHostRoutingMiddleware` selects `request.urlconf`:

| Host in… | → URLconf | Surface |
|---|---|---|
| `RASTISI_PLATFORM_ADMIN_HOSTS` | `shop_core.urls_platform_admin` | Platform admin |
| `RASTISI_PLATFORM_HOSTS` | `shop_core.urls_platform` | Marketing + owner portal |
| (else) | `shop_core.urls` (ROOT_URLCONF) | Per-Store storefront + merchant dashboard |

## 2. HTTP routes — ROOT_URLCONF `shop_core/urls.py` (VERIFIED)

| Path | Include / view | Domain |
|---|---|---|
| `favicon.ico`, `sitemap.xml`, `robots.txt` | `apps.core.views.favicon_view`, `apps.core.seo.sitemap_xml/robots_txt` | core (tenant-safe SEO) |
| `admin/` | Django admin (restricted to platform superusers by `stores.admin_permissions`) | — |
| `""` | `apps.catalog.urls` → storefront home (`catalog.views.home` uses render_service) | catalog/storefront |
| `cart/` | `apps.cart.urls` | cart |
| `account/` | `apps.customers.urls` | customers |
| `checkout/` | `apps.orders.urls` | orders |
| `admin-portal/` | `apps.dashboard.urls` (merchant dashboard; `staff_required`) | dashboard |
| `admin-panel/…` | `admin_panel_compat_redirect` | legacy redirect |
| `pages/` | `apps.content.urls` (page_detail, newsletter_subscribe) | content |
| `billing/` | `apps.billing.urls` → `webhook/<provider_code>/` (csrf-exempt) | billing webhook |
| `sms/` | `apps.sms.urls` → SmsRasti device poll/ack | sms gateway |

## 3. HTTP routes — Owner Portal `apps/portal/urls.py` (VERIFIED)

Marketing (home/features/plans/contact/terms/privacy/robots/sitemap); owner auth
(register/login/login-password/verify-OTP/logout/register-email/login-email/reset-password);
owner app (app-home, store-create, onboarding[-identity/-industry/-branding/-review],
store-created, enter-admin); billing (plans/checkout/step-up/return); handle claim (+step-up);
custom domains (begin-verify/check/final-check/activate/+step-up); store deletion
(+step-up/cancel); ownership transfer (+step-up/cancel/accept-by-token); notifications.

## 4. HTTP routes — Platform Admin `apps/portal/platform_admin_urls.py` + `platform_admin_views.py` (VERIFIED)

Gated by `@user_passes_test(_is_platform_staff)` = authenticated AND `is_staff` AND `is_superuser`.
Groups: login, home KPIs, configuration, SMS (providers/templates/messages/credits/logs),
stores (search/detail/suspend/activate/support-login/extend-trial/change-plan/add-note), users,
plans, subscriptions, payments (incl. zibal), industries, domains (check/set-primary), audit-log.

## 5. HTTP routes — Merchant Dashboard `apps/dashboard/urls.py` (VERIFIED, `app_name="dashboard"`)

Auth/shell (login, handoff/<token>, exit-support-mode, home, sales-chart); catalog
(products*, attributes*, brands*, collections*, categories*+schema); commerce (orders*, invoices*,
payments*, customers*+tags+segments, reports*); settings (shop-info, industry*, finance, gift-wrap,
appearance, gateways/gateway-config, shipping, sms*, integrations); content (pages*, homepage/hero*,
homepage/banners*, social-links*, menus*+menu-items*, footer*); **storefront-builder delegation**
(~60 routes wired directly to `apps.storefront_builder.views`, `r4_views`, `media_views`); ops
(staff*, inventory*, coupons*, audit-log*, exports*, imports*, refunds/returns, warehouses*,
reservations*, transfers*, shipping/tax setup, subscription*, billing*).

## 6. Storefront Builder routes (VERIFIED — registered under dashboard, no own urls.py)

- **Legacy R3** (`views.py`): `storefront-builder/`, `/preview/`, `/sections/…`, `/containers/…`,
  `/cells/…`, `/blocks/…`, `/appearance/`, `/header/`, `/footer/`, `/apply-preset/`, `/publish/`,
  `/undo|redo/`, `/history/`+`/restore/`, `/templates/`+`/preview/`, `/apply-industry-layout/`.
  Mutations fail-closed via `_require_legacy_editor_active` when `r4_editor_enabled=True`.
- **R4** (`r4_views.py`): `storefront-builder/r4/…` (editor shell, `/mutate/`, `/design-lab/`,
  `/sections/<pk>/inspector/`, `/resources/picker/`, `/history/`, `/publish/`, `/discard/`,
  `/reset-page/`, `/reset-storefront/`, `/switch-template/`, `/restore/<pk>/`, `/apply-industry-layout/`).
  **Default** target of dashboard nav.
- **Media** (`media_views.py`): `/sections/<pk>/media/<kind>/…`.

## 7. Public storefront rendering entry points (VERIFIED)
- `catalog.views.home` → `render_service.build_render_items` (visual layout) with legacy fallback.
- `catalog.views` product-list / product-detail / collection-index/detail.
- `content.views.page_detail` (uses `build_universal_storefront_context`), `newsletter_subscribe`.

## 8. Webhooks & device callbacks (VERIFIED)
- **Billing webhook:** `billing/webhook/<provider_code>/` → `billing.views.billing_webhook`
  (csrf-exempt, POST, always 200; `webhook_service.ingest_webhook` → `payment_flow_service.process_webhook_event`).
- **Order gateway callback:** `checkout/gateway/callback/<attempt_id>` → server-to-server verify
  (`gateway_payment_service.process_callback_and_verify`).
- **Order payment (simulation):** `checkout/payment-callback/<status>` — status is a client-controlled
  path segment; Http404 unless `PAYMENTS_SIMULATION_ENABLED`.
- **SmsRasti device gateway:** `sms/…` poll (`smsrasti_poll`, GET, `?token`) + ack (`smsrasti_ack`, POST),
  csrf-exempt, device-token-authenticated.

## 9. Management commands (VERIFIED — 34)
billing: `generate_subscription_renewals`, `process_subscription_dunning`, `verify_billing_consistency`.
subscriptions: `evaluate_subscription_states`, `provision_legacy_subscriptions`, `seed_default_plans`,
`verify_subscription_consistency`.
catalog: `cleanup_stale_product_drafts`, `expire_inventory_reservations`, `import_damatajhiz_catalog`,
`migrate_legacy_product_tag_collections`, `provision_default_warehouses`, `reset_store_catalog`,
`seed_industry_templates`, `validate_industry_templates`, `verify_inventory_consistency`.
core: `cleanup_expired_exports`, `seed_shop`.
dashboard: `cleanup_import_files`, `refresh_customer_segments`.
notifications: `process_notification_outbox` (the only notification sender).
orders: `seed_default_shipping_methods`.
storefront_builder: `capture_ready_template_previews`, `qa_storefront_builder`, `qa_storefront_builder_r4`.
stores: `apply_golden_reference_storefront`, `kianstock_qa_data`, `purge_deleted_stores`,
`refresh_rasti_mode_demo_visuals`, `rename_store_handle`, `seed_kianstock_qa_demo`,
`seed_rastisi_fashion_demo`, `seed_ready_template_fashion_demo`, `verify_domain_consistency`.

## 10. Admin actions (VERIFIED)
- `billing.admin`: `action_mark_paid` (→ `confirmation_service.mark_invoice_paid_manually`),
  `action_retry` (webhook reprocess).
- `sms.admin`: `mark_completed` (package purchase).
- Most other admins set `actions = None` and financial/status fields read-only; Django `/admin/`
  is superuser-only.

## 11. Signals (VERIFIED)
- **None.** No `@receiver`/`post_save`/`pre_save`/`.connect(` in production code (only unrelated
  `sqlite3.connect` in QA commands and a service method named `.connect`). The codebase
  deliberately avoids signals (explicit notes in `content/services.py` MED-001 and CustomerProfile
  ADR-50). Side effects are triggered explicitly via services + `transaction.on_commit`.

## 12. `transaction.on_commit` side-effect hooks (VERIFIED)
- `orders/services/order_service.py` (ORDER_PLACED + status SMS), `payment_service.py`
  (PAYMENT_SUCCESS/FAILED SMS), `gateway_payment_service.py` (PAYMENT_SUCCESS SMS).
- `customers/services/auth_service.py` (WELCOME SMS).
- `dashboard/views.py` (post-commit deletion of replaced logo/favicon/image files).
- `content/services.py` (MED-001 retention no-op callback, deliberately retained but inert).

## 13. Client-side JavaScript entry points (INFERRED)
Static JS exists under `storefront_builder/static` and `catalog/static`; not read line-by-line.
The R4 editor is inferred to POST to `storefront-builder/r4/mutate/` (matching
`r4_mutation_service`'s single-boundary design), but the exact client→server endpoint set is
UNKNOWN from JS source (doc 14).
