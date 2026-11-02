"use client";

import { useMemo } from "react";

import { LineChart } from "@/components/LineChart";
import { StatTile } from "@/components/StatTile";
import { cumulative } from "@/lib/analytics";
import { amount, compact, percent } from "@/lib/format";
import type { FlowPoint, MarketMeta, MarketPoint, YieldPoint } from "@/lib/types";

const pct = (v: number) => percent(v, 2);
const pctAxis = (v: number) => percent(v, v !== 0 && Math.abs(v) < 0.1 ? 1 : 0);
/** Below this share of peak TVL a share-price move says little about yield. */
const MIN_TVL_SHARE = 0.01;

export function YieldTab({
  market,
  daily,
  yields,
  flows,
  peakTvl,
}: {
  market: MarketMeta;
  daily: MarketPoint[];
  yields: YieldPoint[];
  flows: FlowPoint[];
  peakTvl: number;
}) {
  const unit = market.underlying.symbol;

  // Join realized yields onto the market days; hide days with negligible capital.
  const rows = useMemo(() => {
    const byDay = new Map(yields.map((y) => [y.day, y]));
    return daily.map((d) => {
      const y = byDay.get(d.day);
      const meaningful = (d.tvl ?? 0) >= peakTvl * MIN_TVL_SHARE;
      return {
        day: d.day,
        supply_apr: d.supply_apr,
        borrow_apr: d.borrow_apr,
        realized_apy_7d: meaningful ? (y?.realized_apy_7d ?? null) : null,
        realized_apy_30d: meaningful ? (y?.realized_apy_30d ?? null) : null,
        realized_apy_90d: meaningful ? (y?.realized_apy_90d ?? null) : null,
        pass_through: meaningful ? (y?.pass_through ?? null) : null,
      };
    });
  }, [daily, yields, peakTvl]);

  const interest = useMemo(() => cumulative(flows, ["interest"]), [flows]);
  const totalInterest = interest.at(-1)?.interest ?? null;
  const last = rows.at(-1);
  const latest = <K extends keyof (typeof rows)[number]>(key: K) => {
    for (let i = rows.length - 1; i >= 0; i--) {
      const v = rows[i]?.[key];
      if (typeof v === "number") return v;
    }
    return null;
  };

  return (
    <>
      <p className="tab-intro">
        Quoted rates are what the interest-rate model advertises. Realized yield is what an {market.pool.symbol} holder
        actually earned: the annualized growth of the share price over the window, net of any losses. Days with
        under {MIN_TVL_SHARE * 100}% of peak TVL are hidden, as tiny balances make share-price moves meaningless.
      </p>
      <div className="grid grid-5">
        <StatTile label="Realized APY, 30 days" value={percent(latest("realized_apy_30d"))} />
        <StatTile label="Realized APY, 90 days" value={percent(latest("realized_apy_90d"))} />
        <StatTile label="Quoted supply APR" value={percent(last?.supply_apr)} />
        <StatTile label="Interest paid to lenders" value={compact(totalInterest)} unit={unit} note="over the selected range" />
        <StatTile label="Pass-through" value={percent(latest("pass_through"), 0)} note="of borrower interest reaching lenders" />
      </div>

      <div className="grid grid-2 section">
        <div className="card">
          <div className="card-title"><h3>Realized vs quoted yield</h3></div>
          <div className="card-sub">30-day realized APY from the share price, against the quoted supply APR</div>
          <LineChart
            title="Realized vs quoted lender yield"
            data={rows}
            series={[
              { key: "realized_apy_30d", label: "Realized (30d)", color: "var(--series-1)" },
              { key: "supply_apr", label: "Quoted supply APR", color: "var(--series-2)" },
            ]}
            format={pct}
            axisFormat={pctAxis}
          />
        </div>
        <div className="card">
          <div className="card-title"><h3>Interest earned by lenders</h3></div>
          <div className="card-sub">Cumulative interest accrued to {market.pool.symbol} holders, in {unit}</div>
          <LineChart
            title="Cumulative interest earned by lenders"
            data={interest}
            series={[{ key: "interest", label: "Interest", color: "var(--series-1)" }]}
            format={(v) => amount(v, unit)}
            axisFormat={compact}
            area
          />
        </div>
        <div className="card">
          <div className="card-title"><h3>Realized yield by window</h3></div>
          <div className="card-sub">Short windows react fast; long windows show the sustained rate</div>
          <LineChart
            title="Realized APY by window"
            data={rows}
            series={[
              { key: "realized_apy_7d", label: "7 days", color: "var(--series-1)" },
              { key: "realized_apy_30d", label: "30 days", color: "var(--series-2)" },
              { key: "realized_apy_90d", label: "90 days", color: "var(--series-3)" },
            ]}
            format={pct}
            axisFormat={pctAxis}
            zeroBased={false}
          />
        </div>
        <div className="card">
          <div className="card-title"><h3>Pass-through</h3></div>
          <div className="card-sub">Supply APR ÷ (borrow APR × utilization): the borrower interest that reaches lenders</div>
          <LineChart
            title="Pass-through of borrower interest"
            data={rows}
            series={[{ key: "pass_through", label: "Pass-through", color: "var(--series-1)" }]}
            format={(v) => percent(v, 1)}
            axisFormat={(v) => percent(v, 0)}
          />
        </div>
      </div>
    </>
  );
}
