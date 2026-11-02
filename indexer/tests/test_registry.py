from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from loop_indexer.chain.abi import get_function
from loop_indexer.registry import Registry, load_registry
from tests.conftest import TEST_REGISTRY


def test_bundled_registry_is_valid(bundled_registry: Registry) -> None:
    assert {m.id for m in bundled_registry.markets} == {"eth", "usd", "bnb", "btc"}
    ids = [s.series_id for s in bundled_registry.series]
    assert len(ids) == len(set(ids))
    # every series resolves to a real ABI function with matching arity
    for s in bundled_registry.series:
        get_function(s.abi, s.function, len(s.args))
        assert s.active_from_block > 0


def test_bundled_registry_known_quirks(bundled_registry: Registry) -> None:
    by_id = {s.series_id: s for s in bundled_registry.series}
    # vault debt is WAD even on the 6-decimal USDC market
    assert by_id["usd.vault.spectra-sdeusd.total_debt"].decimals == 18
    assert by_id["usd.pool.total_borrowed"].decimals == 6
    assert by_id["usd.vault.pendle-syrupusdc-aug25.spot_price"].decimals == 30
    # rates are RAY-scaled
    assert by_id["eth.pool.borrow_rate"].decimals == 27
    # an unregistered vault gets no pool-side metrics
    assert "btc.vault.yncobtck.debt_ceiling" not in by_id
    # the BNB pool's per-vault metrics point at BNB vaults (legacy bug: an ETH address)
    debt = by_id["bnb.vault.pendle-clisbnb-apr25.pool_borrowed"]
    assert debt.args == ("0x03C07e6d561b664246058974dB31dbF1c1C0B416",)


def test_series_expansion(registry: Registry) -> None:
    metrics = {s.series_id for s in registry.series}
    assert "tst.pool.locked_shares" in metrics
    assert "tst.staking.total_assets" in metrics
    assert "tst.vault.alpha.pool_borrowed" in metrics
    assert len(metrics) == 6 + 1 + 2 + 5


def _mutate(path: Path, change: dict) -> Path:  # type: ignore[type-arg]
    data = yaml.safe_load(TEST_REGISTRY)
    market = data["markets"][0]
    for key, value in change.items():
        market[key] = value
    path.write_text(yaml.safe_dump(data))
    return path


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ({"chain": "nowhere"}, "unknown chain"),
        ({"id": "Bad Id"}, "string_pattern_mismatch"),
        (
            {"pool": {"address": "0x123", "symbol": "x", "decimals": 6, "deployed_block": 1}},
            "not an address",
        ),
        ({"unexpected": 1}, "extra_forbidden"),
    ],
)
def test_invalid_registries_are_rejected(tmp_path: Path, change: dict, error: str) -> None:  # type: ignore[type-arg]
    with pytest.raises(ValidationError, match=error):
        load_registry(_mutate(tmp_path / "r.yaml", change))


def test_duplicate_vault_ids_are_rejected(tmp_path: Path) -> None:
    data = yaml.safe_load(TEST_REGISTRY)
    vault = data["markets"][0]["vaults"][0]
    data["markets"][0]["vaults"].append(vault)
    path = tmp_path / "r.yaml"
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValidationError, match="duplicate vault"):
        load_registry(path)


def test_addresses_are_checksummed(registry: Registry) -> None:
    lower = "0x00000000000000000000000000000000000000b1"
    assert registry.markets[0].pool.address != lower
    assert registry.markets[0].pool.address.lower() == lower


def test_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "custom.yaml"
    path.write_text(TEST_REGISTRY)
    monkeypatch.setenv("LOOP_REGISTRY_PATH", str(path))
    assert load_registry().markets[0].id == "tst"
