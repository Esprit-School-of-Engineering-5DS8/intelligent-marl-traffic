/**
 * Signal coordination channel.
 *
 * Every decision, each signalised intersection sends its downstream neighbours the
 * triple `[queue, releasing, pressure]` (`CoTrafficEnv._messages`). `releasing` is the
 * poke: the sender's light is green on the link that feeds the neighbour, so the
 * neighbour knows traffic is about to arrive.
 *
 * This draws that channel as it actually stands. A quiet link is a thin idle line; a
 * link whose sender is currently releasing traffic pulses toward the receiver, so the
 * hand-off is visible as movement rather than as a legend the operator has to read.
 *
 * Everything here is measured: the graph comes from `env.neighbour_links`, the poke
 * from the sender's own phase, and the queue from the lanes that feed the receiver.
 */

const SOURCE_ID = 'live-signal-comms';
const LAYER_HALO = 'live-signal-comms-halo';
const LAYER_LINE = 'live-signal-comms-line';
const LAYER_FLOW = 'live-signal-comms-flow';

const state = {
  getMap: () => null,
  enabled: false,
  lastPaint: 0
};

export function initSignalComms(options = {}) {
  state.getMap = options.getMap || (() => null);
}

/** Toggle the overlay. Returns the new state so the caller can label its button. */
export function setSignalCommsVisible(visible) {
  state.enabled = Boolean(visible);
  const map = state.getMap();
  if (!map) return state.enabled;
  if (!state.enabled) clearComms(map);
  return state.enabled;
}

export function signalCommsVisible() {
  return state.enabled;
}

/**
 * Called on every published snapshot. `metrics.comms` is the channel as the run
 * reports it; when the run has no graph (or the overlay is off) the layers are cleared
 * rather than left showing the previous run's links.
 */
export function renderSignalComms(snapshot) {
  const map = state.getMap();
  if (!map || !map.isStyleLoaded()) return;
  const comms = snapshot?.metrics?.comms;
  if (!state.enabled || !comms || !Array.isArray(comms.links) || !comms.links.length) {
    clearComms(map);
    return;
  }
  ensureLayers(map);
  paint(map, comms);
}

function paint(map, comms) {
  const features = [];
  const flows = [];
  // Weight against the busiest hand-off in this frame, so the brightest link is always
  // the one actually carrying the most traffic. A fixed scale would either saturate on
  // a busy corridor or go invisible on a quiet one.
  const maxQueue = Math.max(1, Number(comms.maxQueue) || 0);
  comms.links.forEach((link) => {
    const from = link.fromPoint;
    const to = link.toPoint;
    if (!Array.isArray(from) || !Array.isArray(to)) return;
    const releasing = Boolean(link.releasing);
    const handover = Boolean(link.handover);
    const queue = Number(link.queue) || 0;
    // 0 when nothing is moving, approaching 1 as the link carries the frame's peak.
    const weight = handover ? Math.max(0.18, Math.min(1, queue / maxQueue)) : 0;
    features.push({
      type: 'Feature',
      properties: {
        from: String(link.from || ''),
        to: String(link.to || ''),
        side: String(link.side || ''),
        releasing,
        handover,
        queue,
        weight,
        greenElapsedS: Number(link.greenElapsedS) || 0
      },
      geometry: { type: 'LineString', coordinates: [from, to] }
    });
    // Only a real hand-off gets the travelling overlay: a green light with nothing
    // behind it stays a quiet idle line instead of pulsing at an empty road.
    if (handover) {
      flows.push({
        type: 'Feature',
        properties: { from: String(link.from || ''), to: String(link.to || ''), weight },
        geometry: { type: 'LineString', coordinates: [from, to] }
      });
    }
  });
  map.getSource(SOURCE_ID)?.setData({ type: 'FeatureCollection', features });
  map.getSource(`${SOURCE_ID}-flow`)?.setData({ type: 'FeatureCollection', features: flows });
  paintLegend(comms);
}

/*
 * The legend states what the overlay is actually showing. The link graph exists in
 * every run, but the message exchange only happens when the active policy observes its
 * neighbours (`observation.neighbours`). Saying so is the difference between "these
 * junctions coordinate" and "these junctions are wired to coordinate".
 */
function paintLegend(comms) {
  const legend = document.querySelector('[data-comms-legend]');
  if (!legend) return;
  legend.hidden = false;
  const count = legend.querySelector('[data-comms-count]');
  if (count) count.textContent = `${comms.pokes} / ${comms.total} handing over`;
  const note = legend.querySelector('[data-comms-note]');
  if (note) {
    const greenOnly = Number(comms.greenOnly) || 0;
    if (!comms.enabled) {
      note.textContent =
        'The active policy does not observe its neighbours, so these links are wired but no messages are exchanged.';
      note.dataset.mode = 'inert';
    } else if (comms.pokes === 0) {
      note.textContent = `No traffic being handed over right now${greenOnly ? ` — ${greenOnly} green link(s) carrying nothing` : ''}.`;
      note.dataset.mode = 'idle';
    } else {
      note.textContent = `The active policy reads neighbour messages; ${comms.pokes} link(s) are carrying traffic across, busiest ${comms.maxQueue} queued.`;
      note.dataset.mode = 'live';
    }
  }
}

function clearComms(map) {
  if (!map || !map.isStyleLoaded()) return;
  map.getSource(SOURCE_ID)?.setData({ type: 'FeatureCollection', features: [] });
  map.getSource(`${SOURCE_ID}-flow`)?.setData({ type: 'FeatureCollection', features: [] });
  const legend = document.querySelector('[data-comms-legend]');
  if (legend && !state.enabled) legend.hidden = true;
}

function ensureLayers(map) {
  const before = map.getLayer('live-vehicles-extrusion') ? 'live-vehicles-extrusion' : undefined;

  if (!map.getSource(SOURCE_ID)) {
    map.addSource(SOURCE_ID, { type: 'geojson', data: empty() });
  }
  if (!map.getSource(`${SOURCE_ID}-flow`)) {
    map.addSource(`${SOURCE_ID}-flow`, { type: 'geojson', data: empty() });
  }

  // Halo: the wide, soft bed the line sits on, so the channel reads as a link between
  // two junctions rather than as another road.
  if (!map.getLayer(LAYER_HALO)) {
    add(map, LAYER_HALO, {
      type: 'line',
      source: SOURCE_ID,
      layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: {
        'line-color': '#5ad1c8',
        'line-width': ['interpolate', ['linear'], ['zoom'], 12, 5, 16, 9, 18, 13],
        'line-opacity': ['case', ['get', 'handover'], ['+', 0.08, ['*', 0.2, ['get', 'weight']]], 0.05]
      }
    }, before);
  }

  // The channel itself. Idle links are dim and thin; a link carrying traffic scales with
  // how much it is carrying, so the busiest hand-off is visibly the brightest.
  if (!map.getLayer(LAYER_LINE)) {
    add(map, LAYER_LINE, {
      type: 'line',
      source: SOURCE_ID,
      layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: {
        'line-color': [
          'case',
          ['get', 'handover'],
          '#5ad1c8',
          ['get', 'releasing'],
          '#8fa8a6',
          '#7d8b93'
        ],
        'line-width': [
          'interpolate', ['linear'], ['zoom'],
          12, ['case', ['get', 'handover'], ['+', 1.2, ['*', 2.2, ['get', 'weight']]], 0.7],
          16, ['case', ['get', 'handover'], ['+', 2, ['*', 3.4, ['get', 'weight']]], 1.1],
          18, ['case', ['get', 'handover'], ['+', 3, ['*', 4.6, ['get', 'weight']]], 1.6]
        ],
        'line-opacity': [
          'case',
          ['get', 'handover'], ['+', 0.45, ['*', 0.5, ['get', 'weight']]],
          ['get', 'releasing'], 0.34,
          0.2
        ],
        'line-dasharray': [
          'case',
          ['get', 'handover'], ['literal', [1.4, 0.8]],
          ['literal', [0.6, 1.6]]
        ]
      }
    }, before);
  }

  // Flow: a bright dashed overlay on the links that are actively handing traffic over,
  // pulsed so an active hand-off reads as live without needing a legend. Mapbox cannot
  // animate line-dasharray, so the pulse is on opacity — a paint property it does animate.
  if (!map.getLayer(LAYER_FLOW)) {
    add(map, LAYER_FLOW, {
      type: 'line',
      source: `${SOURCE_ID}-flow`,
      layout: { 'line-join': 'round', 'line-cap': 'butt' },
      paint: {
        'line-color': '#eafcfa',
        'line-width': [
          'interpolate', ['linear'], ['zoom'],
          12, ['+', 1.2, ['*', 1.4, ['get', 'weight']]],
          16, ['+', 1.8, ['*', 2.2, ['get', 'weight']]],
          18, ['+', 2.6, ['*', 3, ['get', 'weight']]]
        ],
        'line-opacity': 0.85,
        'line-dasharray': ['literal', [0.4, 2.2]]
      }
    }, before);
    pulseFlow(map);
  }
}

/* Pulse the active hand-off overlay. Stops itself once the layer is gone. */
let flowTimer = 0;
function pulseFlow(map) {
  window.clearInterval(flowTimer);
  let up = true;
  flowTimer = window.setInterval(() => {
    if (!map || !map.getLayer(LAYER_FLOW)) {
      window.clearInterval(flowTimer);
      flowTimer = 0;
      return;
    }
    up = !up;
    try {
      map.setPaintProperty(LAYER_FLOW, 'line-opacity', up ? 0.9 : 0.35);
    } catch {
      window.clearInterval(flowTimer);
      flowTimer = 0;
    }
  }, 520);
}

function add(map, id, layer, before) {
  if (map.getLayer(id)) return;
  if (before) map.addLayer({ id, ...layer }, before);
  else map.addLayer({ id, ...layer });
}

function empty() {
  return { type: 'FeatureCollection', features: [] };
}
