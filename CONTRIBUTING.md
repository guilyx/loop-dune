# Contributing

Thanks for helping. Bug reports, data corrections, new metrics and docs fixes are all
welcome.

## Ground rules

* **Open an issue first** for anything larger than a small fix, so we can agree on the
  approach before you write code.
* **Data correctness comes first.** A change that alters numbers needs a test that pins
  the new behaviour, and a note in the PR on why the old value was wrong.
* **Keep PRs focused.** One change per PR, with a description of what and why.

## Setup

Requirements: [uv](https://docs.astral.sh/uv/), Node 20+, Docker (or Postgres ≥ 14).

```bash
cp .env.example .env    # archive RPC URLs (public ones work for small backfills)
make setup              # Python + Node dependencies
make db migrate         # local Postgres + schema
pre-commit install      # optional: run the linters on every commit
```

## Checks

Run what CI runs before pushing:

```bash
make lint   # ruff, ruff format, mypy --strict, tsc
make test   # pytest (+ Postgres suite with TEST_DATABASE_URL) and vitest
make docs   # build the documentation site with --strict
```

CI also builds the Docker images, smoke-runs them, runs shellcheck on the deploy
scripts, and does a full backup → restore round trip.

## Where things live

| Change | Where |
|---|---|
| A contract, vault or market | `indexer/src/loop_indexer/markets.yaml`, then `loop-indexer registry verify` |
| A new metric for every pool or vault | the series templates in `indexer/src/loop_indexer/registry.py` |
| A derived metric | a new migration in `supabase/migrations/` (never edit an applied one), mirrored in `dune/queries/` |
| A chart or tab | `dashboard/components/` |
| Docs | `docs/` (published to the documentation site) |

## Commits and pull requests

* Write commit messages in the imperative ("Add vault capacity view"), with a body
  explaining why when it is not obvious.
* Fill in the pull request template. Screenshots for UI changes.
* By contributing, you agree that your work is licensed under the
  [GPL-3.0](https://github.com/guilyx/loop-dune/blob/master/LICENSE).

## Code of conduct

Be kind and constructive. See the [Code of Conduct](https://github.com/guilyx/loop-dune/blob/master/CODE_OF_CONDUCT.md).
