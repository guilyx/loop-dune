import { NextResponse } from "next/server";

import { getMeta } from "@/lib/data";

export const revalidate = 3600;

/** Catalogue: markets, vaults, series and data freshness. */
export async function GET() {
  return NextResponse.json(await getMeta(), {
    headers: { "Cache-Control": "public, s-maxage=3600, stale-while-revalidate=86400" },
  });
}
