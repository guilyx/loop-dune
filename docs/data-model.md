# Data model

All objects live in the Postgres schema `loop`. Migrations: `supabase/migrations/`.

## Tables

| Table | Grain | Notes |
|---|---|---|
| `markets` | market | pool, staking vault, underlying token |
| `vaults` | (market, vault) | CDP vaults and their collateral |
| `series` | series | how each value is read: contract, function, args, decimals, unit |
| `snapshots` | (chain, ts) | one per sampled grid point: block number/time, failed calls |
| `observations` | (series, ts) | `raw numeric(78,0)` exact uint256, `value numeric` scaled |
| `runs` | run | audit log of every indexer/export run with stats |
| `export_cursors` | destination | Dune export watermark |

`ts` is always the grid instant (UTC, top of the hour). `snapshots.block_timestamp` is
the timestamp of the block actually read, which is at or just before `ts`.

## Views

| View | Grain | Columns |
|---|---|---|
| `observations_enriched` | (series, ts) | observations + catalogue context |
| `market_hourly` | (market, hour) | `tvl`, `available_liquidity`, `total_borrowed`, `utilization`, `borrow_apr`, `supply_apr`, `lp_supply`, `lp_price`, `slp_supply`, `slp_price`, `staked_tvl`, `locked_tvl`, `collateral_value`, `vault_debt`, `active_vaults` |
| `vault_hourly` | (vault, hour) | `collateral_balance`, `spot_price`, `collateral_value`, `total_debt`, `debt_ceiling`, `pool_borrowed`, `ltv` |
| `market_daily`, `vault_daily` | (…, day) | last hourly row of each UTC day |
| `series_latest` | series | latest value |
| `chain_freshness` | chain | last snapshot, lag, failed calls |

Amounts in the views are in the market's **underlying token** (WETH, USDC, WBNB, BTCB).
Rates and ratios are fractions (`0.0473` = 4.73%).

## Series

114 series across 4 markets. Run `loop-indexer registry show --json` for the full list,
or query `loop.series`.

| Entity | Metric | Call | Scale |
|---|---|---|---|
| pool | `total_supply` | `totalSupply()` | pool decimals |
| pool | `expected_liquidity` | `expectedLiquidity()` | underlying decimals |
| pool | `available_liquidity` | `availableLiquidity()` | underlying decimals |
| pool | `total_borrowed` | `totalBorrowed()` | underlying decimals |
| pool | `borrow_rate` | `baseInterestRate()` | RAY (1e27) |
| pool | `supply_rate` | `supplyRate()` | RAY (1e27) |
| pool | `locked_shares` | `balanceOf(locker)` | pool decimals |
| staking | `total_supply` | `totalSupply()` | staking decimals |
| staking | `total_assets` | `totalAssets()` | pool decimals |
| vault | `spot_price` | `spotPrice()` | WAD (1e18) — see quirks |
| vault | `total_debt` | `totalDebt()` | WAD (1e18), always |
| vault | `collateral_balance` | `collateral.balanceOf(vault)` | collateral decimals |
| vault | `debt_ceiling` | `pool.creditManagerDebtLimit(vault)` | underlying decimals |
| vault | `pool_borrowed` | `pool.creditManagerBorrowed(vault)` | underlying decimals |

## Derived metrics

| Metric | Definition |
|---|---|
| TVL | `expectedLiquidity`: cash + outstanding debt + accrued interest owed to lenders |
| Utilization | `total_borrowed / expected_liquidity` |
| lpX price | `expected_liquidity / lp_supply` (underlying per pool share) |
| slpX price | `staking.total_assets / staking.total_supply` (pool shares per staked share) |
| Staked TVL | `staking.total_assets × lp_price` |
| Locked TVL | `locked_shares × lp_price` |
| Collateral value | `collateral_balance × spot_price` (in underlying, at the vault's own oracle) |
| LTV | `total_debt / collateral_value` |

## Protocol quirks the model accounts for

All of these were found by reading the chain, and each is encoded in the registry or
the series templates.

* **Vault debt is WAD on every market.** On lpUSD (USDC, 6 decimals) `totalDebt()`
  returns `2236e18` while the pool's `creditManagerBorrowed` returns `2236e6`.
* **Rates are RAY.** `baseInterestRate()` and `supplyRate()` are annual rates scaled by 1e27.
* **One oracle uses 1e30.** The `pendle-syrupusdc-aug25` vault's `spotPrice()` is
  WAD × 1e12; the registry sets `spot_price_decimals: 30`, and `registry verify` checks
  that every spot price lands in a plausible range.
* **Flash lenders are credit managers.** Each pool's first `creditManagers()` entry is
  a flash lender, not a CDP vault. They are listed as `flash_lenders` and excluded.
* **An unregistered vault.** The `ynCoBTCk` vault points at the lpBTC pool but was
  never added as a credit manager, so it has no pool-side series.
* **Stale oracles revert.** `spectra-sdeusd.spotPrice()` reverts at recent blocks.
  Those hours have no `spot_price` row, so `collateral_value` and `ltv` are null rather
  than zero.

## Findings in the data

* **Undercollateralised syrupUSDC position.** From 20 June 2025 the
  `pendle-syrupusdc-aug25` vault carried about 121.5k USDC of debt against
  0.0000000597 LP tokens of collateral (LTV ≈ 8×10¹¹ at the correctly scaled price). At
  the vault's own 1e30-scaled oracle, that dust was valued at about $153k. The debt was
  later reduced to 4,000 USDC, where it has stayed. The dashboard's "Data findings"
  section flags every vault-day like this automatically.
