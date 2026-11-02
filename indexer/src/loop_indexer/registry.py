"""Typed registry of chains, markets and contracts, and the series derived from it.

The registry (``markets.yaml``) only describes *what exists*: contracts, tokens and
deployment blocks. *What we measure* is defined once per entity type in
:data:`POOL_METRICS`, :data:`STAKING_METRICS` and :func:`_vault_series`, so every
market gets exactly the same metrics. This removes the class of copy-paste bugs the
legacy hand-written config suffered from (wrong vault address on the BNB pool,
``locked_lp_usd_balance`` on the BTC pool, ...).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from functools import cached_property
from importlib import resources
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from eth_utils import is_address, to_checksum_address
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from loop_indexer.chain.abi import get_function
from loop_indexer.chain.multicall import MULTICALL3_ADDRESS

RAY_DECIMALS = 27  # Gearbox-style pools report rates as RAY (1e27 == 100% APR)
WAD_DECIMALS = 18


def _checksum(value: str) -> str:
    if not is_address(value):
        raise ValueError(f"not an address: {value!r}")
    return str(to_checksum_address(value))


Address = Annotated[str, AfterValidator(_checksum)]
Slug = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]*$", max_length=48)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Chain(_Model):
    chain_id: int
    name: str
    rpc_urls_env: str
    multicall3: Address = MULTICALL3_ADDRESS
    explorer: str


class Token(_Model):
    address: Address
    symbol: str
    decimals: int = Field(ge=0, le=36)


class Contract(_Model):
    address: Address
    deployed_block: int = Field(ge=0)


class Pool(Contract):
    symbol: str
    decimals: int = Field(ge=0, le=36)


class Staking(Contract):
    symbol: str
    decimals: int = Field(ge=0, le=36)


class Vault(Contract):
    id: Slug
    name: str
    collateral: Token
    #: Scale of ``spotPrice()``. 18 (WAD) everywhere except where an oracle is
    #: misconfigured; ``registry verify`` flags implausible magnitudes.
    spot_price_decimals: int = WAD_DECIMALS
    #: False when the vault points at the pool but was never added as a credit
    #: manager: it can hold collateral but can never borrow.
    registered: bool = True
    notes: str | None = None


class Market(_Model):
    id: Slug
    name: str
    chain: str
    underlying: Token
    pool: Pool
    staking: Staking | None = None
    locker: Contract | None = None
    #: Credit managers registered on the pool that are not CDP vaults (flash lenders).
    flash_lenders: tuple[Address, ...] = ()
    vaults: tuple[Vault, ...] = ()

    @model_validator(mode="after")
    def _unique_vaults(self) -> Market:
        ids = [v.id for v in self.vaults]
        if len(ids) != len(set(ids)):
            raise ValueError(f"market {self.id}: duplicate vault ids")
        return self

    @property
    def start_block(self) -> int:
        return self.pool.deployed_block


class Registry(_Model):
    version: Literal[1]
    chains: dict[Slug, Chain]
    markets: tuple[Market, ...]

    @model_validator(mode="after")
    def _check_refs(self) -> Registry:
        ids = [m.id for m in self.markets]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate market ids")
        for market in self.markets:
            if market.chain not in self.chains:
                raise ValueError(f"market {market.id}: unknown chain {market.chain!r}")
        return self

    def markets_on(self, chain: str) -> list[Market]:
        return [m for m in self.markets if m.chain == chain]

    @cached_property
    def series(self) -> tuple[Series, ...]:
        out: list[Series] = []
        for market in self.markets:
            out.extend(build_series(market, self.chains[market.chain]))
        ids = [s.series_id for s in out]
        if len(ids) != len(set(ids)):  # pragma: no cover - guarded by unique ids above
            raise ValueError("duplicate series ids")
        return tuple(out)

    def series_on(self, chain: str) -> list[Series]:
        return [s for s in self.series if s.chain == chain]


# --------------------------------------------------------------------------- series

EntityType = Literal["pool", "staking", "vault"]


@dataclass(frozen=True)
class Series:
    """One measurable quantity: a view call on a contract, sampled every hour."""

    series_id: str
    chain: str
    chain_id: int
    market_id: str
    entity_type: EntityType
    entity_id: str
    metric: str
    target: str
    abi: str
    function: str
    args: tuple[Any, ...]
    decimals: int
    unit: str
    description: str
    active_from_block: int
    output_index: int = 0
    tags: dict[str, str] = field(default_factory=dict)

    @property
    def signature(self) -> str:
        return get_function(self.abi, self.function, len(self.args)).signature

    def call_data(self) -> bytes:
        return get_function(self.abi, self.function, len(self.args)).encode(*self.args)

    def decode(self, data: bytes) -> int:
        values = get_function(self.abi, self.function, len(self.args)).decode(data)
        value = values[self.output_index]
        if not isinstance(value, int):
            raise TypeError(f"{self.series_id}: expected an integer, got {type(value)}")
        return value


@dataclass(frozen=True)
class _Metric:
    metric: str
    function: str
    description: str
    decimals: Literal["underlying", "pool", "staking", "ray"]
    unit: Literal["underlying", "pool", "staking", "ratio"]


POOL_METRICS: tuple[_Metric, ...] = (
    _Metric("total_supply", "totalSupply", "Pool shares (lpX) outstanding.", "pool", "pool"),
    _Metric(
        "expected_liquidity",
        "expectedLiquidity",
        "Underlying owed to lenders: idle cash + outstanding debt + accrued interest (TVL).",
        "underlying",
        "underlying",
    ),
    _Metric(
        "available_liquidity",
        "availableLiquidity",
        "Idle underlying held by the pool, available to borrow or withdraw.",
        "underlying",
        "underlying",
    ),
    _Metric(
        "total_borrowed",
        "totalBorrowed",
        "Underlying principal currently lent to vaults.",
        "underlying",
        "underlying",
    ),
    _Metric(
        "borrow_rate",
        "baseInterestRate",
        "Base borrow APR paid by vaults (RAY-scaled on-chain, stored as a ratio).",
        "ray",
        "ratio",
    ),
    _Metric(
        "supply_rate",
        "supplyRate",
        "Supply APR earned by lpX holders (RAY-scaled on-chain, stored as a ratio).",
        "ray",
        "ratio",
    ),
)

STAKING_METRICS: tuple[_Metric, ...] = (
    _Metric(
        "total_supply", "totalSupply", "Staked shares (slpX) outstanding.", "staking", "staking"
    ),
    _Metric(
        "total_assets",
        "totalAssets",
        "Pool shares (lpX) held by the staking vault.",
        "pool",
        "pool",
    ),
)


def build_series(market: Market, chain: Chain) -> Iterator[Series]:
    """Expand a market into its series. Pure: no RPC access."""
    ul = market.underlying
    scales = {
        "underlying": ul.decimals,
        "pool": market.pool.decimals,
        "staking": market.staking.decimals if market.staking else 0,
        "ray": RAY_DECIMALS,
    }
    units = {
        "underlying": ul.symbol,
        "pool": market.pool.symbol,
        "staking": market.staking.symbol if market.staking else "",
        "ratio": "ratio",
    }
    common: dict[str, Any] = {
        "chain": market.chain,
        "chain_id": chain.chain_id,
        "market_id": market.id,
    }

    for m in POOL_METRICS:
        yield Series(
            series_id=f"{market.id}.pool.{m.metric}",
            entity_type="pool",
            entity_id="pool",
            metric=m.metric,
            target=market.pool.address,
            abi="lending_pool",
            function=m.function,
            args=(),
            decimals=scales[m.decimals],
            unit=units[m.unit],
            description=m.description,
            active_from_block=market.pool.deployed_block,
            **common,
        )

    if market.locker is not None:
        yield Series(
            series_id=f"{market.id}.pool.locked_shares",
            entity_type="pool",
            entity_id="pool",
            metric="locked_shares",
            target=market.pool.address,
            abi="lending_pool",
            function="balanceOf",
            args=(market.locker.address,),
            decimals=market.pool.decimals,
            unit=market.pool.symbol,
            description="Pool shares (lpX) deposited in the time-lock contract.",
            active_from_block=max(market.pool.deployed_block, market.locker.deployed_block),
            tags={"locker": market.locker.address},
            **common,
        )

    if market.staking is not None:
        for m in STAKING_METRICS:
            yield Series(
                series_id=f"{market.id}.staking.{m.metric}",
                entity_type="staking",
                entity_id="staking",
                metric=m.metric,
                target=market.staking.address,
                abi="staked_pool",
                function=m.function,
                args=(),
                decimals=scales[m.decimals],
                unit=units[m.unit],
                description=m.description,
                active_from_block=market.staking.deployed_block,
                **common,
            )

    for vault in market.vaults:
        yield from _vault_series(market, vault, common)


def _vault_series(market: Market, vault: Vault, common: dict[str, Any]) -> Iterator[Series]:
    ul, col = market.underlying, vault.collateral
    base: dict[str, Any] = {
        "entity_type": "vault",
        "entity_id": vault.id,
        "active_from_block": vault.deployed_block,
        "tags": {"vault": vault.address, "collateral": col.address},
        **common,
    }
    prefix = f"{market.id}.vault.{vault.id}"
    yield Series(
        series_id=f"{prefix}.spot_price",
        metric="spot_price",
        target=vault.address,
        abi="cdp_vault",
        function="spotPrice",
        args=(),
        decimals=vault.spot_price_decimals,
        unit=f"{ul.symbol}/{col.symbol}",
        description="Oracle price of one collateral token, in underlying.",
        **base,
    )
    yield Series(
        series_id=f"{prefix}.total_debt",
        metric="total_debt",
        target=vault.address,
        abi="cdp_vault",
        function="totalDebt",
        args=(),
        # CDP vaults account in WAD regardless of the pool's underlying decimals
        # (verified on lpUSD: totalDebt 2236e18 vs creditManagerBorrowed 2236e6).
        decimals=WAD_DECIMALS,
        unit=ul.symbol,
        description="Debt reported by the vault (WAD-scaled on-chain).",
        **base,
    )
    yield Series(
        series_id=f"{prefix}.collateral_balance",
        metric="collateral_balance",
        target=col.address,
        abi="erc20",
        function="balanceOf",
        args=(vault.address,),
        decimals=col.decimals,
        unit=col.symbol,
        description="Collateral tokens held by the vault.",
        **base,
    )
    yield Series(
        series_id=f"{prefix}.liquidation_ratio",
        metric="liquidation_ratio",
        target=vault.address,
        abi="cdp_vault",
        function="vaultConfig",
        args=(),
        output_index=1,  # vaultConfig() -> (debtFloor, liquidationRatio)
        decimals=WAD_DECIMALS,
        unit="ratio",
        description="Minimum collateral value / debt before a position can be liquidated.",
        **base,
    )
    yield Series(
        series_id=f"{prefix}.liquidation_penalty",
        metric="liquidation_penalty",
        target=vault.address,
        abi="cdp_vault",
        function="liquidationConfig",
        args=(),
        output_index=0,  # liquidationConfig() -> (liquidationPenalty, liquidationDiscount)
        decimals=WAD_DECIMALS,
        unit="ratio",
        description="Share of repaid debt credited on liquidation (1 - penalty), WAD on-chain.",
        **base,
    )
    if vault.registered:
        yield Series(
            series_id=f"{prefix}.debt_ceiling",
            metric="debt_ceiling",
            target=market.pool.address,
            abi="lending_pool",
            function="creditManagerDebtLimit",
            args=(vault.address,),
            decimals=market.underlying.decimals,
            unit=ul.symbol,
            description="Maximum the pool will lend to this vault.",
            **base,
        )
        yield Series(
            series_id=f"{prefix}.pool_borrowed",
            metric="pool_borrowed",
            target=market.pool.address,
            abi="lending_pool",
            function="creditManagerBorrowed",
            args=(vault.address,),
            decimals=market.underlying.decimals,
            unit=ul.symbol,
            description="Principal the pool has lent to this vault.",
            **base,
        )


# --------------------------------------------------------------------------- loading

DEFAULT_REGISTRY = "markets.yaml"


def load_registry(path: str | Path | None = None) -> Registry:
    """Load and validate the registry (``LOOP_REGISTRY_PATH`` overrides the bundled one)."""
    path = path or os.environ.get("LOOP_REGISTRY_PATH")
    if path:
        text = Path(path).read_text()
    else:
        text = resources.files("loop_indexer").joinpath(DEFAULT_REGISTRY).read_text()
    return Registry.model_validate(yaml.safe_load(text))
