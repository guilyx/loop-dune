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
| `vault_hourly` | (vault, hour) | `collateral_balance`, `spot_price`, `collateral_value`, `total_debt`, `debt_ceiling`, `pool_borrowed`, `ltv`, `liquidation_ratio`, `liquidation_penalty`, `max_ltv`, `capacity_used`, `drop_to_liquidation` |
| `market_daily`, `vault_daily` | (…, day) | last hourly row of each UTC day |
| `market_yield_daily` | (market, day) | `realized_apy_7d/30d/90d` (from lpX share price), `supply_apr`, `borrow_apr`, `utilization`, `pass_through` |
| `market_flows_daily` | (market, day) | `tvl_change` = `interest` + `net_flow`, `borrow_change` |
| `vault_share_daily` | (vault, day) | `debt_share`, `collateral_share` |
| `market_concentration_daily` | (market, day) | `debt_hhi`, `top_vault_share`, `borrowing_vaults` |
| `oracle_daily` | (vault, day) | `spot_price`, `prev_spot_price`, `spot_change` |
| `series_latest` | series | latest value |
| `chain_freshness` | chain | last snapshot, lag, failed calls |
| `coverage_daily` | (chain, day) | snapshots, reverted calls, max block lag |
| `series_health` | series | observations, reverted snapshots, last observed |

Amounts in the views are in the market's **underlying token** (WETH, USDC, WBNB, BTCB).
Rates and ratios are fractions (`0.0473` = 4.73%).

## Series

146 series across 4 markets. Run `loop-indexer registry show --json` for the full list,
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
| vault | `liquidation_ratio` | `vaultConfig()[1]` | WAD (1.1 = 110%) |
| vault | `liquidation_penalty` | `liquidationConfig()[0]` | WAD (0.99 = 1% penalty) |

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
| Capacity used | `LTV × liquidation_ratio`; ≥ 100% means the aggregate position is liquidatable |
| Drop to liquidation | `1 − LTV × liquidation_ratio`: collateral price fall before liquidation |
| Realized APY (n days) | `(lp_price_t / lp_price_{t−n})^(365/n) − 1`, net of any losses |
| Pass-through | `supply_apr / (borrow_apr × utilization)`: borrower interest reaching lenders |
| Interest / net deposits | `lp_supply_{t−1} × Δlp_price` / `Δlp_supply × lp_price_t`; they sum exactly to ΔTVL |
| Debt HHI | `Σ debt_share²` across vaults; 100% = one vault holds all debt |

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

* **syrupUSDC vault borrowed against dust.** On 18 June 2025 the
  `pendle-syrupusdc-aug25` vault held 120,010 USDC of debt against 0.000000059 LP tokens
  of collateral (worth well under a cent). Read through the vault's own 1e30-scaled oracle
  as if it were 1e18, that dust looks like about $150k of collateral, which is what made
  the position look healthy on-chain. Debt peaked at 124,010 USDC and was later reduced.
  4,000 USDC is still outstanding against 0.000000002 LP tokens (as of 2 Nov 2026).
* **sdeUSD oracle failure.** On 7 November 2025 the `spectra-sdeusd` oracle reported
  0.209, a tenth of the previous day's 2.09, which put the vault at 759% LTV. From
  8 November `spotPrice()` reverts. The vault's 2,236 USDC of debt is unchanged.

The dashboard's "Data findings" section flags every vault-day with LTV above 100%
automatically.
