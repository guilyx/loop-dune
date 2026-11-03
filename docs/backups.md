# Backups

**TL;DR** Daily encrypted `pg_dump` → local volume + S3 bucket → checked weekly by
restoring it in CI. Only the public key is on the server.

| | |
|---|---|
| **What** | The whole `loop` database (`pg_dump` custom format, compressed) |
| **When** | Daily at `BACKUP_AT` (03:17 UTC), plus `stack.sh backup` on demand |
| **Where** | `backups` Docker volume (`daily/`, `monthly/`) and, if set, an S3-compatible bucket |
| **Kept** | 14 days of dailies, 400 days of monthlies (1st of the month) |
| **Encryption** | [age](https://age-encryption.org), to the public keys in `BACKUP_AGE_RECIPIENTS` |
| **Integrity** | `pg_restore --list` before keeping a dump; sha256 next to every file; offsite copy checked after upload |
| **Proof** | Weekly restore drill (CI) and a full round trip in CI on every change |
| **RPO / RTO** | ≤ 24 h of the database / ~5 min to restore |

Code: [`deploy/backup/`](https://github.com/guilyx/loopscan/tree/master/deploy/backup). The image is `postgres:16-alpine` with age,
rclone and the scripts; it runs as the `backup` service in the [VPS stack](vps.md).

## What a lost hour actually costs

Every value is read from contract state at a past block, and the indexer fills every
missing hour on each run. So even without a backup, nothing is lost for good: an empty
database rebuilds itself from the chain. Backups turn that long archive-RPC backfill
into a 5-minute restore, and keep the run log (`loop.runs`) and the Dune export cursor.

After a restore, hours indexed since the backup are indexed and exported to Dune again.
The Dune export is at-least-once by design and the queries de-duplicate on
`(series_id, ts)`, so the repeats are harmless.

## Set up

**1. Make a key pair, on your own machine** (not the server):

```bash
age-keygen -o loop-backup.key
# Public key: age1...
```

Store `loop-backup.key` in a password manager. Lose it and the encrypted backups are
unreadable. For a second holder, put both public keys in `BACKUP_AGE_RECIPIENTS`
(space separated); either private key can then restore.

**2. Make a bucket** on any S3-compatible store (Backblaze B2, Cloudflare R2, AWS S3,
Hetzner, Wasabi...). Create two access keys scoped to that bucket:

* *server*: read + write + delete (uploads and pruning)
* *drill*: read only (for the CI restore drill)

Turn on object versioning or object lock if the provider has it: a compromised server
can then not destroy the history.

**3. Fill in** `deploy/vps/.env`:

```bash
BACKUP_AGE_RECIPIENTS=age1...
BACKUP_REMOTE=offsite:my-bucket/loop
OFFSITE_S3_ENDPOINT=https://s3.eu-central-003.backblazeb2.com   # empty for AWS
OFFSITE_S3_REGION=auto                                          # or the AWS region
OFFSITE_S3_ACCESS_KEY_ID=...
OFFSITE_S3_SECRET_ACCESS_KEY=...
BACKUP_HEARTBEAT_URL=https://hc-ping.com/<uuid>                 # optional
```

Then `stack.sh up -d backup && stack.sh backup` and check the bucket.

**4. Turn on the restore drill.** In the GitHub repository:

* variables: `RESTORE_DRILL_ENABLED=true`, `BACKUP_REMOTE`, `OFFSITE_S3_ENDPOINT`,
  `OFFSITE_S3_REGION` (and `OFFSITE_S3_PROVIDER=AWS` on AWS)
* secrets: `BACKUP_AGE_KEY` (contents of `loop-backup.key`), `OFFSITE_S3_ACCESS_KEY_ID`
  and `OFFSITE_S3_SECRET_ACCESS_KEY` (the read-only pair),
  `RESTORE_DRILL_HEARTBEAT_URL` (optional)

Run *Restore drill* once by hand to see it pass.

## The weekly restore drill

A backup is only trusted once it has been restored. Every Monday,
[`restore-drill.yml`](https://github.com/guilyx/loopscan/blob/master/.github/workflows/restore-drill.yml):

1. lists the bucket and takes the newest backup; fails if it is older than
   `BACKUP_MAX_AGE_HOURS` (30),
2. checks its sha256, decrypts it with the private key (passed on stdin),
3. restores it into a throwaway Postgres in one transaction,
4. checks that snapshots, observations and series are there and that the analytics
   views compute.

It runs in CI because the private key must not be on the server. If you do keep a key
on the server (unencrypted backups, or a dedicated drill key), the backup container
runs the same drill itself on `BACKUP_VERIFY_WEEKDAY`.

## Restore

**Into the live database** (pauses the indexer and dashboard, restores, restarts them):

```bash
# from your machine: stream the key over SSH, nothing is written on the server
ssh loop@<server> /opt/loop-dune/deploy/vps/stack.sh restore latest /dev/stdin < loop-backup.key

# or on the server, with the key copied there temporarily
stack.sh restore loop-20261102T031700Z.dump.age ~/loop-backup.key && shred -u ~/loop-backup.key
```

`stack.sh backups` lists the local files; older ones are fetched from the bucket.
The restore is one transaction: it either replaces everything or changes nothing. It
refuses to touch the live database without the explicit confirmation `stack.sh` passes.
After it, the next indexer cycle fills the hours since the backup.

**On a new server** (the old one is gone): run [the VPS setup](vps.md) with the same
`.env` backup settings, `stack.sh up -d db backup`, then restore as above and
`stack.sh deploy`. Restores read straight from the bucket when the local volume is
empty.

**Anywhere else** (a laptop, a managed Postgres): the backup files are standard
`pg_dump` archives.

```bash
age -d -i loop-backup.key -o loop.dump loop-20261102T031700Z.dump.age
pg_restore --no-owner --dbname "$DATABASE_URL" loop.dump
```

## Alerts and health

* `BACKUP_HEARTBEAT_URL` gets a ping after each backup (`/fail` with the reason if one
  fails). Expect one a day.
* The container's health check turns *unhealthy* when the last good backup is older
  than `BACKUP_MAX_AGE_HOURS` (30); `stack.sh status` shows it with the last backup time.
* The restore drill pings `RESTORE_DRILL_HEARTBEAT_URL`, and GitHub emails you when a
  scheduled workflow fails.

## Testing changes to the scripts

CI (`backups` job) builds the image and runs
[`test-roundtrip.sh`](https://github.com/guilyx/loopscan/blob/master/deploy/backup/test-roundtrip.sh) against a real Postgres:
encrypted backup → offsite copy → delete local → restore from offsite → row counts
must match → second restore is idempotent → drill → a tampered file is rejected → a
live restore without confirmation is refused. Locally:

```bash
DATABASE_URL=postgresql://loop:loop@localhost:5432/loop deploy/backup/test-roundtrip.sh
```
