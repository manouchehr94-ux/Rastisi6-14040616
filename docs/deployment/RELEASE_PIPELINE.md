# Release tooling v2 — independent safety remediation

This is a review candidate, not an installed production system. No server or
GitHub settings have been changed by this work. Baseline: PR #46, commit
`cd7b66837bf63bd2a0f5e4d53c80cb3964e6480f`.

## Release contract

The supported automatic path is a code-only change or a statically recognised,
transactional additive migration. Unknown operations, aliases to custom code,
non-atomic migrations, removal of integrity constraints, edited/deleted migration
files and all REVIEW/DESTRUCTIVE reports are refused for online activation.
`allow_migrations` and a destructive phrase do not bypass this restriction, even
if someone has already applied the migration manually. Such releases need a
separate maintenance plan; this tool does not implement that plan.

The release workflow validates exact commits, builds the artifact, tests THAT
artifact's hashed wheelhouse, then waits for the production environment approval
before SSH staging and activation. Ordinary CI resolves one shared wheelhouse
once. Gunicorn is included in tests/audit. Each test job installs offline with
`--require-hashes --no-deps` and runs `pip check`. No production credentials are
available to test/build jobs. Artifacts remain tied to their SHA256.

Releases are separate immutable code directories. The database, Redis, secrets,
public/private uploads and Nginx configuration live outside them. Stage checks
the actual configured Python major/minor, Linux x86_64 and glibc >= 2.28. pip's
offline installation additionally checks ABI/manylinux tags and wheel hashes.
A mismatch in installed tooling version blocks the workflow.

## Database safety and rollback

Activation and rollback take the same exclusive nonblocking flock. Release-aware
cron jobs take a shared lock and pin both app directory and venv to the same
resolved release. The backup configuration must use the same deployment lock.
No deployment may overlap a job or a backup holding that shared lock.

Before migration, verify the production configuration, DB/Redis and existing
local Nginx/TLS/static route, migration plan, report and recent verified backup.
Automatic migration uses PostgreSQL lock_timeout=5 seconds and
statement_timeout=10 minutes (root-owned configuration can choose bounded values).
It is still possible for a large additive operation to require a maintenance
window; this tool does not promise online index construction.

Every migration failure is UNKNOWN until investigated: `INCIDENT` and
`in_progress.json` are retained. An unapplied recorder row DOES NOT prove SQL was
rolled back. Non-atomic operations and surviving child processes can have made
changes. No automatic continuation or rollback follows such a failure.

Rollback is code-only. It never runs reverse migrations or restores a database.
Automatic rollback is permitted only for NONE/ADDITIVE reports and is verified
again. Manual rollback rejects any in-progress marker, even with an unsafe
acknowledgement. It also rejects disagreement between the current symlink and
the active record. Older/unknown targets require explicit acknowledgement after
state reconciliation; acknowledgement alone is not evidence of compatibility.

After interruption: inspect the current link, running process working directory,
Django migration recorder, actual schema and data; stop any surviving migration
processes. Decide fix-forward versus recovery in maintenance. Reconcile release
state before `resolve --note ...`. `resolve` is an administrator decision, not an
automatic repair or proof that the database is safe. Preserve incident evidence.

## One-time staging setup (administrator review required)

Use a dedicated non-root application account and a dedicated deployment account;
neither may be shared with RastiService.ir. Use a dedicated base directory,
PostgreSQL role/database, Redis namespace, static/media roots and ONE service.
Inspect existing unit/drop-ins and all cron/timers before changing paths.
The installer refuses system roots and an unregistered nonempty application
directory. It never recursively changes existing ownership; operations inside a
deploy-owned layout execute as deploy, not root.
These examples are instructions for a later approved staging session, not commands
that have been executed on production.

1. Confirm OS, `/usr/bin/python3`, selected app interpreter, architecture/glibc,
   PostgreSQL/client versions, free disk, `curl`, venv, sudo and OpenSSH.
2. Run `deploy/release/install.sh --dry-run` with the intended service, app user,
   base, env file and port, then install the reviewed tooling. Never use root as
   app user. The installer does not install/start application services.
3. Install the restricted public key per `examples/authorized_keys.example` AND
   the account-wide `examples/sshd_config.snippet`. Validate `sshd -t` before reload.
   `/bin/sh` is needed for OpenSSH to execute the forced command; interactive
   access is denied by the key/account restriction, not by a nologin shell.
   Test `version` succeeds while shell commands, interactive access, forwarding
   and unrelated sudo commands fail. Do not change other accounts' SSH policy.
4. Set smoke_host to the real platform hostname and edge_port to the local TLS
   Nginx listener. The edge probe pins this hostname to 127.0.0.1 with curl
   `--resolve`, preserving SNI/certificate validation. It checks public pages and
   an actual static asset. It never disables TLS verification. Keep
   `edge_probe_enabled=true` on staging/production; false is only for test doubles.
5. Install and verify the backup configuration; run a backup and restore drill.
   Its nonsecret state records are 0644 so deploy can read them. Env files and
   backup passwords stay private to the application account; do not add deploy
   to the application's secret-bearing groups.
6. Register the current deployment with `cutover` (dry run, then `--apply`). Generate
   the unit drop-in with the installed `make_dropin.py`; review the full effective
   unit before applying it. Preserve the original unit AND existing drop-ins.
   A blanket `systemctl revert` can remove unrelated drop-ins; undo only the
   specific release-layout drop-in that was added.
7. Configure ALL background jobs to use installed
   `/usr/local/lib/rastisi/run_current_job.sh` with
   `RASTISI_RELEASE_BASE=<base>` and the unchanged approved `RASTISI_ENV_FILE`.
   Remove stale fixed app/venv paths from cron/timers. The wrapper pins these
   automatically under the shared lock. Handle exit 75 as deferred work, not
   success. Wait for existing old-code jobs to finish. Only then set
   `jobs_follow_current=true` in root-owned deploy.conf. Activation refuses the
   default false setting. This is an operator attestation, not automatic cron
   inventory discovery.
8. Test a no-migration staging release, injected failure, rollback and preserved
   data. Then test an additive migration with a fresh backup. Include webhooks,
   a sandbox payment callback, jobs and all tenant domains in manual acceptance.

## Required GitHub configuration (not applied by this change)

The `production` environment must restrict deployments to the trusted workflow
branch, require owner review, prevent self-review and disable administrator bypass
where available. Put the deploy secret in that environment only. Pin known_hosts
from a trusted channel. Protect release branches and require CODEOWNERS approval
for workflows, deployment/backup tooling and CI policy. Require every CI job,
including the tenant tier and release rehearsal. Protect allowed release branches;
a configurable branch-name regex is not branch protection. Do not assume merely
naming an environment in YAML creates reviewer protection.

## Quality policy and remaining release blockers

Known-failure IDs alone are insufficient: the full normalised diagnostic SHA256
must equal the explicitly reviewed signature set. A new exception, earlier
assertion failure, extra subtest diagnostic or missing signature blocks CI. Flaky
retries also require the exact reviewed diagnostic; ID-only retry entries block.
Only checkout/venv path prefixes and whitespace are normalised. Changes to output
can conservatively require re-review; do not broaden normalisation to hide them.
Expiry/stale-entry checks remain. The refund-failure notification tripwire is a
release blocker, not an accepted financial exception. No financial code changed.

Dependency exceptions also require recorded security-review evidence. Advisory
IDs, versions and expiry still must match. The original unreviewed Pillow
exceptions do not pass. See `DEPENDENCY_SECURITY_REVIEW.md`; absence of a verified
upgrade or a narrowly supported assessment is a blocker, not a reason to renew
all exceptions. Unreproduced known-failure diagnostics also remain blocked.

CI now includes blog and the complete storefront-builder test package. The upgrade
probe selects every mapped managed model and validates write statements on the
new schema, plus an old-code INSERT in a rolled-back transaction. These are schema
contracts, not proof of every business workflow's backward compatibility.

## Availability and testing limits

One Gunicorn instance is restarted: brief request failures remain possible.
Blue/green instances and Nginx upstream switching are a future availability
change, not silently claimed here. Shared hardware, disk/CPU/I/O contention,
PostgreSQL roles and operational privileges still need staging inventory. There
is no direct operation targeting RastiService.ir in the tooling; that is not a
guarantee of resource isolation on an uninspected shared server.

Run tooling tests with `python -m unittest discover -s deploy/release/tests` and CI
policy tests with `python -m unittest discover -s tools/ci`. For real installation,
SSH, PostgreSQL/restic and non-atomic failure, pass the tested dependency directory
to `bash deploy/release/selftest/run_isolated.sh <deps-dir>`. It creates a disposable
container, mounts this repo read-only and installs dependencies offline. Restic's
local repository in this test proves encrypted storage/restore, not off-site
provider durability, credentials or object-lock configuration. No production
host/secret is used.
