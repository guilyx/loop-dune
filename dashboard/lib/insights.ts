/** Derived facts the dashboard calls out. Pure functions over the shared data shapes. */

import type { MarketData, MarketMeta, MarketPoint, VaultPoint } from "@/lib/types";

export interface Peak {
  value: number;
  day: string;
}

export function peak(points: MarketPoint[], key: keyof MarketPoint = "tvl"): Peak | null {
  let best: Peak | null = null;
  for (const p of points) {
    const v = p[key];
    if (typeof v === "number" && (best === null || v > best.value)) best = { value: v, day: p.day };
  }
  return best;
}

export function latest<T extends { day: string }>(points: T[], key: keyof T): T | undefined {
  for (let i = points.length - 1; i >= 0; i--) {
    const p = points[i] as T;
    if (typeof p[key] === "number") return p;
  }
  return undefined;
}

export interface Undercollateralised {
  market: MarketMeta;
  vaultId: string;
  vaultName: string;
  collateralSymbol: string;
  firstDay: string;
  worst: VaultPoint;
  days: number;
}

/**
 * Vault-days where reported debt exceeded collateral valued at the vault's own oracle
 * (LTV > 1). Healthy CDP vaults never show this; it marks bad debt or a mispriced oracle.
 */
export function undercollateralised(
  markets: MarketMeta[],
  data: Record<string, MarketData>,
): Undercollateralised[] {
  const out: Undercollateralised[] = [];
  for (const market of markets) {
    const vaults = data[market.id]?.vaults ?? {};
    for (const vault of market.vaults) {
      const bad = (vaults[vault.id] ?? []).filter(
        (p) => p.ltv !== null && p.ltv > 1 && (p.total_debt ?? 0) > 0,
      );
      if (bad.length === 0) continue;
      const worst = bad.reduce((a, b) => ((b.total_debt ?? 0) > (a.total_debt ?? 0) ? b : a));
      out.push({
        market,
        vaultId: vault.id,
        vaultName: vault.name,
        collateralSymbol: vault.collateral.symbol,
        firstDay: bad[0]!.day,
        worst,
        days: bad.length,
      });
    }
  }
  return out;
}

export const RANGES = [
  { id: "30d", label: "30D", days: 30 },
  { id: "90d", label: "90D", days: 90 },
  { id: "1y", label: "1Y", days: 365 },
  { id: "all", label: "All", days: Infinity },
] as const;
export type RangeId = (typeof RANGES)[number]["id"];

/** Keep points within `days` of the latest point. */
export function inRange<T extends { day: string }>(points: T[], days: number): T[] {
  if (!Number.isFinite(days) || points.length === 0) return points;
  const end = Date.parse(points[points.length - 1]!.day);
  const start = end - days * 86_400_000;
  return points.filter((p) => Date.parse(p.day) >= start);
}
