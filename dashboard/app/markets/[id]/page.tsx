import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { MarketView } from "@/components/MarketView";
import { weeklyLast } from "@/lib/analytics";
import { shortAddress } from "@/lib/format";
import { getMarket, getMeta } from "@/lib/data";

export const revalidate = 3600;

type Params = { params: Promise<{ id: string }> };

export async function generateStaticParams() {
  const meta = await getMeta();
  return meta.markets.map((m) => ({ id: m.id }));
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { id } = await params;
  const market = (await getMeta()).markets.find((m) => m.id === id);
  return { title: market ? market.name : "Market not found" };
}

export default async function MarketPage({ params }: Params) {
  const { id } = await params;
  const meta = await getMeta();
  const market = meta.markets.find((m) => m.id === id);
  const data = market ? await getMarket(id) : null;
  if (!market || !data) notFound();

  const link = (address: string, label: string) => (
    <a href={`${market.explorer}/address/${address}`} target="_blank" rel="noreferrer" title={address}>
      {label} {shortAddress(address)}
    </a>
  );

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{market.name}</h1>
          <p className="lede">
            {market.underlying.symbol} lending pool on {market.chainName}. Lenders deposit{" "}
            {market.underlying.symbol} for {market.pool.symbol}; {market.vaults.length} CDP vault
            {market.vaults.length === 1 ? "" : "s"} borrow against yield-bearing collateral.
          </p>
          <p className="meta-line" style={{ marginTop: 6, display: "flex", gap: 14, flexWrap: "wrap" }}>
            {link(market.pool.address, market.pool.symbol)}
            {market.staking && link(market.staking.address, market.staking.symbol)}
            <a href={`/api/markets/${market.id}?format=csv`}>Download CSV</a>
            <a href={`/api/markets/${market.id}`}>JSON</a>
          </p>
        </div>
      </div>
      <MarketView
        market={market}
        daily={data.daily}
        vaults={Object.fromEntries(
          market.vaults.map((v) => {
            const points = data.vaults[v.id] ?? [];
            return [v.id, points[points.length - 1]];
          }),
        )}
        weekly={Object.fromEntries(
          market.vaults.map((v) => [
            v.id,
            weeklyLast(data.vaults[v.id] ?? []).map((p) => ({
              day: p.day,
              total_debt: p.total_debt,
              capacity_used: p.capacity_used,
            })),
          ]),
        )}
        analytics={data.analytics}
      />
    </>
  );
}
