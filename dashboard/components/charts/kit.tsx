"use client";

import { type ReactNode, type RefObject, useEffect, useRef, useState } from "react";

/** Measure the chart container so SVG geometry is in real pixels (crisp hairlines). */
export function useWidth<T extends HTMLElement>(): [RefObject<T | null>, number] {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setWidth(Math.floor(entry.contentRect.width));
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

export type LegendKey = "line" | "rect" | "dot";

export function Legend({ items }: { items: { label: string; color: string; key?: LegendKey }[] }) {
  return (
    <div className="legend" aria-hidden="true">
      {items.map((it) => (
        <span key={it.label}>
          <span
            className={it.key === "line" ? "legend-key" : "swatch"}
            style={{
              background: it.color,
              ...(it.key === "dot" ? { borderRadius: "50%", width: 10, height: 10 } : {}),
            }}
          />
          {it.label}
        </span>
      ))}
    </div>
  );
}

/** The accessible fallback for every chart, rendered only when opened. */
export function TableView({ head, rows }: { head: string[]; rows: ReactNode[][] }) {
  const [open, setOpen] = useState(false);
  return (
    <details className="table-toggle" onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>View as table</summary>
      {open && (
        <div className="table-scroll">
          <table className="data">
            <thead>
              <tr>
                {head.map((h, i) => (
                  <th key={h} className={i ? "num" : undefined}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>
                  {r.map((cell, j) => (
                    <td key={j} className={j ? "num" : undefined}>
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </details>
  );
}

export interface TooltipRow {
  label: string;
  value: string;
  color?: string;
}

/** Values lead, labels follow; keyed with a short line in the series colour. */
export function Tooltip({
  x,
  y,
  width,
  title,
  rows,
}: {
  x: number;
  y: number;
  width: number;
  title: string;
  rows: TooltipRow[];
}) {
  const flip = x > width * 0.6;
  return (
    <div
      className="tooltip"
      role="status"
      style={flip ? { right: width - x + 12, top: y } : { left: x + 12, top: y }}
    >
      <div className="tooltip-date">{title}</div>
      {rows.map((r) => (
        <div className="tooltip-row" key={r.label}>
          {r.color && <span className="legend-key" style={{ background: r.color }} />}
          <strong>{r.value}</strong>
          <span>{r.label}</span>
        </div>
      ))}
    </div>
  );
}

/** Arrow-key navigation over `count` positions; returns the next index or null. */
export function stepIndex(key: string, current: number | null, count: number): number | null {
  const last = count - 1;
  const at = current ?? last;
  if (key === "ArrowLeft") return Math.max(0, at - 1);
  if (key === "ArrowRight") return Math.min(last, at + 1);
  if (key === "Home") return 0;
  if (key === "End") return last;
  return null;
}

/** SVG path for a bar with a 4px rounded data end and a square baseline end. */
export function barPath(x: number, base: number, end: number, width: number): string {
  const h = Math.abs(end - base);
  if (h < 0.5 || width <= 0) return "";
  const r = Math.min(4, width / 2, h);
  const up = end < base; // SVG y grows downwards
  const top = up ? end : base;
  const bottom = up ? base : end;
  if (up) {
    return `M${x},${bottom}V${top + r}Q${x},${top} ${x + r},${top}H${x + width - r}Q${x + width},${top} ${x + width},${top + r}V${bottom}Z`;
  }
  return `M${x},${top}H${x + width}V${bottom - r}Q${x + width},${bottom} ${x + width - r},${bottom}H${x + r}Q${x},${bottom} ${x},${bottom - r}Z`;
}
