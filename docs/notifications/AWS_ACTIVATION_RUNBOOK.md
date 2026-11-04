# Amazon SES / SNS activation runbook — notifications email engine

**Nothing in this document has been executed against a real AWS account.** Every command below is copied from AWS's own CLI/API reference
(linked) and cross-checked against this repo's code; it has not been run live. Follow the 5-state label after each step honestly when you
execute it: **Implemented** (code exists) / **Verified with automated tests** (covered by this repo's fake/stub test suite) /
**Ready for live verification** (code + a documented live command, not yet run) / **Live verified** (you ran it against real AWS and saw the
expected result) / **Blocked by external access** (needs something only the platform owner/AWS/DNS holder can grant).

Run every AWS CLI command with `--region <RASTISI_SES_REGION>` explicitly — SES identities, quotas and sandbox status are **per region**.
Never paste a real access key into a chat, ticket, or this document; only ever put it in environment variables or a secret manager.

## 1. AWS account and region
* Decide the SES region (e.g. `eu-west-1`); set `RASTISI_SES_REGION` to it. One region is this engine's unit of configuration — a second
  region needs its own configuration set, SNS topic and identities. **Blocked by external access** — only the platform owner can choose/pay for the account.

## 2. Least-privilege IAM for the application
SES v2 operations use the **`ses:`** IAM action prefix even though they go through the `sesv2` API/CLI ([AWS SES API v2 guide](https://docs.aws.amazon.com/ses/latest/APIReference-V2/Welcome.html)).
The code (`apps/notifications/mail/ses.py`) only ever calls `create_email_identity`, `get_email_identity`, `send_email`, and `apps/notifications/mail/sns.py`
only *receives* SNS HTTP(S) pushes — it never calls an SNS API, so no `sns:*` IAM action is required for the app itself (only for whoever creates the topic/subscription, step 5).
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {"Effect": "Allow", "Action": ["ses:CreateEmailIdentity", "ses:GetEmailIdentity", "ses:SendEmail"], "Resource": "*"}
  ]
}
```
**UNVERIFIED — resource-level scoping.** `Resource: "*"` is the safe-but-broad starting point; SES v2 *does* support resource-level permissions
on identity and configuration-set ARNs, but the exact ARN shape and whether `SendEmail` can be scoped to "only through configuration set X" needs
a trial in a disposable AWS account (`aws iam simulate-principal-policy` or a real send) before being treated as a security boundary. Until that
trial happens, treat the broad policy above as the floor, not the target. — **Blocked by external access**.
Attach this policy to an instance profile / ECS task role (preferred: no static keys) or create one IAM user with only this policy and put the
two resulting values in `RASTISI_SES_ACCESS_KEY_ID` / `RASTISI_SES_SECRET_ACCESS_KEY` (env/secret-store only, never in git).
Status: **Ready for live verification.**

## 3. Domain identity + DKIM, per store
Code: `EmailSenderIdentity`/`sync_sender_identity` calls `create_email_identity`/`get_email_identity` and maps the 3 returned DKIM tokens to
the exact CNAME records shown in the store panel. This already happens automatically the first time a store gets a verified custom domain —
there is no separate manual step once SES is configured. Equivalent manual CLI for one domain (useful for the smoke test in step 9):
```
aws sesv2 create-email-identity --email-identity mybikestore.com --region eu-west-1
aws sesv2 get-email-identity --email-identity mybikestore.com --region eu-west-1   # DkimAttributes.Tokens, VerificationStatus
```
Status: **Verified with automated tests** (`apps/notifications/tests/test_ses_adapter.py`, `test_ses_botocore_model.py` — 20 tests against the
real botocore service model + `Stubber`, request/response shapes only, no network).

## 4. Sandbox vs. production access
By default every new SES account/region is in the **sandbox**: you may only send to *verified* recipient addresses, the quota is
**200 messages / 24 h**, the maximum send rate is **1 message/second**, and review of a production-access request can take **up to ~96 hours**
([AWS sandbox docs](https://docs.aws.amazon.com/console/ses/sandbox), [`put-account-details` CLI reference](https://docs.aws.amazon.com/cli/latest/reference/sesv2/put-account-details.html)).
```
aws sesv2 put-account-details --region eu-west-1 \
  --mail-type TRANSACTIONAL \
  --website-url "https://rastisi.ir" \
  --use-case-description "Multi-tenant e-commerce platform: order/account/shipping transactional email for merchant stores, each sending from its own verified domain." \
  --production-access-enabled
```
AWS still requires every `From`/`Source` identity to stay verified once in production — this does not relax step 3.
Status: **Blocked by external access** (AWS review + the platform owner's business justification).

## 5. Configuration set with an SNS event destination
```
aws sesv2 create-configuration-set --configuration-set-name rastisi-notifications --region eu-west-1
aws sns create-topic --name rastisi-ses-events --region eu-west-1          # note the TopicArn
aws sesv2 create-configuration-set-event-destination \
  --configuration-set-name rastisi-notifications \
  --event-destination-name rastisi-sns \
  --event-destination '{"Enabled": true, "MatchingEventTypes": ["SEND","DELIVERY","BOUNCE","COMPLAINT"], "SnsDestination": {"TopicArn": "arn:aws:sns:eu-west-1:<account>:rastisi-ses-events"}}' \
  --region eu-west-1
```
`MatchingEventTypes` values are fixed by AWS (`SEND | REJECT | BOUNCE | COMPLAINT | DELIVERY | OPEN | CLICK | RENDERING_FAILURE | DELIVERY_DELAY | SUBSCRIPTION`)
— [CLI reference](https://docs.aws.amazon.com/cli/latest/reference/sesv2/create-configuration-set-event-destination.html). This engine only needs
`BOUNCE`, `COMPLAINT`, `DELIVERY` (`apps/notifications/mail/events_service.py` only understands those three); add `SEND`/`OPEN`/`CLICK` only if you
want them for observability — unused event types are simply ignored by `events_service.ingest`.
Set `RASTISI_SES_CONFIGURATION_SET=rastisi-notifications` so every send attaches it (`SesTransport.send`, already wired — this was a bug this PR fixed).
Status: **Implemented** (configuration-set attachment) + **Ready for live verification** (the AWS-side objects above).

## 6. SNS → RastiSi HTTPS subscription
```
aws sns subscribe --topic-arn arn:aws:sns:eu-west-1:<account>:rastisi-ses-events \
  --protocol https --notification-endpoint https://<platform-host>/notifications/email/ses-events/ --region eu-west-1
```
Add the Topic ARN to `RASTISI_SES_SNS_TOPIC_ARNS` (comma-separated if more than one) — anything not in this allowlist is rejected even with a
valid SNS signature (`apps/notifications/mail/sns.py`). The subscription stays **Pending confirmation** until RastiSi's webhook (which
auto-confirms only for an allowlisted, correctly-signed topic) receives the `SubscriptionConfirmation` push; check with
`aws sns get-subscription-attributes --subscription-arn <arn>` until `PendingConfirmation` is gone.
Status: **Verified with automated tests** (signature v1/v2, tampering, wrong key, foreign/unlisted topic, cert-URL host/scheme/port tricks never
fetched, duplicate delivery idempotent — 48 tests in `test_email_security.py`) + **Ready for live verification** (the real subscribe/confirm round trip).

## 7. Secrets and environment
Set only through your deployment's secret manager / env, never in a file committed to git:
`RASTISI_SES_REGION`, `RASTISI_SES_ACCESS_KEY_ID`, `RASTISI_SES_SECRET_ACCESS_KEY` (omit both if using an instance/task role — preferred),
`RASTISI_SES_CONFIGURATION_SET`, `RASTISI_SES_SNS_TOPIC_ARNS`, and switch `RASTISI_EMAIL_PROVIDER=ses`. The automated secret-scan test
(`apps/notifications/tests/test_qa_tooling.py::SecretScanTests`) fails the build if an AWS access key or private key pattern is ever committed
under `apps/notifications`, `docs/notifications`, `tools/windows-qa` or `deploy`. Status: **Verified with automated tests**.

## 8. Workers and scheduled identity revalidation
`process_notification_outbox` (every 5 minutes) and `refresh_email_identities` (hourly, **added to the crontab in this PR**) must run under the
real deployment's scheduler (`deploy/cron/rastisi.crontab` — **not installed by this repository**; an ops action). Without the hourly job a
sender that becomes unverified later (e.g. the merchant's DNS host drops the CNAME) is only noticed on the merchant's next manual retry.
Status: **Implemented** + **Verified with automated tests** (command unit tests) + **Blocked by external access** (ops installs the crontab).

## 9. Delivery / bounce / complaint smoke tests (first real send)
Prerequisite: steps 2–6 live-verified, one real domain with the 3 DKIM CNAMEs actually published.
1. `python manage.py refresh_email_identities --store <id>` → the store's sender status must become `ACTIVE` **from SES's own verdict**, not from a flag you set.
2. Platform admin → template → test-send to a mailbox **you own**; open the raw headers and confirm `dkim=pass` with the aligned `d=` domain.
3. Send to AWS's documented **mailbox simulator** addresses to exercise the full loop without touching a real inbox or your sending reputation
   ([AWS blog](https://aws.amazon.com/blogs/messaging-and-targeting/how-to-test-email-sending/), [console docs](https://docs.aws.amazon.com/ses/latest/dg/send-an-email-from-console.html)):
   `success@simulator.amazonses.com` (always delivers), `bounce@simulator.amazonses.com` (hard bounce), `complaint@simulator.amazonses.com` (complaint),
   `ooto@simulator.amazonses.com` (out-of-office auto-reply), `suppressionlist@simulator.amazonses.com` (hard bounce as if the address were on SES's global suppression list). Per the AWS docs (verified by fetching the page) these
   do not count against your **daily** quota and do not affect bounce/complaint or deliverability metrics, but they ARE subject to your max sending rate and ARE billed like normal mail. `bounce+label@simulator.amazonses.com` labels are supported. The repo's own wrapper for this is
   `tools/windows-qa/Invoke-RastiSiLiveSesSmoke.ps1` (default `-Scenario success`, read-only unless `-ConfirmLiveSend`) / `manage.py ses_smoke_test`.
4. Confirm the bounce/complaint from step 3 arrives over the real SNS subscription and produces an `EmailSuppression` row and a `delivery_state`
   change on the right `NotificationOutbox` row (same code path as `qa_simulate_email_event`, now fed by a real event instead of a simulated one).
5. Briefly disable the SNS subscription and confirm sending still works and the feedback loop recovers once re-enabled (no silent data loss).
Until 1–4 pass for real, **do not describe e-mail as production-ready** — see `docs/notifications/ACTIVATION_CHECKLIST.md` §E (unchanged policy).
Status: **Ready for live verification** (script + command exist; not yet run against real AWS, per the constraint of this task).

## 10. Monitoring, rate limits, recovery
`check_background_jobs` already alerts on held mail, expired rows, sender errors and overdue revalidation (step 8); wire its non-zero exit into
your ops alerting. `RASTISI_EMAIL_STORE_HOURLY_LIMIT` / `RASTISI_EMAIL_PLATFORM_MINUTE_LIMIT` must be set at or below the account's real
SES sending rate (step 4) — otherwise SES, not RastiSi, becomes the throttle and sends start failing with `Throttling`/`MaxSendingRateExceeded`.
Recovery path for a provider outage or credential rotation: sends fail closed (`SendOutcome(ok=False, retryable=True)`), the outbox retries on
its own schedule, nothing is lost or double-sent (idempotent event ingestion, step 6's tests). Status: **Implemented** + **Verified with
automated tests**; the real rate-limit alignment is **Blocked by external access** (needs the account's actual approved quota from step 4).

## Status matrix (fill in the right column as each step is actually executed)
| # | Step | Status now |
|---|---|---|
| 1 | Account + region | Blocked by external access |
| 2 | Least-privilege IAM | Ready for live verification (resource scoping UNVERIFIED) |
| 3 | Domain identity + DKIM | Verified with automated tests |
| 4 | Sandbox → production access | Blocked by external access |
| 5 | Configuration set + SNS destination | Implemented / Ready for live verification |
| 6 | SNS HTTPS subscription + confirm | Verified with automated tests / Ready for live verification |
| 7 | Secrets/env, no credentials committed | Verified with automated tests |
| 8 | Workers + scheduled revalidation | Implemented / Verified with automated tests / Blocked by external access (crontab install) |
| 9 | Delivery/bounce/complaint smoke test | Ready for live verification |
| 10 | Monitoring/rate limits/recovery | Implemented / Verified with automated tests / Blocked by external access (real quota) |
