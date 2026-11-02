"use client";

import { type KeyboardEvent, type PointerEvent, useState } from "react";

import { TableView, Tooltip, useWidth } from "@/components/charts/kit";
import { day as formatDay, month as formatMonth } from "@/lib/format";

const STEPS = 7; // --seq-1 .. --seq-7

interface Props {
  title: string;
  rows: { id: string; label: string }[];
  /** period start dates (columns), ascending */
  columns: string[];
  value: (rowId: string, column: string) => number | null;
  format: (value: number) => string;
  /** value mapped to the darkest sequential step */
  max?: number;
  /** values at or above this are drawn in the critical status colour */
  criticalAt?: number;
  criticalLabel?: string;
  valueLabel: string;
  periodLabel?: string;
}

const CELL_H = 20;
const ROW_GAP = 2;
const AXIS_H = 24;

export function Heatmap({
  title,
  rows,
  columns,
  value,
  format,
  max = 1,
  criticalAt = 1,
  criticalLabel = "Liquidatable",
  valueLabel,
  periodLabel = "Week of",
}: Props) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [active, setActive] = useState<{ r: number; c: number } | null>(null);

  const labelWidth = Math.min(200, Math.max(...rows.map((r) => r.label.length), 4) * 6.4 + 12);
  const plotW = Math.max(0, width - labelWidth - 4);
  const cellW = columns.length ? plotW / columns.length : 0;
  const gap = cellW > 5 ? 1 : 0;
  const height = rows.length * (CELL_H + ROW_GAP) + AXIS_H;

  const fill = (v: number | null) => {
    if (v === null || v === 0) return "var(--empty-cell)";
    if (v >= criticalAt) return "var(--critical)";
    const step = Math.min(STEPS, Math.max(1, Math.ceil((v / max) * STEPS)));
    return `var(--seq-${step})`;
  };

  const monthTicks: { c: number; text: string }[] = [];
  let lastMonth = "";
  let lastX = -Infinity;
  columns.forEach((col, c) => {
    const m = col.slice(0, 7);
    if (m === lastMonth) return;
    lastMonth = m;
    const x = labelWidth + c * cellW;
    if (x - lastX >= 80) {
      monthTicks.push({ c, text: formatMonth(col) });
      lastX = x;
    }
  });

  function pick(event: PointerEvent<SVGRectElement>) {
    const box = event.currentTarget.getBoundingClientRect();
    const c = Math.floor(((event.clientX - box.left) / Math.max(1, box.width)) * columns.length);
    const r = Math.floor((event.clientY - box.top) / (CELL_H + ROW_GAP));
    if (r >= 0 && r < rows.length && c >= 0 && c < columns.length) setActive({ r, c });
  }
  function keyboard(event: KeyboardEvent<SVGRectElement>) {
    const at = active ?? { r: 0, c: columns.length - 1 };
    const moves: Record<string, { r: number; c: number }> = {
      ArrowLeft: { r: at.r, c: Math.max(0, at.c - 1) },
      ArrowRight: { r: at.r, c: Math.min(columns.length - 1, at.c + 1) },
      ArrowUp: { r: Math.max(0, at.r - 1), c: at.c },
      ArrowDown: { r: Math.min(rows.length - 1, at.r + 1), c: at.c },
    };
    const next = moves[event.key];
    if (next) {
      event.preventDefault();
      setActive(next);
    } else if (event.key === "Escape") setActive(null);
  }

  const activeRow = active ? rows[active.r] : undefined;
  const activeCol = active ? columns[active.c] : undefined;
  const activeValue = activeRow && activeCol ? value(activeRow.id, activeCol) : null;

  const tableRows = rows.flatMap((r) =>
    columns
      .map((col) => ({ col, v: value(r.id, col) }))
      .filter((x) => x.v !== null)
      .map(({ col, v }) => [
        `${r.label} · ${formatDay(col)}`,
        format(v as number),
        (v as number) >= criticalAt ? `▲ ${criticalLabel}` : "",
      ]),
  );

  if (rows.length === 0 || columns.length === 0) {
    return <p className="empty">No vault carried debt in this range.</p>;
  }

  return (
    <div className="chart" ref={ref} style={{ minHeight: height }}>
      <div className="scale-legend" aria-hidden="true">
        <span>{valueLabel}</span>
        <span>0%</span>
        <span className="scale-ramp">
          {Array.from({ length: STEPS }, (_, i) => (
            <span key={i} style={{ background: `var(--seq-${i + 1})` }} />
          ))}
        </span>
        <span>{format(max)}</span>
        <span>
          <span className="swatch" style={{ background: "var(--critical)" }} />▲ {criticalLabel} (≥ {format(criticalAt)})
        </span>
        <span>
          <span className="swatch" style={{ background: "var(--empty-cell)" }} />
          No debt or no data
        </span>
      </div>
      {width > 0 && (
        <svg width={width} height={height} role="img" aria-label={`${title}. Use the table view for exact values.`}>
          {rows.map((r, ri) => (
            <g key={r.id}>
              <text className="heatmap-label" x={labelWidth - 8} y={ri * (CELL_H + ROW_GAP) + CELL_H / 2} dy="0.32em" textAnchor="end">
                {r.label}
              </text>
              {columns.map((col, ci) => (
                <rect
                  key={col}
                  x={labelWidth + ci * cellW}
                  y={ri * (CELL_H + ROW_GAP)}
                  width={Math.max(1, cellW - gap)}
                  height={CELL_H}
                  fill={fill(value(r.id, col))}
                  rx={cellW > 8 ? 2 : 0}
                />
              ))}
            </g>
          ))}
          {active && (
            <rect
              x={labelWidth + active.c * cellW - 1}
              y={active.r * (CELL_H + ROW_GAP) - 1}
              width={Math.max(3, cellW - gap + 2)}
              height={CELL_H + 2}
              fill="none"
              stroke="var(--text-primary)"
              strokeWidth={1.5}
              pointerEvents="none"
            />
          )}
          {monthTicks.map((t) => (
            <text key={t.c} className="axis-text" x={labelWidth + t.c * cellW} y={height - 6}>
              {t.text}
            </text>
          ))}
          <rect
            className="chart-plot"
            x={labelWidth}
            y={0}
            width={plotW}
            height={rows.length * (CELL_H + ROW_GAP)}
            fill="transparent"
            tabIndex={0}
            aria-label={`${title}: use arrow keys to move between cells`}
            onPointerMove={pick}
            onPointerDown={pick}
            onPointerLeave={() => setActive(null)}
            onKeyDown={keyboard}
            onBlur={() => setActive(null)}
          />
        </svg>
      )}
      {active && activeRow && activeCol && (
        <Tooltip
          x={labelWidth + (active.c + 0.5) * cellW}
          y={(active.r + 1) * (CELL_H + ROW_GAP) + 34}
          width={width}
          title={`${activeRow.label} · ${periodLabel} ${formatDay(activeCol)}`}
          rows={[
            { label: valueLabel, value: activeValue === null ? "–" : format(activeValue) },
            ...(activeValue !== null && activeValue >= criticalAt
              ? [{ label: "", value: `▲ ${criticalLabel}` }]
              : []),
          ]}
        />
      )}
      <TableView head={["Vault · period", valueLabel, "Status"]} rows={tableRows} />
    </div>
  );
}
