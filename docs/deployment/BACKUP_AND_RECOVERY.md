# Backup and recovery — tooling v2

Review candidate only. Nothing here has been installed on production. All real
integration tests use synthetic data and a disposable local PostgreSQL/restic
repository; off-site reachability and retention protection need staging validation.

## Installation and permissions

`install.sh` installs the root-owned backup script in `/usr/local/lib/rastisi-backup`
and shared code in `/usr/local/lib/rastisi`. Both source and installed layouts are
tested. Run backup as the dedicated non-root app account, never as the deployer.

Create app-private 0600 restic password/provider credential files outside Git and
keep independently protected recovery copies. Configure `backup.conf.example`;
set deploy_lock_file to the SAME state/deploy.lock used by release and cron. The
job holds a shared deployment lock, preventing code/schema transitions during the
backup. A competing backup/deploy returns 75 and must be rescheduled. State_dir is
0755, app-owned. Its JSON state is 0644, contains no credentials and is readable by
deploy. Do not grant deploy access to app-secret groups.

Use `drill_admin_env_file`, a separate 0600 app-owned file with PGHOST, PGPORT,
PGUSER and PGPASSWORD. A legacy drill_admin_url is supported but makes backup.conf
secret-bearing. The drill role needs CREATEDB, NOSUPERUSER and NOCREATEROLE; it is
separate from the application role. It creates and drops only validated scratch
names, never the live name. Confirm pg_dump/client compatibility with the actual
server major version before installing timers.

## Backup guarantees and limits

`run` makes a consistent PostgreSQL custom-format dump, verifies size/catalogue,
hashes it, snapshots DB/config/media to encrypted restic, reads the stored dump
back and checks its hash/catalogue, then runs a restic integrity subset. Only then
is last_backup.json marked verified and retention allowed. `verify` always reads
100% of repository data, regardless of the normal-run subset. Failed verification
invalidates readiness and writes BACKUP_FAILED.

Timeouts and missing executables enter failure reporting. Failed alert delivery
leaves ALERT_DELIVERY_FAILED and stderr output. Monitor both operation exit status
and marker/state age independently; a configured mail command is not proof that
someone received an alert. A verification or newer-backup failure blocks migrating
deployments until investigated and a successful backup clears the condition.

`restore-drill` performs a real restore into a scratch DB, compares table presence
and critical non-empty counts, samples media and drops the scratch DB. It is not
a row-by-row checksum of all business data and does not measure full server rebuild
time. Test the drill with the actual least-privilege role and off-site provider.

DB/media snapshots are not atomic together. Concurrently replaced/deleted uploads
can require reconciliation. Private generated export/import files are excluded by
the current policy. Nightly dumps allow up to 24 hours of loss; choose a smaller
schedule when justified. WAL/PITR, append-only/offline backup credentials and full
server recovery orchestration are NOT implemented. Use a dedicated repository;
retention operates on that repository. Protect recovery passwords separately.

## Recovery after data loss (administrator maintenance procedure)

Never restore over an active database. Restore to a scratch database first and
verify business records, payment reconciliation needs, credentials/config and
media. Preserve any surviving newer data before deciding to replace it.

1. Stop web writers AND all cron/timer/worker writers and wait for in-flight work.
   Keep the site in explicit maintenance. Do not announce recovery yet.
2. Restore the selected dump into an empty replacement database, using
   pg_restore --no-owner --no-privileges --exit-on-error and the intended app role.
   Restore media into a scratch tree and compare before copying missing files.
   Match the code/config/schema to the selected snapshot; preserve secret keys
   needed to decrypt gateway credentials. On compromise, rotate secrets through
   a separate reviewed recovery plan.
3. If the required code is newer than the dump, inspect its migration plan on the
   RESTORED SCRATCH copy first, verify data preservation and decide whether an
   upgrade is appropriate. Do not start a newer web/job process on the old schema.
   An administrator may run the reviewed target's migrate with the trusted app
   environment while writers remain stopped, then verify schema/data. This is a
   maintenance action, not the normal release workflow.
4. Activating the already-current release is verification-only: it does NOT
   apply pending migrations. Do not use reactivation as a recovery schema-upgrade
   command. Reconcile current/active metadata, migration state and any incident
   only after verifying what actually runs and what schema was restored.
5. Verify ORM/application behavior, local Nginx/TLS/static routes, login, tenant
   boundaries and a sandbox payment flow. Reconcile orders/payments since backup
   against authoritative provider records before enabling customer traffic.
6. Resume jobs using the release-aware wrapper and then reopen. Tell affected
   users the verified recovery point and any unrecoverable interval.

A scratch restore drill alone is not an RTO guarantee. Rehearse the entire recovery
on staging and record measured RPO/RTO. Never run these procedures against
RastiService.ir or another application's database, directories or service.
