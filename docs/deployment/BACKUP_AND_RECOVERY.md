# RastiSi backup and recovery

Status: implemented (`deploy/backup/rastisi_backup.py`) and tested against a real PostgreSQL 16 and a real restic repository (9 end-to-end tests, plus one run inside the full
release rehearsal). **Not installed on any server. The off-site repository, its credentials and the timers are owner actions.**

A deployment never needs a restore: routine releases and rollbacks change code only (`RELEASE_PIPELINE.md`). Backups exist for the cases a release cannot fix:
a destroyed database, a destroyed disk or server, a deleted shop, a corrupted table.

## 1. What is protected

| Data | How | Frequency (default) | Notes |
|---|---|---|---|
| PostgreSQL database of RastiSi | `pg_dump --format=custom` (a consistent snapshot, no downtime), catalogue read back, size and table-count sanity checks | nightly 03:30 (+ before any release that migrates) | the only copy of orders, shops, subscriptions, users; **the most important thing on the server** |
| Media (`DJANGO_MEDIA_ROOT`, product images, logos) | restic snapshot (deduplicated, so a daily run stores only what changed) | nightly | taken minutes apart from the dump, not atomically; harmless for images |
| Configuration: `/etc/rastisi/*.env`, `deploy.conf`, `backup.conf`, and the release records `active.json` + `history.jsonl` | included in the **encrypted** repository only | nightly | contains secrets: never stored unencrypted off the machine |
| Code | not backed up: every release is in GitHub and the last 5 are on the server | | rebuild by running the release workflow for the commit in `state/active.json` |
| Redis | not backed up | | rate-limit counters and CAPTCHA questions only; losing them is harmless |
| Private media (`DJANGO_PRIVATE_MEDIA_ROOT`) | **not included** | | generated export/import files that are deliberately not backed up (see `PRODUCTION_CONFIGURATION.md` section 5a); add it to `media_root` handling if the owner wants it |

**Recovery point objective with the defaults: up to 24 hours of data.** Once real customers place orders, run the backup every 6 hours
(`OnCalendar=*-*-* 00/6:30:00`; the dump is small and restic only uploads changes). Point-in-time recovery (WAL archiving) is *not* implemented: it is the next step if 6 hours of loss is too much.
**Recovery time objective: unknown until the first drill measures it.** The drill prints its duration.

## 2. How a backup run works (and why it cannot hurt)

1. dump the database into a private temporary directory, check size and catalogue (`pg_restore --list`), hash it;
2. add the dump, the config files and the media tree as restic snapshots (client-side AES-256 encryption; the server only ever holds the repository **password file**, the off-site host sees ciphertext);
3. **verify before anything is deleted**: read the dump back out of the repository, compare its hash with the original, read its catalogue, and run `restic check --read-data-subset` (5% by default, 100% in the weekly verify);
4. only then write `last_backup.json` (`verified: true`) and apply retention (`keep-daily 14`, `keep-weekly 8`, `keep-monthly 12`);
5. if any step fails: write `BACKUP_FAILED`, alert, **delete nothing, prune nothing, leave the previous good record untouched**; temporary plaintext is removed in every case.

Tests prove: failed dump keeps the old record and snapshots; a corrupted repository is detected and blocks pruning; an empty database is refused; nothing readable (database rows, media bytes, the env file) is found in the repository; no password reaches any output or state file.

The release tool refuses a migrating deployment unless `last_backup.json` says `verified: true` and is at most 90 minutes old.

## 3. Setting it up (owner/administrator)

1. **Choose an off-site target that is not this server and not the same provider account as the server**: another VPS with SFTP, an S3-compatible bucket, or Backblaze B2. Create credentials limited to that repository.
2. On the server, as the application user:
   ```
   install -d -m 0750 /etc/rastisi/backup
   openssl rand -base64 32 > /etc/rastisi/backup/restic.password && chmod 0600 /etc/rastisi/backup/restic.password
   # >>> copy the password into your password manager NOW. Without it every backup is unreadable. <<<
   restic -r <repository> --password-file /etc/rastisi/backup/restic.password init
   ```
3. Copy `deploy/backup/examples/backup.conf.example` to `/etc/rastisi/backup.conf` (mode 0640) and fill it in. Create `/var/lib/rastisi-backup` (mode 0755, owner = application user).
4. A role for the restore drill that can create databases and nothing else (run once, as the PostgreSQL superuser; never give the application role this):
   ```sql
   CREATE ROLE rastisi_drill LOGIN PASSWORD '<random>' CREATEDB NOSUPERUSER NOCREATEROLE;
   ```
   The drill creates only databases named `<live>_drill_<timestamp>` and drops only those. It cannot read other databases' data (it has no rights on them).
5. First run by hand, watch it, then the drill:
   ```
   sudo -u <app user> RASTISI_BACKUP_CONF=/etc/rastisi/backup.conf python3 /usr/local/lib/rastisi-backup/rastisi_backup.py run
   ... restore-drill
   ... status           # exit 0 = a verified backup younger than max_age_minutes exists
   ```
6. Install the timers (`deploy/backup/examples/*.service|*.timer`): nightly backup, weekly full verification (100% read), monthly restore drill. Then `systemctl enable --now rastisi-backup.timer rastisi-backup-verify.timer rastisi-restore-drill.timer`.
7. Make someone **see** failures: set `alert_cmd`/`alert_to`, and monitor `status` (for example a daily check that alerts on non-zero).

## 4. The restore drill (proof that the backups work)

`rastisi_backup.py restore-drill` restores the newest dump into a scratch database, then compares it with the live database:

* every table that exists live exists in the restored copy;
* row counts of the critical tables (shops, orders, users, subscriptions, invoices) are compared (the restored copy is allowed to be *older*, never *empty* when live has data);
* a sample of media files is streamed back out of the backup and compared byte by byte with the live files (files uploaded after the backup are expected and not an error);
* the scratch database is dropped in every case; the result and duration are written to `last_restore_drill.json`.

A backup that has never been restored is an assumption. Run the drill once at set-up, then monthly (timer), and after any change of PostgreSQL major version.

## 5. Recovery procedures

Rule 1: **stop and think before restoring anything over live data.** A restore replaces data with older data.
Rule 2: restore into a *scratch* database first and look at it. Only then decide.

### A. A table or some rows were damaged or deleted (the server is fine)
1. Restore the newest dump into a scratch database (what the drill does, but keep it): `restic dump latest --tag db <path-to-rastisi.dump> > /tmp/r.dump; createdb rastisi_scratch; pg_restore --no-owner -d rastisi_scratch /tmp/r.dump`.
2. Copy the rows you need from the scratch database (`COPY ... TO` / `INSERT ... SELECT` through `dblink` or a dump of the table). Do not replace the whole live database.
3. Drop the scratch database; delete `/tmp/r.dump`.

### B. The database is lost or unusable (server fine)
1. Put the site in maintenance (stop the unit: `systemctl stop <unit>`; nginx then answers 502, which is honest).
2. Create an empty database with the same name/owner, `pg_restore --no-owner --exit-on-error -d <db> dump`.
3. Start the unit; the release tool's `status` shows which release is current; run `manage.py migrate --plan` as the application user: it must say "nothing to apply" (the dump contains the schema of the release that was running then). If the code is newer than the dump, activate that release again through the workflow.
4. Tell customers that orders placed after the backup time may be missing, and reconcile with the payment gateway statements (`reconcile_platform_payments`, merchant order reconciliation) before reopening.

### C. The server is lost (disk failure, provider incident, compromise)
1. New server (same OS family). Install PostgreSQL, Redis, nginx, Python 3 + venv, `restic`. Do **not** restore the old server's disk.
2. Install the release tooling (`install.sh`) and restore the **config snapshot** (`restic restore latest --tag config --target /tmp/cfg`): this brings back `/etc/rastisi/*.env` (secrets! including `DJANGO_SECRET_KEY` and `PAYMENT_CREDENTIAL_KEY`; without the credential key stored gateway credentials cannot be decrypted).
   * If the server was **compromised**, treat every secret as burnt: rotate the secret key, credential key (re-enter gateway credentials), database and Redis passwords, SMS/e-mail provider keys and the deploy key.
3. Restore the database (procedure B) and the media (`restic restore latest --tag media --target /`).
4. Copy the new server's host key into the `DEPLOY_KNOWN_HOSTS` variable in GitHub; point DNS/nginx at it; run the release workflow for the commit that was active (`active.json` and `history.jsonl` from the old `<base>/state` are in the config snapshot; GitHub's last successful deploy run also shows it).
5. Run the smoke checks and place a test order against the payment gateway's sandbox before announcing recovery.

### D. Media lost, database fine
`restic restore latest --tag media --target /` into a scratch directory, compare, then copy the missing files back. Files uploaded after the backup are gone for good (merchants must re-upload).

## 6. Limits to know about

* Without WAL archiving, the data loss on a database failure is "since the last backup".
* The backup target is only as good as its separation from the server and its own protection (enable object-lock / append-only if the provider offers it, so a compromised server cannot delete its own backups; restic supports `rest-server --append-only`).
* The restic password and the off-site credentials are single points of failure of the *backups*; keep them in the password manager, not only on the server.
* Retention is applied by the same job that creates backups; a stolen server key could in theory prune. Append-only access is the mitigation.
* The first drill will show the real restore time. Write it down; it is the honest RTO.
