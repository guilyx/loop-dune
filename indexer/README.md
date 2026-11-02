# loop-indexer

Hourly on-chain state indexer for Loop Protocol. See the [architecture](../docs/architecture.md)
and the [data model](../docs/data-model.md).

```bash
uv sync                                   # install (Python ≥ 3.11)
uv run loop-indexer --help
```

| Command | What it does |
|---|---|
| `db migrate` | apply `supabase/migrations/*.sql` (idempotent) |
| `registry show [--json]` | list the 114 series and how each is read |
| `registry verify [--chain …]` | re-check every registry fact against an archive node |
| `run [--interval 1h] [--from …] [--to …] [--force] [--chain …]` | snapshot every missing grid point since deployment |
| `export dune [--full]` | append new observations to Dune; refresh catalogue tables |
| `export static --out DIR` | end-of-day JSON for the dashboard's no-database mode |
| `health [--max-lag 3h]` | exit 1 if any chain is stale |

Configuration is environment-only; see [`../.env.example`](../.env.example).

## Layout

```
src/loop_indexer/
  markets.yaml        contract registry (what exists)
  registry.py         typed registry + series templates (what we measure)
  chain/              JSON-RPC client, Multicall3, timestamp→block, deploy-block search
  snapshot.py         read all series at one block
  pipeline.py         plan → resolve → snapshot → persist
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
