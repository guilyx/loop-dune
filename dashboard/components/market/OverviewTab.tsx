"use client";

import { LineChart } from "@/components/LineChart";
import { StatTile } from "@/components/StatTile";
import { amount, change, compact, day, percent, shortAddress } from "@/lib/format";
import { peak } from "@/lib/insights";
import type { MarketMeta, MarketPoint, VaultPoint } from "@/lib/types";

const pct = (v: number) => percent(v, 2);
const pctAxis = (v: number) => percent(v, v !== 0 && Math.abs(v) < 0.1 ? 1 : 0);

export function OverviewTab({
  market,
  daily,
  vaults,
  full,
}: {
  market: MarketMeta;
  daily: MarketPoint[];
  vaults: Record<string, VaultPoint | undefined>;
  /** the full history is selected: show peaks instead of % change from ~0 */
  full: boolean;
}) {
  const unit = market.underlying.symbol;
  const fmt = (v: number) => amount(v, unit);
  const first = daily[0];
  const last = daily[daily.length - 1];
  const since = first ? `since ${day(first.day)}` : "";
  const top = full ? peak(daily, "tvl") : null;
  const topBorrow = full ? peak(daily, "total_borrowed") : null;
  const peakNote = (p: { value: number; day: string } | null) =>
    p ? `peak ${amount(p.value, unit)} · ${day(p.day)}` : undefined;

  return (
    <>
      <div className="grid grid-5">
        <StatTile
          label="TVL"
          value={compact(last?.tvl)}
          unit={unit}
          note={full ? peakNote(top) : undefined}
          delta={full ? undefined : change(first?.tvl ?? null, last?.tvl ?? null)}
          deltaLabel={since}
        />
        <StatTile
          label="Borrowed"
          value={compact(last?.total_borrowed)}
          unit={unit}
          note={full ? peakNote(topBorrow) : undefined}
          delta={full ? undefined : change(first?.total_borrowed ?? null, last?.total_borrowed ?? null)}
          deltaLabel={since}
        />
        <StatTile label="Utilization" value={percent(last?.utilization, 1)} />
        <StatTile label="Supply APR" value={percent(last?.supply_apr)} />
        <StatTile label="Borrow APR" value={percent(last?.borrow_apr)} />
      </div>

      <div className="grid grid-2 section">
        <div className="card">
          <div className="card-title"><h3>Liquidity</h3></div>
          <div className="card-sub">Lender deposits (TVL) and what vaults borrowed from them, in {unit}</div>
          <LineChart
            title={`${market.name} liquidity`}
            data={daily}
            series={[
              { key: "tvl", label: "TVL", color: "var(--series-1)" },
              { key: "total_borrowed", label: "Borrowed", color: "var(--series-2)" },
            ]}
            format={fmt}
            axisFormat={compact}
          />
        </div>
        <div className="card">
          <div className="card-title"><h3>Rates</h3></div>
          <div className="card-sub">Annualised rates set by the pool&apos;s interest-rate model</div>
          <LineChart
            title={`${market.name} rates`}
            data={daily}
            series={[
              { key: "supply_apr", label: "Supply APR", color: "var(--series-1)" },
              { key: "borrow_apr", label: "Borrow APR", color: "var(--series-2)" },
            ]}
            format={pct}
            axisFormat={pctAxis}
          />
        </div>
        <div className="card">
          <div className="card-title"><h3>Utilization</h3></div>
          <div className="card-sub">Borrowed ÷ TVL</div>
          <LineChart
            title={`${market.name} utilization`}
            data={daily}
            series={[{ key: "utilization", label: "Utilization", color: "var(--series-1)" }]}
            format={pct}
            axisFormat={pctAxis}
            area
          />
        </div>
        <div className="card">
          <div className="card-title"><h3>Collateral and debt</h3></div>
          <div className="card-sub">All vaults, collateral valued at each vault&apos;s oracle, in {unit}</div>
          <LineChart
            title={`${market.name} collateral and debt`}
            data={daily}
            series={[
              { key: "collateral_value", label: "Collateral value", color: "var(--series-1)" },
              { key: "vault_debt", label: "Vault debt", color: "var(--series-2)" },
            ]}
            format={fmt}
            axisFormat={compact}
          />
        </div>
        <div className="card">
          <div className="card-title"><h3>{market.pool.symbol} share price</h3></div>
          <div className="card-sub">{unit} per {market.pool.symbol}; rises as interest accrues to lenders</div>
          <LineChart
            title={`${market.pool.symbol} share price`}
            data={daily}
            series={[{ key: "lp_price", label: `${market.pool.symbol} price`, color: "var(--series-1)" }]}
            format={(v) => v.toFixed(5)}
            axisFormat={(v) => v.toFixed(3)}
            zeroBased={false}
          />
        </div>
        <div className="card">
          <div className="card-title"><h3>Staked and locked</h3></div>
          <div className="card-sub">
            Deposits held by {market.staking?.symbol ?? "the staking vault"} and by the time-lock, in {unit}
          </div>
          <LineChart
            title={`${market.name} staked and locked`}
            data={daily}
            series={[
              { key: "staked_tvl", label: "Staked", color: "var(--series-1)" },
              { key: "locked_tvl", label: "Locked", color: "var(--series-2)" },
            ]}
            format={fmt}
            axisFormat={compact}
          />
        </div>
      </div>

      <section className="section">
        <h2>Vaults</h2>
        <p className="hint">
          Latest state ({last ? day(last.day) : "–"}). Collateral value and debt in {unit}; LTV uses
          each vault&apos;s own oracle.
        </p>
        <div className="card table-wrap">
          <VaultTable market={market} vaults={vaults} />
        </div>
      </section>
    </>
  );
}

function VaultTable({
  market,
  vaults,
}: {
  market: MarketMeta;
  vaults: Record<string, VaultPoint | undefined>;
}) {
  const rows = market.vaults.map((vault) => ({ vault, point: vaults[vault.id] }));
  rows.sort((a, b) => (b.point?.total_debt ?? 0) - (a.point?.total_debt ?? 0));
  return (
    <table className="data">
      <thead>
        <tr>
          <th>Vault</th>
          <th className="num">Collateral</th>
          <th className="num">Spot price</th>
          <th className="num">Collateral value</th>
          <th className="num">Debt</th>
          <th className="num">LTV</th>
          <th className="num">Debt ceiling</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(({ vault, point }) => {
          const flagged = (point?.ltv ?? 0) > 1 && (point?.total_debt ?? 0) > 0;
          return (
            <tr key={vault.id} className={flagged ? "flagged" : undefined}>
              <td>
                <div>{vault.name}</div>
                <div className="muted">
                  <a href={`${market.explorer}/address/${vault.address}`} target="_blank" rel="noreferrer">
                    {shortAddress(vault.address)}
                  </a>
                  {!vault.registered && " · not a credit manager"}
                </div>
                {flagged && (
                  <div className="status status-critical">
                    <span aria-hidden="true">▲</span> Undercollateralised
                  </div>
                )}
                {vault.notes && <div className="muted">{vault.notes}</div>}
              </td>
              <td className="num">{amount(point?.collateral_balance, vault.collateral.symbol)}</td>
              <td className="num">{point?.spot_price == null ? "–" : point.spot_price.toFixed(4)}</td>
              <td className="num">{compact(point?.collateral_value)}</td>
              <td className="num">{compact(point?.total_debt)}</td>
              <td className="num">{percent(point?.ltv, 1)}</td>
              <td className="num">{vault.registered ? compact(point?.debt_ceiling) : "–"}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
