import { describe, expect, it } from "vitest";

import { amount, change, compact, day, month, percent, shortAddress } from "@/lib/format";

describe("compact", () => {
  it("formats magnitudes", () => {
    expect(compact(0)).toBe("0");
    expect(compact(0.012345)).toBe("0.0123");
    expect(compact(7.456)).toBe("7.46");
    expect(compact(65.97)).toBe("66");
    expect(compact(1284)).toBe("1,284");
    expect(compact(12_900)).toBe("12.9K");
    expect(compact(399_316)).toBe("399K");
    expect(compact(4_200_000)).toBe("4.2M");
    expect(compact(-12_900)).toBe("-12.9K");
  });
  it("handles missing values", () => {
    expect(compact(null)).toBe("–");
    expect(compact(Number.NaN)).toBe("–");
    expect(amount(null, "WETH")).toBe("–");
    expect(amount(1.5, "WETH")).toBe("1.5 WETH");
  });
});

describe("percent and change", () => {
  it("formats ratios", () => {
    expect(percent(0.0473)).toBe("4.73%");
    expect(percent(1.5)).toBe("150%");
    expect(percent(null)).toBe("–");
    expect(percent(7.9e9)).toBe("> 10,000%");
  });
  it("computes signed change", () => {
    expect(change(100, 50)).toBe(-0.5);
    expect(change(0, 50)).toBeNull();
    expect(change(null, 1)).toBeNull();
  });
});

describe("dates", () => {
  it("is UTC and locale independent", () => {
    expect(day("2025-06-03")).toBe("3 Jun 2025");
    expect(day("2025-06-03T23:59:00Z")).toBe("3 Jun 2025");
    expect(month("2024-12-01")).toBe("Dec 2024");
    expect(shortAddress("0xa684EAf215ad323452e2B2bF6F817d4aa5C116ab")).toBe("0xa684…16ab");
  });
});
