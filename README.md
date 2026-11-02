# Loop Dune

[![CI](https://github.com/guilyx/loop-dune/actions/workflows/ci.yml/badge.svg)](https://github.com/guilyx/loop-dune/actions/workflows/ci.yml)

On-chain analytics for **Loop Protocol**'s lending markets. Every pool and CDP vault is
read straight from contract state on an hourly UTC grid since deployment, stored in
Postgres, published to Dune, and shown on a dashboard.

![Overview](docs/img/overview.png)

| | |
|---|---|
| **Markets** | lpETH and lpUSD on Ethereum; lpBNB and lpBTC on BNB Chain |
| **Coverage** | 4 pools, 4 staking vaults, 16 CDP vaults, 114 series, from each pool's deployment block |
| **Resolution** | hourly (UTC), with daily rollups |
| **Outputs** | Postgres views · public Dune tables · Next.js dashboard · JSON/CSV API |

> The Loop frontend has been sunset. The contracts are still on-chain, so the data can
> still be read, audited and charted. See [the findings](#findings).

## How it works

```mermaid
flowchart LR
  rpc[(Archive RPC<br/>Ethereum · BNB Chain)] -->|Multicall3, 1 call/hour/chain| idx[loop-indexer]
  idx -->|idempotent upserts| pg[(Postgres / Supabase)]
  pg -->|append-only| dune[(Dune tables)]
  pg --> dash[Dashboard · Vercel]
```

* **[Registry](indexer/src/loop_indexer/markets.yaml) verified on-chain.** Tokens,
  decimals, deployment blocks and each pool's vault list are re-checked against the chain
  (`loop-indexer registry verify`).
* **One UTC grid for every chain.** "State as of 14:00 UTC" means the last block at or
  before 14:00 on each chain, so Ethereum and BNB Chain series join row for row.
* **Exact and honest.** Raw `uint256` is kept alongside scaled values. A reverting call
  is recorded as missing, never as zero.
* **Self-healing.** Every run fills every missing hour since deployment. Re-runs are
  no-ops, and outages repair themselves on the next run.

Details: [architecture](docs/architecture.md) · [data model](docs/data-model.md) ·
[deployment](docs/deployment.md) · [Dune](dune/README.md).

![Market page](docs/img/market-eth.png)

## Quick start

Requirements: [uv](https://docs.astral.sh/uv/), Node 20+, and Docker (or any Postgres ≥ 14).

```bash
cp .env.example .env          # add archive RPC URLs
make setup                    # Python + Node dependencies
make db migrate               # local Postgres + schema
make verify                   # check the registry against the chain
make backfill                 # daily snapshots since deployment (~1.5k points)
make run                      # fill in hourly resolution
make export-static dashboard  # http://localhost:3000
```

The dashboard also runs with **no database**: `cd dashboard && npm ci && npm run dev`
serves the committed snapshot in `dashboard/data/`.

## Using the data

| Where | How |
|---|---|
| Postgres | `loop.market_hourly`, `loop.vault_hourly`, `loop.market_daily`, … ([data model](docs/data-model.md)) |
| Dune | `dune.<namespace>.loop_observations` + catalogue tables, and [ready-made queries](dune/queries/) |
| HTTP | `/api/markets`, `/api/markets/eth`, `/api/markets/eth?format=csv` |

```sql
-- utilization and supply APR, end of day
select day, market_id, utilization, supply_apr
from loop.market_daily
order by day desc, market_id;
```

## Findings

The indexer surfaced things the protocol's own accounting hid:

* **A vault borrowed 120k USDC against dust.** The `syrupUSDC` vault's oracle reports
  prices scaled 1e30 instead of 1e18. Read as 1e18, 0.000000059 LP tokens look like about
  $150k of collateral. Debt peaked at 124k USDC. 4,000 USDC is still outstanding.
* **10 of 16 vaults were never tracked** by the previous pipeline, including vaults with
  debt. Its BNB pool metrics read an Ethereum address and were always zero.
* **TVL is 92–99% below its peak.** lpETH went from 915 to 77 WETH, lpUSD from 594k to
  12.9k USDC, and lpBNB from 1,588 to 10 WBNB (2 Nov 2026). lpBTC shows no deposits in
  any daily sample. What remains on lpETH is still 86% borrowed.

More in [docs/data-model.md](docs/data-model.md#findings-in-the-data). The audit of the
old pipeline is in [docs/legacy-review.md](docs/legacy-review.md).

## Repository

```
indexer/      Python indexer: registry, chain client, pipeline, Postgres, exporters, CLI
supabase/     SQL migrations: tables, analysis views, read-only role
dashboard/    Next.js dashboard and JSON/CSV API (Postgres or static snapshot)
dune/         DuneSQL queries over the exported tables
docs/         architecture, data model, deployment runbook, legacy review
.github/      CI (lint, types, tests, builds) and the hourly indexer workflow
```

## Development

```bash
make lint     # ruff, ruff format, mypy --strict, tsc
make test     # pytest (in-memory EVM + Postgres via TEST_DATABASE_URL) and vitest
```

## License

[GPL-3.0](LICENSE).
