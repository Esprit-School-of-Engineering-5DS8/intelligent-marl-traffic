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

## Backend integration seam

There is no HTTP backend in this repository yet; the dashboard currently renders demo data. When the Python/TraCI service is added, the expected endpoints are:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/simulation/state` | Run state, step, KPIs, junction phases |
| `POST` | `/api/simulation/start` | Start a scenario / controller |
| `POST` | `/api/simulation/step` | Advance one simulation step |
| `POST` | `/api/simulation/pause` | Pause the run |
| `POST` | `/api/simulation/stop` | Stop and reset the run |

The UI expects the response shape documented in the main project README (status, step, KPIs, junctions, vehicles). Map access can also be configured from the console:

```js
KEMATARA.setMapToken('pk.eyJ1...');
KEMATARA.focus();
```
