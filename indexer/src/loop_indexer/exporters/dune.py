"""Export to Dune via the Uploads API (``/v1/uploads``).

Tables (public, in ``dune.<namespace>.<prefix>_*``):

* ``<prefix>_observations`` - append-only fact table, one row per (series, hour).
  Created once with an explicit schema, then appended to with ``/insert``.
* ``<prefix>_markets``, ``<prefix>_vaults``, ``<prefix>_series`` - small catalogues,
  overwritten on every export with ``/uploads/csv``.

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

    def upload_csv(
        self, table: str, data: str, *, description: str, is_private: bool = False
    ) -> None:
        """Create-or-overwrite a small table in one call."""
        self._request(
            "POST",
            "/uploads/csv",
            json={
                "table_name": table,
                "data": data,
                "description": description,
                "is_private": is_private,
            },
        )


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
        tables = {
            "markets": ("select * from loop.markets order by market_id", "Loop markets"),
            "vaults": ("select * from loop.vaults order by market_id, vault_id", "Loop vaults"),
            "series": ("select * from loop.series order by series_id", "Loop series catalogue"),
        }
        for name, (sql, description) in tables.items():
            rows = self.store.query(sql)
            if not rows:
                continue
            columns = [c for c in rows[0] if c not in {"call_args", "updated_at"}]
            self.client.upload_csv(
                f"{self.prefix}_{name}", to_csv(rows, columns), description=description
            )
            log.info("dune.catalogue_uploaded", table=f"{self.prefix}_{name}", rows=len(rows))

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
