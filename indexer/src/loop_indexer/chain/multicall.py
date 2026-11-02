"""Multicall3 batching: read many view functions at one block in a single ``eth_call``."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from eth_abi import decode, encode
from eth_utils import function_signature_to_4byte_selector

from loop_indexer.chain.rpc import RpcClient

# Deployed at the same address on every chain we index (and most EVM chains).
# https://github.com/mds1/multicall
MULTICALL3_ADDRESS = "0xcA11bde05977b3631167028862bE2a173976CA11"

_AGGREGATE3 = bytes(function_signature_to_4byte_selector("aggregate3((address,bool,bytes)[])"))


@dataclass(frozen=True)
class Call:
    target: str
    data: bytes


@dataclass(frozen=True)
class CallResult:
    success: bool
    data: bytes


def encode_aggregate3(calls: Sequence[Call]) -> bytes:
    # allowFailure=True: one reverting call must never sink the whole snapshot.
    payload = [(c.target, True, c.data) for c in calls]
    return _AGGREGATE3 + encode(["(address,bool,bytes)[]"], [payload])


def decode_aggregate3(data: bytes) -> list[CallResult]:
    (results,) = decode(["(bool,bytes)[]"], data)
    return [CallResult(success=bool(ok), data=bytes(ret)) for ok, ret in results]


def aggregate3(
    rpc: RpcClient,
    calls: Sequence[Call],
    block: int,
    *,
    address: str = MULTICALL3_ADDRESS,
    chunk_size: int = 100,
) -> list[CallResult]:
    """Execute ``calls`` at ``block`` and return one result per call, in order."""
    results: list[CallResult] = []
    for start in range(0, len(calls), chunk_size):
        chunk = calls[start : start + chunk_size]
        raw = rpc.eth_call(address, encode_aggregate3(chunk), block)
        decoded = decode_aggregate3(raw)
        if len(decoded) != len(chunk):
            raise ValueError(f"multicall returned {len(decoded)} results for {len(chunk)} calls")
        results.extend(decoded)
    return results
