# Indexer CLI and configuration

`loop-indexer` is a Python package in
[`indexer/`](https://github.com/guilyx/loop-dune/tree/master/indexer) (Python ≥ 3.11,
managed with [uv](https://docs.astral.sh/uv/)). It also ships as a Docker image,
`ghcr.io/guilyx/loop-dune-indexer`.

```bash
cd indexer
uv sync
uv run loop-indexer --help
```

## Commands

| Command | What it does |
|---|---|
| `db migrate` | Apply `supabase/migrations/*.sql` (idempotent) |
| `registry show [--json]` | List the 146 series and how each is read |
| `registry verify [--chain …]` | Re-check every registry fact against an archive node |
| `run [--interval 1h] [--from …] [--to …] [--force] [--chain …]` | Snapshot every missing grid point since deployment, and back-fill newly registered series at stored blocks |
| `export dune [--full]` | Append new observations to Dune; refresh the catalogue tables |
| `export static --out DIR` | End-of-day JSON for the dashboard's no-database mode |
| `health [--max-lag 3h]` | Exit 1 if any chain is stale |
| `schedule [--every 1h] [--offset 17m]` | Long-running loop for servers (below) |

### `schedule`

For hosts without their own cron (a VPS, a Fly.io machine, a Kubernetes Deployment):

1. applies pending migrations on start, then runs a cycle immediately;
2. every hour at :17 UTC: **index → export to Dune** (if configured) **→ refresh the
   dashboard** (if configured) **→ freshness check**;
3. after each cycle, pings `HEARTBEAT_URL` (`<url>/fail` with the failed steps in the
   body if any step failed).

A failing step never stops the next one or the next hour. `SIGTERM` lets the current
step finish and exits without waiting for the next slot, so `docker stop` is safe.

Options: `--every`, `--offset` (delay after each boundary, so the chain's finality
window has passed), `--interval` (sampling), `--max-lag`, `--no-dune`, `--concurrency`,
`--no-run-now`, `--no-migrate`.

## Configuration

Environment variables only (a `.env` file in the working directory is read too). See
[`.env.example`](https://github.com/guilyx/loop-dune/blob/master/.env.example).

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql://loop:loop@localhost:5432/loop` | Postgres (owner role) |
| `ETH_RPC_URLS`, `BSC_RPC_URLS` | | Archive RPC endpoints, comma-separated; the client fails over between them |
| `RPC_TIMEOUT` | `30` | Seconds per request |
| `RPC_MAX_RETRIES` | `6` | Retries with backoff per request |
| `RPC_MAX_BATCH_SIZE` | `20` | JSON-RPC batch size |
| `FINALITY_SECONDS` | `900` | Never snapshot closer than this to the chain head (reorg safety) |
| `DUNE_API_KEY`, `DUNE_NAMESPACE` | | Enable the Dune export |
| `DUNE_TABLE_PREFIX` | `loop` | Dune table names: `<prefix>_observations`, … |
| `MIGRATIONS_DIR` | repo `supabase/migrations` | Set in the Docker image |
| `HEARTBEAT_URL` | | Dead-man's switch pinged by `schedule` |
| `DASHBOARD_REVALIDATE_URL`, `REVALIDATE_TOKEN` | | Refresh the dashboard after each `schedule` cycle |
| `LOG_LEVEL` | `INFO` | |
| `LOG_FORMAT` | `auto` | `json` (one object per line), `console`, or `auto` (console on a TTY, JSON otherwise) |

## Layout

```text
src/loop_indexer/
  markets.yaml        contract registry (what exists)
  registry.py         typed registry + series templates (what we measure)
  chain/              JSON-RPC client, Multicall3, timestamp → block, deploy-block search
  snapshot.py         read all series at one block
  pipeline.py         plan → resolve → snapshot → persist
  scheduler.py        the `schedule` loop and heartbeat
  storage/store.py    Postgres access (idempotent upserts)
  exporters/          Dune (Uploads API), static JSON
  verify.py           registry vs chain checks
  cli.py              Typer CLI
tests/                in-memory EVM (fakechain.py) + Postgres integration tests
```

## Tests

```bash
uv run pytest                                              # unit tests
TEST_DATABASE_URL=postgresql://…/loop_test uv run pytest   # + Postgres suite
uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy
```

CI runs all of it with a Postgres service and enforces 85% coverage.
