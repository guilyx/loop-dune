# HTTP API

The dashboard serves its data as JSON and CSV. Responses are end-of-day values,
cached for an hour (`Cache-Control: public, s-maxage=3600, stale-while-revalidate=86400`).
For hourly data, query [Postgres](data-model.md) or [Dune](dune.md) directly.

## `GET /api/markets`

The catalogue: markets, vaults, every series and how it is read, and data freshness.

```bash
curl -s https://<dashboard>/api/markets | jq '.markets[] | {id, name, chainName}'
```

| Field | Contents |
|---|---|
| `source` | `postgres` or `static` |
| `generatedAt` | when this response was built (ISO 8601) |
| `resolution` | `1d` |
| `freshness` | latest snapshot per chain id |
| `markets[]` | `id`, `name`, `chain`, `chainName`, `chainId`, `explorer`, `underlying`, `pool`, `staking`, `vaults` |
| `health` | coverage per chain and the series with reverting calls |
| `series[]` | `series_id`, `market_id`, `entity_type`, `entity_id`, `metric`, `unit`, `description`, `contract`, `call` |

## `GET /api/markets/{id}`

Everything for one market (`eth`, `usd`, `bnb`, `btc`):

| Field | Contents |
|---|---|
| `market` | the market id |
| `daily[]` | end-of-day market rows (columns below) |
| `vaults` | per-vault end-of-day series, keyed by vault id |
| `analytics` | `yield`, `flows`, `concentration`, `oracleEvents` (the analytics views) |

Unknown ids return `404 {"error": "unknown market <id>"}`.

### `?format=csv`

The `daily` rows as CSV, one line per day:

```text
day,tvl,available_liquidity,total_borrowed,utilization,borrow_apr,supply_apr,lp_supply,
lp_price,slp_supply,slp_price,staked_tvl,locked_tvl,collateral_value,vault_debt,active_vaults
```

```bash
curl -s "https://<dashboard>/api/markets/eth?format=csv" -o loop-eth-daily.csv
```

Amounts are in the market's underlying token (WETH, USDC, WBNB, BTCB) with decimals
applied; rates and utilization are fractions (`0.1289` = 12.89%). Empty cells mean the
on-chain call reverted that day.

## `POST /api/revalidate`

Rebuilds every cached page from the database now, instead of at the next hourly
revalidation. The indexer calls it after each cycle; the VPS deploy script calls it
after a deploy.

```bash
curl -fsS -X POST -H "Authorization: Bearer $REVALIDATE_TOKEN" https://<dashboard>/api/revalidate
# {"revalidated":true,"at":"2026-11-02T20:54:00.551Z"}
```

| Response | When |
|---|---|
| `200` | token matches; pages rebuilt |
| `401` | wrong or missing bearer token (compared in constant time) |
| `404` | `REVALIDATE_TOKEN` is not set: the endpoint is disabled |
