"use client";

import { useMemo } from "react";

import { StatTile } from "@/components/StatTile";
import { BarChart } from "@/components/charts/BarChart";
import { XYChart } from "@/components/charts/XYChart";
import { binnedMedian, histogram, median } from "@/lib/analytics";
import { day, percent } from "@/lib/format";
import type { MarketMeta, MarketPoint } from "@/lib/types";

const RECENCY = ["var(--ord-1)", "var(--ord-2)", "var(--ord-3)", "var(--ord-4)", "var(--ord-5)"];

export function RateModelTab({ market, daily }: { market: MarketMeta; daily: MarketPoint[] }) {
  const points = useMemo(
    () =>
      daily
        .filter((d) => (d.tvl ?? 0) > 0 && d.utilization !== null && d.borrow_apr !== null)
        .map((d) => ({ day: d.day, u: d.utilization as number, borrow: d.borrow_apr as number, supply: d.supply_apr ?? 0 })),
    [daily],
  );
  const curve = useMemo(() => binnedMedian(points.map((p) => ({ x: p.u, y: p.borrow })), 0.05), [points]);
  const hist = useMemo(
    () =>
      histogram(
        points.map((p) => p.u),
        0.1,
        1,
      ).map((b) => ({ day: String(b.from), label: `${Math.round(b.from * 100)}–${Math.round(b.to * 100)}%`, share: b.share })),
    [points],
  );

  // Colour each day by recency (ordinal ramp, older lighter in light mode).
  const dots = points.map((p, i) => ({
    x: p.u,
    y: p.borrow,
    color: RECENCY[Math.min(4, Math.floor((i / Math.max(1, points.length)) * 5))],
    title: day(p.day),
  }));
  const high = points.filter((p) => p.u >= 0.9);
  const low = points.filter((p) => p.u < 0.5);

  return (
    <>
      <p className="tab-intro">
        Each day&apos;s utilization against the borrow rate the pool charged: the interest-rate model as it was actually
        applied. Rates normally climb gently, then steeply past the model&apos;s kink; vertical clusters or jumps show the
        model&apos;s parameters being changed.
      </p>
      <div className="grid grid-4">
        <StatTile label="Median utilization" value={percent(median(points.map((p) => p.u)), 0)} />
        <StatTile
          label="Days above 90% utilization"
          value={points.length ? percent(high.length / points.length, 0) : "–"}
          note={`${high.length} of ${points.length} days`}
        />
        <StatTile label="Median borrow APR below 50% util." value={percent(median(low.map((p) => p.borrow)))} />
        <StatTile label="Median borrow APR above 90% util." value={percent(median(high.map((p) => p.borrow)))} />
      </div>

      <div className="grid grid-2 section">
        <div className="card">
          <div className="card-title"><h3>Utilization vs borrow rate</h3></div>
          <div className="card-sub">One dot per day, coloured older → newer; the line is the median per 5-point bucket</div>
          <XYChart
            title={`${market.name} utilization vs borrow APR`}
            layers={[
              { kind: "dots", label: "Daily observation", color: "var(--ord-3)", points: dots },
              { kind: "line", label: "Median by utilization", color: "var(--series-2)", points: curve.map((c) => ({ x: c.x, y: c.y })) },
            ]}
            legend={[
              ...RECENCY.map((c, i) => ({ label: i === 0 ? "Older" : i === RECENCY.length - 1 ? "Newer" : "", color: c, key: "dot" as const })).filter((l) => l.label),
              { label: "Median by utilization", color: "var(--series-2)", key: "line" as const },
            ]}
            xLabel="Utilization"
            yLabel="Borrow APR"
            xFormat={(v) => percent(v, 1)}
            xAxisFormat={(v) => percent(v, 0)}
            yFormat={(v) => percent(v, 2)}
            yAxisFormat={(v) => percent(v, 0)}
            xMin={0}
            height={300}
          />
        </div>
        <div className="card">
          <div className="card-title"><h3>How often the pool ran hot</h3></div>
          <div className="card-sub">Share of days in each utilization bucket</div>
          <BarChart
            title="Utilization distribution"
            data={hist}
            mode="stack"
            x="band"
            series={[{ key: "share", label: "Share of days", color: "var(--series-1)" }]}
            format={(v) => percent(v, 0)}
            height={300}
          />
        </div>
      </div>
    </>
  );
}
