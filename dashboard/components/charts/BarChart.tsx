"use client";

import { type KeyboardEvent, type PointerEvent, useMemo, useState } from "react";

import { Legend, TableView, Tooltip, barPath, stepIndex, useWidth } from "@/components/charts/kit";
import { day as formatDay, month as formatMonth } from "@/lib/format";
import { linear, niceTicks } from "@/lib/scale";

export interface BarSeries {
  key: string;
  label: string;
  color: string;
}

type Row = { day: string; label?: string };

interface Props {
  title: string;
  data: Row[];
  /**
   * "stack": every series stacked from the baseline (parts of a whole over time).
   * "diverging": one signed series, coloured by sign (inflow / outflow).
   */
  mode: "stack" | "diverging";
  series: BarSeries[];
  /** diverging mode: labels for positive / negative bars */
  signLabels?: [string, string];
  format: (value: number) => string;
  axisFormat?: (value: number) => string;
  /** "time": rows are periods labelled by date; "band": rows carry their own `label`. */
  x?: "time" | "band";
  periodLabel?: string;
  height?: number;
}

const MARGIN = { top: 10, bottom: 26, right: 12 };
const POS = "var(--div-pos)";
const NEG = "var(--div-neg)";

function num(row: Row | undefined, key: string): number | null {
  const v = (row as Record<string, unknown> | undefined)?.[key];
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

export function BarChart({
  title,
  data,
  mode,
  series,
  signLabels = ["Inflow", "Outflow"],
  format,
  axisFormat = format,
  x = "time",
  periodLabel = "Week of",
  height = 220,
}: Props) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [active, setActive] = useState<number | null>(null);

  const model = useMemo(() => {
    if (data.length === 0) return null;
    let lo = 0;
    let hi = 0;
    for (const r of data) {
      if (mode === "stack") {
        const total = series.reduce((sum, s) => sum + Math.max(0, num(r, s.key) ?? 0), 0);
        hi = Math.max(hi, total);
      } else {
        const v = num(r, series[0]!.key) ?? 0;
        lo = Math.min(lo, v);
        hi = Math.max(hi, v);
      }
    }
    const ticks = niceTicks(lo, hi === lo ? lo + 1 : hi, 4);
    const left = Math.max(...ticks.map((t) => axisFormat(t).length)) * 6.6 + 10;
    return { ticks, left };
  }, [data, series, mode, axisFormat]);

  const label = (r: Row) => (x === "band" ? (r.label ?? r.day) : `${periodLabel} ${formatDay(r.day)}`);
  const tableHead = [x === "band" ? "Bucket" : periodLabel, ...(mode === "stack" ? [...series.map((s) => s.label), "Total"] : [series[0]!.label])];
  const tableRows = [...data].reverse().map((r) => {
    const values = series.map((s) => num(r, s.key));
    const cells = values.map((v) => (v === null ? "–" : format(v)));
    if (mode === "stack") cells.push(format(values.reduce<number>((a, v) => a + (v ?? 0), 0)));
    return [x === "band" ? (r.label ?? r.day) : formatDay(r.day), ...cells];
  });

  if (!model) {
    return (
      <div className="chart" ref={ref} style={{ minHeight: height }}>
        <p className="empty">No data in this range.</p>
      </div>
    );
  }

  const { ticks, left } = model;
  const right = Math.max(left + 40, width - MARGIN.right);
  const band = (right - left) / data.length;
  const gap = band > 6 ? 2 : band > 3 ? 1 : 0;
  const barWidth = Math.max(1, Math.min(24, band - gap));
  const xAt = (i: number) => left + i * band + (band - barWidth) / 2;
  const y = linear([ticks[0] as number, ticks[ticks.length - 1] as number], [height - MARGIN.bottom, MARGIN.top]);
  const base = y(0);

  // Label the first bar of a month, keeping labels at least 80px apart.
  const monthTicks: { i: number; text: string }[] = [];
  if (x === "time") {
    let lastMonth = "";
    let lastX = -Infinity;
    data.forEach((r, i) => {
      const m = r.day.slice(0, 7);
      if (m === lastMonth) return;
      lastMonth = m;
      if (xAt(i) - lastX >= 80) {
        monthTicks.push({ i, text: formatMonth(r.day) });
        lastX = xAt(i);
      }
    });
  }
  const bandLabelEvery = Math.max(1, Math.ceil(data.length / Math.max(1, Math.floor((right - left) / 48))));

  function pick(event: PointerEvent<SVGRectElement>) {
    const box = event.currentTarget.getBoundingClientRect();
    const i = Math.floor(((event.clientX - box.left) / Math.max(1, box.width)) * data.length);
    setActive(Math.min(data.length - 1, Math.max(0, i)));
  }
  function keyboard(event: KeyboardEvent<SVGRectElement>) {
    const next = stepIndex(event.key, active, data.length);
    if (next !== null) {
      event.preventDefault();
      setActive(next);
    } else if (event.key === "Escape") setActive(null);
  }

  const activeRow = active === null ? undefined : data[active];
  const tipRows = activeRow
    ? mode === "stack"
      ? [
          ...series
            .map((s) => ({ s, v: num(activeRow, s.key) }))
            .filter(({ v }) => v !== null && v !== 0)
            .reverse()
            .map(({ s, v }) => ({ label: s.label, value: format(v as number), color: s.color })),
          {
            label: "Total",
            value: format(series.reduce((a, s) => a + (num(activeRow, s.key) ?? 0), 0)),
          },
        ]
      : [
          {
            label: series[0]!.label,
            value: (() => {
              const v = num(activeRow, series[0]!.key);
              return v === null ? "–" : `${v > 0 ? "+" : ""}${format(v)}`;
            })(),
            color: (num(activeRow, series[0]!.key) ?? 0) >= 0 ? POS : NEG,
          },
        ]
    : [];

  return (
    <div className="chart" ref={ref} style={{ minHeight: height }}>
      <Legend
        items={
          mode === "stack"
            ? series.map((s) => ({ label: s.label, color: s.color, key: "rect" as const }))
            : [
                { label: signLabels[0], color: POS, key: "rect" as const },
                { label: signLabels[1], color: NEG, key: "rect" as const },
              ]
        }
      />
      {width > 0 && (
        <svg width={width} height={height} role="img" aria-label={`${title}. Use the table view for exact values.`}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={left} x2={right} y1={y(t)} y2={y(t)} stroke="var(--grid)" strokeWidth={1} shapeRendering="crispEdges" />
              <text className="axis-text" x={left - 8} y={y(t)} dy="0.32em" textAnchor="end">
                {axisFormat(t)}
              </text>
            </g>
          ))}
          {data.map((r, i) => {
            const bx = xAt(i);
            const faded = active !== null && active !== i ? 0.55 : 1;
            if (mode === "diverging") {
              const v = num(r, series[0]!.key);
              if (v === null || v === 0) return null;
              return <path key={r.day} d={barPath(bx, base, y(v), barWidth)} fill={v > 0 ? POS : NEG} opacity={faded} />;
            }
            // stacked: bottom series first, 2px surface gap between segments
            let acc = 0;
            const segs = series
              .map((s) => {
                const v = Math.max(0, num(r, s.key) ?? 0);
                const from = acc;
                acc += v;
                return { s, from, to: acc, v };
              })
              .filter((g) => g.v > 0);
            return (
              <g key={r.day} opacity={faded}>
                {segs.map((g, j) => {
                  const isTop = j === segs.length - 1;
                  const y0 = y(g.from);
                  const y1 = y(g.to) + (isTop ? 0 : 1);
                  const y0g = j === 0 ? y0 : y0 - 1;
                  return isTop ? (
                    <path key={g.s.key} d={barPath(bx, y0g, y1, barWidth)} fill={g.s.color} />
                  ) : (
                    <rect key={g.s.key} x={bx} y={y1} width={barWidth} height={Math.max(0, y0g - y1)} fill={g.s.color} />
                  );
                })}
              </g>
            );
          })}
          <line x1={left} x2={right} y1={base} y2={base} stroke="var(--baseline)" strokeWidth={1} shapeRendering="crispEdges" />
          {x === "time"
            ? monthTicks.map((t) => (
                <text key={t.i} className="axis-text" x={xAt(t.i) + barWidth / 2} y={height - 6} textAnchor="middle">
                  {t.text}
                </text>
              ))
            : data.map((r, i) =>
                i % bandLabelEvery === 0 ? (
                  <text key={r.day} className="axis-text" x={xAt(i) + barWidth / 2} y={height - 6} textAnchor="middle">
                    {r.label}
                  </text>
                ) : null,
              )}
          <rect
            className="chart-plot"
            x={left}
            y={MARGIN.top}
            width={Math.max(0, right - left)}
            height={height - MARGIN.top - MARGIN.bottom}
            fill="transparent"
            tabIndex={0}
            aria-label={`${title}: use arrow keys to move between bars`}
            onPointerMove={pick}
            onPointerDown={pick}
            onPointerLeave={() => setActive(null)}
            onKeyDown={keyboard}
            onBlur={() => setActive(null)}
          />
        </svg>
      )}
      {activeRow && (
        <Tooltip x={xAt(active as number) + barWidth / 2} y={MARGIN.top + 28} width={width} title={label(activeRow)} rows={tipRows} />
      )}
      <TableView head={tableHead} rows={tableRows} />
    </div>
  );
}
