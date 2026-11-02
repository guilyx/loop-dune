"use client";

import { useEffect, useMemo, useState } from "react";

import { Tabs } from "@/components/Tabs";
import { FlowsTab } from "@/components/market/FlowsTab";
import { OverviewTab } from "@/components/market/OverviewTab";
import { RateModelTab } from "@/components/market/RateModelTab";
import { RiskTab, type VaultWeek } from "@/components/market/RiskTab";
import { YieldTab } from "@/components/market/YieldTab";
import { day } from "@/lib/format";
import { RANGES, type RangeId, peak } from "@/lib/insights";
import type { MarketAnalytics, MarketMeta, MarketPoint, VaultPoint } from "@/lib/types";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "yield", label: "Yield" },
  { id: "flows", label: "Flows" },
  { id: "risk", label: "Risk" },
  { id: "rates", label: "Rate model" },
] as const;
type TabId = (typeof TABS)[number]["id"];

const EMPTY: MarketAnalytics = { yield: [], flows: [], concentration: [], oracleEvents: [] };

/** First day kept by a range ending at the latest day (ranges never move the end). */
function cutoff(lastDay: string | undefined, days: number): string {
  if (!lastDay || !Number.isFinite(days)) return "";
  return new Date(Date.parse(lastDay) - days * 86_400_000).toISOString().slice(0, 10);
}

export function MarketView({
  market,
  daily: allDays,
  vaults,
  weekly: allWeeks,
  analytics = EMPTY,
}: {
  market: MarketMeta;
  daily: MarketPoint[];
  /** Latest state of each vault (ranges only move the start date, never the end). */
  vaults: Record<string, VaultPoint | undefined>;
  /** End-of-week debt and capacity used per vault. */
  weekly: Record<string, VaultWeek[]>;
  analytics?: MarketAnalytics;
}) {
  const [range, setRange] = useState<RangeId>("all");
  const [tab, setTab] = useState<TabId>("overview");

  // Deep links (/markets/eth#risk) and back/forward between tabs.
  useEffect(() => {
    const sync = () => {
      const fromHash = window.location.hash.slice(1);
      setTab(TABS.some((t) => t.id === fromHash) ? (fromHash as TabId) : "overview");
    };
    sync();
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);
  function selectTab(id: TabId) {
    setTab(id);
    window.history.pushState(null, "", `#${id}`);
  }

  const days = RANGES.find((r) => r.id === range)?.days ?? Infinity;
  const since = cutoff(allDays.at(-1)?.day, days);
  const keep = <T extends { day: string }>(rows: T[]) => (since ? rows.filter((r) => r.day >= since) : rows);

  const daily = useMemo(() => keep(allDays), [allDays, since]);
  const scoped = useMemo(
    () => ({
      yields: keep(analytics.yield),
      flows: keep(analytics.flows),
      concentration: keep(analytics.concentration),
      oracleEvents: keep(analytics.oracleEvents),
      weekly: Object.fromEntries(Object.entries(allWeeks).map(([id, w]) => [id, keep(w)])),
    }),
    [analytics, allWeeks, since],
  );
  const peakTvl = useMemo(() => peak(allDays, "tvl")?.value ?? 0, [allDays]);
  const first = daily[0];
  const last = daily[daily.length - 1];

  return (
    <>
      <Tabs tabs={[...TABS]} active={tab} onChange={selectTab} label={`${market.name} analytics`} />
      <div className="filters" role="group" aria-label="Date range">
        <div className="seg">
          {RANGES.map((r) => (
            <button key={r.id} type="button" aria-pressed={range === r.id} onClick={() => setRange(r.id)}>
              {r.label}
            </button>
          ))}
        </div>
        <span className="meta-line">
          {first && last ? `${day(first.day)} – ${day(last.day)} · end-of-day values` : ""}
        </span>
      </div>

      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} style={{ marginTop: 16 }}>
        {tab === "overview" && <OverviewTab market={market} daily={daily} vaults={vaults} full={range === "all"} />}
        {tab === "yield" && (
          <YieldTab market={market} daily={daily} yields={scoped.yields} flows={scoped.flows} peakTvl={peakTvl} />
        )}
        {tab === "flows" && <FlowsTab market={market} flows={scoped.flows} />}
        {tab === "risk" && (
          <RiskTab
            market={market}
            latest={vaults}
            weekly={scoped.weekly}
            concentration={scoped.concentration}
            oracleEvents={scoped.oracleEvents}
          />
        )}
        {tab === "rates" && <RateModelTab market={market} daily={daily} />}
      </div>
    </>
  );
}
