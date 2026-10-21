# SUMO Transportation Operations Dashboard (KEMATARA)

Standalone, framework-free vanilla dashboard. The 3D city map of Monaco is powered by **Mapbox GL JS** with the SUMO traffic simulation overlaid on top.

## 3D city map (Mapbox GL)

- `mapbox-gl` (`dark-v11` style) renders the Principality with extruded 3D buildings (`fill-extrusion`, `composite/building` source layer). Buildings fade out below zoom 13 (LOD).
- Camera: pitch 62°, bearing −28°, centered on Monaco/MoST at **43.7384, 7.4246 (WGS84)**, with a custom fog + light rig for the dusk ambiance. A `3D / 2D` HUD toggle flips between pitched and top-down camera; the choice persists in `localStorage` under `kematara.mapMode`.
- `NavigationControl` (with pitch visualization) sits top-right; a metric `ScaleControl` sits bottom-right.

### Mapbox access token

Mapbox GL requires an access token. Provide it in any of these ways (checked in this order):

1. `localStorage.kematara.mapboxToken` — populated by the token panel shown on first load ("Connect"), or `KEMATARA.setMapToken('<token>')` in the console.
2. `VITE_MAPBOX_TOKEN` in `frontend/.env` — recommended for local dev:
   ```
   VITE_MAPBOX_TOKEN=pk.eyJ1...
   ```
3. `window.MAPBOX_TOKEN` — for embedded production bundles.

If no/no-valid token is provided, a non-blocking token panel appears over the map and the rest of the dashboard stays usable.

## SUMO traffic overlay

The real Monaco MoST road network is served from `public/monaco-network.json`, generated from `scenarios/monaco/in/most.net.xml` (SUMO Traffic (MoST) Scenario, Codeca & Härri, VNC 2017). Regenerate after network changes, from the repo root:

```bash
python frontend/scripts/extract_monaco_network.py
```

The extractor georeferences the UTM zone 32N net coordinates to WGS84 with `pyproj` and emits 460 driving edges + the 12 signalized (TLS) junctions (≈0.11 MB).

Overlay features:

- `sumo-roads-base` — network road geometry (width by lane count).
- `sumo-roads-glow` / `sumo-roads-heat` — congestion heat map per edge (teal → amber → red), driven by the edge `q` property.
- `sumo-vehicles` — animated vehicles following real edge polylines. Demo mode spawns up to 140 vehicles that walk a junction graph route and slow down as local congestion rises. Click a vehicle dot for a popup.
- `sumo-tls` — TLS junction disks (J1–J4) colored by queue length, with click-to-focus labels anchored on the nearest real TLS junction.
- The overlay is driven by the existing Run / Pause / Step / Stop control bar (1 step = 1 s). Pausing freezes vehicles in place; Stop clears them.

### Live data seam

`window.KEMATARA.applySimState({ step, junctions, vehicles })` replaces the demo state:

```js
// vehicle positions are absolute indices into monaco-network.json edges
window.KEMATARA.applySimState({
  step: 128,
  junctions: [{ id: 'J1', queue: 7, phase: 'Through' }],
  vehicles: [{ edge: 121, position: 0.42, speed: 11.2, type: 'car' }]
});
```

Point this at a Python/TraCI bridge (see the API integration seam below) and the map shows real SUMO vehicles instead of the demo simulation.

## Run locally

From this directory:

```bash
npm install
npm install-scripts approve esbuild @esbuild/win32-x64
npm run dev
```

For a production build, run `npm run build`, then `npm run preview`.

Mapbox tiles and the `mapbox-network.json` overlay require network access / the generated file. Leaflet has been removed; Mapbox GL is the only map npm UI library in use.

## API integration seam

Replace the event handlers and `state` object in `app.js` with a small adapter that calls the Python/TraCI service. The UI expects these future endpoints:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/simulation/state` | Connection, run state, step, KPIs, junction phases |
| `POST` | `/api/simulation/start` | Start a configured scenario/controller |
| `POST` | `/api/simulation/step` | Advance one simulation step |
| `POST` | `/api/simulation/pause` | Pause the current run |
| `POST` | `/api/simulation/stop` | Stop and optionally reset the run |

Suggested response shape:

```json
{
  "status": "running",
  "scenario": "Monaco / MoST",
  "step": 128,
  "total_steps": 3600,
  "kpis": { "average_speed": 31.8, "waiting_time": 1284, "throughput": 742, "co2": 18.4 },
  "junctions": [{ "id": "J1", "name": "Casino", "phase": 3, "phase_name": "Through", "queue": 4 }],
  "vehicles": [{ "edge": 121, "position": 0.42, "speed": 11.2, "type": "car" }]
}
```

The backend should enable CORS for the dev origin or proxy `/api` through Vite.
