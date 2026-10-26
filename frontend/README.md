# KEMETRA Transportation Operations Dashboard

Standalone Vite + vanilla JS dashboard styled to match the KEMETRA operations reference. The layout is responsive and keeps the two-column desktop composition: map on the left, traffic insights and incident detail on the right.

## UI composition

- **Sidebar** — KEMETRA brand, primary navigation (Dashboard, Live Map, Events, Optimize, Predict, Message, Rules Engine, Permissions, Settings), and Store / Get Help.
- **Top bar** — location switcher for **Central Austin**, Overview / Device log / Settings tabs, notifications, and the operator account card.
- **Map** — Mapbox GL `light-v11` street map centered on **East 7th & Comal, Austin**, with a green focus marker and custom zoom / reset controls.
- **Traffic Insights** — vehicle count (VEH) and speed (MPH) cards with average / max / min legends and SVG trend charts.
- **Events / CTECC** — accident severity summary, event facts, and department dispatch statuses.
- **Key Metrics** — camera, V2X, signal, conflict, accident, and flood counters.

The previous Material 3 stylesheet and the 3D/SUMO overlay HUD have been removed. The visual language is now the light KEMETRA dashboard from the reference image.

## Mapbox token

Mapbox GL requires an access token. The dashboard checks, in order:

1. `localStorage.kematara.mapboxToken` — set by the token panel or `KEMATARA.setMapToken('<token>')`.
2. `VITE_MAPBOX_TOKEN` in `frontend/.env`.
3. `window.MAPBOX_TOKEN`.

If no valid token is available, the map area shows an offline state and the rest of the dashboard stays usable.

## Run locally

From this directory:

```bash
npm install
npm run dev
```

Production build and preview:

```bash
npm run build
npm run preview
```

## Backend

The FastAPI backend lives at `api/` in the repository root. Start it first:

```bash
# from the repository root
uvicorn api.main:app --port 8000
```

Vite proxies `/api` and `/ws` to `http://127.0.0.1:8000` (see `vite.config.js`), so the dev
server needs no absolute URLs. The dashboard reads exported result files in two modes:

- `mock` — `public/data/*.json`, bundled; no backend needed;
- `live` — the same files served by `GET /api/data/{path}`.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | liveness |
| `GET` | `/api/data/{path}` | exported result files (same JSON as `public/data`) |
| `GET` | `/api/simulation/state` | live run snapshot |
| `POST` | `/api/simulation/start` \| `pause` \| `resume` \| `step` \| `stop` \| `speed` | live controls |
| `PUT` | `/api/policy` | active control policy (method + checkpoint) |

Architecture and the controller catalog: [../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).

### Two entries (migrating)

`index.html` currently loads `app.js` (vanilla control room). The React SPA in `src/`
(`main.tsx` → `src/app/router.tsx`) is built but not yet the entry; `benchmark-rami.jsx`
embeds four of its pages inside the benchmark tab. The switch happens once the live map
reaches parity — see the roadmap in `docs/ARCHITECTURE.md` §7.

Map access can also be configured from the console:

```js
KEMATARA.setMapToken('pk.eyJ1...');
KEMATARA.focus();
```
