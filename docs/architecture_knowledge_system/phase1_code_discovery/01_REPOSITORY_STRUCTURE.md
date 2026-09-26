# 01 — Repository Structure

Evidence class legend: **VERIFIED** = read directly; **INFERRED** = deduced from strong
code evidence; **UNKNOWN** = not established.

---

## 1. Top-level layout (VERIFIED)

```
/ (repo root)
├── manage.py                      Django entry point
├── requirements.txt               Django>=5.2, jdatetime, Pillow, requests, cryptography,
│                                   psycopg[binary], beautifulsoup4, PySocks, dnspython
├── shop_core/                     Django project package (settings, 3 URLconfs, wsgi/asgi)
├── apps/                          16 Django applications (the domain code)
├── templates/                     project-level templates (403/404/500, base, storefront_shell,
│                                   partials, seo/sitemap.xml)
├── static/                        project-level static root
├── scripts/                       ad-hoc verification scripts (verify_six_families*, product entry UI)
├── tools/                         Node-based QA harnesses (storefront_builder_qa, _r4_qa)
├── docs/                          documentation corpus (EXCLUDED as a Phase-1 discovery source)
├── .env.example                   full environment variable catalogue
├── CLAUDE.md, SIX_NEW_FAMILIES_*  agent/impl notes (not used as architecture evidence)
└── .claude/, .mcp.json            agent tooling config
```

## 2. `shop_core/` project package (VERIFIED)

| File | Role |
|---|---|
| `settings.py` | All configuration; environment-driven via `env_config.py`. Defines `INSTALLED_APPS`, `MIDDLEWARE`, `TEMPLATES` (incl. 18 context processors), platform host sets, billing/SMS/domain settings. |
| `env_config.py` | Parsing/validation of env vars (`build_database_config`, `resolve_allowed_hosts`, `resolve_secret_key`, …), kept separate so it is unit-testable. |
| `urls.py` | **ROOT_URLCONF** — per-Store storefront + merchant dashboard host. Includes catalog, cart, customers, orders, dashboard (`admin-portal/`), content, billing webhook, sms gateway, Django admin, SEO. |
| `urls_platform.py` | URLconf for platform marketing + owner portal hosts (`RASTISI_PLATFORM_HOSTS`). Includes `apps.portal.urls`. |
| `urls_platform_admin.py` | URLconf for platform-admin hosts (`RASTISI_PLATFORM_ADMIN_HOSTS`). Includes `apps.portal.platform_admin_urls`. |
| `wsgi.py` / `asgi.py` | Servers. |
| `tests/` | Project-level tests (settings/env). |

**Host-based URLconf selection (VERIFIED):** `apps.portal.middleware.PlatformHostRoutingMiddleware`
sets `request.urlconf` to `urls_platform_admin` or `urls_platform` when the Host is in the
respective setting; otherwise Django falls back to `ROOT_URLCONF` (`shop_core.urls`). This is
the one mechanism that partitions the three surfaces.

## 3. The 16 apps (VERIFIED) — size and shape

LOC is production Python (excludes `migrations/` and `tests/`). See doc 02 for domain grouping.

| App | Code LOC | Test LOC | models.py LOC | Has services/ | Has urls.py | Notable extra modules |
|---|---:|---:|---:|:--:|:--:|---|
| `core` | 2,711 | 918 | 519 | ✓ | ✗ | storage.py, seo.py, color_utils, theme_presets, phone, converters |
| `catalog` | 12,746 | 10,007 | 2,121 | ✓ | ✓ | industry_templates/, seed_data/, templatetags/, commands/ |
| `customers` | 926 | 1,141 | 265 | ✓ | ✓ | forms.py, context_processors.py |
| `cart` | 1,116 | 2,251 | 106 | ✓ | ✓ | context_processors.py |
| `orders` | 5,206 | 5,726 | 1,169 | ✓ | ✓ | gateways/, encryption.py, forms.py |
| `dashboard` | 12,746 | 17,491 | 3 | ✓ | ✓ | decorators.py, middleware.py, forms.py, templatetags/ |
| `blog` | 63 | 20 | 23 | ✗ | ✗ | views.py is a stub |
| `sms` | 1,375 | 1,369 | 287 | ✓ | ✓ | events.py, gateway_views.py |
| `content` | 1,900 | 6,021 | 1,104 | services.py (single file) | ✓ | media_reachability.py, templatetags/ |
| `storefront_builder` | 29,611 | 60,977 | 976 | ✓ | ✗ (routes via dashboard) | many *_registry.py / *_catalog.py / schema modules; r4_views.py; media_views.py; storefront_appearance/ |
| `stores` | 8,325 | 7,456 | 764 | ✓ | ✗ | middleware.py, resolution.py, hostnames.py, authorization.py, admin_permissions.py, integrations/ |
| `subscriptions` | 2,371 | 1,672 | 403 | ✓ | ✗ | entitlements.py |
| `billing` | 3,081 | 2,348 | 544 | ✓ | ✓ | providers/ |
| `portal` | 5,407 | 7,499 | 469 | ✓ | ✓ | middleware.py, decorators.py, platform_admin_urls.py, platform_admin_views.py, phone.py |
| `notifications` | 210 | 130 | 57 | ✓ | ✗ | — |

Observations:
- **`dashboard` has essentially no models** (`models.py` = 3 lines) yet the largest views layer
  after storefront_builder. It is a controller/orchestration app over other domains (doc 06, doc 12).
- **`storefront_builder` is by far the largest app** (~29.6k code + ~61k test LOC) and has no
  `urls.py`; its routes are registered inside `apps/dashboard/urls.py`.
- **`content` has no service package**, only a single `services.py` that is read/resolve-only
  (no write service) — see doc 03/12.
- **`blog` is a single model with a stub `views.py` and no `urls.py`** (POTENTIALLY_DEAD storefront
  wiring — doc 13).

## 4. Configuration surface (VERIFIED, from `settings.py` + `.env.example`)

Key runtime switches discovered in code:
- `PAYMENTS_SIMULATION_ENABLED` (defaults to `DEBUG`) — gates the simulated order-payment flow.
- `PAYMENT_CREDENTIAL_KEY` — Fernet-style key for `apps/orders/encryption.py` credential encryption.
- `RASTISI_PLATFORM_HOSTS`, `RASTISI_PLATFORM_ADMIN_HOSTS`, `RASTISI_PLATFORM_PRIMARY_HOST`,
  `RASTISI_ADMIN_DOMAIN_SUFFIX`, `RASTISI_CANONICAL_DOMAIN_SUFFIX` — host partitioning + tenant host building.
- `RASTISI_DEFAULT_PLAN_CODE`, `RASTISI_DEFAULT_PLAN_START_TRIAL` — default subscription provisioning.
- `RASTISI_BILLING_PROVIDER` (default `manual`), `RASTISI_BILLING_WEBHOOK_SECRET`,
  `RASTISI_BILLING_RENEWAL_LEAD_DAYS`, `RASTISI_BILLING_DUNNING_SCHEDULE`, `RASTISI_BILLING_TAX_RATE`.
- `RASTISI_OWNER_SMS_*` — platform-level (Store-independent) OTP SMS backend config.
- `PRIVATE_MEDIA_ROOT` — private storage for export/import files, deliberately outside `MEDIA_ROOT`.

These are **feature flags / configuration registries**; duplication concerns are in doc 13.
