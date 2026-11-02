# Deployment

Everything needed to host the stack is in this repository. Nothing is deployed by
default: every scheduled workflow stays off until you enable it. Two ways to host it:

| | Managed (this page) | One VPS ([vps.md](vps.md)) |
|---|---|---|
| Database | Supabase | Postgres container |
| Hourly indexer | GitHub Actions cron | `loop-indexer schedule` container |
| Dashboard | Vercel | Container behind Caddy (auto HTTPS) |
| Backups | Supabase's own (Pro: daily) | Encrypted `pg_dump` to S3, drilled weekly ([backups.md](backups.md)) |
| Cost | RPC plan + Supabase Pro for the full hourly history | RPC plan + a ~€5/month server + a few cents of storage |
| Ops | None | Docker host to keep patched (automated by `bootstrap.sh`) |

Pick one. Running both against different databases would export the same hours to
Dune twice (harmless for the queries, which de-duplicate, but wasteful).

The rest of this page is the managed setup. Budget about an hour.

| Component | Service | Free tier enough? |
|---|---|---|
| Database | Supabase (Postgres 15+) | Partly: ~1M rows (~340 MB with indexes) per year of hourly data, so the full history since 2024 (~700 MB) exceeds the free plan's database size. Use Pro, or keep older history daily. |
| Indexer | GitHub Actions cron | Yes: ~1–2 min per hourly run once caught up |
| Dashboard | Vercel | Yes |
| Dune export | Dune API | Yes, for public tables |
| Archive RPC | Alchemy / QuickNode / dRPC / NodeReal | Usually needs a paid plan for a full hourly backfill |

## 1. Database (Supabase)

1. Create a project. Note the **direct** connection string (indexer) and the
   **transaction pooler** string (dashboard, port 6543).
2. Apply the schema, either way:
   ```bash
   supabase link --project-ref <ref> && supabase db push      # Supabase CLI
   ```
   ```bash
   DATABASE_URL=<direct-url> make migrate                      # or the indexer
   ```
   The migrations are idempotent, so running both is harmless.
3. Create a read-only login for the dashboard (the migration creates the `loop_reader` role):
   ```sql
   create role dashboard login password '<strong-password>' in role loop_reader;
   ```
   The `loop` schema is not exposed through Supabase's REST API. Access is via SQL
   connections only.

## 2. Indexer (GitHub Actions)

In **Settings → Secrets and variables → Actions**:

| Kind | Name | Value |
|---|---|---|
| Secret | `DATABASE_URL` | direct connection string (read/write) |
| Secret | `ETH_RPC_URLS` | comma-separated Ethereum **archive** endpoints |
| Secret | `BSC_RPC_URLS` | comma-separated BNB Chain **archive** endpoints |
| Secret | `DUNE_API_KEY` | optional, Read/Write scope |
| Variable | `DUNE_NAMESPACE` | optional, your Dune user or team handle |
| Variable | `INDEXER_ENABLED` | `true` to turn on the hourly schedule |

Then:

1. Run **Actions → Indexer → Run workflow** with interval `1d` once for a fast first
   backfill (about 1.5k snapshots).
2. Run it again with `1h`. This fills the remaining ~35k hourly points. Every snapshot
   is committed as soon as it is read, so if a run hits the job's 50-minute timeout or
   the RPC's rate limits, just run it again: it resumes at the first missing hour.
3. Set `INDEXER_ENABLED=true`. From then on, each hourly run snapshots the hours it
   finds missing, appends them to Dune and fails if any chain is more than 3 hours behind.

> GitHub may delay scheduled runs by several minutes and disables schedules in
> repositories with no activity for 60 days. For a stricter SLA, run the same image on
> a container host (see *Alternative: container host* below).

## 3. Dashboard (Vercel)

1. Import the repository and set **Root Directory** to `dashboard/`.
2. Environment variables:
   * `DATABASE_URL`: the pooled string for the `dashboard` login (`?sslmode=require` is implied).
   * `NEXT_PUBLIC_DUNE_NAMESPACE`: optional, shown on the Data page.
3. Deploy. Pages revalidate hourly.
4. Optional, for instant refreshes: set `REVALIDATE_TOKEN` (any long random string) in
   Vercel, and in GitHub the secret `REVALIDATE_TOKEN` plus the variable
   `DASHBOARD_REVALIDATE_URL=https://<your-app>/api/revalidate`. The indexer workflow
   then rebuilds the pages right after each run.

Without `DATABASE_URL`, the dashboard serves the static snapshot in `dashboard/data/`.
That is how preview deployments and forks work. Refresh the snapshot with
`make export-static`.

## 4. Dune

With `DUNE_API_KEY` and `DUNE_NAMESPACE` set, every indexer run:

* creates the public tables on first use (`loop_observations`, `loop_markets`,
  `loop_vaults`, `loop_series`),
* replaces the three small catalogue tables,
* appends observations ingested since the last acknowledged batch.

Create queries from `dune/queries/` and set their `namespace` parameter. See
[`dune/README.md`](../dune/README.md).

## Other container hosts

The images on GHCR (`loop-dune-indexer`, `loop-dune-dashboard`, `loop-dune-backup`, see
[vps.md](vps.md#images)) run anywhere:

* **Long-running** (a VPS, Fly.io machine, Kubernetes Deployment): run the indexer as
  `loop-indexer schedule`. It migrates on start, runs every hour at :17, survives
  failing steps, stops cleanly on SIGTERM and pings `HEARTBEAT_URL` after each cycle.
* **Platform cron** (Railway cron, Kubernetes CronJob, Cloud Run jobs): run
  `loop-indexer run`, then `loop-indexer export dune`, hourly.

`docker-compose.yml` at the root runs the full stack locally; `deploy/vps/` is the
production version.

## Operations runbook

| Task | Command |
|---|---|
| Is it healthy? | `loop-indexer health --max-lag 3h`, or `select * from loop.chain_freshness` |
| What did the last runs do? | `select * from loop.runs order by run_id desc limit 10` |
| Which calls fail? | `select ts, failed_series from loop.snapshots where failed_count > 0 order by ts desc` |
| Backfill a window | `loop-indexer run --from 2025-01-01 --to 2025-02-01` |
| Re-read a window (e.g. after a registry fix) | `loop-indexer run --from … --to … --force` |
| A new vault or metric | add it to `markets.yaml` (or the series templates), run `registry verify`; the next `run` back-fills its history at the stored snapshot blocks |
| Rebuild the Dune table | `loop-indexer export dune --full` |
| Rotate an RPC key | update the `*_RPC_URLS` secret; several URLs give failover |
