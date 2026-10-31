/* Three.js environment for the Live Map on the San Francisco grids.
 *
 * Exactly two inputs: /api/simulation/network/{scenario} (lane + signal
 * geometry, in SUMO metres) and the /api/simulation/state stream (vehicles,
 * live signal phases). Everything below renders in SUMO coordinates, so what
 * you see matches what the vehicles drive. No plate, no floating deck —
 * roads lie flat on a ground plane that can be textured with the Mapbox
 * raster underneath when a token is available.
 *
 * Mount contract used by app.js:
 *   const env = mountSumoLiveMap(container, state, { onSimAction });
 *   env.update(nextState); env.zoomIn(); env.zoomOut(); env.reset(); env.destroy();
 */

import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

const MAX_VEHICLES = 800;
const VEHICLE_STYLES = {
  car: { length: 4.5, width: 1.9, height: 1.55, color: 0x4f9fd8 },
  taxi: { length: 4.5, width: 1.9, height: 1.6, color: 0xe9b83f },
  bus: { length: 11.5, width: 2.5, height: 3.25, color: 0x35a77a },
  truck: { length: 7.2, width: 2.45, height: 3.0, color: 0x9babb7 },
  emergency: { length: 5.4, width: 2.1, height: 2.15, color: 0xf2f1ec },
  bicycle: { length: 1.9, width: 0.65, height: 1.25, color: 0xee9f37 },
  motorcycle: { length: 2.2, width: 0.8, height: 1.35, color: 0x555d68 },
};
const PEDESTRIAN_SIZE = { height: 1.7, radius: 0.24 };
const CLASS_FILTERS = new Map(Object.keys(VEHICLE_STYLES).map((kind) => [kind, true]));
CLASS_FILTERS.set('pedestrian', true);
const pickRaycaster = new THREE.Raycaster();
const pickPointer = new THREE.Vector2();
const SIGNAL_HEIGHT = 5.6;
const FOV = 40;
const TILT = 72; // degrees from vertical: a low, street-level oblique view that exposes vehicle sides

const COLORS = {
  asphalt: 0x3a3f45,
  marking: 0xe8e4d8,
  vehicleFast: 0x2f8f46,
  vehicleSlow: 0xd9a13b,
  vehicleStopped: 0xc04b3f,
  mast: 0x2b2f34,
  red: 0xe04b3f,
  amber: 0xf0b429,
  green: 0x35c05a,
  ground: 0xe8ecef,
  sky: 0x9db4c4,
};

function resolveToken() {
  try {
    return localStorage.getItem('sumo.mapboxToken')
      || import.meta.env?.VITE_MAPBOX_TOKEN
      || window.MAPBOX_TOKEN
      || '';
  } catch { return ''; }
}

/* ------------------------------------------------------------ geometry */

function prepareNetwork(payload) {
  const lanes = (payload.sumoLanes || []).filter(
    (lane) => Array.isArray(lane.shape) && lane.shape.length >= 2
  );
  if (!lanes.length) return null;
  return {
    lanes,
    signals: payload.signals || [],
    lonlatBounds: lonlatBoundsOf(payload),
    anchors: geoAnchorsOf(payload),
  };
}

/** Lane-id matches between the geographic features and the SUMO lane shapes.
 *  Each matched lane contributes two anchors (its shape's endpoints), which
 *  pin the basemap to the road grid exactly — no assumed north-up mapping. */
function geoAnchorsOf(payload) {
  const sumoById = new Map((payload.sumoLanes || []).map((s) => [s.id, s]));
  const anchors = [];
  (payload.features || []).forEach((feature) => {
    const sumo = sumoById.get(feature.properties?.id);
    const geo = feature.geometry?.coordinates || [];
    if (!sumo || geo.length < 2 || sumo.shape.length < 2) return;
    anchors.push({ geo: geo[0], sumo: sumo.shape[0] });
    anchors.push({ geo: geo[geo.length - 1], sumo: sumo.shape[sumo.shape.length - 1] });
  });
  return anchors.length >= 4 ? anchors : [];
}

/** Fit the similarity (uniform scale + rotation + translation) that maps
 *  geographic metric space into SUMO's own metre frame, using the anchors.
 *  Real nets are built in UTM, whose grid-north deviates from true north by
 *  the meridian convergence, so a north-up assumption kicks streets off the
 *  basemap. Least-squares over endpoint pairs resolves rotation and scale.
 *  One robust pass drops far-off anchors (clipped lane tails) and refits. */
function fitGeoToWorld(anchors) {
  let south = Infinity, north = -Infinity;
  anchors.forEach((a) => {
    south = Math.min(south, a.geo[1]);
    north = Math.max(north, a.geo[1]);
  });
  const cosMid = Math.cos(((south + north) / 2) * Math.PI / 180);
  const toGeoM = ([lon, lat]) => [lon * 111320 * cosMid, lat * 111320];

  function kabsch(list) {
    const A = list.map((a) => toGeoM(a.geo));
    const B = list.map((a) => a.sumo); /* straight SUMO metres, y = north */
    const n = A.length;
    let ax = 0, ay = 0, bx = 0, by = 0;
    for (let i = 0; i < n; i += 1) { ax += A[i][0]; ay += A[i][1]; bx += B[i][0]; by += B[i][1]; }
    ax /= n; ay /= n; bx /= n; by /= n;
    let sxx = 0, sxy = 0;
    for (let i = 0; i < n; i += 1) {
      const x = A[i][0] - ax, y = A[i][1] - ay;
      const u = B[i][0] - bx, v = B[i][1] - by;
      sxx += x * u + y * v;
      sxy += y * u - x * v;
    }
    const theta = Math.atan2(sxy, sxx);
    const scale = Math.hypot(sxx, sxy) / A.reduce((sum, [x, y]) => sum + (x - ax) ** 2 + (y - ay) ** 2, 0);
    return { ax, ay, bx, by, theta, scale, cos: Math.cos(theta), sin: Math.sin(theta) };
  }
  function residual(fit, anchor) {
    const [gx, gy] = toGeoM(anchor.geo);
    const dx = gx - fit.ax, dy = gy - fit.ay;
    const rx = fit.scale * (fit.cos * dx - fit.sin * dy) + fit.bx;
    const ry = fit.scale * (fit.sin * dx + fit.cos * dy) + fit.by;
    return Math.hypot(rx - anchor.sumo[0], ry - anchor.sumo[1]);
  }

  let fit = kabsch(anchors);
  const residuals = anchors.map((a) => residual(fit, a)).sort((p, q) => p - q);
  const median = residuals[Math.floor(residuals.length / 2)] || 0;
  const kept = anchors.filter((a) => residual(fit, a) < Math.max(3 * median, 5));
  if (kept.length >= 4) fit = kabsch(kept);

  /* geographic extent of the kept anchors, in geo metric metres */
  const geo = kept.map((a) => toGeoM(a.geo));
  const geoBounds = {
    minX: Math.min(...geo.map((g) => g[0])), maxX: Math.max(...geo.map((g) => g[0])),
    minY: Math.min(...geo.map((g) => g[1])), maxY: Math.max(...geo.map((g) => g[1])),
  };
  const geoCentre = [(geoBounds.minX + geoBounds.maxX) / 2, (geoBounds.minY + geoBounds.maxY) / 2];
  /* scene coordinates of the geographic centre: sumo = R·geo + t, then
     scene X = x − cx, scene Z = cy − y (SUMO north → −z). */
  const sumoCentre = [
    fit.scale * (fit.cos * (geoCentre[0] - fit.ax) - fit.sin * (geoCentre[1] - fit.ay)) + fit.bx,
    fit.scale * (fit.sin * (geoCentre[0] - fit.ax) + fit.cos * (geoCentre[1] - fit.ay)) + fit.by,
  ];
  return {
    theta: fit.theta,
    scale: fit.scale,
    geoBounds, geoCentre, sumoCentre, cosMid,
    geoCentreLon: geoCentre[0] / (111320 * cosMid),
    geoCentreLat: geoCentre[1] / 111320,
    padX: 0.55 * (geoBounds.maxX - geoBounds.minX),
    padY: 0.55 * (geoBounds.maxY - geoBounds.minY),
    residualMax: Math.max(...kept.map((a) => residual(fit, a))),
    kept: kept.length,
  };
}

function lonlatBoundsOf(payload) {
  let west = Infinity, east = -Infinity, south = Infinity, north = -Infinity;
  (payload.features || []).forEach((feature) => {
    (feature.geometry?.coordinates || []).forEach(([lon, lat]) => {
      if (lon < west) west = lon;
      if (lon > east) east = lon;
      if (lat < south) south = lat;
      if (lat > north) north = lat;
    });
  });
  return Number.isFinite(west) ? { west, east, south, north } : null;
}

/** Extract world centre + extents of the SUMO areas actually simulated. */
function frameOf(lanes, signals) {
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  const step = (x, y) => {
    if (x < minX) minX = x; if (x > maxX) maxX = x;
    if (y < minY) minY = y; if (y > maxY) maxY = y;
  };
  lanes.forEach((lane) => lane.shape.forEach(([x, y]) => step(x, y)));
  signals.forEach((signal) => step(signal.x, signal.y));
  if (!Number.isFinite(minX)) return null;
  return { minX, maxX, minY, maxY, cx: (minX + maxX) / 2, cy: (minY + maxY) / 2, span: Math.max(maxX - minX, maxY - minY, 140) };
}

/* --------------------------------------------------------------- parts */

function mergeRoadGeometry(lanes, frame) {
  const capacity = lanes.reduce((sum, lane) => sum + (lane.shape.length - 1), 0);
  const position = new Float32Array(capacity * 4 * 3);
  let offset = 0;
  /* SUMO's +y (north) must become three.js −z: the ground plane's texture top
     (north) sits at −z, so negating keeps roads pinned to the map streets. */
  const toWorld = ([x, y]) => [x - frame.cx, frame.cy - y];
  lanes.forEach((lane) => {
    const pts = lane.shape.map(toWorld);
    const halfWidth = Math.max(lane.width, 2.6) / 2;
    for (let i = 0; i < pts.length - 1; i += 1) {
      const [ax, az] = pts[i];
      const [bx, bz] = pts[i + 1];
      const dx = bx - ax, dz = bz - az;
      const len = Math.hypot(dx, dz) || 1;
      const nx = (-dz / len) * halfWidth;
      const nz = (dx / len) * halfWidth;
      position.set([ax + nx, 0.04, az + nz], offset); offset += 3;
      position.set([ax - nx, 0.04, az - nz], offset); offset += 3;
      position.set([bx - nx, 0.04, bz - nz], offset); offset += 3;
      position.set([bx + nx, 0.04, bz + nz], offset); offset += 3;
    }
  });
  const indices = [];
  for (let quad = 0; quad < capacity; quad += 1) {
    const base = quad * 4;
    indices.push(base, base + 1, base + 2, base, base + 2, base + 3);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(position, 3));
  geometry.setIndex(indices);
  return geometry;
}

/* Lane-marking bands: a light strip per lane edge, merged into one mesh. */
function mergeMarkingGeometry(lanes, frame, y = 0.07) {
  const segments = [];
  const toWorld = ([x, y]) => [x - frame.cx, frame.cy - y];
  lanes.forEach((lane) => {
    const pts = lane.shape.map(toWorld);
    for (let i = 0; i < pts.length - 1; i += 1) {
      segments.push(pts[i][0], y, pts[i][1], pts[i + 1][0], y, pts[i + 1][1]);
    }
  });
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(segments, 3));
  return geometry;
}

function makeInstancePool(scene, geometry, capacity = MAX_VEHICLES) {
  const mesh = new THREE.InstancedMesh(
    geometry,
    new THREE.MeshStandardMaterial({ roughness: 0.48, metalness: 0.08 }),
    capacity,
  );
  mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  mesh.count = 0;
  scene.add(mesh);
  return mesh;
}

function buildVehiclePools(scene) {
  const pools = {};
  for (const [kind, style] of Object.entries(VEHICLE_STYLES)) {
    const body = new THREE.BoxGeometry(style.width, style.height, style.length);
    // Geometry is centred on Y=0, so the instance origin is the road surface.
    // Roof ridges and windows are separate raised meshes; unlike a flat map
    // icon, each silhouette has visible vertical sides from the default view.
    body.translate(0, style.height / 2, 0);
    pools[kind] = makeInstancePool(scene, body);
    if (kind === 'car') {
      const hood = new THREE.BoxGeometry(style.width * 0.9, style.height * 0.25, style.length * 0.28);
      hood.translate(0, style.height * 0.69, style.length * 0.31);
      pools.carHood = makeInstancePool(scene, hood);
      const cabin = new THREE.BoxGeometry(style.width * 0.72, style.height * 0.5, style.length * 0.43);
      cabin.translate(0, style.height * 0.88, -style.length * 0.03);
      pools.carCabin = makeInstancePool(scene, cabin);
      const glass = new THREE.BoxGeometry(style.width * 0.66, style.height * 0.31, style.length * 0.34);
      glass.translate(0, style.height * 0.92, -style.length * 0.03);
      pools.carGlass = makeInstancePool(scene, glass);
    }
    if (kind === 'bus') {
      const roof = new THREE.BoxGeometry(style.width * 0.9, style.height * 0.16, style.length * 0.84);
      roof.translate(0, style.height * 1.04, 0);
      pools.busRoof = makeInstancePool(scene, roof);
      const windows = new THREE.BoxGeometry(style.width * 0.06, style.height * 0.36, style.length * 0.72);
      windows.translate(style.width * 0.49, style.height * 0.58, 0);
      pools.busWindows = makeInstancePool(scene, windows);
    }
    if (kind === 'emergency') {
      const cabin = new THREE.BoxGeometry(style.width * 0.76, style.height * 0.5, style.length * 0.46);
      cabin.translate(0, style.height * 0.89, -style.length * 0.03);
      pools.emergencyCabin = makeInstancePool(scene, cabin);
      const glass = new THREE.BoxGeometry(style.width * 0.68, style.height * 0.28, style.length * 0.36);
      glass.translate(0, style.height * 0.94, -style.length * 0.03);
      pools.emergencyGlass = makeInstancePool(scene, glass);
      const beacon = new THREE.BoxGeometry(style.width * 0.42, 0.18, style.length * 0.14);
      beacon.translate(0, style.height * 1.1, 0);
      pools.emergencyBeacon = makeInstancePool(scene, beacon);
    }
    if (kind === 'bicycle') {
      const frame = new THREE.BoxGeometry(0.08, 0.08, style.length * 0.58);
      frame.translate(0, 0.95, 0);
      pools.bicycleFrame = makeInstancePool(scene, frame);
      const rider = new THREE.CylinderGeometry(0.14, 0.19, 0.72, 6);
      rider.translate(0, 1.42, 0);
      pools.bicycleRider = makeInstancePool(scene, rider);
    }
  }    const wheelGeometry = new THREE.CylinderGeometry(0.34, 0.34, 0.2, 8);
    wheelGeometry.rotateZ(Math.PI / 2);
  pools.wheels = makeInstancePool(scene, wheelGeometry, MAX_VEHICLES * 4);
  return pools;
}

function buildPedestrianPools(scene) {
  const capacity = MAX_VEHICLES;
  const body = new THREE.CylinderGeometry(0.19, 0.25, PEDESTRIAN_SIZE.height * 0.62, 6);
  body.translate(0, PEDESTRIAN_SIZE.height * 0.38, 0);
  const head = new THREE.SphereGeometry(PEDESTRIAN_SIZE.radius, 8, 6);
  head.translate(0, PEDESTRIAN_SIZE.height * 0.83, 0);
  return {
    body: makeInstancePool(scene, body, capacity),
    head: makeInstancePool(scene, head, capacity),
  };
}

function buildSignals(scene, signals, frame) {
  /* One light per controlled lane: the TLS state string's i-th character is the
     i-th controlled link, so every incoming lane gets its own lamp with its own
     colour, mounted at that lane's stop line. */
  const targets = [];
  const mastGeometry = new THREE.CylinderGeometry(0.08, 0.1, 3.4, 6);
  mastGeometry.translate(0, 1.7, 0);
  const lampGeometry = new THREE.BoxGeometry(0.34, 1.0, 0.34);
  const mastMaterial = new THREE.MeshStandardMaterial({ color: COLORS.mast, roughness: 0.7 });

  signals.forEach((signal) => {
    const lanes = signal.lanes || [];
    lanes.forEach((entry) => {
      const mast = new THREE.Mesh(mastGeometry, mastMaterial);
      mast.position.set(entry.x - frame.cx, 0, frame.cy - entry.y);
      scene.add(mast);
      const lamp = new THREE.Mesh(lampGeometry, new THREE.MeshBasicMaterial({ color: COLORS.amber }));
      lamp.position.set(entry.x - frame.cx, 3.2, frame.cy - entry.y);
      scene.add(lamp);
      targets.push({ lamp, signalId: signal.id, laneIndex: entry.index });
    });
  });
  return targets;
}

function lampColourFor(stateChar) {
  const char = String(stateChar || 'G');
  if (/r/i.test(char)) return COLORS.red;
  if (/y/i.test(char)) return COLORS.amber;
  return COLORS.green;
}

/* -------------------------------------------------------------- mount */

export function mountSumoLiveMap(container, initial, { onSimAction } = {}) {
  void onSimAction;

  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(container.clientWidth || 640, container.clientHeight || 480);
  container.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(COLORS.sky);

  const camera = new THREE.PerspectiveCamera(FOV, 1, 0.5, 6000);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.maxPolarAngle = THREE.MathUtils.degToRad(80);
  controls.enableDamping = true;

  scene.add(new THREE.HemisphereLight(0xfaf4e6, 0x53606a, 1.2));
  const sun = new THREE.DirectionalLight(0xffffff, 1.05);
  sun.position.set(-320, 520, 220);
  scene.add(sun);

  let destroyed = false;
  let scenario = initial?.scenario || 'grid-2x2';
  let lastState = initial || { vehicles: [], signals: [] };

  let frame = null;
  let groundPlane = null;
  let vehiclePools = null;
  let pedestrianPools = null;
  let signalTargets = [];
  let previousState = null;
  let currentState = null;
  let stateReceivedAt = performance.now();
  let selectedVehicle = null;
  let selectedMarker = null;
  let overlay = null;
  let raf = 0;
  const runtimeMeshes = [];

  function renderLoop(now) {
    if (destroyed) return;
    const duration = Math.max(80, 1000 / Math.max(Number(lastState?.speed || 1), 0.25));
    const alpha = Math.min(1, Math.max(0, (now - stateReceivedAt) / duration));
    if (currentState && previousState && alpha < 1) {
      applyState(interpolateState(previousState, currentState, alpha));
    } else if (currentState) {
      applyState(currentState);
    }
    controls.update();
    renderer.render(scene, camera);
    raf = window.requestAnimationFrame(renderLoop);
  }
  raf = window.requestAnimationFrame(renderLoop);

  function resetView() {
    if (!frame) return;
    const radius = Math.max(frame.span * 0.85, 260);
    controls.target.set(0, 0, 0);
    camera.position.set(
      0,
      radius * Math.sin(THREE.MathUtils.degToRad(TILT)),
      radius * Math.cos(THREE.MathUtils.degToRad(TILT))
    );
    controls.update();
  }

  function clearSitework() {
    runtimeMeshes.splice(0).forEach((entry) => {
      scene.remove(entry.mesh);
      entry.mesh.geometry?.dispose();
      delete entry.mesh.material?.map;
      entry.mesh.material?.dispose();
    });
    signalTargets = [];
  }

  function applyGroundTexture() {
    if (!frame?.fit) return;
    const mapToken = resolveToken();
    if (!mapToken) return;
    const { west, south, east, north } = frame.fit.mapBbox;
    /* Image spans the padded geographic bbox at its native aspect; Mapbox caps
       static images at 1280 base pixels per axis (2560 at @2x). */
    const ratio = (north - south) * 111320 / ((east - west) * 111320 * Math.cos(((south + north) / 2) * Math.PI / 180));
    let imgWidth = 1280, imgHeight = Math.round(1280 * ratio);
    if (imgHeight > 1280) { imgHeight = 1280; imgWidth = Math.max(256, Math.round(1280 / ratio)); }
    if (imgHeight < 256) imgHeight = 256;
    const url =
      'https://api.mapbox.com/styles/v1/mapbox/streets-v12/static/' +
      `[${west},${south},${east},${north}]/` +
      `${imgWidth}x${imgHeight}@2x?access_token=${encodeURIComponent(mapToken)}`;
    new THREE.TextureLoader().load(url, (texture) => {
      if (destroyed) return;
      texture.colorSpace = THREE.SRGBColorSpace;
      if (groundPlane) {
        groundPlane.material = new THREE.MeshBasicMaterial({ map: texture });
      }
    });
  }

  async function loadNetwork(nextScenario) {
    const mapped = nextScenario === 'grid-3x3' ? 'grid-3x3' : 'grid-2x2';
    const host = `${window.location.protocol}//${window.location.hostname}:8000`;
    const response = await fetch(`${host}/api/simulation/network/${mapped}`);
    if (!response.ok) throw new Error(`network ${response.status}`);
    const payload = await response.json();
    const prepared = prepareNetwork(payload);
    if (!prepared) throw new Error('empty network');

    frame = frameOf(prepared.lanes, prepared.signals);
    if (!frame) throw new Error('flat network');
    frame.lonlatBounds = prepared.lonlatBounds;

    clearSitework();

    const roadMesh = new THREE.Mesh(
      mergeRoadGeometry(prepared.lanes, frame),
      new THREE.MeshStandardMaterial({ color: COLORS.asphalt, roughness: 0.95, metalness: 0.05, side: THREE.DoubleSide })
    );
    scene.add(roadMesh);
    runtimeMeshes.push({ mesh: roadMesh });

    const markingsMesh = new THREE.LineSegments(
      mergeMarkingGeometry(prepared.lanes, frame),
      new THREE.LineBasicMaterial({ color: COLORS.marking, transparent: true, opacity: 0.8 })
    );
    scene.add(markingsMesh);
    runtimeMeshes.push({ mesh: markingsMesh });

    signalTargets = buildSignals(scene, prepared.signals, frame);
    if (!vehiclePools) vehiclePools = buildVehiclePools(scene);
    if (!pedestrianPools) pedestrianPools = buildPedestrianPools(scene);

    // Junction paving: a slightly lighter asphalt patch under each
    // signalised junction so the crossings read clearly against the lanes.
    const padGeometry = new THREE.PlaneGeometry(1, 1);
    padGeometry.rotateX(-Math.PI / 2);
    const padMaterial = new THREE.MeshStandardMaterial({ color: 0x494e55, roughness: 0.9 });
    prepared.signals.forEach((signal) => {
      const pad = new THREE.Mesh(padGeometry, padMaterial);
      const size = 22;
      pad.scale.set(size, 1, size);
      pad.position.set(signal.x - frame.cx, 0.02, frame.cy - signal.y);
      scene.add(pad);
      runtimeMeshes.push({ mesh: pad });
    });

    /* The basemap is anchored by a similarity fit between the network's own
       geo-referenced lane shapes and the SUMO metre frame (which is UTM, so
       rotated off true north). The plane is therefore rotated by the fitted
       angle and positioned at the fitted centre — streets meet roads. */
    frame.fit = prepared.anchors.length >= 4 ? fitGeoToWorld(prepared.anchors, frame) : null;
    if (frame.fit) {
      const { west, east, south, north } = prepared.lonlatBounds;
      frame.fit.centreLon = (west + east) / 2;
      frame.fit.centreLat = (south + north) / 2;
      /* Keep the full street-feature extent plus generous padding; do not crop
         the Mapbox context to lane endpoints. Size the image plane in the same
         local metric projection used for the similarity fit. */
      const centreLon = (west + east) / 2;
      const centreLat = (south + north) / 2;
      const cosLat = Math.cos(centreLat * Math.PI / 180);
      const padLon = (east - west) * 0.35;
      const padLat = (north - south) * 0.35;
      const mapW = (east - west + 2 * padLon) * 111320 * cosLat;
      const mapH = (north - south + 2 * padLat) * 111320;
      frame.fit.mapBbox = {
        west: west - padLon, east: east + padLon,
        south: south - padLat, north: north + padLat,
      };
      frame.fit.planeW = mapW * frame.fit.scale;
      frame.fit.planeH = mapH * frame.fit.scale;
      frame.fit.sceneCentre = [
        frame.fit.sumoCentre[0] - frame.cx,
        frame.cy - frame.fit.sumoCentre[1],
      ];
    }

    if (groundPlane) {
      scene.remove(groundPlane);
      groundPlane.geometry.dispose();
    }
    const planeW = frame.fit ? frame.fit.planeW : frame.span * 2.2;
    const planeH = frame.fit ? frame.fit.planeH : frame.span * 2.2;
    const groundGeometry = new THREE.PlaneGeometry(planeW, planeH);
    groundGeometry.rotateX(-Math.PI / 2);
    groundPlane = new THREE.Mesh(
      groundGeometry,
      new THREE.MeshStandardMaterial({ color: COLORS.ground, roughness: 1 })
    );
    if (frame.fit) {
      groundPlane.rotation.y = frame.fit.theta; /* geo east/north → world rotation */
      groundPlane.position.set(frame.fit.sceneCentre[0], 0, frame.fit.sceneCentre[1]);
    }
    scene.add(groundPlane);
    applyGroundTexture();

    resetView();
    applyState(lastState);
  }

  function networkFailure() {
    window.setTimeout(() => {
      if (!destroyed) loadNetwork(scenario).catch(networkFailure);
    }, 2500);
  }

  function toWorld(x, y) { return [x - frame.cx, frame.cy - y]; }

  function updateVehicles(vehicles, pedestrians = []) {
    if (!vehiclePools || !pedestrianPools) return;
    const grouped = { car: [], taxi: [], bus: [], truck: [], emergency: [], bicycle: [], motorcycle: [] };
    (vehicles || []).forEach((vehicle) => {
      const cls = `${vehicle.vehicleClass || ''} ${vehicle.type || ''}`.toLowerCase();
      const kind = /emergency|fire|police|ambulance/.test(cls) ? 'emergency'
        : /bus|coach/.test(cls) ? 'bus'
          : /taxi/.test(cls) ? 'taxi'
            : /truck|delivery|trailer/.test(cls) ? 'truck'
              : /bicycle|bike/.test(cls) ? 'bicycle'
                : /motorcycle|moped/.test(cls) ? 'motorcycle' : 'car';
      if (CLASS_FILTERS.get(kind) && grouped[kind].length < MAX_VEHICLES) grouped[kind].push(vehicle);
    });
    const matrix = new THREE.Matrix4();
    const orientation = new THREE.Matrix4();
    const position = new THREE.Vector3();
    const scale = new THREE.Vector3(1, 1, 1);
    const quaternion = new THREE.Quaternion();
    for (const [kind, pool] of Object.entries(vehiclePools)) {
      const sourceKind = kind.startsWith('car') ? 'car'
        : kind.startsWith('taxi') ? 'taxi'
          : kind.startsWith('bus') ? 'bus'
            : kind.startsWith('truck') ? 'truck'
              : kind.startsWith('emergency') ? 'emergency'
                : kind.startsWith('bicycle') ? 'bicycle'
                  : kind.startsWith('motorcycle') ? 'motorcycle'
                    : kind;
      if (kind === 'wheels') continue;
      const items = grouped[sourceKind] || [];
      pool.count = items.length;
      items.forEach((vehicle, index) => {
        const style = VEHICLE_STYLES[sourceKind];
        orientation.makeRotationY(THREE.MathUtils.degToRad(-(vehicle.angle || 0)));
        const offsetY = kind === 'wheels' ? 0 : 0.03;
        position.set(vehicle.x - frame.cx, offsetY, frame.cy - vehicle.y);
        orientation.decompose(new THREE.Vector3(), quaternion, scale);
        matrix.compose(position, quaternion, scale);
        pool.setMatrixAt(index, matrix);
        const isGlass = /Glass|Windows/.test(kind);
        const isAccent = /Cabin|Roof|Hood|Beacon|Frame|Rider/.test(kind);
        const color = isGlass ? 0x9fd0df
          : kind.includes('Beacon') ? 0xf5f4ed
            : isAccent ? (sourceKind === 'bus' ? 0xf4d36a : style.color)
              : vehicle.waiting ? COLORS.vehicleStopped : style.color;
        pool.setColorAt(index, new THREE.Color(color));
      });
      pool.instanceMatrix.needsUpdate = true;
      if (pool.instanceColor) pool.instanceColor.needsUpdate = true;
    }

    const wheels = vehiclePools.wheels;
    let wheelIndex = 0;
    (vehicles || []).slice(0, MAX_VEHICLES).forEach((vehicle) => {
      const cls = `${vehicle.vehicleClass || ''} ${vehicle.type || ''}`.toLowerCase();
      const kind = /emergency|fire|police|ambulance/.test(cls) ? 'emergency'
        : /bus|coach/.test(cls) ? 'bus'
          : /taxi/.test(cls) ? 'taxi'
            : /truck|delivery|trailer/.test(cls) ? 'truck'
              : /bicycle|bike/.test(cls) ? 'bicycle'
                : /motorcycle|moped/.test(cls) ? 'motorcycle' : 'car';
      if (!CLASS_FILTERS.get(kind)) return;
      const style = VEHICLE_STYLES[kind];
      const wheelbase = kind === 'bus' ? style.length * 0.36 : style.length * 0.32;
      const track = style.width * 0.48;
      const wheelRadius = kind === 'bicycle' ? 0.38 : kind === 'bus' ? 0.42 : 0.34;
      const wheelWidth = kind === 'bicycle' ? 0.09 : 0.2;
      const offsets = kind === 'bicycle'
        ? [[0, wheelRadius, -style.length * 0.39], [0, wheelRadius, style.length * 0.39]]
        : [[-track, wheelRadius, -wheelbase], [track, wheelRadius, -wheelbase], [-track, wheelRadius, wheelbase], [track, wheelRadius, wheelbase]];
      const angle = THREE.MathUtils.degToRad((vehicle.angle || 0) + 90);
      offsets.forEach(([lx, ly, lz]) => {
        const wx = vehicle.x - frame.cx + lx * Math.cos(angle) + lz * Math.sin(angle);
        const wz = frame.cy - vehicle.y - lx * Math.sin(angle) + lz * Math.cos(angle);
        position.set(wx, ly, wz);
        quaternion.setFromAxisAngle(new THREE.Vector3(0, 1, 0), angle);
        matrix.compose(position, quaternion, new THREE.Vector3(wheelWidth / 0.2, 1, 1));
        wheels.setMatrixAt(wheelIndex, matrix);
        wheels.setColorAt(wheelIndex, new THREE.Color(0x252a30));
        wheelIndex += 1;
      });
    });
    wheels.count = wheelIndex;
    wheels.instanceMatrix.needsUpdate = true;
    if (wheels.instanceColor) wheels.instanceColor.needsUpdate = true;

    const walkers = (pedestrians || []).slice(0, MAX_VEHICLES);
    for (const pool of Object.values(pedestrianPools)) {
      pool.count = walkers.length;
      walkers.forEach((person, index) => {
        const [wx, wz] = toWorld(person.x, person.y);
        position.set(wx, 0.12, wz);
        quaternion.identity();
        matrix.compose(position, quaternion, scale);
        pool.setMatrixAt(index, matrix);
        pool.setColorAt(index, person.waiting ? 0xc84343 : 0x7952bd);
      });
      pool.instanceMatrix.needsUpdate = true;
      if (pool.instanceColor) pool.instanceColor.needsUpdate = true;
    }
  }

  function updateSignalLamps(signalEntries) {
    const byId = new Map((signalEntries || []).map((s) => [s.id, s.state]));
    signalTargets.forEach(({ lamp, signalId, laneIndex }) => {
      const state = byId.get(signalId);
      const chars = String(state || '');
      lamp.material.color.setHex(chars ? lampColourFor(chars[laneIndex % chars.length]) : COLORS.amber);
    });
  }

  function applyState(state) {
    if (!state || !frame) return;
    updateVehicles(state.vehicles || [], state.pedestrians || []);
    updateSignalLamps(state.signals || []);
    if (selectedVehicle) {
      const entity = (state.vehicles || []).find((item) => item.id === selectedVehicle.id);
      if (entity && selectedMarker) selectedMarker.position.set(entity.x - frame.cx, 0.08, frame.cy - entity.y);
      else clearSelection();
    }
  }

  function shortestAngle(a, b, alpha) {
    const delta = ((b - a + 540) % 360) - 180;
    return a + delta * alpha;
  }

  function interpolateState(previous, current, alpha) {
    const previousVehicles = new Map((previous.vehicles || []).map((item) => [item.id, item]));
    const blend = (items = [], oldItems = previousVehicles) => items.map((item) => {
      const old = oldItems.get(item.id);
      if (!old) return item;
      return { ...item,
        x: old.x + (item.x - old.x) * alpha,
        y: old.y + (item.y - old.y) * alpha,
        angle: shortestAngle(Number(old.angle || 0), Number(item.angle || 0), alpha),
      };
    });
    const previousPeople = new Map((previous.pedestrians || []).map((item) => [item.id, item]));
    return { ...current, vehicles: blend(current.vehicles), pedestrians: blend(current.pedestrians, previousPeople) };
  }

  function clearSelection() {
    selectedVehicle = null;
    if (selectedMarker) { scene.remove(selectedMarker); selectedMarker.geometry.dispose(); selectedMarker.material.dispose(); selectedMarker = null; }
  }

  function selectVehicle(event) {
    const rect = renderer.domElement.getBoundingClientRect();
    pickPointer.set(((event.clientX - rect.left) / rect.width) * 2 - 1, -((event.clientY - rect.top) / rect.height) * 2 + 1);
    pickRaycaster.setFromCamera(pickPointer, camera);
    const pools = [...Object.values(vehiclePools || {}).filter((mesh) => mesh !== vehiclePools.wheels), ...Object.values(pedestrianPools || {})];
    const hit = pickRaycaster.intersectObjects(pools, false)[0];
    if (!hit) { clearSelection(); return; }
    const point = hit.point;
    const vehicle = [...(currentState?.vehicles || []), ...(currentState?.pedestrians || [])]
      .reduce((closest, item) => !closest || Math.hypot(item.x - frame.cx - point.x, frame.cy - item.y - point.z) < Math.hypot(closest.x - frame.cx - point.x, frame.cy - closest.y - point.z) ? item : closest, null);
    if (!vehicle) return;
    clearSelection();
    selectedVehicle = vehicle;
    selectedMarker = new THREE.Mesh(new THREE.TorusGeometry(2.8, 0.12, 6, 24), new THREE.MeshBasicMaterial({ color: 0xffffff }));
    selectedMarker.rotation.x = Math.PI / 2;
    selectedMarker.position.set(vehicle.x - frame.cx, 0.08, frame.cy - vehicle.y);
    scene.add(selectedMarker);
    const cls = vehicle.vehicleClass || vehicle.type || 'pedestrian';
    container.dispatchEvent(new CustomEvent('sumo:vehiclepick', { bubbles: true, detail: { id: vehicle.id, vehicleClass: cls, speed: vehicle.speed, waiting: vehicle.waiting } }));
  }
  renderer.domElement.addEventListener('click', selectVehicle);

  const env = {
    update(next) {
      if (!next) return;
      previousState = currentState;
      currentState = next;
      lastState = next;
      stateReceivedAt = performance.now();
      if (next.scenario && next.scenario !== scenario) {
        scenario = next.scenario;
        loadNetwork(scenario).catch(networkFailure);
      }
      applyState(next);
    },
    /* Layer toggles from the Live Map's layers menu. */
    setBasemap(visible) {
      if (!groundPlane) return false;
      if (visible) applyGroundTexture();
      groundPlane.visible = Boolean(visible);
      return true;
    },
    setRoads(visible) {
      runtimeMeshes.forEach(({ mesh }) => { mesh.visible = Boolean(visible); });
    },
    setVehicles(visible) {
      Object.values(vehiclePools || {}).forEach((pool) => { pool.visible = Boolean(visible); });
      Object.values(pedestrianPools || {}).forEach((pool) => { pool.visible = Boolean(visible); });
    },
    setClassVisible(kind, visible) {
      CLASS_FILTERS.set(kind, Boolean(visible));
      if (currentState) applyState(currentState);
    },
    follow(id) {
      const entity = [...(currentState?.vehicles || []), ...(currentState?.pedestrians || [])].find((item) => item.id === id);
      if (!entity) return false;
      controls.target.set(entity.x - frame.cx, 0, frame.cy - entity.y);
      controls.update();
      return true;
    },
    zoomIn() { camera.position.multiplyScalar(0.82); controls.update(); },
    zoomOut() { camera.position.multiplyScalar(1.22); controls.update(); },
    reset() { resetView(); },
    destroy() {
      destroyed = true;
      window.cancelAnimationFrame(raf);
      controls.dispose();
      renderer.domElement.removeEventListener('click', selectVehicle);
      if (overlay) map.removeControl(overlay);
      clearSelection();
      renderer.dispose();
      renderer.domElement.remove();
    },
  };

  loadNetwork(scenario).catch(networkFailure);

  const resizeObserver = new ResizeObserver(() => {
    const width = container.clientWidth || 640;
    const height = container.clientHeight || 480;
    renderer.setSize(width, height);
    camera.aspect = width / Math.max(height, 1);
    camera.updateProjectionMatrix();
  });
  resizeObserver.observe(container);

  window.__sumo3d = { env, renderer, scene, camera, controls };
  return env;
}

export default mountSumoLiveMap;
