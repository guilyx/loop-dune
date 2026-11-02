/** Minimal scale helpers for the hand-built SVG charts. */

export interface Linear {
  (value: number): number;
  domain: [number, number];
  range: [number, number];
}

export function linear(domain: [number, number], range: [number, number]): Linear {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  const span = d1 - d0 || 1;
  const fn = ((value: number) => r0 + ((value - d0) / span) * (r1 - r0)) as Linear;
  fn.domain = domain;
  fn.range = range;
  return fn;
}

/** "Nice" tick values covering [min, max] with roughly `count` ticks. */
export function niceTicks(min: number, max: number, count = 4): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [0];
  if (min === max) {
    if (min === 0) return [0, 1];
    const pad = Math.abs(min) * 0.1;
    return niceTicks(min - pad, max + pad, count);
  }
  const step = niceStep((max - min) / Math.max(1, count));
  const start = Math.floor(min / step) * step;
  const end = Math.ceil(max / step) * step;
  const ticks: number[] = [];
  for (let v = start; v <= end + step / 2; v += step) {
    ticks.push(Number(v.toPrecision(12)));
  }
  return ticks;
}

function niceStep(raw: number): number {
  const exponent = Math.floor(Math.log10(raw));
  const fraction = raw / 10 ** exponent;
  const nice = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 2.5 ? 2.5 : fraction <= 5 ? 5 : 10;
  return nice * 10 ** exponent;
}

/** Index of the element of sorted `xs` nearest to `x`. */
export function nearestIndex(xs: number[], x: number): number {
  if (xs.length === 0) return -1;
  let lo = 0;
  let hi = xs.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if ((xs[mid] as number) <= x) lo = mid;
    else hi = mid;
  }
  return Math.abs((xs[lo] as number) - x) <= Math.abs((xs[hi] as number) - x) ? lo : hi;
}

/** Break a series into contiguous runs of non-null points (gaps stay gaps). */
export function segments<T>(points: T[], value: (p: T) => number | null): T[][] {
  const out: T[][] = [];
  let current: T[] = [];
  for (const p of points) {
    if (value(p) === null) {
      if (current.length) out.push(current);
      current = [];
    } else {
      current.push(p);
    }
  }
  if (current.length) out.push(current);
  return out;
}

export function epochDay(iso: string): number {
  return Date.parse(`${iso.slice(0, 10)}T00:00:00Z`);
}
