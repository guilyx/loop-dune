"""Take one snapshot: every active series of a chain, read at one block."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

import structlog
from eth_abi.exceptions import DecodingError

from loop_indexer.chain.multicall import Call, aggregate3
from loop_indexer.chain.rpc import RpcClient
from loop_indexer.registry import Series

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class Observation:
    series_id: str
    raw: int
    value: Decimal


@dataclass(frozen=True)
class Snapshot:
    chain_id: int
    ts: datetime
    block_number: int
    block_timestamp: datetime
    observations: tuple[Observation, ...]
    series_count: int
    failed: tuple[str, ...] = field(default_factory=tuple)


def scale(raw: int, decimals: int) -> Decimal:
    return Decimal(raw).scaleb(-decimals)


def take_snapshot(
    rpc: RpcClient,
    series: Sequence[Series],
    *,
    chain_id: int,
    ts: datetime,
    block_number: int,
    block_timestamp: datetime,
    multicall_address: str,
) -> Snapshot:
    """Read all series active at ``block_number`` in one Multicall3 ``eth_call``.

    A call that reverts or returns undecodable data is recorded in ``failed`` and
    produces no observation: we never write a fabricated zero.
    """
    active = [s for s in series if s.active_from_block <= block_number]
    calls = [Call(s.target, s.call_data()) for s in active]
    results = aggregate3(rpc, calls, block_number, address=multicall_address) if calls else []

    observations: list[Observation] = []
    failed: list[str] = []
    for s, result in zip(active, results, strict=True):
        if not result.success or not result.data:
            failed.append(s.series_id)
            continue
        try:
            raw = s.decode(result.data)
        except (DecodingError, TypeError, ValueError):
            failed.append(s.series_id)
            continue
        observations.append(Observation(s.series_id, raw, scale(raw, s.decimals)))

    if failed:
        log.debug("snapshot.failed_calls", ts=ts.isoformat(), failed=failed)
    return Snapshot(
        chain_id=chain_id,
        ts=ts,
        block_number=block_number,
        block_timestamp=block_timestamp,
        observations=tuple(observations),
        series_count=len(active),
        failed=tuple(failed),
    )
