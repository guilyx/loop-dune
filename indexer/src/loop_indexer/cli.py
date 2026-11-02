"""``loop-indexer`` command line interface."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated

import structlog
import typer

from loop_indexer.chain.rpc import RpcClient
from loop_indexer.logs import configure_logging
from loop_indexer.registry import Registry, load_registry
from loop_indexer.settings import Settings, get_settings
from loop_indexer.storage.store import Store
from loop_indexer.timegrid import parse_duration, parse_time

app = typer.Typer(no_args_is_help=True, add_completion=False, help=__doc__)
db_app = typer.Typer(no_args_is_help=True, help="Database management.")
registry_app = typer.Typer(no_args_is_help=True, help="Inspect and verify the contract registry.")
export_app = typer.Typer(no_args_is_help=True, help="Export data to downstream consumers.")
app.add_typer(db_app, name="db")
app.add_typer(registry_app, name="registry")
app.add_typer(export_app, name="export")

log = structlog.get_logger("loop_indexer")

ChainOpt = Annotated[
    list[str] | None, typer.Option("--chain", "-c", help="Chain(s) to process (default: all).")
]


@app.callback()
def _main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)


def _rpc(settings: Settings, registry: Registry, chain: str) -> RpcClient:
    env = registry.chains[chain].rpc_urls_env
    urls = settings.rpc_urls(env)
    if not urls:
        raise typer.BadParameter(f"set {env} to one or more archive RPC URLs (comma-separated)")
    return RpcClient(
        urls,
        name=chain,
        timeout=settings.rpc_timeout,
        max_retries=settings.rpc_max_retries,
        max_batch_size=settings.rpc_max_batch_size,
    )


def _chains(registry: Registry, chains: list[str] | None) -> list[str]:
    selected = chains or list(registry.chains)
    unknown = sorted(set(selected) - set(registry.chains))
    if unknown:
        raise typer.BadParameter(f"unknown chain(s): {', '.join(unknown)}")
    return selected


def _migrations_dir(settings: Settings) -> Path:
    if settings.migrations_dir:
        return settings.migrations_dir
    for base in (Path.cwd(), *Path.cwd().parents, *Path(__file__).resolve().parents):
        candidate = base / "supabase" / "migrations"
        if candidate.is_dir():
            return candidate
    raise typer.BadParameter("supabase/migrations not found; set MIGRATIONS_DIR")


# ---------------------------------------------------------------------------- db


@db_app.command("migrate")
def db_migrate() -> None:
    """Apply pending SQL migrations from supabase/migrations."""
    settings = get_settings()
    with Store(settings.database_url) as store:
        applied = store.migrate(_migrations_dir(settings))
    typer.echo(
        f"applied {len(applied)} migration(s)" + (f": {', '.join(applied)}" if applied else "")
    )


# ---------------------------------------------------------------------------- registry


@registry_app.command("show")
def registry_show(
    as_json: Annotated[bool, typer.Option("--json", help="Machine-readable output.")] = False,
) -> None:
    """List every series the indexer samples."""
    registry = load_registry()
    if as_json:
        rows = [
            {
                "series_id": s.series_id,
                "chain": s.chain,
                "contract": s.target,
                "call": s.signature,
                "args": [str(a) for a in s.args],
                "decimals": s.decimals,
                "unit": s.unit,
                "description": s.description,
            }
            for s in registry.series
        ]
        typer.echo(json.dumps(rows, indent=2))
        return
    for market in registry.markets:
        series = [s for s in registry.series if s.market_id == market.id]
        name, vaults = f"{market.id:4} {market.name:10} {market.chain:9}", len(market.vaults)
        typer.echo(f"{name} {vaults:2} vaults  {len(series):3} series")
    typer.echo(f"total: {len(registry.series)} series")


@registry_app.command("verify")
def registry_verify(chain: ChainOpt = None) -> None:
    """Check addresses, decimals, deployment blocks and vault lists on-chain."""
    from loop_indexer.verify import verify_registry

    settings, registry = get_settings(), load_registry()
    rpcs = {c: _rpc(settings, registry, c) for c in _chains(registry, chain)}
    try:
        issues = verify_registry(registry, rpcs)
    finally:
        for rpc in rpcs.values():
            rpc.close()
    for issue in issues:
        typer.echo(f"FAIL {issue}", err=True)
    if issues:
        raise typer.Exit(1)
    typer.echo(f"registry OK ({len(registry.markets)} markets, {len(registry.series)} series)")


# ---------------------------------------------------------------------------- run


@app.command("run")
def run(
    chain: ChainOpt = None,
    interval: Annotated[str, typer.Option(help="Sampling interval, e.g. 1h or 1d.")] = "1h",
    start: Annotated[
        str | None, typer.Option("--from", help="ISO start (default: deploy).")
    ] = None,
    end: Annotated[str | None, typer.Option("--to", help="ISO end (default: head).")] = None,
    force: Annotated[bool, typer.Option(help="Re-sample points already stored.")] = False,
    concurrency: Annotated[int, typer.Option(min=1, max=32)] = 4,
    max_points: Annotated[
        int | None, typer.Option(help="Cap points per chain (useful for smoke tests).")
    ] = None,
) -> None:
    """Snapshot every missing grid point since deployment (idempotent, self-healing)."""
    from loop_indexer.pipeline import Indexer, RunOptions

    settings, registry = get_settings(), load_registry()
    chains = _chains(registry, chain)
    options = RunOptions(
        interval=parse_duration(interval),
        start=parse_time(start) if start else None,
        end=parse_time(end) if end else None,
        force=force,
        concurrency=concurrency,
        max_points=max_points,
        finality_seconds=settings.finality_seconds,
    )
    params = {"chains": chains, "interval": interval, "from": start, "to": end, "force": force}
    with Store(settings.database_url) as store:
        run_id = store.start_run("run", params)
        try:
            results = Indexer(registry, store, lambda c: _rpc(settings, registry, c)).run(
                chains, options
            )
        except Exception as exc:
            store.finish_run(run_id, "failed", {}, error=repr(exc))
            raise
        ok = all(r.ok for r in results)
        stats = {r.chain: r.as_dict() for r in results}
        store.finish_run(run_id, "succeeded" if ok else "partial", stats)
    for r in results:
        typer.echo(f"{r.chain}: {r.completed}/{r.planned} points, {r.topped_up} back-filled, "
                   f"{r.observations} observations, {r.failed_calls} reverted calls, "
                   f"{len(r.failed_hours)} failed points, {r.seconds}s")  # fmt: skip
    if not ok:
        raise typer.Exit(1)


# ---------------------------------------------------------------------------- export


@export_app.command("dune")
def export_dune(
    full: Annotated[bool, typer.Option(help="Clear the Dune table and re-upload all.")] = False,
    batch_size: Annotated[int, typer.Option(min=1, max=500_000)] = 50_000,
    catalogue: Annotated[bool, typer.Option(help="Also refresh catalogue tables.")] = True,
) -> None:
    """Append new observations to Dune (public tables)."""
    from loop_indexer.exporters.dune import DuneClient, DuneExporter

    settings = get_settings()
    if not settings.dune_api_key or not settings.dune_namespace:
        raise typer.BadParameter("DUNE_API_KEY and DUNE_NAMESPACE must be set")
    client = DuneClient(settings.dune_api_key.get_secret_value(), base_url=settings.dune_api_url)
    with Store(settings.database_url) as store:
        run_id = store.start_run("export-dune", {"full": full})
        try:
            exporter = DuneExporter(
                store, client, namespace=settings.dune_namespace, prefix=settings.dune_table_prefix
            )
            if catalogue:
                exporter.export_catalogue()
            stats = exporter.export_observations(full=full, batch_size=batch_size)
        except Exception as exc:
            store.finish_run(run_id, "failed", {}, error=repr(exc))
            raise
        finally:
            client.close()
        store.finish_run(run_id, "succeeded", {"rows": stats.rows, "batches": stats.batches})
    typer.echo(f"exported {stats.rows} rows to dune.{stats.table} in {stats.batches} batch(es)")


@export_app.command("static")
def export_static_cmd(
    out: Annotated[Path, typer.Option(help="Output directory.")] = Path("dashboard/data"),
) -> None:
    """Write end-of-day JSON for the dashboard's no-database mode."""
    from loop_indexer.exporters.static import export_static

    settings, registry = get_settings(), load_registry()
    with Store(settings.database_url) as store:
        files = export_static(store, registry, out)
    typer.echo(f"wrote {len(files)} files to {out}")


# ---------------------------------------------------------------------------- health


@app.command("health")
def health(
    max_lag: Annotated[str, typer.Option(help="Fail if a chain is older than this.")] = "3h",
) -> None:
    """Exit non-zero if any chain's latest snapshot is older than --max-lag."""
    settings, registry = get_settings(), load_registry()
    limit = parse_duration(max_lag)
    with Store(settings.database_url) as store:
        rows = {r["chain_id"]: r for r in store.freshness()}
    stale = False
    for name, chain in registry.chains.items():
        row = rows.get(chain.chain_id)
        if row is None or row["lag"] > limit:
            stale = True
            lag = "never" if row is None else str(row["lag"]).split(".")[0]
            typer.echo(f"STALE {name}: last snapshot {lag} ago", err=True)
        else:
            typer.echo(f"ok    {name}: last snapshot {row['last_snapshot'].isoformat()}")
    if stale:
        raise typer.Exit(1)


def main() -> None:  # pragma: no cover
    sys.exit(app())
