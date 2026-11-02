"use client";

import { useMemo } from "react";

import { LineChart } from "@/components/LineChart";
import { StatTile } from "@/components/StatTile";
import { BarChart } from "@/components/charts/BarChart";
import { cumulative, weeklySum } from "@/lib/analytics";
import { amount, compact, day } from "@/lib/format";
import type { FlowPoint, MarketMeta } from "@/lib/types";

export function FlowsTab({ market, flows }: { market: MarketMeta; flows: FlowPoint[] }) {
  const unit = market.underlying.symbol;
  const fmt = (v: number) => amount(v, unit);

  const weekly = useMemo(
    () => weeklySum(flows, ["net_flow", "interest", "borrow_change", "tvl_change"]),
    [flows],
  );
  const running = useMemo(() => cumulative(flows, ["net_flow", "interest"]), [flows]);

  const totals = running.at(-1);
  const extremes = weekly.reduce<{ in?: (typeof weekly)[number]; out?: (typeof weekly)[number] }>(
    (acc, w) => {
      const v = w.net_flow ?? 0;
      if (v > (acc.in?.net_flow ?? 0)) acc.in = w;
      if (v < (acc.out?.net_flow ?? 0)) acc.out = w;
      return acc;
    },
    {},
  );

  return (
    <>
      <p className="tab-intro">
        Every day&apos;s change in TVL splits exactly into <strong>interest</strong> accrued to existing{" "}
        {market.pool.symbol} and <strong>net deposits</strong> (shares minted minus shares burned). That separates
        money arriving or leaving from the pool simply earning yield.
      </p>
      <div className="grid grid-4">
        <StatTile label="Net deposits" value={compact(totals?.net_flow)} unit={unit} note="over the selected range" />
        <StatTile label="Interest accrued" value={compact(totals?.interest)} unit={unit} note="over the selected range" />
        <StatTile
          label="Largest weekly inflow"
          value={compact(extremes.in?.net_flow)}
          unit={unit}
          note={extremes.in ? `week of ${day(extremes.in.day)}` : undefined}
        />
        <StatTile
          label="Largest weekly outflow"
          value={compact(extremes.out?.net_flow)}
          unit={unit}
          note={extremes.out ? `week of ${day(extremes.out.day)}` : undefined}
        />
      </div>

      <div className="grid grid-2 section">
        <div className="card">
          <div className="card-title"><h3>Net deposits per week</h3></div>
          <div className="card-sub">Deposits minus withdrawals, in {unit}</div>
          <BarChart
            title="Net deposits per week"
            data={weekly}
            mode="diverging"
            series={[{ key: "net_flow", label: "Net deposits", color: "var(--div-pos)" }]}
            signLabels={["Deposits", "Withdrawals"]}
            format={fmt}
            axisFormat={compact}
          />
        </div>
        <div className="card">
          <div className="card-title"><h3>Net borrowing per week</h3></div>
          <div className="card-sub">New borrowing minus repayments, in {unit}</div>
          <BarChart
            title="Net borrowing per week"
            data={weekly}
            mode="diverging"
            series={[{ key: "borrow_change", label: "Net borrowing", color: "var(--div-pos)" }]}
            signLabels={["Borrowed", "Repaid"]}
            format={fmt}
            axisFormat={compact}
          />
        </div>
        <div className="card" style={{ gridColumn: "1 / -1" }}>
          <div className="card-title"><h3>What moved TVL</h3></div>
          <div className="card-sub">Cumulative since the start of the range, in {unit}</div>
          <LineChart
            title="Cumulative net deposits and interest"
            data={running}
            series={[
              { key: "net_flow", label: "Net deposits", color: "var(--series-1)" },
              { key: "interest", label: "Interest", color: "var(--series-2)" },
            ]}
            format={fmt}
            axisFormat={compact}
            zeroBased={false}
          />
        </div>
      </div>
    </>
  );
}
