import { describe, expect, it } from "vitest";

import {
  binnedMedian,
  cumulative,
  histogram,
  median,
  stress,
  stressCurve,
  topWithOther,
  weekStart,
  weeklyLast,
  weeklySum,
} from "@/lib/analytics";

describe("weekly bucketing", () => {
  it("starts weeks on Monday (UTC)", () => {
    expect(weekStart("2025-06-04")).toBe("2025-06-02"); // Wednesday
    expect(weekStart("2025-06-02")).toBe("2025-06-02"); // Monday
    expect(weekStart("2025-06-08")).toBe("2025-06-02"); // Sunday
  });

  it("sums flows and keeps the last state per week", () => {
    const days = [
      { day: "2025-06-02", net_flow: 10, interest: 1 },
      { day: "2025-06-03", net_flow: -4, interest: null },
      { day: "2025-06-09", net_flow: 5, interest: 2 },
    ];
    expect(weeklySum(days, ["net_flow", "interest"])).toEqual([
      { day: "2025-06-02", net_flow: 6, interest: 1 },
      { day: "2025-06-09", net_flow: 5, interest: 2 },
    ]);
    expect(weeklyLast(days).map((d) => d.net_flow)).toEqual([-4, 5]);
  });

  it("accumulates from zero", () => {
    const rows = cumulative([{ day: "a", x: 1 }, { day: "b", x: null }, { day: "c", x: 2 }], ["x"]);
    expect(rows.map((r) => r.x)).toEqual([1, 1, 3]);
  });
});

describe("distributions", () => {
  it("computes medians and histograms", () => {
    expect(median([3, 1, 2])).toBe(2);
    expect(median([4, 1, 3, 2])).toBe(2.5);
    expect(median([])).toBeNull();
    const h = histogram([0.05, 0.15, 0.95, 1.2], 0.5);
    expect(h.map((b) => b.count)).toEqual([2, 2]); // values >= max land in the last bucket
    expect(h[0]?.share).toBe(0.5);
  });

  it("finds the empirical rate curve", () => {
    const pts = [
      { x: 0.51, y: 0.04 },
      { x: 0.52, y: 0.06 },
      { x: 0.91, y: 0.3 },
    ];
    expect(binnedMedian(pts, 0.1).map((p) => [p.n, Number(p.y.toFixed(2))])).toEqual([
      [2, 0.05],
      [1, 0.3],
    ]);
  });

  it("folds small series into Other", () => {
    const w = { a: 5, b: 1, c: 3, d: 0.5, e: 2 };
    expect(topWithOther(w, 3)).toEqual({ keep: ["a", "c", "e"], other: ["b", "d"] });
    expect(topWithOther({ a: 1, b: 2 }, 3).other).toEqual([]);
  });
});

describe("stress test", () => {
  const vaults = [
    // LTV 0.5 -> liquidatable once collateral falls below 1.1 x debt: a 45% drop
    { id: "safe", name: "Safe", collateralValue: 200, debt: 100, liquidationRatio: 1.1 },
    // LTV 0.8 -> liquidatable after a 12% drop
    { id: "tight", name: "Tight", collateralValue: 125, debt: 100, liquidationRatio: 1.1 },
  ];

  it("flags vaults that cross their liquidation ratio", () => {
    expect(stress(vaults, 0).liquidatable).toEqual([]);
    const r = stress(vaults, 0.2);
    expect(r.liquidatable.map((v) => v.id)).toEqual(["tight"]);
    expect(r.debtAtRisk).toBe(100);
    expect(r.uncovered).toBe(0); // 100 collateral still covers 100 debt
    const deep = stress(vaults, 0.5);
    expect(deep.liquidatable).toHaveLength(2);
    expect(deep.uncovered).toBeCloseTo(37.5); // tight: 100 - 62.5
  });

  it("builds a monotonic curve", () => {
    const curve = stressCurve(vaults);
    expect(curve[0]?.shock).toBe(0);
    expect(curve.at(-1)?.shock).toBe(0.9);
    for (let i = 1; i < curve.length; i++) {
      expect(curve[i]!.debtAtRisk).toBeGreaterThanOrEqual(curve[i - 1]!.debtAtRisk);
    }
  });
});
