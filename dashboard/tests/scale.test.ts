import { describe, expect, it } from "vitest";

import { inRange, peak, undercollateralised } from "@/lib/insights";
import { linear, nearestIndex, niceTicks, segments } from "@/lib/scale";
import type { MarketData, MarketMeta, MarketPoint } from "@/lib/types";

describe("scales", () => {
  it("maps linearly", () => {
    const s = linear([0, 10], [100, 200]);
    expect(s(5)).toBe(150);
  });
  it("produces nice ticks", () => {
    expect(niceTicks(0, 699)).toEqual([0, 200, 400, 600, 800]);
    expect(niceTicks(0, 0.12)).toEqual([0, 0.05, 0.1, 0.15]);
    expect(niceTicks(0, 0)).toEqual([0, 1]);
  });
  it("finds the nearest index", () => {
    expect(nearestIndex([0, 10, 20], 14)).toBe(1);
    expect(nearestIndex([0, 10, 20], 16)).toBe(2);
    expect(nearestIndex([], 1)).toBe(-1);
  });
  it("keeps gaps as gaps", () => {
    const runs = segments([1, null, 2, 3, null], (v) => v);
    expect(runs).toEqual([[1], [2, 3]]);
  });
});

const point = (day: string, tvl: number | null): MarketPoint =>
  ({ day, tvl }) as unknown as MarketPoint;

describe("insights", () => {
  it("finds the peak and filters ranges", () => {
    const pts = [point("2025-01-01", 5), point("2025-02-01", 9), point("2025-03-01", null)];
    expect(peak(pts)).toEqual({ value: 9, day: "2025-02-01" });
    expect(inRange(pts, 30).map((p) => p.day)).toEqual(["2025-02-01", "2025-03-01"]);
    expect(inRange(pts, Infinity)).toHaveLength(3);
  });

  it("flags vault-days with debt above collateral value", () => {
    const market = {
      id: "usd",
      name: "Loop USD",
      vaults: [{ id: "v", name: "V", collateral: { symbol: "LPT" } }],
    } as unknown as MarketMeta;
    const vp = (day: string, ltv: number, debt: number) => ({
      day, ltv, total_debt: debt, collateral_balance: 1, spot_price: 1, collateral_value: 1,
      debt_ceiling: 0, pool_borrowed: debt, liquidation_ratio: 1.1, liquidation_penalty: 0.99,
      max_ltv: 1 / 1.1, capacity_used: ltv * 1.1, drop_to_liquidation: 0,
    });
    const data: Record<string, MarketData> = {
      usd: { market: "usd", daily: [], vaults: { v: [vp("2025-06-19", 0.5, 1), vp("2025-06-20", 8e11, 121_504), vp("2025-07-01", 8e11, 120_009)] } },
    };
    const [flag] = undercollateralised([market], data);
    expect(flag?.days).toBe(2);
    expect(flag?.firstDay).toBe("2025-06-20");
    expect(flag?.worst.total_debt).toBe(121_504);
  });
});
