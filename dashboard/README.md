# Loop dashboard

Next.js (App Router) dashboard over the indexer's data.

```bash
npm ci
npm run dev        # http://localhost:3000
```

* **Data source.** With `DATABASE_URL` set, pages read the Postgres views
  (`loop.market_daily`, `loop.vault_daily`, …). Without it, they read the static
  snapshot in `data/`, which you refresh with `make export-static` from the repo root.
  Both sources return identical shapes (`lib/types.ts`).
* **Pages.** `/` overview and findings · `/markets/[id]` charts and vault table ·
  `/data` how to consume the data.
* **API.** `GET /api/markets`, `GET /api/markets/:id`, `GET /api/markets/:id?format=csv`.
* **Charts.** Hand-built SVG (`components/LineChart.tsx`): one axis per chart, a
  crosshair tooltip that lists every series, keyboard navigation, a "view as table"
  fallback, and a validated categorical palette in light and dark themes.

Deploy on Vercel with Root Directory `dashboard/` (see `../docs/deployment.md`), or
self-host with the `Dockerfile` (standalone Next.js server).

```bash
npm run typecheck && npm test && npm run build
```
