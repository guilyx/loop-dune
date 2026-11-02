import "server-only";

import { cache } from "react";

import { PostgresSource } from "@/lib/data/postgres";
import { StaticSource } from "@/lib/data/static";
import type { DataSource, MarketData, Meta } from "@/lib/types";

let source: DataSource | undefined;

/** Live Postgres when DATABASE_URL is set, otherwise the bundled static snapshot. */
export function dataSource(): DataSource {
  source ??= process.env.DATABASE_URL
    ? new PostgresSource(process.env.DATABASE_URL)
    : new StaticSource();
  return source;
}

export const getMeta = cache((): Promise<Meta> => dataSource().meta());

export const getMarket = cache((id: string): Promise<MarketData | null> => dataSource().market(id));
