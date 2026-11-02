"use client";

import { type KeyboardEvent, type PointerEvent, useEffect, useMemo, useRef, useState } from "react";

import { day as formatDay, month as formatMonth } from "@/lib/format";
import { epochDay, linear, nearestIndex, niceTicks, segments } from "@/lib/scale";

export interface ChartSeries {
  key: string;
  label: string;
  /** CSS colour, normally a categorical token such as var(--series-1). */
  color: string;
}

type Row = { day: string };

interface Props {
  title: string;
  data: Row[];
  series: ChartSeries[];
  /** Formats a value for the tooltip, end label and table. */
  format: (value: number) => string;
  /** Formats y-axis ticks (defaults to `format`). */
  axisFormat?: (value: number) => string;
  height?: number;
  /** Soft wash under a single series. */
  area?: boolean;
  /** Start the y-axis at zero (default) - magnitudes should. */
  zeroBased?: boolean;
}

const MARGIN = { top: 10, bottom: 26 };
const LABEL_GAP = 14;

function value(row: Row | undefined, key: string): number | null {
  const v = (row as Record<string, unknown> | undefined)?.[key];
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/** Month-start ticks, thinned to fit the available width. */
function timeTicks(start: number, end: number, width: number): number[] {
  const months: number[] = [];
  const d = new Date(start);
  let cursor = Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1);
  while (cursor <= end) {
    months.push(cursor);
    const c = new Date(cursor);
    cursor = Date.UTC(c.getUTCFullYear(), c.getUTCMonth() + 1, 1);
  }
  const max = Math.max(2, Math.floor(width / 90));
  const step = Math.max(1, Math.ceil(months.length / max));
  return months.filter((_, i) => i % step === 0);
}

export function LineChart({
  title,
  data,
  series,
  format,
  axisFormat = format,
  height = 220,
  area = false,
  zeroBased = true,
}: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const [active, setActive] = useState<number | null>(null);
  // The table view is rendered on demand: it is the accessible fallback, not page weight.
  const [tableOpen, setTableOpen] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setWidth(Math.floor(entry.contentRect.width));
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const model = useMemo(() => {
    const xs = data.map((r) => epochDay(r.day));
    const values = data.flatMap((r) => series.map((s) => value(r, s.key))).filter(
      (v): v is number => v !== null,
    );
    if (values.length === 0 || xs.length === 0) return null;
    const lo = Math.min(...values);
    const hi = Math.max(...values);
    const ticks = niceTicks(zeroBased ? Math.min(0, lo) : lo, hi, 4);
    const labelWidth = Math.max(...ticks.map((t) => axisFormat(t).length)) * 6.6 + 10;
    const single = series.length === 1;
    const right = single ? 12 + Math.min(80, format(hi).length * 7) : 12 + 70;
    return { xs, ticks, left: labelWidth, right, single };
  }, [data, series, zeroBased, axisFormat, format]);

  if (!model) {
    return (
      <div className="chart" ref={ref} style={{ minHeight: height }}>
        <p className="empty">No data in this range.</p>
      </div>
    );
  }

  const { xs, ticks, left, single } = model;
  const plotRight = Math.max(left + 40, width - model.right);
  const x = linear([xs[0] as number, xs[xs.length - 1] as number], [left, plotRight]);
  const y = linear([ticks[0] as number, ticks[ticks.length - 1] as number], [
    height - MARGIN.bottom,
    MARGIN.top,
  ]);
  const baseY = y(Math.max(0, ticks[0] as number));

  const paths = series.map((s) => {
    const runs = segments(data, (r) => value(r, s.key));
    const d = runs
      .map((run) =>
        run
          .map((r, i) => `${i ? "L" : "M"}${x(epochDay(r.day)).toFixed(1)},${y(value(r, s.key) ?? 0).toFixed(1)}`)
          .join(""),
      )
      .join("");
    const wash =
      area && single
        ? runs
            .map((run) => {
              const first = x(epochDay(run[0]!.day)).toFixed(1);
              const last = x(epochDay(run[run.length - 1]!.day)).toFixed(1);
              const line = run
                .map((r) => `L${x(epochDay(r.day)).toFixed(1)},${y(value(r, s.key) ?? 0).toFixed(1)}`)
                .join("");
              return `M${first},${baseY}${line}L${last},${baseY}Z`;
            })
            .join("")
        : null;
    return { s, d, wash };
  });

  // Direct end labels: value for one series, name for several - dropped if they collide.
  // Only series that reach the right edge get one; a label mid-plot would sit on the lines.
  const ends = series
    .map((s) => {
      const i = data.length - 1;
      const v = value(data[i], s.key);
      return v === null ? null : { s, v, x: x(xs[i] as number), y: y(v) };
    })
    .filter((e): e is NonNullable<typeof e> => e !== null)
    .sort((a, b) => a.y - b.y);
  const collide = ends.some((e, i) => i > 0 && e.y - (ends[i - 1] as typeof e).y < LABEL_GAP);
  const showEnds = series.length <= 4 && !collide && width > 0;

  const activeRow = active === null ? undefined : data[active];
  const activeX = active === null ? 0 : x(xs[active] as number);

  function pick(event: PointerEvent<SVGRectElement>) {
    const box = event.currentTarget.getBoundingClientRect();
    const fraction = (event.clientX - box.left) / Math.max(1, box.width);
    setActive(nearestIndex(xs, x.domain[0] + fraction * (x.domain[1] - x.domain[0])));
  }

  function keyboard(event: KeyboardEvent<SVGRectElement>) {
    const last = data.length - 1;
    const current = active ?? last;
    const next =
      event.key === "ArrowLeft" ? Math.max(0, current - 1)
      : event.key === "ArrowRight" ? Math.min(last, current + 1)
      : event.key === "Home" ? 0
      : event.key === "End" ? last
      : null;
    if (next !== null) {
      event.preventDefault();
      setActive(next);
    } else if (event.key === "Escape") {
      setActive(null);
    }
  }

  const tooltipLeft = activeX > width * 0.6;

  return (
    <div className="chart" ref={ref} style={{ minHeight: height }}>
      {series.length > 1 && (
        <div className="legend" aria-hidden="true">
          {series.map((s) => (
            <span key={s.key}>
              <span className="legend-key" style={{ background: s.color }} />
              {s.label}
            </span>
          ))}
        </div>
      )}
      {width > 0 && (
        <svg width={width} height={height} role="img" aria-label={`${title}. Use the table view for exact values.`}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={left} x2={plotRight} y1={y(t)} y2={y(t)} stroke="var(--grid)" strokeWidth={1} shapeRendering="crispEdges" />
              <text className="axis-text" x={left - 8} y={y(t)} dy="0.32em" textAnchor="end">
                {axisFormat(t)}
              </text>
            </g>
          ))}
          <line x1={left} x2={plotRight} y1={baseY} y2={baseY} stroke="var(--baseline)" strokeWidth={1} shapeRendering="crispEdges" />
          {timeTicks(x.domain[0], x.domain[1], plotRight - left).map((t) => (
            <text key={t} className="axis-text" x={x(t)} y={height - 6} textAnchor="middle">
              {formatMonth(new Date(t).toISOString())}
            </text>
          ))}
          {paths.map(({ s, wash }) =>
            wash ? <path key={`${s.key}-wash`} d={wash} fill={s.color} opacity={0.1} /> : null,
          )}
          {paths.map(({ s, d }) => (
            <path key={s.key} d={d} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          ))}
          {showEnds &&
            ends.map((e) => (
              <text key={e.s.key} className="end-label" x={e.x + 8} y={e.y} dy="0.32em">
                {single ? format(e.v) : e.s.label}
              </text>
            ))}
          {activeRow && (
            <g pointerEvents="none">
              <line x1={activeX} x2={activeX} y1={MARGIN.top} y2={height - MARGIN.bottom} stroke="var(--baseline)" strokeWidth={1} />
              {series.map((s) => {
                const v = value(activeRow, s.key);
                return v === null ? null : (
                  <circle key={s.key} cx={activeX} cy={y(v)} r={4} fill={s.color} stroke="var(--surface-1)" strokeWidth={2} />
                );
              })}
            </g>
          )}
          <rect
            className="chart-plot"
            x={left}
            y={MARGIN.top}
            width={Math.max(0, plotRight - left)}
            height={height - MARGIN.top - MARGIN.bottom}
            fill="transparent"
            tabIndex={0}
            aria-label={`${title}: use arrow keys to move between days`}
            onPointerMove={pick}
            onPointerDown={pick}
            onPointerLeave={() => setActive(null)}
            onKeyDown={keyboard}
            onBlur={() => setActive(null)}
          />
        </svg>
      )}
      {activeRow && (
        <div
          className="tooltip"
          role="status"
          style={
            tooltipLeft
              ? { right: width - activeX + 12, top: MARGIN.top + (series.length > 1 ? 28 : 0) }
              : { left: activeX + 12, top: MARGIN.top + (series.length > 1 ? 28 : 0) }
          }
        >
          <div className="tooltip-date">{formatDay(activeRow.day)}</div>
          {series.map((s) => {
            const v = value(activeRow, s.key);
            return (
              <div className="tooltip-row" key={s.key}>
                <span className="legend-key" style={{ background: s.color }} />
                <strong>{v === null ? "–" : format(v)}</strong>
                <span>{s.label}</span>
              </div>
            );
          })}
        </div>
      )}
      <details className="table-toggle" onToggle={(e) => setTableOpen(e.currentTarget.open)}>
        <summary>View as table</summary>
        {tableOpen && (
        <div className="table-scroll">
          <table className="data">
            <thead>
              <tr>
                <th>Date</th>
                {series.map((s) => (
                  <th key={s.key} className="num">
                    {s.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[...data].reverse().map((r) => (
                <tr key={r.day}>
                  <td>{formatDay(r.day)}</td>
                  {series.map((s) => {
                    const v = value(r, s.key);
                    return (
                      <td key={s.key} className="num">
                        {v === null ? "–" : format(v)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        )}
      </details>
    </div>
  );
}
