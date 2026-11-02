/**
 * Road geometry for the mode panels.
 *
 * The run's own network (`/api/simulation/network/<scenario>`) is turned into a tiny
 * directed graph: every lane shape is a polyline, edges that meet at the same junction
 * are connected, and Dijkstra walks that graph. Optimize uses it to draw the approach it
 * is changing and the alternative around it; Predict uses it to estimate a trip between
 * two points the operator picked on the map.
 *
 * Nothing here is invented: a route is the measured lane geometry, and a distance is the
 * length of the polyline the run would drive. When the geometry has not loaded, callers
 * get `null` and the panels say so instead of drawing a placeholder corridor.
 */

const API_BASE = `${window.location.protocol}//${window.location.hostname}:8000`;
const METRES_PER_DEG = 111320;
const SNAP_M = 26; // edge endpoints within this distance share a junction node
const PICK_M = 90; // how far from a lane a click may land and still count as "on a road"

let cache = { scenario: null, geometry: null, pending: null, error: null };

const EMPTY = { type: 'FeatureCollection', features: [] };

/** Distance in metres between two [lng, lat] points, locally planar. */
export function metersBetween(a, b) {
  const lat = ((a[1] + b[1]) / 2) * (Math.PI / 180);
  const scaleX = METRES_PER_DEG * Math.max(Math.cos(lat), 0.01);
  return Math.hypot((b[0] - a[0]) * scaleX, (b[1] - a[1]) * METRES_PER_DEG);
}

function lineMeters(coords) {
  let total = 0;
  for (let index = 1; index < coords.length; index += 1) {
    total += metersBetween(coords[index - 1], coords[index]);
  }
  return total;
}

/** Closest point on a polyline: which segment, how far along it, and how far away. */
export function projectOnLine(point, coords) {
  let best = null;
  for (let index = 0; index < coords.length - 1; index += 1) {
    const start = coords[index];
    const end = coords[index + 1];
    const lat = point[1] * (Math.PI / 180);
    const scaleX = METRES_PER_DEG * Math.max(Math.cos(lat), 0.01);
    const ax = (start[0] - point[0]) * scaleX;
    const ay = (start[1] - point[1]) * METRES_PER_DEG;
    const dx = (end[0] - start[0]) * scaleX;
    const dy = (end[1] - start[1]) * METRES_PER_DEG;
    const span = dx * dx + dy * dy;
    const t = span > 0 ? Math.max(0, Math.min(1, -(ax * dx + ay * dy) / span)) : 0;
    const px = ax + dx * t;
    const py = ay + dy * t;
    const distance = Math.hypot(px, py);
    if (!best || distance < best.distance) {
      best = {
        distance,
        index,
        t,
        point: [point[0] + px / scaleX, point[1] + py / METRES_PER_DEG]
      };
    }
  }
  return best;
}

/** Index a network GeoJSON payload into the routing graph (exported for checks). */
export function buildGeometry(data) {
  const edges = new Map();
  const edgeByLane = new Map();

  (data.features || []).forEach((feature) => {
    const edgeId = feature?.properties?.edge;
    const coords = feature?.geometry?.coordinates;
    if (!edgeId || !Array.isArray(coords) || coords.length < 2) return;
    edgeByLane.set(feature.properties.id, edgeId);
    if (!edges.has(edgeId)) {
      edges.set(edgeId, {
        id: edgeId,
        // OSM-built nets carry the street name; fall back to the SUMO edge id.
        name: feature.properties.name || edgeId,
        coords,
        length: lineMeters(coords),
        start: coords[0],
        end: coords[coords.length - 1],
        lanes: []
      });
    }
    edges.get(edgeId).lanes.push(feature.properties.id);
  });

  // Snap edge endpoints into junction nodes so the graph is connected where the
  // network is connected, without needing the net's <connection> table.
  const nodes = [];
  const cell = 0.0003;
  const buckets = new Map();
  const nodeFor = (point) => {
    const ix = Math.floor(point[0] / cell);
    const iy = Math.floor(point[1] / cell);
    let best = null;
    for (let dx = -1; dx <= 1; dx += 1) {
      for (let dy = -1; dy <= 1; dy += 1) {
        const list = buckets.get(`${ix + dx},${iy + dy}`) || [];
        for (const node of list) {
          const distance = metersBetween(node.point, point);
          if (distance <= SNAP_M && (!best || distance < best.distance)) {
            best = { node, distance };
          }
        }
      }
    }
    if (best) return best.node;
    const node = { id: nodes.length, point, out: [], in: [] };
    nodes.push(node);
    const key = `${ix},${iy}`;
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key).push(node);
    return node;
  };

  edges.forEach((edge) => {
    edge.startNode = nodeFor(edge.start);
    edge.endNode = nodeFor(edge.end);
    edge.startNode.out.push(edge.id);
    edge.endNode.in.push(edge.id);
  });

  const signals = (data.signals || []).map((signal) => ({
    id: signal.id,
    center: [Number(signal.lng), Number(signal.lat)],
    lanes: (signal.lanes || []).map((lane) => ({
      lane: lane.lane,
      linkIndices: Array.isArray(lane.linkIndices) ? lane.linkIndices.map(Number) : [],
      point: [Number(lane.lng), Number(lane.lat)],
      edge: edgeByLane.get(lane.lane) || null
    }))
  }));

  const edgeList = [...edges.values()];
  return { edges, edgeByLane, edgeList, nodes, signals, features: data.features || [] };
}

/** The loaded geometry for a scenario, or `null` while it is being fetched. */
export function geometryFor(scenario) {
  if (!scenario || cache.scenario !== scenario) return null;
  return cache.geometry;
}

export function geometryState(scenario) {
  if (!scenario) return { ready: false, pending: false, error: null };
  const same = cache.scenario === scenario;
  return {
    ready: Boolean(same && cache.geometry),
    pending: Boolean(same && cache.pending),
    error: same ? cache.error : null
  };
}

/** Fetch and index the scenario's network once. Safe to call from any render. */
export function loadGeometry(scenario) {
  if (!scenario) return Promise.resolve(null);
  if (cache.scenario === scenario) {
    if (cache.geometry) return Promise.resolve(cache.geometry);
    if (cache.pending) return cache.pending;
  }
  cache = { scenario, geometry: null, pending: null, error: null };
  cache.pending = fetch(`${API_BASE}/api/simulation/network/${scenario}`)
    .then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    })
    .then((data) => {
      cache.geometry = buildGeometry(data);
      cache.error = null;
      return cache.geometry;
    })
    .catch((error) => {
      cache.error = error.message || 'Network geometry unavailable.';
      return null;
    })
    .finally(() => {
      cache.pending = null;
    });
  return cache.pending;
}

/** The driving edge nearest to a point, or `null` if the point is off the network. */
export function nearestEdge(geometry, point, limit = PICK_M) {
  if (!geometry || !Array.isArray(point)) return null;
  let best = null;
  geometry.edgeList.forEach((edge) => {
    if (edge.length < 4) return;
    const hit = projectOnLine(point, edge.coords);
    if (hit && (!best || hit.distance < best.distance)) best = { edge, ...hit };
  });
  if (!best) return null;
  return best.distance <= limit ? best : null;
}

function tailCoords(coords, index, point) {
  return [point, ...coords.slice(index + 1)];
}

function headCoords(coords, index, point) {
  return [...coords.slice(0, index + 1), point];
}

/**
 * Shortest path from one point to another over the network's directed edges.
 * `avoid` holds edge ids a reroute should not use.
 *
 * Returns `{ distanceM, coordinates, edgeIds }` or `null` when either point is off
 * the network or no path exists.
 */
export function routeBetween(
  geometry,
  from,
  to,
  { avoid = new Set(), fromEdgeStart = false } = {}
) {
  if (!geometry) return null;
  const start = nearestEdge(geometry, from);
  const end = nearestEdge(geometry, to);
  if (!start || !end) return null;
  const startEdge = start.edge;
  const endEdge = end.edge;

  // The same road: measure the piece between the two projections.
  if (startEdge.id === endEdge.id) {
    const coords =
      end.index >= start.index
        ? [start.point, ...startEdge.coords.slice(start.index + 1, end.index + 1), end.point]
        : [start.point, ...startEdge.coords.slice(end.index + 1, start.index + 1).reverse(), end.point];
    return { distanceM: Math.round(lineMeters(coords)), coordinates: coords, edgeIds: [startEdge.id] };
  }

  // A detour leaves from the intersection before the approach, so it starts at the
  // approach's own start node instead of driving the approach to the junction.
  const startTail = fromEdgeStart
    ? [start.point]
    : tailCoords(startEdge.coords, start.index, start.point);
  const endHead = headCoords(endEdge.coords, end.index, end.point);
  const startNode = fromEdgeStart ? startEdge.startNode.id : startEdge.endNode.id;
  const targetNode = endEdge.startNode.id;

  const dist = new Map([[startNode, fromEdgeStart ? 0 : lineMeters(startTail)]]);
  const via = new Map();
  const done = new Set();

  while (true) {
    let current = null;
    for (const [nodeId, value] of dist) {
      if (done.has(nodeId)) continue;
      if (!current || value < current.value) current = { nodeId, value };
    }
    if (!current) break;
    if (current.nodeId === targetNode) break;
    done.add(current.nodeId);
    const node = geometry.nodes[current.nodeId];
    if (!node) continue;
    for (const edgeId of node.out) {
      const edge = geometry.edges.get(edgeId);
      if (!edge || avoid.has(edgeId)) continue;
      const next = edge.endNode.id;
      const cost = current.value + edge.length;
      if (!dist.has(next) || cost < dist.get(next)) {
        dist.set(next, cost);
        via.set(next, edgeId);
      }
    }
  }

  if (!dist.has(targetNode)) return null;

  const pathEdges = [];
  const visited = new Set();
  let nodeId = targetNode;
  while (nodeId !== startNode) {
    if (visited.has(nodeId)) return null;
    visited.add(nodeId);
    const edgeId = via.get(nodeId);
    if (!edgeId) return null;
    pathEdges.unshift(edgeId);
    nodeId = geometry.edges.get(edgeId).startNode.id;
  }

  const middle = pathEdges.flatMap((edgeId) => geometry.edges.get(edgeId).coords);
  const coordinates = [...startTail, ...middle, ...endHead];
  return {
    distanceM: Math.round(lineMeters(coordinates)),
    coordinates,
    // A detour starts at the upstream intersection, not on the road it avoids.
    edgeIds: fromEdgeStart
      ? [...pathEdges, endEdge.id]
      : [startEdge.id, ...pathEdges, endEdge.id]
  };
}

/** The inbound approaches of one signalised junction, from the network metadata. */
export function junctionApproaches(geometry, signalId) {
  if (!geometry) return null;
  const signal = geometry.signals.find((entry) => entry.id === signalId);
  if (!signal) return null;
  const edgeIds = [...new Set(signal.lanes.map((lane) => lane.edge).filter(Boolean))];
  return {
    id: signal.id,
    center: signal.center,
    lanes: signal.lanes,
    edges: edgeIds.map((id) => geometry.edges.get(id)).filter(Boolean)
  };
}

function bearing(coords) {
  const first = coords[0];
  const last = coords[coords.length - 1];
  return Math.atan2(last[0] - first[0], last[1] - first[1]);
}

/**
 * The alternative around a junction: from the upstream end of the busiest approach to
 * the same downstream point the corridor reaches, without using the approach edges.
 *
 * `original` is the same trip through the junction; `alternative` is the detour. Returns
 * `null` when the network has no other way through.
 */
export function bypassFor(geometry, signalId) {
  const approaches = junctionApproaches(geometry, signalId);
  if (!geometry || !approaches || !approaches.edges.length) return null;
  const approachIds = new Set(approaches.edges.map((edge) => edge.id));
  const main = [...approaches.edges].sort((a, b) => b.length - a.length)[0];

  // The continuation of the same street past the junction: an outgoing edge that starts
  // at the junction and points the same way as the approach.
  const approachBearing = bearing(main.coords);
  let continuation = null;
  geometry.edgeList.forEach((edge) => {
    if (approachIds.has(edge.id)) return;
    if (metersBetween(edge.start, approaches.center) > 55) return;
    // The destination must be clearly past the junction, or its endpoint would snap
    // back onto an approach lane and the "alternative" would be the original road.
    if (metersBetween(edge.end, approaches.center) < 80) return;
    const delta = Math.abs(
      Math.atan2(
        Math.sin(bearing(edge.coords) - approachBearing),
        Math.cos(bearing(edge.coords) - approachBearing)
      )
    );
    if (!continuation || delta < continuation.delta) continuation = { edge, delta };
  });
  if (!continuation) return null;

  const from = main.start;
  const to = continuation.edge.end;
  const original = routeBetween(geometry, from, to);
  // The detour leaves from the upstream intersection and reaches the same downstream
  // point without driving the closed approach: it comes in from another street.
  const alternative = routeBetween(geometry, from, to, {
    avoid: approachIds,
    fromEdgeStart: true
  });
  if (!alternative || alternative.edgeIds.length < 2) return null;
  // A detour that drives the avoided approach is not a detour.
  if (alternative.edgeIds.some((edgeId) => approachIds.has(edgeId))) return null;

  return {
    signalId,
    approachEdgeIds: [...approachIds],
    approachNames: [...new Set(approaches.edges.map((edge) => edge.name))],
    from,
    to,
    original,
    alternative
  };
}

/** GeoJSON feature collection for a route, for a Mapbox source. */
export function routeFeature(route, properties = {}) {
  if (!route) return EMPTY;
  return {
    type: 'Feature',
    properties,
    geometry: { type: 'LineString', coordinates: route.coordinates }
  };
}
