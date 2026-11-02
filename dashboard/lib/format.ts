/** Number and date formatting. Pure functions: unit-tested in tests/format.test.ts. */

const compactUnits: [number, string][] = [
  [1e12, "T"],
  [1e9, "B"],
  [1e6, "M"],
  [1e3, "K"],
];

/** 1,284 / 12.9K / 4.2M; small values keep significant digits (0.0123). */
export function compact(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "–";
  const abs = Math.abs(value);
  if (abs === 0) return "0";
  if (abs < 1) return value.toPrecision(digits).replace(/\.?0+$/, "");
  if (abs < 10_000) {
    const decimals = abs < 10 ? 2 : abs < 100 ? 1 : 0;
    return value.toLocaleString("en-US", {
      minimumFractionDigits: 0,
      maximumFractionDigits: decimals,
    });
  }
  for (const [size, suffix] of compactUnits) {
    if (abs >= size) {
      // three significant figures: 12.9K, 399K, 4.2M
      const scaled = value / size;
      const text = Math.abs(scaled) >= 100 ? Math.round(scaled).toString() : scaled.toPrecision(3);
      return `${text.includes(".") ? text.replace(/\.?0+$/, "") : text}${suffix}`;
    }
  }
  return value.toString(); // unreachable: abs >= 10_000 always matches K
}

export function amount(value: number | null | undefined, unit: string): string {
  const text = compact(value);
  return text === "–" ? text : `${text} ${unit}`;
}

/** Ratio -> percentage (0.0473 -> "4.73%"). */
export function percent(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "–";
  const pct = value * 100;
  if (pct >= 1e4) return "> 10,000%";
  return `${pct.toFixed(Math.abs(pct) >= 100 ? 0 : digits)}%`;
}

/** Signed change between two values, as a percentage of the first. */
export function change(from: number | null, to: number | null): number | null {
  if (from === null || to === null || from === 0) return null;
  return (to - from) / Math.abs(from);
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2025-06-03" -> "3 Jun 2025" (UTC, locale-independent). */
export function day(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return `${d} ${MONTHS[(m ?? 1) - 1]} ${y}`;
}

/** "2025-06-03" -> "Jun 2025". */
export function month(iso: string): string {
  const [y, m] = iso.slice(0, 10).split("-").map(Number);
  return `${MONTHS[(m ?? 1) - 1]} ${y}`;
}

export function shortAddress(address: string): string {
  return `${address.slice(0, 6)}…${address.slice(-4)}`;
}
