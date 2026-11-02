# Review of the legacy pipeline (November 2026)

This is the audit that led to the rewrite. The legacy code and the CSVs it produced are
preserved in git history (last legacy commit: `58ffcc9`).

## Verdict

The pipeline had stopped producing data (the last rows were from 3–4 June 2025), and
several defects made it unrecoverable by patching. The data it had produced contained
systematic errors. Everything was rebuilt. Only the contract addresses (re-verified
on-chain) and three ABIs were kept.

## Why nothing was updating

| Problem | Where (legacy) |
|---|---|
| Only BTC was collected. ETH, USD and BNB were never run. | `scripts/collect_and_upload.py:22` (`ASSETS = ["BTC"]`) |
| The Docker image could not build: a nonexistent Poetry group, and missing ABI folders. | `Dockerfile:38`, `Dockerfile:51` |
| Dune `/v1/table/*` endpoints were deprecated, with removal set for 1 March 2026. | `dune_uploader.py:78`, `sync.py:126,188` |
| Etherscan's free tier dropped BNB Chain, so creation-block lookups failed every run. | `collector.py:247` |
| The upload CLI passed the namespace as the table name. | `dune_uploader.py:186` |
| `loop-sync` called the collector with arguments that don't exist (TypeError) and read env vars that were never set. | `sync.py:243-248`, `sync.py:62` |
| Errors were printed and the process exited 0, so nothing alerted. | throughout |

## Data quality

* 10 of the 16 CDP vaults registered on the pools were never tracked, including vaults
  carrying debt.
* The BNB pool's per-vault metrics queried an Ethereum vault address, so they were always 0.
* Resuming at `last_block + 1` created 4–21 near-duplicate rows per file. The sampling
  interval also changed mid-history (3,500 → 2,000 blocks; 14,000 → 12,000), and it was
  block-based, so chains could not be aligned in time.
* Values were stored as raw uint256 strings with no decimals: USDC (6) and WETH (18)
  were indistinguishable, and vault debt is WAD even on USDC.
* Timestamps used the host's local timezone and two formats.
* One metric was split across two columns, and five orphan CSVs (including a misspelled
  duplicate) matched no configuration.
* Failed calls were skipped silently, and the gaps were never refilled.

## Engineering

* Three dependency manifests that disagreed, and a gitignored lockfile.
* "Parallel" workers all shared one RPC connection. No batching, no retries.
* 11 tests at 28% coverage, all against a non-production code path, with everything
  mocked. That is how the crash above went unnoticed.
* `eval()` of a source file, an unused 4.8k-line JSON config, and a Streamlit page that
  could not run.

## What replaced it

See [architecture.md](architecture.md). In short: a typed, chain-verified registry;
an hourly UTC grid; Multicall3 snapshots; Postgres as the source of truth; idempotent,
self-healing runs; at-least-once Dune export via the current Uploads API; a dashboard;
and 54 indexer tests (91% coverage) running against an in-memory EVM and a real Postgres.
