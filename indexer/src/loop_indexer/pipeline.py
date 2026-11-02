"""Indexing pipeline: plan missing grid points, resolve blocks, snapshot, persist.

Guarantees:

* **Idempotent** - every write is an upsert keyed by (series, ts) / (chain, ts).
* **Self-healing** - each run fills *every* missing grid point since deployment, so a
  failed hour or a week of downtime is repaired by the next successful run.
* **Honest** - a reverted call yields no row (never a fake zero); hours that could
  not be read are reported and make the run exit non-zero.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

import structlog

from loop_indexer.chain.blocks import BlockResolver
from loop_indexer.chain.rpc import RpcClient, RpcError
from loop_indexer.registry import Registry
from loop_indexer.snapshot import Snapshot, take_snapshot
from loop_indexer.storage.store import Store
from loop_indexer.timegrid import ceil_to, floor_to, from_unix, grid, to_unix

log = structlog.get_logger(__name__)

RpcFactory = Callable[[str], RpcClient]


@dataclass
class ChainStats:
    chain: str
    start: str | None = None
    end: str | None = None
    planned: int = 0
    completed: int = 0
    #: existing snapshots re-read at their stored block to fill newly registered series
    topped_up: int = 0
    failed_hours: list[str] = field(default_factory=list)
    observations: int = 0
    failed_calls: int = 0
    block_round_trips: int = 0
    seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return not self.failed_hours

    def as_dict(self) -> dict[str, object]:
        out = asdict(self)
        out["failed_hours"] = self.failed_hours[:50]
        out["failed_hour_count"] = len(self.failed_hours)
        return out


@dataclass(frozen=True)
class RunOptions:
    interval: timedelta = timedelta(hours=1)
    start: datetime | None = None
    end: datetime | None = None
    force: bool = False
    concurrency: int = 4
    max_points: int | None = None
    finality_seconds: int = 900


class Indexer:
    def __init__(self, registry: Registry, store: Store, rpc_factory: RpcFactory) -> None:
        self.registry = registry
        self.store = store
        self.rpc_factory = rpc_factory

    def run(self, chains: Sequence[str], options: RunOptions) -> list[ChainStats]:
        self.store.sync_registry(self.registry)
        return [self._run_chain(chain, options) for chain in chains]

    # ------------------------------------------------------------------ planning

    def plan(
        self, chain: str, resolver: BlockResolver, options: RunOptions
    ) -> tuple[datetime, datetime, list[datetime]]:
        """Grid points to sample for ``chain`` within the requested window."""
        cfg = self.registry.chains[chain]
        first_block = min(m.start_block for m in self.registry.markets_on(chain))
        deployed_at = from_unix(resolver.timestamp(first_block))
        _, head_ts = resolver.latest(refresh=True)
        safe_head = from_unix(head_ts - options.finality_seconds)

        start = max(ceil_to(deployed_at, options.interval), options.start or deployed_at)
        end = min(floor_to(safe_head, options.interval), options.end or safe_head)
        points = grid(start, end, options.interval)
        if not options.force:
            done = self.store.snapshot_times(cfg.chain_id, start, end)
            points = [p for p in points if p not in done]
        if options.max_points is not None:
            points = points[: options.max_points]
        return start, end, points

    # ------------------------------------------------------------------ execution

    def _run_chain(self, chain: str, options: RunOptions) -> ChainStats:
        started = time.monotonic()
        cfg = self.registry.chains[chain]
        series = self.registry.series_on(chain)
        stats = ChainStats(chain=chain)
        rpc = self.rpc_factory(chain)
        try:
            resolver = BlockResolver(rpc, anchors=self.store.block_anchors(cfg.chain_id))
            start, end, points = self.plan(chain, resolver, options)
            stats.start, stats.end, stats.planned = start.isoformat(), end.isoformat(), len(points)
            log.info(
                "chain.plan", chain=chain, start=stats.start, end=stats.end, points=len(points)
            )

            def snapshot(ts: datetime, block: int, block_ts: int) -> Snapshot:
                return take_snapshot(
                    rpc,
                    series,
                    chain_id=cfg.chain_id,
                    ts=ts,
                    block_number=block,
                    block_timestamp=from_unix(block_ts),
                    multicall_address=cfg.multicall3,
                )

            pending: dict[Future[Snapshot], datetime] = {}
            with ThreadPoolExecutor(max_workers=max(1, options.concurrency)) as pool:
                for ts in points:
                    try:
                        # Block resolution is sequential: consecutive points reuse the
                        # previous answer as an anchor (~1 round trip per point).
                        block = resolver.block_at(to_unix(ts))
                        block_ts = resolver.timestamp(block)
                    except RpcError as exc:
                        log.error("chain.block_lookup_failed", chain=chain, ts=ts.isoformat(),
                                  error=str(exc))  # fmt: skip
                        stats.failed_hours.append(ts.isoformat())
                        continue
                    pending[pool.submit(snapshot, ts, block, block_ts)] = ts
                    if len(pending) >= options.concurrency * 2:
                        self._drain(pending, stats, block=False)
                self._drain(pending, stats, block=True)

                # Series added to the registry after older snapshots were taken: re-read
                # them at the stored block (no timestamp->block resolution needed).
                stale = self.store.snapshots_missing_new_series(cfg.chain_id, start, end)
                if options.max_points is not None:
                    stale = stale[: options.max_points]
                if stale:
                    log.info("chain.top_up", chain=chain, snapshots=len(stale))
                before = stats.completed
                for ts, block, block_ts in stale:
                    pending[pool.submit(snapshot, ts, block, block_ts)] = ts
                    if len(pending) >= options.concurrency * 2:
                        self._drain(pending, stats, block=False)
                self._drain(pending, stats, block=True)
                stats.topped_up = stats.completed - before
                stats.completed = before
            stats.block_round_trips = resolver.rpc_round_trips
        finally:
            rpc.close()
            stats.seconds = round(time.monotonic() - started, 1)
        log.info("chain.done", **stats.as_dict())
        return stats

    def _drain(
        self, pending: dict[Future[Snapshot], datetime], stats: ChainStats, *, block: bool
    ) -> None:
        while pending:
            done, _ = wait(list(pending), return_when=FIRST_COMPLETED)
            for future in done:
                ts = pending.pop(future)
                try:
                    snap = future.result()
                except RpcError as exc:
                    log.error("chain.snapshot_failed", chain=stats.chain, ts=ts.isoformat(),
                              error=str(exc))  # fmt: skip
                    stats.failed_hours.append(ts.isoformat())
                    continue
                self.store.save_snapshot(snap)
                stats.completed += 1
                stats.observations += len(snap.observations)
                stats.failed_calls += len(snap.failed)
                if stats.completed % 100 == 0:
                    log.info("chain.progress", chain=stats.chain, completed=stats.completed,
                             planned=stats.planned, ts=ts.isoformat())  # fmt: skip
            if not block:
                return
