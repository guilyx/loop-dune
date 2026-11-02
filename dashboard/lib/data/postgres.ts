import postgres from "postgres";

import type {
  DataSource,
  MarketAnalytics,
  MarketData,
  MarketMeta,
  MarketPoint,
  Meta,
  SeriesMeta,
  VaultPoint,
} from "@/lib/types";

const CHAINS: Record<number, { name: string; explorer: string }> = {
  1: { name: "Ethereum", explorer: "https://etherscan.io" },
  56: { name: "BNB Smart Chain", explorer: "https://bscscan.com" },
};

const MARKET_COLUMNS = [
  "tvl", "available_liquidity", "total_borrowed", "utilization", "borrow_apr", "supply_apr",
  "lp_supply", "lp_price", "slp_supply", "slp_price", "staked_tvl", "locked_tvl",
  "collateral_value", "vault_debt", "active_vaults",
] as const;
const VAULT_COLUMNS = [
  "collateral_balance", "spot_price", "collateral_value", "total_debt", "debt_ceiling",
  "pool_borrowed", "ltv", "liquidation_ratio", "liquidation_penalty", "max_ltv",
  "capacity_used", "drop_to_liquidation",
] as const;
// Mirrors ANALYTICS in indexer/src/loop_indexer/exporters/static.py.
const ANALYTICS = {
  yield: ["loop.market_yield_daily", ["realized_apy_7d", "realized_apy_30d", "realized_apy_90d", "pass_through"]],
  flows: ["loop.market_flows_daily", ["tvl_change", "interest", "net_flow", "borrow_change"]],
  concentration: ["loop.market_concentration_daily", ["debt_hhi", "top_vault_share", "borrowing_vaults"]],
} as const;
const ORACLE_MOVE_THRESHOLD = 0.2;

type Row = Record<string, unknown>;

const num = (v: unknown): number | null => (v === null || v === undefined ? null : Number(v));
const isoDay = (v: unknown): string => (v instanceof Date ? v.toISOString() : String(v)).slice(0, 10);

/** Live data from the loop.* views (read-only role recommended). */
export class PostgresSource implements DataSource {
  private readonly sql: postgres.Sql;

  constructor(url: string) {
    const local = /@(localhost|127\.0\.0\.1|postgres|db)(:|\/)/.test(url);
    this.sql = postgres(url, {
      max: 3,
      idle_timeout: 20,
      prepare: false, // compatible with transaction-mode poolers (Supabase/PgBouncer)
      ssl: local ? false : "require",
    });
  }

  async meta(): Promise<Meta> {
    const [markets, vaults, series, freshness] = await Promise.all([
      // Registry order (chain, then deployment), so colours match the static snapshot.
      this.sql<Row[]>`select * from loop.markets order by chain_id, start_block`,
      this.sql<Row[]>`select * from loop.vaults order by market_id, vault_id`,
      this.sql<Row[]>`
        select series_id, market_id, entity_type, entity_id, metric, unit, description,
               contract_address, function_signature
        from loop.series order by series_id`,
      this.sql<Row[]>`select chain_id, last_snapshot from loop.chain_freshness`,
    ]);
    const [coverage, reverting] = await Promise.all([
      this.sql<Row[]>`
        select chain_id, min(day) as first_day, max(day) as last_day, count(*) as days,
               sum(snapshots) as snapshots, sum(failed_calls) as failed_calls,
               max(max_block_lag_seconds) as max_lag
        from loop.coverage_daily group by chain_id order by chain_id`,
      this.sql<Row[]>`
        select series_id, observations, reverted, last_observed from loop.series_health
        where reverted > 0 order by reverted desc, series_id`,
    ]);
    const marketMeta: MarketMeta[] = markets.map((m) => {
      const chainId = Number(m.chain_id);
      const chain = CHAINS[chainId] ?? { name: String(m.chain), explorer: "" };
      return {
        id: String(m.market_id),
        name: String(m.name),
        chain: String(m.chain),
        chainName: chain.name,
        chainId,
        explorer: chain.explorer,
        underlying: {
          address: String(m.underlying_address),
          symbol: String(m.underlying_symbol),
          decimals: Number(m.underlying_decimals),
        },
        pool: { address: String(m.pool_address), symbol: String(m.pool_symbol) },
        staking: m.staking_address
          ? { address: String(m.staking_address), symbol: String(m.staking_symbol) }
          : null,
        vaults: vaults
          .filter((v) => v.market_id === m.market_id)
          .map((v) => ({
            id: String(v.vault_id),
            name: String(v.name),
            address: String(v.address),
            collateral: {
              address: String(v.collateral_address),
              symbol: String(v.collateral_symbol),
              decimals: Number(v.collateral_decimals),
            },
            registered: Boolean(v.registered),
            notes: v.notes === null ? null : String(v.notes),
          })),
      };
    });
    return {
      source: "postgres",
      generatedAt: new Date().toISOString(),
      resolution: "1d",
      freshness: Object.fromEntries(
        freshness.map((f) => [String(f.chain_id), new Date(f.last_snapshot as string).toISOString()]),
      ),
      markets: marketMeta,
      health: {
        chains: coverage.map((c) => {
          const first = new Date(c.first_day as string);
          const last = new Date(c.last_day as string);
          const span = Math.round((last.getTime() - first.getTime()) / 86_400_000) + 1;
          return {
            chainId: Number(c.chain_id),
            firstDay: isoDay(c.first_day),
            lastDay: isoDay(c.last_day),
            days: Number(c.days),
            coverage: span > 0 ? Number(c.days) / span : null,
            snapshots: Number(c.snapshots),
            failedCalls: Number(c.failed_calls ?? 0),
            maxBlockLagSeconds: num(c.max_lag),
          };
        }),
        reverting: reverting.map((r) => ({
          series_id: String(r.series_id),
          observations: Number(r.observations),
          reverted: Number(r.reverted),
          lastObserved: r.last_observed ? new Date(r.last_observed as string).toISOString() : null,
        })),
      },
      series: series.map(
        (s): SeriesMeta => ({
          series_id: String(s.series_id),
          market_id: String(s.market_id),
          entity_type: s.entity_type as SeriesMeta["entity_type"],
          entity_id: String(s.entity_id),
          metric: String(s.metric),
          unit: String(s.unit),
          description: String(s.description),
          contract: String(s.contract_address),
          call: String(s.function_signature),
        }),
      ),
    };
  }

  async market(id: string): Promise<MarketData | null> {
    const [daily, vaults] = await Promise.all([
      this.sql<Row[]>`select * from loop.market_daily where market_id = ${id} order by day`,
      this.sql<Row[]>`select * from loop.vault_daily where market_id = ${id} order by vault_id, day`,
    ]);
    if (daily.length === 0) return null;
    const byVault: Record<string, VaultPoint[]> = {};
    for (const row of vaults) {
      const point = { day: isoDay(row.day) } as VaultPoint;
      for (const c of VAULT_COLUMNS) point[c] = num(row[c]);
      (byVault[String(row.vault_id)] ??= []).push(point);
    }
    const analytics: Record<string, unknown[]> = {};
    for (const [key, [view, columns]] of Object.entries(ANALYTICS)) {
      // `view` comes from the constant map above (never user input); the id is bound.
      const rows = (await this.sql.unsafe(
        `select * from ${view} where market_id = $1 order by day`,
        [id],
      )) as Row[];
      analytics[key] = rows.map((r) => {
        const point: Record<string, unknown> = { day: isoDay(r.day) };
        for (const c of columns) point[c] = num(r[c]);
        return point;
      });
    }
    const oracle = await this.sql<Row[]>`
      select vault_id, day, spot_price, prev_spot_price, spot_change from loop.oracle_daily
      where market_id = ${id}
        and (abs(spot_change) >= ${ORACLE_MOVE_THRESHOLD}
             or (spot_price is null and prev_spot_price is not null))
      order by day, vault_id`;
    return {
      market: id,
      analytics: {
        yield: analytics.yield as MarketAnalytics["yield"],
        flows: analytics.flows as MarketAnalytics["flows"],
        concentration: analytics.concentration as MarketAnalytics["concentration"],
        oracleEvents: oracle.map((r) => ({
          vault: String(r.vault_id),
          day: isoDay(r.day),
          kind: r.spot_price === null ? "reverted" : "move",
          from: num(r.prev_spot_price),
          to: num(r.spot_price),
          change: num(r.spot_change),
        })),
      },
      daily: daily.map((row) => {
        const point = { day: isoDay(row.day) } as MarketPoint;
        for (const c of MARKET_COLUMNS) point[c] = num(row[c]);
        return point;
      }),
      vaults: byVault,
    };
  }
}
