/**
 * Live-map modes: Optimize · Predict · Roam.
 *
 * One controller, one store, three panel systems. The Events tab keeps the
 * existing dashboard untouched; switching tabs crossfades the mode layer in
 * and swaps what the map and timeline show.
 */

import { modeData, formatClock } from './data.js';

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
  forecastMinute: null,
  hiddenPanels: new Set()
};

let map = null;
let getMap = () => null;
let showToast = () => {};
let dashTimer = 0;
let lastRenderedMode = '';
let modeLayerExitTimer = 0;
let dockSwapTimer = 0;
let styleHooked = false;

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
        <span class="mp-clock">${clock(state.minute)}</span>
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

function ensureAdaptive(mapbox, intensity = 1) {
  const features = modeData.congestion(state.zone, intensity);

  if (!mapbox.getSource('mode-congestion')) {
    mapbox.addSource('mode-congestion', { type: 'geojson', data: features });
  } else {
    mapbox.getSource('mode-congestion').setData(features);
  }

  if (!mapbox.getLayer('mode-congestion-line')) {
    mapbox.addLayer({
      id: 'mode-congestion-line',
      type: 'line',
      source: 'mode-congestion',
      filter: ['==', ['get', 'kind'], 'corridor'],
      layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: {
        'line-width': 7,
        'line-opacity': 0,
        'line-color': [
          'interpolate',
          ['linear'],
          ['get', 'intensity'],
          0, '#7cbd40',
          0.55, '#d8b13a',
          1, '#c74a4a'
        ]
      }
    });
  }

  if (!mapbox.getLayer('mode-reroute-line')) {
    mapbox.addLayer({
      id: 'mode-reroute-line',
      type: 'line',
      source: 'mode-congestion',
      filter: ['==', ['get', 'kind'], 'reroute'],
      layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: {
        'line-width': 3,
        'line-opacity': 0,
        'line-color': '#5f9c2b',
        'line-dasharray': [0, 4, 3]
      }
    });
  }
}

/* Predict needs a halo behind the corridor: the softer and wider it is, the
   less certain the forecast. It sits under the coloured line. */
function ensureForecastBand(mapbox) {
  if (mapbox.getLayer('mode-forecast-band')) return;
  mapbox.addLayer(
    {
      id: 'mode-forecast-band',
      type: 'line',
      source: 'mode-congestion',
      filter: ['==', ['get', 'kind'], 'corridor'],
      layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: {
        'line-width': 22,
        'line-opacity': 0,
        'line-color': '#3d6f9e',
        'line-blur': 10
      }
    },
    mapbox.getLayer('mode-congestion-line') ? 'mode-congestion-line' : undefined
  );
}

function fadeLayers(mapbox, ids, opacity, duration = 420) {
  ids.forEach((id) => {
    if (!mapbox.getLayer(id)) return;
    const start = performance.now();
    const from = Number(mapbox.getPaintProperty(id, 'line-opacity') ?? 0);
    if (prefersReducedMotion()) {
      mapbox.setPaintProperty(id, 'line-opacity', opacity);
      return;
    }
    const step = (now) => {
      const t = Math.min(1, (now - start) / duration);
      mapbox.setPaintProperty(id, 'line-opacity', from + (opacity - from) * t);
      if (t < 1 && mapbox.getLayer(id)) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  });
}

function animateDashes(active) {
  window.clearInterval(dashTimer);
  if (!active || !map || prefersReducedMotion()) return;
  let offset = 0;
  dashTimer = window.setInterval(() => {
    if (!map?.getLayer('mode-reroute-line')) return;
    offset = (offset + 0.6) % 12;
    map.setPaintProperty('mode-reroute-line', 'line-dasharray', [0, offset, 3]);
  }, 90);
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
  const wantsOptimize = mode === 'optimize';
  const wantsPredict = mode === 'predict';
  const wantsPreview = wantsOptimize && Boolean(state.previewId);

  if (wantsOptimize) {
    ensureAdaptive(mapbox);
    fadeLayers(mapbox, ['mode-congestion-line'], 0.85);
    fadeLayers(mapbox, ['mode-reroute-line'], wantsPreview ? 1 : 0.55);
    if (mapbox.getLayer('mode-forecast-band')) fadeLayers(mapbox, ['mode-forecast-band'], 0);
    animateDashes(wantsPreview);
    return;
  }

  if (wantsPredict) {
    const forecast = modeData.forecast(state.zone, state.minute, [...state.inputs]);
    const predicted = Math.min(0.96, (LIVE_LOAD + forecast.expectedDelay * 0.9) / 100);
    ensureAdaptive(mapbox, predicted);
    ensureForecastBand(mapbox);
    if (mapbox.getLayer('mode-forecast-band')) {
      mapbox.setPaintProperty('mode-forecast-band', 'line-width', 16 + forecast.band * 2.4);
      fadeLayers(mapbox, ['mode-forecast-band'], 0.5);
    }
    fadeLayers(mapbox, ['mode-congestion-line'], 0.8);
    fadeLayers(mapbox, ['mode-reroute-line'], 0);
    animateDashes(false);
    return;
  }

  if (mapbox.getLayer('mode-congestion-line')) {
    fadeLayers(mapbox, ['mode-congestion-line', 'mode-reroute-line', 'mode-forecast-band'], 0);
    animateDashes(false);
  }
}

/* -------------------------------------------------------------- mode markup */

function optimizePanel() {
  const recs = modeData
    .recommendations(state.zone, state.minute)
    .filter((rec) => !state.dismissed.has(rec.id));

  if (!recs.length) {
    return `
      <aside class="mode-panel mp-optimize" data-panel="optimize">
        ${panelHead({
          icon: 'i-bulb',
          label: 'Optimize',
          title: 'Recommendations',
          sub: 'Sector 6 · all clear',
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
        sub: 'Sector 6 · ranked by delay saved',
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
            </div>`
          : `<p class="mp-foot-note">Impact is a modelled estimate for this sector at ${clock(state.minute)}. Preview before applying.</p>`
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
        sub: `Sector 6 · ${horizon}`,
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
          ${state.compareTypical ? '<span><i class="is-typical"></i>Typical day</span>' : ''}
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
        <p class="predict-note">Toggling an input re-runs the forecast for the selected time.</p>
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

function roamStrip() {
  const stats = modeData.roamStats(state.zone, state.minute);
  const segments = stats.segments
    .map(
      (seg) => `
      <li class="roam-seg is-${seg.state}" data-roam-seg="${seg.id}">
        <span class="roam-seg-name">${seg.label}</span>
        <span class="roam-seg-speed">${seg.speed} km/h</span>
      </li>`
    )
    .join('');

  return `
    <div class="mode-roam" data-panel="roam">
      <div class="roam-strip">
        <div class="roam-stat"><span>Speed</span><strong>${stats.speed}</strong><i>km/h</i></div>
        <div class="roam-stat"><span>Density</span><strong>${Math.round(stats.density * 100)}</strong><i>%</i></div>
        <div class="roam-stat"><span>Vehicles</span><strong>${stats.vehicles}</strong><i>live</i></div>
        <div class="roam-stat"><span>Incidents</span><strong>${stats.incidents}</strong><i>open</i></div>
      </div>

      <div class="roam-pills">
        <button type="button" class="roam-pill${state.followMode ? ' is-on' : ''}" data-roam-follow>Follow vehicle</button>
        <button type="button" class="roam-pill" data-roam-flythrough>Fly-through</button>
        <button type="button" class="roam-pill" data-roam-open>Segments</button>
        <button type="button" class="roam-pill" data-roam-recenter>Recenter</button>
      </div>

      <ul class="roam-legend">
        <li><span class="roam-dot is-flow"></span>Free flow</li>
        <li><span class="roam-dot is-dense"></span>Dense</li>
        <li><span class="roam-dot is-jam"></span>Jammed</li>
      </ul>

      <div class="roam-inspector" hidden>
        <header><strong data-roam-inspector-title>Inspector</strong><button type="button" class="mp-btn is-ghost" data-roam-close>Close</button></header>
        <ul class="roam-seg-list">${segments}</ul>
      </div>
    </div>`;
}

/* --------------------------------------------------------------- dock bits */

function signalEditor() {
  const timing = modeData.signalTiming(state.zone, state.minute);
  const rows = timing.phases
    .map(
      (phase) => `
      <label class="sig-row">
        <span class="sig-name">${phase.label}</span>
        <input type="range" min="6" max="60" step="1" value="${phase.green}" data-sig="${phase.id}" aria-label="${phase.label} green time">
        <span class="sig-value" data-sig-value="${phase.id}">${phase.green}s</span>
      </label>`
    )
    .join('');

  return `
    <div class="signal-editor" data-panel="signal-editor" hidden>
      <header class="signal-head"><h3>Signal timing</h3><span>${timing.cycle}s cycle</span></header>
      <div class="signal-body">${rows}</div>
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
      .recommendations(state.zone, state.minute)
      .filter((rec) => !state.dismissed.has(rec.id));
    const lead = recs[0];
    return `
      <button type="button" class="mode-pill" data-panel-expand aria-expanded="false" aria-label="Expand recommendations">
        <span class="mode-pill-dot" aria-hidden="true"></span>
        <span class="mode-pill-copy"><strong>${recs.length} recommendations</strong><i>${lead ? `−${lead.delayMin} min delay available` : 'Corridor clear'}</i></span>
      </button>`;
  }

  if (state.mode === 'predict') {
    const forecast = modeData.forecast(state.zone, state.minute, [...state.inputs]);
    return `
      <button type="button" class="mode-pill" data-panel-expand aria-expanded="false" aria-label="Expand forecast">
        <span class="mode-pill-dot is-predict" aria-hidden="true"></span>
        <span class="mode-pill-copy"><strong>Peak ${forecast.peak.label}</strong><i>+${forecast.expectedDelay} m · ${Math.round(forecast.confidence * 100)}% conf.</i></span>
      </button>`;
  }

  return '';
}

function modeLayerMarkup(mode) {
  if (mode === 'optimize' || mode === 'predict') {
    return state.panelCollapsed
      ? collapsedPill()
      : mode === 'optimize'
        ? optimizePanel()
        : predictPanel();
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
  const view = document.getElementById('liveMapView');
  const mode = state.mode;
  const previousMode = lastRenderedMode;
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
    ? modeData.recommendations(state.zone, state.minute).find((r) => r.id === state.previewId)
    : null;
  if (after) {
    after.style.width = `${Math.max(2, progress)}%`;
    after.style.opacity = preview ? '1' : '0';
  }
}

function updateFutureBand() {
  const future = $('.timeline-future');
  if (!future) return;
  const forecast = modeData.forecast(state.zone, state.minute, [...state.inputs]);
  const nowPct = (state.minute / 1440) * 100;
  future.style.left = `${nowPct}%`;
  future.style.width = `${Math.max(0, 100 - nowPct)}%`;
  future.style.setProperty('--band', `${Math.min(34, 10 + forecast.band * 4)}px`);

  const handle = $('.timeline-forecast-handle');
  if (handle) {
    const target = Number(handle.dataset.minute || Math.min(1439, state.minute + 120));
    handle.style.left = `${(Number(target) / 1440) * 100}%`;
  }
}

/* ----------------------------------------------------------------- gauges */

const LIVE_LOAD = 52;
const LIVE_EFFICIENCY = 46;

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

function syncGaugesForMode() {
  const loadSelector = '.live-load-card .live-dock-metric';
  const effSelector = '.live-efficiency-card .live-dock-metric';

  if (state.mode === 'optimize') {
    const base = modeData.recommendations(state.zone, state.minute);
    const preview = state.previewId ? base.find((r) => r.id === state.previewId) : null;
    const projectedLoad = preview ? preview.projected.load : LIVE_LOAD;
    const projectedEff = preview ? preview.projected.efficiency : LIVE_EFFICIENCY;
    setGaugeValue(0, projectedLoad);
    setGaugeValue(1, projectedEff);
    setGaugeGhost(0, preview ? LIVE_LOAD : null);
    setGaugeGhost(1, preview ? LIVE_EFFICIENCY : null);
    setDockMetric(loadSelector, projectedLoad);
    setDockMetric(effSelector, projectedEff);
    return;
  }

  if (state.mode === 'predict') {
    const forecast = modeData.forecast(state.zone, state.minute, [...state.inputs]);
    const predictedLoad = Math.min(96, LIVE_LOAD + forecast.expectedDelay * 0.9);
    const predictedEff = Math.max(24, LIVE_EFFICIENCY - forecast.band);
    setGaugeValue(0, predictedLoad);
    setGaugeValue(1, predictedEff);
    setGaugeGhost(0, LIVE_LOAD);
    setGaugeGhost(1, LIVE_EFFICIENCY);
    setDockMetric(loadSelector, predictedLoad);
    setDockMetric(effSelector, predictedEff);
    return;
  }

  setGaugeValue(0, LIVE_LOAD);
  setGaugeValue(1, LIVE_EFFICIENCY);
  setGaugeGhost(0, null);
  setGaugeGhost(1, null);
  setDockMetric(loadSelector, LIVE_LOAD);
  setDockMetric(effSelector, LIVE_EFFICIENCY);
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
  }
}

function wire() {
  document.addEventListener('click', (event) => {
    const target = event.target.closest('[data-rec-apply],[data-rec-preview],[data-rec-dismiss],[data-rec-clear],[data-whatif],[data-compare-toggle],[data-sig],[data-roam-seg],[data-roam-open],[data-roam-follow],[data-roam-flythrough],[data-roam-recenter],[data-roam-close],[data-preset],[data-panel-toggle],[data-panel-collapse],[data-panel-expand]');
    if (!target) return;

    if (target.dataset.recApply) {
      const id = target.dataset.recApply;
      if (state.applied.has(id)) {
        state.applied.delete(id);
        showToast('Recommendation reverted.');
      } else {
        state.applied.add(id);
        showToast('Recommendation applied to the corridor.');
      }
      saveState();
      render();
      syncGaugesForMode();
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

    if (target.dataset.sig) {
      const value = Number(target.value);
      const out = $(`[data-sig-value="${target.dataset.sig}"]`);
      if (out) out.textContent = `${value}s`;
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
      state.followMode = !state.followMode;
      target.classList.toggle('is-on', state.followMode);
      showToast(state.followMode ? 'Following vehicle M-204.' : 'Follow mode off.');
      return;
    }

    if ('roamFlythrough' in target.dataset) {
      const mapbox = getMap();
      if (!mapbox) return showToast('Map is not ready yet.');
      mapbox.flyTo({ center: [7.4245, 43.7335], zoom: 15.6, pitch: 58, bearing: 34, duration: prefersReducedMotion() ? 0 : 2600, essential: true });
      return;
    }

    if ('roamRecenter' in target.dataset) {
      const mapbox = getMap();
      if (!mapbox) return;
      mapbox.easeTo({ center: [7.4245, 43.7335], zoom: 14.6, pitch: 45, bearing: 0, duration: prefersReducedMotion() ? 0 : 900 });
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

  // Timeline scrubbing drives the mode panels.
  const scrubber = document.getElementById('simulationTime');
  scrubber?.addEventListener('input', () => {
    setMinute(Number(scrubber.value) / 60);
  });

  // Mode switching.
  document.addEventListener('sumo:livetabchange', (event) => {
    state.mode = event.detail?.tab || 'events';
    state.panelCollapsed = false;
    if (state.mode !== 'optimize') state.previewId = null;
    render();
    syncGaugesForMode();
    syncTabIndicator();
    showModeHint();
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
    roam: 'Roam · free camera over the live network.',
    events: ''
  };
  const hint = hints[state.mode];
  if (hint) showToast(hint);
}

/* ---------------------------------------------------------------------- init */

export function initModes(options = {}) {
  getMap = options.getMap || (() => window.sumoLiveMap || null);
  showToast = options.showToast || (() => {});
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
    syncMapForMode(state.mode);
    if (state.mode === 'events' || mapbox.getLayer?.('mode-congestion-line')) return;
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
