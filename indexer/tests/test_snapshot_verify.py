from __future__ import annotations

from datetime import UTC, datetime

from eth_utils import to_checksum_address

from loop_indexer.chain.rpc import RpcClient
from loop_indexer.registry import Registry
from loop_indexer.snapshot import scale, take_snapshot
from loop_indexer.verify import verify_registry
from tests.conftest import FLASH, VAULT
from tests.fakechain import FakeChain, FakeContract

TS = datetime(2024, 1, 1, tzinfo=UTC)


def _snap(registry: Registry, rpc: RpcClient, block: int):  # type: ignore[no-untyped-def]
    return take_snapshot(
        rpc,
        registry.series,
        chain_id=31337,
        ts=TS,
        block_number=block,
        block_timestamp=TS,
        multicall_address=registry.chains["testnet"].multicall3,
    )


def test_snapshot_only_reads_active_series(registry: Registry, rpc: RpcClient) -> None:
    snap = _snap(registry, rpc, 150)  # only the pool exists
    assert snap.series_count == 6
    assert {o.series_id.split(".")[1] for o in snap.observations} == {"pool"}
    assert snap.failed == ()


def test_snapshot_values_are_scaled(registry: Registry, rpc: RpcClient) -> None:
    snap = _snap(registry, rpc, 1_000)
    values = {o.series_id: o for o in snap.observations}
    assert snap.series_count == 16
    assert values["tst.pool.expected_liquidity"].value == 900  # (1000-100) TST
    assert values["tst.pool.borrow_rate"].value == scale(5, 2)  # 5% APR from RAY
    assert values["tst.vault.alpha.total_debt"].value == 150  # WAD-scaled debt
    assert values["tst.vault.alpha.collateral_balance"].raw == 3 * 10**18
    # tuple outputs: the registry picks the right element
    assert values["tst.vault.alpha.liquidation_ratio"].value == scale(11, 1)
    assert values["tst.vault.alpha.liquidation_penalty"].value == scale(99, 2)


def test_reverted_calls_are_recorded_not_zeroed(registry: Registry, rpc: RpcClient) -> None:
    snap = _snap(registry, rpc, 2_600)  # the vault oracle reverts from block 2_500
    assert snap.failed == ("tst.vault.alpha.spot_price",)
    assert "tst.vault.alpha.spot_price" not in {o.series_id for o in snap.observations}


def test_verify_passes_on_consistent_registry(registry: Registry, rpc: RpcClient) -> None:
    assert verify_registry(registry, {"testnet": rpc}) == []


def test_verify_detects_drift(registry: Registry, chain: FakeChain, rpc: RpcClient) -> None:
    pool = next(c for c in chain.contracts.values() if c.abi == "lending_pool")
    new_vault = to_checksum_address("0x00000000000000000000000000000000000000e9")
    pool.handlers["creditManagers"] = lambda b: [FLASH, VAULT, new_vault]
    vault = chain.contracts[VAULT]
    vault.handlers["token"] = lambda b: new_vault
    vault.deployed_block = 650  # registry says 700
    chain.add(FakeContract(new_vault, 900, "cdp_vault", {}))

    messages = [str(i) for i in verify_registry(registry, {"testnet": rpc})]
    assert any("not in the registry" in m for m in messages)
    assert any("token() is" in m for m in messages)
    assert any("already deployed before block 700" in m for m in messages)


def test_verify_detects_wrong_chain(registry: Registry, chain: FakeChain, rpc: RpcClient) -> None:
    chain.chain_id = 1
    assert any("chain id 1" in str(i) for i in verify_registry(registry, {"testnet": rpc}))
