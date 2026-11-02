"""Postgres persistence. All writes are idempotent upserts."""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg
import structlog
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from loop_indexer.registry import Registry
from loop_indexer.snapshot import Snapshot
from loop_indexer.timegrid import to_unix

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ExportCursor:
    destination: str
    ingested_at: datetime | None
    series_id: str | None
    ts: datetime | None
    rows_exported: int


class Store:
    def __init__(self, dsn: str) -> None:
        # Autocommit: reads never hold a transaction open, and every write goes through
        # an explicit `transaction()` block, so it commits atomically or not at all.
        self.conn = psycopg.connect(dsn, row_factory=dict_row, autocommit=True)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[psycopg.Cursor[dict[str, Any]]]:
        with self.conn.transaction(), self.conn.cursor() as cur:
            yield cur

    # ------------------------------------------------------------------ migrations

    def migrate(self, migrations_dir: Path) -> list[str]:
        """Apply ``*.sql`` files in name order, once each. Returns applied versions."""
        files = sorted(migrations_dir.glob("*.sql"))
        if not files:
            raise FileNotFoundError(f"no migrations in {migrations_dir}")
        with self.transaction() as cur:
            cur.execute("create schema if not exists loop")
            cur.execute(
                "create table if not exists loop.schema_migrations ("
                " version text primary key, applied_at timestamptz not null default now())"
            )
            cur.execute("select version from loop.schema_migrations")
            done = {row["version"] for row in cur.fetchall()}
        applied: list[str] = []
        for path in files:
            if path.stem in done:
                continue
            with self.transaction() as cur:
                cur.execute(path.read_text().encode())
                cur.execute(
                    "insert into loop.schema_migrations (version) values (%s)", (path.stem,)
                )
            applied.append(path.stem)
            log.info("db.migration_applied", version=path.stem)
        return applied

    # ------------------------------------------------------------------ catalogue

    def sync_registry(self, registry: Registry) -> None:
        with self.transaction() as cur:
            for m in registry.markets:
                chain = registry.chains[m.chain]
                cur.execute(
                    """
                    insert into loop.markets (market_id, name, chain, chain_id,
                        underlying_symbol, underlying_address, underlying_decimals,
                        pool_address, pool_symbol, staking_address, staking_symbol,
                        start_block, updated_at)
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                    on conflict (market_id) do update set
                        name = excluded.name, chain = excluded.chain,
                        chain_id = excluded.chain_id,
                        underlying_symbol = excluded.underlying_symbol,
                        underlying_address = excluded.underlying_address,
                        underlying_decimals = excluded.underlying_decimals,
                        pool_address = excluded.pool_address,
                        pool_symbol = excluded.pool_symbol,
                        staking_address = excluded.staking_address,
                        staking_symbol = excluded.staking_symbol,
                        start_block = excluded.start_block, updated_at = now()
                    """,
                    (
                        m.id, m.name, m.chain, chain.chain_id,
                        m.underlying.symbol, m.underlying.address, m.underlying.decimals,
                        m.pool.address, m.pool.symbol,
                        m.staking.address if m.staking else None,
                        m.staking.symbol if m.staking else None,
                        m.start_block,
                    ),
                )  # fmt: skip
                for v in m.vaults:
                    cur.execute(
                        """
                        insert into loop.vaults (market_id, vault_id, name, address,
                            collateral_symbol, collateral_address, collateral_decimals,
                            registered, deployed_block, notes, updated_at)
                        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                        on conflict (market_id, vault_id) do update set
                            name = excluded.name, address = excluded.address,
                            collateral_symbol = excluded.collateral_symbol,
                            collateral_address = excluded.collateral_address,
                            collateral_decimals = excluded.collateral_decimals,
                            registered = excluded.registered,
                            deployed_block = excluded.deployed_block,
                            notes = excluded.notes, updated_at = now()
                        """,
                        (
                            m.id, v.id, v.name, v.address, v.collateral.symbol,
                            v.collateral.address, v.collateral.decimals, v.registered,
                            v.deployed_block, v.notes,
                        ),
                    )  # fmt: skip
            cur.executemany(
                """
                insert into loop.series (series_id, chain, chain_id, market_id, entity_type,
                    entity_id, metric, contract_address, function_signature, call_args,
                    decimals, unit, description, active_from_block, updated_at)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                on conflict (series_id) do update set
                    contract_address = excluded.contract_address,
                    function_signature = excluded.function_signature,
                    call_args = excluded.call_args, decimals = excluded.decimals,
                    unit = excluded.unit, description = excluded.description,
                    active_from_block = excluded.active_from_block, updated_at = now()
                """,
                [
                    (
                        s.series_id, s.chain, s.chain_id, s.market_id, s.entity_type,
                        s.entity_id, s.metric, s.target, s.signature,
                        Jsonb([str(a) for a in s.args]), s.decimals, s.unit, s.description,
                        s.active_from_block,
                    )
                    for s in registry.series
                ],
            )  # fmt: skip

    # ------------------------------------------------------------------ snapshots

    def snapshot_times(self, chain_id: int, start: datetime, end: datetime) -> set[datetime]:
        with self.conn.cursor() as cur:
            cur.execute(
                "select ts from loop.snapshots where chain_id = %s and ts between %s and %s",
                (chain_id, start, end),
            )
            return {row["ts"] for row in cur.fetchall()}

    def block_anchors(self, chain_id: int) -> list[tuple[int, int]]:
        """(block, unix timestamp) pairs already known for a chain."""
        with self.conn.cursor() as cur:
            cur.execute(
                "select block_number, block_timestamp from loop.snapshots where chain_id = %s",
                (chain_id,),
            )
            return [(r["block_number"], to_unix(r["block_timestamp"])) for r in cur.fetchall()]

    def save_snapshot(self, snap: Snapshot) -> None:
        with self.transaction() as cur:
            if snap.observations:
                cur.executemany(
                    """
                    insert into loop.observations (series_id, ts, block_number, raw, value)
                    values (%s, %s, %s, %s, %s)
                    on conflict (series_id, ts) do update set
                        block_number = excluded.block_number,
                        raw = excluded.raw,
                        value = excluded.value,
                        ingested_at = now()
                    where (loop.observations.raw, loop.observations.block_number)
                        is distinct from (excluded.raw, excluded.block_number)
                    """,
                    [(o.series_id, snap.ts, snap.block_number, o.raw, o.value)
                     for o in snap.observations],
                )  # fmt: skip
            cur.execute(
                """
                insert into loop.snapshots (chain_id, ts, block_number, block_timestamp,
                    series_count, failed_count, failed_series)
                values (%s, %s, %s, %s, %s, %s, %s)
                on conflict (chain_id, ts) do update set
                    block_number = excluded.block_number,
                    block_timestamp = excluded.block_timestamp,
                    series_count = excluded.series_count,
                    failed_count = excluded.failed_count,
                    failed_series = excluded.failed_series,
                    ingested_at = now()
                """,
                (
                    snap.chain_id, snap.ts, snap.block_number, snap.block_timestamp,
                    snap.series_count, len(snap.failed), list(snap.failed),
                ),
            )  # fmt: skip

    def freshness(self) -> list[dict[str, Any]]:
        with self.conn.cursor() as cur:
            cur.execute("select * from loop.chain_freshness order by chain_id")
            return list(cur.fetchall())

    # ------------------------------------------------------------------ runs

    def start_run(self, command: str, params: dict[str, Any]) -> int:
        with self.transaction() as cur:
            cur.execute(
                "insert into loop.runs (command, params) values (%s, %s) returning run_id",
                (command, Jsonb(params)),
            )
            row = cur.fetchone()
            if row is None:  # pragma: no cover - INSERT ... RETURNING always yields a row
                raise RuntimeError("failed to create run")
            return int(row["run_id"])

    def finish_run(
        self, run_id: int, status: str, stats: dict[str, Any], error: str | None = None
    ) -> None:
        with self.transaction() as cur:
            cur.execute(
                "update loop.runs set finished_at = now(), status = %s, stats = %s, error = %s"
                " where run_id = %s",
                (status, Jsonb(json.loads(json.dumps(stats, default=str))), error, run_id),
            )

    # ------------------------------------------------------------------ exports

    def get_cursor(self, destination: str) -> ExportCursor:
        with self.conn.cursor() as cur:
            cur.execute("select * from loop.export_cursors where destination = %s", (destination,))
            row = cur.fetchone()
        if row is None:
            return ExportCursor(destination, None, None, None, 0)
        return ExportCursor(
            destination, row["ingested_at"], row["series_id"], row["ts"], row["rows_exported"]
        )

    def set_cursor(self, cursor: ExportCursor) -> None:
        with self.transaction() as cur:
            cur.execute(
                """
                insert into loop.export_cursors
                    (destination, ingested_at, series_id, ts, rows_exported, updated_at)
                values (%s, %s, %s, %s, %s, now())
                on conflict (destination) do update set
                    ingested_at = excluded.ingested_at, series_id = excluded.series_id,
                    ts = excluded.ts, rows_exported = excluded.rows_exported, updated_at = now()
                """,
                (
                    cursor.destination, cursor.ingested_at, cursor.series_id, cursor.ts,
                    cursor.rows_exported,
                ),
            )  # fmt: skip

    def observations_after(self, cursor: ExportCursor, limit: int) -> list[dict[str, Any]]:
        """Next page of observations in (ingested_at, series_id, ts) order."""
        where: str = ""
        params: list[Any] = [limit]
        if cursor.ingested_at is not None:
            where = "where (o.ingested_at, o.series_id, o.ts) > (%s, %s, %s)"
            params = [cursor.ingested_at, cursor.series_id, cursor.ts, limit]
        with self.conn.cursor() as cur:
            cur.execute(
                f"""
                select o.ts, s.chain_id, o.block_number, s.market_id, s.entity_type,
                       s.entity_id, s.metric, o.series_id, s.unit, o.value, o.raw,
                       o.ingested_at
                from loop.observations o
                join loop.series s using (series_id)
                {where}
                order by o.ingested_at, o.series_id, o.ts
                limit %s
                """,
                params,
            )
            return list(cur.fetchall())

    def execute(self, sql: str, params: Sequence[Any] = ()) -> None:
        """Run statement(s) that return no rows (multiple statements allowed without params)."""
        with self.conn.cursor() as cur:
            cur.execute(sql.encode(), params or None)

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        with self.conn.cursor() as cur:
            cur.execute(sql.encode(), params or None)
            return list(cur.fetchall())
