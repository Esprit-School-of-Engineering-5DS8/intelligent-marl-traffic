import mapboxgl from 'mapbox-gl';
import * as THREE from 'three';
import 'mapbox-gl/dist/mapbox-gl.css';
import { mountBenchmarkView, setBenchmarkTab } from './benchmark-mount.jsx';
import { mountGauges } from './gauge.js';
import { initModes, refreshLiveGauges } from './modes/index.js';
import { setLiveState } from './modes/live.js';

const $ = (id) => document.getElementById(id);
// Declared up here because applyScenarioChrome() runs during module evaluation and
// reaches setMapLayerVisibility(), which reads liveMap long before the live-map
// section below would otherwise initialise it (temporal dead zone crash).
let liveMap = null;
const FOCUS = [-97.7264, 30.2653];
const DEFAULT_ZOOM = 13.5;
const TOKEN_KEY = 'kematara.mapboxToken';
const SCENARIO_KEY = 'sumo.scenario';

const SCENARIOS = {
  'grid-2x2': {
    label: 'SF Mission 2×2',
    title: 'San Francisco · Mission 2×2',
    menuSub: 'Mission / Howard × 6th / 7th',
    place: 'Mission & 6th, San Francisco',
    zone: 'SoMa corridor',
    queuedRoad: 'Mission · Westbound',
    mapCenter: [-122.4091, 37.7796],
    mapZoom: 16,
    liveCenter: [-122.4091, 37.7796],
    liveZoom: 16.2,
    route: [
      [-122.4109, 37.7792], [-122.4087, 37.7810],
      [-122.4072, 37.7797], [-122.4094, 37.7780],
      [-122.4109, 37.7792]
    ],
    crossRoute: [
      [-122.4072, 37.7797], [-122.4094, 37.7780],
      [-122.4087, 37.7810], [-122.4109, 37.7792]
    ]
  },
  'grid-3x3': {
    label: 'SF Mission 3×3',
    title: 'San Francisco · Mission 3×3',
    menuSub: 'Mission / Howard / Folsom × 6th / 7th / 8th',
    place: 'Mission & 7th, San Francisco',
    zone: 'SoMa corridor',
    queuedRoad: 'Mission · Westbound',
    mapCenter: [-122.4094, 37.7781],
    mapZoom: 15.7,
    liveCenter: [-122.4094, 37.7781],
    liveZoom: 16,
    route: [
      [-122.4132, 37.7775], [-122.4087, 37.7810],
      [-122.4056, 37.7785], [-122.4101, 37.7750],
      [-122.4132, 37.7775]
    ],
    crossRoute: [
      [-122.4072, 37.7797], [-122.4094, 37.7780], [-122.4116, 37.7762],
      [-122.4101, 37.7750], [-122.4079, 37.7768], [-122.4056, 37.7785]
    ]
  }
,
  monaco: {
    label: 'Monaco',
    title: 'Monaco',
    menuSub: 'Urban corridor simulation',
    place: 'Monaco',
    zone: 'Monaco',
    queuedRoad: 'Monaco · Westbound',
    mapCenter: [7.4246, 43.7384],
    mapZoom: 14,
    liveCenter: [7.4246, 43.7384],
    liveZoom: 15.6,
    route: [
      [7.4208, 43.73831], [7.42312, 43.73848], [7.42316, 43.73852], [7.42315, 43.73855],
      [7.42312, 43.73858], [7.42305, 43.73859], [7.42301, 43.73866], [7.42294, 43.73893],
      [7.42285, 43.73909], [7.42242, 43.73943], [7.42373, 43.73985], [7.42404, 43.73996],
      [7.42438, 43.74012], [7.42443, 43.74015], [7.42485, 43.74061], [7.42493, 43.74067],
      [7.42501, 43.74068], [7.4252, 43.74066], [7.4256, 43.74045], [7.42551, 43.7403],
      [7.42706, 43.73947], [7.42718, 43.73949], [7.42721, 43.73959], [7.4273, 43.73971],
      [7.42806, 43.74047], [7.42816, 43.74041], [7.42827, 43.74039], [7.4287, 43.74043],
      [7.42885, 43.74042], [7.429, 43.74036], [7.42917, 43.74024], [7.42927, 43.74013],
      [7.42937, 43.73985], [7.42931, 43.73952], [7.42943, 43.7394], [7.42942, 43.73931],
      [7.42493, 43.74067], [7.42501, 43.74068], [7.42504, 43.74068], [7.42512, 43.74068],
      [7.4252, 43.74066], [7.42548, 43.7405], [7.4255, 43.74049], [7.4256, 43.74045],
      [7.42551, 43.7403], [7.42547, 43.74025], [7.42545, 43.74021], [7.42537, 43.74009]
    ]
  },
  tunis: {
    label: 'Tunis',
    title: 'Tunis',
    menuSub: 'Metropolitan network simulation',
    place: 'Tunis',
    zone: 'Tunis',
    queuedRoad: 'Tunis · Westbound',
    mapCenter: [10.197, 36.806],
    mapZoom: 12.9,
    liveCenter: [10.197, 36.806],
    liveZoom: 13.4,
    route: [
      [10.17761, 36.80653], [10.17751, 36.80637], [10.17745, 36.80618], [10.17748, 36.80584],
      [10.177, 36.80579], [10.17693, 36.80572], [10.17694, 36.80566], [10.17698, 36.80562],
      [10.17707, 36.80559], [10.17773, 36.80552], [10.17857, 36.8055], [10.17994, 36.80563],
      [10.18062, 36.80572], [10.1809, 36.80613], [10.18113, 36.80619], [10.18522, 36.80663],
      [10.18524, 36.80649]
    ],
    crossRoute: [
      [10.18062, 36.80572], [10.18086, 36.80609], [10.1809, 36.80613], [10.18094, 36.80616],
      [10.18113, 36.80619], [10.18141, 36.80622], [10.18148, 36.80585], [10.18149, 36.80578],
      [10.18149, 36.80572]
    ]
  }};
let activeScenario = 'grid-2x2';
try {
  const savedScenario = localStorage.getItem(SCENARIO_KEY);
  if (savedScenario && SCENARIOS[savedScenario]) activeScenario = savedScenario;
} catch {
  // Keep the default scenario if storage is unavailable.
}

function getScenario() {
  return SCENARIOS[activeScenario] || SCENARIOS['grid-2x2'];
}

/** The scenario id sent to the backend. Never silently fall back to an SF grid. */
function simulationScenarioId() {
  return SCENARIOS[activeScenario] ? activeScenario : 'grid-2x2';
}

let map = null;
let benchmarkMounted = false;
let benchmarkTab = 'models';
let mapFocusMarker = null;
let simulationSeeded = false;

function resolveToken() {
  return localStorage.getItem(TOKEN_KEY)
    || import.meta.env.VITE_MAPBOX_TOKEN
    || window.MAPBOX_TOKEN
    || '';
}

function showTokenPanel(message) {
  const panel = $('tokenPanel');
  if (!panel) return;
  panel.hidden = false;
  const note = panel.querySelector('.token-message');
  if (note) note.textContent = message || 'Mapbox access token required for the live map.';
}

function hideTokenPanel() {
  const panel = $('tokenPanel');
  if (panel) panel.hidden = true;
}

function setOffline(offline) {
  const node = $('mapOffline');
  if (node) node.hidden = !offline;
  if (offline) {
    const container = $('map');
    if (container) container.innerHTML = '';
    map = null;
    mapFocusMarker = null;
  }
}

function buildMap(token) {
  if (map) {
    map.remove();
    map = null;
  }
  mapFocusMarker = null;

  mapboxgl.accessToken = token;
  const container = $('map');
  if (!container) return;
  container.innerHTML = '';
  setOffline(false);

  const scenario = getScenario();
  map = new mapboxgl.Map({
    container,
    center: scenario.mapCenter,
    zoom: scenario.mapZoom,
    pitch: 0,
    bearing: 0,
    antialias: true,
    attributionControl: false,
    style: 'mapbox://styles/mapbox/light-v11'
  });

  map.addControl(new mapboxgl.AttributionControl({ compact: true }), 'bottom-right');

  const marker = document.createElement('div');
  marker.className = 'focus-marker';
  mapFocusMarker = new mapboxgl.Marker({ element: marker, anchor: 'center' })
    .setLngLat(scenario.mapCenter)
    .addTo(map);

  map.on('error', (event) => {
    const message = String(event?.error?.message || '');
    if (/token|401|unauthorized|not authorized/i.test(message)) {
      showTokenPanel(message);
      setOffline(true);
    }
  });
}

function resetMapView() {
  if (!map) return;
  const scenario = getScenario();
  map.flyTo({ center: scenario.mapCenter, zoom: scenario.mapZoom, pitch: 0, bearing: 0, duration: 900 });
}

document.querySelectorAll('[data-map-action]').forEach((button) => {
  button.addEventListener('click', () => {
    if (!map) {
      showTokenPanel('Connect a Mapbox token to use the map.');
      return;
    }
    const action = button.dataset.mapAction;
    if (action === 'zoom-in') map.zoomIn();
    if (action === 'zoom-out') map.zoomOut();
    if (action === 'reset') resetMapView();
  });
});

const scenarioTriggers = [...document.querySelectorAll('[data-scenario-trigger]')];
const scenarioMenus = [...document.querySelectorAll('[data-scenario-menu]')];

function scenarioOptionMarkup(key, scenario) {
  return `
        <button type="button" class="scenario-option" data-scenario-option="${key}" role="option" aria-selected="false">
          <span class="scenario-option-check"><svg class="ico"><use href="#i-check"/></svg></span>
          <span class="scenario-option-copy">
            <strong>${scenario.label}</strong>
            <small>${scenario.menuSub}</small>
          </span>
        </button>`;
}

/* Every menu offers the scenarios. The two headless SUMO grids (San Francisco
   Mission corridors) are grouped apart because they draw the TraCI network on
   the canvas scene over a Mapbox basemap instead of the live map layers. */
function renderScenarioMenus() {
  scenarioMenus.forEach((menu) => {
    const all = Object.entries(SCENARIOS);
    // Real-city networks and the synthetic SF grids are grouped apart: the grids
    // draw the TraCI network on the canvas scene, the city nets use map layers.
    const isGrid = ([key]) => key.startsWith('grid-');
    const places = all.filter((entry) => !isGrid(entry));
    const grids = all.filter(isGrid);
    menu.innerHTML = `
      <div class="scenario-menu-head" role="presentation">
        <span>Simulation scenario</span>
      <small>${all.length} available</small>
      </div>
      ${
        places.length
          ? `<div class="scenario-menu-group" role="presentation"><span>City networks</span><small>OSM · MoST</small></div>
      ${places.map(([key, scenario]) => scenarioOptionMarkup(key, scenario)).join('')}`
          : ''
      }
      ${
        grids.length
          ? `<div class="scenario-menu-group" role="presentation"><span>San Francisco grids</span><small>Live TraCI · OSM</small></div>
      ${grids.map(([key, scenario]) => scenarioOptionMarkup(key, scenario)).join('')}`
          : ''
      }
    `;
  });

  document.querySelectorAll('[data-scenario-option]').forEach((option) => {
    option.addEventListener('click', () => {
      setScenario(option.dataset.scenarioOption);
      closeScenarioMenus();
    });
  });
}

function setScenarioMenuOpen(menu, open) {
  if (!menu) return;
  menu.hidden = !open;
  menu.closest('.site-card, .live-scenario-wrap')?.classList.toggle('is-menu-open', open);
  scenarioTriggers.forEach((trigger) => {
    if (trigger.getAttribute('aria-controls') === menu.id) {
      trigger.setAttribute('aria-expanded', String(open));
    }
  });
}

function closeScenarioMenus() {
  scenarioMenus.forEach((menu) => setScenarioMenuOpen(menu, false));
}

function toggleScenarioMenu(trigger) {
  const menu = $(trigger.getAttribute('aria-controls'));
  if (!menu) return;
  const willOpen = menu.hidden;
  closeScenarioMenus();
  setScenarioMenuOpen(menu, willOpen);
}

function applyScenarioChrome() {
  const scenario = getScenario();
  const siteTitle = $('siteTitle');
  if (siteTitle) siteTitle.textContent = scenario.title;
  const liveScenarioName = $('liveScenarioName');
  if (liveScenarioName) liveScenarioName.textContent = scenario.title;
  const mapLocation = $('mapLocationName');
  if (mapLocation) mapLocation.textContent = scenario.zone;
  const livePlace = $('livePlaceName');
  if (livePlace) livePlace.textContent = scenario.place;
  const zoneSector = $('liveZoneSector');
  if (zoneSector) zoneSector.textContent = scenario.zone;
  const queuedRoad = $('liveQueuedRoad');
  if (queuedRoad) queuedRoad.textContent = scenario.queuedRoad;
  const liveCanvas = $('liveMap');
  if (liveCanvas) liveCanvas.setAttribute('aria-label', `3D live traffic map of ${scenario.place}`);
  const simStart = $('simulationStart');
  if (simStart) {
    const labels = {
      'grid-2x2': '2×2',
      'grid-3x3': '3×3'
    };
    const startLabel = labels[activeScenario] || scenario.label;
    simStart.innerHTML = `<svg class="ico"><use href="#i-refresh"/></svg>Start ${startLabel}`;
  }
  document.querySelectorAll('[data-scenario-option]').forEach((option) => {
    const selected = option.dataset.scenarioOption === activeScenario;
    option.classList.toggle('is-selected', selected);
    option.setAttribute('aria-selected', String(selected));
  });
  document.title = `SUMO · ${scenario.title}`;
}

const WEATHER_CODES = [
  { match: (c) => c === 0, icon: 'i-sun', label: 'Clear sky' },
  { match: (c) => c === 1, icon: 'i-sun', label: 'Mainly clear' },
  { match: (c) => c === 2, icon: 'i-cloud-sun', label: 'Partly cloudy' },
  { match: (c) => c === 3, icon: 'i-cloud', label: 'Overcast' },
  { match: (c) => c === 45 || c === 48, icon: 'i-fog', label: 'Fog' },
  { match: (c) => c >= 51 && c <= 57, icon: 'i-rain', label: 'Drizzle' },
  { match: (c) => c >= 80 && c <= 82, icon: 'i-rain', label: 'Rain showers' },
  { match: (c) => c >= 61 && c <= 67, icon: 'i-rain', label: 'Rain' },
  { match: (c) => (c >= 71 && c <= 77) || c === 85 || c === 86, icon: 'i-snow', label: 'Snow' },
  { match: (c) => c >= 95, icon: 'i-storm', label: 'Thunderstorm' }
];

let weatherToken = 0;

function describeWeather(code) {
  return WEATHER_CODES.find((entry) => entry.match(code)) || { icon: 'i-cloud', label: 'Unknown conditions' };
}

function setLiveWeather(icon, label) {
  const box = $('liveWeatherIcon');
  if (!box) return;
  box.querySelector('use')?.setAttribute('href', `#${icon}`);
  box.dataset.weather = icon.replace(/^i-/, '');
  box.setAttribute('aria-label', label);
  box.setAttribute('title', label);
}

async function loadLiveWeather() {
  const scenarioKey = activeScenario;
  const [longitude, latitude] = getScenario().liveCenter;
  const token = ++weatherToken;
  try {
    const response = await fetch(`https://api.open-meteo.com/v1/forecast?latitude=${latitude}&longitude=${longitude}&current=temperature_2m,weather_code&timezone=auto`);
    if (!response.ok) throw new Error(`Weather request failed (${response.status})`);
    const data = await response.json();
    if (token !== weatherToken || scenarioKey !== activeScenario) return;
    const weather = describeWeather(Number(data?.current?.weather_code));
    const temperature = Math.round(Number(data?.current?.temperature_2m));
    setLiveWeather(weather.icon, Number.isFinite(temperature) ? `${weather.label} · ${temperature}°C` : weather.label);
  } catch {
    if (token !== weatherToken) return;
    setLiveWeather('i-cloud', 'Weather unavailable');
  }
}

/* Moving between the two grids must not leave the previous run's vehicles on
   the new network: if something is already live, restart it on this grid. */
/* A new scenario takes over the live run: the backend maps every scenario id to its
   own network (monaco, tunis included), so the picker restarts the run on it. A page
   that has not received a socket frame yet asks the service for the current run. */
async function retargetSimulation(name) {
  if (!SCENARIOS[name]) return;
  const live = latestSimulationState
    || await simulationFetch('/api/simulation/state')
      .then((response) => (response.ok ? response.json() : null))
      .catch(() => null);
  if (!live) return;
  const active = ['running', 'paused', 'starting'].includes(live.status);
  // The selected scenario owns the live run. Bailing out when the run was idle
  // left the map on the old scenario's last snapshot, so its vehicles and lights
  // vanished; starting here keeps the picker and the map in agreement.
  if (active && live.scenario === name) return;
  simulationFetch('/api/simulation/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scenario: name, speed: simulationSpeed })
  })
    .then((response) => (response.ok ? response.json() : null))
    .then((state) => state && updateSimulationState(state))
    .catch(() => {});
}

function setScenario(name, { announce = true, retarget = true } = {}) {
  if (!SCENARIOS[name]) return;
  activeScenario = name;
  try {
    localStorage.setItem(SCENARIO_KEY, activeScenario);
  } catch {
    // Scenario still applies for the current session.
  }
  applyScenarioChrome();
  loadLiveWeather();

  const scenario = getScenario();
  if (map) {
    map.flyTo({ center: scenario.mapCenter, zoom: scenario.mapZoom, duration: 1000, essential: true });
    mapFocusMarker?.setLngLat(scenario.mapCenter);
  }
  refreshLiveMapScenario();
  loadSimulationNetwork(activeScenario);
  if (retarget) retargetSimulation(activeScenario);

  document.dispatchEvent(new CustomEvent('sumo:scenariochange', {
    detail: { scenario: activeScenario, ...scenario }
  }));
  if (announce) showToast(`${scenario.label} scenario loaded.`);
}

scenarioTriggers.forEach((trigger) => {
  trigger.addEventListener('click', (event) => {
    event.stopPropagation();
    toggleScenarioMenu(trigger);
  });
});

document.addEventListener('click', (event) => {
  if (!event.target.closest('[data-scenario-menu], [data-scenario-trigger]')) closeScenarioMenus();
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') closeScenarioMenus();
});

renderScenarioMenus();
applyScenarioChrome();
loadLiveWeather();

const dashboardView = $('dashboardView');
const activityLogView = $('activityLogView');
const messagesView = $('messagesView');
const settingsView = $('settingsView');
const accessView = $('accessView');
const liveMapView = $('liveMapView');
const liveTopLeft = document.querySelector('.live-top-left');

function syncZonePanelWidth() {
  if (!liveMapView || !liveTopLeft) return;
  const width = liveTopLeft.getBoundingClientRect().width;
  if (width > 0) liveMapView.style.setProperty('--zone-panel-width', `${Math.round(width)}px`);
}

/* The tool rail stacks exactly one gutter above the timeline, so it needs the
   timeline's real height rather than a guessed one. The timeline's own offset
   never reads --timeline-h, so this cannot feed back into itself. */
function syncTimelineHeight() {
  if (!liveMapView) return;
  const height = liveMapView.querySelector('.simulation-timeline')?.getBoundingClientRect().height || 0;
  if (height > 0) liveMapView.style.setProperty('--timeline-h', `${Math.round(height)}px`);
}

syncZonePanelWidth();
syncTimelineHeight();
window.addEventListener('resize', syncZonePanelWidth);
window.addEventListener('resize', syncTimelineHeight);
if ('ResizeObserver' in window && liveTopLeft) {
  new ResizeObserver(syncZonePanelWidth).observe(liveTopLeft);
}
if ('ResizeObserver' in window && liveMapView) {
  const timeline = liveMapView.querySelector('.simulation-timeline');
  if (timeline) new ResizeObserver(syncTimelineHeight).observe(timeline);
}

const appShell = document.querySelector('.app-shell');
const appSidebar = document.querySelector('.sidebar');
const appTopbar = document.querySelector('.topbar');
const sidebarToggle = $('sidebarToggle');
const SIDEBAR_KEY = 'sumo.sidebarCollapsed';
let liveMapEnterTimer = 0;
let liveMapInitTimer = 0;
const accessNavGroup = document.querySelector('[data-nav-group="access"]');
const accessNavParent = accessNavGroup?.querySelector('.nav-parent');
const accessSubmenu = $('accessSubnav');
const accessLinks = [...document.querySelectorAll('[data-access-link]')];
const liveNavGroup = document.querySelector('[data-nav-group="live"]');
const liveNavParent = liveNavGroup?.querySelector('.nav-parent');
const liveSubmenu = $('liveSubnav');
const liveLinks = [...document.querySelectorAll('[data-live-tab]')];
const benchmarkNavGroup = document.querySelector('[data-nav-group="benchmark"]');
const benchmarkNavParent = benchmarkNavGroup?.querySelector('.nav-parent');
const benchmarkSubmenu = $('benchmarkSubnav');
const liveModeTabs = [...document.querySelectorAll('[data-live-mode]')];
let activeLiveTab = 'events';
// Remember whether the operator had panels collapsed before Roam auto-collapsed
// them, so leaving Roam restores that choice instead of forcing panels back.
let roamRestoreCollapsed = null;

function isSidebarCollapsed() {
  return document.documentElement.classList.contains('is-sidebar-collapsed');
}

function syncSidebarLabels() {
  document.querySelectorAll('.primary-nav .nav-item, .sidebar-footer .nav-item').forEach((item) => {
    const label = [...item.children].find((child) => child.tagName === 'SPAN')?.textContent.trim();
    if (!label) return;
    item.setAttribute('aria-label', label);
    item.title = label;
  });
}

function setSidebarCollapsed(collapsed, { persist = true } = {}) {
  document.documentElement.classList.toggle('is-sidebar-collapsed', collapsed);
  if (sidebarToggle) {
    const label = collapsed ? 'Expand sidebar' : 'Collapse sidebar';
    sidebarToggle.setAttribute('aria-expanded', String(!collapsed));
    sidebarToggle.setAttribute('aria-label', label);
    sidebarToggle.title = label;
    const copy = sidebarToggle.querySelector('span');
    if (copy) copy.textContent = label;
  }
  syncSidebarLabels();
  if (persist) {
    try {
      localStorage.setItem(SIDEBAR_KEY, String(collapsed));
    } catch {
      // Collapse still applies for the current session.
    }
  }
  [70, 320, 680].forEach((delay) => {
    window.setTimeout(() => {
      map?.resize();
      liveMap?.resize();
    }, delay);
  });
}

sidebarToggle?.addEventListener('click', () => {
  setSidebarCollapsed(!isSidebarCollapsed());
});

setSidebarCollapsed(isSidebarCollapsed(), { persist: false });

const notificationToggle = $('notificationToggle');
const notificationPanel = $('notificationPanel');
const notificationScrim = $('notificationScrim');
const notificationClose = $('notificationClose');
const notificationViewAll = $('notificationViewAll');
const notificationEarlier = $('notificationEarlier');
const notificationCount = $('notificationCount');
const notificationBadge = $('notificationBadge');
const notificationItems = [...document.querySelectorAll('[data-notification]')];

function setNotificationPanelOpen(open) {
  if (!notificationPanel || !notificationToggle) return;
  notificationPanel.hidden = !open;
  if (notificationScrim) notificationScrim.hidden = !open;
  notificationToggle.setAttribute('aria-expanded', String(open));
  if (open) {
    closeAccountMenu();
    closeScenarioMenus();
  }
}

function closeNotificationPanel() {
  setNotificationPanelOpen(false);
}

function updateNotificationCount() {
  const unread = notificationItems.filter((item) => item.classList.contains('is-unread')).length;
  if (notificationCount) {
    notificationCount.textContent = unread ? `(${unread})` : '';
    notificationCount.hidden = unread === 0;
  }
  if (notificationBadge) notificationBadge.hidden = unread === 0;
}

notificationToggle?.addEventListener('click', (event) => {
  event.stopPropagation();
  setNotificationPanelOpen(notificationPanel?.hidden ?? false);
});

notificationClose?.addEventListener('click', () => {
  closeNotificationPanel();
  notificationToggle?.focus();
});

notificationViewAll?.addEventListener('click', () => {
  if (!notificationEarlier) return;
  const showAll = notificationEarlier.hidden;
  notificationEarlier.hidden = !showAll;
  notificationViewAll.textContent = showAll ? 'Show less' : 'View all';
  notificationViewAll.setAttribute('aria-expanded', String(showAll));
});

notificationItems.forEach((item) => {
  item.addEventListener('click', () => {
    if (!item.classList.contains('is-unread')) return;
    item.classList.remove('is-unread');
    updateNotificationCount();
    showToast('Notification marked as read.');
  });
});

document.addEventListener('click', (event) => {
  if (notificationPanel?.hidden) return;
  if (!event.target.closest('.notification-wrap')) closeNotificationPanel();
});

document.addEventListener('keydown', (event) => {
  if (event.key !== 'Escape' || notificationPanel?.hidden) return;
  closeNotificationPanel();
  notificationToggle?.focus();
});

updateNotificationCount();

const account = $('account');
const accountToggle = $('accountToggle');
const accountMenu = $('accountMenu');
const accountMenuItems = [...document.querySelectorAll('[data-account-action]')];

function setAccountMenuOpen(open) {
  if (!accountMenu || !accountToggle) return;
  accountMenu.hidden = !open;
  accountToggle.setAttribute('aria-expanded', String(open));
  account?.classList.toggle('is-open', open);
  if (open) {
    closeNotificationPanel();
    closeScenarioMenus();
  }
}

function closeAccountMenu() {
  setAccountMenuOpen(false);
}

function openSettingsTab(tabName = 'general') {
  setActiveNav('Settings');
  setActiveViewTab('Settings');
  showView('Settings');
  document.querySelector(`[data-settings-tab="${tabName}"]`)?.click();
}

accountToggle?.addEventListener('click', (event) => {
  event.stopPropagation();
  setAccountMenuOpen(accountMenu?.hidden ?? false);
});

accountMenuItems.forEach((item) => {
  item.addEventListener('click', () => {
    const action = item.dataset.accountAction;
    closeAccountMenu();
    accountToggle?.focus();

    if (action === 'account' || action === 'settings') {
      openSettingsTab('general');
      return;
    }
    if (action === 'pricing') {
      showToast('Pricing is managed by your workspace administrator.');
      return;
    }
    if (action === 'faq') {
      showToast('Opening the SUMO help center.');
      return;
    }
    if (action === 'signout') {
      showToast('Signed out of SUMO.');
    }
  });
});

document.addEventListener('click', (event) => {
  if (accountMenu?.hidden) return;
  if (!event.target.closest('.account')) closeAccountMenu();
});

document.addEventListener('keydown', (event) => {
  if (event.key !== 'Escape' || accountMenu?.hidden) return;
  closeAccountMenu();
  accountToggle?.focus();
});

const ROUTE_BASES = {
  'Live Map': '/live-map',
  'Roles & Permissions': '/access',
  Benchmark: '/benchmark',
  Dashboard: '/',
  Message: '/messages',
  Settings: '/settings',
  'Activity log': '/activity-log',
};
const BENCHMARK_TABS = ['training', 'models', 'runs', 'compare', 'simulation'];
const LIVE_TABS = ['events', 'optimize', 'predict', 'roam'];
const ACCESS_TABS = ['roles', 'permissions'];
const SETTINGS_TABS = ['general', 'notifications', 'workspace', 'integrations', 'members', 'security', 'billing'];

function routeFor(view, subtab) {
  const base = ROUTE_BASES[view] || '/';
  if (view === 'Benchmark' && BENCHMARK_TABS.includes(subtab)) return `${base}/${subtab}`;
  if (view === 'Live Map' && LIVE_TABS.includes(subtab)) return `${base}/${subtab}`;
  if (view === 'Roles & Permissions' && ACCESS_TABS.includes(subtab)) return `${base}/${subtab}`;
  if (view === 'Settings' && SETTINGS_TABS.includes(subtab)) return `${base}/${subtab}`;
  return base;
}

function setRoute(view, subtab, { replace = false } = {}) {
  const path = routeFor(view, subtab);
  const url = new URL(window.location.href);
  url.pathname = path;
  url.searchParams.delete('view');
  url.searchParams.delete('tab');
  // compareRuns is intentional state shared between Runs and Compare; keep it while routing.
  if (replace) window.history.replaceState({ view, subtab }, '', url);
  else window.history.pushState({ view, subtab }, '', url);
}

function routeFromLocation() {
  const parts = window.location.pathname.split('/').filter(Boolean);
  const [section, subtab] = parts;
  if (section === 'benchmark') return { view: 'Benchmark', subtab: BENCHMARK_TABS.includes(subtab) ? subtab : 'runs' };
  if (section === 'live-map') return { view: 'Live Map', subtab: LIVE_TABS.includes(subtab) ? subtab : 'events' };
  if (section === 'access') return { view: 'Roles & Permissions', subtab: ACCESS_TABS.includes(subtab) ? subtab : 'roles' };
  if (section === 'messages') return { view: 'Message', subtab: null };
  if (section === 'settings') return { view: 'Settings', subtab: SETTINGS_TABS.includes(subtab) ? subtab : 'general' };
  if (section === 'activity-log') return { view: 'Activity log', subtab: null };
  if (section === 'dashboard' || parts.length === 0) return { view: 'Dashboard', subtab: null };
  return null;
}

function navigateTo(view, subtab, { replace = false } = {}) {
  if (view === 'Live Map') {
    activeLiveTab = LIVE_TABS.includes(subtab) ? subtab : 'events';
    setRoute(view, activeLiveTab, { replace });
    setActiveNav(view);
    setActiveViewTab('Dashboard');
    showView(view);
    setLiveSubnavActive(activeLiveTab);
    liveMapView?.classList.toggle('live-roam-mode', activeLiveTab === 'roam');
    if (activeLiveTab === 'roam') {
      if (roamRestoreCollapsed === null) roamRestoreCollapsed = liveMapView?.classList.contains('live-panels-collapsed') ? 1 : 0;
      liveMapView?.classList.add('live-panels-collapsed');
    } else if (roamRestoreCollapsed !== null) {
      liveMapView?.classList.toggle('live-panels-collapsed', roamRestoreCollapsed === 1);
      roamRestoreCollapsed = null;
    }
    document.dispatchEvent(new CustomEvent('sumo:livetabchange', { detail: { tab: activeLiveTab } }));
    return;
  }
  if (view === 'Settings') {
    const settingsTab = SETTINGS_TABS.includes(subtab) ? subtab : 'general';
    setRoute(view, settingsTab, { replace });
    setActiveNav('Settings');
    setActiveViewTab('Settings');
    showView(view);
    setSettingsTab(settingsTab, false);
    return;
  }
  if (view === 'Roles & Permissions') {
    setRoute(view, ACCESS_TABS.includes(subtab) ? subtab : 'roles', { replace });
    setActiveNav(view);
    setActiveViewTab('Dashboard');
    showView(view);
    setAccessTab(ACCESS_TABS.includes(subtab) ? subtab : 'roles', false);
    return;
  }
  if (view === 'Benchmark') {
    benchmarkTab = BENCHMARK_TABS.includes(subtab) ? subtab : 'runs';
    setRoute(view, benchmarkTab, { replace });
    setActiveNav(view);
    setActiveViewTab('Dashboard');
    showView(view);
    setBenchmarkNavOpen(true);
    setBenchmarkTab(benchmarkTab);
    document.querySelectorAll('#benchmarkSubnav [data-benchmark-tab]').forEach((item) => item.classList.toggle('is-active', item.dataset.benchmarkTab === benchmarkTab));
    return;
  }
  setRoute(view, null, { replace });
  setActiveNav(view === 'Settings' ? 'Settings' : view);
  setActiveViewTab(view === 'Settings' ? 'Settings' : 'Dashboard');
  showView(view);
}

function setLiveSubnavActive(tabName) {
  liveLinks.forEach((link) => {
    const active = link.dataset.liveTab === tabName;
    link.classList.toggle('is-active', active);
    if (active) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
  liveModeTabs.forEach((tab) => {
    const active = tab.dataset.liveMode === tabName;
    tab.classList.toggle('is-active', active);
    tab.setAttribute('aria-selected', String(active));
  });
  if (liveMapView) liveMapView.dataset.liveTab = tabName || '';
}

function selectLiveTab(tabName) {
  navigateTo('Live Map', tabName || 'events');
}

function setLiveNavOpen(open) {
  if (!liveNavGroup || !liveNavParent || !liveSubmenu) return;
  liveNavGroup.classList.toggle('is-open', open);
  liveSubmenu.classList.toggle('is-open', open);
  liveSubmenu.setAttribute('aria-hidden', String(!open));
  liveNavParent.setAttribute('aria-expanded', String(open));
}

function setAccessSubnavActive(tabName) {
  accessLinks.forEach((link) => {
    const active = link.dataset.accessLink === tabName;
    link.classList.toggle('is-active', active);
    if (active) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
}

function setAccessNavOpen(open) {
  if (!accessNavGroup || !accessNavParent || !accessSubmenu) return;
  accessNavGroup.classList.toggle('is-open', open);
  accessSubmenu.classList.toggle('is-open', open);
  accessSubmenu.setAttribute('aria-hidden', String(!open));
  accessNavParent.setAttribute('aria-expanded', String(open));
}

function setBenchmarkNavOpen(open) {
  if (!benchmarkNavGroup || !benchmarkNavParent || !benchmarkSubmenu) return;
  benchmarkNavGroup.classList.toggle('is-open', open);
  benchmarkSubmenu.classList.toggle('is-open', open);
  benchmarkSubmenu.setAttribute('aria-hidden', String(!open));
  benchmarkNavParent.setAttribute('aria-expanded', String(open));
}

function resizeLiveMapThroughTransition() {
  [0, 70, 140, 220, 320, 440, 580, 720].forEach((delay) => {
    window.setTimeout(() => liveMap?.resize(), delay);
  });
}

function setLiveMapMode(active) {
  appShell?.classList.toggle('is-live-map', active);
  if (active) {
    closeNotificationPanel();
    closeAccountMenu();
  }
  if (appSidebar) appSidebar.inert = active;
  if (appTopbar) appTopbar.inert = active;
  if (!liveMapView) return;

  window.clearTimeout(liveMapEnterTimer);
  liveMapView.classList.remove('is-entering');

  if (!active) {
    window.clearTimeout(liveMapInitTimer);
    return;
  }
  void liveMapView.offsetWidth;
  liveMapView.classList.add('is-entering');
  liveMapEnterTimer = window.setTimeout(() => liveMapView.classList.remove('is-entering'), 1300);
  resizeLiveMapThroughTransition();
}

let liveMapPollTimer = null;
function startLiveMapSimulationPolling() {
  if (liveMapPollTimer) return;
  connectSimulationSocket();
  const poll = async () => {
    try {
      const res = await simulationFetch('/api/simulation/state');
      if (res.ok) {
        const state = await res.json();
        if (state && state.status === 'idle') {
          // If simulation is not running yet, automatically start it on the active scenario
          const scenario = simulationScenarioId();
          await simulationFetch('/api/simulation/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ scenario, speed: simulationSpeed || 1 })
          });
        } else if (state) {
          updateSimulationState(state);
        }
      }
    } catch {}
  };
  poll();
  liveMapPollTimer = setInterval(poll, 1000);
}

function stopLiveMapSimulationPolling() {
  if (liveMapPollTimer) {
    clearInterval(liveMapPollTimer);
    liveMapPollTimer = null;
  }
}

function ensureLiveMap() {
  startLiveMapSimulationPolling();

  if (liveMap) {
    liveMap.resize();
    return;
  }
  window.clearTimeout(liveMapInitTimer);
  liveMapInitTimer = window.setTimeout(() => {
    initLiveMap();
    window.setTimeout(() => liveMap?.resize(), 90);
  }, 460);
}

function showView(name) {
  const isMessages = name === 'Message';
  const isBenchmark = name === 'Benchmark';
  const isSettings = name === 'Settings';
  const isAccess = name === 'Roles & Permissions';
  const isLiveMap = name === 'Live Map';
  const isActivityLog = name === 'Activity log';
  if (dashboardView) dashboardView.hidden = isMessages || isSettings || isAccess || isLiveMap || isActivityLog || isBenchmark;
  if (messagesView) messagesView.hidden = !isMessages;
  if (settingsView) settingsView.hidden = !isSettings;
  if (accessView) accessView.hidden = !isAccess;
  if (liveMapView) liveMapView.hidden = !isLiveMap;
  if (activityLogView) activityLogView.hidden = !isActivityLog;
  const benchmarkView = $('benchmarkView');
  if (benchmarkView) benchmarkView.hidden = !isBenchmark;
  if (isBenchmark && !benchmarkMounted && benchmarkView) { benchmarkView.replaceChildren(); const mountPoint = document.createElement('div'); mountPoint.className = 'benchmark-react-shell'; benchmarkView.appendChild(mountPoint); mountBenchmarkView(mountPoint, benchmarkTab); benchmarkMounted = true; }
  setLiveMapMode(isLiveMap);
  if (isLiveMap) {
    ensureLiveMap();
    return;
  }
  if (isMessages || isSettings || isAccess || isActivityLog || isBenchmark) {
    if (isMessages) renderChatList();
    if (isSettings) settingsView?.scrollTo({ top: 0 });
    if (isAccess) accessView?.scrollTo({ top: 0 });
    if (isActivityLog) {
      renderActivityLog();
      activityLogView?.scrollTo({ top: 0 });
    }
    return;
  }
  window.setTimeout(() => {
    if (map) map.resize();
  }, 60);
}

document.querySelectorAll('[data-benchmark-tab]').forEach((tab) => tab.addEventListener('click', () => {
  document.querySelectorAll('[data-benchmark-tab]').forEach((item) => item.classList.toggle('is-active', item === tab));
  benchmarkTab = tab.dataset.benchmarkTab || 'runs';
  setBenchmarkTab(benchmarkTab);
}));

window.addEventListener('benchmark:navigate', (event) => {
  const tab = event.detail;
  if (!BENCHMARK_TABS.includes(tab)) return;
  navigateTo('Benchmark', tab);
});

const ACTIVITY_LOG = [
  {
    date: '2026-10-22',
    time: '10:15 AM',
    type: 'incident',
    icon: 'i-warning',
    title: 'Incident <strong>INC-2041</strong> was assigned to <b>Maya Chen</b>.',
    tags: [['Incident', 'is-warning'], ['Priority high', ''], ['In progress', 'is-accent']],
    details: [['Source', 'Live Map'], ['Actor', 'Control Room'], ['Event ID', 'EVT-90421']]
  },
  {
    date: '2026-10-22',
    time: '09:42 AM',
    type: 'signal',
    icon: 'i-signal',
    title: 'Adaptive signal plan <strong>SP-118</strong> applied to the <b>East 7th corridor</b>.',
    tags: [['Signal', 'is-success'], ['Adaptive', ''], ['Applied', 'is-success']],
    details: [['Source', 'Signal Engine'], ['Actor', 'A. Rivera'], ['Plan', 'SP-118']]
  },
  {
    date: '2026-10-22',
    time: '08:57 AM',
    type: 'system',
    icon: 'i-activity',
    title: '<b>V2X broadcast</b> switched to <strong>FLASH mode</strong> at 3 intersections.',
    tags: [['System', ''], ['Safety', 'is-info'], ['Logged', '']],
    details: [['Source', 'V2X Gateway'], ['Actor', 'System'], ['Event ID', 'EVT-90398']]
  },
  {
    date: '2026-10-21',
    time: '04:31 PM',
    type: 'access',
    icon: 'i-user-check',
    title: '<b>Omar Haddad</b> was added to the <strong>Dispatch Lead</strong> role.',
    tags: [['Access', 'is-info'], ['Role change', ''], ['Approved', 'is-success']],
    details: [['Source', 'Workspace'], ['Actor', 'Jane Cooper'], ['Role', 'Dispatch Lead']]
  },
  {
    date: '2026-10-21',
    time: '02:08 PM',
    type: 'field',
    icon: 'i-car',
    title: 'Queue backlog at <strong>Congress Ave</strong> cleared after field response.',
    tags: [['Field', ''], ['Resolved', 'is-success'], ['12 min', '']],
    details: [['Source', 'Field Unit 06'], ['Actor', 'L. Bennett'], ['Event ID', 'EVT-90354']]
  },
  {
    date: '2026-10-20',
    time: '11:26 AM',
    type: 'system',
    icon: 'i-activity',
    title: 'Camera feed <strong>CAM-04</strong> restored after scheduled maintenance.',
    tags: [['System', ''], ['Camera', ''], ['Online', 'is-success']],
    details: [['Source', 'Camera Network'], ['Actor', 'System'], ['Device', 'CAM-04']]
  },
  {
    date: '2026-10-20',
    time: '09:05 AM',
    type: 'signal',
    icon: 'i-signal',
    title: 'Emergency green corridor activated for <strong>Engine 12</strong>.',
    tags: [['Signal', 'is-success'], ['Emergency', 'is-warning'], ['Completed', 'is-success']],
    details: [['Source', 'Live Map'], ['Actor', 'M. Chen'], ['Route', 'East 7th → 5th']]
  },
  {
    date: '2026-10-19',
    time: '05:48 PM',
    type: 'access',
    icon: 'i-user-check',
    title: 'Permission matrix updated for <strong>4 workspace members</strong>.',
    tags: [['Access', 'is-info'], ['Permissions', ''], ['Updated', '']],
    details: [['Source', 'Roles & Permissions'], ['Actor', 'Jane Cooper'], ['Scope', '4 members']]
  }
];

const activityTimeline = $('activityTimeline');
const activitySearch = $('activitySearch');
const activityFrom = $('activityFrom');
const activityTo = $('activityTo');
const activityResultCount = $('activityResultCount');
const activityEmpty = $('activityEmpty');
const activityFilterButtons = [...document.querySelectorAll('[data-activity-filter]')];
let activeActivityFilter = 'all';

function formatActivityDate(isoDate) {
  const [year, month, day] = isoDate.split('-');
  return `${day}.${month}.${year}`;
}

function activityEventMarkup(event) {
  const tags = event.tags
    .map(([label, tone]) => `<span class="activity-tag ${tone}">${label}</span>`)
    .join('');
  const details = event.details
    .map(([label, value]) => `<span><small>${label}</small><b>${value}</b></span>`)
    .join('');

  return `
    <article class="activity-event" data-activity-type="${event.type}" data-activity-date="${event.date}">
      <span class="activity-marker is-${event.type}"><svg class="ico"><use href="#${event.icon}"/></svg></span>
      <div class="activity-event-body">
        <div class="activity-event-main">
          <div class="activity-event-copy">
            <p>${event.title}</p>
            <time datetime="${event.date}">${formatActivityDate(event.date)} · ${event.time} CST</time>
          </div>
          <button type="button" class="activity-expand" aria-label="Show event details" aria-expanded="false"><svg class="ico"><use href="#i-chevron"/></svg></button>
        </div>
        <div class="activity-tags">${tags}</div>
        <div class="activity-event-detail" hidden>${details}</div>
      </div>
    </article>`;
}

function renderActivityLog() {
  if (!activityTimeline || activityTimeline.childElementCount) return;

  const groups = new Map();
  ACTIVITY_LOG.forEach((event) => {
    if (!groups.has(event.date)) groups.set(event.date, []);
    groups.get(event.date).push(event);
  });

  activityTimeline.innerHTML = [...groups.entries()]
    .map(([date, events]) => `
      <section class="activity-day">
        <div class="activity-day-label">${formatActivityDate(date)}</div>
        <div class="activity-events">${events.map(activityEventMarkup).join('')}</div>
      </section>`)
    .join('');

  applyActivityFilters();
}

function applyActivityFilters() {
  if (!activityTimeline) return;

  const query = (activitySearch?.value || '').trim().toLowerCase();
  const from = activityFrom?.value || '';
  const to = activityTo?.value || '';
  let visible = 0;

  activityTimeline.querySelectorAll('.activity-event').forEach((event) => {
    const matchesType = activeActivityFilter === 'all' || event.dataset.activityType === activeActivityFilter;
    const matchesSearch = !query || event.textContent.toLowerCase().includes(query);
    const date = event.dataset.activityDate;
    const matchesDate = (!from || date >= from) && (!to || date <= to);
    const show = matchesType && matchesSearch && matchesDate;
    event.hidden = !show;
    if (show) visible += 1;
  });

  activityTimeline.querySelectorAll('.activity-day').forEach((day) => {
    day.hidden = ![...day.querySelectorAll('.activity-event')].some((event) => !event.hidden);
  });

  if (activityEmpty) activityEmpty.hidden = visible > 0;
  if (activityResultCount) activityResultCount.textContent = `${visible} result${visible === 1 ? '' : 's'}`;
}

activitySearch?.addEventListener('input', applyActivityFilters);
activityFrom?.addEventListener('change', applyActivityFilters);
activityTo?.addEventListener('change', applyActivityFilters);

activityFilterButtons.forEach((button) => {
  button.setAttribute('aria-pressed', String(button.classList.contains('is-active')));
  button.addEventListener('click', () => {
    activeActivityFilter = button.dataset.activityFilter;
    activityFilterButtons.forEach((item) => {
      const active = item === button;
      item.classList.toggle('is-active', active);
      item.setAttribute('aria-pressed', String(active));
    });
    applyActivityFilters();
  });
});

activityTimeline?.addEventListener('click', (event) => {
  const toggle = event.target.closest('.activity-expand');
  if (!toggle) return;
  const item = toggle.closest('.activity-event');
  const detail = item?.querySelector('.activity-event-detail');
  if (!detail) return;
  const expanded = toggle.getAttribute('aria-expanded') === 'true';
  toggle.setAttribute('aria-expanded', String(!expanded));
  toggle.setAttribute('aria-label', expanded ? 'Show event details' : 'Hide event details');
  detail.hidden = expanded;
});

function setActiveNav(name) {
  document.querySelectorAll('.primary-nav .nav-item').forEach((node) => {
    node.classList.toggle('is-active', node.dataset.nav === name);
  });
  if (name === 'Roles & Permissions') {
    setAccessNavOpen(true);
    setLiveNavOpen(false);
    setAccessSubnavActive(document.querySelector('[data-access-tab].is-active')?.dataset.accessTab || 'roles');
  } else {
    setAccessNavOpen(false);
  }
  if (name === 'Live Map') {
    setLiveNavOpen(true);
    setAccessNavOpen(false);
    setLiveSubnavActive(activeLiveTab);
  } else {
    setLiveNavOpen(false);
  }
}

function setActiveViewTab(name) {
  document.querySelectorAll('.view-tab').forEach((node) => {
    node.classList.toggle('is-active', node.dataset.view === name);
  });
}

document.querySelectorAll('.primary-nav .nav-item').forEach((item) => {
  if (item.classList.contains('nav-parent')) return;
  item.addEventListener('click', () => navigateTo(item.dataset.nav || 'Dashboard'));
});

accessNavParent?.addEventListener('click', () => {
  const wasHidden = Boolean(accessView?.hidden);
  if (wasHidden || isSidebarCollapsed()) {
    const currentTab = document.querySelector('[data-access-tab].is-active')?.dataset.accessTab;
    setActiveNav('Roles & Permissions');
    setActiveViewTab('Dashboard');
    showView('Roles & Permissions');
    setAccessTab(wasHidden ? 'roles' : (currentTab || 'roles'));
    return;
  }
  setAccessNavOpen(!accessNavGroup?.classList.contains('is-open'));
});

accessLinks.forEach((link) => {
  link.addEventListener('click', () => navigateTo('Roles & Permissions', link.dataset.accessLink));
});

liveNavParent?.addEventListener('click', () => {
  if (window.matchMedia('(max-width: 760px)').matches || isSidebarCollapsed()) {
    selectLiveTab(activeLiveTab || 'events');
    return;
  }
  const willOpen = !liveNavGroup?.classList.contains('is-open');
  setAccessNavOpen(false);
  setLiveNavOpen(willOpen);
});

benchmarkNavParent?.addEventListener('click', () => {
  const willOpen = !benchmarkNavGroup?.classList.contains('is-open');
  setAccessNavOpen(false); setLiveNavOpen(false); setBenchmarkNavOpen(willOpen);
  setActiveNav('Benchmark'); setActiveViewTab('Dashboard'); showView('Benchmark');
});

document.querySelectorAll('#benchmarkSubnav [data-benchmark-tab]').forEach((link) => {
  link.addEventListener('click', () => navigateTo('Benchmark', link.dataset.benchmarkTab || 'runs'));
});

document.addEventListener('sumo:open-training', () => {
  setBenchmarkNavOpen(true);
  document.querySelector('#benchmarkSubnav [data-benchmark-tab="training"]')?.click();
});

liveLinks.forEach((link) => {
  link.addEventListener('click', () => selectLiveTab(link.dataset.liveTab || ''));
});

liveModeTabs.forEach((tab) => {
  tab.addEventListener('click', () => selectLiveTab(tab.dataset.liveMode || ''));
});

document.querySelectorAll('.view-tab').forEach((tab) => {
  tab.addEventListener('click', () => navigateTo(tab.dataset.view || 'Dashboard'));
});

function exitLiveMap() {
  if (document.fullscreenElement) document.exitFullscreen?.().catch(() => {});
  navigateTo('Dashboard');
}

document.querySelectorAll('[data-live-exit]').forEach((button) => {
  button.addEventListener('click', exitLiveMap);
});

document.addEventListener('keydown', (event) => {
  if (event.key !== 'Escape' || !liveMapView || liveMapView.hidden || document.fullscreenElement) return;
  exitLiveMap();
});

$('resetChange')?.addEventListener('click', () => {
  document.querySelectorAll('.chart-card').forEach((card) => {
    card.classList.remove('is-reset');
    void card.offsetWidth;
    card.classList.add('is-reset');
    setTimeout(() => card.classList.remove('is-reset'), 700);
  });
});

$('tokenSave')?.addEventListener('click', () => {
  const value = $('tokenInput').value.trim();
  if (!value) {
    $('tokenInput').focus();
    return;
  }
  localStorage.setItem(TOKEN_KEY, value);
  hideTokenPanel();
  buildMap(value);
});

$('tokenSkip')?.addEventListener('click', () => {
  hideTokenPanel();
  setOffline(true);
});

const token = resolveToken();
if (token) {
  buildMap(token);
} else {
  showTokenPanel();
  setOffline(true);
}

// ---------------- Live 3D map ----------------

const LIVE_FOCUS = [-97.7325, 30.2663];
const LIVE_VIEW = { center: LIVE_FOCUS, zoom: 16.05, pitch: 58, bearing: -26 };
let liveMap3dOn = true;
let liveSceneMarkers = [];
const LIVE_ROUTE_OVERLAYS_ENABLED = false;
const LIVE_FOG_ENABLED = false;
const LIVE_SCENE_MARKERS_ENABLED = false;

const simulationClock = $('simulationClock');
const simulationStatus = $('simulationStatus');
const simulationMetrics = $('simulationMetrics');
const simulationTime = $('simulationTime');
const simulationTimeline = $('simulationTimeline');
const simulationTrack = $('simulationTrack');
const simulationProfile = $('simulationProfile');
const simulationBubble = $('simulationBubble');
const simulationHoverLabel = $('simulationHoverLabel');
const simulationStatusText = $('simulationStatusText');
const simulationPlayButton = $('simulationPlay');

/* Shape of a normal weekday in the corridor: a morning ramp, a midday dip and
   an evening peak. Drawn behind the scrub track so the day's rhythm is visible
   while dragging the playhead. */
/* The corridor's demand across the operating day, which starts at 08:00: the
   school/work ramp, the midday plateau, the evening peak and the overnight trough.
   One bar per clock hour, from 08:00 back round to 08:00. */
const SIMULATION_DAY_PROFILE = [
  62, 78, 86, 90, 94, 92, 88, 86, 90, 96, 100, 96,
  84, 70, 56, 44, 32, 24, 18, 14, 12, 16, 30, 46
];
const DAY_START_SECONDS = 8 * 3600;

/* The hourly samples are smoothed into one continuous silhouette: a soft filled
   area with a hairline top, so the peaks read as demand rather than as a row of
   blocks sitting inside the scrub track. */
function buildSimulationProfile() {
  if (!simulationProfile || simulationProfile.childElementCount) return;
  const points = SIMULATION_DAY_PROFILE;
  const step = 100 / (points.length - 1);
  const coords = points.map((height, index) => [index * step, 100 - height]);
  let path = `M 0 100 L ${coords[0][0].toFixed(2)} ${coords[0][1].toFixed(2)}`;
  for (let index = 0; index < coords.length - 1; index += 1) {
    const p0 = coords[index - 1] || coords[index];
    const p1 = coords[index];
    const p2 = coords[index + 1];
    const p3 = coords[index + 2] || p2;
    const c1x = p1[0] + (p2[0] - p0[0]) / 6;
    const c1y = p1[1] + (p2[1] - p0[1]) / 6;
    const c2x = p2[0] - (p3[0] - p1[0]) / 6;
    const c2y = p2[1] - (p3[1] - p1[1]) / 6;
    path += ` C ${c1x.toFixed(2)} ${c1y.toFixed(2)}, ${c2x.toFixed(2)} ${c2y.toFixed(2)}, ${p2[0].toFixed(2)} ${p2[1].toFixed(2)}`;
  }
  simulationProfile.innerHTML = `
    <svg class="sim-profile-svg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true" focusable="false">
      <path class="sim-profile-area" d="${path} L 100 100 Z" />
      <path class="sim-profile-line" d="${path}" />
    </svg>`;
}

function formatSimulationTime(seconds) {
  // The track is one operating day: 0 s is 08:00, 24 h later is 08:00 again.
  const value = ((Math.max(0, Math.min(86400, Number(seconds) || 0)) + DAY_START_SECONDS) % 86400);
  const hours = String(Math.floor(value / 3600)).padStart(2, '0');
  const minutes = String(Math.floor((value % 3600) / 60)).padStart(2, '0');
  return `${hours}:${minutes}`;
}

/* Drives the whole ribbon: the wash behind the bars, the playhead knob, the
   bubble that rides it and the input's spoken value. */
function paintSimulationTimeline(seconds) {
  if (!simulationTime) return;
  const value = Math.max(0, Math.min(86400, Number(seconds) || 0));
  const label = formatSimulationTime(value);
  simulationTimeline?.style.setProperty('--timeline-progress', `${(value / 86400) * 100}%`);
  if (simulationBubble) simulationBubble.textContent = label;
  simulationTime.setAttribute('aria-valuetext', label);
}

function setSimulationStatus(status) {
  const key = String(status || 'idle').toLowerCase();
  if (simulationStatus) simulationStatus.dataset.state = key;
  if (simulationStatusText) simulationStatusText.textContent = key.charAt(0).toUpperCase() + key.slice(1);
  const playing = key === 'running' || key === 'starting';
  simulationPlayButton?.classList.toggle('is-playing', playing);
  simulationPlayButton?.setAttribute('aria-label', playing ? 'Pause simulation' : 'Play simulation');
}

buildSimulationProfile();
paintSimulationTimeline(simulationTime?.value || 0);

/* Hover read-out: a dashed guide and the time under the pointer. */
simulationTrack?.addEventListener('pointermove', (event) => {
  if (event.pointerType && event.pointerType !== 'mouse') return;
  const rect = simulationTrack.getBoundingClientRect();
  if (!rect.width) return;
  const ratio = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
  simulationTrack.style.setProperty('--hover-progress', `${(ratio * 100).toFixed(3)}%`);
  simulationTrack.classList.add('is-hovering');
  if (simulationHoverLabel) simulationHoverLabel.textContent = formatSimulationTime(ratio * 86400);
});
simulationTrack?.addEventListener('pointerleave', () => simulationTrack.classList.remove('is-hovering'));
simulationTrack?.addEventListener('pointerdown', () => simulationTrack.classList.remove('is-hovering'));

let simulationSocket = null;
let simulationSpeed = 1;
let simulationScrubUntil = 0;
let latestSimulationState = null;
let previousVehicleFrame = null;
let currentVehicleFrame = null;
let vehicleFrameTime = 0;
// Measured gap between two *distinct* simulation steps, not an assumed 1 s.
let vehicleFrameInterval = 1000;
let currentFrameKey = '';
let vehicleAnimationFrame = 0;
let simulationSignalFeatures = [];
// Lane id → lane polyline for the running network, used to keep moving bodies on the road.
let simulationLaneShapes = new Map();
const simulationSignalMarkers = new Map();
const API_BASE = `${window.location.protocol}//${window.location.hostname}:8000`;
const SIMULATION_BOUNDS = {
  'grid-2x2': { west: -122.4109, east: -122.4072, south: 37.778, north: 37.781, width: 330, height: 340 },
  'grid-3x3': { west: -122.4132, east: -122.4056, south: 37.775, north: 37.781, width: 700, height: 660 }
};

function simulationFetch(path, options) {
  return fetch(`${API_BASE}${path}`, options);
}

/* SUMO x/y → lng/lat, only for the networks whose net-local extent we know. The
   backend sends lng/lat for every vehicle and signal lane; this fallback used to
   land anything missing them in San Francisco on *every other* network. Returning
   null lets the caller skip the object instead of drawing it in the wrong city. */
function simulationPoint(scenario, x, y) {
  const bounds = SIMULATION_BOUNDS[scenario];
  if (!bounds) return null;
  return [
    bounds.west + (Number(x) / bounds.width) * (bounds.east - bounds.west),
    bounds.south + (Number(y) / bounds.height) * (bounds.north - bounds.south)
  ];
}

function refreshSimulationSignals(state) {
  if (!liveMap) return;
  // Frames from the previous run keep arriving for a moment after a switch; their
  // signal ids belong to another network, so they must not repaint these markers.
  if (state?.scenario && state.scenario !== activeScenario) return;
  const active = new Map((state?.signals || []).map((signal) => [signal.id, signal.state || '']));
  simulationSignalFeatures.forEach((signal) => {
    const stateString = active.get(signal.signalId) || '';
    const signalState = (signal.linkIndices || []).map((index) => stateString[index]).find((value) => value === 'G' || value === 'g')
      || (signal.linkIndices || []).map((index) => stateString[index]).find((value) => value === 'y' || value === 'Y')
      || 'r';
    const marker = simulationSignalMarkers.get(signal.key);
    if (!marker) return;
    marker.querySelectorAll('[data-lamp]').forEach((lamp) => {
      const lit = lamp.dataset.lamp === lampForSignalState(signalState);
      lamp.classList.toggle('is-lit', lit);
    });
    marker.title = `Traffic light · ${signalState === 'G' || signalState === 'g' ? 'Green' : signalState === 'y' || signalState === 'Y' ? 'Yellow' : 'Red'}`;
  });
}

function lampForSignalState(state) {
  if (state === 'G' || state === 'g') return 'green';
  if (state === 'y' || state === 'Y') return 'yellow';
  return 'red';
}

function setSimulationSignalMarkers(signals) {
  simulationSignalMarkers.forEach((marker) => marker.remove());
  simulationSignalMarkers.clear();
  simulationSignalFeatures = signals;
  if (!liveMap) return;
  signals.forEach((signal) => {
    const root = document.createElement('div');
    root.className = 'sumo-signal-marker';
    root.setAttribute('role', 'img');
    root.setAttribute('aria-label', 'Traffic light');
    root.innerHTML = '<span class="sumo-signal-housing"><i data-lamp="red"></i><i data-lamp="yellow"></i><i data-lamp="green"></i></span>';
    simulationSignalMarkers.set(signal.key, root);
    new mapboxgl.Marker({ element: root, anchor: 'center' })
      .setLngLat(signal.coordinates)
      .addTo(liveMap);
  });
  refreshSimulationSignals(latestSimulationState);
}

const VEHICLE_RENDER = {
  passenger: { label: 'Car', color: '#5b8fb0', length: 4.5, width: 1.9, height: 1.55 },
  taxi: { label: 'Taxi', color: '#d9a12b', length: 4.5, width: 1.9, height: 1.6 },
  // Buses are the long yellow bars: ~2.5 car lengths, full height.
  bus: { label: 'Bus', color: '#f2c200', length: 12.0, width: 2.55, height: 3.25 },
  truck: { label: 'Truck', color: '#8b9299', length: 7.2, width: 2.45, height: 3.0 },
  // Base colour only; the layer paints ambulances red/blue alternately.
  emergency: { label: 'Ambulance', color: '#ed2939', length: 5.4, width: 2.1, height: 2.15 },
  bicycle: { label: 'Bicycle', color: '#ee9f37', length: 1.9, width: 0.65, height: 1.25 },
  motorcycle: { label: 'Motorcycle', color: '#525963', length: 2.2, width: 0.8, height: 1.35 },
  pedestrian: { label: 'Pedestrian', color: '#8464d8', length: 0.65, width: 0.65, height: 1.7 },
};

function vehicleRenderClass(vehicle) {
  const source = `${vehicle.vehicleClass || ''} ${vehicle.type || ''}`.toLowerCase();
  if (/emergency|ambulance|fire|police/.test(source)) return 'emergency';
  if (/bus|coach/.test(source)) return 'bus';
  if (/taxi/.test(source)) return 'taxi';
  if (/truck|delivery|trailer/.test(source)) return 'truck';
  if (/bicycle|bike/.test(source)) return 'bicycle';
  if (/motorcycle|moped/.test(source)) return 'motorcycle';
  return 'passenger';
}

// Bodies are drawn at close to their real footprint. They used to be scaled 1.9× so a
// 4.5 m car stayed readable, but a queued car then covered 8.5 m — twice the gap between
// stopped vehicles — and a line of them fused into one long rectangle that read as a bus.
// Slightly over life keeps them legible while leaving daylight between queued cars.
const VEHICLE_DRAW_SCALE = 1.18;

/* TraCI reports a vehicle's position at its front bumper, so a body drawn around that
   point sits half a length ahead of the vehicle. In a queue that pushes every car over
   the one in front — the line reads as one long rectangle — and a bus swings its tail
   through a corner. Place the body at the centre of the vehicle instead. */
function nearestOnPolyline(point, coords) {
  const lat = point[1] * (Math.PI / 180);
  const scaleX = 111320 * Math.max(Math.cos(lat), 0.01);
  let best = null;
  for (let index = 0; index < coords.length - 1; index += 1) {
    const ax = (coords[index][0] - point[0]) * scaleX;
    const ay = (coords[index][1] - point[1]) * 111320;
    const bx = (coords[index + 1][0] - point[0]) * scaleX;
    const by = (coords[index + 1][1] - point[1]) * 111320;
    const dx = bx - ax;
    const dy = by - ay;
    const span = dx * dx + dy * dy;
    const t = span > 0 ? Math.max(0, Math.min(1, -(ax * dx + ay * dy) / span)) : 0;
    const px = ax + dx * t;
    const py = ay + dy * t;
    const distance = Math.hypot(px, py);
    if (!best || distance < best.distance) {
      best = { distance, point: [point[0] + px / scaleX, point[1] + py / 111320] };
    }
  }
  return best;
}

/* The lane shapes are the path SUMO drives. Interpolating between two snapshots moves
   a body along a straight chord, which cuts the corner off a left or right turn;
   snapping the interpolated point onto the vehicle's own lane follows the SUMO turn
   instead. A point far from that lane is left alone, so nothing is yanked sideways. */
function snapToLane(point, laneId) {
  if (!point || !laneId) return point;
  const shape = simulationLaneShapes.get(laneId);
  if (!shape || shape.length < 2) return point;
  const hit = nearestOnPolyline(point, shape);
  return hit && hit.distance <= 25 ? hit.point : point;
}

function vehicleBodyCenter(front, angle, length) {
  if (!front) return front;
  const radians = (Number(angle) || 0) * (Math.PI / 180);
  const lat = Number(front[1]) || 0;
  const back = (Number(length) || 4.5) / 2;
  const scaleX = 111320 * Math.max(Math.cos(lat * (Math.PI / 180)), 0.01);
  return [
    front[0] - (Math.sin(radians) * back) / scaleX,
    front[1] - (Math.cos(radians) * back) / 111320
  ];
}

function vehicleFootprint(center, angle, length, width) {
  const radians = Number(angle || 0) * Math.PI / 180;
  // SUMO angle is clockwise from north. Build a true lane-aligned footprint,
  // then convert its local metre offsets to geographic coordinates.
  const forward = [Math.sin(radians), Math.cos(radians)];
  const right = [Math.cos(radians), -Math.sin(radians)];
  const cosLat = Math.cos(center[1] * Math.PI / 180);
  const corners = [[-1, -1], [1, -1], [1, 1], [-1, 1], [-1, -1]];
  return [corners.map(([along, across]) => {
    const east = forward[0] * along * length / 2 + right[0] * across * width / 2;
    const north = forward[1] * along * length / 2 + right[1] * across * width / 2;
    return [center[0] + east / (111320 * Math.max(cosLat, 0.01)), center[1] + north / 111320];
  })];
}

const vehicleClassVisibility = new Map(Object.keys(VEHICLE_RENDER).map((kind) => [kind, true]));
const vehicleInstances = new Map();
// Follow target marker. Shared material: the layer rebuilds meshes every frame
// and disposes their geometries, so the ring gets a fresh geometry but not a
// fresh material.
const FOLLOW_RING_MATERIAL = new THREE.MeshBasicMaterial({
  color: 0x35c05a,
  transparent: true,
  opacity: 0.9,
  side: THREE.DoubleSide,
  depthWrite: false
});
let selectedVehicleId = null;

// Three.js 3D Vehicle Renderer on Mapbox
let threeScene = null;
let threeCamera = null;
let threeRenderer = null;
let threeVehicleGroup = null;
let threeLayerInstalled = false;

// Reusable 3D box geometries for all vehicle classes, bicycles and pedestrians
const BOX_GEOMETRIES = {
  passenger: new THREE.BoxGeometry(1.9, 4.5, 1.5),
  taxi: new THREE.BoxGeometry(1.9, 4.5, 1.5),
  bus: new THREE.BoxGeometry(2.6, 11.5, 3.2),
  truck: new THREE.BoxGeometry(2.5, 7.5, 2.9),
  emergency: new THREE.BoxGeometry(2.2, 5.2, 2.1),
  bicycle: new THREE.BoxGeometry(0.7, 1.9, 1.2),
  motorcycle: new THREE.BoxGeometry(0.8, 2.2, 1.3),
  pedestrian: new THREE.BoxGeometry(0.65, 0.65, 1.7),
};

function create3DVehicleMesh(vehicleClass, colorHex) {
  const geo = BOX_GEOMETRIES[vehicleClass] || BOX_GEOMETRIES.passenger;
  const color = new THREE.Color(colorHex);
  const material = new THREE.MeshStandardMaterial({
    color,
    roughness: 0.35,
    metalness: 0.2
  });
  const mesh = new THREE.Mesh(geo, material);
  // Center mesh so bottom sits on the ground (z=0)
  const h = (VEHICLE_RENDER[vehicleClass] || VEHICLE_RENDER.passenger).height || 1.5;
  mesh.position.z = h / 2;
  mesh.castShadow = true;

  const container = new THREE.Group();
  container.add(mesh);
  return container;
}

const customThreeVehicleLayer = {
  id: 'three-3d-vehicles',
  type: 'custom',
  renderingMode: '3d',
  onAdd: function (mapInstance, gl) {
    threeCamera = new THREE.Camera();
    threeScene = new THREE.Scene();

    const ambientLight = new THREE.AmbientLight(0xffffff, 1.2);
    threeScene.add(ambientLight);
    const sunLight = new THREE.DirectionalLight(0xffffff, 2.0);
    sunLight.position.set(50, -80, 100).normalize();
    threeScene.add(sunLight);

    threeVehicleGroup = new THREE.Group();
    threeScene.add(threeVehicleGroup);

    threeRenderer = new THREE.WebGLRenderer({
      canvas: mapInstance.getCanvas(),
      context: gl,
      antialias: true
    });
    threeRenderer.autoClear = false;
  },
  render: function (gl, matrix) {
    if (!threeRenderer || !threeScene || !threeCamera || !liveMap) return;

    // Synchronize vehicle meshes with vehicleInstances
    if (threeVehicleGroup) {
      // Clear previous frame meshes
      while (threeVehicleGroup.children.length > 0) {
        const obj = threeVehicleGroup.children.pop();
        if (obj.geometry) obj.geometry.dispose();
      }

      for (const vehicle of vehicleInstances.values()) {
        if (!vehicle.position || !vehicleClassVisibility.get(vehicle.renderClass)) continue;

        const coords = vehicleBodyCenter(
          vehicle.position,
          vehicle.angle,
          (vehicle.length || 4.5) * VEHICLE_DRAW_SCALE
        );
        const modelAsMercator = mapboxgl.MercatorCoordinate.fromLngLat(
          { lng: coords[0], lat: coords[1] },
          0
        );

        const meterScale = modelAsMercator.meterInMercatorCoordinateUnits();
        const vMesh = create3DVehicleMesh(vehicle.renderClass, vehicle.color);

        // Position in Mapbox Mercator coordinate space
        vMesh.position.set(modelAsMercator.x, modelAsMercator.y, modelAsMercator.z);
        // Scale to real-world meters
        vMesh.scale.set(meterScale, meterScale, meterScale);
        // Rotate: SUMO heading is degrees clockwise from North.
        // Three.js Z-axis is up in Mercator, Y is South, X is East
        const rad = -(Number(vehicle.angle || 0)) * Math.PI / 180;
        vMesh.rotation.z = rad;

        threeVehicleGroup.add(vMesh);

        if (vehicle.selected) {
          const ring = new THREE.Mesh(
            new THREE.RingGeometry(3.4, 4.6, 32),
            FOLLOW_RING_MATERIAL
          );
          ring.position.set(
            modelAsMercator.x,
            modelAsMercator.y,
            modelAsMercator.z + meterScale * 0.4
          );
          ring.scale.setScalar(meterScale);
          threeVehicleGroup.add(ring);
        }
      }
    }

    const m = new THREE.Matrix4().fromArray(matrix);
    threeCamera.projectionMatrix = m;
    threeRenderer.resetState();
    threeRenderer.render(threeScene, threeCamera);
    if (liveMap) liveMap.triggerRepaint();
  }
};

/* Display headings are eased toward the telemetry heading. SUMO reports a new
   angle at every step, so a 90° turn at a junction used to snap the whole body
   round in one frame; this sweeps it over a few frames instead. */
const vehicleDisplayHeadings = new Map();
let lastHeadingFrameAt = 0;

function smoothVehicleHeading(id, target, elapsed) {
  const previous = vehicleDisplayHeadings.get(id);
  if (previous === undefined) {
    vehicleDisplayHeadings.set(id, target);
    return target;
  }
  const delta = ((target - previous + 540) % 360) - 180;
  // More than a junction turn is not a turn (lane change, spawn, run restart): snap
  // rather than spinning the body the long way round.
  if (Math.abs(delta) > 140) {
    vehicleDisplayHeadings.set(id, target);
    return target;
  }
  // Sweep at a capped angular speed (90° in ~0.19 s). The elapsed time comes from the
  // frame, not from this call: timing each vehicle separately gave almost no budget and
  // made every turn creep round.
  const maxStep = 480 * elapsed;
  const next = (previous + Math.max(-maxStep, Math.min(maxStep, delta)) + 360) % 360;
  vehicleDisplayHeadings.set(id, next);
  return next;
}

/* Headings belong to a run: a restarted run reuses ids like bus_0, and a stale
   heading would spin a brand-new vehicle to the old run's direction. */
function resetVehicleHeadings() {
  vehicleDisplayHeadings.clear();
  lastHeadingFrameAt = 0;
}

let lastVehicleRunId = null;

function refreshSimulationVehicles(state) {
  if (!liveMap || !state?.scenario) return;
  const source = liveMap.getSource('live-vehicles');
  // While a scenario switch retargets the run, snapshots still describe the old
  // network. Drawing them here put SF bodies (or none) on Monaco/Tunis. Clear and
  // wait for the retargeted run instead.
  if (state.scenario !== activeScenario) {
    vehicleInstances.clear();
    source?.setData({ type: 'FeatureCollection', features: [] });
    return;
  }
  // A new run reuses ids (car_0, bus_0), and a stale heading would spin a fresh
  // vehicle toward the previous run's direction before it has driven anywhere.
  if (state.runId !== lastVehicleRunId) {
    lastVehicleRunId = state.runId;
    resetVehicleHeadings();
  }
  vehicleInstances.clear();
  // The crash is whichever vehicle the operator's incident stopped.
  const incidentVehicleId = state.incident?.active
    ? String(state.incident.vehicleId || '')
    : '';
  const timestamp = Number(state.simulationTime || 0);
  const headingNow = performance.now();
  const headingElapsed = Math.min(0.25, Math.max(0.004, (headingNow - lastHeadingFrameAt) / 1000));
  lastHeadingFrameAt = headingNow;

  const addVehicle = (object, pedestrian = false) => {
    const renderClass = pedestrian ? 'pedestrian' : vehicleRenderClass(object);
    if (!vehicleClassVisibility.get(renderClass)) return;
    const style = VEHICLE_RENDER[renderClass];    const center = Number.isFinite(Number(object.lng)) && Number.isFinite(Number(object.lat))
      ? [Number(object.lng), Number(object.lat)]
      : simulationPoint(state.scenario, object.x, object.y);
    if (!center) return;
    const angle = Number(object.angle || 0);
    const id = String(object.id || renderClass + "-" + vehicleInstances.size);
    const displayAngle = smoothVehicleHeading(id, angle, headingElapsed);
    const waiting = Boolean(object.waiting);
    const data = {
      id, vehicleClass: renderClass, classLabel: style.label, speed: Number(object.speed || 0),
      waiting, emergency: renderClass === 'emergency', incident: id === incidentVehicleId,
      color: waiting ? '#d45c52' : style.color,
      height: style.height * VEHICLE_DRAW_SCALE, simulationTime: timestamp,
      pedestrian: pedestrian || renderClass === 'pedestrian',
    };
    vehicleInstances.set(id, { ...data, position: center, angle: displayAngle, renderClass, length: style.length, width: style.width, height: style.height, selected: id === selectedVehicleId });
  };

  (state.vehicles || []).slice(0, 5000).forEach((vehicle) => addVehicle(vehicle));
  (state.pedestrians || []).slice(0, 2000).forEach((person) => addVehicle(person, true));

  if (source) {
    const features = [...vehicleInstances.values()].map((vehicle) => ({
      type: 'Feature',
      id: vehicle.id,
      properties: {
        ...vehicle,
        angle: vehicle.angle,
        height: vehicle.height || 1.6,
        base_height: 0,
        color: vehicle.color
      },
      geometry: {
        type: 'Polygon',
        coordinates: vehicleFootprint(
          vehicleBodyCenter(
            vehicle.position,
            vehicle.angle,
            (vehicle.length || 4.5) * VEHICLE_DRAW_SCALE
          ),
          vehicle.angle,
          (vehicle.length || 4.5) * VEHICLE_DRAW_SCALE,
          (vehicle.width || 1.9) * VEHICLE_DRAW_SCALE
        )
      }
    }));
    source.setData({ type: 'FeatureCollection', features });
  }

  if (liveMap) {
    liveMap.triggerRepaint();
  }
}

function interpolateVehicleFrame(now) {
  if (!currentVehicleFrame || !liveMap) {
    // The poll can publish a frame before the map exists. Clear the handle so the
    // next updateSimulationState restarts the loop, instead of it dying silently.
    vehicleAnimationFrame = 0;
    return;
  }
  try {
  const elapsed = Math.max(0, now - vehicleFrameTime);
  // Sweep over the interval the run is actually publishing at. The stream pushes at
  // ~4 Hz while the run steps once per decision, so a fixed divisor restarted the
  // sweep mid-step and the cars crept, then snapped forward — the bounce you saw.
  const alpha = Math.min(1, elapsed / Math.max(80, vehicleFrameInterval));
  if (previousVehicleFrame && alpha < 1) {
    const priorVehicles = new Map((previousVehicleFrame.vehicles || []).map((vehicle) => [String(vehicle.id), vehicle]));
    const priorPeople = new Map((previousVehicleFrame.pedestrians || []).map((person) => [String(person.id), person]));
    const blend = (items, oldItems) => (items || []).map((item) => {
      const old = oldItems.get(String(item.id));
      if (!old) return item;
      const delta = ((Number(item.angle || 0) - Number(old.angle || 0) + 540) % 360) - 180;
      const lng = Number.isFinite(Number(old.lng)) && Number.isFinite(Number(item.lng))
        ? Number(old.lng) + (Number(item.lng) - Number(old.lng)) * alpha
        : item.lng;
      const lat = Number.isFinite(Number(old.lat)) && Number.isFinite(Number(item.lat))
        ? Number(old.lat) + (Number(item.lat) - Number(old.lat)) * alpha
        : item.lat;
      // Follow the lane through the junction rather than the straight chord.
      const [laneLng, laneLat] = snapToLane([Number(lng), Number(lat)], item.lane);
      return { ...item,
        x: Number(old.x) + (Number(item.x) - Number(old.x)) * alpha,
        y: Number(old.y) + (Number(item.y) - Number(old.y)) * alpha,
        lng: Number.isFinite(laneLng) ? laneLng : lng,
        lat: Number.isFinite(laneLat) ? laneLat : lat,
        angle: Number(old.angle || 0) + delta * alpha,
      };
    });
    refreshSimulationVehicles({ ...currentVehicleFrame, vehicles: blend(currentVehicleFrame.vehicles, priorVehicles), pedestrians: blend(currentVehicleFrame.pedestrians, priorPeople) });
  } else {
    refreshSimulationVehicles(currentVehicleFrame);
  }
  } finally {
    // Always keep the loop alive: one bad frame must not freeze every vehicle.
    vehicleAnimationFrame = window.requestAnimationFrame(interpolateVehicleFrame);
  }
}
/* Accept only frames that actually advanced the simulation. The websocket repeats the
   same snapshot four times a second, and treating each repeat as a new frame kept
   resetting the interpolation clock (the source of the stutter and the snap). */
function queueVehicleFrame(state) {
  const simTime = Number(state.simulationTime) || 0;
  const key = `${state.runId || ''}:${simTime}`;
  if (currentVehicleFrame && key === currentFrameKey) return;

  const now = performance.now();
  if (currentVehicleFrame && state.runId === currentVehicleFrame.runId) {
    const gap = now - vehicleFrameTime;
    // Ignore pauses (resume, tab wake) when learning the cadence.
    if (gap > 30 && gap < 6000) {
      vehicleFrameInterval = vehicleFrameInterval * 0.6 + gap * 0.4;
    }
    previousVehicleFrame = currentVehicleFrame;
  } else {
    // First frame of a run: nothing to move from, so draw it where it is.
    previousVehicleFrame = null;
    vehicleFrameInterval = 1000;
  }

  currentVehicleFrame = state;
  currentFrameKey = key;
  vehicleFrameTime = now;
  if (!vehicleAnimationFrame) {
    vehicleAnimationFrame = window.requestAnimationFrame(interpolateVehicleFrame);
  }
}

/* Roam follow camera. The Roam pills choose a vehicle; this keeps the Mapbox
   camera on it as the 4 Hz snapshots arrive. `pov` puts the camera inside the
   car looking down its heading, `follow` keeps a chase view above it. */
let roamFollow = null;
let roamTarget = null;
let roamSmooth = null;
let roamCameraFrame = 0;
let roamCameraAt = 0;

document.addEventListener('sumo:roamfollow', (event) => {
  const detail = event.detail;
  const next = detail && detail.id && detail.view
    ? { id: String(detail.id), view: String(detail.view) }
    : null;
  if (!next) {
    roamFollow = null;
    roamTarget = null;
    roamSmooth = null;
    selectedVehicleId = null;
    if (currentVehicleFrame) refreshSimulationVehicles(currentVehicleFrame);
    return;
  }
  // A new target should not glide the camera all the way across the network.
  if (!roamFollow || roamFollow.id !== next.id) roamSmooth = null;
  roamFollow = next;
  // The followed body carries the map's selection ring.
  selectedVehicleId = next.id;
  if (currentVehicleFrame) refreshSimulationVehicles(currentVehicleFrame);
  if (next.view === 'pov') liveMap?.setMaxPitch?.(85);
  requestRoamCameraFrame();
});

function requestRoamCameraFrame() {
  if (!roamCameraFrame) roamCameraFrame = window.requestAnimationFrame(stepRoamCamera);
}

/** Move a lng/lat by `meters` along a compass `bearing` (degrees from north). */
function offsetLngLat(lng, lat, meters, bearing) {
  const radians = (Number(bearing) || 0) * Math.PI / 180;
  const north = Math.cos(radians) * meters;
  const east = Math.sin(radians) * meters;
  return [
    lng + east / (111320 * Math.cos(lat * Math.PI / 180)),
    lat + north / 111320
  ];
}

/** Roam click: the nearest rendered vehicle within 24 screen pixels wins. */
function handleRoamVehicleClick(event) {
  const view = document.getElementById('liveMapView');
  if (!liveMap || view?.dataset.mode !== 'roam') return;
  let best = null;
  let bestDistance = 24;
  vehicleInstances.forEach((vehicle) => {
    if (vehicle.pedestrian || !vehicle.position) return;
    const projected = liveMap.project(vehicle.position);
    const distance = Math.hypot(projected.x - event.point.x, projected.y - event.point.y);
    if (distance < bestDistance) {
      best = vehicle;
      bestDistance = distance;
    }
  });
  if (!best) return;
  document.dispatchEvent(
    new CustomEvent('sumo:roamvehiclepick', { detail: { id: best.id } })
  );
}

function stepRoamCamera(now) {
  roamCameraFrame = 0;
  if (!roamFollow || !roamTarget || !liveMap) return;
  const elapsed = roamCameraAt
    ? Math.min(0.1, Math.max(0.001, (now - roamCameraAt) / 1000))
    : 0.016;
  roamCameraAt = now;
  if (!roamSmooth) {
    roamSmooth = {
      lng: roamTarget.lng,
      lat: roamTarget.lat,
      bearing: roamTarget.bearing
    };
  }
  // Frame-rate independent smoothing. The camera keeps moving between the 4 Hz
  // snapshots instead of restarting an easeTo on every publish, which was the
  // pulse that made follow look jittery at the snapshot cadence.
  const tau = roamTarget.view === 'pov' ? 0.07 : 0.16;
  const alpha = 1 - Math.exp(-elapsed / tau);
  roamSmooth.lng += (roamTarget.lng - roamSmooth.lng) * alpha;
  roamSmooth.lat += (roamTarget.lat - roamSmooth.lat) * alpha;
  const delta = ((roamTarget.bearing - roamSmooth.bearing + 540) % 360) - 180;
  roamSmooth.bearing = (roamSmooth.bearing + delta * alpha + 360) % 360;
  liveMap.jumpTo({
    center: [roamSmooth.lng, roamSmooth.lat],
    bearing: roamSmooth.bearing,
    pitch: roamTarget.view === 'pov' ? 82 : 58,
    zoom: roamTarget.view === 'pov' ? 19.2 : 17.4
  });
  if (roamFollow && roamTarget) requestRoamCameraFrame();
}

function syncRoamCamera(state) {
  if (!roamFollow || !liveMap) return;
  const vehicle = (state?.vehicles || []).find((item) => String(item.id) === roamFollow.id);
  const lng = Number(vehicle?.lng);
  const lat = Number(vehicle?.lat);
  if (!vehicle || !Number.isFinite(lng) || !Number.isFinite(lat)) {
    roamFollow = null;
    roamTarget = null;
    roamSmooth = null;
    selectedVehicleId = null;
    if (currentVehicleFrame) refreshSimulationVehicles(currentVehicleFrame);
    document.dispatchEvent(new CustomEvent('sumo:roamfollowlost'));
    return;
  }
  const bearing = Number(vehicle.angle) || 0;
  const view = roamFollow.view;
  if (view === 'pov') liveMap.setMaxPitch?.(85);
  // POV looks 9 m ahead of the car so the vehicle sits low in frame; the chase
  // view centres the vehicle itself.
  const [targetLng, targetLat] = view === 'pov'
    ? offsetLngLat(lng, lat, 9, bearing)
    : [lng, lat];
  roamTarget = { lng: targetLng, lat: targetLat, bearing, view };
  requestRoamCameraFrame();
}

function install3dVehicleLayer() {
  if (!liveMap || threeLayerInstalled) return;
  if (!liveMap.getLayer('three-3d-vehicles')) {
    try {
      liveMap.addLayer(customThreeVehicleLayer);
      threeLayerInstalled = true;
    } catch (err) {
      console.warn('Three.js vehicle layer mount error:', err);
    }
  }
}

/* The snapshot ships a 60-sample trend; the whole run history is fetched once per run
   so the mode panels see the episode, not only the last minute. */
let loadedHistoryRunId = null;
function loadRunHistory(runId) {
  if (!runId || runId === loadedHistoryRunId) return;
  loadedHistoryRunId = runId;
  simulationFetch('/api/simulation/history')
    .then((response) => (response.ok ? response.json() : null))
    .then((body) => {
      if (!body || !Array.isArray(body.samples) || !latestSimulationState) return;
      if (body.runId && body.runId !== runId) return;
      setLiveState(latestSimulationState, body.samples);
    })
    .catch(() => {});
}

function updateSimulationState(state) {
  if (!state) return;
  latestSimulationState = state;
  // The Optimize / Predict / Roam panels read the same snapshot as the map.
  setLiveState(state, state.trend);
  loadRunHistory(state.runId);
  refreshLiveGauges();
  renderLiveOps(state);
  syncRunControls(state);
  // A chart-bar scrub holds the timeline for a few seconds; otherwise the 4 Hz
  // stream would snap the playhead back to the live time immediately.
  const followingLive = performance.now() >= simulationScrubUntil;
  if (simulationClock && followingLive) {
    simulationClock.textContent = formatSimulationClock(state.simulationTime || 0);
  }
  setSimulationStatus(state.status);
  if (simulationMetrics) simulationMetrics.textContent = `${state.metrics?.vehicles || 0} vehicles · ${state.metrics?.pedestrians || 0} pedestrians`;
  renderLiveEvents(state.events);
  renderOverview(state);
  if (followingLive && simulationTime && Number.isFinite(Number(state.simulationTime))) simulationTime.value = state.simulationTime;
  paintSimulationTimeline(simulationTime?.value || 0);
  queueVehicleFrame(state);
  syncRoamCamera(state);
  refreshSimulationSignals(state);
}

function formatSimulationClock(seconds) {
  const value = ((Math.max(0, Number(seconds) || 0) + DAY_START_SECONDS) % 86400);
  return `${String(Math.floor(value / 3600)).padStart(2, '0')}:${String(Math.floor(value % 3600 / 60)).padStart(2, '0')}:${String(Math.floor(value % 60)).padStart(2, '0')}`;
}

function scrubSimulationTimeline(seconds) {
  const value = Math.max(0, Math.min(86400, Number(seconds) || 0));
  simulationScrubUntil = performance.now() + 6000;
  if (simulationTime) simulationTime.value = String(value);
  if (simulationClock) simulationClock.textContent = formatSimulationClock(value);
  paintSimulationTimeline(value);
  if (simulationBubble) simulationBubble.textContent = formatSimulationTime(value);
}

simulationTime?.addEventListener('input', () => {
  const seconds = Number(simulationTime.value);
  simulationScrubUntil = performance.now() + 6000;
  paintSimulationTimeline(seconds);
  if (simulationClock) simulationClock.textContent = formatSimulationClock(seconds);
});

document.getElementById('simulationPlay')?.addEventListener('click', async (event) => {
  /* currentTarget is null once the handler awaits, so keep the button. */
  const button = event.currentTarget;
  const status = simulationStatus?.dataset.state;
  let endpoint = 'resume';
  let options = { method: 'POST' };
  if (!status || status === 'idle' || status === 'error') {
    connectSimulationSocket();
    const scenario = simulationScenarioId();
    endpoint = 'start';
    options = { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ scenario, speed: simulationSpeed }) };
  } else if (status === 'running' || status === 'starting') {
    endpoint = 'pause';
  }
  button.classList.toggle('is-playing', endpoint !== 'pause');
  try {
    const response = await simulationFetch(`/api/simulation/${endpoint}`, options);
    updateSimulationState(await response.json());
  } catch {
    button.classList.remove('is-playing');
    showToast('Simulation service is offline.');
  }
});

function connectSimulationSocket() {
  if (simulationSocket || !window.WebSocket) return;
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
  simulationSocket = new WebSocket(`${protocol}://${window.location.hostname}:8000/ws/simulation`);
  simulationSocket.onmessage = (event) => updateSimulationState(JSON.parse(event.data));
  simulationSocket.onclose = () => { simulationSocket = null; };
}

document.getElementById('simulationStart')?.addEventListener('click', async () => {
  connectSimulationSocket();
  const scenario = simulationScenarioId();
  try {
    const response = await simulationFetch('/api/simulation/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ scenario, speed: simulationSpeed }) });
    updateSimulationState(await response.json());
  } catch {
    showToast('Simulation service is offline.');
  }
});
document.getElementById('simulationPause')?.addEventListener('click', async () => {
  const endpoint = simulationStatus?.dataset.state === 'paused' ? 'resume' : 'pause';
  try {
    const response = await simulationFetch(`/api/simulation/${endpoint}`, { method: 'POST' });
    updateSimulationState(await response.json());
  } catch {
    showToast('Simulation service is offline.');
  }
});
document.getElementById('liveSimulateIncident')?.addEventListener('click', async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    const response = await simulationFetch('/api/simulation/incident', { method: 'POST' });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      showToast(detail.detail || 'Start the live run before injecting an accident.');
      return;
    }
    // A new incident must reopen the backlog card even if the last one was closed.
    queueShownFor = null;
    updateSimulationState(await response.json());
    showToast('Accident injected — queue backlog estimate opened.');
  } catch {
    showToast('Simulation service is offline.');
  } finally {
    button.disabled = false;
  }
});

document.getElementById('simulationSpeed')?.addEventListener('click', async (event) => {
  simulationSpeed = simulationSpeed === 1 ? 5 : simulationSpeed === 5 ? 20 : 1;
  event.currentTarget.textContent = `${simulationSpeed}×`;
  try {
    const response = await simulationFetch('/api/simulation/speed', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ scenario: simulationScenarioId(), speed: simulationSpeed }) });
    updateSimulationState(await response.json());
  } catch {
    showToast('Simulation service is offline.');
  }
});

/* A scenario card starts the backend run, then hands the target scenario and the
   initial snapshot to the vanilla live map without reloading the shell. */
document.addEventListener('sumo:launch-scenario', (event) => {
  const name = event.detail?.scenario;
  if (!SCENARIOS[name]) return;
  selectLiveTab('events');
  window.setTimeout(() => {
    setScenario(name, { announce: false, retarget: false });
    if (event.detail?.state) updateSimulationState(event.detail.state);
  }, 80);
  connectSimulationSocket();
  showToast(`Live simulation started on ${SCENARIOS[name].label}.`);
});
let activeMapStyle = 'light';

const MAP_STYLES = {
  light: { preset: 'day', label: 'Day' },
  dark: { preset: 'night', label: 'Night' },
  sunset: { preset: 'dusk', label: 'Dusk' },
  dawn: { preset: 'dawn', label: 'Dawn' }
};

function getLiveScenarioView() {
  const scenario = getScenario();
  return {
    center: scenario.liveCenter,
    zoom: scenario.liveZoom,
    pitch: LIVE_VIEW.pitch,
    bearing: LIVE_VIEW.bearing
  };
}

function showLiveMapFallback(message) {
  const fallback = $('liveMapFallback');
  if (!fallback) return;
  fallback.hidden = false;
  const copy = $('liveMapFallbackMessage');
  if (copy) copy.textContent = message || 'The 3D environment could not be loaded.';
}

function hideLiveMapFallback() {
  const fallback = $('liveMapFallback');
  if (fallback) fallback.hidden = true;
}

function addLiveMapMarker(lngLat, className, html) {
  if (!liveMap) return;
  const element = document.createElement('div');
  element.className = `live-map-marker ${className}`;
  element.innerHTML = html;
  const marker = new mapboxgl.Marker({ element, anchor: 'center' }).setLngLat(lngLat).addTo(liveMap);
  liveSceneMarkers.push(marker);
}

function clearLiveMapSceneMarkers() {
  liveSceneMarkers.forEach((marker) => marker.remove());
  liveSceneMarkers = [];
}

function getScenarioFogFeature() {
  const scenario = getScenario();
  if (!['grid-2x2', 'grid-3x3'].includes(activeScenario)) return null;
  const points = [...(scenario.route || []), ...(scenario.crossRoute || [])];
  if (!points.length) return null;
  const lngs = points.map(([lng]) => lng);
  const lats = points.map(([, lat]) => lat);
  // Keep the simulated avenues visible while masking the surrounding
  // neighborhood blocks that are context-only and not SUMO lanes.
  const padLng = activeScenario === 'grid-2x2' ? 0.0018 : 0.0022;
  const padLat = activeScenario === 'grid-2x2' ? 0.0015 : 0.0018;
  const west = Math.min(...lngs) - padLng;
  const east = Math.max(...lngs) + padLng;
  const south = Math.min(...lats) - padLat;
  const north = Math.max(...lats) + padLat;
  const outer = [[-180, -85], [180, -85], [180, 85], [-180, 85], [-180, -85]];
  const hole = [[west, south], [west, north], [east, north], [east, south], [west, south]];
  return { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [outer, hole] } };
}

function refreshLiveMapFog() {
  if (!liveMap || !LIVE_FOG_ENABLED) return;
  const source = liveMap.getSource('live-fog');
  if (!source) return;
  const feature = getScenarioFogFeature();
  source.setData(feature || { type: 'FeatureCollection', features: [] });
}

function lineFeature(coordinates) {
  return {
    type: 'Feature',
    properties: {},
    geometry: { type: 'LineString', coordinates }
  };
}

function pointAlongRoute(coordinates, fraction) {
  if (!coordinates || coordinates.length < 2) return coordinates?.[0] || [0, 0];
  const segments = [];
  let total = 0;
  for (let index = 1; index < coordinates.length; index += 1) {
    const [startLng, startLat] = coordinates[index - 1];
    const [endLng, endLat] = coordinates[index];
    const length = Math.hypot(
      (endLng - startLng) * Math.cos((startLat * Math.PI) / 180),
      endLat - startLat
    );
    segments.push({ startLng, startLat, endLng, endLat, length });
    total += length;
  }
  let remaining = total * Math.min(Math.max(fraction, 0), 1);
  for (const segment of segments) {
    if (remaining <= segment.length) {
      const ratio = segment.length ? remaining / segment.length : 0;
      return [
        segment.startLng + (segment.endLng - segment.startLng) * ratio,
        segment.startLat + (segment.endLat - segment.startLat) * ratio
      ];
    }
    remaining -= segment.length;
  }
  return coordinates[coordinates.length - 1];
}

function getLiveSceneCoordinates() {
  const scenario = getScenario();
  if (!scenario.route || !scenario.crossRoute) return null;
  const at = (fraction) => pointAlongRoute(scenario.route, fraction);
  return {
    route: lineFeature(scenario.route),
    crossRoute: lineFeature(scenario.crossRoute),
    markers: [
      { point: at(0.16), className: 'is-zone', html: '<span class="live-zone-ring"></span><span class="live-zone-dot"></span>' },
      { point: at(0.46), className: 'is-incident', html: '<span class="live-marker-halo"></span><span class="live-marker-core"></span><div class="live-marker-label"><strong>Accident</strong><small>1 lane blocked</small></div>' },
      { point: at(0.82), className: 'is-queue', html: '<span class="live-marker-halo"></span><span class="live-marker-core"></span><div class="live-marker-label"><strong>Queue backlog</strong><small>+9 min delay</small></div>' },
      { point: at(0.07), className: 'is-camera', html: '<span class="live-camera-dot"></span><span class="live-camera-label">CAM 04</span>' },
      { point: at(0.64), className: 'is-camera', html: '<span class="live-camera-dot"></span>' }
    ]
  };
}

function addLiveSceneMarkers(scene) {
  if (!LIVE_SCENE_MARKERS_ENABLED) return;
  scene.markers.forEach((marker) => addLiveMapMarker(marker.point, marker.className, marker.html));
}

function refreshLiveMapScenario() {
  if (!liveMap) {
    initLiveMap();
    return;
  }
  const container = $('liveMap');
  if (container) { container.hidden = false; container.style.display = ''; }
  liveMap.flyTo({ ...getLiveScenarioView(), duration: 1000, essential: true });

  const routeSource = liveMap.getSource('live-route');
  if (!routeSource) return;
  const scene = getLiveSceneCoordinates();
  if (!scene) return;
  routeSource.setData(scene.route);
  liveMap.getSource('live-cross-route')?.setData(scene.crossRoute);
  refreshLiveMapFog();
  clearLiveMapSceneMarkers();
  addLiveSceneMarkers(scene);
}

function buildLiveMapScene() {
  if (!liveMap) return;
  hideLiveMapFallback();

  try {
    liveMap.getStyle().layers.forEach((layer) => {
      if (layer.type === 'symbol') {
        liveMap.setLayoutProperty(layer.id, 'visibility', 'none');
      }
    });
  } catch {
    // Keep the base labels if the style cannot be traversed.
  }

  try {
    // No fog: its near-white haze washed the edges of the view out into a vignette.
    liveMap.setFog(null);
    liveMap.setLight({ anchor: 'viewport', color: '#fffdf8', intensity: 0.62, position: [1.3, 212, 34] });
  } catch {
    // Older styles may not expose fog or light configuration.
  }

  if (liveMap.getSource('composite') && !liveMap.getLayer('live-3d-buildings')) {
    liveMap.addLayer({
      id: 'live-3d-buildings',
      source: 'composite',
      'source-layer': 'building',
      filter: ['==', 'extrude', 'true'],
      type: 'fill-extrusion',
      minzoom: 14.5,
      paint: {
        'fill-extrusion-color': [
          'interpolate', ['linear'], ['coalesce', ['get', 'height'], 12],
          0, '#e9ebe6',
          40, '#e1e4de',
          100, '#d8dcd5',
          180, '#cdd2ca',
          280, '#c2c8bf'
        ],
        'fill-extrusion-height': [
          'interpolate', ['linear'], ['zoom'],
          14.5, 0,
          15.15, ['coalesce', ['get', 'height'], 14]
        ],
        'fill-extrusion-base': ['coalesce', ['get', 'min_height'], 0],
        'fill-extrusion-opacity': 0.94,
        'fill-extrusion-vertical-gradient': true
      }
    });
  }

  const scene = getLiveSceneCoordinates();
  if (!scene) return;
  const { route, crossRoute } = scene;

  if (!liveMap.getSource('live-route')) {
    liveMap.addSource('live-route', { type: 'geojson', data: route });
    liveMap.addSource('live-cross-route', { type: 'geojson', data: crossRoute });
  }

  if (liveMap.getLayer('live-sumo-road')) liveMap.removeLayer('live-sumo-road');
  if (liveMap.getSource('live-sumo-road')) liveMap.removeSource('live-sumo-road');
  if (liveMap.getLayer('live-mapbox-layout')) liveMap.removeLayer('live-mapbox-layout');
  if (!liveMap.getLayer('live-sumo-road')) {
    liveMap.addLayer({
      id: 'live-sumo-road', type: 'line', source: 'live-route',
      layout: { 'line-join': 'round', 'line-cap': 'round', visibility: 'none' },
      paint: {
        'line-color': '#4f8428',
        'line-width': ['interpolate', ['linear'], ['zoom'], 14, 0.8, 17, 1.15, 20, 1.5],
        'line-opacity': 0.84
      }
    });
  }
  /* Corridor borders for the SF grids: the bbox the SUMO networks are clipped
     to, drawn as a dashed operational boundary under the route overlays. */
  if (!liveMap.getSource('live-net-bounds')) {
    liveMap.addSource('live-net-bounds', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
  }
  if (!liveMap.getLayer('live-net-bounds')) {
    liveMap.addLayer({
      id: 'live-net-bounds', type: 'line', source: 'live-net-bounds',
      paint: {
        'line-color': '#8fd14f',
        'line-width': 2.4,
        'line-opacity': 0.75,
        'line-dasharray': [2.4, 1.8]
      }
    });
  }
  if (!liveMap.getSource('live-vehicles')) {
    liveMap.addSource('live-vehicles', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
  }
  // The Three.js vehicle group is left unmounted: the flat extrusion below is the only
  // vehicle body, so nothing can overlap it or cast shading over it.
  if (!liveMap.getLayer('live-vehicles-extrusion')) {
    liveMap.addLayer({
      id: 'live-vehicles-extrusion',
      // Mapbox Standard draws its basemap buildings in the middle slot; vehicles must sit
      // above them or they are hidden as soon as the camera pitches over the buildings.
      slot: 'top',
      type: 'fill-extrusion',
      source: 'live-vehicles',
      paint: {
        // Class colour carried by the feature; ambulances alternate red/blue on every
        // state refresh so they read as a flashing emergency vehicle.
        'fill-extrusion-color': [
          // The crashed vehicle twitches orange/blue so a stopped body reads as an
          // incident, not as traffic waiting at a light.
          'case', ['get', 'incident'],
          ['case',
            ['==', ['%', ['floor', ['*', ['to-number', ['get', 'simulationTime']], 3]], 2], 0],
            '#f2913a', '#1769ff'],
          ['case', ['get', 'emergency'],
            ['case',
              ['==', ['%', ['floor', ['*', ['to-number', ['get', 'simulationTime']], 2]], 2], 0],
              '#ed2939', '#1769ff'],
          ['coalesce', ['get', 'color'], '#5b8fb0']]
        ],
        'fill-extrusion-height': ['coalesce', ['get', 'height'], 1.6],
        'fill-extrusion-base': 0,
        'fill-extrusion-opacity': 1
      }
    });
  }
  // A flat footprint of the same body, so vehicles stay visible when the camera is
  // straight above: a fill-extrusion has no on-screen height at pitch 0.
  if (!liveMap.getLayer('live-vehicles-flat')) {
    liveMap.addLayer({
      id: 'live-vehicles-flat',
      type: 'fill',
      source: 'live-vehicles',
      paint: {
        'fill-color': [
          // Same twitch as the 3D body, for the flat 2D footprint.
          'case', ['get', 'incident'],
          ['case',
            ['==', ['%', ['floor', ['*', ['to-number', ['get', 'simulationTime']], 3]], 2], 0],
            '#f2913a', '#1769ff'],
          ['case', ['get', 'emergency'],
            ['case',
              ['==', ['%', ['floor', ['*', ['to-number', ['get', 'simulationTime']], 2]], 2], 0],
              '#ed2939', '#1769ff'],
          ['coalesce', ['get', 'color'], '#5b8fb0']]
        ],
        'fill-opacity': 0.95
      }
    }, liveMap.getLayer('live-vehicles-extrusion') ? 'live-vehicles-extrusion' : undefined);
  }
  const ensureMapIcon = (name, width, height, draw) => {
    if (liveMap.hasImage(name)) return;
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    draw(canvas.getContext('2d'));
    liveMap.addImage(name, { width, height, data: new Uint8Array(canvas.getContext('2d').getImageData(0, 0, width, height).data) }, { sdf: true });
  };
  ensureMapIcon('vehicle-rectangle', 56, 32, (context) => {
    // Top-down vehicle silhouette with visible cabin, windshield and wheels.
    context.fillStyle = '#151a20';
    context.beginPath();
    context.roundRect(4, 2, 48, 28, 8);
    context.fill();
    context.fillStyle = '#fff';
    context.beginPath();
    context.moveTo(8, 7); context.lineTo(15, 5); context.lineTo(18, 3);
    context.lineTo(39, 3); context.lineTo(43, 6); context.lineTo(49, 8);
    context.lineTo(49, 24); context.lineTo(43, 26); context.lineTo(39, 29);
    context.lineTo(18, 29); context.lineTo(15, 26); context.lineTo(8, 24);
    context.closePath(); context.fill();
    context.fillStyle = '#151a20';
    context.beginPath(); context.roundRect(17, 8, 22, 16, 4); context.fill();
    context.fillStyle = '#bce8f3';
    context.beginPath(); context.moveTo(19, 9); context.lineTo(37, 9); context.lineTo(37, 14); context.lineTo(19, 14); context.closePath(); context.fill();
    context.fillStyle = '#d4edf3';
    context.fillRect(19, 17, 18, 5);
    context.fillStyle = '#ef5c52'; context.fillRect(5, 6, 3, 5); context.fillRect(5, 21, 3, 5);
    context.fillStyle = '#ffe39a'; context.fillRect(48, 6, 3, 5); context.fillRect(48, 21, 3, 5);
  });
  ensureMapIcon('bus-rectangle', 64, 34, (context) => {
    context.fillStyle = '#252a30'; context.beginPath(); context.roundRect(3, 2, 58, 30, 7); context.fill();
    context.fillStyle = '#fff'; context.beginPath(); context.roundRect(6, 3, 52, 28, 5); context.fill();
    context.fillStyle = '#bce8f3';
    for (let x = 11; x < 52; x += 9) context.fillRect(x, 6, 6, 8);
    context.fillStyle = '#f3c844'; context.fillRect(10, 17, 44, 9);
    context.fillStyle = '#292f35'; context.fillRect(10, 27, 8, 5); context.fillRect(47, 27, 8, 5);
    context.fillStyle = '#ef5c52'; context.fillRect(5, 5, 3, 5); context.fillRect(5, 24, 3, 5);
  });
  ensureMapIcon('emergency-rectangle', 56, 32, (context) => {
    context.fillStyle = '#252a30'; context.beginPath(); context.roundRect(4, 2, 48, 28, 7); context.fill();
    context.fillStyle = '#e83c49'; context.beginPath(); context.roundRect(7, 4, 42, 24, 5); context.fill();
    context.fillStyle = '#bce8f3'; context.beginPath(); context.roundRect(18, 9, 20, 13, 3); context.fill();
    context.fillStyle = '#fff'; context.fillRect(10, 14, 36, 3);
    context.fillStyle = '#3888f5'; context.fillRect(21, 5, 7, 3);
    context.fillStyle = '#fff'; context.fillRect(28, 5, 7, 3);
    context.fillStyle = '#ffe39a'; context.fillRect(48, 6, 3, 5); context.fillRect(48, 21, 3, 5);
  });
  ensureMapIcon('bicycle-rectangle', 40, 32, (context) => {
    context.strokeStyle = '#fff'; context.lineWidth = 3;
    context.beginPath(); context.arc(8, 22, 6, 0, Math.PI * 2); context.arc(31, 22, 6, 0, Math.PI * 2); context.stroke();
    context.strokeStyle = '#20262c'; context.lineWidth = 2;
    context.beginPath(); context.moveTo(8, 22); context.lineTo(16, 10); context.lineTo(22, 22); context.lineTo(8, 22); context.lineTo(27, 10); context.lineTo(31, 22); context.lineTo(22, 22); context.stroke();
    context.fillStyle = '#e7a82e'; context.beginPath(); context.arc(21, 7, 3, 0, Math.PI * 2); context.fill();
  });
  ensureMapIcon('pedestrian-rectangle', 24, 24, (context) => {
    context.fillStyle = '#26252d'; context.beginPath(); context.arc(12, 12, 11, 0, Math.PI * 2); context.fill();
    context.fillStyle = '#fff'; context.beginPath(); context.arc(12, 6, 3, 0, Math.PI * 2); context.fill();
    context.strokeStyle = '#fff'; context.lineWidth = 3; context.lineCap = 'round';
    context.beginPath(); context.moveTo(12, 10); context.lineTo(12, 17); context.moveTo(12, 12); context.lineTo(7, 15); context.moveTo(12, 12); context.lineTo(17, 14); context.moveTo(12, 17); context.lineTo(8, 22); context.moveTo(12, 17); context.lineTo(16, 22); context.stroke();
  });
  if (!liveMap.getLayer('live-vehicles')) {
    liveMap.addLayer({
      id: 'live-vehicles', type: 'symbol', source: 'live-vehicles',
      filter: ['!', ['get', 'pedestrian']],
      layout: {
        'icon-image': ['match', ['get', 'vehicleClass'], 'bus', 'bus-rectangle', 'emergency', 'emergency-rectangle', 'bicycle', 'bicycle-rectangle', 'vehicle-rectangle'],
        'icon-size': ['interpolate', ['linear'], ['zoom'], 14, 0.78, 17, 1.12],
        // The sprites are drawn nose-right (east), while SUMO's angle is clockwise from
        // north: subtracting 90 puts every body on its real heading instead of a
        // quarter-turn off, which is what made corners look like the whole fleet spun.
        'icon-rotate': ['-', ['get', 'angle'], 90],
        'icon-rotation-alignment': 'map',
        'icon-allow-overlap': true,
        'icon-ignore-placement': true
      },
      paint: {
        'icon-color': ['case', ['get', 'emergency'], ['case', ['==', ['%', ['floor', ['*', ['to-number', ['get', 'simulationTime']], 2]], 2], 0], '#ed2939', '#1769ff'], ['get', 'color']],
        'icon-halo-color': ['case', ['get', 'waiting'], '#f1b84b', '#ffffff'],
        'icon-halo-width': ['case', ['get', 'waiting'], 1.8, 0.8],
        'icon-opacity': 1
      }
    });
  }
  if (!liveMap.getLayer('live-pedestrians')) {
    liveMap.addLayer({
      id: 'live-pedestrians', type: 'symbol', source: 'live-vehicles',
      filter: ['==', ['get', 'pedestrian'], true],
      layout: {
        'icon-image': 'pedestrian-rectangle',
        'icon-size': ['interpolate', ['linear'], ['zoom'], 14, 0.9, 17, 1.2],
        'icon-rotate': ['get', 'angle'],
        'icon-rotation-alignment': 'map',
        'icon-allow-overlap': true,
        'icon-ignore-placement': true
      },
      paint: {
        'icon-color': '#7b4ce2',
        'icon-halo-color': '#ffffff',
        'icon-halo-width': 0.9,
        'icon-opacity': 1
      }
    });
  }
  // One representation only: the flat 3D extrusion. The sprite icons drawn above are
  // dropped so a vehicle never shows as two overlapping shapes (sprite + body).
  ['live-vehicles', 'live-pedestrians'].forEach((id) => {
    if (liveMap.getLayer(id)) liveMap.removeLayer(id);
  });
  loadSimulationNetwork(activeScenario);
  refreshSimulationVehicles(latestSimulationState);
  refreshSimulationSignals(latestSimulationState);
  syncVehicleFlatLayer(liveMap);

  if (!liveMap.getSource('live-fog')) {
    liveMap.addSource('live-fog', {
      type: 'geojson',
      data: getScenarioFogFeature() || { type: 'FeatureCollection', features: [] }
    });
  }

  if (!liveMap.getLayer('live-fog')) {
    liveMap.addLayer({
      id: 'live-fog',
      type: 'fill',
      source: 'live-fog',
      paint: {
        'fill-color': '#17201f',
        'fill-opacity': 0.64,
        'fill-antialias': true
      }
    });
  }

  if (!liveMap.getLayer('live-route-glow')) {
    liveMap.addLayer({
      id: 'live-route-glow',
      type: 'line',
      source: 'live-route',
      layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: { 'line-color': '#7cbd40', 'line-width': 16, 'line-blur': 12, 'line-opacity': 0.3 }
    });
  }

  if (!liveMap.getLayer('live-cross-route')) {
    liveMap.addLayer({
      id: 'live-cross-route',
      type: 'line',
      source: 'live-cross-route',
      layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: { 'line-color': '#d9bb68', 'line-width': 2.4, 'line-opacity': 0.54, 'line-dasharray': [1.1, 1.4] }
    });
  }

  if (!liveMap.getLayer('live-route-casing')) {
    liveMap.addLayer({
      id: 'live-route-casing',
      type: 'line',
      source: 'live-route',
      layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: { 'line-color': '#ffffff', 'line-width': 7, 'line-opacity': 0.72 }
    });
  }

  if (!liveMap.getLayer('live-route')) {
    liveMap.addLayer({
      id: 'live-route',
      type: 'line',
      source: 'live-route',
      layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: { 'line-color': '#e6b23d', 'line-width': 3.5, 'line-opacity': 0.98 }
    });
  }

  ['live-fog', 'live-route-glow', 'live-cross-route', 'live-route-casing', 'live-route', 'live-sumo-road'].forEach((layerId) => {
    if (liveMap.getLayer(layerId)) {
      liveMap.setLayoutProperty(
        layerId,
        'visibility',
        layerId === 'live-sumo-road'
          ? 'none'
          : (layerId === 'live-fog' ? LIVE_FOG_ENABLED : LIVE_ROUTE_OVERLAYS_ENABLED) ? 'visible' : 'none'
      );
    }
  });

  clearLiveMapSceneMarkers();
  addLiveSceneMarkers(scene);
}

const simulationNetworkCache = new Map();

/* Draw one scenario's network: the lane shapes vehicles snap to, and a lamp for
   every signalised lane. */
function applySimulationNetwork(scenario, data) {
  // Keep the lane polylines: they are the path the run drives, and the map snaps
  // moving bodies onto them so a turning vehicle follows the corner.
  simulationLaneShapes = new Map();
    (data.features || []).forEach((feature) => {
      const coords = feature?.geometry?.coordinates;
      const id = feature?.properties?.id;
      if (id && Array.isArray(coords) && coords.length >= 2) {
        simulationLaneShapes.set(id, coords);
      }
    });
    const signalLaneByKey = new Map();
    (data.signals || []).forEach((signal) => {
      (signal.lanes || []).forEach((lane) => {
        const coordinates = Number.isFinite(Number(lane.lng)) && Number.isFinite(Number(lane.lat))
          ? [Number(lane.lng), Number(lane.lat)]
          : simulationPoint(scenario, lane.x, lane.y);
        // Unknown projection: skip the lamp rather than place it in another city.
        if (!coordinates) return;
        const key = `${signal.id}:${lane.lane}`;
        const existing = signalLaneByKey.get(key);
        const linkIndices = Array.isArray(lane.linkIndices)
          ? lane.linkIndices.map(Number).filter(Number.isInteger)
          : Number.isInteger(Number(lane.index)) ? [Number(lane.index)] : [];
        if (existing) existing.linkIndices.push(...linkIndices);
        else signalLaneByKey.set(key, {
          key,
          signalId: signal.id,
          linkIndices,
          coordinates
        });
      });
    });
  setSimulationSignalMarkers([...signalLaneByKey.values()]);
  liveMap.getSource('live-net-bounds')?.setData(networkBoundsFeature(scenario, data));
  syncNetworkBoundsVisibility();
}

async function loadSimulationNetwork(scenario) {
  if (!liveMap) return;
  // Drop the previous network's lights and lane shapes before the new ones land,
  // otherwise the old scenario's markers sit over the new streets.
  setSimulationSignalMarkers([]);
  simulationLaneShapes = new Map();
  // One payload per scenario: switching back is instant, and a slow response for a
  // scenario the operator already left can never overwrite the current one.
  const cached = simulationNetworkCache.get(scenario);
  if (cached) {
    applySimulationNetwork(scenario, cached);
    return;
  }
  try {
    const response = await simulationFetch(`/api/simulation/network/${scenario}`);
    if (!response.ok) return;
    const data = await response.json();
    simulationNetworkCache.set(scenario, data);
    if (scenario !== activeScenario) return;
    applySimulationNetwork(scenario, data);
  } catch {
    // The map remains usable when the SUMO service is offline.
  }
}

/* The corridor limits we clipped the SUMO nets to: the bounding box of the
   projected lane geometry, padded so the dashed border frames the roads. */
function networkBoundsFeature(scenario, data) {
  if (!scenario.startsWith('grid-')) {
    return { type: 'FeatureCollection', features: [] };
  }
  let minLng = Infinity;
  let minLat = Infinity;
  let maxLng = -Infinity;
  let maxLat = -Infinity;
  (data.features || []).forEach((feature) => {
    const lines = feature.geometry?.type === 'MultiLineString'
      ? feature.geometry.coordinates
      : [feature.geometry?.coordinates];
    lines.forEach((line) => {
      (line || []).forEach(([lng, lat]) => {
        if (typeof lng !== 'number' || typeof lat !== 'number') return;
        minLng = Math.min(minLng, lng);
        maxLng = Math.max(maxLng, lng);
        minLat = Math.min(minLat, lat);
        maxLat = Math.max(maxLat, lat);
      });
    });
  });
  if (!Number.isFinite(minLng)) return { type: 'FeatureCollection', features: [] };
  const padLng = (maxLng - minLng) * 0.02 + 0.00008;
  const padLat = (maxLat - minLat) * 0.02 + 0.0001;
  return {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        properties: { scenario },
        geometry: {
          type: 'Polygon',
          coordinates: [[
            [minLng - padLng, minLat - padLat],
            [maxLng + padLng, minLat - padLat],
            [maxLng + padLng, maxLat + padLat],
            [minLng - padLng, maxLat + padLat],
            [minLng - padLng, minLat - padLat]
          ]]
        }
      }
    ]
  };
}

/* The corridor boundary belongs to the road layout, which is always drawn. */
function syncNetworkBoundsVisibility() {
  if (!liveMap || !liveMap.getLayer('live-net-bounds')) return;
  liveMap.setLayoutProperty(
    'live-net-bounds',
    'visibility',
    activeScenario.startsWith('grid-') ? 'visible' : 'none'
  );
}

function initLiveMap() {
  const container = $('liveMap');
  if (!container) return;
  container.hidden = false;
  container.style.display = '';
  if (liveMap) {
    liveMap.getContainer().style.display = '';
    liveMap.resize();
    return;
  }

  const token = resolveToken();
  if (!token) {
    showLiveMapFallback('Add a Mapbox token to enable the live environment.');
    return;
  }

  mapboxgl.accessToken = token;
  liveMap = new mapboxgl.Map({
    container,
    ...getLiveScenarioView(),
    antialias: true,
    attributionControl: false,
    style: 'mapbox://styles/mapbox/standard',
    config: {
      basemap: {
        lightPreset: MAP_STYLES[activeMapStyle].preset,
        showPedestrianRoads: false
      }
    },
    maxPitch: 72
  });

  // The modes layer falls back to this global when no getter is injected.
  window.sumoLiveMap = liveMap;
  liveMap.on('click', handleRoamVehicleClick);
  // The flat vehicle footprint only stands in when the camera cannot show height.
  liveMap.on('pitch', () => syncVehicleFlatLayer(liveMap));

  liveMap.addControl(new mapboxgl.AttributionControl({ compact: true }), 'bottom-right');
  liveMap.on('load', () => {
    hideLiveMapFallback();
    buildLiveMapScene();
    document.dispatchEvent(new CustomEvent('sumo:livemapready'));
  });
  liveMap.on('error', (event) => {
    const message = String(event?.error?.message || event?.message || '');
    if (/token|401|403|unauthorized|not authorized|NetworkError|failed to fetch/i.test(message)) {
      showLiveMapFallback(message || 'Mapbox token invalid or network error.');
    }
  });

  $('liveMapTokenSave')?.addEventListener('click', () => {
    const val = $('liveMapTokenInput')?.value.trim();
    if (!val) return;
    localStorage.setItem(TOKEN_KEY, val);
    hideLiveMapFallback();
    if (liveMap) { liveMap.remove(); liveMap = null; }
    ensureLiveMap();
  });

  window.setTimeout(() => liveMap?.resize(), 80);
}

function applyLiveMapStyle(styleName) {
  const style = MAP_STYLES[styleName];
  if (!style) return;
  // The operator panels follow the map scene: Day and Dawn are light scenes, so the
  // panels are light; Night and Dusk are dark scenes, so the panels are dark.
  setPanelTheme(styleName === 'light' || styleName === 'dawn');
  if (!liveMap || styleName === activeMapStyle) return;
  activeMapStyle = styleName;
  liveMap.setConfigProperty('basemap', 'lightPreset', style.preset);
  liveMap.setConfigProperty('basemap', 'showPedestrianRoads', false);
  document.querySelectorAll('[data-map-style]').forEach((option) => {
    const selected = option.dataset.mapStyle === styleName;
    option.classList.toggle('is-selected', selected);
    option.setAttribute('aria-checked', String(selected));
  });
  showToast(`${style.label} map mode applied.`);
}

function resetLiveMapView() {
  if (!liveMap) return;
  liveMap.flyTo({ ...getLiveScenarioView(), duration: 1100, essential: true });
  document.querySelector('[data-live-action="perspective"]')?.classList.add('is-active');
}

document.querySelectorAll('[data-live-map-action]').forEach((button) => {
  button.addEventListener('click', () => {
    const action = button.dataset.liveMapAction;
    if (!liveMap) {
      showLiveMapFallback('Connect a Mapbox token to use the live map.');
      return;
    }
    if (action === 'zoom-in') liveMap.zoomIn({ duration: 420 });
    if (action === 'zoom-out') liveMap.zoomOut({ duration: 420 });
    if (action === 'reset') resetLiveMapView();
  });
});

document.querySelectorAll('[data-queue-close]').forEach((button) => {
  button.addEventListener('click', () => {
    const panel = button.closest('.queue-panel');
    if (!panel) return;
    panel.classList.add('is-closing');
    window.setTimeout(() => {
      panel.hidden = true;
      panel.classList.remove('is-closing');
    }, 180);
  });
});

document.querySelector('[data-zone-close]')?.addEventListener('click', () => {
  document.querySelector('.zone-panel')?.setAttribute('hidden', '');
});

mountGauges();

/* Modes layer: Optimize / Predict / Roam panels, map layers and timeline
   bands. It reads the same scrubber and mode tabs as the rest of the map. */
initModes({
  getMap: () => liveMap,
  showToast: (message, options) => showToast(message, options),
  getScenario: () => getScenario()
});

document.querySelectorAll('[data-live-action]').forEach((button) => {
  button.addEventListener('click', () => {
    const action = button.dataset.liveAction;

    if (action === 'perspective') {
      const to3d = !liveMap || liveMap.getPitch() < 10;
      liveMap?.easeTo({ pitch: to3d ? LIVE_VIEW.pitch : 0, duration: 900 });
      button.classList.toggle('is-active', to3d);
      showToast(to3d ? '3D perspective restored.' : '2D map perspective.');
      return;
    }

    if (action === 'layers') {
      const menu = button.parentElement?.querySelector('.live-layer-menu');
      const open = menu?.hidden;
      if (menu) menu.hidden = !open;
      button.setAttribute('aria-expanded', String(Boolean(open)));
      return;
    }

    if (action === 'style') {
      const menu = button.parentElement?.querySelector('.live-style-menu');
      const open = menu?.hidden;
      if (menu) menu.hidden = !open;
      button.setAttribute('aria-expanded', String(Boolean(open)));
      return;
    }

    if (action === 'locate') {
      resetLiveMapView();
      showToast(`Recentered on ${getScenario().title}.`);
      return;
    }

    if (action === 'fullscreen') {
      const view = $('liveMapView');
      if (!document.fullscreenElement) {
        view?.requestFullscreen?.().then(() => liveMap?.resize()).catch(() => showToast('Fullscreen is unavailable in this browser.'));
      } else {
        document.exitFullscreen?.().then(() => liveMap?.resize());
      }
      return;
    }

    if (action === 'weather') {
      showToast('Clear · 24°C · wind 8 km/h NW');
      return;
    }

    if (action === 'traffic') {
      showToast('12 active traffic signals on the current corridor.');
      return;
    }

    if (action === 'dispatch') {
      showToast('Dispatch request sent to CTECC.');
      return;
    }

  });
});

/* ---------------- Live run controls (dock) ----------------
   The Control Actions card used to toggle decorative tiles and toast a message. These
   buttons drive the real session endpoints — pause/resume, one-decision step, speed,
   restart, incident, stop — and show the status the backend publishes. */

const RUN_COMMAND_TOASTS = {
  pause: (state) => (state?.status === 'paused' ? 'Run paused.' : 'Run resumed.'),
  step: () => 'Advanced one decision.',
  stop: () => 'Run stopped.',
  incident: () => 'Incident injected into the live run.',
  restart: () => 'Scenario restarted with the active controller.',
  speed: () => `Speed set to ${simulationSpeed}×.`
};

async function runSimulationCommand(command) {
  const current = latestSimulationState || {};
  let path = null;
  let body = null;
  if (command === 'pause') {
    path = current.status === 'paused' ? '/api/simulation/resume' : '/api/simulation/pause';
  } else if (command === 'step') {
    path = '/api/simulation/step';
    body = { count: 1 };
  } else if (command === 'stop') {
    path = '/api/simulation/stop';
  } else if (command === 'incident') {
    path = '/api/simulation/incident';
  } else if (command === 'restart') {
    path = '/api/simulation/start';
    body = { scenario: current.scenario || activeScenario || 'grid-2x2', speed: simulationSpeed };
  } else if (command === 'speed') {
    simulationSpeed = simulationSpeed === 1 ? 5 : simulationSpeed === 5 ? 20 : 1;
    path = '/api/simulation/speed';
    body = { speed: simulationSpeed };
    const chip = document.getElementById('simulationSpeed');
    if (chip) chip.textContent = `${simulationSpeed}×`;
  }
  if (!path) return;
  const options = body
    ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
    : { method: 'POST' };
  try {
    const response = await simulationFetch(path, options);
    const state = await response.json().catch(() => null);
    if (!response.ok) {
      showToast(state?.detail || `Command failed (HTTP ${response.status}).`);
      return;
    }
    if (state) updateSimulationState(state);
    showToast(RUN_COMMAND_TOASTS[command]?.(state) || 'Command applied.');
  } catch {
    showToast('Simulation service is offline.');
  }
}

document.querySelectorAll('[data-sim-control]').forEach((button) => {
  button.addEventListener('click', () => runSimulationCommand(button.dataset.simControl));
});

function syncRunControls(state) {
  const status = String(state?.status || 'idle');
  const live = ['running', 'paused', 'starting'].includes(status);
  const pause = document.querySelector('[data-sim-control="pause"]');
  if (pause) {
    const label = pause.querySelector('.action-label');
    if (label) label.textContent = status === 'paused' ? 'Resume' : 'Pause';
    pause.querySelector('[data-sim-icon]')?.setAttribute('href', status === 'paused' ? '#i-play' : '#i-pause');
    pause.classList.toggle('is-active', status === 'paused');
  }
  const statusValue = document.querySelector('[data-sim-value="status"]');
  if (statusValue) statusValue.textContent = status;
  const scenarioValue = document.querySelector('[data-sim-value="scenario"]');
  if (scenarioValue) {
    scenarioValue.textContent = SCENARIOS[state?.scenario]?.label || state?.scenario || 'idle';
  }
  const speedValue = document.querySelector('[data-sim-value="speed"]');
  if (speedValue) speedValue.textContent = `${simulationSpeed}×`;
  document.querySelectorAll('[data-sim-control]').forEach((button) => {
    // Restart is also how an idle session is started again.
    button.disabled = button.dataset.simControl === 'restart' ? false : !live;
  });
}

document.querySelectorAll('[data-map-style]').forEach((option) => {
  option.addEventListener('click', () => {
    applyLiveMapStyle(option.dataset.mapStyle);
    option.closest('.live-style-menu')?.setAttribute('hidden', '');
    option.closest('.live-style-picker')?.querySelector('[data-live-action="style"]')?.setAttribute('aria-expanded', 'false');
  });
});

function setVehicleClassVisibility(kind, enabled) {
  vehicleClassVisibility.set(kind, Boolean(enabled));
  if (latestSimulationState) refreshSimulationVehicles(latestSimulationState);
}

document.querySelectorAll('[data-vehicle-class]').forEach((option) => {
  option.addEventListener('click', () => {
    const enabled = option.getAttribute('aria-checked') !== 'true';
    option.setAttribute('aria-checked', String(enabled));
    option.classList.toggle('is-selected', enabled);
    setVehicleClassVisibility(option.dataset.vehicleClass, enabled);
  });
});

/* Vehicles are a fill-extrusion in 3D and a flat fill in 2D; only one shows at a time. */
function syncVehicleFlatLayer(mapbox) {
  if (!mapbox?.getLayer?.('live-vehicles-flat')) return;
  const flat = mapbox.getPitch() < 6;
  mapbox.setLayoutProperty('live-vehicles-flat', 'visibility', flat ? 'visible' : 'none');
}

function setMapLayerVisibility(layerName, enabled) {
  if (!liveMap) return;
  if (layerName === 'vehicles') {
    if (threeVehicleGroup) threeVehicleGroup.visible = enabled;
    if (liveMap.getLayer('live-vehicles-extrusion')) {
      liveMap.setLayoutProperty('live-vehicles-extrusion', 'visibility', enabled ? 'visible' : 'none');
    }
    if (liveMap.getLayer('live-vehicles-flat')) {
      liveMap.setLayoutProperty('live-vehicles-flat', 'visibility', enabled && liveMap.getPitch() < 6 ? 'visible' : 'none');
    }
    document.querySelectorAll('[data-vehicle-class]').forEach((option) => { option.disabled = !enabled; });
    simulationSignalMarkers.forEach((marker) => marker.getElement().classList.toggle('is-hidden', !enabled));
    if (liveMap) liveMap.triggerRepaint();
    return;
  }
  if (layerName === 'vehicles') {
    // Toggle vehicle / model layers produced by the SUMO live feed
    ['live-vehicles', 'live-pedestrians', 'live-vehicle-labels', 'live-vehicle-models'].forEach((id) => {
      if (liveMap.getLayer(id)) liveMap.setLayoutProperty(id, 'visibility', enabled ? 'visible' : 'none');
    });
  }
  if (layerName === 'signals') {
    simulationSignalMarkers.forEach((marker) => marker.getElement().classList.toggle('is-hidden', !enabled));
  }
}

document.querySelectorAll('[data-map-layer]').forEach((option) => {
  option.addEventListener('click', () => {
    if (option.disabled) return;
    if (!resolveToken()) {
      showToast('Add a Mapbox token to show the map layers.');
      return;
    }
    const enabled = option.getAttribute('aria-checked') !== 'true';
    option.setAttribute('aria-checked', String(enabled));
    option.classList.toggle('is-selected', enabled);
    setMapLayerVisibility(option.dataset.mapLayer, enabled);
  });
});

document.getElementById('simulationResetView')?.addEventListener('click', resetLiveMapView);

function setPanelTheme(light) {
  const enabled = liveMapView ? liveMapView.classList.toggle('live-panels-light', Boolean(light)) : Boolean(light);
  document.querySelectorAll('[data-panel-theme-toggle]').forEach((button) => {
    button.classList.toggle('is-light', enabled);
    button.setAttribute('title', enabled ? 'Panels: Light' : 'Panels: Dark');
    button.setAttribute('aria-label', enabled ? 'Switch panels to dark mode' : 'Switch panels to light mode');
    // The icon names the theme in use: sun for light panels, moon for dark ones.
    button.querySelector('use')?.setAttribute('href', enabled ? '#i-sun' : '#i-moon');
  });
  return enabled;
}

document.querySelectorAll('[data-panel-theme-toggle]').forEach((toggle) => toggle.addEventListener('click', () => {
  setPanelTheme(!liveMapView?.classList.contains('live-panels-light'));
}));

document.addEventListener('click', (event) => {
  document.querySelectorAll('.live-style-picker').forEach((picker) => {
    if (!picker.contains(event.target)) {
      picker.querySelector('.live-style-menu')?.setAttribute('hidden', '');
      picker.querySelector('[data-live-action="style"]')?.setAttribute('aria-expanded', 'false');
    }
  });
  document.querySelectorAll('.live-layer-picker').forEach((picker) => {
    if (!picker.contains(event.target)) {
      picker.querySelector('.live-layer-menu')?.setAttribute('hidden', '');
      picker.querySelector('[data-live-action="layers"]')?.setAttribute('aria-expanded', 'false');
    }
  });
});

// ---------------- Messages ----------------

const CONVERSATIONS = [
  { id: 'product-team', name: 'Product Team', initials: 'PT', tone: 'sage', pinned: true, unread: 3, time: 'Jun 11', preview: 'Let us lock scope in tomorrow standup.', group: true, status: 'online', fav: true },
  { id: 'sarah-johnson', name: 'Sarah Johnson', initials: 'SJ', tone: 'rose', pinned: true, unread: 2, time: 'Jun 11', preview: 'Can we present this to leadership on Friday?', status: 'online', fav: true },
  { id: 'leadership', name: 'Leadership', initials: 'LD', tone: 'slate', pinned: true, unread: 0, time: 'Jun 6', preview: 'Please keep the product section to 10 minutes max.', group: true, status: 'offline', fav: true },
  { id: 'sales-marketing', name: 'Sales & Marketing', initials: 'SM', tone: 'amber', unread: 1, time: 'Jun 11', preview: 'Prospect confirmed Thursday 2 PM — calendar invite sent.', group: true, status: 'offline', fav: true },
  { id: 'jessica-martinez', name: 'Jessica Martinez', initials: 'JM', tone: 'violet', unread: 1, time: 'Jun 11', preview: 'Can you confirm the headcount assumptions on slide 8?', status: 'away', fav: true },
  { id: 'lisa-nguyen', name: 'Lisa Nguyen', initials: 'LN', tone: 'teal', unread: 2, time: 'Jun 11', preview: 'Team offsite survey closes tomorrow — reminder to share with leads.', status: 'online', fav: true },
  { id: 'design-review', name: 'Design Review', initials: 'DR', tone: 'coral', unread: 4, time: 'Jun 11', preview: 'Thanks Emma — I will link this in the help center draft.', group: true, status: 'offline' },
  { id: 'emma-wilson', name: 'Emma Wilson', initials: 'EW', tone: 'blue', unread: 1, time: 'Jun 11', preview: 'Ready for your final sign-off when you have a moment.', status: 'busy', muted: true },
  { id: 'alex-thompson', name: 'Alex Thompson', initials: 'AT', tone: 'mustard', unread: 0, time: 'Jun 10', preview: 'production-rollout-runbook.pdf', status: 'away', attachment: true },
  { id: 'marcus-webb', name: 'Marcus Webb', initials: 'MW', tone: 'olive', unread: 0, time: 'Jun 10', preview: 'You: Forwarded to product — Michael will send an updated version.', status: 'away' },
  { id: 'michael-chen', name: 'Michael Chen', initials: 'MC', tone: 'indigo', unread: 0, time: 'Jun 10', preview: 'Will do — I will share the full timeline doc tomorrow.', status: 'away' },
  { id: 'david-park', name: 'David Park', initials: 'DP', tone: 'forest', unread: 0, time: 'Jun 9', preview: 'Merged. Deploying to staging now.', status: 'online' },
  { id: 'ryan-obrien', name: "Ryan O'Brien", initials: 'RO', tone: 'sky', unread: 0, time: 'Jun 8', preview: 'You: Perfect — thanks for the quick turnaround Ryan.', status: 'online', muted: true },
  { id: 'tom-bradley', name: 'Tom Bradley', initials: 'TB', tone: 'stone', unread: 0, time: 'Jun 8', preview: 'You: Approved — please countersign when ready.', status: 'offline' },
  { id: 'engineering', name: 'Engineering', initials: 'EN', tone: 'charcoal', unread: 0, time: 'Jun 7', preview: 'You: Thanks Alex — all set on our end.', group: true, status: 'offline' },
  { id: 'priya-patel', name: 'Priya Patel', initials: 'PP', tone: 'ruby', unread: 0, time: 'Jun 6', preview: 'You: Exactly what I needed — thank you Priya.', status: 'busy' }
];

let activeChatId = null;
let chatFilter = 'all';
let chatQuery = '';
const collapsedSections = { Pinned: false, Recent: false };

const escapeHtml = (value) => String(value)
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#39;');

const presenceLabel = (status) => {
  if (status === 'online') return 'Online';
  if (status === 'away') return 'Away';
  if (status === 'busy') return 'Busy';
  return 'Offline';
};

function threadFor(chat) {
  if (chat.messages) return chat.messages;
  chat.messages = [
    { from: 'them', text: `Welcome to ${chat.name}. This is the conversation preview from the SUMO messaging workspace.`, time: '09:30' },
    { from: 'me', text: 'Thanks — I am reviewing the latest update now.', time: '09:32' },
    { from: 'them', text: chat.preview, time: chat.time }
  ];
  return chat.messages;
}

function renderChatRow(chat) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = `chat-row${chat.id === activeChatId ? ' is-active' : ''}`;
  const attachment = chat.attachment ? '<svg class="ico"><use href="#i-paperclip"/></svg>' : '';
  const pin = chat.pinned ? '<svg class="ico"><use href="#i-pin"/></svg>' : '';
  const mute = chat.muted ? '<svg class="ico"><use href="#i-bell-off"/></svg>' : '';
  const unread = chat.unread ? `<span class="unread-badge">${chat.unread}</span>` : '';
  const presence = chat.status ? `<i class="presence ${chat.status}"></i>` : '';
  button.innerHTML = `
    <span class="chat-avatar tone-${chat.tone}">${escapeHtml(chat.initials)}${presence}</span>
    <span class="chat-row-body">
      <span class="chat-row-top">
        <span class="chat-name">${escapeHtml(chat.name)}</span>
        <span class="chat-time">${escapeHtml(chat.time)}</span>
      </span>
      <span class="chat-row-bottom">
        <span class="chat-preview">${attachment}${escapeHtml(chat.preview)}</span>
        <span class="chat-meta">${pin}${mute}${unread}</span>
      </span>
    </span>`;
  button.addEventListener('click', () => openConversation(chat.id));
  return button;
}

function renderChatList() {
  const list = $('chatList');
  if (!list) return;

  const matches = CONVERSATIONS.filter((chat) => {
    if (chatFilter === 'unread' && !chat.unread) return false;
    if (chatFilter === 'groups' && !chat.group) return false;
    if (chatFilter === 'favourites' && !chat.fav) return false;
    if (chatQuery && !`${chat.name} ${chat.preview}`.toLowerCase().includes(chatQuery)) return false;
    return true;
  });

  const groups = [
    ['Pinned', matches.filter((chat) => chat.pinned)],
    ['Recent', matches.filter((chat) => !chat.pinned)]
  ].filter(([, rows]) => rows.length);

  list.innerHTML = '';

  if (!groups.length) {
    list.innerHTML = '<div class="chat-no-results">No conversations found.</div>';
    return;
  }

  groups.forEach(([label, rows]) => {
    const section = document.createElement('div');
    section.className = `chat-section${collapsedSections[label] ? ' is-collapsed' : ''}`;
    const head = document.createElement('button');
    head.type = 'button';
    head.className = 'chat-section-head';
    head.setAttribute('aria-expanded', String(!collapsedSections[label]));
    head.innerHTML = `<span>${label}</span><svg class="ico"><use href="#i-chevron"/></svg>`;
    head.addEventListener('click', () => {
      collapsedSections[label] = !collapsedSections[label];
      renderChatList();
    });
    const wrap = document.createElement('div');
    wrap.className = 'chat-rows';
    rows.forEach((chat) => wrap.appendChild(renderChatRow(chat)));
    section.append(head, wrap);
    list.appendChild(section);
  });
}

function renderMessages(chat) {
  const wrap = $('chatMessages');
  if (!wrap) return;
  wrap.innerHTML = threadFor(chat).map((message) => `
    <div class="msg ${message.from === 'me' ? 'me' : 'them'}">
      <div class="msg-bubble">${escapeHtml(message.text)}</div>
      <span class="msg-time">${escapeHtml(message.time)}</span>
    </div>`).join('');
  wrap.scrollTop = wrap.scrollHeight;
}

function openConversation(id) {
  const chat = CONVERSATIONS.find((item) => item.id === id);
  if (!chat) return;
  activeChatId = id;

  const empty = $('chatEmpty');
  const thread = $('chatThread');
  if (empty) empty.hidden = true;
  if (thread) thread.hidden = false;

  const avatar = $('threadAvatar');
  if (avatar) {
    avatar.className = `chat-avatar tone-${chat.tone}`;
    avatar.innerHTML = `${escapeHtml(chat.initials)}${chat.status ? `<i class="presence ${chat.status}"></i>` : ''}`;
  }
  if ($('threadName')) $('threadName').textContent = chat.name;
  if ($('threadStatus')) $('threadStatus').textContent = presenceLabel(chat.status);

  renderMessages(chat);
  renderChatList();
  $('chatInput')?.focus();
}

document.querySelectorAll('[data-chat-tab]').forEach((tab) => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('[data-chat-tab]').forEach((node) => {
      const active = node === tab;
      node.classList.toggle('is-active', active);
      node.setAttribute('aria-selected', String(active));
    });
    chatFilter = tab.dataset.chatTab;
    renderChatList();
  });
});

$('chatSearch')?.addEventListener('input', (event) => {
  chatQuery = event.target.value.trim().toLowerCase();
  renderChatList();
});

$('inviteBtn')?.addEventListener('click', () => {
  showToast('Invite flow is ready to connect.');
});

$('chatForm')?.addEventListener('submit', (event) => {
  event.preventDefault();
  const input = $('chatInput');
  const text = input?.value.trim();
  if (!text || !activeChatId) return;
  const chat = CONVERSATIONS.find((item) => item.id === activeChatId);
  if (!chat) return;
  threadFor(chat).push({
    from: 'me',
    text,
    time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
  });
  input.value = '';
  renderMessages(chat);
  renderChatList();
});

function showToast(message, options = {}) {
  let node = document.querySelector('.app-toast');
  if (!node) {
    node = document.createElement('div');
    node.className = 'app-toast';
    node.setAttribute('role', 'status');
    document.body.appendChild(node);
  }
  node.textContent = '';
  const text = document.createElement('span');
  text.textContent = message;
  node.append(text);
  if (options.action) {
    const action = document.createElement('button');
    action.type = 'button';
    action.className = 'app-toast-action';
    action.textContent = options.action.label;
    action.addEventListener('click', () => {
      options.action.onClick?.();
      node.classList.remove('is-visible');
    });
    node.append(action);
  }
  node.classList.add('is-visible');
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(
    () => node.classList.remove('is-visible'),
    options.duration || (options.action ? 5200 : 2200)
  );
}

renderChatList();

const initialParams = new URLSearchParams(window.location.search);
if (initialParams.get('view') === 'live-map') {
  const requestedLiveTab = initialParams.get('tab');
  activeLiveTab = ['events', 'optimize', 'predict'].includes(requestedLiveTab) ? requestedLiveTab : 'events';
  setActiveNav('Live Map');
  setActiveViewTab('Dashboard');
  showView('Live Map');
  setLiveSubnavActive(activeLiveTab);
}

if (initialParams.get('view') === 'message') {
  document.querySelectorAll('.primary-nav .nav-item').forEach((node) => {
    node.classList.toggle('is-active', node.dataset.nav === 'Message');
  });
  showView('Message');
  if (initialParams.get('chat')) openConversation(initialParams.get('chat'));
}

if (initialParams.get('view') === 'settings') {
  setActiveNav('Settings');
  setActiveViewTab('Settings');
  showView('Settings');
}

const accessTabs = [...document.querySelectorAll('[data-access-tab]')];
const accessPanels = [...document.querySelectorAll('[data-access-panel]')];

function setAccessTab(name, updateUrl = true) {
  const tabName = name === 'permissions' ? 'permissions' : 'roles';
  accessTabs.forEach((tab) => {
    const active = tab.dataset.accessTab === tabName;
    tab.classList.toggle('is-active', active);
    tab.setAttribute('aria-selected', String(active));
  });
  accessPanels.forEach((panel) => {
    panel.hidden = panel.dataset.accessPanel !== tabName;
  });
  setAccessSubnavActive(tabName);
  if (accessView && !accessView.hidden) setAccessNavOpen(true);
  accessView?.scrollTo({ top: 0, behavior: 'smooth' });
  if (updateUrl) setRoute('Roles & Permissions', tabName);
}

accessTabs.forEach((tab) => {
  tab.addEventListener('click', () => setAccessTab(tab.dataset.accessTab));
});

if (initialParams.get('view') === 'access') {
  setActiveNav('Roles & Permissions');
  setActiveViewTab('Dashboard');
  showView('Roles & Permissions');
  setAccessTab(initialParams.get('tab') === 'permissions' ? 'permissions' : 'roles', false);
}

function setSettingsTab(name, updateUrl = true) {
  const tabName = document.querySelector(`[data-settings-tab="${name}"]`) ? name : 'general';
  document.querySelectorAll('[data-settings-tab]').forEach((node) => {
    const active = node.dataset.settingsTab === tabName;
    node.classList.toggle('is-active', active);
    node.setAttribute('aria-selected', String(active));
  });
  document.querySelectorAll('[data-settings-panel]').forEach((panel) => {
    panel.hidden = panel.dataset.settingsPanel !== tabName;
  });
  settingsView?.scrollTo({ top: 0, behavior: 'smooth' });
  if (updateUrl) setRoute('Settings', tabName);
}

document.querySelectorAll('[data-settings-tab]').forEach((tab) => {
  tab.addEventListener('click', () => setSettingsTab(tab.dataset.settingsTab));
});

/* ---------------- Control model picker (Settings → Models) ----------------
   The catalog lists the checkpoints the backend will accept (selected runs, raw
   training runs, registry versions); choosing one pins it in the active policy so the
   next run uses exactly those weights instead of whatever seed1.zip happens to be. */

const modelList = document.getElementById('modelList');
const modelStatus = document.getElementById('modelStatus');
const modelNetwork = document.getElementById('modelNetwork');

const escapeModelText = (value) => String(value ?? '').replace(
  /[&<>"']/g,
  (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]),
);

function describeActivePolicy(policy) {
  if (!policy || !modelStatus) return;
  const weights = policy.checkpoint ? String(policy.checkpoint).split(/[\\/]/).pop() : 'auto';
  modelStatus.textContent = `Active: ${policy.label || policy.method} · ${policy.network} · ${weights}`;
}

async function refreshActivePolicy() {
  try {
    const response = await fetch('/api/policy');
    if (response.ok) describeActivePolicy(await response.json());
  } catch { /* the panel keeps the last known policy */ }
}

function renderModelCatalog(payload) {
  if (!modelList) return;
  const models = payload.models || [];
  if (!models.length) {
    modelList.innerHTML = '<p class="model-empty">No trained checkpoint for this network yet. Train one in Models &amp; Runs, then refresh.</p>';
    return;
  }
  modelList.innerHTML = models.map((model) => {
    const seed = model.seed == null ? '—' : model.seed;
    const steps = model.timesteps ? ` · ${model.timesteps} steps` : '';
    const reason = model.available ? '' : `<small class="model-reason">${escapeModelText(model.reason || 'unavailable')}</small>`;
    return `
      <article class="model-row${model.available ? '' : ' is-unavailable'}" role="listitem">
        <div class="model-copy">
          <strong>${escapeModelText(model.label)}</strong>
          <small>${escapeModelText(model.agent)} · seed ${seed}${steps} · ${escapeModelText(model.source)}</small>
          ${reason}
        </div>
        <button type="button" class="settings-btn" data-model-id="${escapeModelText(model.id)}"${model.available ? '' : ' disabled'}>Use for simulation</button>
      </article>`;
  }).join('');
  modelList.querySelectorAll('[data-model-id]').forEach((button) => {
    button.addEventListener('click', () => {
      const model = models.find((entry) => entry.id === button.dataset.modelId);
      if (model) applyModelToPolicy(model, button);
    });
  });
}

async function applyModelToPolicy(model, button) {
  if (modelStatus) modelStatus.textContent = `Applying ${model.label}…`;
  try {
    const response = await fetch('/api/policy', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        method: model.agent,
        network: model.network,
        checkpoint: model.checkpointPath,
      }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`);
    describeActivePolicy(body);
    if (modelStatus) modelStatus.textContent += ' — restart the run to use it.';
    if (button) { button.textContent = 'Active'; button.disabled = true; }
  } catch (error) {
    if (modelStatus) modelStatus.textContent = `Could not apply: ${error.message}`;
  }
}

async function loadModelCatalog() {
  if (!modelList) return;
  const network = modelNetwork?.value || '';
  if (modelStatus) modelStatus.textContent = 'Loading trained models…';
  refreshActivePolicy();
  try {
    const query = network ? `?network=${encodeURIComponent(network)}` : '';
    const response = await fetch(`/api/models/catalog${query}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    renderModelCatalog(await response.json());
  } catch (error) {
    if (modelStatus) modelStatus.textContent = `Model catalog unavailable: ${error.message}`;
    if (modelList) modelList.innerHTML = '';
  }
}

modelNetwork?.addEventListener('change', loadModelCatalog);
document.getElementById('modelRefresh')?.addEventListener('click', loadModelCatalog);
document.querySelector('[data-settings-tab="models"]')?.addEventListener('click', loadModelCatalog);

/* ---------------- Live operation panels (Events tab) ----------------
   Zone Monitoring and the dock's Event Log used to be demo copy. They now read
   the same snapshot as the map, and show an explicit idle state before a run. */

const liveZoneStatus = document.getElementById('liveZoneStatus');
const liveZoneControl = document.getElementById('liveZoneControl');
const liveZoneIncidents = document.getElementById('liveZoneIncidents');
const liveZoneSpeed = document.getElementById('liveZoneSpeed');
const liveQueueLen = document.getElementById('liveQueueLen');
const liveDelay = document.getElementById('liveDelay');
const liveQueueKpi = liveQueueLen?.closest('.zone-kpi');
const liveDelayKpi = liveDelay?.closest('.zone-kpi');
const liveZoneVolumeValue = document.getElementById('liveZoneVolumeValue');
const liveZoneVolumeMeta = document.getElementById('liveZoneVolumeMeta');
const liveZoneCapacity = document.getElementById('liveZoneCapacity');
const liveZonePeak = document.getElementById('liveZonePeak');
const liveZoneVolumeSpeed = document.getElementById('liveZoneVolumeSpeed');
const liveZoneChartBars = document.getElementById('liveZoneChartBars');
const liveZoneChartAxis = document.getElementById('liveZoneChartAxis');
const liveZoneChartSelection = document.getElementById('liveZoneChartSelection');
const liveZoneExpand = document.getElementById('liveZoneExpand');
let zoneChartSignature = '';
let zoneVolumeExpanded = false;

const ZONE_CHART_SAMPLES = 12;
const ZONE_BUSY_RATIO = 0.12;
const ZONE_CONGESTED_RATIO = 0.4;

function zoneCongestionState(ratio) {
  if (ratio >= ZONE_CONGESTED_RATIO) return 'congested';
  if (ratio >= ZONE_BUSY_RATIO) return 'busy';
  return 'flowing';
}

function zoneSampleTip(sample) {
  const clock = String(sample.clock || '--:--:--').slice(0, 5);
  return `${clock} · ${Number(sample.vehicles) || 0} vehicles · ${Number(sample.queued) || 0} queued · ${Math.round(Number(sample.avgSpeedKmh) || 0)} km/h`;
}

function setZoneChartSelection(text) {
  if (liveZoneChartSelection) liveZoneChartSelection.textContent = text;
}

/* Bars are red/orange/green by the measured queue share of that sample, and
   rebuild only when a new history sample lands, so hover/selection survives. */
function renderZoneChart(samples, live) {
  if (!liveZoneChartBars) return;
  const slice = live ? samples.slice(-ZONE_CHART_SAMPLES) : [];
  const signature = slice.map((sample) => `${sample.t}:${sample.vehicles}:${sample.queued}`).join('|');
  if (signature === zoneChartSignature) return;
  zoneChartSignature = signature;
  if (!slice.length) {
    liveZoneChartBars.replaceChildren();
    liveZoneChartAxis?.replaceChildren();
    setZoneChartSelection('Waiting for the run.');
    return;
  }
  const peak = Math.max(...slice.map((sample) => Number(sample.vehicles) || 0), 1);
  liveZoneChartBars.replaceChildren(...slice.map((sample, index) => {
    const vehicles = Number(sample.vehicles) || 0;
    const ratio = vehicles ? (Number(sample.queued) || 0) / vehicles : 0;
    const bar = document.createElement('i');
    bar.className = `is-${zoneCongestionState(ratio)}${index === slice.length - 1 ? ' is-current' : ''}`;
    bar.style.height = `${Math.max(10, Math.round((vehicles / peak) * 100))}%`;
    bar.tabIndex = 0;
    bar.dataset.t = String(Number(sample.t) || 0);
    bar.dataset.tip = zoneSampleTip(sample);
    bar.title = bar.dataset.tip;
    bar.setAttribute('role', 'img');
    bar.setAttribute('aria-label', bar.dataset.tip);
    return bar;
  }));
  if (liveZoneChartAxis) {
    const ticks = [slice[0], slice[Math.floor(slice.length / 2)], slice[slice.length - 1]];
    liveZoneChartAxis.replaceChildren(...ticks.map((sample) => {
      const tick = document.createElement('span');
      tick.textContent = String(sample.clock || '').slice(0, 5) || '—';
      return tick;
    }));
  }
  setZoneChartSelection(zoneSampleTip(slice[slice.length - 1]));
}

if (liveZoneChartBars) {
  const showTip = (event) => {
    const bar = event.target.closest?.('i[data-tip]');
    if (bar) setZoneChartSelection(bar.dataset.tip);
  };
  liveZoneChartBars.addEventListener('pointerover', showTip);
  liveZoneChartBars.addEventListener('focusin', showTip);
  liveZoneChartBars.addEventListener('click', (event) => {
    const bar = event.target.closest?.('i[data-tip]');
    if (!bar) return;
    liveZoneChartBars.querySelectorAll('i.is-selected').forEach((node) => node.classList.remove('is-selected'));
    bar.classList.add('is-selected');
    setZoneChartSelection(bar.dataset.tip);
    scrubSimulationTimeline(Number(bar.dataset.t));
  });
  liveZoneChartBars.addEventListener('pointerout', (event) => {
    if (event.relatedTarget && liveZoneChartBars.contains(event.relatedTarget)) return;
    const last = liveZoneChartBars.querySelector('i.is-current') || liveZoneChartBars.lastElementChild;
    setZoneChartSelection(last?.dataset.tip || 'Waiting for the run.');
  });
}

liveZoneExpand?.addEventListener('click', () => {
  zoneVolumeExpanded = !zoneVolumeExpanded;
  liveZoneExpand.closest('.zone-volume')?.classList.toggle('is-expanded', zoneVolumeExpanded);
  liveZoneExpand.setAttribute('aria-expanded', String(zoneVolumeExpanded));
});
const liveDockEvents = document.getElementById('liveDockEvents');
const liveActionsSub = document.querySelector('.live-actions-card .live-dock-sub');
let latestLiveEvents = [];
const queueBacklogPanel = document.getElementById('queueBacklogPanel');
const queueLengthValue = document.getElementById('queueLengthValue');
const queueLengthDelta = document.getElementById('queueLengthDelta');
const queueDelayValue = document.getElementById('queueDelayValue');
const queueDelayDelta = document.getElementById('queueDelayDelta');
const queueBacklogNote = document.getElementById('queueBacklogNote');
let queueShownFor = null;
// The backlog card announces itself a beat after the incident instead of during it.
const QUEUE_REVEAL_DELAY_MS = 2500;
let queueRevealTimer = 0;

/* Where the backlog card should point the camera: the incident itself when the run
   published a position, else the busiest junction's stop lines, else the view centre. */
function queueIncidentPoint() {
  // The staged crash is the precise target; the event is only a fallback.
  const active = latestSimulationState?.incident;
  if (active?.active && Number.isFinite(Number(active.lng)) && Number.isFinite(Number(active.lat))) {
    return [Number(active.lng), Number(active.lat)];
  }
  const incident = latestLiveEvents.find((event) => event.kind === 'incident');
  const fromEvent = incident ? liveEventPoint(incident) : null;
  if (fromEvent) return fromEvent;
  const junctions = latestSimulationState?.metrics?.junctions || [];
  const busiest = [...junctions].sort(
    (a, b) => (Number(b.queue) || 0) - (Number(a.queue) || 0)
  )[0];
  const lanes = simulationSignalFeatures.filter((entry) => entry.signalId === busiest?.id);
  if (lanes.length) {
    const [lng, lat] = lanes.reduce(
      (acc, entry) => [acc[0] + entry.coordinates[0], acc[1] + entry.coordinates[1]],
      [0, 0]
    );
    return [lng / lanes.length, lat / lanes.length];
  }
  return getScenario()?.liveCenter || null;
}

function focusQueueLocation() {
  const point = queueIncidentPoint();
  if (!point || !liveMap) {
    showToast('No incident location published yet.');
    return;
  }
  flashLiveEventFocus(point);
  liveMap.flyTo({
    center: point,
    zoom: Math.min(18.5, Math.max(Number(liveMap.getZoom()) || 0, 16.8)),
    pitch: LIVE_VIEW.pitch,
    bearing: liveMap.getBearing(),
    duration: 900,
    essential: true
  });
}

document.getElementById('queueLocate')?.addEventListener('click', focusQueueLocation);

/* Event Log rows are map shortcuts: the published event carries no coordinate,
   so resolve one from the vehicle it names, or from the queue for congestion. */
function liveEventPoint(event) {
  const detail = event?.detail || {};
  if (Number.isFinite(Number(detail.lng)) && Number.isFinite(Number(detail.lat))) {
    return [Number(detail.lng), Number(detail.lat)];
  }
  const state = latestSimulationState;
  if (!state) return null;
  const mentioned = String(event?.message || '').match(/\(([A-Za-z]+_\d+)\)/);
  const wanted = detail.vehicleId || mentioned?.[1];
  const pool = [...(state.vehicles || []), ...(state.pedestrians || [])];
  const vehicle = wanted
    ? pool.find((item) => String(item.id) === String(wanted))
    : ['congestion', 'queue'].includes(event?.kind)
      ? pool.find((item) => item.waiting)
      : null;
  if (!vehicle) return null;
  if (Number.isFinite(Number(vehicle.lng)) && Number.isFinite(Number(vehicle.lat))) {
    return [Number(vehicle.lng), Number(vehicle.lat)];
  }
  return simulationPoint(state.scenario, vehicle.x, vehicle.y);
}

let liveEventFocusMarker = null;
let liveEventFocusTimer = 0;

/* A short-lived ring marks the event's spot, so the camera move has a target. */
function flashLiveEventFocus(lngLat) {
  if (!liveMap) return;
  window.clearTimeout(liveEventFocusTimer);
  liveEventFocusMarker?.remove();
  const element = document.createElement('div');
  element.className = 'live-map-marker is-event-focus';
  element.innerHTML = '<span class="live-focus-ring"></span><span class="live-marker-core"></span>';
  liveEventFocusMarker = new mapboxgl.Marker({ element, anchor: 'center' }).setLngLat(lngLat).addTo(liveMap);
  liveEventFocusTimer = window.setTimeout(() => {
    liveEventFocusMarker?.remove();
    liveEventFocusMarker = null;
  }, 2600);
}

function focusLiveEvent(event) {
  if (!event || !liveMap) return;
  const point = liveEventPoint(event);
  if (!point) return;
  flashLiveEventFocus(point);
  liveMap.flyTo({
    center: point,
    zoom: Math.min(18.5, Math.max(Number(liveMap.getZoom()) || 0, 16.8)),
    pitch: LIVE_VIEW.pitch,
    bearing: liveMap.getBearing(),
    duration: 900,
    essential: true
  });
}

function activateLiveEventRow(row) {
  if (!row) return;
  focusLiveEvent(latestLiveEvents.find((item) => String(item.id) === row.dataset.eventId));
}

liveDockEvents?.addEventListener('click', (event) => {
  activateLiveEventRow(event.target.closest('.live-event-row'));
});

liveDockEvents?.addEventListener('keydown', (event) => {
  if (event.key !== 'Enter' && event.key !== ' ') return;
  const row = event.target.closest('.live-event-row');
  if (!row) return;
  event.preventDefault();
  activateLiveEventRow(row);
});

function renderLiveOps(state) {
  const metrics = state.metrics || {};
  // Signal transitions are counted in the KPIs, not shown as feed entries.
  const events = (Array.isArray(state.events) ? state.events : []).filter((event) => event.kind !== 'signalChange');
  latestLiveEvents = events;
  const live = ['running', 'paused', 'starting'].includes(String(state.status));
  const vehicles = Number(metrics.vehicles) || 0;
  const queued = Number(metrics.queued) || 0;
  const critical = events.filter((event) => event.severity === 'critical').length;

  const queueRatio = vehicles ? queued / vehicles : 0;
  const trendSamples = Array.isArray(state.trend) ? state.trend : [];
  const congestionState = zoneCongestionState(queueRatio);
  liveQueueKpi?.setAttribute('data-state', live ? congestionState : 'idle');
  liveDelayKpi?.setAttribute('data-state', live ? congestionState : 'idle');
  if (liveZoneStatus) {
    const label = !live ? 'Idle' : zoneCongestionState(queueRatio) === 'congested' ? 'Congested' : zoneCongestionState(queueRatio) === 'busy' ? 'Busy' : 'Flowing';
    liveZoneStatus.lastChild.nodeValue = label;
    liveZoneStatus.dataset.state = label.toLowerCase();
  }
  if (liveZoneControl) liveZoneControl.textContent = state.policy?.label || state.method || '—';
  if (liveActionsSub?.lastChild) {
    liveActionsSub.lastChild.nodeValue = `Sector 6 · ${live ? (state.policy?.label || state.method || 'Auto') : 'Idle'}`;
  }
  if (liveZoneIncidents) liveZoneIncidents.textContent = live ? `${critical} active` : '—';
  if (liveZoneSpeed) {
    liveZoneSpeed.textContent = live ? `${Math.round(Number(metrics.avgSpeedKmh) || 0)} km/h` : '—';
  }
  if (liveQueueLen) {
    // ~7 m of road per queued vehicle: an estimate from the measured queue count.
    liveQueueLen.innerHTML = live
      ? `${escapeModelText((queued * 0.007).toFixed(1))} <small>km</small>`
      : '— <small>km</small>';
  }
  if (liveDelay) {
    liveDelay.innerHTML = live
      ? `${Math.round((Number(metrics.avgWaitingS) || 0) / 60)} <small>m</small>`
      : '— <small>m</small>';
  }

  // Volume block: arrived vehicles, measured congestion, peak queue time and
  // the run's average speed, all from the published snapshot/history.
  if (liveZoneVolumeValue) {
    const arrived = Number(metrics.arrivedTotal ?? metrics.arrived) || 0;
    liveZoneVolumeValue.innerHTML = live
      ? `${arrived >= 1000 ? (arrived / 1000).toFixed(1) : arrived}${arrived >= 1000 ? '<span>k</span>' : ''}`
      : '—';
  }
  if (liveZoneVolumeMeta) liveZoneVolumeMeta.textContent = live ? 'Vehicles cleared this run' : 'Last 24h trends';
  if (liveZoneCapacity) liveZoneCapacity.textContent = live ? `${Math.round(queueRatio * 100)}%` : '—';
  const peakSample = trendSamples.reduce(
    (best, sample) => ((Number(sample.queued) || 0) > (Number(best?.queued) || 0) ? sample : best),
    null
  );
  if (liveZonePeak) liveZonePeak.textContent = live && peakSample?.clock ? String(peakSample.clock).slice(0, 5) : '—';
  if (liveZoneVolumeSpeed) {
    liveZoneVolumeSpeed.textContent = live ? `${Math.round(Number(metrics.avgSpeedKmh) || 0)} km/h` : '—';
  }
  renderZoneChart(trendSamples, live);
  if (liveDockEvents) {
    const recent = events.slice(-8).reverse();
    liveDockEvents.innerHTML = recent.length
      ? recent.map((event) => {
          const severity = escapeModelText(event.severity || 'info');
          return `
        <li class="live-event-row is-${severity}" data-event-id="${escapeModelText(event.id || '')}" role="button" tabindex="0" aria-label="${escapeModelText(`${event.message || event.kind || 'Event'} at ${formatSimulationClock(event.t || 0)}`)}">
          <span class="live-event-dot" aria-hidden="true"></span>
          <span class="live-event-text" title="${escapeModelText(event.message || event.kind || '')}">${escapeModelText(event.message || event.kind || '')}</span>
          <time class="live-event-time">${escapeModelText(formatSimulationClock(event.t || 0))}</time>
        </li>`;
        }).join('')
      : '<li class="live-event-empty">Waiting for the run — events appear once the simulation publishes.</li>';
  }

  // Queue Backlog: starts hidden, pops up when an incident is published, and keeps
  // the two metric slots on the run's measured queue/delay plus a clearance ETA.
  const incident = [...events].reverse().find((event) => event.kind === 'incident');
  const incidentAge = incident ? (Number(state.simulationTime) || 0) - (Number(incident.t) || 0) : Infinity;
  if (queueBacklogPanel) {
    if (live && incident && incidentAge <= 300 && queueShownFor !== incident.id) {
      queueShownFor = incident.id;
      window.clearTimeout(queueRevealTimer);
      queueBacklogPanel.classList.remove('is-visible');
      queueRevealTimer = window.setTimeout(() => {
        // A later incident (or a closed card) owns the panel by now.
        if (queueShownFor !== incident.id) return;
        queueBacklogPanel.hidden = false;
        queueBacklogPanel.classList.add('is-incident');
        queueBacklogPanel.classList.remove('is-closing');
        // Paint the faded state once, so the transition has somewhere to start.
        requestAnimationFrame(() => queueBacklogPanel.classList.add('is-visible'));
      }, QUEUE_REVEAL_DELAY_MS);
    }
    const queueKm = queued * 0.007;
    const samples = Array.isArray(state.trend) ? state.trend : [];
    const oldest = samples.length > 1 ? samples[0] : null;
    const trendPct = oldest && Number(oldest.queued) > 0
      ? Math.round(((queued - Number(oldest.queued)) / Number(oldest.queued)) * 100)
      : null;
    const throughput = Number(metrics.throughputPerMin) || 0;
    const eta = throughput > 0 ? Math.max(1, Math.ceil(queued / throughput)) : null;
    if (queueLengthValue) queueLengthValue.textContent = live ? queueKm.toFixed(1) : '—';
    if (queueLengthDelta) {
      queueLengthDelta.textContent = !live
        ? '—'
        : trendPct === null
          ? `${queued} veh`
          : `${trendPct >= 0 ? '+' : ''}${trendPct}% / min`;
    }
    if (queueDelayValue) {
      queueDelayValue.textContent = live ? String(Math.round((Number(metrics.avgWaitingS) || 0) / 60)) : '—';
    }
    if (queueDelayDelta) queueDelayDelta.textContent = eta === null ? 'ETA —' : `ETA ${eta} min`;
    if (queueBacklogNote) {
      queueBacklogNote.textContent = live
        ? `${queued} vehicles queued · ${throughput.toFixed(1)} veh/min clearing`
        : 'Waiting for an incident.';
    }
  }
}

/* ---------------- Live events (Events tab) ----------------
   The backend publishes rising-edge events with the simulation state; once a run has
   any, they replace the static demo incident so the card reflects this run. */

const liveEvents = document.getElementById('liveEvents');

function renderLiveEvents(events) {
  if (!liveEvents) return;
  const list = (Array.isArray(events) ? events : []).filter((event) => event.kind !== 'signalChange');
  if (!list.length) return;
  const recent = list.slice(-6).reverse();
  liveEvents.innerHTML = recent.map((event) => `
    <li class="live-event is-${escapeModelText(event.severity || 'info')}">
      <span class="live-event-time">${escapeModelText(event.clock || '')}</span>
      <span class="live-event-copy">${escapeModelText(event.message || event.kind || '')}</span>
    </li>`).join('');
  liveEvents.hidden = false;
  document.querySelectorAll('.events-card [data-overview-static]').forEach((node) => {
    node.hidden = true;
  });
}

/* ---------------- Overview dashboard (live) ----------------
   Every panel on the Overview page reads the same `/api/simulation/state` snapshot as
   the live map: measured metrics, the session's trend series and its rising-edge events.
   A value the run cannot measure stays at "—"; nothing here is a demo constant. */

const OVERVIEW_LIVE_STATUSES = new Set(['running', 'paused', 'starting']);

function overviewSet(selector, value) {
  document.querySelectorAll(selector).forEach((node) => {
    node.textContent = value === null || value === undefined || value === '' ? '—' : String(value);
  });
}

function overviewSeries(state, key) {
  return (Array.isArray(state?.trend) ? state.trend : [])
    .map((sample) => Number(sample[key]))
    .filter((value) => Number.isFinite(value));
}

function overviewPoints(values, width = 400, height = 108, pad = 6) {
  if (!values.length) return [];
  const low = Math.min(...values);
  const high = Math.max(...values);
  const span = high - low || Math.max(1, high * 0.1);
  const step = values.length > 1 ? width / (values.length - 1) : width;
  return values.map((value, index) => [
    Number((index * step).toFixed(1)),
    Number((pad + (1 - (value - low) / span) * (height - pad * 2)).toFixed(1))
  ]);
}

function overviewLine(points) {
  return points.map(([x, y], index) => `${index ? 'L' : 'M'}${x} ${y}`).join(' ');
}

function overviewArea(points, height = 108) {
  if (!points.length) return '';
  const [lastX] = points[points.length - 1];
  const [firstX] = points[0];
  return `${overviewLine(points)} L${lastX} ${height} L${firstX} ${height} Z`;
}

function overviewDrawChart(state, prefix, key, live) {
  const line = document.querySelector(`[data-overview-chart="${prefix}-line"]`);
  const area = document.querySelector(`[data-overview-chart="${prefix}-area"]`);
  const average = document.querySelector(`[data-overview-chart="${prefix}-average"]`);
  const axis = document.querySelector(`[data-overview-chart="${prefix}-axis"]`);
  const values = live ? overviewSeries(state, key) : [];
  const points = overviewPoints(values);
  if (line) line.setAttribute('d', overviewLine(points));
  if (area) area.setAttribute('d', overviewArea(points));
  if (average) {
    if (!values.length) average.setAttribute('d', '');
    else {
      const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
      const [, y] = overviewPoints([mean, mean])[0] || [0, 54];
      average.setAttribute('d', `M0 ${y} L400 ${y}`);
    }
  }
  const samples = live && Array.isArray(state?.trend) ? state.trend : [];
  [...(axis?.querySelectorAll('span') || [])].forEach((slot, index, slots) => {
    if (!samples.length) {
      slot.textContent = '—';
      return;
    }
    const position = Math.round((index / Math.max(1, slots.length - 1)) * (samples.length - 1));
    slot.textContent = String(samples[position]?.clock || '').slice(0, 5) || '—';
  });
}

function renderOverview(state) {
  const status = String(state?.status || 'idle').toLowerCase();
  const live = OVERVIEW_LIVE_STATUSES.has(status);
  const metrics = live ? (state?.metrics || {}) : {};
  const policy = state?.policy || {};
  const clock = live ? state?.clock || '—' : '—';
  const scenario = SCENARIOS[state?.scenario];
  const events = live && Array.isArray(state?.events)
    ? state.events.filter((event) => event.kind !== 'signalChange')
    : [];

  overviewSet('[data-overview-updated]', clock);
  overviewSet('[data-overview-clock]', clock);
  overviewSet('[data-overview-scenario]', scenario?.label || state?.scenario);
  overviewSet('[data-overview-value="vehicles"]', live ? metrics.vehicles : null);
  overviewSet('[data-overview-value="speed"]', live ? metrics.avgSpeedKmh : null);
  overviewSet('[data-overview-metric="vehicles"]', live ? metrics.vehicles : null);
  overviewSet('[data-overview-metric="pedestrians"]', live ? metrics.pedestrians : null);
  overviewSet('[data-overview-metric="queued"]', live ? metrics.queued : null);
  overviewSet(
    '[data-overview-metric="queueShare"]',
    live && metrics.queueShare != null ? `${Math.round(metrics.queueShare * 100)}%` : null
  );
  overviewSet('[data-overview-metric="avgSpeedKmh"]', live ? metrics.avgSpeedKmh : null);
  overviewSet('[data-overview-metric="throughputPerMin"]', live ? metrics.throughputPerMin : null);
  overviewSet(
    '[data-overview-metric="signalPhaseChanges"]',
    live ? metrics.signalPhaseChanges : null
  );
  overviewSet('[data-overview-metric="controllerCalls"]', live ? metrics.controllerCalls : null);
  overviewSet(
    '[data-overview-decision]',
    live && metrics.lastDecisionMs != null ? `${metrics.lastDecisionMs} ms` : null
  );
  overviewSet('[data-overview-controller]', live ? policy.label || policy.method : null);
  overviewSet(
    '[data-overview-weights]',
    live ? String(policy.checkpoint || 'auto').split(/[\\/]/).pop() : null
  );
  overviewSet('[data-overview-event-id]', events.length ? events[events.length - 1].id : null);

  const badge = document.querySelector('[data-overview-status]');
  if (badge) {
    badge.textContent = status.charAt(0).toUpperCase() + status.slice(1);
    badge.className = status === 'running'
      ? 'status dispatched'
      : status === 'paused'
        ? 'status progress'
        : status === 'starting'
          ? 'status progress'
          : 'status notified';
  }

  overviewDrawChart(state, 'vehicles', 'vehicles', live);
  overviewDrawChart(state, 'speed', 'avgSpeedKmh', live);

  const staticEvent = document.querySelector('.events-card [data-overview-static]');
  if (staticEvent) staticEvent.hidden = events.length > 0;
  if (liveEvents && !events.length) {
    liveEvents.innerHTML = '';
    liveEvents.hidden = true;
  }
}

/* The dashboard polls while it is the visible view; the live map pushes the same
   snapshot over its socket, so both pages show the same numbers. */
async function refreshOverview() {
  if (!dashboardView || dashboardView.hidden) return;
  try {
    const response = await simulationFetch('/api/simulation/state');
    if (!response.ok) return;
    renderOverview(await response.json());
  } catch {
    // Backend offline: keep the last published values on screen.
  }
}

refreshOverview();
window.setInterval(refreshOverview, 2000);

function applyLocationRoute({ replaceLegacy = false } = {}) {
  const legacy = new URLSearchParams(window.location.search);
  const legacyView = legacy.get('view');
  const legacyRoute = legacyView === 'live-map'
    ? { view: 'Live Map', subtab: legacy.get('tab') || 'events' }
    : legacyView === 'access'
      ? { view: 'Roles & Permissions', subtab: legacy.get('tab') || 'roles' }
      : legacyView === 'message'
        ? { view: 'Message', subtab: null }
        : legacyView === 'settings'
          ? { view: 'Settings', subtab: 'general' }
          : null;
  const route = legacyRoute || routeFromLocation() || (() => {
    const view = legacy.get('view');
    if (view === 'live-map') return { view: 'Live Map', subtab: legacy.get('tab') || 'events' };
    if (view === 'access') return { view: 'Roles & Permissions', subtab: legacy.get('tab') || 'roles' };
    if (view === 'message') return { view: 'Message', subtab: null };
    if (view === 'settings') return { view: 'Settings', subtab: 'general' };
    return { view: 'Dashboard', subtab: null };
  })();
  navigateTo(route.view, route.subtab, { replace: replaceLegacy });
  if (route.view === 'Message' && legacy.get('chat')) openConversation(legacy.get('chat'));
}

window.addEventListener('popstate', () => applyLocationRoute({ replaceLegacy: true }));
applyLocationRoute({ replaceLegacy: true });

const avatarInput = $('avatarInput');
const avatarImage = $('avatarImage');
const avatarPlaceholder = $('avatarPlaceholder');
const avatarRemoveBtn = $('avatarRemoveBtn');
let avatarObjectUrl = '';

function clearAvatar() {
  if (avatarImage) {
    avatarImage.removeAttribute('src');
    avatarImage.hidden = true;
  }
  if (avatarPlaceholder) avatarPlaceholder.hidden = false;
  if (avatarRemoveBtn) avatarRemoveBtn.disabled = true;
  if (avatarInput) avatarInput.value = '';
  if (avatarObjectUrl) {
    URL.revokeObjectURL(avatarObjectUrl);
    avatarObjectUrl = '';
  }
}

$('avatarUploadBtn')?.addEventListener('click', () => avatarInput?.click());

avatarInput?.addEventListener('change', () => {
  const file = avatarInput.files?.[0];
  if (!file) return;
  if (file.size > 1024 * 1024) {
    showToast('Avatar must be 1MB or smaller.');
    avatarInput.value = '';
    return;
  }
  if (avatarObjectUrl) URL.revokeObjectURL(avatarObjectUrl);
  avatarObjectUrl = URL.createObjectURL(file);
  if (avatarImage) {
    avatarImage.src = avatarObjectUrl;
    avatarImage.hidden = false;
  }
  if (avatarPlaceholder) avatarPlaceholder.hidden = true;
  if (avatarRemoveBtn) avatarRemoveBtn.disabled = false;
});

avatarRemoveBtn?.addEventListener('click', clearAvatar);

const workspaceLogoInput = $('workspaceLogoInput');
const workspaceLogoImage = $('workspaceLogoImage');
const workspaceLogoPlaceholder = $('workspaceLogoPlaceholder');
const workspaceLogoRemoveBtn = $('workspaceLogoRemoveBtn');
let workspaceLogoObjectUrl = '';

function clearWorkspaceLogo() {
  if (workspaceLogoImage) {
    workspaceLogoImage.removeAttribute('src');
    workspaceLogoImage.hidden = true;
  }
  if (workspaceLogoPlaceholder) workspaceLogoPlaceholder.hidden = false;
  if (workspaceLogoRemoveBtn) workspaceLogoRemoveBtn.disabled = true;
  if (workspaceLogoInput) workspaceLogoInput.value = '';
  if (workspaceLogoObjectUrl) {
    URL.revokeObjectURL(workspaceLogoObjectUrl);
    workspaceLogoObjectUrl = '';
  }
}

$('workspaceLogoUploadBtn')?.addEventListener('click', () => workspaceLogoInput?.click());

workspaceLogoInput?.addEventListener('change', () => {
  const file = workspaceLogoInput.files?.[0];
  if (!file) return;
  if (file.size > 1024 * 1024) {
    showToast('Logo must be 1MB or smaller.');
    workspaceLogoInput.value = '';
    return;
  }
  if (workspaceLogoObjectUrl) URL.revokeObjectURL(workspaceLogoObjectUrl);
  workspaceLogoObjectUrl = URL.createObjectURL(file);
  if (workspaceLogoImage) {
    workspaceLogoImage.src = workspaceLogoObjectUrl;
    workspaceLogoImage.hidden = false;
  }
  if (workspaceLogoPlaceholder) workspaceLogoPlaceholder.hidden = true;
  if (workspaceLogoRemoveBtn) workspaceLogoRemoveBtn.disabled = false;
});

workspaceLogoRemoveBtn?.addEventListener('click', clearWorkspaceLogo);

$('personalForm')?.addEventListener('submit', (event) => {
  event.preventDefault();
  showToast('Personal information saved.');
});

const newPassword = $('newPassword');
const passwordStrength = $('passwordStrength');
const passwordRules = $('passwordRules');
const passwordTests = {
  length: (value) => value.length >= 12,
  lower: (value) => /[a-z]/.test(value),
  upper: (value) => /[A-Z]/.test(value),
  number: (value) => /\d/.test(value),
  special: (value) => /[^A-Za-z0-9]/.test(value)
};

function updatePasswordStrength() {
  const value = newPassword?.value || '';
  let met = 0;
  Object.entries(passwordTests).forEach(([rule, test]) => {
    const passed = test(value);
    if (passed) met += 1;
    const item = passwordRules?.querySelector(`[data-rule="${rule}"]`);
    if (!item) return;
    item.classList.toggle('is-met', passed);
    item.querySelector('use')?.setAttribute('href', passed ? '#i-check' : '#i-x');
  });
  if (passwordStrength) {
    passwordStrength.classList.remove('is-weak', 'is-fair', 'is-good', 'is-strong');
    if (met > 0) {
      passwordStrength.classList.add(met <= 2 ? 'is-weak' : met === 3 ? 'is-fair' : met === 4 ? 'is-good' : 'is-strong');
    }
    passwordStrength.querySelectorAll('span').forEach((bar, index) => {
      bar.classList.toggle('is-filled', index < met);
    });
  }
}

newPassword?.addEventListener('input', updatePasswordStrength);

document.querySelectorAll('[data-toggle-password]').forEach((button) => {
  button.addEventListener('click', () => {
    const input = $(button.dataset.togglePassword);
    if (!input) return;
    const show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    button.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
  });
});

$('passwordForm')?.addEventListener('submit', (event) => {
  event.preventDefault();
  const allMet = Object.values(passwordTests).every((test) => test(newPassword?.value || ''));
  if (!allMet) {
    showToast('New password does not meet all requirements.');
    return;
  }
  showToast('Email and password settings saved.');
});

document.querySelectorAll('form[data-settings-form]').forEach((form) => {
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    showToast(form.dataset.settingsForm || 'Settings saved.');
  });
});

function channelBoxes(channel) {
  return [...document.querySelectorAll(`.notify-table [data-notify-channel="${channel}"]`)];
}

function syncToggleAll() {
  document.querySelectorAll('[data-notify-toggle]').forEach((button) => {
    const boxes = channelBoxes(button.dataset.notifyToggle);
    button.setAttribute('aria-pressed', String(boxes.length > 0 && boxes.every((box) => box.checked)));
  });
}

document.querySelectorAll('[data-notify-toggle]').forEach((button) => {
  button.addEventListener('click', () => {
    const boxes = channelBoxes(button.dataset.notifyToggle);
    if (!boxes.length) return;
    const next = !boxes.every((box) => box.checked);
    boxes.forEach((box) => { box.checked = next; });
    syncToggleAll();
  });
});

document.querySelectorAll('.notify-table .check-input').forEach((box) => {
  box.addEventListener('change', syncToggleAll);
});

syncToggleAll();

document.querySelectorAll('.day-toggle button').forEach((button) => {
  button.addEventListener('click', () => {
    button.setAttribute('aria-pressed', String(button.getAttribute('aria-pressed') !== 'true'));
  });
});

$('enableNotificationsBtn')?.addEventListener('click', async () => {
  if (!('Notification' in window)) {
    showToast('Desktop notifications are not supported in this browser.');
    return;
  }
  try {
    const permission = await Notification.requestPermission();
    showToast(permission === 'granted' ? 'Desktop notifications enabled.' : 'Desktop notifications were not enabled.');
  } catch {
    showToast('Desktop notifications were not enabled.');
  }
});

$('addSocialBtn')?.addEventListener('click', () => {
  const wrap = $('socialFields');
  if (!wrap) return;
  const input = document.createElement('input');
  input.type = 'url';
  input.placeholder = 'Link to social profile';
  input.setAttribute('aria-label', 'Social profile URL');
  wrap.appendChild(input);
  input.focus();
});

document.querySelectorAll('.connected-remove').forEach((button) => {
  button.addEventListener('click', () => {
    button.closest('.connected-chip')?.remove();
    showToast('Connected account removed.');
  });
});

$('addAppBtn')?.addEventListener('click', () => showToast('App directory is ready to connect.'));

/* ---------------- Settings → Integrations ----------------
   Every card mirrors a real backend credential instead of a toggle: the state comes
   from GET /api/integrations, saving goes through PUT, and the Mapbox token is kept in
   this browser too so the map picks it up without a reload. */

const integrationCards = [...document.querySelectorAll('.integration-card[data-integration]')];

function renderIntegration(entry) {
  const card = document.querySelector(`.integration-card[data-integration="${entry.id}"]`);
  if (!card) return;
  let stored = null;
  try {
    stored = entry.id === 'mapbox' ? localStorage.getItem(TOKEN_KEY) : null;
  } catch {
    stored = null;
  }
  const connected = Boolean(entry.configured || stored);
  const badge = card.querySelector('[data-integration-status]');
  if (badge) {
    badge.classList.toggle('is-connected', connected);
    badge.querySelector('use')?.setAttribute('href', connected ? '#i-check' : '#i-link');
    const label = badge.querySelector('span');
    if (label) label.textContent = connected ? 'Connected' : 'Not configured';
  }
  card.classList.toggle('is-connected', connected);
  const detail = card.querySelector('[data-integration-detail]');
  if (detail) {
    detail.classList.remove('is-error');
    detail.textContent = entry.detail || (connected ? 'Configured.' : 'Not configured.');
  }
  const input = card.querySelector('input[name="value"]');
  if (input && entry.placeholder) input.placeholder = entry.placeholder;
  // A token saved in .env is handed to this browser once, then remembered locally.
  if (entry.id === 'mapbox' && entry.token && !stored) {
    try {
      localStorage.setItem(TOKEN_KEY, entry.token);
    } catch {
      // Private mode: the map still opens for this page load.
    }
    if (!map) {
      hideTokenPanel();
      buildMap(entry.token);
    }
  }
}

async function loadIntegrations() {
  if (!integrationCards.length) return;
  try {
    const response = await fetch('/api/integrations');
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const body = await response.json();
    (body.integrations || []).forEach(renderIntegration);
  } catch {
    integrationCards.forEach((card) => {
      const detail = card.querySelector('[data-integration-detail]');
      if (!detail) return;
      detail.classList.add('is-error');
      detail.textContent = 'Backend unreachable — start the API on :8000 to read live status.';
    });
  }
}

async function saveIntegration(id, value) {
  const card = document.querySelector(`.integration-card[data-integration="${id}"]`);
  const detail = card?.querySelector('[data-integration-detail]');
  const submit = card?.querySelector('button[type="submit"]');
  if (submit) submit.disabled = true;
  try {
    const response = await fetch('/api/integrations', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id, value })
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (detail) {
        detail.classList.add('is-error');
        detail.textContent = body.detail || `Could not save (HTTP ${response.status}).`;
      }
      return;
    }
    if (id === 'mapbox') {
      try {
        if (value) localStorage.setItem(TOKEN_KEY, value);
        else localStorage.removeItem(TOKEN_KEY);
      } catch {
        // Private mode: the map still applies the token for this page load.
      }
      if (value) {
        hideTokenPanel();
        buildMap(value);
      } else {
        setOffline(true);
        showTokenPanel('Mapbox access token required for the live map.');
      }
    }
    (body.integrations || []).forEach(renderIntegration);
    const input = card?.querySelector('input[name="value"]');
    if (input) input.value = '';
    const label = { groq: 'Groq', gemini: 'Gemini', mapbox: 'Mapbox' }[id] || id;
    showToast(`${label} ${value ? 'saved' : 'cleared'}.`);
  } catch {
    if (detail) {
      detail.classList.add('is-error');
      detail.textContent = 'Backend unreachable — nothing was saved.';
    }
  } finally {
    if (submit) submit.disabled = false;
  }
}

async function testIntegration(id, button) {
  const card = document.querySelector(`.integration-card[data-integration="${id}"]`);
  const detail = card?.querySelector('[data-integration-detail]');
  if (detail) {
    detail.classList.remove('is-error');
    detail.textContent = 'Testing the connection…';
  }
  button.disabled = true;
  try {
    const response = await fetch(`/api/integrations/${id}/test`, { method: 'POST' });
    const body = await response.json().catch(() => ({}));
    if (!detail) return;
    if (!response.ok) {
      detail.classList.add('is-error');
      detail.textContent = body.detail || `Test failed (HTTP ${response.status}).`;
      return;
    }
    detail.textContent = `${body.detail} · ${Math.round(body.latencyMs)} ms`;
  } catch {
    if (detail) {
      detail.classList.add('is-error');
      detail.textContent = 'Backend unreachable — the test did not run.';
    }
  } finally {
    button.disabled = false;
  }
}

document.querySelectorAll('[data-integration-test]').forEach((button) => {
  button.addEventListener('click', () =>
    testIntegration(button.dataset.integrationTest, button)
  );
});

document.querySelectorAll('[data-integration-form]').forEach((form) => {
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const input = form.querySelector('input[name="value"]');
    saveIntegration(form.dataset.integrationForm, (input?.value || '').trim());
  });
});

document
  .querySelectorAll('[data-settings-tab="integrations"]')
  .forEach((tab) => tab.addEventListener('click', loadIntegrations));

loadIntegrations();
$('deleteAccountBtn')?.addEventListener('click', () => showToast('Account deletion requires administrator confirmation.'));
$('inviteMemberBtn')?.addEventListener('click', () => showToast('Invite link copied to clipboard.'));

document.querySelectorAll('.member-row select').forEach((select) => {
  select.addEventListener('change', () => {
    const name = select.closest('.member-row')?.querySelector('.member-name')?.textContent.trim() || 'Member';
    showToast(`${name} role updated to ${select.value}.`);
  });
});

const spendToggle = $('spendToggle');
const spendPanel = $('spendPanel');

function syncSpendPanel() {
  if (!spendPanel) return;
  const enabled = spendToggle?.checked ?? true;
  spendPanel.classList.toggle('is-collapsed', !enabled);
  spendPanel.setAttribute('aria-hidden', String(!enabled));
}

spendToggle?.addEventListener('change', syncSpendPanel);
syncSpendPanel();

const creditToggle = $('creditToggle');
const creditPanel = $('creditPanel');

creditToggle?.addEventListener('click', () => {
  if (!creditPanel) return;
  const open = creditToggle.getAttribute('aria-expanded') !== 'true';
  creditToggle.setAttribute('aria-expanded', String(open));
  creditPanel.hidden = !open;
});

document.querySelectorAll('.addon-toggle').forEach((input) => {
  input.addEventListener('change', () => {
    showToast(`${input.dataset.addonName || 'Add-on'} ${input.checked ? 'activated' : 'deactivated'}.`);
  });
});

const accessRows = [...document.querySelectorAll('#accessUserRows tr[data-role]')];
const accessRoleFilter = $('accessRoleFilter');
const accessPlanFilter = $('accessPlanFilter');
const accessStatusFilter = $('accessStatusFilter');
const accessUserSearch = $('accessUserSearch');
const accessEmpty = $('accessEmpty');
const accessUserCount = $('accessUserCount');
const selectAllUsers = $('selectAllUsers');

function applyAccessFilters() {
  const role = accessRoleFilter?.value || '';
  const plan = accessPlanFilter?.value || '';
  const status = accessStatusFilter?.value || '';
  const query = (accessUserSearch?.value || '').trim().toLowerCase();
  let visible = 0;

  accessRows.forEach((row) => {
    const matches = (!role || row.dataset.role === role)
      && (!plan || row.dataset.plan === plan)
      && (!status || row.dataset.status === status)
      && (!query || row.textContent.toLowerCase().includes(query));
    row.hidden = !matches;
    if (matches) visible += 1;
  });

  if (accessEmpty) accessEmpty.hidden = visible !== 0;
  if (accessUserCount) {
    const filtering = Boolean(role || plan || status || query);
    accessUserCount.innerHTML = filtering
      ? `Showing <strong>${visible}</strong> of <strong>${accessRows.length}</strong> matching users`
      : `Showing <strong>1 to ${accessRows.length}</strong> of <strong>48</strong> users`;
  }
  syncAccessSelection();
}

function syncAccessSelection() {
  if (!selectAllUsers) return;
  const visibleRows = accessRows.filter((row) => !row.hidden);
  const checkedRows = visibleRows.filter((row) => row.querySelector('.row-check')?.checked);
  selectAllUsers.checked = visibleRows.length > 0 && checkedRows.length === visibleRows.length;
  selectAllUsers.indeterminate = checkedRows.length > 0 && checkedRows.length < visibleRows.length;
}

[accessRoleFilter, accessPlanFilter, accessStatusFilter].forEach((filter) => {
  filter?.addEventListener('change', applyAccessFilters);
});

accessUserSearch?.addEventListener('input', applyAccessFilters);

selectAllUsers?.addEventListener('change', () => {
  accessRows.filter((row) => !row.hidden).forEach((row) => {
    const checkbox = row.querySelector('.row-check');
    if (checkbox) checkbox.checked = selectAllUsers.checked;
  });
  if (selectAllUsers.checked) selectAllUsers.indeterminate = false;
});

document.querySelectorAll('.row-check').forEach((checkbox) => {
  checkbox.addEventListener('change', syncAccessSelection);
});

$('exportUsersBtn')?.addEventListener('click', () => {
  const rows = accessRows.filter((row) => !row.hidden).map((row) => [
    row.querySelector('.access-user strong')?.textContent.trim() || '',
    row.querySelector('.access-user small')?.textContent.trim() || '',
    row.dataset.role,
    row.dataset.plan,
    row.cells[4].textContent.trim(),
    row.dataset.status,
    row.cells[6].textContent.trim()
  ]);
  const csv = [
    ['User', 'Email', 'Role', 'Plan', 'Billing', 'Status', 'Joined Date'],
    ...rows
  ].map((cells) => cells.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(',')).join('\r\n');
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'sumo-users.csv';
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  showToast('User list exported.');
});

document.querySelectorAll('.access-pagination .page-btn').forEach((button) => {
  if (!/^\d+$/.test(button.textContent.trim())) return;
  button.addEventListener('click', () => {
    document.querySelectorAll('.access-pagination .page-btn').forEach((node) => {
      node.classList.toggle('is-active', node === button);
      node.removeAttribute('aria-current');
    });
    button.setAttribute('aria-current', 'page');
  });
});

const PERMISSION_ROLES = [
  { id: 'admin', label: 'Admin', users: 5 },
  { id: 'editor', label: 'Editor', users: 8 },
  { id: 'maintainer', label: 'Maintainer', users: 10 },
  { id: 'subscriber', label: 'Subscriber', users: 10 },
  { id: 'guest', label: 'Guest', users: 7 }
];

const PERMISSION_ACTIONS = [
  { id: 'read', label: 'Read', icon: 'i-eye' },
  { id: 'write', label: 'Write', icon: 'i-edit' },
  { id: 'create', label: 'Create', icon: 'i-plus' },
  { id: 'delete', label: 'Delete', icon: 'i-trash' }
];

const PERMISSION_RESOURCES = [
  {
    id: 'user-management',
    name: 'User Management',
    access: {
      admin: ['read', 'write', 'create', 'delete'],
      editor: ['read', 'write'],
      maintainer: ['read', 'write'],
      subscriber: ['read'],
      guest: ['read']
    }
  },
  {
    id: 'content-management',
    name: 'Content Management',
    access: {
      admin: ['read', 'write', 'create', 'delete'],
      editor: ['read', 'write'],
      maintainer: ['read', 'write'],
      subscriber: ['read'],
      guest: ['read']
    }
  },
  {
    id: 'disputes-management',
    name: 'Disputes Management',
    access: {
      admin: ['read', 'write', 'create', 'delete'],
      editor: ['read', 'write'],
      maintainer: ['read', 'write'],
      subscriber: ['read'],
      guest: []
    }
  },
  {
    id: 'database-management',
    name: 'Database Management',
    access: {
      admin: ['read', 'write', 'create', 'delete'],
      editor: ['read'],
      maintainer: ['read', 'write'],
      subscriber: [],
      guest: []
    }
  },
  {
    id: 'financial-management',
    name: 'Financial Management',
    access: {
      admin: ['read', 'write', 'create', 'delete'],
      editor: ['read'],
      maintainer: ['read'],
      subscriber: [],
      guest: []
    }
  },
  {
    id: 'reporting',
    name: 'Reporting',
    access: {
      admin: ['read', 'write', 'create', 'delete'],
      editor: ['read'],
      maintainer: ['read', 'write'],
      subscriber: ['read'],
      guest: ['read']
    }
  },
  {
    id: 'api-control',
    name: 'API Control',
    access: {
      admin: ['read', 'write', 'create', 'delete'],
      editor: ['read'],
      maintainer: ['read', 'write'],
      subscriber: [],
      guest: []
    }
  },
  {
    id: 'repository-management',
    name: 'Repository Management',
    access: {
      admin: ['read', 'write', 'create', 'delete'],
      editor: ['read', 'write'],
      maintainer: ['read', 'write'],
      subscriber: [],
      guest: []
    }
  },
  {
    id: 'payroll',
    name: 'Payroll',
    access: {
      admin: ['read', 'write', 'create', 'delete'],
      editor: [],
      maintainer: [],
      subscriber: [],
      guest: []
    }
  }
];

const permissionRows = $('permissionRows');
const permissionActiveCount = $('permissionActiveCount');
const permissionRoleCount = $('permissionRoleCount');
const permissionResourceCount = $('permissionResourceCount');

function getActivePermissionTotal() {
  return PERMISSION_RESOURCES.reduce((total, resource) => (
    total + PERMISSION_ROLES.reduce((roleTotal, role) => roleTotal + (resource.access[role.id]?.length || 0), 0)
  ), 0);
}

function updatePermissionTotal() {
  if (permissionActiveCount) permissionActiveCount.textContent = String(getActivePermissionTotal());
}

function renderPermissionRows() {
  if (!permissionRows) return;
  if (permissionRoleCount) permissionRoleCount.textContent = String(PERMISSION_ROLES.length);
  if (permissionResourceCount) permissionResourceCount.textContent = String(PERMISSION_RESOURCES.length);

  permissionRows.innerHTML = PERMISSION_RESOURCES.map((resource) => {
    const cells = PERMISSION_ROLES.map((role) => {
      const granted = resource.access[role.id] || [];
      const toggles = PERMISSION_ACTIONS.map((action) => {
        const active = granted.includes(action.id);
        const label = `${action.label}: ${resource.name} for ${role.label}. ${active ? 'Granted' : 'Not granted'}.`;
        return `<button type="button" class="perm-toggle${active ? ' is-active' : ''}" data-permission-resource="${resource.id}" data-permission-role="${role.id}" data-permission-action="${action.id}" aria-label="${label}" aria-pressed="${active}" title="${action.label} — ${active ? 'granted' : 'not granted'}"><svg class="ico"><use href="#${action.icon}"/></svg></button>`;
      }).join('');
      return `<td><div class="perm-actions">${toggles}</div></td>`;
    }).join('');

    return `<tr><td>${resource.name}</td>${cells}</tr>`;
  }).join('');

  updatePermissionTotal();
}

renderPermissionRows();

permissionRows?.addEventListener('click', (event) => {
  const button = event.target.closest('.perm-toggle');
  if (!button) return;

  const resource = PERMISSION_RESOURCES.find((item) => item.id === button.dataset.permissionResource);
  const role = PERMISSION_ROLES.find((item) => item.id === button.dataset.permissionRole);
  const action = PERMISSION_ACTIONS.find((item) => item.id === button.dataset.permissionAction);
  if (!resource || !role || !action) return;

  const granted = resource.access[role.id];
  const index = granted.indexOf(action.id);
  const active = index === -1;

  if (active) granted.push(action.id);
  else granted.splice(index, 1);

  button.classList.toggle('is-active', active);
  button.setAttribute('aria-pressed', String(active));
  button.setAttribute('aria-label', `${action.label}: ${resource.name} for ${role.label}. ${active ? 'Granted' : 'Not granted'}.`);
  button.title = `${action.label} — ${active ? 'granted' : 'not granted'}`;
  updatePermissionTotal();
});

document.querySelectorAll('[data-toast]').forEach((button) => {
  button.addEventListener('click', () => showToast(button.dataset.toast));
});

window.SUMO = {
  setMapToken(value) {
    if (!value) return;
    localStorage.setItem(TOKEN_KEY, value);
    hideTokenPanel();
    buildMap(value);
  },
  focus() {
    resetMapView();
  }
};
