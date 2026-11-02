"use client";

import { LineChart, type ChartSeries } from "@/components/LineChart";
import { percent } from "@/lib/format";

type Row = { day: string } & Record<string, number | null | string>;

const pct = (v: number) => percent(v, 2);
const pctAxis = (v: number) => percent(v, v !== 0 && Math.abs(v) < 0.1 ? 1 : 0);

/** Same-unit (ratio) comparisons across markets - one axis, one chart each. */
export function CrossMarketCharts({
  utilization,
  supplyApr,
  series,
}: {
  utilization: Row[];
  supplyApr: Row[];
  series: ChartSeries[];
}) {
  return (
    <div className="grid grid-2">
      <div className="card">
        <div className="card-title"><h3>Utilization by market</h3></div>
        <div className="card-sub">Borrowed ÷ TVL, end of day</div>
        <LineChart title="Utilization by market" data={utilization} series={series} format={pct} axisFormat={pctAxis} />
      </div>
      <div className="card">
        <div className="card-title"><h3>Supply APR by market</h3></div>
        <div className="card-sub">What lenders earned, end of day</div>
        <LineChart title="Supply APR by market" data={supplyApr} series={series} format={pct} axisFormat={pctAxis} />
      </div>
    </div>
  );
}
