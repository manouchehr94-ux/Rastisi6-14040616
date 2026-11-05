# Unified Messaging settings & UX redesign

Branch `kiro/messaging-settings-ux-20261104`, based on the combined integration branch
`kiro/notifications-integrated-20261104` @ `fe3ded78`. **Backend unchanged — this is a management-interface
consolidation.** No schema change, no new migration, no change to the dispatcher, SES adapter, SMS backends, queues,
outbox workers, suppression, retries, audit logs, or any financial logic.

## Round 2 corrections (product-owner review)
1. **Canonical Settings → پیام‌رسانی section** — a real route `settings/messaging/` (`settings_messaging` view +
   `messaging_home.html`): a management center with a live KPI summary and five subsection cards, not just a shared nav
   bar. Navigation has one canonical `messaging` tab (url `settings-messaging`) with the five subsections as Level-3
   children. The Marketing entry is now a **command-palette shortcut** into this canonical section, not a competing
   sidebar tab — so there is exactly one administration structure. Nav invariants are satisfied architecturally (distinct
   canonical landing route; no two tabs share a destination; each tab resolves to itself).
2. **Redesigned event editor** (`notification_template_form.html`) — full content width (max 1500px), genuinely
   side-by-side SMS and Email at ≥1100px (verified at 1280 and 1440), stacked below; compact cards, toggle switches,
   per-channel effective-status badges, SMS character + segment counter, click-to-insert variable chips, subject/plain/
   HTML for email, previews, and one atomic sticky save bar. No narrow form with wasted whitespace.
3. **Real-font visual evidence** at 1440 / 1280 / 768 / 390 in `ui-evidence/messaging-redesign/fx_*` (Vazirmatn embedded,
   Persian renders correctly).

## What changed and why
The product owner rejected the split messaging management: event templates and channels lived under **Marketing →
«اعلان‌ها و پیام‌ها»**, while the SMS provider, credits, Android gateway and logs lived under **Settings → «پیامک»**, with
no shared navigation and a duplicate SMS-template edit surface. This redesign makes one coherent **«پیام‌رسانی»** experience.

### One central section, five subsections
A single shared sub-navigation bar (`dashboard/partials/notification_tabs.html`) now appears on every messaging page, with
the spec's exact Persian labels:

1. **رویدادها و قالب‌ها** — `notification-templates` (event list with SMS+Email status; one row per event → unified editor)
2. **کانال‌های ارسال** — `notification-channels` (independent SMS/Email enable per event)
3. **فرستنده‌ی ایمیل و دامنه** — `notification-sender` (sender identity, DKIM, verification)
4. **سرویس پیامک و اعتبار** — `settings?section=sms` (method, device, credits, test-send, logs)
5. **تاریخچه و صف ارسال** — `notification-history` (+ links to the SMS phone-gateway queue/logs)

### One event = one editor (unchanged, already correct)
The per-event editor (`notification_template_form.html`) already shows both channels together in two balanced cards
(SMS: enable, body, preview; Email: enable, subject, plain body, HTML, preview), with one save, revision history, and
gated test-send. The redesign keeps it and ties it into the unified navigation; the event list links each event to it.

### No competing system / no conflicting switches
The SMS settings page previously embedded a **second** SMS-template edit surface (its own channel switches), which could
conflict with the unified editor. It now **links to** the unified editor for per-event SMS text and only keeps the
provider/credits/device controls (the SMS-template list is behind a read-only «نمایش فهرست» disclosure). There is exactly
one editable destination per channel-per-event.

## Navigation
`apps/dashboard/navigation.py`:
- Marketing tab relabelled «پیام‌رسانی (اعلان‌ها و پیام‌ها)» — the entry merchants expect next to campaigns; owns the
  `notification-*` routes.
- Settings tab relabelled «سرویس پیامک و اعتبار» — the SMS-provider subsection; owns `?section=sms` and `sms-*` routes.
- Both carry the identical five-subsection sub-bar, so the user gets one experience regardless of entry point. The
  one-destination-per-tab and round-trip navigation invariants are preserved (see `test_admin_navigation.py`).

## Separation of configuration from delivery readiness (preserved)
The pages continue to distinguish, with actionable Persian text: channel enabled/disabled vs template configured vs sender
verified/unverified vs SMS provider available vs message queued/sent/delivered/failed/suppressed. An enabled email template
with an unverified sender still shows the "sender not active, mail is held" banner and never implies delivery. Email and SMS
failure isolation is unchanged.

## Protected events, RBAC, tenant isolation (preserved)
Security/OTP templates stay always-on and platform-locked; store admins cannot bypass them. Everything remains gated by
`can_manage_settings` (SMS-template editing additionally needs the SMS-settings permission), and every query is scoped to
`request.store`. Platform defaults and store overrides are unchanged.

## Tests
- New `apps/dashboard/tests/test_messaging_ux.py` (12): unified sub-bar on every page incl. the SMS settings page; exact
  labels; links resolve to the real views; one-destination-per-tab; unified editor shows both channels + all controls;
  saving one channel does not reset the other; event list shows both statuses; RBAC + tenant isolation.
- Updated `test_admin_navigation.py` and `test_admin_v22_shell.py` for the new IA labels.
- Regression: `apps.dashboard` 2143 OK, `apps.notifications` 465 OK, `apps.sms`/`apps.portal` pass (one pre-existing
  parallel-isolation flake in `test_public_site_v2`, unrelated — passes when run alone; no portal file changed here).

## Files changed
- `apps/dashboard/navigation.py` — tab labels + keywords (no new tabs, no duplicate destinations)
- `apps/dashboard/views.py` — `SETTINGS_SECTIONS` SMS label/description
- `apps/dashboard/templates/dashboard/partials/notification_tabs.html` — unified five-subsection bar
- `apps/dashboard/templates/dashboard/partials/settings_sms.html` — sub-bar + heading; de-duplicated the SMS-template editor
- `apps/dashboard/templates/dashboard/notification_templates.html` / `notification_channels.html` / `notification_sender.html` / `notification_history.html` — spec labels; history links the SMS queue/logs
- `apps/dashboard/tests/test_messaging_ux.py` (new), `test_admin_navigation.py`, `test_admin_v22_shell.py`
- `docs/notifications/MESSAGING_UX_REDESIGN.md`, `docs/notifications/ui-evidence/messaging-redesign/`

## Limitations
- No live email/SMS/payment is sent anywhere; QA uses the fake providers.
- Persian text in the committed standalone screenshots renders as boxes (web font not embedded in the snapshot); the live
  server renders correctly.
- The per-event editor layout was already two balanced cards; this change did not restructure it beyond wiring navigation.
