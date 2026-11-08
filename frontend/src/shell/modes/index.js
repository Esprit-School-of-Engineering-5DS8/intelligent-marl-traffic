/**
 * Live-map modes: Optimize · Predict · Roam.
 *
 * One controller, one store, three panel systems. The Events tab keeps the
 * existing dashboard untouched; switching tabs crossfades the mode layer in
 * and swaps what the map and timeline show.
 */

import { modeData, formatClock } from './data.js';
import {
  bypassFor,
  geometryFor,
  geometryState,
  junctionApproaches,
  loadGeometry,
  metersBetween,
  nearestEdge,
  routeBetween,
  routeFeature
} from './geometry.js';
import {
  applySignalChange,
  forecastState,
  getLiveHistory,
  getLiveRunId,
  getLiveState,
  isLive,
  liveEfficiency,
  liveForecast,
  liveLoad,
  liveMetrics,
  refreshForecast,
  setLiveState,
} from './live.js';

const STORAGE_KEY = 'sumo.liveModes.v1';

const state = {
  mode: 'events',
  zone: 'sec-6',
  minute: 0,
  previewId: null,
  applied: new Set(),
  dismissed: new Set(),
  inputs: new Set(),
  compareTypical: true,
  panelsPreset: 'full',
  panelCollapsed: false,
  followMode: false,
  povMode: false,
  followVehicleId: null,
  roamClass: '',
  sigDrafts: new Map(),
  forecastMinute: null,
  hiddenPanels: new Set(),
  // Predict's trip estimator: two points picked on the map.
  etaA: null,
  etaB: null,
  etaPick: null
};

let map = null;
let getMap = () => null;
let showToast = () => {};
let lastRenderedMode = '';
let modeLayerExitTimer = 0;
let dockSwapTimer = 0;
let styleHooked = false;
let clickHooked = false;
let lastRunId = null;
let getScenario = () => null;

const MODE_LAYER_EXIT_MS = 620;
const DOCK_SWAP_MS = 760;

/* ------------------------------------------------------------------ helpers */

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const prefersReducedMotion = () =>
  window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;

function saveState() {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        zone: state.zone,
        applied: [...state.applied],
        dismissed: [...state.dismissed],
        inputs: [...state.inputs],
        compareTypical: state.compareTypical,
        panelsPreset: state.panelsPreset
      })
    );
  } catch {
    /* storage may be unavailable — the UI still works in-memory */
  }
}

function loadState() {
  try {
    const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
    if (raw.zone) state.zone = raw.zone;
    if (Array.isArray(raw.applied)) state.applied = new Set(raw.applied);
    if (Array.isArray(raw.dismissed)) state.dismissed = new Set(raw.dismissed);
    if (Array.isArray(raw.inputs)) state.inputs = new Set(raw.inputs);
    if (typeof raw.compareTypical === 'boolean') state.compareTypical = raw.compareTypical;
    if (raw.panelsPreset) state.panelsPreset = raw.panelsPreset;
  } catch {
    /* ignore malformed storage */
  }
}

const clock = (minute) => formatClock(minute);

const SCENARIO_LABELS = {
  'grid-2x2': 'SF Mission 2x2',
  'grid-3x3': 'SF Mission 3x3',
  monaco: 'Monaco',
  tunis: 'Tunis'
};

/* The panel "now" is the run's own clock while live; the scrubber only drives the
   deterministic demo model. */
function nowMinute() {
  const live = getLiveState();
  const seconds = Number(live?.simulationTime);
  if (isLive() && Number.isFinite(seconds)) return Math.floor(seconds / 60) % 1440;
  return state.minute;
}

function zoneLabel() {
  const scenario = getLiveState()?.scenario;
  if (isLive() && scenario) return SCENARIO_LABELS[scenario] || scenario;
  return 'Sector 6';
}

function runStatusLabel() {
  const status = String(getLiveState()?.status || 'idle');
  if (!isLive()) return 'model';
  return status === 'paused' ? 'paused' : 'live';
}

const KIND_LABELS = {
  signal: 'Signal',
  reroute: 'Reroute',
  ramp: 'Ramp meter',
  transit: 'Transit'
};

/* Shared panel chrome: eyebrow, headline, and the summary strip that carries
   the one number the operator should see before reading any row. */
function panelHead({
  icon,
  label,
  title,
  sub,
  badge,
  collapseLabel,
  summaryLabel,
  summaryValue,
  summaryUnit,
  summaryMeta
}) {
  return `
    <header class="mp-head">
      <div class="mp-eyebrow">
        <span class="mp-system"><svg class="ico" aria-hidden="true"><use href="#${icon}"/></svg>${label}</span>
        <span class="mp-clock">${runStatusLabel()} · ${clock(nowMinute())}</span>
      </div>
      <div class="mp-headline">
        <div class="mp-heading">
          <h2 class="mp-title">${title}</h2>
          <p class="mp-sub">${sub}</p>
        </div>
        <div class="mp-head-tools">
          <span class="mp-count" title="${title}">${badge}</span>
          <button type="button" class="mp-icon-btn" data-panel-collapse aria-label="${collapseLabel}" title="Collapse panel"><svg class="ico"><use href="#i-minus"/></svg></button>
        </div>
      </div>
      <div class="mp-summary">
        <span class="mp-summary-label">${summaryLabel}</span>
        <strong class="mp-summary-value">${summaryValue}<small>${summaryUnit}</small></strong>
        <span class="mp-summary-meta">${summaryMeta}</span>
      </div>
    </header>`;
}

/* ------------------------------------------------------------------ map ops */

/* The corridor congestion / reroute lines that used to be painted here came from
   the mock provider (a hardcoded Monaco polyline), so they drew a road the run was
   not simulating. The modes now draw only measured geometry: Optimize's preview
   lines and Predict's routed trip both come from the loaded network (geometry.js). */

/* -------------------------------------------------- Optimize preview geometry */

/* The preview draws the road the run is actually changing: the junction's inbound
   approaches, a lamp for every controlled lane in its live phase colour, and the
   alternative that reaches the same downstream point without those approaches. */

let previewCache = { key: null, value: null };

function previewRecommendation() {
  if (!state.previewId) return null;
  return (
    modeData
      .recommendations(state.zone, nowMinute())
      .find((rec) => rec.id === state.previewId) || null
  );
}

function signalLampState(stateString, linkIndices) {
  if (!stateString) return null;
  const chars = (linkIndices || []).map((index) => stateString[index]).filter(Boolean);
  if (chars.some((value) => value === 'G' || value === 'g')) return 'green';
  if (chars.some((value) => value === 'y' || value === 'Y')) return 'amber';
  return chars.length ? 'red' : null;
}

function previewContext(rec) {
  const empty = { roads: [], signals: '', bypass: null, note: '' };
  if (!rec?.junction) return empty;
  const scenario = getLiveState()?.scenario;
  const key = `${getLiveRunId()}:${scenario}:${rec.junction}:${rec.green}`;
  if (previewCache.key === key) return previewCache.value;
  const geometry = geometryFor(scenario);
  if (!geometry) {
    const { pending } = geometryState(scenario);
    return {
      ...empty,
      note: pending ? 'Loading the corridor geometry…' : 'Corridor geometry is not loaded.'
    };
  }
  const approaches = junctionApproaches(geometry, rec.junction);
  const live = (getLiveState()?.signals || []).find((signal) => signal.id === rec.junction);
  const lamps = (approaches?.lanes || [])
    .map((lane) => signalLampState(live?.state, lane.linkIndices))
    .filter(Boolean);
  const green = lamps.filter((lamp) => lamp === 'green').length;
  const red = lamps.filter((lamp) => lamp === 'red').length;
  const bypass = bypassFor(geometry, rec.junction);
  const value = {
    roads: approaches
      ? [...new Set(approaches.edges.map((edge) => edge.name))].slice(0, 3)
      : [],
    signals: lamps.length ? `${green} green · ${red} red of ${lamps.length}` : '',
    bypass,
    note: bypass ? '' : 'No alternative road through this junction in the loaded network.'
  };
  previewCache = { key, value };
  return value;
}

function previewFeatures() {
  const rec = previewRecommendation();
  const empty = { type: 'FeatureCollection', features: [] };
  if (!rec?.junction) return empty;
  const geometry = geometryFor(getLiveState()?.scenario);
  if (!geometry) return empty;
  const approaches = junctionApproaches(geometry, rec.junction);
  if (!approaches) return empty;
  const live = (getLiveState()?.signals || []).find((signal) => signal.id === rec.junction);
  const features = [];

  approaches.edges.forEach((edge) => {
    features.push({
      type: 'Feature',
      properties: { kind: 'approach', name: edge.name },
      geometry: { type: 'LineString', coordinates: edge.coords }
    });
  });

  approaches.lanes.forEach((lane) => {
    const lamp = signalLampState(live?.state, lane.linkIndices);
    if (!lamp) return;
    features.push({
      type: 'Feature',
      properties: { kind: 'signal', lamp },
      geometry: { type: 'Point', coordinates: lane.point }
    });
  });

  const attachment = previewContext(rec).bypass;
  if (attachment?.alternative) {
    features.push(
      routeFeature(attachment.alternative, {
        kind: 'alternative',
        name: attachment.approachNames.join(', ')
      })
    );
  }

  return { type: 'FeatureCollection', features };
}

/* The preview strip names the road being changed and the detour beside it, so the
   operator can read the map highlight instead of guessing what the lines mean. */
function previewMapMarkup(rec) {
  if (!rec.junction) {
    return `<p class="mp-preview-note">Modelled corridor action — no single junction to highlight.</p>`;
  }
  const context = previewContext(rec);
  const rows = [];
  if (context.roads.length) {
    rows.push(`
      <div class="mp-preview-map-row">
        <span class="mp-preview-legend is-approach"></span>
        <span>Approach</span>
        <b>${context.roads.join(' · ')}</b>
      </div>`);
  }
  if (context.signals) {
    rows.push(`
      <div class="mp-preview-map-row">
        <span class="mp-preview-legend is-signal"></span>
        <span>Signals</span>
        <b>${context.signals}</b>
      </div>`);
  }
  if (context.bypass) {
    const { alternative, original } = context.bypass;
    const delta = alternative.distanceM - (original?.distanceM ?? alternative.distanceM);
    rows.push(`
      <div class="mp-preview-map-row">
        <span class="mp-preview-legend is-alt"></span>
        <span>Alternative</span>
        <b>${(alternative.distanceM / 1000).toFixed(2)} km · ${delta >= 0 ? '+' : '−'}${Math.abs(Math.round(delta))} m</b>
      </div>`);
  }
  return `<div class="mp-preview-map">${rows.join('')}</div>${
    context.note ? `<p class="mp-preview-note">${context.note}</p>` : ''
  }`;
}

function ensurePreviewLayers(mapbox) {
  if (!mapbox.getSource('mode-preview')) {
    mapbox.addSource('mode-preview', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] }
    });
  }

  if (!mapbox.getLayer('mode-approach-line')) {
    mapbox.addLayer({
      id: 'mode-approach-line',
      type: 'line',
      source: 'mode-preview',
      filter: ['==', ['get', 'kind'], 'approach'],
      layout: { 'line-join': 'round', 'line-cap': 'round', visibility: 'none' },
      paint: {
        'line-width': 6,
        'line-color': '#c74a4a',
        'line-opacity': 0.85,
        'line-blur': 0.4
      }
    });
  }

  if (!mapbox.getLayer('mode-alternative-line')) {
    mapbox.addLayer({
      id: 'mode-alternative-line',
      type: 'line',
      source: 'mode-preview',
      filter: ['==', ['get', 'kind'], 'alternative'],
      layout: { 'line-join': 'round', 'line-cap': 'round', visibility: 'none' },
      paint: {
        'line-width': 4,
        'line-color': '#2f7d3a',
        'line-opacity': 0.95,
        'line-dasharray': [1.6, 1.4]
      }
    });
  }

  if (!mapbox.getLayer('mode-signal-dot')) {
    mapbox.addLayer({
      id: 'mode-signal-dot',
      type: 'circle',
      source: 'mode-preview',
      filter: ['==', ['get', 'kind'], 'signal'],
      layout: { visibility: 'none' },
      paint: {
        'circle-radius': 5,
        'circle-color': [
          'match',
          ['get', 'lamp'],
          'green', '#4f9d2f',
          'amber', '#d8a13a',
          '#c74a4a'
        ],
        'circle-stroke-color': '#fffdf6',
        'circle-stroke-width': 1.6,
        'circle-opacity': 0.95
      }
    });
  }
}

function setPreviewVisible(mapbox, visible) {
  ['mode-approach-line', 'mode-alternative-line', 'mode-signal-dot'].forEach((id) => {
    if (mapbox.getLayer(id)) {
      mapbox.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none');
    }
  });
}

function syncPreviewLayers(mapbox) {
  const source = mapbox.getSource('mode-preview');
  if (!source) return;
  const collection = previewFeatures();
  source.setData(collection);
  setPreviewVisible(mapbox, collection.features.length > 0);
}

/* ------------------------------------------------------ Predict route estimate */

/* Two points picked on the map, joined along the network's lanes, with the arrival
   time estimated from the speed the run is actually measuring. */

let etaMemo = { key: null, value: null };

function routeEstimate() {
  const { etaA: a, etaB: b } = state;
  if (!a || !b) return null;
  const scenario = getLiveState()?.scenario;
  const geometry = geometryFor(scenario);
  if (!geometry) return { pending: true };
  const key = `${scenario}:${a.join(',')}:${b.join(',')}`;
  if (etaMemo.key !== key) etaMemo = { key, value: routeBetween(geometry, a, b) };
  const route = etaMemo.value;
  if (!route) return { error: 'No road path between A and B.' };
  const crossings = geometry.signals.filter((signal) =>
    route.coordinates.some((point) => metersBetween(point, signal.center) < 26)
  ).length;
  const speed = Number(liveMetrics().avgSpeedKmh) || 0;
  const minutes =
    speed > 0
      ? Math.max(1, Math.round((route.distanceM / 1000 / speed) * 60 + crossings * 0.4))
      : null;
  return { distanceKm: route.distanceM / 1000, crossings, speed, minutes };
}

function etaFeatures() {
  const features = [];
  const estimate = routeEstimate();
  if (estimate && !estimate.error && !estimate.pending && etaMemo.value) {
    features.push(routeFeature(etaMemo.value, { kind: 'route' }));
  }
  [
    ['a', state.etaA],
    ['b', state.etaB]
  ].forEach(([end, point]) => {
    if (!point) return;
    features.push({
      type: 'Feature',
      properties: { kind: 'endpoint', end },
      geometry: { type: 'Point', coordinates: point }
    });
  });
  return { type: 'FeatureCollection', features };
}

function ensureEtaLayers(mapbox) {
  if (!mapbox.getSource('mode-eta')) {
    mapbox.addSource('mode-eta', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] }
    });
  }

  if (!mapbox.getLayer('mode-eta-line')) {
    mapbox.addLayer({
      id: 'mode-eta-line',
      type: 'line',
      source: 'mode-eta',
      filter: ['==', ['get', 'kind'], 'route'],
      layout: { 'line-join': 'round', 'line-cap': 'round', visibility: 'none' },
      paint: {
        'line-width': 4.5,
        'line-color': '#2f6d4f',
        'line-opacity': 0.92,
        'line-dasharray': [1.6, 1.2]
      }
    });
  }

  if (!mapbox.getLayer('mode-eta-point')) {
    mapbox.addLayer({
      id: 'mode-eta-point',
      type: 'circle',
      source: 'mode-eta',
      filter: ['==', ['get', 'kind'], 'endpoint'],
      layout: { visibility: 'none' },
      paint: {
        'circle-radius': 7,
        'circle-color': ['match', ['get', 'end'], 'a', '#5f9c2b', '#c74a4a'],
        'circle-stroke-color': '#fffdf6',
        'circle-stroke-width': 2
      }
    });
  }
}

function setEtaVisible(mapbox, visible) {
  ['mode-eta-line', 'mode-eta-point'].forEach((id) => {
    if (mapbox.getLayer(id)) {
      mapbox.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none');
    }
  });
}

function syncEtaLayers(mapbox) {
  const source = mapbox.getSource('mode-eta');
  if (!source) return;
  const collection = etaFeatures();
  source.setData(collection);
  setEtaVisible(mapbox, collection.features.length > 0);
}

/** A click on the map sets the point the Predict picker is waiting for. */
function handleMapClick(event) {
  if (state.mode !== 'predict' || !state.etaPick) return;
  const point = [event.lngLat.lng, event.lngLat.lat];
  const scenario = getLiveState()?.scenario;
  const geometry = geometryFor(scenario);
  if (!geometry) {
    showToast('Corridor geometry is still loading.');
    return;
  }
  if (!nearestEdge(geometry, point)) {
    showToast('Pick a point on a road.');
    return;
  }
  if (state.etaPick === 'a') state.etaA = point;
  else state.etaB = point;
  // A is set first, then the picker moves to B, then it closes.
  state.etaPick = state.etaPick === 'a' ? 'b' : null;
  render();
  syncMapForMode(state.mode);
}

function syncMapForMode(mode) {
  const mapbox = getMap();
  map = mapbox;
  if (!mapbox) return;

  // A style that is still streaming cannot take sources or layers; the
  // readiness poll and style.load listener retry until it can.
  try {
    applyModeLayers(mapbox, mode);
  } catch {
    /* style not ready yet */
  }
}

function applyModeLayers(mapbox, mode) {
  if (mode === 'optimize') {
    ensurePreviewLayers(mapbox);
    setEtaVisible(mapbox, false);
    syncPreviewLayers(mapbox);
    return;
  }

  if (mode === 'predict') {
    ensureEtaLayers(mapbox);
    setPreviewVisible(mapbox, false);
    syncEtaLayers(mapbox);
    return;
  }

  setPreviewVisible(mapbox, false);
  setEtaVisible(mapbox, false);
}

/* -------------------------------------------------------------- mode markup */

function optimizePanel() {
  const recs = modeData
    .recommendations(state.zone, nowMinute())
    .filter((rec) => !state.dismissed.has(rec.id));

  if (!recs.length) {
    return `
      <aside class="mode-panel mp-optimize" data-panel="optimize">
        ${panelHead({
          icon: 'i-bulb',
          label: 'Optimize',
          title: 'Recommendations',
          sub: `${zoneLabel()} · all clear`,
          badge: '0',
          collapseLabel: 'Collapse recommendations panel',
          summaryLabel: 'Top impact',
          summaryValue: '0',
          summaryUnit: 'min',
          summaryMeta: 'no pending actions'
        })}
        <div class="mp-empty">
          <strong>Corridor is running clear.</strong>
          <span>Dismissed items return after the next signal cycle, or scrub to rush hour to see what would be proposed.</span>
        </div>
      </aside>`;
  }

  const preview = recs.find((rec) => rec.id === state.previewId);
  const lead = recs[0];
  const maxDelay = Math.max(...recs.map((rec) => rec.delayMin), 0.1);
  const appliedCount = recs.filter((rec) => state.applied.has(rec.id)).length;

  const rows = recs
    .map((rec, index) => {
      const applied = state.applied.has(rec.id);
      const previewing = state.previewId === rec.id;
      const weight = Math.max(8, Math.round((rec.delayMin / maxDelay) * 100));
      return `
        <li class="rec${previewing ? ' is-previewing' : ''}${applied ? ' is-applied' : ''}" data-rec="${rec.id}" style="--row:${index};--impact:${weight}%">
          <div class="rec-head">
            <span class="rec-rank">${String(index + 1).padStart(2, '0')}</span>
            <div class="rec-copy">
              <strong class="rec-title">${rec.title}</strong>
              <span class="rec-detail">${rec.detail}</span>
            </div>
            <span class="rec-kind">${KIND_LABELS[rec.kind] || 'Action'}</span>
          </div>
          <div class="rec-stats">
            <span class="rec-stat is-lead"><b>−${rec.delayMin}</b> min</span>
            <span class="rec-stat"><b>+${rec.throughput}</b>% flow</span>
            <span class="rec-stat"><b>+${rec.efficiency}</b>% eff.</span>
            <span class="rec-stat is-muted"><b>${Math.round(rec.confidence * 100)}</b>% conf.</span>
          </div>
          <div class="rec-impact-row" aria-hidden="true">
            <span>Impact</span>
            <span class="rec-meter"><i></i></span>
          </div>
          <div class="rec-actions">
            <button type="button" class="mp-btn is-apply${applied ? ' is-on' : ''}" data-rec-apply="${rec.id}">${applied ? 'Applied' : 'Apply'}</button>
            <button type="button" class="mp-btn is-preview${previewing ? ' is-on' : ''}" data-rec-preview="${rec.id}">${previewing ? 'Previewing' : 'Preview'}</button>
            <button type="button" class="mp-btn is-ghost" data-rec-dismiss="${rec.id}" aria-label="Dismiss recommendation">Dismiss</button>
          </div>
        </li>`;
    })
    .join('');

  return `
    <aside class="mode-panel mp-optimize" data-panel="optimize">
      ${panelHead({
        icon: 'i-bulb',
        label: 'Optimize',
        title: 'Recommendations',
        sub: `${zoneLabel()} · ranked by delay saved`,
        badge: String(recs.length),
        collapseLabel: 'Collapse recommendations panel',
        summaryLabel: 'Top impact',
        summaryValue: `−${lead.delayMin}`,
        summaryUnit: 'min',
        summaryMeta: `${Math.round(lead.confidence * 100)}% conf. · ${appliedCount} applied`
      })}

      <ol class="rec-list">${rows}</ol>

      ${
        preview
          ? `<div class="mp-preview-strip">
              <div class="mp-preview-head">
                <span class="mp-preview-label">Previewing</span>
                <span class="mp-preview-name">${preview.title}</span>
                <button type="button" class="mp-btn is-ghost" data-rec-clear>Clear</button>
              </div>
              <div class="mp-preview-deltas">
                <span class="mp-delta"><i>Delay</i><b>−${preview.delayMin} min</b></span>
                <span class="mp-delta"><i>Flow</i><b>+${preview.throughput}%</b></span>
                <span class="mp-delta"><i>Efficiency</i><b>+${preview.efficiency}%</b></span>
              </div>
              ${previewMapMarkup(preview)}
            </div>`
          : `<p class="mp-foot-note">Impact is a modelled estimate for ${zoneLabel()} at ${clock(nowMinute())}. Preview before applying.</p>`
      }
    </aside>`;
}

function predictPanel() {
  const forecast = modeData.forecast(state.zone, state.minute, [...state.inputs]);
  const series = forecast.series;
  const max = Math.max(
    ...series.map((slot) => slot.volume),
    ...forecast.typical.map((slot) => slot.volume)
  );
  const toPoints = (list) =>
    list
      .map((slot, index) => {
        const x = (index / (list.length - 1)) * 100;
        const y = 34 - (slot.volume / max) * 30;
        return `${x.toFixed(2)},${y.toFixed(2)}`;
      })
      .join(' ');
  const points = toPoints(series);
  const typicalPoints = toPoints(forecast.typical);
  const nowX = (state.minute / 1440) * 100;
  const peakIndex = Math.max(0, series.findIndex((slot) => slot.minute === forecast.peak.minute));
  const typicalPeak = forecast.typical[peakIndex]?.volume || forecast.peak.volume;
  const typicalPeakSlot = forecast.typical.reduce(
    (best, slot) => (slot.volume > best.volume ? slot : best),
    forecast.typical[0]
  );
  const peakDelta = Math.round((forecast.peak.volume / typicalPeak - 1) * 100);
  const peakX = (forecast.peak.minute / 1440) * 100;
  const peakY = 34 - (forecast.peak.volume / max) * 30;
  const activeCount = forecast.inputs.filter((input) => input.active).length;
  const upcoming = series.filter((slot) => slot.minute >= state.minute);
  const risk = (upcoming.length ? upcoming : series)
    .slice()
    .sort((a, b) => b.volume - a.volume)
    .slice(0, 3)
    .sort((a, b) => a.minute - b.minute)
    .map((slot) => {
      const share = slot.volume / forecast.peak.volume;
      return {
        clock: formatClock(slot.minute),
        delay: Math.max(1, Math.round(forecast.expectedDelay * share)),
        fill: Math.round((slot.volume / max) * 100),
        severity: share > 0.9 ? 'heavy' : share > 0.72 ? 'busy' : 'steady'
      };
    });
  const riskRows = risk
    .map(
      (row) => `
      <li class="risk-row is-${row.severity}">
        <span class="risk-time">${row.clock}</span>
        <span class="risk-bar"><i style="width:${row.fill}%"></i></span>
        <span class="risk-delay">+${row.delay} min</span>
      </li>`
    )
    .join('');
  const remaining = Math.max(0, 1440 - state.minute);
  const horizon = remaining >= 120 ? `${Math.round(remaining / 60)}h ahead` : `${remaining} min ahead`;
  const confidence = Math.round(forecast.confidence * 100);

  const chips = forecast.inputs
    .map(
      (input) => `
      <button type="button" class="whatif-chip${input.active ? ' is-on' : ''}" data-whatif="${input.id}" title="${input.detail}">
        <span class="whatif-dot"></span>${input.label}
      </button>`
    )
    .join('');

  return `
    <aside class="mode-panel mp-predict" data-panel="predict">
      ${panelHead({
        icon: 'i-cloud-sun',
        label: 'Predict',
        title: 'Forecast',
        sub: `${zoneLabel()} · ${horizon}`,
        badge: `${confidence}%`,
        collapseLabel: 'Collapse forecast panel',
        summaryLabel: 'Expected delay',
        summaryValue: `+${forecast.expectedDelay}`,
        summaryUnit: 'min',
        summaryMeta: `Peak ${forecast.peak.label} · ±${forecast.band} min`
      })}

      <dl class="predict-grid">
        <div><dt>Peak time</dt><dd>${forecast.peak.label}<small>${state.compareTypical ? (formatClock(typicalPeakSlot.minute) === forecast.peak.label ? 'matches typical day' : `typical ${formatClock(typicalPeakSlot.minute)}`) : 'today'}</small></dd></div>
        <div><dt>Peak volume</dt><dd>${(forecast.peak.volume / 1000).toFixed(1)}<small>k / 30m</small></dd></div>
        <div><dt>Confidence</dt><dd>${confidence}<small>% ${confidence >= 85 ? 'high' : 'medium'}</small></dd></div>
      </dl>

      <section class="predict-card">
        <header class="mp-card-head">
          <h3>Predicted volume</h3>
          <span class="mp-card-badge${peakDelta > 0 ? ' is-up' : ''}">${peakDelta > 0 ? '+' : ''}${peakDelta}% vs typical</span>
        </header>
        <div class="predict-spark">
          <svg viewBox="0 0 100 36" preserveAspectRatio="none" role="img" aria-label="Predicted volume across the day">
            <line class="predict-now" x1="${nowX.toFixed(2)}" y1="0" x2="${nowX.toFixed(2)}" y2="34" />
            ${state.compareTypical ? `<polyline class="predict-line is-typical" points="${typicalPoints}" />` : ''}
            <polyline class="predict-line is-forecast" points="${points}" />
            <circle class="predict-peak" cx="${peakX.toFixed(2)}" cy="${peakY.toFixed(2)}" r="1.5" />
          </svg>
          <span class="predict-spark-axis"><i>00:00</i><i>06:00</i><i>12:00</i><i>18:00</i><i>24:00</i></span>
        </div>
        <footer class="predict-key">
          <span><i class="is-forecast"></i>Forecast</span>
          ${state.compareTypical ? `<span><i class="is-typical"></i>${forecast.baselineLabel || 'Typical day'}</span>` : ''}
          <span class="predict-key-meta">Peak ${forecast.peak.label}</span>
        </footer>
      </section>

      <section class="predict-card">
        <header class="mp-card-head">
          <h3>Hours at risk</h3>
          <span class="mp-card-meta">next ${risk.length} peaks</span>
        </header>
        <ul class="risk-list">${riskRows}</ul>
      </section>

      <section class="predict-card">
        <header class="mp-card-head">
          <h3>Scenario inputs</h3>
          <span class="mp-card-meta">${activeCount ? `${activeCount} active` : 'Baseline'}</span>
        </header>
        <div class="whatif-chips">${chips}</div>
        <p class="predict-note">${forecast.basisNote ? `Live basis: ${forecast.basisNote}` : 'Toggling an input re-runs the forecast for the selected time.'}</p>
      </section>

      <footer class="mp-footer">
        <div class="mp-toggle-row">
          <div class="mp-toggle-copy">
            <strong>Compare with typical day</strong>
            <span>Dashed baseline at the same hour</span>
          </div>
          <button type="button" class="mp-switch${state.compareTypical ? ' is-on' : ''}" data-compare-toggle role="switch" aria-checked="${state.compareTypical}" aria-label="Compare with typical day"><i></i></button>
        </div>
      </footer>
    </aside>`;
}

/* ------------------------------------------------------------------ Predict ETA */

/* Pick A and B on the map and the panel reports the road distance and the arrival
   time that distance implies at the speed the run is measuring. */
function etaCard(estimate) {
  const pick = (slot) => {
    const set = slot === 'a' ? state.etaA : state.etaB;
    const active = state.etaPick === slot;
    const letter = slot.toUpperCase();
    return `<button type="button" class="eta-pick${set ? ' is-set' : ''}${
      active ? ' is-picking' : ''
    }" data-eta-pick="${slot}">${
      active ? 'Click the map…' : set ? `${letter} set` : `Pick ${letter}`
    }</button>`;
  };

  const body = !estimate
    ? `<p class="predict-note">Pick an origin and a destination on the network; the estimate follows the run's own lanes at the measured speed.</p>`
    : estimate.pending
      ? `<p class="predict-note">Loading the corridor geometry…</p>`
      : estimate.error
        ? `<p class="predict-note">${estimate.error}</p>`
        : `<div class="eta-result">
             <strong>${estimate.minutes == null ? '—' : estimate.minutes}<small>min</small></strong>
             <span>${estimate.distanceKm.toFixed(2)} km · ${estimate.crossings} signal${estimate.crossings === 1 ? '' : 's'}${estimate.speed ? ` · ${Math.round(estimate.speed)} km/h measured` : ''}</span>
           </div>
           <p class="predict-note">${
             estimate.minutes == null
               ? 'No measured corridor speed yet — start or unpause the run.'
               : 'Estimated at the measured corridor speed plus 0.4 min per signalised crossing.'
           }</p>`;

  return `
    <section class="predict-card eta-card">
      <header class="mp-card-head">
        <h3>Route estimate A → B</h3>
        <span class="mp-card-meta">${
          estimate && estimate.minutes != null ? `${estimate.minutes} min` : 'pick two points'
        }</span>
      </header>
      <div class="eta-picks">
        ${pick('a')}
        ${pick('b')}
        ${state.etaA || state.etaB ? '<button type="button" class="mp-btn is-ghost" data-eta-clear>Clear</button>' : ''}
      </div>
      ${body}
    </section>`;
}

/* Predict while a run is live: the measured queue up to now and the backend's
   projection after it, on one axis. Every projected number carries its basis. */
function predictLivePanel() {
  const forecast = liveForecast();
  const status = forecastState();
  if (!forecast) {
    return `
      <aside class="mode-panel mp-predict" data-panel="predict">
        ${panelHead({
          icon: 'i-cloud-sun',
          label: 'Predict',
          title: 'Forecast',
          sub: `${zoneLabel()} · collecting run samples`,
          badge: '—',
          collapseLabel: 'Collapse forecast panel',
          summaryLabel: 'Queue ahead',
          summaryValue: '—',
          summaryUnit: 'veh',
          summaryMeta: status.error || 'needs a few decision ticks'
        })}
        <div class="mp-empty">
          <strong>Collecting samples.</strong>
          <span>The projection appears once the run has published a few decision ticks${status.error ? ` — ${status.error}` : '.'}</span>
        </div>
      </aside>`;
  }

  const values = forecast.values;
  const max = Math.max(...values, 1);
  const toPoint = (value, index) => {
    const x = values.length > 1 ? (index / (values.length - 1)) * 100 : 0;
    const y = 34 - (value / max) * 30;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  };
  const measuredPoints = forecast.measured.map((entry, index) => toPoint(entry.queue, index)).join(' ');
  const projectedPoints = forecast.projected
    .map((entry, index) => toPoint(entry.queue, forecast.split + index))
    .join(' ');
  const splitX = values.length > 1 ? ((Math.max(1, forecast.split) - 1) / (values.length - 1)) * 100 : 0;
  const peakIndex = values.lastIndexOf(forecast.peak.queue);
  const peakPoint = toPoint(forecast.peak.queue, peakIndex < 0 ? values.length - 1 : peakIndex);
  const peakX = peakPoint.split(',')[0];
  const peakY = peakPoint.split(',')[1];
  const horizon = Number(forecast.horizonMin) || 15;
  const confidence = Math.round(forecast.confidence * 100);
  const growth = Math.round(forecast.projectedQueue - forecast.currentQueue);
  const risk = [...forecast.projected].sort((a, b) => b.queue - a.queue).slice(0, 3).sort((a, b) => a.minute - b.minute);
  const nowClock = forecast.measured[forecast.measured.length - 1]?.clock || '—';
  const endClock = forecast.projected[forecast.projected.length - 1]?.clock || '—';
  const estimate = routeEstimate();

  return `
    <aside class="mode-panel mp-predict" data-panel="predict">
      ${panelHead({
        icon: 'i-cloud-sun',
        label: 'Predict',
        title: 'Forecast',
        sub: `${zoneLabel()} · next ${horizon} min`,
        badge: `${confidence}%`,
        collapseLabel: 'Collapse forecast panel',
        summaryLabel: `Queue in ${horizon} min`,
        summaryValue: `${Math.round(forecast.projectedQueue)}`,
        summaryUnit: 'veh',
        summaryMeta: `now ${Math.round(forecast.currentQueue)} · peak ${Math.round(forecast.peak.queue)} at ${forecast.peak.clock}`
      })}

      <dl class="predict-grid">
        <div><dt>Now</dt><dd>${Math.round(forecast.currentQueue)}<small>veh queued</small></dd></div>
        <div><dt>In ${horizon} min</dt><dd>${Math.round(forecast.projectedQueue)}<small>${growth >= 0 ? '+' : ''}${growth} vs now</small></dd></div>
        <div><dt>Confidence</dt><dd>${confidence}<small>% · ${forecast.samples} samples</small></dd></div>
      </dl>

      <section class="predict-card">
        <header class="mp-card-head">
          <h3>Measured → projected queue</h3>
          <span class="mp-card-meta">±${forecast.band} veh</span>
        </header>
        <div class="predict-spark">
          <svg viewBox="0 0 100 36" preserveAspectRatio="none" role="img" aria-label="Measured queue and the projected queue">
            <polyline class="predict-line is-measured" points="${measuredPoints}" />
            <polyline class="predict-line is-forecast" points="${projectedPoints}" />
            <line class="predict-now" x1="${splitX.toFixed(2)}" y1="0" x2="${splitX.toFixed(2)}" y2="34" />
            <circle class="predict-peak" cx="${peakX}" cy="${peakY}" r="1.5" />
          </svg>
          <span class="predict-spark-axis"><i>${forecast.measured[0]?.clock || '—'}</i><i>${nowClock}</i><i>${endClock}</i></span>
        </div>
        <footer class="predict-key">
          <span><i class="is-measured"></i>Measured</span>
          <span><i class="is-forecast"></i>Forecast</span>
          <span class="predict-key-meta">${forecast.method}</span>
        </footer>
      </section>

      <section class="predict-card">
        <header class="mp-card-head">
          <h3>Highest projected queue</h3>
          <span class="mp-card-meta">next ${horizon} min</span>
        </header>
        <ul class="risk-list">
          ${risk
            .map(
              (row) => `
            <li class="risk-row is-${row.queue > forecast.currentQueue * 1.2 ? 'heavy' : row.queue > forecast.currentQueue ? 'busy' : 'steady'}">
              <span class="risk-time">${row.clock}</span>
              <span class="risk-bar"><i style="width:${Math.round((row.queue / max) * 100)}%"></i></span>
              <span class="risk-delay">${Math.round(row.queue)} veh</span>
            </li>`
            )
            .join('')}
        </ul>
      </section>

      ${etaCard(estimate)}

      <footer class="mp-footer">
        <p class="mp-foot-note">Live basis: ${forecast.basisNote}. Projection assumes the vehicle count stays at ${Number(liveMetrics().vehicles) || 0}.</p>
      </footer>
    </aside>`;
}

/* The four strip numbers, formatted once so the first paint and every later
   snapshot write the same strings. `stats` is the measured run while live and
   the demo day model when idle — the segment list below uses the same source,
   so the strip and the inspector can never disagree. */
function roamStripValues(stats) {
  const source = stats || modeData.roamStats(state.zone, nowMinute());
  return {
    speed: source.speed,
    density: Math.round(source.density * 100),
    vehicles: source.vehicles,
    incidents: source.incidents,
    critical: Number(source.critical) || 0
  };
}

function roamStrip() {
  const stats = modeData.roamStats(state.zone, nowMinute());
  const strip = roamStripValues(stats);
  const segments = stats.segments
    .map(
      (seg) => `
      <li class="roam-seg is-${seg.state}" data-roam-seg="${seg.id}">
        <span class="roam-seg-name">${seg.label}${seg.lanes ? ` · ${seg.lanes} lanes` : ''}</span>
        <span class="roam-seg-speed">${seg.speed} km/h${seg.queue != null ? ` · ${seg.queue} queued` : ''}</span>
      </li>`
    )
    .join('');
  const classes = roamClassCounts();
  const classOptions = classes
    .map(
      ([key, count]) =>
        `<option value="${key}"${state.roamClass === key ? ' selected' : ''}>${ROAM_CLASS_LABELS[key] || key} · ${count}</option>`
    )
    .join('');

  return `
    <div class="mode-roam" data-panel="roam">
      <div class="roam-strip${isLive() ? ' is-live' : ''}">
        <div class="roam-stat"><span>Speed</span><strong data-roam-stat="speed">${strip.speed}</strong><i>km/h</i></div>
        <div class="roam-stat"><span>Density</span><strong data-roam-stat="density">${strip.density}</strong><i>%</i></div>
        <div class="roam-stat"><span>Vehicles</span><strong data-roam-stat="vehicles">${strip.vehicles}</strong><i>live</i></div>
        <div class="roam-stat${strip.critical ? ' is-critical' : ''}"><span>Incidents</span><strong data-roam-stat="incidents">${strip.incidents}</strong><i>open</i></div>
      </div>

      <div class="roam-pills">
        <select class="roam-pill roam-select" data-roam-class aria-label="Follow a vehicle class"${classes.length ? '' : ' disabled'}>
          <option value="">Vehicle class</option>${classOptions}
        </select>
        <button type="button" class="roam-pill${state.followMode ? ' is-on' : ''}" data-roam-follow aria-pressed="${state.followMode}">Follow vehicle</button>
        <button type="button" class="roam-pill${state.povMode ? ' is-on' : ''}" data-roam-pov aria-pressed="${state.povMode}">Vehicle POV</button>
        <button type="button" class="roam-pill" data-roam-flythrough>Fly-through</button>
        <button type="button" class="roam-pill" data-roam-open>Segments</button>
        <button type="button" class="roam-pill" data-roam-recenter>Recenter</button>
      </div>

      <ul class="roam-legend">
        <li><span class="roam-dot is-flow"></span>Free flow</li>
        <li><span class="roam-dot is-dense"></span>Dense</li>
        <li><span class="roam-dot is-jam"></span>Jammed</li>
      </ul>

      <ul class="roam-shortcuts" aria-label="Roam keyboard shortcuts">
        <li><kbd>F</kbd>Follow</li>
        <li><kbd>V</kbd>POV</li>
        <li><kbd>N</kbd><kbd>P</kbd>Cycle</li>
        <li><kbd>Esc</kbd>Stop</li>
      </ul>

      <div class="roam-inspector" hidden>
        <header><strong data-roam-inspector-title>Inspector</strong><button type="button" class="mp-btn is-ghost" data-roam-close>Close</button></header>
        <ul class="roam-seg-list">${segments}</ul>
      </div>
    </div>`;
}

/* Roam camera: the map follows one vehicle. The panels own the choice; app.js
   owns the camera, so the two never fight over who moves the view. */
function roamVehicles() {
  return isLive() ? getLiveState()?.vehicles || [] : [];
}

function pickRoamVehicle(candidates = roamVehicles()) {
  const vehicles = candidates;
  if (!vehicles.length) return null;
  const emergency = vehicles.find(
    (vehicle) =>
      vehicle.vehicleClass === 'emergency' || String(vehicle.type || '').includes('emergency')
  );
  if (emergency) return emergency;
  // Follow something that is actually moving: the slowest car is usually stopped
  // at a red light, which would pin the camera to one corner of the corridor.
  const moving = vehicles.filter((vehicle) => Number(vehicle.speed) > 1);
  return [...(moving.length ? moving : vehicles)].sort(
    (a, b) => Number(b.speed || 0) - Number(a.speed || 0)
  )[0];
}

const ROAM_CLASS_LABELS = {
  passenger: 'Cars',
  car: 'Cars',
  taxi: 'Taxis',
  bus: 'Buses',
  truck: 'Trucks',
  trailer: 'Trucks',
  emergency: 'Emergency',
  bicycle: 'Bikes',
  motorcycle: 'Motorcycles'
};

let roamClassSignature = '';
let povStopVehicleId = null;
let povStoppedAt = null;

/** Vehicle classes in the current run, busiest first, for the Roam picker. */
function roamClassCounts() {
  const counts = new Map();
  roamVehicles().forEach((vehicle) => {
    if (vehicle.pedestrian) return;
    const key = String(vehicle.vehicleClass || 'car');
    counts.set(key, (counts.get(key) || 0) + 1);
  });
  return [...counts.entries()].sort((a, b) => b[1] - a[1]);
}

/** Refresh the picker only when the classes or their counts actually change. */
function syncRoamClassOptions() {
  const select = document.querySelector('[data-roam-class]');
  if (!select) return;
  // Counts change every snapshot; rebuilding the options while the native
  // dropdown is open would close it mid-choice. Catch up after it loses focus.
  if (document.activeElement === select) return;
  const classes = roamClassCounts();
  const signature = classes.map(([key, count]) => `${key}:${count}`).join('|');
  if (signature === roamClassSignature) return;
  roamClassSignature = signature;
  select.innerHTML = [
    '<option value="">Vehicle class</option>',
    ...classes.map(
      ([key, count]) =>
        `<option value="${key}">${ROAM_CLASS_LABELS[key] || key} · ${count}</option>`
    )
  ].join('');
  select.value = classes.some(([key]) => key === state.roamClass) ? state.roamClass : '';
  if (!select.value) state.roamClass = '';
  select.disabled = classes.length === 0;
}

/*
 * The strip is telemetry, so it is patched in place on every published snapshot.
 * Re-rendering the panel here would rebuild the class <select> (closing it while
 * the operator is choosing) and collapse the segment inspector, so the numbers
 * are written where they sit instead.
 */
function syncRoamStats() {
  const stripEl = $('.roam-strip');
  if (!stripEl) return;
  const values = roamStripValues();
  const live = isLive();
  Object.entries(values).forEach(([key, value]) => {
    if (key === 'critical') return;
    const node = stripEl.querySelector(`[data-roam-stat="${key}"]`);
    if (node && node.textContent !== String(value)) node.textContent = String(value);
  });
  stripEl.classList.toggle('is-live', live);
  stripEl
    .querySelector('[data-roam-stat="incidents"]')
    ?.closest('.roam-stat')
    ?.classList.toggle('is-critical', values.critical > 0);
  syncRoamSegments(modeData.roamStats(state.zone, nowMinute()).segments);
}

/** Segment rows in the inspector carry the same measured speed as the strip. */
function syncRoamSegments(segments) {
  if (!Array.isArray(segments)) return;
  segments.forEach((seg) => {
    const row = document.querySelector(`[data-roam-seg="${seg.id}"]`);
    if (!row) return;
    row.classList.remove('is-flow', 'is-dense', 'is-jam');
    row.classList.add(`is-${seg.state}`);
    const speed = row.querySelector('.roam-seg-speed');
    const text = `${seg.speed} km/h${seg.queue != null ? ` · ${seg.queue} queued` : ''}`;
    if (speed && speed.textContent !== text) speed.textContent = text;
  });
}

function dispatchRoamFollow(detail) {
  document.dispatchEvent(new CustomEvent('sumo:roamfollow', { detail }));
}

function syncRoamPills() {
  document.querySelectorAll('[data-roam-follow]').forEach((button) => {
    button.classList.toggle('is-on', state.followMode);
    button.setAttribute('aria-pressed', String(state.followMode));
  });
  document.querySelectorAll('[data-roam-pov]').forEach((button) => {
    button.classList.toggle('is-on', state.povMode);
    button.setAttribute('aria-pressed', String(state.povMode));
  });
}

function roamView() {
  return state.povMode ? 'pov' : 'follow';
}

function followRoamVehicle(vehicle) {
  if (!vehicle) return;
  state.followMode = true;
  state.followVehicleId = vehicle.id;
  povStopVehicleId = null;
  povStoppedAt = null;
  dispatchRoamFollow({ id: vehicle.id, view: roamView() });
  syncRoamPills();
  showToast(
    state.povMode
      ? `In-vehicle view of ${vehicle.id}.`
      : `Following ${vehicle.id} at ${Math.round((vehicle.speed || 0) * 3.6)} km/h.`
  );
}

function stopRoamFollow() {
  if (!state.followMode && !state.povMode) return;
  state.followMode = false;
  state.povMode = false;
  state.followVehicleId = null;
  povStopVehicleId = null;
  povStoppedAt = null;
  dispatchRoamFollow(null);
  syncRoamPills();
  showToast('Follow mode off.');
}

/**
 * A windscreen view of a parked car shows nothing, so POV falls back to chase
 * after 3 s of simulated standstill. Simulated time (not wall time) means a
 * paused run never triggers it.
 */
function maybeDropStoppedPov() {
  if (!state.povMode || !state.followVehicleId) {
    povStopVehicleId = null;
    povStoppedAt = null;
    return;
  }
  const snapshot = getLiveState();
  const now = Number(snapshot?.simulationTime);
  const vehicle = (snapshot?.vehicles || []).find(
    (item) => String(item.id) === String(state.followVehicleId)
  );
  if (!vehicle || !Number.isFinite(now)) {
    povStopVehicleId = null;
    povStoppedAt = null;
    return;
  }
  if (String(povStopVehicleId) !== String(vehicle.id)) {
    povStopVehicleId = vehicle.id;
    povStoppedAt = now;
    return;
  }
  if (Number(vehicle.speed) > 0.5) {
    povStoppedAt = now;
    return;
  }
  if (povStoppedAt == null) {
    povStoppedAt = now;
    return;
  }
  if (now - povStoppedAt < 3) return;
  state.povMode = false;
  dispatchRoamFollow({ id: state.followVehicleId, view: 'follow' });
  syncRoamPills();
  showToast(`${state.followVehicleId} stopped — switched to chase view.`);
  povStoppedAt = null;
}

/** N/P cycle the follow target in a stable id order, keeping the current view. */
function cycleRoamVehicle(direction) {
  const vehicles = roamVehicles()
    .filter((vehicle) => !vehicle.pedestrian)
    .sort((a, b) => String(a.id).localeCompare(String(b.id)));
  if (!vehicles.length) {
    showToast('No vehicles in the live run to cycle through.');
    return;
  }
  const current = vehicles.findIndex(
    (vehicle) => String(vehicle.id) === String(state.followVehicleId)
  );
  const index = current < 0 ? 0 : (current + direction + vehicles.length) % vehicles.length;
  followRoamVehicle(vehicles[index]);
}

/* --------------------------------------------------------------- dock bits */

function signalEditor() {
  const timing = modeData.signalTiming(state.zone, nowMinute());
  const maximum = timing.live ? 90 : 60;
  const rows = timing.phases
    .map((phase) => {
      const value = state.sigDrafts.get(phase.id) ?? phase.green;
      return `
      <label class="sig-row${phase.held ? ' is-held' : ''}">
        <span class="sig-name">${phase.label}${phase.held ? ' <i>held</i>' : ''}</span>
        <input type="range" min="6" max="${maximum}" step="1" value="${value}" data-sig="${phase.id}" aria-label="${phase.label} green time">
        <span class="sig-value" data-sig-value="${phase.id}">${value}s</span>
      </label>`;
    })
    .join('');
  const heldCount = timing.phases.filter((phase) => phase.held).length;
  const caption = timing.live
    ? `${timing.phases.length} signals${heldCount ? ` · ${heldCount} held open` : ''}`
    : `${timing.cycle}s cycle`;

  return `
    <div class="signal-editor" data-panel="signal-editor" hidden>
      <header class="signal-head"><h3>Signal timing</h3><span>${caption}</span></header>
      <div class="signal-body">${rows}</div>
      ${
        timing.live
          ? `<footer class="signal-foot">
              <button type="button" class="mp-btn is-apply" data-sig-apply>Apply plan</button>
              <span class="signal-note">Sets the current phase's duration</span>
            </footer>`
          : ''
      }
    </div>`;
}

/* --------------------------------------------------------------------- mount */

let root = null;
let timeline = null;

function mount() {
  const view = document.getElementById('liveMapView');
  const overlay = $('.live-map-overlay', view || document);
  if (!view || !overlay) return;

  loadState();

  root = document.createElement('div');
  root.className = 'mode-layer';
  root.setAttribute('aria-live', 'polite');
  overlay.append(root);

  // Comparison band, forecast band and forecast handle live on the scrub
  // track itself, so they share the playhead's coordinate space.
  timeline = $('.simulation-timeline');
  const track = $('#simulationTrack');
  if (track) {
    track.insertAdjacentHTML(
      'beforeend',
      `<div class="timeline-future" hidden aria-hidden="true"></div>
       <div class="timeline-compare" hidden aria-hidden="true"><i class="tc-before"></i><i class="tc-after"></i></div>
       <button type="button" class="timeline-forecast-handle" hidden aria-label="Forecast handle" title="Drag to set the forecast time"><span></span></button>`
    );
  }

  // Signal editor lives inside the Control Actions card for Optimize mode.
  const actions = $('.live-actions-card');
  if (actions) {
    actions.insertAdjacentHTML('beforeend', signalEditor());
  }

  // Panels menu (presets + per-panel toggles), anchored to the top bar.
  const panelsBtn = $('[data-panels-menu]');
  const topActions = $('.live-top-actions');
  if (panelsBtn && topActions) {
    const menu = document.createElement('div');
    menu.className = 'panels-menu';
    menu.hidden = true;
    menu.innerHTML = `
      <p class="panels-menu-title">Layout presets</p>
      ${['full', 'focus', 'map', 'ops']
        .map(
          (preset) => `<button type="button" class="panels-menu-item${state.panelsPreset === preset ? ' is-on' : ''}" data-preset="${preset}">
            <span>${preset === 'full' ? 'Full' : preset === 'focus' ? 'Focus' : preset === 'map' ? 'Map only' : 'Ops'}</span>
            <small>${preset === 'full' ? 'All panels' : preset === 'focus' ? 'Map + timeline' : preset === 'map' ? 'Map only' : 'Data panels'}</small>
          </button>`
        )
        .join('')}
      <p class="panels-menu-title">Panels</p>
      ${['zone', 'queue', 'dock', 'timeline']
        .map(
          (panel) => `<label class="panels-menu-check"><input type="checkbox" data-panel-toggle="${panel}" ${state.hiddenPanels.has(panel) ? '' : 'checked'}> ${panel === 'dock' ? 'Bottom cards' : panel === 'zone' ? 'Zone monitoring' : panel === 'queue' ? 'Queue backlog' : 'Timeline'}</label>`
        )
        .join('')}
    `;
    topActions.append(menu);
    panelsBtn.setAttribute('aria-expanded', 'false');
    panelsBtn.addEventListener('click', (event) => {
      event.stopPropagation();
      const open = menu.hidden;
      menu.hidden = !open;
      panelsBtn.setAttribute('aria-expanded', String(open));
    });
    document.addEventListener('click', (event) => {
      if (menu.hidden) return;
      if (event.target.closest('.panels-menu') || event.target === panelsBtn) return;
      menu.hidden = true;
      panelsBtn.setAttribute('aria-expanded', 'false');
    });
    document.addEventListener('keydown', (event) => {
      if (event.key !== 'Escape' || menu.hidden) return;
      menu.hidden = true;
      panelsBtn.setAttribute('aria-expanded', 'false');
      panelsBtn.focus();
    });
  }

  render();
  applyPreset(state.panelsPreset, { silent: true });
  wire();
  initForecastHandle();
  syncTabIndicator();
  // The active tab class is applied after this module mounts (and the view may
  // still be hidden), so re-measure once the shell has settled.
  window.setTimeout(syncTabIndicator, 0);
  window.setTimeout(syncTabIndicator, 320);
  window.setTimeout(syncTimelineVar, 0);
  window.setTimeout(syncTimelineVar, 320);
  window.addEventListener('resize', syncTimelineVar);
  window.addEventListener('resize', syncTabIndicator);
  window.requestAnimationFrame(syncTimelineVar);
  window.requestAnimationFrame(syncTabIndicator);
}

/* The forecast handle is dragged along the same track as the playhead. It sets
   where "now + forecast" points without moving the scrubber itself. */
function initForecastHandle() {
  const handle = $('.timeline-forecast-handle');
  const track = $('#simulationTrack');
  if (!handle || !track) return;

  const place = (event) => {
    const rect = track.getBoundingClientRect();
    if (!rect.width) return;
    const ratio = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
    const minute = Math.min(1439, Math.round((ratio * 1440) / 5) * 5);
    state.forecastMinute = minute;
    handle.dataset.minute = String(minute);
    handle.style.left = `${(minute / 1440) * 100}%`;
    updateFutureBand();
  };

  handle.addEventListener('pointerdown', (event) => {
    event.preventDefault();
    handle.classList.add('is-dragging');
    place(event);
    const move = (moveEvent) => place(moveEvent);
    const up = () => {
      handle.classList.remove('is-dragging');
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  });
}

/* -------------------------------------------------------------------- render */

/* The green pill under the active mode slides between tabs instead of
   blinking from one to the next. */
function syncTabIndicator() {
  const bar = $('.live-mode-tabs');
  const active = $('.live-mode-tab.is-active');
  if (!bar || !active) return;
  let indicator = $('.mode-tab-indicator', bar);
  if (!indicator) {
    indicator = document.createElement('span');
    indicator.className = 'mode-tab-indicator';
    indicator.setAttribute('aria-hidden', 'true');
    bar.prepend(indicator);
  }
  indicator.style.left = `${active.offsetLeft}px`;
  indicator.style.width = `${active.offsetWidth}px`;
}

/* Collapsed panels shrink to a pill that still carries the headline number,
   so hiding detail never hides the state of the corridor. */
function collapsedPill() {
  if (state.mode === 'optimize') {
    const recs = modeData
      .recommendations(state.zone, nowMinute())
      .filter((rec) => !state.dismissed.has(rec.id));
    const lead = recs[0];
    return `
      <button type="button" class="mode-pill" data-panel-expand aria-expanded="false" aria-label="Expand recommendations">
        <span class="mode-pill-dot" aria-hidden="true"></span>
        <span class="mode-pill-copy"><strong>${recs.length} recommendations</strong><i>${lead ? `−${lead.delayMin} min delay available` : 'Corridor clear'}</i></span>
      </button>`;
  }

  if (state.mode === 'predict') {
    const forecast = isLive()
      ? liveForecast()
      : modeData.forecast(state.zone, state.minute, [...state.inputs]);
    if (!forecast) {
      return `
      <button type="button" class="mode-pill" data-panel-expand aria-expanded="false" aria-label="Expand forecast">
        <span class="mode-pill-dot is-predict" aria-hidden="true"></span>
        <span class="mode-pill-copy"><strong>Forecast</strong><i>collecting run samples</i></span>
      </button>`;
    }
    const peakLabel = isLive() ? forecast.peak.clock : forecast.peak.label;
    const headline = isLive()
      ? `${Math.round(forecast.projectedQueue)} veh in ${forecast.horizonMin} min`
      : `+${forecast.expectedDelay} m`;
    return `
      <button type="button" class="mode-pill" data-panel-expand aria-expanded="false" aria-label="Expand forecast">
        <span class="mode-pill-dot is-predict" aria-hidden="true"></span>
        <span class="mode-pill-copy"><strong>Peak ${peakLabel}</strong><i>${headline} · ${Math.round(forecast.confidence * 100)}% conf.</i></span>
      </button>`;
  }

  return '';
}

function modeLayerMarkup(mode) {
  if (mode === 'optimize') {
    return state.panelCollapsed ? collapsedPill() : optimizePanel();
  }
  if (mode === 'predict') {
    if (state.panelCollapsed) return collapsedPill();
    // A live run forecasts the run; only the idle demo uses the synthetic day model.
    return isLive() ? predictLivePanel() : predictPanel();
  }
  return mode === 'roam' ? roamStrip() : '';
}

function swapModeLayer(markup) {
  const leaving = [...root.children];
  leaving.forEach((node) => {
    if (node.classList.contains('is-leaving')) {
      node.remove();
      return;
    }
    node.classList.remove('is-entering');
    node.classList.add('is-leaving');
    node.setAttribute('aria-hidden', 'true');
  });

  if (markup) {
    const before = new Set(root.children);
    root.insertAdjacentHTML('beforeend', markup);
    [...root.children].forEach((node) => {
      if (!before.has(node)) node.classList.add('is-entering');
    });
  }

  window.clearTimeout(modeLayerExitTimer);
  modeLayerExitTimer = window.setTimeout(() => {
    [...root.children].forEach((node) => {
      if (node.classList.contains('is-leaving')) node.remove();
    });
  }, MODE_LAYER_EXIT_MS);
}

function render() {
  if (!root) return;
  // Reset when the run changes: a restart must not inherit applied/dismissed rows.
  const runId = getLiveRunId();
  if (runId !== lastRunId) {
    lastRunId = runId;
    state.applied.clear();
    state.dismissed.clear();
    state.sigDrafts.clear();
    state.previewId = null;
    saveState();
  }
  const view = document.getElementById('liveMapView');
  const mode = state.mode;
  const previousMode = lastRenderedMode;

  // The map highlight and the trip estimate both come from the run's own network;
  // fetch it once per scenario and re-render when it lands.
  const scenario = getLiveState()?.scenario;
  if (isLive() && scenario && (mode === 'optimize' || mode === 'predict')) {
    if (!geometryFor(scenario) && !geometryState(scenario).pending) {
      loadGeometry(scenario).then(() => {
        if (getLiveState()?.scenario !== scenario) return;
        render();
        syncMapForMode(state.mode);
      });
    }
  }
  const modeChanged = mode !== previousMode;

  if (view) view.dataset.mode = mode;

  const markup = modeLayerMarkup(mode);
  if (modeChanged) swapModeLayer(markup);
  else root.innerHTML = markup;

  if (view) {
    const dockSwap = modeChanged && previousMode !== '' && previousMode !== 'roam' && mode !== 'roam';
    window.clearTimeout(dockSwapTimer);
    view.classList.toggle('is-mode-switching', dockSwap);
    if (dockSwap) {
      dockSwapTimer = window.setTimeout(() => view.classList.remove('is-mode-switching'), DOCK_SWAP_MS);
    }
  }

  syncTimelineVar();

  const timelineEl = $('.simulation-timeline');
  const future = $('.timeline-future', timelineEl || document);
  const compare = $('.timeline-compare', timelineEl || document);
  const handle = $('.timeline-forecast-handle', timelineEl || document);
  const signal = $('.signal-editor', document);

  if (future) future.hidden = mode !== 'predict';
  if (compare) compare.hidden = mode !== 'optimize';
  if (handle) handle.hidden = mode !== 'predict';
  if (signal) signal.hidden = mode !== 'optimize';
  const actionGrid = $('.live-action-grid');
  if (actionGrid) actionGrid.hidden = mode === 'optimize';

  if (mode === 'optimize') updateCompareBand();
  if (mode === 'predict') updateFutureBand();
  if (mode === 'roam') {
    // The stats strip lives inside the timeline so it always hugs the rail,
    // whatever height the responsive chrome gives it.
    const strip = $('.roam-strip');
    const timelineEl = $('.simulation-timeline');
    if (strip && timelineEl) timelineEl.append(strip);
  } else {
    $('.simulation-timeline .roam-strip')?.remove();
  }

  syncMapForMode(mode);
  const canvas = getMap()?.getCanvas?.();
  if (canvas) canvas.style.cursor = mode === 'predict' && state.etaPick ? 'crosshair' : '';
  lastRenderedMode = mode;
}

/* The Roam strip sits directly above the timeline, so it needs the rail's real
   height — the responsive layout wraps the controls and changes it. */
function syncTimelineVar() {
  const view = document.getElementById('liveMapView');
  const track = document.querySelector('.simulation-timeline');
  if (!view || !track) return;
  const height = track.getBoundingClientRect().height;
  if (height > 0) view.style.setProperty('--timeline-h', `${Math.round(height)}px`);
}

function updateCompareBand() {
  const compare = $('.timeline-compare');
  if (!compare) return;
  const progress = (state.minute / 1440) * 100;
  const before = $('.tc-before', compare);
  const after = $('.tc-after', compare);
  if (before) before.style.width = `${Math.max(2, progress)}%`;
  const preview = state.previewId
    ? modeData.recommendations(state.zone, nowMinute()).find((r) => r.id === state.previewId)
    : null;
  if (after) {
    after.style.width = `${Math.max(2, progress)}%`;
    after.style.opacity = preview ? '1' : '0';
  }
}

/* The timeline is an operating day starting at 08:00, so a run's elapsed seconds
   land on that axis, not at 0:00. */
function timelineMinute(seconds) {
  return Math.floor((((Number(seconds) || 0) + 8 * 3600) % 86400) / 60);
}

function updateFutureBand() {
  const future = $('.timeline-future');
  if (!future) return;
  const live = isLive();
  const forecast = modeData.forecast(state.zone, state.minute, [...state.inputs]);
  // A live run forecasts a horizon of minutes from its own clock; only the idle
  // demo shades the rest of the day, because that is what it is modelling.
  const nowMinute = live ? timelineMinute(getLiveState()?.simulationTime) : state.minute;
  const span = live
    ? Math.max(5, Number(liveForecast()?.horizonMin) || 15)
    : 1440 - nowMinute;
  const nowPct = (nowMinute / 1440) * 100;
  future.style.left = `${nowPct}%`;
  future.style.width = `${Math.max(0, (span / 1440) * 100)}%`;
  future.style.setProperty('--band', `${Math.min(34, 10 + forecast.band * 4)}px`);

  const handle = $('.timeline-forecast-handle');
  if (handle) {
    const target = Number(
      handle.dataset.minute || (live ? nowMinute + span : Math.min(1439, state.minute + 120))
    );
    handle.style.left = `${(Number(target) / 1440) * 100}%`;
  }
}

/* ----------------------------------------------------------------- gauges */


function setGaugeValue(index, value) {
  const hosts = $$('[data-gauge]');
  const host = hosts[index];
  if (host?.gauge) host.gauge.setValue(value);
  host?.classList.toggle('is-forecast', value !== null && value !== undefined);
}

function setGaugeGhost(index, value) {
  const hosts = $$('[data-gauge]');
  const host = hosts[index];
  host?.gauge?.setGhost(value);
}

/* Numbers count between values instead of jumping. */
function setDockMetricText(selector, text) {
  const metric = $(selector);
  if (!metric?.firstChild) return;
  metric.firstChild.nodeValue = String(text);
}

function setDockMetric(selector, value) {
  const metric = $(selector);
  if (!metric?.firstChild) return;
  const target = Math.round(Number(value) || 0);
  if (prefersReducedMotion()) {
    metric.firstChild.nodeValue = String(target);
    return;
  }
  const startValue = Number(metric.firstChild.nodeValue) || 0;
  if (startValue === target) return;
  const started = performance.now();
  const tick = (now) => {
    const t = Math.min(1, (now - started) / 420);
    const eased = 1 - (1 - t) ** 3;
    metric.firstChild.nodeValue = String(Math.round(startValue + (target - startValue) * eased));
    if (t < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

/* The header lines are data too: they name what the gauges are measuring. */
function syncGaugeCaptions() {
  const loadSub = $('.live-load-card .live-dock-sub');
  if (loadSub) {
    const metrics = liveMetrics();
    loadSub.textContent = isLive()
      ? `${Number(metrics.vehicles) || 0} vehicles · ${Number(metrics.queued) || 0} queued`
      : zoneLabel();
  }
}

/* Efficiency delta against the first sample of the run, not a fixed +4.2. */
function syncEfficiencyDelta() {
  const delta = $('.live-efficiency-card .live-dock-delta');
  if (!delta) return;
  const current = liveEfficiency();
  const history = getLiveHistory();
  const first = history.length > 1 ? history[0] : null;
  if (current == null || !first) {
    delta.innerHTML = '<strong>—</strong> vs. run start';
    return;
  }
  const startVehicles = Number(first.vehicles) || 0;
  const startQueued = Number(first.queued) || 0;
  const startLoad = startVehicles ? (startQueued / startVehicles) * 100 : 0;
  const startEfficiency = Math.max(0, Math.min(100, 100 - startLoad * 0.82));
  const diff = current - startEfficiency;
  const magnitude = Math.abs(diff).toFixed(1);
  const sign = diff > 0.05 ? '+' : diff < -0.05 ? '−' : '';
  delta.innerHTML = `<strong>${sign}${magnitude}</strong> vs. run start`;
}

function syncGaugesForMode() {
  const loadSelector = '.live-load-card .live-dock-metric';
  const effSelector = '.live-efficiency-card .live-dock-metric';
  syncGaugeCaptions();

  if (state.mode === 'optimize') {
    const base = modeData.recommendations(state.zone, nowMinute());
    const preview = state.previewId ? base.find((r) => r.id === state.previewId) : null;
    const projectedLoad = preview ? preview.projected.load : (liveLoad() ?? 0);
    const projectedEff = preview ? preview.projected.efficiency : (liveEfficiency() ?? 0);
    setGaugeValue(0, projectedLoad);
    setGaugeValue(1, projectedEff);
    setGaugeGhost(0, preview ? (liveLoad() ?? 0) : null);
    setGaugeGhost(1, preview ? (liveEfficiency() ?? 0) : null);
    setDockMetric(loadSelector, projectedLoad);
    setDockMetric(effSelector, projectedEff);
    return;
  }

  if (state.mode === 'predict') {
    const metrics = liveMetrics();
    const vehicles = Number(metrics.vehicles) || 0;
    const forecast = isLive() ? liveForecast() : null;
    const current = liveLoad();
    // Projected load assumes the vehicle count stays where it is now; the panel shows
    // the projection with its confidence for that reason.
    const projected = forecast && vehicles
      ? Math.round(Math.min(100, (forecast.projectedQueue / vehicles) * 100))
      : null;
    const predictedLoad = projected ?? current ?? 0;
    const predictedEff = Math.round(Math.max(0, 100 - predictedLoad * 0.82));
    setGaugeValue(0, predictedLoad);
    setGaugeValue(1, predictedEff);
    setGaugeGhost(0, current);
    setGaugeGhost(1, liveEfficiency());
    if (projected == null) setDockMetricText(loadSelector, '—');
    else setDockMetric(loadSelector, projected);
    setDockMetric(effSelector, predictedEff);
    return;
  }

  const load = liveLoad();
  const efficiency = liveEfficiency();
  // Idle means nothing measured yet: empty gauges, not a permanent 52% / 46%.
  setGaugeValue(0, load ?? 0);
  setGaugeValue(1, efficiency ?? 0);
  setGaugeGhost(0, null);
  setGaugeGhost(1, null);
  if (load == null) setDockMetricText(loadSelector, '—');
  else setDockMetric(loadSelector, load);
  if (efficiency == null) setDockMetricText(effSelector, '—');
  else setDockMetric(effSelector, efficiency);
  syncEfficiencyDelta();
}

/** app.js calls this on every published simulation snapshot. */
export function refreshLiveGauges() {
  if (state.mode === 'roam') {
    syncRoamStats();
    syncRoamClassOptions();
    maybeDropStoppedPov();
  }
  if (state.mode === 'predict' && isLive()) {
    refreshForecast(15).then((arrived) => {
      if (!arrived) return;
      render();
      syncGaugesForMode();
    });
  }
  syncGaugesForMode();
}

/* ------------------------------------------------------------------ presets */

const PRESETS = {
  full: new Set(),
  focus: new Set(['zone', 'queue', 'dock']),
  map: new Set(['zone', 'queue', 'dock', 'timeline']),
  ops: new Set(['queue'])
};

function applyPreset(name, { silent = false } = {}) {
  state.panelsPreset = name;
  state.hiddenPanels = new Set(PRESETS[name] || []);
  const view = document.getElementById('liveMapView');
  if (view) {
    view.classList.toggle('is-panel-zone-hidden', state.hiddenPanels.has('zone'));
    view.classList.toggle('is-panel-queue-hidden', state.hiddenPanels.has('queue'));
    view.classList.toggle('is-panel-dock-hidden', state.hiddenPanels.has('dock'));
    view.classList.toggle('is-panel-timeline-hidden', state.hiddenPanels.has('timeline'));
  }
  $$('[data-panel-toggle]').forEach((box) => {
    box.checked = !state.hiddenPanels.has(box.dataset.panelToggle);
  });
  $$('[data-preset]').forEach((btn) => btn.classList.toggle('is-on', btn.dataset.preset === name));
  saveState();
  if (!silent) showToast(`${name === 'map' ? 'Map only' : name[0].toUpperCase() + name.slice(1)} layout applied.`);
}

/* -------------------------------------------------------------------- wiring */

function setMinute(minute) {
  state.minute = Math.max(0, Math.min(1439, Math.round(minute)));
  if (state.mode === 'optimize') {
    updateCompareBand();
    render();
    syncGaugesForMode();
  } else if (state.mode === 'predict') {
    updateFutureBand();
    // The forecast layer is coloured by the volume under the scrubber.
    syncMapForMode('predict');
  } else if (state.mode === 'roam') {
    // Idle roam reads the demo day model, so the strip follows the scrubber.
    syncRoamStats();
  }
}

function wire() {
  document.addEventListener('click', (event) => {
    const target = event.target.closest('[data-rec-apply],[data-rec-preview],[data-rec-dismiss],[data-rec-clear],[data-whatif],[data-compare-toggle],[data-sig-apply],[data-eta-pick],[data-eta-clear],[data-roam-seg],[data-roam-open],[data-roam-follow],[data-roam-pov],[data-roam-flythrough],[data-roam-recenter],[data-roam-close],[data-preset],[data-panel-toggle],[data-panel-collapse],[data-panel-expand]');
    if (!target) return;

    if (target.dataset.recApply) {
      const id = target.dataset.recApply;
      if (state.applied.has(id)) {
        state.applied.delete(id);
        showToast('Recommendation reverted.');
        saveState();
        render();
        syncGaugesForMode();
        return;
      }
      const rec = modeData
        .recommendations(state.zone, nowMinute())
        .find((entry) => entry.id === id);
      if (!rec) return;
      if (!rec.junction) {
        showToast('Start a live run to change a signal.');
        return;
      }
      target.disabled = true;
      applySignalChange(rec.junction, rec.green)
        .then((snapshot) => {
          setLiveState(snapshot, snapshot.trend);
          state.applied.add(id);
          saveState();
          showToast(
            rec.held
              ? `${rec.junction} green held for ${rec.green}s.`
              : `${rec.junction} green extended to ${rec.green}s.`
          );
        })
        .catch((error) => showToast(`Not applied: ${error.message}`))
        .finally(() => {
          render();
          syncGaugesForMode();
        });
      return;
    }

    if (target.dataset.recPreview) {
      state.previewId = state.previewId === target.dataset.recPreview ? null : target.dataset.recPreview;
      render();
      syncGaugesForMode();
      syncMapForMode(state.mode);
      return;
    }

    if (target.dataset.recDismiss) {
      const id = target.dataset.recDismiss;
      state.dismissed.add(id);
      if (state.previewId === id) state.previewId = null;
      saveState();
      render();
      showToast('Recommendation dismissed.', {
        action: { label: 'Undo', onClick: () => { state.dismissed.delete(id); render(); } }
      });
      return;
    }

    if ('recClear' in target.dataset) {
      state.previewId = null;
      render();
      syncGaugesForMode();
      syncMapForMode(state.mode);
      return;
    }

    if (target.dataset.etaPick) {
      const slot = target.dataset.etaPick;
      state.etaPick = state.etaPick === slot ? null : slot;
      render();
      syncMapForMode(state.mode);
      return;
    }

    if ('etaClear' in target.dataset) {
      state.etaA = null;
      state.etaB = null;
      state.etaPick = null;
      etaMemo = { key: null, value: null };
      render();
      syncMapForMode(state.mode);
      return;
    }

    if (target.dataset.whatif) {
      const id = target.dataset.whatif;
      if (state.inputs.has(id)) state.inputs.delete(id);
      else state.inputs.add(id);
      saveState();
      render();
      syncGaugesForMode();
      updateFutureBand();
      return;
    }

    if ('compareToggle' in target.dataset) {
      state.compareTypical = !state.compareTypical;
      saveState();
      render();
      return;
    }

    if ('sigApply' in target.dataset) {
      const timing = modeData.signalTiming(state.zone, nowMinute());
      const staged = [...state.sigDrafts.entries()]
        .map(([id, green]) => {
          const phase = timing.phases.find((entry) => entry.id === id);
          return phase?.tls ? { tls: phase.tls, green } : null;
        })
        .filter(Boolean);
      if (!staged.length) {
        showToast('Move a slider to stage a change.');
        return;
      }
      target.disabled = true;
      Promise.allSettled(staged.map((entry) => applySignalChange(entry.tls, entry.green))).then(
        (results) => {
          const applied = results.filter((result) => result.status === 'fulfilled').length;
          const refused = results.length - applied;
          state.sigDrafts.clear();
          render();
          showToast(
            refused
              ? `${applied} split(s) applied, ${refused} refused by the run.`
              : `${applied} split(s) applied to the live run.`
          );
        }
      );
      return;
    }

    if ('roamOpen' in target.dataset) {
      const inspector = $('.roam-inspector');
      if (inspector) inspector.hidden = !inspector.hidden;
      target.classList.toggle('is-on', !inspector?.hidden);
      return;
    }

    if (target.dataset.roamSeg) {
      const inspector = $('.roam-inspector');
      const title = $('[data-roam-inspector-title]');
      if (inspector) inspector.hidden = false;
      if (title) title.textContent = target.querySelector('.roam-seg-name')?.textContent || 'Inspector';
      return;
    }

    if ('roamClose' in target.dataset) {
      const inspector = $('.roam-inspector');
      if (inspector) inspector.hidden = true;
      return;
    }

    if ('roamFollow' in target.dataset) {
      if (state.followMode) {
        state.followMode = false;
        state.povMode = false;
        state.followVehicleId = null;
        dispatchRoamFollow(null);
        syncRoamPills();
        showToast('Follow mode off.');
        return;
      }
      const vehicle = pickRoamVehicle();
      if (!vehicle) {
        showToast('Start a live run with vehicles to follow.');
        return;
      }
      state.followMode = true;
      state.povMode = false;
      state.followVehicleId = vehicle.id;
      dispatchRoamFollow({ id: vehicle.id, view: 'follow' });
      syncRoamPills();
      showToast(`Following ${vehicle.id} at ${Math.round((vehicle.speed || 0) * 3.6)} km/h.`);
      return;
    }

    if ('roamPov' in target.dataset) {
      if (state.povMode) {
        state.povMode = false;
        if (state.followVehicleId) {
          dispatchRoamFollow({ id: state.followVehicleId, view: 'follow' });
        } else {
          state.followMode = false;
          dispatchRoamFollow(null);
        }
        syncRoamPills();
        showToast(state.followVehicleId ? 'Back to chase view.' : 'POV off.');
        return;
      }
      const followed = roamVehicles().find((vehicle) => vehicle.id === state.followVehicleId);
      const vehicle = followed || pickRoamVehicle();
      if (!vehicle) {
        showToast('Start a live run with vehicles for the in-vehicle view.');
        return;
      }
      state.followMode = true;
      state.povMode = true;
      state.followVehicleId = vehicle.id;
      povStopVehicleId = null;
      povStoppedAt = null;
      dispatchRoamFollow({ id: vehicle.id, view: 'pov' });
      syncRoamPills();
      showToast(`In-vehicle view of ${vehicle.id}.`);
      return;
    }

    if ('roamFlythrough' in target.dataset) {
      const mapbox = getMap();
      if (!mapbox) return showToast('Map is not ready yet.');
      const scenario = getScenario();
      if (!scenario?.liveCenter) return showToast('Scenario view is not available yet.');
      mapbox.flyTo({
        center: scenario.liveCenter,
        zoom: (scenario.liveZoom || 15) + 0.4,
        pitch: 58,
        bearing: 34,
        duration: prefersReducedMotion() ? 0 : 2600,
        essential: true
      });
      return;
    }

    if ('roamRecenter' in target.dataset) {
      const mapbox = getMap();
      if (!mapbox) return;
      const scenario = getScenario();
      if (!scenario?.liveCenter) return showToast('Scenario view is not available yet.');
      mapbox.easeTo({
        center: scenario.liveCenter,
        zoom: scenario.liveZoom || 15,
        pitch: 45,
        bearing: 0,
        duration: prefersReducedMotion() ? 0 : 900
      });
      return;
    }

    if ('panelCollapse' in target.dataset) {
      state.panelCollapsed = true;
      render();
      $('.mode-pill')?.focus();
      return;
    }

    if ('panelExpand' in target.dataset) {
      state.panelCollapsed = false;
      render();
      $('.mp-icon-btn')?.focus();
      return;
    }

    if (target.dataset.preset) {
      applyPreset(target.dataset.preset);
      const menu = $('.panels-menu');
      const opener = $('[data-panels-menu]');
      if (menu) menu.hidden = true;
      opener?.setAttribute('aria-expanded', 'false');
      return;
    }

    if (target.dataset.panelToggle) {
      const panel = target.dataset.panelToggle;
      if (target.checked) state.hiddenPanels.delete(panel);
      else state.hiddenPanels.add(panel);
      const view = document.getElementById('liveMapView');
      view?.classList.toggle(`is-panel-${panel}-hidden`, !target.checked);
      saveState();
    }
  });

  // Signal sliders stage a change only; nothing is sent until Apply is pressed.
  document.addEventListener('input', (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement) || !('sig' in target.dataset)) return;
    const value = Number(target.value);
    const out = $(`[data-sig-value="${target.dataset.sig}"]`);
    if (out) out.textContent = `${value}s`;
    const timing = modeData.signalTiming(state.zone, nowMinute());
    const phase = timing.phases.find((entry) => entry.id === target.dataset.sig);
    if (timing.live && phase?.tls) state.sigDrafts.set(target.dataset.sig, value);
  });

  // Timeline scrubbing drives the mode panels.
  const scrubber = document.getElementById('simulationTime');
  scrubber?.addEventListener('input', () => {
    setMinute(Number(scrubber.value) / 60);
  });

  // Mode switching.
  document.addEventListener('sumo:livetabchange', (event) => {
    state.mode = event.detail?.tab || 'events';
    state.panelCollapsed = false;
    if (state.mode !== 'roam' && (state.followMode || state.povMode)) {
      state.followMode = false;
      state.povMode = false;
      state.followVehicleId = null;
      dispatchRoamFollow(null);
    }
    if (state.mode !== 'optimize') state.previewId = null;
    render();
    syncGaugesForMode();
    if (state.mode === 'predict' && isLive()) {
      refreshForecast(15).then((arrived) => {
        if (!arrived) return;
        render();
        syncGaugesForMode();
      });
    }
    syncTabIndicator();
    showModeHint();
  });

  // The followed vehicle can leave the run (arrived, teleported, run restarted).
  document.addEventListener('sumo:roamfollowlost', () => {
    if (!state.followMode && !state.povMode) return;
    state.followMode = false;
    state.povMode = false;
    state.followVehicleId = null;
    syncRoamPills();
    showToast('Follow ended: that vehicle left the live run.');
  });

  // Clicking a vehicle on the Roam map retargets the camera. app.js finds the
  // nearest rendered vehicle (the 3D bodies are a custom layer, so Mapbox cannot
  // query them) and sends the id here.
  document.addEventListener('sumo:roamvehiclepick', (event) => {
    if (state.mode !== 'roam') return;
    const id = String(event.detail?.id || '');
    const vehicle = roamVehicles().find((item) => String(item.id) === id);
    if (!vehicle) return;
    state.followMode = true;
    state.followVehicleId = vehicle.id;
    dispatchRoamFollow({ id: vehicle.id, view: state.povMode ? 'pov' : 'follow' });
    syncRoamPills();
    showToast(
      state.povMode
        ? `In-vehicle view of ${vehicle.id}.`
        : `Following ${vehicle.id} at ${Math.round((vehicle.speed || 0) * 3.6)} km/h.`
    );
  });

  // The class picker targets a representative of the chosen class. Emergency and
  // bus are explicitly selectable even when cars dominate the headcount.
  document.addEventListener('change', (event) => {
    const target = event.target;
    if (!(target instanceof HTMLSelectElement) || !('roamClass' in target.dataset)) return;
    state.roamClass = target.value;
    if (!state.roamClass) return;
    const candidates = roamVehicles().filter(
      (vehicle) =>
        !vehicle.pedestrian && String(vehicle.vehicleClass || 'car') === state.roamClass
    );
    const vehicle = pickRoamVehicle(candidates);
    if (!vehicle) {
      showToast('No vehicle of that class in the run right now.');
      return;
    }
    state.followMode = true;
    state.followVehicleId = vehicle.id;
    dispatchRoamFollow({ id: vehicle.id, view: state.povMode ? 'pov' : 'follow' });
    syncRoamPills();
    showToast(
      state.povMode
        ? `In-vehicle view of ${vehicle.id}.`
        : `Following ${ROAM_CLASS_LABELS[state.roamClass] || state.roamClass}: ${vehicle.id}.`
    );
  });

  const view = document.getElementById('liveMapView');

  // Keyboard shortcuts.
  document.addEventListener('keydown', (event) => {
    const target = event.target instanceof Element ? event.target : null;
    if (target?.matches('input, textarea, select, [contenteditable="true"]')) return;
    if (event.altKey || event.ctrlKey || event.metaKey) return;
    const tabs = ['events', 'optimize', 'predict', 'roam'];

    if (event.key >= '1' && event.key <= '4') {
      document.querySelector(`[data-live-mode="${tabs[Number(event.key) - 1]}"]`)?.click();
      return;
    }

    if (state.mode === 'roam' && !event.shiftKey) {
      const key = event.key.toLowerCase();
      if (key === 'f') {
        document.querySelector('[data-roam-follow]')?.click();
        return;
      }
      if (key === 'v') {
        document.querySelector('[data-roam-pov]')?.click();
        return;
      }
      if (key === 'n' || key === 'p') {
        cycleRoamVehicle(key === 'n' ? 1 : -1);
        return;
      }
    }

    if (state.mode === 'roam' && event.key === 'Escape') {
      stopRoamFollow();
      return;
    }

    if (event.key.toLowerCase() === 'h') {
      const collapsed = view?.classList.toggle('live-panels-collapsed');
      showToast(collapsed ? 'Panels hidden — press H to restore.' : 'Panels restored.');
      return;
    }

    if (event.code === 'Space') {
      event.preventDefault();
      document.getElementById('simulationPlay')?.click();
      return;
    }

    if (event.key === '[' || event.key === ']') {
      document.getElementById('simulationSpeed')?.click();
      return;
    }

    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      const input = document.getElementById('simulationTime');
      if (!input) return;
      const step = (event.shiftKey ? 15 : 5) * 60;
      input.value = String(Math.max(0, Math.min(86400, Number(input.value) + (event.key === 'ArrowRight' ? step : -step))));
      input.dispatchEvent(new Event('input', { bubbles: true }));
      event.preventDefault();
    }
  });
}

function showModeHint() {
  const hints = {
    optimize: 'Optimize · preview a recommendation to see its effect on the map.',
    predict: 'Predict · scrub past now to shade the forecast window.',
    roam: 'Roam · click a vehicle, F follow, V POV, N/P cycle, Esc stop.',
    events: ''
  };
  const hint = hints[state.mode];
  if (hint) showToast(hint);
}

/* ---------------------------------------------------------------------- init */

export function initModes(options = {}) {
  getMap = options.getMap || (() => window.sumoLiveMap || null);
  showToast = options.showToast || (() => {});
  getScenario = options.getScenario || (() => null);
  mount();

  /* The map style is often still loading on first paint; re-apply the mode's
     layers as soon as the scene exists. */
  document.addEventListener('sumo:livemapready', () => {
    map = getMap();
    syncMapForMode(state.mode);
  });

  /* Deep links can enter a mode before the map's load event fires, and this
     module may attach its listener after that event. Retry until the scene
     exists, then sync whenever the style finishes loading. */
  const attachToMap = (attempt = 0) => {
    const mapbox = getMap();
    if (mapbox && !styleHooked) {
      styleHooked = true;
      // Styles can be swapped at runtime; re-add the mode layers each time.
      mapbox.on?.('style.load', () => syncMapForMode(state.mode));
    }
  if (mapbox) {
    if (!clickHooked) {
      clickHooked = true;
      mapbox.on?.('click', handleMapClick);
    }
    syncMapForMode(state.mode);
    // Events needs no mode layers; the others are ready once their own source exists.
    const ready =
      state.mode === 'events' ||
      mapbox.getLayer?.('mode-approach-line') ||
      mapbox.getLayer?.('mode-eta-line');
    if (ready) return;
  }
  if (attempt < 60) window.setTimeout(() => attachToMap(attempt + 1), 250);
  };
  window.setTimeout(() => attachToMap(0), 0);

  const params = new URLSearchParams(window.location.search);
  const tab = params.get('tab');
  if (tab) {
    state.mode = tab;
    render();
    syncGaugesForMode();
  }
}
