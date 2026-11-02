from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest

from loop_indexer.chain.rpc import RpcClient
from loop_indexer.exporters.dune import DuneClient, DuneError, DuneExporter, to_csv
from loop_indexer.pipeline import Indexer, RunOptions
from loop_indexer.registry import Registry
from loop_indexer.storage.store import Store
from tests.fakechain import FakeChain


class FakeDune:
    def __init__(self) -> None:
        self.tables: dict[str, list[str]] = {}
        self.calls: list[str] = []
        self.fail_next: list[int] = []

    def transport(self) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path.removeprefix("/api/v1")
            self.calls.append(f"{request.method} {path}")
            assert request.headers["x-dune-api-key"] == "secret"
            if self.fail_next:
                return httpx.Response(self.fail_next.pop(0), json={"error": "busy"})
            if path == "/uploads" and request.method == "POST":
                body = json.loads(request.content)
                name = f"{body['namespace']}.{body['table_name']}"
                existed = name in self.tables
                self.tables.setdefault(name, [])
                return httpx.Response(200, json={"already_existed": existed, "full_name": name})
            parts = path.strip("/").split("/")  # uploads/<ns>/<table>/<op>
            name = f"{parts[1]}.{parts[2]}"
            if name not in self.tables:
                return httpx.Response(404, json={"error": "table not found"})
            if parts[3] == "insert":
                lines = request.content.decode().strip().split("\n")[1:]
                self.tables[name].extend(lines)
                return httpx.Response(200, json={"rows_written": len(lines)})
            if parts[3] == "clear":
                self.tables[name] = []
                return httpx.Response(200, json={"message": "cleared"})
            return httpx.Response(400, json={"error": "bad request"})

        return httpx.MockTransport(handler)


def _client(dune: FakeDune) -> DuneClient:
    return DuneClient("secret", transport=dune.transport(), max_retries=2)


def test_to_csv_formats_cells() -> None:
    rows = [{"ts": datetime(2025, 1, 1, tzinfo=UTC), "v": Decimal("1.50"), "n": None, "b": True,
             "raw": Decimal(10**30)}]  # fmt: skip
    assert to_csv(rows, ["ts", "v", "n", "b", "raw"]) == (
        "ts,v,n,b,raw\n2025-01-01T00:00:00Z,1.5,,true,1000000000000000000000000000000\n"
    )


def test_client_retries_then_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("loop_indexer.exporters.dune.time.sleep", lambda _: None)
    dune = FakeDune()
    dune.fail_next = [429, 502]
    client = _client(dune)
    assert client.create_table("ns", "t", [("a", "varchar", True)], description="d") is True
    assert client.create_table("ns", "t", [("a", "varchar", True)], description="d") is False
    with pytest.raises(DuneError, match="404"):
        client.insert_csv("ns", "missing", "a\n1\n")


@pytest.mark.db
def test_exporter_appends_incrementally_and_reloads(
    registry: Registry, store: Store, chain: FakeChain, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("loop_indexer.exporters.dune.time.sleep", lambda _: None)
    indexer = Indexer(registry, store,
                      lambda _: RpcClient(["http://x"], transport=chain.transport()))  # fmt: skip
    options = RunOptions(interval=timedelta(hours=1), finality_seconds=0, max_points=4)
    indexer.run(["testnet"], options)
    total = store.query("select count(*) as n from loop.observations")[0]["n"]

    dune = FakeDune()
    exporter = DuneExporter(store, _client(dune), namespace="ns", prefix="loop")
    exporter.export_catalogue()
    exporter.export_catalogue()  # second run replaces rather than duplicates
    assert len(dune.tables["ns.loop_markets"]) == 1
    assert len(dune.tables["ns.loop_vaults"]) == 1
    assert len(dune.tables["ns.loop_series"]) == len(registry.series)

    stats = exporter.export_observations(batch_size=7)
    assert stats.created
    assert stats.rows == total
    assert len(dune.tables["ns.loop_observations"]) == total

    # Nothing new: nothing sent. New hours: only those rows are appended.
    assert exporter.export_observations(batch_size=7).rows == 0
    indexer.run(["testnet"], RunOptions(interval=timedelta(hours=1), finality_seconds=0))
    grown = store.query("select count(*) as n from loop.observations")[0]["n"]
    assert exporter.export_observations(batch_size=1000).rows == grown - total
    assert len(dune.tables["ns.loop_observations"]) == grown

    # A full reload clears the table first, so Dune ends up with exactly one copy.
    assert exporter.export_observations(full=True, batch_size=1000).rows == grown
    assert len(dune.tables["ns.loop_observations"]) == grown
    assert "POST /uploads/ns/loop_observations/clear" in dune.calls
    first_row = dune.tables["ns.loop_observations"][0].split(",")
    assert len(first_row) == 12  # one cell per column of OBSERVATIONS_SCHEMA


@pytest.mark.db
def test_exporter_rejects_short_writes(registry: Registry, store: Store, chain: FakeChain) -> None:
    indexer = Indexer(registry, store,
                      lambda _: RpcClient(["http://x"], transport=chain.transport()))  # fmt: skip
    indexer.run(["testnet"], RunOptions(interval=timedelta(hours=1), finality_seconds=0,
                                        max_points=1))  # fmt: skip

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/insert"):
            return httpx.Response(200, json={"rows_written": 1})
        return httpx.Response(200, json={"already_existed": True})

    client = DuneClient("secret", transport=httpx.MockTransport(handler))
    exporter = DuneExporter(store, client, namespace="ns", prefix="loop")
    with pytest.raises(DuneError, match="expected"):
        exporter.export_observations()
    assert store.get_cursor(exporter.destination).rows_exported == 0
