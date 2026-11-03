import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import { Nav } from "@/components/Nav";
import { ThemeToggle } from "@/components/ThemeToggle";
import { getMeta } from "@/lib/data";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Loop Analytics", template: "%s · Loop Analytics" },
  description:
    "Hourly on-chain state of every Loop Protocol lending market: liquidity, rates, vaults and collateral.",
};

export default async function RootLayout({ children }: { children: ReactNode }) {
  const meta = await getMeta();
  return (
    <html lang="en">
      <body>
        <div className="shell">
          <header className="topbar">
            <Link href="/" className="brand">
              <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">
                <circle cx="9" cy="12" r="6" fill="none" stroke="var(--series-1)" strokeWidth="2.5" />
                <circle cx="15" cy="12" r="6" fill="none" stroke="var(--series-2)" strokeWidth="2.5" />
              </svg>
              Loop Analytics
            </Link>
            <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
              <Nav markets={meta.markets.map((m) => ({ id: m.id, label: m.name.replace(/^Loop /, "") }))} />
              <ThemeToggle />
            </div>
          </header>
          <main>{children}</main>
          <footer className="footer">
            Data read directly from contract state by{" "}
            <a href="https://github.com/guilyx/loopscan">loop-indexer</a> ·{" "}
            {meta.source === "postgres" ? "live database" : "static snapshot"} · generated{" "}
            {meta.generatedAt.slice(0, 10)}
          </footer>
        </div>
      </body>
    </html>
  );
}
