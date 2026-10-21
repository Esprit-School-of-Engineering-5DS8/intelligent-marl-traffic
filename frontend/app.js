import mapboxgl from 'mapbox-gl';
import 'mapbox-gl/dist/mapbox-gl.css';

const $ = (id) => document.getElementById(id);
const MONACO_CENTER = [7.4246, 43.7384];
const MAX_VEHICLES = 140;

const JUNCTIONS = [
  { id: 'J1', name: 'Casino', near: [7.4273, 43.7397], phase: 'Through', queue: 4 },
  { id: 'J2', name: 'Port Hercule', near: [7.4215, 43.7359], phase: 'Left turn', queue: 11 },
  { id: 'J3', name: 'Larvotto', near: [7.4317, 43.7473], phase: 'Crossing', queue: 24 },
  { id: 'J4', name: 'Fontvieille', near: [7.4154, 43.7274], phase: 'Right turn', queue: 7 }
];

const state = { running: false, paused: false, step: 0, timer: null, scenario: 'Monaco / MoST', controller: 'Max Pressure RL' };

const toast = (message) => {
  const node = $('toast');
  node.textContent = message;
  node.classList.add('show');
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => node.classList.remove('show'), 2200);
};

const haversine = (a, b) => {
  const R = 6371000;
  const dLat = ((b[1] - a[1]) * Math.PI) / 180;
  const dLon = ((b[0] - a[0]) * Math.PI) / 180;
  const s = Math.sin(dLat / 2) ** 2 + Math.cos((a[1] * Math.PI) / 180) * Math.cos((b[1] * Math.PI) / 180) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(s));
};

let net = null;
let roadFeatures = [];
let edgeByFrom = new Map();
let vehicles = [];
let junctionMarkers = [];
let map = null;
let mapMode = localStorage.getItem('kematara.mapMode') || '3d';
let overlayReady = false;
const junctionsTaken = new Set();

function render() {
  $('runBtn').disabled = state.running && !state.paused;
  $('pauseBtn').disabled = !state.running;
  $('stopBtn').disabled = !state.running && state.step === 0;
  $('runStatus').textContent = state.running ? (state.paused ? 'Paused · SUMO MoST overlay' : 'Running · SUMO MoST overlay') : 'Standby · SUMO MoST overlay';
  $('timeMetric').textContent = new Date(state.step * 1000).toISOString().substring(11, 19);
  const activeVehicles = vehicles.length ? `${vehicles.length.toLocaleString()} · ` : '';
  $('waitMetric').firstChild.textContent = `${activeVehicles}${Math.max(0, 1284 - state.step * 2).toLocaleString()} `;
  $('updatedAt').textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function prepareNetwork() {
  roadFeatures = net.edges.map((edge) => ({
    type: 'Feature',
    geometry: { type: 'LineString', coordinates: edge.c },
    properties: { id: edge.id, lanes: edge.lanes, speed: edge.speed, q: 0 }
  }));
  edgeByFrom = new Map();
  net.edges.forEach((edge, index) => {
    if (!edgeByFrom.has(edge.from)) edgeByFrom.set(edge.from, []);
    edgeByFrom.get(edge.from).push(index);
  });
  const tls = net.junctions.filter((j) => j.tls);
  JUNCTIONS.forEach((junction) => {
    const nearest = tls
      .filter((j) => !junctionsTaken.has(j.id))
      .sort((a, b) => haversine(a.c, junction.near) - haversine(b.c, junction.near))[0];
    if (!nearest) return;
    junctionsTaken.add(nearest.id);
    junction.c = nearest.c;
    junction.tlsId = nearest.id;
  });
}

function spawnVehicle() {
  const startEdge = Math.floor(Math.random() * net.edges.length);
  vehicles.push({
    path: [startEdge],
    i: 0,
    t: 0,
    len: net.edges[startEdge].len,
    sf: 0.65 + Math.random() * 0.35,
    type: Math.random() < 0.08 ? 'bus' : 'car'
  });
}

function pointOnEdge(edge, vehicle) {
  const coords = edge.c;
  let remaining = Math.min(0.999, Math.max(0, vehicle.t)) * edge.len;
  for (let i = 1; i < coords.length; i++) {
    const segLen = haversine(coords[i - 1], coords[i]);
    if (remaining <= segLen || i === coords.length - 1) {
      const f = segLen ? remaining / segLen : 0;
      return [coords[i - 1][0] + (coords[i][0] - coords[i - 1][0]) * f, coords[i - 1][1] + (coords[i][1] - coords[i - 1][1]) * f];
    }
    remaining -= segLen;
  }
  return coords[0];
}

function pickNextEdge(edgeIdx) {
  const options = edgeByFrom.get(net.edges[edgeIdx].to) || [];
  if (!options.length) return -1;
  const forward = options.filter((e) => net.edges[e].to !== net.edges[edgeIdx].from);
  const pool = forward.length ? forward : options;
  return pool[Math.floor(Math.random() * pool.length)];
}

function advanceVehicles() {
  const active = state.running && !state.paused;
  if (active && net) for (let i = 0; i < 2 && vehicles.length < MAX_VEHICLES; i++) spawnVehicle();
  const traffic = new Map();
  for (const vehicle of vehicles) traffic.set(vehicle.path[vehicle.i], (traffic.get(vehicle.path[vehicle.i]) || 0) + 1);
  roadFeatures.forEach((feature, index) => {
    const n = traffic.get(index) || 0;
    feature.properties.q = n ? Math.min(1, n / ((net.edges[index].lanes || 1) * 3)) : 0;
  });

  const vehicleFC = {
    type: 'FeatureCollection',
    features: vehicles.map((vehicle) => {
      const edgeIdx = vehicle.path[vehicle.i];
      const edge = net.edges[edgeIdx];
      const q = roadFeatures[edgeIdx].properties.q;
      const speed = Math.min(edge.speed * vehicle.sf, edge.speed * (1 - 0.75 * q) + 0.3);
      if (active) vehicle.t += speed / vehicle.len;
      return {
        type: 'Feature',
        geometry: { type: 'Point', coordinates: pointOnEdge(edge, vehicle) },
        properties: { color: q < 0.34 ? '#2dd4bf' : q < 0.67 ? '#facc15' : '#ef4444', type: vehicle.type }
      };
    })
  };

  if (active) {
    for (let i = vehicles.length - 1; i >= 0; i--) {
      const vehicle = vehicles[i];
      if (vehicle.t < 1) continue;
      const nextIdx = pickNextEdge(vehicle.path[vehicle.i]);
      if (nextIdx === -1) {
        vehicles.splice(i, 1);
        continue;
      }
      vehicle.path.push(nextIdx);
      vehicle.i++;
      vehicle.t = 0;
      vehicle.len = net.edges[nextIdx].len;
    }
  }
  return vehicleFC;
}

function junctionQueueOf(junction, index) {
  const wave = Math.sin(state.step / 9 + index) * 6 + Math.sin(state.step / 23 + index * 2.7) * 4;
  return Math.max(0, Math.min(40, Math.round(junction.queue + wave)));
}

function junctionFC() {
  return {
    type: 'FeatureCollection',
    features: JUNCTIONS.filter((j) => j.c).map((junction, index) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: junction.c },
      properties: { q: junctionQueueOf(junction, index) / 40, id: junction.id }
    }))
  };
}

function updateOverlay() {
  const vehicleFC = net ? advanceVehicles() : { type: 'FeatureCollection', features: [] };
  if (!map || !overlayReady || !map.isStyleLoaded()) return;
  map.getSource('sumo-roads').setData({ type: 'FeatureCollection', features: roadFeatures });
  map.getSource('sumo-vehicles').setData(vehicleFC);
  map.getSource('sumo-tls').setData(junctionFC());
  JUNCTIONS.forEach((junction, index) => {
    const marker = junctionMarkers[index];
    if (marker) marker.badge.textContent = `Q ${junctionQueueOf(junction, index)}`;
  });
}

function initMapPrep() {
  map.on('load', () => {
    map.setLight({ anchor: 'map', color: '#9db4d9', intensity: 0.42, position: [1.6, 80, 84] });
    map.setFog({ color: '#101828', 'high-color': '#1b2b4d', horizonColor: '#2b3a55', spaceColor: '#0b1120', 'horizon-blend': 0.42, range: [0.8, 8] });
    applyCamera(mapMode, false);
    overlayInit();
    if (overlayReady) applyCamera(mapMode, mapMode === '2d');
  });
  map.on('click', 'vehicle-core', (event) => {
    const feature = event.features[0];
    new mapboxgl.Popup({ offset: 8, closeButton: false })
      .setLngLat(feature.geometry.coordinates)
      .setHTML(`<strong>SUMO vehicle</strong><br>Type: ${feature.properties.type}`)
      .addTo(map);
  });
  map.on('mouseenter', 'vehicle-core', () => { map.getCanvas().style.cursor = 'pointer'; });
  map.on('mouseleave', 'vehicle-core', () => { map.getCanvas().style.cursor = ''; });
}

function applyBuildingLOD() {
  map.on('zoom', () => {
    if (!overlayReady) return;
    map.setPaintProperty('3d-city-buildings', 'fill-extrusion-opacity', map.getZoom() < 13 ? 0 : 0.94);
  });
}

function applyCamera(mode, fly = true) {
  mapMode = mode;
  localStorage.setItem('kematara.mapMode', mode);
  document.querySelectorAll('[data-map-mode]').forEach((button) => button.classList.toggle('active', button.dataset.mapMode === mode));
  if (!fly || !map || !map.isStyleLoaded()) return;
  map.jumpTo({
    center: MONACO_CENTER,
    zoom: mode === '2d' ? 14.6 : 15.6,
    pitch: mode === '2d' ? 0 : 65,
    bearing: mode === '2d' ? 0 : -28
  });
}

function step() {
  state.step++;
  updateOverlay();
  render();
}

$('runBtn').addEventListener('click', () => {
  state.running = true;
  state.paused = false;
  clearInterval(state.timer);
  state.timer = setInterval(step, 1000);
  toast('Simulation started · SUMO MoST overlay live');
  render();
});
$('pauseBtn').addEventListener('click', () => {
  state.paused = !state.paused;
  if (state.paused) clearInterval(state.timer);
  else state.timer = setInterval(step, 1000);
  toast(state.paused ? 'Simulation paused' : 'Simulation resumed');
  render();
});
$('stopBtn').addEventListener('click', () => {
  state.running = false;
  state.paused = false;
  clearInterval(state.timer);
  state.step = 0;
  vehicles = [];
  roadFeatures.forEach((feature) => { feature.properties.q = 0; });
  updateOverlay();
  toast('Simulation stopped · overlay cleared');
  render();
});
$('stepBtn').addEventListener('click', () => { step(); toast('Advanced one simulation step'); });
$('refreshBtn').addEventListener('click', () => {
  state.step++;
  if (state.running && !state.paused) updateOverlay();
  $('updatedAt').textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  if (map && map.isStyleLoaded()) map.flyTo({ center: MONACO_CENTER, zoom: mapMode === '2d' ? 14.6 : 15.6, pitch: mapMode === '2d' ? 0 : 65, bearing: mapMode === '2d' ? 0 : -28, duration: 1400 });
  toast('Network state refreshed');
  render();
});
$('changeRange').addEventListener('click', () => toast('Chart range reset to the latest 3 hours'));
$('apiBtn').addEventListener('click', () => { $('apiNotes').hidden = !$('apiNotes').hidden; $('apiBtn').setAttribute('aria-expanded', String(!$('apiNotes').hidden)); });
$('scenario').addEventListener('change', (event) => { state.scenario = event.target.value; toast(`Scenario: ${state.scenario}`); });
$('controller').addEventListener('change', (event) => { state.controller = event.target.value; toast(`Controller: ${state.controller}`); });

function setTab(tab) {
  document.querySelectorAll('[data-tab]').forEach((item) => {
    const active = item.dataset.tab === tab;
    item.classList.toggle('active', active);
    if (item.getAttribute('role') === 'tab') item.setAttribute('aria-selected', String(active));
  });
  toast(`${tab} selected`);
}
document.querySelectorAll('[data-tab]').forEach((item) => item.addEventListener('click', () => setTab(item.dataset.tab)));

document.querySelectorAll('[data-map-mode]').forEach((button) => {
  button.addEventListener('click', () => {
    if (!map || !overlayReady) {
      showTokenPanel('Connect a Mapbox token first to control the 3D camera.');
      return;
    }
    applyCamera(button.dataset.mapMode);
    toast(button.dataset.mapMode === '2d' ? 'Top-down ortho view' : '3D city view');
    render();
  });
});

function resolveToken() {
  return localStorage.getItem('kematara.mapboxToken') || import.meta.env.VITE_MAPBOX_TOKEN || window.MAPBOX_TOKEN || '';
}

function showTokenPanel(message) {
  const panel = $('tokenPanel');
  if (!panel) return;
  panel.hidden = false;
  const note = panel.querySelector('.token-message');
  if (note) note.textContent = message || 'A Mapbox access token is required for the 3D city view.';
}

function hideTokenPanel() {
  const panel = $('tokenPanel');
  if (panel) panel.hidden = true;
}

function prepareMap(token) {
  mapboxgl.accessToken = token;
  map = new mapboxgl.Map({
    container: 'sumoMap',
    center: MONACO_CENTER,
    zoom: mapMode === '2d' ? 14.6 : 15.2,
    pitch: mapMode === '2d' ? 0 : 62,
    bearing: mapMode === '2d' ? 0 : -28,
    antialias: true,
    attributionControl: 'compact',
    style: 'mapbox://styles/mapbox/dark-v11'
  });
  map.addControl(new mapboxgl.NavigationControl({ visualizePitch: true }), 'top-right');
  map.addControl(new mapboxgl.ScaleControl({ unit: 'metric' }), 'bottom-right');
  map.on('error', (event) => {
    const message = event && event.error && event.error.message ? String(event.error.message) : '';
    if (/token|401|unauthorized|not authorized/i.test(message)) showTokenPanel(message);
    else console.warn('Mapbox error', event && event.error);
  });
  initMapPrep();
  applyBuildingLOD();
}

document.querySelectorAll('[data-map-mode]').forEach((button) => button.classList.toggle('active', button.dataset.mapMode === mapMode));

if ($('tokenSave')) $('tokenSave').addEventListener('click', () => {
  const value = $('tokenInput').value.trim();
  if (!value) {
    $('tokenInput').focus();
    return;
  }
  localStorage.setItem('kematara.mapboxToken', value);
  hideTokenPanel();
  prepareMap(value);
  toast('Mapbox connected · 3D city loading');
});

if ($('tokenSkip')) $('tokenSkip').addEventListener('click', () => {
  hideTokenPanel();
  $('sumoMap').innerHTML = '<div class="map-fallback">3D city view disabled. SUMO state remains available.<br>Set <code>VITE_MAPBOX_TOKEN</code> in frontend/.env and reload.</div>';
});

const MAPBOX_TOKEN = resolveToken();
if (MAPBOX_TOKEN) prepareMap(MAPBOX_TOKEN);
else showTokenPanel();

fetch('./monaco-network.json')
  .then((response) => {
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  })
  .then((data) => {
    net = data;
    prepareNetwork();
    updateOverlay();
    render();
  })
  .catch((error) => {
    console.warn('Monaco network overlay failed to load', error);
    const caption = document.querySelector('.map-caption');
    if (caption) caption.textContent = '12 active junctions · Monaco · SUMO overlay offline';
  });

window.KEMATARA = {
  applySimState({ step, junctions, vehicles: liveVehicles } = {}) {
    if (typeof step === 'number') state.step = step;
    if (Array.isArray(junctions)) {
      junctions.forEach((j) => {
        const known = JUNCTIONS.find((k) => k.id === j.id);
        if (known) {
          known.queue = j.queue || 0;
          if (j.phase) known.phase = j.phase;
        }
      });
    }
    if (Array.isArray(liveVehicles) && net) {
      vehicles = liveVehicles
        .filter((v) => Number.isInteger(v.edge) && net.edges[v.edge])
        .map((v) => ({
          path: [v.edge],
          i: 0,
          t: Math.min(0.999, Math.max(0, v.position || 0)),
          len: net.edges[v.edge].len,
          sf: v.speed || 1,
          type: v.type || 'car'
        }));
    }
    updateOverlay();
    render();
  },
  setMapToken(token) {
    localStorage.setItem('kematara.mapboxToken', token);
    hideTokenPanel();
    prepareMap(token);
    toast('Mapbox connected · 3D city loading');
  }
};

render();
