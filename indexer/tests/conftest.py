from __future__ import annotations

import os
import textwrap
from collections.abc import Iterator
from pathlib import Path

import pytest
from eth_utils import to_checksum_address

from loop_indexer.chain.rpc import RpcClient
from loop_indexer.registry import Registry, load_registry
from loop_indexer.storage.store import Store
from tests.fakechain import FakeChain, FakeContract, RevertedError, linear_timestamps

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = REPO_ROOT / "supabase" / "migrations"

# Addresses for the synthetic market (any valid checksummed addresses work).
UNDERLYING = to_checksum_address("0x00000000000000000000000000000000000000a1")
POOL = to_checksum_address("0x00000000000000000000000000000000000000b1")
STAKING = to_checksum_address("0x00000000000000000000000000000000000000c1")
LOCKER = to_checksum_address("0x00000000000000000000000000000000000000d1")
VAULT = to_checksum_address("0x00000000000000000000000000000000000000e1")
COLLATERAL = to_checksum_address("0x00000000000000000000000000000000000000f1")
FLASH = to_checksum_address("0x00000000000000000000000000000000000000f2")

GENESIS_TS = 1_700_000_000  # 2023-11-14T22:13:20Z
BLOCK_TIME = 12
WAD = 10**18
RAY = 10**27


TEST_REGISTRY = textwrap.dedent(
    f"""
    version: 1
    chains:
      testnet:
        chain_id: 31337
        name: Testnet
        rpc_urls_env: TEST_RPC_URLS
        explorer: https://example.invalid
    markets:
      - id: tst
        name: Loop TST
        chain: testnet
        underlying: {{ address: "{UNDERLYING}", symbol: TST, decimals: 6 }}
        pool: {{ address: "{POOL}", symbol: lpTST, decimals: 6, deployed_block: 100 }}
        staking: {{ address: "{STAKING}", symbol: slpTST, decimals: 6, deployed_block: 400 }}
        locker: {{ address: "{LOCKER}", deployed_block: 400 }}
        flash_lenders: ["{FLASH}"]
        vaults:
          - id: alpha
            name: Alpha LP
            address: "{VAULT}"
            deployed_block: 700
            collateral: {{ address: "{COLLATERAL}", symbol: ALP, decimals: 18 }}
    """
)


@pytest.fixture
def registry(tmp_path: Path) -> Registry:
    path = tmp_path / "markets.yaml"
    path.write_text(TEST_REGISTRY)
    return load_registry(path)


def _same(a: str, b: str) -> bool:
    return a.lower() == b.lower()


def _pool_state(block: int) -> dict[str, int]:
    """Deterministic pool state: deposits grow 1 TST/block, borrows half of that."""
    deposits = max(0, block - 100) * 10**6
    borrowed = max(0, block - 700) * 10**6 // 2 if block >= 700 else 0
    return {"expected": deposits, "borrowed": borrowed, "available": deposits - borrowed}


def build_chain(blocks: int = 3_000) -> FakeChain:
    chain = FakeChain(31337, [0, *linear_timestamps(GENESIS_TS, blocks - 1, BLOCK_TIME)])
    chain.add(FakeContract(UNDERLYING, 1, "erc20", {"decimals": lambda b: 6}))
    chain.add(
        FakeContract(
            POOL,
            100,
            "lending_pool",
            {
                "asset": lambda b: UNDERLYING,
                "decimals": lambda b: 6,
                "totalSupply": lambda b: _pool_state(b)["expected"],
                "expectedLiquidity": lambda b: _pool_state(b)["expected"],
                "availableLiquidity": lambda b: _pool_state(b)["available"],
                "totalBorrowed": lambda b: _pool_state(b)["borrowed"],
                "baseInterestRate": lambda b: 5 * RAY // 100,
                "supplyRate": lambda b: 2 * RAY // 100,
                "balanceOf": lambda b, who: 7 * 10**6 if _same(who, LOCKER) else 0,
                "creditManagers": lambda b: [FLASH, VAULT] if b >= 700 else [FLASH],
                "creditManagerDebtLimit": lambda b, v: 10**12,
                "creditManagerBorrowed": lambda b, v: _pool_state(b)["borrowed"],
            },
        )
    )
    chain.add(
        FakeContract(
            STAKING,
            400,
            "staked_pool",
            {
                "asset": lambda b: POOL,
                "decimals": lambda b: 6,
                "totalSupply": lambda b: 50 * 10**6,
                "totalAssets": lambda b: 55 * 10**6,
            },
        )
    )
    chain.add(FakeContract(LOCKER, 400, "erc20", {}))
    chain.add(FakeContract(FLASH, 90, "erc20", {}))

    def spot(block: int) -> int:
        if block >= 2_500:
            raise_revert()
        return 2 * WAD

    chain.add(
        FakeContract(
            VAULT,
            700,
            "cdp_vault",
            {
                "token": lambda b: COLLATERAL,
                "pool": lambda b: POOL,
                "spotPrice": spot,
                "totalDebt": lambda b: _pool_state(b)["borrowed"] * 10**12,  # WAD
                "vaultConfig": lambda b: (WAD, 11 * WAD // 10),  # debt floor 1, ratio 1.1
                "liquidationConfig": lambda b: (99 * WAD // 100, 98 * WAD // 100),
            },
        )
    )
    chain.add(
        FakeContract(
            COLLATERAL,
            50,
            "erc20",
            {
                "decimals": lambda b: 18,
                "balanceOf": lambda b, who: 3 * WAD if _same(who, VAULT) else 0,
            },
        )
    )
    return chain


def raise_revert() -> None:
    raise RevertedError("oracle stale")


@pytest.fixture
def chain() -> FakeChain:
    return build_chain()


@pytest.fixture
def rpc(chain: FakeChain) -> Iterator[RpcClient]:
    client = RpcClient(["http://fake"], name="testnet", transport=chain.transport(),
                       backoff_base=0, max_retries=2)  # fmt: skip
    yield client
    client.close()


@pytest.fixture(scope="session")
def bundled_registry() -> Registry:
    return load_registry()


# ---------------------------------------------------------------------------- database


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    with Store(url) as store:
        store.execute("drop schema if exists loop cascade")
        store.migrate(MIGRATIONS)
    return url


@pytest.fixture
def store(database_url: str) -> Iterator[Store]:
    with Store(database_url) as s:
        s.execute(
            "truncate loop.observations, loop.snapshots, loop.series, loop.vaults,"
            " loop.markets, loop.runs, loop.export_cursors"
        )
        yield s
