"""Find the block a contract was deployed in, using only ``eth_getCode`` (archive node).

This replaces the legacy Etherscan ``getcontractcreation`` lookup, which needed an API
key and is no longer on Etherscan's free tier for BNB Chain. Deployment blocks are
resolved once and pinned in the registry; ``loop-indexer registry verify`` re-checks them.
"""

from __future__ import annotations

from loop_indexer.chain.rpc import RpcClient


def has_code(rpc: RpcClient, address: str, block: int) -> bool:
    return len(rpc.get_code(address, block)) > 0


def find_deployment_block(rpc: RpcClient, address: str, *, latest: int | None = None) -> int:
    """Smallest block at which ``address`` has code (binary search, ~log2(head) calls)."""
    hi = latest if latest is not None else rpc.block_number()
    if not has_code(rpc, address, hi):
        raise ValueError(f"{address} has no code at block {hi}")
    lo = 0  # invariant: no code at lo (genesis has no contracts we care about)
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if has_code(rpc, address, mid):
            hi = mid
        else:
            lo = mid
    return hi
