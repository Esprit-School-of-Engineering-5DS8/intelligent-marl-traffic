/**
 * Mode data adapter.
 *
 * Every Optimize / Predict / Roam surface reads through this one object, so a
 * real backend can be dropped in later without touching the UI:
 *
 *   export const modeData = createModeAdapter({ ...fetch-based provider });
 *
 * The mock provider is deterministic for a given (zone, minute) pair so the
 * dashboard never "flickers" between renders.
 */

const ZONES = {
  'sec-6': { id: 'sec-6', name: 'Sector 6', junction: 'Junction 4', baseDelay: 18, baseVolume: 12500 },
  'sec-4': { id: 'sec-4', name: 'Sector 4', junction: 'Junction 2', baseDelay: 11, baseVolume: 9400 },
  'sec-2': { id: 'sec-2', name: 'Sector 2', junction: 'Junction 7', baseDelay: 24, baseVolume: 15100 }
};

/** Deterministic hash -> [0, 1). Keeps mock values stable across renders. */
function noise(seed) {
  let h = 2166136261;
  const text = String(seed);
  for (let i = 0; i < text.length; i += 1) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return ((h >>> 0) % 10000) / 10000;
}

/* Rounded to the step without float dust (3.3000000000000003 → 3.3). */
const round = (value, step = 1) => Number((Math.round(value / step) * step).toFixed(2));

function zone(key) {
  return ZONES[key] || ZONES['sec-6'];
}

/* ---------------------------------------------------------------- Optimize */

const RECOMMENDATION_BLUEPRINTS = [
  {
    id: 'green-phase',
    title: 'Extend green phase at Junction 4',
    detail: '+8s on the eastbound approach, 12:15–12:45',
    kind: 'signal',
    weight: 1
  },
  {
    id: 'reroute-north',
    title: 'Shift 18% of through-traffic north',
    detail: 'Rue Grimaldi → Boulevard du Larvotto',
    kind: 'reroute',
    weight: 0.72
  },
  {
    id: 'ramp-meter',
    title: 'Meter the A1 on-ramp',
    detail: 'Release one vehicle every 4.5s for 20 min',
    kind: 'ramp',
    weight: 0.58
  },
  {
    id: 'bus-priority',
    title: 'Hold bus priority on Avenue Princesse Grace',
    detail: 'Suspend pre-emption while the queue drains',
    kind: 'transit',
    weight: 0.41
  }
];

function recommendations(zoneId, minuteOfDay) {
  const z = zone(zoneId);
  const t = Number(minuteOfDay) || 0;
  const load = 0.75 + noise(`${z.id}-load-${Math.floor(t / 30)}`) * 0.5;

  return RECOMMENDATION_BLUEPRINTS.map((bp, index) => {
    const jitter = 0.85 + noise(`${z.id}-${bp.id}-${Math.floor(t / 15)}`) * 0.3;
    const delayMin = round(6.4 * bp.weight * jitter * load, 0.1);
    const throughput = round(4.1 * bp.weight * jitter * load, 0.1);
    const efficiency = round(3.2 * bp.weight * jitter, 0.1);
    return {
      ...bp,
      rank: index + 1,
      delayMin,
      throughput,
      efficiency,
      confidence: round(Math.min(0.97, 0.72 + bp.weight * 0.2 + noise(bp.id) * 0.05), 0.01),
      // Projected gauge values once this recommendation is applied.
      projected: {
        load: round(Math.max(24, 52 - efficiency * 1.6), 1),
        efficiency: round(Math.min(96, 46 + efficiency * 1.4), 1)
      }
    };
  }).sort((a, b) => b.delayMin - a.delayMin);
}

function signalTiming(zoneId, minuteOfDay) {
  const z = zone(zoneId);
  const phase = Math.floor((Number(minuteOfDay) || 0) / 15);
  const wave = noise(`${z.id}-signal-${phase}`);
  return {
    cycle: 90,
    phases: [
      { id: 'ns', label: 'North–South', green: Math.round(34 + wave * 10), pedestrian: 12 },
      { id: 'ew', label: 'East–West', green: Math.round(28 + (1 - wave) * 12), pedestrian: 10 },
      { id: 'turn', label: 'Left turn', green: Math.round(6 + wave * 5), pedestrian: 0 }
    ]
  };
}

/* ----------------------------------------------------------------- Predict */

const FORECAST_INPUTS = [
  { id: 'rain', label: 'Rain', weight: 0.18, detail: 'Light showers 14:00–17:00' },
  { id: 'concert', label: 'Concert', weight: 0.26, detail: 'Stade Louis II, 21:00' },
  { id: 'roadworks', label: 'Roadworks', weight: 0.14, detail: 'Boulevard de Suisse, 09:00–11:00' }
];

function forecast(zoneId, minuteOfDay, activeInputs = []) {
  const z = zone(zoneId);
  const t = Number(minuteOfDay) || 0;
  const active = new Set(activeInputs);

  const series = Array.from({ length: 48 }, (_, slot) => {
    const minutes = slot * 30;
    const morning = Math.exp(-((minutes - 510) ** 2) / (2 * 90 ** 2));
    const evening = Math.exp(-((minutes - 1080) ** 2) / (2 * 105 ** 2));
    const base = 2200 + morning * 6800 + evening * 7400;
    const bump = FORECAST_INPUTS.reduce(
      (sum, input) => (active.has(input.id) ? sum + base * input.weight : sum),
      0
    );
    return { minute: minutes, volume: Math.round(base + bump) };
  });

  const boost = FORECAST_INPUTS.reduce(
    (sum, input) => (active.has(input.id) ? sum + input.weight : sum),
    0
  );
  const expectedDelay = round(z.baseDelay * (1 + boost) * 0.9 + noise(`${z.id}-delay-${t}`) * 5, 1);
  const confidence = round(Math.max(0.55, 0.93 - boost * 0.35 - (t > 1140 ? 0.06 : 0)), 0.01);
  const peakSlot = series.reduce((best, slot) => (slot.volume > best.volume ? slot : best), series[0]);
  const typical = series.map((slot) => ({
    minute: slot.minute,
    volume: Math.round(slot.volume / (1 + boost * 0.8))
  }));

  return {
    expectedDelay,
    confidence,
    // Uncertainty band in minutes, used for the scrubber band and the delta chip.
    band: Math.round((1 - confidence) * 12 + boost * 4),
    peak: {
      minute: peakSlot.minute,
      volume: peakSlot.volume,
      label: formatClock(peakSlot.minute)
    },
    series,
    typical,
    inputs: FORECAST_INPUTS.map((input) => ({ ...input, active: active.has(input.id) }))
  };
}

/* -------------------------------------------------------------------- Roam */

function roamStats(zoneId, minuteOfDay) {
  const z = zone(zoneId);
  const t = Number(minuteOfDay) || 0;
  const n = noise(`${z.id}-roam-${Math.floor(t / 10)}`);
  return {
    speed: Math.round(18 + n * 22),
    density: round(0.32 + n * 0.5, 0.01),
    vehicles: Math.round(320 + n * 260),
    incidents: n > 0.72 ? 2 : 1,
    signal: n > 0.5 ? 'Adaptive' : 'Manual',
    segments: [
      { id: 'cam-1', label: 'Avenue Princesse Grace', speed: Math.round(14 + n * 18), state: n > 0.55 ? 'dense' : 'flow' },
      { id: 'cam-2', label: 'Rue Grimaldi', speed: Math.round(22 + n * 16), state: 'flow' },
      { id: 'cam-3', label: 'Boulevard du Larvotto', speed: Math.round(9 + n * 12), state: 'jam' }
    ]
  };
}

/* ------------------------------------------------------------------ Helpers */

export function formatClock(minutes) {
  const m = ((Math.round(Number(minutes) || 0) % 1440) + 1440) % 1440;
  return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
}

function congestionFeatureCollection(zoneId, intensity = 1) {
  // A short Monaco corridor, roughly matching the live scene's default view.
  const line = [
    [7.4155, 43.7295],
    [7.4195, 43.7312],
    [7.4235, 43.7328],
    [7.4275, 43.7344],
    [7.4315, 43.7359]
  ];
  const split = [
    [7.4235, 43.7328],
    [7.4265, 43.7349],
    [7.4298, 43.7372]
  ];
  const z = zone(zoneId);
  return {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        properties: { kind: 'corridor', intensity, zone: z.id },
        geometry: { type: 'LineString', coordinates: line }
      },
      {
        type: 'Feature',
        properties: { kind: 'reroute', intensity: Math.min(1, intensity + 0.15), zone: z.id },
        geometry: { type: 'LineString', coordinates: split }
      }
    ]
  };
}

/* ------------------------------------------------------------------ Adapter */

export function createModeAdapter(provider) {
  return {
    recommendations: (zoneId, minute) => provider.recommendations(zoneId, minute),
    signalTiming: (zoneId, minute) => provider.signalTiming(zoneId, minute),
    forecast: (zoneId, minute, inputs) => provider.forecast(zoneId, minute, inputs),
    roamStats: (zoneId, minute) => provider.roamStats(zoneId, minute),
    congestion: (zoneId, intensity) => provider.congestion(zoneId, intensity)
  };
}

export const mockProvider = {
  recommendations,
  signalTiming,
  forecast,
  roamStats,
  congestion: congestionFeatureCollection
};

export const modeData = createModeAdapter(mockProvider);
export const zones = ZONES;
