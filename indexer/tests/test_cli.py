from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from loop_indexer.cli import app
from loop_indexer.settings import get_settings

runner = CliRunner()


@pytest.fixture(autouse=True)
def _fresh_settings() -> None:
    get_settings.cache_clear()


def test_registry_show() -> None:
    result = runner.invoke(app, ["registry", "show"])
    assert result.exit_code == 0, result.output
    assert "total: 114 series" in result.output

    result = runner.invoke(app, ["registry", "show", "--json"])
    rows = json.loads(result.output)
    assert {r["series_id"] for r in rows} >= {"eth.pool.total_borrowed"}


def test_run_requires_rpc_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ETH_RPC_URLS", "")
    monkeypatch.setenv("DATABASE_URL", "postgresql://invalid:1/none")
    result = runner.invoke(app, ["registry", "verify", "--chain", "ethereum"])
    assert result.exit_code != 0
    assert "ETH_RPC_URLS" in result.output


def test_unknown_chain_is_rejected() -> None:
    result = runner.invoke(app, ["registry", "verify", "--chain", "solana"])
    assert result.exit_code != 0
    assert "unknown chain" in result.output


def test_export_dune_requires_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DUNE_API_KEY", raising=False)
    monkeypatch.delenv("DUNE_NAMESPACE", raising=False)
    result = runner.invoke(app, ["export", "dune"])
    assert result.exit_code != 0
    assert "DUNE_API_KEY" in result.output


@pytest.mark.db
def test_migrate_and_health(database_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", database_url)
    result = runner.invoke(app, ["db", "migrate"])
    assert result.exit_code == 0, result.output
    assert "applied 0 migration(s)" in result.output
    result = runner.invoke(app, ["health", "--max-lag", "1h"])
    assert result.exit_code == 1  # nothing indexed for the bundled chains
    assert "STALE ethereum" in result.output
