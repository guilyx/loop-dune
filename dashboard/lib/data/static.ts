import { readFile } from "node:fs/promises";
import path from "node:path";

import type { DataSource, MarketData, Meta } from "@/lib/types";

/** Reads the JSON snapshot written by `loop-indexer export static`. */
export class StaticSource implements DataSource {
  constructor(private readonly dir = path.join(process.cwd(), "data")) {}

  private async read<T>(file: string): Promise<T> {
    return JSON.parse(await readFile(path.join(this.dir, file), "utf8")) as T;
  }

  async meta(): Promise<Meta> {
    const meta = await this.read<Omit<Meta, "source">>("meta.json");
    return { ...meta, source: "static" };
  }

  async market(id: string): Promise<MarketData | null> {
    if (!/^[a-z0-9-]+$/.test(id)) return null;
    try {
      return await this.read<MarketData>(`${id}.json`);
    } catch {
      return null;
    }
  }
}
