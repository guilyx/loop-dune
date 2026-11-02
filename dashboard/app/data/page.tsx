import type { Metadata } from "next";

import { day } from "@/lib/format";
import { getMeta } from "@/lib/data";

export const metadata: Metadata = { title: "Data" };
export const revalidate = 3600;

const VIEWS: [string, string][] = [
  ["loop.observations", "Fact table: one row per (series, hour) with the exact uint256 (raw) and the scaled value."],
  ["loop.market_hourly", "One row per market and hour: TVL, borrowed, utilization, APRs, share prices, staked/locked, vault totals."],
  ["loop.vault_hourly", "One row per vault and hour: collateral, oracle price, collateral value, debt, ceiling, LTV."],
  ["loop.market_daily / loop.vault_daily", "End-of-day versions of the two views above."],
  ["loop.series", "How every value is read: contract, function, arguments, decimals, unit."],
  ["loop.chain_freshness", "Latest snapshot and lag per chain; what the health check alerts on."],
];

export default async function DataPage() {
  const meta = await getMeta();
  const namespace = process.env.NEXT_PUBLIC_DUNE_NAMESPACE || "<namespace>";
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Data</h1>
          <p className="lede">
            Everything on this site comes from {meta.series.length} on-chain series, sampled on an hourly UTC
            grid and stored in Postgres. The same data is published to Dune and served as JSON and CSV.
          </p>
        </div>
      </div>

      <div className="grid grid-2">
        <div className="card">
          <h3>Dune</h3>
          <p className="card-sub">Public tables, appended after every indexer run.</p>
          <pre className="code">{`select *
from dune.${namespace}.loop_observations
where market_id = 'eth'
  and metric = 'expected_liquidity'
order by ts desc`}</pre>
          <p className="muted" style={{ fontSize: 13 }}>
            Also <code>loop_markets</code>, <code>loop_vaults</code>, <code>loop_series</code>. Ready-made
            queries live in <code>dune/queries/</code> in the repository.
          </p>
        </div>
        <div className="card">
          <h3>HTTP</h3>
          <p className="card-sub">End-of-day series, cached for an hour.</p>
          <pre className="code">{`GET /api/markets             # catalogue + freshness
GET /api/markets/eth         # daily market + vault series
GET /api/markets/eth?format=csv`}</pre>
          <p className="muted" style={{ fontSize: 13 }}>
            Source: {meta.source === "postgres" ? "live Postgres" : "static snapshot"} · freshness{" "}
            {Object.entries(meta.freshness)
              .map(([chain, ts]) => `chain ${chain}: ${day(ts)}`)
              .join(", ") || "–"}
          </p>
        </div>
      </div>

      <section className="section">
        <h2>Postgres views</h2>
        <p className="hint">Schema <code>loop</code>. Grant the <code>loop_reader</code> role for read-only access.</p>
        <div className="card table-wrap">
          <table className="data">
            <tbody>
              {VIEWS.map(([name, text]) => (
                <tr key={name}>
                  <td style={{ whiteSpace: "nowrap" }}><code>{name}</code></td>
                  <td>{text}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="section">
        <h2>Series catalogue</h2>
        <p className="hint">Every value the indexer reads, and exactly how.</p>
        <div className="card table-wrap" style={{ maxHeight: 520, overflow: "auto", padding: 0 }}>
          <table className="data">
            <thead>
              <tr>
                <th>Series</th>
                <th>Call</th>
                <th>Unit</th>
                <th>Description</th>
              </tr>
            </thead>
            <tbody>
              {meta.series.map((s) => (
                <tr key={s.series_id}>
                  <td style={{ whiteSpace: "nowrap" }}><code>{s.series_id}</code></td>
                  <td style={{ whiteSpace: "nowrap" }}><code>{s.call}</code></td>
                  <td>{s.unit}</td>
                  <td className="muted">{s.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
