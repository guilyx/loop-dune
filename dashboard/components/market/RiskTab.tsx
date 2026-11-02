"use client";

import { useMemo, useState } from "react";

import { LineChart } from "@/components/LineChart";
import { StatTile } from "@/components/StatTile";
import { BarChart } from "@/components/charts/BarChart";
import { Heatmap } from "@/components/charts/Heatmap";
import { XYChart } from "@/components/charts/XYChart";
import { stress, stressCurve, stressVaults, topWithOther } from "@/lib/analytics";
import { amount, compact, day, percent } from "@/lib/format";
import type { ConcentrationPoint, MarketMeta, OracleEvent, VaultPoint } from "@/lib/types";

export interface VaultWeek {
  day: string;
  total_debt: number | null;
  capacity_used: number | null;
}

const SLOTS = ["var(--series-1)", "var(--series-2)", "var(--series-3)", "var(--series-4)", "var(--series-5)"];

export function RiskTab({
  market,
  latest,
  weekly,
  concentration,
  oracleEvents,
}: {
  market: MarketMeta;
  latest: Record<string, VaultPoint | undefined>;
  weekly: Record<string, VaultWeek[]>;
  concentration: ConcentrationPoint[];
  oracleEvents: OracleEvent[];
}) {
  const unit = market.underlying.symbol;
  const names = Object.fromEntries(market.vaults.map((v) => [v.id, v.name]));

  // ---- debt composition: top 4 vaults by peak debt, the rest folded into "Other"
  const weeks = useMemo(
    () => [...new Set(Object.values(weekly).flatMap((w) => w.map((p) => p.day)))].sort(),
    [weekly],
  );
  const borrowers = useMemo(
    () => Object.keys(weekly).filter((id) => (weekly[id] ?? []).some((p) => (p.total_debt ?? 0) > 0)),
    [weekly],
  );
  const { keep, other } = useMemo(() => {
    const peakDebt = Object.fromEntries(
      borrowers.map((id) => [id, Math.max(0, ...(weekly[id] ?? []).map((p) => p.total_debt ?? 0))]),
    );
    return topWithOther(peakDebt, 4);
  }, [borrowers, weekly]);
  const debtRows = useMemo(() => {
    const lookup = new Map(
      Object.entries(weekly).flatMap(([id, pts]) => pts.map((p) => [`${id}|${p.day}`, p] as const)),
    );
    return weeks.map((w) => {
      const row: Record<string, number | string | null> = { day: w };
      for (const id of keep) row[id] = lookup.get(`${id}|${w}`)?.total_debt ?? 0;
      if (other.length) row.other = other.reduce((s, id) => s + (lookup.get(`${id}|${w}`)?.total_debt ?? 0), 0);
      return row as { day: string };
    });
  }, [weeks, keep, other, weekly]);
  const debtSeries = [
    ...keep.map((id, i) => ({ key: id, label: names[id] ?? id, color: SLOTS[i]! })),
    ...(other.length ? [{ key: "other", label: `Other (${other.length})`, color: SLOTS[4]! }] : []),
  ];

  // ---- liquidation proximity heatmap
  const capacity = useMemo(() => {
    const m = new Map<string, number | null>();
    for (const [id, pts] of Object.entries(weekly)) for (const p of pts) m.set(`${id}|${p.day}`, p.capacity_used);
    return m;
  }, [weekly]);

  const conc = concentration.at(-1);

  return (
    <>
      <p className="tab-intro">
        A position can be liquidated once its collateral value falls below the vault&apos;s{" "}
        <strong>liquidation ratio</strong> × debt (110% on every Loop vault, a 90.9% max LTV).{" "}
        <strong>Capacity used</strong> = LTV × liquidation ratio, so 100% means liquidatable. All figures are
        vault-wide aggregates at each vault&apos;s own oracle: individual positions can be riskier.
      </p>

      <StressTest market={market} latest={latest} names={names} />

      <div className="grid grid-2 section">
        <div className="card" style={{ gridColumn: "1 / -1" }}>
          <div className="card-title"><h3>Liquidation proximity by vault</h3></div>
          <div className="card-sub">Weekly capacity used for every vault that carried debt in the range</div>
          <Heatmap
            title="Liquidation proximity by vault"
            rows={borrowers.map((id) => ({ id, label: names[id] ?? id }))}
            columns={weeks}
            value={(id, w) => capacity.get(`${id}|${w}`) ?? null}
            format={(v) => percent(v, 0)}
            valueLabel="Capacity used"
          />
        </div>
        <div className="card">
          <div className="card-title"><h3>Debt by vault</h3></div>
          <div className="card-sub">End of each week, in {unit}; smaller vaults folded into Other</div>
          <BarChart
            title="Debt by vault"
            data={debtRows}
            mode="stack"
            series={debtSeries}
            format={(v) => amount(v, unit)}
            axisFormat={compact}
          />
        </div>
        <div className="card">
          <div className="card-title"><h3>Debt concentration</h3></div>
          <div className="card-sub">
            Herfindahl index of debt across vaults: 100% means one vault holds all of it
            {conc ? ` · now ${percent(conc.debt_hhi, 0)}, ${conc.borrowing_vaults ?? 0} borrowing vault(s)` : ""}
          </div>
          <LineChart
            title="Debt concentration (HHI)"
            data={concentration}
            series={[{ key: "debt_hhi", label: "HHI", color: "var(--series-1)" }]}
            format={(v) => percent(v, 0)}
            axisFormat={(v) => percent(v, 0)}
          />
        </div>
      </div>

      <section className="section">
        <h2>Oracle events</h2>
        <p className="hint">Day-over-day collateral price moves of 20% or more, and days an oracle stopped answering.</p>
        {oracleEvents.length === 0 ? (
          <div className="card muted">No oracle events in this range.</div>
        ) : (
          <div className="card table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Vault</th>
                  <th>Day</th>
                  <th>Event</th>
                  <th className="num">Price before</th>
                  <th className="num">Price after</th>
                  <th className="num">Change</th>
                </tr>
              </thead>
              <tbody>
                {oracleEvents.map((e) => (
                  <tr key={`${e.vault}-${e.day}`}>
                    <td>{names[e.vault] ?? e.vault}</td>
                    <td>{day(e.day)}</td>
                    <td>
                      <span className="status status-critical">
                        <span aria-hidden="true">▲</span> {e.kind === "reverted" ? "Oracle stopped answering" : "Large price move"}
                      </span>
                    </td>
                    <td className="num">{e.from === null ? "–" : e.from.toFixed(4)}</td>
                    <td className="num">{e.to === null ? "–" : e.to.toFixed(4)}</td>
                    <td className="num">{e.change === null ? "–" : `${e.change > 0 ? "+" : ""}${percent(e.change, 1)}`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

function StressTest({
  market,
  latest,
  names,
}: {
  market: MarketMeta;
  latest: Record<string, VaultPoint | undefined>;
  names: Record<string, string>;
}) {
  const unit = market.underlying.symbol;
  const [shockPct, setShockPct] = useState(20);
  const vaults = useMemo(() => stressVaults(latest, names), [latest, names]);
  const result = stress(vaults, shockPct / 100);
  const curve = useMemo(() => stressCurve(vaults), [vaults]);
  const totalDebt = vaults.reduce((s, v) => s + v.debt, 0);
  // Vaults with debt we cannot simulate: no oracle price (reverting) or no liquidation ratio.
  const excluded = Object.entries(latest)
    .filter(([id, v]) => v && (v.total_debt ?? 0) > 0 && !vaults.some((s) => s.id === id))
    .map(([id, v]) => ({ id, name: names[id] ?? id, debt: v?.total_debt ?? 0 }));

  return (
    <div className="card">
      <div className="card-title"><h3>Stress test: collateral price shock</h3></div>
      <div className="card-sub">
        Drop every vault&apos;s collateral price at once and see which aggregate positions cross their liquidation ratio.
      </div>
      {vaults.length === 0 ? (
        <p className="empty">No vault carries debt with a working oracle at the latest snapshot.</p>
      ) : (
        <>
          <div className="slider-row">
            <label htmlFor="shock" className="stat-label">
              Collateral price shock
            </label>
            <input
              id="shock"
              type="range"
              min={0}
              max={90}
              step={1}
              value={shockPct}
              onChange={(e) => setShockPct(Number(e.target.value))}
              aria-valuetext={`${shockPct}% price drop`}
            />
            <span className="slider-value">−{shockPct}%</span>
          </div>
          <div className="grid grid-4">
            <StatTile label="Vaults liquidatable" value={`${result.liquidatable.length} / ${vaults.length}`} />
            <StatTile
              label="Debt at risk"
              value={compact(result.debtAtRisk)}
              unit={unit}
              note={totalDebt ? `${percent(result.debtAtRisk / totalDebt, 0)} of vault debt` : undefined}
            />
            <StatTile label="Uncovered debt" value={compact(result.uncovered)} unit={unit} note="debt above shocked collateral value" />
            <StatTile label="Total vault debt" value={compact(totalDebt)} unit={unit} />
          </div>
          <div style={{ marginTop: 16 }}>
            <XYChart
              title="Debt at risk by price shock"
              hover="x"
              layers={[
                { kind: "line", label: "Debt at risk", color: "var(--series-1)", points: curve.map((r) => ({ x: r.shock, y: r.debtAtRisk })) },
                { kind: "line", label: "Uncovered debt", color: "var(--series-2)", points: curve.map((r) => ({ x: r.shock, y: r.uncovered })) },
              ]}
              xLabel="Collateral price shock"
              yLabel={unit}
              xFormat={(v) => `−${percent(v, 0)}`}
              xAxisFormat={(v) => `−${percent(v, 0)}`}
              yFormat={(v) => amount(v, unit)}
              yAxisFormat={compact}
              marker={{ x: shockPct / 100, label: `−${shockPct}%` }}
              height={240}
            />
            <div className="table-wrap" style={{ marginTop: 12 }}>
              <table className="data">
                <thead>
                  <tr>
                    <th>Vault</th>
                    <th className="num">Debt</th>
                    <th className="num">Capacity used</th>
                    <th className="num">Drop to liquidation</th>
                    <th>At −{shockPct}%</th>
                  </tr>
                </thead>
                <tbody>
                  {[...vaults]
                    .sort((a, b) => b.debt - a.debt)
                    .map((v) => {
                      const used = v.debt * v.liquidationRatio / v.collateralValue;
                      const hit = result.liquidatable.some((l) => l.id === v.id);
                      return (
                        <tr key={v.id} className={hit ? "flagged" : undefined}>
                          <td>{v.name}</td>
                          <td className="num">{compact(v.debt)}</td>
                          <td className="num">{percent(used, 0)}</td>
                          <td className="num">{used >= 1 ? "already" : `−${percent(1 - used, 0)}`}</td>
                          <td>
                            {hit ? (
                              <span className="status status-critical"><span aria-hidden="true">▲</span> Liquidatable</span>
                            ) : (
                              <span className="status status-ok"><span aria-hidden="true">●</span> Safe</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                </tbody>
              </table>
            </div>
          </div>
          {excluded.length > 0 && (
            <p className="note">
              <span className="status status-critical">
                <span aria-hidden="true">▲</span> Not simulated:
              </span>{" "}
              {excluded.map((e) => `${e.name} (${amount(e.debt, unit)} of debt)`).join(", ")}: no working oracle
              price, so its collateral cannot be valued.
            </p>
          )}
          <p className="note">
            Aggregate positions at each vault&apos;s oracle: a floor on liquidations, not a forecast. Liquidators also
            receive a {percent(1 - (latest[vaults[0]!.id]?.liquidation_penalty ?? 1), 0)} penalty discount, so recoveries
            can be lower than the collateral value shown.
          </p>
        </>
      )}
    </div>
  );
}
