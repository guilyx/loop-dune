from __future__ import annotations

import random

import httpx
import pytest
from eth_abi import encode

from loop_indexer.chain.abi import get_function
from loop_indexer.chain.blocks import BlockResolver
from loop_indexer.chain.deploy import find_deployment_block
from loop_indexer.chain.multicall import (
    Call,
    aggregate3,
    decode_aggregate3,
    encode_aggregate3,
)
from loop_indexer.chain.rpc import CallRevertedError, RpcClient, RpcError
from tests.conftest import POOL, VAULT
from tests.fakechain import FakeChain

# ---------------------------------------------------------------------------- abi


def test_selectors_match_known_values() -> None:
    assert get_function("erc20", "totalSupply").selector.hex() == "18160ddd"
    assert get_function("erc20", "balanceOf").selector.hex() == "70a08231"
    assert get_function("cdp_vault", "spotPrice").signature == "spotPrice()"


def test_tuple_outputs_are_expanded() -> None:
    fn = get_function("cdp_vault", "vaultConfig")
    assert fn.output_types == ("uint128", "uint64")
    assert fn.decode(encode(["uint128", "uint64"], [1, 2])) == (1, 2)


def test_unknown_function_and_bad_arity() -> None:
    with pytest.raises(KeyError):
        get_function("erc20", "nope")
    with pytest.raises(TypeError):
        get_function("erc20", "balanceOf").encode()


# ---------------------------------------------------------------------------- multicall


def test_aggregate3_round_trip() -> None:
    data = encode_aggregate3([Call(POOL, b"\x01\x02")])
    assert data[:4].hex() == "82ad56cb"
    encoded = encode(["(bool,bytes)[]"], [[(True, b"\xaa"), (False, b"")]])
    assert [(r.success, r.data) for r in decode_aggregate3(encoded)] == [
        (True, b"\xaa"),
        (False, b""),
    ]


def test_aggregate3_chunks_and_tolerates_failures(rpc: RpcClient, chain: FakeChain) -> None:
    supply = get_function("lending_pool", "totalSupply")
    spot = get_function("cdp_vault", "spotPrice")
    calls = [Call(POOL, supply.encode())] * 5 + [Call(VAULT, spot.encode())]
    results = aggregate3(rpc, calls, block=2_600, chunk_size=2)  # spot reverts after 2_500
    assert len(results) == 6
    assert all(r.success for r in results[:5])
    assert not results[5].success
    assert chain.requests.count("eth_call") == 3


# ---------------------------------------------------------------------------- rpc


def test_failover_on_retryable_http_status(chain: FakeChain) -> None:
    chain.fail_next = [429, 503]
    client = RpcClient(["http://a", "http://b"], transport=chain.transport(), backoff_base=0)
    assert client.block_number() == chain.head


def test_gives_up_after_max_retries(chain: FakeChain) -> None:
    chain.fail_next = [500] * 10
    client = RpcClient(["http://a"], transport=chain.transport(), backoff_base=0, max_retries=2)
    with pytest.raises(RpcError):
        client.block_number()


def test_revert_is_not_retried(rpc: RpcClient, chain: FakeChain) -> None:
    spot = get_function("cdp_vault", "spotPrice")
    with pytest.raises(CallRevertedError):
        rpc.eth_call(VAULT, spot.encode(), 2_600)
    assert chain.requests.count("eth_call") == 1


def test_batch_preserves_order_and_chunks(chain: FakeChain) -> None:
    client = RpcClient(["http://a"], transport=chain.transport(), max_batch_size=3)
    stamps = client.block_timestamps([10, 2, 7, 1, 9])
    assert stamps == {n: chain.timestamps[n] for n in [10, 2, 7, 1, 9]}


def test_rpc_errors_and_malformed_responses_are_retried() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "error": {"code": -32005, "message": "rate limit"},
                },
            )
        if calls["n"] == 2:
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1})
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": "0x10"})

    client = RpcClient(["http://a"], transport=httpx.MockTransport(handler), backoff_base=0)
    assert client.block_number() == 16
    assert calls["n"] == 3


def test_requires_urls() -> None:
    with pytest.raises(ValueError, match="at least one"):
        RpcClient(["", " "])


# ---------------------------------------------------------------------------- blocks


def _variable_chain() -> FakeChain:
    """Genesis at t=0, then 12s blocks, a slowdown, repeated timestamps, a speed-up."""
    rng = random.Random(7)
    stamps = [0, 1_600_000_000]
    for i in range(20_000):
        if i < 5_000:
            step = 12
        elif i < 10_000:
            step = rng.choice([12, 24, 36])
        elif i < 15_000:
            step = rng.choice([0, 1])  # sub-second blocks share timestamps
        else:
            step = 3
        stamps.append(stamps[-1] + step)
    return FakeChain(1, stamps)


def _expected(stamps: list[int], ts: int) -> int:
    return max(i for i, t in enumerate(stamps) if t <= ts)


def test_block_at_matches_brute_force_on_irregular_chain() -> None:
    chain = _variable_chain()
    rpc = RpcClient(["http://a"], transport=chain.transport())
    resolver = BlockResolver(rpc, window=16)
    lo, hi = chain.timestamps[1], chain.timestamps[-1]
    rng = random.Random(1)
    for ts in sorted(rng.randrange(lo, hi) for _ in range(150)):
        assert resolver.block_at(ts) == _expected(chain.timestamps, ts)


def test_block_at_is_one_round_trip_for_consecutive_hours(chain: FakeChain) -> None:
    rpc = RpcClient(["http://a"], transport=chain.transport())
    resolver = BlockResolver(rpc)
    start = chain.timestamps[200] - chain.timestamps[200] % 3600 + 3600
    resolver.block_at(start)
    before = resolver.rpc_round_trips
    for hour in range(1, 6):
        resolver.block_at(start + hour * 3600)
    assert resolver.rpc_round_trips - before <= 5


def test_block_at_daily_steps_stay_cheap_on_fast_chains() -> None:
    # ~0.75s blocks with jitter and a drifting rate, whole-second timestamps:
    # like BNB Chain after Maxwell. A slope measured on one day misses the next
    # day's boundary by ~100 blocks, which must not degrade into a long bisection.
    rng = random.Random(3)
    start, ms, stamps = 1_750_000_000, 0, [0]
    for i in range(700_000):
        drift = 1 + 0.004 * ((i // 115_200) % 2)  # alternate slightly slower days
        ms += int(rng.uniform(700, 800) * drift)
        stamps.append(start + ms // 1000)
    chain = FakeChain(56, stamps)
    rpc = RpcClient(["http://a"], transport=chain.transport(), max_batch_size=32)
    resolver = BlockResolver(rpc)
    day = 86_400
    first = start - start % day + day
    resolver.block_at(first)  # cold start
    before = resolver.rpc_round_trips
    for n in range(1, 6):
        ts = first + n * day
        assert resolver.block_at(ts) == _expected_fast(chain.timestamps, ts)
    assert (resolver.rpc_round_trips - before) / 5 <= 3


def _expected_fast(stamps: list[int], ts: int) -> int:
    import bisect

    return bisect.bisect_right(stamps, ts) - 1


def test_block_at_edges(chain: FakeChain) -> None:
    rpc = RpcClient(["http://a"], transport=chain.transport())
    resolver = BlockResolver(rpc, anchors=[(10, chain.timestamps[10])])
    assert resolver.block_at(chain.timestamps[-1] + 100) == chain.head
    assert resolver.block_at(chain.timestamps[10]) == 10
    assert resolver.block_at(chain.timestamps[10] + 1) == 10
    with pytest.raises(ValueError, match="genesis"):
        BlockResolver(rpc).block_at(-1)


def test_find_deployment_block(rpc: RpcClient) -> None:
    assert find_deployment_block(rpc, VAULT) == 700
    with pytest.raises(ValueError, match="no code"):
        find_deployment_block(rpc, "0x0000000000000000000000000000000000000999")
