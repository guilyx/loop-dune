import { epochDay, linear } from "@/lib/scale";

/** Trend glyph for stat tiles: de-emphasised line, current value in the accent. */
export function Sparkline({
  points,
  label,
}: {
  points: { day: string; value: number | null }[];
  label: string;
}) {
  const valid = points.filter((p): p is { day: string; value: number } => p.value !== null);
  if (valid.length < 2) return null;
  const w = 100;
  const h = 28;
  const values = valid.map((p) => p.value);
  const x = linear([epochDay(valid[0]!.day), epochDay(valid[valid.length - 1]!.day)], [1, w - 1]);
  const y = linear([Math.min(0, ...values), Math.max(...values) || 1], [h - 2, 2]);
  const d = valid.map((p, i) => `${i ? "L" : "M"}${x(epochDay(p.day)).toFixed(2)},${y(p.value).toFixed(2)}`).join("");
  const last = valid[valid.length - 1]!;
  const lx = x(epochDay(last.day)).toFixed(2);
  const ly = y(last.value).toFixed(2);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" width="100%" height={h} role="img" aria-label={label}>
      <path d={d} fill="none" stroke="var(--deemphasis)" strokeWidth={1.5} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
      {/* zero-length round-capped path renders as an undistorted dot */}
      <path d={`M${lx},${ly}L${lx},${ly}`} stroke="var(--accent)" strokeWidth={7} strokeLinecap="round" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
