## What and why

<!-- What does this change, and why? Link the issue if there is one. -->

## How it was tested

<!-- Commands run, data checked, screenshots for UI changes. -->

## Checklist

- [ ] `make lint` and `make test` pass
- [ ] Data changes come with a test, and a note on why the old value was wrong
- [ ] New migrations are additive (applied migrations are never edited) and mirrored in `dune/queries/` when they change a metric
- [ ] Docs updated (`docs/`, README) where behaviour or setup changed
