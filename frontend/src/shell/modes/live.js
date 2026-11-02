/**
 * Live bridge for the mode panels (Events · Optimize · Predict · Roam).
 *
 * Every live surface reads the same `/api/simulation/state` snapshot as the map
 * (`setLiveState` is pushed by `app.js` on each publish). Anything derived here is
 * labelled as such: recommendations' impact figures are modelled estimates, the
 * forecast carries its basis and confidence, and a value the run cannot measure stays
 * `null` instead of becoming a demo constant.
 *
 * The run is also the unit of state: `runId` from the snapshot scopes the cached
 * forecast and the history, so a restart can never show the previous run's numbers.
 */

const API_BASE = `${window.location.protocol}//${window.location.hostname}:8000`;

let snapshot = null;
let samples = [];
let runId = null;

const ACTIVE = new Set(['running', 'paused', 'starting']);
const clamp = (value, low, high) => Math.min(high, Math.max(low, value));
const round = (value, step = 1) => Number((Math.round(value / step) * step).toFixed(2));

function clockLabel(minutes) {
  const m = ((Math.round(Number(minutes) || 0) % 1440) + 1440) % 1440;
  return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
}

function minuteOf(seconds) {
  return Math.round(((Number(seconds) || 0) % 86400) / 60);
}

/** Called on every published state. `history` is the run's samples (up to 900). */
export function setLiveState(state, history) {
  const next = state && typeof state === 'object' ? state : null;
  const nextRun = next?.runId || null;
  if (nextRun !== runId) {
    runId = nextRun;
    samples = [];
    forecastCache = null;
    forecastFor = null;
    forecastAt = 0;
    forecastInfo = { ready: false, error: null };
  }
  snapshot = next;
  if (Array.isArray(history) && history.length >= samples.length) samples = history;
  else if (Array.isArray(next?.trend) && next.trend.length > samples.length) samples = next.trend;
}

export function getLiveState() {
  return snapshot;
}

export function getLiveHistory() {
  return samples;
}

export function getLiveRunId() {
  return runId;
}

export function isLive() {
  return Boolean(snapshot && ACTIVE.has(String(snapshot.status)));
}

export function liveMetrics() {
  return (isLive() && snapshot.metrics) || {};
}

/** Corridor load 0–100 derived from the measured share of queued vehicles. */
export function liveLoad() {
  const metrics = liveMetrics();
  if (!isLive() || metrics.queueShare == null) return null;
  return Math.round(clamp(Number(metrics.queueShare) * 100, 0, 100));
}

export function liveEfficiency() {
  const load = liveLoad();
  return load == null ? null : Math.round(clamp(100 - load * 0.82, 0, 100));
}

/**
 * Optimize recommendations from the live per-junction table. `queue`, `pressure`,
 * `avgSpeedKmh` and the phase duration are measured; the impact figures are modelled
 * estimates (the panel says so). Each row carries the junction and the green time it
 * would set, so Apply has a real target.
 */
export function liveRecommendations() {
  const metrics = liveMetrics();
  const junctions = Array.isArray(metrics.junctions) ? metrics.junctions : [];
  if (!isLive() || !junctions.length) return null;
  const ranked = [...junctions]
    .sort((a, b) => (Number(b.pressure) || 0) - (Number(a.pressure) || 0))
    .slice(0, 4);
  const peak = Math.max(...ranked.map((j) => Number(j.pressure) || 0), 0.1);
  const load = liveLoad() ?? 0;
  const efficiency = liveEfficiency() ?? 0;

  return ranked
    .map((junction, index) => {
      const pressure = Number(junction.pressure) || 0;
      const queue = Number(junction.queue) || 0;
      const speed = Math.round(Number(junction.avgSpeedKmh) || 0);
      const remaining = Number(junction.green);
      const held = !Number.isFinite(remaining);
      const share = pressure / peak;
      const delayMin = round(Math.min(9.5, queue * 0.18 + pressure * 0.6), 0.1);
      const gain = round(Math.min(28, queue * 1.8), 0.1);
      const eff = round(Math.min(22, queue * 1.2), 0.1);
      const green = held ? 30 : Math.round(clamp(remaining + 6, 6, 90));
      return {
        id: `live-junction-${junction.id}`,
        junction: junction.id,
        green,
        phase: junction.phase,
        title: held ? `Hold ${junction.id} green for ${green}s` : `Extend green at ${junction.id}`,
        held,
        detail: `${queue} queued · ${speed} km/h · ${junction.lanes} lanes · ${Math.round(share * 100)}% of peak pressure`,
        kind: 'signal',
        rank: index + 1,
        delayMin,
        throughput: gain,
        efficiency: eff,
        confidence: round(clamp(0.6 + share * 0.3, 0.6, 0.95), 0.01),
        projected: {
          load: round(clamp(load - eff * 0.7, 0, 100), 1),
          efficiency: round(clamp(efficiency + eff * 0.7, 0, 100), 1),
        },
      };
    })
    .sort((a, b) => b.delayMin - a.delayMin);
}

/** Signal editor rows from the TLS durations the session reports. */
export function liveSignalTiming() {
  const signals = isLive() && Array.isArray(snapshot.signals) ? snapshot.signals : [];
  if (!signals.length) return null;
  // `green` is the measured time left in the current phase. A phase the controller
  // holds open has no remaining green, so the editor offers a labelled hold instead of
  // inventing a split: applying it sets the current phase's duration to 30s.
  const phases = signals.slice(0, 6).map((signal) => {
    const remaining = Number(signal.green);
    const held = !Number.isFinite(remaining);
    return {
      id: `tls-${signal.id}`,
      tls: signal.id,
      label: signal.id,
      green: held ? 30 : Math.round(clamp(remaining, 6, 90)),
      held,
      pedestrian: 0,
    };
  });
  const cycle = Math.round(phases.reduce((sum, phase) => sum + phase.green, 0)) || 90;
  return { cycle, phases, live: true };
}

/** Roam strip: measured speed per junction, plus the run's own counters. */
export function liveRoamStats() {
  const metrics = liveMetrics();
  if (!isLive()) return null;
  const vehicles = Number(metrics.vehicles) || 0;
  const queued = Number(metrics.queued) || 0;
  const speed = Math.round(Number(metrics.avgSpeedKmh) || 0);
  const critical = (snapshot.events || []).filter((event) => event.severity === 'critical').length;
  const junctions = Array.isArray(metrics.junctions) ? metrics.junctions : [];
  return {
    speed,
    density: round(vehicles ? queued / vehicles : 0, 0.01),
    vehicles,
    incidents: critical,
    signal: snapshot.policy?.label || String(snapshot.method || 'Live'),
    segments: junctions.slice(0, 6).map((junction) => {
      const segmentSpeed = Math.round(Number(junction.avgSpeedKmh) || 0);
      return {
        id: `live-${junction.id}`,
        label: junction.id,
        speed: segmentSpeed,
        state: segmentSpeed >= 25 ? 'flow' : segmentSpeed >= 10 ? 'dense' : 'jam',
        queue: Number(junction.queue) || 0,
        lanes: Number(junction.lanes) || 0,
      };
    }),
  };
}

/* ------------------------------------------------------------------ forecast */

let forecastCache = null;
let forecastFor = null;
let forecastAt = 0;
let forecastPending = null;
let forecastInfo = { ready: false, error: null };

function mapForecast(payload) {
  const measured = (payload.measured || []).map((sample) => ({
    minute: minuteOf(sample.t),
    clock: sample.clock || clockLabel(minuteOf(sample.t)),
    queue: Number(sample.queue) || 0,
  }));
  const projected = (payload.points || []).map((point) => ({
    minute: minuteOf(point.t),
    clock: point.clock || clockLabel(minuteOf(point.t)),
    queue: Number(point.queue) || 0,
  }));
  const values = [...measured, ...projected].map((point) => point.queue);
  const peak = projected.reduce(
    (best, point) => (point.queue > best.queue ? point : best),
    projected[0] || measured[measured.length - 1] || { queue: 0, clock: '—', minute: 0 }
  );
  return {
    horizonMin: Number(payload.horizonMin) || 15,
    confidence: Number(payload.confidence) || 0,
    method: payload.method || 'forecast',
    samples: Number(payload.samples) || 0,
    alpha: payload.alpha,
    basisNote: `${payload.method || 'forecast'} · ${payload.samples || 0} samples`,
    measured,
    projected,
    values,
    split: measured.length,
    currentQueue: measured.length ? measured[measured.length - 1].queue : 0,
    projectedQueue: projected.length
      ? projected[projected.length - 1].queue
      : measured.length
        ? measured[measured.length - 1].queue
        : 0,
    peak: { clock: peak.clock, queue: peak.queue, minute: peak.minute },
    band: Math.round((1 - (Number(payload.confidence) || 0)) * 10),
  };
}

/**
 * Ask the backend for a projection of the running corridor. Returns true when new
 * points arrived (the caller can re-render); repeated calls are de-duplicated.
 */
export function refreshForecast(horizon = 15) {
  const currentRun = snapshot?.runId || null;
  if (!isLive()) return Promise.resolve(false);
  const fresh = Boolean(forecastCache) && forecastFor === currentRun && Date.now() - forecastAt < 6000;
  if (fresh || forecastPending) return Promise.resolve(false);
  forecastPending = fetch(`${API_BASE}/api/simulation/forecast?horizon=${horizon}`)
    .then(async (response) => {
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        // A 404 here means the API process predates this endpoint (it is registered in
        // api/routes/simulation.py), so say that instead of showing "Not Found".
        if (response.status === 404) {
          throw new Error('The API is running an older build — restart it to load /api/simulation/forecast.');
        }
        throw new Error(body.detail || `HTTP ${response.status}`);
      }
      return response.json();
    })
    .then((payload) => {
      forecastAt = Date.now();
      if (payload?.runId && currentRun && payload.runId !== currentRun) return false;
      forecastFor = currentRun;
      forecastCache = mapForecast(payload);
      forecastInfo = { ready: true, error: null };
      return true;
    })
    .catch((error) => {
      forecastInfo = { ready: Boolean(forecastCache), error: error.message || 'Forecast unavailable.' };
      return false;
    })
    .finally(() => {
      forecastPending = null;
    });
  return forecastPending;
}

/** The mapped forecast for the current run, or null while it is being collected. */
export function liveForecast() {
  return isLive() && forecastCache ? forecastCache : null;
}

export function forecastState() {
  return { ...forecastInfo, pending: Boolean(forecastPending) };
}

/* ------------------------------------------------------------------ controls */

/** Change the current phase's green time at one junction of the running corridor. */
export async function applySignalChange(junction, green) {
  const response = await fetch(`${API_BASE}/api/simulation/signal`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ junction, green: Number(green) }),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`);
  return body;
}
