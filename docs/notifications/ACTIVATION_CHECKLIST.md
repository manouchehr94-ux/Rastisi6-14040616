# Production activation checklist — email engine

**Nothing below has been verified against a real AWS account, DNS server, SNS topic or mailbox.** "Tested" means automated tests
with the evidence type named; "Live" means proven in the real world (all rows: **No**).

Legend — Code: IMPLEMENTED / PARTIAL / MISSING. Tests: the strongest evidence that exists. Live: Yes / No.

## A. Amazon SES
| # | Prerequisite | Code | Tests (evidence type) | Live | Missing / who |
|---|---|---|---|---|---|
| A1 | AWS account, SES region chosen (`RASTISI_SES_REGION`) | n/a | — | No | **Platform owner.** Identities, quotas and sandbox status are *per region*. |
| A2 | `boto3` on the deployment | IMPLEMENTED (in `requirements.txt`, lazy import) | adapter run against the real botocore `sesv2` client with `Stubber` (8 tests; skipped automatically when boto3 is absent) | No | Platform owner: install, then `python -c "import boto3"`. |
| A3 | Credentials: instance/task role **or** `RASTISI_SES_ACCESS_KEY_ID/SECRET` (env only) | IMPLEMENTED | credentials never logged/stored (unit) | No | Platform owner. No key exists in the repo. |
| A4 | IAM permissions | n/a | — | No | Platform owner. SES v2 uses IAM service prefix `ses` (AWS docs). Needed operations: `CreateEmailIdentity`, `GetEmailIdentity`, `SendEmail`. **Exact least-privilege resource scoping is UNVERIFIED** — AWS notes that restricting `Resource` needs additional statements (identity + configuration set); validate in a test account. |
| A5 | Domain identity + Easy DKIM (3 CNAMEs) per store | IMPLEMENTED (`CreateEmailIdentity`/`GetEmailIdentity`, token→CNAME mapping) | request/response shapes validated by the botocore service model; status mapping unit-tested | No | Real verification needs the merchant's DNS (see C). |
| A6 | **Production access** (leave the sandbox) | MISSING (account setting) | — | No | **Platform owner.** AWS: sandbox allows only verified recipients, **200 messages/24 h, 1 message/second**; review takes up to ~96 h; you must have a bounce/complaint process (this PR provides one). Until granted, sends to normal customers fail permanently (`DEAD`). |
| A7 | Configuration set + event destination → SNS (Bounce, Complaint, Delivery) | PARTIAL: `RASTISI_SES_CONFIGURATION_SET` is now attached to every send (bug fixed in this pass — it was unused) | `ConfigurationSetName` request shape validated (botocore model) | No | **Platform owner** creates the set and event destination; without it no bounce/complaint ever reaches RastiSi and suppression never happens. |
| A8 | Send-rate / quota alignment | PARTIAL (`RASTISI_EMAIL_STORE_HOURLY_LIMIT`, `_PLATFORM_MINUTE_LIMIT`, DB-counted) | unit | No | Platform owner: set limits ≤ the account's real max send rate / daily quota. |

## B. SNS webhook
| # | Prerequisite | Code | Tests | Live | Missing / who |
|---|---|---|---|---|---|
| B1 | Public HTTPS platform host (member of `RASTISI_PLATFORM_HOSTS`) serving `/notifications/email/ses-events/` | IMPLEMENTED (routing **fixed** in this pass: it was only on the tenant URLconf) | host-routing test: served on the platform host, **not** on the Platform Admin or tenant hosts | No | Platform owner: DNS/TLS for the host. |
| B2 | SNS topic; ARN in `RASTISI_SES_SNS_TOPIC_ARNS` (otherwise **everything is rejected**) | IMPLEMENTED (fail-closed allowlist) | 48 security tests: signature v1/v2, tampering, wrong key, foreign topic, bad cert URLs (scheme/host/port tricks) never fetched, fetch failure fails closed, duplicate delivery idempotent, tenant attribution only from our own outbox | No | Platform owner. |
| B3 | HTTPS subscription + confirmation | IMPLEMENTED (auto-confirm only for a signed, allowlisted topic) | stubbed confirm | No | Platform owner: create subscription, watch it become *Confirmed*. |
| B4 | Outbound HTTPS from the app to `sns.<region>.amazonaws.com` (certificate fetch) | IMPLEMENTED (`requests`, 5 s timeout, fails closed) | stubbed fetcher; signatures verified with locally generated RSA keys | No | Network egress rules. |

## C. DNS
| # | Prerequisite | Code | Tests | Live | Missing / who |
|---|---|---|---|---|---|
| C1 | Merchant adds 3 DKIM CNAMEs (manual path) | IMPLEMENTED (exact records, relative names, Persian steps, per-record "seen" probe, recheck cron) | rendering + state machine; **DNS lookups were not performed against real zones** | No | Merchant. This is the path that works **today**. |
| C2 | Automatic record creation | IMPLEMENTED but **disabled by default** (RFC 2136+TSIG, or a custom provisioner) | in-memory authoritative server: safety rules, conflicts, partial failure, secrets | No | **Platform owner decision.** RastiSi has no DNS-write authority over any merchant zone (audit). Needs: a zone RastiSi controls/was delegated, a TSIG key, `RASTISI_EMAIL_DNS_*` env. Otherwise stay manual. |
| C3 | Mail-From / SPF alignment, merchant DMARC | MISSING (not customised) | — | No | Optional hardening; DMARC currently passes by DKIM alignment only. |

## D. Workers and scheduling
| # | Prerequisite | Code | Tests | Live | Missing / who |
|---|---|---|---|---|---|
| D1 | `process_notification_outbox` every 5 min | EXISTING (crontab) | command tests | No | Ops: install crontab (`deploy/cron/rastisi.crontab`, "not installed by the repository; not verified on any real server"). |
| D2 | `refresh_email_identities` hourly | **ADDED** to crontab + `validate_jobs.sh` step 9 | unit (due/changed counting) | No | Ops: install and run `validate_jobs.sh`. Without it a once-verified domain that later breaks is never noticed. |
| D3 | Health monitoring | EXTENDED (`check_background_jobs`): held mail, expired rows, sender errors, overdue revalidation; held mail no longer raises a false "cron dead" | 4 tests | No | Ops: alert on non-zero exit. |

## E. First real-delivery smoke test (not yet done)
1. Staging SES account (out of sandbox, or with verified recipients). 2. One real test domain with the 3 CNAMEs published.
3. `refresh_email_identities --store <id>` → status must become `ACTIVE` **from the provider**, not from us.
4. Platform admin → template → controlled test send to a mailbox you own; inspect headers (`dkim=pass`, aligned `d=` domain).
5. Send to AWS's documented mailbox-simulator addresses to exercise bounce and complaint → confirm rows get `delivery_state` and a suppression.
6. Stop the SNS subscription briefly and confirm mail still sends and the feedback loop recovers.
Until step 3–5 pass, **do not describe email as production-ready.**
