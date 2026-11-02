import { NextResponse } from "next/server";

import { getMarket } from "@/lib/data";
import type { MarketPoint } from "@/lib/types";

export const revalidate = 3600;

const COLUMNS: (keyof MarketPoint)[] = [
  "day", "tvl", "available_liquidity", "total_borrowed", "utilization", "borrow_apr",
  "supply_apr", "lp_supply", "lp_price", "slp_supply", "slp_price", "staked_tvl", "locked_tvl",
  "collateral_value", "vault_debt", "active_vaults",
];

/** End-of-day market and vault series. `?format=csv` returns the market rows as CSV. */
export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const data = await getMarket(id);
  if (!data) return NextResponse.json({ error: `unknown market ${id}` }, { status: 404 });
  const headers = { "Cache-Control": "public, s-maxage=3600, stale-while-revalidate=86400" };

  if (new URL(request.url).searchParams.get("format") === "csv") {
    const lines = [COLUMNS.join(",")];
    for (const row of data.daily) lines.push(COLUMNS.map((c) => row[c] ?? "").join(","));
    return new NextResponse(`${lines.join("\n")}\n`, {
      headers: {
        ...headers,
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": `attachment; filename="loop-${id}-daily.csv"`,
      },
    });
  }
  return NextResponse.json(data, { headers });
}
