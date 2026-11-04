# Notifications migration collision — analysis and integration proposal

## Facts (reproduced, not assumed)
| branch | notifications migrations added | parent |
|---|---|---|
| `main` (`7d311556`) | … `0003_sms_log_mirror` | |
| `integration/payment-engine-unified-20261104` (rehearsed at `1b0d3ef0`, **re-rehearsed at `4a30c54b`**; Claude Code) | `0004_inbox_engine` | `0003` |
| this PR (#37) | `0005_email_sender_identity_platform_templates`, `0006_expiry_status_and_dns_automation` | `0003` |

Both lineages descend from `0003` → **two leaf nodes**. Reproduced in a disposable worktree:
`CommandError: Conflicting migrations detected; multiple leaf nodes in the migration graph: (0004_inbox_engine, 0006_expiry_status_and_dns_automation in notifications)`
— `migrate`, `makemigrations --check` and the test runner all refuse to run until resolved.

Textual conflicts when merging the PR into the integration branch (`git merge-tree`, then a real merge in the scratch tree): **three files**,
all mechanical — `apps/dashboard/urls.py` (one `from . import …` line), `apps/stores/services/domain_verification_service.py`
(keep Claude's `admin_events.domain_verification(...)` call *and* the sender-provisioning hook) and `deploy/cron/rastisi.crontab`
(both sides add independent jobs in the same block: keep both). The third appeared when the integration branch moved during this work;
`rehearse.sh` aborts on any conflict it does not know, which is how it was noticed. Everything else auto-merges
(`models.py` — my models live in `models_email.py`, `settings.py`, `urls_platform.py`, platform `base.html`, `portal/views.py`).
The schemas are disjoint: the two lineages add different tables/columns (`NotificationEvent`, `InboxItem`, … vs `EmailSenderIdentity`,
`PlatformNotificationTemplate`, … plus four columns and a status choice on `NotificationOutbox`, which the Inbox lineage does not touch).

## Two collision-free strategies (both rehearsed with existing data)
**Option B — recommended: linear graph.** Land the payment-engine branch first, then re-point this PR's `0005` onto it:
```
-        ("notifications", "0003_sms_log_mirror"),
+        ("notifications", "0004_inbox_engine"),
```
(`optionB_retarget_0005.patch`). No merge migration, history stays linear, nobody has applied `0005`/`0006` anywhere yet so no renumbering risk.
**Option A — merge migration:** if this PR lands first/independently, whoever lands second runs
`python manage.py makemigrations --merge --noinput notifications` (an empty migration depending on `0004_inbox_engine` and
`0006_expiry_status_and_dns_automation`; template in `optionA_merge_migration.py.txt`).
Do **not** apply either branch's migrations to a shared database before choosing; if one was already applied, Option A is the only safe choice.

## Evidence
`docs/notifications/migration-integration/rehearse.sh` (repeatable by anyone with both refs; uses a throw-away worktree, never pushes,
never touches a real database) and `verify_graph.py`:
1. migrate to `0003`, **seed** 7 outbox rows (email/sms/in-app; sent/pending/dead/failed/skipped) + 3 store templates through *historical* models;
2. migrate to head; assert every row and column value is unchanged, new columns have safe defaults, **both** lineages' tables exist, `makemigrations --check` is clean;
3. migrate **back** to `0003` and forward again; rows survive the round trip.
Results: Option A ✔, Option B ✔ (both on the merged tree); then `manage.py test apps.notifications apps.dashboard.tests.test_notification_admin apps.portal.tests.test_platform_notification_admin apps.sms` on the **integrated** tree:
**667 tests, 0 failures** at integration tip `4a30c54b` (Claude's Inbox suites and this PR's suites together), for both strategies.

## Integration defects the rehearsal found and this PR fixed
1. Claude's repo-wide guard `test_templates_do_not_inline_user_content_into_scripts` forbids `|safe` in any notifications template; my email layout used it.
   Fixed: the template uses plain autoescape; the single "mark safe" happens in Python after **re-sanitizing** (allowlist), so even a tampered DB row cannot inject markup.
2. My parity scanner did not know the new trigger `customers/services/account_security_service.py` (→ `account.sensitive_changed`) nor the Inbox
   `registry.py` documentation string. Fixed (optional extra trigger sites; registry allowlisted).

## What this PR deliberately did NOT do
It does not merge, rebase or modify any financial branch/file (path audit: no billing/gateway/refund/checkout/subscription files in the diff), does not
push to `integration/*`, `feature/kiro-payment-engine-*`, `handoff/*`, and applies no migration to any shared database.

## Requested from Claude Code
1. Choose A or B (B preferred) and say whether `0004_inbox_engine` is already applied anywhere shared.
2. Run `bash docs/notifications/migration-integration/rehearse.sh <pr-ref> <integration-ref> B` on the final integration tip.
3. Confirm Inbox does not intend to add columns to `NotificationOutbox` (I add `html_body`, `sender_address`, `delivery_state`, `held_since`, status `expired`).
4. **Second e-mail path.** The Inbox engine's e-mail channel (`channel_delivery.EmailChannel`, `RASTISI_NOTIF_EMAIL_ENABLED`, off by default) sends with Django SMTP and
   `DEFAULT_FROM_EMAIL` to the platform's own admin users. That is platform→staff mail (same class as this PR's `platform.*` notices), so it does **not** break the
   own-domain rule for store→customer mail — but it bypasses this PR's suppression list, rate limits, expiry rules, provider abstraction and bounce ingestion.
   Decide whether to move it onto `apps.notifications.mail.registry.get_transport()` (platform sender) before enabling the flag in production.
5. Confirm financial events remain consumed only through `business_events` (`payment.*`, `refund.completed`, `staff.late_payment`); I read `Order.status/payment_status` and `Coupon` fields in `expiry.py` and never write them.
