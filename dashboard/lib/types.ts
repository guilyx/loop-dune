/** Shapes shared by both data sources (Postgres and the static JSON snapshot). */

export interface TokenMeta {
  address: string;
  symbol: string;
  decimals: number;
}

export interface VaultMeta {
  id: string;
  name: string;
  address: string;
  collateral: TokenMeta;
  registered: boolean;
  notes: string | null;
}

export interface MarketMeta {
  id: string;
  name: string;
  chain: string;
  chainName: string;
  chainId: number;
  explorer: string;
  underlying: TokenMeta;
  pool: { address: string; symbol: string };
  staking: { address: string; symbol: string } | null;
  vaults: VaultMeta[];
}

export interface SeriesMeta {
  series_id: string;
  market_id: string;
  entity_type: "pool" | "staking" | "vault";
  entity_id: string;
  metric: string;
  unit: string;
  description: string;
  contract: string;
  call: string;
}

export interface ChainHealth {
  chainId: number;
  firstDay: string;
  lastDay: string;
  days: number;
  /** share of calendar days with at least one snapshot */
  coverage: number | null;
  snapshots: number;
  failedCalls: number;
  maxBlockLagSeconds: number | null;
}

export interface SeriesHealth {
  series_id: string;
  observations: number;
  reverted: number;
  lastObserved: string | null;
}

export interface Health {
  chains: ChainHealth[];
  reverting: SeriesHealth[];
}

export interface Meta {
  source: "postgres" | "static";
  generatedAt: string;
  resolution: "1d";
  /** chain id -> ISO timestamp of the latest snapshot */
  freshness: Record<string, string>;
  markets: MarketMeta[];
  series: SeriesMeta[];
  health?: Health;
}

type Num = number | null;

/** End-of-day market state (columns of loop.market_daily). */
export interface MarketPoint {
  day: string;
  tvl: Num;
  available_liquidity: Num;
  total_borrowed: Num;
  utilization: Num;
  borrow_apr: Num;
  supply_apr: Num;
  lp_supply: Num;
  lp_price: Num;
  slp_supply: Num;
  slp_price: Num;
  staked_tvl: Num;
  locked_tvl: Num;
  collateral_value: Num;
  vault_debt: Num;
  active_vaults: Num;
}

/** End-of-day vault state (columns of loop.vault_daily). */
export interface VaultPoint {
  day: string;
  collateral_balance: Num;
  spot_price: Num;
  collateral_value: Num;
  total_debt: Num;
  debt_ceiling: Num;
  pool_borrowed: Num;
  ltv: Num;
  liquidation_ratio: Num;
  liquidation_penalty: Num;
  max_ltv: Num;
  /** LTV x liquidation ratio: >= 1 means liquidatable at the vault's oracle */
  capacity_used: Num;
  /** collateral price fall that would make the aggregate position liquidatable */
  drop_to_liquidation: Num;
}

/** loop.market_yield_daily */
export interface YieldPoint {
  day: string;
  realized_apy_7d: Num;
  realized_apy_30d: Num;
  realized_apy_90d: Num;
  pass_through: Num;
}

/** loop.market_flows_daily: tvl_change = interest + net_flow */
export interface FlowPoint {
  day: string;
  tvl_change: Num;
  interest: Num;
  net_flow: Num;
  borrow_change: Num;
}

/** loop.market_concentration_daily */
export interface ConcentrationPoint {
  day: string;
  debt_hhi: Num;
  top_vault_share: Num;
  borrowing_vaults: Num;
}

export interface OracleEvent {
  vault: string;
  day: string;
  kind: "move" | "reverted";
  from: Num;
  to: Num;
  change: Num;
}

export interface MarketAnalytics {
  yield: YieldPoint[];
  flows: FlowPoint[];
  concentration: ConcentrationPoint[];
  oracleEvents: OracleEvent[];
}

export interface MarketData {
  market: string;
  daily: MarketPoint[];
  vaults: Record<string, VaultPoint[]>;
  analytics?: MarketAnalytics;
}

export interface DataSource {
  meta(): Promise<Meta>;
  market(id: string): Promise<MarketData | null>;
}
