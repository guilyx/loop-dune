# Changelog

Notable changes, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

### Added
- Documentation site (MkDocs Material) published to GitHub Pages, with a dashboard
  feature tour, API, CLI and Dune references, and an embedded demo video.
- A reproducible demo-video recorder (`scripts/record-demo.mjs`).
- Community files: contributing guide, security policy, code of conduct, issue and pull
  request templates, CODEOWNERS, `.editorconfig`, pre-commit hooks.
- CodeQL scanning, workflow linting (actionlint), and smoke tests that start each Docker
  image in CI.

### Changed
- The indexer image builds and runs on the same Python base image, so base-image
  updates can no longer leave packages built for another Python version.

## 2026-11-02 · Single-VPS deployment and backups ([#11](https://github.com/guilyx/loopscan/pull/11))

### Added
- `deploy/vps`: Docker Compose stack (Postgres, scheduled indexer, dashboard behind
  Caddy with automatic HTTPS, backups), `bootstrap.sh` server provisioning, `stack.sh`.
- Daily age-encrypted `pg_dump` backups with offsite copies, retention, a weekly CI
  restore drill and a full backup → restore round trip in CI.
- `release.yml`: images published to GHCR by commit SHA, optional SSH deploy and
  rollback.
- `loop-indexer schedule` for long-running hosts; `POST /api/revalidate` for instant
  dashboard refreshes.

### Changed
- Dependency and GitHub Actions updates from Dependabot (#2, #3, #5–#10).

## 2026-11-02 · Rebuild ([#1](https://github.com/guilyx/loopscan/pull/1))

### Added
- Hourly state indexer (Multicall3, on-chain-verified registry, self-healing runs).
- Postgres schema and analytics views; public Dune tables and queries.
- Next.js dashboard with five analysis tabs, a stress test and a JSON/CSV API.
