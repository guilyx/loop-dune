/**
 * Pure analytics helpers for the market tabs. Everything that can be defined in SQL is
 * (loop.market_yield_daily, loop.market_flows_daily, ...); what lives here is
 * presentation-time work: bucketing, cumulative sums and the interactive stress test.
 */

import type { VaultPoint } from "@/lib/types";

type Row = { day: string };
const DAY_MS = 86_400_000;

/** Monday (UTC) of the ISO week containing `iso`, as YYYY-MM-DD. */
export function weekStart(iso: string): string {
  const t = Date.parse(`${iso.slice(0, 10)}T00:00:00Z`);
  const dow = (new Date(t).getUTCDay() + 6) % 7; // Monday = 0
  return new Date(t - dow * DAY_MS).toISOString().slice(0, 10);
}

/** Sum numeric fields per ISO week (flows). Weeks with no data for a field stay null. */
export function weeklySum<T extends Row>(points: T[], keys: (keyof T)[]): (Row & Record<string, number | null>)[] {
  const out = new Map<string, Row & Record<string, number | null>>();
  for (const p of points) {
    const week = weekStart(p.day);
    const row = out.get(week) ?? ({ day: week } as Row & Record<string, number | null>);
    for (const k of keys) {
      const v = p[k];
      if (typeof v === "number") row[k as string] = (row[k as string] ?? 0) + v;
      else row[k as string] ??= null;
    }
    out.set(week, row);
  }
  return [...out.values()].sort((a, b) => a.day.localeCompare(b.day));
}

/** Last point of each ISO week (states such as debt or LTV). */
export function weeklyLast<T extends Row>(points: T[]): T[] {
  const out = new Map<string, T>();
  for (const p of points) out.set(weekStart(p.day), { ...p, day: weekStart(p.day) });
  return [...out.values()].sort((a, b) => a.day.localeCompare(b.day));
}

/** Running totals of numeric fields, starting from 0 at the first point. */
export function cumulative<T extends Row>(points: T[], keys: (keyof T)[]): (Row & Record<string, number>)[] {
  const totals: Record<string, number> = {};
  return points.map((p) => {
    const row = { day: p.day } as Row & Record<string, number>;
    for (const k of keys) {
      const v = p[k];
      totals[k as string] = (totals[k as string] ?? 0) + (typeof v === "number" ? v : 0);
      row[k as string] = totals[k as string] as number;
    }
    return row;
  });
}

export function median(values: number[]): number | null {
  if (values.length === 0) return null;
  const s = [...values].sort((a, b) => a - b);
  const mid = s.length >> 1;
  return s.length % 2 ? (s[mid] as number) : ((s[mid - 1] as number) + (s[mid] as number)) / 2;
}

/** Share of points falling in each utilization bucket ([0, 0.1), [0.1, 0.2), ...). */
export function histogram(values: number[], bucket = 0.1, max = 1): { from: number; to: number; share: number; count: number }[] {
  const n = Math.round(max / bucket);
  const counts = new Array<number>(n).fill(0);
  for (const v of values) {
    const i = Math.min(n - 1, Math.max(0, Math.floor(v / bucket)));
    counts[i] = (counts[i] as number) + 1;
  }
  return counts.map((count, i) => ({
    from: i * bucket,
    to: (i + 1) * bucket,
    count,
    share: values.length ? count / values.length : 0,
  }));
}

/** Median of y for x grouped into buckets: the empirical shape of a rate curve. */
export function binnedMedian(points: { x: number; y: number }[], bucket = 0.05): { x: number; y: number; n: number }[] {
  const groups = new Map<number, number[]>();
  for (const p of points) {
    const k = Math.floor(p.x / bucket);
    groups.set(k, [...(groups.get(k) ?? []), p.y]);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => a - b)
    .map(([k, ys]) => ({ x: (k + 0.5) * bucket, y: median(ys) as number, n: ys.length }));
}

/** Keep the `n` largest series by `weight`, fold the rest into "Other". */
export function topWithOther<K extends string>(weights: Record<K, number>, n: number): { keep: K[]; other: K[] } {
  const ranked = (Object.keys(weights) as K[]).sort((a, b) => weights[b] - weights[a]);
  return ranked.length <= n + 1 ? { keep: ranked, other: [] } : { keep: ranked.slice(0, n), other: ranked.slice(n) };
}

// --------------------------------------------------------------------------- stress test

export interface StressVault {
  id: string;
  name: string;
  collateralValue: number;
  debt: number;
  /** minimum collateral value / debt (1.1 = 110%) */
  liquidationRatio: number;
}

export interface StressResult {
  shock: number;
  liquidatable: StressVault[];
  /** debt held by vaults whose aggregate position would be liquidatable */
  debtAtRisk: number;
  /** debt not covered by collateral even if fully seized: potential bad debt */
  uncovered: number;
}

export function stressVaults(latest: Record<string, VaultPoint | undefined>, names: Record<string, string>): StressVault[] {
  return Object.entries(latest)
    .filter((e): e is [string, VaultPoint] => {
      const v = e[1];
      return !!v && (v.total_debt ?? 0) > 0 && v.collateral_value !== null && (v.liquidation_ratio ?? 0) > 0;
    })
    .map(([id, v]) => ({
      id,
      name: names[id] ?? id,
      collateralValue: v.collateral_value as number,
      debt: v.total_debt as number,
      liquidationRatio: v.liquidation_ratio as number,
    }));
}

/**
 * Apply a uniform collateral price shock (0.3 = -30%) to every vault's aggregate
 * position. Aggregates hide the riskiest individual positions, so this is a floor
 * on what would be liquidated, not an estimate of liquidations.
 */
export function stress(vaults: StressVault[], shock: number): StressResult {
  const liquidatable: StressVault[] = [];
  let debtAtRisk = 0;
  let uncovered = 0;
  for (const v of vaults) {
    const shocked = v.collateralValue * (1 - shock);
    if (shocked < v.debt * v.liquidationRatio) {
      liquidatable.push(v);
      debtAtRisk += v.debt;
    }
    uncovered += Math.max(0, v.debt - shocked);
  }
  return { shock, liquidatable, debtAtRisk, uncovered };
}

export function stressCurve(vaults: StressVault[], max = 0.9, step = 0.01): StressResult[] {
  const out: StressResult[] = [];
  for (let s = 0; s <= max + 1e-9; s += step) out.push(stress(vaults, Number(s.toFixed(4))));
  return out;
}
