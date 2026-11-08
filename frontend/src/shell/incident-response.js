const PANEL_ID = 'incidentResponsePanel';
const CLEARED_LINGER_MS = 12000;

const sourceIds = {
  blocked: 'live-incident-blocked',
  diversion: 'live-diversion',
  ambulanceRoute: 'live-ambulance-route',
  incidentPoint: 'live-incident-point',
  ambulancePoint: 'live-incident-ambulance-point'
};

const layerIds = {
  blocked: 'live-incident-blocked-line',
  diversion: 'live-diversion-line',
  ambulanceRoute: 'live-ambulance-route-line',
  incidentHalo: 'live-incident-halo',
  incidentCore: 'live-incident-core',
  ambulanceCore: 'live-ambulance-core'
};

const moduleState = {
  getMap: () => null,
  onClear: null,
  lastIncident: null,
  dismissedKey: '',
  clearedKey: '',
  clearedAt: 0
};

export function initIncidentResponse(options = {}) {
  moduleState.getMap = options.getMap || (() => null);
  moduleState.onClear = options.onClear || null;
  bindPanel();
}

export function renderIncidentResponse(snapshot) {
  bindPanel();
  const panel = document.getElementById(PANEL_ID);
  const map = moduleState.getMap();
  const incident = snapshot?.incident;
  if (!incident) {
    moduleState.lastIncident = null;
    hidePanel(panel);
    clearMap(map);
    return;
  }

  moduleState.lastIncident = incident;
  const key = `${incident.vehicleId || ''}:${incident.since || ''}`;
  const active = Boolean(incident.active);
  if (active) {
    if (moduleState.dismissedKey !== key) {
      moduleState.dismissedKey = '';
      if (panel) {
        panel.hidden = false;
        panel.classList.add('is-visible');
      }
    }
  } else if (incident.cleared) {
    if (moduleState.clearedKey !== key) {
      moduleState.clearedKey = key;
      moduleState.clearedAt = Date.now();
    }
    if (Date.now() - moduleState.clearedAt > CLEARED_LINGER_MS) hidePanel(panel);
  } else {
    hidePanel(panel);
  }

  paintPanel(panel, incident, active);
  if (active) paintMap(map, snapshot, incident);
  else clearMap(map);
}

function bindPanel() {
  const panel = document.getElementById(PANEL_ID);
  if (!panel || panel.dataset.bound) return;
  panel.dataset.bound = '1';
  panel.querySelector('[data-incident-close]')?.addEventListener('click', () => {
    const incident = moduleState.lastIncident;
    moduleState.dismissedKey = incident ? `${incident.vehicleId || ''}:${incident.since || ''}` : '';
    hidePanel(panel);
  });
  panel.querySelector('[data-incident-locate]')?.addEventListener('click', () => {
    const incident = moduleState.lastIncident;
    const map = moduleState.getMap();
    if (!incident || !map) return;
    const center = [Number(incident.lng), Number(incident.lat)];
    if (!center.every(Number.isFinite)) return;
    map.flyTo({ center, zoom: 16.6, pitch: 55, duration: 1200, essential: true });
  });
  panel.querySelector('[data-incident-clear]')?.addEventListener('click', async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    try {
      await moduleState.onClear?.();
    } finally {
      button.disabled = false;
    }
  });
}

function hidePanel(panel) {
  if (!panel) return;
  panel.hidden = true;
  panel.classList.remove('is-visible');
}

function paintPanel(panel, incident, active) {
  if (!panel) return;
  panel.classList.toggle('is-cleared', !active);
  setText(panel, '[data-incident-status]', active ? 'Active response' : 'Incident cleared');
  setText(panel, '[data-incident-location]', incident.street || incident.edge || '—');
  setText(panel, '[data-incident-lane]', incident.lane || '—');
  setText(
    panel,
    '[data-incident-rerouted]',
    Number(incident.reroutedCount) > 0 ? `${incident.reroutedCount} vehicles` : 'None'
  );
  setText(panel, '[data-incident-ambulance]', incident.ambulance || '—');
  setText(panel, '[data-incident-eta]', formatEta(incident.ambulanceEtaS));
  setText(panel, '[data-incident-distance]', formatDistance(incident.ambulanceDistanceM));

  paintDispatch(panel, incident, active);
  paintController(panel, incident);

  const timeline = panel.querySelector('[data-incident-timeline]');
  if (timeline) {
    const steps = Array.isArray(incident.response) ? incident.response : [];
    timeline.innerHTML = steps.map((step) => `
      <li class="incident-step is-${escapeHtml(step.status || 'done')}">
        <span class="incident-step-dot" aria-hidden="true"></span>
        <span class="incident-step-copy">
          <strong>${escapeHtml(step.agent || 'Response')}</strong>
          <small>${escapeHtml(step.label || '')}</small>
        </span>
        <time>${escapeHtml(step.clock || '')}</time>
      </li>`).join('');
  }

  const clear = panel.querySelector('[data-incident-clear]');
  if (clear) {
    clear.disabled = !active;
    clear.textContent = active ? 'Clear incident' : 'Cleared';
  }
}

/*
 * The dispatch window: where the ambulance is in its run to the scene. The phase is
 * the session's own state (dispatched → enroute → onScene → arrived), and the bar is
 * the distance actually remaining, so it never fills on a timer.
 */
const DISPATCH_PHASES = {
  dispatched: { label: 'Dispatched', order: 0 },
  enroute: { label: 'En route', order: 1 },
  onScene: { label: 'On scene', order: 2 },
  arrived: { label: 'Arrived', order: 3 },
  unavailable: { label: 'No unit available', order: 0 }
};

function paintDispatch(panel, incident, active) {
  const wrap = panel.querySelector('[data-incident-dispatch]');
  if (!wrap) return;
  const phase = String(incident.ambulancePhase || (incident.ambulance ? 'dispatched' : 'unavailable'));
  const meta = DISPATCH_PHASES[phase] || DISPATCH_PHASES.dispatched;
  wrap.hidden = !active;
  wrap.dataset.phase = phase;
  setText(panel, '[data-incident-phase]', meta.label);

  const bar = panel.querySelector('[data-incident-progress]');
  if (!bar) return;
  // Progress is the share of the dispatch approach already covered, measured against
  // the distance the session recorded when it sent the unit — not a timer.
  const remaining = Number(incident.ambulanceDistanceM);
  const start = Number(incident.ambulanceStartM);
  let percent;
  if (meta.order >= 2) percent = 100;
  else if (Number.isFinite(start) && start > 0 && Number.isFinite(remaining)) {
    percent = Math.max(4, Math.min(97, (1 - remaining / start) * 100));
  } else percent = 4;
  bar.style.width = `${percent.toFixed(1)}%`;
}

/* The controller's own account of the incident, so a policy change is visible here. */
function paintController(panel, incident) {
  const wrap = panel.querySelector('[data-incident-controller]');
  const controller = incident.controller;
  if (!wrap) return;
  if (!controller) {
    wrap.hidden = true;
    return;
  }
  wrap.hidden = false;
  setText(panel, '[data-incident-controller-label]', controller.label || '—');
  setText(panel, '[data-incident-controller-note]', controller.note || '—');
  const list = panel.querySelector('[data-incident-preempts]');
  if (!list) return;
  const ids = Array.isArray(controller.preempted) ? controller.preempted : [];
  list.innerHTML = ids
    .map((id) => `<li><i aria-hidden="true"></i>${escapeHtml(id)}</li>`)
    .join('');
  list.hidden = ids.length === 0;
}

function paintMap(map, snapshot, incident) {
  if (!map || !map.isStyleLoaded()) return;
  ensureMapLayers(map);

  const blocked = lineFeature(incident.blocked);
  const diversion = lineFeature(incident.diversion);
  const ambulanceRoute = lineFeature(incident.ambulanceRoute);
  map.getSource(sourceIds.blocked)?.setData(blocked);
  map.getSource(sourceIds.diversion)?.setData(diversion);
  map.getSource(sourceIds.ambulanceRoute)?.setData(ambulanceRoute);

  const incidentPoint = pointFeature(incident.lng, incident.lat);
  map.getSource(sourceIds.incidentPoint)?.setData(incidentPoint);

  const ambulance = (snapshot.vehicles || []).find(
    (vehicle) => String(vehicle.id) === String(incident.ambulance)
  );
  // Once the unit reaches the scene its body leaves the network, so the marker falls
  // back to the incident point: the panel says "on scene", and the map must agree.
  const onScene = ['onScene', 'arrived'].includes(String(incident.ambulancePhase || ''));
  const ambulancePoint = ambulance
    ? pointFeature(ambulance.lng, ambulance.lat)
    : onScene
      ? pointFeature(incident.lng, incident.lat)
      : firstPoint(incident.ambulanceRoute);
  map.getSource(sourceIds.ambulancePoint)?.setData(ambulancePoint);
}

function clearMap(map) {
  if (!map || !map.isStyleLoaded()) return;
  for (const id of [sourceIds.blocked, sourceIds.diversion, sourceIds.ambulanceRoute, sourceIds.incidentPoint, sourceIds.ambulancePoint]) {
    map.getSource(id)?.setData(emptyCollection());
  }
}

function ensureMapLayers(map) {
  const before = map.getLayer('live-vehicles-extrusion')
    ? 'live-vehicles-extrusion'
    : undefined;
  addSource(map, sourceIds.blocked);
  addSource(map, sourceIds.diversion);
  addSource(map, sourceIds.ambulanceRoute);
  addSource(map, sourceIds.incidentPoint);
  addSource(map, sourceIds.ambulancePoint);

  addLayer(map, layerIds.blocked, {
    type: 'line',
    source: sourceIds.blocked,
    layout: { 'line-join': 'round', 'line-cap': 'round' },
    paint: {
      'line-color': '#ff5a4e',
      'line-width': ['interpolate', ['linear'], ['zoom'], 13, 4, 16, 7, 18, 9],
      'line-opacity': 0.92,
      'line-dasharray': [1.1, 0.9]
    }
  }, before);

  addLayer(map, layerIds.diversion, {
    type: 'line',
    source: sourceIds.diversion,
    layout: { 'line-join': 'round', 'line-cap': 'round' },
    paint: {
      'line-color': '#12b5a5',
      'line-width': ['interpolate', ['linear'], ['zoom'], 13, 3, 16, 5, 18, 6],
      'line-opacity': 0.95,
      'line-dasharray': [2.2, 1.4]
    }
  }, before);

  addLayer(map, layerIds.ambulanceRoute, {
    type: 'line',
    source: sourceIds.ambulanceRoute,
    layout: { 'line-join': 'round', 'line-cap': 'round' },
    paint: {
      'line-color': '#ffb020',
      'line-width': ['interpolate', ['linear'], ['zoom'], 13, 2.4, 16, 3.6, 18, 4.6],
      'line-opacity': 0.9,
      'line-dasharray': [0.8, 1.1]
    }
  }, before);

  addLayer(map, layerIds.incidentHalo, {
    type: 'circle',
    source: sourceIds.incidentPoint,
    paint: {
      'circle-color': '#ff5a4e',
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 13, 12, 16, 20, 18, 28],
      'circle-opacity': 0.22,
      'circle-stroke-width': 0
    }
  }, before);

  addLayer(map, layerIds.incidentCore, {
    type: 'circle',
    source: sourceIds.incidentPoint,
    paint: {
      'circle-color': '#ff5a4e',
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 13, 4, 16, 6, 18, 8],
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': 2
    }
  }, before);

  addLayer(map, layerIds.ambulanceCore, {
    type: 'circle',
    source: sourceIds.ambulancePoint,
    paint: {
      'circle-color': '#ffd23f',
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 13, 4, 16, 6, 18, 8],
      'circle-stroke-color': '#20232a',
      'circle-stroke-width': 2
    }
  }, before);
}

function addSource(map, id) {
  if (!map.getSource(id)) {
    map.addSource(id, { type: 'geojson', data: emptyCollection() });
  }
}

function addLayer(map, id, layer, before) {
  if (map.getLayer(id)) return;
  if (before) map.addLayer({ id, ...layer }, before);
  else map.addLayer({ id, ...layer });
}

function lineFeature(coordinates) {
  if (!Array.isArray(coordinates) || coordinates.length < 2) return emptyCollection();
  return {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        properties: {},
        geometry: { type: 'LineString', coordinates }
      }
    ]
  };
}

function pointFeature(lng, lat) {
  const point = [Number(lng), Number(lat)];
  if (!point.every(Number.isFinite)) return emptyCollection();
  return {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        properties: {},
        geometry: { type: 'Point', coordinates: point }
      }
    ]
  };
}

function firstPoint(coordinates) {
  if (!Array.isArray(coordinates) || !coordinates.length) return emptyCollection();
  const [lng, lat] = coordinates[0] || [];
  return pointFeature(lng, lat);
}

function emptyCollection() {
  return { type: 'FeatureCollection', features: [] };
}

function setText(panel, selector, value) {
  const node = panel.querySelector(selector);
  if (node) node.textContent = value === null || value === undefined || value === '' ? '—' : String(value);
}

function formatEta(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value < 0) return '—';
  if (value < 60) return Math.round(value) + ' s';
  return Math.floor(value / 60) + ':' + String(Math.round(value % 60)).padStart(2, '0');
}

function formatDistance(meters) {
  const value = Number(meters);
  if (!Number.isFinite(value)) return '—';
  if (value >= 1000) return `${(value / 1000).toFixed(1)} km`;
  return `${Math.round(value)} m`;
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
