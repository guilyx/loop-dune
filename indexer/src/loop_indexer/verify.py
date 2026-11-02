"""Check the registry against the chain. Run in CI-like fashion before trusting data.

Catches the failure modes the legacy setup shipped with: wrong addresses, wrong
decimals, vaults added to a pool but never tracked, misplaced deployment blocks.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from eth_utils import to_checksum_address

from loop_indexer.chain.abi import get_function
from loop_indexer.chain.deploy import has_code
from loop_indexer.chain.rpc import CallRevertedError, RpcClient
from loop_indexer.registry import Market, Registry


@dataclass(frozen=True)
class Issue:
    market: str
    subject: str
    message: str

    def __str__(self) -> str:
        return f"[{self.market}] {self.subject}: {self.message}"


def _call(rpc: RpcClient, address: str, abi: str, fn: str, *args: Any) -> Any:
    f = get_function(abi, fn, len(args))
    values = f.decode(rpc.eth_call(address, f.encode(*args)))
    return values[0] if len(values) == 1 else values


def _same(a: str, b: str) -> bool:
    return bool(to_checksum_address(a) == to_checksum_address(b))


def verify_chain_id(rpc: RpcClient, expected: int) -> list[Issue]:
    actual = int(rpc.request("eth_chainId", []), 16)
    if actual != expected:
        return [Issue("*", "rpc", f"chain id {actual}, expected {expected}")]
    return []


def verify_market(rpc: RpcClient, market: Market) -> list[Issue]:
    issues: list[Issue] = []

    def check(subject: str, ok: bool, message: str) -> None:
        if not ok:
            issues.append(Issue(market.id, subject, message))

    pool = market.pool
    asset = _call(rpc, pool.address, "lending_pool", "asset")
    check("pool", _same(asset, market.underlying.address), f"asset() is {asset}")
    check("pool", _call(rpc, pool.address, "erc20", "decimals") == pool.decimals, "decimals")
    check(
        "underlying",
        _call(rpc, market.underlying.address, "erc20", "decimals") == market.underlying.decimals,
        "decimals",
    )

    contracts: list[tuple[str, str, int]] = [("pool", pool.address, pool.deployed_block)]
    if market.staking:
        st = market.staking
        staked = _call(rpc, st.address, "staked_pool", "asset")
        check("staking", _same(staked, pool.address), f"asset() is {staked}, not the pool")
        check("staking", _call(rpc, st.address, "erc20", "decimals") == st.decimals, "decimals")
        contracts.append(("staking", st.address, st.deployed_block))
    if market.locker:
        contracts.append(("locker", market.locker.address, market.locker.deployed_block))

    registered = {to_checksum_address(a) for a in _call(rpc, pool.address, "lending_pool",
                                                         "creditManagers")}  # fmt: skip
    expected = {v.address for v in market.vaults if v.registered} | set(market.flash_lenders)
    for missing in sorted(registered - expected):
        check("pool", False, f"credit manager {missing} is not in the registry")
    for extra in sorted(expected - registered):
        check("pool", False, f"{extra} is not a credit manager of the pool")

    for vault in market.vaults:
        subject = f"vault {vault.id}"
        token = _call(rpc, vault.address, "cdp_vault", "token")
        check(subject, _same(token, vault.collateral.address), f"token() is {token}")
        vault_pool = _call(rpc, vault.address, "cdp_vault", "pool")
        check(subject, _same(vault_pool, pool.address), f"pool() is {vault_pool}")
        decimals = _call(rpc, vault.collateral.address, "erc20", "decimals")
        check(subject, decimals == vault.collateral.decimals, f"collateral decimals {decimals}")
        try:
            spot = Decimal(_call(rpc, vault.address, "cdp_vault", "spotPrice"))
            price = spot.scaleb(-vault.spot_price_decimals)
            check(subject, Decimal("1e-6") < price < Decimal("1e6"),
                  f"implausible spot price {price}; check spot_price_decimals")  # fmt: skip
        except CallRevertedError:
            pass  # a stale oracle is a data fact, not a registry error
        contracts.append((subject, vault.address, vault.deployed_block))

    for subject, address, block in contracts:
        check(subject, has_code(rpc, address, block), f"no code at deployed_block {block}")
        check(subject, not has_code(rpc, address, block - 1),
              f"already deployed before block {block}")  # fmt: skip
    return issues


def verify_registry(registry: Registry, rpc_for: dict[str, RpcClient]) -> list[Issue]:
    issues: list[Issue] = []
    for chain, rpc in rpc_for.items():
        issues += verify_chain_id(rpc, registry.chains[chain].chain_id)
        for market in registry.markets_on(chain):
            issues += verify_market(rpc, market)
    return issues
