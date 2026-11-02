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

export interface Meta {
  source: "postgres" | "static";
  generatedAt: string;
  resolution: "1d";
  /** chain id -> ISO timestamp of the latest snapshot */
  freshness: Record<string, string>;
  markets: MarketMeta[];
  series: SeriesMeta[];
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
}

export interface MarketData {
  market: string;
  daily: MarketPoint[];
  vaults: Record<string, VaultPoint[]>;
}

export interface DataSource {
  meta(): Promise<Meta>;
  market(id: string): Promise<MarketData | null>;
}
