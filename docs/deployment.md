# Deployment

Everything needed to host the stack is in this repository. Nothing is deployed by
default: the hourly workflow stays off until you enable it. Budget about an hour. The
running costs are an archive RPC plan and, for the full hourly history, Supabase Pro.

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
2. Run it again with `1h`. This fills the remaining ~35k hourly points; with a paid RPC
   it takes tens of minutes and resumes where it stopped if interrupted.
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

## Alternative: container host

```bash
docker build -f indexer/Dockerfile -t loop-indexer .
docker run --env-file .env loop-indexer db migrate
docker run --env-file .env loop-indexer run
```

Schedule `run` (then `export dune`) hourly with the platform's cron, for example a
Railway or Fly.io scheduled machine, or a Kubernetes CronJob. The dashboard has a
standalone image too: `docker build -t loop-dashboard dashboard/`.
`docker-compose.yml` runs the full stack locally.

## Operations runbook

| Task | Command |
|---|---|
| Is it healthy? | `loop-indexer health --max-lag 3h`, or `select * from loop.chain_freshness` |
| What did the last runs do? | `select * from loop.runs order by run_id desc limit 10` |
| Which calls fail? | `select ts, failed_series from loop.snapshots where failed_count > 0 order by ts desc` |
| Backfill a window | `loop-indexer run --from 2025-01-01 --to 2025-02-01` |
| Re-read a window (e.g. after a registry fix) | `loop-indexer run --from … --to … --force` |
| A new vault appeared | add it to `markets.yaml`, run `registry verify`, then `run --force` from its deployment date |
| Rebuild the Dune table | `loop-indexer export dune --full` |
| Rotate an RPC key | update the `*_RPC_URLS` secret; several URLs give failover |
