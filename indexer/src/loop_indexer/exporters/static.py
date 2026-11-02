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
    "pool_borrowed", "ltv",
)  # fmt: skip


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
        "markets": [market_meta(registry, m) for m in registry.markets],
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
        payload = {
            "market": market.id,
            "daily": [
                {"day": _day(r["day"]), **{c: _num(r[c]) for c in MARKET_COLUMNS}} for r in daily
            ],
            "vaults": vaults,
        }
        path = out_dir / f"{market.id}.json"
        path.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
        written.append(path)
    return written
