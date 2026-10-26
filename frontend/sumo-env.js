/* Three.js environment for the headless SUMO grids.
 *
 * The TraCI network is built as a lit model — a plate, road slabs, signal heads
 * and vehicles as boxes — and driven by a real perspective camera with
 * OrbitControls: drag to orbit, wheel to zoom, right-drag to pan. The dashboard's
 * map buttons (zoom in / zoom out / reset) talk to the same camera through the
 * returned API.
 *
 * Mount contract used by app.js:
 *   const env = mountSumoLiveMap(container, state);
 *   env.update(nextState); env.reset(); env.zoomIn(); env.zoomOut(); env.destroy();
 */

import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

/* Roads are painted onto the plate, not raised on slabs. A raised deck needs
   side walls and a kerb lip, and at any distance those read as the street
   floating above the model. A 10 cm lift keeps the paint off the plate without
   a visible step. */
const ROAD_LEVEL = 0.1; // metres above the plate
const PLATE_MARGIN = 30; // metres of plate around the network
const PLATE_THICKNESS = 46; // metres: the model's base, scaled up to stay visible
const SIGNAL_HEIGHT = 6.2; // metres: gantry arm the signal heads hang from
const SIGNAL_DROP = 0.9; // metres the head hangs below the arm
const MAX_VEHICLES = 600;
const MAX_SIGNALS = 720;
const BACKGROUND = '#d9e6ee';
const FOV = 42;

const UP = new THREE.Vector3(0, 1, 0);

const COLORS = {
  roadTop: '#6d7a85',
  roadSide: '#59656f',
  median: '#7d8a95',
  gantry: '#55616d',
  kerb: '#8a97a2',
  plateTop: '#c6d4de',
  plateSide: '#9aadbb',
  marking: '#eef4f8',
  flow: '#3f8f1f',
  slow: '#cc8f16',
  stop: '#c9433a',
  green: '#3fae5a',
  amber: '#e2b12f',
  red: '#d9544a'
};

/* ------------------------------------------------------------------ network */

function prepareNetwork(geojson) {
  const features = (geojson?.features || []).filter(
    (feature) => feature?.geometry?.coordinates?.length > 1
  );
  if (!features.length) return null;

  let west = Infinity;
  let east = -Infinity;
  let south = Infinity;
  let north = -Infinity;
  features.forEach((feature) => {
    feature.geometry.coordinates.forEach(([lng, lat]) => {
      if (lng < west) west = lng;
      if (lng > east) east = lng;
      if (lat < south) south = lat;
      if (lat > north) north = lat;
    });
  });
  if (!Number.isFinite(west) || !Number.isFinite(south)) return null;

  const centreLng = (west + east) / 2;
  const centreLat = (south + north) / 2;
  const cosLat = Math.cos((centreLat * Math.PI) / 180);
  // TraCI hands back lng/lat projected from net metres, so one linear mapping
  // keeps vehicles exactly on their own road. Degrees-to-metres differs per
  // axis, which would stretch the square grid; the ratio squares it back up.
  const metresX = (east - west) * 111320 * cosLat;
  const metresZ = (north - south) * 110540;
  const zScale = metresZ > 1 ? metresX / metresZ : 1;
  const toX = (lng) => (lng - centreLng) * 111320 * cosLat;
  const toZ = (lat) => -(lat - centreLat) * 110540 * zScale;

  // Lanes of one edge run side by side: merge them into a single slab.
  const groups = new Map();
  features.forEach((feature) => {
    const points = [];
    feature.geometry.coordinates.forEach(([lng, lat]) => {
      const point = [toX(lng), toZ(lat)];
      const previous = points[points.length - 1];
      if (!previous || Math.hypot(point[0] - previous[0], point[1] - previous[1]) > 0.4) {
        points.push(point);
      }
    });
    if (points.length < 2) return;
    const key = String(feature.properties?.edge ?? feature.properties?.id ?? points.length);
    const lane = {
      // The SUMO lane id, so a signal head can show the state of its own lane.
      id: String(feature.properties?.id ?? ""),
      width: Math.max(2.6, Number.parseFloat(feature.properties?.width) || 3.2),
      points
    };
    const group = groups.get(key);
    if (group) group.push(lane);
    else groups.set(key, [lane]);
  });

  /* Lanes of one edge sit side by side at a fixed lateral offset. Averaging
     their point lists would flatten a two-lane carriageway onto one line and
     leave its traffic overhanging the slab, so the offsets are measured and
     the deck is built to span every lane of the group. */
  const lanes = [...groups.values()].map((group) => {
    const reference = group.reduce(
      (best, lane) => (lane.points.length > best.points.length ? lane : best),
      group[0]
    );
    const normals = reference.points.map((point, index) => {
      const previous = reference.points[Math.max(0, index - 1)];
      const next = reference.points[Math.min(reference.points.length - 1, index + 1)];
      const dx = next[0] - previous[0];
      const dz = next[1] - previous[1];
      const length = Math.hypot(dx, dz) || 1;
      return [-dz / length, dx / length];
    });
    const offsets = group.map((lane) => {
      if (lane.points.length !== reference.points.length) return 0;
      const total = lane.points.reduce(
        (sum, [x, z], index) =>
          sum + (x - reference.points[index][0]) * normals[index][0] +
          (z - reference.points[index][1]) * normals[index][1],
        0
      );
      return total / lane.points.length;
    });
    const minOffset = Math.min(0, ...offsets);
    const maxOffset = Math.max(0, ...offsets);
    const laneWidth = group.reduce((sum, lane) => sum + lane.width, 0) / group.length;
    const shift = (minOffset + maxOffset) / 2;
    const points = reference.points.map(([x, z], index) => [
      x + normals[index][0] * shift,
      z + normals[index][1] * shift
    ]);
    const first = points[0];
    const last = points[points.length - 1];
    const run = Math.hypot(last[0] - first[0], last[1] - first[1]) || 1;
    return {
      // A floor keeps the street readable when the whole district is in frame,
      // and stops opposing carriageways leaving a sliver of plate between them.
      width: Math.max(8.5, maxOffset - minOffset + laneWidth + 2.4),
      deckWidth: maxOffset - minOffset + laneWidth,
      points,
      laneWidth,
      // Lane centres relative to the merged centreline, for paint and decks.
      offsets: offsets.map((offset) => offset - shift).sort((a, b) => a - b),
      // The individual lanes behind that centreline: a signal head per lane
      // needs each lane's own offset and its SUMO id.
      sublanes: group
        .map((member, index) => ({ id: member.id, offset: offsets[index] - shift }))
        .sort((a, b) => a.offset - b.offset),
      direction: [(last[0] - first[0]) / run, (last[1] - first[1]) / run]
    };
  }).filter((lane) => lane.points.length > 1);

  let minX = Infinity;
  let maxX = -Infinity;
  let minZ = Infinity;
  let maxZ = -Infinity;
  lanes.forEach((lane) => {
    lane.points.forEach(([x, z]) => {
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (z < minZ) minZ = z;
      if (z > maxZ) maxZ = z;
    });
  });

  const offsetX = (minX + maxX) / 2;
  const offsetZ = (minZ + maxZ) / 2;
  lanes.forEach((lane) => {
    lane.points = lane.points.map(([x, z]) => [x - offsetX, z - offsetZ]);
  });

  /* The grids are rectangular, so lane endpoints cluster onto a handful of
     street lines. Clustering those gives the junctions and the city blocks
     without guessing from raw point density. */
  const cluster = (values, tolerance = 16) => {
    const sorted = [...values].sort((a, b) => a - b);
    const groups = [];
    sorted.forEach((value) => {
      const last = groups[groups.length - 1];
      if (last && Math.abs(value - last.sum / last.count) < tolerance) {
        last.sum += value;
        last.count += 1;
      } else {
        groups.push({ sum: value, count: 1 });
      }
    });
    return groups.map((group) => group.sum / group.count);
  };

  const endX = [];
  const endZ = [];
  lanes.forEach((lane) => {
    const first = lane.points[0];
    const last = lane.points[lane.points.length - 1];
    endX.push(first[0], last[0]);
    endZ.push(first[1], last[1]);
  });
  const streetX = cluster(endX);
  const streetZ = cluster(endZ);

  /* Deck edges are shared by the road surface, the markings and the junction
     pads, so the three always meet: a deck runs out to the middle of the median
     when a carriageway faces the opposite direction, and a kerb is drawn only
     on the sides that face open ground. */
  const analysis = analyseCorridor(lanes);
  lanes.forEach((lane, index) => {
    const opposite = analysis[index];
    const half = lane.deckWidth / 2;
    const paired = opposite?.partner >= 0;
    const inner = paired ? Math.max(half, Math.min(opposite.gap / 2, half + 7)) : half;
    lane.loEdge = paired && opposite.side < 0 ? -inner : -half;
    lane.hiEdge = paired && opposite.side > 0 ? inner : half;
    lane.loOpen = !(paired && opposite.side < 0);
    lane.hiOpen = !(paired && opposite.side > 0);
  });

  // Junction pads are built from the lane ends themselves, so their size and
  // position come from the SUMO network rather than from a street grid guess.
  const junctions = findJunctions(lanes);

  return {
    lanes,
    junctions,
    streetX,
    streetZ,
    toX: (lng) => toX(lng) - offsetX,
    toZ: (lat) => toZ(lat) - offsetZ,
    width: Math.max(1, maxX - minX),
    depth: Math.max(1, maxZ - minZ)
  };
}

/** True junctions: lane ends that meet from crossing directions. */
function findJunctions(lanes) {
  const ends = [];
  lanes.forEach((lane) => {
    const count = lane.points.length;
    if (count < 2) return;
    const normalAt = (from, to) => {
      const dx = to[0] - from[0];
      const dz = to[1] - from[1];
      const length = Math.hypot(dx, dz) || 1;
      return [-dz / length, dx / length, dx / length, dz / length];
    };
    const first = normalAt(lane.points[0], lane.points[1]);
    const last = normalAt(lane.points[count - 2], lane.points[count - 1]);
    ends.push(
      {
        lane,
        point: lane.points[0],
        normal: [first[0], first[1]],
        direction: [-first[2], -first[3]],
        // A lane starts where traffic enters the network and ends at its stop
        // line, so only the end of a lane carries a signal for that lane.
        stopLine: false
      },
      {
        lane,
        point: lane.points[count - 1],
        normal: [last[0], last[1]],
        direction: [last[2], last[3]],
        stopLine: true
      }
    );
  });

  const clusters = [];
  ends.forEach((end) => {
    let cluster = null;
    clusters.forEach((candidate) => {
      if (
        !cluster &&
        Math.hypot(candidate.x - end.point[0], candidate.z - end.point[1]) < 42
      ) {
        cluster = candidate;
      }
    });
    if (!cluster) {
      clusters.push({ x: end.point[0], z: end.point[1], count: 1, ends: [end] });
      return;
    }
    cluster.ends.push(end);
    cluster.count += 1;
    cluster.x += (end.point[0] - cluster.x) / cluster.count;
    cluster.z += (end.point[1] - cluster.z) / cluster.count;
  });

  return clusters
    .filter((cluster) => {
      if (cluster.count < 3) return false;
      // A dead end has both ends of a street pointing out of the model; a
      // real junction has arms crossing at an angle.
      return cluster.ends.some((end, index) =>
        cluster.ends.some((other, otherIndex) => {
          if (otherIndex === index) return false;
          const dot =
            end.direction[0] * other.direction[0] + end.direction[1] * other.direction[1];
          return Math.abs(dot) < 0.5;
        })
      );
    })
    .map((cluster) => ({ x: cluster.x, z: cluster.z, ends: cluster.ends }));
}

/** The paved crossing, as one rectangle per street axis. Each spans from one
 *  approach to the opposite one and covers the decks that run through it. Two
 *  rectangles rather than one hull, because the approaches are not equally far
 *  from the centre: a hull grows a spur into the block on the long side, which
 *  is what made the crossings read as a diamond lying over the street. */
function junctionPads(junction) {
  const groups = new Map();
  junction.ends.forEach((end) => {
    const [dx, dz] = end.direction;
    const key = Math.abs(dx) >= Math.abs(dz) ? 'x' : 'z';
    const group = groups.get(key) || [];
    groups.set(key, group);
    const [nx, nz] = end.normal;
    group.push(
      [end.point[0] + nx * end.lane.loEdge, end.point[1] + nz * end.lane.loEdge],
      [end.point[0] + nx * end.lane.hiEdge, end.point[1] + nz * end.lane.hiEdge],
      end.point
    );
  });
  const pads = [];
  groups.forEach((corners) => {
    let minX = Infinity;
    let maxX = -Infinity;
    let minZ = Infinity;
    let maxZ = -Infinity;
    corners.forEach(([x, z]) => {
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (z < minZ) minZ = z;
      if (z > maxZ) maxZ = z;
    });
    if (maxX - minX < 1 || maxZ - minZ < 1) return;
    pads.push([minX, minZ, maxX, maxZ]);
  });
  return pads;
}

/** A vertical quad between two ground points, from `bottom` to `top`. */
function addVerticalQuad(positions, colors, p1, p2, bottom, top, color) {
  const push = (x, y, z) => {
    positions.push(x, y, z);
    colors.push(color.r, color.g, color.b);
  };
  push(p1[0], bottom, p1[1]);
  push(p2[0], bottom, p2[1]);
  push(p2[0], top, p2[1]);
  push(p1[0], bottom, p1[1]);
  push(p2[0], top, p2[1]);
  push(p1[0], top, p1[1]);
}

/** A square post standing on the plate. */
function addColumn(positions, colors, x, z, bottom, top, size, color) {
  const half = size / 2;
  const corners = [
    [x - half, z - half],
    [x + half, z - half],
    [x + half, z + half],
    [x - half, z + half]
  ];
  for (let index = 0; index < 4; index += 1) {
    addVerticalQuad(positions, colors, corners[index], corners[(index + 1) % 4], bottom, top, color);
  }
}

/** An axis-aligned rectangle, emitted through the strip builder so it shares
 *  the exact winding and shading of the roads it joins. */
function addRect(positions, colors, [minX, minZ, maxX, maxZ], y, color) {
  const midZ = (minZ + maxZ) / 2;
  const half = (maxZ - minZ) / 2;
  addStrip(positions, colors, [[minX, midZ], [maxX, midZ]], -half, half, y, color);
}

/** A strip of surface between two signed offsets from a polyline. `dash` is an
 *  optional [painted, blanked] pair in metres. */
function addStrip(positions, colors, points, lo, hi, y, color, dash) {
  let travelled = 0;
  for (let index = 0; index + 1 < points.length; index += 1) {
    const [ax, az] = points[index];
    const [bx, bz] = points[index + 1];
    const dx = bx - ax;
    const dz = bz - az;
    const length = Math.hypot(dx, dz);
    if (length < 0.001) continue;
    const ux = dx / length;
    const uz = dz / length;
    const nx = -uz;
    const nz = ux;
    const originX = ax;
    const originZ = az;
    const ranges = [];
    if (dash) {
      const [paint, blank] = dash;
      const period = paint + blank;
      let cursor = -(travelled % period);
      while (cursor < length) {
        const start = Math.max(0, cursor);
        const end = Math.min(length, cursor + paint);
        if (end > start) ranges.push([start, end]);
        cursor += period;
      }
    } else {
      ranges.push([0, length]);
    }
    ranges.forEach(([start, end]) => {
      const sx = originX + ux * start;
      const sz = originZ + uz * start;
      const ex = originX + ux * end;
      const ez = originZ + uz * end;
      const p1 = [sx + nx * lo, sz + nz * lo];
      const p2 = [sx + nx * hi, sz + nz * hi];
      const p3 = [ex + nx * hi, ez + nz * hi];
      const p4 = [ex + nx * lo, ez + nz * lo];
      [p1, p2, p3, p1, p3, p4].forEach(([x, z]) => {
        positions.push(x, y, z);
        if (color && colors) colors.push(color.r, color.g, color.b);
      });
    });
    travelled += length;
  }
}

/** Finds, for every carriageway, the opposing carriageway across the street
 *  and the side it sits on — the cue for the solid centre line and the kerb. */
function analyseCorridor(lanes) {
  return lanes.map((lane, index) => {
    let partner = -1;
    let gap = Infinity;
    let side = 0;
    lanes.forEach((other, otherIndex) => {
      if (otherIndex === index) return;
      const dot =
        lane.direction[0] * other.direction[0] + lane.direction[1] * other.direction[1];
      if (dot > -0.9) return;
      const mid = Math.floor(lane.points.length / 2);
      const here = lane.points[mid];
      const there = other.points[Math.floor(other.points.length / 2)];
      const distance = Math.hypot(there[0] - here[0], there[1] - here[1]);
      if (distance > 30 || distance >= gap) return;
      const before = lane.points[Math.max(0, mid - 1)];
      const after = lane.points[Math.min(lane.points.length - 1, mid + 1)];
      const dx = after[0] - before[0];
      const dz = after[1] - before[1];
      const length = Math.hypot(dx, dz) || 1;
      gap = distance;
      partner = otherIndex;
      side = Math.sign(((there[0] - here[0]) * -dz + (there[1] - here[1]) * dx) / length) || 1;
    });
    return { partner, gap, side };
  });
}

/** One asphalt surface per carriageway, kerb bands and the junction pads,
 *  merged into one draw call. Everything is flat on the plate: a deck with side
 *  walls and a kerb lip reads as a slab hovering over the model. */
function buildRoadGeometry(lanes, junctions) {
  const positions = [];
  const colors = [];
  const top = new THREE.Color(COLORS.roadTop);
  const kerb = new THREE.Color(COLORS.kerb);
  const median = new THREE.Color(COLORS.median);

  lanes.forEach((lane) => {
    addStrip(positions, colors, lane.points, lane.loEdge, lane.hiEdge, ROAD_LEVEL, top);

    /* Where a carriageway reaches out to meet the opposite direction, the part
       past its own lanes is painted as median, so the lanes stay legible
       instead of dissolving into a wide blank sheet of asphalt. */
    const half = lane.deckWidth / 2;
    if (lane.loEdge < -half - 0.01) {
      addStrip(positions, colors, lane.points, lane.loEdge, -half, ROAD_LEVEL + 0.006, median);
    }
    if (lane.hiEdge > half + 0.01) {
      addStrip(positions, colors, lane.points, half, lane.hiEdge, ROAD_LEVEL + 0.006, median);
    }

    // Kerbs only where the carriageway faces open ground.
    if (lane.loOpen) {
      addStrip(positions, colors, lane.points, lane.loEdge - 0.6, lane.loEdge, ROAD_LEVEL + 0.015, kerb);
    }
    if (lane.hiOpen) {
      addStrip(positions, colors, lane.points, lane.hiEdge, lane.hiEdge + 0.6, ROAD_LEVEL + 0.015, kerb);
    }
  });

  /* Junction pads. SUMO moves vehicles across the intersection on internal
     edges, which are not exported with the roads, so without a paved pad a
     crossing vehicle looks like it has left the street. The pad is the hull of
     the approaching carriageways, so it is exactly as wide as the roads that
     run into it. */
  junctions.forEach((junction) => {
    junctionPads(junction).forEach((pad, index) => {
      addRect(positions, colors, pad, ROAD_LEVEL + 0.022 + index * 0.028, top);
    });
  });

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
  geometry.computeVertexNormals();
  return geometry;
}

/** Low city blocks in the cells between streets, so the diorama has depth and
 *  the roads read as streets rather than lines on a plate. */
function buildCityGeometry(network) {
  const positions = [];
  const colors = [];
  const top = new THREE.Color('#e2ecf2');
  const sideA = new THREE.Color('#c3d2dc');
  const sideB = new THREE.Color('#b0c2ce');

  const push = (x, y, z, color) => {
    positions.push(x, y, z);
    colors.push(color.r, color.g, color.b);
  };

  const xs = network.streetX || [];
  const zs = network.streetZ || [];
  if (xs.length < 2 || zs.length < 2) return null;

  const roadGap = 13; // keep clear of the carriageway and its kerb
  const box = (cx, cz, sx, sz, height, topColor) => {
    const x0 = cx - sx / 2;
    const x1 = cx + sx / 2;
    const z0 = cz - sz / 2;
    const z1 = cz + sz / 2;
    // roof
    push(x0, height, z0, topColor); push(x0, height, z1, topColor); push(x1, height, z1, topColor);
    push(x0, height, z0, topColor); push(x1, height, z1, topColor); push(x1, height, z0, topColor);
    // walls
    const wall = (p1, p2, color) => {
      push(p1[0], height, p1[1], color); push(p2[0], height, p2[1], color); push(p2[0], 0, p2[1], color);
      push(p1[0], height, p1[1], color); push(p2[0], 0, p2[1], color); push(p1[0], 0, p1[1], color);
    };
    wall([x0, z0], [x1, z0], sideA);
    wall([x1, z0], [x1, z1], sideB);
    wall([x1, z1], [x0, z1], sideA);
    wall([x0, z1], [x0, z0], sideB);
  };

  let seed = 20261025;
  const random = () => {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    return seed / 0x7fffffff;
  };

  for (let ix = 0; ix + 1 < xs.length; ix += 1) {
    for (let iz = 0; iz + 1 < zs.length; iz += 1) {
      const x0 = xs[ix] + roadGap;
      const x1 = xs[ix + 1] - roadGap;
      const z0 = zs[iz] + roadGap;
      const z1 = zs[iz + 1] - roadGap;
      const width = x1 - x0;
      const depth = z1 - z0;
      if (width < 12 || depth < 12) continue;
      // Two to four lots per cell, with a gap so the blocks stay legible.
      const columns = width > 90 ? 2 : 1;
      const rows = depth > 90 ? 2 : 1;
      for (let cx = 0; cx < columns; cx += 1) {
        for (let cz = 0; cz < rows; cz += 1) {
          const lotWidth = width / columns;
          const lotDepth = depth / rows;
          const pad = Math.min(lotWidth, lotDepth) * 0.16;
          const cxCenter = x0 + lotWidth * (cx + 0.5);
          const czCenter = z0 + lotDepth * (cz + 0.5);
          const height = 7 + random() * 17;
          box(
            cxCenter,
            czCenter,
            lotWidth - pad * 2,
            lotDepth - pad * 2,
            height,
            top
          );
        }
      }
    }
  }

  if (!positions.length) return null;
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
  geometry.computeVertexNormals();
  return geometry;
}

/** Lane paint, at the offsets SUMO uses, so the paint and the traffic agree:
 *  a solid edge line inside each kerb, a dashed divider between the lanes of
 *  one carriageway, and a solid centre line where the opposite carriageway
 *  runs alongside. Unlit, so it stays crisp at any exposure. */
function buildMarkingGeometry(lanes) {
  const positions = [];
  const ignored = [];
  const y = ROAD_LEVEL + 0.09;
  const edge = 0.11;
  const divider = 0.09;

  lanes.forEach((lane) => {
    const half = lane.deckWidth / 2;
    // Solid lines bound the carriageway on both sides: at the kerb where it
    // faces open ground, at its own edge where the median begins.
    const loLine = lane.loOpen ? lane.loEdge + 0.34 : -half + 0.14;
    const hiLine = lane.hiOpen ? lane.hiEdge - 0.34 : half - 0.14;
    addStrip(positions, ignored, lane.points, loLine - edge / 2, loLine + edge / 2, y, null);
    addStrip(positions, ignored, lane.points, hiLine - edge / 2, hiLine + edge / 2, y, null);

    // Dashed dividers between the lanes of this carriageway.
    lane.offsets.forEach((offset, laneIndex) => {
      if (laneIndex + 1 >= lane.offsets.length) return;
      const boundary = (offset + lane.offsets[laneIndex + 1]) / 2;
      addStrip(positions, ignored, lane.points, boundary - divider / 2, boundary + divider / 2, y, null, [5, 7]);
    });
  });

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  geometry.computeVertexNormals();
  return geometry;
}

/* --------------------------------------------------------------- environment */

export function mountSumoLiveMap(container, initial, options = {}) {
  const state = { ...(initial || {}) };
  let scene = null; // prepared network
  let scenario = null;
  let destroyed = false;

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
  renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
  renderer.setClearColor(BACKGROUND);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 0.92;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  renderer.domElement.className = 'sumo-3d-canvas';
  container.replaceChildren(renderer.domElement);

  const view = new THREE.Scene();
  view.background = new THREE.Color(BACKGROUND);

  const camera = new THREE.PerspectiveCamera(FOV, 1, 1, 20000);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.screenSpacePanning = false;
  controls.maxPolarAngle = Math.PI / 2.06;
  controls.minPolarAngle = 0.06;

  view.add(new THREE.HemisphereLight(0xffffff, 0xa9bccb, 0.32));
  view.add(new THREE.AmbientLight(0xffffff, 0.1));
  const sun = new THREE.DirectionalLight(0xfff8ef, 1.2);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  view.add(sun);

  const model = new THREE.Group();
  view.add(model);

  let disposables = [];
  let vehicles = null;
  let signals = null;
  let signalHeads = [];
  let junctions = [];
  let fit = { position: new THREE.Vector3(600, 900, 800), distance: 1400 };

  function clearModel() {
    model.clear();
    disposables.forEach((item) => item.dispose?.());
    disposables = [];
    vehicles = null;
    signals = null;
    signalHeads = [];
  }

  function buildScene(network) {
    clearModel();
    junctions = network.junctions.slice(0, MAX_SIGNALS);

    const plateWidth = network.width + PLATE_MARGIN * 2;
    const plateDepth = network.depth + PLATE_MARGIN * 2;
    const span = Math.max(plateWidth, plateDepth);

    // A deep plate makes the model read as a solid block rather than a decal.
    const plateGeometry = new THREE.BoxGeometry(plateWidth, PLATE_THICKNESS, plateDepth);
    const plateMaterial = new THREE.MeshStandardMaterial({
      color: COLORS.plateTop,
      roughness: 0.94,
      metalness: 0
    });
    const plate = new THREE.Mesh(plateGeometry, plateMaterial);
    plate.position.y = -PLATE_THICKNESS / 2;
    plate.receiveShadow = true;
    // Receiving only: a plate that casts on itself is shadowed from edge to
    // edge by its own geometry.
    plate.castShadow = false;
    model.add(plate);
    disposables.push(plateGeometry, plateMaterial);

    // A hairline edge gives the plate a physical outline against the sky.
    const edgeGeometry = new THREE.EdgesGeometry(plateGeometry);
    const edgeMaterial = new THREE.LineBasicMaterial({ color: '#a8b9c6', transparent: true, opacity: 0.75 });
    const outline = new THREE.LineSegments(edgeGeometry, edgeMaterial);
    outline.position.y = -PLATE_THICKNESS / 2;
    model.add(outline);
    disposables.push(edgeGeometry, edgeMaterial);

    const floorGeometry = new THREE.PlaneGeometry(span * 6, span * 6);
    const floorMaterial = new THREE.ShadowMaterial({ color: '#5a7182', opacity: 0.28 });
    const floor = new THREE.Mesh(floorGeometry, floorMaterial);
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = -PLATE_THICKNESS - 0.1;
    floor.receiveShadow = true;
    model.add(floor);
    disposables.push(floorGeometry, floorMaterial);

    const roadGeometry = buildRoadGeometry(network.lanes, junctions);
    const roadMaterial = new THREE.MeshStandardMaterial({
      vertexColors: true,
      roughness: 0.9,
      metalness: 0,
      side: THREE.DoubleSide
    });
    const roads = new THREE.Mesh(roadGeometry, roadMaterial);
    // Roads sit almost on the plate, so a cast shadow would read as a gap
    // under the street and make it look like it is floating.
    roads.castShadow = false;
    roads.receiveShadow = true;
    model.add(roads);
    disposables.push(roadGeometry, roadMaterial);

    const cityGeometry = buildCityGeometry(network);
    if (cityGeometry) {
      const cityMaterial = new THREE.MeshStandardMaterial({
        vertexColors: true,
        roughness: 0.88,
        metalness: 0,
        flatShading: true
      });
      const city = new THREE.Mesh(cityGeometry, cityMaterial);
      city.castShadow = true;
      city.receiveShadow = true;
      model.add(city);
      disposables.push(cityGeometry, cityMaterial);
    }

    const markingGeometry = buildMarkingGeometry(network.lanes);
    const markingMaterial = new THREE.MeshBasicMaterial({
      color: COLORS.marking,
      transparent: true,
      opacity: 0.82
    });
    const markings = new THREE.Mesh(markingGeometry, markingMaterial);
    model.add(markings);
    disposables.push(markingGeometry, markingMaterial);

    /* Signals: one head per lane, hung over that lane's stop line from a
       gantry at the kerb. A single lamp per junction said nothing about which
       lane had the right of way, which is what an operator reads first. */
    const gantryPositions = [];
    const gantryColors = [];
    const gantryColor = new THREE.Color(COLORS.gantry);
    signalHeads = [];
    junctions.forEach((junction) => {
      junction.ends.forEach((end) => {
        if (!end.stopLine) return;
        const lane = end.lane;
        const [nx, nz] = end.normal;
        const at = (offset) => [end.point[0] + nx * offset, end.point[1] + nz * offset];
        const mast = at(lane.hiOpen ? lane.hiEdge + 1.3 : lane.loEdge - 1.3);
        const far = at(lane.hiOpen ? lane.loEdge : lane.hiEdge);
        addColumn(gantryPositions, gantryColors, mast[0], mast[1], 0, SIGNAL_HEIGHT, 0.3, gantryColor);
        addVerticalQuad(
          gantryPositions,
          gantryColors,
          mast,
          far,
          SIGNAL_HEIGHT - 0.34,
          SIGNAL_HEIGHT,
          gantryColor
        );
        // A flat top as well, so the arm still reads when the camera looks
        // straight down at the junction.
        addStrip(
          gantryPositions,
          gantryColors,
          [mast, far],
          -0.11,
          0.11,
          SIGNAL_HEIGHT - 0.02,
          gantryColor
        );
        lane.sublanes.forEach((sub) => {
          const [x, z] = at(sub.offset);
          signalHeads.push({
            x,
            z,
            laneId: sub.id,
            // Lanes that never reach the junction (they merge before the stop
            // line) are not controlled by the TLS; they follow their
            // neighbours in the same carriageway.
            siblings: lane.sublanes.map((member) => member.id),
            junction
          });
        });
      });
    });
    if (gantryPositions.length) {
      const gantryGeometry = new THREE.BufferGeometry();
      gantryGeometry.setAttribute('position', new THREE.Float32BufferAttribute(gantryPositions, 3));
      gantryGeometry.setAttribute('color', new THREE.Float32BufferAttribute(gantryColors, 3));
      gantryGeometry.computeVertexNormals();
      const gantryMaterial = new THREE.MeshStandardMaterial({
        vertexColors: true,
        roughness: 0.5,
        metalness: 0.3,
        side: THREE.DoubleSide
      });
      model.add(new THREE.Mesh(gantryGeometry, gantryMaterial));
      disposables.push(gantryGeometry, gantryMaterial);
    }

    // One lamp per lane, under the gantry arm.
    const signalGeometry = new THREE.SphereGeometry(0.8, 10, 8);
    const signalMaterial = new THREE.MeshStandardMaterial({ roughness: 0.35, metalness: 0.1 });
    const signalBudget = Math.min(MAX_SIGNALS, Math.max(1, signalHeads.length));
    signals = new THREE.InstancedMesh(signalGeometry, signalMaterial, signalBudget);
    signals.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    signals.frustumCulled = false;
    signals.castShadow = false;
    model.add(signals);
    signalHeads = signalHeads.slice(0, signalBudget);
    disposables.push(signalGeometry, signalMaterial);

    // Vehicles.
    const vehicleGeometry = new THREE.BoxGeometry(1, 1, 1);
    const vehicleMaterial = new THREE.MeshStandardMaterial({ roughness: 0.55, metalness: 0.05 });
    vehicles = new THREE.InstancedMesh(vehicleGeometry, vehicleMaterial, MAX_VEHICLES);
    vehicles.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    vehicles.frustumCulled = false;
    vehicles.castShadow = true;
    model.add(vehicles);
    disposables.push(vehicleGeometry, vehicleMaterial);

    const fogNear = span * 1.9;
    view.fog = new THREE.Fog(BACKGROUND, fogNear, span * 5);
    sun.position.set(span * 0.45, span * 0.95, span * 0.6);
    sun.target.position.set(0, 0, 0);
    sun.shadow.camera.left = -span * 0.72;
    sun.shadow.camera.right = span * 0.72;
    sun.shadow.camera.top = span * 0.72;
    sun.shadow.camera.bottom = -span * 0.72;
    sun.shadow.camera.near = 1;
    sun.shadow.camera.far = span * 5;
    sun.shadow.bias = -0.0004;
    sun.shadow.normalBias = 3;
    sun.shadow.camera.updateProjectionMatrix();
    view.add(sun.target);

    frameScene();
  }

  /** Place the camera so the whole plate is in shot for the current viewport. */
  function frameScene() {
    if (!scene) return;
    const span = Math.max(scene.width, scene.depth) + PLATE_MARGIN * 2;
    const aspect = Math.max(0.2, container.clientWidth / Math.max(1, container.clientHeight));
    const halfFov = (FOV * Math.PI) / 360;
    const fitHeight = span / (2 * Math.tan(halfFov));
    const fitWidth = fitHeight / aspect;
    // The plate's near edge sits closer to the camera than its centre, so it
    // projects larger: pad the distance enough that the corner still fits.
    const distance = Math.max(fitHeight, fitWidth) * 1.46;
    fit = {
      position: new THREE.Vector3(0.62, 1.3, 1.05).normalize().multiplyScalar(distance * 1.1),
      distance
    };
    // A near plane this far out costs nothing at district scale and buys
    // enough depth precision to keep the road, kerb and paint layers apart.
    camera.near = Math.max(1, distance / 200);
    camera.far = distance * 8;
    camera.updateProjectionMatrix();
    controls.minDistance = distance * 0.06;
    controls.maxDistance = distance * 2.2;
    applyFit();
    draw();
  }

  function applyFit() {
    camera.position.copy(fit.position);
    controls.target.set(0, 0, 0);
    controls.update();
  }

  /** direction: 1 dolly in, -1 dolly out. */
  function zoom(direction) {
    const offset = camera.position.clone().sub(controls.target);
    const distance = THREE.MathUtils.clamp(
      offset.length() * (direction > 0 ? 0.78 : 1.28),
      controls.minDistance,
      controls.maxDistance
    );
    offset.setLength(distance);
    camera.position.copy(controls.target).add(offset);
    userMoved = true;
    draw();
  }

  /* -------------------------------------------------------- camera movement */

  let tween = null;

  /** Move the camera (and its focus point) with a short ease, so view changes
   *  read as a camera move rather than a cut. */
  function flyTo(position, target, duration = 480) {
    tween = {
      from: camera.position.clone(),
      to: position.clone(),
      fromTarget: controls.target.clone(),
      toTarget: target.clone(),
      start: performance.now(),
      duration
    };
    userMoved = true;
  }

  function advanceTween() {
    if (!tween) return;
    const progress = Math.min(1, (performance.now() - tween.start) / tween.duration);
    const eased = progress < 0.5
      ? 2 * progress * progress
      : 1 - Math.pow(-2 * progress + 2, 2) / 2;
    camera.position.lerpVectors(tween.from, tween.to, eased);
    controls.target.lerpVectors(tween.fromTarget, tween.toTarget, eased);
    if (progress >= 1) tween = null;
  }

  /** Screen-relative pan: the camera and its focus slide together. */
  function panView(axis, sign) {
    if (!scene) return;
    const step = Math.max(scene.width, scene.depth) * 0.07;
    const forward = new THREE.Vector3();
    camera.getWorldDirection(forward);
    forward.y = 0;
    if (forward.lengthSq() < 1e-6) forward.set(0, 0, -1);
    forward.normalize();
    const right = new THREE.Vector3().crossVectors(forward, UP).normalize();
    const direction = axis === 'x' ? right : forward;
    const limit = Math.max(80, Math.min(scene.width, scene.depth) * 0.7);
    const next = controls.target.clone().addScaledVector(direction, sign * step);
    next.x = THREE.MathUtils.clamp(next.x, -limit, limit);
    next.z = THREE.MathUtils.clamp(next.z, -limit, limit);
    const delta = next.sub(controls.target);
    controls.target.add(delta);
    camera.position.add(delta);
    userMoved = true;
    draw();
  }

  function setView(kind) {
    const distance = fit.distance;
    if (kind === 'top') {
      flyTo(new THREE.Vector3(0, distance * 1.3, 0.0001), new THREE.Vector3(0, 0, 0), 620);
    } else if (kind === 'street') {
      const angle = Math.PI / 5;
      flyTo(
        new THREE.Vector3(Math.cos(angle) * distance * 0.34, distance * 0.14, Math.sin(angle) * distance * 0.34),
        new THREE.Vector3(0, 0, 0),
        620
      );
    } else {
      flyTo(fit.position, new THREE.Vector3(0, 0, 0), 620);
    }
    controls.update();
  }

  function handleNav(action) {
    if (action === 'in') zoom(1);
    else if (action === 'out') zoom(-1);
    else if (action === 'forward') panView('z', 1);
    else if (action === 'back') panView('z', -1);
    else if (action === 'left') panView('x', -1);
    else if (action === 'right') panView('x', 1);
    else if (action === 'reset') {
      applyFit();
      userMoved = true;
      draw();
    } else if (action === 'top' || action === 'iso' || action === 'street') setView(action);
  }

  /* Arrow keys / WASD / +- / R while the scene has focus. */
  container.tabIndex = 0;
  container.addEventListener('keydown', (event) => {
    const keys = {
      ArrowUp: 'forward', KeyW: 'forward',
      ArrowDown: 'back', KeyS: 'back',
      ArrowLeft: 'left', KeyA: 'left',
      ArrowRight: 'right', KeyD: 'right',
      Equal: 'in', NumpadAdd: 'in',
      Minus: 'out', NumpadSubtract: 'out',
      KeyR: 'reset', KeyT: 'top'
    };
    const action = keys[event.code];
    if (!action) return;
    event.preventDefault();
    handleNav(action);
  });

  /* ------------------------------------------------------------- live state */

  const dummy = new THREE.Object3D();
  const tint = new THREE.Color();
  let userMoved = false;
  controls.addEventListener('start', () => {
    userMoved = true;
  });

  function paintVehicles() {
    if (!vehicles || !scene) return;
    const list = Array.isArray(state.vehicles) ? state.vehicles : [];
    let count = 0;
    for (const vehicle of list) {
      if (count >= MAX_VEHICLES) break;
      const x = scene.toX(Number(vehicle.lng));
      const z = scene.toZ(Number(vehicle.lat));
      if (!Number.isFinite(x) || !Number.isFinite(z)) continue;
      const speed = Number(vehicle.speed) || 0;
      const radians = ((Number(vehicle.angle) || 0) * Math.PI) / 180;
      // Toy-scale boxes: at district zoom a real 5 m car is two pixels wide.
      dummy.position.set(x, ROAD_LEVEL + 1.0, z);
      dummy.rotation.set(0, -radians, 0);
      // A car is 2 m wide on a 3.2 m lane; anything wider spills over the
      // markings and reads as traffic driving off the road.
      dummy.scale.set(2.2, 2.4, 5.4);
      dummy.updateMatrix();
      vehicles.setMatrixAt(count, dummy.matrix);
      vehicles.setColorAt(
        count,
        tint.set(speed < 0.15 ? COLORS.stop : speed < 4 ? COLORS.slow : COLORS.flow)
      );
      count += 1;
    }
    vehicles.count = count;
    vehicles.instanceMatrix.needsUpdate = true;
    if (vehicles.instanceColor) vehicles.instanceColor.needsUpdate = true;
  }

  /** SUMO link characters to the three lamp colours. */
  const LAMPS = { G: COLORS.green, g: COLORS.green, y: COLORS.amber, Y: COLORS.amber, r: COLORS.red, R: COLORS.red };

  function paintSignals() {
    if (!signals) return;
    // Per-lane state straight from TraCI; without it (backend too old, or a run
    // that has not started) fall back to a cycle so the heads still read.
    const lights = new Map();
    (Array.isArray(state.signals) ? state.signals : []).forEach((tls) => {
      Object.entries(tls?.lanes || {}).forEach(([laneId, character]) => {
        const lamp = LAMPS[character];
        if (lamp) lights.set(laneId, lamp);
      });
    });
    const seconds = Number(state.simulationTime) || 0;
    const junctionIndex = new Map(junctions.map((junction, index) => [junction, index]));

    signalHeads.forEach((head, index) => {
      dummy.position.set(head.x, SIGNAL_HEIGHT - SIGNAL_DROP, head.z);
      dummy.rotation.set(0, 0, 0);
      dummy.scale.set(1, 1, 1);
      dummy.updateMatrix();
      signals.setMatrixAt(index, dummy.matrix);
      let lamp = lights.get(head.laneId);
      if (!lamp) {
        for (const sibling of head.siblings) {
          const shared = lights.get(sibling);
          if (shared) {
            lamp = shared;
            break;
          }
        }
      }
      const fallback = [COLORS.red, COLORS.amber, COLORS.green][
        (Math.floor(seconds / 8) + (junctionIndex.get(head.junction) || 0)) % 3
      ];
      signals.setColorAt(index, tint.set(lamp || fallback));
    });
    signals.count = signalHeads.length;
    signals.instanceMatrix.needsUpdate = true;
    if (signals.instanceColor) signals.instanceColor.needsUpdate = true;
  }

  /* ------------------------------------------------------------------ loop */

  let frame = 0;
  let lastPaint = 0;

  function resize() {
    const width = container.clientWidth || 1;
    const height = container.clientHeight || 1;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    // The panel is often still hidden when the scene mounts, so re-frame once
    // it has its real size — unless the operator has already moved the camera.
    if (scene && !userMoved) frameScene();
    else draw();
  }

  /** One frame, on demand. A backgrounded tab gets no animation frames, so the
   *  scene must also be able to draw itself when state or camera changes. */
  function draw() {
    if (destroyed) return;
    advanceTween();
    controls.update();
    paintVehicles();
    paintSignals();
    renderer.render(view, camera);
  }

  function tick(time) {
    if (destroyed) return;
    frame = window.requestAnimationFrame(tick);
    advanceTween();
    if (tween || controls.autoRotate) controls.update();
    /* The state stream arrives at ~4 Hz; repaint the actors on that beat only. */
    if (time - lastPaint > 120) {
      lastPaint = time;
      controls.update();
      paintVehicles();
      paintSignals();
    }
    renderer.render(view, camera);
  }

  async function load() {
    const next = state.scenario === 'grid-3x3' ? 'grid-3x3' : 'grid-2x2';
    if (next === scenario) return;
    scenario = next;
    try {
      const response = await fetch(
        `${window.location.protocol}//${window.location.hostname}:8000/api/simulation/network/${next}`
      );
      if (!response.ok) throw new Error(`network ${response.status}`);
      const prepared = prepareNetwork(await response.json());
      if (!prepared || destroyed) throw new Error('empty network');
      scene = prepared;
      buildScene(scene);
    } catch {
      if (destroyed) return;
      scene = null;
      scenario = null;
      showNote('The SUMO network could not be loaded. Is the simulation API running?');
      window.setTimeout(() => {
        if (!destroyed && !scene) load();
      }, 2500);
    }
  }

  function showNote(message) {
    let note = container.querySelector('.sumo-env-note');
    if (!note) {
      note = document.createElement('p');
      note.className = 'sumo-env-note';
      note.setAttribute('role', 'status');
      container.appendChild(note);
    }
    note.textContent = message;
  }

  const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(resize) : null;
  observer?.observe(container);
  window.addEventListener('resize', resize);

  resize();
  load();
  frame = window.requestAnimationFrame(tick);

  return {
    get scenario() {
      return state.scenario;
    },
    update(next) {
      if (!next) return;
      const changed = next.scenario !== state.scenario;
      Object.assign(state, next);
      if (!changed) {
        draw();
        return;
      }
      scene = null;
      scenario = null;
      container.querySelector('.sumo-env-note')?.remove();
      load();
    },
    reset() {
      applyFit();
      draw();
    },
    zoomIn() {
      zoom(1);
    },
    zoomOut() {
      zoom(-1);
    },
    pan(axis, sign) {
      panView(axis, sign);
    },
    view(kind) {
      setView(kind);
    },
    destroy() {
      destroyed = true;
      window.cancelAnimationFrame(frame);
      window.removeEventListener('resize', resize);
      observer?.disconnect();
      controls.dispose();
      clearModel();
      renderer.dispose();
      container.replaceChildren();
    }
  };
}
