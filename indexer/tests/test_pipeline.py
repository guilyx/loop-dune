"""End-to-end: fake chain -> pipeline -> Postgres -> views -> exporters."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from loop_indexer.chain.rpc import RpcClient
from loop_indexer.exporters.static import export_static, oracle_events
from loop_indexer.pipeline import Indexer, RunOptions
from loop_indexer.registry import Registry
from loop_indexer.storage.store import Store
from loop_indexer.timegrid import from_unix
from tests.fakechain import FakeChain

pytestmark = pytest.mark.db

HOURLY = RunOptions(interval=timedelta(hours=1), finality_seconds=0, concurrency=3)


def _indexer(registry: Registry, store: Store, chain: FakeChain) -> Indexer:
    return Indexer(
        registry,
        store,
        lambda _: RpcClient(["http://fake"], transport=chain.transport(), backoff_base=0),
    )


def test_full_run_is_complete_and_idempotent(
    registry: Registry, store: Store, chain: FakeChain
) -> None:
    indexer = _indexer(registry, store, chain)
    [stats] = indexer.run(["testnet"], HOURLY)
    # pool deployed at block 100 (22:33:08), head block 2999 (08:12:56 next day):
    # grid points 23:00 .. 08:00 -> 10 hours
    assert stats.planned == stats.completed == 10
    assert stats.ok

    snaps = store.query("select ts, block_number, block_timestamp from loop.snapshots order by ts")
    for row in snaps:
        assert row["block_timestamp"] <= row["ts"]
        assert row["ts"] - row["block_timestamp"] < timedelta(seconds=12)

    [again] = indexer.run(["testnet"], HOURLY)
    assert again.planned == 0  # nothing left to do


def test_gaps_are_healed_and_force_resamples(
    registry: Registry, store: Store, chain: FakeChain
) -> None:
    indexer = _indexer(registry, store, chain)
    indexer.run(["testnet"], HOURLY)
    store.execute("delete from loop.snapshots where ts = (select min(ts) from loop.snapshots)")
    [healed] = indexer.run(["testnet"], HOURLY)
    assert healed.planned == 1

    before = store.query("select max(ingested_at) as t from loop.observations")[0]["t"]
    [forced] = indexer.run(["testnet"], RunOptions(**{**HOURLY.__dict__, "force": True}))
    assert forced.planned == 10
    after = store.query("select max(ingested_at) as t from loop.observations")[0]["t"]
    assert after == before  # identical values do not bump ingested_at (no re-export)


def test_views_compute_derived_metrics(registry: Registry, store: Store, chain: FakeChain) -> None:
    _indexer(registry, store, chain).run(["testnet"], HOURLY)
    row = store.query("select * from loop.market_hourly order by ts desc limit 1")[0]
    block = store.query("select block_number from loop.snapshots order by ts desc limit 1")[0]
    b = block["block_number"]
    deposits, borrowed = (b - 100), (b - 700) // 2
    assert row["tvl"] == pytest.approx(deposits)
    assert row["utilization"] == pytest.approx(borrowed / deposits)
    assert row["borrow_apr"] == pytest.approx(0.05)
    assert row["lp_price"] == pytest.approx(1.0)
    assert row["slp_price"] == pytest.approx(1.1)
    assert row["locked_tvl"] == pytest.approx(7)

    # the oracle reverts in the last hour: no price, so no collateral value (not zero)
    latest = store.query("select * from loop.vault_hourly order by ts desc limit 1")[0]
    assert latest["spot_price"] is None
    assert latest["collateral_value"] is None

    vault = store.query(
        "select v.*, s.block_number from loop.vault_hourly v join loop.snapshots s using (ts)"
        " where v.spot_price is not null order by ts desc limit 1"
    )[0]
    vault_borrowed = (vault["block_number"] - 700) // 2
    assert vault["collateral_value"] == pytest.approx(6)  # 3 ALP * 2 TST
    assert vault["ltv"] == pytest.approx(vault_borrowed / 6)

    daily = store.query("select count(*) as n from loop.market_daily")[0]["n"]
    assert daily == 2  # 23:00 on day one, 00:00-08:00 on day two


def test_new_series_are_backfilled_at_stored_blocks(
    registry: Registry, store: Store, chain: FakeChain
) -> None:
    indexer = _indexer(registry, store, chain)
    indexer.run(["testnet"], HOURLY)
    sid = "tst.vault.alpha.liquidation_ratio"
    expected = store.query(
        "select count(*) as n from loop.observations where series_id = %s", (sid,)
    )[0]["n"]
    assert expected > 0
    # Simulate the metric being added to the registry after these snapshots were taken.
    store.execute("delete from loop.observations where series_id = %s", (sid,))
    store.execute("update loop.series set created_at = now() where series_id = %s", (sid,))
    calls_before = chain.requests.count("eth_getBlockByNumber")

    [stats] = indexer.run(["testnet"], HOURLY)
    assert stats.planned == 0
    assert stats.topped_up == expected
    restored = store.query(
        "select count(*) as n from loop.observations where series_id = %s", (sid,)
    )[0]["n"]
    assert restored == expected
    # Re-read at the stored blocks: only the run's plan touches block headers.
    assert chain.requests.count("eth_getBlockByNumber") - calls_before <= 3

    [again] = indexer.run(["testnet"], HOURLY)
    assert again.topped_up == 0


def test_analytics_views(registry: Registry, store: Store, chain: FakeChain) -> None:
    _indexer(registry, store, chain).run(["testnet"], HOURLY)
    # flows: the TVL change splits exactly into interest and net deposits
    for f in store.query("select * from loop.market_flows_daily"):
        assert f["tvl_change"] == pytest.approx(f["interest"] + f["net_flow"])
    # risk: capacity used = LTV x liquidation ratio; a single vault holds all debt
    v = store.query(
        "select * from loop.vault_hourly where spot_price is not null order by ts desc limit 1"
    )[0]
    assert v["liquidation_ratio"] == pytest.approx(1.1)
    assert v["max_ltv"] == pytest.approx(1 / 1.1)
    assert v["capacity_used"] == pytest.approx(v["ltv"] * 1.1)
    assert v["drop_to_liquidation"] == pytest.approx(max(0.0, 1 - v["ltv"] * 1.1))
    c = store.query("select * from loop.market_concentration_daily order by day desc limit 1")[0]
    assert c["debt_hhi"] == pytest.approx(1.0)
    assert c["borrowing_vaults"] == 1
    # yield: pass-through = supply / (borrow x utilization)
    y = store.query("select * from loop.market_yield_daily order by day desc limit 1")[0]
    assert y["pass_through"] == pytest.approx(0.02 / (0.05 * y["utilization"]))
    # data quality: every chain-day is covered; the stale oracle is reported
    cov = store.query("select sum(snapshots) as n from loop.coverage_daily")[0]["n"]
    assert cov == 10
    health = {r["series_id"]: r for r in store.query("select * from loop.series_health")}
    assert health["tst.vault.alpha.spot_price"]["reverted"] >= 1


def test_failed_calls_are_tracked(registry: Registry, store: Store, chain: FakeChain) -> None:
    # Make the oracle revert from the start of the chain's last hour.
    _indexer(registry, store, chain).run(["testnet"], HOURLY)
    last = store.query("select * from loop.snapshots order by ts desc limit 1")[0]
    assert last["failed_series"] == ["tst.vault.alpha.spot_price"]
    fresh = store.freshness()
    assert fresh[0]["chain_id"] == 31337
    assert fresh[0]["failed_calls"] >= 1


def test_window_options(registry: Registry, store: Store, chain: FakeChain) -> None:
    start = from_unix(chain.timestamps[1000])
    options = RunOptions(**{**HOURLY.__dict__, "start": start, "max_points": 2})
    [stats] = _indexer(registry, store, chain).run(["testnet"], options)
    assert stats.planned == 2
    assert all(r["ts"] >= start for r in store.query("select ts from loop.snapshots"))


def test_abandoned_runs_are_closed(store: Store) -> None:
    old = store.start_run("run", {})
    store.execute("update loop.runs set started_at = now() - interval '1 day' where run_id = %s",
                  (old,))  # fmt: skip
    current = store.start_run("run", {})
    rows = {r["run_id"]: r for r in store.query("select * from loop.runs")}
    assert rows[old]["status"] == "failed"
    assert rows[old]["error"].startswith("abandoned")
    assert rows[current]["status"] == "running"


def test_static_export(registry: Registry, store: Store, chain: FakeChain, tmp_path: Path) -> None:
    _indexer(registry, store, chain).run(["testnet"], HOURLY)
    files = export_static(store, registry, tmp_path)
    assert {f.name for f in files} == {"meta.json", "tst.json"}
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert meta["markets"][0]["vaults"][0]["id"] == "alpha"
    assert len(meta["series"]) == len(registry.series)
    data = json.loads((tmp_path / "tst.json").read_text())
    assert data["daily"][0]["tvl"] > 0
    assert set(data["vaults"]) == {"alpha"}
    assert set(data["analytics"]) == {"yield", "flows", "concentration", "oracleEvents"}
    assert data["vaults"]["alpha"][-1]["liquidation_ratio"] == pytest.approx(1.1)
    assert meta["health"]["chains"][0]["coverage"] == 1
    assert meta["health"]["reverting"][0]["series_id"] == "tst.vault.alpha.spot_price"
    assert isinstance(data["analytics"]["oracleEvents"], list)


def test_oracle_events(registry: Registry, store: Store) -> None:
    store.sync_registry(registry)
    spot, coll = "tst.vault.alpha.spot_price", "tst.vault.alpha.collateral_balance"
    days = ["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04"]
    prices = [2.0, 2.0, 0.2, None]  # -90% move, then the oracle stops answering
    for day, price in zip(days, prices, strict=True):
        ts = f"{day}T23:00:00Z"
        store.execute(
            "insert into loop.observations (series_id, ts, block_number, raw, value)"
            " values (%s, %s, 1, 1, 1)",
            (coll, ts),
        )
        if price is not None:
            store.execute(
                "insert into loop.observations (series_id, ts, block_number, raw, value)"
                " values (%s, %s, 1, 1, %s)",
                (spot, ts, price),
            )
    events = oracle_events(store, "tst")
    assert [(e["day"], e["kind"]) for e in events] == [
        ("2025-01-03", "move"),
        ("2025-01-04", "reverted"),
    ]
    assert events[0]["change"] == pytest.approx(-0.9)
