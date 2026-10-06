# RastiChat integration (adapter) — `apps/chat_integration`

RastiChat is a **standalone, reusable, multi-tenant chat service**. RastiSi is its first *host application*: it talks to
RastiChat only through the generic **Integration Contract v1** (RastiChat repo: `docs/integrations/INTEGRATION_CONTRACT_V1.md`),
exactly like any other product would. This app only maps RastiSi concepts onto the contract's generic ones. It contains no
chat logic and RastiChat contains no RastiSi logic.

> **Default state after deploying this code: nothing changes.** `RASTICHAT_INTEGRATION_ENABLED` is **off**, no store has a
> connection, no template emits anything, every new URL is 404. Chat exists for a store only after a *platform superuser*
> enables it for that store.

## Mapping
| RastiSi | RastiChat (generic) | Source of truth |
|---|---|---|
| `Store` | tenant (workspace + widget project); `external_tenant_id = str(store.public_id)` | storefront Host → `request.store`; admin Host → `staff_required`; platform page → URL of a superuser-only view. **Never a browser value** |
| verified, un-retired `StoreDomain` hostnames | project allowed domains (`verified_domains`, exact hosts) | RastiSi's own verification (merchant-claimed domains never reach RastiChat) |
| `Store.name`, `Store.status` | tenant display name, `active`/`suspended` | `chat_sync_tenants` + lifecycle hooks |
| authenticated `Customer` | `customer` assertion, `sub = c<pk>`, name only (no phone/email) | the storefront session |
| `StoreMembership` ACTIVE: owner / administrator / order_manager | staff role `owner` / `admin` / `operator` (generic) | `apps.stores.authorization.get_active_membership` |
| platform superuser (`is_staff and is_superuser`) | platform staff `owner` | existing platform-owner semantics (no new support role invented) |

Other store roles (catalog manager, content editor, analyst) get no chat access. Platform support (talking to the RastiSi
team) is limited to owner/administrator. These role sets deliberately live in `services/identity_service.py`, **not** in
the (exhaustively tested) permission matrix of `apps.stores.authorization`.

## Configuration (environment)
| Variable | Meaning |
|---|---|
| `RASTICHAT_INTEGRATION_ENABLED` | global switch, **default False** |
| `RASTICHAT_BASE_URL` | e.g. `https://chatchat.rastisi.ir` |
| `RASTICHAT_WIDGET_URL` | the built widget script URL |
| `RASTICHAT_DASHBOARD_URL` | operator dashboard incl. its base path (e.g. `…/admin`) |
| `RASTICHAT_PLATFORM_DASHBOARD_URL` | platform dashboard incl. base path (e.g. `…/platform`) |
| `RASTICHAT_KEY_ID` | the `kid` RastiChat issued for RastiSi's **public** key |
| `RASTICHAT_PRIVATE_KEY` / `RASTICHAT_PRIVATE_KEY_FILE` | RastiSi's **Ed25519 private key** (PEM). A secret: environment or root-readable file only; never in the DB, repo or logs |
| `RASTICHAT_INTEGRATION_SLUG` (`rastisi`), `RASTICHAT_TOKEN_AUDIENCE` (`rastichat`), `RASTICHAT_WS_BASE`, `RASTICHAT_EXTRA_VERIFIED_DOMAINS` (dev/test only) | optional |

With the flag on and anything required missing the app **refuses to start** (`ImproperlyConfigured`) — a half-configured chat
must not be discovered by a customer. Generate the key pair on the RastiSi side
(`openssl genpkey -algorithm ed25519 -out rastisi.private.pem && openssl pkey -in rastisi.private.pem -pubout -out rastisi.public.pem`)
and give RastiChat's operator only the public key (`manage.py integration_key_add`). RastiChat never sees the private key.

## Enabling a pilot store (platform owner only)
1. RastiChat operator registers the `rastisi` integration with scopes `tenants:read,tenants:write,identity:customer,identity:staff,identity:platform,conversations:initiate`.
2. Deploy RastiSi with the environment above and `RASTICHAT_INTEGRATION_ENABLED=1`.
3. Platform admin → store page → tab **«گفتگوی آنلاین»** → **فعال‌سازی گفتگو برای این فروشگاه**. This provisions the tenant in
   RastiChat (idempotent; if RastiChat refuses or is down, nothing is enabled) and records the per-store switch in the existing
   `StoreIntegrationConnection` table (provider code `rastichat`, intentionally **not** in the merchant-facing integration registry,
   so merchants cannot toggle it).
4. The storefront now shows a small icon-only launcher (configuration seeded once: icon only, no questions, conversation starts on the first message, guests allowed; the store's chat admins can change launcher/pre-chat later in RastiChat's *Widget settings* and RastiSi never overwrites that).

**Rollback:** the same page → *غیرفعال‌سازی* (instant: widget and menu entries vanish; history stays in RastiChat), or set
`RASTICHAT_INTEGRATION_ENABLED=0` (all stores at once). No migration is involved.

## The three flows
1. **Customer ↔ store.** Storefront page renders `{% rastichat_widget %}` (only when enabled for this Host's store). The widget's
   `bootstrap()` calls this site's `GET /chat/identity/` (same-origin, session cookie) which returns a fresh 60-s single-use
   assertion for the logged-in customer (tenant from the Host, subject from the session) or 401 → guest. No second login.
2. **Store admin ↔ platform.** Seller portal (`/admin-portal/`) → customers → **«پشتیبانی پلتفرم»** (owner/administrator) or
   **«گفتگوی مشتریان»** (also order manager): the view (behind `staff_required`, i.e. the admin Host's store + an ACTIVE membership)
   syncs the member to RastiChat and redirects to the RastiChat dashboard `/sso#assertion=…` (URL **fragment**, `no-store`, `no-referrer`).
   A user managing several stores must use each store's own admin host; the tenant/role always come from that host's store+membership.
3. **Platform owner → store.** Platform admin → store → *ارسال پیام به مدیر فروشگاه*: RastiSi's **server** calls
   `POST /api/v1/integrations/tenants/{store}/support-conversations/` with the superuser as initiator and an `Idempotency-Key`
   minted when the form was rendered (double clicks / retries cannot duplicate). The store's owner/administrators see it in
   their support inbox (and get an in-app notification) even if they never wrote first. *صندوق گفتگوی پلتفرم* opens the platform inbox via SSO.

## Lifecycle hooks (best effort, after commit, no-ops unless the store has chat)
Store suspended/activated → tenant `suspended`/`active`; membership revoked or moved to a role without chat access → member removed
(live sockets close); platform suspends a user → chat identity disabled. A RastiChat outage never breaks a RastiSi action.
`manage.py chat_sync_tenants [--dry-run]` re-sends name/domains/status for every enabled store (renames, domain changes, missed hooks).
Customers: an account disabled in RastiSi can no longer obtain an assertion; an already-open chat session ends with its own short TTL.

## Security notes
* Browser input is never identity: store from Host, customer from session, staff from membership, platform from superuser.
* Tokens: Ed25519, `iss=rastisi`, 30 s (API, bound to method+path+body) / 60 s (assertion), single use; never logged.
* The assertion `origin` claim equals the storefront origin, so a leaked assertion is useless on another site.
* Chat is optional UI: if RastiChat is down the widget shows its unavailable state; nothing in RastiSi depends on it.

## Tests
`apps/chat_integration/tests/` (53 tests): default-off, client signing/binding/log hygiene, enablement + mapping, customer flow
(two stores, forged parameters, guest, inactive), merchant SSO (role mapping, multi-store host selection, revoked, 403s),
platform enable/message/inbox (permissions, idempotency key, failures), hooks, sync command. Cross-repo end-to-end proof lives in the RastiChat repo (`e2e/rastisi`).
