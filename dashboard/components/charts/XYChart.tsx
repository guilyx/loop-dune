"use client";

import { type KeyboardEvent, type PointerEvent, useMemo, useState } from "react";

import { Legend, type LegendKey, TableView, Tooltip, useWidth } from "@/components/charts/kit";
import { linear, nearestIndex, niceTicks } from "@/lib/scale";

export interface XYPoint {
  x: number;
  y: number;
  /** per-point colour (dots), e.g. a sequential step for recency */
  color?: string;
  /** shown as the tooltip title for this point */
  title?: string;
}

export interface XYLayer {
  kind: "dots" | "line";
  label: string;
  color: string;
  points: XYPoint[];
}

interface Props {
  title: string;
  layers: XYLayer[];
  xLabel: string;
  yLabel: string;
  xFormat: (v: number) => string;
  yFormat: (v: number) => string;
  xAxisFormat?: (v: number) => string;
  yAxisFormat?: (v: number) => string;
  /**
   * "nearest": tooltip for the dot closest to the pointer (scatter).
   * "x": crosshair snapping to x, listing every line at that x (curves).
   */
  hover?: "nearest" | "x";
  /** vertical reference line, e.g. the simulator's current shock */
  marker?: { x: number; label: string };
  legend?: { label: string; color: string; key?: LegendKey }[];
  height?: number;
  xMin?: number;
}

const MARGIN = { top: 10, right: 16, bottom: 40 };
const HIT_RADIUS = 28;

export function XYChart({
  title,
  layers,
  xLabel,
  yLabel,
  xFormat,
  yFormat,
  xAxisFormat = xFormat,
  yAxisFormat = yFormat,
  hover = "nearest",
  marker,
  legend,
  height = 260,
  xMin,
}: Props) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [active, setActive] = useState<number | null>(null);

  const all = useMemo(() => layers.flatMap((l) => l.points), [layers]);
  const domain = useMemo(() => {
    if (all.length === 0) return null;
    const xs = all.map((p) => p.x);
    const ys = all.map((p) => p.y);
    const xt = niceTicks(xMin ?? Math.min(0, ...xs), Math.max(...xs), 5);
    const yt = niceTicks(Math.min(0, ...ys), Math.max(...ys), 4);
    const left = Math.max(...yt.map((t) => yAxisFormat(t).length)) * 6.6 + 12;
    return { xt, yt, left };
  }, [all, xMin, yAxisFormat]);

  // Hover targets: dots for "nearest", the first line's x grid for "x".
  const targets = useMemo(() => {
    if (hover === "x") {
      const line = layers.find((l) => l.kind === "line");
      return (line?.points ?? []).map((p) => ({ ...p, layer: line as XYLayer }));
    }
    return layers
      .filter((l) => l.kind === "dots")
      .flatMap((l) => l.points.map((p) => ({ ...p, layer: l })))
      .sort((a, b) => a.x - b.x);
  }, [layers, hover]);

  if (!domain) {
    return (
      <div className="chart" ref={ref} style={{ minHeight: height }}>
        <p className="empty">No data in this range.</p>
      </div>
    );
  }

  const { xt, yt, left } = domain;
  const right = Math.max(left + 40, width - MARGIN.right);
  const x = linear([xt[0] as number, xt[xt.length - 1] as number], [left, right]);
  const y = linear([yt[0] as number, yt[yt.length - 1] as number], [height - MARGIN.bottom, MARGIN.top]);

  function pick(event: PointerEvent<SVGRectElement>) {
    const box = event.currentTarget.getBoundingClientRect();
    const px = left + event.clientX - box.left;
    const py = MARGIN.top + event.clientY - box.top;
    if (hover === "x") {
      const value = x.domain[0] + ((px - left) / (right - left)) * (x.domain[1] - x.domain[0]);
      setActive(nearestIndex(targets.map((t) => t.x), value));
      return;
    }
    let best = -1;
    let bestD = HIT_RADIUS;
    targets.forEach((t, i) => {
      const d = Math.hypot(x(t.x) - px, y(t.y) - py);
      if (d < bestD) {
        best = i;
        bestD = d;
      }
    });
    setActive(best >= 0 ? best : null);
  }
  function keyboard(event: KeyboardEvent<SVGRectElement>) {
    const last = targets.length - 1;
    const at = active ?? 0;
    const next =
      event.key === "ArrowLeft" ? Math.max(0, at - 1)
      : event.key === "ArrowRight" ? Math.min(last, at + 1)
      : event.key === "Home" ? 0
      : event.key === "End" ? last
      : null;
    if (next !== null) {
      event.preventDefault();
      setActive(next);
    } else if (event.key === "Escape") setActive(null);
  }

  const target = active === null ? undefined : targets[active];
  const lines = layers.filter((l) => l.kind === "line");
  const tooltipRows = target
    ? hover === "x"
      ? lines.map((l) => {
          const p = l.points[nearestIndex(l.points.map((q) => q.x), target.x)];
          return { label: l.label, value: p ? yFormat(p.y) : "–", color: l.color };
        })
      : [
          { label: yLabel, value: yFormat(target.y), color: target.color ?? target.layer.color },
          { label: xLabel, value: xFormat(target.x) },
        ]
    : [];

  const tableLayers = hover === "x" ? lines : layers.filter((l) => l.kind === "dots");
  const tableHead = hover === "x" ? [xLabel, ...lines.map((l) => l.label)] : ["Point", xLabel, yLabel];
  const tableRows =
    hover === "x"
      ? (lines[0]?.points ?? []).map((p, i) => [xFormat(p.x), ...lines.map((l) => (l.points[i] ? yFormat(l.points[i].y) : "–"))])
      : tableLayers.flatMap((l) => l.points.map((p) => [p.title ?? l.label, xFormat(p.x), yFormat(p.y)]));

  return (
    <div className="chart" ref={ref} style={{ minHeight: height }}>
      <Legend
        items={
          legend ??
          layers.map((l) => ({ label: l.label, color: l.color, key: l.kind === "line" ? ("line" as const) : ("dot" as const) }))
        }
      />
      {width > 0 && (
        <svg width={width} height={height} role="img" aria-label={`${title}. Use the table view for exact values.`}>
          {yt.map((t) => (
            <g key={`y${t}`}>
              <line x1={left} x2={right} y1={y(t)} y2={y(t)} stroke="var(--grid)" strokeWidth={1} shapeRendering="crispEdges" />
              <text className="axis-text" x={left - 8} y={y(t)} dy="0.32em" textAnchor="end">
                {yAxisFormat(t)}
              </text>
            </g>
          ))}
          {xt.map((t) => (
            <text key={`x${t}`} className="axis-text" x={x(t)} y={height - MARGIN.bottom + 16} textAnchor="middle">
              {xAxisFormat(t)}
            </text>
          ))}
          <line x1={left} x2={right} y1={y(Math.max(0, yt[0] as number))} y2={y(Math.max(0, yt[0] as number))} stroke="var(--baseline)" strokeWidth={1} shapeRendering="crispEdges" />
          <text className="axis-text" x={(left + right) / 2} y={height - 4} textAnchor="middle">
            {xLabel}
          </text>
          {marker && (
            <g>
              <line x1={x(marker.x)} x2={x(marker.x)} y1={MARGIN.top} y2={height - MARGIN.bottom} stroke="var(--text-secondary)" strokeWidth={1} />
              <text className="end-label" x={x(marker.x) + 6} y={MARGIN.top + 10}>
                {marker.label}
              </text>
            </g>
          )}
          {layers.map((l) =>
            l.kind === "dots" ? (
              <g key={l.label}>
                {l.points.map((p, i) => (
                  <circle key={i} cx={x(p.x)} cy={y(p.y)} r={3.5} fill={p.color ?? l.color} stroke="var(--surface-1)" strokeWidth={1} opacity={0.9} />
                ))}
              </g>
            ) : (
              <path
                key={l.label}
                d={l.points.map((p, i) => `${i ? "L" : "M"}${x(p.x).toFixed(1)},${y(p.y).toFixed(1)}`).join("")}
                fill="none"
                stroke={l.color}
                strokeWidth={2}
                strokeLinejoin="round"
                strokeLinecap="round"
              />
            ),
          )}
          {target && hover === "x" && (
            <g pointerEvents="none">
              <line x1={x(target.x)} x2={x(target.x)} y1={MARGIN.top} y2={height - MARGIN.bottom} stroke="var(--baseline)" strokeWidth={1} />
              {lines.map((l) => {
                const p = l.points[nearestIndex(l.points.map((q) => q.x), target.x)];
                return p ? <circle key={l.label} cx={x(p.x)} cy={y(p.y)} r={4} fill={l.color} stroke="var(--surface-1)" strokeWidth={2} /> : null;
              })}
            </g>
          )}
          {target && hover === "nearest" && (
            <circle cx={x(target.x)} cy={y(target.y)} r={6} fill="none" stroke="var(--text-primary)" strokeWidth={1.5} pointerEvents="none" />
          )}
          <rect
            className="chart-plot"
            x={left}
            y={MARGIN.top}
            width={Math.max(0, right - left)}
            height={height - MARGIN.top - MARGIN.bottom}
            fill="transparent"
            tabIndex={0}
            aria-label={`${title}: use arrow keys to move between points`}
            onPointerMove={pick}
            onPointerDown={pick}
            onPointerLeave={() => setActive(null)}
            onKeyDown={keyboard}
            onBlur={() => setActive(null)}
          />
        </svg>
      )}
      {target && (
        <Tooltip
          x={x(target.x)}
          y={MARGIN.top + 28}
          width={width}
          title={hover === "x" ? `${xLabel}: ${xFormat(target.x)}` : (target.title ?? target.layer.label)}
          rows={tooltipRows}
        />
      )}
      <TableView head={tableHead} rows={tableRows} />
    </div>
  );
}
