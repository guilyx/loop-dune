"""Export end-of-day aggregates as static JSON for the dashboard's no-database mode.

The JSON shapes match what the dashboard's Postgres data source returns, so the
dashboard can be deployed (or opened locally) without any database at all.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from loop_indexer.registry import Market, Registry
from loop_indexer.storage.store import Store

MARKET_COLUMNS = (
    "tvl", "available_liquidity", "total_borrowed", "utilization", "borrow_apr", "supply_apr",
    "lp_supply", "lp_price", "slp_supply", "slp_price", "staked_tvl", "locked_tvl",
    "collateral_value", "vault_debt", "active_vaults",
)  # fmt: skip
VAULT_COLUMNS = (
    "collateral_balance", "spot_price", "collateral_value", "total_debt", "debt_ceiling",
    "pool_borrowed", "ltv", "liquidation_ratio", "liquidation_penalty", "max_ltv",
    "capacity_used", "drop_to_liquidation",
)  # fmt: skip
# Analytics views exported per market: (view, columns).
ANALYTICS: dict[str, tuple[str, tuple[str, ...]]] = {
    "yield": (
        "loop.market_yield_daily",
        ("realized_apy_7d", "realized_apy_30d", "realized_apy_90d", "pass_through"),
    ),
    "flows": (
        "loop.market_flows_daily",
        ("tvl_change", "interest", "net_flow", "borrow_change"),
    ),
    "concentration": (
        "loop.market_concentration_daily",
        ("debt_hhi", "top_vault_share", "borrowing_vaults"),
    ),
}
#: Day-over-day oracle moves at least this large are reported as events.
ORACLE_MOVE_THRESHOLD = 0.2


def _num(value: Any) -> float | int | None:
    if value is None:
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    if number.is_integer() and abs(number) < 2**53:
        return int(number)
    return float(f"{number:.6g}")


def _day(value: datetime | date) -> str:
    return value.strftime("%Y-%m-%d")


def oracle_events(store: Store, market_id: str) -> list[dict[str, Any]]:
    """Large day-over-day oracle moves, and days an oracle stopped answering."""
    rows = store.query(
        """
        select vault_id, day, spot_price, prev_spot_price, spot_change
        from loop.oracle_daily
        where market_id = %s
          and (abs(spot_change) >= %s or (spot_price is null and prev_spot_price is not null))
        order by day, vault_id
        """,
        (market_id, ORACLE_MOVE_THRESHOLD),
    )
    return [
        {
            "vault": r["vault_id"],
            "day": _day(r["day"]),
            "kind": "reverted" if r["spot_price"] is None else "move",
            "from": _num(r["prev_spot_price"]),
            "to": _num(r["spot_price"]),
            "change": _num(r["spot_change"]),
        }
        for r in rows
    ]


def health(store: Store) -> dict[str, Any]:
    """Coverage per chain and per-series revert counts (data-quality panel)."""
    chains = store.query(
        """
        select chain_id, min(day) as first_day, max(day) as last_day, count(*) as days,
               sum(snapshots) as snapshots, sum(failed_calls) as failed_calls,
               max(max_block_lag_seconds) as max_block_lag_seconds
        from loop.coverage_daily group by chain_id order by chain_id
        """
    )
    series = store.query(
        "select series_id, observations, reverted, last_observed from loop.series_health"
        " where reverted > 0 order by reverted desc, series_id"
    )
    out_chains = []
    for c in chains:
        span = (c["last_day"] - c["first_day"]).days + 1
        out_chains.append(
            {
                "chainId": c["chain_id"],
                "firstDay": _day(c["first_day"]),
                "lastDay": _day(c["last_day"]),
                "days": int(c["days"]),
                "coverage": _num(c["days"] / span) if span > 0 else None,
                "snapshots": int(c["snapshots"]),
                "failedCalls": int(c["failed_calls"] or 0),
                "maxBlockLagSeconds": _num(c["max_block_lag_seconds"]),
            }
        )
    return {
        "chains": out_chains,
        "reverting": [
            {
                "series_id": s["series_id"],
                "observations": int(s["observations"]),
                "reverted": int(s["reverted"]),
                "lastObserved": s["last_observed"].isoformat() if s["last_observed"] else None,
            }
            for s in series
        ],
    }


def market_meta(registry: Registry, market: Market) -> dict[str, Any]:
    chain = registry.chains[market.chain]
    return {
        "id": market.id,
        "name": market.name,
        "chain": market.chain,
        "chainName": chain.name,
        "chainId": chain.chain_id,
        "explorer": chain.explorer,
        "underlying": market.underlying.model_dump(),
        "pool": {"address": market.pool.address, "symbol": market.pool.symbol},
        "staking": (
            {"address": market.staking.address, "symbol": market.staking.symbol}
            if market.staking
            else None
        ),
        "vaults": [
            {
                "id": v.id,
                "name": v.name,
                "address": v.address,
                "collateral": v.collateral.model_dump(),
                "registered": v.registered,
                "notes": v.notes,
            }
            for v in market.vaults
        ],
    }


def export_static(store: Store, registry: Registry, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    freshness = {
        str(row["chain_id"]): row["last_snapshot"].isoformat() for row in store.freshness()
    }
    meta = {
        "generatedAt": datetime.now(tz=UTC).isoformat(timespec="seconds"),
        "resolution": "1d",
        "freshness": freshness,
        "health": health(store),
        "markets": [market_meta(registry, m) for m in registry.markets],
        "series": [
            {
                "series_id": s.series_id,
                "market_id": s.market_id,
                "entity_type": s.entity_type,
                "entity_id": s.entity_id,
                "metric": s.metric,
                "unit": s.unit,
                "description": s.description,
                "contract": s.target,
                "call": s.signature,
            }
            for s in registry.series
        ],
    }
    path = out_dir / "meta.json"
    path.write_text(json.dumps(meta, indent=1) + "\n")
    written.append(path)

    for market in registry.markets:
        daily = store.query(
            "select * from loop.market_daily where market_id = %s order by day", (market.id,)
        )
        vault_rows = store.query(
            "select * from loop.vault_daily where market_id = %s order by vault_id, day",
            (market.id,),
        )
        vaults: dict[str, list[dict[str, Any]]] = {v.id: [] for v in market.vaults}
        for row in vault_rows:
            vaults.setdefault(row["vault_id"], []).append(
                {"day": _day(row["day"]), **{c: _num(row[c]) for c in VAULT_COLUMNS}}
            )
        analytics: dict[str, Any] = {}
        for key, (view, columns) in ANALYTICS.items():
            rows = store.query(
                f"select * from {view} where market_id = %s order by day", (market.id,)
            )
            analytics[key] = [
                {"day": _day(r["day"]), **{c: _num(r[c]) for c in columns}} for r in rows
            ]
        analytics["oracleEvents"] = oracle_events(store, market.id)
        payload = {
            "market": market.id,
            "daily": [
                {"day": _day(r["day"]), **{c: _num(r[c]) for c in MARKET_COLUMNS}} for r in daily
            ],
            "vaults": vaults,
            "analytics": analytics,
        }
        path = out_dir / f"{market.id}.json"
        path.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
        written.append(path)
    return written
