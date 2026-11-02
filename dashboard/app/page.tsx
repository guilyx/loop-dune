import Link from "next/link";

import { CrossMarketCharts } from "@/components/CrossMarketCharts";
import { Sparkline } from "@/components/Sparkline";
import { amount, compact, day, percent } from "@/lib/format";
import { latest, peak, undercollateralised } from "@/lib/insights";
import { getMarket, getMeta } from "@/lib/data";
import type { MarketData } from "@/lib/types";

export const revalidate = 3600;

const SLOTS = ["var(--series-1)", "var(--series-2)", "var(--series-3)", "var(--series-4)"];

export default async function Overview() {
  const meta = await getMeta();
  const entries = await Promise.all(meta.markets.map(async (m) => [m.id, await getMarket(m.id)] as const));
  const data = Object.fromEntries(entries.filter(([, d]) => d !== null)) as Record<string, MarketData>;

  // Colour follows the market (fixed slot order), never its rank.
  const series = meta.markets.map((m, i) => ({ key: m.id, label: m.name, color: SLOTS[i % SLOTS.length]! }));
  const days = [...new Set(Object.values(data).flatMap((d) => d.daily.map((p) => p.day)))].sort();
  const pivot = (key: "utilization" | "supply_apr") => {
    const byDay = new Map(days.map((d) => [d, { day: d } as { day: string } & Record<string, number | null | string>]));
    for (const [id, d] of Object.entries(data)) {
      for (const p of d.daily) byDay.get(p.day)![id] = p[key];
    }
    return [...byDay.values()];
  };

  const flagged = undercollateralised(meta.markets, data);
  const asOf = Object.values(meta.freshness).sort().at(-1);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Loop Protocol, on-chain</h1>
          <p className="lede">
            Every Loop lending market, read straight from contract state on a fixed UTC grid since
            each pool was deployed. The Loop frontend has been sunset; the contracts are still on-chain
            and this dashboard keeps tracking them.
          </p>
        </div>
        <span className="badge">{asOf ? `Data to ${day(asOf)}` : "No data yet"}</span>
      </div>

      <div className="grid grid-4">
        {meta.markets.map((m) => {
          const d = data[m.id];
          const now = d ? latest(d.daily, "tvl") : undefined;
          const top = d ? peak(d.daily) : null;
          const drawdown = top && now?.tvl != null && top.value > 0 ? 1 - now.tvl / top.value : null;
          return (
            <Link key={m.id} href={`/markets/${m.id}`} className="card market-card">
              <div className="card-title">
                <h3>{m.name}</h3>
                <span className="muted" style={{ fontSize: 12 }}>{m.chainName}</span>
              </div>
              <div className="stat-label" style={{ marginTop: 8 }}>TVL</div>
              <div className="stat-value">
                {compact(now?.tvl)}
                <span className="stat-unit">{m.underlying.symbol}</span>
              </div>
              <Sparkline label={`${m.name} TVL trend`} points={(d?.daily ?? []).map((p) => ({ day: p.day, value: p.tvl }))} />
              <div className="rows">
                <span>Peak TVL</span>
                <span>{top ? `${amount(top.value, m.underlying.symbol)}` : "–"}</span>
                <span>Peak date</span>
                <span>{top ? day(top.day) : "–"}</span>
                <span>Below peak</span>
                <span>{percent(drawdown, 1)}</span>
                <span>Utilization</span>
                <span>{percent(now?.utilization, 1)}</span>
                <span>Supply APR</span>
                <span>{percent(now?.supply_apr)}</span>
                <span>Vaults</span>
                <span>{m.vaults.length}</span>
              </div>
            </Link>
          );
        })}
      </div>

      <section className="section">
        <h2>Across markets</h2>
        <p className="hint">Ratios share one axis; amounts are in different tokens, so they stay on each market&apos;s page.</p>
        <CrossMarketCharts utilization={pivot("utilization")} supplyApr={pivot("supply_apr")} series={series} />
      </section>

      <section className="section">
        <h2>Data findings</h2>
        <p className="hint">
          Vault-days where debt exceeded collateral valued at the vault&apos;s own oracle (LTV above 100%).
        </p>
        {flagged.length === 0 ? (
          <div className="card muted">No undercollateralised vault-days in the data.</div>
        ) : (
          <div className="card table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Vault</th>
                  <th>First seen</th>
                  <th className="num">Days</th>
                  <th className="num">Peak debt</th>
                  <th className="num">Collateral then</th>
                  <th className="num">LTV then</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {flagged.map((f) => (
                  <tr key={`${f.market.id}-${f.vaultId}`} className="flagged">
                    <td>
                      <Link href={`/markets/${f.market.id}`}>{f.vaultName}</Link>
                      <div className="muted">{f.market.name}</div>
                    </td>
                    <td>{day(f.firstDay)}</td>
                    <td className="num">{f.days}</td>
                    <td className="num">{amount(f.worst.total_debt, f.market.underlying.symbol)}</td>
                    <td className="num">{amount(f.worst.collateral_balance, f.collateralSymbol)}</td>
                    <td className="num">{percent(f.worst.ltv, 0)}</td>
                    <td>
                      <span className="status status-critical"><span aria-hidden="true">▲</span> Undercollateralised</span>
                    </td>
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
