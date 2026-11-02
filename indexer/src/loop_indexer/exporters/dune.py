"""Export to Dune via the Uploads API (``/v1/uploads``).

Tables (public, in ``dune.<namespace>.<prefix>_*``):

* ``<prefix>_observations`` - append-only fact table, one row per (series, hour).
  Created once with an explicit schema, then appended to with ``/insert``.
* ``<prefix>_markets``, ``<prefix>_vaults``, ``<prefix>_series`` - small catalogues,
  replaced on every export (``/clear`` then ``/insert``). Using create + insert for
  every table keeps them all addressable as ``dune.<namespace>.<table>``.

Delivery is at-least-once: the cursor advances only after Dune acknowledges a batch,
so a crash can re-send one batch. Queries de-duplicate on ``(series_id, ts)`` keeping
the latest ``ingested_at`` (see ``dune/queries/``).
"""

from __future__ import annotations

import csv
import io
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

import httpx
import structlog

from loop_indexer.storage.store import ExportCursor, Store

log = structlog.get_logger(__name__)

# (name, Dune type, nullable)
OBSERVATIONS_SCHEMA: tuple[tuple[str, str, bool], ...] = (
    ("ts", "timestamp", False),
    ("chain_id", "integer", False),
    ("block_number", "integer", False),
    ("market_id", "varchar", False),
    ("entity_type", "varchar", False),
    ("entity_id", "varchar", False),
    ("metric", "varchar", False),
    ("series_id", "varchar", False),
    ("unit", "varchar", False),
    ("value", "double", False),
    # Exact uint256 as a decimal string: cast(raw_value as uint256) in DuneSQL.
    ("raw_value", "varchar", False),
    ("ingested_at", "timestamp", False),
)


_V, _I, _B = "varchar", "integer", "boolean"

# Catalogue tables: (schema, source query, description). Joined in dune/queries/*.sql.
CATALOGUE: dict[str, tuple[tuple[tuple[str, str, bool], ...], str, str]] = {
    "markets": (
        (
            ("market_id", _V, False), ("name", _V, False), ("chain", _V, False),
            ("chain_id", _I, False), ("underlying_symbol", _V, False),
            ("underlying_address", _V, False), ("underlying_decimals", _I, False),
            ("pool_address", _V, False), ("pool_symbol", _V, False),
            ("staking_address", _V, True), ("staking_symbol", _V, True),
            ("start_block", _I, False),
        ),
        "select * from loop.markets order by market_id",
        "Loop markets (one lending pool each).",
    ),
    "vaults": (
        (
            ("market_id", _V, False), ("vault_id", _V, False), ("name", _V, False),
            ("address", _V, False), ("collateral_symbol", _V, False),
            ("collateral_address", _V, False), ("collateral_decimals", _I, False),
            ("registered", _B, False), ("deployed_block", _I, False), ("notes", _V, True),
        ),
        "select * from loop.vaults order by market_id, vault_id",
        "Loop CDP vaults (borrowers of each pool).",
    ),
    "series": (
        (
            ("series_id", _V, False), ("chain", _V, False), ("chain_id", _I, False),
            ("market_id", _V, False), ("entity_type", _V, False), ("entity_id", _V, False),
            ("metric", _V, False), ("contract_address", _V, False),
            ("function_signature", _V, False), ("decimals", _I, False), ("unit", _V, False),
            ("description", _V, False), ("active_from_block", _I, False),
        ),
        "select * from loop.series order by series_id",
        "Loop series catalogue: how each observed value is read on-chain.",
    ),
}  # fmt: skip


class DuneError(Exception):
    pass


def _iso(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _cell(value: Any) -> Any:
    if isinstance(value, datetime):
        return _iso(value)
    if isinstance(value, Decimal):
        return format(value, "f") if value == value.to_integral_value() else repr(float(value))
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return value


def to_csv(rows: Iterable[Mapping[str, Any]], columns: Sequence[str]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_cell(row[c]) for c in columns])
    return buf.getvalue()


class DuneClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.dune.com/api/v1",
        timeout: float = 300.0,
        max_retries: int = 4,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._http = httpx.Client(
            base_url=base_url,
            timeout=timeout,
            transport=transport,
            headers={"X-DUNE-API-KEY": api_key, "user-agent": "loop-indexer/1.0"},
        )
        self._max_retries = max_retries

    def close(self) -> None:
        self._http.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        for attempt in range(self._max_retries + 1):
            try:
                response = self._http.request(method, path, **kwargs)
            except httpx.TransportError as exc:
                if attempt == self._max_retries:
                    raise DuneError(f"{method} {path}: {exc}") from exc
            else:
                if response.status_code < 400:
                    return response
                retryable = response.status_code == 429 or response.status_code >= 500
                if not retryable or attempt == self._max_retries:
                    raise DuneError(f"{method} {path}: HTTP {response.status_code} {response.text}")
            time.sleep(min(30.0, 2.0**attempt))
        raise DuneError(f"{method} {path}: retries exhausted")  # pragma: no cover

    def create_table(
        self,
        namespace: str,
        table: str,
        schema: Sequence[tuple[str, str, bool]],
        *,
        description: str,
        is_private: bool = False,
    ) -> bool:
        """Create ``table``; returns False if it already existed."""
        body = {
            "namespace": namespace,
            "table_name": table,
            "description": description,
            "is_private": is_private,
            "schema": [{"name": n, "type": t, "nullable": null} for n, t, null in schema],
        }
        try:
            response = self._request("POST", "/uploads", json=body)
        except DuneError as exc:
            if "already exist" in str(exc).lower():
                return False
            raise
        return not bool(response.json().get("already_existed", False))

    def insert_csv(self, namespace: str, table: str, data: str) -> int:
        response = self._request(
            "POST",
            f"/uploads/{namespace}/{table}/insert",
            content=data.encode(),
            headers={"content-type": "text/csv"},
        )
        return int(response.json().get("rows_written", 0))

    def clear_table(self, namespace: str, table: str) -> None:
        self._request("POST", f"/uploads/{namespace}/{table}/clear")


@dataclass
class ExportStats:
    table: str
    rows: int = 0
    batches: int = 0
    created: bool = False


class DuneExporter:
    def __init__(self, store: Store, client: DuneClient, *, namespace: str, prefix: str) -> None:
        self.store = store
        self.client = client
        self.namespace = namespace
        self.prefix = prefix

    @property
    def observations_table(self) -> str:
        return f"{self.prefix}_observations"

    @property
    def destination(self) -> str:
        return f"dune:{self.namespace}.{self.observations_table}"

    def export_catalogue(self) -> None:
        """Replace the small catalogue tables (create once, then clear + insert)."""
        for name, (schema, sql, description) in CATALOGUE.items():
            table = f"{self.prefix}_{name}"
            rows = self.store.query(sql)
            created = self.client.create_table(
                self.namespace, table, schema, description=description
            )
            if not created:
                self.client.clear_table(self.namespace, table)
            if rows:
                columns = [c for c, _, _ in schema]
                self.client.insert_csv(self.namespace, table, to_csv(rows, columns))
            log.info("dune.catalogue_replaced", table=table, rows=len(rows))

    def export_observations(
        self, *, full: bool = False, batch_size: int = 50_000, max_batches: int | None = None
    ) -> ExportStats:
        table = self.observations_table
        stats = ExportStats(table=f"{self.namespace}.{table}")
        stats.created = self.client.create_table(
            self.namespace,
            table,
            OBSERVATIONS_SCHEMA,
            description="Loop Protocol on-chain state sampled hourly. One row per series and "
            "hour; de-duplicate on (series_id, ts) by latest ingested_at.",
        )
        cursor = self.store.get_cursor(self.destination)
        if full:
            if not stats.created:
                self.client.clear_table(self.namespace, table)
            cursor = ExportCursor(self.destination, None, None, None, 0)
            self.store.set_cursor(cursor)

        columns = [name for name, _, _ in OBSERVATIONS_SCHEMA]
        while max_batches is None or stats.batches < max_batches:
            rows = self.store.observations_after(cursor, batch_size)
            if not rows:
                break
            payload = [{**r, "raw_value": r["raw"]} for r in rows]
            written = self.client.insert_csv(self.namespace, table, to_csv(payload, columns))
            if written != len(rows):
                raise DuneError(f"Dune wrote {written} rows, expected {len(rows)}")
            last = rows[-1]
            cursor = ExportCursor(
                self.destination,
                last["ingested_at"],
                last["series_id"],
                last["ts"],
                cursor.rows_exported + written,
            )
            self.store.set_cursor(cursor)
            stats.rows += written
            stats.batches += 1
            log.info("dune.batch_inserted", table=table, rows=written, total=stats.rows)
        return stats
