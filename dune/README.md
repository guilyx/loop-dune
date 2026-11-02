# Dune

The indexer publishes four **public** tables to `dune.<namespace>.*` through the Dune
Uploads API (`/v1/uploads`). They are created on first export and kept current by the
hourly job.

| Table | Grain | Refresh |
|---|---|---|
| `loop_observations` | (series, hour) | append-only; one row per series per hour |
| `loop_markets` | market | replaced every run |
| `loop_vaults` | (market, vault) | replaced every run |
| `loop_series` | series | replaced every run (how each value is read on-chain) |

`loop_observations` columns: `ts`, `chain_id`, `block_number`, `market_id`,
`entity_type`, `entity_id`, `metric`, `series_id`, `unit`, `value` (double, decimals
applied), `raw_value` (exact uint256 as text; `cast(raw_value as uint256)`),
`ingested_at`.

Delivery is at-least-once. Always de-duplicate on `(series_id, ts)` keeping the latest
`ingested_at`. Every query below does this.

## Queries

| File | Use it for |
|---|---|
| [`00_observations_dedup.sql`](queries/00_observations_dedup.sql) | base view; save once and reference as `query_<id>` |
| [`01_market_hourly.sql`](queries/01_market_hourly.sql) | TVL, borrows, utilization, APRs, share prices per market and hour |
| [`02_vault_hourly.sql`](queries/02_vault_hourly.sql) | collateral, oracle price, debt and LTV per vault and hour |
| [`03_tvl_daily.sql`](queries/03_tvl_daily.sql) | chart-ready end-of-day TVL / borrows / utilization |
| [`04_market_overview.sql`](queries/04_market_overview.sql) | counters: latest state, all-time peak, drawdown |
| [`05_flows_daily.sql`](queries/05_flows_daily.sql) | TVL change split into interest and net deposits |
| [`06_realized_yield.sql`](queries/06_realized_yield.sql) | realized lender APY from share price vs quoted APR |
| [`07_vault_risk.sql`](queries/07_vault_risk.sql) | capacity used and price drop to liquidation per vault |
| [`08_debt_concentration.sql`](queries/08_debt_concentration.sql) | debt HHI and top-vault share per market |

Each query takes a text parameter `{{namespace}}` (your `DUNE_NAMESPACE`). The
definitions match the Postgres views in `supabase/migrations/`, so Dune and the hosted
dashboard always agree.

## Joining with Dune's own tables

`ts` is the top of the hour in UTC, so it joins directly with hourly price tables:

```sql
select o.ts, o.tvl * p.price as tvl_usd
from query_<market_hourly_id> o
join prices.usd p
  on p.blockchain = 'ethereum'
 and p.contract_address = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2  -- WETH
 and p.minute = o.ts
where o.market_id = 'eth'
```
